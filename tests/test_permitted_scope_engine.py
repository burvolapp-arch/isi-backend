"""
tests/test_permitted_scope.py — Tests for Permitted Output Scope Engine (Section 4)
"""

from __future__ import annotations

import unittest

from backend.permitted_scope import (
    SCOPE_ORDER,
    SCOPE_PERMISSIONS,
    ScopeLevel,
    VALID_SCOPE_LEVELS,
    determine_permitted_scope,
    enforce_scope,
)


class TestScopeLevel(unittest.TestCase):
    """Scope levels must be formally defined and ordered."""

    def test_five_scope_levels(self):
        self.assertEqual(len(VALID_SCOPE_LEVELS), 5)

    def test_ordering_strict(self):
        self.assertLess(SCOPE_ORDER[ScopeLevel.FULL], SCOPE_ORDER[ScopeLevel.RESTRICTED])
        self.assertLess(SCOPE_ORDER[ScopeLevel.RESTRICTED], SCOPE_ORDER[ScopeLevel.CONTEXT_ONLY])
        self.assertLess(SCOPE_ORDER[ScopeLevel.CONTEXT_ONLY], SCOPE_ORDER[ScopeLevel.SUPPRESSED])
        self.assertLess(SCOPE_ORDER[ScopeLevel.SUPPRESSED], SCOPE_ORDER[ScopeLevel.BLOCKED])

    def test_all_levels_have_permissions(self):
        for level in VALID_SCOPE_LEVELS:
            self.assertIn(level, SCOPE_PERMISSIONS)


class TestScopePermissions(unittest.TestCase):
    """Scope permissions must be consistent with level semantics."""

    def test_full_permits_everything(self):
        perms = SCOPE_PERMISSIONS[ScopeLevel.FULL]
        self.assertTrue(perms["ranking_permitted"])
        self.assertTrue(perms["comparison_permitted"])
        self.assertTrue(perms["composite_permitted"])
        self.assertTrue(perms["score_permitted"])
        self.assertFalse(perms["caveats_required"])

    def test_restricted_no_ranking(self):
        perms = SCOPE_PERMISSIONS[ScopeLevel.RESTRICTED]
        self.assertFalse(perms["ranking_permitted"])
        self.assertFalse(perms["comparison_permitted"])
        self.assertTrue(perms["score_permitted"])
        self.assertTrue(perms["caveats_required"])

    def test_context_only_no_composite(self):
        perms = SCOPE_PERMISSIONS[ScopeLevel.CONTEXT_ONLY]
        self.assertFalse(perms["ranking_permitted"])
        self.assertFalse(perms["composite_permitted"])
        self.assertTrue(perms["score_permitted"])

    def test_suppressed_no_scores(self):
        perms = SCOPE_PERMISSIONS[ScopeLevel.SUPPRESSED]
        self.assertFalse(perms["score_permitted"])
        self.assertFalse(perms["classification_permitted"])

    def test_blocked_nothing_permitted(self):
        perms = SCOPE_PERMISSIONS[ScopeLevel.BLOCKED]
        self.assertFalse(perms["ranking_permitted"])
        self.assertFalse(perms["comparison_permitted"])
        self.assertFalse(perms["composite_permitted"])
        self.assertFalse(perms["score_permitted"])
        self.assertFalse(perms["classification_permitted"])


class TestDeterminePermittedScope(unittest.TestCase):
    """Scope determination must follow truth/override/data checks."""

    def test_no_inputs_returns_full(self):
        result = determine_permitted_scope()
        self.assertEqual(result["scope_level"], ScopeLevel.FULL)
        self.assertEqual(result["n_reasons"], 0)

    def test_export_blocked_returns_blocked(self):
        truth = {"export_blocked": True, "block_reasons": ["test"]}
        result = determine_permitted_scope(truth_result=truth)
        self.assertEqual(result["scope_level"], ScopeLevel.BLOCKED)

    def test_invalid_truth_returns_suppressed(self):
        truth = {"truth_status": "INVALID"}
        result = determine_permitted_scope(truth_result=truth)
        self.assertEqual(result["scope_level"], ScopeLevel.SUPPRESSED)

    def test_non_comparable_returns_suppressed(self):
        truth = {
            "final_governance_tier": "NON_COMPARABLE",
            "truth_status": "VALID",
        }
        result = determine_permitted_scope(truth_result=truth)
        self.assertEqual(result["scope_level"], ScopeLevel.SUPPRESSED)

    def test_low_confidence_returns_context_only(self):
        truth = {
            "final_governance_tier": "LOW_CONFIDENCE",
            "truth_status": "VALID",
            "final_ranking_eligible": False,
        }
        result = determine_permitted_scope(truth_result=truth)
        self.assertIn(result["scope_level"], {
            ScopeLevel.CONTEXT_ONLY,
            ScopeLevel.RESTRICTED,
        })

    def test_not_ranking_eligible_restricted(self):
        truth = {
            "final_governance_tier": "FULLY_COMPARABLE",
            "truth_status": "VALID",
            "final_ranking_eligible": False,
        }
        result = determine_permitted_scope(truth_result=truth)
        self.assertIn(result["scope_level"], {
            ScopeLevel.RESTRICTED,
            ScopeLevel.CONTEXT_ONLY,
        })

    def test_override_blocking_returns_blocked(self):
        override_summary = {"has_blocking": True}
        result = determine_permitted_scope(override_summary=override_summary)
        self.assertEqual(result["scope_level"], ScopeLevel.BLOCKED)

    def test_override_restrictions_restrict_scope(self):
        override_summary = {"n_accepted": 1, "n_restricted": 2}
        result = determine_permitted_scope(override_summary=override_summary)
        self.assertEqual(result["scope_level"], ScopeLevel.RESTRICTED)

    def test_incomplete_data_restricts(self):
        data = {"axes_available": 4, "axes_required": 6}
        result = determine_permitted_scope(data_completeness=data)
        self.assertEqual(result["scope_level"], ScopeLevel.CONTEXT_ONLY)

    def test_no_data_suppresses(self):
        data = {"axes_available": 0, "axes_required": 6}
        result = determine_permitted_scope(data_completeness=data)
        self.assertEqual(result["scope_level"], ScopeLevel.SUPPRESSED)

    def test_multiple_restrictions_stack(self):
        """Most restrictive scope wins when multiple apply."""
        truth = {
            "truth_status": "VALID",
            "final_governance_tier": "LOW_CONFIDENCE",
            "final_ranking_eligible": False,
            "final_composite_suppressed": True,
        }
        data = {"axes_available": 3, "axes_required": 6}
        result = determine_permitted_scope(
            truth_result=truth, data_completeness=data,
        )
        # Should be CONTEXT_ONLY or worse (multiple restrictions)
        self.assertIn(result["scope_level"], {
            ScopeLevel.CONTEXT_ONLY,
            ScopeLevel.SUPPRESSED,
            ScopeLevel.BLOCKED,
        })

    def test_result_has_honesty_note(self):
        result = determine_permitted_scope()
        self.assertIn("honesty_note", result)


class TestEnforceScope(unittest.TestCase):
    """enforce_scope must modify output according to permissions."""

    def test_full_scope_no_changes(self):
        output = {
            "isi_composite": 0.42,
            "isi_classification": "moderate",
            "ranking_position": 5,
            "axes": [{"axis_id": 1, "score": 0.3, "classification": "low"}],
        }
        scope = determine_permitted_scope()
        result = enforce_scope(output, scope)
        self.assertEqual(result["isi_composite"], 0.42)
        self.assertEqual(result["ranking_position"], 5)

    def test_restricted_hides_ranking(self):
        output = {
            "isi_composite": 0.42,
            "ranking_position": 5,
            "axes": [],
        }
        scope = determine_permitted_scope(
            truth_result={
                "final_ranking_eligible": False,
                "truth_status": "VALID",
                "final_governance_tier": "PARTIALLY_COMPARABLE",
            },
        )
        result = enforce_scope(output, scope)
        self.assertIsNone(result["ranking_position"])

    def test_suppressed_hides_scores(self):
        output = {
            "isi_composite": 0.42,
            "isi_classification": "moderate",
            "ranking_position": 5,
            "axes": [{"axis_id": 1, "score": 0.3, "classification": "low"}],
        }
        scope = determine_permitted_scope(
            truth_result={
                "truth_status": "INVALID",
            },
        )
        result = enforce_scope(output, scope)
        self.assertIsNone(result["isi_composite"])
        # Axes scores should be suppressed
        for ax in result.get("axes", []):
            self.assertIsNone(ax.get("score"))

    def test_enforced_output_has_scope_metadata(self):
        output = {"isi_composite": 0.42, "axes": []}
        scope = determine_permitted_scope()
        result = enforce_scope(output, scope)
        self.assertIn("permitted_scope", result)
        self.assertIn("scope_level", result["permitted_scope"])


class TestCriticalScopeEnforcement(unittest.TestCase):
    """CRITICAL: The system must NEVER produce output beyond scope."""

    def test_blocked_country_gets_no_scores(self):
        """A blocked country must not have any usable scores."""
        output = {
            "isi_composite": 0.42,
            "isi_classification": "moderate",
            "ranking_position": 3,
            "axes": [
                {"axis_id": i, "score": 0.3, "classification": "low"}
                for i in range(1, 7)
            ],
        }
        scope = determine_permitted_scope(
            truth_result={"export_blocked": True, "block_reasons": ["test"]},
        )
        result = enforce_scope(output, scope)
        self.assertIsNone(result["isi_composite"])
        self.assertIsNone(result["ranking_position"])
        for ax in result["axes"]:
            self.assertIsNone(ax["score"])

    def test_non_comparable_gets_no_ranking(self):
        """NON_COMPARABLE country must not have ranking position."""
        output = {
            "isi_composite": 0.42,
            "ranking_position": 5,
            "axes": [],
        }
        scope = determine_permitted_scope(
            truth_result={
                "final_governance_tier": "NON_COMPARABLE",
                "truth_status": "VALID",
            },
        )
        result = enforce_scope(output, scope)
        self.assertIsNone(result["ranking_position"])


if __name__ == "__main__":
    unittest.main()
