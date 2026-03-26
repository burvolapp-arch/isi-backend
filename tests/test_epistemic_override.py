"""
tests/test_epistemic_override.py — Tests for Epistemic Override Engine (Section 3)
"""

from __future__ import annotations

import unittest

from backend.epistemic_override import (
    OverrideOutcome,
    OverrideResult,
    VALID_OVERRIDE_OUTCOMES,
    compute_override_summary,
    evaluate_batch_overrides,
    evaluate_epistemic_override,
    override_result_to_dict,
)
from backend.epistemic_hierarchy import EpistemicLevel


class TestOverrideOutcome(unittest.TestCase):
    """Override outcomes must be formally defined."""

    def test_five_outcomes(self):
        self.assertEqual(len(VALID_OVERRIDE_OUTCOMES), 5)

    def test_expected_outcomes_exist(self):
        expected = {"ACCEPTED", "RESTRICTED", "FLAGGED", "BLOCKED", "NO_CONFLICT"}
        self.assertEqual(VALID_OVERRIDE_OUTCOMES, expected)


class TestOverrideResult(unittest.TestCase):
    """OverrideResult must validate outcome."""

    def test_valid_result(self):
        result = OverrideResult(
            outcome=OverrideOutcome.ACCEPTED,
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.55,
            resolved_value=0.55,
            authority_id="AUTH_BIS",
            authority_tier="TIER_1_PRIMARY",
            override_reason="BIS is primary.",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.55)

    def test_invalid_outcome_raises(self):
        with self.assertRaises(ValueError):
            OverrideResult(
                outcome="BOGUS",
                field="x",
                internal_value=1,
                external_value=2,
                resolved_value=2,
                authority_id="test",
                authority_tier="test",
                override_reason="test",
            )

    def test_result_is_frozen(self):
        result = OverrideResult(
            outcome=OverrideOutcome.NO_CONFLICT,
            field="x", internal_value=1, external_value=1,
            resolved_value=1, authority_id="test",
            authority_tier="test", override_reason="test",
        )
        with self.assertRaises(AttributeError):
            result.outcome = "BLOCKED"  # type: ignore


class TestOverrideResultToDict(unittest.TestCase):
    """Serialization must produce complete dicts."""

    def test_has_all_fields(self):
        result = OverrideResult(
            outcome=OverrideOutcome.ACCEPTED,
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.55,
            resolved_value=0.55,
            authority_id="AUTH_BIS",
            authority_tier="TIER_1_PRIMARY",
            override_reason="BIS primary.",
            warnings=("Warning 1",),
        )
        d = override_result_to_dict(result)
        self.assertEqual(d["outcome"], "ACCEPTED")
        self.assertEqual(d["field"], "axis_1_score")
        self.assertEqual(d["warnings"], ["Warning 1"])


class TestEvaluateEpistemicOverride(unittest.TestCase):
    """Core override evaluation must follow tier hierarchy."""

    def test_tier_1_override_accepted(self):
        """Tier 1 (primary) authority MUST override internal computation."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.55,
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.55)
        self.assertEqual(result.authority_tier, "TIER_1_PRIMARY")

    def test_tier_2_override_restricted(self):
        """Tier 2 (authoritative) authority restricts to conservative."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.55,
            authority_id="AUTH_IMF",
        )
        self.assertEqual(result.outcome, OverrideOutcome.RESTRICTED)
        # Conservative = higher value (more concentrated)
        self.assertEqual(result.resolved_value, 0.55)

    def test_tier_3_override_flagged(self):
        """Tier 3 (supporting) authority flags but does not override."""
        # UNCTAD is Tier 2 in our registry; no Tier 3 authorities yet.
        # Test with unknown authority (which is flagged).
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.55,
            authority_id="AUTH_UNKNOWN",
        )
        self.assertEqual(result.outcome, OverrideOutcome.FLAGGED)
        self.assertEqual(result.resolved_value, 0.42)  # Internal retained

    def test_agreement_no_conflict(self):
        """When values agree, no override needed."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.42,
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.NO_CONFLICT)

    def test_near_agreement_no_conflict(self):
        """Within tolerance = no conflict."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.420,
            external_value=0.425,
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.NO_CONFLICT)

    def test_eurostat_tier_1_override(self):
        """Eurostat is Tier 1 — must override."""
        result = evaluate_epistemic_override(
            field="axis_2_score",
            internal_value=0.30,
            external_value=0.50,
            authority_id="AUTH_EUROSTAT",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.50)

    def test_override_has_warnings(self):
        """All overrides except NO_CONFLICT should have warnings."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.42,
            external_value=0.55,
            authority_id="AUTH_BIS",
        )
        self.assertGreater(len(result.warnings), 0)

    def test_boolean_tier_1_override(self):
        """Tier 1 overrides boolean values too."""
        result = evaluate_epistemic_override(
            field="ranking_eligible",
            internal_value=True,
            external_value=False,
            authority_id="AUTH_EUROSTAT",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, False)

    def test_string_tier_2_restriction(self):
        """Tier 2 restricts to more conservative tier."""
        result = evaluate_epistemic_override(
            field="governance_tier",
            internal_value="FULLY_COMPARABLE",
            external_value="LOW_CONFIDENCE",
            authority_id="AUTH_SIPRI",
        )
        self.assertEqual(result.outcome, OverrideOutcome.RESTRICTED)
        # LOW_CONFIDENCE is more conservative than FULLY_COMPARABLE
        self.assertEqual(result.resolved_value, "LOW_CONFIDENCE")


class TestEvaluateBatchOverrides(unittest.TestCase):
    """Batch evaluation must process all claims."""

    def test_batch_processes_all(self):
        overrides = [
            {
                "field": "axis_1_score",
                "internal_value": 0.42,
                "external_value": 0.55,
                "authority_id": "AUTH_BIS",
            },
            {
                "field": "axis_2_score",
                "internal_value": 0.30,
                "external_value": 0.30,
                "authority_id": "AUTH_IEA",
            },
        ]
        results = evaluate_batch_overrides(overrides)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(results[1].outcome, OverrideOutcome.NO_CONFLICT)

    def test_empty_batch(self):
        results = evaluate_batch_overrides([])
        self.assertEqual(len(results), 0)


class TestComputeOverrideSummary(unittest.TestCase):
    """Summary must aggregate results correctly."""

    def test_summary_counts(self):
        results = [
            OverrideResult(
                outcome=OverrideOutcome.ACCEPTED,
                field="x", internal_value=1, external_value=2,
                resolved_value=2, authority_id="A",
                authority_tier="TIER_1_PRIMARY",
                override_reason="test",
                warnings=("w1",),
            ),
            OverrideResult(
                outcome=OverrideOutcome.NO_CONFLICT,
                field="y", internal_value=1, external_value=1,
                resolved_value=1, authority_id="B",
                authority_tier="TIER_1_PRIMARY",
                override_reason="test",
            ),
            OverrideResult(
                outcome=OverrideOutcome.RESTRICTED,
                field="z", internal_value=1, external_value=3,
                resolved_value=3, authority_id="C",
                authority_tier="TIER_2_AUTHORITATIVE",
                override_reason="test",
                warnings=("w2",),
            ),
        ]
        summary = compute_override_summary(results)
        self.assertEqual(summary["n_overrides"], 3)
        self.assertEqual(summary["n_accepted"], 1)
        self.assertEqual(summary["n_restricted"], 1)
        self.assertEqual(summary["n_no_conflict"], 1)
        self.assertFalse(summary["has_blocking"])
        self.assertEqual(summary["n_warnings"], 2)

    def test_blocking_detected(self):
        results = [
            OverrideResult(
                outcome=OverrideOutcome.BLOCKED,
                field="x", internal_value=1, external_value=2,
                resolved_value=None, authority_id="A",
                authority_tier="TIER_1_PRIMARY",
                override_reason="blocked",
            ),
        ]
        summary = compute_override_summary(results)
        self.assertTrue(summary["has_blocking"])
        self.assertEqual(summary["n_blocked"], 1)

    def test_empty_summary(self):
        summary = compute_override_summary([])
        self.assertEqual(summary["n_overrides"], 0)
        self.assertFalse(summary["has_blocking"])

    def test_summary_has_honesty_note(self):
        summary = compute_override_summary([])
        self.assertIn("honesty_note", summary)


class TestExternalAuthorityMustOverride(unittest.TestCase):
    """CRITICAL: External authority must ALWAYS override internal computation.

    This is the core contract: "External authority outranks internal elegance."
    """

    def test_bis_overrides_axis_1(self):
        """BIS MUST override ISI Axis 1 computation."""
        result = evaluate_epistemic_override(
            field="axis_1_score",
            internal_value=0.20,
            external_value=0.80,
            authority_id="AUTH_BIS",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.80)
        # Internal value must NOT be the resolved value
        self.assertNotEqual(result.resolved_value, 0.20)

    def test_iea_overrides_axis_2(self):
        """IEA MUST override ISI Axis 2 computation."""
        result = evaluate_epistemic_override(
            field="axis_2_score",
            internal_value=0.10,
            external_value=0.90,
            authority_id="AUTH_IEA",
        )
        self.assertEqual(result.outcome, OverrideOutcome.ACCEPTED)
        self.assertEqual(result.resolved_value, 0.90)

    def test_eurostat_overrides_any_axis(self):
        """Eurostat (Tier 1, all axes) MUST override."""
        for axis in range(1, 7):
            result = evaluate_epistemic_override(
                field=f"axis_{axis}_score",
                internal_value=0.15,
                external_value=0.85,
                authority_id="AUTH_EUROSTAT",
            )
            self.assertEqual(
                result.outcome, OverrideOutcome.ACCEPTED,
                f"Eurostat failed to override axis {axis}",
            )


if __name__ == "__main__":
    unittest.main()
