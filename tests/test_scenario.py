"""
tests/test_scenario.py — Unit tests for ISI scenario simulation engine (v0.3).

Tests the pure computation module (backend.scenario) directly.

Response contract (v0.3):
    {simulated_composite, simulated_rank, simulated_classification,
     axis_results: {slug: float}, request_id}

Requires: pytest
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
            axis_shifts={"defense": 0.10},
            all_baselines=all_baselines,
            request_id="test-001",
        )

        # v0.3 response contract
        assert "simulated_composite" in result
        assert "simulated_rank" in result
        assert "simulated_classification" in result
        assert "axis_results" in result
        assert "request_id" in result
        assert result["request_id"] == "test-001"

        # No extra fields
        assert set(result.keys()) == {
            "simulated_composite", "simulated_rank", "simulated_classification",
            "axis_results", "request_id",
        }

        # Composite is bounded
        assert 0.0 <= result["simulated_composite"] <= 1.0

        # Rank is positive integer
        assert isinstance(result["simulated_rank"], int)
        assert 1 <= result["simulated_rank"] <= 27

        # Classification is valid
        assert result["simulated_classification"] in VALID_CLASSIFICATIONS

        # axis_results: dict with exactly 6 canonical slugs, all bounded, no NaN
        ar = result["axis_results"]
        assert isinstance(ar, dict)
        assert set(ar.keys()) == set(AXIS_SLUGS)
        for slug, val in ar.items():
            assert 0.0 <= val <= 1.0
            assert not math.isnan(val)

        # Defense axis should have increased
        assert ar["defense"] == pytest.approx(0.40)

    def test_empty_axis_shifts_returns_baseline(self, all_baselines):
        """Empty axis_shifts {} → zero deltas, returns baseline composite."""
        result = simulate(
            country_code="SE",
            axis_shifts={},
            all_baselines=all_baselines,
            request_id="test-empty",
        )
        # SE baseline: (0.15+0.10+0.25+0.30+0.20+0.18)/6 ≈ 0.1967
        assert result["simulated_composite"] == pytest.approx(
            (0.15 + 0.10 + 0.25 + 0.30 + 0.20 + 0.18) / 6, abs=1e-8
        )

    def test_no_change_zero_shifts(self, all_baselines):
        """Explicit zero shifts produce same result as empty shifts."""
        result = simulate(
            country_code="SE",
            axis_shifts={"defense": 0.0},
            all_baselines=all_baselines,
            request_id="test-002",
        )
        baseline_result = simulate(
            country_code="SE",
            axis_shifts={},
            all_baselines=all_baselines,
            request_id="test-002",
        )
        assert result["simulated_composite"] == baseline_result["simulated_composite"]
        assert result["axis_results"] == baseline_result["axis_results"]

    def test_clamp_at_one(self, all_baselines):
        """Shift that pushes score above 1.0 should clamp."""
        result = simulate(
            country_code="SE",
            axis_shifts={"defense": 0.20},  # 0.30 + 0.20 = 0.50 (still under 1.0)
            all_baselines=all_baselines,
            request_id="test-003",
        )
        assert result["axis_results"]["defense"] == pytest.approx(0.50)

    def test_clamp_at_zero(self, all_baselines):
        """Negative shift should clamp at 0.0."""
        result = simulate(
            country_code="SE",
            axis_shifts={"energy": -0.20},  # 0.10 - 0.20 = -0.10 → clamped to 0.0
            all_baselines=all_baselines,
            request_id="test-004",
        )
        assert result["axis_results"]["energy"] == 0.0

    def test_missing_country_raises(self, all_baselines):
        """Country not in baselines → ValueError."""
        with pytest.raises(ValueError, match="not found"):
            simulate(
                country_code="XX",
                axis_shifts={"defense": 0.10},
                all_baselines=all_baselines,
                request_id="test-005",
            )

    def test_multiple_shifts(self, all_baselines):
        """Multiple axes shifted simultaneously."""
        result = simulate(
            country_code="SE",
            axis_shifts={"defense": 0.10, "energy": -0.05, "financial": 0.05},
            all_baselines=all_baselines,
            request_id="test-006",
        )
        ar = result["axis_results"]
        assert ar["defense"] == pytest.approx(0.40)
        assert ar["energy"] == pytest.approx(0.05)
        assert ar["financial"] == pytest.approx(0.20)

    def test_idempotent(self, all_baselines):
        """Same inputs always produce identical outputs (deterministic)."""
        kwargs = dict(
            country_code="SE",
            axis_shifts={"defense": 0.10},
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
            axis_shifts={"defense": 0.10},
            all_baselines=all_baselines,
            request_id="test-null",
        )
        assert result["simulated_composite"] is not None
        assert result["simulated_rank"] is not None
        assert result["simulated_classification"] is not None
        assert result["axis_results"] is not None
        assert result["request_id"] is not None
        for slug, val in result["axis_results"].items():
            assert slug is not None
            assert val is not None


# ---------------------------------------------------------------------------
# Pydantic validation tests
# ---------------------------------------------------------------------------

class TestScenarioRequestValidation:
    def test_valid_request(self):
        req = ScenarioRequest(country_code="SE", axis_shifts={"defense": 0.10})
        assert req.country_code == "SE"
        assert req.axis_shifts["defense"] == 0.10

    def test_uppercase_country(self):
        req = ScenarioRequest(country_code="se", axis_shifts={"defense": 0.10})
        assert req.country_code == "SE"

    def test_unknown_slug_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", axis_shifts={"unknown_axis": 0.10})

    def test_out_of_range_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", axis_shifts={"defense": 0.50})

    def test_negative_out_of_range_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", axis_shifts={"defense": -0.50})

    def test_nan_rejected(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="SE", axis_shifts={"defense": float("nan")})

    def test_empty_axis_shifts_accepted(self):
        """Empty axis_shifts {} is valid — returns baseline (no deltas)."""
        req = ScenarioRequest(country_code="SE", axis_shifts={})
        assert req.axis_shifts == {}

    def test_default_axis_shifts_empty(self):
        """axis_shifts defaults to {} when omitted."""
        req = ScenarioRequest(country_code="SE")
        assert req.axis_shifts == {}

    def test_extra_fields_ignored(self):
        """Extra fields silently ignored (frontend may send metadata)."""
        req = ScenarioRequest(
            country_code="SE",
            axis_shifts={"defense": 0.10},
            extra_field="should be ignored",  # type: ignore[call-arg]
        )
        assert req.country_code == "SE"
        assert req.axis_shifts == {"defense": 0.10}

    def test_invalid_country_code(self):
        with pytest.raises(Exception):
            ScenarioRequest(country_code="123", axis_shifts={"defense": 0.10})

    def test_boundary_shift_accepted(self):
        req = ScenarioRequest(country_code="SE", axis_shifts={"defense": 0.20})
        assert req.axis_shifts["defense"] == 0.20
        req2 = ScenarioRequest(country_code="SE", axis_shifts={"defense": -0.20})
        assert req2.axis_shifts["defense"] == -0.20

    def test_alias_countryCode(self):
        """Frontend sends camelCase countryCode — should be accepted."""
        req = ScenarioRequest.model_validate({"countryCode": "SE", "adjustments": {"defense": 0.10}})
        assert req.country_code == "SE"
        assert req.axis_shifts == {"defense": 0.10}

    def test_alias_adjustments(self):
        """Frontend sends 'adjustments' as alias for axis_shifts."""
        req = ScenarioRequest.model_validate({"country_code": "SE", "adjustments": {"energy": 0.05}})
        assert req.axis_shifts == {"energy": 0.05}
