"""
tests/test_truth_resolution.py — Tests for the Truth Resolver (Section 3)

Verifies:
    1. Clean state → VALID truth status, no conflicts
    2. Enforcement overrides governance tier → DEGRADED
    3. DO_NOT_USE forces INVALID_FOR_COMPARISON
    4. DIVERGENT alignment forces ranking exclusion
    5. Reality conflicts CRITICAL forces ranking exclusion
    6. Invariant CRITICAL forces usability downgrade
    7. Construct not-producible forces composite suppression
    8. NON_COMPARABLE forces all comparative flags off
    9. LOW_CONFIDENCE forces ranking off
    10. Export blocked → INVALID truth status
    11. Multiple conflicts combine correctly
    12. All resolution decisions logged
"""

from __future__ import annotations

import unittest

from backend.truth_resolver import (
    resolve_truth,
    TruthStatus,
    VALID_TRUTH_STATUSES,
)


def _base_state(**overrides) -> dict:
    """Build minimal valid pipeline state."""
    state = {
        "governance": {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
        },
        "decision_usability": {
            "decision_usability_class": "TRUSTED_COMPARABLE",
        },
        "construct_enforcement": {
            "composite_producible": True,
            "n_valid": 6,
        },
        "external_validation": {
            "overall_alignment": "STRONGLY_ALIGNED",
        },
        "failure_visibility": {
            "trust_level": "STRUCTURALLY_SOUND",
        },
        "reality_conflicts": {
            "has_critical": False,
            "n_critical": 0,
        },
        "invariant_assessment": {
            "has_critical": False,
            "n_critical": 0,
        },
        "alignment_sensitivity": {
            "stability_class": "ALIGNMENT_STABLE",
        },
    }
    state.update(overrides)
    return state


def _base_enforcement(**overrides) -> dict:
    """Build clean enforcement result."""
    enf = {
        "actions": [],
        "n_actions": 0,
        "export_blocked": False,
        "block_reasons": [],
        "enforced_governance_tier": "FULLY_COMPARABLE",
        "enforced_ranking_eligible": True,
        "enforced_cross_country_comparable": True,
        "enforced_composite_suppressed": False,
        "enforced_usability_class": "TRUSTED_COMPARABLE",
    }
    enf.update(overrides)
    return enf


class TestCleanState(unittest.TestCase):
    """Clean state → VALID truth status."""

    def test_clean_state_valid(self):
        result = resolve_truth(_base_state(), _base_enforcement())
        self.assertEqual(result["truth_status"], TruthStatus.VALID)
        self.assertEqual(result["n_conflicts"], 0)
        self.assertEqual(result["n_resolutions"], 0)

    def test_clean_state_preserves_all_fields(self):
        result = resolve_truth(_base_state(), _base_enforcement())
        self.assertEqual(result["final_governance_tier"], "FULLY_COMPARABLE")
        self.assertTrue(result["final_ranking_eligible"])
        self.assertTrue(result["final_cross_country_comparable"])
        self.assertFalse(result["final_composite_suppressed"])
        self.assertEqual(result["final_decision_usability"], "TRUSTED_COMPARABLE")


class TestTierConflict(unittest.TestCase):
    """Enforcement tier override → conflict logged."""

    def test_tier_override_produces_conflict(self):
        state = _base_state()
        enf = _base_enforcement(enforced_governance_tier="LOW_CONFIDENCE")
        result = resolve_truth(state, enf)
        self.assertEqual(result["truth_status"], TruthStatus.DEGRADED)
        self.assertGreater(result["n_conflicts"], 0)
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C001", conflict_ids)

    def test_tier_override_uses_enforcement(self):
        state = _base_state()
        enf = _base_enforcement(enforced_governance_tier="LOW_CONFIDENCE")
        result = resolve_truth(state, enf)
        self.assertEqual(result["final_governance_tier"], "LOW_CONFIDENCE")
        self.assertFalse(result["final_ranking_eligible"])


class TestRankingConflict(unittest.TestCase):
    """Enforcement ranking override → conflict logged."""

    def test_ranking_override_produces_conflict(self):
        state = _base_state()
        enf = _base_enforcement(enforced_ranking_eligible=False)
        result = resolve_truth(state, enf)
        self.assertFalse(result["final_ranking_eligible"])
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C002", conflict_ids)


class TestDoNotUseOverride(unittest.TestCase):
    """DO_NOT_USE forces usability to INVALID_FOR_COMPARISON."""

    def test_do_not_use_forces_invalid(self):
        state = _base_state()
        state["failure_visibility"]["trust_level"] = "DO_NOT_USE"
        # Even if enforcement didn't catch it, truth resolver does
        enf = _base_enforcement(enforced_usability_class="TRUSTED_COMPARABLE")
        result = resolve_truth(state, enf)
        self.assertEqual(result["final_decision_usability"], "INVALID_FOR_COMPARISON")
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C004", conflict_ids)


class TestDivergentAlignment(unittest.TestCase):
    """DIVERGENT alignment forces ranking exclusion."""

    def test_divergent_forces_ranking_off(self):
        state = _base_state()
        state["external_validation"]["overall_alignment"] = "DIVERGENT"
        enf = _base_enforcement(enforced_ranking_eligible=True)
        result = resolve_truth(state, enf)
        self.assertFalse(result["final_ranking_eligible"])
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C005", conflict_ids)


class TestRealityCritical(unittest.TestCase):
    """Reality conflicts CRITICAL → ranking exclusion."""

    def test_critical_reality_forces_ranking_off(self):
        state = _base_state()
        state["reality_conflicts"]["has_critical"] = True
        state["reality_conflicts"]["n_critical"] = 2
        enf = _base_enforcement(enforced_ranking_eligible=True)
        result = resolve_truth(state, enf)
        self.assertFalse(result["final_ranking_eligible"])
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C006", conflict_ids)


class TestInvariantCritical(unittest.TestCase):
    """Invariant CRITICAL → usability downgrade."""

    def test_critical_invariants_downgrade(self):
        state = _base_state()
        state["invariant_assessment"]["has_critical"] = True
        state["invariant_assessment"]["n_critical"] = 1
        enf = _base_enforcement(enforced_usability_class="TRUSTED_COMPARABLE")
        result = resolve_truth(state, enf)
        self.assertEqual(result["final_decision_usability"], "REQUIRES_CONTEXT")
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C007", conflict_ids)

    def test_requires_context_not_downgraded_further(self):
        state = _base_state()
        state["invariant_assessment"]["has_critical"] = True
        enf = _base_enforcement(enforced_usability_class="REQUIRES_CONTEXT")
        result = resolve_truth(state, enf)
        # Already at REQUIRES_CONTEXT, no further downgrade
        self.assertEqual(result["final_decision_usability"], "REQUIRES_CONTEXT")


class TestConstructSuppression(unittest.TestCase):
    """Construct not-producible → composite suppressed."""

    def test_construct_not_producible_suppresses(self):
        state = _base_state()
        state["construct_enforcement"]["composite_producible"] = False
        # If enforcement didn't catch this
        enf = _base_enforcement(enforced_composite_suppressed=False)
        result = resolve_truth(state, enf)
        self.assertTrue(result["final_composite_suppressed"])
        conflict_ids = [c["conflict_id"] for c in result["conflicts"]]
        self.assertIn("TRUTH-C003", conflict_ids)


class TestTierConsistency(unittest.TestCase):
    """Tier consistency assertions."""

    def test_non_comparable_forces_all_off(self):
        state = _base_state()
        enf = _base_enforcement(
            enforced_governance_tier="NON_COMPARABLE",
            enforced_ranking_eligible=False,
            enforced_cross_country_comparable=False,
        )
        result = resolve_truth(state, enf)
        self.assertFalse(result["final_ranking_eligible"])
        self.assertFalse(result["final_cross_country_comparable"])
        self.assertTrue(result["final_composite_suppressed"])

    def test_low_confidence_forces_ranking_off(self):
        state = _base_state()
        enf = _base_enforcement(
            enforced_governance_tier="LOW_CONFIDENCE",
            enforced_ranking_eligible=True,  # Should be forced False
        )
        result = resolve_truth(state, enf)
        self.assertFalse(result["final_ranking_eligible"])


class TestExportBlocked(unittest.TestCase):
    """Export blocked → INVALID truth status."""

    def test_export_blocked_invalid(self):
        state = _base_state()
        enf = _base_enforcement(export_blocked=True, block_reasons=["Missing layer"])
        result = resolve_truth(state, enf)
        self.assertEqual(result["truth_status"], TruthStatus.INVALID)
        self.assertTrue(result["export_blocked"])
        self.assertEqual(result["block_reasons"], ["Missing layer"])


class TestMultipleConflicts(unittest.TestCase):
    """Multiple conflicts combine correctly."""

    def test_divergent_and_critical_reality(self):
        state = _base_state()
        state["external_validation"]["overall_alignment"] = "DIVERGENT"
        state["reality_conflicts"]["has_critical"] = True
        state["reality_conflicts"]["n_critical"] = 1
        enf = _base_enforcement(enforced_ranking_eligible=True)
        result = resolve_truth(state, enf)
        self.assertFalse(result["final_ranking_eligible"])
        self.assertEqual(result["truth_status"], TruthStatus.DEGRADED)

    def test_do_not_use_and_invariant_critical(self):
        state = _base_state()
        state["failure_visibility"]["trust_level"] = "DO_NOT_USE"
        state["invariant_assessment"]["has_critical"] = True
        enf = _base_enforcement(enforced_usability_class="TRUSTED_COMPARABLE")
        result = resolve_truth(state, enf)
        # DO_NOT_USE takes highest priority
        self.assertEqual(result["final_decision_usability"], "INVALID_FOR_COMPARISON")


class TestTruthMetadata(unittest.TestCase):
    """Truth result includes proper metadata."""

    def test_honesty_note_present(self):
        result = resolve_truth(_base_state(), _base_enforcement())
        self.assertIn("honesty_note", result)
        self.assertIn("Truth resolver", result["honesty_note"])

    def test_enforcement_actions_included(self):
        actions = [{"rule_id": "ENF-001", "action": "BLOCK_EXPORT"}]
        enf = _base_enforcement(actions=actions)
        result = resolve_truth(_base_state(), enf)
        self.assertEqual(result["enforcement_actions"], actions)


class TestTruthStatusValues(unittest.TestCase):
    """TruthStatus constants are well-formed."""

    def test_all_statuses_in_valid_set(self):
        for status in [TruthStatus.VALID, TruthStatus.DEGRADED, TruthStatus.INVALID]:
            self.assertIn(status, VALID_TRUTH_STATUSES)

    def test_valid_set_complete(self):
        self.assertEqual(len(VALID_TRUTH_STATUSES), 3)


if __name__ == "__main__":
    unittest.main()
