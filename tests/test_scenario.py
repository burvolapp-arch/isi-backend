"""
tests/test_scenario.py — Unit tests for ISI scenario simulation engine (scenario-v1).

Tests the pure computation module (backend.scenario) directly,
AND the Pydantic request/response models for contract enforcement.

scenario-v1 contract:
- Input:  ScenarioRequest  {"country": "SE", "adjustments": {...}}
- Output: ScenarioResponse {country, baseline, simulated, delta, meta}
- Computation: multiplicative — simulated = clamp(baseline * (1 + adj), 0, 1)
- Pydantic validation on both request AND response
- All 6 axis keys present in every response block, always

Requires: pytest, pydantic
"""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from backend.scenario import (
    CANONICAL_AXIS_KEYS,
    CANONICAL_TO_ISI_KEY,
    ISI_AXIS_KEYS,
    ISI_KEY_TO_CANONICAL,
    MAX_ADJUSTMENT,
    SCENARIO_VERSION,
    VALID_CANONICAL_KEYS,
    ScenarioRequest,
    ScenarioResponse,
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
# Pydantic model validation tests — ScenarioRequest
# ---------------------------------------------------------------------------

class TestScenarioRequest:
    def test_valid_minimal(self):
        """Country only, no adjustments."""
        req = ScenarioRequest(country="SE")
        assert req.country == "SE"
        assert req.adjustments == {}

    def test_valid_with_adjustments(self):
        req = ScenarioRequest(
            country="SE",
            adjustments={K_DEF: 0.10, K_ENE: -0.15},
        )
        assert req.country == "SE"
        assert req.adjustments[K_DEF] == 0.10
        assert req.adjustments[K_ENE] == -0.15

    def test_lowercase_country_normalised(self):
        req = ScenarioRequest(country="se")
        assert req.country == "SE"

    def test_invalid_country_not_eu27(self):
        with pytest.raises(ValidationError):
            ScenarioRequest(country="US")

    def test_invalid_country_too_short(self):
        with pytest.raises(ValidationError):
            ScenarioRequest(country="S")

    def test_invalid_country_too_long(self):
        with pytest.raises(ValidationError):
            ScenarioRequest(country="SWE")

    def test_missing_country(self):
        with pytest.raises(ValidationError):
            ScenarioRequest()  # type: ignore[call-arg]

    def test_unknown_axis_key_rejected(self):
        with pytest.raises(ValidationError, match="Unknown axis key"):
            ScenarioRequest(country="SE", adjustments={"bogus_key": 0.05})

    def test_out_of_range_positive(self):
        with pytest.raises(ValidationError, match="must be in"):
            ScenarioRequest(country="SE", adjustments={K_DEF: 0.50})

    def test_out_of_range_negative(self):
        with pytest.raises(ValidationError, match="must be in"):
            ScenarioRequest(country="SE", adjustments={K_DEF: -0.50})

    def test_nan_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            ScenarioRequest(country="SE", adjustments={K_DEF: float("nan")})

    def test_inf_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            ScenarioRequest(country="SE", adjustments={K_DEF: float("inf")})

    def test_boundary_values_accepted(self):
        req = ScenarioRequest(
            country="SE",
            adjustments={K_DEF: 0.20, K_ENE: -0.20},
        )
        assert req.adjustments[K_DEF] == 0.20
        assert req.adjustments[K_ENE] == -0.20


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
# Scenario simulation integration tests — scenario-v1 response shape
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_returns_scenario_response(self, all_baselines):
        """simulate() returns a ScenarioResponse Pydantic model."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        assert isinstance(result, ScenarioResponse)

    def test_response_contract_shape(self, all_baselines):
        """Response has exact scenario-v1 contract fields."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        d = result.model_dump()
        assert set(d.keys()) == {"country", "baseline", "simulated", "delta", "meta"}
        assert result.country == "SE"

        # baseline block
        assert set(d["baseline"].keys()) == {"composite", "rank", "classification", "axes"}
        assert set(d["baseline"]["axes"].keys()) == set(CANONICAL_AXIS_KEYS)

        # simulated block
        assert set(d["simulated"].keys()) == {"composite", "rank", "classification", "axes"}
        assert set(d["simulated"]["axes"].keys()) == set(CANONICAL_AXIS_KEYS)

        # delta block
        assert set(d["delta"].keys()) == {"composite", "rank", "axes"}
        assert set(d["delta"]["axes"].keys()) == set(CANONICAL_AXIS_KEYS)

        # meta block
        assert d["meta"]["version"] == SCENARIO_VERSION
        assert d["meta"]["bounds"] == {"min": -0.2, "max": 0.2}
        assert "timestamp" in d["meta"]

    def test_all_six_axes_always_present(self, all_baselines):
        """baseline.axes and simulated.axes MUST include ALL 6 keys."""
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            all_baselines=all_baselines,
        )
        for ckey in CANONICAL_AXIS_KEYS:
            bval = getattr(result.baseline.axes, ckey)
            sval = getattr(result.simulated.axes, ckey)
            assert not math.isnan(bval) and not math.isinf(bval)
            assert not math.isnan(sval) and not math.isinf(sval)

    def test_defense_plus_010_multiplicative(self, all_baselines):
        """SE defense baseline=0.30, adj=+0.10 → simulated=0.30*(1+0.10)=0.33."""
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            all_baselines=all_baselines,
        )

        assert 0.0 <= result.baseline.composite <= 1.0
        assert 0.0 <= result.simulated.composite <= 1.0
        assert result.simulated.composite > result.baseline.composite

        assert getattr(result.baseline.axes, K_DEF) == pytest.approx(0.30)
        assert getattr(result.simulated.axes, K_DEF) == pytest.approx(0.33)
        assert getattr(result.delta.axes, K_DEF) == pytest.approx(0.03)

    def test_no_adjustments_baseline_equals_simulated(self, all_baselines):
        """Empty adjustments: baseline == simulated for every field."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )

        assert result.baseline.composite == result.simulated.composite
        assert result.baseline.rank == result.simulated.rank
        assert result.baseline.classification == result.simulated.classification
        assert result.delta.composite == pytest.approx(0.0)
        assert result.delta.rank == 0

        for ckey in CANONICAL_AXIS_KEYS:
            assert getattr(result.delta.axes, ckey) == pytest.approx(0.0)
            assert (
                getattr(result.baseline.axes, ckey)
                == getattr(result.simulated.axes, ckey)
            )

    def test_multiplicative_model(self, all_baselines):
        """Verify the formula: simulated = baseline * (1 + adj)."""
        result = simulate(
            country_code="SE",
            adjustments={K_FIN: 0.20, K_ENE: -0.15},
            all_baselines=all_baselines,
        )

        assert getattr(result.simulated.axes, K_FIN) == pytest.approx(0.18)
        assert getattr(result.simulated.axes, K_ENE) == pytest.approx(0.085)

    def test_delta_is_simulated_minus_baseline(self, all_baselines):
        """delta.composite = simulated.composite - baseline.composite, etc."""
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.10, K_ENE: -0.05},
            all_baselines=all_baselines,
        )
        assert result.delta.composite == pytest.approx(
            result.simulated.composite - result.baseline.composite
        )
        assert result.delta.rank == result.simulated.rank - result.baseline.rank

        for ckey in CANONICAL_AXIS_KEYS:
            assert getattr(result.delta.axes, ckey) == pytest.approx(
                getattr(result.simulated.axes, ckey) - getattr(result.baseline.axes, ckey)
            )

    def test_clamp_at_zero(self, all_baselines):
        """Large negative adjustment: simulated stays >= 0."""
        result = simulate(
            country_code="SE",
            adjustments={K_ENE: -0.20},
            all_baselines=all_baselines,
        )
        assert getattr(result.simulated.axes, K_ENE) == pytest.approx(0.08)
        assert getattr(result.simulated.axes, K_ENE) >= 0.0

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
            adjustments={K_DEF: 0.10, K_ENE: -0.05, K_FIN: 0.05},
            all_baselines=all_baselines,
        )
        assert getattr(result.simulated.axes, K_DEF) == pytest.approx(0.33)
        assert getattr(result.simulated.axes, K_ENE) == pytest.approx(0.095)
        assert getattr(result.simulated.axes, K_FIN) == pytest.approx(0.1575)

    def test_idempotent(self, all_baselines):
        """Same inputs always produce identical outputs (except timestamp)."""
        kwargs = dict(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            all_baselines=all_baselines,
        )
        r1 = simulate(**kwargs)
        r2 = simulate(**kwargs)
        d1 = r1.model_dump()
        d2 = r2.model_dump()
        d1["meta"].pop("timestamp")
        d2["meta"].pop("timestamp")
        assert d1 == d2

    def test_no_null_fields(self, all_baselines):
        """No field in the response may be None."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        assert result.country is not None
        assert result.baseline.composite is not None
        assert result.simulated.composite is not None
        assert result.baseline.rank is not None
        assert result.simulated.rank is not None
        assert result.baseline.classification is not None
        assert result.simulated.classification is not None
        for ckey in CANONICAL_AXIS_KEYS:
            assert getattr(result.baseline.axes, ckey) is not None
            assert getattr(result.simulated.axes, ckey) is not None
            assert getattr(result.delta.axes, ckey) is not None

    def test_ranks_valid(self, all_baselines):
        """Ranks are positive integers within bounds."""
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.20},
            all_baselines=all_baselines,
        )
        assert isinstance(result.baseline.rank, int)
        assert isinstance(result.simulated.rank, int)
        assert 1 <= result.baseline.rank <= 27
        assert 1 <= result.simulated.rank <= 27

    def test_classifications_valid(self, all_baselines):
        """Classifications are from the known label set."""
        from backend.scenario import VALID_CLASSIFICATIONS
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.20},
            all_baselines=all_baselines,
        )
        assert result.baseline.classification in VALID_CLASSIFICATIONS
        assert result.simulated.classification in VALID_CLASSIFICATIONS

    def test_country_in_response(self, all_baselines):
        """Response includes the country field."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        assert result.country == "SE"

    def test_meta_block(self, all_baselines):
        """Meta block has version, timestamp, bounds."""
        result = simulate(
            country_code="SE",
            adjustments={},
            all_baselines=all_baselines,
        )
        assert result.meta.version == SCENARIO_VERSION
        assert result.meta.bounds == {"min": -MAX_ADJUSTMENT, "max": MAX_ADJUSTMENT}
        assert isinstance(result.meta.timestamp, str)
        assert len(result.meta.timestamp) > 0

    def test_all_countries_work(self, all_baselines):
        """Simulation works for every EU-27 country."""
        for code, _ in EU27_CODES:
            result = simulate(
                country_code=code,
                adjustments={},
                all_baselines=all_baselines,
            )
            assert result.country == code
            assert 0.0 <= result.baseline.composite <= 1.0
            assert isinstance(result, ScenarioResponse)

    def test_model_dump_serialisable(self, all_baselines):
        """model_dump(mode='json') produces a JSON-serialisable dict."""
        import json as _json
        result = simulate(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            all_baselines=all_baselines,
        )
        body = result.model_dump(mode="json")
        serialised = _json.dumps(body)
        assert isinstance(serialised, str)
        parsed = _json.loads(serialised)
        assert parsed["country"] == "SE"
        assert set(parsed["baseline"]["axes"].keys()) == set(CANONICAL_AXIS_KEYS)
