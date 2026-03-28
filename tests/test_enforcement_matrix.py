"""
tests/test_enforcement_matrix.py — Tests for the Enforcement Matrix (Section 2)

Verifies:
    1. Missing layers block export
    2. Construct invalidity suppresses composite
    3. DIVERGENT alignment excludes from ranking
    4. DO_NOT_USE trust forces usability downgrade
    5. Reality conflicts CRITICAL forces ranking exclusion
    6. Producer inversion >= 2 forces LOW_CONFIDENCE floor
    7. Alignment unstable downgrades usability
    8. Invariant CRITICAL forces review
    9. NON_COMPARABLE tier forces all flags off
    10. Clean state produces no enforcement actions
"""

from __future__ import annotations

import unittest

from backend.enforcement_matrix import (
    apply_enforcement,
    get_enforcement_rules,
    ENFORCEMENT_RULES,
    TIER_ORDER,
)


def _base_state(**overrides) -> dict:
    """Build a minimal valid pipeline state for enforcement testing."""
    state = {
        "governance": {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
        },
        "decision_usability": {
            "decision_usability_class": "TRUSTED_COMPARABLE",
        },
        "construct_enforcement": {
            "composite_producible": True,
            "n_valid": 6,
            "n_invalid": 0,
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


class TestEnforcementCleanState(unittest.TestCase):
    """Clean state should produce no enforcement actions."""

    def test_no_actions_for_clean_state(self):
        result = apply_enforcement(_base_state())
        self.assertEqual(result["n_actions"], 0)
        self.assertFalse(result["export_blocked"])
        self.assertEqual(result["enforced_governance_tier"], "FULLY_COMPARABLE")
        self.assertTrue(result["enforced_ranking_eligible"])
        self.assertTrue(result["enforced_cross_country_comparable"])
        self.assertFalse(result["enforced_composite_suppressed"])

    def test_clean_state_preserves_usability(self):
        result = apply_enforcement(_base_state())
        self.assertEqual(result["enforced_usability_class"], "TRUSTED_COMPARABLE")


class TestENF001MissingLayers(unittest.TestCase):
    """ENF-001: Missing layers block export."""

    def test_missing_governance_blocks(self):
        state = _base_state()
        state["governance"] = None
        result = apply_enforcement(state)
        self.assertTrue(result["export_blocked"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-001", rule_ids)

    def test_missing_construct_enforcement_blocks(self):
        state = _base_state()
        state["construct_enforcement"] = None
        result = apply_enforcement(state)
        self.assertTrue(result["export_blocked"])

    def test_errored_layer_blocks(self):
        state = _base_state()
        state["failure_visibility"] = {"error": "Something failed"}
        result = apply_enforcement(state)
        self.assertTrue(result["export_blocked"])

    def test_all_layers_present_no_block(self):
        result = apply_enforcement(_base_state())
        self.assertFalse(result["export_blocked"])


class TestENF002ConstructInvalid(unittest.TestCase):
    """ENF-002: Construct invalid suppresses composite."""

    def test_composite_not_producible_suppresses(self):
        state = _base_state()
        state["construct_enforcement"]["composite_producible"] = False
        state["construct_enforcement"]["n_valid"] = 2
        state["construct_enforcement"]["n_invalid"] = 4
        result = apply_enforcement(state)
        self.assertTrue(result["enforced_composite_suppressed"])
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-002", rule_ids)


class TestENF003DivergentAlignment(unittest.TestCase):
    """ENF-003: DIVERGENT alignment excludes from ranking."""

    def test_divergent_excludes_ranking(self):
        state = _base_state()
        state["external_validation"]["overall_alignment"] = "DIVERGENT"
        result = apply_enforcement(state)
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-003", rule_ids)

    def test_weakly_aligned_keeps_ranking(self):
        state = _base_state()
        state["external_validation"]["overall_alignment"] = "WEAKLY_ALIGNED"
        result = apply_enforcement(state)
        self.assertTrue(result["enforced_ranking_eligible"])


class TestENF004FailureVisibility(unittest.TestCase):
    """ENF-004: DO_NOT_USE forces usability downgrade."""

    def test_do_not_use_forces_invalid(self):
        state = _base_state()
        state["failure_visibility"]["trust_level"] = "DO_NOT_USE"
        result = apply_enforcement(state)
        self.assertEqual(result["enforced_usability_class"], "INVALID_FOR_COMPARISON")
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-004", rule_ids)

    def test_structurally_sound_preserves_usability(self):
        state = _base_state()
        state["failure_visibility"]["trust_level"] = "STRUCTURALLY_SOUND"
        result = apply_enforcement(state)
        self.assertEqual(result["enforced_usability_class"], "TRUSTED_COMPARABLE")


class TestENF005RealityConflictsCritical(unittest.TestCase):
    """ENF-005: CRITICAL reality conflicts → ranking exclusion."""

    def test_critical_reality_excludes_ranking(self):
        state = _base_state()
        state["reality_conflicts"]["has_critical"] = True
        state["reality_conflicts"]["n_critical"] = 2
        result = apply_enforcement(state)
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-005", rule_ids)

    def test_no_critical_keeps_ranking(self):
        state = _base_state()
        state["reality_conflicts"]["has_critical"] = False
        result = apply_enforcement(state)
        self.assertTrue(result["enforced_ranking_eligible"])


class TestENF006ProducerInversion(unittest.TestCase):
    """ENF-006: ≥2 producer-inverted → LOW_CONFIDENCE floor."""

    def test_two_inversions_forces_low_confidence(self):
        state = _base_state()
        state["governance"]["n_producer_inverted_axes"] = 2
        result = apply_enforcement(state)
        self.assertEqual(result["enforced_governance_tier"], "LOW_CONFIDENCE")
        self.assertFalse(result["enforced_cross_country_comparable"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-006", rule_ids)

    def test_one_inversion_no_floor(self):
        state = _base_state()
        state["governance"]["n_producer_inverted_axes"] = 1
        result = apply_enforcement(state)
        self.assertEqual(result["enforced_governance_tier"], "FULLY_COMPARABLE")

    def test_three_inversions_still_low_confidence_floor(self):
        state = _base_state()
        state["governance"]["n_producer_inverted_axes"] = 3
        result = apply_enforcement(state)
        # Floor is LOW_CONFIDENCE; governance may say NON_COMPARABLE
        # but enforcement enforces at least LOW_CONFIDENCE
        self.assertIn(
            result["enforced_governance_tier"],
            ("LOW_CONFIDENCE", "NON_COMPARABLE"),
        )


class TestENF007AlignmentUnstable(unittest.TestCase):
    """ENF-007: ALIGNMENT_UNSTABLE downgrades usability."""

    def test_unstable_downgrades_trusted(self):
        state = _base_state()
        state["alignment_sensitivity"]["stability_class"] = "ALIGNMENT_UNSTABLE"
        result = apply_enforcement(state)
        self.assertNotEqual(result["enforced_usability_class"], "TRUSTED_COMPARABLE")
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-007", rule_ids)

    def test_stable_preserves_trusted(self):
        state = _base_state()
        state["alignment_sensitivity"]["stability_class"] = "ALIGNMENT_STABLE"
        result = apply_enforcement(state)
        self.assertEqual(result["enforced_usability_class"], "TRUSTED_COMPARABLE")


class TestENF008InvariantCritical(unittest.TestCase):
    """ENF-008: CRITICAL invariants downgrade usability and exclude ranking."""

    def test_critical_invariants_downgrade(self):
        state = _base_state()
        state["invariant_assessment"]["has_critical"] = True
        state["invariant_assessment"]["n_critical"] = 1
        result = apply_enforcement(state)
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-008", rule_ids)


class TestNonComparableOverride(unittest.TestCase):
    """NON_COMPARABLE tier forces all comparative flags off."""

    def test_non_comparable_forces_all_off(self):
        state = _base_state()
        state["governance"]["governance_tier"] = "NON_COMPARABLE"
        state["governance"]["ranking_eligible"] = False
        state["governance"]["cross_country_comparable"] = False
        result = apply_enforcement(state)
        self.assertFalse(result["enforced_ranking_eligible"])
        self.assertFalse(result["enforced_cross_country_comparable"])
        self.assertTrue(result["enforced_composite_suppressed"])

    def test_low_confidence_forces_ranking_off(self):
        state = _base_state()
        state["governance"]["governance_tier"] = "LOW_CONFIDENCE"
        state["governance"]["ranking_eligible"] = False
        result = apply_enforcement(state)
        self.assertFalse(result["enforced_ranking_eligible"])


class TestEnforcementMetadata(unittest.TestCase):
    """Enforcement result includes proper metadata."""

    def test_tier_change_tracked(self):
        state = _base_state()
        state["governance"]["n_producer_inverted_axes"] = 2
        result = apply_enforcement(state)
        self.assertTrue(result["tier_changed"])
        self.assertNotEqual(
            result["original_governance_tier"],
            result["enforced_governance_tier"],
        )

    def test_ranking_change_tracked(self):
        state = _base_state()
        state["external_validation"]["overall_alignment"] = "DIVERGENT"
        result = apply_enforcement(state)
        self.assertTrue(result["ranking_changed"])

    def test_honesty_note_present(self):
        result = apply_enforcement(_base_state())
        self.assertIn("honesty_note", result)
        self.assertIn("Enforcement matrix", result["honesty_note"])


class TestEnforcementRuleRegistry(unittest.TestCase):
    """Enforcement rule registry is well-formed."""

    def test_registry_non_empty(self):
        self.assertGreater(len(ENFORCEMENT_RULES), 0)

    def test_all_rules_have_required_fields(self):
        for rule in ENFORCEMENT_RULES:
            self.assertIn("rule_id", rule)
            self.assertIn("name", rule)
            self.assertIn("description", rule)

    def test_rule_ids_unique(self):
        ids = [r["rule_id"] for r in ENFORCEMENT_RULES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_get_enforcement_rules_returns_copy(self):
        rules = get_enforcement_rules()
        rules.append({"rule_id": "FAKE"})
        self.assertNotEqual(len(get_enforcement_rules()), len(rules))

    def test_registry_has_8_rules(self):
        self.assertEqual(len(ENFORCEMENT_RULES), 8)


class TestMultipleEnforcementsCombine(unittest.TestCase):
    """Multiple enforcement actions should combine correctly."""

    def test_divergent_and_critical_reality(self):
        state = _base_state()
        state["external_validation"]["overall_alignment"] = "DIVERGENT"
        state["reality_conflicts"]["has_critical"] = True
        state["reality_conflicts"]["n_critical"] = 1
        result = apply_enforcement(state)
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-003", rule_ids)
        self.assertIn("ENF-005", rule_ids)

    def test_do_not_use_and_invariant_critical(self):
        state = _base_state()
        state["failure_visibility"]["trust_level"] = "DO_NOT_USE"
        state["invariant_assessment"]["has_critical"] = True
        result = apply_enforcement(state)
        self.assertEqual(result["enforced_usability_class"], "INVALID_FOR_COMPARISON")
        self.assertFalse(result["enforced_ranking_eligible"])
        rule_ids = [a["rule_id"] for a in result["actions"]]
        self.assertIn("ENF-004", rule_ids)
        self.assertIn("ENF-008", rule_ids)


if __name__ == "__main__":
    unittest.main()
