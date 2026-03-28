"""
tests/test_audit_replay.py — Tests for Audit Replay Engine (Section 7)
"""

from __future__ import annotations

import unittest

from backend.audit_replay import (
    AuditStatus,
    VALID_AUDIT_STATUSES,
    replay_country_audit,
)


class TestAuditStatus(unittest.TestCase):
    """Audit statuses must be formally defined."""

    def test_three_statuses(self):
        self.assertEqual(len(VALID_AUDIT_STATUSES), 3)

    def test_expected_statuses(self):
        expected = {"COMPLETE", "PARTIAL", "UNAUDITABLE"}
        self.assertEqual(VALID_AUDIT_STATUSES, expected)


class TestReplayCountryAudit(unittest.TestCase):
    """Audit replay must trace the full decision chain."""

    def test_none_json_returns_unauditable(self):
        result = replay_country_audit("DE", country_json=None)
        self.assertEqual(result["audit_status"], AuditStatus.UNAUDITABLE)
        self.assertEqual(result["country"], "DE")

    def test_complete_json_returns_complete(self):
        country_json = {
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "decision_usability": {"decision_usability_class": "TRUSTED_COMPARABLE"},
            "external_validation": {"overall_alignment": "WEAKLY_ALIGNED"},
            "construct_enforcement": {"composite_producible": True},
            "failure_visibility": {"trust_level": "STRUCTURALLY_SOUND"},
            "reality_conflicts": {"n_conflicts": 0, "has_critical": False},
            "enforcement_actions": {"n_actions": 0, "export_blocked": False},
            "truth_resolution": {
                "truth_status": "VALID",
                "final_governance_tier": "FULLY_COMPARABLE",
            },
            "permitted_scope": {"scope_level": "FULL"},
        }
        result = replay_country_audit("DE", country_json=country_json)
        self.assertEqual(result["audit_status"], AuditStatus.COMPLETE)
        self.assertEqual(result["n_gaps"], 0)
        self.assertGreater(result["n_decision_steps"], 5)

    def test_missing_governance_is_unauditable(self):
        country_json = {
            "decision_usability": {},
            "external_validation": {},
            "construct_enforcement": {},
            "failure_visibility": {},
            "reality_conflicts": {},
            "enforcement_actions": {},
            "truth_resolution": {},
        }
        result = replay_country_audit("DE", country_json=country_json)
        self.assertEqual(result["audit_status"], AuditStatus.UNAUDITABLE)
        self.assertIn("governance_missing", result["gaps"])

    def test_missing_truth_resolution_is_unauditable(self):
        country_json = {
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "decision_usability": {},
            "external_validation": {},
            "construct_enforcement": {},
            "failure_visibility": {},
            "reality_conflicts": {},
            "enforcement_actions": {},
        }
        result = replay_country_audit("DE", country_json=country_json)
        self.assertEqual(result["audit_status"], AuditStatus.UNAUDITABLE)
        self.assertIn("truth_resolution_missing", result["gaps"])

    def test_partial_missing_non_critical(self):
        country_json = {
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "enforcement_actions": {"n_actions": 0},
            "truth_resolution": {"truth_status": "VALID"},
        }
        result = replay_country_audit("DE", country_json=country_json)
        self.assertEqual(result["audit_status"], AuditStatus.PARTIAL)
        self.assertGreater(result["n_gaps"], 0)

    def test_decision_chain_has_step_numbers(self):
        country_json = {
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "enforcement_actions": {"n_actions": 0},
            "truth_resolution": {"truth_status": "VALID"},
        }
        result = replay_country_audit("DE", country_json=country_json)
        for step in result["decision_chain"]:
            self.assertIn("step", step)
            self.assertIn("layer", step)
            self.assertIn("decision", step)

    def test_result_has_honesty_note(self):
        result = replay_country_audit("DE", country_json=None)
        self.assertIn("honesty_note", result)


if __name__ == "__main__":
    unittest.main()
