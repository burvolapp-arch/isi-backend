#!/usr/bin/env python3
"""
export_snapshot.py — ISI Snapshot Materializer (v2)

Parameterized exporter that reads year-specific CSVs, computes per-country
hashes, and writes an atomic, immutable snapshot to:

    backend/snapshots/{methodology}/{year}/

This replaces the monolithic export_isi_backend_v01.py (now quarantined in _archive/).
The old exporter is not used for new snapshot production.

Usage:
    python -m backend.export_snapshot --year 2024 --methodology v1.0
    python -m backend.export_snapshot --year 2024 --methodology v1.0 --force

Protocol:
    1. Write to .tmp_{methodology}_{year}_{uuid}/
    2. Verify all hashes.
    3. Write HASH_SUMMARY.json (last file).
    4. Atomic os.rename() to final directory.
    5. Set files read-only (chmod 0o444).

Hard constraints:
    - All floats rounded via ROUND_PRECISION.
    - All JSON written with sort_keys=True.
    - All sorting includes deterministic tie-breaker.
    - If snapshot directory already exists → abort (freeze policy).
    - If any hash mismatch → abort.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import stat
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.constants import (
    COUNTRY_NAMES,
    EU27_CODES,
    EU27_SORTED,
    ISI_AXIS_KEYS,
    NUM_AXES,
    ROUND_PRECISION,
)
from backend.hashing import (
    canonical_float,
    compute_country_hash,
    compute_snapshot_hash,
)
from backend.methodology import classify, compute_composite, get_methodology
from backend.governance import (
    assess_axis_confidence,
    assess_country_governance,
    enforce_truthfulness_contract,
    PRODUCER_INVERSION_REGISTRY,
    LOGISTICS_AXIS_ID,
)
from backend.severity import (
    compute_axis_severity,
    compute_axis_data_severity,
    compute_country_severity,
    assign_comparability_tier,
)
from backend.falsification import assess_country_falsification
from backend.eligibility import (
    build_axis_readiness_matrix,
    classify_decision_usability,
    classify_empirical_alignment,
)
from backend.external_validation import build_external_validation_block
from backend.failure_visibility import build_visibility_block
from backend.reality_conflicts import detect_reality_conflicts
from backend.construct_enforcement import enforce_all_axes
from backend.benchmark_mapping_audit import (
    get_mapping_audit_registry,
    should_downgrade_alignment,
)
from backend.alignment_sensitivity import (
    run_alignment_sensitivity,
    should_downgrade_for_instability,
)
from backend.invariants import assess_country_invariants
from backend.enforcement_matrix import apply_enforcement
from backend.truth_resolver import resolve_truth
from backend.epistemic_arbiter import adjudicate as arbiter_adjudicate
from backend.publishability import assess_publishability
from backend.signing import (
    SIGNATURE_FILENAME,
    load_private_key,
    sign_snapshot_hash,
)

# ═══════════════════════════════════════════════════════════════════════════
# VERSION LOCKING — embedded in every export for reproducibility
# ═══════════════════════════════════════════════════════════════════════════

PIPELINE_VERSION = "2.0.0"
TRUTH_LOGIC_VERSION = "1.0.0"
ENFORCEMENT_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "processed"
SNAPSHOTS_ROOT = PROJECT_ROOT / "backend" / "snapshots"

# ---------------------------------------------------------------------------
# Axis registry — maps axis number to CSV metadata
#
# For v2 snapshots, we only need the final score CSV per axis.
# The full AXIS_REGISTRY with channel/audit detail remains in the
# legacy exporter for backend/v01/ backward compatibility.
# ---------------------------------------------------------------------------

AXIS_SCORE_FILES: dict[int, dict[str, str]] = {
    1: {
        "slug": "financial",
        "data_dir": "finance",
        "final_file": "finance_dependency_{year}_eu27.csv",
        "score_column": "finance_dependency",
        "country_key": "geo",
    },
    2: {
        "slug": "energy",
        "data_dir": "energy",
        "final_file": "energy_dependency_{year}_eu27.csv",
        "score_column": "energy_dependency",
        "country_key": "geo",
    },
    3: {
        "slug": "technology",
        "data_dir": "tech",
        "final_file": "tech_dependency_{year}_eu27.csv",
        "score_column": "tech_dependency",
        "country_key": "geo",
    },
    4: {
        "slug": "defense",
        "data_dir": "defense",
        "final_file": "defense_dependency_{year}_eu27.csv",
        "score_column": "defense_dependency",
        "country_key": "geo",
    },
    5: {
        "slug": "critical_inputs",
        "data_dir": "critical_inputs",
        "final_file": "critical_inputs_dependency_{year}_eu27.csv",
        "score_column": "critical_inputs_dependency",
        "country_key": "geo",
    },
    6: {
        "slug": "logistics",
        "data_dir": "logistics",
        "final_file": "logistics_freight_axis_score.csv",
        "score_column": "axis6_logistics_score",
        "country_key": "reporter",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fatal(msg: str) -> None:
    """Print error and exit."""
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(filepath: Path) -> list[dict[str, str]]:
    """Read a CSV file. Returns list of dicts. Hard-fails if file missing."""
    if not filepath.is_file():
        fatal(f"File not found: {filepath}")
    with open(filepath, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_float(val: str, context: str) -> float:
    """Parse a string to float. Hard-fail on bad values."""
    try:
        f = float(val)
    except (ValueError, TypeError):
        fatal(f"Non-numeric value '{val}' in {context}")
    if math.isnan(f) or math.isinf(f):
        fatal(f"NaN/Inf value in {context}")
    # Reject negative zero — causes JSON non-determinism
    if f == 0.0 and math.copysign(1.0, f) < 0:
        f = 0.0  # Normalize -0.0 → 0.0
    return f


def write_canonical_json(filepath: Path, data: object) -> None:
    """Write JSON in canonical form: sort_keys=True, UTF-8, trailing newline.

    This is NOT atomic by itself — the atomic protocol wraps this
    via the temp-dir → rename dance in materialize_snapshot().
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    content += "\n"
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)


def sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_axis_scores(axis_num: int, year: int) -> dict[str, float]:
    """Load final scores for one axis from CSV.

    Returns {country_code: rounded_score}.
    """
    spec = AXIS_SCORE_FILES[axis_num]
    filename = spec["final_file"].format(year=year)
    filepath = DATA_ROOT / spec["data_dir"] / filename
    rows = read_csv(filepath)

    if not rows:
        fatal(f"Axis {axis_num}: zero rows in {filepath}")

    score_col = spec["score_column"]
    country_col = spec["country_key"]
    eu27_set = EU27_CODES
    scores: dict[str, float] = {}

    for row in rows:
        geo = row.get(country_col, "").strip()
        if geo not in eu27_set:
            continue
        raw = row.get(score_col, "").strip()
        s = parse_float(raw, f"axis {axis_num}, country {geo}")
        if s < 0.0 or s > 1.0:
            fatal(f"Axis {axis_num}: score {s} out of [0,1] for {geo}")
        if geo in scores:
            fatal(f"Axis {axis_num}: duplicate country {geo}")
        scores[geo] = round(s, ROUND_PRECISION)

    missing = eu27_set - set(scores.keys())
    if missing:
        fatal(f"Axis {axis_num}: missing EU-27 countries: {sorted(missing)}")

    return scores


# ---------------------------------------------------------------------------
# Snapshot building
# ---------------------------------------------------------------------------

def build_isi_json(
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
    country_arbiter_verdicts: dict[str, dict[str, Any]] | None = None,
) -> dict:
    """Build isi.json: composite scores for all 27 countries.

    Response shape matches existing backend/v01/isi.json exactly,
    with added per-country governance_tier and ranking_eligible
    fields (TASK 2/10 hardening).
    """
    rows = []
    for country in EU27_SORTED:
        axis_scores_isi: dict[str, float] = {}
        complete = True
        for axis_num in range(1, NUM_AXES + 1):
            s = all_scores.get(axis_num, {}).get(country)
            if s is not None:
                key = ISI_AXIS_KEYS[axis_num - 1]
                axis_scores_isi[key] = s
            else:
                complete = False

        if complete and len(axis_scores_isi) == NUM_AXES:
            raw_composite = compute_composite(axis_scores_isi, methodology_version)
            composite = round(raw_composite, ROUND_PRECISION)
        else:
            composite = None

        # ── Per-country governance annotation (TASK 2/10) ──
        # Compute lightweight governance tier so the ranking list
        # is NOT undifferentiated. Full governance detail remains
        # in /country/{code}.
        producer_info = PRODUCER_INVERSION_REGISTRY.get(country, None)
        inverted_axes = producer_info["inverted_axes"] if producer_info else []
        axis_results_for_gov: list[dict[str, Any]] = []
        for axis_num in range(1, NUM_AXES + 1):
            flags: list[str] = []
            if axis_num in inverted_axes:
                flags.append("PRODUCER_INVERSION")
            has_data = all_scores.get(axis_num, {}).get(country) is not None
            axis_results_for_gov.append({
                "axis_id": axis_num,
                "data_quality_flags": flags,
                "is_proxy": axis_num == LOGISTICS_AXIS_ID,
                "validity": "VALID" if has_data else "INVALID",
            })
        # Severity for governance assessment
        gov_sev_total = sum(
            compute_axis_severity(ar["data_quality_flags"])
            for ar in axis_results_for_gov
            if ar["validity"] == "VALID"
        )
        gov_tier_strict = assign_comparability_tier(gov_sev_total)
        gov = assess_country_governance(
            country=country,
            axis_results=axis_results_for_gov,
            severity_total=gov_sev_total,
            strict_comparability_tier=gov_tier_strict,
        )

        row = {
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
        }
        for axis_num in range(1, NUM_AXES + 1):
            key = ISI_AXIS_KEYS[axis_num - 1]
            row[key] = axis_scores_isi.get(key)
        row["isi_composite"] = composite
        row["classification"] = classify(composite, methodology_version) if composite is not None else None
        row["complete"] = complete
        # ── Governance fields propagated into ranking list ──
        # If arbiter verdicts are available, use arbiter-constrained values.
        # The arbiter is the SINGLE FINAL AUTHORITY — raw governance
        # may be more permissive than what the arbiter allows.
        arbiter = (country_arbiter_verdicts or {}).get(country)
        if arbiter is not None:
            arbiter_forbidden = set(arbiter.get("final_forbidden_claims", []))
            arbiter_status = arbiter.get("final_epistemic_status", "VALID")
            # Arbiter overrides: if arbiter forbids ranking, country is not ranking-eligible
            arbiter_ranking_eligible = (
                gov["ranking_eligible"]
                and "ranking" not in arbiter_forbidden
                and arbiter_status not in ("BLOCKED", "SUPPRESSED")
            )
            arbiter_comparable = (
                gov["cross_country_comparable"]
                and "comparison" not in arbiter_forbidden
                and "country_ordering" not in arbiter_forbidden
            )
            row["governance_tier"] = gov["governance_tier"]
            row["ranking_eligible"] = arbiter_ranking_eligible
            row["cross_country_comparable"] = arbiter_comparable
            row["arbiter_status"] = arbiter_status
            row["dominant_constraint"] = arbiter.get("dominant_constraint")
            row["dominant_constraint_source"] = arbiter.get("dominant_constraint_source")
        else:
            # Fallback: raw governance (backward-compatible for tests
            # that call build_isi_json without arbiter verdicts)
            row["governance_tier"] = gov["governance_tier"]
            row["ranking_eligible"] = gov["ranking_eligible"]
            row["cross_country_comparable"] = gov["cross_country_comparable"]
            row["arbiter_status"] = None
        # ── Layer 3: decision usability class for ISI ranking context ──
        try:
            usability = classify_decision_usability(
                country=country, governance_result=gov,
            )
            row["decision_usability_class"] = usability["decision_usability_class"]
            row["policy_usability_class"] = usability.get(
                "policy_usability_class", "NOT_ASSESSED"
            )
        except Exception:
            row["decision_usability_class"] = "NOT_ASSESSED"
            row["policy_usability_class"] = "NOT_ASSESSED"
        rows.append(row)

    # Sort: descending by composite, tie-break alphabetical by country (D-2 fix)
    rows.sort(key=lambda x: (-(x["isi_composite"] if x["isi_composite"] is not None else -1.0), x["country"]))

    vals = [r["isi_composite"] for r in rows if r["isi_composite"] is not None]

    return {
        "version": methodology_version,
        "window": data_window,
        "aggregation_rule": "unweighted_arithmetic_mean",
        "formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
        "countries_complete": len(vals),
        "countries_total": len(EU27_SORTED),
        "statistics": {
            "min": round(min(vals), ROUND_PRECISION) if vals else None,
            "max": round(max(vals), ROUND_PRECISION) if vals else None,
            "mean": round(sum(vals) / len(vals), ROUND_PRECISION) if vals else None,
        },
        "_truthfulness_caveat": (
            "Each country row now includes governance_tier, ranking_eligible, "
            "cross_country_comparable, and policy_usability_class fields. "
            "Countries at different governance tiers should NOT be directly "
            "compared. Use /country/{code} for full governance context "
            "including per-axis confidence, structural limitations, "
            "comparability analysis, and external validation. "
            "'Ranking-eligible' is a THEORETICAL classification based on "
            "internal governance rules, not an empirical quality guarantee."
        ),
        "external_validation_status": _get_external_validation_status(),
        "countries": rows,
    }


def _get_external_validation_status() -> dict[str, Any]:
    """Return summary of external validation framework status for ISI JSON.

    Wraps external_validation.get_external_validation_status() with
    graceful error handling.
    """
    try:
        from backend.external_validation import get_external_validation_status
        return get_external_validation_status()
    except Exception:
        return {
            "status": "NOT_AVAILABLE",
            "error": "External validation status unavailable",
        }


def build_country_json(
    country: str,
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
) -> dict:
    """Build per-country detail JSON.

    TRUTHFULNESS REQUIREMENT: Every country JSON MUST include:
    - Per-axis confidence assessments
    - Country governance tier
    - Structural limitations
    - Ranking/comparison eligibility
    - Producer-inversion status
    - Logistics coverage status

    No export path may produce a "clean-looking" result that omits
    critical governance metadata.
    """
    name = COUNTRY_NAMES.get(country, country)
    axes_detail = []
    score_sum = 0.0
    axes_with_data = 0
    axis_severity_tuples: list[tuple[int, str, float]] = []

    # Check producer inversion from registry
    producer_info = PRODUCER_INVERSION_REGISTRY.get(country, None)
    inverted_axes = producer_info["inverted_axes"] if producer_info else []

    for axis_num in range(1, NUM_AXES + 1):
        slug = AXIS_SCORE_FILES[axis_num]["slug"]
        score = all_scores.get(axis_num, {}).get(country)

        # Build data quality flags for this axis in export context
        flags: list[str] = []
        if axis_num in inverted_axes:
            flags.append("PRODUCER_INVERSION")

        has_data = score is not None
        is_proxy = False  # v2 snapshots don't have proxy detection yet

        # Axis confidence assessment
        confidence = assess_axis_confidence(
            axis_id=axis_num,
            data_quality_flags=flags,
            is_proxy=is_proxy,
            has_data=has_data,
        )

        axis_entry: dict[str, Any] = {
            "axis_id": axis_num,
            "axis_slug": slug,
            "confidence": confidence,
        }

        if score is not None:
            axis_entry["score"] = score
            axis_entry["classification"] = classify(score, methodology_version)
            axis_entry["data_quality_flags"] = flags
            axis_entry["validity"] = "VALID"
            score_sum += score
            axes_with_data += 1

            # Compute severity for governance
            sev = compute_axis_severity(flags)
            axis_severity_tuples.append((axis_num, slug, sev))
            axis_entry["degradation_severity"] = sev
        else:
            axis_entry["score"] = None
            axis_entry["classification"] = None
            axis_entry["data_quality_flags"] = ["INVALID_AXIS"]
            axis_entry["validity"] = "INVALID"
            axis_entry["degradation_severity"] = 0.0

        axes_detail.append(axis_entry)

    if axes_with_data == NUM_AXES:
        raw_composite = score_sum / NUM_AXES
        composite = round(raw_composite, ROUND_PRECISION)
    else:
        composite = None

    # Country-level severity and governance
    country_sev = compute_country_severity(axis_severity_tuples)
    strict_tier = assign_comparability_tier(country_sev["total_severity"])

    governance = assess_country_governance(
        country=country,
        axis_results=axes_detail,
        severity_total=country_sev["total_severity"],
        strict_comparability_tier=strict_tier,
    )

    # ── Compute layers in dependency order ──
    # Layer 2+3: falsification and decision usability
    falsification = _compute_country_falsification(country, governance)
    decision_usability = _compute_decision_usability(country, governance)

    # Layer 4: external validation — empirical grounding
    external_validation = _compute_external_validation(country, all_scores)

    # Layer 4a: construct enforcement — requires readiness matrix + alignment
    construct_enforcement_result = _compute_construct_enforcement(
        country, external_validation,
    )

    # Layer 4b: benchmark mapping audit — per-benchmark mapping validity
    mapping_audit_results = _compute_mapping_audit()

    # Layer 4c: alignment sensitivity — robustness of alignment
    sensitivity_result = _compute_alignment_sensitivity(
        country, all_scores, external_validation,
    )

    # Layer 4d: empirical alignment classification
    empirical_alignment = _compute_empirical_alignment(external_validation)

    # Layer 5: invariant assessment — structural integrity
    invariant_result = _compute_invariants(
        country, all_scores, governance, external_validation,
        decision_usability, construct_enforcement_result,
        mapping_audit_results, sensitivity_result,
    )

    # Layer 6: failure visibility — anti-bullshit layer (needs ALL upstream data)
    failure_visibility = _compute_failure_visibility(
        country, governance, decision_usability,
        construct_enforcement_result, external_validation,
        sensitivity_result, mapping_audit_results,
        invariant_result,
    )

    # Layer 7: reality conflicts — structural contradiction layer
    reality_conflicts = _compute_reality_conflicts(
        country, governance,
        alignment=external_validation,
        decision_usability=decision_usability,
        empirical_alignment=empirical_alignment,
    )

    # ── Enforcement Matrix — flags must have consequences ──
    enforcement_state = {
        "governance": governance,
        "decision_usability": decision_usability,
        "construct_enforcement": construct_enforcement_result,
        "external_validation": external_validation,
        "failure_visibility": failure_visibility,
        "reality_conflicts": reality_conflicts,
        "invariant_assessment": invariant_result,
        "alignment_sensitivity": sensitivity_result,
    }
    enforcement_result = apply_enforcement(enforcement_state)

    # ── Truth Resolver — single authoritative source ──
    truth_result = resolve_truth(enforcement_state, enforcement_result)

    # Apply truth-resolved values to output
    enforced_composite = composite
    if truth_result["final_composite_suppressed"]:
        enforced_composite = None

    # ── Runtime Status (Section 4) ──
    # Detect degraded layers (layers that caught their own errors)
    degraded_layers: list[str] = []
    for layer_key in [
        "falsification", "decision_usability", "external_validation",
        "construct_enforcement", "alignment_sensitivity",
        "failure_visibility", "reality_conflicts", "invariant_assessment",
    ]:
        block = locals().get(layer_key) or {}
        if isinstance(block, dict):
            # Check renamed local vars
            if layer_key == "construct_enforcement":
                block = construct_enforcement_result
            elif layer_key == "alignment_sensitivity":
                block = sensitivity_result
            elif layer_key == "invariant_assessment":
                block = invariant_result
            if isinstance(block, dict) and block.get("error"):
                degraded_layers.append(layer_key)

    runtime_status: dict[str, Any] = {
        "pipeline_status": "DEGRADED" if degraded_layers else "HEALTHY",
        "degraded_layers": degraded_layers,
        "failed_layers": [],
        "export_blocked": truth_result.get("export_blocked", False),
        "export_blocked_reason": (
            truth_result.get("block_reasons", []) if truth_result.get("export_blocked") else []
        ),
    }

    # ── Publishability Assessment ──
    publishability_result = _compute_publishability(country, truth_result)

    # ── Epistemic Arbiter — SINGLE FINAL AUTHORITY ──
    # The arbiter takes ALL upstream results and produces a single,
    # binding epistemic verdict. ALL exports must respect this.
    arbiter_verdict = _compute_arbiter_verdict(
        country=country,
        runtime_status=runtime_status,
        truth_result=truth_result,
        governance=governance,
        failure_visibility=failure_visibility,
        invariant_result=invariant_result,
        reality_conflicts=reality_conflicts,
        publishability_result=publishability_result,
    )

    # ── Version Locking (Section 5) ──
    version_info: dict[str, str] = {
        "methodology_version": methodology_version,
        "pipeline_version": PIPELINE_VERSION,
        "truth_logic_version": TRUTH_LOGIC_VERSION,
        "enforcement_version": ENFORCEMENT_VERSION,
    }

    # ── Safe Mode Export (Section 7) ──
    # Safe mode now derives from the arbiter verdict, not duplicated logic.
    arbiter_status = arbiter_verdict.get("final_epistemic_status", "VALID")
    arbiter_forbidden = set(arbiter_verdict.get("final_forbidden_claims", []))
    safe_mode_warnings: list[str] = list(
        arbiter_verdict.get("final_required_warnings", [])
    )
    safe_mode_ranking_hidden = False

    # Arbiter-driven ranking suppression
    if "ranking" in arbiter_forbidden or "country_ordering" in arbiter_forbidden:
        safe_mode_ranking_hidden = True
        safe_mode_warnings.append(
            f"Rankings hidden: arbiter status is {arbiter_status}. "
            f"Epistemic authority has determined ranking claims are not defensible."
        )

    # Fallback: also check truth_result for backward compatibility
    final_tier = truth_result.get("final_governance_tier", "NON_COMPARABLE")
    if final_tier in ("LOW_CONFIDENCE", "NON_COMPARABLE") and not safe_mode_ranking_hidden:
        safe_mode_ranking_hidden = True
        safe_mode_warnings.append(
            f"Rankings hidden: governance tier is {final_tier}. "
            f"This country's data quality does not support ranking comparisons."
        )

    if not truth_result.get("final_ranking_eligible", False) and not safe_mode_ranking_hidden:
        safe_mode_ranking_hidden = True
        safe_mode_warnings.append(
            "Rankings hidden: country is not ranking-eligible."
        )

    if arbiter_status in ("BLOCKED", "SUPPRESSED"):
        safe_mode_warnings.append(
            f"ARBITER {arbiter_status}: Epistemic authority has determined "
            f"this country's output must not be used for decision-making."
        )

    if truth_result.get("export_blocked", False):
        safe_mode_warnings.append(
            "EXPORT BLOCKED: Structural issues prevent reliable export. "
            "Data in this snapshot should not be used for decision-making."
        )

    # Deduplicate warnings
    safe_mode_warnings = list(dict.fromkeys(safe_mode_warnings))

    safe_mode: dict[str, Any] = {
        "ranking_hidden": safe_mode_ranking_hidden,
        "warnings": safe_mode_warnings,
        "n_warnings": len(safe_mode_warnings),
    }

    return {
        "country": country,
        "country_name": name,
        "version": methodology_version,
        "year": year,
        "window": data_window,
        "isi_composite": enforced_composite,
        "isi_classification": classify(enforced_composite, methodology_version) if enforced_composite is not None else None,
        "axes_available": axes_with_data,
        "axes_required": NUM_AXES,
        "severity_analysis": country_sev,
        "strict_comparability_tier": strict_tier,
        "governance": governance,
        "axes": axes_detail,
        "falsification": falsification,
        "decision_usability": decision_usability,
        "external_validation": external_validation,
        "construct_enforcement": construct_enforcement_result,
        "alignment_sensitivity": sensitivity_result,
        "failure_visibility": failure_visibility,
        "reality_conflicts": reality_conflicts,
        "invariant_assessment": invariant_result,
        "enforcement_actions": enforcement_result,
        "truth_resolution": truth_result,
        "publishability": publishability_result,
        "arbiter_verdict": arbiter_verdict,
        "runtime_status": runtime_status,
        "version_info": version_info,
        "safe_mode": safe_mode,
    }


def _compute_country_falsification(
    country: str,
    governance: dict[str, Any],
) -> dict[str, Any]:
    """Compute falsification assessment for a country's governance output.

    Wraps backend.falsification.assess_country_falsification with
    graceful error handling for export context.
    """
    try:
        return assess_country_falsification(country, governance)
    except Exception:
        return {
            "country": country,
            "overall_flag": "NOT_ASSESSED",
            "error": "Falsification assessment failed during export",
        }


def _compute_decision_usability(
    country: str,
    governance: dict[str, Any],
) -> dict[str, Any]:
    """Compute decision usability classification for export context.

    Wraps backend.eligibility.classify_decision_usability with
    graceful error handling.
    """
    try:
        return classify_decision_usability(
            country=country,
            governance_result=governance,
        )
    except Exception:
        return {
            "country": country,
            "decision_usability_class": "NOT_ASSESSED",
            "error": "Decision usability classification failed during export",
        }


def _compute_external_validation(
    country: str,
    all_scores: dict[int, dict[str, float]],
    external_data: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Compute external validation block for a country's export JSON.

    Wraps backend.external_validation.build_external_validation_block with
    graceful error handling.

    Args:
        country: ISO-2 code.
        all_scores: {axis_id: {country: score}} for all axes.
        external_data: {benchmark_id: {country: value}} if available.
    """
    try:
        axis_scores: dict[int, float | None] = {}
        for axis_id in range(1, NUM_AXES + 1):
            scores = all_scores.get(axis_id, {})
            axis_scores[axis_id] = scores.get(country)

        return build_external_validation_block(
            country=country,
            axis_scores=axis_scores,
            external_data=external_data,
        )
    except Exception:
        return {
            "country": country,
            "overall_alignment": "NOT_ASSESSED",
            "error": "External validation failed during export",
            "empirical_grounding_answer": (
                "CANNOT ANSWER — external validation failed during export."
            ),
        }


def _compute_failure_visibility(
    country: str,
    governance: dict[str, Any],
    decision_usability: dict[str, Any] | None = None,
    construct_enforcement: dict[str, Any] | None = None,
    external_validation: dict[str, Any] | None = None,
    sensitivity_result: dict[str, Any] | None = None,
    mapping_audit_results: dict[str, dict[str, Any]] | None = None,
    invariant_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute failure visibility block for a country's export JSON.

    Wraps backend.failure_visibility.build_visibility_block with
    graceful error handling.

    This is the anti-bullshit layer — every exported country JSON
    MUST include embedded limitation data. ALL upstream layer results
    are passed through so the visibility block can surface every
    known limitation.
    """
    try:
        return build_visibility_block(
            country=country,
            governance_result=governance,
            decision_usability=decision_usability,
            construct_enforcement=construct_enforcement,
            external_validation=external_validation,
            sensitivity_result=sensitivity_result,
            mapping_audit_results=mapping_audit_results,
            invariant_result=invariant_result,
        )
    except Exception:
        return {
            "country": country,
            "trust_level": "UNKNOWN",
            "trust_explanation": (
                "Failure visibility computation failed during export. "
                "Treat output as UNVALIDATED."
            ),
            "severity_summary": {
                "n_critical": 0,
                "n_error": 0,
                "n_warning": 0,
                "n_info": 0,
                "total_flags": 0,
            },
            "error": "Failure visibility failed during export",
        }


def _compute_reality_conflicts(
    country: str,
    governance: dict[str, Any],
    alignment: dict[str, Any] | None = None,
    decision_usability: dict[str, Any] | None = None,
    empirical_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute reality conflicts block for a country's export JSON.

    Wraps backend.reality_conflicts.detect_reality_conflicts with
    graceful error handling.

    Reality conflicts are STRUCTURAL entries — not flags, not logs.
    They surface when ISI's internal classification contradicts
    external evidence.
    """
    try:
        return detect_reality_conflicts(
            country=country,
            governance_result=governance,
            alignment_result=alignment,
            decision_usability=decision_usability,
            empirical_alignment=empirical_alignment,
        )
    except Exception:
        return {
            "country": country,
            "n_conflicts": 0,
            "n_warnings": 0,
            "n_errors": 0,
            "n_critical": 0,
            "has_critical": False,
            "conflicts": [],
            "interpretation": (
                f"Reality conflict detection failed for {country}. "
                f"Treat as UNVERIFIED."
            ),
            "error": "Reality conflict detection failed during export",
        }


def _compute_construct_enforcement(
    country: str,
    external_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute construct enforcement for a country's export JSON.

    Wraps backend.construct_enforcement.enforce_all_axes with
    graceful error handling. Requires readiness matrix and optional
    alignment data from external_validation.

    Args:
        country: ISO-2 code.
        external_validation: External validation block (for per-axis alignment).
    """
    try:
        readiness_matrix = build_axis_readiness_matrix(country)

        # Extract per-axis alignment classes from external_validation
        axis_alignment_map: dict[int, str] | None = None
        if external_validation and "per_axis_summary" in external_validation:
            axis_alignment_map = {}
            for ax_summary in external_validation["per_axis_summary"]:
                axis_id = ax_summary.get("axis_id")
                alignment_status = ax_summary.get("alignment_status", "UNKNOWN")
                if axis_id is not None:
                    axis_alignment_map[axis_id] = alignment_status

        return enforce_all_axes(
            readiness_matrix=readiness_matrix,
            axis_alignment_map=axis_alignment_map,
        )
    except Exception:
        return {
            "per_axis": [],
            "n_valid": 0,
            "n_degraded": 0,
            "n_invalid": 0,
            "composite_producible": False,
            "error": f"Construct enforcement failed for {country}",
        }


def _compute_mapping_audit() -> dict[str, dict[str, Any]]:
    """Compute benchmark mapping audit results for export.

    Returns the full mapping audit registry so downstream layers
    (failure_visibility, invariants) can check mapping validity.
    """
    try:
        return get_mapping_audit_registry()
    except Exception:
        return {}


def _compute_alignment_sensitivity(
    country: str,
    all_scores: dict[int, dict[str, float]],
    external_validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute alignment sensitivity for a country's export JSON.

    Wraps backend.alignment_sensitivity.run_alignment_sensitivity with
    graceful error handling.

    Args:
        country: ISO-2 code.
        all_scores: {axis_id: {country: score}} for all axes.
        external_validation: External validation block (for original class).
    """
    try:
        axis_scores: dict[int, float | None] = {}
        for axis_id in range(1, NUM_AXES + 1):
            scores = all_scores.get(axis_id, {})
            axis_scores[axis_id] = scores.get(country)

        original_class = None
        if external_validation:
            original_class = external_validation.get("overall_alignment")

        return run_alignment_sensitivity(
            country=country,
            axis_scores=axis_scores,
            original_alignment_class=original_class,
        )
    except Exception:
        return {
            "country": country,
            "stability_class": "NOT_ASSESSED",
            "original_alignment_class": None,
            "n_perturbations_run": 0,
            "n_perturbations_changed": 0,
            "error": f"Alignment sensitivity failed for {country}",
        }


def _compute_empirical_alignment(
    external_validation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Compute empirical alignment classification for export.

    Wraps backend.eligibility.classify_empirical_alignment with
    graceful error handling.

    Args:
        external_validation: External validation block.
    """
    try:
        return classify_empirical_alignment(external_validation)
    except Exception:
        return None


def _compute_invariants(
    country: str,
    all_scores: dict[int, dict[str, float]],
    governance: dict[str, Any],
    external_validation: dict[str, Any] | None = None,
    decision_usability: dict[str, Any] | None = None,
    construct_enforcement: dict[str, Any] | None = None,
    mapping_audit_results: dict[str, dict[str, Any]] | None = None,
    sensitivity_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute invariant assessment for a country's export JSON.

    Wraps backend.invariants.assess_country_invariants with
    graceful error handling. Passes ALL available upstream data
    so invariant checks are comprehensive.

    Args:
        country: ISO-2 code.
        all_scores: {axis_id: {country: score}} for all axes.
        governance: Governance result.
        external_validation: External validation block.
        decision_usability: Decision usability result.
        construct_enforcement: Construct enforcement result.
        mapping_audit_results: Benchmark mapping audit results.
        sensitivity_result: Alignment sensitivity result.
    """
    try:
        axis_scores: dict[int, float | None] = {}
        for axis_id in range(1, NUM_AXES + 1):
            scores = all_scores.get(axis_id, {})
            axis_scores[axis_id] = scores.get(country)

        du_class = None
        if decision_usability:
            du_class = decision_usability.get("decision_usability_class")

        return assess_country_invariants(
            country=country,
            axis_scores=axis_scores,
            governance_result=governance,
            alignment_result=external_validation,
            decision_usability_class=du_class,
            construct_enforcement=construct_enforcement,
            mapping_audit_results=mapping_audit_results,
            sensitivity_result=sensitivity_result,
        )
    except Exception:
        return {
            "country": country,
            "n_violations": 0,
            "n_warnings": 0,
            "n_errors": 0,
            "n_critical": 0,
            "has_critical": False,
            "violations": [],
            "error": f"Invariant assessment failed for {country}",
        }


def _compute_publishability(
    country: str,
    truth_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute publishability assessment for a country's export JSON.

    Wraps backend.publishability.assess_publishability with
    graceful error handling.

    Args:
        country: ISO-2 code.
        truth_result: Output of resolve_truth().
    """
    try:
        return assess_publishability(
            country=country,
            truth_result=truth_result,
        )
    except Exception:
        return {
            "country": country,
            "publishability_status": "NOT_PUBLISHABLE",
            "is_publishable": False,
            "requires_caveats": False,
            "reasons": [],
            "caveats": [],
            "blockers": ["Publishability assessment failed during export"],
            "error": f"Publishability assessment failed for {country}",
        }


def _compute_arbiter_verdict(
    *,
    country: str,
    runtime_status: dict[str, Any] | None = None,
    truth_result: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    failure_visibility: dict[str, Any] | None = None,
    invariant_result: dict[str, Any] | None = None,
    reality_conflicts: dict[str, Any] | None = None,
    publishability_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the final epistemic arbiter verdict for a country.

    The arbiter is the SINGLE FINAL AUTHORITY over all outward-facing
    epistemic state. It consumes all upstream results and produces
    a binding verdict that safe_mode and all consumers must respect.

    Args:
        country: ISO-2 code.
        runtime_status: Pipeline runtime status.
        truth_result: Output of resolve_truth().
        governance: Governance assessment result.
        failure_visibility: Failure visibility result.
        invariant_result: Invariant assessment result.
        reality_conflicts: Reality conflict detection result.
        publishability_result: Publishability assessment result.

    Returns:
        Arbiter verdict dict with final epistemic status, bounds,
        allowed/forbidden claims, and reasoning.
    """
    try:
        return arbiter_adjudicate(
            country=country,
            runtime_status=runtime_status,
            truth_resolution=truth_result,
            governance=governance,
            failure_visibility=failure_visibility,
            invariant_report=invariant_result,
            reality_conflicts=reality_conflicts,
            publishability_result=publishability_result,
        )
    except Exception:
        return {
            "country": country,
            "final_epistemic_status": "BLOCKED",
            "final_confidence_cap": 0.0,
            "final_publishability": "NOT_PUBLISHABLE",
            "final_allowed_claims": [],
            "final_forbidden_claims": [
                "ranking", "comparison", "policy_claim",
                "composite", "country_ordering",
            ],
            "final_required_warnings": [
                "Arbiter computation failed — all claims forbidden.",
            ],
            "final_bounds": {},
            "binding_constraints": ["arbiter_failed"],
            "arbiter_reasoning": [{
                "source": "arbiter_error",
                "decision": "BLOCKED",
                "detail": "Arbiter computation failed during export.",
            }],
            "fault_scope": {},
            "scoped_publishability": {},
            "n_inputs_evaluated": 0,
            "n_reasons": 1,
            "n_warnings": 1,
            "n_forbidden_claims": 5,
            "n_allowed_claims": 0,
            "n_binding_constraints": 1,
            "error": f"Arbiter verdict computation failed for {country}",
        }


def build_axis_json(
    axis_num: int,
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
) -> dict:
    """Build per-axis detail JSON across all countries."""
    slug = AXIS_SCORE_FILES[axis_num]["slug"]
    scores = all_scores.get(axis_num, {})

    countries = []
    for country in EU27_SORTED:
        score = scores.get(country)

        # Determine flags for this country+axis
        flags: list[str] = []
        producer_info = PRODUCER_INVERSION_REGISTRY.get(country, None)
        if producer_info and axis_num in producer_info.get("inverted_axes", []):
            flags.append("PRODUCER_INVERSION")

        has_data = score is not None
        confidence = assess_axis_confidence(
            axis_id=axis_num,
            data_quality_flags=flags,
            is_proxy=False,
            has_data=has_data,
        )

        entry: dict[str, Any] = {
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
            "confidence": confidence,
        }
        if score is not None:
            entry["score"] = score
            entry["classification"] = classify(score, methodology_version)
            entry["data_quality_flags"] = flags
        else:
            entry["score"] = None
            entry["classification"] = None
            entry["data_quality_flags"] = ["INVALID_AXIS"]
        countries.append(entry)

    # Sort by score descending, tie-break alphabetical by country (D-2 fix)
    countries.sort(key=lambda x: (-(x["score"] if x["score"] is not None else -1.0), x["country"]))

    vals = [c["score"] for c in countries if c["score"] is not None]

    return {
        "axis_id": axis_num,
        "axis_slug": slug,
        "version": methodology_version,
        "year": year,
        "countries_scored": len(vals),
        "statistics": {
            "min": round(min(vals), ROUND_PRECISION) if vals else None,
            "max": round(max(vals), ROUND_PRECISION) if vals else None,
            "mean": round(sum(vals) / len(vals), ROUND_PRECISION) if vals else None,
        },
        "countries": countries,
    }


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

def compute_all_hashes(
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
    methodology_params: dict,
) -> tuple[dict[str, str], str]:
    """Compute per-country and snapshot-level hashes.

    Returns (country_hashes, snapshot_hash).
    """
    country_hashes: dict[str, str] = {}

    for country in EU27_SORTED:
        # Build axis_scores dict keyed by slug
        axis_scores_by_slug: dict[str, float] = {}
        for axis_num in range(1, NUM_AXES + 1):
            slug = AXIS_SCORE_FILES[axis_num]["slug"]
            score = all_scores.get(axis_num, {}).get(country)
            if score is not None:
                axis_scores_by_slug[slug] = score

        if len(axis_scores_by_slug) != NUM_AXES:
            fatal(f"Country {country}: incomplete axis scores ({len(axis_scores_by_slug)}/{NUM_AXES})")

        # Compute composite (already rounded in all_scores)
        isi_axes = {}
        for axis_num in range(1, NUM_AXES + 1):
            key = ISI_AXIS_KEYS[axis_num - 1]
            isi_axes[key] = all_scores[axis_num][country]

        raw_composite = compute_composite(isi_axes, methodology_version)
        composite = round(raw_composite, ROUND_PRECISION)

        h = compute_country_hash(
            country_code=country,
            year=year,
            methodology_version=methodology_version,
            axis_scores=axis_scores_by_slug,
            composite=composite,
            data_window=data_window,
            methodology_params=methodology_params,
        )
        country_hashes[country] = h

    snapshot_hash = compute_snapshot_hash(country_hashes)
    return country_hashes, snapshot_hash


# ---------------------------------------------------------------------------
# MANIFEST generation
# ---------------------------------------------------------------------------

def generate_manifest(snapshot_dir: Path) -> dict:
    """Generate MANIFEST.json for a snapshot directory.

    Computes SHA-256 for every JSON file in the snapshot (excluding MANIFEST.json
    and HASH_SUMMARY.json themselves).
    """
    files = []
    for filepath in sorted(snapshot_dir.rglob("*.json")):
        rel = filepath.relative_to(snapshot_dir)
        if rel.name in ("MANIFEST.json", "HASH_SUMMARY.json", SIGNATURE_FILENAME):
            continue
        files.append({
            "path": str(rel),
            "sha256": sha256_file(filepath),
            "size_bytes": filepath.stat().st_size,
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": "export_snapshot.py",
        "file_count": len(files),
        "files": files,
    }


# ---------------------------------------------------------------------------
# Filesystem protection
# ---------------------------------------------------------------------------

def make_readonly(directory: Path) -> None:
    """Remove write permissions from all files in a snapshot directory."""
    for f in directory.rglob("*"):
        if f.is_file():
            f.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444
    directory.chmod(
        stat.S_IRUSR | stat.S_IXUSR |
        stat.S_IRGRP | stat.S_IXGRP |
        stat.S_IROTH | stat.S_IXOTH
    )  # 0o555
    # Make subdirectories traversable
    for d in directory.rglob("*"):
        if d.is_dir():
            d.chmod(
                stat.S_IRUSR | stat.S_IXUSR |
                stat.S_IRGRP | stat.S_IXGRP |
                stat.S_IROTH | stat.S_IXOTH
            )  # 0o555


def cleanup_partial_snapshots() -> int:
    """Remove any temp directories from failed materializations."""
    removed = 0
    if not SNAPSHOTS_ROOT.is_dir():
        return removed
    for d in SNAPSHOTS_ROOT.iterdir():
        if d.is_dir() and d.name.startswith(".tmp_"):
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Main materialization
# ---------------------------------------------------------------------------

def materialize_snapshot(
    year: int,
    methodology_version: str,
    *,
    force: bool = False,
    no_sign: bool = False,
) -> Path:
    """Materialize a complete snapshot atomically.

    1. Load methodology from registry.
    2. Load all axis scores from CSVs.
    3. Compute hashes.
    4. Write to temp directory.
    5. Verify.
    6. Atomic rename to final location.
    7. Set read-only.

    Returns the final snapshot directory path.
    """
    # ── LOAD METHODOLOGY ──
    methodology = get_methodology(methodology_version)
    data_window = f"2022\u20132024"  # Fixed to v1.0 reference window; future versions derive from registry

    print(f"Materializing snapshot: {methodology_version}/{year}")
    print(f"  Methodology: {methodology['label']}")
    print(f"  Data window: {data_window}")
    print()

    # ── FREEZE ENFORCEMENT ──
    final_dir = SNAPSHOTS_ROOT / methodology_version / str(year)
    if final_dir.exists() and not force:
        fatal(
            f"FREEZE VIOLATION: Snapshot {methodology_version}/{year} already exists at {final_dir}. "
            f"Historical snapshots are immutable. "
            f"To publish revised data, register a new methodology version. "
            f"Use --force to override (development only)."
        )

    if final_dir.exists() and force:
        print(f"  WARNING: --force specified. Removing existing snapshot at {final_dir}")
        # Need to make writable first if read-only
        for f in final_dir.rglob("*"):
            if f.is_file():
                f.chmod(stat.S_IWUSR | stat.S_IRUSR)
        for d in [final_dir] + list(final_dir.rglob("*")):
            if d.is_dir():
                d.chmod(stat.S_IRWXU)
        shutil.rmtree(final_dir)
        print()

    # ── LOAD AXIS SCORES ──
    print("Phase 1: Loading axis scores...")
    all_scores: dict[int, dict[str, float]] = {}
    for axis_num in range(1, NUM_AXES + 1):
        scores = load_axis_scores(axis_num, year)
        all_scores[axis_num] = scores
        slug = AXIS_SCORE_FILES[axis_num]["slug"]
        print(f"  Axis {axis_num} ({slug}): {len(scores)} countries")
    print()

    # ── COMPUTE HASHES ──
    print("Phase 2: Computing hashes...")
    country_hashes, snapshot_hash = compute_all_hashes(
        all_scores, methodology_version, year, data_window, methodology,
    )
    print(f"  Snapshot hash: {snapshot_hash[:16]}...")
    print()

    # ── TEMP DIRECTORY ──
    temp_name = f".tmp_{methodology_version}_{year}_{uuid.uuid4().hex[:8]}"
    temp_dir = SNAPSHOTS_ROOT / temp_name
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        # ── WRITE SNAPSHOT FILES ──
        print("Phase 3: Writing snapshot files...")

        # country/{CODE}.json — MUST be built FIRST so arbiter verdicts
        # are available for the ranking list. The arbiter is the single
        # final authority; building isi.json before countries would
        # bypass the arbiter and produce ranking rows with raw governance.
        country_arbiter_verdicts: dict[str, dict[str, Any]] = {}
        for country in EU27_SORTED:
            detail = build_country_json(country, all_scores, methodology_version, year, data_window)
            write_canonical_json(temp_dir / "country" / f"{country}.json", detail)
            # Extract arbiter verdict for ISI ranking row injection
            if "arbiter_verdict" in detail:
                country_arbiter_verdicts[country] = detail["arbiter_verdict"]
        print(f"  country/*.json ({len(EU27_SORTED)} files)")

        # isi.json — now with arbiter-constrained governance values
        isi_data = build_isi_json(
            all_scores, methodology_version, year, data_window,
            country_arbiter_verdicts=country_arbiter_verdicts,
        )
        write_canonical_json(temp_dir / "isi.json", isi_data)
        print(f"  isi.json ({isi_data['countries_complete']} countries)")

        # axis/{n}.json
        for axis_num in range(1, NUM_AXES + 1):
            detail = build_axis_json(axis_num, all_scores, methodology_version, year, data_window)
            write_canonical_json(temp_dir / "axis" / f"{axis_num}.json", detail)
        print(f"  axis/*.json ({NUM_AXES} files)")

        # MANIFEST.json (hashes of data files only)
        manifest = generate_manifest(temp_dir)
        write_canonical_json(temp_dir / "MANIFEST.json", manifest)
        print(f"  MANIFEST.json ({manifest['file_count']} files tracked)")

        # HASH_SUMMARY.json (computation hashes — LAST file written)
        hash_summary = {
            "schema_version": 1,
            "year": year,
            "methodology_version": methodology_version,
            "snapshot_hash": snapshot_hash,
            "computed_at": datetime.now(UTC).isoformat(),
            "computed_by": f"export_snapshot.py",
            "round_precision": ROUND_PRECISION,
            "country_hashes": country_hashes,
        }
        write_canonical_json(temp_dir / "HASH_SUMMARY.json", hash_summary)
        print(f"  HASH_SUMMARY.json (snapshot_hash={snapshot_hash[:16]}...)")

        # SIGNATURE.json (cryptographic Ed25519 signature)
        signed = False
        if not no_sign:
            signing_key_b64 = os.environ.get("ISI_SIGNING_PRIVATE_KEY", "")
            if not signing_key_b64:
                fatal(
                    "ISI_SIGNING_PRIVATE_KEY not set. "
                    "Set the environment variable or use --no-sign for development."
                )
            private_key = load_private_key(signing_key_b64)
            sig_data = sign_snapshot_hash(snapshot_hash, private_key, "v1")
            write_canonical_json(temp_dir / SIGNATURE_FILENAME, sig_data)
            print(f"  SIGNATURE.json (key=v1, alg=ed25519)")
            signed = True
        else:
            print("  SIGNATURE.json SKIPPED (--no-sign)")
        print()

        # ── VERIFY COMPLETENESS ──
        print("Phase 4: Verifying...")
        # isi + countries + axes + manifest + hash_summary + (signature if signed)
        expected_files = 1 + len(EU27_SORTED) + NUM_AXES + 1 + 1 + (1 if signed else 0)
        actual_files = len(list(temp_dir.rglob("*.json")))
        if actual_files != expected_files:
            fatal(f"Expected {expected_files} files, found {actual_files}")
        print(f"  File count: {actual_files}/{expected_files} ✓")

        # Verify MANIFEST hashes match actual files
        for entry in manifest["files"]:
            filepath = temp_dir / entry["path"]
            actual_hash = sha256_file(filepath)
            if actual_hash != entry["sha256"]:
                fatal(f"MANIFEST hash mismatch: {entry['path']}")
        print(f"  MANIFEST verification: {manifest['file_count']} files ✓")

        # Verify snapshot hash is reproducible
        country_hashes_2, snapshot_hash_2 = compute_all_hashes(
            all_scores, methodology_version, year, data_window, methodology,
        )
        if snapshot_hash_2 != snapshot_hash:
            fatal("Snapshot hash is NOT reproducible — determinism violation")
        print(f"  Hash reproducibility: ✓")
        print()

        # ── ATOMIC PROMOTION ──
        print("Phase 5: Promoting snapshot...")

        # Ensure parent directory exists
        final_dir.parent.mkdir(parents=True, exist_ok=True)

        os.rename(temp_dir, final_dir)
        print(f"  Renamed {temp_dir.name} → {final_dir}")

        # ── MAKE READ-ONLY ──
        make_readonly(final_dir)
        print(f"  Permissions set to read-only")

    except Exception:
        # Clean up temp directory on ANY failure
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    # ── SUMMARY ──
    print()
    print("═" * 60)
    print(f"  SNAPSHOT MATERIALIZED: {methodology_version}/{year}")
    print(f"  Location:      {final_dir}")
    print(f"  Files:         {actual_files}")
    print(f"  Snapshot hash: {snapshot_hash}")
    print("═" * 60)

    return final_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ISI Snapshot Materializer — produces immutable snapshot directories.",
    )
    parser.add_argument("--year", type=int, required=True, help="Reference year (e.g., 2024)")
    parser.add_argument("--methodology", type=str, required=True, help="Methodology version (e.g., v1.0)")
    parser.add_argument("--force", action="store_true", help="Override freeze protection (development only)")
    parser.add_argument("--no-sign", action="store_true", dest="no_sign", help="Skip Ed25519 signing (development only)")
    parser.add_argument("--cleanup", action="store_true", help="Clean up partial snapshots before materializing")

    args = parser.parse_args()

    if args.cleanup:
        removed = cleanup_partial_snapshots()
        if removed:
            print(f"Cleaned up {removed} partial snapshot(s)")
        else:
            print("No partial snapshots found")
        print()

    materialize_snapshot(
        year=args.year,
        methodology_version=args.methodology,
        force=args.force,
        no_sign=args.no_sign,
    )


if __name__ == "__main__":
    main()
