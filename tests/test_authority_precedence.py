"""
tests.test_authority_precedence — Tests for Authority Precedence Resolution

Verifies:
    - Single authority → trivially resolved.
    - Higher tier wins over lower tier.
    - Close margins → conservative bound applied.
    - Residual conflict detected and documented.
    - Multi-field resolution works.
    - Deterministic: same inputs → same winner.
"""

from __future__ import annotations

from backend.authority_precedence import (
    PrecedenceOutcome,
    VALID_PRECEDENCE_OUTCOMES,
    resolve_authority_precedence,
    resolve_multi_field_precedence,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: BASIC RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

class TestBasicPrecedence:
    """Basic authority precedence resolution."""

    def test_no_claims_is_unresolvable(self):
        result = resolve_authority_precedence([], field="test")
        assert result["outcome"] == PrecedenceOutcome.UNRESOLVABLE
        assert result["n_claims"] == 0

    def test_single_claim_is_resolved(self):
        claims = [{"authority_id": "AUTH_BIS", "value": 0.5}]
        result = resolve_authority_precedence(claims, field="score")
        assert result["outcome"] == PrecedenceOutcome.RESOLVED
        assert result["winning_authority"] == "AUTH_BIS"
        assert result["winning_value"] == 0.5

    def test_all_outcomes_are_valid(self):
        assert len(VALID_PRECEDENCE_OUTCOMES) == 3
        assert PrecedenceOutcome.RESOLVED in VALID_PRECEDENCE_OUTCOMES
        assert PrecedenceOutcome.CONSERVATIVE_BOUND in VALID_PRECEDENCE_OUTCOMES
        assert PrecedenceOutcome.UNRESOLVABLE in VALID_PRECEDENCE_OUTCOMES


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: TIER PRECEDENCE
# ═══════════════════════════════════════════════════════════════════════════

class TestTierPrecedence:
    """Higher tier should win over lower tier."""

    def test_tier1_beats_tier2(self):
        claims = [
            {
                "authority_id": "AUTH_BIS",
                "value": 0.4,
                "recency": 0.5,
                "domain_specificity": 0.5,
            },
            {
                "authority_id": "AUTH_UNCTAD",
                "value": 0.6,
                "recency": 0.5,
                "domain_specificity": 0.5,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        assert result["outcome"] == PrecedenceOutcome.RESOLVED
        assert result["winning_authority"] == "AUTH_BIS"

    def test_tier1_beats_tier2_imf(self):
        claims = [
            {
                "authority_id": "AUTH_BIS",
                "value": 0.4,
                "recency": 0.5,
            },
            {
                "authority_id": "AUTH_IMF",
                "value": 0.6,
                "recency": 0.5,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        assert result["outcome"] == PrecedenceOutcome.RESOLVED
        assert result["winning_authority"] == "AUTH_BIS"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: CONSERVATIVE BOUND
# ═══════════════════════════════════════════════════════════════════════════

class TestConservativeBound:
    """Close margins should trigger conservative bound."""

    def test_same_tier_close_dimensions_conservative(self):
        """Two authorities at same tier with same dimensions → conservative."""
        claims = [
            {
                "authority_id": "AUTH_BIS",
                "value": 0.4,
                "recency": 0.5,
                "domain_specificity": 0.5,
                "construct_validity": 0.5,
                "data_coverage": 0.5,
            },
            {
                "authority_id": "AUTH_EUROSTAT",
                "value": 0.6,
                "recency": 0.5,
                "domain_specificity": 0.5,
                "construct_validity": 0.5,
                "data_coverage": 0.5,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        # Both are Tier 1 with identical dimensions → margin < 0.05
        assert result["outcome"] == PrecedenceOutcome.CONSERVATIVE_BOUND
        assert result["conservative_bound_applied"] is True
        assert result["residual_conflict"] is True

    def test_conservative_value_for_numbers_is_max(self):
        """For numeric values, conservative = max (higher concentration = worse)."""
        claims = [
            {
                "authority_id": "AUTH_BIS",
                "value": 0.4,
                "recency": 0.5,
                "domain_specificity": 0.5,
                "construct_validity": 0.5,
                "data_coverage": 0.5,
            },
            {
                "authority_id": "AUTH_EUROSTAT",
                "value": 0.8,
                "recency": 0.5,
                "domain_specificity": 0.5,
                "construct_validity": 0.5,
                "data_coverage": 0.5,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        if result["outcome"] == PrecedenceOutcome.CONSERVATIVE_BOUND:
            assert result["conservative_value"] == 0.8


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: RESIDUAL CONFLICT
# ═══════════════════════════════════════════════════════════════════════════

class TestResidualConflict:
    """Residual conflicts must be detected and documented."""

    def test_no_residual_when_values_agree(self):
        claims = [
            {"authority_id": "AUTH_BIS", "value": 0.5},
            {
                "authority_id": "AUTH_UNCTAD",
                "value": 0.5,
                "recency": 0.1,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        assert result["residual_conflict"] is False

    def test_residual_when_values_disagree(self):
        claims = [
            {"authority_id": "AUTH_BIS", "value": 0.5},
            {
                "authority_id": "AUTH_UNCTAD",
                "value": 0.9,
                "recency": 0.1,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        if result["outcome"] == PrecedenceOutcome.RESOLVED:
            assert result["residual_conflict"] is True

    def test_residual_severity_documented(self):
        claims = [
            {"authority_id": "AUTH_BIS", "value": 0.5},
            {
                "authority_id": "AUTH_UNCTAD",
                "value": 0.9,
                "recency": 0.1,
            },
        ]
        result = resolve_authority_precedence(claims, field="score")
        assert "residual_conflict_severity" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: MULTI-FIELD RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiFieldPrecedence:
    """resolve_multi_field_precedence() handles multiple fields."""

    def test_multi_field_resolution(self):
        field_claims = {
            "score_axis1": [{"authority_id": "AUTH_BIS", "value": 0.5}],
            "score_axis2": [
                {"authority_id": "AUTH_BIS", "value": 0.4},
                {"authority_id": "AUTH_UNCTAD", "value": 0.6, "recency": 0.1},
            ],
        }
        result = resolve_multi_field_precedence(field_claims)
        assert result["n_fields"] == 2
        assert "score_axis1" in result["resolutions"]
        assert "score_axis2" in result["resolutions"]
        assert "honesty_note" in result

    def test_multi_field_tracks_residuals(self):
        field_claims = {
            "field1": [{"authority_id": "AUTH_BIS", "value": 0.5}],
        }
        result = resolve_multi_field_precedence(field_claims)
        assert "has_residual_conflict" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: DETERMINISM
# ═══════════════════════════════════════════════════════════════════════════

class TestPrecedenceDeterminism:
    """Same inputs must produce same outputs."""

    def test_deterministic_resolution(self):
        claims = [
            {"authority_id": "AUTH_BIS", "value": 0.5, "recency": 0.8},
            {"authority_id": "AUTH_UNCTAD", "value": 0.7, "recency": 0.3},
        ]
        r1 = resolve_authority_precedence(claims, field="test")
        r2 = resolve_authority_precedence(claims, field="test")
        assert r1["outcome"] == r2["outcome"]
        assert r1["winning_authority"] == r2["winning_authority"]
        assert r1["winning_value"] == r2["winning_value"]

    def test_honesty_note_present(self):
        result = resolve_authority_precedence([], field="test")
        assert "honesty_note" in result
