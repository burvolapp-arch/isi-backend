"""
backend.severity — Weighted degradation severity model for ISI v1.1+.

Replaces binary degradation counting with a calibrated severity model
that quantifies the degree to which each data quality issue reduces
the interpretability and comparability of an axis or composite score.

Design contract:
    - SEVERITY_WEIGHTS is the ONLY place severity weights are defined.
    - compute_axis_severity() is the ONLY function that computes per-axis severity.
    - compute_country_severity() is the ONLY function that computes per-country severity.
    - assign_comparability_tier() is deterministic, threshold-driven, no manual overrides.
    - check_cross_country_comparability() enforces pairwise comparability guards.
    - compute_stability_analysis() runs leave-one-out axis removal.
    - build_interpretation() generates mandatory interpretation flags and summary.

Severity weights are justified below. They are NOT arbitrary — they reflect
the degree to which each issue distorts the measured construct (bilateral
concentration via HHI). Higher weight = greater distortion of the score's
meaning relative to an unflagged score.

This module does NOT modify scores, formulas, or the HHI construct.
It quantifies the epistemic reliability of each score.
"""

from __future__ import annotations

import math
from typing import Any

from backend.constants import ROUND_PRECISION


# ---------------------------------------------------------------------------
# SEVERITY WEIGHTS — Calibrated, documented, extensible
# ---------------------------------------------------------------------------
# Each weight ∈ [0.0, 1.0] represents the fractional reduction in
# interpretive reliability caused by the corresponding data quality issue.
#
# Calibration rationale (each justified individually):
#
#   HS6_GRANULARITY (0.2):
#       HS6 vs CN8 collapses ~7 semiconductor subcategories to ~3.
#       HHI is computed over the same partner set; only Channel B
#       category weights change. Empirically, EU-27 CN8→HS6 mapping
#       shows <5% score deviation for most countries. Low severity.
#
#   TEMPORAL_MISMATCH (0.3):
#       Mixing partners from different years breaks point-in-time
#       bilateral structure. Partner set may partially overlap.
#       PRO-003 declares this as DEGRADED, not INVALID. Moderate.
#
#   SINGLE_CHANNEL_A (0.4):
#       Loss of Channel B removes one entire dimension of bilateral
#       structure (e.g., portfolio debt for financial, category weights
#       for technology). Score reflects only Channel A concentration.
#       Moderate-to-high: the construct is narrowed but not destroyed.
#
#   SOURCE_HETEROGENEITY (0.4):
#       Composite merges axes from incompatible data sources (e.g.,
#       BIS + Comtrade + SIPRI). Each source has different partner
#       universes, coverage, and classification. Cross-axis mixing
#       reduces composite interpretability. Same severity as channel loss.
#
#   CPIS_NON_PARTICIPANT (0.5):
#       IMF CPIS absence eliminates portfolio investment concentration
#       entirely. For Axis 1, this means only banking claims (BIS LBS)
#       are measured. The financial exposure construct is halved.
#       Higher than generic channel loss because the specific absent
#       channel (portfolio debt) is economically significant.
#
#   ZERO_BILATERAL_SUPPLIERS (0.6):
#       Zero imports → HHI = 0.0 by default (D-5 semantic). The score
#       is technically valid but measures "absence of bilateral dependency"
#       not "low concentration." This is a construct-level ambiguity.
#       High severity: the score is correct but semantically misleading.
#
#   PRODUCER_INVERSION (0.7):
#       Country is a major global exporter of the measured commodity.
#       Import concentration is mechanically low or undefined.
#       The ISI construct (import concentration) does not capture
#       the country's actual strategic position on this axis.
#       Very high severity: score is correct but misrepresents reality.
#
#   SANCTIONS_DISTORTION (1.0):
#       Active sanctions regime during the measurement window
#       fundamentally alters trade patterns. Data reflects a
#       crisis-distorted regime, not steady-state bilateral structure.
#       Maximum severity: score is not comparable to any non-sanctioned
#       country under any interpretation.
#
# Extensibility: Add new entries to SEVERITY_WEIGHTS with a float ∈ [0.0, 1.0]
# and a documented rationale. No other code changes required — the severity
# computation engine picks up new flags automatically.
# ---------------------------------------------------------------------------

SEVERITY_WEIGHTS: dict[str, float] = {
    "HS6_GRANULARITY": 0.2,
    "SINGLE_CHANNEL_A": 0.4,
    "SINGLE_CHANNEL_B": 0.4,          # Symmetric with A — same construct loss
    "CPIS_NON_PARTICIPANT": 0.5,
    "PRODUCER_INVERSION": 0.7,
    "SANCTIONS_DISTORTION": 1.0,
    "ZERO_BILATERAL_SUPPLIERS": 0.6,
    "TEMPORAL_MISMATCH": 0.3,
    "SOURCE_HETEROGENEITY": 0.4,
    "REDUCED_PRODUCT_GRANULARITY": 0.2,  # Alias for HS6 in flag namespace
}

# Flag-to-severity mapping (maps data_quality_flags → SEVERITY_WEIGHTS keys)
# This handles the namespace difference between data_quality_flags and
# severity weight keys.
_FLAG_TO_SEVERITY_KEY: dict[str, str] = {
    "SINGLE_CHANNEL_A": "SINGLE_CHANNEL_A",
    "SINGLE_CHANNEL_B": "SINGLE_CHANNEL_B",
    "REDUCED_PRODUCT_GRANULARITY": "REDUCED_PRODUCT_GRANULARITY",
    "PRODUCER_INVERSION": "PRODUCER_INVERSION",
    "SANCTIONS_DISTORTION": "SANCTIONS_DISTORTION",
    "CPIS_NON_PARTICIPANT": "CPIS_NON_PARTICIPANT",
    "ZERO_BILATERAL_SUPPLIERS": "ZERO_BILATERAL_SUPPLIERS",
    "TEMPORAL_MISMATCH": "TEMPORAL_MISMATCH",
}


# ---------------------------------------------------------------------------
# DEGRADATION GROUPS — Dependency-aware severity resolution
# ---------------------------------------------------------------------------
# Problem: CPIS_NON_PARTICIPANT and SINGLE_CHANNEL_A both represent
# "loss of a bilateral data channel." Summing both double-counts the
# same construct-level damage. Similarly, HS6_GRANULARITY and
# REDUCED_PRODUCT_GRANULARITY are the same underlying issue.
#
# Resolution: Group flags by the underlying degradation mechanism.
# Within each group, take MAX (worst representative). Across groups, SUM.
# This prevents inflating severity from redundant flags while preserving
# independent orthogonal contributions.
#
# Groups:
#   CHANNEL_LOSS — flags representing loss of a bilateral data channel.
#                  CPIS absence IS channel loss (eliminates Channel B for Axis 1).
#                  SINGLE_CHANNEL_A/B are the generic form.
#                  Max-within-group: the worst channel loss dominates.
#
#   DATA_GRANULARITY — granularity/temporal resolution issues.
#                      HS6_GRANULARITY and REDUCED_PRODUCT_GRANULARITY
#                      are the same underlying issue (CN8→HS6 collapse).
#                      TEMPORAL_MISMATCH is a temporal resolution issue.
#
#   STRUCTURAL_BIAS — structural position invalidates the import-concentration
#                     construct. PRODUCER_INVERSION is the canonical case.
#
#   DATA_VALIDITY — regime-level data distortion. SANCTIONS_DISTORTION.
#
#   CONSTRUCT_AMBIGUITY — the measured quantity is technically correct but
#                         semantically misleading. ZERO_BILATERAL_SUPPLIERS.
#
# Ungrouped flags: severity weights for flags not in any group are added
# independently (backward-compatible extensibility).

DEGRADATION_GROUPS: dict[str, list[str]] = {
    "CHANNEL_LOSS": [
        "CPIS_NON_PARTICIPANT",
        "SINGLE_CHANNEL_A",
        "SINGLE_CHANNEL_B",
    ],
    "DATA_GRANULARITY": [
        "HS6_GRANULARITY",
        "REDUCED_PRODUCT_GRANULARITY",
        "TEMPORAL_MISMATCH",
    ],
    "STRUCTURAL_BIAS": [
        "PRODUCER_INVERSION",
    ],
    "DATA_VALIDITY": [
        "SANCTIONS_DISTORTION",
    ],
    "CONSTRUCT_AMBIGUITY": [
        "ZERO_BILATERAL_SUPPLIERS",
    ],
}

# Precompute reverse lookup: severity_key → group_name
_SEVERITY_KEY_TO_GROUP: dict[str, str] = {}
for _group_name, _members in DEGRADATION_GROUPS.items():
    for _member in _members:
        _SEVERITY_KEY_TO_GROUP[_member] = _group_name


# ---------------------------------------------------------------------------
# STRUCTURAL FLAGS — Severity contributes to comparability but NOT aggregation
# ---------------------------------------------------------------------------
# These flags reflect the country's economic position, not data quality.
# Their severity enters total_severity (for tier/comparability assessment)
# but is EXCLUDED from the quality weight function ω(·) that drives
# the degradation-adjusted composite.
#
# Rationale: A producer-inverted axis is measured correctly — it is the
# construct (import concentration) that is inapplicable. Downweighting
# a correctly-measured axis in the composite because of the country's
# economic structure would introduce systematic bias.
STRUCTURAL_FLAGS: frozenset[str] = frozenset({
    "PRODUCER_INVERSION",
})


# ---------------------------------------------------------------------------
# Comparability tier thresholds — deterministic, no manual overrides
# ---------------------------------------------------------------------------
# These thresholds partition the total_severity space into 4 tiers.
# They are calibrated against the severity weights above:
#
#   TIER_1 (< 0.5):  At most one minor issue (HS6 granularity + temporal)
#                     or one moderate issue (single channel).
#
#   TIER_2 (< 1.5):  Multiple moderate issues or one severe issue.
#                     Scores are usable with explicit caveats.
#
#   TIER_3 (< 3.0):  Major structural compromise. Multiple severe issues
#                     or pervasive degradation. Weakly comparable at best.
#
#   TIER_4 (≥ 3.0):  Sanctions-level distortion or compound severe issues.
#                     NOT comparable to any clean country.

TIER_THRESHOLDS: list[tuple[float, str]] = [
    (0.5, "TIER_1"),
    (1.5, "TIER_2"),
    (3.0, "TIER_3"),
    # Everything ≥ 3.0 → TIER_4
]

# Cross-country comparability — DUAL-CONDITION guard.
# Pair is non-comparable if EITHER condition triggers:
#   1. Absolute difference > DIFF_THRESHOLD
#   2. Severity ratio > RATIO_THRESHOLD (max/min)
# Dual-condition catches cases that a single test misses:
#   - Diff-only: misses 0.1 vs 0.5 (ratio = 5.0, diff only 0.4)
#   - Ratio-only: misses 2.0 vs 3.6 (ratio = 1.8, diff = 1.6)
CROSS_COUNTRY_SEVERITY_THRESHOLD: float = 1.5  # backward-compat alias (diff)
CROSS_COUNTRY_DIFF_THRESHOLD: float = 1.5
CROSS_COUNTRY_RATIO_THRESHOLD: float = 3.0
CROSS_COUNTRY_RATIO_EPSILON: float = 0.05  # avoid division by near-zero

# Degradation-aware aggregation — EXPONENTIAL penalty.
# axis_quality_weight = max(exp(-alpha * severity), MIN_WEIGHT)
#
# Why exponential instead of linear:
#   Linear: w = max(1.0 - severity * 0.5, 0.1)
#     → severity=0.6 gives w=0.7 (too generous for moderate degradation)
#     → severity=1.0 gives w=0.5 (acceptable but plateaus quickly)
#
#   Exponential: w = max(exp(-1.2 * severity), 0.1)
#     → severity=0.0 gives w=1.0 (clean)
#     → severity=0.4 gives w≈0.62 (single channel loss — meaningful penalty)
#     → severity=0.7 gives w≈0.43 (producer inversion — significant)
#     → severity=1.0 gives w≈0.30 (sanctions — heavy but not suppressed)
#     → severity=1.5 gives w≈0.17 (compound severe — barely contributing)
#     → severity>1.9 gives w=0.10 (floor — never fully suppressed)
#
# alpha=1.2 calibrated against the severity weight scale:
#   - Moderate issues (0.3-0.5) get ~50-70% weight → meaningful penalty
#   - Severe issues (0.7-1.0) get ~30-43% weight → heavy penalty
#   - Compound severe (>1.5) hit the floor → near-suppression
AGGREGATION_ALPHA: float = 1.2
AGGREGATION_MIN_WEIGHT: float = 0.1

# Legacy alias — kept for import compatibility in tests
AGGREGATION_PENALTY_RATE: float = 0.5


# ---------------------------------------------------------------------------
# Per-axis severity computation
# ---------------------------------------------------------------------------

def compute_axis_severity(data_quality_flags: list[str]) -> float:
    """Compute degradation severity for a single axis.

    Uses DEPENDENCY-AWARE resolution:
      1. Map each flag to its severity weight key.
      2. For flags belonging to a DEGRADATION_GROUP, take MAX within group.
      3. For ungrouped flags, add independently.
      4. Sum MAX-per-group + ungrouped = total severity.

    This prevents double-counting of flags that represent the same
    underlying degradation mechanism (e.g., CPIS_NON_PARTICIPANT +
    SINGLE_CHANNEL_A both represent channel loss → only the worse counts).

    INVALID axes return 0.0 (they are excluded from composites entirely).

    Args:
        data_quality_flags: Flags from AxisResult.to_dict()["data_quality_flags"].

    Returns:
        Severity score (non-negative float).
    """
    if "INVALID_AXIS" in data_quality_flags:
        return 0.0

    # Collect per-group max weights and ungrouped weights
    group_max: dict[str, float] = {}
    ungrouped_total = 0.0

    for flag in data_quality_flags:
        key = _FLAG_TO_SEVERITY_KEY.get(flag)
        if key is None or key not in SEVERITY_WEIGHTS:
            continue
        weight = SEVERITY_WEIGHTS[key]
        group = _SEVERITY_KEY_TO_GROUP.get(key)
        if group is not None:
            group_max[group] = max(group_max.get(group, 0.0), weight)
        else:
            ungrouped_total += weight

    severity = sum(group_max.values()) + ungrouped_total
    return round(severity, ROUND_PRECISION)


def compute_axis_data_severity(data_quality_flags: list[str]) -> float:
    """Compute DATA RELIABILITY severity only, excluding structural flags.

    This is identical to compute_axis_severity() but excludes flags in
    STRUCTURAL_FLAGS (e.g., PRODUCER_INVERSION). The result is used
    exclusively for the quality weight function ω(·) in the
    degradation-adjusted composite.

    Structural flags affect comparability assessment (via total severity)
    but NOT aggregation weights.

    Args:
        data_quality_flags: Flags from AxisResult.to_dict()["data_quality_flags"].

    Returns:
        Data reliability severity (non-negative float).
    """
    if "INVALID_AXIS" in data_quality_flags:
        return 0.0

    group_max: dict[str, float] = {}
    ungrouped_total = 0.0

    for flag in data_quality_flags:
        key = _FLAG_TO_SEVERITY_KEY.get(flag)
        if key is None or key not in SEVERITY_WEIGHTS:
            continue
        # Skip structural flags — they don't affect data reliability
        if key in STRUCTURAL_FLAGS:
            continue
        weight = SEVERITY_WEIGHTS[key]
        group = _SEVERITY_KEY_TO_GROUP.get(key)
        if group is not None:
            group_max[group] = max(group_max.get(group, 0.0), weight)
        else:
            ungrouped_total += weight

    severity = sum(group_max.values()) + ungrouped_total
    return round(severity, ROUND_PRECISION)


def compute_axis_severity_breakdown(
    data_quality_flags: list[str],
) -> dict[str, float]:
    """Compute severity with per-flag breakdown and group resolution.

    Returns dict mapping each contributing flag to its weight,
    plus a "total" key with the group-aware aggregate, and a
    "group_resolution" key showing per-group max selection.

    Flags that are shadowed by a higher-weight flag in the same group
    still appear in the breakdown with their individual weight, but
    the total reflects only the group max.
    """
    if "INVALID_AXIS" in data_quality_flags:
        return {"total": 0.0}

    breakdown: dict[str, float] = {}
    group_max: dict[str, float] = {}
    group_winner: dict[str, str] = {}
    ungrouped_total = 0.0

    for flag in data_quality_flags:
        key = _FLAG_TO_SEVERITY_KEY.get(flag)
        if key is None or key not in SEVERITY_WEIGHTS:
            continue
        w = SEVERITY_WEIGHTS[key]
        breakdown[flag] = w

        group = _SEVERITY_KEY_TO_GROUP.get(key)
        if group is not None:
            if w > group_max.get(group, 0.0):
                group_max[group] = w
                group_winner[group] = flag
        else:
            ungrouped_total += w

    total = sum(group_max.values()) + ungrouped_total
    breakdown["total"] = round(total, ROUND_PRECISION)

    # Include group resolution for transparency
    if group_max:
        breakdown["group_resolution"] = {  # type: ignore[assignment]
            g: {"max_weight": mw, "representative_flag": group_winner[g]}
            for g, mw in group_max.items()
        }

    return breakdown


# ---------------------------------------------------------------------------
# Per-country severity computation
# ---------------------------------------------------------------------------

def compute_country_severity(
    axis_severities: list[tuple[int, str, float]],
) -> dict[str, Any]:
    """Compute country-level severity profile from per-axis severities.

    Args:
        axis_severities: List of (axis_id, axis_slug, severity) tuples
                         for all INCLUDED (non-INVALID) axes.

    Returns:
        Dict with:
            total_severity: float — sum of all axis severities
            mean_severity: float — mean across included axes
            max_axis_severity: float — highest single-axis severity
            worst_axis: str — slug of the worst axis
            severity_profile: dict — per-axis breakdown
            n_clean_axes: int — axes with severity == 0.0
            n_degraded_axes: int — axes with severity > 0.0
    """
    if not axis_severities:
        return {
            "total_severity": 0.0,
            "mean_severity": 0.0,
            "max_axis_severity": 0.0,
            "worst_axis": None,
            "severity_profile": {},
            "n_clean_axes": 0,
            "n_degraded_axes": 0,
        }

    total = sum(s for _, _, s in axis_severities)
    mean = total / len(axis_severities)
    max_sev = max(s for _, _, s in axis_severities)
    worst_idx = max(range(len(axis_severities)), key=lambda i: axis_severities[i][2])
    worst_slug = axis_severities[worst_idx][1]

    profile = {}
    n_clean = 0
    n_degraded = 0
    for axis_id, slug, sev in axis_severities:
        profile[slug] = round(sev, ROUND_PRECISION)
        if sev == 0.0:
            n_clean += 1
        else:
            n_degraded += 1

    return {
        "total_severity": round(total, ROUND_PRECISION),
        "mean_severity": round(mean, ROUND_PRECISION),
        "max_axis_severity": round(max_sev, ROUND_PRECISION),
        "worst_axis": worst_slug,
        "severity_profile": profile,
        "n_clean_axes": n_clean,
        "n_degraded_axes": n_degraded,
    }


# ---------------------------------------------------------------------------
# Comparability tier assignment
# ---------------------------------------------------------------------------

def assign_comparability_tier(total_severity: float) -> str:
    """Assign strict comparability tier based on total severity.

    Deterministic. No manual overrides. No exceptions.

    Tiers:
        TIER_1 — Fully comparable (total_severity < 0.5)
        TIER_2 — Comparable with caveats (0.5 ≤ total_severity < 1.5)
        TIER_3 — Weakly comparable (1.5 ≤ total_severity < 3.0)
        TIER_4 — Not comparable (total_severity ≥ 3.0)
    """
    for threshold, tier in TIER_THRESHOLDS:
        if total_severity < threshold:
            return tier
    return "TIER_4"


# ---------------------------------------------------------------------------
# Cross-country comparability enforcement
# ---------------------------------------------------------------------------

def check_cross_country_comparability(
    country_severities: dict[str, float],
) -> list[dict[str, Any]]:
    """Check all country pairs for comparability violations.

    Uses DUAL-CONDITION guard — pair is non-comparable if EITHER:
      1. abs(severity_A - severity_B) > DIFF_THRESHOLD, OR
      2. max(sA, sB) / (min(sA, sB) + epsilon) > RATIO_THRESHOLD

    The ratio condition catches cases where both severities are low
    but one is dramatically worse than the other relative to scale
    (e.g., 0.0 vs 0.4 — diff only 0.4, but ratio is ~8.0).

    The diff condition catches cases where both are high but differ
    substantially (e.g., 2.0 vs 3.6 — ratio ~1.8, diff = 1.6).

    Returns a list of pairwise non-comparability warnings.
    Each entry contains: country_a, country_b, severity_a, severity_b,
    severity_differential, severity_ratio, trigger, warning_code.

    This check is AUTOMATIC and CANNOT be bypassed.
    """
    violations: list[dict[str, Any]] = []
    countries = sorted(country_severities.keys())

    for i, ca in enumerate(countries):
        for cb in countries[i + 1:]:
            sa = country_severities[ca]
            sb = country_severities[cb]
            diff = abs(sa - sb)
            hi = max(sa, sb)
            lo = min(sa, sb)
            ratio = hi / (lo + CROSS_COUNTRY_RATIO_EPSILON)

            triggers: list[str] = []
            if diff > CROSS_COUNTRY_DIFF_THRESHOLD:
                triggers.append("DIFF")
            if ratio > CROSS_COUNTRY_RATIO_THRESHOLD:
                triggers.append("RATIO")

            if triggers:
                violations.append({
                    "country_a": ca,
                    "country_b": cb,
                    "severity_a": round(sa, ROUND_PRECISION),
                    "severity_b": round(sb, ROUND_PRECISION),
                    "severity_differential": round(diff, ROUND_PRECISION),
                    "severity_ratio": round(ratio, ROUND_PRECISION),
                    "trigger": "+".join(triggers),
                    "warning_code": "W-CROSS-COUNTRY-NONCOMPARABLE",
                })

    return violations


# ---------------------------------------------------------------------------
# Degradation-aware aggregation
# ---------------------------------------------------------------------------

def compute_adjusted_composite(
    axis_scores: list[tuple[float, float]],
) -> float | None:
    """Compute degradation-adjusted composite score.

    Each axis contributes proportionally to its data quality.
    Clean axes (severity=0) contribute at full weight (1.0).
    Degraded axes contribute at EXPONENTIALLY reduced weight:
        quality_weight = max(exp(-alpha * severity), MIN_WEIGHT)

    This is superior to linear penalty because:
    - Clean axes: w = 1.0 (identical to linear)
    - Moderate: steeper penalty than linear at mid-range severity
    - Severe: approaches MIN_WEIGHT asymptotically instead of hitting
      a cliff edge (linear reaches 0.1 abruptly at severity=1.8)

    Formula:
        composite_adjusted = Σ(score_i * w_i) / Σ(w_i)

    where w_i = max(exp(-alpha * severity_i), MIN_WEIGHT)

    Args:
        axis_scores: List of (score, severity) tuples for included axes.

    Returns:
        Adjusted composite score, rounded to ROUND_PRECISION.
        None if no axes provided.
    """
    if not axis_scores:
        return None

    weighted_sum = 0.0
    weight_sum = 0.0

    for score, severity in axis_scores:
        quality_weight = max(
            math.exp(-AGGREGATION_ALPHA * severity),
            AGGREGATION_MIN_WEIGHT,
        )
        weighted_sum += score * quality_weight
        weight_sum += quality_weight

    if weight_sum == 0.0:
        return None

    return round(weighted_sum / weight_sum, ROUND_PRECISION)


# ---------------------------------------------------------------------------
# Stability analysis (leave-one-out)
# ---------------------------------------------------------------------------

def compute_stability_analysis(
    included_axes: list[tuple[int, str, float]],
) -> dict[str, Any]:
    """Leave-one-out stability analysis for a country's composite.

    For each included axis, removes it and recomputes the composite
    from the remaining axes. This quantifies:
    - How sensitive the composite is to any single axis
    - Which axis has the most influence
    - Overall stability of the composite

    Args:
        included_axes: List of (axis_id, slug, score) for all included axes.

    Returns:
        Dict with:
            baseline_composite: float — original composite (mean of all)
            leave_one_out: dict — axis_slug → composite without that axis
            axis_impacts: dict — axis_slug → signed impact (removal - baseline)
            stability_score: float — 1.0 - (max absolute impact / baseline),
                             clamped to [0.0, 1.0]. Higher = more stable.
            max_axis_impact: float — largest absolute change from removing one axis
            most_influential_axis: str — slug of the axis whose removal changes composite most
    """
    if len(included_axes) < 2:
        baseline = included_axes[0][2] if included_axes else 0.0
        slug = included_axes[0][1] if included_axes else None
        return {
            "baseline_composite": round(baseline, ROUND_PRECISION),
            "leave_one_out": {},
            "axis_impacts": {},
            "stability_score": 0.0,
            "max_axis_impact": 0.0,
            "most_influential_axis": slug,
        }

    total = sum(s for _, _, s in included_axes)
    n = len(included_axes)
    baseline = total / n

    leave_one_out: dict[str, float] = {}
    axis_impacts: dict[str, float] = {}

    for axis_id, slug, score in included_axes:
        remaining_total = total - score
        remaining_n = n - 1
        if remaining_n == 0:
            loo_composite = 0.0
        else:
            loo_composite = remaining_total / remaining_n
        loo_composite = round(loo_composite, ROUND_PRECISION)
        leave_one_out[slug] = loo_composite

        impact = loo_composite - round(baseline, ROUND_PRECISION)
        axis_impacts[slug] = round(impact, ROUND_PRECISION)

    max_abs_impact = max(abs(v) for v in axis_impacts.values())
    most_influential = max(axis_impacts.keys(), key=lambda k: abs(axis_impacts[k]))

    # Stability score: higher = more stable (less sensitive to any single axis)
    if baseline > 0.0:
        stability = 1.0 - (max_abs_impact / abs(round(baseline, ROUND_PRECISION)))
        stability = max(0.0, min(1.0, stability))
    else:
        stability = 1.0 if max_abs_impact == 0.0 else 0.0

    return {
        "baseline_composite": round(baseline, ROUND_PRECISION),
        "leave_one_out": leave_one_out,
        "axis_impacts": axis_impacts,
        "stability_score": round(stability, ROUND_PRECISION),
        "max_axis_impact": round(max_abs_impact, ROUND_PRECISION),
        "most_influential_axis": most_influential,
    }


# ---------------------------------------------------------------------------
# Interpretation engine
# ---------------------------------------------------------------------------

def build_interpretation(
    total_severity: float,
    comparability_tier: str,
    n_degraded_axes: int,
    n_included_axes: int,
    confidence: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Build mandatory interpretation flags and summary text.

    This function MUST be called for every composite output.
    If severity is high or tier ≥ TIER_3, the summary MUST include
    explicit warning language. This is not optional.

    Returns:
        Dict with:
            interpretation_flags: list[str] — machine-readable flags
            interpretation_summary: str — human-readable summary
    """
    flags: list[str] = []
    parts: list[str] = []

    # --- Severity-based flags ---
    if total_severity == 0.0:
        flags.append("CLEAN")
        parts.append("All included axes are clean with no structural degradation.")
    elif total_severity < 0.5:
        flags.append("MINOR_DEGRADATION")
        parts.append(
            f"Minor data quality issues detected (total severity: "
            f"{total_severity:.2f}). Scores are reliable for most purposes."
        )
    elif total_severity < 1.5:
        flags.append("MODERATE_DEGRADATION")
        parts.append(
            f"Moderate data quality degradation (total severity: "
            f"{total_severity:.2f}). Scores should be interpreted "
            f"with awareness of structural limitations."
        )
    elif total_severity < 3.0:
        flags.append("SEVERE_DEGRADATION")
        parts.append(
            f"WARNING: Severe data quality degradation (total severity: "
            f"{total_severity:.2f}). Scores reflect significant structural "
            f"compromise. Direct comparison with clean countries is NOT valid."
        )
    else:
        flags.append("CRITICAL_DEGRADATION")
        parts.append(
            f"CRITICAL WARNING: Extreme data quality degradation "
            f"(total severity: {total_severity:.2f}). Scores are NOT "
            f"comparable to any other country. Use only for isolated, "
            f"within-country temporal analysis."
        )

    # --- Tier-based flags ---
    if comparability_tier in ("TIER_3", "TIER_4"):
        flags.append("COMPARABILITY_WARNING")
        tier_label = (
            "weakly comparable" if comparability_tier == "TIER_3"
            else "not comparable"
        )
        parts.append(
            f"Comparability tier: {comparability_tier} ({tier_label}). "
            f"Cross-country ranking including this country is methodologically unsound."
        )

    # --- Axis coverage ---
    if n_included_axes < 6:
        flags.append("INCOMPLETE_COVERAGE")
        n_excluded = 6 - n_included_axes
        parts.append(
            f"{n_excluded} axis(es) excluded from composite. "
            f"Score is based on {n_included_axes}/6 axes."
        )

    # --- Confidence warning ---
    if confidence == "LOW_CONFIDENCE":
        flags.append("LOW_CONFIDENCE_WARNING")
        parts.append(
            "Confidence level is LOW_CONFIDENCE. Result has limited "
            "reliability for policy or publication use."
        )

    # --- Specific warning flags ---
    if any("W-SANCTIONS-DISTORTION" in w for w in warnings):
        flags.append("SANCTIONS_AFFECTED")
        parts.append(
            "Active sanctions regime distorts bilateral data. "
            "Score reflects crisis-era patterns, not steady-state structure."
        )

    if any("W-PRODUCER-INVERSION" in w for w in warnings):
        flags.append("PRODUCER_COUNTRY")
        parts.append(
            "Country is a major exporter on one or more axes. "
            "Low import concentration may not reflect strategic vulnerability."
        )

    interpretation_summary = " ".join(parts)

    return {
        "interpretation_flags": flags,
        "interpretation_summary": interpretation_summary,
    }


# ---------------------------------------------------------------------------
# Structural class system — IMPORTER / BALANCED / PRODUCER
# ---------------------------------------------------------------------------
# The ISI construct measures import concentration. But a country that is
# a major EXPORTER on multiple axes has fundamentally different structural
# position than a pure importer. Comparing their ISI scores as if they
# measure the same thing is methodologically unsound.
#
# Classification:
#   PRODUCER  — producer-inverted on ≥2 included axes (or ≥50% if <4 axes)
#   BALANCED  — producer-inverted on exactly 1 included axis
#   IMPORTER  — producer-inverted on 0 included axes
#
# Cross-class warnings:
#   Comparing a PRODUCER to an IMPORTER triggers
#   W-STRUCTURAL-CLASS-NONCOMPARABLE even if their severity scores
#   are similar, because the measured construct means different things.

STRUCTURAL_CLASSES = ("IMPORTER", "BALANCED", "PRODUCER")


def classify_structural_class(
    country: str,
    axis_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify a country's structural position.

    Args:
        country: ISO-2 country code.
        axis_results: List of axis to_dict() outputs (included only).

    Returns:
        Dict with:
            structural_class: str — IMPORTER / BALANCED / PRODUCER
            n_producer_inverted: int — count of producer-inverted axes
            producer_inverted_axes: list[str] — slugs of inverted axes
    """
    from backend.scope import PRODUCER_INVERSION_FLAGS

    n_inverted = 0
    inverted_slugs: list[str] = []

    for ad in axis_results:
        if ad.get("validity") == "INVALID":
            continue
        axis_id = ad["axis_id"]
        # Check if this country is a known producer on this axis
        producers = PRODUCER_INVERSION_FLAGS.get(axis_id, frozenset())
        if country in producers:
            n_inverted += 1
            inverted_slugs.append(ad["axis_slug"])

    n_included = sum(1 for ad in axis_results if ad.get("validity") != "INVALID")

    if n_included > 0 and n_inverted >= 2:
        structural_class = "PRODUCER"
    elif n_inverted == 1:
        structural_class = "BALANCED"
    else:
        structural_class = "IMPORTER"

    return {
        "structural_class": structural_class,
        "n_producer_inverted": n_inverted,
        "producer_inverted_axes": inverted_slugs,
    }


def check_structural_class_comparability(
    country_classes: dict[str, str],
) -> list[dict[str, Any]]:
    """Check all country pairs for structural class non-comparability.

    PRODUCER vs IMPORTER pairs are flagged with
    W-STRUCTURAL-CLASS-NONCOMPARABLE.

    BALANCED pairs or same-class pairs are NOT flagged.

    Args:
        country_classes: Dict of country → structural_class.

    Returns:
        List of pairwise structural non-comparability warnings.
    """
    violations: list[dict[str, Any]] = []
    countries = sorted(country_classes.keys())

    for i, ca in enumerate(countries):
        for cb in countries[i + 1:]:
            class_a = country_classes[ca]
            class_b = country_classes[cb]
            # Only flag PRODUCER vs IMPORTER (not BALANCED pairs)
            pair = frozenset({class_a, class_b})
            if pair == frozenset({"PRODUCER", "IMPORTER"}):
                violations.append({
                    "country_a": ca,
                    "country_b": cb,
                    "class_a": class_a,
                    "class_b": class_b,
                    "warning_code": "W-STRUCTURAL-CLASS-NONCOMPARABLE",
                })

    return violations
