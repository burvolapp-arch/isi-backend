"""
backend.snapshot_diff — Snapshot Differential Analysis

SYSTEM 3: Compares two materialized snapshots to produce per-country
composite, rank, governance, and usability deltas with root cause
analysis and change classification.

This module answers: "What exactly changed between versions, and why?"

Change classification taxonomy:
    DATA_CHANGE — Input data (axis scores) changed.
    METHODOLOGY_CHANGE — Methodology version or aggregation rules changed.
    THRESHOLD_CHANGE — Governance/severity threshold values changed.
    GOVERNANCE_CHANGE — Governance tier changed (new rules, re-assessment).
    BUG_FIX — Explicitly labeled as a correction.

Design contract:
    - Comparison is between two MATERIALIZED snapshots (frozen JSON).
    - Diff is deterministic — same two snapshots, same diff.
    - Root cause analysis identifies WHICH axis moved, not WHY it moved.
    - Global summary provides aggregate statistics.
    - Diff artifacts are storable alongside snapshot metadata.

Honesty note:
    Diffs show WHAT changed and attempt to classify WHY.
    Root cause attribution is STRUCTURAL, not CAUSAL.
    We can say "Axis 2 score changed by +0.08" but not
    "the EU changed its trade policy."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# CHANGE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class ChangeType:
    """Classification of what caused a change between snapshots."""
    DATA_CHANGE = "DATA_CHANGE"
    METHODOLOGY_CHANGE = "METHODOLOGY_CHANGE"
    THRESHOLD_CHANGE = "THRESHOLD_CHANGE"
    GOVERNANCE_CHANGE = "GOVERNANCE_CHANGE"
    BUG_FIX = "BUG_FIX"
    NO_CHANGE = "NO_CHANGE"


VALID_CHANGE_TYPES = frozenset({
    ChangeType.DATA_CHANGE,
    ChangeType.METHODOLOGY_CHANGE,
    ChangeType.THRESHOLD_CHANGE,
    ChangeType.GOVERNANCE_CHANGE,
    ChangeType.BUG_FIX,
    ChangeType.NO_CHANGE,
})


# ═══════════════════════════════════════════════════════════════════════════
# SNAPSHOT LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_snapshot_isi(snapshot_path: Path) -> dict[str, Any]:
    """Load the ISI summary JSON from a snapshot directory.

    Args:
        snapshot_path: Path to snapshot directory (e.g., backend/snapshots/ISI-M-2025-001/2025/).

    Returns:
        Parsed ISI JSON.

    Raises:
        FileNotFoundError: If isi.json not found.
    """
    isi_file = snapshot_path / "isi.json"
    if not isi_file.exists():
        raise FileNotFoundError(f"isi.json not found at {isi_file}")
    return json.loads(isi_file.read_text())


def load_snapshot_country(snapshot_path: Path, country: str) -> dict[str, Any] | None:
    """Load a per-country JSON from a snapshot directory.

    Args:
        snapshot_path: Path to snapshot directory.
        country: ISO-2 code (e.g., "DE").

    Returns:
        Parsed country JSON, or None if not found.
    """
    country_file = snapshot_path / "countries" / f"{country}.json"
    if not country_file.exists():
        return None
    return json.loads(country_file.read_text())


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY
# ═══════════════════════════════════════════════════════════════════════════

def _extract_nested(
    detail: dict[str, Any] | None, block_key: str, field: str,
) -> Any | None:
    """Safely extract a nested field from country detail JSON.

    Args:
        detail: Country detail JSON dict (may be None).
        block_key: Top-level key (e.g., "reality_conflicts").
        field: Nested key within the block (e.g., "n_conflicts").

    Returns:
        The value if found, None otherwise.
    """
    if detail is None:
        return None
    block = detail.get(block_key)
    if not isinstance(block, dict):
        return None
    return block.get(field)


# ═══════════════════════════════════════════════════════════════════════════
# PER-COUNTRY DIFF
# ═══════════════════════════════════════════════════════════════════════════

def diff_country(
    country: str,
    isi_entry_a: dict[str, Any] | None,
    isi_entry_b: dict[str, Any] | None,
    country_detail_a: dict[str, Any] | None = None,
    country_detail_b: dict[str, Any] | None = None,
    methodology_a: str | None = None,
    methodology_b: str | None = None,
) -> dict[str, Any]:
    """Compute the diff between two versions for a single country.

    Args:
        country: ISO-2 code.
        isi_entry_a: ISI entry for this country from snapshot A (or None if new).
        isi_entry_b: ISI entry for this country from snapshot B (or None if removed).
        country_detail_a: Full country JSON from snapshot A (for axis-level analysis).
        country_detail_b: Full country JSON from snapshot B.
        methodology_a: Methodology version for snapshot A.
        methodology_b: Methodology version for snapshot B.

    Returns:
        Per-country diff record.
    """
    # Handle additions / removals
    if isi_entry_a is None:
        return {
            "country": country,
            "status": "ADDED",
            "change_types": [ChangeType.DATA_CHANGE],
            "composite_delta": None,
            "rank_delta": None,
            "governance_change": None,
            "usability_change": None,
            "reality_conflicts_change": None,
            "visibility_change": None,
            "construct_enforcement_change": None,
            "sensitivity_change": None,
            "enforcement_actions_change": None,
            "truth_status_change": None,
            "axis_deltas": {},
            "root_causes": ["Country added in version B"],
        }

    if isi_entry_b is None:
        return {
            "country": country,
            "status": "REMOVED",
            "change_types": [ChangeType.DATA_CHANGE],
            "composite_delta": None,
            "rank_delta": None,
            "governance_change": None,
            "usability_change": None,
            "reality_conflicts_change": None,
            "visibility_change": None,
            "construct_enforcement_change": None,
            "sensitivity_change": None,
            "enforcement_actions_change": None,
            "truth_status_change": None,
            "axis_deltas": {},
            "root_causes": ["Country removed in version B"],
        }

    # ── Composite delta ──
    comp_a = isi_entry_a.get("isi_composite")
    comp_b = isi_entry_b.get("isi_composite")
    composite_delta = None
    if comp_a is not None and comp_b is not None:
        composite_delta = round(comp_b - comp_a, 8)

    # ── Rank delta ──
    rank_a = isi_entry_a.get("rank")
    rank_b = isi_entry_b.get("rank")
    rank_delta = None
    if rank_a is not None and rank_b is not None:
        rank_delta = rank_b - rank_a

    # ── Governance tier change ──
    gov_a = isi_entry_a.get("governance_tier", isi_entry_a.get("governance", {}).get("governance_tier"))
    gov_b = isi_entry_b.get("governance_tier", isi_entry_b.get("governance", {}).get("governance_tier"))
    governance_change = None
    if gov_a and gov_b:
        governance_change = {
            "from": gov_a,
            "to": gov_b,
            "changed": gov_a != gov_b,
        }

    # ── Usability class change ──
    usab_a = isi_entry_a.get("decision_usability_class")
    usab_b = isi_entry_b.get("decision_usability_class")
    usability_change = None
    if usab_a and usab_b:
        usability_change = {
            "from": usab_a,
            "to": usab_b,
            "changed": usab_a != usab_b,
        }

    # ── Reality conflicts change ──
    rc_a = _extract_nested(country_detail_a, "reality_conflicts", "n_conflicts")
    rc_b = _extract_nested(country_detail_b, "reality_conflicts", "n_conflicts")
    reality_conflicts_change = None
    if rc_a is not None and rc_b is not None:
        reality_conflicts_change = {
            "from": rc_a,
            "to": rc_b,
            "changed": rc_a != rc_b,
        }

    # ── Failure visibility trust level change ──
    fv_a = _extract_nested(country_detail_a, "failure_visibility", "trust_level")
    fv_b = _extract_nested(country_detail_b, "failure_visibility", "trust_level")
    visibility_change = None
    if fv_a is not None and fv_b is not None:
        visibility_change = {
            "from": fv_a,
            "to": fv_b,
            "changed": fv_a != fv_b,
        }

    # ── Construct enforcement change ──
    ce_a_prod = _extract_nested(country_detail_a, "construct_enforcement", "composite_producible")
    ce_b_prod = _extract_nested(country_detail_b, "construct_enforcement", "composite_producible")
    construct_enforcement_change = None
    if ce_a_prod is not None and ce_b_prod is not None:
        ce_a_valid = _extract_nested(country_detail_a, "construct_enforcement", "n_valid") or 0
        ce_b_valid = _extract_nested(country_detail_b, "construct_enforcement", "n_valid") or 0
        construct_enforcement_change = {
            "composite_producible_from": ce_a_prod,
            "composite_producible_to": ce_b_prod,
            "n_valid_from": ce_a_valid,
            "n_valid_to": ce_b_valid,
            "changed": ce_a_prod != ce_b_prod or ce_a_valid != ce_b_valid,
        }

    # ── Alignment sensitivity change ──
    sens_a = _extract_nested(country_detail_a, "alignment_sensitivity", "stability_class")
    sens_b = _extract_nested(country_detail_b, "alignment_sensitivity", "stability_class")
    sensitivity_change = None
    if sens_a is not None and sens_b is not None:
        sensitivity_change = {
            "from": sens_a,
            "to": sens_b,
            "changed": sens_a != sens_b,
        }

    # ── Enforcement actions change ──
    enf_a_n = _extract_nested(country_detail_a, "enforcement_actions", "n_actions")
    enf_b_n = _extract_nested(country_detail_b, "enforcement_actions", "n_actions")
    enf_a_blocked = _extract_nested(country_detail_a, "enforcement_actions", "export_blocked")
    enf_b_blocked = _extract_nested(country_detail_b, "enforcement_actions", "export_blocked")
    enforcement_actions_change = None
    if enf_a_n is not None and enf_b_n is not None:
        enforcement_actions_change = {
            "n_actions_from": enf_a_n,
            "n_actions_to": enf_b_n,
            "export_blocked_from": enf_a_blocked,
            "export_blocked_to": enf_b_blocked,
            "changed": enf_a_n != enf_b_n or enf_a_blocked != enf_b_blocked,
        }

    # ── Truth status change ──
    truth_a = _extract_nested(country_detail_a, "truth_resolution", "truth_status")
    truth_b = _extract_nested(country_detail_b, "truth_resolution", "truth_status")
    truth_status_change = None
    if truth_a is not None and truth_b is not None:
        truth_status_change = {
            "from": truth_a,
            "to": truth_b,
            "changed": truth_a != truth_b,
        }

    # ── Axis-level deltas ──
    axis_deltas: dict[int, dict[str, Any]] = {}
    axes_a_map: dict[int, float | None] = {}
    axes_b_map: dict[int, float | None] = {}

    if country_detail_a and country_detail_b:
        for ax in country_detail_a.get("axes", []):
            axes_a_map[ax["axis_id"]] = ax.get("score")
        for ax in country_detail_b.get("axes", []):
            axes_b_map[ax["axis_id"]] = ax.get("score")
    else:
        # Fallback: try to extract from ISI entry axis scores if present
        for ax_key in ("axis_scores", "axes"):
            for entry, target in [(isi_entry_a, axes_a_map), (isi_entry_b, axes_b_map)]:
                data = entry.get(ax_key, {})
                if isinstance(data, dict):
                    for k, v in data.items():
                        try:
                            target[int(k)] = v
                        except (ValueError, TypeError):
                            pass
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and "axis_id" in item:
                            target[item["axis_id"]] = item.get("score")

    for ax_id in range(1, 7):
        sa = axes_a_map.get(ax_id)
        sb = axes_b_map.get(ax_id)
        if sa is not None and sb is not None:
            delta = round(sb - sa, 8)
            axis_deltas[ax_id] = {
                "score_a": sa,
                "score_b": sb,
                "delta": delta,
                "abs_delta": round(abs(delta), 8),
            }
        elif sa is None and sb is not None:
            axis_deltas[ax_id] = {
                "score_a": None,
                "score_b": sb,
                "delta": None,
                "status": "ADDED",
            }
        elif sa is not None and sb is None:
            axis_deltas[ax_id] = {
                "score_a": sa,
                "score_b": None,
                "delta": None,
                "status": "REMOVED",
            }

    # ── Root cause analysis ──
    root_causes: list[str] = []
    change_types: list[str] = []

    # Check methodology change
    if methodology_a and methodology_b and methodology_a != methodology_b:
        change_types.append(ChangeType.METHODOLOGY_CHANGE)
        root_causes.append(
            f"Methodology changed from {methodology_a} to {methodology_b}"
        )

    # Check data changes (axis-level)
    data_changed_axes = [
        ax_id for ax_id, d in axis_deltas.items()
        if d.get("delta") is not None and abs(d["delta"]) > 1e-10
    ]
    if data_changed_axes:
        change_types.append(ChangeType.DATA_CHANGE)
        for ax_id in data_changed_axes:
            d = axis_deltas[ax_id]
            root_causes.append(
                f"Axis {ax_id} score changed by {d['delta']:+.8f}"
            )
    elif composite_delta is not None and abs(composite_delta) > 1e-10:
        # Composite changed but no axis-level data available to attribute
        change_types.append(ChangeType.DATA_CHANGE)
        root_causes.append(
            f"Composite changed by {composite_delta:+.8f} "
            f"(axis-level attribution unavailable)"
        )

    # Check governance change
    if governance_change and governance_change["changed"]:
        change_types.append(ChangeType.GOVERNANCE_CHANGE)
        root_causes.append(
            f"Governance tier: {governance_change['from']} → {governance_change['to']}"
        )

    # Check usability change
    if usability_change and usability_change["changed"]:
        # Usability is derivative, so don't add a separate change type
        root_causes.append(
            f"Usability class: {usability_change['from']} → {usability_change['to']}"
        )

    # If nothing changed at axis/composite/methodology level, check rank
    if not change_types:
        if rank_delta is not None and rank_delta != 0:
            change_types.append(ChangeType.DATA_CHANGE)
            root_causes.append(
                f"Rank changed by {rank_delta:+d} (composite unchanged)"
            )

    # If nothing changed
    if not change_types:
        change_types.append(ChangeType.NO_CHANGE)

    # Status
    has_changes = ChangeType.NO_CHANGE not in change_types
    status = "CHANGED" if has_changes else "UNCHANGED"

    return {
        "country": country,
        "status": status,
        "change_types": change_types,
        "composite_delta": composite_delta,
        "rank_delta": rank_delta,
        "governance_change": governance_change,
        "usability_change": usability_change,
        "reality_conflicts_change": reality_conflicts_change,
        "visibility_change": visibility_change,
        "construct_enforcement_change": construct_enforcement_change,
        "sensitivity_change": sensitivity_change,
        "enforcement_actions_change": enforcement_actions_change,
        "truth_status_change": truth_status_change,
        "axis_deltas": axis_deltas,
        "root_causes": root_causes,
    }


# ═══════════════════════════════════════════════════════════════════════════
# FULL SNAPSHOT COMPARISON
# ═══════════════════════════════════════════════════════════════════════════

def compare_snapshots(
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
    country_details_a: dict[str, dict[str, Any]] | None = None,
    country_details_b: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare two ISI snapshots and produce a full differential report.

    Args:
        snapshot_a: Parsed ISI JSON from version A.
        snapshot_b: Parsed ISI JSON from version B.
        country_details_a: {country: detail_json} from version A (optional, for axis-level).
        country_details_b: {country: detail_json} from version B (optional).

    Returns:
        Full differential report with per-country diffs and global summary.
    """
    methodology_a = snapshot_a.get("methodology_version")
    methodology_b = snapshot_b.get("methodology_version")

    # Build country lookup from ISI ranking lists
    countries_a = _isi_country_map(snapshot_a)
    countries_b = _isi_country_map(snapshot_b)

    all_countries = sorted(set(countries_a.keys()) | set(countries_b.keys()))

    per_country: dict[str, dict[str, Any]] = {}
    for country in all_countries:
        entry_a = countries_a.get(country)
        entry_b = countries_b.get(country)

        detail_a = (country_details_a or {}).get(country)
        detail_b = (country_details_b or {}).get(country)

        per_country[country] = diff_country(
            country=country,
            isi_entry_a=entry_a,
            isi_entry_b=entry_b,
            country_detail_a=detail_a,
            country_detail_b=detail_b,
            methodology_a=methodology_a,
            methodology_b=methodology_b,
        )

    # ── Global summary ──
    n_total = len(all_countries)
    n_changed = sum(1 for d in per_country.values() if d["status"] != "UNCHANGED")
    n_added = sum(1 for d in per_country.values() if d["status"] == "ADDED")
    n_removed = sum(1 for d in per_country.values() if d["status"] == "REMOVED")
    n_unchanged = n_total - n_changed

    # Rank movements
    rank_deltas = [
        d["rank_delta"] for d in per_country.values()
        if d["rank_delta"] is not None and d["rank_delta"] != 0
    ]
    avg_rank_movement = (
        round(sum(abs(r) for r in rank_deltas) / len(rank_deltas), 4)
        if rank_deltas else 0
    )
    max_rank_movement = max((abs(r) for r in rank_deltas), default=0)

    # Composite movements
    comp_deltas = [
        d["composite_delta"] for d in per_country.values()
        if d["composite_delta"] is not None and d["composite_delta"] != 0
    ]
    avg_composite_delta = (
        round(sum(abs(c) for c in comp_deltas) / len(comp_deltas), 8)
        if comp_deltas else 0
    )

    # Governance tier changes
    n_governance_changed = sum(
        1 for d in per_country.values()
        if d.get("governance_change") and d["governance_change"].get("changed")
    )

    # Reality conflict changes
    n_reality_conflicts_changed = sum(
        1 for d in per_country.values()
        if d.get("reality_conflicts_change") and d["reality_conflicts_change"].get("changed")
    )

    # Visibility trust level changes
    n_visibility_changed = sum(
        1 for d in per_country.values()
        if d.get("visibility_change") and d["visibility_change"].get("changed")
    )

    # Construct enforcement changes
    n_construct_enforcement_changed = sum(
        1 for d in per_country.values()
        if d.get("construct_enforcement_change") and d["construct_enforcement_change"].get("changed")
    )

    # Alignment sensitivity changes
    n_sensitivity_changed = sum(
        1 for d in per_country.values()
        if d.get("sensitivity_change") and d["sensitivity_change"].get("changed")
    )

    # Enforcement actions changes
    n_enforcement_actions_changed = sum(
        1 for d in per_country.values()
        if d.get("enforcement_actions_change") and d["enforcement_actions_change"].get("changed")
    )

    # Truth status changes
    n_truth_status_changed = sum(
        1 for d in per_country.values()
        if d.get("truth_status_change") and d["truth_status_change"].get("changed")
    )

    # Change type distribution
    change_type_counts: dict[str, int] = {}
    for d in per_country.values():
        for ct in d["change_types"]:
            change_type_counts[ct] = change_type_counts.get(ct, 0) + 1

    # Methodology change flag
    methodology_changed = (
        methodology_a is not None
        and methodology_b is not None
        and methodology_a != methodology_b
    )

    global_summary = {
        "version_a": {
            "methodology": methodology_a,
            "year": snapshot_a.get("year"),
            "data_window": snapshot_a.get("data_window"),
            "n_countries": len(countries_a),
        },
        "version_b": {
            "methodology": methodology_b,
            "year": snapshot_b.get("year"),
            "data_window": snapshot_b.get("data_window"),
            "n_countries": len(countries_b),
        },
        "n_total_countries": n_total,
        "n_changed": n_changed,
        "n_unchanged": n_unchanged,
        "n_added": n_added,
        "n_removed": n_removed,
        "pct_changed": round(100 * n_changed / n_total, 2) if n_total > 0 else 0,
        "methodology_changed": methodology_changed,
        "n_governance_tier_changes": n_governance_changed,
        "n_reality_conflicts_changes": n_reality_conflicts_changed,
        "n_visibility_changes": n_visibility_changed,
        "n_construct_enforcement_changes": n_construct_enforcement_changed,
        "n_sensitivity_changes": n_sensitivity_changed,
        "n_enforcement_actions_changes": n_enforcement_actions_changed,
        "n_truth_status_changes": n_truth_status_changed,
        "rank_movement": {
            "n_countries_with_rank_change": len(rank_deltas),
            "avg_abs_rank_movement": avg_rank_movement,
            "max_abs_rank_movement": max_rank_movement,
        },
        "composite_movement": {
            "n_countries_with_composite_change": len(comp_deltas),
            "avg_abs_composite_delta": avg_composite_delta,
        },
        "change_type_distribution": change_type_counts,
    }

    return {
        "diff_version": "1.0",
        "global_summary": global_summary,
        "per_country": per_country,
        "honesty_note": (
            "This diff shows WHAT changed between versions and classifies "
            "change types structurally. Root cause attribution is structural, "
            "not causal — we can say 'score changed' but not 'why the "
            "underlying economic reality changed.'"
        ),
    }


def compare_snapshots_from_paths(
    path_a: Path,
    path_b: Path,
    include_country_details: bool = True,
) -> dict[str, Any]:
    """Compare two snapshots given their filesystem paths.

    Args:
        path_a: Path to snapshot A directory.
        path_b: Path to snapshot B directory.
        include_country_details: If True, load per-country JSONs for axis-level diffs.

    Returns:
        Full differential report.
    """
    snapshot_a = load_snapshot_isi(path_a)
    snapshot_b = load_snapshot_isi(path_b)

    country_details_a = None
    country_details_b = None

    if include_country_details:
        # Get all countries from both snapshots
        countries_a_map = _isi_country_map(snapshot_a)
        countries_b_map = _isi_country_map(snapshot_b)
        all_countries = set(countries_a_map.keys()) | set(countries_b_map.keys())

        country_details_a = {}
        country_details_b = {}
        for country in all_countries:
            detail_a = load_snapshot_country(path_a, country)
            if detail_a:
                country_details_a[country] = detail_a
            detail_b = load_snapshot_country(path_b, country)
            if detail_b:
                country_details_b[country] = detail_b

    return compare_snapshots(
        snapshot_a, snapshot_b,
        country_details_a, country_details_b,
    )


def get_diff_summary_text(diff_result: dict[str, Any]) -> str:
    """Generate a human-readable summary of the diff.

    Returns:
        Multi-line text summary.
    """
    gs = diff_result["global_summary"]
    lines = [
        "═══ Snapshot Differential Summary ═══",
        "",
        f"  Version A: {gs['version_a']['methodology']} ({gs['version_a']['year']})",
        f"  Version B: {gs['version_b']['methodology']} ({gs['version_b']['year']})",
        "",
        f"  Countries: {gs['n_total_countries']} total",
        f"    Changed:   {gs['n_changed']} ({gs['pct_changed']}%)",
        f"    Unchanged: {gs['n_unchanged']}",
        f"    Added:     {gs['n_added']}",
        f"    Removed:   {gs['n_removed']}",
        "",
        f"  Methodology changed: {gs['methodology_changed']}",
        f"  Governance tier changes: {gs['n_governance_tier_changes']}",
        "",
        "  Rank Movement:",
        f"    Countries with rank change: {gs['rank_movement']['n_countries_with_rank_change']}",
        f"    Avg |rank| movement: {gs['rank_movement']['avg_abs_rank_movement']}",
        f"    Max |rank| movement: {gs['rank_movement']['max_abs_rank_movement']}",
        "",
        "  Composite Movement:",
        f"    Countries with composite change: {gs['composite_movement']['n_countries_with_composite_change']}",
        f"    Avg |composite| delta: {gs['composite_movement']['avg_abs_composite_delta']}",
        "",
        "  Change Type Distribution:",
    ]
    for ct, count in sorted(gs["change_type_distribution"].items()):
        lines.append(f"    {ct}: {count}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# POLICY IMPACT ASSESSMENT (SECTION 4 — Final Hardening)
# ═══════════════════════════════════════════════════════════════════════════

class PolicyImpactClass:
    """Classification of policy impact from snapshot changes.

    Answers: "Would a policy-maker who relied on the previous version
    need to revise their conclusions?"
    """
    NO_IMPACT = "NO_IMPACT"
    MINOR_ADJUSTMENT = "MINOR_ADJUSTMENT"
    INTERPRETATION_CHANGE = "INTERPRETATION_CHANGE"
    INVALIDATES_PRIOR_RESULTS = "INVALIDATES_PRIOR_RESULTS"


VALID_POLICY_IMPACT_CLASSES = frozenset({
    PolicyImpactClass.NO_IMPACT,
    PolicyImpactClass.MINOR_ADJUSTMENT,
    PolicyImpactClass.INTERPRETATION_CHANGE,
    PolicyImpactClass.INVALIDATES_PRIOR_RESULTS,
})

# Thresholds for policy impact classification
_RANK_SHIFT_MINOR = 2        # ≤2 rank positions = MINOR
_RANK_SHIFT_MATERIAL = 5     # >5 rank positions = potentially INVALIDATING
_COMPOSITE_SHIFT_MINOR = 0.03  # ≤0.03 = MINOR
_COMPOSITE_SHIFT_MATERIAL = 0.10  # >0.10 = potentially INVALIDATING

# Governance tier severity ordering (higher = more restrictive)
_GOVERNANCE_SEVERITY: dict[str, int] = {
    "FULLY_COMPARABLE": 0,
    "PARTIALLY_COMPARABLE": 1,
    "LOW_CONFIDENCE": 2,
    "NON_COMPARABLE": 3,
}

# Usability severity ordering
_USABILITY_SEVERITY: dict[str, int] = {
    "TRUSTED_COMPARABLE": 0,
    "CONDITIONALLY_USABLE": 1,
    "STRUCTURALLY_LIMITED": 2,
    "INVALID_FOR_COMPARISON": 3,
}


def assess_country_policy_impact(
    country_diff: dict[str, Any],
) -> dict[str, Any]:
    """Assess policy impact of changes for a single country.

    Classification rules (applied in priority order):
        1. INVALIDATES_PRIOR_RESULTS if:
           - Governance tier worsened to NON_COMPARABLE
           - Usability class became INVALID_FOR_COMPARISON
           - Rank moved by >5 positions AND composite moved by >0.10
        2. INTERPRETATION_CHANGE if:
           - Governance tier changed at all
           - Usability class changed at all
           - Rank moved by >5 positions
           - Composite moved by >0.10
        3. MINOR_ADJUSTMENT if:
           - Rank moved by 1-2 positions
           - Composite moved by >0 but ≤0.03
        4. NO_IMPACT if:
           - No material changes

    Args:
        country_diff: Single-country diff from diff_country().

    Returns:
        Policy impact assessment for this country.
    """
    status = country_diff.get("status", "UNCHANGED")
    country = country_diff["country"]

    if status == "UNCHANGED":
        return {
            "country": country,
            "impact_class": PolicyImpactClass.NO_IMPACT,
            "reasons": [],
            "recommendation": "No action required.",
        }

    if status in ("ADDED", "REMOVED"):
        return {
            "country": country,
            "impact_class": PolicyImpactClass.INTERPRETATION_CHANGE,
            "reasons": [f"Country {status.lower()} in new version"],
            "recommendation": (
                f"Country was {status.lower()}. "
                f"Any prior analysis referencing this country must be reviewed."
            ),
        }

    reasons: list[str] = []
    impact_level = 0  # 0=none, 1=minor, 2=interpretation, 3=invalidates

    # ── Governance tier change ──
    gov_change = country_diff.get("governance_change")
    if gov_change and gov_change.get("changed"):
        sev_from = _GOVERNANCE_SEVERITY.get(gov_change["from"], 0)
        sev_to = _GOVERNANCE_SEVERITY.get(gov_change["to"], 0)

        if gov_change["to"] == "NON_COMPARABLE":
            impact_level = max(impact_level, 3)
            reasons.append(
                f"Governance tier worsened to NON_COMPARABLE "
                f"(was {gov_change['from']})"
            )
        elif sev_to > sev_from:
            impact_level = max(impact_level, 2)
            reasons.append(
                f"Governance tier worsened: "
                f"{gov_change['from']} → {gov_change['to']}"
            )
        elif sev_to < sev_from:
            impact_level = max(impact_level, 2)
            reasons.append(
                f"Governance tier improved: "
                f"{gov_change['from']} → {gov_change['to']}"
            )
        else:
            # Different tier, same severity — still interpretation change
            impact_level = max(impact_level, 2)
            reasons.append(
                f"Governance tier changed: "
                f"{gov_change['from']} → {gov_change['to']}"
            )

    # ── Usability class change ──
    usab_change = country_diff.get("usability_change")
    if usab_change and usab_change.get("changed"):
        sev_from = _USABILITY_SEVERITY.get(usab_change["from"], 0)
        sev_to = _USABILITY_SEVERITY.get(usab_change["to"], 0)

        if usab_change["to"] == "INVALID_FOR_COMPARISON":
            impact_level = max(impact_level, 3)
            reasons.append(
                f"Usability class became INVALID_FOR_COMPARISON "
                f"(was {usab_change['from']})"
            )
        elif sev_to > sev_from:
            impact_level = max(impact_level, 2)
            reasons.append(
                f"Usability class worsened: "
                f"{usab_change['from']} → {usab_change['to']}"
            )
        elif sev_to < sev_from:
            impact_level = max(impact_level, 2)
            reasons.append(
                f"Usability class improved: "
                f"{usab_change['from']} → {usab_change['to']}"
            )

    # ── Rank movement ──
    rank_delta = country_diff.get("rank_delta")
    if rank_delta is not None:
        abs_rank = abs(rank_delta)
        if abs_rank > _RANK_SHIFT_MATERIAL:
            impact_level = max(impact_level, 2)
            reasons.append(f"Rank shifted by {rank_delta:+d} positions (material)")
        elif abs_rank > _RANK_SHIFT_MINOR:
            impact_level = max(impact_level, 2)
            reasons.append(f"Rank shifted by {rank_delta:+d} positions")
        elif abs_rank > 0:
            impact_level = max(impact_level, 1)
            reasons.append(f"Rank shifted by {rank_delta:+d} position(s) (minor)")

    # ── Composite movement ──
    comp_delta = country_diff.get("composite_delta")
    if comp_delta is not None:
        abs_comp = abs(comp_delta)
        if abs_comp > _COMPOSITE_SHIFT_MATERIAL:
            impact_level = max(impact_level, 2)
            reasons.append(
                f"Composite score changed by {comp_delta:+.8f} (material)"
            )
        elif abs_comp > _COMPOSITE_SHIFT_MINOR:
            impact_level = max(impact_level, 2)
            reasons.append(f"Composite score changed by {comp_delta:+.8f}")
        elif abs_comp > 1e-10:
            impact_level = max(impact_level, 1)
            reasons.append(
                f"Composite score changed by {comp_delta:+.8f} (minor)"
            )

    # ── Combined escalation: large rank + large composite ──
    if (
        rank_delta is not None
        and comp_delta is not None
        and abs(rank_delta) > _RANK_SHIFT_MATERIAL
        and abs(comp_delta) > _COMPOSITE_SHIFT_MATERIAL
    ):
        impact_level = max(impact_level, 3)
        reasons.append(
            "Combined rank and composite shift exceeds material thresholds"
        )

    # Map level to class
    impact_class_map = {
        0: PolicyImpactClass.NO_IMPACT,
        1: PolicyImpactClass.MINOR_ADJUSTMENT,
        2: PolicyImpactClass.INTERPRETATION_CHANGE,
        3: PolicyImpactClass.INVALIDATES_PRIOR_RESULTS,
    }
    impact_class = impact_class_map.get(impact_level, PolicyImpactClass.NO_IMPACT)

    # Recommendation
    recommendations = {
        PolicyImpactClass.NO_IMPACT:
            "No action required.",
        PolicyImpactClass.MINOR_ADJUSTMENT:
            "Minor adjustments needed. Update numerical references only.",
        PolicyImpactClass.INTERPRETATION_CHANGE:
            "Interpretation may have changed. Review all conclusions "
            "that reference this country.",
        PolicyImpactClass.INVALIDATES_PRIOR_RESULTS:
            "PRIOR RESULTS POTENTIALLY INVALID. Any policy document, "
            "report, or analysis referencing this country's ISI output "
            "MUST be revised or retracted.",
    }

    return {
        "country": country,
        "impact_class": impact_class,
        "reasons": reasons,
        "recommendation": recommendations.get(impact_class, "Review required."),
    }


def assess_policy_impact(diff_result: dict[str, Any]) -> dict[str, Any]:
    """Assess policy impact across all countries in a snapshot diff.

    This is the policy-facing summary that answers:
    "What needs to change in published analyses?"

    Args:
        diff_result: Full diff from compare_snapshots().

    Returns:
        Policy impact assessment with per-country and global summary.
    """
    per_country_impacts: dict[str, dict[str, Any]] = {}

    for country, country_diff in diff_result.get("per_country", {}).items():
        per_country_impacts[country] = assess_country_policy_impact(country_diff)

    # Global impact statistics
    impact_counts: dict[str, int] = {
        PolicyImpactClass.NO_IMPACT: 0,
        PolicyImpactClass.MINOR_ADJUSTMENT: 0,
        PolicyImpactClass.INTERPRETATION_CHANGE: 0,
        PolicyImpactClass.INVALIDATES_PRIOR_RESULTS: 0,
    }
    for pi in per_country_impacts.values():
        ic = pi["impact_class"]
        impact_counts[ic] = impact_counts.get(ic, 0) + 1

    n_invalidated = impact_counts[PolicyImpactClass.INVALIDATES_PRIOR_RESULTS]
    n_interpretation = impact_counts[PolicyImpactClass.INTERPRETATION_CHANGE]
    n_minor = impact_counts[PolicyImpactClass.MINOR_ADJUSTMENT]
    n_none = impact_counts[PolicyImpactClass.NO_IMPACT]

    # Overall impact level
    if n_invalidated > 0:
        overall_class = PolicyImpactClass.INVALIDATES_PRIOR_RESULTS
        overall_recommendation = (
            f"{n_invalidated} country(ies) have potentially INVALIDATED "
            f"prior results. ALL published analyses referencing these "
            f"countries must be reviewed and potentially retracted."
        )
    elif n_interpretation > 0:
        overall_class = PolicyImpactClass.INTERPRETATION_CHANGE
        overall_recommendation = (
            f"{n_interpretation} country(ies) have interpretation changes. "
            f"Published analyses should be reviewed."
        )
    elif n_minor > 0:
        overall_class = PolicyImpactClass.MINOR_ADJUSTMENT
        overall_recommendation = (
            f"{n_minor} country(ies) have minor adjustments. "
            f"Update numerical references."
        )
    else:
        overall_class = PolicyImpactClass.NO_IMPACT
        overall_recommendation = "No policy impact. No action required."

    # Countries requiring urgent attention
    urgent_countries = sorted([
        country for country, pi in per_country_impacts.items()
        if pi["impact_class"] == PolicyImpactClass.INVALIDATES_PRIOR_RESULTS
    ])

    return {
        "overall_impact_class": overall_class,
        "overall_recommendation": overall_recommendation,
        "impact_distribution": impact_counts,
        "urgent_countries": urgent_countries,
        "per_country": per_country_impacts,
        "n_total_countries": len(per_country_impacts),
        "honesty_note": (
            "Policy impact classification is STRUCTURAL — it identifies "
            "which published results need review based on the magnitude "
            "and nature of changes. The system CANNOT assess whether "
            "policy conclusions remain valid — only domain experts can "
            "make that judgment."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _isi_country_map(isi_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract {country_code: entry} from ISI JSON.

    Handles both ranking list format and countries dict format.
    """
    result: dict[str, dict[str, Any]] = {}

    # Format 1: ranking list
    ranking = isi_json.get("ranking", [])
    for entry in ranking:
        code = entry.get("country") or entry.get("country_code")
        if code:
            result[code] = entry

    # Format 2: countries dict
    if not result:
        countries = isi_json.get("countries", {})
        if isinstance(countries, dict):
            result = dict(countries)
        elif isinstance(countries, list):
            for entry in countries:
                code = entry.get("country") or entry.get("country_code")
                if code:
                    result[code] = entry

    return result
