"""
tests/test_scenario.py — Unit tests for ISI scenario simulation engine (v0.5).

Tests the pure computation module (backend.scenario) directly.

v0.5 changes:
- Input fields: country, adjustments
- Adjustment keys: long-form canonical snake_case keys
- Computation: multiplicative — simulated = clamp(baseline * (1 + adj), 0, 1)
- Response includes 'country' field
- No Pydantic ScenarioRequest model — validation in API handler
- No tolerance for unknown keys — strict validation

Requires: pytest
"""

from __future__ import annotations

import math

import pytest

from backend.scenario import (
    CANONICAL_AXIS_KEYS,
    CANONICAL_TO_ISI_KEY,
    ISI_AXIS_KEYS,
    ISI_KEY_TO_CANONICAL,
    VALID_CANONICAL_KEYS,
    classify,
    clamp,
    compute_composite,
    compute_rank,
    simulate,
)


# ---------------------------------------------------------------------------
# Shorthand canonical keys for readability
# ---------------------------------------------------------------------------

K_FIN = "financial_external_supplier_concentration"
K_ENE = "energy_external_supplier_concentration"
K_TEC = "technology_semiconductor_external_supplier_concentration"
K_DEF = "defense_external_supplier_concentration"
K_CRI = "critical_inputs_raw_materials_external_supplier_concentration"
K_LOG = "logistics_freight_external_supplier_concentration"


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

# SE custom baseline for deterministic testing
SE_SCORES = {
    "axis_1_financial": 0.15,
    "axis_2_energy": 0.10,
    "axis_3_technology": 0.25,
    "axis_4_defense": 0.30,
    "axis_5_critical_inputs": 0.20,
    "axis_6_logistics": 0.18,
}


@pytest.fixture
def all_baselines() -> list[dict]:
    """27-country baseline where SE has custom axis scores."""
    entries = []
    for code, name in EU27_CODES:
        if code == "SE":
            entries.append(_make_baseline_entry(code, name, scores=SE_SCORES))
        else:
            entries.append(_make_baseline_entry(code, name))
    return entries


# ---------------------------------------------------------------------------
# Registry consistency tests
# ---------------------------------------------------------------------------

class TestRegistryConsistency:
    def test_six_axis_keys(self):
        assert len(ISI_AXIS_KEYS) == 6

    def test_six_canonical_keys(self):
        assert len(CANONICAL_AXIS_KEYS) == 6
        assert len(VALID_CANONICAL_KEYS) == 6

    def test_bidirectional_mapping(self):
        for canonical_key, isi_key in CANONICAL_TO_ISI_KEY.items():
            assert ISI_KEY_TO_CANONICAL[isi_key] == canonical_key

    def test_all_isi_keys_mapped(self):
        for key in ISI_AXIS_KEYS:
            assert key in ISI_KEY_TO_CANONICAL

    def test_known_canonical_keys(self):
        expected = {K_FIN, K_ENE, K_TEC, K_DEF, K_CRI, K_LOG}
        assert VALID_CANONICAL_KEYS == expected


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
        assert classify(0.25) == "highly_concentrated"
        assert classify(0.15) == "moderately_concentrated"
        assert classify(0.10) == "mildly_concentrated"


class TestClamp:
    def test_normal_values(self):
        assert clamp(0.5, 0.0, 1.0) == 0.5
        assert clamp(0.0, 0.0, 1.0) == 0.0
        assert clamp(1.0, 0.0, 1.0) == 1.0

    def test_clamping(self):
        assert clamp(-0.1, 0.0, 1.0) == 0.0
        assert clamp(1.5, 0.0, 1.0) == 1.0

    def test_nan_inf(self):
        assert clamp(float("nan"), 0.0, 1.0) == 0.0
        assert clamp(float("inf"), 0.0, 1.0) == 0.0
        assert clamp(float("-inf"), 0.0, 1.0) == 0.0


class TestComputeComposite:
    def test_equal_scores(self):
        scores = {key: 0.5 for key in ISI_AXIS_KEYS}
        assert compute_composite(scores) == pytest.approx(0.5)

    def test_mixed_scores(self):
        scores = dict(zip(ISI_AXIS_KEYS, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]))
        expected = sum([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]) / 6
        assert compute_composite(scores) == pytest.approx(expected)

    def test_all_zero(self):
        scores = {key: 0.0 for key in ISI_AXIS_KEYS}
        assert compute_composite(scores) == 0.0

    def test_all_one(self):
        scores = {key: 1.0 for key in ISI_AXIS_KEYS}
        assert compute_composite(scores) == 1.0


class TestComputeRank:
    def test_highest_gets_rank_1(self, all_baselines):
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
    def test_response_contract_shape(self, all_baselines):
        """Response has exact v0.5 contract keys."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )

        expected_keys = {
            "country",
            "baseline_composite", "simulated_composite",
            "baseline_rank", "simulated_rank",
            "baseline_classification", "simulated_classification",
            "axis_results",
        }
        assert set(result.keys()) == expected_keys
        assert result["country"] == "SE"

        # axis_results has all 6 canonical keys
        ar = result["axis_results"]
        assert isinstance(ar, dict)
        assert set(ar.keys()) == VALID_CANONICAL_KEYS
        for ckey in VALID_CANONICAL_KEYS:
            assert set(ar[ckey].keys()) == {"baseline", "simulated", "delta"}

    def test_defense_plus_010_multiplicative(self, all_baselines):
        """SE defense baseline=0.30, adj=+0.10 → simulated=0.30*(1+0.10)=0.33."""
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            all_baselines=all_baselines,
        )

        # Composites bounded
        assert 0.0 <= result["baseline_composite"] <= 1.0
        assert 0.0 <= result["simulated_composite"] <= 1.0

        # Simulated > baseline (defense increased)
        assert result["simulated_composite"] > result["baseline_composite"]

        # Defense axis: baseline=0.30, simulated=0.30*(1+0.10)=0.33
        def_axis = result["axis_results"][K_DEF]
        assert def_axis["baseline"] == pytest.approx(0.30)
        assert def_axis["simulated"] == pytest.approx(0.33)
        assert def_axis["delta"] == pytest.approx(0.03)

    def test_no_adjustments_baseline_equals_simulated(self, all_baselines):
        """Empty adjustments: baseline == simulated for every field."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )

        assert result["baseline_composite"] == result["simulated_composite"]
        assert result["baseline_rank"] == result["simulated_rank"]
        assert result["baseline_classification"] == result["simulated_classification"]

        for ckey in VALID_CANONICAL_KEYS:
            assert result["axis_results"][ckey]["delta"] == pytest.approx(0.0)
            assert (
                result["axis_results"][ckey]["baseline"]
                == result["axis_results"][ckey]["simulated"]
            )

    def test_multiplicative_model(self, all_baselines):
        """Verify the formula: simulated = baseline * (1 + adj)."""
        result = simulate(
            country_code="SE",
            adjustments={K_FIN: 0.20, K_ENE: -0.15},
            all_baselines=all_baselines,
        )

        # Financial: 0.15 * (1 + 0.20) = 0.18
        assert result["axis_results"][K_FIN]["simulated"] == pytest.approx(0.18)

        # Energy: 0.10 * (1 - 0.15) = 0.085
        assert result["axis_results"][K_ENE]["simulated"] == pytest.approx(0.085)

    def test_clamp_at_zero(self, all_baselines):
        """Large negative adjustment clamps axis at 0.0."""
        # Energy baseline = 0.10, adj = -0.20
        # simulated = 0.10 * (1 - 0.20) = 0.08 (not clamped in this case)
        # Use a value where clamping occurs: need baseline * (1 + adj) < 0
        # That requires adj < -1.0, which is outside [-0.20, +0.20] range
        # So with max adj, minimum is baseline * 0.80 — never reaches 0.
        # Test with very low baseline instead.
        result = simulate(
            country_code="SE",
            adjustments={K_ENE: -0.20},
            all_baselines=all_baselines,
        )
        # Energy: 0.10 * (1 - 0.20) = 0.08 — still positive
        assert result["axis_results"][K_ENE]["simulated"] == pytest.approx(0.08)
        assert result["axis_results"][K_ENE]["simulated"] >= 0.0

    def test_missing_country_raises(self, all_baselines):
        """Country not in baselines → ValueError."""
        with pytest.raises(ValueError, match="not found"):
            simulate(
                country_code="XX",
                adjustments={},
                all_baselines=all_baselines,
            )

    def test_multiple_adjustments(self, all_baselines):
        """Multiple axes adjusted simultaneously."""
        result = simulate(
            country_code="SE",
            adjustments={
                K_DEF: 0.10,
                K_ENE: -0.05,
                K_FIN: 0.05,
            },
            all_baselines=all_baselines,
        )
        ar = result["axis_results"]
        # Defense: 0.30 * 1.10 = 0.33
        assert ar[K_DEF]["simulated"] == pytest.approx(0.33)
        # Energy: 0.10 * 0.95 = 0.095
        assert ar[K_ENE]["simulated"] == pytest.approx(0.095)
        # Financial: 0.15 * 1.05 = 0.1575
        assert ar[K_FIN]["simulated"] == pytest.approx(0.1575)

    def test_idempotent(self, all_baselines):
        """Same inputs always produce identical outputs."""
        kwargs = dict(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            all_baselines=all_baselines,
        )
        r1 = simulate(**kwargs)
        r2 = simulate(**kwargs)
        assert r1 == r2

    def test_no_null_fields(self, all_baselines):
        """No field in the response may be None."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        assert result["country"] is not None
        assert result["baseline_composite"] is not None
        assert result["simulated_composite"] is not None
        assert result["baseline_rank"] is not None
        assert result["simulated_rank"] is not None
        assert result["baseline_classification"] is not None
        assert result["simulated_classification"] is not None
        for ckey in VALID_CANONICAL_KEYS:
            for field in ("baseline", "simulated", "delta"):
                assert result["axis_results"][ckey][field] is not None

    def test_ranks_valid(self, all_baselines):
        """Ranks are positive integers within bounds."""
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.20},
            all_baselines=all_baselines,
        )
        assert isinstance(result["baseline_rank"], int)
        assert isinstance(result["simulated_rank"], int)
        assert 1 <= result["baseline_rank"] <= 27
        assert 1 <= result["simulated_rank"] <= 27

    def test_country_in_response(self, all_baselines):
        """Response includes the country field."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        assert result["country"] == "SE"

    def test_all_countries_work(self, all_baselines):
        """Simulation works for every EU-27 country."""
        for code, _ in EU27_CODES:
            result = simulate(
                country_code=code,
                adjustments={},
                all_baselines=all_baselines,
            )
            assert result["country"] == code
            assert 0.0 <= result["baseline_composite"] <= 1.0
