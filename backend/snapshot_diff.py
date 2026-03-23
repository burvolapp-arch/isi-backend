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
