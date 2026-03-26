"""
tests/test_misuse_resistance.py — Misuse Resistance Tests (Section 12)

Validates:
    - The system CANNOT produce output stronger than authority allows.
    - Clean rankings without caveats are impossible for degraded countries.
    - Policy-usable output requires full epistemic chain.
    - Stripped context triggers structural detection.
"""

from __future__ import annotations

import unittest

from backend.epistemic_override import (
    OverrideOutcome,
    evaluate_epistemic_override,
    compute_override_summary,
)
from backend.permitted_scope import (
    ScopeLevel,
    determine_permitted_scope,
    enforce_scope,
)
from backend.publishability import (
    PublishabilityStatus,
    assess_publishability,
)
from backend.truth_resolver import TruthStatus


class TestCannotProduceCleanRankingForDegradedCountry(unittest.TestCase):
    """A country with epistemic issues must NEVER have clean ranking."""

    def test_non_comparable_blocks_ranking(self):
        """NON_COMPARABLE tier → no ranking permitted."""
        truth_result = {
            "truth_status": TruthStatus.DEGRADED,
            "final_governance_tier": "NON_COMPARABLE",
            "final_ranking_eligible": False,
            "final_composite_suppressed": True,
            "export_blocked": False,
        }
        scope = determine_permitted_scope(truth_result)
        self.assertFalse(scope["permissions"]["ranking_permitted"])

    def test_invalid_truth_suppresses_all(self):
        """INVALID truth status with export blocked → BLOCKED scope."""
        truth_result = {
            "truth_status": TruthStatus.INVALID,
            "final_governance_tier": "NON_COMPARABLE",
            "final_ranking_eligible": False,
            "final_composite_suppressed": True,
            "export_blocked": True,
        }
        scope = determine_permitted_scope(truth_result)
        self.assertEqual(scope["scope_level"], ScopeLevel.BLOCKED)

    def test_export_blocked_prevents_scope(self):
        """export_blocked → BLOCKED scope level."""
        truth_result = {
            "truth_status": TruthStatus.INVALID,
            "final_governance_tier": "NON_COMPARABLE",
            "final_ranking_eligible": False,
            "final_composite_suppressed": True,
            "export_blocked": True,
        }
        scope = determine_permitted_scope(truth_result)
        self.assertIn(scope["scope_level"], {ScopeLevel.BLOCKED, ScopeLevel.SUPPRESSED})

    def test_tier1_override_always_accepted(self):
        """Tier 1 authority override is ALWAYS accepted — not negotiable."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.25,
            external_value=0.35,
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.35)

    def test_cannot_ignore_tier1_authority(self):
        """Even if internal value is 'better', Tier 1 wins."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.10,  # "better" (lower dependency)
            external_value=0.50,  # Worse but authoritative
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.50)


class TestPolicyUsableOutputRequiresEpistemicChain(unittest.TestCase):
    """Output marked PUBLISHABLE must have full epistemic chain."""

    def test_publishable_requires_valid_truth(self):
        """PUBLISHABLE status requires VALID truth."""
        result = assess_publishability(
            country="DE",
            truth_result={
                "truth_status": TruthStatus.VALID,
                "export_blocked": False,
            },
            scope_result={
                "scope_level": ScopeLevel.FULL,
                "ranking_permitted": True,
                "caveats_required": False,
            },
        )
        self.assertEqual(result["publishability_status"], PublishabilityStatus.PUBLISHABLE)

    def test_degraded_truth_requires_caveats(self):
        """DEGRADED truth → PUBLISHABLE_WITH_CAVEATS at best."""
        result = assess_publishability(
            country="DE",
            truth_result={
                "truth_status": TruthStatus.DEGRADED,
                "export_blocked": False,
            },
            scope_result={
                "scope_level": ScopeLevel.RESTRICTED,
                "ranking_permitted": False,
                "caveats_required": True,
            },
        )
        self.assertIn(result["publishability_status"], {
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
            PublishabilityStatus.NOT_PUBLISHABLE,
        })

    def test_invalid_truth_not_publishable(self):
        """INVALID truth → NOT_PUBLISHABLE."""
        result = assess_publishability(
            country="DE",
            truth_result={
                "truth_status": TruthStatus.INVALID,
                "export_blocked": True,
            },
            scope_result={
                "scope_level": ScopeLevel.BLOCKED,
                "ranking_permitted": False,
                "caveats_required": True,
            },
        )
        self.assertEqual(result["publishability_status"], PublishabilityStatus.NOT_PUBLISHABLE)


class TestStrippedContextDetection(unittest.TestCase):
    """Output with stripped context must be detectable."""

    def test_enforce_scope_adds_caveats(self):
        """When scope requires caveats, enforce_scope must add them."""
        output = {
            "isi_composite": 0.35,
            "isi_classification": "mildly_concentrated",
        }
        scope_result = {
            "scope_level": ScopeLevel.CONTEXT_ONLY,
            "permissions": {
                "ranking_permitted": False,
                "comparison_permitted": False,
                "composite_permitted": False,
                "score_permitted": True,
                "classification_permitted": True,
                "caveats_required": True,
            },
        }
        enforced = enforce_scope(output, scope_result)
        self.assertIn("permitted_scope", enforced)

    def test_scope_suppressed_nullifies_composite(self):
        """SUPPRESSED scope must suppress composite."""
        output = {
            "isi_composite": 0.35,
            "isi_classification": "mildly_concentrated",
        }
        scope_result = {
            "scope_level": ScopeLevel.SUPPRESSED,
            "permissions": {
                "ranking_permitted": False,
                "comparison_permitted": False,
                "composite_permitted": False,
                "score_permitted": False,
                "classification_permitted": False,
                "caveats_required": True,
            },
        }
        enforced = enforce_scope(output, scope_result)
        # Composite should be nullified
        self.assertIsNone(enforced.get("isi_composite"))
        scope_info = enforced.get("permitted_scope", {})
        self.assertIn(scope_info.get("scope_level", ""), {
            ScopeLevel.SUPPRESSED, ScopeLevel.BLOCKED,
        })


class TestOverrideSummaryBlocking(unittest.TestCase):
    """Override summary must correctly propagate blocking."""

    def test_blocking_override_propagates(self):
        """A BLOCKED override should propagate to summary."""
        from backend.epistemic_override import OverrideResult

        results = [
            OverrideResult(
                outcome=OverrideOutcome.BLOCKED,
                field="governance_tier",
                internal_value="FULLY_COMPARABLE",
                external_value="NON_COMPARABLE",
                resolved_value=None,
                authority_id="AUTH_EUROSTAT",
                authority_tier="TIER_1_PRIMARY",
                override_reason="Irreconcilable.",
            ),
        ]
        summary = compute_override_summary(results)
        self.assertTrue(summary["has_blocking"])
        self.assertEqual(summary["n_blocked"], 1)


class TestConservativeResolutionAlways(unittest.TestCase):
    """Tier 2 authorities must always resolve to conservative value."""

    def test_tier2_picks_conservative_numeric(self):
        """Tier 2 resolves to higher (worse) numeric value."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.20,
            external_value=0.40,
            authority_id="AUTH_IMF",  # Tier 2
        )
        self.assertEqual(result.outcome, OverrideOutcome.RESTRICTED)
        # Conservative = higher concentration = max
        self.assertEqual(result.resolved_value, max(0.20, 0.40))

    def test_tier2_picks_conservative_boolean(self):
        """Tier 2 resolves boolean to False (more conservative)."""
        result = evaluate_epistemic_override(
            field="ranking_eligible",
            internal_value=True,
            external_value=False,
            authority_id="AUTH_IMF",
        )
        self.assertEqual(result.outcome, OverrideOutcome.RESTRICTED)
        self.assertFalse(result.resolved_value)


if __name__ == "__main__":
    unittest.main()
