"""
tests.test_publishability_gate — Tests for Publication Fitness Gate

Verifies:
    - RESTRICTED status exists and works.
    - WITH_CAVEATS allowed ONLY if conditions met.
    - Residual authority conflict triggers RESTRICTED.
    - All publishability statuses are valid.
"""

from __future__ import annotations

from backend.publishability import (
    PublishabilityStatus,
    VALID_PUBLISHABILITY_STATUSES,
    assess_publishability,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: PUBLISHABILITY STATUS
# ═══════════════════════════════════════════════════════════════════════════

class TestPublishabilityStatus:
    """PublishabilityStatus class integrity."""

    def test_restricted_status_exists(self):
        assert hasattr(PublishabilityStatus, "RESTRICTED")
        assert PublishabilityStatus.RESTRICTED == "RESTRICTED"

    def test_four_statuses_exist(self):
        assert len(VALID_PUBLISHABILITY_STATUSES) == 4
        assert PublishabilityStatus.PUBLISHABLE in VALID_PUBLISHABILITY_STATUSES
        assert PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS in VALID_PUBLISHABILITY_STATUSES
        assert PublishabilityStatus.RESTRICTED in VALID_PUBLISHABILITY_STATUSES
        assert PublishabilityStatus.NOT_PUBLISHABLE in VALID_PUBLISHABILITY_STATUSES


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: BASIC ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

class TestBasicAssessment:
    """Basic publishability assessment behavior."""

    def test_no_inputs_is_publishable(self):
        result = assess_publishability("DE")
        assert result["publishability_status"] == PublishabilityStatus.PUBLISHABLE

    def test_export_blocked_is_not_publishable(self):
        result = assess_publishability(
            "DE",
            truth_result={"export_blocked": True, "truth_status": "VALID"},
        )
        assert result["publishability_status"] == PublishabilityStatus.NOT_PUBLISHABLE

    def test_invalid_truth_is_not_publishable(self):
        result = assess_publishability(
            "DE",
            truth_result={"truth_status": "INVALID"},
        )
        assert result["publishability_status"] == PublishabilityStatus.NOT_PUBLISHABLE

    def test_critical_authority_is_not_publishable(self):
        result = assess_publishability(
            "DE",
            authority_conflicts={"has_critical": True, "n_conflicts": 1},
        )
        assert result["publishability_status"] == PublishabilityStatus.NOT_PUBLISHABLE


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: RESTRICTED STATUS
# ═══════════════════════════════════════════════════════════════════════════

class TestRestrictedStatus:
    """RESTRICTED status must trigger on residual authority conflicts."""

    def test_residual_error_conflict_triggers_restricted(self):
        result = assess_publishability(
            "DE",
            authority_conflicts={
                "has_critical": False,
                "n_conflicts": 2,
                "has_residual_conflict": True,
                "residual_conflict_severity": "ERROR",
            },
        )
        assert result["publishability_status"] == PublishabilityStatus.RESTRICTED

    def test_residual_critical_conflict_triggers_restricted(self):
        result = assess_publishability(
            "DE",
            authority_conflicts={
                "has_critical": False,
                "n_conflicts": 1,
                "has_residual_conflict": True,
                "residual_conflict_severity": "CRITICAL",
            },
        )
        assert result["publishability_status"] == PublishabilityStatus.RESTRICTED

    def test_residual_warning_does_not_restrict(self):
        """WARNING severity residual conflict doesn't trigger RESTRICTED."""
        result = assess_publishability(
            "DE",
            authority_conflicts={
                "has_critical": False,
                "n_conflicts": 1,
                "has_residual_conflict": True,
                "residual_conflict_severity": "WARNING",
            },
        )
        # Should be PUBLISHABLE_WITH_CAVEATS (from n_conflicts > 0), not RESTRICTED
        assert result["publishability_status"] in (
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
            PublishabilityStatus.PUBLISHABLE,
        )

    def test_not_publishable_is_not_downgraded_to_restricted(self):
        """NOT_PUBLISHABLE should not be 'upgraded' to RESTRICTED."""
        result = assess_publishability(
            "DE",
            truth_result={"truth_status": "INVALID"},
            authority_conflicts={
                "has_critical": False,
                "n_conflicts": 1,
                "has_residual_conflict": True,
                "residual_conflict_severity": "ERROR",
            },
        )
        assert result["publishability_status"] == PublishabilityStatus.NOT_PUBLISHABLE


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: CAVEATS
# ═══════════════════════════════════════════════════════════════════════════

class TestPublishabilityCaveats:
    """Caveats must be properly assigned."""

    def test_degraded_truth_adds_caveats(self):
        result = assess_publishability(
            "DE",
            truth_result={"truth_status": "DEGRADED", "n_conflicts": 2},
        )
        assert result["requires_caveats"] is True
        assert len(result["caveats"]) > 0

    def test_restricted_scope_adds_caveats(self):
        result = assess_publishability(
            "DE",
            scope_result={"scope_level": "RESTRICTED"},
        )
        assert result["requires_caveats"] is True

    def test_incomplete_data_adds_caveats(self):
        result = assess_publishability(
            "DE",
            data_completeness={"axes_available": 4, "axes_required": 6},
        )
        assert result["requires_caveats"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: OUTPUT STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class TestPublishabilityOutputStructure:
    """Output must have all required fields."""

    def test_output_has_required_fields(self):
        result = assess_publishability("DE")
        required = [
            "country", "publishability_status", "is_publishable",
            "requires_caveats", "reasons", "caveats", "blockers",
            "honesty_note",
        ]
        for field in required:
            assert field in result

    def test_publishable_is_publishable(self):
        result = assess_publishability("DE")
        assert result["is_publishable"] is True

    def test_not_publishable_is_not_publishable(self):
        result = assess_publishability(
            "DE",
            truth_result={"truth_status": "INVALID"},
        )
        assert result["is_publishable"] is False
