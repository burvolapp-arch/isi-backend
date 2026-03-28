"""
backend.calibration — Calibration, falsifiability, and epistemic registry for ISI.

AUTHORITY NOTE:
    This module is a METADATA and AUDIT module. It does NOT determine
    eligibility, compute scores, or define benchmarks. Authority hierarchy:

    - Eligibility: backend/eligibility.py (AUTHORITATIVE)
      This module's EligibilityClass + COUNTRY_ELIGIBILITY_REGISTRY are
      supplementary metadata, subordinate to eligibility.py.

    - External benchmarks: backend/benchmark_registry.py (AUTHORITATIVE)
      This module's EXTERNAL_BENCHMARK_REGISTRY is DEPRECATED.
      Use benchmark_registry.py for all benchmark work.

    - Thresholds: backend/threshold_registry.py has machine-readable
      justification entries. This module has calibration-class entries.
      Both are valid — threshold_registry.py is richer.

    - Unique content preserved here:
      * CalibrationClass + THRESHOLD_CALIBRATION entries (epistemic status)
      * FALSIFIABILITY_REGISTRY (mechanism-based falsification criteria)
      * CIRCULARITY_AUDIT (data-flow circularity analysis)
      * AXIS_CALIBRATION_NOTES (per-axis holistic calibration metadata)
      * Governance-threshold sensitivity analysis
      * PSEUDO_RIGOR_AUDIT (self-audit for false confidence)
      * build_governance_explanation() (enhanced governance explanation)

This module exists because:
    - Every threshold in the governance/severity model has an
      epistemic status: some are empirically calibrated, some are
      semi-empirical, some are heuristic, and some are normative.
    - If a threshold LOOKS calibrated but is actually a guess, the
      system is dishonest. This module makes that impossible.
    - Every mechanism in the governance model must have explicit
      falsifiability criteria — what evidence would STRENGTHEN,
      WEAKEN, or FALSIFY each assumption.

This is NOT a scoring module. It does not modify any computed values.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# TASK 1 + 2: THRESHOLD CALIBRATION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════
# Every numeric threshold in governance.py and severity.py is listed here
# with its calibration_class, evidence_basis, sensitivity_note, and
# what would need to change to upgrade it.

class CalibrationClass:
    """Calibration classification constants."""
    EMPIRICAL = "EMPIRICAL"
    SEMI_EMPIRICAL = "SEMI_EMPIRICAL"
    HEURISTIC = "HEURISTIC"
    STRUCTURAL_NORMATIVE = "STRUCTURAL_NORMATIVE"


VALID_CALIBRATION_CLASSES = frozenset({
    CalibrationClass.EMPIRICAL,
    CalibrationClass.SEMI_EMPIRICAL,
    CalibrationClass.HEURISTIC,
    CalibrationClass.STRUCTURAL_NORMATIVE,
})


def _threshold_entry(
    *,
    name: str,
    value: Any,
    module: str,
    calibration_class: str,
    evidence_basis: str,
    sensitivity_note: str,
    upgrade_path: str,
    falsifiable_by: str,
) -> dict[str, Any]:
    """Create a validated threshold registry entry."""
    assert calibration_class in VALID_CALIBRATION_CLASSES, (
        f"Invalid calibration_class '{calibration_class}' for threshold '{name}'"
    )
    return {
        "name": name,
        "value": value,
        "module": module,
        "calibration_class": calibration_class,
        "evidence_basis": evidence_basis,
        "sensitivity_note": sensitivity_note,
        "upgrade_path": upgrade_path,
        "falsifiable_by": falsifiable_by,
    }


# ---------------------------------------------------------------------------
# SEVERITY WEIGHTS — from backend/severity.py
# ---------------------------------------------------------------------------

SEVERITY_WEIGHT_CALIBRATIONS: list[dict[str, Any]] = [
    _threshold_entry(
        name="SEVERITY_WEIGHT:HS6_GRANULARITY",
        value=0.2,
        module="severity",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "EU-27 CN8→HS6 mapping shows <5% score deviation for most "
            "countries. Weight reflects 'low but non-zero' impact on HHI. "
            "Semi-empirical: the direction is data-informed but the 0.2 "
            "magnitude is a judgmental rounding."
        ),
        sensitivity_note=(
            "±0.1 change (0.1→0.3) would not change any tier boundary "
            "because this flag rarely appears alone and its weight is "
            "dominated by co-occurring flags."
        ),
        upgrade_path=(
            "Full calibration requires: compute HHI at CN8 and HS6 for "
            "all EU-27 countries, measure RMSD of score differences, "
            "set weight = RMSD / max_possible_HHI_change."
        ),
        falsifiable_by=(
            "If CN8→HS6 remapping produces >10% HHI change for >25% of "
            "countries, 0.2 is too low. If <2% for all countries, 0.2 "
            "is unnecessarily high."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:TEMPORAL_MISMATCH",
        value=0.3,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Judgment: mixing partners from adjacent years introduces "
            "moderate noise because bilateral trade structure has year-on-"
            "year autocorrelation >0.8 for most country pairs. The 0.3 "
            "value is a heuristic midpoint between 'negligible' (0.1) "
            "and 'major' (0.5)."
        ),
        sensitivity_note=(
            "±0.1 change affects countries with ONLY temporal mismatch. "
            "Most flagged countries also have channel loss flags, making "
            "this weight subordinate in the degradation-group MAX rule."
        ),
        upgrade_path=(
            "Calibrate by computing HHI scores for each EU-27 country "
            "using t vs t-1 data and measuring the distribution of "
            "absolute deviations. Weight = median(|HHI_t - HHI_{t-1}|) / scale."
        ),
        falsifiable_by=(
            "If year-on-year HHI autocorrelation is <0.6 for >10 countries, "
            "temporal mismatch is more damaging than 0.3 implies. If "
            "autocorrelation >0.95 universally, 0.3 is too conservative."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:SINGLE_CHANNEL_A",
        value=0.4,
        module="severity",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "Losing Channel B (category weights for tech, portfolio "
            "debt for financial) narrows the construct substantially. "
            "For Axis 1, Channel A alone (BIS LBS) captures banking "
            "but not securities — empirically ~40-60% of bilateral "
            "financial exposure for most countries. 0.4 reflects "
            "'moderate-to-high construct narrowing.'"
        ),
        sensitivity_note=(
            "In DATA_GRANULARITY degradation group, this is MAX'd with "
            "CPIS_NON_PARTICIPANT (0.5). Moving from 0.4→0.5 changes "
            "nothing when CPIS flag is co-present. Moving to 0.3 "
            "would lower severity for countries with ONLY single-channel."
        ),
        upgrade_path=(
            "Compute dual-channel vs single-channel HHI for countries "
            "where both are available. Weight = mean(|HHI_dual - HHI_single|) "
            "/ scale."
        ),
        falsifiable_by=(
            "If dual-channel vs single-channel HHI correlation >0.95 for "
            ">80% of countries, 0.4 is too high. If correlation <0.7, "
            "0.4 is too low."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:SINGLE_CHANNEL_B",
        value=0.4,
        module="severity",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "Symmetric with SINGLE_CHANNEL_A by design — same construct "
            "narrowing rationale. Both represent loss of one bilateral "
            "dimension. If evidence shows A vs B asymmetry, split weights."
        ),
        sensitivity_note="Same as SINGLE_CHANNEL_A.",
        upgrade_path="Same as SINGLE_CHANNEL_A.",
        falsifiable_by="Same as SINGLE_CHANNEL_A.",
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:CPIS_NON_PARTICIPANT",
        value=0.5,
        module="severity",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "IMF CPIS absence eliminates portfolio investment bilateral "
            "data entirely. For Axis 1, this halves the available "
            "bilateral structure. 0.5 = 'half the construct is missing.' "
            "Higher than generic channel loss because CPIS specifically "
            "measures cross-border securities — a large component of "
            "financial exposure for developed economies."
        ),
        sensitivity_note=(
            "Axis 1 specific. Moving to 0.4 (same as generic channel "
            "loss) would undercount the financial significance. Moving "
            "to 0.6 is defensible but pushes toward treating non-"
            "participation as near-structural."
        ),
        upgrade_path=(
            "Compare Axis 1 scores for CPIS participants vs non-"
            "participants using the same partner universe. If scores "
            "diverge significantly, weight is justified or too low."
        ),
        falsifiable_by=(
            "If CPIS data adds <10% explanatory power to Axis 1 HHI "
            "for CPIS participants, 0.5 is too high. If Axis 1 scores "
            "are qualitatively different with/without CPIS for >50% of "
            "participants, 0.5 is justified."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:ZERO_BILATERAL_SUPPLIERS",
        value=0.6,
        module="severity",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Zero imports → HHI = 0.0 by construction (D-5 semantic). "
            "This is a CONSTRUCT choice: we define 'no bilateral "
            "suppliers' as semantically distinct from 'low concentration.' "
            "0.6 reflects 'score is correct but likely misleading.' "
            "This is normative, not empirically calibrated."
        ),
        sensitivity_note=(
            "Affects only axes where a country has zero bilateral "
            "partners. Moving to 0.5 or 0.7 changes few tier "
            "outcomes because zero-supplier axes co-occur with "
            "other flags."
        ),
        upgrade_path=(
            "Normative — no empirical upgrade path. Could be "
            "reclassified if zero-supplier HHI is given a distinct "
            "semantic category instead of being penalized."
        ),
        falsifiable_by=(
            "If zero-supplier countries systematically rank 'correctly' "
            "in validation against expert assessments, the penalty is "
            "unnecessary. If they rank incorrectly, the penalty is "
            "insufficient or the construct needs redesign."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:PRODUCER_INVERSION",
        value=0.7,
        module="severity",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "For a major exporter, import concentration measures "
            "'absence of import dependency' not 'strategic vulnerability.' "
            "The ISI construct is structurally inapplicable. 0.7 reflects "
            "'construct is measuring the wrong thing on this axis.' "
            "This is a normative design decision about when the construct "
            "breaks, not an empirical calibration."
        ),
        sensitivity_note=(
            "Raising to 0.8-1.0 would make any producer-inverted axis "
            "tantamount to axis-absent. Lowering to 0.5 would make "
            "producer countries look more comparable than they are."
        ),
        upgrade_path=(
            "Would require an alternative construct for producers "
            "(e.g., export dependency HHI) to validate whether import "
            "concentration truly misrepresents their position."
        ),
        falsifiable_by=(
            "If a method is developed to validate ISI rankings against "
            "expert panel assessments of strategic vulnerability, and "
            "producer-inverted countries rank 'correctly' despite "
            "inversion, the 0.7 penalty is too high."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:SANCTIONS_DISTORTION",
        value=1.0,
        module="severity",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Sanctions fundamentally alter trade patterns. Data from a "
            "sanctions period reflects crisis-regime bilateral structure, "
            "not steady-state concentration. Maximum weight by design: "
            "sanctioned data is never comparable to non-sanctioned."
        ),
        sensitivity_note=(
            "Already at maximum (1.0). Lowering requires a principled "
            "argument that sanctions-era data retains partial validity."
        ),
        upgrade_path=(
            "Could be refined with pre/post sanctions trade structure "
            "comparison — if trade patterns show partial continuity, "
            "a weight <1.0 might be defensible."
        ),
        falsifiable_by=(
            "If pre-sanctions and sanctions-era HHI are correlated "
            ">0.7 for sanctioned countries, 1.0 is unnecessarily "
            "severe. If correlation <0.3, 1.0 is justified."
        ),
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:REDUCED_PRODUCT_GRANULARITY",
        value=0.2,
        module="severity",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis="Alias for HS6_GRANULARITY. Same calibration basis.",
        sensitivity_note="Same as HS6_GRANULARITY.",
        upgrade_path="Same as HS6_GRANULARITY.",
        falsifiable_by="Same as HS6_GRANULARITY.",
    ),
    _threshold_entry(
        name="SEVERITY_WEIGHT:SOURCE_HETEROGENEITY",
        value=0.4,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Cross-source compositing (BIS+Comtrade+SIPRI) introduces "
            "incompatible partner universes and coverage. 0.4 is a "
            "heuristic reflecting 'moderate construct mixing.' No "
            "direct empirical calibration available."
        ),
        sensitivity_note=(
            "Affects composite defensibility. ±0.1 change has limited "
            "tier impact because source heterogeneity is inherent to "
            "the ISI design and always present."
        ),
        upgrade_path=(
            "Calibrate by computing axes from homogeneous vs "
            "heterogeneous sources for overlapping partner sets."
        ),
        falsifiable_by=(
            "If composite scores are insensitive to source choice "
            "(permutation test), 0.4 is too high. If sensitive, "
            "0.4 is justified or too low."
        ),
    ),
]


# ---------------------------------------------------------------------------
# SEVERITY TIER THRESHOLDS — from backend/severity.py
# ---------------------------------------------------------------------------

SEVERITY_TIER_CALIBRATIONS: list[dict[str, Any]] = [
    _threshold_entry(
        name="TIER_THRESHOLD:TIER_1",
        value=0.5,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "TIER_1 boundary at 0.5 means: at most one minor issue "
            "(e.g., HS6 granularity at 0.2 + temporal mismatch at 0.3). "
            "This is a heuristic boundary — chosen to partition 'clean' "
            "from 'slightly degraded.' Not empirically calibrated against "
            "output quality."
        ),
        sensitivity_note=(
            "Moving to 0.4 makes TIER_1 stricter (fewer countries qualify). "
            "Moving to 0.6 relaxes it. The current value permits one "
            "moderate flag without leaving TIER_1, which is an intentional "
            "design choice."
        ),
        upgrade_path=(
            "Calibrate against output validation: what severity level "
            "actually correlates with 'outputs are fully trustworthy' "
            "as assessed by domain experts."
        ),
        falsifiable_by=(
            "If countries at severity 0.4 and 0.6 have indistinguishable "
            "output quality, the boundary is arbitrary. If there's a "
            "measurable quality drop at 0.5, it's validated."
        ),
    ),
    _threshold_entry(
        name="TIER_THRESHOLD:TIER_2",
        value=1.5,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "TIER_2 boundary at 1.5 means: multiple moderate issues "
            "OR one severe issue. The gap from 0.5→1.5 is deliberately "
            "wide — it absorbs the broad middle range of data quality. "
            "Heuristic: chosen to create meaningful separation between "
            "'caveated' and 'problematic.'"
        ),
        sensitivity_note=(
            "Moving to 1.0 would push many EU-27 countries from TIER_2 "
            "to TIER_3, significantly increasing LOW_CONFIDENCE "
            "classifications. Moving to 2.0 collapses TIER_2 into "
            "TIER_3 for most purposes."
        ),
        upgrade_path=(
            "Same as TIER_1 — requires output quality validation."
        ),
        falsifiable_by=(
            "If severity 1.0 vs 1.4 countries have different output "
            "reliability, 1.5 may be too generous. If severity 1.5 "
            "vs 2.0 countries are indistinguishable, the tier structure "
            "is poorly calibrated."
        ),
    ),
    _threshold_entry(
        name="TIER_THRESHOLD:TIER_3",
        value=3.0,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "TIER_3/TIER_4 boundary at 3.0 = compound severe issues. "
            "A single SANCTIONS_DISTORTION (1.0) + PRODUCER_INVERSION "
            "(0.7) + channel loss (0.5) exceeds 2.0 but not 3.0. "
            "3.0 requires either sanctions + multiple structural flags "
            "or extreme cumulative degradation. Heuristic: boundary "
            "reflects 'beyond recovery' for any interpretive purpose."
        ),
        sensitivity_note=(
            "Moving to 2.5 makes more countries TIER_4 (non-comparable). "
            "Moving to 3.5 relaxes it. Currently, only sanctions-"
            "affected countries with additional flags reach TIER_4."
        ),
        upgrade_path=(
            "Validate against expert panel: are TIER_4 countries truly "
            "non-comparable, or does the boundary exclude recoverable "
            "cases?"
        ),
        falsifiable_by=(
            "If TIER_4 countries produce outputs that experts consider "
            "'usable with heavy caveats,' 3.0 is too strict. If TIER_3 "
            "countries (severity 2.0-2.9) are also considered unusable, "
            "3.0 is too lenient."
        ),
    ),
]


# ---------------------------------------------------------------------------
# GOVERNANCE THRESHOLDS — from backend/governance.py
# ---------------------------------------------------------------------------

GOVERNANCE_THRESHOLD_CALIBRATIONS: list[dict[str, Any]] = [
    # -- Axis confidence baselines --
    _threshold_entry(
        name="AXIS_BASELINE:financial",
        value=0.75,
        module="governance",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "BIS LBS covers ~30 reporting countries with complete bilateral "
            "structure. CPIS adds ~70 participants. Dual-channel baseline of "
            "0.75 reflects: 'good but not perfect' — known gaps include "
            "offshore financial centers and non-reporting developing "
            "countries. The 0.75 is a judgmental assessment of source "
            "completeness, not a measured quantity."
        ),
        sensitivity_note=(
            "±0.05 change shifts all Axis 1 confidence levels by that "
            "amount. At 0.70, more countries drop from HIGH to MODERATE. "
            "At 0.80, fewer penalties push countries below MODERATE."
        ),
        upgrade_path=(
            "Measure: what fraction of a country's actual bilateral "
            "financial exposure is captured by BIS+CPIS? Requires "
            "validation against national balance-of-payments data."
        ),
        falsifiable_by=(
            "If BIS+CPIS coverage demonstrably captures >90% of "
            "bilateral financial flows for reporting countries, 0.75 "
            "is too conservative. If <60%, it's too generous."
        ),
    ),
    _threshold_entry(
        name="AXIS_BASELINE:energy",
        value=0.80,
        module="governance",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "UN Comtrade HS Chapter 27 has broad country coverage and "
            "annual reporting. 0.80 reflects high but imperfect coverage — "
            "known gaps: re-exports, energy transit (gas pipelines), "
            "and LNG swap arrangements not captured in bilateral "
            "merchandise trade."
        ),
        sensitivity_note=(
            "Energy axis is well-covered; ±0.05 has minimal tier impact."
        ),
        upgrade_path=(
            "Cross-validate Comtrade energy with IEA bilateral energy "
            "trade data for overlapping countries."
        ),
        falsifiable_by=(
            "If Comtrade vs IEA bilateral energy data diverge by >15% "
            "for >10 countries, 0.80 is too high."
        ),
    ),
    _threshold_entry(
        name="AXIS_BASELINE:technology",
        value=0.80,
        module="governance",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "Same Comtrade basis as energy, HS 8541/8542. 0.80 reflects "
            "good product coverage but with known HS6 limitation — "
            "semiconductor subcategories collapse at HS6 level."
        ),
        sensitivity_note=(
            "Technology axis is sensitive to granularity penalties. "
            "0.80 baseline - 0.10 granularity penalty = 0.70, which "
            "is still HIGH."
        ),
        upgrade_path=(
            "Compare HS6 vs CN8 semiconductor classification for "
            "EU-27 to measure actual information loss."
        ),
        falsifiable_by=(
            "If HS6 semiconductor classification produces >10% HHI "
            "deviation from CN8 for >25% of countries, 0.80 baseline "
            "should incorporate a standing discount."
        ),
    ),
    _threshold_entry(
        name="AXIS_BASELINE:defense",
        value=0.55,
        module="governance",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "SIPRI TIV covers major conventional arms only — lumpy, "
            "multi-year delivery schedules, excludes small arms, "
            "ammunition, dual-use. 0.55 is the lowest baseline "
            "among trade-based axes, reflecting known narrow scope. "
            "Semi-empirical: SIPRI's own coverage assessment informs "
            "the direction; magnitude is judgmental."
        ),
        sensitivity_note=(
            "Defense axis already has low baseline. Moving to 0.50 "
            "would push more defense results to MODERATE. Moving to "
            "0.60 relaxes it, which may be unjustified given SIPRI's "
            "known coverage limitations."
        ),
        upgrade_path=(
            "Compare SIPRI bilateral arms data to national defense "
            "procurement reports for 5-10 reference countries."
        ),
        falsifiable_by=(
            "If SIPRI captures <40% of actual bilateral arms transfers "
            "for reference countries, 0.55 is too high. If >70%, it's "
            "too low."
        ),
    ),
    _threshold_entry(
        name="AXIS_BASELINE:critical_inputs",
        value=0.75,
        module="governance",
        calibration_class=CalibrationClass.SEMI_EMPIRICAL,
        evidence_basis=(
            "Comtrade HS chapters for critical raw materials. Coverage "
            "is good for traded minerals but misses domestic extraction "
            "and strategic reserves. 0.75 reflects 'same source quality "
            "as financial, applied to trade data.'"
        ),
        sensitivity_note="Similar to energy — well-covered, low sensitivity.",
        upgrade_path=(
            "Cross-validate against EU Critical Raw Materials Act data "
            "or USGS mineral commodity summaries for bilateral flows."
        ),
        falsifiable_by=(
            "If Comtrade mineral data diverges >20% from USGS bilateral "
            "estimates for reference countries, 0.75 is questionable."
        ),
    ),
    _threshold_entry(
        name="AXIS_BASELINE:logistics",
        value=0.60,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Logistics data is the weakest axis: mixed sources, maritime "
            "is strongest (UNCTAD liner shipping), rail and air cargo "
            "are partial. 0.60 is a heuristic reflecting 'structurally "
            "lower coverage than any trade-based axis.' Not calibrated "
            "against actual coverage measurement."
        ),
        sensitivity_note=(
            "Logistics baseline directly affects the LOGISTICS_PROXY_ "
            "CONFIDENCE_CAP interaction. At 0.60, even without "
            "penalties, logistics starts below trade axes."
        ),
        upgrade_path=(
            "Measure: for how many countries does logistics data "
            "cover all three modes (maritime, rail, air)? Weight "
            "baseline by modal coverage fraction."
        ),
        falsifiable_by=(
            "If logistics data actually covers >80% of freight value "
            "for >50% of countries, 0.60 is too conservative. If "
            "maritime dominates and covers <50% of total freight, "
            "0.60 may be too generous for rail/air-dependent countries."
        ),
    ),

    # -- Confidence penalties --
    _threshold_entry(
        name="CONFIDENCE_PENALTY:SINGLE_CHANNEL_A",
        value=0.20,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Confidence penalty for single-channel data (governance "
            "layer). Distinct from severity weight (0.4) — this is "
            "the epistemic confidence reduction, not the construct "
            "narrowing measure. 0.20 is a heuristic chosen to move "
            "most dual-channel baselines one 'step' down (e.g., "
            "0.75 → 0.55 = MODERATE)."
        ),
        sensitivity_note=(
            "±0.05 shifts confidence levels for single-channel "
            "countries. The current 0.20 is large enough to matter "
            "but not so large as to push to LOW."
        ),
        upgrade_path=(
            "Align with severity weight calibration once severity "
            "weights are empirically grounded."
        ),
        falsifiable_by=(
            "If single-channel and dual-channel results are "
            "statistically indistinguishable for most countries, "
            "0.20 is too high."
        ),
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:SINGLE_CHANNEL_B",
        value=0.20,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis="Symmetric with SINGLE_CHANNEL_A.",
        sensitivity_note="Same as SINGLE_CHANNEL_A.",
        upgrade_path="Same as SINGLE_CHANNEL_A.",
        falsifiable_by="Same as SINGLE_CHANNEL_A.",
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:CPIS_NON_PARTICIPANT",
        value=0.25,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "CPIS non-participation eliminates a major bilateral "
            "dimension for Axis 1. Penalty (0.25) is larger than "
            "generic channel loss (0.20) because CPIS specifically "
            "measures portfolio investment — economically significant. "
            "But less than severity weight (0.5) because confidence "
            "and severity operate on different scales."
        ),
        sensitivity_note=(
            "Primarily affects Axis 1 for non-CPIS countries (CN, "
            "many developing countries). ±0.05 shifts Axis 1 from "
            "0.50 to 0.45/0.55."
        ),
        upgrade_path=(
            "Align with CPIS severity weight calibration."
        ),
        falsifiable_by=(
            "If CPIS absence has minimal impact on Axis 1 scores "
            "for countries where both channels are testable, 0.25 "
            "is too high."
        ),
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:REDUCED_PRODUCT_GRANULARITY",
        value=0.10,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Smallest confidence penalty. HS6 vs CN8 has limited "
            "impact on most axes. 0.10 is a 'token acknowledgment' "
            "rather than a major degradation signal."
        ),
        sensitivity_note="Minimal impact. ±0.05 affects almost nothing.",
        upgrade_path="Same as HS6_GRANULARITY severity weight.",
        falsifiable_by="Same as HS6_GRANULARITY severity weight.",
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:TEMPORAL_MISMATCH",
        value=0.15,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Moderate confidence reduction for year mismatch. "
            "0.15 is between the token 0.10 and the substantial "
            "0.20. Heuristic midpoint."
        ),
        sensitivity_note=(
            "Affects countries with temporal alignment issues. "
            "±0.05 moves few confidence levels."
        ),
        upgrade_path=(
            "Same as TEMPORAL_MISMATCH severity weight — calibrate "
            "against year-on-year HHI stability."
        ),
        falsifiable_by=(
            "Same as TEMPORAL_MISMATCH severity weight."
        ),
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:PRODUCER_INVERSION",
        value=0.30,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Largest non-catastrophic confidence penalty. Reflects "
            "that the measured construct is structurally inapplicable "
            "for this axis on this country. 0.30 is normative — it "
            "represents 'significant construct mismatch' in confidence "
            "terms."
        ),
        sensitivity_note=(
            "Moving to 0.20 would keep more inverted axes at MODERATE. "
            "Moving to 0.40 would push most inverted axes to LOW."
        ),
        upgrade_path=(
            "Requires construct-validity evidence — does import "
            "concentration actually capture strategic vulnerability "
            "for exporters?"
        ),
        falsifiable_by=(
            "If producer countries' import concentration rankings "
            "correlate >0.5 with expert vulnerability assessments, "
            "0.30 is too high."
        ),
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:SANCTIONS_DISTORTION",
        value=0.50,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Maximum non-absolute penalty. Sanctions compromise all "
            "bilateral data for the sanctioned country. 0.50 means "
            "'confidence is halved at minimum.' Normative by design."
        ),
        sensitivity_note=(
            "Sanctions-affected countries already hit TIER_4 via "
            "severity. This penalty is redundant but exists for "
            "defense-in-depth."
        ),
        upgrade_path="Same as sanctions severity weight.",
        falsifiable_by="Same as sanctions severity weight.",
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:ZERO_BILATERAL_SUPPLIERS",
        value=0.25,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Zero bilateral suppliers means 'no measured imports,' "
            "not 'low concentration.' Normative penalty reflects "
            "construct ambiguity."
        ),
        sensitivity_note=(
            "Affects axes where partner count = 0. ±0.05 has "
            "limited impact — these axes already have construct "
            "issues."
        ),
        upgrade_path="Normative — no direct calibration path.",
        falsifiable_by=(
            "If zero-supplier axes produce useful comparative "
            "information despite the ambiguity, penalty is too high."
        ),
    ),
    _threshold_entry(
        name="CONFIDENCE_PENALTY:INVALID_AXIS",
        value=1.00,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Axis absent → confidence = 0.0. This is definitional, "
            "not calibrated."
        ),
        sensitivity_note="Not adjustable — axiomatically correct.",
        upgrade_path="None — definitionally correct.",
        falsifiable_by="Not falsifiable — axiom.",
    ),

    # -- Confidence level thresholds --
    _threshold_entry(
        name="CONFIDENCE_LEVEL:HIGH",
        value=0.65,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "HIGH confidence threshold at 0.65 means: baseline "
            "minus at most one minor penalty. Heuristic — chosen to "
            "ensure that 'HIGH' actually requires most of the original "
            "data quality intact. Not calibrated against external "
            "reliability measures."
        ),
        sensitivity_note=(
            "Moving to 0.60 makes HIGH easier to achieve (more "
            "countries get HIGH on more axes). Moving to 0.70 "
            "restricts HIGH to nearly-perfect data."
        ),
        upgrade_path=(
            "Calibrate against output quality: what confidence "
            "score actually correlates with 'reliable for comparison' "
            "as assessed by domain experts?"
        ),
        falsifiable_by=(
            "If countries with confidence 0.60 and 0.70 have "
            "indistinguishable output quality, the 0.65 boundary "
            "is arbitrary."
        ),
    ),
    _threshold_entry(
        name="CONFIDENCE_LEVEL:MODERATE",
        value=0.45,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "MODERATE threshold at 0.45. Countries with one major "
            "penalty or two minor penalties land here. Heuristic — "
            "midpoint between 'clearly fine' and 'clearly problematic.'"
        ),
        sensitivity_note=(
            "This threshold directly drives ranking eligibility "
            "(MIN_MEAN_CONFIDENCE_FOR_RANKING = 0.45). ±0.05 change "
            "affects which countries can be ranked."
        ),
        upgrade_path="Same as HIGH threshold.",
        falsifiable_by="Same as HIGH threshold.",
    ),
    _threshold_entry(
        name="CONFIDENCE_LEVEL:LOW",
        value=0.25,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "LOW threshold at 0.25. Multiple severe penalties required. "
            "Below 0.25 = MINIMAL. Heuristic — chosen to create a "
            "meaningful gap between 'unreliable' and 'absent.'"
        ),
        sensitivity_note=(
            "Moving to 0.20 narrows the MINIMAL band. Moving to "
            "0.30 expands it, pushing more degraded axes to MINIMAL."
        ),
        upgrade_path="Same as HIGH threshold.",
        falsifiable_by="Same as HIGH threshold.",
    ),

    # -- Composite eligibility thresholds --
    _threshold_entry(
        name="COMPOSITE:MIN_AXES",
        value=4,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Minimum 4 of 6 axes for composite computation. This is "
            "a normative design choice: a composite from fewer than "
            "4 axes covers <67% of the ISI construct and is considered "
            "structurally incomplete."
        ),
        sensitivity_note=(
            "Moving to 3 allows very sparse composites. Moving to "
            "5 excludes many non-EU countries."
        ),
        upgrade_path=(
            "Normative — but could be validated by measuring "
            "composite stability under axis removal."
        ),
        falsifiable_by=(
            "If leave-one-out analysis shows composites are stable "
            "with 3 axes, 4 is unnecessarily strict. If unstable "
            "with 4, the minimum should be higher."
        ),
    ),
    _threshold_entry(
        name="COMPOSITE:MIN_AXES_RANKING",
        value=5,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "Minimum 5 axes for ranking eligibility. Stricter than "
            "composite computation (4) because ranking implies "
            "pairwise comparability, which requires broader "
            "construct coverage."
        ),
        sensitivity_note=(
            "Moving to 4 allows more countries into rankings but "
            "reduces construct coverage guarantee. Moving to 6 "
            "requires ALL axes, which excludes many non-EU countries."
        ),
        upgrade_path="Same as MIN_AXES — leave-one-out stability analysis.",
        falsifiable_by=(
            "If rankings are stable between 4-axis and 5-axis "
            "composites, 5 is unnecessarily strict."
        ),
    ),
    _threshold_entry(
        name="COMPOSITE:MIN_MEAN_CONFIDENCE_RANKING",
        value=0.45,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Same value as MODERATE confidence threshold. Heuristic "
            "rationale: ranking requires at least 'moderate' overall "
            "data quality. Coincidence with MODERATE threshold is "
            "intentional but not empirically necessary."
        ),
        sensitivity_note=(
            "Moving to 0.40 admits more countries to rankings. "
            "Moving to 0.50 excludes countries with mixed "
            "confidence profiles."
        ),
        upgrade_path=(
            "Calibrate by measuring rank stability at different "
            "mean-confidence cutoffs."
        ),
        falsifiable_by=(
            "If countries with mean confidence 0.40 and 0.50 have "
            "indistinguishable rank stability, 0.45 is arbitrary."
        ),
    ),
    _threshold_entry(
        name="COMPOSITE:MAX_LOW_CONFIDENCE_AXES_RANKING",
        value=2,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Maximum 2 LOW/MINIMAL axes before ranking exclusion. "
            "Heuristic: if >1/3 of axes are unreliable, the composite "
            "is structurally fragile for ranking. Chosen because "
            "2/6 = 33%, which is a conventional 'third' breakpoint."
        ),
        sensitivity_note=(
            "Moving to 1 is very strict (many EU countries have 1 "
            "low axis). Moving to 3 allows half-degraded composites "
            "into rankings."
        ),
        upgrade_path=(
            "Measure rank volatility as a function of how many "
            "low-confidence axes are present."
        ),
        falsifiable_by=(
            "If rankings are stable even with 3 low-confidence "
            "axes, 2 is too strict."
        ),
    ),
    _threshold_entry(
        name="COMPOSITE:MAX_INVERTED_COMPARABLE",
        value=2,
        module="governance",
        calibration_class=CalibrationClass.STRUCTURAL_NORMATIVE,
        evidence_basis=(
            "At 2 inverted axes, 33% of the ISI construct is "
            "measuring the wrong thing. Beyond 2 (→ NON_COMPARABLE "
            "at 3), the country's ISI is fundamentally a different "
            "construct than a pure importer's ISI. Normative choice."
        ),
        sensitivity_note=(
            "Moving to 1 makes all inverted-axis countries "
            "NON_COMPARABLE. Moving to 3 allows heavily inverted "
            "countries (like US with 3) into LOW_CONFIDENCE."
        ),
        upgrade_path="Normative — no direct calibration path.",
        falsifiable_by=(
            "If 2-inverted-axis countries rank 'correctly' against "
            "expert assessments, the threshold is too restrictive."
        ),
    ),
    _threshold_entry(
        name="COMPOSITE:DEFENSIBILITY_FLOOR",
        value=0.30,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Mean confidence below 0.30 → composite not defensible. "
            "Heuristic: 0.30 is below LOW threshold, meaning most "
            "axes are in MINIMAL territory. A composite of mostly-"
            "MINIMAL axes is not publishable."
        ),
        sensitivity_note=(
            "Moving to 0.25 aligns with LOW threshold. Moving to "
            "0.35 is stricter. Current value is between LOW and "
            "MODERATE."
        ),
        upgrade_path=(
            "Calibrate against expert judgment of composite "
            "publication suitability."
        ),
        falsifiable_by=(
            "If composites with mean confidence 0.25-0.35 are "
            "considered useful by domain experts, 0.30 needs "
            "adjustment."
        ),
    ),

    # -- Logistics-specific --
    _threshold_entry(
        name="LOGISTICS:PROXY_CONFIDENCE_CAP",
        value=0.40,
        module="governance",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Proxy logistics data is capped at 0.40 confidence "
            "regardless of other factors. 0.40 is at the boundary "
            "of MODERATE/LOW. Heuristic: proxy data should never "
            "achieve MODERATE confidence or above."
        ),
        sensitivity_note=(
            "Moving to 0.30 pushes all proxy logistics to LOW. "
            "Moving to 0.50 allows proxy to reach MODERATE."
        ),
        upgrade_path=(
            "Validate by comparing proxy logistics data to primary "
            "logistics data for countries where both exist."
        ),
        falsifiable_by=(
            "If proxy logistics data tracks primary data with "
            "correlation >0.8, 0.40 is too conservative. If <0.5, "
            "0.40 is too generous."
        ),
    ),

    # -- Cross-country severity thresholds --
    _threshold_entry(
        name="CROSS_COUNTRY:DIFF_THRESHOLD",
        value=1.5,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Country pair is non-comparable if severity difference "
            ">1.5. This equals one full tier gap (TIER_1→TIER_2). "
            "Heuristic: comparing a TIER_1 country to a TIER_3 "
            "country is meaningless."
        ),
        sensitivity_note=(
            "Moving to 1.0 is very strict (many pairs become "
            "non-comparable). Moving to 2.0 permits comparing "
            "across two tier boundaries."
        ),
        upgrade_path=(
            "Calibrate against rank stability: at what severity "
            "difference do rankings become unreliable?"
        ),
        falsifiable_by=(
            "If rankings are stable even for severity differences "
            "of 2.0, 1.5 is too strict."
        ),
    ),
    _threshold_entry(
        name="CROSS_COUNTRY:RATIO_THRESHOLD",
        value=3.0,
        module="severity",
        calibration_class=CalibrationClass.HEURISTIC,
        evidence_basis=(
            "Country pair is non-comparable if severity ratio >3.0. "
            "Catches cases like 0.1 vs 0.5 (ratio=5.0, diff=0.4). "
            "Heuristic: 3x severity ratio means fundamentally "
            "different data quality regimes."
        ),
        sensitivity_note=(
            "Moving to 2.0 catches more pairs. Moving to 5.0 "
            "only flags extreme asymmetry."
        ),
        upgrade_path=(
            "Same as DIFF_THRESHOLD — calibrate against rank stability."
        ),
        falsifiable_by=(
            "Same as DIFF_THRESHOLD."
        ),
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# COMPLETE THRESHOLD REGISTRY — Flat list for queries/audits
# ═══════════════════════════════════════════════════════════════════════════

THRESHOLD_REGISTRY: list[dict[str, Any]] = (
    SEVERITY_WEIGHT_CALIBRATIONS
    + SEVERITY_TIER_CALIBRATIONS
    + GOVERNANCE_THRESHOLD_CALIBRATIONS
)


def get_threshold_registry() -> list[dict[str, Any]]:
    """Return the complete threshold calibration registry."""
    return list(THRESHOLD_REGISTRY)


def get_thresholds_by_class(
    calibration_class: str,
) -> list[dict[str, Any]]:
    """Filter thresholds by calibration class."""
    return [
        t for t in THRESHOLD_REGISTRY
        if t["calibration_class"] == calibration_class
    ]


def get_thresholds_by_module(module: str) -> list[dict[str, Any]]:
    """Filter thresholds by originating module."""
    return [t for t in THRESHOLD_REGISTRY if t["module"] == module]


def get_calibration_summary() -> dict[str, Any]:
    """Return summary statistics of calibration classes across all thresholds."""
    counts: dict[str, int] = {}
    for t in THRESHOLD_REGISTRY:
        cls = t["calibration_class"]
        counts[cls] = counts.get(cls, 0) + 1
    total = len(THRESHOLD_REGISTRY)
    return {
        "total_thresholds": total,
        "by_class": counts,
        "by_class_pct": {
            k: round(v / total * 100, 1) if total > 0 else 0.0
            for k, v in counts.items()
        },
        "honesty_note": (
            f"Of {total} thresholds: "
            f"{counts.get('EMPIRICAL', 0)} are empirically calibrated, "
            f"{counts.get('SEMI_EMPIRICAL', 0)} are semi-empirical "
            f"(data-informed but with judgmental component), "
            f"{counts.get('HEURISTIC', 0)} are heuristic "
            f"(expert judgment, not directly data-calibrated), "
            f"{counts.get('STRUCTURAL_NORMATIVE', 0)} are structural/"
            f"normative design choices. This system does not pretend "
            f"its thresholds are more rigorous than they are."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# TASK 3: FALSIFIABILITY FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════
# Every governance mechanism has explicit falsification criteria.

FALSIFIABILITY_REGISTRY: list[dict[str, Any]] = [
    {
        "mechanism": "Producer-Inversion Registry",
        "module": "governance",
        "description": (
            "Countries registered as having structurally inverted ISI "
            "interpretation on specific axes."
        ),
        "support_evidence": [
            "Country's net export position on the relevant commodity "
            "is positive and substantial (>20% of global market).",
            "Import concentration HHI is mechanically low (<0.1) "
            "for the inverted axes.",
            "Domain literature identifies the country as a major "
            "exporter in the relevant sector.",
        ],
        "weaken_evidence": [
            "Country's export dominance is declining (net export "
            "share falling below 10% of global market).",
            "Country becomes a net importer in a previously "
            "export-dominant sector.",
            "Import concentration on the inverted axis is actually "
            "high (>0.3), suggesting real dependency despite "
            "export position.",
        ],
        "falsify_evidence": [
            "Expert panel assessment shows the country IS strategically "
            "vulnerable despite being a major exporter.",
            "Historical crisis demonstrates that export dominance "
            "did not protect the country from supply disruption on "
            "the flagged axis.",
            "Net export position reverses to net import for the "
            "majority of inverted axes.",
        ],
        "current_status": "ACTIVE — based on SIPRI and Comtrade export "
                          "position data. Registry is static; should be "
                          "reviewed annually.",
    },
    {
        "mechanism": "Governance Tier Ordering Rules",
        "module": "governance",
        "description": (
            "14 ordered rules that map country characteristics to "
            "governance tiers. First match wins."
        ),
        "support_evidence": [
            "Output quality (as measured by rank stability, expert "
            "agreement, or prediction accuracy) degrades monotonically "
            "across tiers: FULLY > PARTIALLY > LOW > NON.",
            "Tier boundaries align with meaningful breaks in output "
            "reliability.",
            "Rule ordering produces face-valid classifications for "
            "well-understood reference countries.",
        ],
        "weaken_evidence": [
            "PARTIALLY_COMPARABLE countries have similar output quality "
            "to FULLY_COMPARABLE (tier distinction is cosmetic).",
            "LOW_CONFIDENCE countries occasionally produce more stable "
            "rankings than PARTIALLY_COMPARABLE countries.",
            "Rule ordering produces counter-intuitive classifications "
            "for >3 reference countries.",
        ],
        "falsify_evidence": [
            "Systematic comparison shows no correlation between "
            "governance tier and output quality/stability.",
            "Expert panel consistently disagrees with tier assignments.",
            "Tier system fails to predict which country outputs "
            "change most under data updates.",
        ],
        "current_status": "ACTIVE — rules are heuristically ordered by "
                          "severity. No empirical validation of ordering.",
    },
    {
        "mechanism": "Axis Confidence Baseline + Penalty Model",
        "module": "governance",
        "description": (
            "Per-axis confidence = baseline - sum(applicable penalties). "
            "Additive penalty model with per-flag deductions."
        ),
        "support_evidence": [
            "Baselines reflect known source coverage (BIS ~30 reporting "
            "countries, Comtrade broad, SIPRI limited).",
            "Penalties are monotonic: more data quality issues → lower "
            "confidence.",
            "Resulting confidence levels are face-valid for reference "
            "countries.",
        ],
        "weaken_evidence": [
            "Penalties are additive but underlying issues may interact "
            "non-linearly (e.g., CPIS absence + single channel = double "
            "counting).",
            "Baselines do not account for country-specific source "
            "coverage (BIS covers 30 reporters, but coverage varies).",
            "Degradation-group MAX rule in severity is not replicated "
            "in confidence (penalties sum instead of MAX).",
        ],
        "falsify_evidence": [
            "If confidence scores show no correlation with actual output "
            "reliability (measured by rank stability or expert agreement), "
            "the model is uninformative.",
            "If the additive penalty model produces systematically wrong "
            "confidence orderings (e.g., a clearly-worse axis gets higher "
            "confidence), the model structure is flawed.",
        ],
        "current_status": "ACTIVE — penalty values are heuristic. The additive "
                          "structure differs from severity's group-MAX model, which "
                          "is a known inconsistency (see circularity audit).",
    },
    {
        "mechanism": "Logistics Structural Limitation",
        "module": "governance",
        "description": (
            "Missing or proxy logistics caps governance tier at "
            "PARTIALLY_COMPARABLE and confidence at 0.40."
        ),
        "support_evidence": [
            "Logistics data has demonstrably lower coverage than "
            "trade-based axes (fewer countries, fewer modes).",
            "Countries without logistics data are missing a genuine "
            "dimension of supply-chain vulnerability.",
        ],
        "weaken_evidence": [
            "Logistics may be a small component of overall ISI "
            "variation — if composite rankings are insensitive to "
            "logistics scores, the cap is disproportionate.",
            "Maritime data alone may capture >80% of freight for "
            "island/coastal nations, making 'partial coverage' "
            "adequate for those countries.",
        ],
        "falsify_evidence": [
            "If removing Axis 6 from all countries produces rank "
            "orderings that are >0.95 correlated with 6-axis "
            "rankings, logistics is not influential enough to "
            "justify its governance impact.",
        ],
        "current_status": "ACTIVE — structurally sound, but quantitative "
                          "impact on rankings is not measured.",
    },
    {
        "mechanism": "Composite Eligibility Rules",
        "module": "governance",
        "description": (
            "Minimum axes (4 for computation, 5 for ranking), "
            "mean confidence floor, low-axis count cap."
        ),
        "support_evidence": [
            "Composites from fewer axes have higher rank volatility "
            "under leave-one-out tests (expected by construction).",
            "Mean confidence floor ensures minimum data quality "
            "across the composite.",
        ],
        "weaken_evidence": [
            "The specific thresholds (4, 5, 0.45, 2) are not "
            "calibrated against measured rank stability — they are "
            "round-number heuristics.",
            "Countries with exactly 4 or 5 axes may fall on either "
            "side of the boundary by accident of data availability, "
            "not by methodological significance.",
        ],
        "falsify_evidence": [
            "If rank stability analysis shows no meaningful difference "
            "between 3-axis and 5-axis composites, the thresholds are "
            "protective theater.",
            "If sensitivity analysis shows thresholds are not at "
            "natural breakpoints in the data, they are arbitrary.",
        ],
        "current_status": "ACTIVE — thresholds are heuristic. Sensitivity "
                          "analysis (TASK 8) is designed to test this.",
    },
    {
        "mechanism": "Truthfulness Contract Enforcement",
        "module": "governance",
        "description": (
            "Required fields and consistency checks that must be "
            "satisfied before any export."
        ),
        "support_evidence": [
            "Contract prevents logically inconsistent outputs "
            "(e.g., NON_COMPARABLE with a rank).",
            "Required fields ensure every output carries "
            "self-disclosure about its limitations.",
        ],
        "weaken_evidence": [
            "Contract checks structural consistency, not semantic "
            "truthfulness — an output can pass the contract while "
            "being methodologically misleading.",
        ],
        "falsify_evidence": [
            "If an output passes the truthfulness contract but a "
            "competent reader finds it misleading based on the "
            "disclosed metadata, the contract has gaps.",
        ],
        "current_status": "ACTIVE — structurally sound within its scope. "
                          "Does not catch all possible misleading outputs.",
    },
]


def get_falsifiability_registry() -> list[dict[str, Any]]:
    """Return the complete falsifiability registry."""
    return list(FALSIFIABILITY_REGISTRY)


# ═══════════════════════════════════════════════════════════════════════════
# TASK 4: CIRCULARITY AUDIT
# ═══════════════════════════════════════════════════════════════════════════
# Documents the data flow and identifies circular dependencies.

CIRCULARITY_AUDIT: dict[str, Any] = {
    "flow_description": (
        "data sources → pipeline/ingestion → pipeline/validation → "
        "backend/axis_result (AxisResult) → backend/severity (per-axis "
        "severity) → backend/severity (country severity + tier) → "
        "backend/governance (axis confidence + country governance) → "
        "backend/export_snapshot (gated export)"
    ),
    "data_flow_nodes": [
        {
            "stage": "1. Data Ingestion",
            "module": "pipeline/",
            "inputs": "Raw data files (Comtrade, BIS, SIPRI, etc.)",
            "outputs": "Validated bilateral records + data_quality_flags",
            "depends_on_governance": False,
        },
        {
            "stage": "2. Axis Computation",
            "module": "backend/axis_result.py",
            "inputs": "Bilateral records + data_quality_flags",
            "outputs": "AxisResult objects (HHI scores, flags, validity)",
            "depends_on_governance": False,
        },
        {
            "stage": "3. Severity Assessment",
            "module": "backend/severity.py",
            "inputs": "AxisResult.to_dict() (flags, severity per axis)",
            "outputs": "total_severity, comparability_tier",
            "depends_on_governance": False,
        },
        {
            "stage": "4. Governance Assessment",
            "module": "backend/governance.py",
            "inputs": (
                "axis_results (from stage 2), severity_total + "
                "comparability_tier (from stage 3)"
            ),
            "outputs": (
                "governance_tier, axis_confidences, ranking_eligible, "
                "composite_defensible, cross_country_comparable"
            ),
            "depends_on_governance": False,
            "note": (
                "Governance CONSUMES severity outputs but does not "
                "feed back into severity. This is the critical non-"
                "circularity property."
            ),
        },
        {
            "stage": "5. Export Gating",
            "module": "backend/export_snapshot.py",
            "inputs": "Country results + governance (from stage 4)",
            "outputs": "Gated JSON exports",
            "depends_on_governance": True,
            "note": (
                "Export depends on governance but does not feed back "
                "into computation. The chain is strictly linear."
            ),
        },
    ],
    "circularity_status": "NO_CIRCULARITY",
    "circularity_analysis": (
        "The data flow is strictly linear: ingestion → computation → "
        "severity → governance → export. No downstream stage feeds back "
        "into an upstream stage. Governance does NOT modify scores — it "
        "only governs interpretation, ranking eligibility, and export "
        "permission. The severity model does NOT depend on governance "
        "outputs. This is by design."
    ),
    "known_tension": (
        "CONFIDENCE PENALTIES vs SEVERITY WEIGHTS: The governance module "
        "uses an additive penalty model for axis confidence, while the "
        "severity module uses a degradation-group MAX model. These are "
        "measuring related but distinct quantities (epistemic confidence "
        "vs construct narrowing). The architectural separation is "
        "intentional — confidence and severity are NOT the same thing — "
        "but the use of different aggregation rules (additive vs group-"
        "MAX) for similar flag sets is a design tension that should be "
        "explicitly acknowledged."
    ),
    "defense": (
        "The additive confidence model was chosen because confidence "
        "penalties are smaller and more granular than severity weights. "
        "Multiple independent quality issues DO compound for confidence "
        "(two minor problems are worse than one), while severity uses "
        "group-MAX to prevent double-counting of the SAME underlying "
        "problem. This is a defensible but debatable design choice."
    ),
}


def get_circularity_audit() -> dict[str, Any]:
    """Return the circularity audit documentation."""
    return dict(CIRCULARITY_AUDIT)


# ═══════════════════════════════════════════════════════════════════════════
# TASK 5: PER-AXIS CALIBRATION NOTES
# ═══════════════════════════════════════════════════════════════════════════

AXIS_CALIBRATION_NOTES: dict[int, dict[str, Any]] = {
    1: {
        "axis_name": "Financial (BIS LBS + CPIS)",
        "baseline": 0.75,
        "baseline_class": CalibrationClass.SEMI_EMPIRICAL,
        "source_coverage": (
            "BIS LBS: ~30 reporting countries (banking claims). "
            "CPIS: ~70 participating economies (portfolio investment). "
            "Dual-channel when both available."
        ),
        "known_gaps": [
            "Offshore financial centers may be underrepresented in BIS",
            "Non-CPIS countries (incl. China) lose portfolio dimension",
            "Banking claims may not capture shadow banking or fintech flows",
        ],
        "construct_validity": (
            "HHI on bilateral financial claims measures banking+portfolio "
            "concentration. VALID for measuring bilateral financial "
            "exposure concentration. DOES NOT measure total financial "
            "vulnerability (misses domestic financial system resilience, "
            "FDI, currency exposure)."
        ),
        "sensitivity_to_penalties": (
            "CPIS_NON_PARTICIPANT (-0.25) is the most impactful penalty. "
            "For non-CPIS countries, confidence drops to 0.50 (MODERATE), "
            "meaning the financial axis is measuring only half the "
            "intended construct."
        ),
        "falsifiable_claim": (
            "CLAIM: BIS+CPIS dual-channel captures >60% of bilateral "
            "financial exposure for reporting countries. "
            "FALSIFIABLE BY: comparing BIS+CPIS bilateral totals against "
            "national balance-of-payments bilateral breakdowns."
        ),
    },
    2: {
        "axis_name": "Energy (Comtrade HS27)",
        "baseline": 0.80,
        "baseline_class": CalibrationClass.SEMI_EMPIRICAL,
        "source_coverage": (
            "UN Comtrade HS Chapter 27 (mineral fuels). Annual reporting "
            "for most countries. Broad product coverage within chapter."
        ),
        "known_gaps": [
            "Re-exports and transit trade (esp. gas pipelines via hub countries)",
            "LNG swap arrangements not captured in bilateral trade stats",
            "Electricity trade (not merchandise) is excluded",
        ],
        "construct_validity": (
            "HHI on bilateral energy imports measures energy import "
            "source concentration. VALID for fossil fuel import "
            "dependency. DOES NOT capture energy mix, domestic "
            "production, renewables, or strategic reserves."
        ),
        "sensitivity_to_penalties": (
            "PRODUCER_INVERSION (-0.30) is the most impactful penalty "
            "for energy exporters (US, NO, AU, SA, RU). For these "
            "countries, the axis is measuring the wrong construct."
        ),
        "falsifiable_claim": (
            "CLAIM: Comtrade HS27 captures >75% of bilateral energy "
            "trade value for non-transit countries. "
            "FALSIFIABLE BY: comparing Comtrade with IEA bilateral "
            "energy trade statistics."
        ),
    },
    3: {
        "axis_name": "Technology/Semiconductor (Comtrade HS8541/8542)",
        "baseline": 0.80,
        "baseline_class": CalibrationClass.SEMI_EMPIRICAL,
        "source_coverage": (
            "UN Comtrade HS 8541 (diodes/transistors/semiconductors) "
            "and 8542 (electronic integrated circuits). Good product "
            "coverage at HS6; CN8 provides better subcategory detail."
        ),
        "known_gaps": [
            "HS6 collapses ~7 semiconductor subcategories to ~3",
            "Does not capture semiconductor equipment or EDA tools",
            "Re-exports via hubs (Singapore, Netherlands) inflate bilateral",
            "Design vs fabrication distinction not captured",
        ],
        "construct_validity": (
            "HHI on bilateral semiconductor imports measures chip "
            "import source concentration. VALID for measuring physical "
            "chip supply dependency. DOES NOT capture technology "
            "dependency, IP licensing, or foundry access."
        ),
        "sensitivity_to_penalties": (
            "REDUCED_PRODUCT_GRANULARITY (-0.10) is the typical "
            "penalty when HS6 is used instead of CN8. Minor impact. "
            "The bigger risk is re-export distortion, which is not "
            "currently penalized."
        ),
        "falsifiable_claim": (
            "CLAIM: HS6 semiconductor classification captures the "
            "same supplier concentration structure as CN8 for >75% "
            "of countries. "
            "FALSIFIABLE BY: comparing HS6 vs CN8 HHI scores for "
            "EU-27 countries where both are available."
        ),
    },
    4: {
        "axis_name": "Defense (SIPRI TIV)",
        "baseline": 0.55,
        "baseline_class": CalibrationClass.SEMI_EMPIRICAL,
        "source_coverage": (
            "SIPRI Arms Transfers Database. Covers major conventional "
            "weapons using Trend Indicator Values (TIV). Annual "
            "updates. Good country coverage for major transfers."
        ),
        "known_gaps": [
            "Only major conventional weapons — excludes small arms, ammunition",
            "TIV is not monetary value — it measures military capability transferred",
            "Lumpy delivery schedules create year-on-year volatility",
            "Dual-use items not captured",
            "Licensed production (esp. EU) partially captured",
        ],
        "construct_validity": (
            "HHI on bilateral arms imports (TIV) measures major weapons "
            "supplier concentration. VALID for measuring dependence on "
            "foreign arms suppliers for major platforms. DOES NOT capture "
            "domestic defense industrial capacity, ammunition supply, or "
            "technology transfer."
        ),
        "sensitivity_to_penalties": (
            "PRODUCER_INVERSION (-0.30) is critical for major exporters "
            "(US, FR, DE, CN, RU). These countries export arms, so their "
            "import concentration is structurally uninformative. "
            "TEMPORAL_MISMATCH (-0.15) is common due to SIPRI's multi-year "
            "delivery reporting."
        ),
        "falsifiable_claim": (
            "CLAIM: SIPRI TIV captures >50% of actual bilateral arms "
            "transfer value for major importing countries. "
            "FALSIFIABLE BY: comparing SIPRI bilateral data to national "
            "defense procurement transparency reports for reference "
            "countries (SE, AU, JP)."
        ),
    },
    5: {
        "axis_name": "Critical Inputs / Raw Materials (Comtrade)",
        "baseline": 0.75,
        "baseline_class": CalibrationClass.SEMI_EMPIRICAL,
        "source_coverage": (
            "UN Comtrade HS chapters for critical raw materials "
            "(rare earths, lithium, cobalt, etc.). Product codes "
            "aligned with EU Critical Raw Materials Act list."
        ),
        "known_gaps": [
            "Domestic extraction and recycling not captured",
            "Strategic stockpiles not reflected in trade data",
            "Processing stage matters (ore vs refined) — trade data may mix stages",
            "China's dominance in processing may be understated in import data",
        ],
        "construct_validity": (
            "HHI on bilateral critical mineral imports measures raw "
            "material import source concentration. VALID for measuring "
            "import dependency for critical inputs. DOES NOT capture "
            "processing dependency, domestic alternatives, or "
            "substitution potential."
        ),
        "sensitivity_to_penalties": (
            "PRODUCER_INVERSION (-0.30) affects major mineral exporters "
            "(AU, CN, US). ZERO_BILATERAL_SUPPLIERS (-0.25) may appear "
            "for countries with minimal mineral imports."
        ),
        "falsifiable_claim": (
            "CLAIM: Comtrade mineral trade data captures >70% of "
            "bilateral critical input flows for major importing "
            "countries. "
            "FALSIFIABLE BY: comparing Comtrade with USGS mineral "
            "commodity summaries or EU CRM supply studies."
        ),
    },
    6: {
        "axis_name": "Logistics / Freight (Mixed Sources)",
        "baseline": 0.60,
        "baseline_class": CalibrationClass.HEURISTIC,
        "source_coverage": (
            "Mixed sources: UNCTAD liner shipping connectivity, "
            "trade-weighted logistics proxies. Maritime data is "
            "strongest; rail and air cargo are partial or proxied."
        ),
        "known_gaps": [
            "Rail freight bilateral data is sparse for most countries",
            "Air cargo bilateral structure is poorly measured",
            "Port-to-port ≠ origin-to-destination for containerized goods",
            "Many developing countries have no bilateral logistics data",
            "Landlocked countries require transit data which is incomplete",
        ],
        "construct_validity": (
            "HHI on bilateral logistics flows measures freight "
            "route concentration. PARTIALLY VALID — captures "
            "maritime dependency well, but incomplete for multimodal "
            "and landlocked-country logistics. The construct is "
            "weaker than trade-based axes."
        ),
        "sensitivity_to_penalties": (
            "PROXY_DATA_CAP (0.40) is the dominant control. Any "
            "proxy logistics data is capped at LOW/MODERATE boundary. "
            "The baseline (0.60) is already the lowest, so even "
            "without penalties, logistics starts behind other axes."
        ),
        "falsifiable_claim": (
            "CLAIM: Maritime-based logistics data captures >60% of "
            "bilateral freight concentration for coastal countries. "
            "FALSIFIABLE BY: comparing UNCTAD maritime connectivity "
            "with comprehensive freight statistics from national "
            "transport agencies."
        ),
    },
}


def get_axis_calibration_notes() -> dict[int, dict[str, Any]]:
    """Return per-axis calibration notes."""
    return dict(AXIS_CALIBRATION_NOTES)


# ═══════════════════════════════════════════════════════════════════════════
# TASK 6 + 7: COUNTRY ELIGIBILITY REGISTRY
# ═══════════════════════════════════════════════════════════════════════════
# ⚠️ SUPPLEMENTARY METADATA ONLY — NOT authoritative for eligibility.
#
# AUTHORITY UNIFICATION (LAYER 4):
#
#   The SINGLE authoritative eligibility system is backend/eligibility.py.
#   That module defines:
#   - TheoreticalEligibility (6-level classification)
#   - DecisionUsabilityClass (4-level structural decision classification)
#   - EmpiricalAlignmentClass (5-level empirical grounding dimension)
#   - PolicyUsabilityClass (6-level combined policy usability)
#
#   This module retains:
#   - EligibilityClass: backward-compatible 4-level classification for
#     hand-curated country metadata (data_strengths, data_weaknesses, etc.)
#   - COUNTRY_ELIGIBILITY_REGISTRY: supplementary metadata per country
#     (rationale, data architecture notes, upgrade conditions)
#   - Query functions: backward-compatible API surface
#
#   This module does NOT determine eligibility. It provides supplementary
#   metadata. For authoritative eligibility determination, use:
#     backend.eligibility.classify_country()
#     backend.eligibility.classify_decision_usability()
#     backend.eligibility.classify_policy_usability()
#
#   See: docs/AUTHORITY_UNIFICATION.md for the full design rationale.
# ═══════════════════════════════════════════════════════════════════════════

class EligibilityClass:
    """Country eligibility classifications (supplementary metadata level).

    NOTE: This is the calibration module's METADATA classification.
    The AUTHORITATIVE eligibility system is in backend/eligibility.py
    (TheoreticalEligibility + DecisionUsabilityClass).

    This classification is retained for backward compatibility and
    hand-curated per-country notes. It should be consistent with
    but subordinate to eligibility.py's classifications.
    """
    CONFIDENTLY_RATEABLE = "CONFIDENTLY_RATEABLE"
    RATEABLE_WITH_CAVEATS = "RATEABLE_WITH_CAVEATS"
    PARTIALLY_RATEABLE = "PARTIALLY_RATEABLE"
    NOT_CURRENTLY_RATEABLE = "NOT_CURRENTLY_RATEABLE"


VALID_ELIGIBILITY_CLASSES = frozenset({
    EligibilityClass.CONFIDENTLY_RATEABLE,
    EligibilityClass.RATEABLE_WITH_CAVEATS,
    EligibilityClass.PARTIALLY_RATEABLE,
    EligibilityClass.NOT_CURRENTLY_RATEABLE,
})


def _eligibility_entry(
    *,
    country: str,
    name: str,
    eligibility_class: str,
    expected_governance_tier: str,
    rationale: str,
    data_strengths: list[str],
    data_weaknesses: list[str],
    axes_at_risk: list[int],
    upgrade_conditions: str,
) -> dict[str, Any]:
    """Create a validated country eligibility entry."""
    assert eligibility_class in VALID_ELIGIBILITY_CLASSES, (
        f"Invalid eligibility_class '{eligibility_class}' for {country}"
    )
    return {
        "country": country,
        "name": name,
        "eligibility_class": eligibility_class,
        "expected_governance_tier": expected_governance_tier,
        "rationale": rationale,
        "data_strengths": data_strengths,
        "data_weaknesses": data_weaknesses,
        "axes_at_risk": axes_at_risk,
        "upgrade_conditions": upgrade_conditions,
    }


# ---------------------------------------------------------------------------
# EU-27 — Generally well-covered
# ---------------------------------------------------------------------------
# EU-27 countries have Comtrade (Eurostat mirror), BIS (most are reporters),
# CPIS (most participate), and relatively good logistics coverage.

_EU27_CORE_STRENGTHS = [
    "Eurostat/Comtrade trade data: comprehensive bilateral coverage",
    "BIS LBS reporting country (banking claims)",
    "CPIS participant (portfolio investment)",
    "CN8 product granularity available for intra-EU trade",
]

_EU27_COMMON_WEAKNESSES = [
    "Logistics axis may use proxy data for smaller member states",
    "Intra-EU re-exports may inflate apparent bilateral diversity",
    "Defense axis (SIPRI TIV) may be lumpy for smaller importers",
]

# Large EU members: DE, FR, IT, ES, NL, PL — all CONFIDENTLY_RATEABLE
# Medium EU members: AT, BE, CZ, DK, FI, GR, HU, IE, PT, RO, SE, SK
# Small EU members: BG, CY, EE, HR, LT, LU, LV, MT, SI

_EU27_LARGE = ["DE", "FR", "IT", "ES", "NL", "PL"]
_EU27_MEDIUM = ["AT", "BE", "CZ", "DK", "FI", "EL", "HU", "IE", "PT", "RO", "SE", "SK"]
_EU27_SMALL = ["BG", "CY", "EE", "HR", "LT", "LU", "LV", "MT", "SI"]

_EU27_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "EE": "Estonia", "EL": "Greece",
    "ES": "Spain", "FI": "Finland", "FR": "France",
    "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
    "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia",
}

COUNTRY_ELIGIBILITY_REGISTRY: list[dict[str, Any]] = []

# Generate EU-27 large member entries
for _code in _EU27_LARGE:
    _extra_weakness: list[str] = list(_EU27_COMMON_WEAKNESSES)
    _axes_risk: list[int] = [6]  # Logistics is always a risk
    if _code == "FR":
        _extra_weakness.append("Defense axis: FR is a major arms exporter (producer inversion on Axis 4)")
        _axes_risk.append(4)
    if _code == "DE":
        _extra_weakness.append("Defense axis: DE is a major arms exporter (producer inversion on Axis 4)")
        _axes_risk.append(4)
    if _code == "NL":
        _extra_weakness.append("Semiconductor re-exports via NL may inflate technology axis bilateral diversity")

    COUNTRY_ELIGIBILITY_REGISTRY.append(_eligibility_entry(
        country=_code,
        name=_EU27_NAMES[_code],
        eligibility_class=(
            EligibilityClass.RATEABLE_WITH_CAVEATS
            if _code in ("FR", "DE")
            else EligibilityClass.CONFIDENTLY_RATEABLE
        ),
        expected_governance_tier=(
            "PARTIALLY_COMPARABLE" if _code in ("FR", "DE")
            else "FULLY_COMPARABLE"
        ),
        rationale=(
            f"{_EU27_NAMES[_code]}: large EU member with comprehensive data coverage "
            f"across all axes."
            + (" Producer inversion on defense axis." if _code in ("FR", "DE") else "")
        ),
        data_strengths=list(_EU27_CORE_STRENGTHS),
        data_weaknesses=_extra_weakness,
        axes_at_risk=_axes_risk,
        upgrade_conditions=(
            "Already at maximum for this data architecture."
            if _code not in ("FR", "DE")
            else "Would require construct adjustment for defense-exporter countries."
        ),
    ))

# Generate EU-27 medium member entries
for _code in _EU27_MEDIUM:
    COUNTRY_ELIGIBILITY_REGISTRY.append(_eligibility_entry(
        country=_code,
        name=_EU27_NAMES[_code],
        eligibility_class=EligibilityClass.CONFIDENTLY_RATEABLE,
        expected_governance_tier="FULLY_COMPARABLE",
        rationale=(
            f"{_EU27_NAMES[_code]}: medium EU member with comprehensive data "
            f"coverage. Generally same data architecture as large members."
        ),
        data_strengths=list(_EU27_CORE_STRENGTHS),
        data_weaknesses=list(_EU27_COMMON_WEAKNESSES) + [
            "Smaller trade volumes → fewer bilateral partners → potentially "
            "higher HHI by construction (not a data problem, a structural one)"
        ],
        axes_at_risk=[6],
        upgrade_conditions="Already at maximum for this data architecture.",
    ))

# Generate EU-27 small member entries
for _code in _EU27_SMALL:
    COUNTRY_ELIGIBILITY_REGISTRY.append(_eligibility_entry(
        country=_code,
        name=_EU27_NAMES[_code],
        eligibility_class=EligibilityClass.RATEABLE_WITH_CAVEATS,
        expected_governance_tier="PARTIALLY_COMPARABLE",
        rationale=(
            f"{_EU27_NAMES[_code]}: small EU member. Data architecture is same "
            f"as larger members, but smaller trade volumes mean fewer bilateral "
            f"partners and potentially higher structural HHI. Defense axis may "
            f"have sparse SIPRI data."
        ),
        data_strengths=list(_EU27_CORE_STRENGTHS),
        data_weaknesses=list(_EU27_COMMON_WEAKNESSES) + [
            "Small trade volumes → few bilateral partners → structural HHI inflation",
            "SIPRI TIV may show zero or very lumpy defense transfers",
            "Logistics axis particularly sparse for landlocked/small states",
        ],
        axes_at_risk=[4, 6],
        upgrade_conditions=(
            "Limited by country size, not data architecture. No upgrade "
            "path without construct modification."
        ),
    ))


# ---------------------------------------------------------------------------
# Non-EU Reference Countries
# ---------------------------------------------------------------------------

COUNTRY_ELIGIBILITY_REGISTRY.extend([
    _eligibility_entry(
        country="GB",
        name="United Kingdom",
        eligibility_class=EligibilityClass.CONFIDENTLY_RATEABLE,
        expected_governance_tier="FULLY_COMPARABLE",
        rationale=(
            "GB (United Kingdom): Major economy with comprehensive data "
            "coverage. BIS reporter, CPIS participant, Comtrade reporting. "
            "Post-Brexit trade data may show transitional patterns."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "CPIS participant",
            "Comtrade: comprehensive bilateral trade data",
            "SIPRI: well-documented arms trade",
        ],
        data_weaknesses=[
            "Post-Brexit transitional trade patterns (2020-2023)",
            "Financial center effects (London) may skew Axis 1",
            "Logistics axis coverage: good for maritime, partial for others",
        ],
        axes_at_risk=[6],
        upgrade_conditions="Already at maximum for this data architecture.",
    ),
    _eligibility_entry(
        country="JP",
        name="Japan",
        eligibility_class=EligibilityClass.CONFIDENTLY_RATEABLE,
        expected_governance_tier="FULLY_COMPARABLE",
        rationale=(
            "Japan: Major economy, BIS reporter, CPIS participant. "
            "Strong bilateral data across all trade-based axes. "
            "Defense imports well-documented via SIPRI."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "CPIS participant",
            "Comtrade: excellent bilateral trade coverage",
            "SIPRI: well-documented defense imports (F-35 etc.)",
        ],
        data_weaknesses=[
            "Technology re-exports may affect Axis 3",
            "Logistics: good maritime data, limited rail (island nation)",
        ],
        axes_at_risk=[6],
        upgrade_conditions="Already at maximum for this data architecture.",
    ),
    _eligibility_entry(
        country="KR",
        name="South Korea",
        eligibility_class=EligibilityClass.CONFIDENTLY_RATEABLE,
        expected_governance_tier="FULLY_COMPARABLE",
        rationale=(
            "South Korea: Major economy, BIS reporter, CPIS participant. "
            "Strong bilateral trade data. Major semiconductor producer "
            "but net IMPORTER of many semiconductor categories."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "CPIS participant",
            "Comtrade: comprehensive trade data",
            "Major defense importer — SIPRI coverage strong",
        ],
        data_weaknesses=[
            "Semiconductor self-sufficiency may affect Axis 3 interpretation",
            "Logistics: good maritime, no rail trade (peninsula)",
        ],
        axes_at_risk=[6],
        upgrade_conditions="Already at maximum for this data architecture.",
    ),
    _eligibility_entry(
        country="NO",
        name="Norway",
        eligibility_class=EligibilityClass.RATEABLE_WITH_CAVEATS,
        expected_governance_tier="PARTIALLY_COMPARABLE",
        rationale=(
            "Norway: BIS reporter, CPIS participant, Comtrade reporting. "
            "BUT: major energy exporter — Axis 2 is producer-inverted."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "CPIS participant",
            "Comtrade: comprehensive",
            "Good data architecture overall",
        ],
        data_weaknesses=[
            "Energy axis (Axis 2) is producer-inverted — Norway is a major "
            "petroleum/gas exporter",
            "Small country → fewer bilateral partners on some axes",
        ],
        axes_at_risk=[2, 6],
        upgrade_conditions=(
            "Would require alternative energy axis construct for exporters."
        ),
    ),
    _eligibility_entry(
        country="AU",
        name="Australia",
        eligibility_class=EligibilityClass.RATEABLE_WITH_CAVEATS,
        expected_governance_tier="LOW_CONFIDENCE",
        rationale=(
            "Australia: BIS reporter, CPIS participant. BUT: major "
            "exporter of energy AND critical inputs — 2 axes producer-"
            "inverted. This pushes to LOW_CONFIDENCE despite good data."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "CPIS participant",
            "Comtrade: comprehensive",
        ],
        data_weaknesses=[
            "Energy axis (Axis 2): major coal/LNG exporter — inverted",
            "Critical inputs axis (Axis 5): major iron ore/lithium/rare earths — inverted",
            "2 inverted axes → LOW_CONFIDENCE governance tier",
        ],
        axes_at_risk=[2, 5, 6],
        upgrade_conditions=(
            "Would require alternative construct for producer countries "
            "on energy and critical inputs."
        ),
    ),
    _eligibility_entry(
        country="US",
        name="United States",
        eligibility_class=EligibilityClass.PARTIALLY_RATEABLE,
        expected_governance_tier="NON_COMPARABLE",
        rationale=(
            "US: Comprehensive data architecture (BIS, partial CPIS). "
            "BUT: 3 producer-inverted axes (energy, defense, critical "
            "inputs) → NON_COMPARABLE. The ISI construct is structurally "
            "inapplicable to the US for majority of axes."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "Comtrade: comprehensive trade data",
            "SIPRI: well-documented (as exporter)",
        ],
        data_weaknesses=[
            "3 producer-inverted axes (2, 4, 5) → NON_COMPARABLE",
            "ISI measures the wrong construct for the US",
            "Defense axis: US is the world's largest arms exporter",
            "Energy axis: US is a major shale oil/gas producer",
            "Critical inputs: US is a significant mineral exporter",
        ],
        axes_at_risk=[2, 4, 5],
        upgrade_conditions=(
            "Fundamental construct redesign required. ISI would need an "
            "alternative measurement framework for net-exporter countries "
            "to make the US rateable."
        ),
    ),
    _eligibility_entry(
        country="CN",
        name="China",
        eligibility_class=EligibilityClass.PARTIALLY_RATEABLE,
        expected_governance_tier="LOW_CONFIDENCE",
        rationale=(
            "China: NOT a CPIS participant. 2 producer-inverted axes "
            "(defense, critical inputs). The combination of CPIS absence "
            "(degrades Axis 1) and 2 inversions pushes to LOW_CONFIDENCE. "
            "Directional insight only."
        ),
        data_strengths=[
            "Comtrade: China reports comprehensive trade data",
            "BIS: partial coverage (some Chinese banks report)",
        ],
        data_weaknesses=[
            "NOT a CPIS participant — Axis 1 is single-channel",
            "Defense axis (Axis 4): major arms exporter — inverted",
            "Critical inputs (Axis 5): dominant rare earths exporter — inverted",
            "2 inverted axes → LOW_CONFIDENCE minimum",
            "Financial data quality: BIS coverage may undercount",
        ],
        axes_at_risk=[1, 4, 5, 6],
        upgrade_conditions=(
            "China joining CPIS would upgrade Axis 1. Producer inversion "
            "requires construct redesign."
        ),
    ),
    _eligibility_entry(
        country="SA",
        name="Saudi Arabia",
        eligibility_class=EligibilityClass.PARTIALLY_RATEABLE,
        expected_governance_tier="PARTIALLY_COMPARABLE",
        rationale=(
            "Saudi Arabia: 1 producer-inverted axis (energy). Not a BIS "
            "reporter (limited Axis 1). CPIS participant. Comtrade data "
            "available but less comprehensive than OECD members."
        ),
        data_strengths=[
            "CPIS participant",
            "Comtrade data available",
            "SIPRI: well-documented defense imports",
        ],
        data_weaknesses=[
            "Energy axis (Axis 2): world's largest petroleum exporter — inverted",
            "Not a BIS LBS reporting country — Axis 1 degraded",
            "Logistics data may be partial",
        ],
        axes_at_risk=[1, 2, 6],
        upgrade_conditions=(
            "SA joining BIS reporting would help Axis 1. Energy inversion "
            "requires construct redesign."
        ),
    ),
    _eligibility_entry(
        country="RU",
        name="Russia",
        eligibility_class=EligibilityClass.NOT_CURRENTLY_RATEABLE,
        expected_governance_tier="NON_COMPARABLE",
        rationale=(
            "Russia: SANCTIONS_DISTORTION makes all bilateral data from "
            "2022+ non-comparable. Additionally, 3 producer-inverted "
            "axes (energy, defense, critical inputs). Double structural "
            "disqualification."
        ),
        data_strengths=[
            "Pre-sanctions: Comtrade, BIS (limited), SIPRI well-documented",
        ],
        data_weaknesses=[
            "Active sanctions regime → SANCTIONS_DISTORTION (severity=1.0)",
            "3 producer-inverted axes (2, 4, 5) → NON_COMPARABLE",
            "Not a CPIS participant",
            "Post-2022 trade data reflects crisis regime, not steady state",
        ],
        axes_at_risk=[1, 2, 4, 5, 6],
        upgrade_conditions=(
            "Sanctions lifting + stabilization period (3+ years) + "
            "construct redesign for producer countries."
        ),
    ),
    _eligibility_entry(
        country="BR",
        name="Brazil",
        eligibility_class=EligibilityClass.RATEABLE_WITH_CAVEATS,
        expected_governance_tier="PARTIALLY_COMPARABLE",
        rationale=(
            "Brazil: CPIS participant, Comtrade reporting. No producer "
            "inversions. But: not a BIS LBS reporter, logistics data "
            "partial. Generally good data architecture for a major "
            "emerging economy."
        ),
        data_strengths=[
            "CPIS participant",
            "Comtrade: comprehensive trade data",
            "SIPRI: well-documented defense imports",
            "No producer inversions on any axis",
        ],
        data_weaknesses=[
            "Not a BIS LBS reporting country — Axis 1 single-channel",
            "Logistics: continental size, mixed modal coverage",
        ],
        axes_at_risk=[1, 6],
        upgrade_conditions=(
            "Brazil joining BIS LBS reporting would upgrade Axis 1."
        ),
    ),
    _eligibility_entry(
        country="IN",
        name="India",
        eligibility_class=EligibilityClass.RATEABLE_WITH_CAVEATS,
        expected_governance_tier="PARTIALLY_COMPARABLE",
        rationale=(
            "India: CPIS participant, Comtrade reporting. No producer "
            "inversions. BIS coverage limited. Large economy with "
            "generally good import data. Defense imports well-documented "
            "via SIPRI."
        ),
        data_strengths=[
            "CPIS participant",
            "Comtrade: good bilateral trade data",
            "SIPRI: India is a major arms importer — well-documented",
            "No producer inversions",
        ],
        data_weaknesses=[
            "Not a BIS LBS reporting country — Axis 1 single-channel",
            "Logistics: partial coverage, infrastructure heterogeneity",
        ],
        axes_at_risk=[1, 6],
        upgrade_conditions=(
            "India joining BIS LBS reporting would upgrade Axis 1."
        ),
    ),
    _eligibility_entry(
        country="ZA",
        name="South Africa",
        eligibility_class=EligibilityClass.RATEABLE_WITH_CAVEATS,
        expected_governance_tier="PARTIALLY_COMPARABLE",
        rationale=(
            "South Africa: BIS reporter, CPIS participant. No producer "
            "inversions. Good data architecture for an emerging economy. "
            "Logistics axis may be partial."
        ),
        data_strengths=[
            "BIS LBS reporting country",
            "CPIS participant",
            "Comtrade: good bilateral trade data",
            "No producer inversions",
        ],
        data_weaknesses=[
            "Logistics: mixed modal coverage",
            "Defense imports (SIPRI): may be lumpy for smaller transfers",
        ],
        axes_at_risk=[6],
        upgrade_conditions=(
            "Logistics data improvement would help. Otherwise good."
        ),
    ),
])


def get_country_eligibility_registry() -> list[dict[str, Any]]:
    """Return the complete country eligibility registry."""
    return list(COUNTRY_ELIGIBILITY_REGISTRY)


def get_countries_by_eligibility(
    eligibility_class: str,
) -> list[dict[str, Any]]:
    """Filter countries by eligibility class."""
    return [
        c for c in COUNTRY_ELIGIBILITY_REGISTRY
        if c["eligibility_class"] == eligibility_class
    ]


def get_eligibility_summary() -> dict[str, Any]:
    """Return summary of country eligibility classifications."""
    counts: dict[str, int] = {}
    countries_by_class: dict[str, list[str]] = {}
    for c in COUNTRY_ELIGIBILITY_REGISTRY:
        cls = c["eligibility_class"]
        counts[cls] = counts.get(cls, 0) + 1
        countries_by_class.setdefault(cls, []).append(c["country"])

    return {
        "total_countries_assessed": len(COUNTRY_ELIGIBILITY_REGISTRY),
        "by_class": counts,
        "countries_by_class": countries_by_class,
        "answer_to_who_is_rateable_now": {
            "confidently_rateable": countries_by_class.get(
                EligibilityClass.CONFIDENTLY_RATEABLE, []
            ),
            "rateable_with_caveats": countries_by_class.get(
                EligibilityClass.RATEABLE_WITH_CAVEATS, []
            ),
            "partially_rateable": countries_by_class.get(
                EligibilityClass.PARTIALLY_RATEABLE, []
            ),
            "not_currently_rateable": countries_by_class.get(
                EligibilityClass.NOT_CURRENTLY_RATEABLE, []
            ),
        },
        "honesty_note": (
            "These classifications reflect the ISI data architecture "
            "as currently implemented. 'Confidently rateable' means the "
            "data sources and construct are appropriate — it does NOT mean "
            "the ISI score is 'correct' in any absolute sense. All ISI "
            "outputs remain estimates with documented uncertainty."
        ),
        "authority_note": (
            "This is the calibration module's SUPPLEMENTARY eligibility "
            "metadata. The AUTHORITATIVE eligibility system is in "
            "backend/eligibility.py (TheoreticalEligibility + "
            "DecisionUsabilityClass). Use eligibility.classify_country() "
            "and eligibility.classify_decision_usability() for "
            "authoritative classifications."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# TASK 8: SENSITIVITY ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════════
# Perturb governance thresholds and measure impact on tier/eligibility.

def run_sensitivity_analysis(
    country_governance_results: dict[str, dict[str, Any]],
    perturbation_pct: float = 0.15,
) -> dict[str, Any]:
    """Run sensitivity analysis on governance thresholds.

    Perturbs key thresholds by ±perturbation_pct and measures
    how many countries change governance tier or eligibility.

    This is a STATIC analysis — it does not re-run the full pipeline.
    It simulates threshold changes against the existing governance
    results to identify which thresholds are consequential.

    Args:
        country_governance_results: Dict of country → governance assessment
            (output of assess_all_countries or assess_country_governance).
        perturbation_pct: Fraction to perturb thresholds (default 15%).

    Returns:
        Dict with per-threshold sensitivity analysis.
    """
    from backend.governance import (
        CONFIDENCE_THRESHOLDS,
        MIN_MEAN_CONFIDENCE_FOR_RANKING,
        MAX_LOW_CONFIDENCE_AXES_FOR_RANKING,
        MAX_INVERTED_AXES_FOR_COMPARABLE,
    )

    results: dict[str, Any] = {
        "perturbation_pct": perturbation_pct,
        "n_countries_analyzed": len(country_governance_results),
        "threshold_sensitivities": [],
    }

    # Analyze key thresholds
    _analyze_confidence_threshold_sensitivity(
        country_governance_results, perturbation_pct, results
    )
    _analyze_mean_confidence_sensitivity(
        country_governance_results, perturbation_pct, results
    )
    _analyze_inverted_axes_sensitivity(
        country_governance_results, results
    )

    # Overall assessment
    total_changes = sum(
        s.get("countries_affected_up", 0) + s.get("countries_affected_down", 0)
        for s in results["threshold_sensitivities"]
    )
    results["overall_sensitivity"] = (
        "HIGH" if total_changes > len(country_governance_results) * 0.3
        else "MODERATE" if total_changes > len(country_governance_results) * 0.1
        else "LOW"
    )
    results["interpretation"] = (
        f"Under ±{perturbation_pct*100:.0f}% perturbation of governance "
        f"thresholds, {total_changes} country-threshold combinations "
        f"show tier/eligibility changes. Sensitivity is "
        f"{results['overall_sensitivity']}."
    )

    return results


def _analyze_confidence_threshold_sensitivity(
    gov_results: dict[str, dict[str, Any]],
    perturbation_pct: float,
    output: dict[str, Any],
) -> None:
    """Analyze sensitivity of confidence level thresholds."""
    from backend.governance import CONFIDENCE_THRESHOLDS

    for threshold_val, level_name in CONFIDENCE_THRESHOLDS:
        perturbed_up = threshold_val * (1 + perturbation_pct)
        perturbed_down = threshold_val * (1 - perturbation_pct)

        affected_up: list[str] = []
        affected_down: list[str] = []

        for country, gov in gov_results.items():
            for ac in gov.get("axis_confidences", []):
                score = ac.get("confidence_score", 0)
                # Would this axis change level with perturbed threshold?
                if perturbed_down <= score < threshold_val:
                    # Score is below current threshold but above lowered one
                    # → would gain this level with lowered threshold
                    affected_down.append(f"{country}:axis{ac.get('axis_id')}")
                elif threshold_val <= score < perturbed_up:
                    # Score meets current threshold but not raised one
                    # → would lose this level with raised threshold
                    affected_up.append(f"{country}:axis{ac.get('axis_id')}")

        output["threshold_sensitivities"].append({
            "threshold": f"CONFIDENCE_LEVEL:{level_name}",
            "current_value": threshold_val,
            "perturbed_up": round(perturbed_up, 4),
            "perturbed_down": round(perturbed_down, 4),
            "countries_affected_up": len(affected_up),
            "countries_affected_down": len(affected_down),
            "affected_up_detail": affected_up[:10],  # Cap detail
            "affected_down_detail": affected_down[:10],
            "interpretation": (
                f"Raising {level_name} threshold to {perturbed_up:.3f}: "
                f"{len(affected_up)} axis-country results would lose "
                f"{level_name} status. Lowering to {perturbed_down:.3f}: "
                f"{len(affected_down)} would gain it."
            ),
        })


def _analyze_mean_confidence_sensitivity(
    gov_results: dict[str, dict[str, Any]],
    perturbation_pct: float,
    output: dict[str, Any],
) -> None:
    """Analyze sensitivity of mean confidence ranking threshold."""
    from backend.governance import MIN_MEAN_CONFIDENCE_FOR_RANKING

    threshold = MIN_MEAN_CONFIDENCE_FOR_RANKING
    perturbed_up = threshold * (1 + perturbation_pct)
    perturbed_down = threshold * (1 - perturbation_pct)

    would_lose_ranking: list[str] = []
    would_gain_ranking: list[str] = []

    for country, gov in gov_results.items():
        mean_conf = gov.get("mean_axis_confidence", 0)
        is_eligible = gov.get("ranking_eligible", False)

        if threshold <= mean_conf < perturbed_up and is_eligible:
            would_lose_ranking.append(country)
        elif perturbed_down <= mean_conf < threshold and not is_eligible:
            would_gain_ranking.append(country)

    output["threshold_sensitivities"].append({
        "threshold": "RANKING:MIN_MEAN_CONFIDENCE",
        "current_value": threshold,
        "perturbed_up": round(perturbed_up, 4),
        "perturbed_down": round(perturbed_down, 4),
        "countries_affected_up": len(would_lose_ranking),
        "countries_affected_down": len(would_gain_ranking),
        "affected_up_detail": would_lose_ranking[:10],
        "affected_down_detail": would_gain_ranking[:10],
        "interpretation": (
            f"Raising ranking confidence threshold to {perturbed_up:.3f}: "
            f"{len(would_lose_ranking)} countries would lose ranking "
            f"eligibility. Lowering to {perturbed_down:.3f}: "
            f"{len(would_gain_ranking)} would gain it."
        ),
    })


def _analyze_inverted_axes_sensitivity(
    gov_results: dict[str, dict[str, Any]],
    output: dict[str, Any],
) -> None:
    """Analyze sensitivity of inverted-axes thresholds.

    This is a discrete threshold (integer), so we test ±1.
    """
    from backend.governance import MAX_INVERTED_AXES_FOR_COMPARABLE

    current = MAX_INVERTED_AXES_FOR_COMPARABLE

    stricter_would_change: list[str] = []
    laxer_would_change: list[str] = []

    for country, gov in gov_results.items():
        n_inv = gov.get("n_producer_inverted_axes", 0)
        tier = gov.get("governance_tier", "")

        # If threshold goes from 2→1: countries with exactly 2 inversions
        # that are currently LOW_CONFIDENCE would become NON_COMPARABLE
        if n_inv == current and tier == "LOW_CONFIDENCE":
            stricter_would_change.append(country)

        # If threshold goes from 2→3: countries with exactly 3 inversions
        # that are NON_COMPARABLE might become LOW_CONFIDENCE
        if n_inv == current + 1 and tier == "NON_COMPARABLE":
            laxer_would_change.append(country)

    output["threshold_sensitivities"].append({
        "threshold": "GOVERNANCE:MAX_INVERTED_AXES_COMPARABLE",
        "current_value": current,
        "perturbed_up": current + 1,
        "perturbed_down": max(1, current - 1),
        "countries_affected_up": len(laxer_would_change),
        "countries_affected_down": len(stricter_would_change),
        "affected_up_detail": laxer_would_change[:10],
        "affected_down_detail": stricter_would_change[:10],
        "interpretation": (
            f"Tightening inverted-axis threshold to {max(1, current-1)}: "
            f"{len(stricter_would_change)} countries would move from "
            f"LOW_CONFIDENCE to NON_COMPARABLE. "
            f"Relaxing to {current+1}: "
            f"{len(laxer_would_change)} would move from NON_COMPARABLE "
            f"to LOW_CONFIDENCE."
        ),
    })


# ═══════════════════════════════════════════════════════════════════════════
# TASK 9: EXTERNAL BENCHMARK HOOKS
# ═══════════════════════════════════════════════════════════════════════════
# ⚠️ DEPRECATED — Superseded by backend/benchmark_registry.py
#
# The benchmark_registry.py module defines 8 benchmarks with full metadata
# (comparison types, alignment thresholds, integration status, coverage).
# The external_validation.py module implements the alignment engine.
#
# This EXTERNAL_BENCHMARK_REGISTRY is retained ONLY for backward
# compatibility with existing tests. It should NOT be extended or
# modified. For all new benchmark work, use:
#   backend.benchmark_registry.get_benchmark_registry()
#   backend.benchmark_registry.get_benchmarks_for_axis()
#   backend.external_validation.compare_to_benchmark()
# ═══════════════════════════════════════════════════════════════════════════

EXTERNAL_BENCHMARK_REGISTRY: list[dict[str, Any]] = [
    {
        "benchmark_id": "EU_CRM_SUPPLY",
        "name": "EU Critical Raw Materials Supply Study",
        "description": (
            "EU CRM Act supply concentration data for critical raw "
            "materials. Potential validation source for Axis 5."
        ),
        "relevant_axes": [5],
        "comparison_type": "RANK_CORRELATION",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Download EU CRM bilateral supply data",
            "Map EU CRM country codes to ISI ISO-2",
            "Compute HHI-equivalent concentration from CRM data",
            "Compute Spearman rank correlation with ISI Axis 5",
        ],
        "expected_correlation": "0.6-0.8 for EU-27 countries",
        "validation_threshold": (
            "If Spearman rho < 0.4, ISI Axis 5 is not measuring the "
            "same construct as EU CRM. If rho > 0.7, strong validation."
        ),
    },
    {
        "benchmark_id": "IEA_ENERGY_SECURITY",
        "name": "IEA Energy Security Indicators",
        "description": (
            "IEA energy import dependency and diversification metrics. "
            "Potential validation source for Axis 2."
        ),
        "relevant_axes": [2],
        "comparison_type": "RANK_CORRELATION",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Access IEA energy security indicators API",
            "Extract bilateral energy import concentration data",
            "Map to ISI country universe",
            "Compute rank correlation with ISI Axis 2",
        ],
        "expected_correlation": "0.7-0.9 for OECD countries",
        "validation_threshold": (
            "If Spearman rho < 0.5, ISI Axis 2 energy measurement "
            "diverges from IEA's. If rho > 0.8, strong validation."
        ),
    },
    {
        "benchmark_id": "SIPRI_MILEX",
        "name": "SIPRI Military Expenditure Database",
        "description": (
            "SIPRI military expenditure as a cross-check for defense "
            "axis. High military spending + low import concentration "
            "suggests domestic production (producer inversion signal)."
        ),
        "relevant_axes": [4],
        "comparison_type": "STRUCTURAL_CONSISTENCY",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Download SIPRI MILEX data",
            "Identify countries with high MILEX but low Axis 4 HHI",
            "These should be flagged as potential producer inversions",
            "Compare against PRODUCER_INVERSION_REGISTRY for coverage",
        ],
        "expected_correlation": "Structural check, not correlation",
        "validation_threshold": (
            "If >3 countries have high MILEX + low Axis 4 HHI but are "
            "NOT in the producer inversion registry, the registry is "
            "incomplete."
        ),
    },
    {
        "benchmark_id": "BIS_FINANCIAL_EXPOSURE",
        "name": "BIS Consolidated Banking Statistics",
        "description": (
            "BIS CBS provides a different view of bilateral financial "
            "exposure (ultimate risk basis). Could validate Axis 1."
        ),
        "relevant_axes": [1],
        "comparison_type": "RANK_CORRELATION",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Access BIS CBS data (different from LBS used in ISI)",
            "Compute HHI-equivalent from CBS bilateral exposure",
            "Compare with ISI Axis 1 (BIS LBS + CPIS based)",
        ],
        "expected_correlation": "0.7-0.9 for reporting countries",
        "validation_threshold": (
            "If rho < 0.5 between LBS-based and CBS-based measures, "
            "the financial axis is source-dependent, raising questions "
            "about construct validity."
        ),
    },
]


def get_external_benchmarks() -> list[dict[str, Any]]:
    """Return the external benchmark registry."""
    return list(EXTERNAL_BENCHMARK_REGISTRY)


def get_benchmark_integration_status() -> dict[str, str]:
    """Return integration status for all benchmarks."""
    return {
        b["benchmark_id"]: b["status"]
        for b in EXTERNAL_BENCHMARK_REGISTRY
    }


# ═══════════════════════════════════════════════════════════════════════════
# TASK 10: GOVERNANCE EXPLANATION OBJECT ENHANCEMENT
# ═══════════════════════════════════════════════════════════════════════════

def build_governance_explanation(
    governance: dict[str, Any],
) -> dict[str, Any]:
    """Build an enhanced governance explanation object for a country.

    This extends the basic governance assessment with calibration
    metadata, falsifiability references, and explicit uncertainty
    disclosure.

    Args:
        governance: Output of assess_country_governance().

    Returns:
        Enhanced explanation object with calibration context.
    """
    country = governance.get("country", "UNKNOWN")
    tier = governance.get("governance_tier", "UNKNOWN")

    # Classify each axis confidence by calibration quality
    axis_calibration_quality: list[dict[str, Any]] = []
    for ac in governance.get("axis_confidences", []):
        axis_id = ac.get("axis_id", 0)
        notes = AXIS_CALIBRATION_NOTES.get(axis_id, {})
        axis_calibration_quality.append({
            "axis_id": axis_id,
            "confidence_score": ac.get("confidence_score", 0),
            "confidence_level": ac.get("confidence_level", "UNKNOWN"),
            "baseline_calibration_class": notes.get(
                "baseline_class", CalibrationClass.HEURISTIC
            ),
            "construct_validity_note": notes.get("construct_validity", ""),
            "falsifiable_claim": notes.get("falsifiable_claim", ""),
        })

    # Count calibration classes across thresholds that affect this country
    n_heuristic = len(get_thresholds_by_class(CalibrationClass.HEURISTIC))
    n_total = len(THRESHOLD_REGISTRY)
    heuristic_pct = round(n_heuristic / n_total * 100, 1) if n_total else 0

    # Find matching eligibility entry
    eligibility = None
    for entry in COUNTRY_ELIGIBILITY_REGISTRY:
        if entry["country"] == country:
            eligibility = entry
            break

    return {
        "country": country,
        "governance_tier": tier,
        "tier_meaning": _tier_meaning(tier),
        "axis_calibration_quality": axis_calibration_quality,
        "calibration_disclosure": (
            f"This governance assessment depends on {n_total} thresholds, "
            f"of which {heuristic_pct}% are heuristic (expert judgment, "
            f"not empirically calibrated). The governance tier is a "
            f"structured expert assessment, not a measured quantity."
        ),
        "eligibility_class": (
            eligibility["eligibility_class"] if eligibility else "NOT_ASSESSED"
        ),
        "eligibility_rationale": (
            eligibility["rationale"] if eligibility else "Country not in eligibility registry."
        ),
        "structural_limitations": governance.get("structural_limitations", []),
        "falsifiability_note": (
            "Every governance mechanism has explicit falsification criteria. "
            "See FALSIFIABILITY_REGISTRY for what evidence would change "
            "this country's classification."
        ),
        "honesty_statement": (
            f"ISI governance tier '{tier}' for {country} is a structured "
            f"assessment based on data quality flags, source coverage, "
            f"and structural analysis. It is NOT a definitive measure of "
            f"data reliability. It represents our BEST CURRENT JUDGMENT "
            f"about how much this country's ISI output can be trusted "
            f"for comparative purposes."
        ),
    }


def _tier_meaning(tier: str) -> str:
    """Return plain-language tier meaning."""
    meanings = {
        "FULLY_COMPARABLE": (
            "All structural requirements met. ISI output is suitable for "
            "cross-country comparison and ranking. This does NOT mean "
            "the score is 'correct' — it means the measurement basis "
            "supports meaningful comparison."
        ),
        "PARTIALLY_COMPARABLE": (
            "Comparison is valid but structural limitations exist. "
            "Use with awareness of documented caveats. Ranking is "
            "permitted within the same partition."
        ),
        "LOW_CONFIDENCE": (
            "ISI composite is computable but NOT defensible for ranking. "
            "Significant structural issues affect interpretation. "
            "Use for directional insight only."
        ),
        "NON_COMPARABLE": (
            "ISI output is too structurally compromised for any "
            "comparative purpose. Do NOT use for ranking or cross-"
            "country comparison."
        ),
    }
    return meanings.get(tier, "Unknown tier.")


# ═══════════════════════════════════════════════════════════════════════════
# TASK 13: SELF-AUDIT FOR PSEUDO-RIGOR
# ═══════════════════════════════════════════════════════════════════════════
# Explicit inventory of where the system might create false confidence.

PSEUDO_RIGOR_AUDIT: list[dict[str, Any]] = [
    {
        "risk": "Confidence scores look precise but are built on heuristic penalties",
        "location": "governance.py: CONFIDENCE_PENALTIES",
        "mitigation": (
            "Every penalty is documented with calibration_class in this "
            "module. HEURISTIC penalties are explicitly labeled. Confidence "
            "scores are displayed to 2 decimal places but the underlying "
            "precision is ±0.1 at best."
        ),
        "residual_risk": "MEDIUM — users may still over-interpret 0.55 vs 0.50",
        "recommendation": (
            "Consider displaying confidence as bands (HIGH/MODERATE/LOW) "
            "rather than numeric scores in user-facing outputs."
        ),
    },
    {
        "risk": "Governance tiers suggest objective classification but rules are heuristic",
        "location": "governance.py: _determine_governance_tier()",
        "mitigation": (
            "14 tier rules are documented with evidence basis and "
            "falsifiability criteria. The ordering is explicit and "
            "auditable."
        ),
        "residual_risk": "MEDIUM — rule ordering is heuristic, not empirically validated",
        "recommendation": (
            "Future: validate rule ordering against expert panel "
            "assessments for 10+ reference countries."
        ),
    },
    {
        "risk": "Severity weights suggest calibrated measurement but are expert estimates",
        "location": "severity.py: SEVERITY_WEIGHTS",
        "mitigation": (
            "Each weight has a documented calibration rationale in "
            "severity.py comments and in this module's calibration "
            "registry. Weights are labeled SEMI_EMPIRICAL or HEURISTIC, "
            "not EMPIRICAL."
        ),
        "residual_risk": "LOW — honest labeling reduces false confidence",
        "recommendation": (
            "Empirical calibration requires output validation against "
            "external benchmarks (TASK 9)."
        ),
    },
    {
        "risk": "Country eligibility registry may create false binary between 'rateable' and 'not rateable'",
        "location": "calibration.py: COUNTRY_ELIGIBILITY_REGISTRY",
        "mitigation": (
            "Four-level classification (CONFIDENTLY_RATEABLE through "
            "NOT_CURRENTLY_RATEABLE) with explicit rationale and upgrade "
            "conditions for each country."
        ),
        "residual_risk": "LOW — explicit boundaries with documented reasoning",
        "recommendation": (
            "Review eligibility classifications annually against "
            "updated data availability."
        ),
    },
    {
        "risk": "Composite eligibility thresholds (4 axes, 5 for ranking) are round numbers that suggest deliberation but are actually arbitrary",
        "location": "governance.py: MIN_AXES_FOR_COMPOSITE, MIN_AXES_FOR_RANKING",
        "mitigation": (
            "Thresholds are labeled STRUCTURAL_NORMATIVE in calibration "
            "registry. Sensitivity analysis (TASK 8) can measure their "
            "impact. They are design choices, not empirical findings."
        ),
        "residual_risk": "LOW — honest labeling",
        "recommendation": (
            "Run leave-one-out composite stability analysis to check "
            "whether the 4/5 boundary is at a natural breakpoint."
        ),
    },
    {
        "risk": "The system's extensive documentation may itself create false confidence through thoroughness",
        "location": "All governance and calibration modules",
        "mitigation": (
            "This self-audit exists specifically to counteract that risk. "
            "The system explicitly states: 'Thoroughly documented uncertainty "
            "is still uncertainty. Documentation ≠ precision.'"
        ),
        "residual_risk": "MEDIUM — unavoidable to some degree",
        "recommendation": (
            "Every user-facing output should include: 'This assessment "
            "is based on structured expert judgment, not empirical "
            "calibration. See calibration registry for evidence basis.'"
        ),
    },
    {
        "risk": "Falsifiability criteria exist but are not actually tested",
        "location": "calibration.py: FALSIFIABILITY_REGISTRY",
        "mitigation": (
            "External benchmark hooks (TASK 9) provide the infrastructure "
            "for future testing. Current status: falsifiability criteria "
            "are DECLARED but NOT EXECUTED."
        ),
        "residual_risk": "HIGH — declared falsifiability without testing is performative",
        "recommendation": (
            "Prioritize integration of at least one external benchmark "
            "(EU CRM or IEA energy) to move from declared to tested "
            "falsifiability."
        ),
    },
]


def get_pseudo_rigor_audit() -> list[dict[str, Any]]:
    """Return the pseudo-rigor self-audit."""
    return list(PSEUDO_RIGOR_AUDIT)


def get_pseudo_rigor_summary() -> dict[str, Any]:
    """Return summary statistics of the pseudo-rigor audit."""
    risk_levels = {}
    for item in PSEUDO_RIGOR_AUDIT:
        level = item["residual_risk"].split(" — ")[0] if " — " in item["residual_risk"] else item["residual_risk"]
        risk_levels[level] = risk_levels.get(level, 0) + 1

    return {
        "total_risks_identified": len(PSEUDO_RIGOR_AUDIT),
        "by_residual_risk_level": risk_levels,
        "highest_residual_risk": (
            "Declared falsifiability without testing is performative. "
            "External benchmark integration is the highest-priority "
            "action item."
        ),
        "overall_assessment": (
            "The system has strong structural honesty (every threshold "
            "is labeled, every mechanism has falsification criteria) but "
            "weak empirical grounding (no external benchmarks integrated, "
            "no output validation against expert panels). This is "
            "HONEST but NOT YET EMPIRICALLY ANCHORED."
        ),
    }
