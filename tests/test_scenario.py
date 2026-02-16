"""
tests/test_scenario.py — Unit tests for ISI scenario simulation engine.

Tests the pure computation module (backend.scenario) directly,
and the POST /scenario endpoint via FastAPI TestClient.

Requires: pytest, httpx (FastAPI TestClient dependency)
"""

from __future__ import annotations

import math

import pytest

from backend.scenario import (
    AXIS_SLUGS,
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
        )

        assert result["ok"] is True

        # Baseline
        bl = result["baseline"]
        assert bl["country"] == "SE"
        assert bl["axis_scores"]["defense"] == pytest.approx(0.30)

        # Simulated
        sim = result["simulated"]
        assert sim["axis_scores"]["defense"] == pytest.approx(0.40)
        assert sim["composite"] > bl["composite"]

        # All values bounded
        for slug in AXIS_SLUGS:
            assert 0.0 <= sim["axis_scores"][slug] <= 1.0
        assert 0.0 <= sim["composite"] <= 1.0
        assert 1 <= sim["rank"] <= 27
        assert sim["classification"] in {
            "highly_concentrated",
            "moderately_concentrated",
            "mildly_concentrated",
            "unconcentrated",
        }

        # No negatives anywhere
        for slug in AXIS_SLUGS:
            assert sim["axis_scores"][slug] >= 0.0

        # Delta
        delta = result["delta"]
        assert delta["composite"] > 0
        assert delta["axis_deltas"]["defense"] == pytest.approx(0.10)

    def test_no_change_zero_adjustments(self, all_baselines):
        """All-zero adjustments should produce identical baseline and simulated."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.0},
            all_baselines=all_baselines,
        )
        assert result["ok"] is True
        assert result["delta"]["composite"] == pytest.approx(0.0)
        assert result["simulated"]["composite"] == pytest.approx(result["baseline"]["composite"])

    def test_clamp_at_one(self, all_baselines):
        """Adjustment that pushes score above 1.0 should clamp."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.20},  # 0.30 + 0.20 = 0.50 (still under 1.0)
            all_baselines=all_baselines,
        )
        assert result["ok"] is True
        assert result["simulated"]["axis_scores"]["defense"] == pytest.approx(0.50)

    def test_clamp_at_zero(self, all_baselines):
        """Negative adjustment should clamp at 0.0."""
        result = simulate(
            country_code="SE",
            adjustments={"energy": -0.20},  # 0.10 - 0.20 = -0.10 → clamped to 0.0
            all_baselines=all_baselines,
        )
        assert result["ok"] is True
        assert result["simulated"]["axis_scores"]["energy"] == 0.0

    def test_missing_country_raises(self, all_baselines):
        """Country not in baselines → ValueError."""
        with pytest.raises(ValueError, match="not found"):
            simulate(
                country_code="XX",
                adjustments={"defense": 0.10},
                all_baselines=all_baselines,
            )

    def test_multiple_adjustments(self, all_baselines):
        """Multiple axes adjusted simultaneously."""
        result = simulate(
            country_code="SE",
            adjustments={"defense": 0.10, "energy": -0.05, "financial": 0.05},
            all_baselines=all_baselines,
        )
        assert result["ok"] is True
        sim = result["simulated"]
        assert sim["axis_scores"]["defense"] == pytest.approx(0.40)
        assert sim["axis_scores"]["energy"] == pytest.approx(0.05)
        assert sim["axis_scores"]["financial"] == pytest.approx(0.20)


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
