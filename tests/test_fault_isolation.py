"""
tests.test_fault_isolation — Fault Isolation Test Suite

TRUE FINAL PASS v3, SECTION 8: Tests for epistemic fault isolation,
localized conservatism, and non-collapsing truth system.

Coverage:
    1. Single-axis failure isolation
    2. Authority conflict locality
    3. Runtime containment
    4. Composite degradation vs suppression
    5. Multi-failure merging without explosion
    6. Justified global escalation
    7. Epistemic dependency graph correctness
    8. Scoped publishability
    9. Counterfactual fault resolution
    10. Snapshot diff fault scope tracking
"""

from __future__ import annotations

import pytest

from backend.epistemic_dependencies import (
    OutputType,
    VALID_OUTPUT_TYPES,
    OUTPUT_DEPENDENCIES,
    get_axis_insight_dependencies,
    get_output_dependencies,
    is_output_affected,
    compute_affected_outputs,
    get_composite_weight_threshold,
    should_suppress_composite,
)
from backend.epistemic_fault_isolation import (
    ContainmentLevel,
    VALID_CONTAINMENT_LEVELS,
    EpistemicFaultScope,
    fault_scope_to_dict,
    compute_fault_isolation,
    compute_scoped_publishability,
)
from backend.publishability import (
    PublishabilityStatus,
    assess_publishability,
    assess_scoped_publishability,
)
from backend.audit_replay import (
    counterfactual_fault_resolution,
)
from backend.snapshot_diff import (
    diff_fault_scope,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: EPISTEMIC DEPENDENCY GRAPH
# ═══════════════════════════════════════════════════════════════════════════

class TestOutputType:
    """Tests for OutputType constants."""

    def test_valid_output_types_is_frozenset(self) -> None:
        assert isinstance(VALID_OUTPUT_TYPES, frozenset)

    def test_seven_output_types(self) -> None:
        assert len(VALID_OUTPUT_TYPES) == 7

    def test_all_types_are_strings(self) -> None:
        for ot in VALID_OUTPUT_TYPES:
            assert isinstance(ot, str), f"OutputType {ot!r} is not a string"

    def test_known_types_present(self) -> None:
        expected = {
            OutputType.RANKING,
            OutputType.COMPOSITE,
            OutputType.AXIS_INSIGHT,
            OutputType.POLICY_CLAIM,
            OutputType.COMPARISON,
            OutputType.COUNTRY_ORDERING,
            OutputType.AXIS_SCORE,
        }
        assert expected == VALID_OUTPUT_TYPES

    def test_output_type_values_unique(self) -> None:
        values = [
            OutputType.RANKING,
            OutputType.COMPOSITE,
            OutputType.AXIS_INSIGHT,
            OutputType.POLICY_CLAIM,
            OutputType.COMPARISON,
            OutputType.COUNTRY_ORDERING,
            OutputType.AXIS_SCORE,
        ]
        assert len(values) == len(set(values))


class TestOutputDependencies:
    """Tests for dependency graph correctness."""

    def test_output_dependencies_is_dict(self) -> None:
        assert isinstance(OUTPUT_DEPENDENCIES, dict)

    def test_all_output_types_have_dependencies(self) -> None:
        for ot in VALID_OUTPUT_TYPES:
            if ot in (OutputType.AXIS_INSIGHT, OutputType.AXIS_SCORE):
                continue  # Per-axis, resolved dynamically
            assert ot in OUTPUT_DEPENDENCIES, f"Missing deps for {ot}"

    def test_ranking_depends_on_all_axes(self) -> None:
        deps = get_output_dependencies(OutputType.RANKING)
        assert deps == frozenset({1, 2, 3, 4, 5, 6})

    def test_composite_depends_on_all_axes(self) -> None:
        deps = get_output_dependencies(OutputType.COMPOSITE)
        assert deps == frozenset({1, 2, 3, 4, 5, 6})

    def test_policy_claim_depends_on_all_axes(self) -> None:
        deps = get_output_dependencies(OutputType.POLICY_CLAIM)
        assert deps == frozenset({1, 2, 3, 4, 5, 6})

    def test_comparison_depends_on_all_axes(self) -> None:
        deps = get_output_dependencies(OutputType.COMPARISON)
        assert deps == frozenset({1, 2, 3, 4, 5, 6})

    def test_country_ordering_depends_on_all_axes(self) -> None:
        deps = get_output_dependencies(OutputType.COUNTRY_ORDERING)
        assert deps == frozenset({1, 2, 3, 4, 5, 6})

    def test_axis_insight_depends_on_single_axis(self) -> None:
        for ax in range(1, 7):
            deps = get_axis_insight_dependencies(ax)
            assert deps == frozenset({ax}), f"Axis insight {ax} has wrong deps: {deps}"

    def test_axis_insight_invalid_axis_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid axis_id"):
            get_axis_insight_dependencies(0)
        with pytest.raises(ValueError, match="Invalid axis_id"):
            get_axis_insight_dependencies(7)

    def test_get_output_dependencies_axis_insight_with_axis_id(self) -> None:
        deps = get_output_dependencies(OutputType.AXIS_INSIGHT, axis_id=3)
        assert deps == frozenset({3})

    def test_get_output_dependencies_axis_score_with_axis_id(self) -> None:
        deps = get_output_dependencies(OutputType.AXIS_SCORE, axis_id=5)
        assert deps == frozenset({5})

    def test_get_output_dependencies_axis_insight_without_axis_id(self) -> None:
        with pytest.raises(ValueError, match="requires axis_id"):
            get_output_dependencies(OutputType.AXIS_INSIGHT)

    def test_dependencies_are_frozensets(self) -> None:
        for ot, deps in OUTPUT_DEPENDENCIES.items():
            assert isinstance(deps, frozenset), f"Deps for {ot} not frozenset"


class TestIsOutputAffected:
    """Tests for output-failure overlap detection."""

    def test_ranking_affected_by_any_single_axis(self) -> None:
        for ax in range(1, 7):
            assert is_output_affected(OutputType.RANKING, {ax}) is True

    def test_axis_insight_not_affected_by_unrelated_axis(self) -> None:
        assert is_output_affected(OutputType.AXIS_INSIGHT, {2}, axis_id=1) is False

    def test_axis_insight_affected_by_own_axis(self) -> None:
        assert is_output_affected(OutputType.AXIS_INSIGHT, {3}, axis_id=3) is True

    def test_no_failed_axes_affects_nothing(self) -> None:
        for ot in VALID_OUTPUT_TYPES:
            if ot in (OutputType.AXIS_INSIGHT, OutputType.AXIS_SCORE):
                assert is_output_affected(ot, set(), axis_id=1) is False
            else:
                assert is_output_affected(ot, set()) is False


class TestComputeAffectedOutputs:
    """Tests for bulk output impact computation."""

    def test_no_failures_no_affected(self) -> None:
        result = compute_affected_outputs(set())
        assert result["affected_outputs"] == []
        assert len(result["unaffected_outputs"]) > 0

    def test_single_axis_failure_affects_global_outputs(self) -> None:
        result = compute_affected_outputs({1})
        assert OutputType.RANKING in result["affected_outputs"]
        assert OutputType.COMPOSITE in result["affected_outputs"]

    def test_single_axis_failure_spares_other_axis_insights(self) -> None:
        result = compute_affected_outputs({1})
        # Axis 2 insight should NOT be affected
        affected_set = set(result["affected_outputs"])
        for ax in range(2, 7):
            assert f"axis_insight_{ax}" not in affected_set

    def test_single_axis_failure_affects_own_insight(self) -> None:
        result = compute_affected_outputs({3})
        assert result["per_axis_insights"][3]["affected"] is True

    def test_all_axes_fail_everything_affected(self) -> None:
        result = compute_affected_outputs({1, 2, 3, 4, 5, 6})
        assert len(result["unaffected_outputs"]) == 0


class TestCompositeSuppression:
    """Tests for composite threshold logic."""

    def test_threshold_is_50_percent(self) -> None:
        assert get_composite_weight_threshold() == 0.50

    def test_no_failures_valid(self) -> None:
        result = should_suppress_composite(set())
        assert result["action"] == "VALID"
        assert result["suppress"] is False

    def test_single_axis_failure_degrade(self) -> None:
        result = should_suppress_composite({1})
        assert result["action"] in ("VALID", "DEGRADE")

    def test_four_or_more_axes_suppress(self) -> None:
        result = should_suppress_composite({1, 2, 3, 4})
        assert result["action"] == "SUPPRESS"
        assert result["suppress"] is True

    def test_equal_weights_three_axes_degrade(self) -> None:
        weights = {i: 1.0 / 6 for i in range(1, 7)}
        result = should_suppress_composite({1, 2, 3}, axis_weights=weights)
        assert result["action"] == "DEGRADE"
        assert result["suppress"] is False

    def test_heavy_weight_on_failed_axis_suppress(self) -> None:
        weights = {1: 0.60, 2: 0.08, 3: 0.08, 4: 0.08, 5: 0.08, 6: 0.08}
        result = should_suppress_composite({1}, axis_weights=weights)
        assert result["action"] == "SUPPRESS"
        assert result["suppress"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: FAULT ISOLATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TestContainmentLevel:
    """Tests for containment level constants."""

    def test_valid_levels_count(self) -> None:
        assert len(VALID_CONTAINMENT_LEVELS) == 3

    def test_known_levels(self) -> None:
        assert ContainmentLevel.LOCAL in VALID_CONTAINMENT_LEVELS
        assert ContainmentLevel.REGIONAL in VALID_CONTAINMENT_LEVELS
        assert ContainmentLevel.GLOBAL in VALID_CONTAINMENT_LEVELS


class TestEpistemicFaultScope:
    """Tests for EpistemicFaultScope dataclass."""

    def test_create_fault_scope(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset({OutputType.AXIS_INSIGHT}),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Test scope",
        )
        assert scope.containment_level == ContainmentLevel.LOCAL
        assert 1 in scope.affected_axes
        assert scope.propagation_allowed is True

    def test_fault_scope_is_frozen(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset(),
            affected_countries=frozenset(),
            affected_outputs=frozenset(),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="VALID",
            reasoning="Empty scope",
        )
        with pytest.raises(AttributeError):
            scope.containment_level = ContainmentLevel.GLOBAL  # type: ignore[misc]

    def test_fault_scope_to_dict(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1, 2}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset({OutputType.AXIS_INSIGHT}),
            containment_level=ContainmentLevel.REGIONAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Test scope",
        )
        d = fault_scope_to_dict(scope)
        assert isinstance(d, dict)
        assert d["containment_level"] == ContainmentLevel.REGIONAL
        assert sorted(d["affected_axes"]) == [1, 2]
        assert d["composite_action"] == "DEGRADE"
        assert "reasoning" in d


class TestComputeFaultIsolation:
    """Tests for the main fault isolation engine."""

    def test_no_failures_local_scope(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        assert scope.containment_level == ContainmentLevel.LOCAL
        assert len(scope.affected_axes) == 0
        assert len(scope.affected_outputs) == 0

    def test_single_axis_failure_local(self) -> None:
        """FI-002: Single axis failure stays LOCAL."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={3},
        )
        assert scope.containment_level == ContainmentLevel.LOCAL
        assert 3 in scope.affected_axes
        # Axis 3 insight affected, but axis 1 insight NOT
        assert f"axis_insight_1" not in scope.affected_outputs

    def test_two_axis_failure_regional(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1, 4},
        )
        assert scope.containment_level in (
            ContainmentLevel.LOCAL,
            ContainmentLevel.REGIONAL,
        )

    def test_four_or_more_axes_global(self) -> None:
        """FI-008: ≥4 failed axes → GLOBAL escalation."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1, 2, 3, 4},
        )
        assert scope.containment_level == ContainmentLevel.GLOBAL

    def test_authority_conflict_locality(self) -> None:
        """FI-005: Authority conflicts scoped to their axis."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={
                "conflicts": [{"axis_id": 2}],
            },
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        assert 2 in scope.affected_axes
        # Should NOT escalate to global
        assert scope.containment_level != ContainmentLevel.GLOBAL

    def test_runtime_pipeline_failure_global(self) -> None:
        """FI-007: Full pipeline failure → GLOBAL."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={"pipeline_status": "FAILED"},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        assert scope.containment_level == ContainmentLevel.GLOBAL

    def test_non_comparable_governance_global(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={"governance_tier": "NON_COMPARABLE"},
            axis_failures=set(),
        )
        assert scope.containment_level == ContainmentLevel.GLOBAL

    def test_critical_invariant_global(self) -> None:
        """FI-006: System-wide CRITICAL invariant → GLOBAL."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[
                {"severity": "CRITICAL", "invariant_type": "PIPELINE_INTEGRITY"},
            ],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        assert scope.containment_level == ContainmentLevel.GLOBAL

    def test_axis_scoped_invariant_local(self) -> None:
        """FI-006: Axis-scoped invariant stays local."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[
                {"severity": "WARNING", "affected_axes": [2]},
            ],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        assert scope.containment_level != ContainmentLevel.GLOBAL
        assert 2 in scope.affected_axes

    def test_composite_action_set(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1, 2, 3, 4},
        )
        assert scope.composite_action in ("VALID", "DEGRADE", "SUPPRESS")

    def test_unaffected_outputs_populated(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
        )
        assert len(scope.unaffected_outputs) > 0

    def test_axis_weights_affect_composite(self) -> None:
        """Heavy weight on failed axis → SUPPRESS."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
            axis_weights={1: 0.70, 2: 0.06, 3: 0.06, 4: 0.06, 5: 0.06, 6: 0.06},
        )
        assert scope.composite_action == "SUPPRESS"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: SCOPED PUBLISHABILITY
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeScopedPublishability:
    """Tests for per-output publishability from fault scope."""

    def test_no_faults_all_publishable(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset(),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset(),
            unaffected_outputs=frozenset(VALID_OUTPUT_TYPES),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="VALID",
            reasoning="No faults",
        )
        result = compute_scoped_publishability(scope)
        for key, val in result.items():
            if key.startswith("publishability_"):
                assert val == "PUBLISHABLE", f"{key} should be PUBLISHABLE"

    def test_affected_output_gets_caveats(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset({OutputType.AXIS_INSIGHT}),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Axis 1 failed",
        )
        result = compute_scoped_publishability(scope)
        assert result[f"publishability_{OutputType.RANKING}"] == "PUBLISHABLE_WITH_CAVEATS"

    def test_global_affected_output_not_publishable(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1, 2, 3, 4, 5, 6}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING, OutputType.COMPOSITE}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.GLOBAL,
            propagation_allowed=False,
            composite_action="SUPPRESS",
            reasoning="Global failure",
        )
        result = compute_scoped_publishability(scope)
        assert result[f"publishability_{OutputType.RANKING}"] == "NOT_PUBLISHABLE"

    def test_composite_suppress_not_publishable(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1, 2, 3, 4}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.COMPOSITE}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.REGIONAL,
            propagation_allowed=True,
            composite_action="SUPPRESS",
            reasoning="Composite suppressed",
        )
        result = compute_scoped_publishability(scope)
        assert result[f"publishability_{OutputType.COMPOSITE}"] == "NOT_PUBLISHABLE"

    def test_composite_degrade_caveats(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1, 2}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.COMPOSITE}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.REGIONAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Composite degraded",
        )
        result = compute_scoped_publishability(scope)
        assert result[f"publishability_{OutputType.COMPOSITE}"] == "PUBLISHABLE_WITH_CAVEATS"

    def test_per_axis_publishability_present(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset(),
            unaffected_outputs=frozenset(VALID_OUTPUT_TYPES),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="VALID",
            reasoning="Axis 1",
        )
        result = compute_scoped_publishability(scope)
        assert "publishability_axis_1" in result
        assert "publishability_axis_6" in result

    def test_affected_axis_gets_caveats_others_publishable(self) -> None:
        """Core test: axis failure isolates to that axis only."""
        scope = EpistemicFaultScope(
            affected_axes=frozenset({2}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({f"axis_insight_2"}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Axis 2 only",
        )
        result = compute_scoped_publishability(scope)
        assert result["publishability_axis_2"] == "PUBLISHABLE_WITH_CAVEATS"
        # Other axes should be unaffected
        for ax in [1, 3, 4, 5, 6]:
            assert result[f"publishability_axis_{ax}"] == "PUBLISHABLE"

    def test_honesty_note_present(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset(),
            affected_countries=frozenset(),
            affected_outputs=frozenset(),
            unaffected_outputs=frozenset(VALID_OUTPUT_TYPES),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="VALID",
            reasoning="Clean",
        )
        result = compute_scoped_publishability(scope)
        assert "honesty_note" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: ASSESS SCOPED PUBLISHABILITY (publishability.py wrapper)
# ═══════════════════════════════════════════════════════════════════════════

class TestAssessScopedPublishability:
    """Tests for the high-level scoped publishability wrapper."""

    def test_no_fault_scope_legacy_mode(self) -> None:
        result = assess_scoped_publishability(
            country="DE",
            fault_scope=None,
        )
        assert result["scoped"] is False
        assert result["publishability_status"] in (
            PublishabilityStatus.PUBLISHABLE,
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
            PublishabilityStatus.NOT_PUBLISHABLE,
            PublishabilityStatus.RESTRICTED,
        )
        assert result["per_output_publishability"] == {}

    def test_with_fault_scope_is_scoped(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset({OutputType.AXIS_INSIGHT}),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Axis 1 failed",
        )
        result = assess_scoped_publishability(
            country="DE",
            fault_scope=scope,
        )
        assert result["scoped"] is True
        assert "per_output_publishability" in result
        assert len(result["per_output_publishability"]) > 0

    def test_baseline_preserved(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset(),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset(),
            unaffected_outputs=frozenset(VALID_OUTPUT_TYPES),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="VALID",
            reasoning="No faults",
        )
        result = assess_scoped_publishability(
            country="DE",
            fault_scope=scope,
        )
        assert "baseline_status" in result
        assert result["baseline_status"] == PublishabilityStatus.PUBLISHABLE

    def test_affected_axes_reported(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({2, 5}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.REGIONAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Two axes failed",
        )
        result = assess_scoped_publishability(
            country="DE",
            fault_scope=scope,
        )
        assert result["n_affected_axes"] == 2
        assert result["affected_axes"] == [2, 5]

    def test_honesty_note_mentions_isolation(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset({OutputType.AXIS_INSIGHT}),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Test",
        )
        result = assess_scoped_publishability(
            country="DE",
            fault_scope=scope,
        )
        assert "axis failures do NOT suppress" in result["honesty_note"]

    def test_output_counts_present(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset({OutputType.AXIS_INSIGHT}),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Test",
        )
        result = assess_scoped_publishability(
            country="DE",
            fault_scope=scope,
        )
        assert "n_outputs_publishable" in result
        assert "n_outputs_caveats" in result
        assert "n_outputs_blocked" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: COUNTERFACTUAL FAULT RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

class TestCounterfactualFaultResolution:
    """Tests for counterfactual fault resolution in audit replay."""

    def test_no_fault_scope(self) -> None:
        result = counterfactual_fault_resolution(
            country="DE",
            fault_scope=None,
        )
        assert result["resolution_status"] == "NO_FAULTS"
        assert result["n_resolutions"] == 0

    def test_no_affected_outputs(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset(),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset(),
            unaffected_outputs=frozenset(VALID_OUTPUT_TYPES),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="VALID",
            reasoning="Clean",
        )
        result = counterfactual_fault_resolution(
            country="DE",
            fault_scope=scope,
        )
        assert result["resolution_status"] == "ALL_CLEAR"

    def test_single_axis_resolution(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({3}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({"axis_insight_3"}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Axis 3 failed",
        )
        result = counterfactual_fault_resolution(
            country="DE",
            fault_scope=scope,
        )
        assert result["resolution_status"] == "ANALYZED"
        assert result["n_resolutions"] > 0
        assert result["n_restorable"] > 0

    def test_resolution_has_required_fields(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Axis 1 failed",
        )
        result = counterfactual_fault_resolution(
            country="DE",
            fault_scope=scope,
        )
        for r in result["resolutions"]:
            assert "output" in r
            assert "remove_constraint" in r
            assert "restore_if" in r
            assert "smallest_fix" in r
            assert "difficulty" in r

    def test_composite_suppress_resolution(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1, 2, 3, 4}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.COMPOSITE}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.GLOBAL,
            propagation_allowed=False,
            composite_action="SUPPRESS",
            reasoning="Too many failures",
        )
        result = counterfactual_fault_resolution(
            country="DE",
            fault_scope=scope,
        )
        composite_resolutions = [
            r for r in result["resolutions"]
            if r["output"] == OutputType.COMPOSITE
        ]
        assert len(composite_resolutions) == 1
        assert "50%" in composite_resolutions[0]["restore_if"]

    def test_honesty_note_present(self) -> None:
        scope = EpistemicFaultScope(
            affected_axes=frozenset({1}),
            affected_countries=frozenset({"DE"}),
            affected_outputs=frozenset({OutputType.RANKING}),
            unaffected_outputs=frozenset(),
            containment_level=ContainmentLevel.LOCAL,
            propagation_allowed=True,
            composite_action="DEGRADE",
            reasoning="Test",
        )
        result = counterfactual_fault_resolution(
            country="DE",
            fault_scope=scope,
        )
        assert "honesty_note" in result
        assert "SMALLEST" in result["honesty_note"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: SNAPSHOT DIFF FAULT SCOPE TRACKING
# ═══════════════════════════════════════════════════════════════════════════

class TestDiffFaultScope:
    """Tests for fault scope diff in snapshot_diff."""

    def test_no_scopes(self) -> None:
        result = diff_fault_scope("DE", None, None)
        assert result["fault_scope_status"] == "NO_SCOPE"
        assert result["has_change"] is False
        assert result["is_material"] is False

    def test_scope_introduced(self) -> None:
        scope_b = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [OutputType.RANKING],
        }
        result = diff_fault_scope("DE", None, scope_b)
        assert result["fault_scope_status"] == "INTRODUCED"
        assert result["has_change"] is True
        assert result["is_material"] is True
        assert result["scope_direction"] == "EXPANSION"

    def test_scope_resolved(self) -> None:
        scope_a = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [OutputType.RANKING],
        }
        result = diff_fault_scope("DE", scope_a, None)
        assert result["fault_scope_status"] == "RESOLVED"
        assert result["has_change"] is True
        assert result["scope_direction"] == "CONTRACTION"
        # Resolution is non-material (improvement)
        assert result["is_material"] is False

    def test_scope_unchanged(self) -> None:
        scope = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [OutputType.RANKING],
        }
        result = diff_fault_scope("DE", scope, scope)
        assert result["fault_scope_status"] == "UNCHANGED"
        assert result["has_change"] is False

    def test_scope_expansion_is_material(self) -> None:
        """Rule: Any scope expansion = MATERIAL CHANGE."""
        scope_a = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [OutputType.RANKING],
        }
        scope_b = {
            "containment_level": ContainmentLevel.REGIONAL,
            "affected_axes": [1, 2],
            "affected_outputs": [OutputType.RANKING, OutputType.COMPOSITE],
        }
        result = diff_fault_scope("DE", scope_a, scope_b)
        assert result["has_change"] is True
        assert result["is_material"] is True
        assert result["scope_direction"] == "EXPANSION"
        assert result["axes_added"] == [2]
        assert OutputType.COMPOSITE in result["outputs_added"]

    def test_scope_contraction_not_material(self) -> None:
        scope_a = {
            "containment_level": ContainmentLevel.REGIONAL,
            "affected_axes": [1, 2, 3],
            "affected_outputs": [OutputType.RANKING, OutputType.COMPOSITE],
        }
        scope_b = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [OutputType.RANKING],
        }
        result = diff_fault_scope("DE", scope_a, scope_b)
        assert result["has_change"] is True
        assert result["scope_direction"] == "CONTRACTION"
        assert result["is_material"] is False
        assert result["axes_removed"] == [2, 3]

    def test_containment_level_expansion_is_material(self) -> None:
        scope_a = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [],
        }
        scope_b = {
            "containment_level": ContainmentLevel.GLOBAL,
            "affected_axes": [1],
            "affected_outputs": [],
        }
        result = diff_fault_scope("DE", scope_a, scope_b)
        assert result["has_change"] is True
        assert result["is_material"] is True
        assert result["containment_change"]["from"] == ContainmentLevel.LOCAL
        assert result["containment_change"]["to"] == ContainmentLevel.GLOBAL

    def test_honesty_note_present(self) -> None:
        scope_a = {
            "containment_level": ContainmentLevel.LOCAL,
            "affected_axes": [1],
            "affected_outputs": [OutputType.RANKING],
        }
        scope_b = {
            "containment_level": ContainmentLevel.REGIONAL,
            "affected_axes": [1, 2],
            "affected_outputs": [OutputType.RANKING],
        }
        result = diff_fault_scope("DE", scope_a, scope_b)
        assert "honesty_note" in result
        assert "MATERIAL" in result["honesty_note"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: MULTI-FAILURE MERGING
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiFailureMerging:
    """Tests that multiple failures merge without explosion."""

    def test_two_axis_failures_merge_not_explode(self) -> None:
        """Two independent axis failures should not escalate to GLOBAL."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1, 3},
        )
        # 2 axes should not be GLOBAL
        assert scope.containment_level != ContainmentLevel.GLOBAL
        assert len(scope.affected_axes) == 2

    def test_three_axis_failures_not_global(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1, 2, 5},
        )
        assert scope.containment_level != ContainmentLevel.GLOBAL

    def test_axis_failure_plus_authority_conflict_merge(self) -> None:
        """Axis failure + authority conflict on different axis → merge, not explode."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={
                "conflicts": [{"axis_id": 4}],
            },
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
        )
        assert 1 in scope.affected_axes
        assert 4 in scope.affected_axes
        # 2 affected axes should not be GLOBAL
        assert scope.containment_level != ContainmentLevel.GLOBAL

    def test_multiple_fault_sources_total_axes_count_for_escalation(self) -> None:
        """Combined faults reach ≥4 axes → GLOBAL."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[
                {"severity": "WARNING", "affected_axes": [5]},
                {"severity": "WARNING", "affected_axes": [6]},
            ],
            authority_conflicts={
                "conflicts": [{"axis_id": 3}],
            },
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
        )
        # 4 total affected axes (1, 3, 5, 6) → should escalate
        assert scope.containment_level == ContainmentLevel.GLOBAL


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: INTEGRATION / ARBITER FAULT SCOPE
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterFaultScopeIntegration:
    """Tests that arbiter correctly passes fault scope through."""

    def test_arbiter_returns_fault_scope(self) -> None:
        from backend.epistemic_arbiter import adjudicate

        result = adjudicate(
            country="DE",
            epistemic_bounds={},
            invariant_report={"status": "VALID", "violations": []},
            governance={},
        )
        assert "fault_scope" in result
        assert isinstance(result["fault_scope"], dict)
        assert "containment_level" in result["fault_scope"]

    def test_arbiter_returns_scoped_publishability(self) -> None:
        from backend.epistemic_arbiter import adjudicate

        result = adjudicate(
            country="DE",
            epistemic_bounds={},
            invariant_report={"status": "VALID", "violations": []},
            governance={},
        )
        assert "scoped_publishability" in result
        assert isinstance(result["scoped_publishability"], dict)

    def test_arbiter_fault_scope_has_containment_level(self) -> None:
        from backend.epistemic_arbiter import adjudicate

        result = adjudicate(
            country="DE",
            epistemic_bounds={},
            invariant_report={"status": "VALID", "violations": []},
            governance={},
        )
        level = result["fault_scope"]["containment_level"]
        assert level in VALID_CONTAINMENT_LEVELS

    def test_arbiter_with_axis_failures(self) -> None:
        from backend.epistemic_arbiter import adjudicate

        result = adjudicate(
            country="DE",
            epistemic_bounds={},
            invariant_report={"status": "VALID", "violations": []},
            governance={},
            axis_failures={2},
        )
        assert 2 in result["fault_scope"]["affected_axes"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: CORE ISOLATION INVARIANT TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCoreIsolationInvariants:
    """Tests for the core invariant: axis failure must not suppress unrelated outputs."""

    def test_axis_1_failure_does_not_suppress_axis_2_insight(self) -> None:
        """THE CORE INVARIANT: unrelated outputs survive."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
        )
        pub = compute_scoped_publishability(scope)
        # Axis 2 should remain publishable
        assert pub["publishability_axis_2"] == "PUBLISHABLE"
        # Axis 1 should have caveats
        assert pub["publishability_axis_1"] == "PUBLISHABLE_WITH_CAVEATS"

    def test_axis_failure_does_not_suppress_unrelated_insights(self) -> None:
        """Verify ALL unrelated axes remain publishable."""
        for failed_ax in range(1, 7):
            scope = compute_fault_isolation(
                country="DE",
                invariant_violations=[],
                authority_conflicts={},
                runtime_failures={},
                epistemic_bounds={},
                governance={},
                axis_failures={failed_ax},
            )
            pub = compute_scoped_publishability(scope)
            for other_ax in range(1, 7):
                if other_ax != failed_ax:
                    assert pub[f"publishability_axis_{other_ax}"] == "PUBLISHABLE", (
                        f"Axis {failed_ax} failure suppressed axis {other_ax}"
                    )

    def test_global_does_suppress_everything(self) -> None:
        """When escalation is justified, suppression IS correct."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={"pipeline_status": "FAILED"},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        assert scope.containment_level == ContainmentLevel.GLOBAL
        pub = compute_scoped_publishability(scope)
        # At least some outputs should be NOT_PUBLISHABLE
        not_pub_count = sum(
            1 for k, v in pub.items()
            if k.startswith("publishability_") and v == "NOT_PUBLISHABLE"
        )
        assert not_pub_count > 0

    def test_no_false_suppression_with_clean_state(self) -> None:
        """Zero failures → zero suppression."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures=set(),
        )
        pub = compute_scoped_publishability(scope)
        for key, val in pub.items():
            if key.startswith("publishability_"):
                assert val == "PUBLISHABLE", f"{key} was {val} with no failures"

    def test_fault_scope_reasoning_is_nonempty(self) -> None:
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
        )
        assert isinstance(scope.reasoning, (str, tuple, list))
        assert len(scope.reasoning) > 0

    def test_all_output_types_accounted_for(self) -> None:
        """affected + unaffected should cover all output types (approximately)."""
        scope = compute_fault_isolation(
            country="DE",
            invariant_violations=[],
            authority_conflicts={},
            runtime_failures={},
            epistemic_bounds={},
            governance={},
            axis_failures={1},
        )
        total = len(scope.affected_outputs) + len(scope.unaffected_outputs)
        # Should have at least the global output types + some per-axis
        assert total >= len(VALID_OUTPUT_TYPES) - 2  # minus AXIS_INSIGHT and AXIS_SCORE base types
