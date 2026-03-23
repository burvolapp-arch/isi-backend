"""
backend.governance — Country-level and axis-level governance model for ISI.

This is the INSTITUTIONALIZATION LAYER. It exists because:
    - technically computable ≠ defensibly comparable
    - a score ≠ a valid result
    - software correctness ≠ methodological validity

This module defines and enforces:
    1. Country governance tiers (FULLY_COMPARABLE → NON_COMPARABLE)
    2. Axis confidence levels (per-axis reliability assessment)
    3. Comparability gating (consequences, not just labels)
    4. Producer-inversion governance
    5. Logistics structural limitation propagation
    6. Composite eligibility rules
    7. Output truthfulness contract enforcement

NO score modification happens here. This module governs
INTERPRETATION, COMPARABILITY, RANKING ELIGIBILITY, and EXPORT
PERMISSION — not the underlying values.

Calibration status (see backend/calibration.py for full registry):
    - Axis confidence baselines: SEMI_EMPIRICAL (data-informed, judgmental magnitude)
    - Confidence penalties: mostly HEURISTIC (expert judgment)
    - Confidence level thresholds: HEURISTIC (not calibrated to external quality measures)
    - Governance tier rules: HEURISTIC ordering (face-valid, not empirically validated)
    - Composite eligibility thresholds: STRUCTURAL_NORMATIVE (design choices)
    - Producer inversion registry: SEMI_EMPIRICAL (based on trade position data)

Design contract:
    - assess_country_governance() is the SINGLE entry point for
      country-level governance classification.
    - assess_axis_confidence() is the SINGLE entry point for
      axis-level confidence assessment.
    - enforce_truthfulness_contract() gates all exports.
    - All classifications are deterministic and auditable.
    - No manual overrides. No exceptions. No soft opinions.
"""

from __future__ import annotations

from typing import Any

from backend.constants import ROUND_PRECISION


# ---------------------------------------------------------------------------
# Country Governance Tiers
# ---------------------------------------------------------------------------
# These replace soft comparability labels with HARD governance
# classifications that drive actual system behavior.
#
# FULLY_COMPARABLE:
#   All 6 axes present, confidence ≥ 0.6, no structural inversions
#   on ≥2 axes, logistics present with at least proxy coverage.
#   Ranking-eligible. Cross-country comparison permitted.
#
# PARTIALLY_COMPARABLE:
#   5+ axes, some confidence reduction, at most 1 structural inversion,
#   or logistics absent/proxy only. Ranking-eligible WITHIN PARTITION.
#   Cross-country comparison requires explicit caveat.
#
# LOW_CONFIDENCE:
#   4+ axes but significant structural issues: ≥2 inversions,
#   logistics absent, multiple low-confidence axes. Composite
#   computed but ranking-ineligible. Published only with mandatory
#   governance annotations.
#
# NON_COMPARABLE:
#   < 4 axes, or sanctions-distorted, or fundamental structural
#   mismatch. Composite suppressed. Ranking excluded.
#   Export requires explicit "non_comparable" framing.

GOVERNANCE_TIERS = (
    "FULLY_COMPARABLE",
    "PARTIALLY_COMPARABLE",
    "LOW_CONFIDENCE",
    "NON_COMPARABLE",
)

# ---------------------------------------------------------------------------
# Axis Confidence Levels
# ---------------------------------------------------------------------------
# Per-axis confidence is NOT the same as data_quality_flags.
# Data quality flags describe WHAT went wrong.
# Confidence levels describe HOW MUCH the result can be trusted.
#
# HIGH:     Source has full scope, dual-channel, no proxy, no gap.
# MODERATE: Minor limitations (HS6 granularity, partial year).
# LOW:      Major limitations (single channel, CPIS absent, proxy data).
# MINIMAL:  Structural unsuitability (producer inversion, zero suppliers).

CONFIDENCE_LEVELS = ("HIGH", "MODERATE", "LOW", "MINIMAL")

# Confidence baseline per axis (from AXIS_REGISTRY, codified here for governance)
# Calibration class: SEMI_EMPIRICAL — informed by source coverage data,
# but magnitudes are judgmental. See backend/calibration.py for full evidence basis.
AXIS_CONFIDENCE_BASELINES: dict[int, float] = {
    1: 0.75,  # Financial: BIS+CPIS dual-channel, ~30 reporting countries
    2: 0.80,  # Energy: Comtrade, good coverage
    3: 0.80,  # Technology: Comtrade, good coverage (HS6 risk)
    4: 0.55,  # Defense: SIPRI TIV, lumpy, major weapons only
    5: 0.75,  # Critical inputs: Comtrade, good coverage
    6: 0.60,  # Logistics: mixed sources, partial coverage
}

# Confidence penalties — each flag reduces confidence by this amount
# Calibration class: mostly HEURISTIC. See backend/calibration.py for
# per-penalty evidence basis and falsifiability criteria.
CONFIDENCE_PENALTIES: dict[str, float] = {
    "SINGLE_CHANNEL_A": 0.20,
    "SINGLE_CHANNEL_B": 0.20,
    "CPIS_NON_PARTICIPANT": 0.25,
    "REDUCED_PRODUCT_GRANULARITY": 0.10,
    "TEMPORAL_MISMATCH": 0.15,
    "PRODUCER_INVERSION": 0.30,
    "SANCTIONS_DISTORTION": 0.50,
    "ZERO_BILATERAL_SUPPLIERS": 0.25,
    "INVALID_AXIS": 1.00,  # Axis absent → confidence = 0
}

# Confidence level thresholds (confidence_score → level)
# Calibration class: HEURISTIC — not calibrated against external
# reliability measures. See backend/calibration.py for falsifiability.
CONFIDENCE_THRESHOLDS: list[tuple[float, str]] = [
    (0.65, "HIGH"),
    (0.45, "MODERATE"),
    (0.25, "LOW"),
    # Everything < 0.25 → MINIMAL
]


# ---------------------------------------------------------------------------
# Producer-Inversion Registry
# ---------------------------------------------------------------------------
# Countries with structurally inverted ISI interpretation on specific axes.
# Import concentration for a major exporter does NOT measure
# strategic vulnerability — it measures the ABSENCE of import dependency,
# which is a fundamentally different construct.

PRODUCER_INVERSION_REGISTRY: dict[str, dict[str, Any]] = {
    # ── Major energy exporters ──
    "US": {
        "inverted_axes": [2, 4, 5],
        "rationale": "Major exporter in energy (shale), defense (arms), critical inputs (rare earths limited, but net exporter in many minerals)",
        "structural_class": "PRODUCER",
    },
    "NO": {
        "inverted_axes": [2],
        "rationale": "Major petroleum/gas exporter; energy import concentration structurally misleading",
        "structural_class": "BALANCED",
    },
    "AU": {
        "inverted_axes": [2, 5],
        "rationale": "Major exporter of coal, LNG, iron ore, lithium, rare earths",
        "structural_class": "PRODUCER",
    },
    # ── Major defense exporters ──
    "FR": {
        "inverted_axes": [4],
        "rationale": "Top-5 global arms exporter; defense import concentration reflects procurement choice, not dependency",
        "structural_class": "BALANCED",
    },
    "DE": {
        "inverted_axes": [4],
        "rationale": "Top-5 global arms exporter",
        "structural_class": "BALANCED",
    },
    # ── Major critical inputs exporters ──
    "CN": {
        "inverted_axes": [4, 5],
        "rationale": "Dominant exporter of rare earths, processed critical minerals; major defense exporter; CPIS non-participant",
        "structural_class": "PRODUCER",
    },
    # ── Saudi Arabia (non-EU but structurally important reference) ──
    "SA": {
        "inverted_axes": [2],
        "rationale": "Largest petroleum exporter globally; energy import concentration is meaningless",
        "structural_class": "PRODUCER",
    },
    # ── Russia (sanctions + producer) ──
    "RU": {
        "inverted_axes": [2, 4, 5],
        "rationale": "Major energy/defense/minerals exporter AND sanctions-distorted",
        "structural_class": "PRODUCER",
    },
}


# ---------------------------------------------------------------------------
# Logistics Gap Impact
# ---------------------------------------------------------------------------
# Axis 6 is the structural weak point globally. Missing or proxy
# logistics MUST downgrade comparability — you cannot claim two countries
# are equivalently measured when one has logistics data and the other doesn't.

LOGISTICS_AXIS_ID: int = 6

# If logistics is absent, country cannot be FULLY_COMPARABLE
LOGISTICS_ABSENT_MAX_TIER = "PARTIALLY_COMPARABLE"

# If logistics is proxy-only, confidence capped
LOGISTICS_PROXY_CONFIDENCE_CAP: float = 0.40


# ---------------------------------------------------------------------------
# Composite Eligibility Rules
# ---------------------------------------------------------------------------
# A composite score exists ≠ a composite score is defensible.

# Minimum axes for composite computation (existing rule, kept)
MIN_AXES_FOR_COMPOSITE: int = 4

# Minimum axes for ranking eligibility (stricter)
MIN_AXES_FOR_RANKING: int = 5

# Minimum mean axis confidence for ranking eligibility
MIN_MEAN_CONFIDENCE_FOR_RANKING: float = 0.45

# Maximum number of LOW/MINIMAL confidence axes before composite
# is downgraded to "computed but not defensible"
MAX_LOW_CONFIDENCE_AXES_FOR_RANKING: int = 2

# Producer-inverted axes count threshold for NON_COMPARABLE
MAX_INVERTED_AXES_FOR_COMPARABLE: int = 2


# ---------------------------------------------------------------------------
# Axis Confidence Assessment
# ---------------------------------------------------------------------------

def assess_axis_confidence(
    axis_id: int,
    data_quality_flags: list[str],
    is_proxy: bool = False,
    has_data: bool = True,
) -> dict[str, Any]:
    """Assess confidence level for a single axis result.

    This is NOT data quality (which flag-based severity handles).
    This is EPISTEMIC CONFIDENCE — how much can this axis result
    be trusted for comparative and interpretive purposes.

    Args:
        axis_id: Axis identifier (1-6).
        data_quality_flags: Flags from AxisResult.to_dict().
        is_proxy: Whether this axis uses proxy data.
        has_data: Whether the axis has any data at all.

    Returns:
        Dict with:
            axis_id: int
            confidence_score: float [0.0, 1.0]
            confidence_level: str (HIGH/MODERATE/LOW/MINIMAL)
            penalties_applied: list of {flag, penalty}
            baseline: float
            is_proxy: bool
            interpretation_constraints: list[str]
    """
    if not has_data:
        return {
            "axis_id": axis_id,
            "confidence_score": 0.0,
            "confidence_level": "MINIMAL",
            "penalties_applied": [{"flag": "NO_DATA", "penalty": 1.0}],
            "baseline": AXIS_CONFIDENCE_BASELINES.get(axis_id, 0.5),
            "is_proxy": is_proxy,
            "interpretation_constraints": [
                "Axis has no data — excluded from all comparative analysis"
            ],
        }

    baseline = AXIS_CONFIDENCE_BASELINES.get(axis_id, 0.5)
    score = baseline
    penalties: list[dict[str, Any]] = []
    constraints: list[str] = []

    for flag in data_quality_flags:
        penalty = CONFIDENCE_PENALTIES.get(flag, 0.0)
        if penalty > 0:
            penalties.append({"flag": flag, "penalty": penalty})
            score -= penalty

    # Proxy data cap
    if is_proxy:
        if score > LOGISTICS_PROXY_CONFIDENCE_CAP:
            old = score
            score = LOGISTICS_PROXY_CONFIDENCE_CAP
            penalties.append({
                "flag": "PROXY_DATA",
                "penalty": round(old - score, ROUND_PRECISION),
            })
        constraints.append(
            "Uses proxy data — not directly comparable to axes with primary data"
        )

    # Logistics-specific interpretation constraint
    if axis_id == LOGISTICS_AXIS_ID:
        constraints.append(
            "Logistics axis has structurally lower coverage than trade-based axes. "
            "Maritime data is most complete; rail and air cargo are partial."
        )

    # Producer inversion constraint
    if "PRODUCER_INVERSION" in data_quality_flags:
        constraints.append(
            "Country is a major exporter on this axis. Import concentration "
            "does NOT measure strategic vulnerability — it measures absence "
            "of import dependency, a fundamentally different construct."
        )

    # CPIS absence constraint
    if "CPIS_NON_PARTICIPANT" in data_quality_flags:
        constraints.append(
            "Country is not an IMF CPIS participant. Portfolio investment "
            "concentration is unavailable — financial axis measures only "
            "banking claims (BIS LBS), not full financial exposure."
        )

    # Zero bilateral suppliers
    if "ZERO_BILATERAL_SUPPLIERS" in data_quality_flags:
        constraints.append(
            "Zero bilateral suppliers recorded. Score of 0.0 means "
            "'no measured imports', not 'low concentration'. "
            "Semantically distinct from a low but positive score."
        )

    # Floor at 0.0
    score = max(0.0, score)
    score = round(score, ROUND_PRECISION)

    # Determine level
    level = "MINIMAL"
    for threshold, lev in CONFIDENCE_THRESHOLDS:
        if score >= threshold:
            level = lev
            break

    return {
        "axis_id": axis_id,
        "confidence_score": score,
        "confidence_level": level,
        "penalties_applied": penalties,
        "baseline": baseline,
        "is_proxy": is_proxy,
        "interpretation_constraints": constraints,
    }


# ---------------------------------------------------------------------------
# Country Governance Assessment
# ---------------------------------------------------------------------------

def assess_country_governance(
    country: str,
    axis_results: list[dict[str, Any]],
    severity_total: float,
    strict_comparability_tier: str,
) -> dict[str, Any]:
    """Assess country-level governance classification.

    This is the SINGLE function that determines whether a country's
    ISI output is institutionally defensible, and at what level.

    Inputs are the ALREADY-COMPUTED axis results and severity.
    This function does NOT recompute scores — it governs them.

    Args:
        country: ISO-2 code.
        axis_results: List of axis to_dict() outputs.
        severity_total: Total severity from compute_country_severity().
        strict_comparability_tier: From assign_comparability_tier().

    Returns:
        Comprehensive governance assessment dict.
    """
    # ── Step 1: Axis confidence assessment ──
    axis_confidences: list[dict[str, Any]] = []
    for ad in axis_results:
        flags = ad.get("data_quality_flags", [])
        is_proxy = ad.get("is_proxy", False)
        has_data = ad.get("validity") != "INVALID"
        ac = assess_axis_confidence(
            axis_id=ad["axis_id"],
            data_quality_flags=flags,
            is_proxy=is_proxy,
            has_data=has_data,
        )
        axis_confidences.append(ac)

    # ── Step 2: Aggregate confidence metrics ──
    included_confidences = [
        ac for ac in axis_confidences if ac["confidence_level"] != "MINIMAL"
        or ac["confidence_score"] > 0
    ]
    n_axes_with_data = sum(
        1 for ad in axis_results if ad.get("validity") != "INVALID"
    )
    confidence_scores = [ac["confidence_score"] for ac in axis_confidences]
    mean_confidence = (
        sum(confidence_scores) / len(confidence_scores)
        if confidence_scores else 0.0
    )
    n_low_minimal = sum(
        1 for ac in axis_confidences
        if ac["confidence_level"] in ("LOW", "MINIMAL")
    )
    n_high = sum(
        1 for ac in axis_confidences
        if ac["confidence_level"] == "HIGH"
    )

    # ── Step 3: Producer inversion assessment ──
    producer_info = PRODUCER_INVERSION_REGISTRY.get(country, None)
    n_inverted = 0
    inverted_axes: list[int] = []
    if producer_info:
        n_inverted = len(producer_info["inverted_axes"])
        inverted_axes = producer_info["inverted_axes"]

    # ── Step 4: Logistics assessment ──
    logistics_present = False
    logistics_proxy = False
    for ad in axis_results:
        if ad["axis_id"] == LOGISTICS_AXIS_ID:
            if ad.get("validity") != "INVALID":
                logistics_present = True
                if ad.get("is_proxy", False):
                    logistics_proxy = True
            break

    # ── Step 5: Governance tier determination ──
    governance_tier = _determine_governance_tier(
        n_axes=n_axes_with_data,
        n_inverted=n_inverted,
        n_low_minimal=n_low_minimal,
        mean_confidence=mean_confidence,
        severity_total=severity_total,
        strict_tier=strict_comparability_tier,
        logistics_present=logistics_present,
        logistics_proxy=logistics_proxy,
    )

    # ── Step 6: Ranking and comparison eligibility ──
    ranking_eligible = _is_ranking_eligible(
        governance_tier=governance_tier,
        n_axes=n_axes_with_data,
        mean_confidence=mean_confidence,
        n_low_minimal=n_low_minimal,
    )

    cross_country_comparable = _is_cross_country_comparable(
        governance_tier=governance_tier,
        n_inverted=n_inverted,
    )

    composite_defensible = _is_composite_defensible(
        governance_tier=governance_tier,
        n_axes=n_axes_with_data,
        mean_confidence=mean_confidence,
    )

    # ── Step 7: Build governance limitations ──
    limitations: list[str] = []

    # Severity-driven limitation
    if strict_comparability_tier == "TIER_4":
        limitations.append(
            f"Severity tier TIER_4 (total={severity_total:.2f}). "
            f"Structural distortions render ISI output non-comparable."
        )
    elif strict_comparability_tier == "TIER_3":
        limitations.append(
            f"Severity tier TIER_3 (total={severity_total:.2f}). "
            f"Significant data quality issues reduce confidence."
        )

    if n_inverted > 0:
        limitations.append(
            f"Producer-inverted on {n_inverted} axis(es) {inverted_axes}. "
            f"ISI import-concentration construct is structurally inapplicable "
            f"on these axes."
        )
    if not logistics_present:
        limitations.append(
            "Logistics axis (Axis 6) absent. Country cannot be compared to "
            "countries with full logistics coverage without explicit caveat."
        )
    elif logistics_proxy:
        limitations.append(
            "Logistics axis uses proxy data. Comparability with countries "
            "using primary logistics data is limited."
        )
    if n_low_minimal > MAX_LOW_CONFIDENCE_AXES_FOR_RANKING:
        limitations.append(
            f"{n_low_minimal} axes have LOW or MINIMAL confidence. "
            f"Composite is structurally fragile."
        )
    if n_axes_with_data < MIN_AXES_FOR_COMPOSITE:
        limitations.append(
            f"Only {n_axes_with_data} axes with data (minimum {MIN_AXES_FOR_COMPOSITE}). "
            f"Composite not computable."
        )

    # ── Step 8: Build mandatory interpretation text ──
    interpretation = _build_governance_interpretation(
        governance_tier=governance_tier,
        ranking_eligible=ranking_eligible,
        cross_country_comparable=cross_country_comparable,
        composite_defensible=composite_defensible,
        limitations=limitations,
        country=country,
    )

    return {
        "country": country,
        "governance_tier": governance_tier,
        "ranking_eligible": ranking_eligible,
        "cross_country_comparable": cross_country_comparable,
        "composite_defensible": composite_defensible,
        "n_axes_with_data": n_axes_with_data,
        "mean_axis_confidence": round(mean_confidence, ROUND_PRECISION),
        "n_low_confidence_axes": n_low_minimal,
        "n_high_confidence_axes": n_high,
        "n_producer_inverted_axes": n_inverted,
        "producer_inverted_axes": inverted_axes,
        "logistics_present": logistics_present,
        "logistics_proxy": logistics_proxy,
        "axis_confidences": axis_confidences,
        "structural_limitations": limitations,
        "governance_interpretation": interpretation,
        "calibration_note": (
            "This governance assessment is based on structured expert "
            "judgment. Thresholds are documented with calibration classes "
            "(EMPIRICAL/SEMI_EMPIRICAL/HEURISTIC/STRUCTURAL_NORMATIVE) "
            "in backend/calibration.py. See that module for evidence "
            "basis and falsifiability criteria for every threshold."
        ),
    }


def _determine_governance_tier(
    *,
    n_axes: int,
    n_inverted: int,
    n_low_minimal: int,
    mean_confidence: float,
    severity_total: float,
    strict_tier: str,
    logistics_present: bool,
    logistics_proxy: bool,
) -> str:
    """Deterministic governance tier assignment.

    Rules applied in order (first match wins):
    """
    # Rule 1: TIER_4 severity → always NON_COMPARABLE
    if strict_tier == "TIER_4":
        return "NON_COMPARABLE"

    # Rule 2: Fewer than 4 axes → NON_COMPARABLE
    if n_axes < MIN_AXES_FOR_COMPOSITE:
        return "NON_COMPARABLE"

    # Rule 3: ≥3 producer-inverted axes → NON_COMPARABLE
    if n_inverted >= 3:
        return "NON_COMPARABLE"

    # Rule 4: ≥2 inverted + logistics absent → LOW_CONFIDENCE
    if n_inverted >= MAX_INVERTED_AXES_FOR_COMPARABLE and not logistics_present:
        return "LOW_CONFIDENCE"

    # Rule 5: ≥2 inverted axes → LOW_CONFIDENCE minimum
    if n_inverted >= MAX_INVERTED_AXES_FOR_COMPARABLE:
        return "LOW_CONFIDENCE"

    # Rule 6: Severity ≥ 1.5 (TIER_3) → LOW_CONFIDENCE
    if strict_tier == "TIER_3":
        return "LOW_CONFIDENCE"

    # Rule 7: Mean confidence below threshold → LOW_CONFIDENCE
    if mean_confidence < MIN_MEAN_CONFIDENCE_FOR_RANKING:
        return "LOW_CONFIDENCE"

    # Rule 8: >2 low/minimal confidence axes → LOW_CONFIDENCE
    if n_low_minimal > MAX_LOW_CONFIDENCE_AXES_FOR_RANKING:
        return "LOW_CONFIDENCE"

    # Rule 9: Logistics absent → cap at PARTIALLY_COMPARABLE
    if not logistics_present:
        return "PARTIALLY_COMPARABLE"

    # Rule 10: Logistics proxy-only → cap at PARTIALLY_COMPARABLE
    if logistics_proxy:
        return "PARTIALLY_COMPARABLE"

    # Rule 11: 1 inverted axis → PARTIALLY_COMPARABLE
    if n_inverted == 1:
        return "PARTIALLY_COMPARABLE"

    # Rule 12: 5 axes (not 6) → PARTIALLY_COMPARABLE
    if n_axes < 6:
        return "PARTIALLY_COMPARABLE"

    # Rule 13: TIER_2 severity → PARTIALLY_COMPARABLE
    if strict_tier == "TIER_2":
        return "PARTIALLY_COMPARABLE"

    # Rule 14: All conditions met → FULLY_COMPARABLE
    return "FULLY_COMPARABLE"


def _is_ranking_eligible(
    *,
    governance_tier: str,
    n_axes: int,
    mean_confidence: float,
    n_low_minimal: int,
) -> bool:
    """Determine if country is eligible for cross-country ranking.

    NON_COMPARABLE and LOW_CONFIDENCE are NEVER ranking-eligible.
    PARTIALLY_COMPARABLE requires additional checks.
    """
    if governance_tier in ("NON_COMPARABLE", "LOW_CONFIDENCE"):
        return False

    if n_axes < MIN_AXES_FOR_RANKING:
        return False

    if mean_confidence < MIN_MEAN_CONFIDENCE_FOR_RANKING:
        return False

    if n_low_minimal > MAX_LOW_CONFIDENCE_AXES_FOR_RANKING:
        return False

    return True


def _is_cross_country_comparable(
    *,
    governance_tier: str,
    n_inverted: int,
) -> bool:
    """Determine if country's ISI is meaningfully comparable to other countries.

    PRODUCER countries with ≥2 inversions are structurally measuring
    a different construct than IMPORTER countries.
    """
    if governance_tier == "NON_COMPARABLE":
        return False

    if governance_tier == "LOW_CONFIDENCE":
        return False

    if n_inverted >= MAX_INVERTED_AXES_FOR_COMPARABLE:
        return False

    return True


def _is_composite_defensible(
    *,
    governance_tier: str,
    n_axes: int,
    mean_confidence: float,
) -> bool:
    """Determine if composite score is institutionally defensible.

    A composite can be COMPUTED (arithmetic) but NOT DEFENSIBLE
    (methodologically sound for publication/policy).
    """
    if governance_tier == "NON_COMPARABLE":
        return False

    if n_axes < MIN_AXES_FOR_COMPOSITE:
        return False

    if mean_confidence < 0.30:
        return False

    return True


def _build_governance_interpretation(
    *,
    governance_tier: str,
    ranking_eligible: bool,
    cross_country_comparable: bool,
    composite_defensible: bool,
    limitations: list[str],
    country: str,
) -> str:
    """Build mandatory human-readable governance interpretation.

    This text MUST accompany every exported country result.
    """
    parts: list[str] = []

    tier_descriptions = {
        "FULLY_COMPARABLE": (
            f"{country}: FULLY COMPARABLE — all structural requirements met. "
            f"ISI composite and axis scores are suitable for cross-country "
            f"comparison and ranking within the measured construct."
        ),
        "PARTIALLY_COMPARABLE": (
            f"{country}: PARTIALLY COMPARABLE — comparison is valid but requires "
            f"awareness of structural limitations. Some axes may have reduced "
            f"reliability or coverage gaps. Rank comparisons should note caveats."
        ),
        "LOW_CONFIDENCE": (
            f"{country}: LOW CONFIDENCE — ISI composite is computable but not "
            f"defensible for cross-country ranking. Significant structural "
            f"limitations affect interpretation. Use for directional insight "
            f"only, not for definitive comparative claims."
        ),
        "NON_COMPARABLE": (
            f"{country}: NON-COMPARABLE — ISI output is either not computable "
            f"or too structurally compromised for any comparative purpose. "
            f"Do NOT include in rankings, league tables, or cross-country "
            f"comparisons."
        ),
    }

    parts.append(tier_descriptions.get(governance_tier, f"{country}: UNKNOWN TIER"))

    if not ranking_eligible:
        parts.append("RANKING EXCLUDED: not eligible for ranked comparisons.")

    if not cross_country_comparable:
        parts.append(
            "CROSS-COUNTRY COMPARISON SUPPRESSED: structural class mismatch "
            "or insufficient reliability prevents meaningful comparison."
        )

    if not composite_defensible:
        parts.append(
            "COMPOSITE NOT DEFENSIBLE: score is arithmetically valid but "
            "methodologically insufficient for publication or policy use."
        )

    for lim in limitations:
        parts.append(f"LIMITATION: {lim}")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Truthfulness Contract Enforcement
# ---------------------------------------------------------------------------
# Every user-facing / export-facing result MUST satisfy this contract.
# If it does not, export is BLOCKED.

TRUTHFULNESS_REQUIRED_FIELDS: frozenset[str] = frozenset({
    "governance_tier",
    "ranking_eligible",
    "cross_country_comparable",
    "composite_defensible",
    "axis_confidences",
    "structural_limitations",
    "governance_interpretation",
    "n_producer_inverted_axes",
    "logistics_present",
    "mean_axis_confidence",
})


def enforce_truthfulness_contract(
    country_result: dict[str, Any],
) -> list[str]:
    """Verify that a country result satisfies the truthfulness contract.

    Returns list of violations (empty = contract satisfied).
    This MUST be called before any export/materialization.
    """
    violations: list[str] = []
    country = country_result.get("country", "UNKNOWN")

    # Check governance metadata presence
    governance = country_result.get("governance", {})
    if not governance:
        violations.append(
            f"{country}: missing 'governance' block — "
            f"result cannot be exported without governance metadata"
        )
        return violations  # Can't check further

    missing = TRUTHFULNESS_REQUIRED_FIELDS - set(governance.keys())
    if missing:
        violations.append(
            f"{country}: governance block missing required fields: "
            f"{sorted(missing)}"
        )

    # Check that NON_COMPARABLE countries don't have ranking
    tier = governance.get("governance_tier")
    if tier == "NON_COMPARABLE":
        if country_result.get("rank") is not None:
            violations.append(
                f"{country}: NON_COMPARABLE but rank is not NULL"
            )
        if country_result.get("composite_adjusted") is not None:
            violations.append(
                f"{country}: NON_COMPARABLE but composite_adjusted is not NULL"
            )

    # Check that LOW_CONFIDENCE countries are not ranking-eligible
    if tier == "LOW_CONFIDENCE":
        if governance.get("ranking_eligible", False):
            violations.append(
                f"{country}: LOW_CONFIDENCE but ranking_eligible is True"
            )

    # Check axis confidences are present for all axes
    axis_confs = governance.get("axis_confidences", [])
    if len(axis_confs) < 1:
        violations.append(
            f"{country}: no axis confidence assessments present"
        )

    # Check structural limitations are populated for non-FULLY_COMPARABLE
    if tier != "FULLY_COMPARABLE":
        lims = governance.get("structural_limitations", [])
        if not lims:
            violations.append(
                f"{country}: governance_tier={tier} but no "
                f"structural_limitations documented"
            )

    return violations


# ---------------------------------------------------------------------------
# Batch governance assessment
# ---------------------------------------------------------------------------

def assess_all_countries(
    country_composite_dicts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run governance assessment for all countries in a result set.

    Args:
        country_composite_dicts: Dict of country_code → composite.to_dict() output.

    Returns:
        Dict of country_code → governance assessment.
    """
    results: dict[str, dict[str, Any]] = {}

    for country, cd in country_composite_dicts.items():
        axis_dicts = cd.get("axes", [])
        severity_total = cd.get("severity_analysis", {}).get("total_severity", 0.0)
        strict_tier = cd.get("strict_comparability_tier", "TIER_4")

        gov = assess_country_governance(
            country=country,
            axis_results=axis_dicts,
            severity_total=severity_total,
            strict_comparability_tier=strict_tier,
        )
        results[country] = gov

    return results


# ---------------------------------------------------------------------------
# Export gate — the final checkpoint
# ---------------------------------------------------------------------------

def gate_export(
    country_result: dict[str, Any],
    governance: dict[str, Any],
) -> dict[str, Any]:
    """Apply governance gating to a country result before export.

    This function:
    1. Injects governance metadata into the result
    2. Suppresses ranking for ineligible countries
    3. Suppresses composite_adjusted for non-defensible cases
    4. Enforces truthfulness contract

    Returns the gated result (modified in place for efficiency).
    Raises ValueError if truthfulness contract is violated.
    """
    # Inject governance
    country_result["governance"] = governance

    tier = governance["governance_tier"]

    # Suppress ranking for ineligible countries
    if not governance["ranking_eligible"]:
        country_result["rank"] = None
        country_result["exclude_from_rankings"] = True

    # Suppress composite_adjusted for non-defensible
    if not governance["composite_defensible"]:
        country_result["composite_adjusted"] = None

    # For NON_COMPARABLE: suppress everything comparative
    if tier == "NON_COMPARABLE":
        country_result["composite_adjusted"] = None
        country_result["rank"] = None
        country_result["exclude_from_rankings"] = True
        country_result["ranking_partition"] = "NON_COMPARABLE"

    # For LOW_CONFIDENCE: mark ranking partition
    if tier == "LOW_CONFIDENCE":
        country_result["ranking_partition"] = "LIMITED"

    # Enforce truthfulness contract
    violations = enforce_truthfulness_contract(country_result)
    if violations:
        raise ValueError(
            f"Truthfulness contract violation for "
            f"{governance.get('country', 'UNKNOWN')}: "
            + "; ".join(violations)
        )

    return country_result
