"""
backend.invariants — Structural Invariants Engine

SYSTEM 1: Detects when the system produces internally inconsistent outputs,
even when all computations are technically correct.

Three classes of invariants:
    1. CROSS_AXIS — logical contradictions across axes
    2. GOVERNANCE — governance output consistency
    3. TEMPORAL — cross-version snapshot consistency

Each violation produces a structured record with:
    invariant_id, type, severity, description, affected_country, evidence

Design contract:
    - Invariant checks are PURE FUNCTIONS — no side effects.
    - All checks are deterministic and auditable.
    - CRITICAL violations automatically downgrade DecisionUsabilityClass.
    - Invariant results are attached to country JSON and ISI export.
    - This module does NOT modify scores.

Honesty note:
    Invariants verify INTERNAL CONSISTENCY, not external validity.
    A system can be perfectly internally consistent and still wrong.
    Invariants catch structural anomalies — they do not validate truth.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# INVARIANT TYPES AND SEVERITY
# ═══════════════════════════════════════════════════════════════════════════

class InvariantType:
    """Classification of invariant checks."""
    CROSS_AXIS = "CROSS_AXIS"
    GOVERNANCE = "GOVERNANCE"
    TEMPORAL = "TEMPORAL"


VALID_INVARIANT_TYPES = frozenset({
    InvariantType.CROSS_AXIS,
    InvariantType.GOVERNANCE,
    InvariantType.TEMPORAL,
})


class InvariantSeverity:
    """Severity of an invariant violation."""
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


VALID_SEVERITIES = frozenset({
    InvariantSeverity.WARNING,
    InvariantSeverity.ERROR,
    InvariantSeverity.CRITICAL,
})


# ═══════════════════════════════════════════════════════════════════════════
# INVARIANT REGISTRY — every invariant has a unique ID and rule
# ═══════════════════════════════════════════════════════════════════════════

INVARIANT_REGISTRY: list[dict[str, str]] = [
    # ── Cross-Axis Invariants ──
    {
        "invariant_id": "CA-001",
        "type": InvariantType.CROSS_AXIS,
        "name": "Logistics Divergence from Goods-Based Axes",
        "description": (
            "If logistics concentration (Axis 6) increases while ALL "
            "goods-based axes (2, 3, 5) decrease, the pattern is suspicious — "
            "logistics should co-move with trade flows."
        ),
    },
    {
        "invariant_id": "CA-002",
        "type": InvariantType.CROSS_AXIS,
        "name": "Producer Country High-Import Anomaly",
        "description": (
            "A country with registered producer inversions should NOT show "
            "high import concentration (score > 0.6) on inverted axes."
        ),
    },
    {
        "invariant_id": "CA-003",
        "type": InvariantType.CROSS_AXIS,
        "name": "Low Axis Majority with High Composite",
        "description": (
            "If 4+ out of 6 axes have scores < 0.15, the composite should "
            "not exceed 0.25. A high composite with mostly low axes signals "
            "that one axis is dominating the unweighted mean."
        ),
    },
    {
        "invariant_id": "CA-004",
        "type": InvariantType.CROSS_AXIS,
        "name": "Uniform Score Anomaly",
        "description": (
            "If all 6 axis scores are within 0.02 of each other, this "
            "is structurally improbable — different data sources measuring "
            "different constructs should not produce identical values."
        ),
    },
    # ── Governance Consistency Invariants ──
    {
        "invariant_id": "GOV-001",
        "type": InvariantType.GOVERNANCE,
        "name": "Ranking Eligible but Wrong Tier",
        "description": (
            "ranking_eligible=True is only valid for FULLY_COMPARABLE "
            "or PARTIALLY_COMPARABLE tiers."
        ),
    },
    {
        "invariant_id": "GOV-002",
        "type": InvariantType.GOVERNANCE,
        "name": "Cross-Comparable with Excessive Inversions",
        "description": (
            "cross_country_comparable=True should not be possible "
            "with n_producer_inverted_axes > MAX_INVERTED threshold."
        ),
    },
    {
        "invariant_id": "GOV-003",
        "type": InvariantType.GOVERNANCE,
        "name": "LOW_CONFIDENCE but Ranked",
        "description": (
            "A country at LOW_CONFIDENCE or NON_COMPARABLE must not "
            "have ranking_eligible=True."
        ),
    },
    {
        "invariant_id": "GOV-004",
        "type": InvariantType.GOVERNANCE,
        "name": "Composite Defensible but Non-Comparable",
        "description": (
            "composite_defensible=True should not coexist with "
            "governance_tier=NON_COMPARABLE."
        ),
    },
    {
        "invariant_id": "GOV-005",
        "type": InvariantType.GOVERNANCE,
        "name": "Confidence–Tier Mismatch",
        "description": (
            "Mean axis confidence below MIN_MEAN_CONFIDENCE_FOR_RANKING "
            "but governance tier is FULLY_COMPARABLE."
        ),
    },
    {
        "invariant_id": "GOV-006",
        "type": InvariantType.GOVERNANCE,
        "name": "Sanctions Flag but High Tier",
        "description": (
            "A country with SANCTIONS_DISTORTION flag on any axis "
            "must not be FULLY_COMPARABLE or PARTIALLY_COMPARABLE."
        ),
    },
    # ── Temporal / Snapshot Invariants ──
    {
        "invariant_id": "TEMP-001",
        "type": InvariantType.TEMPORAL,
        "name": "Large Rank Shift without Input Change",
        "description": (
            "Rank change > 5 positions between versions without any "
            "axis score changing by > 0.05."
        ),
    },
    {
        "invariant_id": "TEMP-002",
        "type": InvariantType.TEMPORAL,
        "name": "Composite Change without Axis Change",
        "description": (
            "Composite changed by > 0.02 but no individual axis "
            "changed by > 0.01."
        ),
    },
    {
        "invariant_id": "TEMP-003",
        "type": InvariantType.TEMPORAL,
        "name": "Governance Tier Change without Structural Cause",
        "description": (
            "Governance tier changed between versions without an "
            "axis confidence change, inversion change, or severity change."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# VIOLATION CONSTRUCTOR
# ═══════════════════════════════════════════════════════════════════════════

def _violation(
    invariant_id: str,
    inv_type: str,
    severity: str,
    description: str,
    country: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Construct a canonical invariant violation record."""
    return {
        "invariant_id": invariant_id,
        "type": inv_type,
        "severity": severity,
        "description": description,
        "affected_country": country,
        "evidence": evidence,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-AXIS INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_cross_axis_invariants(
    country: str,
    axis_scores: dict[int, float | None],
    governance_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check cross-axis structural invariants for a single country.

    Args:
        country: ISO-2 code.
        axis_scores: {axis_id: score} for axes 1-6. None if missing.
        governance_result: governance dict from assess_country_governance().

    Returns:
        List of violation dicts (empty if no violations).
    """
    violations: list[dict[str, Any]] = []
    present = {k: v for k, v in axis_scores.items() if v is not None}

    if len(present) < 3:
        return violations  # Not enough data for cross-axis checks

    # ── CA-001: Logistics divergence from goods-based axes ──
    logistics = axis_scores.get(6)
    goods_axes = [axis_scores.get(a) for a in (2, 3, 5)]
    goods_valid = [s for s in goods_axes if s is not None]
    if logistics is not None and len(goods_valid) >= 2:
        goods_mean = sum(goods_valid) / len(goods_valid)
        # If logistics is > 2x goods mean and goods mean is very low
        if goods_mean < 0.10 and logistics > 0.30:
            violations.append(_violation(
                invariant_id="CA-001",
                inv_type=InvariantType.CROSS_AXIS,
                severity=InvariantSeverity.WARNING,
                description=(
                    f"Logistics axis ({logistics:.4f}) is significantly higher "
                    f"than goods-based axes mean ({goods_mean:.4f}). "
                    f"Logistics should co-move with trade flows."
                ),
                country=country,
                evidence={
                    "logistics_score": logistics,
                    "goods_mean": round(goods_mean, 8),
                    "goods_scores": {a: axis_scores.get(a) for a in (2, 3, 5)},
                },
            ))

    # ── CA-002: Producer country high-import anomaly ──
    if governance_result:
        inverted_axes = governance_result.get("producer_inverted_axes", [])
        for ax_id in inverted_axes:
            score = axis_scores.get(ax_id)
            if score is not None and score > 0.60:
                violations.append(_violation(
                    invariant_id="CA-002",
                    inv_type=InvariantType.CROSS_AXIS,
                    severity=InvariantSeverity.ERROR,
                    description=(
                        f"Producer-inverted axis {ax_id} has high import "
                        f"concentration ({score:.4f} > 0.60). A major exporter "
                        f"should not show high import dependency."
                    ),
                    country=country,
                    evidence={
                        "axis_id": ax_id,
                        "score": score,
                        "threshold": 0.60,
                        "inverted_axes": inverted_axes,
                    },
                ))

    # ── CA-003: Low axis majority with high composite ──
    all_scores = [v for v in present.values()]
    if len(all_scores) >= 4:
        n_low = sum(1 for s in all_scores if s < 0.15)
        composite = sum(all_scores) / len(all_scores)
        if n_low >= 4 and composite > 0.25:
            violations.append(_violation(
                invariant_id="CA-003",
                inv_type=InvariantType.CROSS_AXIS,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"{n_low} axes have scores < 0.15 but composite is "
                    f"{composite:.4f} > 0.25. One axis may be dominating "
                    f"the unweighted mean."
                ),
                country=country,
                evidence={
                    "n_low_axes": n_low,
                    "composite": round(composite, 8),
                    "scores": dict(present),
                },
            ))

    # ── CA-004: Uniform score anomaly ──
    if len(all_scores) == 6:
        score_range = max(all_scores) - min(all_scores)
        if score_range < 0.02:
            violations.append(_violation(
                invariant_id="CA-004",
                inv_type=InvariantType.CROSS_AXIS,
                severity=InvariantSeverity.WARNING,
                description=(
                    f"All 6 axis scores are within {score_range:.4f} of each "
                    f"other. Structurally improbable for independent data sources."
                ),
                country=country,
                evidence={
                    "score_range": round(score_range, 8),
                    "min_score": min(all_scores),
                    "max_score": max(all_scores),
                    "scores": dict(present),
                },
            ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# GOVERNANCE CONSISTENCY INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_governance_invariants(
    country: str,
    governance_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check that governance outputs are internally consistent.

    Args:
        country: ISO-2 code.
        governance_result: from assess_country_governance().

    Returns:
        List of violation dicts (empty if consistent).
    """
    violations: list[dict[str, Any]] = []

    tier = governance_result.get("governance_tier", "UNKNOWN")
    ranking_eligible = governance_result.get("ranking_eligible", False)
    comparable = governance_result.get("cross_country_comparable", False)
    composite_defensible = governance_result.get("composite_defensible", False)
    n_inverted = governance_result.get("n_producer_inverted_axes", 0)
    mean_conf = governance_result.get("mean_axis_confidence", 0)

    # Import thresholds
    from backend.governance import (
        MAX_INVERTED_AXES_FOR_COMPARABLE,
        MIN_MEAN_CONFIDENCE_FOR_RANKING,
    )

    # ── GOV-001: ranking_eligible only for FULLY or PARTIALLY ──
    if ranking_eligible and tier not in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE"):
        violations.append(_violation(
            invariant_id="GOV-001",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"ranking_eligible=True but tier={tier}. "
                f"Only FULLY or PARTIALLY_COMPARABLE may be ranking-eligible."
            ),
            country=country,
            evidence={
                "ranking_eligible": ranking_eligible,
                "governance_tier": tier,
            },
        ))

    # ── GOV-002: cross_country_comparable with excessive inversions ──
    if comparable and n_inverted > MAX_INVERTED_AXES_FOR_COMPARABLE:
        violations.append(_violation(
            invariant_id="GOV-002",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"cross_country_comparable=True but {n_inverted} inverted "
                f"axes exceed threshold ({MAX_INVERTED_AXES_FOR_COMPARABLE})."
            ),
            country=country,
            evidence={
                "cross_country_comparable": comparable,
                "n_inverted": n_inverted,
                "max_threshold": MAX_INVERTED_AXES_FOR_COMPARABLE,
            },
        ))

    # ── GOV-003: LOW_CONFIDENCE or NON_COMPARABLE must not be ranking-eligible ──
    if ranking_eligible and tier in ("LOW_CONFIDENCE", "NON_COMPARABLE"):
        violations.append(_violation(
            invariant_id="GOV-003",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"ranking_eligible=True but tier={tier}. "
                f"LOW_CONFIDENCE and NON_COMPARABLE are never ranking-eligible."
            ),
            country=country,
            evidence={
                "ranking_eligible": ranking_eligible,
                "governance_tier": tier,
            },
        ))

    # ── GOV-004: composite_defensible + NON_COMPARABLE ──
    if composite_defensible and tier == "NON_COMPARABLE":
        violations.append(_violation(
            invariant_id="GOV-004",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"composite_defensible=True but tier=NON_COMPARABLE. "
                f"A non-comparable country cannot have a defensible composite."
            ),
            country=country,
            evidence={
                "composite_defensible": composite_defensible,
                "governance_tier": tier,
            },
        ))

    # ── GOV-005: confidence–tier mismatch ──
    if (tier == "FULLY_COMPARABLE"
            and mean_conf < MIN_MEAN_CONFIDENCE_FOR_RANKING):
        violations.append(_violation(
            invariant_id="GOV-005",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.ERROR,
            description=(
                f"FULLY_COMPARABLE but mean confidence {mean_conf:.4f} is "
                f"below MIN_MEAN_CONFIDENCE_FOR_RANKING "
                f"({MIN_MEAN_CONFIDENCE_FOR_RANKING})."
            ),
            country=country,
            evidence={
                "governance_tier": tier,
                "mean_confidence": mean_conf,
                "threshold": MIN_MEAN_CONFIDENCE_FOR_RANKING,
            },
        ))

    # ── GOV-006: sanctions flag but high tier ──
    axis_confs = governance_result.get("axis_confidences", [])
    has_sanctions = False
    for ac in axis_confs:
        for p in ac.get("penalties_applied", []):
            if p.get("flag") == "SANCTIONS_DISTORTION":
                has_sanctions = True
                break
    if has_sanctions and tier in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE"):
        violations.append(_violation(
            invariant_id="GOV-006",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"SANCTIONS_DISTORTION penalty applied but tier={tier}. "
                f"Sanctioned countries must be LOW_CONFIDENCE or NON_COMPARABLE."
            ),
            country=country,
            evidence={
                "governance_tier": tier,
                "sanctions_flag_present": True,
            },
        ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# TEMPORAL / SNAPSHOT INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_temporal_invariants(
    country: str,
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check temporal consistency between two country snapshots.

    Args:
        country: ISO-2 code.
        snapshot_a: Earlier country detail dict (from build_country_json).
        snapshot_b: Later country detail dict (from build_country_json).

    Returns:
        List of violation dicts (empty if temporally consistent).
    """
    violations: list[dict[str, Any]] = []

    composite_a = snapshot_a.get("isi_composite")
    composite_b = snapshot_b.get("isi_composite")
    rank_a = snapshot_a.get("rank")
    rank_b = snapshot_b.get("rank")

    # Extract axis scores
    axes_a: dict[int, float | None] = {}
    axes_b: dict[int, float | None] = {}
    for ax in snapshot_a.get("axes", []):
        axes_a[ax["axis_id"]] = ax.get("score")
    for ax in snapshot_b.get("axes", []):
        axes_b[ax["axis_id"]] = ax.get("score")

    # Extract governance
    gov_a = snapshot_a.get("governance", {})
    gov_b = snapshot_b.get("governance", {})
    tier_a = gov_a.get("governance_tier", "UNKNOWN")
    tier_b = gov_b.get("governance_tier", "UNKNOWN")

    # Compute max axis delta
    max_axis_delta = 0.0
    axis_deltas: dict[int, float] = {}
    for ax_id in range(1, 7):
        sa = axes_a.get(ax_id)
        sb = axes_b.get(ax_id)
        if sa is not None and sb is not None:
            delta = abs(sb - sa)
            axis_deltas[ax_id] = round(delta, 8)
            if delta > max_axis_delta:
                max_axis_delta = delta

    # ── TEMP-001: Large rank shift without input change ──
    if rank_a is not None and rank_b is not None:
        rank_shift = abs(rank_b - rank_a)
        if rank_shift > 5 and max_axis_delta < 0.05:
            violations.append(_violation(
                invariant_id="TEMP-001",
                inv_type=InvariantType.TEMPORAL,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"Rank shifted by {rank_shift} positions but max axis "
                    f"delta is only {max_axis_delta:.4f} (< 0.05)."
                ),
                country=country,
                evidence={
                    "rank_a": rank_a,
                    "rank_b": rank_b,
                    "rank_shift": rank_shift,
                    "max_axis_delta": max_axis_delta,
                    "axis_deltas": axis_deltas,
                },
            ))

    # ── TEMP-002: Composite change without axis change ──
    if composite_a is not None and composite_b is not None:
        composite_delta = abs(composite_b - composite_a)
        if composite_delta > 0.02 and max_axis_delta < 0.01:
            violations.append(_violation(
                invariant_id="TEMP-002",
                inv_type=InvariantType.TEMPORAL,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Composite changed by {composite_delta:.4f} but no axis "
                    f"changed by more than {max_axis_delta:.4f}. "
                    f"Composite should be derived from axes."
                ),
                country=country,
                evidence={
                    "composite_a": composite_a,
                    "composite_b": composite_b,
                    "composite_delta": round(composite_delta, 8),
                    "max_axis_delta": max_axis_delta,
                    "axis_deltas": axis_deltas,
                },
            ))

    # ── TEMP-003: Governance tier change without structural cause ──
    if tier_a != tier_b and tier_a != "UNKNOWN" and tier_b != "UNKNOWN":
        n_inv_a = gov_a.get("n_producer_inverted_axes", 0)
        n_inv_b = gov_b.get("n_producer_inverted_axes", 0)
        conf_a = gov_a.get("mean_axis_confidence", 0)
        conf_b = gov_b.get("mean_axis_confidence", 0)
        conf_delta = abs(conf_b - conf_a)

        # A tier change without inversion change or confidence change
        if n_inv_a == n_inv_b and conf_delta < 0.05 and max_axis_delta < 0.05:
            violations.append(_violation(
                invariant_id="TEMP-003",
                inv_type=InvariantType.TEMPORAL,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"Governance tier changed from {tier_a} to {tier_b} "
                    f"without structural cause (no inversion change, "
                    f"confidence delta {conf_delta:.4f} < 0.05, "
                    f"max axis delta {max_axis_delta:.4f} < 0.05)."
                ),
                country=country,
                evidence={
                    "tier_a": tier_a,
                    "tier_b": tier_b,
                    "n_inverted_a": n_inv_a,
                    "n_inverted_b": n_inv_b,
                    "confidence_delta": round(conf_delta, 8),
                    "max_axis_delta": max_axis_delta,
                },
            ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# UNIFIED INVARIANT ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def assess_country_invariants(
    country: str,
    axis_scores: dict[int, float | None],
    governance_result: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
    current_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all invariant checks for a single country.

    Args:
        country: ISO-2 code.
        axis_scores: {axis_id: score_or_None} for axes 1-6.
        governance_result: from assess_country_governance().
        previous_snapshot: Earlier country JSON (for temporal checks).
        current_snapshot: Current country JSON (for temporal checks).

    Returns:
        Invariant assessment with violations, counts, and severity summary.
    """
    all_violations: list[dict[str, Any]] = []

    # Cross-axis checks
    all_violations.extend(
        check_cross_axis_invariants(country, axis_scores, governance_result)
    )

    # Governance consistency checks
    all_violations.extend(
        check_governance_invariants(country, governance_result)
    )

    # Temporal checks (only if both snapshots provided)
    if previous_snapshot is not None and current_snapshot is not None:
        all_violations.extend(
            check_temporal_invariants(country, previous_snapshot, current_snapshot)
        )

    # Severity counts
    n_warning = sum(1 for v in all_violations if v["severity"] == InvariantSeverity.WARNING)
    n_error = sum(1 for v in all_violations if v["severity"] == InvariantSeverity.ERROR)
    n_critical = sum(1 for v in all_violations if v["severity"] == InvariantSeverity.CRITICAL)

    return {
        "country": country,
        "n_violations": len(all_violations),
        "n_warnings": n_warning,
        "n_errors": n_error,
        "n_critical": n_critical,
        "has_critical": n_critical > 0,
        "violations": all_violations,
        "honesty_note": (
            "Invariant checks verify INTERNAL CONSISTENCY only. "
            "Zero violations does NOT mean the outputs are correct — "
            "it means they are structurally coherent."
        ),
    }


def assess_all_invariants(
    all_scores: dict[int, dict[str, float]],
    governance_results: dict[str, dict[str, Any]],
    previous_snapshots: dict[str, dict[str, Any]] | None = None,
    current_snapshots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run invariant checks for all countries.

    Args:
        all_scores: {axis_id: {country: score}}.
        governance_results: {country: governance_dict}.
        previous_snapshots: {country: earlier_country_json} (optional).
        current_snapshots: {country: current_country_json} (optional).

    Returns:
        {country: invariant_assessment}.
    """
    results: dict[str, dict[str, Any]] = {}
    for country, gov in governance_results.items():
        axis_scores: dict[int, float | None] = {}
        for ax_id in range(1, 7):
            axis_scores[ax_id] = all_scores.get(ax_id, {}).get(country)

        prev = (previous_snapshots or {}).get(country)
        curr = (current_snapshots or {}).get(country)

        results[country] = assess_country_invariants(
            country, axis_scores, gov, prev, curr,
        )
    return results


def get_invariant_summary(
    invariant_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate invariant results across all countries."""
    total_countries = len(invariant_results)
    total_violations = sum(r["n_violations"] for r in invariant_results.values())
    total_critical = sum(r["n_critical"] for r in invariant_results.values())
    total_errors = sum(r["n_errors"] for r in invariant_results.values())
    total_warnings = sum(r["n_warnings"] for r in invariant_results.values())

    countries_with_violations = sorted(
        c for c, r in invariant_results.items() if r["n_violations"] > 0
    )
    countries_with_critical = sorted(
        c for c, r in invariant_results.items() if r["n_critical"] > 0
    )

    return {
        "total_countries_assessed": total_countries,
        "total_violations": total_violations,
        "total_critical": total_critical,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "countries_with_violations": countries_with_violations,
        "countries_with_critical": countries_with_critical,
        "system_consistent": total_critical == 0,
        "interpretation": (
            f"Of {total_countries} countries, {len(countries_with_violations)} "
            f"have invariant violations. {total_critical} critical, "
            f"{total_errors} errors, {total_warnings} warnings."
        ),
        "honesty_note": (
            "Invariant checks verify internal consistency only. "
            "system_consistent=True means no structural contradictions, "
            "NOT that the outputs are empirically correct."
        ),
    }


def get_invariant_registry() -> list[dict[str, str]]:
    """Return the full invariant registry."""
    return list(INVARIANT_REGISTRY)


def should_downgrade_usability(
    invariant_result: dict[str, Any],
) -> bool:
    """Determine if invariant violations require usability downgrade.

    CRITICAL invariant violations MUST downgrade DecisionUsabilityClass.
    """
    return invariant_result.get("has_critical", False)
