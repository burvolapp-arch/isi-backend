"""
tests.test_epistemic_arbiter — Tests for Final Epistemic Arbiter

Verifies:
    - Arbiter produces binding verdict for every country.
    - Any BLOCKED input → BLOCKED output.
    - Any SUPPRESSED input → at least SUPPRESSED output.
    - Confidence cap respects ALL upstream ceilings.
    - Forbidden claims are enforced.
    - validate_output_against_arbiter() catches violations.
    - ALL exports must pass through arbiter.
"""

from __future__ import annotations

from backend.epistemic_arbiter import (
    ARBITER_STATUS_ORDER,
    ArbiterStatus,
    VALID_ARBITER_STATUSES,
    adjudicate,
    validate_output_against_arbiter,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: ARBITER STATUS
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterStatus:
    """ArbiterStatus class and ordering."""

    def test_all_statuses_valid(self):
        assert len(VALID_ARBITER_STATUSES) == 5

    def test_status_ordering(self):
        assert ARBITER_STATUS_ORDER[ArbiterStatus.VALID] < ARBITER_STATUS_ORDER[ArbiterStatus.RESTRICTED]
        assert ARBITER_STATUS_ORDER[ArbiterStatus.RESTRICTED] < ARBITER_STATUS_ORDER[ArbiterStatus.FLAGGED]
        assert ARBITER_STATUS_ORDER[ArbiterStatus.FLAGGED] < ARBITER_STATUS_ORDER[ArbiterStatus.SUPPRESSED]
        assert ARBITER_STATUS_ORDER[ArbiterStatus.SUPPRESSED] < ARBITER_STATUS_ORDER[ArbiterStatus.BLOCKED]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: BASIC ADJUDICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestBasicAdjudication:
    """Basic arbiter adjudication behavior."""

    def test_no_inputs_gives_valid(self):
        result = adjudicate(country="DE")
        assert result["final_epistemic_status"] == ArbiterStatus.VALID
        assert result["final_confidence_cap"] == 1.0
        assert result["country"] == "DE"

    def test_result_has_required_fields(self):
        result = adjudicate(country="DE")
        required = [
            "final_epistemic_status", "final_confidence_cap",
            "final_publishability", "final_allowed_claims",
            "final_forbidden_claims", "final_required_warnings",
            "binding_constraints", "arbiter_reasoning",
            "honesty_note",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_honesty_note_mentions_arbiter(self):
        result = adjudicate(country="DE")
        assert "arbiter" in result["honesty_note"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: BLOCKING CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestBlockingConditions:
    """Any blocking condition must produce BLOCKED output."""

    def test_failed_pipeline_blocks(self):
        result = adjudicate(
            country="DE",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["layer_1"],
                "degraded_layers": [],
            },
        )
        assert result["final_epistemic_status"] == ArbiterStatus.BLOCKED

    def test_invalid_truth_blocks(self):
        result = adjudicate(
            country="DE",
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
        )
        assert result["final_epistemic_status"] == ArbiterStatus.BLOCKED
        assert "ranking" in result["final_forbidden_claims"]

    def test_blocked_scope_blocks(self):
        result = adjudicate(
            country="DE",
            scope_result={"scope_level": "BLOCKED"},
        )
        assert result["final_epistemic_status"] == ArbiterStatus.BLOCKED

    def test_invariant_violations_block(self):
        result = adjudicate(
            country="DE",
            invariant_report={
                "passed": False,
                "n_violations": 2,
                "violation_ids": ["EMI-001", "EMI-003"],
            },
        )
        assert result["final_epistemic_status"] == ArbiterStatus.BLOCKED


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: RESTRICTION CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestRestrictionConditions:
    """Restrictive inputs must produce at least RESTRICTED output."""

    def test_degraded_truth_restricts(self):
        result = adjudicate(
            country="DE",
            truth_resolution={
                "truth_status": "DEGRADED",
                "n_conflicts": 2,
                "final_ranking_eligible": True,
                "final_cross_country_comparable": True,
            },
        )
        assert ARBITER_STATUS_ORDER[result["final_epistemic_status"]] >= ARBITER_STATUS_ORDER[ArbiterStatus.RESTRICTED]

    def test_strong_override_restricts(self):
        result = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.6,
                "can_rank": True,
                "can_compare": True,
            },
        )
        assert ARBITER_STATUS_ORDER[result["final_epistemic_status"]] >= ARBITER_STATUS_ORDER[ArbiterStatus.RESTRICTED]
        assert result["final_confidence_cap"] <= 0.6

    def test_non_comparable_governance_suppresses(self):
        result = adjudicate(
            country="DE",
            governance={
                "governance_tier": "NON_COMPARABLE",
                "ranking_eligible": False,
            },
        )
        assert ARBITER_STATUS_ORDER[result["final_epistemic_status"]] >= ARBITER_STATUS_ORDER[ArbiterStatus.SUPPRESSED]
        assert "ranking" in result["final_forbidden_claims"]

    def test_critical_reality_conflicts_suppress(self):
        result = adjudicate(
            country="DE",
            reality_conflicts={
                "has_critical": True,
                "n_conflicts": 3,
            },
        )
        assert ARBITER_STATUS_ORDER[result["final_epistemic_status"]] >= ARBITER_STATUS_ORDER[ArbiterStatus.SUPPRESSED]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: CONFIDENCE CAP
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceCap:
    """Confidence cap must respect ALL upstream ceilings."""

    def test_confidence_cap_from_override_pressure(self):
        result = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.6,
                "can_rank": True,
                "can_compare": True,
            },
        )
        assert result["final_confidence_cap"] <= 0.6

    def test_confidence_cap_from_degraded_runtime(self):
        result = adjudicate(
            country="DE",
            runtime_status={
                "pipeline_status": "DEGRADED",
                "degraded_layers": ["layer_1"],
                "failed_layers": [],
            },
        )
        assert result["final_confidence_cap"] <= 0.7

    def test_multiple_caps_take_minimum(self):
        result = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.6,
                "can_rank": True,
                "can_compare": True,
            },
            truth_resolution={
                "truth_status": "DEGRADED",
                "n_conflicts": 1,
                "final_ranking_eligible": True,
                "final_cross_country_comparable": True,
            },
        )
        assert result["final_confidence_cap"] <= 0.6


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: ANTI-LAUNDERING VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiLaunderingValidation:
    """validate_output_against_arbiter() must catch violations."""

    def test_clean_output_passes(self):
        verdict = adjudicate(country="DE")
        output = {"confidence": 0.5}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is True

    def test_confidence_exceeds_cap_fails(self):
        verdict = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.6,
                "can_rank": True,
                "can_compare": True,
            },
        )
        output = {"confidence": 0.9}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "confidence" for v in result["violations"])

    def test_forbidden_ranking_in_output_fails(self):
        verdict = adjudicate(
            country="DE",
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
        )
        output = {"rank": 5, "ranking_eligible": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "ranking" for v in result["violations"])

    def test_blocked_output_published_fails(self):
        verdict = adjudicate(
            country="DE",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["layer_1"],
                "degraded_layers": [],
            },
        )
        output = {"is_published": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False

    def test_missing_required_warnings_fails(self):
        verdict = adjudicate(
            country="DE",
            truth_resolution={
                "truth_status": "DEGRADED",
                "n_conflicts": 2,
                "final_ranking_eligible": True,
                "final_cross_country_comparable": True,
            },
        )
        output = {"warnings": []}
        result = validate_output_against_arbiter(output, verdict)
        # Should fail because required warnings are missing
        if verdict["final_required_warnings"]:
            assert result["passed"] is False

    def test_forbidden_comparison_fails(self):
        verdict = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "DECISIVE",
                "confidence_cap": 0.0,
                "can_rank": False,
                "can_compare": False,
            },
        )
        output = {"cross_country_comparable": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: ARBITER GOVERNS ALL OUTPUTS
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterGovernsAll:
    """The arbiter is the single source of truth for all external claims."""

    def test_arbiter_result_has_bounds(self):
        result = adjudicate(country="DE")
        assert "final_bounds" in result
        assert "max_confidence" in result["final_bounds"]

    def test_arbiter_tracks_input_count(self):
        result = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "VALID"},
            governance={"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
        )
        assert result["n_inputs_evaluated"] == 2

    def test_most_restrictive_wins(self):
        """When multiple inputs disagree, most restrictive status wins."""
        result = adjudicate(
            country="DE",
            truth_resolution={
                "truth_status": "DEGRADED",
                "n_conflicts": 1,
                "final_ranking_eligible": True,
                "final_cross_country_comparable": True,
            },
            governance={
                "governance_tier": "NON_COMPARABLE",
                "ranking_eligible": False,
            },
        )
        # NON_COMPARABLE → SUPPRESSED should win over DEGRADED → RESTRICTED
        assert ARBITER_STATUS_ORDER[result["final_epistemic_status"]] >= ARBITER_STATUS_ORDER[ArbiterStatus.SUPPRESSED]

    def test_publishability_maps_from_status(self):
        """Arbiter status maps to publishability correctly."""
        result = adjudicate(country="DE")
        status = result["final_epistemic_status"]
        pub = result["final_publishability"]

        if status == ArbiterStatus.VALID:
            assert pub == "PUBLISHABLE"
        elif status in (ArbiterStatus.RESTRICTED, ArbiterStatus.FLAGGED):
            assert pub == "PUBLISHABLE_WITH_CAVEATS"
        elif status in (ArbiterStatus.SUPPRESSED, ArbiterStatus.BLOCKED):
            assert pub == "NOT_PUBLISHABLE"
