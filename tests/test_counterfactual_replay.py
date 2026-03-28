"""
tests.test_counterfactual_replay — Tests for Counterfactual Audit Replay

Verifies:
    - build_counterfactual_replay() identifies binding constraints.
    - Produces minimal change recommendations.
    - Handles missing data gracefully.
    - Maps blocked capabilities correctly.
"""

from __future__ import annotations

from backend.audit_replay import (
    build_counterfactual_replay,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: BASIC BEHAVIOR
# ═══════════════════════════════════════════════════════════════════════════

class TestCounterfactualBasic:
    """Basic counterfactual replay behavior."""

    def test_no_data_is_unanalyzable(self):
        result = build_counterfactual_replay("DE", None)
        assert result["counterfactual_status"] == "UNANALYZABLE"

    def test_empty_json_no_constraints(self):
        result = build_counterfactual_replay("DE", {})
        assert result["counterfactual_status"] == "COMPLETE"

    def test_result_has_required_fields(self):
        result = build_counterfactual_replay("DE", {})
        required = [
            "country", "counterfactual_status", "binding_constraints",
            "counterfactuals", "honesty_note",
        ]
        for field in required:
            assert field in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: BINDING CONSTRAINTS
# ═══════════════════════════════════════════════════════════════════════════

class TestBindingConstraints:
    """Binding constraints must be correctly identified."""

    def test_non_comparable_ranking_blocked(self):
        data = {
            "governance": {
                "governance_tier": "NON_COMPARABLE",
                "ranking_eligible": False,
            },
        }
        result = build_counterfactual_replay("DE", data)
        blocked = result["currently_blocked_capabilities"]
        assert "ranking" in blocked

    def test_low_confidence_ranking_blocked(self):
        data = {
            "governance": {
                "governance_tier": "LOW_CONFIDENCE",
                "ranking_eligible": False,
            },
        }
        result = build_counterfactual_replay("DE", data)
        blocked = result["currently_blocked_capabilities"]
        assert "ranking" in blocked

    def test_comparison_blocked_by_truth(self):
        data = {
            "governance": {"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
            "truth_resolution": {
                "final_cross_country_comparable": False,
                "n_conflicts": 3,
            },
        }
        result = build_counterfactual_replay("DE", data)
        blocked = result["currently_blocked_capabilities"]
        assert "comparison" in blocked

    def test_publication_blocked(self):
        data = {
            "governance": {"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
            "publishability": {
                "publishability_status": "NOT_PUBLISHABLE",
                "blockers": ["export_blocked"],
            },
        }
        result = build_counterfactual_replay("DE", data)
        blocked = result["currently_blocked_capabilities"]
        assert "publication" in blocked

    def test_policy_claim_blocked_by_degraded_truth(self):
        data = {
            "governance": {"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
            "truth_resolution": {
                "truth_status": "DEGRADED",
                "final_cross_country_comparable": True,
            },
        }
        result = build_counterfactual_replay("DE", data)
        blocked = result["currently_blocked_capabilities"]
        assert "policy_claim" in blocked

    def test_low_confidence_blocked(self):
        data = {
            "governance": {"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
            "confidence": 0.3,
        }
        result = build_counterfactual_replay("DE", data)
        blocked = result["currently_blocked_capabilities"]
        assert "high_confidence" in blocked


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: COUNTERFACTUAL RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestCounterfactualRecommendations:
    """Counterfactual recommendations must be actionable."""

    def test_recommendations_have_difficulty(self):
        data = {
            "governance": {
                "governance_tier": "NON_COMPARABLE",
                "ranking_eligible": False,
            },
        }
        result = build_counterfactual_replay("DE", data)
        for cf in result["counterfactuals"]:
            assert "difficulty" in cf
            assert cf["difficulty"] in ("LOW", "MODERATE", "HIGH")

    def test_recommendations_have_requires(self):
        data = {
            "governance": {
                "governance_tier": "NON_COMPARABLE",
                "ranking_eligible": False,
            },
        }
        result = build_counterfactual_replay("DE", data)
        for cf in result["counterfactuals"]:
            assert "requires" in cf
            assert isinstance(cf["requires"], list)

    def test_fully_eligible_no_counterfactuals(self):
        data = {
            "governance": {
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            "truth_resolution": {
                "truth_status": "VALID",
                "final_cross_country_comparable": True,
            },
            "confidence": 0.8,
            "publishability": {
                "publishability_status": "PUBLISHABLE",
                "blockers": [],
            },
        }
        result = build_counterfactual_replay("DE", data)
        assert result["n_counterfactuals"] == 0
        assert result["n_binding_constraints"] == 0
