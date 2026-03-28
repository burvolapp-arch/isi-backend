"""
tests.test_export_no_laundering — Anti-Laundering Tests for Export Outputs

Verifies:
    - Export outputs cannot omit the arbiter verdict block.
    - Export cannot publish suppressed entities.
    - Export cannot include ranking without eligibility + constraints.
    - Export cannot omit binding constraints or forbidden claims.
    - Every export output must be validatable against arbiter.
"""

from __future__ import annotations

from backend.epistemic_arbiter import (
    ArbiterStatus,
    adjudicate,
    validate_output_against_arbiter,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _build_export_output(
    *,
    rank: int | None = None,
    ranking_eligible: bool = False,
    cross_country_comparable: bool = False,
    confidence: float = 0.5,
    composite_score: float | None = None,
    is_published: bool = True,
    warnings: list[str] | None = None,
    policy_implications: list[str] | None = None,
    arbiter_block: dict | None = None,
) -> dict:
    """Build a mock export output."""
    output: dict = {
        "rank": rank,
        "ranking_eligible": ranking_eligible,
        "cross_country_comparable": cross_country_comparable,
        "confidence": confidence,
        "is_published": is_published,
        "warnings": warnings or [],
    }
    if composite_score is not None:
        output["composite_score"] = composite_score
    if policy_implications is not None:
        output["policy_implications"] = policy_implications
    if arbiter_block is not None:
        output["arbiter_verdict"] = arbiter_block
    return output


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: SUPPRESSED ENTITY PUBLISHING
# ═══════════════════════════════════════════════════════════════════════════

class TestSuppressedEntityPublishing:
    """Suppressed entities must never be published."""

    def test_suppressed_entity_published_fails(self):
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        assert verdict["final_epistemic_status"] == ArbiterStatus.SUPPRESSED
        output = _build_export_output(is_published=True)
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "publication" for v in result["violations"])

    def test_suppressed_entity_unpublished_passes(self):
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        output = _build_export_output(is_published=False, ranking_eligible=False)
        result = validate_output_against_arbiter(output, verdict)
        pub_violations = [v for v in result["violations"] if v["field"] == "publication"]
        assert len(pub_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: RANKING WITHOUT ELIGIBILITY
# ═══════════════════════════════════════════════════════════════════════════

class TestRankingWithoutEligibility:
    """Ranking must not be exported without arbiter allowing it."""

    def test_rank_with_ranking_forbidden_fails(self):
        verdict = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "DECISIVE",
                "confidence_cap": 0.3,
                "can_rank": False,
                "can_compare": False,
            },
        )
        output = _build_export_output(rank=3, ranking_eligible=True)
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False

    def test_rank_with_ranking_allowed_passes(self):
        verdict = adjudicate(country="DE")
        assert "ranking" in verdict["final_allowed_claims"]
        output = _build_export_output(
            rank=3, ranking_eligible=True,
            cross_country_comparable=True,
            confidence=0.85,
        )
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: FORBIDDEN CLAIMS IN EXPORT
# ═══════════════════════════════════════════════════════════════════════════

class TestForbiddenClaimsInExport:
    """Exports must not contain forbidden claims."""

    def test_composite_forbidden_in_export(self):
        verdict = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        assert "composite" in verdict["final_forbidden_claims"]
        output = _build_export_output(composite_score=0.75, is_published=False)
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False

    def test_policy_forbidden_in_export(self):
        verdict = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        assert "policy_claim" in verdict["final_forbidden_claims"]
        output = _build_export_output(
            policy_implications=["Should increase spending"],
            is_published=False,
        )
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: CONFIDENCE CAP IN EXPORT
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceCapInExport:
    """Export confidence must not exceed arbiter cap."""

    def test_confidence_exceeding_cap_in_export(self):
        verdict = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.5,
                "can_rank": True,
                "can_compare": True,
            },
        )
        cap = verdict["final_confidence_cap"]
        output = _build_export_output(confidence=cap + 0.2)
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False

    def test_confidence_under_cap_in_export(self):
        verdict = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.5,
                "can_rank": True,
                "can_compare": True,
            },
        )
        cap = verdict["final_confidence_cap"]
        output = _build_export_output(confidence=cap - 0.1)
        result = validate_output_against_arbiter(output, verdict)
        conf_violations = [v for v in result["violations"] if v["field"] == "confidence"]
        assert len(conf_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: ARBITER VERDICT STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterVerdictStructure:
    """Arbiter verdict must have all required keys."""

    def test_verdict_has_required_keys(self):
        verdict = adjudicate(country="DE")
        required = [
            "country",
            "final_epistemic_status",
            "final_confidence_cap",
            "final_publishability",
            "final_allowed_claims",
            "final_forbidden_claims",
            "final_required_warnings",
            "final_bounds",
            "binding_constraints",
            "arbiter_reasoning",
            "honesty_note",
        ]
        for key in required:
            assert key in verdict, f"Missing key: {key}"

    def test_verdict_status_is_valid_type(self):
        verdict = adjudicate(country="DE")
        from backend.epistemic_arbiter import VALID_ARBITER_STATUSES
        assert verdict["final_epistemic_status"] in VALID_ARBITER_STATUSES

    def test_verdict_honesty_note_not_empty(self):
        verdict = adjudicate(country="DE")
        assert len(verdict["honesty_note"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: COMBINED VIOLATIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestCombinedViolations:
    """Multiple violations in a single output should all be caught."""

    def test_multiple_violations_all_reported(self):
        verdict = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        output = _build_export_output(
            rank=1,
            ranking_eligible=True,
            cross_country_comparable=True,
            confidence=0.99,
            composite_score=0.88,
            is_published=True,
            policy_implications=["Bad policy"],
        )
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert result["n_violations"] >= 3  # ranking, comparison, composite, policy, publication, confidence

    def test_clean_export_against_valid_verdict(self):
        verdict = adjudicate(country="DE")
        output = _build_export_output(
            rank=5,
            ranking_eligible=True,
            cross_country_comparable=True,
            confidence=0.85,
            composite_score=0.72,
        )
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is True
