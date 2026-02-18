"""
tests/test_scenario.py — Unit tests for ISI scenario simulation engine (v0.4).

Tests the pure computation module (backend.scenario) directly.

Response contract (v0.4):
    {baseline_composite, simulated_composite, baseline_rank, simulated_rank,
     baseline_classification, simulated_classification,
     axis_results: {key: {baseline, simulated, delta}}}

Requires: pytest
"""

from __future__ import annotations

import math

import pytest

from backend.scenario import (
    CANONICAL_AXIS_KEYS,
    CANONICAL_TO_ISI_KEY,
    SHORT_SLUG_TO_CANONICAL,
    VALID_CLASSIFICATIONS,
    ScenarioRequest,
    classify,
    clamp01,
    compute_composite,
    compute_rank,
    compute_baseline_rank,
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

# SE custom baseline for deterministic testing
SE_SCORES = {
    "axis_1_financial": 0.15,
    "axis_2_energy": 0.10,
    "axis_3_technology": 0.25,
    "axis_4_defense": 0.30,
    "axis_5_critical_inputs": 0.20,
    "axis_6_logistics": 0.18,
}

# Shorthand canonical keys for readability
K_FIN = "financial_external_supplier_concentration"
K_ENE = "energy_external_supplier_concentration"
K_TEC = "technology_semiconductor_external_supplier_concentration"
K_DEF = "defense_external_supplier_concentration"
K_CRI = "critical_inputs_raw_materials_external_supplier_concentration"
K_LOG = "logistics_freight_external_supplier_concentration"


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
        scores = {key: 0.5 for key in CANONICAL_AXIS_KEYS}
        assert compute_composite(scores) == pytest.approx(0.5)

    def test_mixed_scores(self):
        scores = dict(zip(CANONICAL_AXIS_KEYS, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]))
        expected = sum([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]) / 6
        assert compute_composite(scores) == pytest.approx(expected)

    def test_all_zero(self):
        scores = {key: 0.0 for key in CANONICAL_AXIS_KEYS}
        assert compute_composite(scores) == 0.0

    def test_all_one(self):
        scores = {key: 1.0 for key in CANONICAL_AXIS_KEYS}
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


class TestComputeBaselineRank:
    def test_baseline_rank_in_bounds(self, all_baselines):
        rank = compute_baseline_rank("SE", all_baselines)
        assert 1 <= rank <= 27


# ---------------------------------------------------------------------------
# Scenario simulation integration tests
# ---------------------------------------------------------------------------

class TestSimulate:
    def test_response_contract_shape(self, all_baselines):
        """Response has exact v0.4 contract keys."""
        result = simulate(
            country_code="SE",
            adjustments={key: 0.0 for key in CANONICAL_AXIS_KEYS},
            all_baselines=all_baselines,
            request_id="test-001",
        )

        expected_keys = {
            "baseline_composite", "simulated_composite",
            "baseline_rank", "simulated_rank",
            "baseline_classification", "simulated_classification",
            "axis_results",
        }
        assert set(result.keys()) == expected_keys

        # axis_results has all 6 canonical keys with baseline/simulated/delta
        ar = result["axis_results"]
        assert isinstance(ar, dict)
        assert set(ar.keys()) == set(CANONICAL_AXIS_KEYS)
        for key in CANONICAL_AXIS_KEYS:
            assert set(ar[key].keys()) == {"baseline", "simulated", "delta"}

    def test_defense_plus_010(self, all_baselines):
        """SE baseline + defense +0.10 → defense simulated increases."""
        result = simulate(
            country_code="SE",
            adjustments={
                **{k: 0.0 for k in CANONICAL_AXIS_KEYS},
                K_DEF: 0.10,
            },
            all_baselines=all_baselines,
            request_id="test-002",
        )

        # Composites bounded
        assert 0.0 <= result["baseline_composite"] <= 1.0
        assert 0.0 <= result["simulated_composite"] <= 1.0

        # Simulated > baseline (defense increased)
        assert result["simulated_composite"] > result["baseline_composite"]

        # Ranks are valid
        assert isinstance(result["baseline_rank"], int)
        assert isinstance(result["simulated_rank"], int)
        assert 1 <= result["baseline_rank"] <= 27
        assert 1 <= result["simulated_rank"] <= 27

        # Classifications valid
        assert result["baseline_classification"] in VALID_CLASSIFICATIONS
        assert result["simulated_classification"] in VALID_CLASSIFICATIONS

        # Defense axis: baseline=0.30, simulated=0.40, delta=+0.10
        def_axis = result["axis_results"][K_DEF]
        assert def_axis["baseline"] == pytest.approx(0.30)
        assert def_axis["simulated"] == pytest.approx(0.40)
        assert def_axis["delta"] == pytest.approx(0.10)

    def test_all_zero_adjustments_baseline_equals_simulated(self, all_baselines):
        """All-zero adjustments: baseline == simulated for every field."""
        result = simulate(
            country_code="SE",
            adjustments={key: 0.0 for key in CANONICAL_AXIS_KEYS},
            all_baselines=all_baselines,
            request_id="test-003",
        )

        assert result["baseline_composite"] == result["simulated_composite"]
        assert result["baseline_rank"] == result["simulated_rank"]
        assert result["baseline_classification"] == result["simulated_classification"]

        for key in CANONICAL_AXIS_KEYS:
            assert result["axis_results"][key]["delta"] == pytest.approx(0.0)
            assert (
                result["axis_results"][key]["baseline"]
                == result["axis_results"][key]["simulated"]
            )

    def test_clamp_at_zero(self, all_baselines):
        """Negative adjustment clamps axis at 0.0."""
        result = simulate(
            country_code="SE",
            adjustments={
                **{k: 0.0 for k in CANONICAL_AXIS_KEYS},
                K_ENE: -0.20,  # 0.10 - 0.20 = -0.10 → clamped to 0.0
            },
            all_baselines=all_baselines,
            request_id="test-004",
        )
        assert result["axis_results"][K_ENE]["simulated"] == 0.0

    def test_missing_country_raises(self, all_baselines):
        """Country not in baselines → ValueError."""
        with pytest.raises(ValueError, match="not found"):
            simulate(
                country_code="XX",
                adjustments={key: 0.0 for key in CANONICAL_AXIS_KEYS},
                all_baselines=all_baselines,
                request_id="test-005",
            )

    def test_multiple_adjustments(self, all_baselines):
        """Multiple axes adjusted simultaneously."""
        result = simulate(
            country_code="SE",
            adjustments={
                **{k: 0.0 for k in CANONICAL_AXIS_KEYS},
                K_DEF: 0.10,
                K_ENE: -0.05,
                K_FIN: 0.05,
            },
            all_baselines=all_baselines,
            request_id="test-006",
        )
        ar = result["axis_results"]
        assert ar[K_DEF]["simulated"] == pytest.approx(0.40)
        assert ar[K_ENE]["simulated"] == pytest.approx(0.05)
        assert ar[K_FIN]["simulated"] == pytest.approx(0.20)

    def test_idempotent(self, all_baselines):
        """Same inputs always produce identical outputs."""
        kwargs = dict(
            country_code="SE",
            adjustments={**{k: 0.0 for k in CANONICAL_AXIS_KEYS}, K_DEF: 0.10},
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
            adjustments={key: 0.0 for key in CANONICAL_AXIS_KEYS},
            all_baselines=all_baselines,
            request_id="test-null",
        )
        assert result["baseline_composite"] is not None
        assert result["simulated_composite"] is not None
        assert result["baseline_rank"] is not None
        assert result["simulated_rank"] is not None
        assert result["baseline_classification"] is not None
        assert result["simulated_classification"] is not None
        for key in CANONICAL_AXIS_KEYS:
            for field in ("baseline", "simulated", "delta"):
                assert result["axis_results"][key][field] is not None


# ---------------------------------------------------------------------------
# Pydantic validation tests — tolerant, never-400
# ---------------------------------------------------------------------------

class TestScenarioRequestValidation:
    def test_valid_request_canonical_keys(self):
        """Full canonical keys accepted."""
        req = ScenarioRequest(
            country_code="SE",
            adjustments={K_DEF: 0.10},
        )
        assert req.country_code == "SE"
        # All 6 keys present after normalization (missing filled with 0.0)
        assert len(req.adjustments) == 6
        assert req.adjustments[K_DEF] == 0.10

    def test_short_slugs_mapped_to_canonical(self):
        """Short slugs (defense, energy, ...) auto-mapped to canonical keys."""
        req = ScenarioRequest(
            country_code="SE",
            adjustments={"defense": 0.10, "energy": -0.05},
        )
        assert req.adjustments[K_DEF] == 0.10
        assert req.adjustments[K_ENE] == -0.05
        # Missing keys filled with 0.0
        assert req.adjustments[K_FIN] == 0.0

    def test_uppercase_country(self):
        req = ScenarioRequest(country_code="se", adjustments={})
        assert req.country_code == "SE"

    def test_alias_countryCode(self):
        """Frontend sends camelCase countryCode."""
        req = ScenarioRequest.model_validate({"countryCode": "SE", "adjustments": {}})
        assert req.country_code == "SE"

    def test_alias_axis_shifts(self):
        """Frontend sends axis_shifts as alias for adjustments."""
        req = ScenarioRequest.model_validate({
            "country_code": "SE",
            "axis_shifts": {K_DEF: 0.05},
        })
        assert req.adjustments[K_DEF] == 0.05

    def test_unknown_keys_silently_ignored(self):
        """Unknown axis keys are silently dropped, not rejected."""
        req = ScenarioRequest(
            country_code="SE",
            adjustments={"unknown_axis": 0.10, K_DEF: 0.05},
        )
        # unknown_axis dropped, defense kept, rest filled with 0.0
        assert "unknown_axis" not in req.adjustments
        assert req.adjustments[K_DEF] == 0.05
        assert len(req.adjustments) == 6

    def test_out_of_range_clamped(self):
        """Values outside [-0.20, +0.20] are clamped, not rejected."""
        req = ScenarioRequest(
            country_code="SE",
            adjustments={K_DEF: 0.50},
        )
        assert req.adjustments[K_DEF] == 0.20

    def test_negative_out_of_range_clamped(self):
        req = ScenarioRequest(
            country_code="SE",
            adjustments={K_DEF: -0.50},
        )
        assert req.adjustments[K_DEF] == -0.20

    def test_nan_replaced_with_zero(self):
        """NaN values are replaced with 0.0, not rejected."""
        req = ScenarioRequest(
            country_code="SE",
            adjustments={K_DEF: float("nan")},
        )
        assert req.adjustments[K_DEF] == 0.0

    def test_empty_adjustments_fills_all_zeros(self):
        """Empty adjustments {} → all 6 keys filled with 0.0."""
        req = ScenarioRequest(country_code="SE", adjustments={})
        assert len(req.adjustments) == 6
        for key in CANONICAL_AXIS_KEYS:
            assert req.adjustments[key] == 0.0

    def test_default_adjustments_fills_all_zeros(self):
        """Omitted adjustments → all 6 keys filled with 0.0."""
        req = ScenarioRequest(country_code="SE")
        assert len(req.adjustments) == 6

    def test_extra_fields_ignored(self):
        """Extra top-level fields silently ignored."""
        req = ScenarioRequest(
            country_code="SE",
            adjustments={K_DEF: 0.10},
            extra_field="ignored",  # type: ignore[call-arg]
        )
        assert req.country_code == "SE"

    def test_meta_optional(self):
        """meta field accepted and optional."""
        req = ScenarioRequest.model_validate({
            "country_code": "SE",
            "adjustments": {},
            "meta": {"preset": "baseline", "client_version": "1.0.0"},
        })
        assert req.meta is not None
        assert req.meta.preset == "baseline"
        assert req.meta.client_version == "1.0.0"

    def test_meta_absent(self):
        req = ScenarioRequest(country_code="SE", adjustments={})
        assert req.meta is None

    def test_boundary_adjustment_accepted(self):
        req = ScenarioRequest(country_code="SE", adjustments={K_DEF: 0.20})
        assert req.adjustments[K_DEF] == 0.20
        req2 = ScenarioRequest(country_code="SE", adjustments={K_DEF: -0.20})
        assert req2.adjustments[K_DEF] == -0.20
