"""
test_institutional_governance — Tests for the ISI governance institutionalization layer.

Tests that the system correctly:
    1. Classifies countries into governance tiers
    2. Assesses per-axis confidence
    3. Enforces comparability gating (consequences, not labels)
    4. Handles producer-country inversion
    5. Propagates logistics structural limitations
    6. Enforces composite eligibility rules
    7. Enforces output truthfulness contracts
    8. Export layer preserves governance metadata
    9. Determinism across structurally diverse country classes
    10. Self-audit: no overclaiming in outputs
"""

from __future__ import annotations

import pytest
from typing import Any


# ---------------------------------------------------------------------------
# MODULE IMPORTS
# ---------------------------------------------------------------------------

from backend.governance import (
    assess_axis_confidence,
    assess_country_governance,
    enforce_truthfulness_contract,
    gate_export,
    assess_all_countries,
    GOVERNANCE_TIERS,
    CONFIDENCE_LEVELS,
    CONFIDENCE_PENALTIES,
    CONFIDENCE_THRESHOLDS,
    AXIS_CONFIDENCE_BASELINES,
    PRODUCER_INVERSION_REGISTRY,
    LOGISTICS_AXIS_ID,
    LOGISTICS_ABSENT_MAX_TIER,
    MIN_AXES_FOR_COMPOSITE,
    MIN_AXES_FOR_RANKING,
    MIN_MEAN_CONFIDENCE_FOR_RANKING,
    MAX_LOW_CONFIDENCE_AXES_FOR_RANKING,
    MAX_INVERTED_AXES_FOR_COMPARABLE,
    TRUTHFULNESS_REQUIRED_FIELDS,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _make_axis_dict(
    axis_id: int,
    slug: str,
    score: float | None = 0.3,
    validity: str = "VALID",
    flags: list[str] | None = None,
    is_proxy: bool = False,
) -> dict[str, Any]:
    """Create a minimal axis result dict for governance testing."""
    return {
        "axis_id": axis_id,
        "axis_slug": slug,
        "score": score,
        "validity": validity,
        "data_quality_flags": flags or [],
        "is_proxy": is_proxy,
        "degradation_severity": 0.0,
    }


def _make_6_clean_axes() -> list[dict[str, Any]]:
    """Create 6 clean axis results."""
    slugs = ["financial", "energy", "technology", "defense", "critical_inputs", "logistics"]
    return [
        _make_axis_dict(i + 1, slugs[i], score=0.3)
        for i in range(6)
    ]


def _make_axes_missing_logistics() -> list[dict[str, Any]]:
    """Create 5 clean axes + 1 INVALID logistics axis."""
    axes = _make_6_clean_axes()
    axes[5] = _make_axis_dict(6, "logistics", score=None, validity="INVALID")
    return axes


def _make_producer_heavy_axes(inverted_axes: list[int]) -> list[dict[str, Any]]:
    """Create axes with PRODUCER_INVERSION flags on specified axis IDs."""
    axes = _make_6_clean_axes()
    for ax_id in inverted_axes:
        axes[ax_id - 1]["data_quality_flags"] = ["PRODUCER_INVERSION"]
    return axes


# ===========================================================================
# TEST CLASS 1: Axis Confidence Assessment
# ===========================================================================

class TestAxisConfidence:
    """Tests for assess_axis_confidence()."""

    def test_clean_axis_gets_high_confidence(self):
        """Clean axis with no flags should get HIGH confidence."""
        result = assess_axis_confidence(axis_id=2, data_quality_flags=[])
        assert result["confidence_level"] == "HIGH"
        assert result["confidence_score"] == AXIS_CONFIDENCE_BASELINES[2]

    def test_no_data_gets_minimal_confidence(self):
        """Axis with no data should get MINIMAL confidence."""
        result = assess_axis_confidence(axis_id=1, data_quality_flags=[], has_data=False)
        assert result["confidence_level"] == "MINIMAL"
        assert result["confidence_score"] == 0.0

    def test_producer_inversion_reduces_confidence(self):
        """Producer inversion should reduce confidence significantly."""
        clean = assess_axis_confidence(axis_id=2, data_quality_flags=[])
        inverted = assess_axis_confidence(axis_id=2, data_quality_flags=["PRODUCER_INVERSION"])
        assert inverted["confidence_score"] < clean["confidence_score"]
        assert inverted["confidence_score"] == clean["confidence_score"] - CONFIDENCE_PENALTIES["PRODUCER_INVERSION"]

    def test_cpis_non_participant_reduces_confidence(self):
        """CPIS absence should reduce financial axis confidence."""
        result = assess_axis_confidence(axis_id=1, data_quality_flags=["CPIS_NON_PARTICIPANT"])
        assert result["confidence_score"] < AXIS_CONFIDENCE_BASELINES[1]
        assert any("CPIS" in c for c in result["interpretation_constraints"])

    def test_proxy_data_caps_confidence(self):
        """Proxy data should cap confidence."""
        result = assess_axis_confidence(axis_id=6, data_quality_flags=[], is_proxy=True)
        assert result["confidence_score"] <= 0.40
        assert result["is_proxy"] is True

    def test_multiple_flags_stack(self):
        """Multiple flags should stack penalties."""
        result = assess_axis_confidence(
            axis_id=3,
            data_quality_flags=["SINGLE_CHANNEL_A", "REDUCED_PRODUCT_GRANULARITY"],
        )
        expected = AXIS_CONFIDENCE_BASELINES[3] - 0.20 - 0.10
        assert result["confidence_score"] == pytest.approx(expected, abs=1e-6)

    def test_confidence_never_negative(self):
        """Confidence should floor at 0.0 even with extreme penalties."""
        result = assess_axis_confidence(
            axis_id=1,
            data_quality_flags=["SANCTIONS_DISTORTION", "CPIS_NON_PARTICIPANT", "SINGLE_CHANNEL_A"],
        )
        assert result["confidence_score"] >= 0.0

    def test_defense_axis_lower_baseline(self):
        """Defense axis (SIPRI) should have lower baseline confidence."""
        assert AXIS_CONFIDENCE_BASELINES[4] < AXIS_CONFIDENCE_BASELINES[2]
        result = assess_axis_confidence(axis_id=4, data_quality_flags=[])
        assert result["confidence_level"] in ("MODERATE", "LOW")  # 0.55 baseline

    def test_zero_bilateral_suppliers_constraint(self):
        """Zero bilateral suppliers should produce interpretation constraint."""
        result = assess_axis_confidence(
            axis_id=4, data_quality_flags=["ZERO_BILATERAL_SUPPLIERS"]
        )
        assert any("Zero bilateral" in c for c in result["interpretation_constraints"])

    def test_logistics_axis_always_has_constraint(self):
        """Logistics axis should always carry coverage constraint."""
        result = assess_axis_confidence(axis_id=6, data_quality_flags=[])
        assert any("Logistics" in c for c in result["interpretation_constraints"])

    def test_all_confidence_levels_reachable(self):
        """All four confidence levels must be reachable."""
        # HIGH: clean energy axis
        high = assess_axis_confidence(axis_id=2, data_quality_flags=[])
        assert high["confidence_level"] == "HIGH"

        # MODERATE: defense axis clean (baseline 0.55)
        mod = assess_axis_confidence(axis_id=4, data_quality_flags=[])
        assert mod["confidence_level"] == "MODERATE"

        # LOW: defense with producer inversion (0.55 - 0.30 = 0.25)
        low = assess_axis_confidence(axis_id=4, data_quality_flags=["PRODUCER_INVERSION"])
        assert low["confidence_level"] == "LOW"

        # MINIMAL: no data
        minimal = assess_axis_confidence(axis_id=1, data_quality_flags=[], has_data=False)
        assert minimal["confidence_level"] == "MINIMAL"


# ===========================================================================
# TEST CLASS 2: Country Governance Tier Classification
# ===========================================================================

class TestCountryGovernance:
    """Tests for assess_country_governance()."""

    def test_fully_comparable_requires_6_clean_axes(self):
        """6 clean axes, no inversions, logistics present → FULLY_COMPARABLE."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "FULLY_COMPARABLE"
        assert gov["ranking_eligible"] is True
        assert gov["cross_country_comparable"] is True
        assert gov["composite_defensible"] is True

    def test_missing_logistics_caps_at_partially_comparable(self):
        """Missing logistics → cannot be FULLY_COMPARABLE."""
        axes = _make_axes_missing_logistics()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "PARTIALLY_COMPARABLE"
        assert gov["logistics_present"] is False

    def test_tier4_always_non_comparable(self):
        """TIER_4 severity → always NON_COMPARABLE."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="RU",
            axis_results=axes,
            severity_total=3.5,
            strict_comparability_tier="TIER_4",
        )
        assert gov["governance_tier"] == "NON_COMPARABLE"
        assert gov["ranking_eligible"] is False
        assert gov["composite_defensible"] is False

    def test_2_inverted_axes_low_confidence(self):
        """≥2 producer-inverted axes → LOW_CONFIDENCE."""
        # AU has exactly 2 inverted axes in PRODUCER_INVERSION_REGISTRY: [2, 5]
        axes = _make_producer_heavy_axes([2, 5])
        gov = assess_country_governance(
            country="AU",
            axis_results=axes,
            severity_total=1.0,
            strict_comparability_tier="TIER_2",
        )
        assert gov["governance_tier"] == "LOW_CONFIDENCE"
        assert gov["ranking_eligible"] is False

    def test_3_inverted_axes_non_comparable(self):
        """≥3 producer-inverted axes → NON_COMPARABLE."""
        axes = _make_producer_heavy_axes([2, 4, 5])
        gov = assess_country_governance(
            country="US",
            axis_results=axes,
            severity_total=1.5,
            strict_comparability_tier="TIER_2",
        )
        assert gov["governance_tier"] == "NON_COMPARABLE"

    def test_1_inverted_axis_partially_comparable(self):
        """1 producer-inverted axis → PARTIALLY_COMPARABLE."""
        axes = _make_producer_heavy_axes([4])
        gov = assess_country_governance(
            country="FR",
            axis_results=axes,
            severity_total=0.3,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "PARTIALLY_COMPARABLE"

    def test_few_axes_non_comparable(self):
        """Fewer than 4 axes → NON_COMPARABLE."""
        axes = _make_6_clean_axes()
        # Make 3 axes INVALID
        for i in [3, 4, 5]:
            axes[i] = _make_axis_dict(i + 1, axes[i]["axis_slug"], score=None, validity="INVALID")
        gov = assess_country_governance(
            country="MT",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "NON_COMPARABLE"
        assert gov["composite_defensible"] is False

    def test_tier3_severity_low_confidence(self):
        """TIER_3 severity → LOW_CONFIDENCE."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="XX",
            axis_results=axes,
            severity_total=2.0,
            strict_comparability_tier="TIER_3",
        )
        assert gov["governance_tier"] == "LOW_CONFIDENCE"

    def test_governance_output_has_all_required_fields(self):
        """Governance output must have all required fields."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="DE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        required = {
            "country", "governance_tier", "ranking_eligible",
            "cross_country_comparable", "composite_defensible",
            "n_axes_with_data", "mean_axis_confidence",
            "n_low_confidence_axes", "n_high_confidence_axes",
            "n_producer_inverted_axes", "producer_inverted_axes",
            "logistics_present", "logistics_proxy",
            "axis_confidences", "structural_limitations",
            "governance_interpretation",
        }
        assert required.issubset(set(gov.keys()))

    def test_structural_limitations_populated_for_non_fully(self):
        """Non-FULLY_COMPARABLE countries must have structural_limitations."""
        axes = _make_axes_missing_logistics()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] != "FULLY_COMPARABLE"
        assert len(gov["structural_limitations"]) > 0


# ===========================================================================
# TEST CLASS 3: Producer-Inversion Governance
# ===========================================================================

class TestProducerInversion:
    """Tests for producer-inversion detection and governance consequences."""

    def test_us_is_in_producer_registry(self):
        """US must be in producer inversion registry."""
        assert "US" in PRODUCER_INVERSION_REGISTRY
        assert len(PRODUCER_INVERSION_REGISTRY["US"]["inverted_axes"]) >= 2

    def test_norway_energy_inverted(self):
        """Norway must be energy-inverted."""
        assert "NO" in PRODUCER_INVERSION_REGISTRY
        assert 2 in PRODUCER_INVERSION_REGISTRY["NO"]["inverted_axes"]

    def test_france_defense_inverted(self):
        """France must be defense-inverted."""
        assert "FR" in PRODUCER_INVERSION_REGISTRY
        assert 4 in PRODUCER_INVERSION_REGISTRY["FR"]["inverted_axes"]

    def test_china_critical_inputs_inverted(self):
        """China must be critical-inputs-inverted."""
        assert "CN" in PRODUCER_INVERSION_REGISTRY
        assert 5 in PRODUCER_INVERSION_REGISTRY["CN"]["inverted_axes"]

    def test_australia_energy_and_minerals_inverted(self):
        """Australia must be energy + critical inputs inverted."""
        assert "AU" in PRODUCER_INVERSION_REGISTRY
        inverted = PRODUCER_INVERSION_REGISTRY["AU"]["inverted_axes"]
        assert 2 in inverted
        assert 5 in inverted

    def test_producer_inversion_flag_reduces_confidence(self):
        """Producer inversion flag must reduce axis confidence."""
        clean = assess_axis_confidence(axis_id=2, data_quality_flags=[])
        inverted = assess_axis_confidence(axis_id=2, data_quality_flags=["PRODUCER_INVERSION"])
        assert inverted["confidence_score"] < clean["confidence_score"]

    def test_producer_country_governance_has_limitations(self):
        """Producer countries must have structural_limitations populated."""
        axes = _make_producer_heavy_axes([2, 4])
        gov = assess_country_governance(
            country="US",
            axis_results=axes,
            severity_total=0.5,
            strict_comparability_tier="TIER_2",
        )
        assert gov["n_producer_inverted_axes"] >= 2
        assert len(gov["structural_limitations"]) > 0
        assert any("Producer" in lim or "exporter" in lim for lim in gov["structural_limitations"])

    def test_producer_country_not_cross_country_comparable(self):
        """Producer-heavy countries should not be cross-country comparable."""
        axes = _make_producer_heavy_axes([2, 4, 5])
        gov = assess_country_governance(
            country="US",
            axis_results=axes,
            severity_total=1.0,
            strict_comparability_tier="TIER_2",
        )
        assert gov["cross_country_comparable"] is False


# ===========================================================================
# TEST CLASS 4: Logistics Limitation Governance
# ===========================================================================

class TestLogisticsGovernance:
    """Tests for logistics structural gap propagation."""

    def test_logistics_is_axis_6(self):
        assert LOGISTICS_AXIS_ID == 6

    def test_missing_logistics_downgrades_governance(self):
        """Missing logistics must downgrade to at most PARTIALLY_COMPARABLE."""
        axes = _make_axes_missing_logistics()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] in ("PARTIALLY_COMPARABLE", "LOW_CONFIDENCE", "NON_COMPARABLE")
        assert gov["governance_tier"] != "FULLY_COMPARABLE"

    def test_proxy_logistics_caps_governance(self):
        """Proxy-only logistics should cap governance."""
        axes = _make_6_clean_axes()
        axes[5] = _make_axis_dict(6, "logistics", score=0.3, is_proxy=True)
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "PARTIALLY_COMPARABLE"
        assert gov["logistics_proxy"] is True

    def test_logistics_absent_in_limitations(self):
        """Missing logistics must appear in structural_limitations."""
        axes = _make_axes_missing_logistics()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert any("Logistics" in lim or "logistics" in lim for lim in gov["structural_limitations"])


# ===========================================================================
# TEST CLASS 5: Composite Eligibility
# ===========================================================================

class TestCompositeEligibility:
    """Tests for composite eligibility hardening."""

    def test_min_axes_for_composite_is_4(self):
        assert MIN_AXES_FOR_COMPOSITE == 4

    def test_min_axes_for_ranking_is_5(self):
        assert MIN_AXES_FOR_RANKING == 5

    def test_4_axes_computable_but_not_ranking_eligible(self):
        """4 axes: composite computable but not ranking-eligible."""
        axes = _make_6_clean_axes()
        # Make 2 INVALID
        for i in [4, 5]:
            axes[i] = _make_axis_dict(i + 1, axes[i]["axis_slug"], score=None, validity="INVALID")
        gov = assess_country_governance(
            country="MT",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        # 4 axes → PARTIALLY_COMPARABLE (because not 6, and logistics missing)
        assert gov["n_axes_with_data"] == 4
        assert gov["ranking_eligible"] is False  # < MIN_AXES_FOR_RANKING

    def test_3_axes_non_comparable(self):
        """3 axes: NON_COMPARABLE, composite not defensible."""
        axes = _make_6_clean_axes()
        for i in [3, 4, 5]:
            axes[i] = _make_axis_dict(i + 1, axes[i]["axis_slug"], score=None, validity="INVALID")
        gov = assess_country_governance(
            country="MT",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "NON_COMPARABLE"
        assert gov["composite_defensible"] is False

    def test_low_mean_confidence_blocks_ranking(self):
        """Low mean confidence should block ranking eligibility."""
        # Build axes where many have severely degraded confidence.
        # Need mean confidence < 0.45 (MIN_MEAN_CONFIDENCE_FOR_RANKING).
        # SANCTIONS_DISTORTION = -0.50, SINGLE_CHANNEL_A = -0.20:
        # Axes 1-4 baselines: 0.75, 0.80, 0.80, 0.55
        # After -0.50 each: 0.25, 0.30, 0.30, 0.05
        # Axes 5-6 clean: 0.75, 0.60
        # Mean = (0.25+0.30+0.30+0.05+0.75+0.60)/6 = 2.25/6 = 0.375 < 0.45 ✓
        axes = _make_6_clean_axes()
        for i in range(4):
            axes[i]["data_quality_flags"] = ["SANCTIONS_DISTORTION"]
        gov = assess_country_governance(
            country="XX",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["ranking_eligible"] is False


# ===========================================================================
# TEST CLASS 6: Truthfulness Contract
# ===========================================================================

class TestTruthfulnessContract:
    """Tests for enforce_truthfulness_contract()."""

    def test_valid_contract_passes(self):
        """Correctly governed result should pass contract."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        result = {
            "country": "SE",
            "governance": gov,
        }
        violations = enforce_truthfulness_contract(result)
        assert violations == []

    def test_missing_governance_fails(self):
        """Result without governance block must fail."""
        result = {"country": "SE"}
        violations = enforce_truthfulness_contract(result)
        assert len(violations) > 0
        assert any("governance" in v.lower() for v in violations)

    def test_non_comparable_with_rank_fails(self):
        """NON_COMPARABLE country with rank must fail."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="XX",
            axis_results=axes,
            severity_total=4.0,
            strict_comparability_tier="TIER_4",
        )
        result = {
            "country": "XX",
            "governance": gov,
            "rank": 5,
        }
        violations = enforce_truthfulness_contract(result)
        assert len(violations) > 0

    def test_low_confidence_ranking_eligible_fails(self):
        """LOW_CONFIDENCE with ranking_eligible=True must fail."""
        gov = {
            "governance_tier": "LOW_CONFIDENCE",
            "ranking_eligible": True,
            "cross_country_comparable": False,
            "composite_defensible": True,
            "axis_confidences": [{}],
            "structural_limitations": ["Some limitation"],
            "n_producer_inverted_axes": 0,
            "logistics_present": True,
            "mean_axis_confidence": 0.5,
        }
        result = {"country": "XX", "governance": gov}
        violations = enforce_truthfulness_contract(result)
        assert len(violations) > 0

    def test_non_fully_comparable_requires_limitations(self):
        """Non-FULLY_COMPARABLE without limitations must fail."""
        gov = {
            "governance_tier": "PARTIALLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "axis_confidences": [{}],
            "structural_limitations": [],  # Empty! Should fail
            "n_producer_inverted_axes": 0,
            "logistics_present": True,
            "mean_axis_confidence": 0.5,
        }
        result = {"country": "XX", "governance": gov}
        violations = enforce_truthfulness_contract(result)
        assert len(violations) > 0


# ===========================================================================
# TEST CLASS 7: Export Gate
# ===========================================================================

class TestExportGate:
    """Tests for gate_export()."""

    def test_gate_injects_governance(self):
        """gate_export must inject governance into result."""
        result = {"country": "SE", "governance": None}
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        gated = gate_export(result, gov)
        assert gated["governance"] == gov
        assert gated["governance"]["governance_tier"] == "FULLY_COMPARABLE"

    def test_gate_suppresses_ranking_for_ineligible(self):
        """Non-ranking-eligible countries must have rank=None."""
        result = {
            "country": "SE",
            "governance": None,
            "rank": 5,
            "exclude_from_rankings": False,
            "composite_adjusted": 0.3,
            "ranking_partition": "FULLY_COMPARABLE",
        }
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=4.0,
            strict_comparability_tier="TIER_4",
        )
        gated = gate_export(result, gov)
        assert gated["rank"] is None
        assert gated["exclude_from_rankings"] is True
        assert gated["composite_adjusted"] is None

    def test_gate_raises_on_truthfulness_violation(self):
        """gate_export must raise ValueError on contract violation."""
        # Create a result that will violate contract (no governance block initially)
        # We need to construct a situation where after gating, contract fails
        # E.g., LOW_CONFIDENCE but ranking_eligible=True
        gov = {
            "governance_tier": "LOW_CONFIDENCE",
            "ranking_eligible": True,  # This is wrong and will trigger violation
            "cross_country_comparable": False,
            "composite_defensible": True,
            "axis_confidences": [{"axis_id": i, "confidence_score": 0.3, "confidence_level": "LOW"} for i in range(1, 7)],
            "structural_limitations": ["Some limitation"],
            "country": "XX",
            "n_producer_inverted_axes": 0,
            "logistics_present": True,
            "mean_axis_confidence": 0.5,
            "n_low_confidence_axes": 3,
            "n_high_confidence_axes": 0,
            "producer_inverted_axes": [],
            "logistics_proxy": False,
            "n_axes_with_data": 6,
            "governance_interpretation": "test",
        }
        result = {
            "country": "XX",
            "governance": None,
        }
        with pytest.raises(ValueError, match="Truthfulness contract"):
            gate_export(result, gov)


# ===========================================================================
# TEST CLASS 8: Export Layer Truthfulness
# ===========================================================================

class TestExportLayerTruthfulness:
    """Tests that export layers preserve governance metadata."""

    def test_export_snapshot_build_country_has_governance(self):
        """build_country_json must include governance block."""
        from backend.export_snapshot import build_country_json, AXIS_SCORE_FILES
        from backend.constants import EU27_SORTED, NUM_AXES

        # Build minimal score data for one country
        all_scores = {}
        country = EU27_SORTED[0]  # AT
        for axis_num in range(1, NUM_AXES + 1):
            all_scores[axis_num] = {c: 0.3 for c in EU27_SORTED}

        result = build_country_json(country, all_scores, "v1.0", 2024, "2022–2024")
        assert "governance" in result
        assert result["governance"]["governance_tier"] in GOVERNANCE_TIERS
        assert "severity_analysis" in result
        assert "strict_comparability_tier" in result

    def test_export_snapshot_build_country_has_axis_confidence(self):
        """build_country_json axis entries must include confidence."""
        from backend.export_snapshot import build_country_json
        from backend.constants import EU27_SORTED, NUM_AXES

        all_scores = {}
        country = EU27_SORTED[0]
        for axis_num in range(1, NUM_AXES + 1):
            all_scores[axis_num] = {c: 0.3 for c in EU27_SORTED}

        result = build_country_json(country, all_scores, "v1.0", 2024, "2022–2024")
        for axis in result["axes"]:
            assert "confidence" in axis
            assert "confidence_score" in axis["confidence"]
            assert "confidence_level" in axis["confidence"]

    def test_export_snapshot_isi_json_has_truthfulness_caveat(self):
        """build_isi_json must include _truthfulness_caveat."""
        from backend.export_snapshot import build_isi_json
        from backend.constants import EU27_SORTED, NUM_AXES

        all_scores = {}
        for axis_num in range(1, NUM_AXES + 1):
            all_scores[axis_num] = {c: 0.3 for c in EU27_SORTED}

        result = build_isi_json(all_scores, "v1.0", 2024, "2022–2024")
        assert "_truthfulness_caveat" in result
        assert "governance" in result["_truthfulness_caveat"].lower()

    def test_export_snapshot_axis_json_has_confidence(self):
        """build_axis_json must include per-country confidence."""
        from backend.export_snapshot import build_axis_json
        from backend.constants import EU27_SORTED, NUM_AXES

        all_scores = {}
        for axis_num in range(1, NUM_AXES + 1):
            all_scores[axis_num] = {c: 0.3 for c in EU27_SORTED}

        result = build_axis_json(1, all_scores, "v1.0", 2024, "2022–2024")
        for country_entry in result["countries"]:
            assert "confidence" in country_entry


# ===========================================================================
# TEST CLASS 9: Comparability Gating (Consequences)
# ===========================================================================

class TestComparabilityGating:
    """Tests that comparability gating has CONSEQUENCES, not just labels."""

    def test_non_comparable_suppresses_composite_adjusted(self):
        """NON_COMPARABLE must suppress composite_adjusted."""
        result = {
            "country": "XX",
            "composite_adjusted": 0.35,
            "rank": 12,
            "exclude_from_rankings": False,
            "ranking_partition": "FULLY_COMPARABLE",
            "governance": None,
        }
        gov = {
            "governance_tier": "NON_COMPARABLE",
            "ranking_eligible": False,
            "cross_country_comparable": False,
            "composite_defensible": False,
            "axis_confidences": [{"axis_id": i, "confidence_score": 0.0, "confidence_level": "MINIMAL"} for i in range(1, 7)],
            "structural_limitations": ["Fewer than 4 axes"],
            "country": "XX",
            "n_producer_inverted_axes": 0,
            "logistics_present": False,
            "mean_axis_confidence": 0.0,
            "n_low_confidence_axes": 6,
            "n_high_confidence_axes": 0,
            "producer_inverted_axes": [],
            "logistics_proxy": False,
            "n_axes_with_data": 3,
            "governance_interpretation": "NON-COMPARABLE",
        }
        gated = gate_export(result, gov)
        assert gated["composite_adjusted"] is None
        assert gated["rank"] is None
        assert gated["exclude_from_rankings"] is True

    def test_low_confidence_blocks_ranking(self):
        """LOW_CONFIDENCE must block ranking eligibility."""
        # AU has exactly 2 inverted axes in registry: [2, 5] → LOW_CONFIDENCE
        axes = _make_producer_heavy_axes([2, 5])
        gov = assess_country_governance(
            country="AU",
            axis_results=axes,
            severity_total=1.0,
            strict_comparability_tier="TIER_2",
        )
        assert gov["governance_tier"] == "LOW_CONFIDENCE"
        assert gov["ranking_eligible"] is False

    def test_partially_comparable_with_5_axes_can_rank(self):
        """PARTIALLY_COMPARABLE with 5+ clean axes can rank."""
        axes = _make_6_clean_axes()
        axes[5] = _make_axis_dict(6, "logistics", score=None, validity="INVALID")
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "PARTIALLY_COMPARABLE"
        assert gov["ranking_eligible"] is True

    def test_fully_comparable_allows_everything(self):
        """FULLY_COMPARABLE allows ranking, comparison, defensible composite."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance(
            country="SE",
            axis_results=axes,
            severity_total=0.0,
            strict_comparability_tier="TIER_1",
        )
        assert gov["governance_tier"] == "FULLY_COMPARABLE"
        assert gov["ranking_eligible"] is True
        assert gov["cross_country_comparable"] is True
        assert gov["composite_defensible"] is True


# ===========================================================================
# TEST CLASS 10: Determinism Across Country Classes
# ===========================================================================

class TestGovernanceDeterminism:
    """Tests that governance assessment is deterministic."""

    def test_same_inputs_same_outputs(self):
        """Identical inputs must produce identical governance."""
        axes = _make_6_clean_axes()
        gov1 = assess_country_governance("SE", axes, 0.0, "TIER_1")
        gov2 = assess_country_governance("SE", axes, 0.0, "TIER_1")
        assert gov1 == gov2

    def test_different_countries_same_data_same_tier(self):
        """Same data structure → same governance tier regardless of code."""
        axes = _make_6_clean_axes()
        gov_se = assess_country_governance("SE", axes, 0.0, "TIER_1")
        gov_fi = assess_country_governance("FI", axes, 0.0, "TIER_1")
        assert gov_se["governance_tier"] == gov_fi["governance_tier"]

    def test_producer_country_different_from_importer(self):
        """Producer and importer countries must get different governance."""
        clean_axes = _make_6_clean_axes()
        inverted_axes = _make_producer_heavy_axes([2, 4, 5])

        gov_importer = assess_country_governance("SE", clean_axes, 0.0, "TIER_1")
        gov_producer = assess_country_governance("US", inverted_axes, 1.0, "TIER_2")

        assert gov_importer["governance_tier"] != gov_producer["governance_tier"]


# ===========================================================================
# TEST CLASS 11: Expanded Determinism Proof (SIPRI)
# ===========================================================================

class TestExpandedDeterminism:
    """Extended determinism verification across structurally diverse countries.

    Tests a broader country basket including:
    - EU countries (SE, DE, FR, PL)
    - Japan (importer)
    - Producer-heavy (US)
    - Low-confidence / partial
    """

    EXPANDED_BASKET = ["JP", "DE", "FR", "US", "GB", "SE", "PL", "IT"]

    def test_sipri_determinism_expanded_basket(self):
        """SIPRI ingestion must be deterministic for expanded basket."""
        from pipeline.ingest.sipri import ingest_sipri

        for cc in self.EXPANDED_BASKET:
            ds1, stats1 = ingest_sipri(cc)
            ds2, stats2 = ingest_sipri(cc)

            if ds1 is None and ds2 is None:
                continue

            assert ds1 is not None, f"{cc}: run1 produced None"
            assert ds2 is not None, f"{cc}: run2 produced None"
            assert ds1.data_hash == ds2.data_hash, (
                f"{cc}: non-deterministic! "
                f"hash1={ds1.data_hash[:16]} != hash2={ds2.data_hash[:16]}"
            )
            assert len(ds1.records) == len(ds2.records), f"{cc}: record count differs"
            assert ds1.total_value == ds2.total_value, f"{cc}: total_value differs"

    def test_expanded_basket_includes_all_structural_classes(self):
        """Basket must cover importer, balanced, and producer classes."""
        importers = {"JP", "PL", "IT"}
        balanced = {"DE", "FR", "GB"}
        producers = {"US"}

        assert importers.issubset(set(self.EXPANDED_BASKET))
        assert balanced.issubset(set(self.EXPANDED_BASKET))
        assert producers.issubset(set(self.EXPANDED_BASKET))


# ===========================================================================
# TEST CLASS 12: Self-Audit for Overclaiming
# ===========================================================================

class TestSelfAuditOverclaiming:
    """Adversarial self-audit: check for overclaiming in outputs."""

    def test_governance_interpretation_contains_warnings_for_non_fully(self):
        """Non-FULLY_COMPARABLE governance must include warning language."""
        axes = _make_axes_missing_logistics()
        gov = assess_country_governance("SE", axes, 0.0, "TIER_1")
        interp = gov["governance_interpretation"]
        assert "PARTIALLY" in interp or "LIMITATION" in interp

    def test_low_confidence_interpretation_warns_against_ranking(self):
        """LOW_CONFIDENCE interpretation must warn against ranking use."""
        axes = _make_producer_heavy_axes([2, 4])
        gov = assess_country_governance("US", axes, 1.0, "TIER_2")
        interp = gov["governance_interpretation"]
        assert "LOW CONFIDENCE" in interp or "RANKING EXCLUDED" in interp

    def test_non_comparable_interpretation_prohibits_comparison(self):
        """NON_COMPARABLE interpretation must prohibit comparison."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance("RU", axes, 4.0, "TIER_4")
        interp = gov["governance_interpretation"]
        assert "NON-COMPARABLE" in interp
        assert "Do NOT" in interp or "not" in interp.lower()

    def test_fully_comparable_does_not_overclaim(self):
        """Even FULLY_COMPARABLE must not overclaim universality."""
        axes = _make_6_clean_axes()
        gov = assess_country_governance("SE", axes, 0.0, "TIER_1")
        interp = gov["governance_interpretation"]
        assert "within the measured construct" in interp

    def test_confidence_baselines_reflect_real_limitations(self):
        """Axis confidence baselines must not be inflated."""
        # Defense (SIPRI) must be lower than trade axes
        assert AXIS_CONFIDENCE_BASELINES[4] < AXIS_CONFIDENCE_BASELINES[2]
        assert AXIS_CONFIDENCE_BASELINES[4] < AXIS_CONFIDENCE_BASELINES[3]
        # Logistics must be lower than financial
        assert AXIS_CONFIDENCE_BASELINES[6] < AXIS_CONFIDENCE_BASELINES[1]
        # No baseline should exceed 0.90 (nothing is that reliable)
        for ax_id, baseline in AXIS_CONFIDENCE_BASELINES.items():
            assert baseline <= 0.90, f"Axis {ax_id} baseline {baseline} is overclaimed"

    def test_producer_inversion_registry_covers_known_producers(self):
        """Registry must cover all structurally important producer countries."""
        known_producers = {"US", "NO", "AU", "FR", "DE", "CN"}
        for country in known_producers:
            assert country in PRODUCER_INVERSION_REGISTRY, (
                f"{country} missing from producer inversion registry"
            )

    def test_all_governance_tiers_are_reachable(self):
        """All four governance tiers must be reachable through legitimate inputs."""
        # FULLY_COMPARABLE
        gov = assess_country_governance("SE", _make_6_clean_axes(), 0.0, "TIER_1")
        assert gov["governance_tier"] == "FULLY_COMPARABLE"

        # PARTIALLY_COMPARABLE
        gov = assess_country_governance("SE", _make_axes_missing_logistics(), 0.0, "TIER_1")
        assert gov["governance_tier"] == "PARTIALLY_COMPARABLE"

        # LOW_CONFIDENCE — AU has exactly 2 inverted axes in registry: [2, 5]
        gov = assess_country_governance("AU", _make_producer_heavy_axes([2, 5]), 1.0, "TIER_2")
        assert gov["governance_tier"] == "LOW_CONFIDENCE"

        # NON_COMPARABLE
        gov = assess_country_governance("RU", _make_6_clean_axes(), 4.0, "TIER_4")
        assert gov["governance_tier"] == "NON_COMPARABLE"


# ===========================================================================
# TEST CLASS 13: Plausibility → Governance Upgrade
# ===========================================================================

class TestPlausibilityGovernance:
    """Tests that plausibility checks have governance consequences."""

    def test_plausibility_check_exists(self):
        """CHECK 13 (output_plausibility_check) must exist."""
        from pipeline.validate import check_output_plausibility, ALL_CHECKS
        assert check_output_plausibility in ALL_CHECKS

    def test_plausibility_returns_validation_result(self):
        """Plausibility check must return structured ValidationResult."""
        from pipeline.validate import check_output_plausibility, ValidationResult
        from pipeline.schema import BilateralDataset, BilateralRecord

        ds = BilateralDataset(
            reporter="JP", axis="defense", source="sipri",
            year_range=(2020, 2025),
            records=[
                BilateralRecord(reporter="JP", partner="US", year=2022, value=100.0, source="sipri", axis="defense", unit="TIV"),
            ],
        )
        ds.compute_metadata()
        result = check_output_plausibility(ds)
        assert isinstance(result, ValidationResult)


# ===========================================================================
# TEST CLASS 14: Constants and Registry Integrity
# ===========================================================================

class TestGovernanceConstants:
    """Tests for governance constants integrity."""

    def test_governance_tiers_are_four(self):
        assert len(GOVERNANCE_TIERS) == 4

    def test_confidence_levels_are_four(self):
        assert len(CONFIDENCE_LEVELS) == 4

    def test_all_6_axes_have_baselines(self):
        for ax_id in range(1, 7):
            assert ax_id in AXIS_CONFIDENCE_BASELINES

    def test_confidence_thresholds_descending(self):
        """Thresholds must be in descending order."""
        thresholds = [t[0] for t in CONFIDENCE_THRESHOLDS]
        assert thresholds == sorted(thresholds, reverse=True)

    def test_penalties_all_positive(self):
        """All confidence penalties must be positive."""
        for flag, penalty in CONFIDENCE_PENALTIES.items():
            assert penalty > 0, f"Penalty for {flag} is not positive"

    def test_truthfulness_required_fields_not_empty(self):
        assert len(TRUTHFULNESS_REQUIRED_FIELDS) > 0
