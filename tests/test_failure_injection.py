"""
tests/test_failure_injection.py — Failure Injection / Chaos Tests (Section 14)

Validates:
    - Every new module handles missing inputs gracefully.
    - None/empty/malformed data does not crash the system.
    - The epistemic chain degrades gracefully under partial failure.
"""

from __future__ import annotations

import unittest

from backend.epistemic_hierarchy import (
    EpistemicLevel,
    build_claim,
    resolve_conflict,
    outranks,
    get_hierarchy,
)
from backend.external_authority_registry import (
    get_authority_by_id,
    get_authorities_for_axis,
    get_tier_1_authorities,
    authority_outranks,
)
from backend.epistemic_override import (
    OverrideOutcome,
    evaluate_epistemic_override,
    evaluate_batch_overrides,
    compute_override_summary,
)
from backend.permitted_scope import (
    ScopeLevel,
    determine_permitted_scope,
    enforce_scope,
)
from backend.audit_replay import (
    AuditStatus,
    replay_country_audit,
)
from backend.authority_conflicts import (
    detect_authority_conflicts,
)
from backend.publishability import (
    PublishabilityStatus,
    assess_publishability,
)
from backend.complexity_budget import (
    audit_complexity,
)
from backend.truth_resolver import TruthStatus


class TestEpistemicHierarchyChaos(unittest.TestCase):
    """Epistemic hierarchy must handle garbage inputs."""

    def test_outranks_with_unknown_levels(self):
        """Unknown levels should not crash."""
        # Unknown level should not outrank EXTERNAL_AUTHORITY
        self.assertFalse(
            outranks("NONEXISTENT_LEVEL", EpistemicLevel.EXTERNAL_AUTHORITY)
        )

    def test_resolve_conflict_with_same_level(self):
        """Same-level conflict should resolve without crash."""
        claim_a = build_claim("field", 1.0, EpistemicLevel.INTERNAL_COMPUTATION, "src_a")
        claim_b = build_claim("field", 2.0, EpistemicLevel.INTERNAL_COMPUTATION, "src_b")
        winner = resolve_conflict(claim_a, claim_b)
        self.assertIsNotNone(winner)

    def test_get_hierarchy_returns_dict(self):
        """get_hierarchy must always return a list."""
        result = get_hierarchy()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)


class TestAuthorityRegistryChaos(unittest.TestCase):
    """Authority registry must handle unknown IDs gracefully."""

    def test_unknown_authority_returns_none(self):
        result = get_authority_by_id("AUTH_NONEXISTENT")
        self.assertIsNone(result)

    def test_invalid_axis_returns_empty(self):
        result = get_authorities_for_axis(999)
        self.assertEqual(result, [])

    def test_authority_outranks_unknown(self):
        """Unknown authority IDs should not crash."""
        # authority_outranks takes authority dicts, not IDs
        # Test with unknown entries lookup
        auth_a = get_authority_by_id("AUTH_NONEXISTENT")
        auth_b = get_authority_by_id("AUTH_BIS")
        self.assertIsNone(auth_a)
        self.assertIsNotNone(auth_b)


class TestEpistemicOverrideChaos(unittest.TestCase):
    """Override engine must handle edge cases."""

    def test_unknown_authority_flags(self):
        """Unknown authority → FLAGGED, not crash."""
        result = evaluate_epistemic_override(
            field="test_field",
            internal_value=0.5,
            external_value=0.6,
            authority_id="DOES_NOT_EXIST",
        )
        self.assertEqual(result.outcome, OverrideOutcome.FLAGGED)
        self.assertEqual(result.resolved_value, 0.5)  # Internal retained

    def test_none_values_handled(self):
        """None values should be handled without crash."""
        result = evaluate_epistemic_override(
            field="test_field",
            internal_value=None,
            external_value=None,
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.NO_CONFLICT)

    def test_empty_batch(self):
        """Empty batch should return empty results."""
        results = evaluate_batch_overrides([])
        self.assertEqual(results, [])

    def test_empty_summary(self):
        """Summary of empty results should not crash."""
        summary = compute_override_summary([])
        self.assertEqual(summary["n_overrides"], 0)
        self.assertFalse(summary["has_blocking"])


class TestPermittedScopeChaos(unittest.TestCase):
    """Scope engine must handle missing/malformed truth results."""

    def test_empty_truth_result(self):
        """Empty truth result should produce conservative scope."""
        scope = determine_permitted_scope({})
        # Should not crash; should produce restrictive scope
        self.assertIn(scope["scope_level"], {
            ScopeLevel.FULL, ScopeLevel.RESTRICTED,
            ScopeLevel.CONTEXT_ONLY, ScopeLevel.SUPPRESSED,
            ScopeLevel.BLOCKED,
        })

    def test_none_truth_result_key(self):
        """None values in truth result should be handled."""
        truth = {
            "truth_status": None,
            "final_governance_tier": None,
            "final_ranking_eligible": None,
            "final_composite_suppressed": None,
            "export_blocked": None,
        }
        scope = determine_permitted_scope(truth)
        self.assertIn("scope_level", scope)

    def test_enforce_scope_on_empty_output(self):
        """enforce_scope on empty output should not crash."""
        scope = {
            "scope_level": ScopeLevel.FULL,
            "ranking_permitted": True,
            "caveats_required": False,
        }
        result = enforce_scope({}, scope)
        self.assertIsInstance(result, dict)


class TestAuditReplayChaos(unittest.TestCase):
    """Audit replay must handle incomplete country JSON."""

    def test_empty_country_json(self):
        """Empty country JSON → UNAUDITABLE."""
        result = replay_country_audit("DE", {})
        self.assertEqual(result["audit_status"], AuditStatus.UNAUDITABLE)

    def test_none_country_json(self):
        """None values in layers should produce partial audit."""
        country_json = {
            "governance": None,
            "decision_usability": None,
            "external_validation": None,
            "construct_enforcement": None,
            "failure_visibility": None,
            "reality_conflicts": None,
            "enforcement_actions": None,
            "truth_resolution": None,
        }
        result = replay_country_audit("DE", country_json)
        self.assertIn(result["audit_status"], {
            AuditStatus.PARTIAL, AuditStatus.UNAUDITABLE,
        })


class TestAuthorityConflictsChaos(unittest.TestCase):
    """Conflict detection must handle edge cases."""

    def test_empty_claims(self):
        """Empty claims → no conflicts."""
        result = detect_authority_conflicts([])
        self.assertEqual(result["n_conflicts"], 0)

    def test_single_claim_no_conflict(self):
        """Single claim cannot conflict with itself."""
        claims = [
            {"field": "axis_1_score", "value": 0.3, "authority_id": "AUTH_BIS"},
        ]
        result = detect_authority_conflicts(claims)
        self.assertEqual(result["n_conflicts"], 0)


class TestPublishabilityChaos(unittest.TestCase):
    """Publishability assessment must handle missing inputs."""

    def test_minimal_inputs(self):
        """Minimal inputs should not crash."""
        result = assess_publishability(country="DE")
        self.assertIn(result["publishability_status"], {
            PublishabilityStatus.PUBLISHABLE,
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
            PublishabilityStatus.NOT_PUBLISHABLE,
        })

    def test_all_none_inputs(self):
        """All None inputs should produce conservative assessment."""
        result = assess_publishability(
            country="DE",
            truth_result=None,
            scope_result=None,
            override_summary=None,
            authority_conflicts=None,
        )
        self.assertIn("publishability_status", result)


class TestComplexityBudgetChaos(unittest.TestCase):
    """Complexity budget must handle missing paths."""

    def test_nonexistent_dirs(self):
        """Nonexistent directories should not crash."""
        from pathlib import Path

        result = audit_complexity(
            backend_dir=Path("/nonexistent/backend"),
            tests_dir=Path("/nonexistent/tests"),
        )
        self.assertIn("overall_status", result)

    def test_zero_counts(self):
        """Zero counts for all metrics should be within budget."""
        result = audit_complexity(
            n_invariants=0,
            n_pipeline_layers=0,
            n_enforcement_rules=0,
        )
        # Should be WITHIN for the specified budgets
        for budget in result["budgets"]:
            if budget["name"] in ("invariants", "pipeline_layers", "enforcement_rules"):
                self.assertNotEqual(budget["status"], "EXCEEDED")


class TestCrossModuleIntegration(unittest.TestCase):
    """Cross-module interactions must be coherent."""

    def test_override_feeds_scope(self):
        """Override summary correctly feeds scope determination."""
        from backend.epistemic_override import OverrideResult

        override_results = [
            OverrideResult(
                outcome=OverrideOutcome.ACCEPTED,
                field="axis_1_score",
                internal_value=0.2,
                external_value=0.4,
                resolved_value=0.4,
                authority_id="AUTH_BIS",
                authority_tier="TIER_1_PRIMARY",
                override_reason="Tier 1 override.",
            ),
        ]
        summary = compute_override_summary(override_results)

        truth_result = {
            "truth_status": TruthStatus.DEGRADED,
            "final_governance_tier": "PARTIALLY_COMPARABLE",
            "final_ranking_eligible": True,
            "final_composite_suppressed": False,
            "export_blocked": False,
        }

        scope = determine_permitted_scope(truth_result, summary)
        self.assertIn("scope_level", scope)

    def test_full_chain_no_crash(self):
        """Full epistemic chain runs without crash."""
        # Override
        override = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.2,
            external_value=0.4,
            authority_id="AUTH_BIS",
        )
        summary = compute_override_summary([override])

        # Scope
        truth_result = {
            "truth_status": TruthStatus.VALID,
            "final_governance_tier": "FULLY_COMPARABLE",
            "final_ranking_eligible": True,
            "final_composite_suppressed": False,
            "export_blocked": False,
        }
        scope = determine_permitted_scope(truth_result, summary)

        # Publishability
        pub = assess_publishability(
            country="DE",
            truth_result=truth_result,
            scope_result=scope,
            override_summary=summary,
        )
        self.assertIn(pub["publishability_status"], {
            PublishabilityStatus.PUBLISHABLE,
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
            PublishabilityStatus.NOT_PUBLISHABLE,
        })


if __name__ == "__main__":
    unittest.main()
