#!/usr/bin/env python3
"""Tests for the state-of-the-art elevation — severity model, strict
comparability tiers, cross-country enforcement, dual composite,
stability analysis, interpretation engine, and validation hardening.

Organized by phase:
    Phase 1: Severity model (per-axis + per-country)
    Phase 2: Strict comparability tiers (TIER_1 through TIER_4)
    Phase 3: Cross-country comparability enforcement
    Phase 4: Degradation-aware aggregation (adjusted composite)
    Phase 5: Dual composite (raw + adjusted)
    Phase 6: Stability analysis (leave-one-out)
    Phase 7: Interpretation flags and summary
    Phase 8: Validation hardening (mandatory field enforcement)
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.axis_result import (
    AXIS_ID_TO_SLUG,
    AxisResult,
    CompositeResult,
    _build_quality_flags,
    _compute_comparability,
    validate_axis_result,
    validate_composite_result,
    make_invalid_axis,
    compute_composite_v11,
)
from backend.constants import ROUND_PRECISION
from backend.severity import (
    SEVERITY_WEIGHTS,
    TIER_THRESHOLDS,
    CROSS_COUNTRY_SEVERITY_THRESHOLD,
    AGGREGATION_PENALTY_RATE,
    AGGREGATION_MIN_WEIGHT,
    compute_axis_severity,
    compute_axis_severity_breakdown,
    compute_country_severity,
    assign_comparability_tier,
    check_cross_country_comparability,
    compute_adjusted_composite,
    compute_stability_analysis,
    build_interpretation,
)


# ── Helpers ──────────────────────────────────────────────────

def _valid(country="US", axis_id=1, score=0.5, source="SRC_A",
           warnings=(), basis="BOTH", validity="VALID"):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis=basis, validity=validity,
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.4, channel_b_concentration=0.6,
    )


def _a_only(country="US", axis_id=1, score=0.3, source="SRC_B",
            warnings=("W-HS6-GRANULARITY",)):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="A_ONLY", validity="A_ONLY",
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.3, channel_b_concentration=None,
    )


def _degraded(country="US", axis_id=4, score=0.01, source="SRC_C",
              warnings=("W-PRODUCER-INVERSION",)):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="BOTH", validity="DEGRADED",
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.01, channel_b_concentration=0.01,
    )


def _sanctions(country="RU", axis_id=2, score=0.8, source="SRC_D"):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="A_ONLY", validity="DEGRADED",
        coverage=None, source=source,
        warnings=("W-SANCTIONS-DISTORTION", "W-PRODUCER-INVERSION"),
        channel_a_concentration=0.8, channel_b_concentration=None,
    )


def _make_composite(axes, country="US", name="United States"):
    """Helper to produce a CompositeResult from axis list."""
    return compute_composite_v11(axes, country, name, "PHASE1-7", "v1.1")


# ═══════════════════════════════════════════════════════════════
# PHASE 1 — SEVERITY MODEL
# ═══════════════════════════════════════════════════════════════

class TestSeverityWeights:
    """Severity weights are correctly defined and documented."""

    def test_all_weights_positive(self):
        for key, val in SEVERITY_WEIGHTS.items():
            assert val > 0.0, f"{key} weight must be positive"

    def test_all_weights_bounded(self):
        for key, val in SEVERITY_WEIGHTS.items():
            assert 0.0 < val <= 1.0, f"{key} weight {val} out of (0,1]"

    def test_sanctions_is_maximum(self):
        assert SEVERITY_WEIGHTS["SANCTIONS_DISTORTION"] == 1.0

    def test_hs6_is_minimum(self):
        assert SEVERITY_WEIGHTS["HS6_GRANULARITY"] == 0.2

    def test_known_weights_present(self):
        expected = {
            "HS6_GRANULARITY", "SINGLE_CHANNEL_A", "SINGLE_CHANNEL_B",
            "CPIS_NON_PARTICIPANT", "PRODUCER_INVERSION",
            "SANCTIONS_DISTORTION", "ZERO_BILATERAL_SUPPLIERS",
            "TEMPORAL_MISMATCH", "SOURCE_HETEROGENEITY",
            "REDUCED_PRODUCT_GRANULARITY",
        }
        assert expected.issubset(set(SEVERITY_WEIGHTS.keys()))


class TestAxisSeverity:
    """Per-axis severity computation."""

    def test_clean_axis_zero_severity(self):
        assert compute_axis_severity([]) == 0.0

    def test_invalid_axis_zero_severity(self):
        assert compute_axis_severity(["INVALID_AXIS"]) == 0.0

    def test_single_channel_a(self):
        sev = compute_axis_severity(["SINGLE_CHANNEL_A"])
        assert sev == SEVERITY_WEIGHTS["SINGLE_CHANNEL_A"]

    def test_producer_inversion(self):
        sev = compute_axis_severity(["PRODUCER_INVERSION"])
        assert sev == SEVERITY_WEIGHTS["PRODUCER_INVERSION"]

    def test_sanctions_distortion(self):
        sev = compute_axis_severity(["SANCTIONS_DISTORTION"])
        assert sev == SEVERITY_WEIGHTS["SANCTIONS_DISTORTION"]

    def test_multiple_flags_sum(self):
        flags = ["SINGLE_CHANNEL_A", "REDUCED_PRODUCT_GRANULARITY"]
        sev = compute_axis_severity(flags)
        expected = (SEVERITY_WEIGHTS["SINGLE_CHANNEL_A"]
                    + SEVERITY_WEIGHTS["REDUCED_PRODUCT_GRANULARITY"])
        assert abs(sev - expected) < 1e-9

    def test_combined_severe_flags(self):
        flags = ["PRODUCER_INVERSION", "SANCTIONS_DISTORTION"]
        sev = compute_axis_severity(flags)
        expected = (SEVERITY_WEIGHTS["PRODUCER_INVERSION"]
                    + SEVERITY_WEIGHTS["SANCTIONS_DISTORTION"])
        assert abs(sev - expected) < 1e-9

    def test_unknown_flag_ignored(self):
        sev = compute_axis_severity(["UNKNOWN_FLAG"])
        assert sev == 0.0

    def test_severity_in_axis_to_dict(self):
        """AxisResult.to_dict() must include degradation_severity."""
        r = _valid()
        d = r.to_dict()
        assert "degradation_severity" in d
        assert d["degradation_severity"] == 0.0

    def test_severity_nonzero_for_degraded(self):
        r = _degraded()
        d = r.to_dict()
        assert d["degradation_severity"] > 0.0

    def test_severity_for_a_only_with_granularity(self):
        r = _a_only()
        d = r.to_dict()
        # A_ONLY + W-HS6-GRANULARITY
        expected = (SEVERITY_WEIGHTS["SINGLE_CHANNEL_A"]
                    + SEVERITY_WEIGHTS["REDUCED_PRODUCT_GRANULARITY"])
        assert abs(d["degradation_severity"] - expected) < 1e-9


class TestAxisSeverityBreakdown:
    """Per-axis severity breakdown."""

    def test_empty_flags(self):
        b = compute_axis_severity_breakdown([])
        assert b["total"] == 0.0

    def test_invalid_axis(self):
        b = compute_axis_severity_breakdown(["INVALID_AXIS"])
        assert b["total"] == 0.0

    def test_single_flag_breakdown(self):
        b = compute_axis_severity_breakdown(["SINGLE_CHANNEL_A"])
        assert "SINGLE_CHANNEL_A" in b
        assert b["SINGLE_CHANNEL_A"] == SEVERITY_WEIGHTS["SINGLE_CHANNEL_A"]
        assert b["total"] == SEVERITY_WEIGHTS["SINGLE_CHANNEL_A"]

    def test_multiple_flags_breakdown(self):
        flags = ["PRODUCER_INVERSION", "TEMPORAL_MISMATCH"]
        b = compute_axis_severity_breakdown(flags)
        # two flags + total + group_resolution = 4 keys
        assert len(b) == 4
        assert "PRODUCER_INVERSION" in b
        assert "TEMPORAL_MISMATCH" in b
        assert "group_resolution" in b
        # Group resolution: STRUCTURAL_BIAS max=0.7, DATA_GRANULARITY max=0.3
        gr = b["group_resolution"]
        assert gr["STRUCTURAL_BIAS"]["max_weight"] == 0.7
        assert gr["DATA_GRANULARITY"]["max_weight"] == 0.3


class TestCountrySeverity:
    """Per-country severity aggregation."""

    def test_empty_axes(self):
        result = compute_country_severity([])
        assert result["total_severity"] == 0.0
        assert result["worst_axis"] is None

    def test_single_clean_axis(self):
        result = compute_country_severity([(1, "financial", 0.0)])
        assert result["total_severity"] == 0.0
        assert result["n_clean_axes"] == 1
        assert result["n_degraded_axes"] == 0

    def test_single_degraded_axis(self):
        result = compute_country_severity([(4, "defense", 0.7)])
        assert result["total_severity"] == 0.7
        assert result["worst_axis"] == "defense"
        assert result["n_clean_axes"] == 0
        assert result["n_degraded_axes"] == 1

    def test_mixed_axes(self):
        axes = [
            (1, "financial", 0.0),
            (2, "energy", 0.4),
            (3, "technology", 0.2),
            (4, "defense", 0.7),
        ]
        result = compute_country_severity(axes)
        assert abs(result["total_severity"] - 1.3) < 1e-9
        assert result["worst_axis"] == "defense"
        assert result["n_clean_axes"] == 1
        assert result["n_degraded_axes"] == 3

    def test_severity_profile_keys(self):
        axes = [
            (1, "financial", 0.0),
            (2, "energy", 0.4),
        ]
        result = compute_country_severity(axes)
        profile = result["severity_profile"]
        assert "financial" in profile
        assert "energy" in profile
        assert profile["financial"] == 0.0
        assert profile["energy"] == 0.4

    def test_country_severity_in_composite(self):
        """CompositeResult.to_dict() must include severity_analysis."""
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "severity_analysis" in d
        sev = d["severity_analysis"]
        assert "total_severity" in sev
        assert "severity_profile" in sev
        assert sev["total_severity"] == 0.0


# ═══════════════════════════════════════════════════════════════
# PHASE 2 — STRICT COMPARABILITY TIERS
# ═══════════════════════════════════════════════════════════════

class TestStrictComparabilityTiers:
    """Deterministic, severity-driven tier assignment."""

    def test_tier_1_clean(self):
        assert assign_comparability_tier(0.0) == "TIER_1"

    def test_tier_1_boundary(self):
        assert assign_comparability_tier(0.49) == "TIER_1"

    def test_tier_2_at_boundary(self):
        assert assign_comparability_tier(0.5) == "TIER_2"

    def test_tier_2_mid(self):
        assert assign_comparability_tier(1.0) == "TIER_2"

    def test_tier_2_upper_boundary(self):
        assert assign_comparability_tier(1.49) == "TIER_2"

    def test_tier_3_at_boundary(self):
        assert assign_comparability_tier(1.5) == "TIER_3"

    def test_tier_3_mid(self):
        assert assign_comparability_tier(2.5) == "TIER_3"

    def test_tier_4_at_boundary(self):
        assert assign_comparability_tier(3.0) == "TIER_4"

    def test_tier_4_extreme(self):
        assert assign_comparability_tier(10.0) == "TIER_4"

    def test_strict_tier_in_composite(self):
        """CompositeResult.to_dict() must include strict_comparability_tier."""
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "strict_comparability_tier" in d
        assert d["strict_comparability_tier"] == "TIER_1"

    def test_degraded_country_gets_higher_tier(self):
        """Heavily degraded country must NOT get TIER_1."""
        axes = [_a_only(axis_id=i) for i in range(1, 5)]
        axes.append(_degraded(axis_id=5, score=0.1))
        axes.append(_degraded(axis_id=6, score=0.1))
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert d["strict_comparability_tier"] != "TIER_1"

    def test_sanctions_country_tier_4(self):
        """Sanctions-affected country should be TIER_3 or TIER_4."""
        axes = [
            _sanctions(axis_id=1, score=0.5),
            _sanctions(axis_id=2, score=0.6),
            _sanctions(axis_id=3, score=0.7),
            _sanctions(axis_id=4, score=0.4),
            _sanctions(axis_id=5, score=0.3),
            _sanctions(axis_id=6, score=0.5),
        ]
        comp = compute_composite_v11(axes, "RU", "Russia", "PHASE1-7", "v1.1")
        d = comp.to_dict()
        assert d["strict_comparability_tier"] in ("TIER_3", "TIER_4")


# ═══════════════════════════════════════════════════════════════
# PHASE 3 — CROSS-COUNTRY COMPARABILITY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════

class TestCrossCountryComparability:
    """Automatic pairwise comparability enforcement."""

    def test_similar_severities_no_violation(self):
        severities = {"US": 0.5, "GB": 0.8, "JP": 0.3}
        violations = check_cross_country_comparability(severities)
        assert len(violations) == 0

    def test_large_differential_triggers_violation(self):
        severities = {"US": 0.0, "RU": 3.0}
        violations = check_cross_country_comparability(severities)
        assert len(violations) == 1
        v = violations[0]
        assert v["warning_code"] == "W-CROSS-COUNTRY-NONCOMPARABLE"
        assert v["country_a"] == "RU"  # sorted order
        assert v["country_b"] == "US"

    def test_exact_diff_threshold_no_violation(self):
        """Diff exactly at threshold but ratio below threshold → no violation."""
        # 1.0 vs 2.5: diff = 1.5 (not >), ratio = 2.5/1.05 ≈ 2.38 (< 3.0)
        severities = {"US": 1.0, "CN": 2.5}
        violations = check_cross_country_comparability(severities)
        assert len(violations) == 0

    def test_just_over_threshold_triggers(self):
        severities = {"US": 0.0, "CN": CROSS_COUNTRY_SEVERITY_THRESHOLD + 0.01}
        violations = check_cross_country_comparability(severities)
        assert len(violations) == 1

    def test_multiple_violations(self):
        # US clean, CN moderate, RU extreme
        severities = {"US": 0.0, "CN": 0.8, "RU": 4.0}
        violations = check_cross_country_comparability(severities)
        # CN-RU: diff=3.2 > 1.5 (DIFF) + ratio=4.0/0.85≈4.7 > 3.0 (RATIO)
        # CN-US: diff=0.8 < 1.5, BUT ratio=0.8/0.05=16.0 > 3.0 (RATIO)
        # RU-US: diff=4.0 > 1.5 (DIFF) + ratio=4.0/0.05=80.0 > 3.0 (RATIO)
        assert len(violations) == 3
        # Verify trigger types
        triggers = {(v["country_a"], v["country_b"]): v["trigger"] for v in violations}
        assert "RATIO" in triggers[("CN", "US")]
        assert "DIFF" in triggers[("RU", "US")]

    def test_empty_input(self):
        violations = check_cross_country_comparability({})
        assert violations == []

    def test_single_country_no_violation(self):
        violations = check_cross_country_comparability({"US": 0.5})
        assert violations == []


# ═══════════════════════════════════════════════════════════════
# PHASE 4 — DEGRADATION-AWARE AGGREGATION
# ═══════════════════════════════════════════════════════════════

class TestAdjustedComposite:
    """Degradation-aware composite computation."""

    def test_all_clean_equals_raw(self):
        """Clean axes: adjusted == raw."""
        scores = [(0.3, 0.0), (0.3, 0.0), (0.3, 0.0),
                  (0.3, 0.0), (0.3, 0.0), (0.3, 0.0)]
        adj = compute_adjusted_composite(scores)
        assert adj is not None
        assert abs(adj - 0.3) < 1e-8

    def test_degraded_axes_lower_adjusted(self):
        """Degraded axes with higher scores should be de-weighted."""
        # One clean axis at 0.2, one heavily degraded at 0.9
        scores = [(0.2, 0.0), (0.9, 1.0)]
        adj = compute_adjusted_composite(scores)
        raw = (0.2 + 0.9) / 2  # 0.55
        # Adjusted should be less than raw because the 0.9 degraded axis
        # contributes less weight
        assert adj is not None
        assert adj < raw

    def test_empty_returns_none(self):
        assert compute_adjusted_composite([]) is None

    def test_min_weight_enforced(self):
        """Even maximum severity gets MIN_WEIGHT, not zero."""
        # severity = 1.0, penalty_rate = 0.5 → weight = 0.5
        # severity = 2.0, penalty_rate = 0.5 → weight = max(0.0, 0.1) = 0.1
        scores = [(0.5, 2.0)]
        adj = compute_adjusted_composite(scores)
        assert adj is not None
        assert adj == round(0.5, ROUND_PRECISION)

    def test_quality_weight_formula(self):
        """Verify the exact exponential quality weight formula."""
        import math
        from backend.severity import AGGREGATION_ALPHA
        # score=0.4, severity=0.6
        # quality_weight = max(exp(-1.2 * 0.6), 0.1) = exp(-0.72) ≈ 0.4868
        # score=0.8, severity=0.0
        # quality_weight = max(exp(-1.2 * 0.0), 0.1) = exp(0) = 1.0
        w1 = math.exp(-AGGREGATION_ALPHA * 0.6)
        w2 = math.exp(-AGGREGATION_ALPHA * 0.0)
        scores = [(0.4, 0.6), (0.8, 0.0)]
        adj = compute_adjusted_composite(scores)
        expected = (0.4 * w1 + 0.8 * w2) / (w1 + w2)
        assert adj is not None
        assert abs(adj - round(expected, ROUND_PRECISION)) < 1e-8

    def test_adjusted_in_composite_output(self):
        """CompositeResult.to_dict() must include composite_adjusted."""
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "composite_adjusted" in d
        assert d["composite_adjusted"] is not None


# ═══════════════════════════════════════════════════════════════
# PHASE 5 — DUAL COMPOSITE
# ═══════════════════════════════════════════════════════════════

class TestDualComposite:
    """Both composite_raw and composite_adjusted must be exported."""

    def test_both_composites_present(self):
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "composite_raw" in d
        assert "composite_adjusted" in d
        assert d["composite_raw"] == d["isi_composite"]

    def test_clean_country_raw_equals_adjusted(self):
        """For clean country, raw ≈ adjusted."""
        axes = [_valid(axis_id=i, score=0.3, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert abs(d["composite_raw"] - d["composite_adjusted"]) < 1e-8

    def test_degraded_country_adjusted_differs(self):
        """For degraded country, adjusted should differ from raw."""
        axes = [_valid(axis_id=i, score=0.2, source="S") for i in range(1, 4)]
        axes.append(_degraded(axis_id=4, score=0.9))  # high score, degraded
        axes.append(_a_only(axis_id=5, score=0.8))     # high score, A_ONLY
        axes.append(_a_only(axis_id=6, score=0.7))     # high score, A_ONLY
        comp = _make_composite(axes)
        d = comp.to_dict()
        # Adjusted should be different because degraded/A_ONLY axes are de-weighted
        assert d["composite_raw"] != d["composite_adjusted"]

    def test_ineligible_country_both_none(self):
        """Country with <4 axes: both composites should be None."""
        axes = [_valid(axis_id=i, score=0.3) for i in range(1, 4)]
        for i in range(4, 7):
            axes.append(make_invalid_axis("US", i, "NONE"))
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert d["composite_raw"] is None
        assert d["composite_adjusted"] is None


# ═══════════════════════════════════════════════════════════════
# PHASE 6 — STABILITY ANALYSIS
# ═══════════════════════════════════════════════════════════════

class TestStabilityAnalysis:
    """Leave-one-out stability analysis."""

    def test_equal_scores_perfect_stability(self):
        """If all axes have equal scores, stability should be high."""
        axes = [(i, AXIS_ID_TO_SLUG[i], 0.3) for i in range(1, 7)]
        result = compute_stability_analysis(axes)
        assert abs(result["baseline_composite"] - 0.3) < 1e-8
        assert result["max_axis_impact"] == 0.0
        assert result["stability_score"] == 1.0

    def test_single_outlier_detected(self):
        """One extreme axis should have high impact."""
        axes = [
            (1, "financial", 0.3),
            (2, "energy", 0.3),
            (3, "technology", 0.3),
            (4, "defense", 0.3),
            (5, "critical_inputs", 0.3),
            (6, "logistics", 0.9),  # outlier
        ]
        result = compute_stability_analysis(axes)
        assert result["most_influential_axis"] == "logistics"
        assert result["max_axis_impact"] > 0.0

    def test_leave_one_out_count(self):
        axes = [(i, AXIS_ID_TO_SLUG[i], 0.3) for i in range(1, 7)]
        result = compute_stability_analysis(axes)
        assert len(result["leave_one_out"]) == 6
        assert len(result["axis_impacts"]) == 6

    def test_stability_score_bounded(self):
        axes = [(i, AXIS_ID_TO_SLUG[i], 0.1 * i) for i in range(1, 7)]
        result = compute_stability_analysis(axes)
        assert 0.0 <= result["stability_score"] <= 1.0

    def test_single_axis_stability(self):
        result = compute_stability_analysis([(1, "financial", 0.5)])
        assert result["stability_score"] == 0.0

    def test_stability_in_composite_output(self):
        """CompositeResult.to_dict() must include stability_analysis."""
        axes = [_valid(axis_id=i, score=0.3, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "stability_analysis" in d
        sa = d["stability_analysis"]
        assert "stability_score" in sa
        assert "max_axis_impact" in sa
        assert "most_influential_axis" in sa
        assert "leave_one_out" in sa
        assert "axis_impacts" in sa

    def test_stability_deterministic(self):
        """Stability analysis must be deterministic."""
        axes = [_valid(axis_id=i, score=0.1 * i, source="S") for i in range(1, 7)]
        comp1 = _make_composite(axes)
        comp2 = _make_composite(axes)
        d1 = comp1.to_dict()["stability_analysis"]
        d2 = comp2.to_dict()["stability_analysis"]
        assert d1 == d2


# ═══════════════════════════════════════════════════════════════
# PHASE 7 — INTERPRETATION FLAGS
# ═══════════════════════════════════════════════════════════════

class TestInterpretation:
    """Mandatory interpretation flags and summary."""

    def test_clean_country_flags(self):
        result = build_interpretation(
            total_severity=0.0,
            comparability_tier="TIER_1",
            n_degraded_axes=0,
            n_included_axes=6,
            confidence="FULL",
            warnings=[],
        )
        assert "CLEAN" in result["interpretation_flags"]
        assert "WARNING" not in result["interpretation_summary"]

    def test_moderate_degradation(self):
        result = build_interpretation(
            total_severity=0.8,
            comparability_tier="TIER_2",
            n_degraded_axes=2,
            n_included_axes=6,
            confidence="REDUCED",
            warnings=[],
        )
        assert "MODERATE_DEGRADATION" in result["interpretation_flags"]

    def test_severe_degradation_warning(self):
        result = build_interpretation(
            total_severity=2.0,
            comparability_tier="TIER_3",
            n_degraded_axes=4,
            n_included_axes=5,
            confidence="LOW_CONFIDENCE",
            warnings=["W-PRODUCER-INVERSION"],
        )
        assert "SEVERE_DEGRADATION" in result["interpretation_flags"]
        assert "COMPARABILITY_WARNING" in result["interpretation_flags"]
        assert "WARNING" in result["interpretation_summary"]

    def test_critical_degradation_warning(self):
        result = build_interpretation(
            total_severity=4.0,
            comparability_tier="TIER_4",
            n_degraded_axes=6,
            n_included_axes=6,
            confidence="LOW_CONFIDENCE",
            warnings=["W-SANCTIONS-DISTORTION"],
        )
        assert "CRITICAL_DEGRADATION" in result["interpretation_flags"]
        assert "SANCTIONS_AFFECTED" in result["interpretation_flags"]
        assert "CRITICAL WARNING" in result["interpretation_summary"]

    def test_incomplete_coverage_flag(self):
        result = build_interpretation(
            total_severity=0.0,
            comparability_tier="TIER_1",
            n_degraded_axes=0,
            n_included_axes=4,
            confidence="REDUCED",
            warnings=[],
        )
        assert "INCOMPLETE_COVERAGE" in result["interpretation_flags"]
        assert "2 axis(es) excluded" in result["interpretation_summary"]

    def test_low_confidence_flag(self):
        result = build_interpretation(
            total_severity=2.0,
            comparability_tier="TIER_3",
            n_degraded_axes=3,
            n_included_axes=6,
            confidence="LOW_CONFIDENCE",
            warnings=[],
        )
        assert "LOW_CONFIDENCE_WARNING" in result["interpretation_flags"]

    def test_producer_country_flag(self):
        result = build_interpretation(
            total_severity=0.7,
            comparability_tier="TIER_2",
            n_degraded_axes=1,
            n_included_axes=6,
            confidence="REDUCED",
            warnings=["W-PRODUCER-INVERSION"],
        )
        assert "PRODUCER_COUNTRY" in result["interpretation_flags"]

    def test_interpretation_in_composite(self):
        """CompositeResult.to_dict() must include interpretation fields."""
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "interpretation_flags" in d
        assert "interpretation_summary" in d
        assert isinstance(d["interpretation_flags"], list)
        assert isinstance(d["interpretation_summary"], str)

    def test_tier_3_forces_warning_language(self):
        """TIER_3 or higher MUST produce warning text in summary."""
        result = build_interpretation(
            total_severity=2.5,
            comparability_tier="TIER_3",
            n_degraded_axes=3,
            n_included_axes=5,
            confidence="LOW_CONFIDENCE",
            warnings=[],
        )
        # Must contain explicit warning language
        summary = result["interpretation_summary"]
        assert "NOT valid" in summary or "WARNING" in summary

    def test_tier_4_forces_critical_warning(self):
        """TIER_4 MUST produce CRITICAL warning."""
        result = build_interpretation(
            total_severity=3.5,
            comparability_tier="TIER_4",
            n_degraded_axes=5,
            n_included_axes=6,
            confidence="LOW_CONFIDENCE",
            warnings=[],
        )
        assert "CRITICAL" in result["interpretation_summary"]


# ═══════════════════════════════════════════════════════════════
# PHASE 8 — VALIDATION HARDENING
# ═══════════════════════════════════════════════════════════════

class TestValidationHardening:
    """System must fail if mandatory fields are missing."""

    def test_valid_composite_passes(self):
        """Properly formed composite passes all validation."""
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        validate_composite_result(comp)  # should not raise

    def test_severity_analysis_present(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "severity_analysis" in d
        assert "total_severity" in d["severity_analysis"]

    def test_strict_comparability_tier_present(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "strict_comparability_tier" in d

    def test_composite_adjusted_present(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "composite_adjusted" in d

    def test_stability_analysis_present(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "stability_analysis" in d

    def test_interpretation_flags_present(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "interpretation_flags" in d
        assert "interpretation_summary" in d

    def test_degradation_severity_per_axis(self):
        """Every axis in composite output must have degradation_severity."""
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        for ad in d["axes"]:
            assert "degradation_severity" in ad


# ═══════════════════════════════════════════════════════════════
# INTEGRATION: EXAMPLE COUNTRY OUTPUTS
# ═══════════════════════════════════════════════════════════════

class TestExampleCountries:
    """End-to-end tests for representative countries."""

    def test_japan_clean(self):
        """Japan: mostly clean, should be TIER_1."""
        axes = [
            _valid(country="JP", axis_id=1, score=0.32, source="BIS_LBS"),
            _valid(country="JP", axis_id=2, score=0.45, source="COMTRADE"),
            _valid(country="JP", axis_id=3, score=0.28, source="COMTRADE"),
            _valid(country="JP", axis_id=4, score=0.15, source="SIPRI"),
            _valid(country="JP", axis_id=5, score=0.38, source="COMTRADE"),
            _a_only(country="JP", axis_id=6, score=0.68, source="ITF_OECD",
                    warnings=()),
        ]
        comp = compute_composite_v11(axes, "JP", "Japan", "PHASE1-7", "v1.1")
        d = comp.to_dict()

        # Structure checks
        assert d["composite_raw"] is not None
        assert d["composite_adjusted"] is not None
        assert d["strict_comparability_tier"] in ("TIER_1", "TIER_2")
        assert "stability_analysis" in d
        assert d["stability_analysis"]["stability_score"] > 0.0
        assert "interpretation_flags" in d
        assert "interpretation_summary" in d

    def test_china_degraded(self):
        """China: CPIS non-participant, producer inversion, sanctions-adjacent."""
        axes = [
            _a_only(country="CN", axis_id=1, score=0.22, source="BIS_LBS",
                    warnings=("F-CPIS-ABSENT",)),
            _degraded(country="CN", axis_id=2, score=0.05,
                      warnings=("W-PRODUCER-INVERSION",)),
            _a_only(country="CN", axis_id=3, score=0.18, source="COMTRADE",
                    warnings=("W-HS6-GRANULARITY",)),
            _degraded(country="CN", axis_id=4, score=0.02,
                      warnings=("W-PRODUCER-INVERSION",)),
            _degraded(country="CN", axis_id=5, score=0.03,
                      warnings=("W-PRODUCER-INVERSION",)),
            _a_only(country="CN", axis_id=6, score=0.42, source="ITF_OECD",
                    warnings=()),
        ]
        comp = compute_composite_v11(axes, "CN", "China", "PHASE1-7", "v1.1")
        d = comp.to_dict()

        # Must NOT be TIER_1 — too degraded
        assert d["strict_comparability_tier"] != "TIER_1"
        # Must have high total severity
        assert d["severity_analysis"]["total_severity"] > 1.0
        # Adjusted composite should differ from raw
        assert d["composite_adjusted"] != d["composite_raw"]
        # Must carry warning interpretation
        assert len(d["interpretation_flags"]) > 1
        # Must flag producer country
        assert "PRODUCER_COUNTRY" in d["interpretation_flags"]

    def test_cross_country_japan_vs_china(self):
        """Japan (clean) vs China (degraded) should trigger non-comparability
        if severity differential exceeds threshold."""
        jp_axes = [_valid(country="JP", axis_id=i, score=0.3, source="S")
                   for i in range(1, 7)]
        cn_axes = [
            _a_only(country="CN", axis_id=1, score=0.2, source="B",
                    warnings=("F-CPIS-ABSENT",)),
            _degraded(country="CN", axis_id=2, score=0.05,
                      warnings=("W-PRODUCER-INVERSION",)),
            _a_only(country="CN", axis_id=3, score=0.18, source="C",
                    warnings=("W-HS6-GRANULARITY",)),
            _degraded(country="CN", axis_id=4, score=0.02,
                      warnings=("W-PRODUCER-INVERSION",)),
            _degraded(country="CN", axis_id=5, score=0.03,
                      warnings=("W-PRODUCER-INVERSION",)),
            _a_only(country="CN", axis_id=6, score=0.4, source="D",
                    warnings=()),
        ]

        jp_comp = compute_composite_v11(jp_axes, "JP", "Japan", "P1", "v1.1")
        cn_comp = compute_composite_v11(cn_axes, "CN", "China", "P1", "v1.1")

        jp_sev = jp_comp.to_dict()["severity_analysis"]["total_severity"]
        cn_sev = cn_comp.to_dict()["severity_analysis"]["total_severity"]

        severities = {"JP": jp_sev, "CN": cn_sev}
        violations = check_cross_country_comparability(severities)

        # China is heavily degraded, Japan is clean — differential should be large
        diff = abs(jp_sev - cn_sev)
        if diff > CROSS_COUNTRY_SEVERITY_THRESHOLD:
            assert len(violations) == 1
            assert violations[0]["warning_code"] == "W-CROSS-COUNTRY-NONCOMPARABLE"


# ═══════════════════════════════════════════════════════════════
# REGRESSION: Existing fields preserved
# ═══════════════════════════════════════════════════════════════

class TestRegressionNewFieldsPreserved:
    """Ensure all new fields coexist with all old fields."""

    def test_axis_result_all_fields(self):
        r = _valid()
        d = r.to_dict()
        required = [
            "country", "axis_id", "axis_slug", "score", "basis",
            "validity", "coverage", "source", "warnings",
            "channel_a_concentration", "channel_b_concentration",
            "data_quality_flags", "degradation_severity",
        ]
        for key in required:
            assert key in d, f"Missing: {key}"

    def test_composite_result_all_fields(self):
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        required = [
            "country", "country_name", "isi_composite",
            "composite_raw", "composite_adjusted",
            "classification", "axes_included", "axes_excluded",
            "confidence", "comparability_tier",
            "strict_comparability_tier", "severity_analysis",
            "structural_degradation_profile", "structural_class",
            "stability_analysis",
            "interpretation_flags", "interpretation_summary",
            "scope", "methodology_version", "warnings", "axes",
        ]
        for key in required:
            assert key in d, f"Missing: {key}"


# ═══════════════════════════════════════════════════════════════
# CORRECTION PASS — ISSUE 1: DEPENDENCY-AWARE SEVERITY
# ═══════════════════════════════════════════════════════════════

class TestDegradationGroups:
    """Verify group-aware severity resolution prevents double counting."""

    def test_cpis_and_single_channel_a_not_double_counted(self):
        """CPIS_NON_PARTICIPANT + SINGLE_CHANNEL_A are both CHANNEL_LOSS.
        Should take max(0.5, 0.4) = 0.5, NOT sum = 0.9."""
        sev = compute_axis_severity(["CPIS_NON_PARTICIPANT", "SINGLE_CHANNEL_A"])
        assert abs(sev - 0.5) < 1e-9, f"Expected 0.5, got {sev}"

    def test_cpis_alone_equals_cpis(self):
        """Single flag in group → just that weight."""
        sev = compute_axis_severity(["CPIS_NON_PARTICIPANT"])
        assert abs(sev - 0.5) < 1e-9

    def test_single_channel_a_and_b_not_double_counted(self):
        """Both channel losses in same group → max(0.4, 0.4) = 0.4."""
        sev = compute_axis_severity(["SINGLE_CHANNEL_A", "SINGLE_CHANNEL_B"])
        assert abs(sev - 0.4) < 1e-9

    def test_different_groups_sum(self):
        """Flags in different groups should still sum."""
        # CHANNEL_LOSS(max=0.4) + STRUCTURAL_BIAS(0.7) = 1.1
        sev = compute_axis_severity(["SINGLE_CHANNEL_A", "PRODUCER_INVERSION"])
        assert abs(sev - 1.1) < 1e-9

    def test_hs6_and_temporal_same_group(self):
        """REDUCED_PRODUCT_GRANULARITY and TEMPORAL_MISMATCH are both
        DATA_GRANULARITY → max(0.2, 0.3) = 0.3."""
        sev = compute_axis_severity(["REDUCED_PRODUCT_GRANULARITY", "TEMPORAL_MISMATCH"])
        assert abs(sev - 0.3) < 1e-9

    def test_all_groups_compound_severity(self):
        """One flag from each of 5 groups → sum of 5 max values."""
        flags = [
            "SINGLE_CHANNEL_A",             # CHANNEL_LOSS: 0.4
            "REDUCED_PRODUCT_GRANULARITY",   # DATA_GRANULARITY: 0.2
            "PRODUCER_INVERSION",            # STRUCTURAL_BIAS: 0.7
            "SANCTIONS_DISTORTION",          # DATA_VALIDITY: 1.0
            "ZERO_BILATERAL_SUPPLIERS",      # CONSTRUCT_AMBIGUITY: 0.6
        ]
        sev = compute_axis_severity(flags)
        expected = 0.4 + 0.2 + 0.7 + 1.0 + 0.6  # = 2.9
        assert abs(sev - expected) < 1e-9

    def test_group_resolution_in_breakdown(self):
        """Breakdown should show group_resolution metadata."""
        flags = ["CPIS_NON_PARTICIPANT", "SINGLE_CHANNEL_A"]
        b = compute_axis_severity_breakdown(flags)
        assert "group_resolution" in b
        gr = b["group_resolution"]
        assert "CHANNEL_LOSS" in gr
        assert gr["CHANNEL_LOSS"]["max_weight"] == 0.5
        assert gr["CHANNEL_LOSS"]["representative_flag"] == "CPIS_NON_PARTICIPANT"
        # Total should be 0.5 (max of group), not 0.9 (sum)
        assert abs(b["total"] - 0.5) < 1e-9

    def test_breakdown_shows_all_individual_weights(self):
        """Even shadowed flags appear with their individual weights."""
        flags = ["CPIS_NON_PARTICIPANT", "SINGLE_CHANNEL_A"]
        b = compute_axis_severity_breakdown(flags)
        assert b["CPIS_NON_PARTICIPANT"] == 0.5
        assert b["SINGLE_CHANNEL_A"] == 0.4

    def test_china_severity_lower_with_groups(self):
        """China's real flag pattern should produce LOWER severity
        than naive sum due to CHANNEL_LOSS group dedup."""
        # China Axis 1: CPIS_NON_PARTICIPANT + SINGLE_CHANNEL_A
        # Old: 0.5 + 0.4 = 0.9
        # New: max(0.5, 0.4) = 0.5
        flags = ["CPIS_NON_PARTICIPANT", "SINGLE_CHANNEL_A"]
        sev = compute_axis_severity(flags)
        naive_sum = 0.5 + 0.4
        assert sev < naive_sum, "Group dedup should reduce severity"
        assert abs(sev - 0.5) < 1e-9


# ═══════════════════════════════════════════════════════════════
# CORRECTION PASS — ISSUE 2: NONLINEAR (EXPONENTIAL) PENALTY
# ═══════════════════════════════════════════════════════════════

class TestExponentialPenalty:
    """Verify exponential weight penalty replaces linear."""

    def test_clean_weight_is_one(self):
        """severity=0 → weight = exp(0) = 1.0."""
        import math
        from backend.severity import AGGREGATION_ALPHA
        w = max(math.exp(-AGGREGATION_ALPHA * 0.0), 0.1)
        assert abs(w - 1.0) < 1e-9

    def test_moderate_severity_penalty(self):
        """severity=0.5 → weight = exp(-0.6) ≈ 0.549."""
        import math
        from backend.severity import AGGREGATION_ALPHA
        w = max(math.exp(-AGGREGATION_ALPHA * 0.5), 0.1)
        assert 0.5 < w < 0.6  # tighter than linear's 0.75

    def test_high_severity_strong_penalty(self):
        """severity=1.0 → weight = exp(-1.2) ≈ 0.301."""
        import math
        from backend.severity import AGGREGATION_ALPHA
        w = max(math.exp(-AGGREGATION_ALPHA * 1.0), 0.1)
        assert 0.25 < w < 0.35  # much stricter than linear's 0.5

    def test_extreme_severity_hits_floor(self):
        """severity=3.0 → weight = exp(-3.6) ≈ 0.027 → clamped to 0.1."""
        import math
        from backend.severity import AGGREGATION_ALPHA, AGGREGATION_MIN_WEIGHT
        raw_w = math.exp(-AGGREGATION_ALPHA * 3.0)
        assert raw_w < AGGREGATION_MIN_WEIGHT
        # Verify compute_adjusted_composite applies the floor
        scores = [(0.5, 3.0)]
        adj = compute_adjusted_composite(scores)
        assert adj is not None
        assert abs(adj - 0.5) < 1e-8  # single axis, weight is floor, score unchanged

    def test_exponential_steeper_than_linear_at_midrange(self):
        """At severity=0.6, exponential weight < linear weight.
        Linear: max(1.0 - 0.6*0.5, 0.1) = 0.7
        Exponential: exp(-1.2 * 0.6) ≈ 0.487"""
        import math
        from backend.severity import AGGREGATION_ALPHA
        linear_w = max(1.0 - 0.6 * 0.5, 0.1)
        exp_w = max(math.exp(-AGGREGATION_ALPHA * 0.6), 0.1)
        assert exp_w < linear_w, "Exponential should be stricter at midrange"

    def test_adjusted_equal_raw_when_clean(self):
        """All clean axes → adjusted == raw."""
        scores = [(0.3, 0.0)] * 6
        adj = compute_adjusted_composite(scores)
        assert adj is not None
        assert abs(adj - 0.3) < 1e-8

    def test_degraded_more_penalized_than_before(self):
        """Heavily degraded axis with high score should be more
        de-weighted under exponential than under linear."""
        import math
        from backend.severity import AGGREGATION_ALPHA
        # One clean axis at 0.2, one degraded at 0.9 with severity=1.0
        scores = [(0.2, 0.0), (0.9, 1.0)]
        adj = compute_adjusted_composite(scores)
        # Linear would give: (0.2*1.0 + 0.9*0.5) / (1.0+0.5) ≈ 0.4333
        # Exponential: (0.2*1.0 + 0.9*exp(-1.2)) / (1.0+exp(-1.2))
        w_deg = math.exp(-AGGREGATION_ALPHA * 1.0)
        exp_expected = (0.2 * 1.0 + 0.9 * w_deg) / (1.0 + w_deg)
        linear_expected = (0.2 * 1.0 + 0.9 * 0.5) / (1.0 + 0.5)
        assert adj is not None
        assert abs(adj - round(exp_expected, 8)) < 1e-8
        assert adj < linear_expected, "Exponential should pull adjusted lower"


# ═══════════════════════════════════════════════════════════════
# CORRECTION PASS — ISSUE 3: DUAL-CONDITION COMPARABILITY GUARD
# ═══════════════════════════════════════════════════════════════

class TestDualConditionGuard:
    """Verify dual-condition (ratio + diff) cross-country check."""

    def test_ratio_catches_low_severity_disparity(self):
        """0.0 vs 0.5 — diff only 0.5 (< 1.5) but ratio ≈ 10.0 (> 3.0).
        The old diff-only check would miss this."""
        violations = check_cross_country_comparability({"US": 0.0, "JP": 0.5})
        assert len(violations) == 1
        assert "RATIO" in violations[0]["trigger"]

    def test_diff_catches_high_severity_pair(self):
        """2.0 vs 3.6 — ratio ≈ 1.76 (< 3.0) but diff = 1.6 (> 1.5).
        Ratio alone would miss this."""
        violations = check_cross_country_comparability({"US": 2.0, "CN": 3.6})
        assert len(violations) == 1
        assert "DIFF" in violations[0]["trigger"]

    def test_both_conditions_trigger(self):
        """0.0 vs 4.0 — diff=4.0 > 1.5 AND ratio=80.0 > 3.0."""
        violations = check_cross_country_comparability({"US": 0.0, "RU": 4.0})
        assert len(violations) == 1
        assert "DIFF" in violations[0]["trigger"]
        assert "RATIO" in violations[0]["trigger"]

    def test_neither_condition_triggers(self):
        """0.5 vs 0.8 — diff=0.3 < 1.5, ratio=0.8/0.55≈1.45 < 3.0."""
        violations = check_cross_country_comparability({"US": 0.5, "GB": 0.8})
        assert len(violations) == 0

    def test_symmetric_behavior(self):
        """Order doesn't matter — violations are symmetric."""
        v1 = check_cross_country_comparability({"A": 0.0, "B": 2.0})
        v2 = check_cross_country_comparability({"B": 2.0, "A": 0.0})
        assert len(v1) == len(v2)

    def test_violation_includes_ratio_field(self):
        """Violation dict must include severity_ratio."""
        violations = check_cross_country_comparability({"US": 0.0, "RU": 3.0})
        assert len(violations) == 1
        v = violations[0]
        assert "severity_ratio" in v
        assert "trigger" in v
        assert v["severity_ratio"] > 3.0

    def test_similar_moderate_severities_no_violation(self):
        """1.0 vs 1.2 — diff=0.2 < 1.5, ratio=1.2/1.05≈1.14 < 3.0."""
        violations = check_cross_country_comparability({"US": 1.0, "GB": 1.2})
        assert len(violations) == 0


# ═══════════════════════════════════════════════════════════════
# CORRECTION PASS — ISSUE 4: STRUCTURAL CLASS SYSTEM
# ═══════════════════════════════════════════════════════════════

class TestStructuralClass:
    """Structural class classification (IMPORTER/BALANCED/PRODUCER)."""

    def test_japan_is_importer(self):
        """Japan is NOT a major exporter on any axis → IMPORTER."""
        from backend.severity import classify_structural_class
        axes = [_valid(country="JP", axis_id=i).to_dict() for i in range(1, 7)]
        sc = classify_structural_class("JP", axes)
        assert sc["structural_class"] == "IMPORTER"
        assert sc["n_producer_inverted"] == 0

    def test_us_is_producer(self):
        """US is a top exporter on axes 2 and 4 → PRODUCER."""
        from backend.severity import classify_structural_class
        axes = [_valid(country="US", axis_id=i).to_dict() for i in range(1, 7)]
        sc = classify_structural_class("US", axes)
        assert sc["structural_class"] == "PRODUCER"
        assert sc["n_producer_inverted"] >= 2
        assert "energy" in sc["producer_inverted_axes"]
        assert "defense" in sc["producer_inverted_axes"]

    def test_australia_is_producer(self):
        """Australia: top exporter on axes 2 and 5 → PRODUCER."""
        from backend.severity import classify_structural_class
        axes = [_valid(country="AU", axis_id=i).to_dict() for i in range(1, 7)]
        sc = classify_structural_class("AU", axes)
        assert sc["structural_class"] == "PRODUCER"
        assert sc["n_producer_inverted"] >= 2

    def test_norway_is_balanced(self):
        """Norway: top exporter only on axis 2 → BALANCED."""
        from backend.severity import classify_structural_class
        axes = [_valid(country="NO", axis_id=i).to_dict() for i in range(1, 7)]
        sc = classify_structural_class("NO", axes)
        assert sc["structural_class"] == "BALANCED"
        assert sc["n_producer_inverted"] == 1

    def test_china_is_producer(self):
        """China: top exporter on axes 4 and 5 → PRODUCER."""
        from backend.severity import classify_structural_class
        axes = [_valid(country="CN", axis_id=i).to_dict() for i in range(1, 7)]
        sc = classify_structural_class("CN", axes)
        assert sc["structural_class"] == "PRODUCER"
        assert sc["n_producer_inverted"] >= 2

    def test_structural_class_in_composite(self):
        """CompositeResult.to_dict() must include structural_class."""
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "structural_class" in d
        sc = d["structural_class"]
        assert "structural_class" in sc
        assert "n_producer_inverted" in sc
        assert "producer_inverted_axes" in sc

    def test_invalid_axes_excluded_from_classification(self):
        """INVALID axes should not count toward producer inversion."""
        from backend.severity import classify_structural_class
        axes_data = []
        for i in range(1, 7):
            if i in (2, 4):
                axes_data.append(make_invalid_axis("US", i, "NONE").to_dict())
            else:
                axes_data.append(_valid(country="US", axis_id=i).to_dict())
        sc = classify_structural_class("US", axes_data)
        # Axes 2 and 4 are INVALID → no producer inversion → IMPORTER
        assert sc["structural_class"] == "IMPORTER"


class TestStructuralClassComparability:
    """Cross-class comparability enforcement."""

    def test_producer_vs_importer_violation(self):
        """PRODUCER vs IMPORTER → W-STRUCTURAL-CLASS-NONCOMPARABLE."""
        from backend.severity import check_structural_class_comparability
        classes = {"US": "PRODUCER", "JP": "IMPORTER"}
        violations = check_structural_class_comparability(classes)
        assert len(violations) == 1
        assert violations[0]["warning_code"] == "W-STRUCTURAL-CLASS-NONCOMPARABLE"

    def test_same_class_no_violation(self):
        """PRODUCER vs PRODUCER → no violation."""
        from backend.severity import check_structural_class_comparability
        classes = {"US": "PRODUCER", "CN": "PRODUCER"}
        violations = check_structural_class_comparability(classes)
        assert len(violations) == 0

    def test_balanced_pairs_no_violation(self):
        """BALANCED vs IMPORTER or BALANCED vs PRODUCER → no violation."""
        from backend.severity import check_structural_class_comparability
        classes = {"NO": "BALANCED", "JP": "IMPORTER", "US": "PRODUCER"}
        violations = check_structural_class_comparability(classes)
        # Only US(PRODUCER) vs JP(IMPORTER) should trigger
        assert len(violations) == 1
        v = violations[0]
        pair = frozenset({v["country_a"], v["country_b"]})
        assert pair == frozenset({"US", "JP"})

    def test_empty_input(self):
        from backend.severity import check_structural_class_comparability
        assert check_structural_class_comparability({}) == []

    def test_single_country_no_violation(self):
        from backend.severity import check_structural_class_comparability
        assert check_structural_class_comparability({"US": "PRODUCER"}) == []


# ═════════════════════════════════════════════════════════════
# METHODOLOGY SPECIFICATION VALIDATION — Data/Structural Separation
# ═════════════════════════════════════════════════════════════

class TestDataSeveritySeparation:
    """Validate that structural severity (PRODUCER_INVERSION) does NOT
    affect aggregation weights, while data reliability severity does.

    This implements the formal requirement from ISI_METHODOLOGY_SPECIFICATION.md
    Section 1.4: "Structural severity MUST NOT enter the weight function."
    """

    def test_data_severity_excludes_producer_inversion(self):
        """compute_axis_data_severity excludes PRODUCER_INVERSION."""
        from backend.severity import compute_axis_data_severity
        flags = ["PRODUCER_INVERSION"]
        assert compute_axis_data_severity(flags) == 0.0

    def test_total_severity_includes_producer_inversion(self):
        """compute_axis_severity includes PRODUCER_INVERSION."""
        sev = compute_axis_severity(["PRODUCER_INVERSION"])
        assert sev == 0.7

    def test_data_severity_preserves_data_flags(self):
        """Data reliability flags are fully counted in data severity."""
        from backend.severity import compute_axis_data_severity
        assert compute_axis_data_severity(["SINGLE_CHANNEL_A"]) == 0.4
        assert compute_axis_data_severity(["CPIS_NON_PARTICIPANT"]) == 0.5
        assert compute_axis_data_severity(["SANCTIONS_DISTORTION"]) == 1.0

    def test_mixed_flags_data_vs_total(self):
        """Mixed data + structural flags: data_severity < total_severity."""
        from backend.severity import compute_axis_data_severity
        flags = ["SINGLE_CHANNEL_A", "PRODUCER_INVERSION"]
        total = compute_axis_severity(flags)
        data = compute_axis_data_severity(flags)
        # SINGLE_CHANNEL_A(0.4) + PRODUCER_INVERSION(0.7) = 1.1 total
        # But groups: CHANNEL_LOSS(max=0.4) + STRUCTURAL_BIAS(max=0.7)
        assert total == round(0.4 + 0.7, ROUND_PRECISION)
        # Data-only: CHANNEL_LOSS(max=0.4), structural excluded
        assert data == 0.4
        assert data < total

    def test_data_severity_group_resolution(self):
        """Data severity still applies group resolution for data flags."""
        from backend.severity import compute_axis_data_severity
        # CPIS(0.5) and SINGLE_CHANNEL_A(0.4) are in CHANNEL_LOSS group
        flags = ["CPIS_NON_PARTICIPANT", "SINGLE_CHANNEL_A"]
        data = compute_axis_data_severity(flags)
        assert data == 0.5  # max within group, not sum

    def test_invalid_axis_data_severity_zero(self):
        """INVALID_AXIS returns 0.0 for data severity."""
        from backend.severity import compute_axis_data_severity
        assert compute_axis_data_severity(["INVALID_AXIS"]) == 0.0

    def test_structural_flags_constant_defined(self):
        """STRUCTURAL_FLAGS is defined and contains PRODUCER_INVERSION."""
        from backend.severity import STRUCTURAL_FLAGS
        assert "PRODUCER_INVERSION" in STRUCTURAL_FLAGS

    def test_axis_result_to_dict_includes_data_severity(self):
        """AxisResult.to_dict() now includes data_severity field."""
        ar = _valid(
            country="US", axis_id=2, score=0.3, basis="BOTH",
            validity="DEGRADED",
            warnings=("W-PRODUCER-INVERSION",),
        )
        d = ar.to_dict()
        assert "data_severity" in d
        assert "degradation_severity" in d
        # Producer inversion → total > data
        assert d["degradation_severity"] > d["data_severity"]
        # data_severity should be 0.0 (only structural flag present)
        assert d["data_severity"] == 0.0

    def test_adjusted_composite_uses_data_severity_not_total(self):
        """The adjusted composite weights axes by data severity ONLY.

        A producer-inverted axis with clean data should get full weight (1.0)
        in the adjusted composite, because PRODUCER_INVERSION is structural.
        """
        import math
        from backend.severity import AGGREGATION_ALPHA, AGGREGATION_MIN_WEIGHT

        # Create 5 clean axes + 1 producer-inverted-only axis
        axes = []
        for i in range(1, 6):
            axes.append(_valid(country="US", axis_id=i, score=0.4,
                               basis="BOTH", validity="VALID"))
        # Axis 2: producer-inverted with clean data
        axes[1] = _valid(
            country="US", axis_id=2, score=0.1,
            basis="BOTH", validity="DEGRADED",
            warnings=("W-PRODUCER-INVERSION",),
        )
        # Axis 6
        axes.append(_valid(country="US", axis_id=6, score=0.4,
                           basis="BOTH", validity="VALID"))

        # Build composite
        axis_dicts = [a.to_dict() for a in axes]
        included_scores_data_sev = []
        for ad in axis_dicts:
            if ad["validity"] != "INVALID" and ad["score"] is not None:
                included_scores_data_sev.append(
                    (ad["score"], ad["data_severity"])
                )

        adj = compute_adjusted_composite(included_scores_data_sev)

        # With data severity only, the producer-inverted axis has
        # data_severity=0.0, so its weight = exp(-1.2*0) = 1.0.
        # All axes get full weight → adjusted == raw
        raw = sum(s for s, _ in included_scores_data_sev) / len(included_scores_data_sev)
        assert adj == round(raw, ROUND_PRECISION)

    def test_adjusted_composite_differs_with_data_degradation(self):
        """An axis with actual data degradation gets reduced weight."""
        import math
        from backend.severity import AGGREGATION_ALPHA, AGGREGATION_MIN_WEIGHT

        # 5 clean axes at 0.5 + 1 channel-degraded axis at 0.9
        axes = []
        for i in range(1, 6):
            axes.append(_valid(country="JP", axis_id=i, score=0.5,
                               basis="BOTH", validity="VALID"))
        axes.append(_valid(country="JP", axis_id=6, score=0.9,
                           basis="A_ONLY", validity="A_ONLY",
                           warnings=()))

        axis_dicts = [a.to_dict() for a in axes]
        included_scores_data_sev = []
        for ad in axis_dicts:
            if ad["validity"] != "INVALID" and ad["score"] is not None:
                included_scores_data_sev.append(
                    (ad["score"], ad["data_severity"])
                )

        adj = compute_adjusted_composite(included_scores_data_sev)
        raw = sum(s for s, _ in included_scores_data_sev) / len(included_scores_data_sev)

        # Axis 6 has SINGLE_CHANNEL_A → data_severity = 0.4 → weight < 1.0
        # So adjusted composite should differ from raw
        assert adj != round(raw, ROUND_PRECISION)
        # The degraded axis (0.9) is above raw mean (≈0.567),
        # so downweighting it should pull adjusted below raw
        assert adj < round(raw, ROUND_PRECISION)

    def test_producer_only_axis_full_weight_in_composite(self):
        """A producer-inverted axis with no data issues receives
        weight = 1.0 in the composite output."""
        import math
        from backend.severity import AGGREGATION_ALPHA

        # All axes clean, axis 2 is producer-inverted but data is fine
        axes = [
            _valid(country="NO", axis_id=1, score=0.3),
            _valid(country="NO", axis_id=2, score=0.05,
                   basis="BOTH", validity="DEGRADED",
                   warnings=("W-PRODUCER-INVERSION",)),
            _valid(country="NO", axis_id=3, score=0.4),
            _valid(country="NO", axis_id=4, score=0.5),
            _valid(country="NO", axis_id=5, score=0.35),
            _valid(country="NO", axis_id=6, score=0.45),
        ]

        # Compute via CompositeResult to test the full pipeline
        result = compute_composite_v11(
            axes, "NO", "Norway", "PHASE1-7", "v1.1",
        )
        d = result.to_dict()

        # raw == adjusted because all data_severity == 0.0
        # (producer inversion is structural, not data)
        assert d["composite_raw"] == d["composite_adjusted"]
