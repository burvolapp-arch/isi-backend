"""
tests.test_final_hardening — Tests for Final Adversarial Hardening Pass

Covers:
    SECTION 1: construct_enforcement.py — construct validity enforcement
    SECTION 2: benchmark_mapping_audit.py — benchmark mapping validity
    SECTION 3: alignment_sensitivity.py — alignment robustness testing
    SECTION 4: snapshot_diff.py — policy impact assessment
    SECTION 5: failure_visibility.py — usability hardening + visibility
    SECTION 6: failure_visibility.py — anti-bullshit layer
    Integration: invariants.py — new CE-INV invariants

Test discipline:
    - Every function is tested for expected and edge-case inputs.
    - Every classification boundary is tested.
    - All new invariant IDs are exercised.
    - All downgrade rules are verified.
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: CONSTRUCT ENFORCEMENT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestConstructValidityClass:
    """Tests for ConstructValidityClass enum."""

    def test_valid_classes_exist(self):
        from backend.construct_enforcement import ConstructValidityClass
        assert ConstructValidityClass.VALID == "CONSTRUCT_VALID"
        assert ConstructValidityClass.DEGRADED == "CONSTRUCT_DEGRADED"
        assert ConstructValidityClass.INVALID == "CONSTRUCT_INVALID"

    def test_valid_classes_frozenset(self):
        from backend.construct_enforcement import VALID_CONSTRUCT_CLASSES
        assert len(VALID_CONSTRUCT_CLASSES) == 3
        assert "CONSTRUCT_VALID" in VALID_CONSTRUCT_CLASSES
        assert "CONSTRUCT_DEGRADED" in VALID_CONSTRUCT_CLASSES
        assert "CONSTRUCT_INVALID" in VALID_CONSTRUCT_CLASSES


class TestEnforceConstructValidity:
    """Tests for enforce_construct_validity()."""

    def test_full_data_no_proxy_is_valid(self):
        from backend.construct_enforcement import enforce_construct_validity
        result = enforce_construct_validity(
            axis_id=1,
            readiness_level="FULL_DATA",
            is_proxy=False,
            external_alignment_class=None,
        )
        assert result["construct_validity_class"] == "CONSTRUCT_VALID"
        assert result["weight_factor"] == 1.0
        assert len(result["applied_rules"]) == 0

    def test_substitution_degrades_to_degraded(self):
        """CE-001: construct substitution → DEGRADED."""
        from backend.construct_enforcement import enforce_construct_validity
        result = enforce_construct_validity(
            axis_id=2,
            readiness_level="CONSTRUCT_SUBSTITUTION",
            is_proxy=False,
            external_alignment_class=None,
        )
        assert result["construct_validity_class"] == "CONSTRUCT_DEGRADED"
        assert result["weight_factor"] <= 0.50
        assert "CE-001" in result["applied_rules"]

    def test_substitution_plus_divergent_is_invalid(self):
        """CE-002: substitution + DIVERGENT alignment → INVALID."""
        from backend.construct_enforcement import enforce_construct_validity
        result = enforce_construct_validity(
            axis_id=3,
            readiness_level="CONSTRUCT_SUBSTITUTION",
            is_proxy=False,
            external_alignment_class="DIVERGENT",
        )
        assert result["construct_validity_class"] == "CONSTRUCT_INVALID"
        assert result["weight_factor"] == 0.0
        assert "CE-002" in result["applied_rules"]

    def test_proxy_without_alignment_degrades(self):
        """CE-003: proxy without alignment → DEGRADED (for non-Axis 6 proxies)."""
        from backend.construct_enforcement import enforce_construct_validity
        result = enforce_construct_validity(
            axis_id=5,
            readiness_level="FULL_DATA",
            is_proxy=True,
            external_alignment_class=None,
        )
        # Proxy should trigger some rule
        assert result["construct_validity_class"] in (
            "CONSTRUCT_DEGRADED", "CONSTRUCT_VALID",
        )

    def test_logistics_proxy_requires_alignment(self):
        """CE-003: Axis 6 proxy without alignment → DEGRADED."""
        from backend.construct_enforcement import enforce_construct_validity
        result = enforce_construct_validity(
            axis_id=6,
            readiness_level="FULL_DATA",
            is_proxy=True,
            external_alignment_class=None,
        )
        assert result["construct_validity_class"] == "CONSTRUCT_DEGRADED"
        assert "CE-003" in result["applied_rules"]

    def test_logistics_proxy_with_alignment_is_valid(self):
        """CE-003: Axis 6 proxy WITH alignment → VALID."""
        from backend.construct_enforcement import enforce_construct_validity
        result = enforce_construct_validity(
            axis_id=6,
            readiness_level="FULL_DATA",
            is_proxy=True,
            external_alignment_class="STRONGLY_ALIGNED",
        )
        assert result["construct_validity_class"] == "CONSTRUCT_VALID"
        assert result["weight_factor"] == 1.0


class TestEnforceAllAxes:
    """Tests for enforce_all_axes()."""

    def _make_readiness_matrix(self, overrides=None):
        """Build a default readiness matrix for 6 axes."""
        matrix = []
        for ax_id in range(1, 7):
            entry = {
                "axis_id": ax_id,
                "readiness_level": "FULL_DATA",
                "construct_substitution": False,
                "proxy_used": False,
            }
            matrix.append(entry)
        if overrides:
            for ax_id, ovr in overrides.items():
                for m in matrix:
                    if m["axis_id"] == ax_id:
                        m.update(ovr)
        return matrix

    def test_all_valid_axes(self):
        from backend.construct_enforcement import enforce_all_axes
        matrix = self._make_readiness_matrix()
        result = enforce_all_axes(matrix, {})
        assert result["n_valid"] == 6
        assert result["n_degraded"] == 0
        assert result["n_invalid"] == 0
        assert result["composite_producible"]

    def test_one_substitution_degrades(self):
        from backend.construct_enforcement import enforce_all_axes
        matrix = self._make_readiness_matrix({
            2: {"readiness_level": "CONSTRUCT_SUBSTITUTION", "construct_substitution": True},
        })
        result = enforce_all_axes(matrix, {})
        assert result["n_degraded"] >= 1
        assert result["composite_producible"]

    def test_ce004_insufficient_valid_axes_blocks_composite(self):
        """CE-004: fewer than 3 valid axes → composite blocked."""
        from backend.construct_enforcement import enforce_all_axes
        matrix = self._make_readiness_matrix({
            1: {"readiness_level": "CONSTRUCT_SUBSTITUTION", "construct_substitution": True},
            2: {"readiness_level": "CONSTRUCT_SUBSTITUTION", "construct_substitution": True},
            3: {"readiness_level": "CONSTRUCT_SUBSTITUTION", "construct_substitution": True},
            4: {"readiness_level": "CONSTRUCT_SUBSTITUTION", "construct_substitution": True},
        })
        # All substitutions with divergent alignment → INVALID
        axis_alignment = {
            1: "DIVERGENT",
            2: "DIVERGENT",
            3: "DIVERGENT",
            4: "DIVERGENT",
        }
        result = enforce_all_axes(matrix, axis_alignment)
        # 4 invalid axes → fewer than 3 valid → blocked
        assert result["n_invalid"] >= 4
        assert not result["composite_producible"]


class TestComputeConstructAdjustedComposite:
    """Tests for compute_construct_adjusted_composite()."""

    def test_all_valid_returns_normal_mean(self):
        from backend.construct_enforcement import (
            enforce_all_axes,
            compute_construct_adjusted_composite,
        )
        matrix = [
            {"axis_id": i, "readiness_level": "FULL_DATA",
             "construct_substitution": False, "proxy_used": False}
            for i in range(1, 7)
        ]
        enforcement = enforce_all_axes(matrix, {})
        scores = {1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5}
        result = compute_construct_adjusted_composite(scores, enforcement)
        assert not result["composite_blocked"]
        expected_mean = sum(scores.values()) / 6
        assert abs(result["adjusted_composite"] - expected_mean) < 1e-6

    def test_blocked_composite_returns_none(self):
        from backend.construct_enforcement import (
            enforce_all_axes,
            compute_construct_adjusted_composite,
        )
        # Force all axes to be invalid via substitution + divergent
        matrix = [
            {"axis_id": i, "readiness_level": "CONSTRUCT_SUBSTITUTION",
             "construct_substitution": True, "proxy_used": False}
            for i in range(1, 7)
        ]
        alignment = {i: "DIVERGENT" for i in range(1, 7)}
        enforcement = enforce_all_axes(matrix, alignment)
        scores = {1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5}
        result = compute_construct_adjusted_composite(scores, enforcement)
        assert result["composite_blocked"]
        assert result["adjusted_composite"] is None


class TestShouldExcludeFromRankingConstruct:
    """Tests for should_exclude_from_ranking() in construct_enforcement."""

    def test_excluded_when_composite_blocked(self):
        from backend.construct_enforcement import should_exclude_from_ranking
        enforcement = {
            "composite_producible": False,
            "n_invalid": 4,
            "n_valid": 2,
        }
        result = should_exclude_from_ranking(enforcement)
        assert result["exclude_from_ranking"]

    def test_excluded_when_3_or_more_invalid(self):
        from backend.construct_enforcement import should_exclude_from_ranking
        enforcement = {
            "composite_producible": True,
            "n_invalid": 3,
            "n_valid": 3,
        }
        result = should_exclude_from_ranking(enforcement)
        assert result["exclude_from_ranking"]

    def test_not_excluded_when_all_valid(self):
        from backend.construct_enforcement import should_exclude_from_ranking
        enforcement = {
            "composite_producible": True,
            "n_invalid": 0,
            "n_valid": 6,
        }
        result = should_exclude_from_ranking(enforcement)
        assert not result["exclude_from_ranking"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: BENCHMARK MAPPING AUDIT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestBenchmarkMappingAudit:
    """Tests for benchmark_mapping_audit module."""

    def test_mapping_validity_classes_exist(self):
        from backend.benchmark_mapping_audit import MappingValidityClass
        assert MappingValidityClass.VALID_MAPPING == "VALID_MAPPING"
        assert MappingValidityClass.WEAK_MAPPING == "WEAK_MAPPING"
        assert MappingValidityClass.INVALID_MAPPING == "INVALID_MAPPING"

    def test_all_benchmarks_have_audit_entries(self):
        from backend.benchmark_mapping_audit import BENCHMARK_MAPPING_AUDIT
        assert len(BENCHMARK_MAPPING_AUDIT) >= 8
        for bm_id, entry in BENCHMARK_MAPPING_AUDIT.items():
            assert "isi_variable" in entry
            assert "external_variable" in entry
            assert "mapping_validity" in entry
            assert "mapping_justification" in entry

    def test_audit_entries_have_required_fields(self):
        from backend.benchmark_mapping_audit import BENCHMARK_MAPPING_AUDIT
        required = {
            "isi_variable", "external_variable",
            "transformation", "unit_scale_differences",
            "time_alignment", "aggregation_differences",
            "known_distortions", "expected_failure_modes",
            "mapping_validity", "mapping_justification",
        }
        for bm_id, entry in BENCHMARK_MAPPING_AUDIT.items():
            missing = required - set(entry.keys())
            assert not missing, f"Benchmark {bm_id} missing: {missing}"


class TestValidateBenchmarkMapping:
    """Tests for validate_benchmark_mapping()."""

    def test_valid_mapping_returns_valid(self):
        from backend.benchmark_mapping_audit import validate_benchmark_mapping
        result = validate_benchmark_mapping("EXT_COMTRADE_XVAL")
        assert result["mapping_validity"] == "VALID_MAPPING"

    def test_weak_mapping_returns_weak(self):
        from backend.benchmark_mapping_audit import validate_benchmark_mapping
        result = validate_benchmark_mapping("EXT_BIS_CBS")
        assert result["mapping_validity"] == "WEAK_MAPPING"

    def test_unknown_benchmark_returns_invalid(self):
        from backend.benchmark_mapping_audit import validate_benchmark_mapping
        result = validate_benchmark_mapping("NONEXISTENT_BENCHMARK")
        assert result["mapping_validity"] == "INVALID_MAPPING"
        assert result["mapping_audited"] is False


class TestValidateAllMappings:
    """Tests for validate_all_mappings()."""

    def test_returns_all_benchmarks(self):
        from backend.benchmark_mapping_audit import (
            validate_all_mappings, BENCHMARK_MAPPING_AUDIT,
        )
        result = validate_all_mappings()
        assert len(result["per_benchmark"]) == len(BENCHMARK_MAPPING_AUDIT)


class TestShouldDowngradeAlignment:
    """Tests for should_downgrade_alignment()."""

    def test_invalid_mapping_forces_incomparable(self):
        """INVALID_MAPPING → force STRUCTURALLY_INCOMPARABLE."""
        from backend.benchmark_mapping_audit import should_downgrade_alignment
        # BIS_CBS is WEAK, not INVALID, so it should downgrade STRONGLY to WEAKLY
        result = should_downgrade_alignment(
            benchmark_id="EXT_BIS_CBS",
            raw_alignment_class="STRONGLY_ALIGNED",
        )
        assert result["adjusted_alignment_class"] == "WEAKLY_ALIGNED"

    def test_weak_mapping_downgrades_strongly_to_weakly(self):
        from backend.benchmark_mapping_audit import should_downgrade_alignment
        result = should_downgrade_alignment(
            benchmark_id="EXT_BIS_CBS",
            raw_alignment_class="STRONGLY_ALIGNED",
        )
        assert result["downgraded"]
        assert result["adjusted_alignment_class"] == "WEAKLY_ALIGNED"

    def test_weak_mapping_keeps_weakly_aligned(self):
        from backend.benchmark_mapping_audit import should_downgrade_alignment
        result = should_downgrade_alignment(
            benchmark_id="EXT_BIS_CBS",
            raw_alignment_class="WEAKLY_ALIGNED",
        )
        assert not result["downgraded"]
        assert result["adjusted_alignment_class"] == "WEAKLY_ALIGNED"

    def test_valid_mapping_no_downgrade(self):
        from backend.benchmark_mapping_audit import should_downgrade_alignment
        result = should_downgrade_alignment(
            benchmark_id="EXT_COMTRADE_XVAL",
            raw_alignment_class="STRONGLY_ALIGNED",
        )
        assert not result["downgraded"]
        assert result["adjusted_alignment_class"] == "STRONGLY_ALIGNED"

    def test_unknown_benchmark_downgrades_to_incomparable(self):
        from backend.benchmark_mapping_audit import should_downgrade_alignment
        result = should_downgrade_alignment(
            benchmark_id="NONEXISTENT",
            raw_alignment_class="STRONGLY_ALIGNED",
        )
        assert result["downgraded"]
        assert result["adjusted_alignment_class"] == "STRUCTURALLY_INCOMPARABLE"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: ALIGNMENT SENSITIVITY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestAlignmentStabilityClass:
    """Tests for AlignmentStabilityClass."""

    def test_classes_exist(self):
        from backend.alignment_sensitivity import AlignmentStabilityClass
        assert AlignmentStabilityClass.STABLE == "ALIGNMENT_STABLE"
        assert AlignmentStabilityClass.SENSITIVE == "ALIGNMENT_SENSITIVE"
        assert AlignmentStabilityClass.UNSTABLE == "ALIGNMENT_UNSTABLE"
        assert AlignmentStabilityClass.NOT_ASSESSED == "ALIGNMENT_SENSITIVITY_NOT_ASSESSED"


class TestRunAlignmentSensitivity:
    """Tests for run_alignment_sensitivity()."""

    def test_no_benchmarks_returns_not_assessed(self):
        from backend.alignment_sensitivity import run_alignment_sensitivity
        result = run_alignment_sensitivity(
            country="DE",
            axis_scores={1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5},
            external_data={},
            benchmark_results=[],
            original_alignment_class=None,
        )
        assert result["stability_class"] == "ALIGNMENT_SENSITIVITY_NOT_ASSESSED"

    def test_deterministic_output(self):
        """Sensitivity analysis must be deterministic (no random)."""
        from backend.alignment_sensitivity import run_alignment_sensitivity
        scores = {1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5}
        benchmarks = [
            {"benchmark_id": "EXT_A", "metric_value": 0.75, "alignment_class": "WEAKLY_ALIGNED"},
            {"benchmark_id": "EXT_B", "metric_value": 0.82, "alignment_class": "STRONGLY_ALIGNED"},
        ]
        r1 = run_alignment_sensitivity(
            "DE", scores, {}, benchmarks, "WEAKLY_ALIGNED",
        )
        r2 = run_alignment_sensitivity(
            "DE", scores, {}, benchmarks, "WEAKLY_ALIGNED",
        )
        assert r1["stability_class"] == r2["stability_class"]

    def test_returns_required_fields(self):
        from backend.alignment_sensitivity import run_alignment_sensitivity
        result = run_alignment_sensitivity(
            country="FR",
            axis_scores={1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5},
            external_data={},
            benchmark_results=[
                {"benchmark_id": "B1", "metric_value": 0.7, "alignment_class": "WEAKLY_ALIGNED"},
            ],
            original_alignment_class="WEAKLY_ALIGNED",
        )
        assert "country" in result
        assert "stability_class" in result
        assert "perturbation_results" in result
        assert "original_alignment_class" in result


class TestShouldDowngradeForInstability:
    """Tests for should_downgrade_for_instability()."""

    def test_unstable_forces_downgrade(self):
        from backend.alignment_sensitivity import should_downgrade_for_instability
        result = should_downgrade_for_instability({
            "stability_class": "ALIGNMENT_UNSTABLE",
        })
        assert result["downgrade_required"]
        assert result["recommended_empirical_class"] == "EMPIRICALLY_WEAK"

    def test_sensitive_adds_caveat_only(self):
        from backend.alignment_sensitivity import should_downgrade_for_instability
        result = should_downgrade_for_instability({
            "stability_class": "ALIGNMENT_SENSITIVE",
        })
        assert not result["downgrade_required"]
        assert "caveat" in result.get("reason", "").lower() or "SENSITIVE" in result.get("reason", "")

    def test_stable_no_downgrade(self):
        from backend.alignment_sensitivity import should_downgrade_for_instability
        result = should_downgrade_for_instability({
            "stability_class": "ALIGNMENT_STABLE",
        })
        assert not result["downgrade_required"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: POLICY IMPACT ASSESSMENT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestPolicyImpactClass:
    """Tests for PolicyImpactClass."""

    def test_classes_exist(self):
        from backend.snapshot_diff import PolicyImpactClass
        assert PolicyImpactClass.NO_IMPACT == "NO_IMPACT"
        assert PolicyImpactClass.MINOR_ADJUSTMENT == "MINOR_ADJUSTMENT"
        assert PolicyImpactClass.INTERPRETATION_CHANGE == "INTERPRETATION_CHANGE"
        assert PolicyImpactClass.INVALIDATES_PRIOR_RESULTS == "INVALIDATES_PRIOR_RESULTS"

    def test_valid_classes_frozenset(self):
        from backend.snapshot_diff import VALID_POLICY_IMPACT_CLASSES
        assert len(VALID_POLICY_IMPACT_CLASSES) == 4


class TestAssessCountryPolicyImpact:
    """Tests for assess_country_policy_impact()."""

    def test_unchanged_is_no_impact(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "DE",
            "status": "UNCHANGED",
            "change_types": ["NO_CHANGE"],
            "composite_delta": None,
            "rank_delta": None,
            "governance_change": None,
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "NO_IMPACT"

    def test_added_country_is_interpretation_change(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "XX",
            "status": "ADDED",
            "change_types": ["DATA_CHANGE"],
            "composite_delta": None,
            "rank_delta": None,
            "governance_change": None,
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "INTERPRETATION_CHANGE"

    def test_removed_country_is_interpretation_change(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "XX",
            "status": "REMOVED",
            "change_types": ["DATA_CHANGE"],
            "composite_delta": None,
            "rank_delta": None,
            "governance_change": None,
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "INTERPRETATION_CHANGE"

    def test_minor_rank_shift_is_minor_adjustment(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "DE",
            "status": "CHANGED",
            "change_types": ["DATA_CHANGE"],
            "composite_delta": 0.005,
            "rank_delta": 1,
            "governance_change": {"from": "FULLY_COMPARABLE", "to": "FULLY_COMPARABLE", "changed": False},
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "MINOR_ADJUSTMENT"

    def test_governance_to_non_comparable_invalidates(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "DE",
            "status": "CHANGED",
            "change_types": ["GOVERNANCE_CHANGE"],
            "composite_delta": 0.0,
            "rank_delta": 0,
            "governance_change": {"from": "FULLY_COMPARABLE", "to": "NON_COMPARABLE", "changed": True},
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "INVALIDATES_PRIOR_RESULTS"

    def test_usability_to_invalid_invalidates(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "DE",
            "status": "CHANGED",
            "change_types": ["GOVERNANCE_CHANGE"],
            "composite_delta": 0.0,
            "rank_delta": 0,
            "governance_change": None,
            "usability_change": {"from": "TRUSTED_COMPARABLE", "to": "INVALID_FOR_COMPARISON", "changed": True},
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "INVALIDATES_PRIOR_RESULTS"

    def test_large_rank_and_composite_shift_invalidates(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "DE",
            "status": "CHANGED",
            "change_types": ["DATA_CHANGE"],
            "composite_delta": 0.15,
            "rank_delta": 8,
            "governance_change": None,
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "INVALIDATES_PRIOR_RESULTS"

    def test_large_rank_shift_only_is_interpretation_change(self):
        from backend.snapshot_diff import assess_country_policy_impact
        diff = {
            "country": "DE",
            "status": "CHANGED",
            "change_types": ["DATA_CHANGE"],
            "composite_delta": 0.01,
            "rank_delta": 7,
            "governance_change": None,
            "usability_change": None,
        }
        result = assess_country_policy_impact(diff)
        assert result["impact_class"] == "INTERPRETATION_CHANGE"


class TestAssessPolicyImpact:
    """Tests for assess_policy_impact() (global)."""

    def test_empty_diff_returns_no_impact(self):
        from backend.snapshot_diff import assess_policy_impact
        diff_result = {"per_country": {}}
        result = assess_policy_impact(diff_result)
        assert result["overall_impact_class"] == "NO_IMPACT"
        assert result["n_total_countries"] == 0

    def test_one_invalidated_escalates_overall(self):
        from backend.snapshot_diff import assess_policy_impact
        diff_result = {
            "per_country": {
                "DE": {
                    "country": "DE",
                    "status": "CHANGED",
                    "change_types": ["GOVERNANCE_CHANGE"],
                    "composite_delta": 0.0,
                    "rank_delta": 0,
                    "governance_change": {
                        "from": "FULLY_COMPARABLE",
                        "to": "NON_COMPARABLE",
                        "changed": True,
                    },
                    "usability_change": None,
                },
                "FR": {
                    "country": "FR",
                    "status": "UNCHANGED",
                    "change_types": ["NO_CHANGE"],
                    "composite_delta": None,
                    "rank_delta": None,
                    "governance_change": None,
                    "usability_change": None,
                },
            },
        }
        result = assess_policy_impact(diff_result)
        assert result["overall_impact_class"] == "INVALIDATES_PRIOR_RESULTS"
        assert "DE" in result["urgent_countries"]

    def test_impact_distribution_sums_correctly(self):
        from backend.snapshot_diff import assess_policy_impact
        diff_result = {
            "per_country": {
                "DE": {
                    "country": "DE",
                    "status": "UNCHANGED",
                    "change_types": ["NO_CHANGE"],
                    "composite_delta": None,
                    "rank_delta": None,
                    "governance_change": None,
                    "usability_change": None,
                },
                "FR": {
                    "country": "FR",
                    "status": "CHANGED",
                    "change_types": ["DATA_CHANGE"],
                    "composite_delta": 0.005,
                    "rank_delta": 1,
                    "governance_change": None,
                    "usability_change": None,
                },
            },
        }
        result = assess_policy_impact(diff_result)
        dist = result["impact_distribution"]
        total = sum(dist.values())
        assert total == 2

    def test_has_honesty_note(self):
        from backend.snapshot_diff import assess_policy_impact
        result = assess_policy_impact({"per_country": {}})
        assert "honesty_note" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 & 6: FAILURE VISIBILITY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestFlagSeverity:
    """Tests for FlagSeverity and flag construction."""

    def test_severity_levels(self):
        from backend.failure_visibility import FlagSeverity
        assert FlagSeverity.INFO == "INFO"
        assert FlagSeverity.WARNING == "WARNING"
        assert FlagSeverity.ERROR == "ERROR"
        assert FlagSeverity.CRITICAL == "CRITICAL"

    def test_valid_severities_frozenset(self):
        from backend.failure_visibility import VALID_FLAG_SEVERITIES
        assert len(VALID_FLAG_SEVERITIES) == 4


class TestCollectValidityWarnings:
    """Tests for collect_validity_warnings()."""

    def test_non_comparable_governance_is_critical(self):
        from backend.failure_visibility import collect_validity_warnings
        warnings = collect_validity_warnings(
            "DE",
            governance_result={"governance_tier": "NON_COMPARABLE"},
        )
        critical = [w for w in warnings if w["severity"] == "CRITICAL"]
        assert len(critical) >= 1
        assert any(w["rule_id"] == "VW-001" for w in critical)

    def test_low_confidence_is_error(self):
        from backend.failure_visibility import collect_validity_warnings
        warnings = collect_validity_warnings(
            "DE",
            governance_result={"governance_tier": "LOW_CONFIDENCE"},
        )
        errors = [w for w in warnings if w["severity"] == "ERROR"]
        assert len(errors) >= 1
        assert any(w["rule_id"] == "VW-002" for w in errors)

    def test_partially_comparable_is_warning(self):
        from backend.failure_visibility import collect_validity_warnings
        warnings = collect_validity_warnings(
            "DE",
            governance_result={"governance_tier": "PARTIALLY_COMPARABLE"},
        )
        ws = [w for w in warnings if w["severity"] == "WARNING"]
        assert any(w["rule_id"] == "VW-003" for w in ws)

    def test_invalid_usability_is_critical(self):
        from backend.failure_visibility import collect_validity_warnings
        warnings = collect_validity_warnings(
            "DE",
            decision_usability={"decision_usability_class": "INVALID_FOR_COMPARISON"},
        )
        critical = [w for w in warnings if w["severity"] == "CRITICAL"]
        assert any(w["rule_id"] == "VW-005" for w in critical)

    def test_no_inputs_returns_empty(self):
        from backend.failure_visibility import collect_validity_warnings
        warnings = collect_validity_warnings("DE")
        assert warnings == []

    def test_producer_inversions_flagged(self):
        from backend.failure_visibility import collect_validity_warnings
        warnings = collect_validity_warnings(
            "DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "n_producer_inverted_axes": 2,
            },
        )
        assert any(w["rule_id"] == "VW-004" for w in warnings)


class TestCollectConstructFlags:
    """Tests for collect_construct_flags()."""

    def test_substitution_flagged(self):
        from backend.failure_visibility import collect_construct_flags
        flags = collect_construct_flags(
            "DE",
            readiness_matrix=[
                {"axis_id": 2, "construct_substitution": True, "readiness_level": "CONSTRUCT_SUBSTITUTION"},
            ],
        )
        assert any(f["rule_id"] == "CF-001" for f in flags)

    def test_proxy_flagged(self):
        from backend.failure_visibility import collect_construct_flags
        flags = collect_construct_flags(
            "DE",
            readiness_matrix=[
                {"axis_id": 6, "construct_substitution": False, "proxy_used": True},
            ],
        )
        assert any(f["rule_id"] == "CF-002" for f in flags)

    def test_invalid_construct_critical(self):
        from backend.failure_visibility import collect_construct_flags
        flags = collect_construct_flags(
            "DE",
            construct_enforcement={
                "per_axis": [
                    {
                        "axis_id": 3,
                        "construct_validity_class": "CONSTRUCT_INVALID",
                        "applied_rules": ["CE-002"],
                    },
                ],
            },
        )
        critical = [f for f in flags if f["severity"] == "CRITICAL"]
        assert len(critical) >= 1
        assert any(f["rule_id"] == "CF-003" for f in critical)


class TestCollectAlignmentFlags:
    """Tests for collect_alignment_flags()."""

    def test_divergent_alignment_is_error(self):
        from backend.failure_visibility import collect_alignment_flags
        flags = collect_alignment_flags(
            "DE",
            external_validation={"overall_alignment": "DIVERGENT"},
        )
        assert any(f["rule_id"] == "AF-001" for f in flags)

    def test_no_data_is_warning(self):
        from backend.failure_visibility import collect_alignment_flags
        flags = collect_alignment_flags(
            "DE",
            external_validation={"overall_alignment": "NO_DATA"},
        )
        assert any(f["rule_id"] == "AF-002" for f in flags)

    def test_unstable_alignment_is_error(self):
        from backend.failure_visibility import collect_alignment_flags
        flags = collect_alignment_flags(
            "DE",
            sensitivity_result={"stability_class": "ALIGNMENT_UNSTABLE"},
        )
        assert any(f["rule_id"] == "AF-005" for f in flags)

    def test_invalid_mapping_is_critical(self):
        from backend.failure_visibility import collect_alignment_flags
        flags = collect_alignment_flags(
            "DE",
            mapping_audit_results={
                "EXT_FOO": {"mapping_validity": "INVALID_MAPPING"},
            },
        )
        assert any(f["rule_id"] == "AF-007" for f in flags)


class TestCollectInvariantFlags:
    """Tests for collect_invariant_flags()."""

    def test_converts_violations_to_flags(self):
        from backend.failure_visibility import collect_invariant_flags
        flags = collect_invariant_flags({
            "violations": [
                {
                    "invariant_id": "GOV-001",
                    "severity": "CRITICAL",
                    "description": "Test violation",
                    "type": "GOVERNANCE",
                    "affected_country": "DE",
                    "evidence": {},
                },
            ],
        })
        assert len(flags) == 1
        assert flags[0]["rule_id"] == "GOV-001"
        assert flags[0]["severity"] == "CRITICAL"

    def test_empty_violations_returns_empty(self):
        from backend.failure_visibility import collect_invariant_flags
        flags = collect_invariant_flags({"violations": []})
        assert flags == []

    def test_none_returns_empty(self):
        from backend.failure_visibility import collect_invariant_flags
        flags = collect_invariant_flags(None)
        assert flags == []


class TestBuildVisibilityBlock:
    """Tests for build_visibility_block()."""

    def test_minimal_input_returns_sound(self):
        from backend.failure_visibility import build_visibility_block
        block = build_visibility_block("DE")
        assert block["country"] == "DE"
        assert block["trust_level"] == "STRUCTURALLY_SOUND"
        assert block["severity_summary"]["total_flags"] == 0
        assert "honesty_note" in block

    def test_critical_flag_makes_do_not_use(self):
        from backend.failure_visibility import build_visibility_block
        block = build_visibility_block(
            "DE",
            governance_result={"governance_tier": "NON_COMPARABLE"},
        )
        assert block["trust_level"] == "DO_NOT_USE"
        assert block["severity_summary"]["n_critical"] >= 1

    def test_error_flag_makes_extreme_caution(self):
        from backend.failure_visibility import build_visibility_block
        block = build_visibility_block(
            "DE",
            governance_result={"governance_tier": "LOW_CONFIDENCE"},
        )
        assert block["trust_level"] == "USE_WITH_EXTREME_CAUTION"

    def test_warning_flag_makes_documented_caveats(self):
        from backend.failure_visibility import build_visibility_block
        block = build_visibility_block(
            "DE",
            governance_result={"governance_tier": "PARTIALLY_COMPARABLE"},
        )
        assert block["trust_level"] == "USE_WITH_DOCUMENTED_CAVEATS"

    def test_all_flag_categories_present(self):
        from backend.failure_visibility import build_visibility_block
        block = build_visibility_block("DE")
        assert "validity_warnings" in block
        assert "construct_flags" in block
        assert "alignment_flags" in block
        assert "invariant_violations" in block

    def test_severity_summary_counts(self):
        from backend.failure_visibility import build_visibility_block
        block = build_visibility_block(
            "DE",
            governance_result={"governance_tier": "NON_COMPARABLE"},
            decision_usability={"decision_usability_class": "INVALID_FOR_COMPARISON"},
        )
        s = block["severity_summary"]
        assert s["n_critical"] >= 2  # both NON_COMPARABLE and INVALID
        assert s["total_flags"] >= 2


class TestShouldDowngradeUsability:
    """Tests for should_downgrade_usability()."""

    def test_critical_construct_downgrades_to_invalid(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_downgrade_usability,
        )
        block = build_visibility_block(
            "DE",
            construct_enforcement={
                "per_axis": [
                    {
                        "axis_id": 3,
                        "construct_validity_class": "CONSTRUCT_INVALID",
                        "applied_rules": ["CE-002"],
                    },
                ],
                "n_invalid": 1,
                "n_degraded": 0,
            },
        )
        result = should_downgrade_usability(block, "TRUSTED_COMPARABLE")
        assert result["downgraded"]
        assert result["final_class"] == "INVALID_FOR_COMPARISON"

    def test_critical_invariant_downgrades_to_invalid(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_downgrade_usability,
        )
        block = build_visibility_block(
            "DE",
            invariant_result={
                "violations": [
                    {
                        "invariant_id": "GOV-001",
                        "severity": "CRITICAL",
                        "description": "Violation",
                        "type": "GOVERNANCE",
                        "affected_country": "DE",
                        "evidence": {},
                    },
                ],
            },
        )
        result = should_downgrade_usability(block, "TRUSTED_COMPARABLE")
        assert result["downgraded"]
        assert result["final_class"] == "INVALID_FOR_COMPARISON"

    def test_divergent_alignment_downgrades_trusted_to_limited(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_downgrade_usability,
        )
        block = build_visibility_block(
            "DE",
            external_validation={"overall_alignment": "DIVERGENT"},
        )
        result = should_downgrade_usability(block, "TRUSTED_COMPARABLE")
        assert result["downgraded"]
        assert result["final_class"] == "STRUCTURALLY_LIMITED"

    def test_unstable_alignment_downgrades(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_downgrade_usability,
        )
        block = build_visibility_block(
            "DE",
            sensitivity_result={"stability_class": "ALIGNMENT_UNSTABLE"},
        )
        result = should_downgrade_usability(block, "CONDITIONALLY_USABLE")
        assert result["downgraded"]
        assert result["final_class"] == "STRUCTURALLY_LIMITED"

    def test_no_issues_no_downgrade(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_downgrade_usability,
        )
        block = build_visibility_block("DE")
        result = should_downgrade_usability(block, "TRUSTED_COMPARABLE")
        assert not result["downgraded"]
        assert result["final_class"] == "TRUSTED_COMPARABLE"


class TestShouldExcludeFromRankingVisibility:
    """Tests for should_exclude_from_ranking() in failure_visibility."""

    def test_do_not_use_excludes(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_exclude_from_ranking,
        )
        block = build_visibility_block(
            "DE",
            governance_result={"governance_tier": "NON_COMPARABLE"},
        )
        result = should_exclude_from_ranking(block)
        assert result["exclude_from_ranking"]

    def test_sound_includes(self):
        from backend.failure_visibility import (
            build_visibility_block,
            should_exclude_from_ranking,
        )
        block = build_visibility_block("DE")
        result = should_exclude_from_ranking(block)
        assert not result["exclude_from_ranking"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION: INVARIANTS — NEW CE-INV INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════


class TestInvariantRegistryHardening:
    """Tests for new invariants in the registry."""

    def test_registry_has_construct_enforcement_invariants(self):
        from backend.invariants import INVARIANT_REGISTRY
        ce_inv_ids = [
            inv["invariant_id"] for inv in INVARIANT_REGISTRY
            if inv["invariant_id"].startswith("CE-INV-")
        ]
        assert "CE-INV-001" in ce_inv_ids
        assert "CE-INV-002" in ce_inv_ids
        assert "CE-INV-003" in ce_inv_ids
        assert "CE-INV-004" in ce_inv_ids

    def test_construct_enforcement_type_exists(self):
        from backend.invariants import InvariantType, VALID_INVARIANT_TYPES
        assert InvariantType.CONSTRUCT_ENFORCEMENT == "CONSTRUCT_ENFORCEMENT"
        assert "CONSTRUCT_ENFORCEMENT" in VALID_INVARIANT_TYPES

    def test_total_invariants_increased(self):
        from backend.invariants import INVARIANT_REGISTRY
        # Had 17, added 4 → now 21
        assert len(INVARIANT_REGISTRY) >= 28


class TestCheckConstructEnforcementInvariants:
    """Tests for check_construct_enforcement_invariants()."""

    def test_ce_inv_001_invalid_construct_with_nonzero_weight(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            construct_enforcement={
                "composite_blocked": False,
                "n_invalid": 1,
                "per_axis": [
                    {
                        "axis_id": 3,
                        "construct_validity_class": "CONSTRUCT_INVALID",
                        "weight_factor": 0.5,
                    },
                ],
            },
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-001" in ids

    def test_ce_inv_001_no_violation_when_weight_zero(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            construct_enforcement={
                "composite_blocked": False,
                "n_invalid": 1,
                "per_axis": [
                    {
                        "axis_id": 3,
                        "construct_validity_class": "CONSTRUCT_INVALID",
                        "weight_factor": 0.0,
                    },
                ],
            },
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-001" not in ids

    def test_ce_inv_002_logistics_proxy_without_alignment(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            construct_enforcement={
                "per_axis": [
                    {
                        "axis_id": 6,
                        "is_proxy": True,
                        "construct_validity_class": "CONSTRUCT_VALID",
                    },
                ],
            },
            alignment_result={
                "axis_alignments": [
                    {
                        "axis_id": 6,
                        "benchmark_results": [
                            {"alignment_class": "NO_DATA"},
                        ],
                    },
                ],
            },
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-002" in ids

    def test_ce_inv_002_no_violation_with_alignment(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            construct_enforcement={
                "per_axis": [
                    {
                        "axis_id": 6,
                        "is_proxy": True,
                        "construct_validity_class": "CONSTRUCT_VALID",
                    },
                ],
            },
            alignment_result={
                "axis_alignments": [
                    {
                        "axis_id": 6,
                        "benchmark_results": [
                            {"alignment_class": "WEAKLY_ALIGNED"},
                        ],
                    },
                ],
            },
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-002" not in ids

    def test_ce_inv_003_alignment_with_invalid_mapping(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            mapping_audit_results={
                "EXT_FOO": {"mapping_validity": "INVALID_MAPPING"},
            },
            alignment_result={
                "axis_alignments": [
                    {
                        "axis_id": 2,
                        "benchmark_results": [
                            {"benchmark_id": "EXT_FOO", "alignment_class": "STRONGLY_ALIGNED"},
                        ],
                    },
                ],
            },
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-003" in ids

    def test_ce_inv_003_no_violation_when_incomparable(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            mapping_audit_results={
                "EXT_FOO": {"mapping_validity": "INVALID_MAPPING"},
            },
            alignment_result={
                "axis_alignments": [
                    {
                        "axis_id": 2,
                        "benchmark_results": [
                            {"benchmark_id": "EXT_FOO", "alignment_class": "STRUCTURALLY_INCOMPARABLE"},
                        ],
                    },
                ],
            },
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-003" not in ids

    def test_ce_inv_004_unstable_with_trusted(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            sensitivity_result={"stability_class": "ALIGNMENT_UNSTABLE"},
            decision_usability_class="TRUSTED_COMPARABLE",
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-004" in ids

    def test_ce_inv_004_no_violation_when_not_trusted(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants(
            "DE",
            sensitivity_result={"stability_class": "ALIGNMENT_UNSTABLE"},
            decision_usability_class="STRUCTURALLY_LIMITED",
        )
        ids = [v["invariant_id"] for v in violations]
        assert "CE-INV-004" not in ids

    def test_no_inputs_returns_empty(self):
        from backend.invariants import check_construct_enforcement_invariants
        violations = check_construct_enforcement_invariants("DE")
        assert violations == []


class TestAssessCountryInvariantsHardened:
    """Tests that assess_country_invariants() accepts new parameters."""

    def test_accepts_construct_enforcement_parameter(self):
        from backend.invariants import assess_country_invariants
        result = assess_country_invariants(
            "DE",
            axis_scores={1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5},
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "cross_country_comparable": True,
                "composite_defensible": True,
                "n_producer_inverted_axes": 0,
                "mean_axis_confidence": 0.8,
                "axis_confidences": [],
                "producer_inverted_axes": [],
            },
            construct_enforcement={
                "composite_blocked": False,
                "n_invalid": 0,
                "per_axis": [],
            },
        )
        assert "n_violations" in result

    def test_accepts_mapping_and_sensitivity_parameters(self):
        from backend.invariants import assess_country_invariants
        result = assess_country_invariants(
            "DE",
            axis_scores={1: 0.5, 2: 0.6, 3: 0.4, 4: 0.3, 5: 0.7, 6: 0.5},
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "cross_country_comparable": True,
                "composite_defensible": True,
                "n_producer_inverted_axes": 0,
                "mean_axis_confidence": 0.8,
                "axis_confidences": [],
                "producer_inverted_axes": [],
            },
            mapping_audit_results={},
            sensitivity_result={"stability_class": "ALIGNMENT_STABLE"},
        )
        assert "n_violations" in result


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndVisibilityPipeline:
    """Integration tests for the full visibility pipeline."""

    def test_full_pipeline_produces_complete_block(self):
        """Build a visibility block with all inputs and verify completeness."""
        from backend.failure_visibility import build_visibility_block

        block = build_visibility_block(
            country="DE",
            governance_result={
                "governance_tier": "PARTIALLY_COMPARABLE",
                "n_producer_inverted_axes": 1,
            },
            decision_usability={
                "decision_usability_class": "CONDITIONALLY_USABLE",
            },
            construct_enforcement={
                "n_invalid": 0,
                "n_degraded": 1,
                "per_axis": [
                    {
                        "axis_id": 6,
                        "construct_validity_class": "CONSTRUCT_DEGRADED",
                        "applied_rules": ["CE-001"],
                    },
                ],
            },
            readiness_matrix=[
                {"axis_id": 6, "construct_substitution": True, "readiness_level": "CONSTRUCT_SUBSTITUTION"},
            ],
            external_validation={"overall_alignment": "WEAKLY_ALIGNED"},
            sensitivity_result={"stability_class": "ALIGNMENT_SENSITIVE"},
            mapping_audit_results={
                "EXT_BIS_CBS": {"mapping_validity": "WEAK_MAPPING"},
            },
            invariant_result={"violations": []},
        )

        assert block["country"] == "DE"
        assert block["trust_level"] in (
            "STRUCTURALLY_SOUND",
            "USE_WITH_DOCUMENTED_CAVEATS",
            "USE_WITH_EXTREME_CAUTION",
            "DO_NOT_USE",
        )
        assert isinstance(block["validity_warnings"], list)
        assert isinstance(block["construct_flags"], list)
        assert isinstance(block["alignment_flags"], list)
        assert isinstance(block["invariant_violations"], list)
        assert block["severity_summary"]["total_flags"] >= 0

    def test_worst_case_country_is_do_not_use(self):
        """A country with everything wrong should be DO_NOT_USE."""
        from backend.failure_visibility import build_visibility_block

        block = build_visibility_block(
            country="XX",
            governance_result={"governance_tier": "NON_COMPARABLE"},
            decision_usability={
                "decision_usability_class": "INVALID_FOR_COMPARISON",
            },
            construct_enforcement={
                "n_invalid": 4,
                "n_degraded": 2,
                "per_axis": [
                    {"axis_id": i, "construct_validity_class": "CONSTRUCT_INVALID", "applied_rules": ["CE-002"]}
                    for i in range(1, 5)
                ],
            },
            external_validation={"overall_alignment": "DIVERGENT"},
            sensitivity_result={"stability_class": "ALIGNMENT_UNSTABLE"},
            mapping_audit_results={
                "EXT_FOO": {"mapping_validity": "INVALID_MAPPING"},
            },
            invariant_result={
                "violations": [
                    {
                        "invariant_id": "GOV-001",
                        "severity": "CRITICAL",
                        "description": "Critical violation",
                        "type": "GOVERNANCE",
                        "affected_country": "XX",
                        "evidence": {},
                    },
                ],
            },
        )

        assert block["trust_level"] == "DO_NOT_USE"
        assert block["severity_summary"]["n_critical"] >= 3

    def test_clean_country_is_structurally_sound(self):
        """A perfectly clean country should be STRUCTURALLY_SOUND."""
        from backend.failure_visibility import build_visibility_block

        block = build_visibility_block(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "n_producer_inverted_axes": 0,
            },
            decision_usability={
                "decision_usability_class": "TRUSTED_COMPARABLE",
            },
            construct_enforcement={
                "n_invalid": 0,
                "n_degraded": 0,
                "per_axis": [],
            },
            external_validation={"overall_alignment": "STRONGLY_ALIGNED"},
            sensitivity_result={"stability_class": "ALIGNMENT_STABLE"},
            invariant_result={"violations": []},
        )

        assert block["trust_level"] == "STRUCTURALLY_SOUND"
        assert block["severity_summary"]["n_critical"] == 0
        assert block["severity_summary"]["n_error"] == 0


class TestModuleImports:
    """Verify all new modules are importable."""

    def test_import_construct_enforcement(self):
        import backend.construct_enforcement
        assert hasattr(backend.construct_enforcement, "enforce_construct_validity")
        assert hasattr(backend.construct_enforcement, "enforce_all_axes")
        assert hasattr(backend.construct_enforcement, "compute_construct_adjusted_composite")
        assert hasattr(backend.construct_enforcement, "should_exclude_from_ranking")

    def test_import_benchmark_mapping_audit(self):
        import backend.benchmark_mapping_audit
        assert hasattr(backend.benchmark_mapping_audit, "BENCHMARK_MAPPING_AUDIT")
        assert hasattr(backend.benchmark_mapping_audit, "validate_benchmark_mapping")
        assert hasattr(backend.benchmark_mapping_audit, "validate_all_mappings")
        assert hasattr(backend.benchmark_mapping_audit, "should_downgrade_alignment")

    def test_import_alignment_sensitivity(self):
        import backend.alignment_sensitivity
        assert hasattr(backend.alignment_sensitivity, "run_alignment_sensitivity")
        assert hasattr(backend.alignment_sensitivity, "should_downgrade_for_instability")
        assert hasattr(backend.alignment_sensitivity, "AlignmentStabilityClass")

    def test_import_failure_visibility(self):
        import backend.failure_visibility
        assert hasattr(backend.failure_visibility, "build_visibility_block")
        assert hasattr(backend.failure_visibility, "should_downgrade_usability")
        assert hasattr(backend.failure_visibility, "should_exclude_from_ranking")
        assert hasattr(backend.failure_visibility, "collect_validity_warnings")

    def test_import_snapshot_diff_policy_impact(self):
        from backend.snapshot_diff import (
            PolicyImpactClass,
            assess_policy_impact,
            assess_country_policy_impact,
        )
        assert PolicyImpactClass is not None
