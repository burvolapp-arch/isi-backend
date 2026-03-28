"""
backend.construct_enforcement — Construct Validity Enforcement Engine

SECTION 1 of Final Hardening Pass.

Problem addressed:
    The system detects construct substitution (axis 6 logistics using
    Comtrade trade data instead of actual logistics metrics) but does
    NOT enforce consequences. An axis using CONSTRUCT_SUBSTITUTION can
    still contribute fully to the composite score, making the output
    look stronger than it is.

This module enforces:
    - Axes with CONSTRUCT_SUBSTITUTION are CAPPED or EXCLUDED from
      composite calculation.
    - Axes with INVALID construct validity are REMOVED from composite.
    - All enforcement decisions are logged with explicit rule_ids.
    - Enforcement results propagate to governance and usability.

Design contract:
    - VALID: Axis construct is genuine. Full contribution to composite.
    - DEGRADED: Axis uses construct substitution. Contribution CAPPED.
    - INVALID: Axis construct is structurally incompatible AND no
      external validation alignment. EXCLUDED from composite.
    - Every decision has a rule_id and is machine-readable.
    - No silent pass-through of invalid constructs.

Honesty note:
    Construct substitution is NOT the same as "low quality data."
    It means the MEASUREMENT ITSELF does not capture what the axis
    label claims. This is a structural issue, not a data issue.
    Degrading or excluding these axes is epistemically honest —
    it prevents the composite from being a weighted lie.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# CONSTRUCT VALIDITY CLASSES
# ═══════════════════════════════════════════════════════════════════════════

class ConstructValidityClass:
    """Classification of axis construct validity.

    VALID:    Axis measures what it claims. Full composite contribution.
    DEGRADED: Axis uses construct substitution (proxy, not genuine measurement).
              Contribution capped at DEGRADED_WEIGHT_CAP.
    INVALID:  Axis construct is structurally incompatible with the axis label
              AND external validation shows DIVERGENT or NO_DATA.
              Excluded from composite entirely.
    """
    VALID = "CONSTRUCT_VALID"
    DEGRADED = "CONSTRUCT_DEGRADED"
    INVALID = "CONSTRUCT_INVALID"


VALID_CONSTRUCT_CLASSES = frozenset({
    ConstructValidityClass.VALID,
    ConstructValidityClass.DEGRADED,
    ConstructValidityClass.INVALID,
})

# Weight cap for DEGRADED axes in composite calculation.
# A degraded axis contributes at most this fraction of its weight.
# Rationale: construct substitution means the axis captures SOMETHING
# related but not the stated construct. 50% is a generous cap.
DEGRADED_WEIGHT_CAP = 0.50

# Minimum number of VALID axes required for a defensible composite.
MIN_VALID_AXES_FOR_COMPOSITE = 3


# ═══════════════════════════════════════════════════════════════════════════
# CONSTRUCT ENFORCEMENT RULES
# ═══════════════════════════════════════════════════════════════════════════

CONSTRUCT_ENFORCEMENT_RULES: list[dict[str, str]] = [
    {
        "rule_id": "CE-001",
        "name": "Construct Substitution Degrades Axis",
        "description": (
            "If an axis uses CONSTRUCT_SUBSTITUTION (measurement does not "
            "match axis label), the axis is DEGRADED — its contribution "
            "to composite is capped."
        ),
        "trigger": "readiness_level == CONSTRUCT_SUBSTITUTION",
        "action": "DEGRADE — cap composite weight",
    },
    {
        "rule_id": "CE-002",
        "name": "Invalid Construct Excludes Axis",
        "description": (
            "If an axis has CONSTRUCT_SUBSTITUTION AND external validation "
            "shows DIVERGENT alignment on that axis, the construct is "
            "INVALID — excluded from composite entirely."
        ),
        "trigger": (
            "readiness_level == CONSTRUCT_SUBSTITUTION AND "
            "external_alignment == DIVERGENT"
        ),
        "action": "EXCLUDE from composite",
    },
    {
        "rule_id": "CE-003",
        "name": "Logistics Proxy Requires Alignment Evidence",
        "description": (
            "Axis 6 (logistics) for non-EU countries uses Comtrade trade "
            "data as a proxy for logistics capacity. This is acceptable "
            "ONLY if external benchmarks (UNCTAD LSCI, WB LPI) show at "
            "least WEAKLY_ALIGNED."
        ),
        "trigger": (
            "axis_id == 6 AND is_proxy AND "
            "alignment NOT in (STRONGLY_ALIGNED, WEAKLY_ALIGNED)"
        ),
        "action": "DEGRADE or EXCLUDE depending on alignment",
    },
    {
        "rule_id": "CE-004",
        "name": "Insufficient Valid Axes Blocks Composite",
        "description": (
            f"If fewer than {MIN_VALID_AXES_FOR_COMPOSITE} axes have "
            f"CONSTRUCT_VALID status, the composite score is not "
            f"defensible and should not be produced."
        ),
        "trigger": f"n_valid_axes < {MIN_VALID_AXES_FOR_COMPOSITE}",
        "action": "Block composite production",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# CORE ENFORCEMENT FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def enforce_construct_validity(
    axis_id: int,
    readiness_level: str,
    is_proxy: bool = False,
    external_alignment_class: str | None = None,
) -> dict[str, Any]:
    """Enforce construct validity for a single axis.

    Args:
        axis_id: ISI axis number (1-6).
        readiness_level: From ReadinessLevel (SOURCE_CONFIDENT, ...,
            CONSTRUCT_SUBSTITUTION, NOT_AVAILABLE).
        is_proxy: Whether this axis uses proxy data for this country.
        external_alignment_class: AlignmentClass from external validation
            for this axis. None if not assessed.

    Returns:
        Enforcement result with construct_validity_class, weight_factor,
        applied_rules, and explanation.
    """
    applied_rules: list[str] = []
    reasons: list[str] = []

    # Default: VALID
    validity_class = ConstructValidityClass.VALID
    weight_factor = 1.0

    # ── Rule CE-001: Construct substitution degrades ──
    if readiness_level == "CONSTRUCT_SUBSTITUTION":
        validity_class = ConstructValidityClass.DEGRADED
        weight_factor = DEGRADED_WEIGHT_CAP
        applied_rules.append("CE-001")
        reasons.append(
            f"Axis {axis_id} uses CONSTRUCT_SUBSTITUTION — measurement "
            f"does not match axis label. Weight capped at {DEGRADED_WEIGHT_CAP}."
        )

        # ── Rule CE-002: DIVERGENT alignment → INVALID ──
        if external_alignment_class == "DIVERGENT":
            validity_class = ConstructValidityClass.INVALID
            weight_factor = 0.0
            applied_rules.append("CE-002")
            reasons.append(
                f"Axis {axis_id} CONSTRUCT_SUBSTITUTION + DIVERGENT "
                f"external alignment → INVALID. Excluded from composite."
            )

    # ── Rule CE-003: Logistics proxy requires alignment evidence ──
    if axis_id == 6 and is_proxy:
        aligned_classes = {"STRONGLY_ALIGNED", "WEAKLY_ALIGNED"}
        if external_alignment_class not in aligned_classes:
            if validity_class == ConstructValidityClass.VALID:
                validity_class = ConstructValidityClass.DEGRADED
                weight_factor = DEGRADED_WEIGHT_CAP
            applied_rules.append("CE-003")
            if external_alignment_class == "DIVERGENT":
                validity_class = ConstructValidityClass.INVALID
                weight_factor = 0.0
                reasons.append(
                    f"Axis 6 logistics proxy with DIVERGENT alignment → "
                    f"INVALID. No evidence proxy captures logistics capacity."
                )
            elif external_alignment_class is None or external_alignment_class == "NO_DATA":
                reasons.append(
                    f"Axis 6 logistics proxy without alignment evidence. "
                    f"Degraded — cannot confirm proxy measures logistics."
                )
            else:
                reasons.append(
                    f"Axis 6 logistics proxy with alignment class "
                    f"'{external_alignment_class}'. Degraded pending "
                    f"stronger evidence."
                )

    # NOT_AVAILABLE → INVALID always
    if readiness_level == "NOT_AVAILABLE":
        validity_class = ConstructValidityClass.INVALID
        weight_factor = 0.0
        if "CE-001" not in applied_rules and "CE-002" not in applied_rules:
            applied_rules.append("CE-004")
        reasons.append(
            f"Axis {axis_id} has NO data. Cannot contribute to composite."
        )

    return {
        "axis_id": axis_id,
        "construct_validity_class": validity_class,
        "weight_factor": weight_factor,
        "readiness_level": readiness_level,
        "is_proxy": is_proxy,
        "external_alignment_class": external_alignment_class,
        "applied_rules": applied_rules,
        "reasons": reasons,
        "explanation": "; ".join(reasons) if reasons else (
            f"Axis {axis_id} construct is valid — full composite contribution."
        ),
    }


def enforce_all_axes(
    readiness_matrix: list[dict[str, Any]],
    axis_alignment_map: dict[int, str] | None = None,
) -> dict[str, Any]:
    """Enforce construct validity across all 6 axes for a country.

    Args:
        readiness_matrix: Output of build_axis_readiness_matrix() — list of
            per-axis readiness dicts with fields: axis_id, readiness_level,
            construct_substitution, proxy_used.
        axis_alignment_map: {axis_id: alignment_class} from external
            validation. None if not assessed.

    Returns:
        Full enforcement result with per-axis results, composite_producible,
        and effective weights.
    """
    alignment_map = axis_alignment_map or {}
    per_axis: list[dict[str, Any]] = []

    for readiness in readiness_matrix:
        axis_id = readiness["axis_id"]
        level = readiness.get("readiness_level", "NOT_AVAILABLE")
        is_proxy = readiness.get("proxy_used", False)
        alignment = alignment_map.get(axis_id)

        result = enforce_construct_validity(
            axis_id=axis_id,
            readiness_level=level,
            is_proxy=is_proxy,
            external_alignment_class=alignment,
        )
        per_axis.append(result)

    # Aggregate
    n_valid = sum(1 for r in per_axis if r["construct_validity_class"] == ConstructValidityClass.VALID)
    n_degraded = sum(1 for r in per_axis if r["construct_validity_class"] == ConstructValidityClass.DEGRADED)
    n_invalid = sum(1 for r in per_axis if r["construct_validity_class"] == ConstructValidityClass.INVALID)

    composite_producible = n_valid >= MIN_VALID_AXES_FOR_COMPOSITE

    blocked_rules: list[str] = []
    if not composite_producible:
        blocked_rules.append("CE-004")

    # Effective weights for composite calculation
    effective_weights: dict[int, float] = {}
    for r in per_axis:
        effective_weights[r["axis_id"]] = r["weight_factor"]

    # Normalized effective weights (sum to 1.0 for contributing axes)
    total_weight = sum(w for w in effective_weights.values() if w > 0)
    normalized_weights: dict[int, float] = {}
    for ax, w in effective_weights.items():
        if total_weight > 0 and w > 0:
            normalized_weights[ax] = round(w / total_weight, 8)
        else:
            normalized_weights[ax] = 0.0

    return {
        "per_axis": per_axis,
        "n_valid": n_valid,
        "n_degraded": n_degraded,
        "n_invalid": n_invalid,
        "composite_producible": composite_producible,
        "blocked_rules": blocked_rules,
        "effective_weights": effective_weights,
        "normalized_weights": normalized_weights,
        "honesty_note": (
            f"Construct enforcement: {n_valid} VALID, {n_degraded} DEGRADED, "
            f"{n_invalid} INVALID axes. "
            f"{'Composite IS producible.' if composite_producible else 'Composite IS NOT producible — insufficient valid axes.'} "
            f"Degraded axes contribute at {DEGRADED_WEIGHT_CAP:.0%} weight. "
            f"Invalid axes are excluded entirely."
        ),
    }


def compute_construct_adjusted_composite(
    axis_scores: dict[int, float | None],
    enforcement_result: dict[str, Any],
) -> dict[str, Any]:
    """Compute composite score with construct validity adjustments.

    Unlike the raw unweighted mean, this applies construct-adjusted
    weights: VALID axes get full weight, DEGRADED axes get capped weight,
    INVALID axes get zero weight.

    Args:
        axis_scores: {axis_id: score_or_None} for axes 1-6.
        enforcement_result: Output of enforce_all_axes().

    Returns:
        Adjusted composite with comparison to raw composite.
    """
    if not enforcement_result["composite_producible"]:
        return {
            "adjusted_composite": None,
            "raw_composite": _raw_mean(axis_scores),
            "composite_blocked": True,
            "block_reason": (
                f"Only {enforcement_result['n_valid']} VALID axes — "
                f"minimum {MIN_VALID_AXES_FOR_COMPOSITE} required."
            ),
            "effective_weights": enforcement_result["effective_weights"],
        }

    weights = enforcement_result["effective_weights"]
    weighted_sum = 0.0
    total_weight = 0.0

    for axis_id in range(1, 7):
        score = axis_scores.get(axis_id)
        w = weights.get(axis_id, 0.0)
        if score is not None and w > 0:
            weighted_sum += score * w
            total_weight += w

    if total_weight == 0:
        adjusted = None
    else:
        adjusted = round(weighted_sum / total_weight, 8)

    raw = _raw_mean(axis_scores)

    return {
        "adjusted_composite": adjusted,
        "raw_composite": raw,
        "composite_blocked": False,
        "adjustment_delta": (
            round(adjusted - raw, 8)
            if adjusted is not None and raw is not None
            else None
        ),
        "effective_weights": weights,
        "honesty_note": (
            f"Adjusted composite applies construct validity weights. "
            f"Raw (unweighted) mean: {raw}. Adjusted: {adjusted}. "
            f"{'Delta shows construct substitution impact.' if adjusted != raw else 'No adjustment needed — all constructs valid.'}"
        ),
    }


def _raw_mean(axis_scores: dict[int, float | None]) -> float | None:
    """Compute raw unweighted mean of available axis scores."""
    valid = [s for s in axis_scores.values() if s is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 8)


# ═══════════════════════════════════════════════════════════════════════════
# SHOULD_EXCLUDE_FROM_RANKING
# ═══════════════════════════════════════════════════════════════════════════

def should_exclude_from_ranking(
    enforcement_result: dict[str, Any],
) -> dict[str, Any]:
    """Determine if construct enforcement requires ranking exclusion.

    Countries whose composite is blocked by construct invalidity
    MUST NOT appear in rankings.
    """
    blocked = not enforcement_result["composite_producible"]
    n_invalid = enforcement_result["n_invalid"]

    exclude = blocked or n_invalid >= 3

    reasons: list[str] = []
    if blocked:
        reasons.append(
            f"Composite not producible — {enforcement_result['n_valid']} "
            f"valid axes (min {MIN_VALID_AXES_FOR_COMPOSITE})"
        )
    if n_invalid >= 3:
        reasons.append(
            f"{n_invalid} axes with INVALID construct — majority of profile "
            f"is not measuring stated constructs"
        )

    return {
        "exclude_from_ranking": exclude,
        "reasons": reasons,
        "n_invalid_axes": n_invalid,
        "n_valid_axes": enforcement_result["n_valid"],
        "rule_id": "CE-004" if blocked else ("CE-002" if n_invalid >= 3 else None),
    }


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRY ACCESSORS
# ═══════════════════════════════════════════════════════════════════════════

def get_construct_enforcement_rules() -> list[dict[str, str]]:
    """Return the full construct enforcement rule registry."""
    return list(CONSTRUCT_ENFORCEMENT_RULES)


def get_degraded_weight_cap() -> float:
    """Return the current weight cap for DEGRADED axes."""
    return DEGRADED_WEIGHT_CAP
