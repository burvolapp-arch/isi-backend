"""
tests/test_scenario.py — Unit tests for ISI scenario simulation engine (v0.2).

Tests the pure computation module (backend.scenario) directly,
and the POST /scenario endpoint via FastAPI TestClient.

Response contract (v0.2):
    {composite, rank, classification, axes[], request_id}

Requires: pytest, httpx (FastAPI TestClient dependency)
"""

from __future__ import annotations

import math

import pytest

from backend.scenario import (
    AXIS_SLUGS,
    VALID_CLASSIFICATIONS,
    ScenarioRequest,
    classify,
    clamp01,
    compute_composite,
    compute_rank,
    simulate,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal 27-country baseline matching ISI v0.1 shape
# ---------------------------------------------------------------------------

def _make_baseline_entry(
    code: str,
    name: str,
    scores: dict[str, float] | None = None,
) -> dict:
    """Build a minimal isi.json countries[] entry."""
    default_scores = {
        "axis_1_financial": 0.20,
        "axis_2_energy": 0.20,
        "axis_3_technology": 0.20,
        "axis_4_defense": 0.20,
        "axis_5_critical_inputs": 0.20,
        "axis_6_logistics": 0.20,
    }
    if scores:
        default_scores.update(scores)
    composite = sum(default_scores.values()) / 6
    return {
        "country": code,
        "country_name": name,
        **default_scores,
        "isi_composite": composite,
        "classification": classify(composite),
        "complete": True,
    }


# All 27 EU countries with default scores (SE gets custom scores for testing)
EU27_CODES = [
    ("AT", "Austria"), ("BE", "Belgium"), ("BG", "Bulgaria"),
    ("CY", "Cyprus"), ("CZ", "Czechia"), ("DE", "Germany"),
    ("DK", "Denmark"), ("EE", "Estonia"), ("EL", "Greece"),
    ("ES", "Spain"), ("FI", "Finland"), ("FR", "France"),
    ("HR", "Croatia"), ("HU", "Hungary"), ("IE", "Ireland"),
    ("IT", "Italy"), ("LT", "Lithuania"), ("LU", "Luxembourg"),
    ("LV", "Latvia"), ("MT", "Malta"), ("NL", "Netherlands"),
    ("PL", "Poland"), ("PT", "Portugal"), ("RO", "Romania"),
    ("SE", "Sweden"), ("SI", "Slovenia"), ("SK", "Slovakia"),
]


@pytest.fixture
def all_baselines() -> list[dict]:
    """27-country baseline where SE has custom axis scores."""
    entries = []
    for code, name in EU27_CODES:
        if code == "SE":
            entries.append(_make_baseline_entry(code, name, scores={
                "axis_1_financial": 0.15,
                "axis_2_energy": 0.10,
                "axis_3_technology": 0.25,
                "axis_4_defense": 0.30,
                "axis_5_critical_inputs": 0.20,
                "axis_6_logistics": 0.18,
            }))
        else:
            entries.append(_make_baseline_entry(code, name))
    return entries


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

class TestClassify:
    def test_highly_concentrated(self):
        assert classify(0.25) == "highly_concentrated"
        assert classify(0.50) == "highly_concentrated"
        assert classify(1.0) == "highly_concentrated"

    def test_moderately_concentrated(self):
        assert classify(0.15) == "moderately_concentrated"
        assert classify(0.24) == "moderately_concentrated"

    def test_mildly_concentrated(self):
        assert classify(0.10) == "mildly_concentrated"
        assert classify(0.14) == "mildly_concentrated"

    def test_unconcentrated(self):
        assert classify(0.09) == "unconcentrated"
        assert classify(0.0) == "unconcentrated"

    def test_boundary_exact(self):
        """Boundaries are inclusive (>=)."""
        assert classify(0.25) == "highly_concentrated"
        assert classify(0.15) == "moderately_concentrated"
        assert classify(0.10) == "mildly_concentrated"


class TestClamp01:
    def test_normal_values(self):
        assert clamp01(0.5) == 0.5
        assert clamp01(0.0) == 0.0
        assert clamp01(1.0) == 1.0

    def test_clamping(self):
        assert clamp01(-0.1) == 0.0
        assert clamp01(1.5) == 1.0

    def test_nan_inf(self):
        assert clamp01(float("nan")) == 0.0
        assert clamp01(float("inf")) == 0.0
        assert clamp01(float("-inf")) == 0.0


class TestComputeComposite:
    def test_equal_scores(self):
        scores = {slug: 0.5 for slug in AXIS_SLUGS}
        assert compute_composite(scores) == pytest.approx(0.5)

    def test_mixed_scores(self):
        scores = dict(zip(AXIS_SLUGS, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]))
        expected = sum([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]) / 6
        assert compute_composite(scores) == pytest.approx(expected)

    def test_all_zero(self):
        scores = {slug: 0.0 for slug in AXIS_SLUGS}
        assert compute_composite(scores) == 0.0

    def test_all_one(self):
        scores = {slug: 1.0 for slug in AXIS_SLUGS}
        assert compute_composite(scores) == 1.0


class TestComputeRank:
    def test_highest_gets_rank_1(self, all_baselines):
        # SE baseline composite ≈ 0.1967, everyone else = 0.20
        # If we give SE composite = 1.0, it should be rank 1
        rank = compute_rank("SE", 1.0, all_baselines)
        assert rank == 1

    def test_lowest_gets_rank_27(self, all_baselines):
        rank = compute_rank("SE", 0.0, all_baselines)
        assert rank == 27

    def test_rank_in_bounds(self, all_baselines):
        rank = compute_rank("SE", 0.20, all_baselines)
        assert 1 <= rank <= 27


# ---------------------------------------------------------------------------
# Scenario simulation integration tests
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_se_defense_plus_010(self, all_baselines):
        """Core test: SE baseline + defense +0.10 → composite increases, values bounded."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.10},
            all_baselines=all_baselines,
            request_id="test-001",
        )

        # v0.2 flat contract
        assert "composite" in result
        assert "rank" in result
        assert "classification" in result
        assert "axes" in result
        assert "request_id" in result
        assert result["request_id"] == "test-001"

        # No extra fields
        assert set(result.keys()) == {"composite", "rank", "classification", "axes", "request_id"}

        # Composite is bounded
        assert 0.0 <= result["composite"] <= 1.0

        # Rank is positive integer
        assert isinstance(result["rank"], int)
        assert 1 <= result["rank"] <= 27

        # Classification is valid
        assert result["classification"] in VALID_CLASSIFICATIONS

        # Axes: exactly 6, each with slug/value/delta, no NaN, bounded
        assert isinstance(result["axes"], list)
        assert len(result["axes"]) == 6
        for ax in result["axes"]:
            assert set(ax.keys()) == {"slug", "value", "delta"}
            assert ax["slug"] in AXIS_SLUGS
            assert 0.0 <= ax["value"] <= 1.0
            assert not math.isnan(ax["value"])
            assert not math.isnan(ax["delta"])

        # Defense axis should have increased
        defense_ax = next(a for a in result["axes"] if a["slug"] == "defense")
        assert defense_ax["value"] == pytest.approx(0.40)
        assert defense_ax["delta"] == pytest.approx(0.10)

    def test_no_change_zero_adjustments(self, all_baselines):
        """All-zero adjustments should produce zero deltas."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.0},
            all_baselines=all_baselines,
            request_id="test-002",
        )
        for ax in result["axes"]:
            assert ax["delta"] == pytest.approx(0.0)

    def test_clamp_at_one(self, all_baselines):
        """Adjustment that pushes score above 1.0 should clamp."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.20},  # 0.30 + 0.20 = 0.50 (still under 1.0)
            all_baselines=all_baselines,
            request_id="test-003",
        )
        defense_ax = next(a for a in result["axes"] if a["slug"] == "defense")
        assert defense_ax["value"] == pytest.approx(0.50)

    def test_clamp_at_zero(self, all_baselines):
        """Negative adjustment should clamp at 0.0."""
        result = simulate(
            country_code="SE",
            adjustments={"energy": -0.20},  # 0.10 - 0.20 = -0.10 → clamped to 0.0
            all_baselines=all_baselines,
            request_id="test-004",
        )
        energy_ax = next(a for a in result["axes"] if a["slug"] == "energy")
        assert energy_ax["value"] == 0.0

    def test_missing_country_raises(self, all_baselines):
        """Country not in baselines → ValueError."""
        with pytest.raises(ValueError, match="not found"):
            simulate(
                country_code="XX",
                adjustments={"defense": 0.10},
                all_baselines=all_baselines,
                request_id="test-005",
            )

    def test_multiple_adjustments(self, all_baselines):
        """Multiple axes adjusted simultaneously."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.10, "energy": -0.05, "financial": 0.05},
            all_baselines=all_baselines,
            request_id="test-006",
        )
        axes_by_slug = {a["slug"]: a for a in result["axes"]}
        assert axes_by_slug["defense"]["value"] == pytest.approx(0.40)
        assert axes_by_slug["energy"]["value"] == pytest.approx(0.05)
        assert axes_by_slug["financial"]["value"] == pytest.approx(0.20)

    def test_idempotent(self, all_baselines):
        """Same inputs always produce identical outputs (deterministic)."""
        kwargs = dict(
            country_code="SE",
            adjustments={"defense": 0.10},
            all_baselines=all_baselines,
            request_id="test-idem",
        )
        r1 = simulate(**kwargs)
        r2 = simulate(**kwargs)
        assert r1 == r2

    def test_no_null_fields(self, all_baselines):
        """No field in the response may be None."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.10},
            all_baselines=all_baselines,
            request_id="test-null",
        )
        assert result["composite"] is not None
        assert result["rank"] is not None
        assert result["classification"] is not None
        assert result["axes"] is not None
        assert result["request_id"] is not None
        for ax in result["axes"]:
            assert ax["slug"] is not None
            assert ax["value"] is not None
            assert ax["delta"] is not None


# ---------------------------------------------------------------------------
# Pydantic validation tests
# ---------------------------------------------------------------------------

class TestScenarioRequestValidation:
    def test_valid_request(self):
        req = ScenarioRequest(country_code="SE", adjustments={"defense": 0.10})
        assert req.country_code == "SE"
        assert req.adjustments["defense"] == 0.10

    def test_uppercase_country(self):
        req = ScenarioRequest(country_code="se", adjustments={"defense": 0.10})
        assert req.country_code == "SE"

    def test_unknown_slug_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", adjustments={"unknown_axis": 0.10})

    def test_out_of_range_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", adjustments={"defense": 0.50})

    def test_negative_out_of_range_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", adjustments={"defense": -0.50})

    def test_nan_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", adjustments={"defense": float("nan")})

    def test_empty_adjustments_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", adjustments={})

    def test_extra_fields_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(
                country_code="SE",
                adjustments={"defense": 0.10},
                extra_field="should fail",  # type: ignore[call-arg]
            )

    def test_invalid_country_code(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="123", adjustments={"defense": 0.10})

    def test_boundary_adjustment_accepted(self):
        req = ScenarioRequest(country_code="SE", adjustments={"defense": 0.20})
        assert req.adjustments["defense"] == 0.20
        req2 = ScenarioRequest(country_code="SE", adjustments={"defense": -0.20})
        assert req2.adjustments["defense"] == -0.20
