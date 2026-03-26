"""
tests.test_override_strength — Tests for Override Strength Model

Verifies:
    - OverrideStrength classification is correct.
    - CONTEXTUAL override (Tier 3 flag) ≠ DECISIVE.
    - Overriding contradiction ≥ STRONG.
    - Mixed strong authorities → cannot upgrade.
    - OverridePressure correctly aggregates.
    - compute_override_pressure() returns correct caps.
"""

from __future__ import annotations

import pytest

from backend.epistemic_override import (
    OverrideOutcome,
    OverridePressure,
    OverrideResult,
    OverrideStrength,
    OVERRIDE_STRENGTH_ORDER,
    VALID_OVERRIDE_STRENGTHS,
    classify_override_strength,
    compute_override_pressure,
    override_pressure_to_dict,
)
from backend.external_authority_registry import AuthorityTier


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _make_result(
    outcome: str = OverrideOutcome.NO_CONFLICT,
    tier: str = AuthorityTier.TIER_3_SUPPORTING,
    authority_id: str = "test_auth",
) -> OverrideResult:
    """Create an OverrideResult for testing."""
    return OverrideResult(
        outcome=outcome,
        field="test_field",
        internal_value=1.0,
        external_value=2.0,
        resolved_value=1.0,
        authority_id=authority_id,
        authority_tier=tier,
        override_reason="Test reason.",
    )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: STRENGTH CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestOverrideStrengthClassification:
    """OverrideStrength classification must follow documented rules."""

    def test_all_strengths_are_valid(self):
        assert len(VALID_OVERRIDE_STRENGTHS) == 5

    def test_strength_ordering(self):
        assert OVERRIDE_STRENGTH_ORDER[OverrideStrength.NONE] < OVERRIDE_STRENGTH_ORDER[OverrideStrength.WEAK]
        assert OVERRIDE_STRENGTH_ORDER[OverrideStrength.WEAK] < OVERRIDE_STRENGTH_ORDER[OverrideStrength.MODERATE]
        assert OVERRIDE_STRENGTH_ORDER[OverrideStrength.MODERATE] < OVERRIDE_STRENGTH_ORDER[OverrideStrength.STRONG]
        assert OVERRIDE_STRENGTH_ORDER[OverrideStrength.STRONG] < OVERRIDE_STRENGTH_ORDER[OverrideStrength.DECISIVE]

    def test_no_conflict_is_none(self):
        r = _make_result(outcome=OverrideOutcome.NO_CONFLICT)
        assert classify_override_strength(r) == OverrideStrength.NONE

    def test_blocked_is_decisive(self):
        r = _make_result(outcome=OverrideOutcome.BLOCKED)
        assert classify_override_strength(r) == OverrideStrength.DECISIVE

    def test_contextual_tier3_flag_is_weak_not_decisive(self):
        """Tier 3 flag (CONTEXTUAL) ≠ DECISIVE."""
        r = _make_result(
            outcome=OverrideOutcome.FLAGGED,
            tier=AuthorityTier.TIER_3_SUPPORTING,
        )
        strength = classify_override_strength(r)
        assert strength == OverrideStrength.WEAK
        assert strength != OverrideStrength.DECISIVE

    def test_tier1_accepted_is_strong(self):
        r = _make_result(
            outcome=OverrideOutcome.ACCEPTED,
            tier=AuthorityTier.TIER_1_PRIMARY,
        )
        assert classify_override_strength(r) == OverrideStrength.STRONG

    def test_tier2_restricted_is_strong(self):
        r = _make_result(
            outcome=OverrideOutcome.RESTRICTED,
            tier=AuthorityTier.TIER_2_AUTHORITATIVE,
        )
        assert classify_override_strength(r) == OverrideStrength.STRONG

    def test_tier2_flagged_is_moderate(self):
        r = _make_result(
            outcome=OverrideOutcome.FLAGGED,
            tier=AuthorityTier.TIER_2_AUTHORITATIVE,
        )
        assert classify_override_strength(r) == OverrideStrength.MODERATE

    def test_overriding_contradiction_at_least_strong(self):
        """Overriding a contradiction should be at least STRONG."""
        r = _make_result(
            outcome=OverrideOutcome.RESTRICTED,
            tier=AuthorityTier.TIER_1_PRIMARY,
        )
        strength = classify_override_strength(r)
        assert OVERRIDE_STRENGTH_ORDER[strength] >= OVERRIDE_STRENGTH_ORDER[OverrideStrength.STRONG]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: OVERRIDE PRESSURE
# ═══════════════════════════════════════════════════════════════════════════

class TestOverridePressure:
    """OverridePressure must correctly aggregate override results."""

    def test_no_results_gives_none_pressure(self):
        pressure = compute_override_pressure([])
        assert pressure.max_strength == OverrideStrength.NONE
        assert pressure.confidence_cap == 1.0
        assert pressure.can_rank is True
        assert pressure.can_compare is True

    def test_decisive_blocks_ranking_and_comparison(self):
        r = _make_result(outcome=OverrideOutcome.BLOCKED)
        pressure = compute_override_pressure([r])
        assert pressure.max_strength == OverrideStrength.DECISIVE
        assert pressure.can_rank is False
        assert pressure.can_compare is False
        assert pressure.confidence_cap == 0.0

    def test_strong_caps_confidence_at_06(self):
        r = _make_result(
            outcome=OverrideOutcome.ACCEPTED,
            tier=AuthorityTier.TIER_1_PRIMARY,
        )
        pressure = compute_override_pressure([r])
        assert pressure.max_strength == OverrideStrength.STRONG
        assert pressure.confidence_cap == 0.6

    def test_mixed_strong_authorities_extra_restriction(self):
        """Multiple strong/decisive overrides → cannot upgrade, extra cap."""
        r1 = _make_result(
            outcome=OverrideOutcome.ACCEPTED,
            tier=AuthorityTier.TIER_1_PRIMARY,
            authority_id="auth1",
        )
        r2 = _make_result(
            outcome=OverrideOutcome.RESTRICTED,
            tier=AuthorityTier.TIER_1_PRIMARY,
            authority_id="auth2",
        )
        pressure = compute_override_pressure([r1, r2])
        assert pressure.n_strong_or_decisive == 2
        assert pressure.confidence_cap <= 0.5

    def test_moderate_requires_caveats(self):
        r = _make_result(
            outcome=OverrideOutcome.FLAGGED,
            tier=AuthorityTier.TIER_2_AUTHORITATIVE,
        )
        pressure = compute_override_pressure([r])
        assert pressure.requires_caveats is True

    def test_weak_does_not_require_caveats(self):
        r = _make_result(
            outcome=OverrideOutcome.FLAGGED,
            tier=AuthorityTier.TIER_3_SUPPORTING,
        )
        pressure = compute_override_pressure([r])
        assert pressure.requires_caveats is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: OVERRIDE PRESSURE DATACLASS
# ═══════════════════════════════════════════════════════════════════════════

class TestOverridePressureDataclass:
    """OverridePressure frozen dataclass integrity."""

    def test_frozen(self):
        p = compute_override_pressure([])
        with pytest.raises(AttributeError):
            p.max_strength = "NONE"  # type: ignore[misc]

    def test_invalid_strength_raises(self):
        with pytest.raises(ValueError, match="Invalid override strength"):
            OverridePressure(
                max_strength="INVALID_STRENGTH",
                n_overrides=0,
                n_strong_or_decisive=0,
                confidence_cap=1.0,
                can_rank=True,
                can_compare=True,
                requires_caveats=False,
                pressure_reasons=(),
            )

    def test_serialization(self):
        p = compute_override_pressure([])
        d = override_pressure_to_dict(p)
        assert isinstance(d, dict)
        assert d["max_strength"] == OverrideStrength.NONE
        assert isinstance(d["pressure_reasons"], list)
