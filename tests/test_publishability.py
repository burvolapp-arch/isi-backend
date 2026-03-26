"""
tests/test_publishability.py — Tests for Publishability Engine (Section 10)
"""

from __future__ import annotations

import unittest

from backend.publishability import (
    PublishabilityStatus,
    VALID_PUBLISHABILITY_STATUSES,
    assess_publishability,
)


class TestPublishabilityStatus(unittest.TestCase):
    """Publishability statuses must be formally defined."""

    def test_three_statuses(self):
        self.assertEqual(len(VALID_PUBLISHABILITY_STATUSES), 3)

    def test_expected_statuses(self):
        expected = {"PUBLISHABLE", "PUBLISHABLE_WITH_CAVEATS", "NOT_PUBLISHABLE"}
        self.assertEqual(VALID_PUBLISHABILITY_STATUSES, expected)


class TestAssessPublishability(unittest.TestCase):
    """Publishability assessment must correctly evaluate fitness."""

    def test_no_inputs_publishable(self):
        result = assess_publishability("DE")
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.PUBLISHABLE,
        )
        self.assertTrue(result["is_publishable"])

    def test_export_blocked_not_publishable(self):
        result = assess_publishability(
            "DE",
            truth_result={"export_blocked": True},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )
        self.assertFalse(result["is_publishable"])
        self.assertGreater(len(result["blockers"]), 0)

    def test_invalid_truth_not_publishable(self):
        result = assess_publishability(
            "DE",
            truth_result={"truth_status": "INVALID"},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )

    def test_degraded_truth_requires_caveats(self):
        result = assess_publishability(
            "DE",
            truth_result={
                "truth_status": "DEGRADED",
                "n_conflicts": 2,
            },
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        )
        self.assertTrue(result["requires_caveats"])

    def test_non_comparable_not_publishable(self):
        result = assess_publishability(
            "DE",
            truth_result={
                "truth_status": "VALID",
                "final_governance_tier": "NON_COMPARABLE",
            },
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )

    def test_low_confidence_requires_caveats(self):
        result = assess_publishability(
            "DE",
            truth_result={
                "truth_status": "VALID",
                "final_governance_tier": "LOW_CONFIDENCE",
            },
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        )

    def test_scope_blocked_not_publishable(self):
        result = assess_publishability(
            "DE",
            scope_result={"scope_level": "BLOCKED"},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )

    def test_scope_restricted_requires_caveats(self):
        result = assess_publishability(
            "DE",
            scope_result={"scope_level": "RESTRICTED"},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        )

    def test_override_blocking_not_publishable(self):
        result = assess_publishability(
            "DE",
            override_summary={"has_blocking": True},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )

    def test_critical_authority_conflicts_not_publishable(self):
        result = assess_publishability(
            "DE",
            authority_conflicts={"has_critical": True},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )

    def test_incomplete_data_requires_caveats(self):
        result = assess_publishability(
            "DE",
            data_completeness={"axes_available": 4, "axes_required": 6},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        )

    def test_no_data_not_publishable(self):
        result = assess_publishability(
            "DE",
            data_completeness={"axes_available": 0, "axes_required": 6},
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )

    def test_result_has_honesty_note(self):
        result = assess_publishability("DE")
        self.assertIn("honesty_note", result)

    def test_blockers_vs_caveats_distinction(self):
        """Blockers prevent publication; caveats allow with context."""
        result = assess_publishability(
            "DE",
            truth_result={
                "truth_status": "DEGRADED",
                "n_conflicts": 1,
            },
        )
        self.assertEqual(len(result["blockers"]), 0)
        self.assertGreater(len(result["caveats"]), 0)

    def test_multiple_checks_most_restrictive_wins(self):
        """When multiple checks apply, most restrictive status wins."""
        result = assess_publishability(
            "DE",
            truth_result={
                "truth_status": "DEGRADED",
                "n_conflicts": 1,
            },
            authority_conflicts={"has_critical": True},
        )
        # Critical authority conflicts = NOT_PUBLISHABLE, overrides DEGRADED
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.NOT_PUBLISHABLE,
        )


if __name__ == "__main__":
    unittest.main()
