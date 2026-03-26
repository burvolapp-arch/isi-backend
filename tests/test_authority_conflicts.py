"""
tests/test_authority_conflicts.py — Tests for Authority Conflicts Engine (Section 8)
"""

from __future__ import annotations

import unittest

from backend.authority_conflicts import (
    ConflictSeverity,
    VALID_CONFLICT_SEVERITIES,
    detect_authority_conflicts,
)


class TestConflictSeverity(unittest.TestCase):
    """Conflict severities must be formally defined."""

    def test_four_severities(self):
        self.assertEqual(len(VALID_CONFLICT_SEVERITIES), 4)


class TestDetectAuthorityConflicts(unittest.TestCase):
    """Conflict detection must find and resolve disagreements."""

    def test_empty_claims(self):
        result = detect_authority_conflicts([])
        self.assertEqual(result["n_claims"], 0)
        self.assertEqual(result["n_conflicts"], 0)

    def test_no_conflict_when_agree(self):
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.42},
            {"authority_id": "AUTH_EUROSTAT", "field": "axis_1_score", "value": 0.42},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 0)

    def test_near_agreement_no_conflict(self):
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.420},
            {"authority_id": "AUTH_EUROSTAT", "field": "axis_1_score", "value": 0.425},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 0)

    def test_tier_1_vs_tier_1_is_critical(self):
        """Two Tier 1 authorities disagreeing is CRITICAL."""
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.30},
            {"authority_id": "AUTH_EUROSTAT", "field": "axis_1_score", "value": 0.70},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 1)
        self.assertTrue(result["has_critical"])
        self.assertTrue(result["output_restricted"])

    def test_tier_1_vs_tier_2_resolved_by_hierarchy(self):
        """Tier 1 authority wins over Tier 2."""
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.30},
            {"authority_id": "AUTH_IMF", "field": "axis_1_score", "value": 0.70},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 1)
        # Resolution should favor AUTH_BIS (Tier 1)
        self.assertEqual(result["resolutions"][0]["resolved_value"], 0.30)

    def test_same_tier_2_conservative(self):
        """Same-tier conflicts resolve to conservative value."""
        claims = [
            {"authority_id": "AUTH_IMF", "field": "axis_1_score", "value": 0.30},
            {"authority_id": "AUTH_OECD", "field": "axis_1_score", "value": 0.70},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 1)
        # Conservative = higher value (more concentrated)
        self.assertEqual(result["resolutions"][0]["resolved_value"], 0.70)

    def test_different_fields_no_conflict(self):
        """Claims about different fields don't conflict."""
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.30},
            {"authority_id": "AUTH_IEA", "field": "axis_2_score", "value": 0.70},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 0)

    def test_three_way_conflict(self):
        """Three authorities disagreeing on same field."""
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.20},
            {"authority_id": "AUTH_EUROSTAT", "field": "axis_1_score", "value": 0.50},
            {"authority_id": "AUTH_IMF", "field": "axis_1_score", "value": 0.80},
        ]
        result = detect_authority_conflicts(claims)
        # Should find multiple conflicts
        self.assertGreater(result["n_conflicts"], 0)

    def test_warnings_generated(self):
        claims = [
            {"authority_id": "AUTH_BIS", "field": "axis_1_score", "value": 0.30},
            {"authority_id": "AUTH_IMF", "field": "axis_1_score", "value": 0.70},
        ]
        result = detect_authority_conflicts(claims)
        self.assertGreater(result["n_warnings"], 0)

    def test_result_has_honesty_note(self):
        result = detect_authority_conflicts([])
        self.assertIn("honesty_note", result)

    def test_boolean_conflict(self):
        claims = [
            {"authority_id": "AUTH_EUROSTAT", "field": "ranking_eligible", "value": True},
            {"authority_id": "AUTH_BIS", "field": "ranking_eligible", "value": False},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 1)


if __name__ == "__main__":
    unittest.main()
