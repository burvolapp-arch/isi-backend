#!/usr/bin/env python3
"""Tests for backend.axis_result — Structured result types and validation.

Validates AxisResult, CompositeResult, validation functions, and
compute_composite_v11 for the ISI v1.1 global expansion.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.axis_result import (
    AXIS_ID_TO_SLUG,
    AXIS_SLUGS,
    VALID_BASIS,
    VALID_VALIDITY,
    VALID_CONFIDENCE,
    AxisResult,
    CompositeResult,
    validate_axis_result,
    validate_composite_result,
    make_invalid_axis,
    compute_composite_v11,
)
from backend.constants import ROUND_PRECISION


# ── Helpers ──────────────────────────────────────────────────

def make_valid_axis(country="US", axis_id=1, score=0.5) -> AxisResult:
    """Create a valid AxisResult for testing."""
    return AxisResult(
        country=country,
        axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score,
        basis="BOTH",
        validity="VALID",
        coverage=None,
        source="TEST",
        warnings=(),
        channel_a_concentration=0.4,
        channel_b_concentration=0.6,
    )


def make_a_only_axis(country="US", axis_id=1, score=0.3) -> AxisResult:
    return AxisResult(
        country=country,
        axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score,
        basis="A_ONLY",
        validity="A_ONLY",
        coverage=None,
        source="TEST",
        warnings=("W-HS6-GRANULARITY",),
        channel_a_concentration=0.3,
        channel_b_concentration=None,
    )


def make_degraded_axis(country="US", axis_id=4, score=0.01) -> AxisResult:
    return AxisResult(
        country=country,
        axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score,
        basis="BOTH",
        validity="DEGRADED",
        coverage=None,
        source="TEST",
        warnings=("W-PRODUCER-INVERSION",),
        channel_a_concentration=0.01,
        channel_b_concentration=0.01,
    )


# ── Enum Constants ───────────────────────────────────────────

class TestEnums:
    def test_basis_values(self):
        assert VALID_BASIS == frozenset({"BOTH", "A_ONLY", "B_ONLY", "INVALID"})

    def test_validity_values(self):
        assert VALID_VALIDITY == frozenset({"VALID", "A_ONLY", "DEGRADED", "INVALID"})

    def test_confidence_values(self):
        assert VALID_CONFIDENCE == frozenset({"FULL", "REDUCED", "LOW_CONFIDENCE"})

    def test_axis_slugs(self):
        assert len(AXIS_SLUGS) == 6

    def test_axis_id_map(self):
        for i in range(1, 7):
            assert i in AXIS_ID_TO_SLUG


# ── AxisResult Construction ──────────────────────────────────

class TestAxisResultCreation:
    def test_valid_result(self):
        r = make_valid_axis()
        validate_axis_result(r)
        assert r.score == 0.5

    def test_frozen(self):
        r = make_valid_axis()
        with pytest.raises(AttributeError):
            r.score = 0.9  # type: ignore[misc]

    def test_to_dict(self):
        r = make_valid_axis()
        d = r.to_dict()
        assert d["country"] == "US"
        assert d["axis_id"] == 1
        assert d["score"] == 0.5
        assert isinstance(d["warnings"], list)

    def test_invalid_result(self):
        r = make_invalid_axis("JP", 3, "TEST")
        validate_axis_result(r)
        assert r.score is None
        assert r.basis == "INVALID"
        assert r.validity == "INVALID"


# ── AxisResult Validation ────────────────────────────────────

class TestAxisResultValidation:
    def test_invalid_basis_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="financial",
            score=0.5, basis="WRONG", validity="VALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="invalid basis"):
            validate_axis_result(r)

    def test_invalid_validity_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="financial",
            score=0.5, basis="BOTH", validity="WRONG",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="invalid validity"):
            validate_axis_result(r)

    def test_invalid_axis_id_raises(self):
        r = AxisResult(
            country="US", axis_id=7, axis_slug="financial",
            score=0.5, basis="BOTH", validity="VALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="axis_id"):
            validate_axis_result(r)

    def test_slug_mismatch_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="energy",
            score=0.5, basis="BOTH", validity="VALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="slug mismatch"):
            validate_axis_result(r)

    def test_invalid_basis_nonzero_score_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="financial",
            score=0.5, basis="INVALID", validity="INVALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="INVALID but score is not None"):
            validate_axis_result(r)

    def test_valid_basis_none_score_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="financial",
            score=None, basis="BOTH", validity="VALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="score is None"):
            validate_axis_result(r)

    def test_score_out_of_bounds_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="financial",
            score=1.5, basis="BOTH", validity="VALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="out of"):
            validate_axis_result(r)

    def test_nan_score_raises(self):
        r = AxisResult(
            country="US", axis_id=1, axis_slug="financial",
            score=float("nan"), basis="BOTH", validity="VALID",
            coverage=None, source="T", warnings=(),
            channel_a_concentration=None, channel_b_concentration=None,
        )
        with pytest.raises(ValueError, match="NaN"):
            validate_axis_result(r)

    def test_edge_score_zero(self):
        r = make_valid_axis(score=0.0)
        validate_axis_result(r)

    def test_edge_score_one(self):
        r = make_valid_axis(score=1.0)
        validate_axis_result(r)


# ── make_invalid_axis ────────────────────────────────────────

class TestMakeInvalidAxis:
    def test_basic(self):
        r = make_invalid_axis("JP", 3, "TEST")
        assert r.country == "JP"
        assert r.axis_id == 3
        assert r.axis_slug == "technology"
        assert r.score is None
        assert r.basis == "INVALID"
        assert r.validity == "INVALID"

    def test_with_warnings(self):
        r = make_invalid_axis("CN", 6, "NONE", warnings=("LIM-003",))
        assert r.warnings == ("LIM-003",)

    def test_all_axes(self):
        for axis_id in range(1, 7):
            r = make_invalid_axis("US", axis_id, "TEST")
            validate_axis_result(r)


# ── CompositeResult ──────────────────────────────────────────

class TestCompositeResult:
    def test_to_dict(self):
        axes = [make_valid_axis(axis_id=i, score=0.3) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        d = comp.to_dict()
        assert d["country"] == "US"
        assert d["isi_composite"] is not None
        assert len(d["axes"]) == 6

    def test_frozen(self):
        axes = [make_valid_axis(axis_id=i) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        with pytest.raises(AttributeError):
            comp.isi_composite = 0.9  # type: ignore[misc]


# ── compute_composite_v11 ───────────────────────────────────

class TestCompositeV11:
    def test_all_valid(self):
        """6 valid axes → composite = mean, confidence = FULL."""
        axes = [make_valid_axis(axis_id=i, score=0.3) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite is not None
        assert abs(comp.isi_composite - 0.3) < 1e-8
        assert comp.axes_included == 6
        assert comp.confidence == "FULL"

    def test_one_invalid(self):
        """5 valid + 1 invalid → composite from 5, confidence = REDUCED."""
        axes = [make_valid_axis(axis_id=i, score=0.4) for i in range(1, 6)]
        axes.append(make_invalid_axis("US", 6, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite is not None
        assert abs(comp.isi_composite - 0.4) < 1e-8
        assert comp.axes_included == 5
        assert len(comp.axes_excluded) == 1
        assert comp.confidence == "REDUCED"

    def test_two_invalid(self):
        """4 valid + 2 invalid → composite from 4, confidence = LOW_CONFIDENCE."""
        axes = [make_valid_axis(axis_id=i, score=0.5) for i in range(1, 5)]
        axes.append(make_invalid_axis("US", 5, "NONE"))
        axes.append(make_invalid_axis("US", 6, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite is not None
        assert abs(comp.isi_composite - 0.5) < 1e-8
        assert comp.axes_included == 4
        assert comp.confidence == "LOW_CONFIDENCE"

    def test_three_invalid_no_composite(self):
        """3 valid + 3 invalid → no composite (< 4 computable)."""
        axes = [make_valid_axis(axis_id=i, score=0.5) for i in range(1, 4)]
        axes.append(make_invalid_axis("US", 4, "NONE"))
        axes.append(make_invalid_axis("US", 5, "NONE"))
        axes.append(make_invalid_axis("US", 6, "NONE"))
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite is None
        assert comp.classification is None
        assert comp.axes_included == 3
        assert comp.confidence == "LOW_CONFIDENCE"

    def test_a_only_counts_as_computable(self):
        """A_ONLY axes count toward composite."""
        axes = [make_a_only_axis(axis_id=i, score=0.3) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite is not None
        assert comp.axes_included == 6

    def test_degraded_counts_but_affects_confidence(self):
        """DEGRADED axes count but reduce confidence."""
        axes = [make_valid_axis(axis_id=i, score=0.3) for i in range(1, 4)]
        axes.append(make_degraded_axis(axis_id=4))
        axes.append(make_degraded_axis(axis_id=5, score=0.02))
        axes.append(make_degraded_axis(axis_id=6, score=0.03))
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite is not None
        assert comp.axes_included == 6
        # 3 degraded > 2 → LOW_CONFIDENCE
        assert comp.confidence == "LOW_CONFIDENCE"

    def test_wrong_axis_count_raises(self):
        """Must provide exactly 6 axis results."""
        axes = [make_valid_axis(axis_id=i) for i in range(1, 6)]
        with pytest.raises(ValueError, match="expected 6"):
            compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")

    def test_composite_score_range(self):
        """Composite score must be in [0, 1]."""
        axes = [make_valid_axis(axis_id=i, score=0.0) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite == 0.0

        axes = [make_valid_axis(axis_id=i, score=1.0) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.isi_composite == 1.0

    def test_typical_expansion_scenario(self):
        """Typical Phase 1 scenario: 5 axes valid, logistics INVALID."""
        axes = [
            make_valid_axis(axis_id=1, score=0.25),   # financial
            make_valid_axis(axis_id=2, score=0.40),   # energy
            make_a_only_axis(axis_id=3, score=0.35),  # tech (A_ONLY)
            make_valid_axis(axis_id=4, score=0.10),   # defense
            make_a_only_axis(axis_id=5, score=0.50),  # critical (A_ONLY)
            make_invalid_axis("GB", 6, "NONE"),        # logistics (INVALID)
        ]
        comp = compute_composite_v11(axes, "GB", "United Kingdom", "PHASE1-7", "v1.1")
        assert comp.isi_composite is not None
        expected = (0.25 + 0.40 + 0.35 + 0.10 + 0.50) / 5
        assert abs(comp.isi_composite - round(expected, ROUND_PRECISION)) < 1e-8
        assert comp.axes_included == 5
        assert len(comp.axes_excluded) == 1
        assert comp.confidence == "REDUCED"

    def test_classification_thresholds(self):
        """Test ISI classification thresholds (v1.1 uses same labels as v1.0)."""
        # highly_concentrated (>= 0.50)
        axes = [make_valid_axis(axis_id=i, score=0.6) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.classification == "highly_concentrated"

        # moderately_concentrated (>= 0.25)
        axes = [make_valid_axis(axis_id=i, score=0.35) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.classification == "moderately_concentrated"

        # mildly_concentrated (>= 0.15)
        axes = [make_valid_axis(axis_id=i, score=0.20) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.classification == "mildly_concentrated"

        # unconcentrated (< 0.15)
        axes = [make_valid_axis(axis_id=i, score=0.10) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        assert comp.classification == "unconcentrated"


# ── Validate Composite Result ────────────────────────────────

class TestValidateCompositeResult:
    def test_axes_count_mismatch_raises(self):
        """axes_included + len(axes_excluded) must equal 6."""
        axes = [make_valid_axis(axis_id=i) for i in range(1, 7)]
        comp = compute_composite_v11(axes, "US", "United States", "PHASE1-7", "v1.1")
        # Manually create invalid composite
        bad = CompositeResult(
            country="US",
            country_name="United States",
            isi_composite=0.5,
            classification="High",
            axes_included=5,  # wrong
            axes_excluded=(),  # empty → 5 + 0 = 5 ≠ 6
            confidence="FULL",
            scope="PHASE1-7",
            methodology_version="v1.1",
            warnings=(),
            axis_results=tuple(axes),
        )
        with pytest.raises(ValueError, match="!= 6"):
            validate_composite_result(bad)
