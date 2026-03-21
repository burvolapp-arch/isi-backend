#!/usr/bin/env python3
"""ISI v1.1 — Full Pipeline Orchestrator (Global Phase 1)

Runs all 6 axis computations for the Phase 1 7-country scope,
produces composite scores, and materializes the v1.1 snapshot.

This is the single entry point for producing a complete v1.1 snapshot.
It imports and calls each axis compute function, assembles the composite
via compute_composite_v11(), then exports the full structured JSON.

Output:
  data/processed/global_v11/isi_v11_snapshot.json

Constraint spec references:
  - Section 5.3 (composite eligibility: N_computable >= 4)
  - Section 9.2 (composite output schema)
  - Section 9.3 (confidence classification)
  - Section 11 (version control: v1.1 is non-breaking addition)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.axis_result import (
    AxisResult,
    CompositeResult,
    compute_composite_v11,
    validate_composite_result,
)
from backend.constants import ROUND_PRECISION
from backend.scope import get_country_name, get_scope_sorted
from backend.severity import (
    check_cross_country_comparability,
    assign_comparability_tier,
)

# Lazy imports for axis modules (same package)
from scripts.global_v11.compute_axis_1_financial import compute_axis_1
from scripts.global_v11.compute_axis_2_energy import compute_axis_2
from scripts.global_v11.compute_axis_3_technology import compute_axis_3
from scripts.global_v11.compute_axis_4_defense import compute_axis_4
from scripts.global_v11.compute_axis_5_critical_inputs import compute_axis_5
from scripts.global_v11.compute_axis_6_logistics import compute_axis_6

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"


def run_all_axes() -> dict[str, list[AxisResult]]:
    """Run all 6 axis computations and return results by axis slug.

    Returns dict: axis_slug → [AxisResult per country (sorted)].
    """
    print("Running Axis 1 — Financial...", flush=True)
    axis_1 = compute_axis_1()
    print(f"  → {len(axis_1)} results\n")

    print("Running Axis 2 — Energy...", flush=True)
    axis_2 = compute_axis_2()
    print(f"  → {len(axis_2)} results\n")

    print("Running Axis 3 — Technology...", flush=True)
    axis_3 = compute_axis_3()
    print(f"  → {len(axis_3)} results\n")

    print("Running Axis 4 — Defense...", flush=True)
    axis_4 = compute_axis_4()
    print(f"  → {len(axis_4)} results\n")

    print("Running Axis 5 — Critical Inputs...", flush=True)
    axis_5 = compute_axis_5()
    print(f"  → {len(axis_5)} results\n")

    print("Running Axis 6 — Logistics...", flush=True)
    axis_6 = compute_axis_6()
    n_valid_6 = sum(1 for r in axis_6 if r.validity != "INVALID")
    n_invalid_6 = sum(1 for r in axis_6 if r.validity == "INVALID")
    print(f"  → {len(axis_6)} results "
          f"(computable={n_valid_6}, invalid={n_invalid_6})\n")

    return {
        "financial": axis_1,
        "energy": axis_2,
        "technology": axis_3,
        "defense": axis_4,
        "critical_inputs": axis_5,
        "logistics": axis_6,
    }


def assemble_composites(
    all_axes: dict[str, list[AxisResult]],
) -> list[CompositeResult]:
    """Assemble per-country composite scores from all axis results.

    For each country, collects its AxisResult from each axis
    and feeds them to compute_composite_v11().
    """
    countries = get_scope_sorted(SCOPE_ID)

    # Build lookup: (country, axis_id) → AxisResult
    lookup: dict[tuple[str, int], AxisResult] = {}
    axis_id_by_slug = {
        "financial": 1,
        "energy": 2,
        "technology": 3,
        "defense": 4,
        "critical_inputs": 5,
        "logistics": 6,
    }

    for slug, results in all_axes.items():
        axis_id = axis_id_by_slug[slug]
        for r in results:
            lookup[(r.country, axis_id)] = r

    composites: list[CompositeResult] = []

    for country in countries:
        country_axes: list[AxisResult] = []
        for axis_id in range(1, 7):
            ar = lookup.get((country, axis_id))
            if ar is None:
                raise ValueError(
                    f"Missing AxisResult for {country}, axis {axis_id}"
                )
            country_axes.append(ar)

        composite = compute_composite_v11(
            axis_results=country_axes,
            country=country,
            country_name=get_country_name(country),
            scope_id=SCOPE_ID,
            methodology_version=METHODOLOGY,
        )
        validate_composite_result(composite)
        composites.append(composite)

    return composites


def export_snapshot(
    composites: list[CompositeResult],
    all_axes: dict[str, list[AxisResult]],
) -> Path:
    """Export full v1.1 snapshot as structured JSON.

    Includes severity model, cross-country comparability enforcement,
    dual composite (raw + adjusted), stability analysis, and
    interpretation flags for every country.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "isi_v11_snapshot.json"

    # Per-axis summaries
    axis_summaries = {}
    for slug, results in all_axes.items():
        valid = sum(1 for r in results if r.validity == "VALID")
        a_only = sum(1 for r in results if r.validity == "A_ONLY")
        degraded = sum(1 for r in results if r.validity == "DEGRADED")
        invalid = sum(1 for r in results if r.validity == "INVALID")
        axis_summaries[slug] = {
            "valid": valid,
            "a_only": a_only,
            "degraded": degraded,
            "invalid": invalid,
        }

    # Composite summary
    n_composite = sum(1 for c in composites if c.isi_composite is not None)
    n_ineligible = len(composites) - n_composite

    # Per-country degradation + severity profiles from the enriched to_dict()
    country_degradation: dict[str, dict[str, Any]] = {}
    country_severities: dict[str, float] = {}
    country_tiers: dict[str, str] = {}
    for c in composites:
        cd = c.to_dict()
        profile = cd.get("structural_degradation_profile", {})
        sev_analysis = cd.get("severity_analysis", {})
        total_sev = sev_analysis.get("total_severity", 0.0)
        strict_tier = cd.get("strict_comparability_tier", "TIER_4")

        country_severities[c.country] = total_sev
        country_tiers[c.country] = strict_tier

        country_degradation[c.country] = {
            "axes_included": c.axes_included,
            "axes_valid_both": profile.get("axes_valid_both", 0),
            "axes_a_only": profile.get("axes_a_only", 0),
            "axes_degraded": profile.get("axes_degraded", 0),
            "axes_invalid": 6 - c.axes_included,
            "axes_reduced_granularity": profile.get("axes_reduced_granularity", 0),
            "axes_producer_inverted": profile.get("axes_producer_inverted", 0),
            "comparability_tier": cd.get("comparability_tier", "UNKNOWN"),
            "strict_comparability_tier": strict_tier,
            "total_severity": total_sev,
            "severity_profile": sev_analysis.get("severity_profile", {}),
        }

    # Cross-country comparability enforcement (Phase 3)
    cross_country_violations = check_cross_country_comparability(country_severities)

    snapshot = {
        "methodology_version": METHODOLOGY,
        "scope": SCOPE_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "countries_count": len(composites),
        "composite_eligible": n_composite,
        "composite_ineligible": n_ineligible,
        "axis_summaries": axis_summaries,
        "country_degradation_profiles": country_degradation,
        "cross_country_comparability_violations": cross_country_violations,
        "country_tier_summary": country_tiers,
        "countries": [c.to_dict() for c in composites],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    return out_path


def print_summary(composites: list[CompositeResult]) -> None:
    """Print human-readable summary to stdout."""
    print()
    print("=" * 76)
    print("ISI v1.1 — COMPOSITE RESULTS")
    print("=" * 76)
    print()
    print(f"  {'Country':<20s} {'Composite':>10s} {'Class':>12s} "
          f"{'Axes':>5s} {'Confidence':>14s}")
    print("  " + "-" * 70)

    for c in composites:
        score_str = f"{c.isi_composite:.8f}" if c.isi_composite is not None else "N/A"
        class_str = c.classification or "N/A"
        print(
            f"  {c.country_name:<20s} {score_str:>10s} {class_str:>12s} "
            f"{c.axes_included:>5d}/6 {c.confidence:>14s}"
        )

    print()

    # Eligibility check
    eligible = [c for c in composites if c.isi_composite is not None]
    ineligible = [c for c in composites if c.isi_composite is None]

    print(f"  Composite eligible: {len(eligible)}/{len(composites)}")
    if ineligible:
        print(f"  Ineligible: {[c.country for c in ineligible]}")

    # Confidence distribution
    full = sum(1 for c in eligible if c.confidence == "FULL")
    reduced = sum(1 for c in eligible if c.confidence == "REDUCED")
    low = sum(1 for c in eligible if c.confidence == "LOW_CONFIDENCE")
    print(f"  Confidence: FULL={full}  REDUCED={reduced}  LOW_CONFIDENCE={low}")

    # Warning summary
    all_warnings = set()
    for c in composites:
        all_warnings.update(c.warnings)
    if all_warnings:
        print(f"\n  Warnings observed: {sorted(all_warnings)}")

    print()


def main() -> None:
    print()
    print("=" * 76)
    print("  ISI v1.1 — FULL PIPELINE ORCHESTRATOR (GLOBAL PHASE 1)")
    print(f"  Scope: {SCOPE_ID} (7 countries)")
    print(f"  Methodology: {METHODOLOGY}")
    print("=" * 76)
    print()

    # Step 1: Compute all axes
    all_axes = run_all_axes()

    # Step 2: Assemble composites
    print("Assembling composite scores...", flush=True)
    composites = assemble_composites(all_axes)
    print(f"  → {len(composites)} composite results\n")

    # Step 3: Export snapshot
    out_path = export_snapshot(composites, all_axes)
    print(f"Snapshot written to {out_path}")

    # Step 4: Print summary
    print_summary(composites)

    # Step 5: Final validation
    print("=" * 76)
    print("  PIPELINE COMPLETE")
    print("=" * 76)
    print()

    # Verify all composites pass validation
    for c in composites:
        validate_composite_result(c)

    # Check minimum eligibility
    eligible = sum(1 for c in composites if c.isi_composite is not None)
    if eligible == 0:
        print("  WARNING: No countries achieved composite eligibility.")
        print("  This likely means raw data files are missing.")
        print("  Check data/raw/ and data/processed/ directories.")
    else:
        print(f"  {eligible}/{len(composites)} countries have valid ISI composite scores.")

    print()


if __name__ == "__main__":
    main()
