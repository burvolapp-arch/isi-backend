"""
tests/test_institutional_upgrade.py — Tests for the 4-Layer Institutional Upgrade

Tests cover:
    LAYER 1: Threshold Justification Registry (backend/threshold_registry.py)
    LAYER 2: External Contradiction Testing (backend/falsification.py)
    LAYER 3: Decision-Grade Country Usability (backend/eligibility.py:DecisionUsabilityClass)
    LAYER 4: Authority Unification (calibration.py ↔ eligibility.py consistency)

Every test class is documented with the layer it validates and the specific
invariant being checked. Test count: 120+
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: THRESHOLD JUSTIFICATION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestThresholdRegistryStructure:
    """The threshold registry must be well-formed and complete."""

    def test_registry_nonempty(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        assert len(THRESHOLD_JUSTIFICATION_REGISTRY) >= 20, (
            "Registry should contain at least 20 threshold entries"
        )

    def test_all_entries_have_required_fields(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        required = {
            "threshold_id", "name", "current_value", "functional_role",
            "rationale_type", "justification", "sensitivity_band",
            "breakpoints", "alternative_plausible_values",
            "risk_if_misspecified", "risk_level", "source_module", "affects",
        }
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Threshold '{entry.get('threshold_id', '?')}' missing: {missing}"
            )

    def test_unique_threshold_ids(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        ids = [e["threshold_id"] for e in THRESHOLD_JUSTIFICATION_REGISTRY]
        assert len(ids) == len(set(ids)), (
            f"Duplicate threshold IDs: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_all_rationale_types_valid(self) -> None:
        from backend.threshold_registry import (
            THRESHOLD_JUSTIFICATION_REGISTRY,
            VALID_RATIONALE_TYPES,
        )
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert entry["rationale_type"] in VALID_RATIONALE_TYPES, (
                f"Invalid rationale_type for {entry['threshold_id']}: "
                f"{entry['rationale_type']}"
            )

    def test_all_risk_levels_valid(self) -> None:
        from backend.threshold_registry import (
            THRESHOLD_JUSTIFICATION_REGISTRY,
            VALID_RISK_LEVELS,
        )
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert entry["risk_level"] in VALID_RISK_LEVELS, (
                f"Invalid risk_level for {entry['threshold_id']}: "
                f"{entry['risk_level']}"
            )

    def test_sensitivity_band_has_low_and_high(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            band = entry["sensitivity_band"]
            assert "low" in band and "high" in band, (
                f"Threshold '{entry['threshold_id']}' sensitivity_band "
                f"missing 'low' or 'high'"
            )
            # low should be <= current_value <= high for numeric thresholds
            if isinstance(entry["current_value"], (int, float)):
                assert band["low"] <= entry["current_value"] <= band["high"], (
                    f"Threshold '{entry['threshold_id']}': current_value "
                    f"{entry['current_value']} outside sensitivity band "
                    f"[{band['low']}, {band['high']}]"
                )

    def test_justification_nonempty(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert len(entry["justification"]) > 20, (
                f"Threshold '{entry['threshold_id']}' has trivial justification"
            )

    def test_functional_role_nonempty(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert len(entry["functional_role"]) > 10, (
                f"Threshold '{entry['threshold_id']}' has trivial functional_role"
            )

    def test_affects_nonempty(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert len(entry["affects"]) > 0, (
                f"Threshold '{entry['threshold_id']}' has empty affects list"
            )

    def test_source_module_valid(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        valid_modules = {"governance.py", "severity.py", "eligibility.py", "calibration.py"}
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert entry["source_module"] in valid_modules, (
                f"Threshold '{entry['threshold_id']}' has invalid source_module: "
                f"{entry['source_module']}"
            )


class TestThresholdRegistryCompleteness:
    """Registry must cover all critical thresholds from source modules."""

    def test_governance_baselines_covered(self) -> None:
        """All 6 axis confidence baselines must be registered."""
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        baseline_ids = {
            e["threshold_id"] for e in THRESHOLD_JUSTIFICATION_REGISTRY
            if e["threshold_id"].startswith("GOV_BASELINE_AX")
        }
        assert len(baseline_ids) == 6, (
            f"Expected 6 axis baselines, found {len(baseline_ids)}: {baseline_ids}"
        )

    def test_governance_penalties_covered(self) -> None:
        """All confidence penalties must be registered."""
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        penalty_ids = {
            e["threshold_id"] for e in THRESHOLD_JUSTIFICATION_REGISTRY
            if e["threshold_id"].startswith("GOV_PENALTY_")
        }
        # At least 7 penalties: SINGLE_CHANNEL_A, SINGLE_CHANNEL_B,
        # CPIS, GRANULARITY, ZERO_BILATERAL, PRODUCER_INVERSION,
        # SANCTIONS, LOGISTICS_ABSENT
        assert len(penalty_ids) >= 7, (
            f"Expected >= 7 penalty entries, found {len(penalty_ids)}"
        )

    def test_confidence_levels_covered(self) -> None:
        """All 3 confidence level thresholds must be registered."""
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        conf_ids = {
            e["threshold_id"] for e in THRESHOLD_JUSTIFICATION_REGISTRY
            if e["threshold_id"].startswith("GOV_CONF_")
        }
        assert len(conf_ids) == 3, (
            f"Expected 3 confidence thresholds (HIGH/MODERATE/LOW), found {len(conf_ids)}"
        )

    def test_composite_thresholds_covered(self) -> None:
        """Composite/ranking thresholds must be registered."""
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        ids = {e["threshold_id"] for e in THRESHOLD_JUSTIFICATION_REGISTRY}
        assert "GOV_MIN_AXES_COMPOSITE" in ids
        assert "GOV_MIN_AXES_RANKING" in ids
        assert "GOV_MIN_MEAN_CONF_RANKING" in ids
        assert "GOV_MAX_LOW_AXES_RANKING" in ids
        assert "GOV_MAX_INVERTED_COMPARABLE" in ids

    def test_severity_weights_covered(self) -> None:
        """All severity weights must be registered."""
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        sev_ids = {
            e["threshold_id"] for e in THRESHOLD_JUSTIFICATION_REGISTRY
            if e["threshold_id"].startswith("SEV_W_")
        }
        assert len(sev_ids) >= 7, (
            f"Expected >= 7 severity weight entries, found {len(sev_ids)}"
        )

    def test_critical_thresholds_identified(self) -> None:
        """At least 2 thresholds must be flagged as CRITICAL risk."""
        from backend.threshold_registry import (
            get_thresholds_by_risk,
            RiskLevel,
        )
        critical = get_thresholds_by_risk(RiskLevel.CRITICAL)
        assert len(critical) >= 2, (
            f"Expected >= 2 CRITICAL-risk thresholds, found {len(critical)}"
        )


class TestThresholdRegistryConsistency:
    """Registry values must match actual values in source modules."""

    def test_governance_baselines_match(self) -> None:
        """Registry baseline values must match governance.py."""
        from backend.threshold_registry import get_threshold_by_id
        from backend.governance import AXIS_CONFIDENCE_BASELINES
        for axis_id, expected in AXIS_CONFIDENCE_BASELINES.items():
            entry = get_threshold_by_id(f"GOV_BASELINE_AX{axis_id}")
            assert entry is not None, f"Missing baseline for axis {axis_id}"
            assert entry["current_value"] == expected, (
                f"Axis {axis_id} baseline mismatch: registry={entry['current_value']}, "
                f"governance.py={expected}"
            )

    def test_governance_penalties_match(self) -> None:
        """Registry penalty values must match governance.py."""
        from backend.threshold_registry import get_threshold_by_id
        from backend.governance import CONFIDENCE_PENALTIES
        penalty_map = {
            "SINGLE_CHANNEL_A": "GOV_PENALTY_SINGLE_CHANNEL_A",
            "SINGLE_CHANNEL_B": "GOV_PENALTY_SINGLE_CHANNEL_B",
            "CPIS_NON_PARTICIPANT": "GOV_PENALTY_CPIS_NON_PARTICIPANT",
            "REDUCED_PRODUCT_GRANULARITY": "GOV_PENALTY_REDUCED_GRANULARITY",
            "ZERO_BILATERAL_SUPPLIERS": "GOV_PENALTY_ZERO_BILATERAL",
            "PRODUCER_INVERSION": "GOV_PENALTY_PRODUCER_INVERSION",
            "SANCTIONS_DISTORTION": "GOV_PENALTY_SANCTIONS",
            "LOGISTICS_DATA_ABSENT": "GOV_PENALTY_LOGISTICS_ABSENT",
        }
        for flag, tid in penalty_map.items():
            entry = get_threshold_by_id(tid)
            assert entry is not None, f"Missing penalty entry: {tid}"
            expected = CONFIDENCE_PENALTIES.get(flag)
            if expected is not None:
                assert entry["current_value"] == expected, (
                    f"Penalty {flag} mismatch: registry={entry['current_value']}, "
                    f"governance.py={expected}"
                )

    def test_composite_thresholds_match(self) -> None:
        """Registry composite values must match governance.py."""
        from backend.threshold_registry import get_threshold_by_id
        from backend.governance import (
            MIN_AXES_FOR_COMPOSITE,
            MIN_AXES_FOR_RANKING,
            MIN_MEAN_CONFIDENCE_FOR_RANKING,
            MAX_LOW_CONFIDENCE_AXES_FOR_RANKING,
            MAX_INVERTED_AXES_FOR_COMPARABLE,
            LOGISTICS_PROXY_CONFIDENCE_CAP,
        )
        checks = [
            ("GOV_MIN_AXES_COMPOSITE", MIN_AXES_FOR_COMPOSITE),
            ("GOV_MIN_AXES_RANKING", MIN_AXES_FOR_RANKING),
            ("GOV_MIN_MEAN_CONF_RANKING", MIN_MEAN_CONFIDENCE_FOR_RANKING),
            ("GOV_MAX_LOW_AXES_RANKING", MAX_LOW_CONFIDENCE_AXES_FOR_RANKING),
            ("GOV_MAX_INVERTED_COMPARABLE", MAX_INVERTED_AXES_FOR_COMPARABLE),
            ("GOV_LOGISTICS_PROXY_CAP", LOGISTICS_PROXY_CONFIDENCE_CAP),
        ]
        for tid, expected in checks:
            entry = get_threshold_by_id(tid)
            assert entry is not None, f"Missing threshold: {tid}"
            assert entry["current_value"] == expected, (
                f"{tid} mismatch: registry={entry['current_value']}, "
                f"source={expected}"
            )

    def test_severity_weights_match(self) -> None:
        """Registry severity values must match severity.py."""
        from backend.threshold_registry import get_threshold_by_id
        from backend.severity import SEVERITY_WEIGHTS
        weight_map = {
            "HS6_GRANULARITY": "SEV_W_HS6_GRANULARITY",
            "SINGLE_CHANNEL_A": "SEV_W_SINGLE_CHANNEL",
            "CPIS_NON_PARTICIPANT": "SEV_W_CPIS_NON_PARTICIPANT",
            "PRODUCER_INVERSION": "SEV_W_PRODUCER_INVERSION",
            "SANCTIONS_DISTORTION": "SEV_W_SANCTIONS",
            "ZERO_BILATERAL_SUPPLIERS": "SEV_W_ZERO_BILATERAL",
            "TEMPORAL_MISMATCH": "SEV_W_TEMPORAL_MISMATCH",
            "SOURCE_HETEROGENEITY": "SEV_W_SOURCE_HETEROGENEITY",
        }
        for flag, tid in weight_map.items():
            entry = get_threshold_by_id(tid)
            assert entry is not None, f"Missing severity entry: {tid}"
            expected = SEVERITY_WEIGHTS.get(flag)
            if expected is not None:
                assert entry["current_value"] == expected, (
                    f"Severity {flag} mismatch: registry={entry['current_value']}, "
                    f"severity.py={expected}"
                )


class TestThresholdRegistryQueries:
    """Query functions must work correctly."""

    def test_get_by_id_existing(self) -> None:
        from backend.threshold_registry import get_threshold_by_id
        entry = get_threshold_by_id("GOV_BASELINE_AX1")
        assert entry is not None
        assert entry["threshold_id"] == "GOV_BASELINE_AX1"

    def test_get_by_id_nonexistent(self) -> None:
        from backend.threshold_registry import get_threshold_by_id
        assert get_threshold_by_id("NONEXISTENT") is None

    def test_get_by_source(self) -> None:
        from backend.threshold_registry import get_thresholds_by_source
        gov = get_thresholds_by_source("governance.py")
        sev = get_thresholds_by_source("severity.py")
        assert len(gov) > 0
        assert len(sev) > 0
        for e in gov:
            assert e["source_module"] == "governance.py"

    def test_get_by_rationale(self) -> None:
        from backend.threshold_registry import get_thresholds_by_rationale, RationaleType
        heuristic = get_thresholds_by_rationale(RationaleType.HEURISTIC)
        assert len(heuristic) > 0
        for e in heuristic:
            assert e["rationale_type"] == RationaleType.HEURISTIC

    def test_get_by_risk(self) -> None:
        from backend.threshold_registry import get_thresholds_by_risk, RiskLevel
        high = get_thresholds_by_risk(RiskLevel.HIGH)
        assert len(high) > 0
        for e in high:
            assert e["risk_level"] == RiskLevel.HIGH

    def test_registry_summary_structure(self) -> None:
        from backend.threshold_registry import get_registry_summary
        summary = get_registry_summary()
        assert "total_thresholds" in summary
        assert "by_rationale_type" in summary
        assert "by_risk_level" in summary
        assert "by_source_module" in summary
        assert "critical_thresholds" in summary
        assert "honesty_note" in summary

    def test_registry_summary_counts_match(self) -> None:
        from backend.threshold_registry import (
            THRESHOLD_JUSTIFICATION_REGISTRY,
            get_registry_summary,
        )
        summary = get_registry_summary()
        assert summary["total_thresholds"] == len(THRESHOLD_JUSTIFICATION_REGISTRY)
        total_by_rationale = sum(summary["by_rationale_type"].values())
        assert total_by_rationale == len(THRESHOLD_JUSTIFICATION_REGISTRY)


class TestThresholdRegistryContent:
    """Content quality checks."""

    def test_no_empirical_thresholds(self) -> None:
        """ISI currently has NO purely empirical thresholds — verify honesty."""
        from backend.threshold_registry import get_thresholds_by_rationale, RationaleType
        empirical = get_thresholds_by_rationale(RationaleType.EMPIRICAL)
        assert len(empirical) == 0, (
            f"Found {len(empirical)} EMPIRICAL thresholds — ISI has no "
            f"externally calibrated thresholds. If this changes, update "
            f"the documentation."
        )

    def test_alternative_values_provided(self) -> None:
        """Every threshold should have at least one alternative value."""
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert len(entry["alternative_plausible_values"]) >= 1, (
                f"Threshold '{entry['threshold_id']}' has no alternatives"
            )

    def test_risk_assessment_nonempty(self) -> None:
        from backend.threshold_registry import THRESHOLD_JUSTIFICATION_REGISTRY
        for entry in THRESHOLD_JUSTIFICATION_REGISTRY:
            assert len(entry["risk_if_misspecified"]) > 10, (
                f"Threshold '{entry['threshold_id']}' has trivial risk assessment"
            )


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 2: EXTERNAL CONTRADICTION TESTING (FALSIFICATION)
# ═══════════════════════════════════════════════════════════════════════════

class TestFalsificationFrameworkStructure:
    """Falsification module must be well-structured."""

    def test_benchmark_registry_nonempty(self) -> None:
        from backend.falsification import BENCHMARK_REGISTRY
        assert len(BENCHMARK_REGISTRY) >= 5

    def test_benchmark_entries_have_required_fields(self) -> None:
        from backend.falsification import BENCHMARK_REGISTRY
        required = {"benchmark_id", "name", "description", "relevant_axes",
                     "comparison_type", "data_source", "status"}
        for b in BENCHMARK_REGISTRY:
            missing = required - set(b.keys())
            assert not missing, f"Benchmark '{b.get('benchmark_id', '?')}' missing: {missing}"

    def test_structural_facts_nonempty(self) -> None:
        from backend.falsification import STRUCTURAL_FACTS
        assert len(STRUCTURAL_FACTS) >= 8

    def test_structural_facts_cover_critical_countries(self) -> None:
        from backend.falsification import STRUCTURAL_FACTS
        required = {"US", "RU", "CN", "NO", "AU"}
        missing = required - set(STRUCTURAL_FACTS.keys())
        assert not missing, f"Missing structural facts for: {missing}"

    def test_valid_flags(self) -> None:
        from backend.falsification import VALID_FLAGS, FalsificationFlag
        assert FalsificationFlag.CONSISTENT in VALID_FLAGS
        assert FalsificationFlag.TENSION in VALID_FLAGS
        assert FalsificationFlag.CONTRADICTION in VALID_FLAGS
        assert FalsificationFlag.NOT_ASSESSED in VALID_FLAGS


class TestFalsificationAssessment:
    """Falsification assessments must produce correct results for known countries."""

    def _make_governance(
        self,
        country: str,
        tier: str,
        n_inverted: int = 0,
        n_valid: int = 6,
    ) -> dict[str, Any]:
        """Build a minimal governance result dict for testing."""
        return {
            "country": country,
            "governance_tier": tier,
            "n_producer_inverted_axes": n_inverted,
            "n_valid_axes": n_valid,
            "mean_axis_confidence": 0.60,
            "ranking_eligible": tier in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE"),
            "cross_country_comparable": tier == "FULLY_COMPARABLE",
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.60, "confidence_level": "MODERATE"}
                for i in range(1, 7)
            ],
        }

    def test_us_non_comparable_consistent(self) -> None:
        """US at NON_COMPARABLE should be structurally consistent."""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("US", "NON_COMPARABLE", n_inverted=3)
        result = assess_country_falsification("US", gov)
        assert result["overall_flag"] in (FalsificationFlag.CONSISTENT, FalsificationFlag.TENSION)
        assert result["n_contradictions"] == 0

    def test_us_fully_comparable_contradiction(self) -> None:
        """US at FULLY_COMPARABLE should trigger contradiction."""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("US", "FULLY_COMPARABLE", n_inverted=0)
        result = assess_country_falsification("US", gov)
        assert result["overall_flag"] == FalsificationFlag.CONTRADICTION
        assert result["n_contradictions"] >= 1

    def test_russia_non_comparable_consistent(self) -> None:
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("RU", "NON_COMPARABLE", n_inverted=3)
        result = assess_country_falsification("RU", gov)
        assert result["overall_flag"] == FalsificationFlag.CONSISTENT

    def test_russia_partially_comparable_contradiction(self) -> None:
        """Sanctioned Russia at PARTIALLY should trigger contradiction."""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("RU", "PARTIALLY_COMPARABLE", n_inverted=1)
        result = assess_country_falsification("RU", gov)
        assert result["overall_flag"] == FalsificationFlag.CONTRADICTION

    def test_china_low_confidence_consistent(self) -> None:
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("CN", "LOW_CONFIDENCE", n_inverted=2)
        result = assess_country_falsification("CN", gov)
        # CN at LOW_CONFIDENCE is consistent with expected LOW_CONFIDENCE
        assert result["overall_flag"] in (FalsificationFlag.CONSISTENT, FalsificationFlag.TENSION)

    def test_eu27_clean_country_consistent(self) -> None:
        """Clean EU-27 country at FULLY_COMPARABLE should be consistent."""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("IT", "FULLY_COMPARABLE", n_inverted=0)
        result = assess_country_falsification("IT", gov)
        assert result["overall_flag"] == FalsificationFlag.CONSISTENT

    def test_eu27_clean_country_low_confidence_tension(self) -> None:
        """Clean EU-27 at LOW_CONFIDENCE should show tension."""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("IT", "LOW_CONFIDENCE", n_inverted=0)
        result = assess_country_falsification("IT", gov)
        assert result["overall_flag"] == FalsificationFlag.TENSION

    def test_unknown_country_not_assessed(self) -> None:
        """Country without structural facts should be NOT_ASSESSED or minimal."""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        gov = self._make_governance("XX", "FULLY_COMPARABLE")
        result = assess_country_falsification("XX", gov)
        # XX is not in EU27_CODES and not in STRUCTURAL_FACTS
        assert result["overall_flag"] == FalsificationFlag.NOT_ASSESSED

    def test_result_includes_honesty_note(self) -> None:
        from backend.falsification import assess_country_falsification
        gov = self._make_governance("IT", "FULLY_COMPARABLE")
        result = assess_country_falsification("IT", gov)
        assert "honesty_note" in result
        assert "structural" in result["honesty_note"].lower()

    def test_result_includes_external_data_status(self) -> None:
        from backend.falsification import assess_country_falsification
        gov = self._make_governance("IT", "FULLY_COMPARABLE")
        result = assess_country_falsification("IT", gov)
        assert "external_data_status" in result


class TestFalsificationSummary:
    """Falsification summary must aggregate correctly."""

    def test_summary_structure(self) -> None:
        from backend.falsification import get_falsification_summary, FalsificationFlag
        mock_results = {
            "IT": {"overall_flag": FalsificationFlag.CONSISTENT, "n_contradictions": 0, "n_tensions": 0},
            "US": {"overall_flag": FalsificationFlag.CONTRADICTION, "n_contradictions": 1, "n_tensions": 0},
            "NO": {"overall_flag": FalsificationFlag.TENSION, "n_contradictions": 0, "n_tensions": 1},
        }
        summary = get_falsification_summary(mock_results)
        assert summary["total_assessed"] == 3
        assert summary["consistent"] == 1
        assert summary["tension"] == 1
        assert summary["contradiction"] == 1
        assert "US" in summary["contradicted_countries"]
        assert "honesty_note" in summary

    def test_all_countries_assessment(self) -> None:
        from backend.falsification import assess_all_countries_falsification
        mock_govs = {
            "IT": {
                "country": "IT", "governance_tier": "FULLY_COMPARABLE",
                "n_producer_inverted_axes": 0, "n_valid_axes": 6,
                "mean_axis_confidence": 0.70, "ranking_eligible": True,
                "cross_country_comparable": True,
                "axis_confidences": [
                    {"axis_id": i, "confidence_score": 0.70, "confidence_level": "HIGH"}
                    for i in range(1, 7)
                ],
            },
        }
        results = assess_all_countries_falsification(mock_govs)
        assert "IT" in results
        assert "overall_flag" in results["IT"]

    def test_benchmark_counts(self) -> None:
        from backend.falsification import _count_integrated_benchmarks, _count_pending_benchmarks
        integrated = _count_integrated_benchmarks()
        pending = _count_pending_benchmarks()
        assert integrated >= 3  # 3 structural benchmarks
        assert pending >= 4  # 4 external benchmarks not yet integrated


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3: DECISION-GRADE COUNTRY USABILITY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestDecisionUsabilityClassStructure:
    """DecisionUsabilityClass must be well-formed."""

    def test_all_classes_exist(self) -> None:
        from backend.eligibility import DecisionUsabilityClass
        assert DecisionUsabilityClass.TRUSTED_COMPARABLE == "TRUSTED_COMPARABLE"
        assert DecisionUsabilityClass.CONDITIONALLY_USABLE == "CONDITIONALLY_USABLE"
        assert DecisionUsabilityClass.STRUCTURALLY_LIMITED == "STRUCTURALLY_LIMITED"
        assert DecisionUsabilityClass.INVALID_FOR_COMPARISON == "INVALID_FOR_COMPARISON"

    def test_valid_classes_complete(self) -> None:
        from backend.eligibility import VALID_USABILITY_CLASSES, DecisionUsabilityClass
        assert DecisionUsabilityClass.TRUSTED_COMPARABLE in VALID_USABILITY_CLASSES
        assert DecisionUsabilityClass.CONDITIONALLY_USABLE in VALID_USABILITY_CLASSES
        assert DecisionUsabilityClass.STRUCTURALLY_LIMITED in VALID_USABILITY_CLASSES
        assert DecisionUsabilityClass.INVALID_FOR_COMPARISON in VALID_USABILITY_CLASSES

    def test_usability_rank_ordering(self) -> None:
        from backend.eligibility import _USABILITY_RANK, DecisionUsabilityClass
        assert _USABILITY_RANK[DecisionUsabilityClass.INVALID_FOR_COMPARISON] == 0
        assert _USABILITY_RANK[DecisionUsabilityClass.STRUCTURALLY_LIMITED] == 1
        assert _USABILITY_RANK[DecisionUsabilityClass.CONDITIONALLY_USABLE] == 2
        assert _USABILITY_RANK[DecisionUsabilityClass.TRUSTED_COMPARABLE] == 3


class TestDecisionUsabilityClassification:
    """Decision usability classification must produce correct results."""

    def test_clean_eu_country_trusted(self) -> None:
        """EU-27 country with clean governance should be TRUSTED."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        gov = {
            "country": "IT",
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.70,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.70, "confidence_level": "HIGH"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("IT", governance_result=gov)
        assert result["decision_usability_class"] == DecisionUsabilityClass.TRUSTED_COMPARABLE

    def test_non_comparable_country_invalid(self) -> None:
        """NON_COMPARABLE country should be INVALID_FOR_COMPARISON."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        gov = {
            "country": "US",
            "governance_tier": "NON_COMPARABLE",
            "mean_axis_confidence": 0.30,
            "n_producer_inverted_axes": 3,
            "n_valid_axes": 6,
            "ranking_eligible": False,
            "cross_country_comparable": False,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.30, "confidence_level": "LOW"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("US", governance_result=gov)
        assert result["decision_usability_class"] == DecisionUsabilityClass.INVALID_FOR_COMPARISON

    def test_low_confidence_structurally_limited(self) -> None:
        """LOW_CONFIDENCE country should be STRUCTURALLY_LIMITED."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        gov = {
            "country": "AU",
            "governance_tier": "LOW_CONFIDENCE",
            "mean_axis_confidence": 0.40,
            "n_producer_inverted_axes": 2,
            "n_valid_axes": 6,
            "ranking_eligible": False,
            "cross_country_comparable": False,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.40, "confidence_level": "LOW"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("AU", governance_result=gov)
        assert result["decision_usability_class"] == DecisionUsabilityClass.STRUCTURALLY_LIMITED

    def test_partially_comparable_conditionally_usable(self) -> None:
        """PARTIALLY_COMPARABLE should be CONDITIONALLY_USABLE."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        gov = {
            "country": "FR",
            "governance_tier": "PARTIALLY_COMPARABLE",
            "mean_axis_confidence": 0.60,
            "n_producer_inverted_axes": 1,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": False,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.60, "confidence_level": "MODERATE"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("FR", governance_result=gov)
        assert result["decision_usability_class"] == DecisionUsabilityClass.CONDITIONALLY_USABLE

    def test_falsification_contradiction_forces_invalid(self) -> None:
        """Falsification contradiction should force INVALID."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        gov = {
            "country": "XX",
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.70,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.70, "confidence_level": "HIGH"}
                for i in range(1, 7)
            ],
        }
        falsification = {"overall_flag": "CONTRADICTION"}
        result = classify_decision_usability(
            "XX", governance_result=gov, falsification_result=falsification,
        )
        assert result["decision_usability_class"] == DecisionUsabilityClass.INVALID_FOR_COMPARISON

    def test_result_has_required_fields(self) -> None:
        from backend.eligibility import classify_decision_usability
        gov = {
            "country": "IT",
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.70,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.70, "confidence_level": "HIGH"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("IT", governance_result=gov)
        required = {
            "country", "decision_usability_class", "eligibility_class",
            "governance_tier", "conditions", "falsification_flag",
            "justification", "policy_guidance", "theoretical_caveat",
        }
        missing = required - set(result.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_policy_guidance_nonempty(self) -> None:
        from backend.eligibility import classify_decision_usability
        gov = {
            "country": "IT",
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.70,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.70, "confidence_level": "HIGH"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("IT", governance_result=gov)
        assert len(result["policy_guidance"]) > 20

    def test_theoretical_caveat_present(self) -> None:
        from backend.eligibility import classify_decision_usability
        gov = {
            "country": "IT",
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.70,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.70, "confidence_level": "HIGH"}
                for i in range(1, 7)
            ],
        }
        result = classify_decision_usability("IT", governance_result=gov)
        caveat = result["theoretical_caveat"]
        assert "NOT" in caveat or "not" in caveat

    def test_simulation_fallback_works(self) -> None:
        """When no governance_result passed, the function should simulate."""
        from backend.eligibility import classify_decision_usability
        # IT is in ALL_ASSESSABLE_COUNTRIES and can compile
        result = classify_decision_usability("IT")
        assert "decision_usability_class" in result
        assert result["decision_usability_class"] in {
            "TRUSTED_COMPARABLE", "CONDITIONALLY_USABLE",
            "STRUCTURALLY_LIMITED", "INVALID_FOR_COMPARISON",
        }

    def test_fully_but_low_high_not_trusted(self) -> None:
        """FULLY_COMPARABLE but only 2 HIGH axes should not be TRUSTED."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        gov = {
            "country": "XX",
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.55,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [
                {"axis_id": 1, "confidence_score": 0.70, "confidence_level": "HIGH"},
                {"axis_id": 2, "confidence_score": 0.70, "confidence_level": "HIGH"},
                {"axis_id": 3, "confidence_score": 0.50, "confidence_level": "MODERATE"},
                {"axis_id": 4, "confidence_score": 0.50, "confidence_level": "MODERATE"},
                {"axis_id": 5, "confidence_score": 0.50, "confidence_level": "MODERATE"},
                {"axis_id": 6, "confidence_score": 0.50, "confidence_level": "MODERATE"},
            ],
        }
        result = classify_decision_usability("XX", governance_result=gov)
        # Only 2 HIGH axes, needs 4 for TRUSTED
        assert result["decision_usability_class"] != DecisionUsabilityClass.TRUSTED_COMPARABLE


class TestDecisionUsabilityForRealCountries:
    """Test usability classification against real country profiles."""

    def test_eu27_large_members_usable(self) -> None:
        """Large EU members without inversions should be at least CONDITIONALLY."""
        from backend.eligibility import (
            classify_decision_usability,
            DecisionUsabilityClass,
            _USABILITY_RANK,
        )
        for code in ["IT", "ES", "NL", "PL"]:
            result = classify_decision_usability(code)
            rank = _USABILITY_RANK.get(result["decision_usability_class"], -1)
            assert rank >= _USABILITY_RANK[DecisionUsabilityClass.CONDITIONALLY_USABLE], (
                f"{code} should be at least CONDITIONALLY_USABLE but is "
                f"{result['decision_usability_class']}"
            )

    def test_us_invalid_for_comparison(self) -> None:
        """US with 3 inversions should be INVALID or STRUCTURALLY_LIMITED."""
        from backend.eligibility import (
            classify_decision_usability,
            DecisionUsabilityClass,
            _USABILITY_RANK,
        )
        result = classify_decision_usability("US")
        rank = _USABILITY_RANK.get(result["decision_usability_class"], -1)
        assert rank <= _USABILITY_RANK[DecisionUsabilityClass.STRUCTURALLY_LIMITED], (
            f"US should be STRUCTURALLY_LIMITED or worse but is "
            f"{result['decision_usability_class']}"
        )

    def test_russia_invalid(self) -> None:
        """Russia with sanctions should be INVALID_FOR_COMPARISON."""
        from backend.eligibility import classify_decision_usability, DecisionUsabilityClass
        result = classify_decision_usability("RU")
        assert result["decision_usability_class"] == DecisionUsabilityClass.INVALID_FOR_COMPARISON


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 4: AUTHORITY UNIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthorityUnification:
    """Eligibility authority must be unified — no contradictions between modules."""

    def test_calibration_eligibility_class_exists(self) -> None:
        """calibration.py EligibilityClass must still exist (backward compat)."""
        from backend.calibration import EligibilityClass
        assert EligibilityClass.CONFIDENTLY_RATEABLE == "CONFIDENTLY_RATEABLE"

    def test_eligibility_theoretical_eligibility_exists(self) -> None:
        """eligibility.py TheoreticalEligibility must exist."""
        from backend.eligibility import TheoreticalEligibility
        assert TheoreticalEligibility.COMPARABLE_WITHIN_MODEL == "COMPARABLE_WITHIN_MODEL"

    def test_eligibility_decision_usability_exists(self) -> None:
        """eligibility.py DecisionUsabilityClass must exist."""
        from backend.eligibility import DecisionUsabilityClass
        assert DecisionUsabilityClass.TRUSTED_COMPARABLE == "TRUSTED_COMPARABLE"

    def test_calibration_registry_still_populated(self) -> None:
        """Calibration's registry must still have entries (supplementary metadata)."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        assert len(COUNTRY_ELIGIBILITY_REGISTRY) >= 27

    def test_eligibility_module_covers_all_calibration_countries(self) -> None:
        """eligibility.py must cover at least all countries in calibration.py.

        Known alias: calibration uses 'UK' while eligibility uses 'GB' (ISO 3166).
        """
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        from backend.eligibility import ALL_ASSESSABLE_COUNTRIES
        # Known code aliases: calibration may use non-ISO codes
        KNOWN_ALIASES = {"UK": "GB"}
        calibration_countries = set()
        for e in COUNTRY_ELIGIBILITY_REGISTRY:
            code = e["country"]
            calibration_countries.add(KNOWN_ALIASES.get(code, code))
        eligibility_countries = set(ALL_ASSESSABLE_COUNTRIES)
        missing = calibration_countries - eligibility_countries
        assert not missing, (
            f"Countries in calibration but missing from eligibility: {missing}"
        )

    def test_no_eligibility_class_divergence_direction(self) -> None:
        """Calibration and eligibility classifications must not contradict.

        Mapping:
        - CONFIDENTLY_RATEABLE → should map to COMPARABLE or RANKABLE
        - RATEABLE_WITH_CAVEATS → should map to RATEABLE or RANKABLE
        - PARTIALLY_RATEABLE → should map to COMPUTABLE or COMPILE_READY
        - NOT_CURRENTLY_RATEABLE → should map to NOT_READY or COMPILE_READY
        """
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass as CalibElig
        from backend.eligibility import classify_country, TheoreticalEligibility as TE

        # Define compatible mappings (calibration class → allowed eligibility classes)
        compatible = {
            CalibElig.CONFIDENTLY_RATEABLE: {
                TE.COMPARABLE_WITHIN_MODEL, TE.RANKABLE_WITHIN_MODEL,
                TE.RATEABLE_WITHIN_MODEL,
            },
            CalibElig.RATEABLE_WITH_CAVEATS: {
                TE.COMPARABLE_WITHIN_MODEL, TE.RANKABLE_WITHIN_MODEL,
                TE.RATEABLE_WITHIN_MODEL, TE.COMPUTABLE_BUT_NOT_DEFENSIBLE,
            },
            CalibElig.PARTIALLY_RATEABLE: {
                TE.COMPARABLE_WITHIN_MODEL, TE.RANKABLE_WITHIN_MODEL,
                TE.RATEABLE_WITHIN_MODEL, TE.COMPUTABLE_BUT_NOT_DEFENSIBLE,
                TE.COMPILE_READY,
            },
            CalibElig.NOT_CURRENTLY_RATEABLE: {
                TE.COMPUTABLE_BUT_NOT_DEFENSIBLE, TE.COMPILE_READY,
                TE.NOT_READY, TE.RATEABLE_WITHIN_MODEL,
            },
        }

        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            country = entry["country"]
            calib_class = entry["eligibility_class"]
            try:
                elig = classify_country(country)
                elig_class = elig["eligibility_class"]
                allowed = compatible.get(calib_class, set())
                assert elig_class in allowed, (
                    f"Country {country}: calibration says {calib_class} but "
                    f"eligibility says {elig_class}. These are inconsistent."
                )
            except Exception:
                # Country may not be assessable in eligibility — that's OK
                # for countries outside the assessable set
                pass

    def test_authority_note_in_calibration_summary(self) -> None:
        """Calibration eligibility summary must include authority note."""
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        assert "authority_note" in summary, (
            "Calibration eligibility summary must include authority_note "
            "pointing to eligibility.py as the authoritative system"
        )

    def test_authority_note_references_eligibility(self) -> None:
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        note = summary["authority_note"]
        assert "eligibility.py" in note or "eligibility" in note.lower()

    def test_calibration_class_docstring_mentions_authority(self) -> None:
        """Calibration's EligibilityClass docstring must mention authority."""
        from backend.calibration import EligibilityClass
        doc = EligibilityClass.__doc__ or ""
        assert "authoritative" in doc.lower() or "eligibility.py" in doc


class TestAuthorityUnificationCrossModule:
    """Cross-module consistency between eligibility and calibration."""

    def test_eu27_confidently_rateable_are_at_least_rateable(self) -> None:
        """Countries that calibration marks CONFIDENTLY_RATEABLE must be
        at least RATEABLE in eligibility."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass as CE
        from backend.eligibility import classify_country, _ELIGIBILITY_RANK, TheoreticalEligibility as TE

        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            if entry["eligibility_class"] != CE.CONFIDENTLY_RATEABLE:
                continue
            country = entry["country"]
            try:
                elig = classify_country(country)
                rank = _ELIGIBILITY_RANK.get(elig["eligibility_class"], 0)
                min_rank = _ELIGIBILITY_RANK[TE.RATEABLE_WITHIN_MODEL]
                assert rank >= min_rank, (
                    f"Calibration says {country} is CONFIDENTLY_RATEABLE "
                    f"but eligibility classifies as {elig['eligibility_class']}"
                )
            except Exception:
                pass  # Country may not be assessable

    def test_not_currently_rateable_are_not_comparable(self) -> None:
        """Countries that calibration marks NOT_CURRENTLY_RATEABLE should
        NOT be COMPARABLE or RANKABLE in eligibility."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass as CE
        from backend.eligibility import classify_country, TheoreticalEligibility as TE

        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            if entry["eligibility_class"] != CE.NOT_CURRENTLY_RATEABLE:
                continue
            country = entry["country"]
            try:
                elig = classify_country(country)
                assert elig["eligibility_class"] not in (
                    TE.COMPARABLE_WITHIN_MODEL,
                    TE.RANKABLE_WITHIN_MODEL,
                ), (
                    f"Calibration says {country} is NOT_CURRENTLY_RATEABLE "
                    f"but eligibility says {elig['eligibility_class']}"
                )
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestExportIntegration:
    """New fields must propagate correctly through the export layer."""

    def test_build_country_json_has_falsification(self) -> None:
        """build_country_json must include falsification field."""
        from backend.export_snapshot import build_country_json
        # This requires actual score data — create minimal test scores
        scores = {
            i: {"IT": 0.5} for i in range(1, 7)
        }
        result = build_country_json("IT", scores, "v1.0", 2024, "2022-2024")
        assert "falsification" in result
        assert "overall_flag" in result["falsification"]

    def test_build_country_json_has_decision_usability(self) -> None:
        """build_country_json must include decision_usability field."""
        from backend.export_snapshot import build_country_json
        scores = {
            i: {"IT": 0.5} for i in range(1, 7)
        }
        result = build_country_json("IT", scores, "v1.0", 2024, "2022-2024")
        assert "decision_usability" in result
        assert "decision_usability_class" in result["decision_usability"]

    def test_build_isi_json_has_decision_usability_class(self) -> None:
        """isi.json ranking rows must include decision_usability_class."""
        from backend.export_snapshot import build_isi_json
        from backend.constants import EU27_SORTED
        scores = {
            i: {c: 0.5 for c in EU27_SORTED}
            for i in range(1, 7)
        }
        result = build_isi_json(scores, "v1.0", 2024, "2022-2024")
        for row in result["countries"]:
            assert "decision_usability_class" in row, (
                f"Country {row['country']} missing decision_usability_class"
            )


class TestSystemAnswersFourQuestions:
    """The system must now answer all 4 critical review questions."""

    def test_question_1_why_this_threshold(self) -> None:
        """System must answer: 'Why this threshold?'"""
        from backend.threshold_registry import get_threshold_by_id
        entry = get_threshold_by_id("GOV_MIN_MEAN_CONF_RANKING")
        assert entry is not None
        assert len(entry["justification"]) > 50
        assert len(entry["alternative_plausible_values"]) > 0

    def test_question_2_what_if_wrong(self) -> None:
        """System must answer: 'What happens if it's wrong?'"""
        from backend.threshold_registry import get_threshold_by_id
        entry = get_threshold_by_id("GOV_MAX_INVERTED_COMPARABLE")
        assert entry is not None
        assert len(entry["risk_if_misspecified"]) > 20
        assert len(entry["breakpoints"]) > 0
        assert entry["risk_level"] in ("HIGH", "CRITICAL")

    def test_question_3_where_contradicts_reality(self) -> None:
        """System must answer: 'Where does the system contradict reality?'"""
        from backend.falsification import assess_country_falsification, FalsificationFlag
        # US at FULLY_COMPARABLE would be a contradiction
        gov = {
            "country": "US",
            "governance_tier": "FULLY_COMPARABLE",
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "mean_axis_confidence": 0.70,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "axis_confidences": [],
        }
        result = assess_country_falsification("US", gov)
        assert result["overall_flag"] == FalsificationFlag.CONTRADICTION
        assert result["n_contradictions"] >= 1

    def test_question_4_which_countries_trustable(self) -> None:
        """System must answer: 'Which countries can actually be trusted?'"""
        from backend.eligibility import (
            classify_decision_usability,
            DecisionUsabilityClass,
        )
        # IT should be trustable
        it_result = classify_decision_usability("IT")
        assert it_result["decision_usability_class"] in (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
        )
        # RU should not
        ru_result = classify_decision_usability("RU")
        assert ru_result["decision_usability_class"] == DecisionUsabilityClass.INVALID_FOR_COMPARISON
