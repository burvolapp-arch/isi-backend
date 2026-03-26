"""
tests.test_epistemic_bounds — Tests for Epistemic Bounds Propagation

Verifies:
    - EpistemicBounds is immutable (frozen dataclass).
    - merge_bounds() always returns bounds ≤ both inputs.
    - tighten_bounds() never loosens any dimension.
    - bounds_are_tighter_or_equal() correctly validates.
    - detect_bounds_violations() catches all expansion attempts.
    - bounds_from_truth_result() maps truth → bounds correctly.
    - bounds_from_scope_result() maps scope → bounds correctly.
"""

from __future__ import annotations

import pytest

from backend.epistemic_bounds import (
    EpistemicBounds,
    bounds_are_tighter_or_equal,
    bounds_from_scope_result,
    bounds_from_truth_result,
    bounds_to_dict,
    detect_bounds_violations,
    merge_bounds,
    tighten_bounds,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: IMMUTABILITY
# ═══════════════════════════════════════════════════════════════════════════

class TestEpistemicBoundsImmutability:
    """EpistemicBounds must be immutable."""

    def test_frozen_dataclass(self):
        b = EpistemicBounds()
        with pytest.raises(AttributeError):
            b.max_confidence = 0.5  # type: ignore[misc]

    def test_default_bounds_are_fully_permissive(self):
        b = EpistemicBounds()
        assert b.max_confidence == 1.0
        assert b.max_publishability == "PUBLISHABLE"
        assert b.can_rank is True
        assert b.can_compare is True
        assert b.can_publish_policy_claim is True
        assert b.can_publish_composite is True
        assert b.can_publish_country_ordering is True
        assert b.required_warnings == ()
        assert b.binding_constraints == ()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: MERGE BOUNDS — ALWAYS TIGHTER
# ═══════════════════════════════════════════════════════════════════════════

class TestMergeBounds:
    """merge_bounds() must always return tighter-or-equal bounds."""

    def test_merge_identical_bounds(self):
        a = EpistemicBounds(max_confidence=0.8)
        result = merge_bounds(a, a)
        assert result.max_confidence == 0.8

    def test_merge_takes_lower_confidence(self):
        a = EpistemicBounds(max_confidence=0.8)
        b = EpistemicBounds(max_confidence=0.5)
        result = merge_bounds(a, b)
        assert result.max_confidence == 0.5

    def test_merge_takes_more_restrictive_publishability(self):
        a = EpistemicBounds(max_publishability="PUBLISHABLE")
        b = EpistemicBounds(max_publishability="RESTRICTED")
        result = merge_bounds(a, b)
        assert result.max_publishability == "RESTRICTED"

    def test_merge_disables_ranking_if_either_disables(self):
        a = EpistemicBounds(can_rank=True)
        b = EpistemicBounds(can_rank=False)
        result = merge_bounds(a, b)
        assert result.can_rank is False

    def test_merge_disables_comparison_if_either_disables(self):
        a = EpistemicBounds(can_compare=False)
        b = EpistemicBounds(can_compare=True)
        result = merge_bounds(a, b)
        assert result.can_compare is False

    def test_merge_accumulates_warnings(self):
        a = EpistemicBounds(required_warnings=("warn1",))
        b = EpistemicBounds(required_warnings=("warn2",))
        result = merge_bounds(a, b)
        assert "warn1" in result.required_warnings
        assert "warn2" in result.required_warnings

    def test_merge_accumulates_constraints(self):
        a = EpistemicBounds(binding_constraints=("c1",))
        b = EpistemicBounds(binding_constraints=("c2",))
        result = merge_bounds(a, b)
        assert "c1" in result.binding_constraints
        assert "c2" in result.binding_constraints

    def test_merge_result_is_tighter_than_both(self):
        a = EpistemicBounds(
            max_confidence=0.8,
            can_rank=True,
            can_compare=False,
            max_publishability="PUBLISHABLE_WITH_CAVEATS",
        )
        b = EpistemicBounds(
            max_confidence=0.6,
            can_rank=False,
            can_compare=True,
            max_publishability="PUBLISHABLE",
        )
        result = merge_bounds(a, b)
        assert bounds_are_tighter_or_equal(result, a)
        assert bounds_are_tighter_or_equal(result, b)

    def test_merge_with_default_is_identity_like(self):
        specific = EpistemicBounds(max_confidence=0.5, can_rank=False)
        default = EpistemicBounds()
        result = merge_bounds(specific, default)
        assert result.max_confidence == 0.5
        assert result.can_rank is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: TIGHTEN BOUNDS — NEVER LOOSENS
# ═══════════════════════════════════════════════════════════════════════════

class TestTightenBounds:
    """tighten_bounds() must never loosen any dimension."""

    def test_tighten_confidence_lower(self):
        base = EpistemicBounds(max_confidence=0.8)
        result = tighten_bounds(base, max_confidence=0.5)
        assert result.max_confidence == 0.5

    def test_tighten_confidence_cannot_raise(self):
        base = EpistemicBounds(max_confidence=0.5)
        result = tighten_bounds(base, max_confidence=0.9)
        assert result.max_confidence == 0.5

    def test_tighten_ranking_cannot_reenable(self):
        base = EpistemicBounds(can_rank=False)
        result = tighten_bounds(base, can_rank=True)
        assert result.can_rank is False

    def test_tighten_adds_warnings(self):
        base = EpistemicBounds(required_warnings=("existing",))
        result = tighten_bounds(base, add_warnings=("new_warning",))
        assert "existing" in result.required_warnings
        assert "new_warning" in result.required_warnings

    def test_tighten_publishability(self):
        base = EpistemicBounds(max_publishability="PUBLISHABLE")
        result = tighten_bounds(base, max_publishability="NOT_PUBLISHABLE")
        assert result.max_publishability == "NOT_PUBLISHABLE"

    def test_tighten_publishability_cannot_upgrade(self):
        base = EpistemicBounds(max_publishability="NOT_PUBLISHABLE")
        result = tighten_bounds(base, max_publishability="PUBLISHABLE")
        assert result.max_publishability == "NOT_PUBLISHABLE"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: BOUNDS VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundsValidation:
    """bounds_are_tighter_or_equal() must catch all expansions."""

    def test_equal_bounds_pass(self):
        a = EpistemicBounds(max_confidence=0.5)
        assert bounds_are_tighter_or_equal(a, a) is True

    def test_tighter_confidence_passes(self):
        child = EpistemicBounds(max_confidence=0.3)
        parent = EpistemicBounds(max_confidence=0.5)
        assert bounds_are_tighter_or_equal(child, parent) is True

    def test_expanded_confidence_fails(self):
        child = EpistemicBounds(max_confidence=0.8)
        parent = EpistemicBounds(max_confidence=0.5)
        assert bounds_are_tighter_or_equal(child, parent) is False

    def test_ranking_reenabledails(self):
        child = EpistemicBounds(can_rank=True)
        parent = EpistemicBounds(can_rank=False)
        assert bounds_are_tighter_or_equal(child, parent) is False

    def test_missing_warnings_fails(self):
        child = EpistemicBounds(required_warnings=())
        parent = EpistemicBounds(required_warnings=("must_keep",))
        assert bounds_are_tighter_or_equal(child, parent) is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: VIOLATION DETECTION
# ═══════════════════════════════════════════════════════════════════════════

class TestDetectBoundsViolations:
    """detect_bounds_violations() must find all expansion attempts."""

    def test_no_violations_when_equal(self):
        b = EpistemicBounds()
        violations = detect_bounds_violations(b, b)
        assert len(violations) == 0

    def test_confidence_expansion_detected(self):
        child = EpistemicBounds(max_confidence=0.9)
        parent = EpistemicBounds(max_confidence=0.5)
        violations = detect_bounds_violations(child, parent)
        assert any(v["dimension"] == "max_confidence" for v in violations)

    def test_publishability_expansion_detected(self):
        child = EpistemicBounds(max_publishability="PUBLISHABLE")
        parent = EpistemicBounds(max_publishability="RESTRICTED")
        violations = detect_bounds_violations(child, parent)
        assert any(v["dimension"] == "max_publishability" for v in violations)

    def test_boolean_expansion_detected(self):
        child = EpistemicBounds(can_rank=True)
        parent = EpistemicBounds(can_rank=False)
        violations = detect_bounds_violations(child, parent)
        assert any(v["dimension"] == "can_rank" for v in violations)

    def test_dropped_warnings_detected(self):
        child = EpistemicBounds(required_warnings=())
        parent = EpistemicBounds(required_warnings=("must_keep",))
        violations = detect_bounds_violations(child, parent)
        assert any(v["dimension"] == "required_warnings" for v in violations)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: BOUNDS FROM TRUTH RESULT
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundsFromTruth:
    """bounds_from_truth_result() must correctly map truth → bounds."""

    def test_valid_truth_gives_full_bounds(self):
        truth = {"truth_status": "VALID", "final_ranking_eligible": True}
        bounds = bounds_from_truth_result(truth)
        assert bounds.max_confidence == 1.0
        assert bounds.can_rank is True

    def test_invalid_truth_blocks_everything(self):
        truth = {"truth_status": "INVALID"}
        bounds = bounds_from_truth_result(truth)
        assert bounds.max_confidence == 0.0
        assert bounds.can_rank is False
        assert bounds.can_compare is False
        assert bounds.max_publishability == "NOT_PUBLISHABLE"

    def test_export_blocked_blocks_everything(self):
        truth = {"export_blocked": True}
        bounds = bounds_from_truth_result(truth)
        assert bounds.max_confidence == 0.0
        assert bounds.max_publishability == "NOT_PUBLISHABLE"

    def test_degraded_truth_caps_confidence(self):
        truth = {"truth_status": "DEGRADED", "n_conflicts": 2}
        bounds = bounds_from_truth_result(truth)
        assert bounds.max_confidence <= 0.7

    def test_non_comparable_tier_caps_confidence(self):
        truth = {
            "truth_status": "VALID",
            "final_governance_tier": "NON_COMPARABLE",
        }
        bounds = bounds_from_truth_result(truth)
        assert bounds.max_confidence <= 0.3


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: BOUNDS FROM SCOPE
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundsFromScope:
    """bounds_from_scope_result() must correctly map scope → bounds."""

    def test_full_scope_gives_full_bounds(self):
        scope = {"scope_level": "FULL"}
        bounds = bounds_from_scope_result(scope)
        assert bounds.max_confidence == 1.0
        assert bounds.can_rank is True

    def test_blocked_scope_blocks_everything(self):
        scope = {"scope_level": "BLOCKED"}
        bounds = bounds_from_scope_result(scope)
        assert bounds.max_confidence == 0.0

    def test_suppressed_scope_blocks_everything(self):
        scope = {"scope_level": "SUPPRESSED"}
        bounds = bounds_from_scope_result(scope)
        assert bounds.max_confidence == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundsSerialization:
    """bounds_to_dict() must produce complete JSON-safe output."""

    def test_serializes_all_fields(self):
        b = EpistemicBounds(
            max_confidence=0.6,
            required_warnings=("w1",),
        )
        d = bounds_to_dict(b)
        assert d["max_confidence"] == 0.6
        assert d["required_warnings"] == ["w1"]
        assert isinstance(d["binding_constraints"], list)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: MONOTONICITY PROPERTY — bounds never expand downstream
# ═══════════════════════════════════════════════════════════════════════════

class TestBoundsMonotonicity:
    """Key property: repeated merging never expands bounds."""

    def test_chain_of_merges_never_expands(self):
        b1 = EpistemicBounds(max_confidence=0.9)
        b2 = EpistemicBounds(max_confidence=0.7)
        b3 = EpistemicBounds(max_confidence=0.5)

        result = merge_bounds(merge_bounds(b1, b2), b3)
        assert result.max_confidence == 0.5
        assert bounds_are_tighter_or_equal(result, b1)
        assert bounds_are_tighter_or_equal(result, b2)
        assert bounds_are_tighter_or_equal(result, b3)

    def test_merge_is_commutative(self):
        a = EpistemicBounds(max_confidence=0.8, can_rank=False)
        b = EpistemicBounds(max_confidence=0.6, can_compare=False)
        assert merge_bounds(a, b) == merge_bounds(b, a)

    def test_merge_is_idempotent(self):
        a = EpistemicBounds(max_confidence=0.5, can_rank=False)
        assert merge_bounds(a, a) == a
