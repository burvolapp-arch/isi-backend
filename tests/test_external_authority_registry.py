"""
tests/test_external_authority_registry.py — Tests for External Authority Registry (Section 2)
"""

from __future__ import annotations

import unittest

from backend.external_authority_registry import (
    AUTHORITY_TIER_DESCRIPTIONS,
    AUTHORITY_TIER_ORDER,
    AuthorityTier,
    EXTERNAL_AUTHORITY_REGISTRY,
    OverridePermission,
    VALID_AUTHORITY_TIERS,
    VALID_OVERRIDE_PERMISSIONS,
    authority_outranks,
    get_authorities_for_axis,
    get_authorities_with_permission,
    get_authority_by_id,
    get_registry_summary,
    get_tier_1_authorities,
)
from backend.epistemic_hierarchy import EpistemicLevel


class TestAuthorityTier(unittest.TestCase):
    """Authority tiers must be formally defined."""

    def test_exactly_three_tiers(self):
        self.assertEqual(len(VALID_AUTHORITY_TIERS), 3)

    def test_tier_order_strict(self):
        self.assertLess(
            AUTHORITY_TIER_ORDER[AuthorityTier.TIER_1_PRIMARY],
            AUTHORITY_TIER_ORDER[AuthorityTier.TIER_2_AUTHORITATIVE],
        )
        self.assertLess(
            AUTHORITY_TIER_ORDER[AuthorityTier.TIER_2_AUTHORITATIVE],
            AUTHORITY_TIER_ORDER[AuthorityTier.TIER_3_SUPPORTING],
        )

    def test_all_tiers_have_descriptions(self):
        for tier in VALID_AUTHORITY_TIERS:
            self.assertIn(tier, AUTHORITY_TIER_DESCRIPTIONS)


class TestOverridePermission(unittest.TestCase):
    """Override permissions must be formally defined."""

    def test_at_least_five_permissions(self):
        self.assertGreaterEqual(len(VALID_OVERRIDE_PERMISSIONS), 5)

    def test_ranking_permission_exists(self):
        self.assertIn(OverridePermission.RANKING, VALID_OVERRIDE_PERMISSIONS)

    def test_axis_score_permission_exists(self):
        self.assertIn(OverridePermission.AXIS_SCORE, VALID_OVERRIDE_PERMISSIONS)


class TestAuthorityRegistry(unittest.TestCase):
    """The authority registry must be populated and valid."""

    def test_registry_has_10_authorities(self):
        self.assertEqual(len(EXTERNAL_AUTHORITY_REGISTRY), 10)

    def test_all_authorities_have_required_fields(self):
        required = {
            "authority_id", "name", "organization", "tier",
            "relevant_axes", "override_permissions", "epistemic_level",
            "data_description", "coverage_scope",
            "why_authoritative", "conflict_resolution",
        }
        for auth in EXTERNAL_AUTHORITY_REGISTRY:
            for field in required:
                self.assertIn(field, auth, f"Missing {field} in {auth['authority_id']}")

    def test_all_authority_ids_unique(self):
        ids = [a["authority_id"] for a in EXTERNAL_AUTHORITY_REGISTRY]
        self.assertEqual(len(ids), len(set(ids)))

    def test_all_authority_tiers_valid(self):
        for auth in EXTERNAL_AUTHORITY_REGISTRY:
            self.assertIn(auth["tier"], VALID_AUTHORITY_TIERS)

    def test_all_epistemic_levels_correct(self):
        valid_levels = {
            EpistemicLevel.EXTERNAL_AUTHORITY,
            EpistemicLevel.STRUCTURAL_BENCHMARK,
        }
        for auth in EXTERNAL_AUTHORITY_REGISTRY:
            self.assertIn(auth["epistemic_level"], valid_levels)

    def test_all_override_permissions_valid(self):
        for auth in EXTERNAL_AUTHORITY_REGISTRY:
            for perm in auth["override_permissions"]:
                self.assertIn(perm, VALID_OVERRIDE_PERMISSIONS)

    def test_all_axes_in_range(self):
        for auth in EXTERNAL_AUTHORITY_REGISTRY:
            for ax in auth["relevant_axes"]:
                self.assertIn(ax, range(1, 7))


class TestSpecificAuthorities(unittest.TestCase):
    """Specific authority entries must have correct properties."""

    def test_bis_is_tier_1(self):
        bis = get_authority_by_id("AUTH_BIS")
        self.assertIsNotNone(bis)
        self.assertEqual(bis["tier"], AuthorityTier.TIER_1_PRIMARY)
        self.assertIn(1, bis["relevant_axes"])

    def test_iea_is_tier_1(self):
        iea = get_authority_by_id("AUTH_IEA")
        self.assertIsNotNone(iea)
        self.assertEqual(iea["tier"], AuthorityTier.TIER_1_PRIMARY)
        self.assertIn(2, iea["relevant_axes"])

    def test_eurostat_covers_all_axes(self):
        eurostat = get_authority_by_id("AUTH_EUROSTAT")
        self.assertIsNotNone(eurostat)
        self.assertEqual(eurostat["tier"], AuthorityTier.TIER_1_PRIMARY)
        self.assertEqual(sorted(eurostat["relevant_axes"]), [1, 2, 3, 4, 5, 6])

    def test_sipri_covers_axis_4(self):
        sipri = get_authority_by_id("AUTH_SIPRI")
        self.assertIsNotNone(sipri)
        self.assertEqual(sipri["tier"], AuthorityTier.TIER_2_AUTHORITATIVE)
        self.assertIn(4, sipri["relevant_axes"])

    def test_eu_crm_is_structural(self):
        eu_crm = get_authority_by_id("AUTH_EU_CRM")
        self.assertIsNotNone(eu_crm)
        self.assertEqual(eu_crm["epistemic_level"], EpistemicLevel.STRUCTURAL_BENCHMARK)

    def test_unknown_authority_returns_none(self):
        self.assertIsNone(get_authority_by_id("AUTH_NONEXISTENT"))


class TestGetAuthoritiesForAxis(unittest.TestCase):
    """Axis-based authority lookup must work correctly."""

    def test_axis_1_has_authorities(self):
        auths = get_authorities_for_axis(1)
        self.assertGreater(len(auths), 0)
        ids = [a["authority_id"] for a in auths]
        self.assertIn("AUTH_BIS", ids)
        self.assertIn("AUTH_EUROSTAT", ids)

    def test_axis_4_includes_sipri(self):
        auths = get_authorities_for_axis(4)
        ids = [a["authority_id"] for a in auths]
        self.assertIn("AUTH_SIPRI", ids)

    def test_axis_5_includes_usgs_and_eu_crm(self):
        auths = get_authorities_for_axis(5)
        ids = [a["authority_id"] for a in auths]
        self.assertIn("AUTH_USGS", ids)
        self.assertIn("AUTH_EU_CRM", ids)

    def test_every_axis_has_at_least_one_authority(self):
        for ax in range(1, 7):
            auths = get_authorities_for_axis(ax)
            self.assertGreater(
                len(auths), 0,
                f"Axis {ax} has no associated authorities.",
            )


class TestGetTier1Authorities(unittest.TestCase):
    """Tier 1 lookup must return only primaries."""

    def test_tier_1_includes_bis_iea_eurostat(self):
        tier_1 = get_tier_1_authorities()
        ids = [a["authority_id"] for a in tier_1]
        self.assertIn("AUTH_BIS", ids)
        self.assertIn("AUTH_IEA", ids)
        self.assertIn("AUTH_EUROSTAT", ids)

    def test_tier_1_excludes_tier_2(self):
        tier_1 = get_tier_1_authorities()
        for a in tier_1:
            self.assertEqual(a["tier"], AuthorityTier.TIER_1_PRIMARY)


class TestAuthorityOutranks(unittest.TestCase):
    """authority_outranks must compare tiers correctly."""

    def test_tier_1_outranks_tier_2(self):
        bis = get_authority_by_id("AUTH_BIS")
        imf = get_authority_by_id("AUTH_IMF")
        self.assertTrue(authority_outranks(bis, imf))

    def test_tier_2_does_not_outrank_tier_1(self):
        imf = get_authority_by_id("AUTH_IMF")
        bis = get_authority_by_id("AUTH_BIS")
        self.assertFalse(authority_outranks(imf, bis))

    def test_same_tier_does_not_outrank(self):
        imf = get_authority_by_id("AUTH_IMF")
        oecd = get_authority_by_id("AUTH_OECD")
        self.assertFalse(authority_outranks(imf, oecd))


class TestGetAuthoritiesWithPermission(unittest.TestCase):
    """Permission-based lookup must work."""

    def test_ranking_permission(self):
        auths = get_authorities_with_permission(OverridePermission.RANKING)
        self.assertGreater(len(auths), 0)

    def test_axis_score_permission(self):
        auths = get_authorities_with_permission(OverridePermission.AXIS_SCORE)
        self.assertGreater(len(auths), 0)
        ids = [a["authority_id"] for a in auths]
        self.assertIn("AUTH_BIS", ids)


class TestRegistrySummary(unittest.TestCase):
    """Registry summary must be complete."""

    def test_summary_has_required_fields(self):
        summary = get_registry_summary()
        self.assertIn("n_authorities", summary)
        self.assertIn("tier_counts", summary)
        self.assertIn("authorities", summary)

    def test_summary_counts_match(self):
        summary = get_registry_summary()
        self.assertEqual(summary["n_authorities"], 10)


if __name__ == "__main__":
    unittest.main()
