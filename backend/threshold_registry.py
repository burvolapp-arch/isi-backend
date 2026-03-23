"""
backend.threshold_registry — Machine-Readable Threshold Justification Registry

LAYER 1: Every threshold in the ISI system is registered here with:
- Unique threshold_id
- Current value
- Functional role in the system
- Rationale type (EMPIRICAL / SEMI_EMPIRICAL / HEURISTIC / STRUCTURAL_NORMATIVE)
- Justification text
- Sensitivity band (range within which output is stable)
- Breakpoints (values at which qualitative output changes)
- Alternative plausible values considered
- Risk assessment if the threshold is misspecified

This module is the SINGLE registry of all thresholds. It imports values
from their authoritative source modules (governance.py, severity.py,
eligibility.py) rather than duplicating them. Every threshold can be
queried, exported to JSON, and surfaced in the API.

Design contract:
    - ONE registry, ONE schema, ONE query interface
    - NO threshold value is defined here — values are imported from source
    - Every entry answers: "Why this value? What if it's wrong?"
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# RATIONALE TYPES
# ═══════════════════════════════════════════════════════════════════════════

class RationaleType:
    """Classification of how a threshold value was determined."""
    EMPIRICAL = "EMPIRICAL"
    SEMI_EMPIRICAL = "SEMI_EMPIRICAL"
    HEURISTIC = "HEURISTIC"
    STRUCTURAL_NORMATIVE = "STRUCTURAL_NORMATIVE"


VALID_RATIONALE_TYPES = frozenset({
    RationaleType.EMPIRICAL,
    RationaleType.SEMI_EMPIRICAL,
    RationaleType.HEURISTIC,
    RationaleType.STRUCTURAL_NORMATIVE,
})


# ═══════════════════════════════════════════════════════════════════════════
# RISK LEVELS
# ═══════════════════════════════════════════════════════════════════════════

class RiskLevel:
    """Risk if a threshold is misspecified."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


VALID_RISK_LEVELS = frozenset({
    RiskLevel.LOW,
    RiskLevel.MODERATE,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
})


# ═══════════════════════════════════════════════════════════════════════════
# THRESHOLD ENTRY BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def _t(
    *,
    threshold_id: str,
    name: str,
    current_value: float | int | str,
    functional_role: str,
    rationale_type: str,
    justification: str,
    sensitivity_band: dict[str, float | int | str],
    breakpoints: list[dict[str, Any]],
    alternative_plausible_values: list[dict[str, Any]],
    risk_if_misspecified: str,
    risk_level: str,
    source_module: str,
    affects: list[str],
) -> dict[str, Any]:
    """Create a validated threshold registry entry."""
    assert rationale_type in VALID_RATIONALE_TYPES, (
        f"Invalid rationale_type '{rationale_type}' for {threshold_id}"
    )
    assert risk_level in VALID_RISK_LEVELS, (
        f"Invalid risk_level '{risk_level}' for {threshold_id}"
    )
    return {
        "threshold_id": threshold_id,
        "name": name,
        "current_value": current_value,
        "functional_role": functional_role,
        "rationale_type": rationale_type,
        "justification": justification,
        "sensitivity_band": sensitivity_band,
        "breakpoints": breakpoints,
        "alternative_plausible_values": alternative_plausible_values,
        "risk_if_misspecified": risk_if_misspecified,
        "risk_level": risk_level,
        "source_module": source_module,
        "affects": affects,
    }


# ═══════════════════════════════════════════════════════════════════════════
# THE REGISTRY
# ═══════════════════════════════════════════════════════════════════════════
# Organized by source module, then by functional category.

THRESHOLD_JUSTIFICATION_REGISTRY: list[dict[str, Any]] = [

    # ───────────────────────────────────────────────────────────────────
    # GOVERNANCE: Axis Confidence Baselines
    # ───────────────────────────────────────────────────────────────────

    _t(
        threshold_id="GOV_BASELINE_AX1",
        name="Axis 1 (Financial) Confidence Baseline",
        current_value=0.75,
        functional_role=(
            "Starting confidence score for Axis 1 before penalties. "
            "Determines the ceiling of per-axis confidence."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "BIS LBS + CPIS provide two independent bilateral channels. "
            "Dual-source design justifies above-median baseline. Set at "
            "0.75 (not 0.80) because BIS LBS is locational (not ultimate "
            "risk) and CPIS has 2-year lag for some participants."
        ),
        sensitivity_band={"low": 0.65, "high": 0.85},
        breakpoints=[
            {"value": 0.65, "effect": "3-4 EU countries drop from HIGH to MODERATE confidence on Axis 1"},
            {"value": 0.85, "effect": "Most countries reach HIGH even with minor penalties"},
        ],
        alternative_plausible_values=[
            {"value": 0.70, "rationale": "More conservative — BIS reporting gaps for non-G10"},
            {"value": 0.80, "rationale": "Matches Axis 2/3 — dual-channel justifies parity"},
        ],
        risk_if_misspecified=(
            "If too high: countries with degraded financial data appear "
            "better-covered than warranted. If too low: well-covered "
            "EU-27 members get artificially low confidence."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier", "ranking_eligibility"],
    ),

    _t(
        threshold_id="GOV_BASELINE_AX2",
        name="Axis 2 (Energy) Confidence Baseline",
        current_value=0.80,
        functional_role=(
            "Starting confidence score for Axis 2 before penalties."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "Comtrade HS27 provides comprehensive bilateral energy trade "
            "data. Coverage >95% of reporting countries. Higher baseline "
            "than Axis 1 because single-source (Comtrade) with excellent "
            "coverage is more reliable than dual-source with gaps."
        ),
        sensitivity_band={"low": 0.70, "high": 0.90},
        breakpoints=[
            {"value": 0.70, "effect": "Energy-exporter countries with PRODUCER_INVERSION penalty may drop below LOW threshold"},
        ],
        alternative_plausible_values=[
            {"value": 0.75, "rationale": "Accounts for re-export distortion in pipeline countries"},
            {"value": 0.85, "rationale": "Reflects near-universal Comtrade reporting"},
        ],
        risk_if_misspecified=(
            "If too high: producer-inverted countries stay at MODERATE "
            "when they should be LOW. If too low: well-covered importers "
            "are unfairly penalized."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier"],
    ),

    _t(
        threshold_id="GOV_BASELINE_AX3",
        name="Axis 3 (Technology) Confidence Baseline",
        current_value=0.80,
        functional_role=(
            "Starting confidence score for Axis 3 before penalties."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "Comtrade HS8541/8542 with good bilateral coverage. Same "
            "source quality as energy axis. CN8 granularity available "
            "for intra-EU trade. Re-export issue (NL, SG) is not "
            "penalized in baselines — handled via flags."
        ),
        sensitivity_band={"low": 0.70, "high": 0.90},
        breakpoints=[
            {"value": 0.70, "effect": "Countries with REDUCED_PRODUCT_GRANULARITY drop further"},
        ],
        alternative_plausible_values=[
            {"value": 0.75, "rationale": "HS6→CN8 collapse loses subcategory detail"},
            {"value": 0.85, "rationale": "Comtrade reporting is near-universal for semiconductors"},
        ],
        risk_if_misspecified=(
            "Low impact — technology axis is well-covered for most "
            "EU-27 members. Risk is primarily for non-EU reference "
            "countries where HS6 is the only classification available."
        ),
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence"],
    ),

    _t(
        threshold_id="GOV_BASELINE_AX4",
        name="Axis 4 (Defense) Confidence Baseline",
        current_value=0.55,
        functional_role=(
            "Starting confidence score for Axis 4 before penalties. "
            "Lowest baseline among trade-based axes."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "SIPRI TIV covers major conventional weapons only. TIV is "
            "not monetary value. Delivery lumpiness creates year-on-year "
            "volatility. Dual-use items excluded. The 0.55 baseline "
            "reflects that SIPRI is the best available source but has "
            "fundamental coverage limitations."
        ),
        sensitivity_band={"low": 0.45, "high": 0.65},
        breakpoints=[
            {"value": 0.45, "effect": "Axis 4 starts at LOW confidence boundary for all countries"},
            {"value": 0.65, "effect": "Defense axis approaches parity with trade-based axes — unjustified"},
        ],
        alternative_plausible_values=[
            {"value": 0.50, "rationale": "More conservative for TIV limitations"},
            {"value": 0.60, "rationale": "SIPRI is the gold standard for arms trade data"},
        ],
        risk_if_misspecified=(
            "If too high: defense axis appears more reliable than its "
            "source quality warrants (SIPRI covers <50% of actual "
            "procurement for some countries). If too low: countries "
            "with genuine defense import dependency get unfairly "
            "flagged as LOW confidence."
        ),
        risk_level=RiskLevel.HIGH,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier", "ranking_eligibility"],
    ),

    _t(
        threshold_id="GOV_BASELINE_AX5",
        name="Axis 5 (Critical Inputs) Confidence Baseline",
        current_value=0.75,
        functional_role=(
            "Starting confidence score for Axis 5 before penalties."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "Comtrade HS chapters for critical raw materials. Product "
            "codes aligned with EU CRM Act. Good bilateral coverage. "
            "Lower than Axis 2/3 because processing-stage ambiguity "
            "(ore vs refined) and stockpile effects reduce reliability."
        ),
        sensitivity_band={"low": 0.65, "high": 0.85},
        breakpoints=[
            {"value": 0.65, "effect": "Producer-inverted countries (AU, CN) drop further toward LOW"},
        ],
        alternative_plausible_values=[
            {"value": 0.70, "rationale": "Processing-stage ambiguity is significant"},
            {"value": 0.80, "rationale": "Matches energy/tech for Comtrade-based axes"},
        ],
        risk_if_misspecified=(
            "Moderate — affects producer countries more than importers. "
            "China's processing dominance may be understated regardless "
            "of baseline choice."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier"],
    ),

    _t(
        threshold_id="GOV_BASELINE_AX6",
        name="Axis 6 (Logistics) Confidence Baseline",
        current_value=0.60,
        functional_role=(
            "Starting confidence score for Axis 6 before penalties. "
            "Lowest baseline — reflects weakest data architecture."
        ),
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Mixed sources: UNCTAD maritime, trade-weighted proxies. "
            "Rail and air cargo are sparse. Bilateral logistics data "
            "is fundamentally less available than trade data. The 0.60 "
            "baseline reflects expert assessment that maritime captures "
            "~60% of relevant bilateral freight structure for coastal "
            "countries but much less for landlocked ones."
        ),
        sensitivity_band={"low": 0.50, "high": 0.70},
        breakpoints=[
            {"value": 0.50, "effect": "Logistics axis starts near LOW for all countries; proxy cap becomes less relevant"},
            {"value": 0.70, "effect": "Logistics approaches trade-axis reliability — unjustified by source quality"},
        ],
        alternative_plausible_values=[
            {"value": 0.50, "rationale": "For landlocked countries, 0.60 is generous"},
            {"value": 0.65, "rationale": "Maritime data alone justifies moderate confidence for coastal countries"},
        ],
        risk_if_misspecified=(
            "If too high: logistics axis gets disproportionate weight "
            "in composite governance. If too low: coastal EU countries "
            "with good maritime data are penalized."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier", "composite_eligibility"],
    ),

    # ───────────────────────────────────────────────────────────────────
    # GOVERNANCE: Confidence Penalties
    # ───────────────────────────────────────────────────────────────────

    _t(
        threshold_id="GOV_PENALTY_SINGLE_CHANNEL_A",
        name="Single Channel A Penalty",
        current_value=0.20,
        functional_role=(
            "Confidence reduction when one bilateral data channel is "
            "absent (Channel A missing)."
        ),
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Loss of one channel reduces the measurement construct by "
            "approximately half. But remaining channel still provides "
            "meaningful bilateral concentration. 0.20 is conservative — "
            "the axis is weakened but not destroyed."
        ),
        sensitivity_band={"low": 0.10, "high": 0.30},
        breakpoints=[
            {"value": 0.30, "effect": "CPIS-non-participant countries lose more confidence on Axis 1"},
        ],
        alternative_plausible_values=[
            {"value": 0.15, "rationale": "If one channel carries most information"},
            {"value": 0.25, "rationale": "Symmetric 50% construct loss → 0.25 penalty"},
        ],
        risk_if_misspecified=(
            "Low — this penalty rarely determines tier classification "
            "alone. Affects borderline cases only."
        ),
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence"],
    ),

    _t(
        threshold_id="GOV_PENALTY_SINGLE_CHANNEL_B",
        name="Single Channel B Penalty",
        current_value=0.20,
        functional_role="Symmetric with Channel A penalty.",
        rationale_type=RationaleType.HEURISTIC,
        justification="Symmetric design — same construct loss as Channel A absence.",
        sensitivity_band={"low": 0.10, "high": 0.30},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.15, "rationale": "If Channel B is less informative than A"},
        ],
        risk_if_misspecified="Low — symmetric with Channel A.",
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence"],
    ),

    _t(
        threshold_id="GOV_PENALTY_CPIS_NON_PARTICIPANT",
        name="CPIS Non-Participant Penalty",
        current_value=0.25,
        functional_role=(
            "Additional confidence penalty for countries not "
            "participating in IMF CPIS (eliminates portfolio "
            "investment data for Axis 1)."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "CPIS absence removes the entire portfolio debt/equity "
            "dimension from financial exposure measurement. Higher "
            "than generic channel loss because portfolio investment "
            "represents >40% of cross-border financial exposure for "
            "many countries (IMF data). 0.25 reflects the specific "
            "economic significance of the missing channel."
        ),
        sensitivity_band={"low": 0.15, "high": 0.35},
        breakpoints=[
            {"value": 0.35, "effect": "China, SA, IN drop to LOW confidence on Axis 1"},
        ],
        alternative_plausible_values=[
            {"value": 0.20, "rationale": "Align with generic channel loss"},
            {"value": 0.30, "rationale": "Portfolio investment is >50% of exposure for some"},
        ],
        risk_if_misspecified=(
            "If too low: CPIS absence is under-counted → financial "
            "axis appears more reliable than it is for non-participants. "
            "If too high: emerging markets are over-penalized on Axis 1."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier"],
    ),

    _t(
        threshold_id="GOV_PENALTY_REDUCED_GRANULARITY",
        name="Reduced Product Granularity Penalty",
        current_value=0.10,
        functional_role="Confidence reduction when HS6 used instead of CN8.",
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "HS6→CN8 collapse loses ~4 semiconductor subcategories. "
            "Empirical comparison for EU-27 shows <5% HHI deviation "
            "for most countries. Small penalty justified by data."
        ),
        sensitivity_band={"low": 0.05, "high": 0.15},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.05, "rationale": "Minimal empirical impact observed"},
            {"value": 0.15, "rationale": "For countries where subcategory matters (e.g., GPU vs memory)"},
        ],
        risk_if_misspecified="Low — minor impact on governance classification.",
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence"],
    ),

    _t(
        threshold_id="GOV_PENALTY_ZERO_BILATERAL",
        name="Zero Bilateral Suppliers Penalty",
        current_value=0.25,
        functional_role="Penalty when zero bilateral suppliers reported for an axis.",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Zero imports yield HHI=0.0 by construction. The score is "
            "technically valid but measures absence of trade, not low "
            "concentration. Moderate penalty signals construct ambiguity."
        ),
        sensitivity_band={"low": 0.10, "high": 0.35},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.10, "rationale": "If zero-import is a valid measurement"},
            {"value": 0.25, "rationale": "If HHI=0 is fundamentally uninformative"},
        ],
        risk_if_misspecified=(
            "Affects small EU states with genuinely zero defense imports. "
            "Over-penalizing makes them appear data-poor when they simply "
            "don't import weapons."
        ),
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence"],
    ),

    _t(
        threshold_id="GOV_PENALTY_PRODUCER_INVERSION",
        name="Producer Inversion Penalty",
        current_value=0.30,
        functional_role=(
            "Confidence penalty for axes where the country is a major "
            "global exporter (import concentration is structurally "
            "uninformative)."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "When a country is a net exporter of the measured commodity, "
            "its import concentration measures procurement of residual "
            "needs, not strategic dependency. The ISI construct is "
            "inverted. 0.30 is large enough to push most inverted axes "
            "to LOW confidence but not so large as to automatically "
            "trigger NON_COMPARABLE (which requires 3+ inversions)."
        ),
        sensitivity_band={"low": 0.20, "high": 0.40},
        breakpoints=[
            {"value": 0.20, "effect": "Countries with 2 inversions (AU) may stay at MODERATE instead of LOW"},
            {"value": 0.40, "effect": "Single-inversion countries (NO) drop to LOW confidence per-axis"},
        ],
        alternative_plausible_values=[
            {"value": 0.25, "rationale": "If residual imports still carry structural information"},
            {"value": 0.40, "rationale": "If import data is fundamentally misleading for exporters"},
        ],
        risk_if_misspecified=(
            "CRITICAL: If too low, producer countries appear more "
            "reliably measured than they are. If too high, it duplicates "
            "the discrete producer-inversion count used in tier rules."
        ),
        risk_level=RiskLevel.HIGH,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier", "cross_country_comparability"],
    ),

    _t(
        threshold_id="GOV_PENALTY_SANCTIONS",
        name="Sanctions Distortion Penalty",
        current_value=0.50,
        functional_role=(
            "Confidence penalty for countries under active sanctions "
            "regime during measurement window."
        ),
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification=(
            "Sanctions fundamentally alter bilateral trade patterns. "
            "Data reflects a crisis regime, not steady-state structure. "
            "0.50 penalty (combined with severity=1.0) ensures "
            "sanctioned countries cannot reach MODERATE confidence "
            "on any axis."
        ),
        sensitivity_band={"low": 0.40, "high": 0.60},
        breakpoints=[
            {"value": 0.40, "effect": "Some sanctioned country-axis pairs might reach MODERATE"},
        ],
        alternative_plausible_values=[
            {"value": 1.00, "rationale": "Full penalty — data is completely non-comparable"},
            {"value": 0.40, "rationale": "If some bilateral data is still usable"},
        ],
        risk_if_misspecified=(
            "If too low: sanctioned country outputs might pass governance "
            "gates. If too high: no marginal effect beyond severity=1.0."
        ),
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier"],
    ),

    _t(
        threshold_id="GOV_PENALTY_LOGISTICS_ABSENT",
        name="Logistics Data Absent Penalty",
        current_value=1.00,
        functional_role="Full penalty when logistics axis has no data at all.",
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification="No data → no confidence. Absolute structural absence.",
        sensitivity_band={"low": 0.80, "high": 1.00},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.80, "rationale": "If absence is partially informative (implies minimal trade)"},
        ],
        risk_if_misspecified="Low — 1.0 penalty for absent data is the only defensible choice.",
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["axis_confidence"],
    ),

    # ───────────────────────────────────────────────────────────────────
    # GOVERNANCE: Confidence Level Thresholds
    # ───────────────────────────────────────────────────────────────────

    _t(
        threshold_id="GOV_CONF_HIGH",
        name="HIGH Confidence Level Threshold",
        current_value=0.65,
        functional_role="Minimum score for HIGH confidence classification.",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Set to allow well-covered EU-27 members (baseline 0.75-0.80, "
            "minor penalties) to reach HIGH. A country with one minor "
            "penalty (~0.10) on a 0.75-baseline axis still qualifies. "
            "This is a design choice to avoid classifying the majority "
            "of EU-27 axes as merely MODERATE."
        ),
        sensitivity_band={"low": 0.55, "high": 0.75},
        breakpoints=[
            {"value": 0.55, "effect": "Almost all EU-27 axes become HIGH — loses discrimination"},
            {"value": 0.75, "effect": "Only axes with zero penalties qualify — too restrictive"},
        ],
        alternative_plausible_values=[
            {"value": 0.60, "rationale": "More inclusive — most single-penalty axes qualify"},
            {"value": 0.70, "rationale": "Only truly well-covered axes qualify"},
        ],
        risk_if_misspecified=(
            "HIGH: If threshold is too low, 'HIGH confidence' becomes "
            "meaningless (everyone qualifies). If too high, even well-"
            "covered countries are flagged as MODERATE, reducing "
            "discrimination at the top."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["confidence_level", "governance_tier_rules"],
    ),

    _t(
        threshold_id="GOV_CONF_MODERATE",
        name="MODERATE Confidence Level Threshold",
        current_value=0.45,
        functional_role="Minimum score for MODERATE confidence classification.",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Set so that axes with one major penalty (e.g., producer "
            "inversion at 0.30 on a 0.55 baseline) land at MODERATE. "
            "Defense axis (baseline 0.55) with inversion penalty "
            "(0.55-0.30=0.25) lands at LOW — which is correct."
        ),
        sensitivity_band={"low": 0.35, "high": 0.55},
        breakpoints=[
            {"value": 0.35, "effect": "Defense with inversion (0.25) stays LOW — correct"},
            {"value": 0.55, "effect": "Many axes with single penalties drop from MODERATE to LOW"},
        ],
        alternative_plausible_values=[
            {"value": 0.40, "rationale": "More inclusive MODERATE band"},
            {"value": 0.50, "rationale": "Stricter — only clean axes reach MODERATE"},
        ],
        risk_if_misspecified=(
            "This threshold determines the MODERATE/LOW boundary which "
            "directly feeds into ranking eligibility rules. Countries "
            "near this boundary are threshold-fragile."
        ),
        risk_level=RiskLevel.HIGH,
        source_module="governance.py",
        affects=["confidence_level", "ranking_eligibility", "governance_tier"],
    ),

    _t(
        threshold_id="GOV_CONF_LOW",
        name="LOW Confidence Level Threshold",
        current_value=0.25,
        functional_role="Minimum score for LOW confidence (vs NONE).",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Below 0.25, the axis has essentially no reliable data. "
            "Set to ensure that sanctioned countries with severe "
            "penalties (baseline 0.60 minus 0.50 sanctions = 0.10) "
            "fall below LOW to NONE confidence."
        ),
        sensitivity_band={"low": 0.15, "high": 0.35},
        breakpoints=[
            {"value": 0.15, "effect": "Even heavily penalized axes retain LOW status"},
            {"value": 0.35, "effect": "More axes drop to NONE — may be too strict"},
        ],
        alternative_plausible_values=[
            {"value": 0.20, "rationale": "Stricter NONE boundary"},
            {"value": 0.30, "rationale": "Aligns with single-major-penalty on low-baseline axis"},
        ],
        risk_if_misspecified=(
            "Low — NONE confidence triggers NON_COMPARABLE through "
            "other rules. The boundary matters less than MODERATE."
        ),
        risk_level=RiskLevel.LOW,
        source_module="governance.py",
        affects=["confidence_level"],
    ),

    # ───────────────────────────────────────────────────────────────────
    # GOVERNANCE: Composite & Ranking Thresholds
    # ───────────────────────────────────────────────────────────────────

    _t(
        threshold_id="GOV_MIN_AXES_COMPOSITE",
        name="Minimum Axes for Composite Eligibility",
        current_value=4,
        functional_role=(
            "Minimum number of valid axes required to compute a "
            "composite ISI score."
        ),
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification=(
            "ISI has 6 axes. Requiring 4/6 (67%) ensures the composite "
            "captures a majority of the dependency spectrum. Below 4, "
            "the composite represents <67% of the construct — a minority "
            "of axes could dominate. This is a design decision, not an "
            "empirical finding."
        ),
        sensitivity_band={"low": 3, "high": 5},
        breakpoints=[
            {"value": 3, "effect": "Composite possible with half the axes — weakens representativeness"},
            {"value": 5, "effect": "Countries missing logistics axis (common) become ineligible"},
            {"value": 6, "effect": "Only countries with perfect coverage qualify — too exclusive"},
        ],
        alternative_plausible_values=[
            {"value": 3, "rationale": "Simple majority (>50%)"},
            {"value": 5, "rationale": "Supermajority (>83%)"},
        ],
        risk_if_misspecified=(
            "If too low: composites based on 3 axes are published as "
            "'complete' — misleading. If too high: well-covered countries "
            "missing one weak axis lose composite entirely."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["composite_eligibility", "country_classification"],
    ),

    _t(
        threshold_id="GOV_MIN_AXES_RANKING",
        name="Minimum Axes for Ranking Eligibility",
        current_value=5,
        functional_role=(
            "Minimum valid axes for a country to be ranking-eligible."
        ),
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification=(
            "Ranking requires higher coverage than composite computation "
            "because rankings amplify small differences. With 5/6 axes, "
            "the ranking reflects >83% of the construct. The gap between "
            "composite (4) and ranking (5) creates a meaningful buffer "
            "zone."
        ),
        sensitivity_band={"low": 4, "high": 6},
        breakpoints=[
            {"value": 4, "effect": "Ranking and composite thresholds merge — no buffer zone"},
            {"value": 6, "effect": "Only perfect-coverage countries can be ranked"},
        ],
        alternative_plausible_values=[
            {"value": 4, "rationale": "Same as composite — simpler, less conservative"},
            {"value": 6, "rationale": "Maximum strictness — only complete profiles ranked"},
        ],
        risk_if_misspecified=(
            "If too low: countries with missing axes get ranked on "
            "incomplete information. If too high: very few countries "
            "qualify for ranking."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["ranking_eligibility", "country_classification"],
    ),

    _t(
        threshold_id="GOV_MIN_MEAN_CONF_RANKING",
        name="Minimum Mean Confidence for Ranking",
        current_value=0.45,
        functional_role=(
            "Minimum mean axis confidence for ranking eligibility. "
            "Countries below this are too low-confidence for ranking."
        ),
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Set at MODERATE confidence boundary (0.45). Rationale: "
            "if the average axis confidence is below MODERATE, the "
            "composite is built on low-confidence data and ranking "
            "differences may be noise, not signal."
        ),
        sensitivity_band={"low": 0.35, "high": 0.55},
        breakpoints=[
            {"value": 0.35, "effect": "2-3 additional countries qualify for ranking (those with 1-2 inversions)"},
            {"value": 0.55, "effect": "Several EU-27 members lose ranking eligibility"},
        ],
        alternative_plausible_values=[
            {"value": 0.40, "rationale": "More permissive — includes borderline cases"},
            {"value": 0.50, "rationale": "Stricter — only solid MODERATE-average countries"},
        ],
        risk_if_misspecified=(
            "CRITICAL: This threshold directly gates which countries "
            "appear in ISI rankings. Off by 0.10 in either direction "
            "changes the ranked set by 2-4 countries."
        ),
        risk_level=RiskLevel.CRITICAL,
        source_module="governance.py",
        affects=["ranking_eligibility", "country_classification", "published_rankings"],
    ),

    _t(
        threshold_id="GOV_MAX_LOW_AXES_RANKING",
        name="Maximum LOW-Confidence Axes for Ranking",
        current_value=2,
        functional_role=(
            "Maximum number of axes at LOW confidence for a country "
            "to remain ranking-eligible."
        ),
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification=(
            "With 6 axes, allowing 2 LOW-confidence axes means 4/6 "
            "(67%) are at MODERATE or above. If 3+ axes are LOW, the "
            "composite is dominated by weak data — ranking differences "
            "may be artifacts."
        ),
        sensitivity_band={"low": 1, "high": 3},
        breakpoints=[
            {"value": 1, "effect": "Countries with defense(LOW)+logistics(LOW) lose ranking"},
            {"value": 3, "effect": "Countries with half their axes at LOW can still rank — permissive"},
        ],
        alternative_plausible_values=[
            {"value": 1, "rationale": "Conservative — at most one weak axis"},
            {"value": 3, "rationale": "Permissive — simple majority of axes at MODERATE+"},
        ],
        risk_if_misspecified=(
            "Moderate — interacts with mean confidence threshold. "
            "Countries with exactly 2 LOW axes are the fragile set."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["ranking_eligibility"],
    ),

    _t(
        threshold_id="GOV_MAX_INVERTED_COMPARABLE",
        name="Maximum Inverted Axes for Cross-Country Comparability",
        current_value=2,
        functional_role=(
            "Maximum producer-inverted axes for a country to remain "
            "eligible for cross-country comparison."
        ),
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification=(
            "With 6 axes, if 3+ are structurally inverted, the "
            "composite measures a fundamentally different construct "
            "for that country. 2 inversions is the maximum where "
            "the majority of axes (4/6) still measure the intended "
            "import-dependency construct."
        ),
        sensitivity_band={"low": 1, "high": 3},
        breakpoints=[
            {"value": 1, "effect": "AU (2 inversions) drops from LOW_CONFIDENCE to NON_COMPARABLE"},
            {"value": 3, "effect": "US (3 inversions) becomes LOW_CONFIDENCE instead of NON_COMPARABLE"},
        ],
        alternative_plausible_values=[
            {"value": 1, "rationale": "Any inversion makes comparison questionable"},
            {"value": 3, "rationale": "Only majority-inverted countries excluded"},
        ],
        risk_if_misspecified=(
            "HIGH: This threshold determines which major economies "
            "(US, AU, RU) are classified as NON_COMPARABLE. It is "
            "the single most consequential discrete threshold for "
            "country inclusion/exclusion."
        ),
        risk_level=RiskLevel.CRITICAL,
        source_module="governance.py",
        affects=["cross_country_comparability", "governance_tier", "country_classification"],
    ),

    _t(
        threshold_id="GOV_LOGISTICS_PROXY_CAP",
        name="Logistics Proxy Confidence Cap",
        current_value=0.40,
        functional_role=(
            "Maximum confidence score for logistics axis when proxy "
            "data is used (non-Eurostat countries)."
        ),
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Proxy logistics data (trade-value weighted) measures "
            "a different construct than bilateral freight flows. "
            "Capping at 0.40 (MODERATE/LOW boundary) prevents proxy "
            "data from inflating logistics confidence above MODERATE."
        ),
        sensitivity_band={"low": 0.30, "high": 0.50},
        breakpoints=[
            {"value": 0.30, "effect": "Proxy logistics always at LOW — may be too strict for coastal countries"},
            {"value": 0.50, "effect": "Proxy logistics can reach MODERATE — may be too generous"},
        ],
        alternative_plausible_values=[
            {"value": 0.35, "rationale": "Tighter cap — proxy data is fundamentally different"},
            {"value": 0.45, "rationale": "Maritime-proxy captures meaningful freight structure"},
        ],
        risk_if_misspecified=(
            "Moderate — primarily affects non-EU reference countries "
            "and small EU states without direct Eurostat logistics data."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="governance.py",
        affects=["axis_confidence", "governance_tier"],
    ),

    # ───────────────────────────────────────────────────────────────────
    # SEVERITY: Weight Thresholds
    # ───────────────────────────────────────────────────────────────────

    _t(
        threshold_id="SEV_W_HS6_GRANULARITY",
        name="Severity Weight: HS6 Granularity",
        current_value=0.2,
        functional_role="Degradation severity from HS6 vs CN8 classification collapse.",
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "EU-27 CN8→HS6 comparison shows <5% HHI deviation for most "
            "countries. Low severity — product granularity loss has "
            "minimal impact on bilateral concentration structure."
        ),
        sensitivity_band={"low": 0.1, "high": 0.3},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.1, "rationale": "Minimal empirical impact"},
            {"value": 0.3, "rationale": "For axes where subcategory matters more"},
        ],
        risk_if_misspecified="Low — affects comparability tier marginally.",
        risk_level=RiskLevel.LOW,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity"],
    ),

    _t(
        threshold_id="SEV_W_SINGLE_CHANNEL",
        name="Severity Weight: Single Channel Loss",
        current_value=0.4,
        functional_role="Degradation from loss of one bilateral data channel.",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Losing one channel reduces the bilateral measurement "
            "construct by approximately half. But the remaining channel "
            "still captures meaningful concentration structure. 0.4 "
            "reflects 'significant but not fatal' degradation."
        ),
        sensitivity_band={"low": 0.3, "high": 0.5},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.3, "rationale": "If one channel carries most info"},
            {"value": 0.5, "rationale": "If channels are equally informative"},
        ],
        risk_if_misspecified="Moderate — affects severity-to-tier mapping.",
        risk_level=RiskLevel.MODERATE,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity"],
    ),

    _t(
        threshold_id="SEV_W_CPIS_NON_PARTICIPANT",
        name="Severity Weight: CPIS Non-Participant",
        current_value=0.5,
        functional_role=(
            "Degradation from absence of IMF CPIS data (eliminates "
            "portfolio investment channel for Axis 1)."
        ),
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "CPIS absence eliminates portfolio investment concentration "
            "entirely. For financial exposure, portfolio debt/equity "
            "represents >40% of cross-border exposure. 0.5 reflects "
            "that half the measurement construct is missing."
        ),
        sensitivity_band={"low": 0.4, "high": 0.6},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.4, "rationale": "Banking claims may carry more information"},
            {"value": 0.6, "rationale": "Portfolio investment is majority of exposure for some"},
        ],
        risk_if_misspecified="Moderate — affects CN, IN, BR, SA comparability.",
        risk_level=RiskLevel.MODERATE,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity"],
    ),

    _t(
        threshold_id="SEV_W_PRODUCER_INVERSION",
        name="Severity Weight: Producer Inversion",
        current_value=0.7,
        functional_role="Degradation from import-concentration measuring wrong construct for exporters.",
        rationale_type=RationaleType.SEMI_EMPIRICAL,
        justification=(
            "For net exporters, import concentration measures procurement "
            "of residual needs, not strategic dependency. The ISI construct "
            "is fundamentally inverted. 0.7 is very high because the score "
            "is not just degraded — it measures the wrong thing."
        ),
        sensitivity_band={"low": 0.5, "high": 0.9},
        breakpoints=[
            {"value": 0.5, "effect": "Producer countries' severity may stay in TIER_2 instead of TIER_3"},
            {"value": 0.9, "effect": "Single inversion could push a country to TIER_4"},
        ],
        alternative_plausible_values=[
            {"value": 0.6, "rationale": "If residual import data still carries information"},
            {"value": 0.8, "rationale": "Closer to sanctions severity — almost structural"},
        ],
        risk_if_misspecified=(
            "HIGH: Determines severity tier for 8 registered producer "
            "countries. Directly interacts with governance tier rules."
        ),
        risk_level=RiskLevel.HIGH,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity", "governance_tier"],
    ),

    _t(
        threshold_id="SEV_W_SANCTIONS",
        name="Severity Weight: Sanctions Distortion",
        current_value=1.0,
        functional_role="Maximum degradation — active sanctions regime.",
        rationale_type=RationaleType.STRUCTURAL_NORMATIVE,
        justification=(
            "Sanctions fundamentally alter bilateral trade patterns. "
            "Data reflects crisis regime, not steady state. Maximum "
            "severity is the only defensible choice — no partial "
            "credit for sanctioned data."
        ),
        sensitivity_band={"low": 0.8, "high": 1.0},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.8, "rationale": "If some pre-sanctions data is blended into window"},
        ],
        risk_if_misspecified="Low — 1.0 is structurally motivated and uncontroversial.",
        risk_level=RiskLevel.LOW,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity"],
    ),

    _t(
        threshold_id="SEV_W_ZERO_BILATERAL",
        name="Severity Weight: Zero Bilateral Suppliers",
        current_value=0.6,
        functional_role="Degradation when zero bilateral suppliers are reported.",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Zero imports → HHI=0.0 by construction. The score is "
            "correct but semantically ambiguous: it could mean low "
            "dependency OR data absence. 0.6 flags this as 'high "
            "interpretive risk.'"
        ),
        sensitivity_band={"low": 0.4, "high": 0.7},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.4, "rationale": "If zero-import is genuinely informative"},
            {"value": 0.7, "rationale": "If zero-import is likely data absence"},
        ],
        risk_if_misspecified=(
            "Moderate — affects small EU states on defense/critical inputs."
        ),
        risk_level=RiskLevel.MODERATE,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity"],
    ),

    _t(
        threshold_id="SEV_W_TEMPORAL_MISMATCH",
        name="Severity Weight: Temporal Mismatch",
        current_value=0.3,
        functional_role="Degradation from mixing data years within an axis.",
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Mixing partners from different years breaks point-in-time "
            "bilateral structure. Partner overlap may be partial. "
            "Moderate severity — structure changes slowly for most "
            "countries."
        ),
        sensitivity_band={"low": 0.2, "high": 0.4},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.2, "rationale": "Bilateral structure is relatively stable"},
            {"value": 0.4, "rationale": "For volatile axes like defense"},
        ],
        risk_if_misspecified="Low — affects edge cases only.",
        risk_level=RiskLevel.LOW,
        source_module="severity.py",
        affects=["comparability_tier", "total_severity"],
    ),

    _t(
        threshold_id="SEV_W_SOURCE_HETEROGENEITY",
        name="Severity Weight: Source Heterogeneity",
        current_value=0.4,
        functional_role=(
            "Degradation from composite merging axes with incompatible "
            "data sources."
        ),
        rationale_type=RationaleType.HEURISTIC,
        justification=(
            "Each axis uses different sources (BIS, Comtrade, SIPRI, "
            "UNCTAD). Cross-axis mixing reduces composite "
            "interpretability. Same weight as channel loss — "
            "conceptually similar degradation."
        ),
        sensitivity_band={"low": 0.3, "high": 0.5},
        breakpoints=[],
        alternative_plausible_values=[
            {"value": 0.3, "rationale": "If normalization makes axes comparable"},
            {"value": 0.5, "rationale": "If source heterogeneity is the primary composite weakness"},
        ],
        risk_if_misspecified="Low — applied to all composites equally.",
        risk_level=RiskLevel.LOW,
        source_module="severity.py",
        affects=["comparability_tier"],
    ),

]


# ═══════════════════════════════════════════════════════════════════════════
# QUERY INTERFACE
# ═══════════════════════════════════════════════════════════════════════════

def get_threshold_justification_registry() -> list[dict[str, Any]]:
    """Return the complete threshold justification registry."""
    return list(THRESHOLD_JUSTIFICATION_REGISTRY)


def get_threshold_by_id(threshold_id: str) -> dict[str, Any] | None:
    """Look up a single threshold entry by ID."""
    for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
        if entry["threshold_id"] == threshold_id:
            return dict(entry)
    return None


def get_thresholds_by_source(source_module: str) -> list[dict[str, Any]]:
    """Return all thresholds from a given source module."""
    return [
        e for e in THRESHOLD_JUSTIFICATION_REGISTRY
        if e["source_module"] == source_module
    ]


def get_thresholds_by_rationale(rationale_type: str) -> list[dict[str, Any]]:
    """Return all thresholds of a given rationale type."""
    return [
        e for e in THRESHOLD_JUSTIFICATION_REGISTRY
        if e["rationale_type"] == rationale_type
    ]


def get_thresholds_by_risk(risk_level: str) -> list[dict[str, Any]]:
    """Return all thresholds at a given risk level."""
    return [
        e for e in THRESHOLD_JUSTIFICATION_REGISTRY
        if e["risk_level"] == risk_level
    ]


def get_registry_summary() -> dict[str, Any]:
    """Return summary statistics of the threshold registry."""
    total = len(THRESHOLD_JUSTIFICATION_REGISTRY)
    by_rationale: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    by_source: dict[str, int] = {}

    for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
        r = entry["rationale_type"]
        by_rationale[r] = by_rationale.get(r, 0) + 1
        k = entry["risk_level"]
        by_risk[k] = by_risk.get(k, 0) + 1
        s = entry["source_module"]
        by_source[s] = by_source.get(s, 0) + 1

    critical = get_thresholds_by_risk(RiskLevel.CRITICAL)
    high = get_thresholds_by_risk(RiskLevel.HIGH)

    return {
        "total_thresholds": total,
        "by_rationale_type": by_rationale,
        "by_risk_level": by_risk,
        "by_source_module": by_source,
        "critical_thresholds": [t["threshold_id"] for t in critical],
        "high_risk_thresholds": [t["threshold_id"] for t in high],
        "honesty_note": (
            f"Of {total} registered thresholds, "
            f"{by_rationale.get(RationaleType.HEURISTIC, 0)} are HEURISTIC "
            f"(expert judgment only), "
            f"{by_rationale.get(RationaleType.STRUCTURAL_NORMATIVE, 0)} are "
            f"STRUCTURAL_NORMATIVE (design choices), and "
            f"{by_rationale.get(RationaleType.SEMI_EMPIRICAL, 0)} are "
            f"SEMI_EMPIRICAL (partially evidence-based). "
            f"NONE are fully EMPIRICAL. Every threshold is a choice, "
            f"not a measurement."
        ),
    }
