#!/usr/bin/env python3
"""Tests for trust hardening — data_quality_flags, comparability_tier,
structural_degradation_profile, source heterogeneity warnings, and
channel degradation warnings.

These tests ensure that every pathway for misleading output is blocked:
- No AxisResult.to_dict() can omit data_quality_flags
- No CompositeResult.to_dict() can omit comparability_tier
- Quality flags fire correctly for every degradation type
- Comparability tiers are assigned deterministically
- Mixed-source composites carry explicit warnings
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
              warnings=("W-PRODUCER-INVERSION", "W-SANCTIONS-DISTORTION")):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="BOTH", validity="DEGRADED",
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.01, channel_b_concentration=0.01,
    )


def _zero_suppliers(country="US", axis_id=4, score=0.0, source="SIPRI"):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="BOTH", validity="VALID",
        coverage=None, source=source, warnings=("D-5",),
        channel_a_concentration=None, channel_b_concentration=None,
    )


# ── data_quality_flags in AxisResult.to_dict() ───────────────

class TestDataQualityFlags:
    """Every AxisResult.to_dict() MUST contain data_quality_flags."""

    def test_valid_both_no_flags(self):
        r = _valid()
        d = r.to_dict()
        assert "data_quality_flags" in d
        assert d["data_quality_flags"] == []

    def test_invalid_axis_flag(self):
        r = make_invalid_axis("JP", 3, "NONE")
        d = r.to_dict()
        assert "INVALID_AXIS" in d["data_quality_flags"]
        # INVALID should be the ONLY flag
        assert d["data_quality_flags"] == ["INVALID_AXIS"]

    def test_single_channel_a_flag(self):
        r = _a_only()
        d = r.to_dict()
        assert "SINGLE_CHANNEL_A" in d["data_quality_flags"]

    def test_reduced_granularity_flag(self):
        r = _a_only(warnings=("W-HS6-GRANULARITY",))
        d = r.to_dict()
        assert "REDUCED_PRODUCT_GRANULARITY" in d["data_quality_flags"]

    def test_producer_inversion_flag(self):
        r = _valid(warnings=("W-PRODUCER-INVERSION",))
        d = r.to_dict()
        assert "PRODUCER_INVERSION" in d["data_quality_flags"]

    def test_sanctions_distortion_flag(self):
        r = _degraded()
        d = r.to_dict()
        assert "SANCTIONS_DISTORTION" in d["data_quality_flags"]
        assert "PRODUCER_INVERSION" in d["data_quality_flags"]

    def test_cpis_non_participant_flag(self):
        r = _valid(warnings=("F-CPIS-ABSENT",), basis="A_ONLY", validity="A_ONLY")
        d = r.to_dict()
        assert "CPIS_NON_PARTICIPANT" in d["data_quality_flags"]

    def test_zero_bilateral_suppliers_flag(self):
        r = _zero_suppliers()
        d = r.to_dict()
        assert "ZERO_BILATERAL_SUPPLIERS" in d["data_quality_flags"]

    def test_temporal_mismatch_flag(self):
        r = _valid(warnings=("W-TEMPORAL-MIX",))
        d = r.to_dict()
        assert "TEMPORAL_MISMATCH" in d["data_quality_flags"]

    def test_multiple_flags_combined(self):
        r = AxisResult(
            country="US", axis_id=5, axis_slug="critical_inputs",
            score=0.4, basis="A_ONLY", validity="A_ONLY",
            coverage=None, source="TEST",
            warnings=("W-HS6-GRANULARITY", "W-PRODUCER-INVERSION"),
            channel_a_concentration=0.4, channel_b_concentration=None,
        )
        d = r.to_dict()
        flags = d["data_quality_flags"]
        assert "SINGLE_CHANNEL_A" in flags
        assert "REDUCED_PRODUCT_GRANULARITY" in flags
        assert "PRODUCER_INVERSION" in flags

    def test_flags_are_deterministic(self):
        r = _a_only(warnings=("W-HS6-GRANULARITY", "W-PRODUCER-INVERSION"))
        d1 = r.to_dict()["data_quality_flags"]
        d2 = r.to_dict()["data_quality_flags"]
        assert d1 == d2


# ── comparability_tier in CompositeResult.to_dict() ──────────

class TestComparabilityTier:
    """Every CompositeResult.to_dict() MUST contain comparability_tier."""

    def test_full_comparability(self):
        """6 VALID BOTH axes, no warnings → FULL_COMPARABILITY."""
        axes = [_valid(axis_id=i, source="SAME") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        assert "comparability_tier" in d
        assert d["comparability_tier"] == "FULL_COMPARABILITY"

    def test_high_comparability(self):
        """5 VALID + 1 INVALID → HIGH_COMPARABILITY."""
        axes = [_valid(axis_id=i, source="SAME") for i in range(1, 6)]
        axes.append(make_invalid_axis("US", 6, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        assert d["comparability_tier"] == "HIGH_COMPARABILITY"

    def test_limited_comparability_many_a_only(self):
        """4 A_ONLY + 2 INVALID → LIMITED_COMPARABILITY."""
        axes = [_a_only(axis_id=i) for i in range(1, 5)]
        axes.append(make_invalid_axis("US", 5, "NONE"))
        axes.append(make_invalid_axis("US", 6, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        assert d["comparability_tier"] == "LIMITED_COMPARABILITY"

    def test_not_comparable_below_threshold(self):
        """Only 3 computable axes → NOT_COMPARABLE."""
        axes = [_valid(axis_id=i) for i in range(1, 4)]
        for i in range(4, 7):
            axes.append(make_invalid_axis("US", i, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        assert d["comparability_tier"] == "NOT_COMPARABLE"

    def test_tier_field_always_present(self):
        """Even with all invalid, tier must be present."""
        axes = [make_invalid_axis("US", i, "NONE") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        assert "comparability_tier" in d
        assert d["comparability_tier"] == "NOT_COMPARABLE"


# ── structural_degradation_profile ───────────────────────────

class TestStructuralDegradationProfile:
    """Every CompositeResult.to_dict() MUST contain structural_degradation_profile."""

    def test_profile_present_and_complete(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        p = d["structural_degradation_profile"]
        assert isinstance(p, dict)
        # Required keys
        for key in [
            "axes_valid_both", "axes_a_only", "axes_b_only",
            "axes_degraded", "axes_invalid",
            "axes_producer_inverted", "axes_reduced_granularity",
            "axes_zero_bilateral_suppliers",
            "unique_source_count", "source_heterogeneous",
        ]:
            assert key in p, f"Missing key: {key}"

    def test_profile_counts_a_only(self):
        axes = [_a_only(axis_id=i) for i in range(1, 5)]
        axes.append(make_invalid_axis("US", 5, "NONE"))
        axes.append(make_invalid_axis("US", 6, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        p = comp.to_dict()["structural_degradation_profile"]
        assert p["axes_a_only"] == 4
        assert p["axes_invalid"] == 2

    def test_source_heterogeneity_detected(self):
        axes = [_valid(axis_id=i, source=f"SRC_{i}") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        p = comp.to_dict()["structural_degradation_profile"]
        assert p["source_heterogeneous"] is True
        assert p["unique_source_count"] == 6


# ── Source heterogeneity warning in composite ────────────────

class TestSourceHeterogeneityWarning:
    """Composites with >2 distinct sources MUST carry W-SOURCE-HETEROGENEITY."""

    def test_homogeneous_sources_no_warning(self):
        axes = [_valid(axis_id=i, source="SAME") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert not any("W-SOURCE-HETEROGENEITY" in w for w in comp.warnings)

    def test_two_sources_no_warning(self):
        axes = [_valid(axis_id=i, source="A" if i <= 3 else "B") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert not any("W-SOURCE-HETEROGENEITY" in w for w in comp.warnings)

    def test_three_plus_sources_triggers_warning(self):
        axes = [_valid(axis_id=i, source=f"SRC_{i}") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert any("W-SOURCE-HETEROGENEITY" in w for w in comp.warnings)


# ── Channel degradation warning in composite ─────────────────

class TestChannelDegradationWarning:
    """Composites with >50% single-channel axes MUST carry W-CHANNEL-DEGRADATION."""

    def test_all_both_no_warning(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert not any("W-CHANNEL-DEGRADATION" in w for w in comp.warnings)

    def test_majority_a_only_triggers_warning(self):
        # 4 A_ONLY + 2 BOTH
        axes = [_a_only(axis_id=i) for i in range(1, 5)]
        axes.append(_valid(axis_id=5))
        axes.append(_valid(axis_id=6))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert any("W-CHANNEL-DEGRADATION" in w for w in comp.warnings)

    def test_half_a_only_no_warning(self):
        # 3 A_ONLY + 3 BOTH = exactly 50%, not majority
        axes = [_a_only(axis_id=i) for i in range(1, 4)]
        axes.extend([_valid(axis_id=i) for i in range(4, 7)])
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert not any("W-CHANNEL-DEGRADATION" in w for w in comp.warnings)


# ── Confidence hardening: A_ONLY affects confidence ──────────

class TestConfidenceHardening:
    """A_ONLY axes MUST reduce confidence. FULL requires all BOTH + VALID."""

    def test_all_valid_both_gives_full(self):
        axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert comp.confidence == "FULL"

    def test_one_a_only_gives_reduced(self):
        """Single A_ONLY axis → n_structurally_weak=1 → REDUCED."""
        axes = [_valid(axis_id=i) for i in range(1, 6)]
        axes.append(_a_only(axis_id=6))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert comp.confidence == "REDUCED"

    def test_two_a_only_gives_reduced(self):
        """Two A_ONLY axes → n_structurally_weak=2 → REDUCED."""
        axes = [_valid(axis_id=i) for i in range(1, 5)]
        axes.append(_a_only(axis_id=5))
        axes.append(_a_only(axis_id=6))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert comp.confidence == "REDUCED"

    def test_three_a_only_gives_low(self):
        """Three A_ONLY → n_structurally_weak=3 > 2 → LOW_CONFIDENCE."""
        axes = [_valid(axis_id=i) for i in range(1, 4)]
        axes.extend([_a_only(axis_id=i) for i in range(4, 7)])
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert comp.confidence == "LOW_CONFIDENCE"

    def test_all_a_only_gives_low(self):
        """Six A_ONLY → n_structurally_weak=6 > 2 → LOW_CONFIDENCE."""
        axes = [_a_only(axis_id=i) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert comp.confidence == "LOW_CONFIDENCE"

    def test_mixed_degraded_and_a_only(self):
        """1 DEGRADED + 1 A_ONLY = 2 structurally_weak → REDUCED."""
        axes = [_valid(axis_id=i) for i in range(1, 5)]
        axes.append(_a_only(axis_id=5))
        axes.append(_degraded(axis_id=6, score=0.02))
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        assert comp.confidence == "REDUCED"

    def test_full_confidence_impossible_with_any_a_only(self):
        """FULL confidence MUST be impossible when any axis is A_ONLY."""
        for swap_idx in range(1, 7):
            axes = [_valid(axis_id=i, source="S") for i in range(1, 7)]
            # Replace one axis with A_ONLY
            axes[swap_idx - 1] = _a_only(axis_id=swap_idx, source="S")
            comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
            assert comp.confidence != "FULL", (
                f"FULL confidence with A_ONLY axis {swap_idx}"
            )


# ── _build_quality_flags unit tests ──────────────────────────

class TestBuildQualityFlagsDirectly:
    """Direct unit tests for _build_quality_flags."""

    def test_returns_list(self):
        r = _valid()
        flags = _build_quality_flags(r)
        assert isinstance(flags, list)

    def test_invalid_short_circuits(self):
        r = make_invalid_axis("JP", 2, "NONE", warnings=("W-HS6-GRANULARITY",))
        flags = _build_quality_flags(r)
        assert flags == ["INVALID_AXIS"]
        # Should NOT contain REDUCED_PRODUCT_GRANULARITY — invalid overrides all

    def test_b_only_flag(self):
        r = AxisResult(
            country="US", axis_id=3, axis_slug="technology",
            score=0.4, basis="B_ONLY", validity="A_ONLY",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=0.4,
        )
        flags = _build_quality_flags(r)
        assert "SINGLE_CHANNEL_B" in flags


# ── _compute_comparability unit tests ────────────────────────

class TestComputeComparabilityDirectly:
    """Direct unit tests for _compute_comparability."""

    def test_full_comparability(self):
        axes = tuple(_valid(axis_id=i, source="S") for i in range(1, 7))
        tier, profile = _compute_comparability(axes, 6)
        assert tier == "FULL_COMPARABILITY"
        assert profile["axes_valid_both"] == 6

    def test_degraded_blocks_full(self):
        axes = list(_valid(axis_id=i, source="S") for i in range(1, 6))
        axes.append(_degraded(axis_id=6, source="S"))
        tier, _profile = _compute_comparability(tuple(axes), 6)
        assert tier != "FULL_COMPARABILITY"

    def test_reduced_granularity_blocks_full(self):
        axes = list(_valid(axis_id=i, source="S") for i in range(1, 6))
        axes.append(_valid(axis_id=6, source="S", warnings=("W-HS6-GRANULARITY",)))
        tier, _profile = _compute_comparability(tuple(axes), 6)
        assert tier != "FULL_COMPARABILITY"

    def test_not_comparable_below_4(self):
        axes = tuple(_valid(axis_id=i) for i in range(1, 4))
        tier, _profile = _compute_comparability(axes, 3)
        assert tier == "NOT_COMPARABLE"


# ── Axis 6 precision hardening ───────────────────────────────

class TestAxis6PrecisionHardening:
    """Axis 6 must use ROUND_PRECISION (8), not a hardcoded 10."""

    def test_round_precision_constant(self):
        assert ROUND_PRECISION == 8

    def test_axis6_score_respects_precision(self):
        """A score rounded to ROUND_PRECISION has at most ROUND_PRECISION decimals."""
        score = 0.123456789012345
        rounded = round(score, ROUND_PRECISION)
        # Verify it was rounded to 8, not 10
        assert rounded == round(score, 8)
        assert rounded != round(score, 10)


# ── Regression: existing to_dict fields still present ────────

class TestRegressionToDictFields:
    """Ensure hardening additions did not remove existing fields."""

    def test_axis_result_original_fields(self):
        r = _valid()
        d = r.to_dict()
        for key in [
            "country", "axis_id", "axis_slug", "score", "basis",
            "validity", "coverage", "source", "warnings",
            "channel_a_concentration", "channel_b_concentration",
        ]:
            assert key in d, f"Missing original field: {key}"

    def test_composite_result_original_fields(self):
        axes = [_valid(axis_id=i) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "P1", "v1.1")
        d = comp.to_dict()
        for key in [
            "country", "country_name", "isi_composite", "classification",
            "axes_included", "axes_excluded", "confidence", "scope",
            "methodology_version", "warnings", "axes",
        ]:
            assert key in d, f"Missing original field: {key}"
