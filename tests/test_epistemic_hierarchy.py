"""
tests/test_epistemic_hierarchy.py — Tests for Epistemic Hierarchy Model (Section 1)
"""

from __future__ import annotations

import unittest

from backend.epistemic_hierarchy import (
    EPISTEMIC_DESCRIPTIONS,
    EPISTEMIC_ORDER,
    EpistemicClaim,
    EpistemicLevel,
    VALID_EPISTEMIC_LEVELS,
    build_claim,
    claim_to_dict,
    epistemic_authority,
    get_hierarchy,
    outranks,
    resolve_conflict,
)


class TestEpistemicLevel(unittest.TestCase):
    """Epistemic levels must be formally defined and ordered."""

    def test_all_levels_defined(self):
        expected = {
            "EXTERNAL_AUTHORITY",
            "STRUCTURAL_BENCHMARK",
            "INTERNAL_GOVERNANCE",
            "INTERNAL_COMPUTATION",
            "DERIVED_INFERENCE",
        }
        self.assertEqual(VALID_EPISTEMIC_LEVELS, expected)

    def test_order_is_strict(self):
        """Lower index = higher authority."""
        self.assertEqual(EPISTEMIC_ORDER[EpistemicLevel.EXTERNAL_AUTHORITY], 0)
        self.assertEqual(EPISTEMIC_ORDER[EpistemicLevel.STRUCTURAL_BENCHMARK], 1)
        self.assertEqual(EPISTEMIC_ORDER[EpistemicLevel.INTERNAL_GOVERNANCE], 2)
        self.assertEqual(EPISTEMIC_ORDER[EpistemicLevel.INTERNAL_COMPUTATION], 3)
        self.assertEqual(EPISTEMIC_ORDER[EpistemicLevel.DERIVED_INFERENCE], 4)

    def test_exactly_five_levels(self):
        self.assertEqual(len(VALID_EPISTEMIC_LEVELS), 5)

    def test_all_levels_have_descriptions(self):
        for level in VALID_EPISTEMIC_LEVELS:
            self.assertIn(level, EPISTEMIC_DESCRIPTIONS)
            self.assertGreater(len(EPISTEMIC_DESCRIPTIONS[level]), 20)


class TestEpistemicAuthority(unittest.TestCase):
    """Authority ranking function must be consistent."""

    def test_external_authority_highest(self):
        self.assertEqual(epistemic_authority(EpistemicLevel.EXTERNAL_AUTHORITY), 0)

    def test_derived_inference_lowest(self):
        self.assertEqual(epistemic_authority(EpistemicLevel.DERIVED_INFERENCE), 4)

    def test_unknown_level_returns_999(self):
        self.assertEqual(epistemic_authority("BOGUS"), 999)

    def test_ordering_consistency(self):
        levels = list(EPISTEMIC_ORDER.keys())
        for i in range(len(levels)):
            for j in range(i + 1, len(levels)):
                self.assertLess(
                    epistemic_authority(levels[i]),
                    epistemic_authority(levels[j]),
                )


class TestOutranks(unittest.TestCase):
    """outranks() must correctly compare epistemic levels."""

    def test_external_outranks_internal(self):
        self.assertTrue(outranks(
            EpistemicLevel.EXTERNAL_AUTHORITY,
            EpistemicLevel.INTERNAL_COMPUTATION,
        ))

    def test_internal_does_not_outrank_external(self):
        self.assertFalse(outranks(
            EpistemicLevel.INTERNAL_COMPUTATION,
            EpistemicLevel.EXTERNAL_AUTHORITY,
        ))

    def test_same_level_does_not_outrank(self):
        self.assertFalse(outranks(
            EpistemicLevel.INTERNAL_GOVERNANCE,
            EpistemicLevel.INTERNAL_GOVERNANCE,
        ))

    def test_structural_outranks_governance(self):
        self.assertTrue(outranks(
            EpistemicLevel.STRUCTURAL_BENCHMARK,
            EpistemicLevel.INTERNAL_GOVERNANCE,
        ))

    def test_governance_outranks_computation(self):
        self.assertTrue(outranks(
            EpistemicLevel.INTERNAL_GOVERNANCE,
            EpistemicLevel.INTERNAL_COMPUTATION,
        ))

    def test_computation_outranks_inference(self):
        self.assertTrue(outranks(
            EpistemicLevel.INTERNAL_COMPUTATION,
            EpistemicLevel.DERIVED_INFERENCE,
        ))


class TestEpistemicClaim(unittest.TestCase):
    """EpistemicClaim must validate inputs and be frozen."""

    def test_valid_claim(self):
        claim = EpistemicClaim(
            field="governance_tier",
            value="FULLY_COMPARABLE",
            level=EpistemicLevel.INTERNAL_GOVERNANCE,
            source="ISI Governance Engine",
            source_id="isi_governance",
        )
        self.assertEqual(claim.field, "governance_tier")
        self.assertEqual(claim.level, EpistemicLevel.INTERNAL_GOVERNANCE)

    def test_invalid_level_raises(self):
        with self.assertRaises(ValueError):
            EpistemicClaim(
                field="x", value="y", level="BOGUS",
                source="test", source_id="test",
            )

    def test_invalid_confidence_raises(self):
        with self.assertRaises(ValueError):
            EpistemicClaim(
                field="x", value="y",
                level=EpistemicLevel.INTERNAL_COMPUTATION,
                source="test", source_id="test",
                confidence=1.5,
            )

    def test_negative_confidence_raises(self):
        with self.assertRaises(ValueError):
            EpistemicClaim(
                field="x", value="y",
                level=EpistemicLevel.INTERNAL_COMPUTATION,
                source="test", source_id="test",
                confidence=-0.1,
            )

    def test_claim_is_frozen(self):
        claim = build_claim(
            field="x", value="y",
            level=EpistemicLevel.INTERNAL_COMPUTATION,
            source="test",
        )
        with self.assertRaises(AttributeError):
            claim.value = "z"  # type: ignore


class TestBuildClaim(unittest.TestCase):
    """build_claim factory must produce valid claims."""

    def test_basic_claim(self):
        claim = build_claim(
            field="axis_1_score",
            value=0.42,
            level=EpistemicLevel.INTERNAL_COMPUTATION,
            source="ISI Pipeline",
        )
        self.assertEqual(claim.field, "axis_1_score")
        self.assertEqual(claim.value, 0.42)
        self.assertEqual(claim.source_id, "isi_pipeline")

    def test_explicit_source_id(self):
        claim = build_claim(
            field="x", value="y",
            level=EpistemicLevel.EXTERNAL_AUTHORITY,
            source="BIS",
            source_id="auth_bis",
        )
        self.assertEqual(claim.source_id, "auth_bis")

    def test_with_confidence(self):
        claim = build_claim(
            field="x", value="y",
            level=EpistemicLevel.EXTERNAL_AUTHORITY,
            source="BIS",
            confidence=0.95,
        )
        self.assertEqual(claim.confidence, 0.95)


class TestClaimToDict(unittest.TestCase):
    """claim_to_dict must produce JSON-safe dicts."""

    def test_serialization(self):
        claim = build_claim(
            field="governance_tier",
            value="FULLY_COMPARABLE",
            level=EpistemicLevel.INTERNAL_GOVERNANCE,
            source="ISI Governance",
            confidence=0.85,
            justification="Data quality assessment passed.",
        )
        d = claim_to_dict(claim)
        self.assertEqual(d["field"], "governance_tier")
        self.assertEqual(d["value"], "FULLY_COMPARABLE")
        self.assertEqual(d["level"], EpistemicLevel.INTERNAL_GOVERNANCE)
        self.assertEqual(d["authority_rank"], 2)
        self.assertEqual(d["confidence"], 0.85)

    def test_authority_rank_included(self):
        claim = build_claim(
            field="x", value="y",
            level=EpistemicLevel.EXTERNAL_AUTHORITY,
            source="BIS",
        )
        d = claim_to_dict(claim)
        self.assertEqual(d["authority_rank"], 0)


class TestResolveConflict(unittest.TestCase):
    """resolve_conflict must pick higher authority."""

    def test_external_beats_internal(self):
        claim_ext = build_claim(
            field="axis_1_score", value=0.55,
            level=EpistemicLevel.EXTERNAL_AUTHORITY,
            source="BIS",
        )
        claim_int = build_claim(
            field="axis_1_score", value=0.42,
            level=EpistemicLevel.INTERNAL_COMPUTATION,
            source="ISI Pipeline",
        )
        winner, loser, reason = resolve_conflict(claim_ext, claim_int)
        self.assertEqual(winner.value, 0.55)
        self.assertEqual(loser.value, 0.42)
        self.assertIn("outranks", reason)

    def test_governance_beats_inference(self):
        claim_gov = build_claim(
            field="ranking_eligible", value=False,
            level=EpistemicLevel.INTERNAL_GOVERNANCE,
            source="Governance Engine",
        )
        claim_inf = build_claim(
            field="ranking_eligible", value=True,
            level=EpistemicLevel.DERIVED_INFERENCE,
            source="Ranking Algorithm",
        )
        winner, _, _ = resolve_conflict(claim_gov, claim_inf)
        self.assertEqual(winner.value, False)

    def test_same_level_returns_first(self):
        claim_a = build_claim(
            field="x", value="A",
            level=EpistemicLevel.INTERNAL_COMPUTATION,
            source="Module A",
        )
        claim_b = build_claim(
            field="x", value="B",
            level=EpistemicLevel.INTERNAL_COMPUTATION,
            source="Module B",
        )
        winner, _, reason = resolve_conflict(claim_a, claim_b)
        self.assertEqual(winner.value, "A")
        self.assertIn("same level", reason.lower())


class TestGetHierarchy(unittest.TestCase):
    """get_hierarchy must return the full hierarchy for documentation."""

    def test_returns_list(self):
        h = get_hierarchy()
        self.assertIsInstance(h, list)
        self.assertEqual(len(h), 5)

    def test_ordered_by_authority(self):
        h = get_hierarchy()
        ranks = [entry["authority_rank"] for entry in h]
        self.assertEqual(ranks, sorted(ranks))

    def test_first_is_external_authority(self):
        h = get_hierarchy()
        self.assertEqual(h[0]["level"], EpistemicLevel.EXTERNAL_AUTHORITY)

    def test_last_is_derived_inference(self):
        h = get_hierarchy()
        self.assertEqual(h[-1]["level"], EpistemicLevel.DERIVED_INFERENCE)


if __name__ == "__main__":
    unittest.main()
