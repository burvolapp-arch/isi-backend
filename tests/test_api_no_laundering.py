"""
tests.test_api_no_laundering — Anti-Laundering Tests for API Outputs

Verifies:
    - API outputs cannot present ranking if arbiter forbids it.
    - API outputs cannot present comparison if arbiter forbids it.
    - API outputs cannot exceed confidence cap.
    - API outputs cannot omit required warnings.
    - Blocked/suppressed outputs cannot claim publication.
    - Composite score cannot appear if forbidden.
    - Policy claims cannot appear if forbidden.
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

def _verdict_blocking_all() -> dict:
    """Arbiter verdict that blocks everything."""
    return adjudicate(
        country="DE",
        truth_resolution={"truth_status": "INVALID", "export_blocked": True},
    )


def _verdict_forbidding_ranking() -> dict:
    """Arbiter verdict that forbids ranking."""
    return adjudicate(
        country="DE",
        override_pressure={
            "max_strength": "DECISIVE",
            "confidence_cap": 0.3,
            "can_rank": False,
            "can_compare": False,
        },
    )


def _verdict_valid() -> dict:
    """Arbiter verdict with no restrictions."""
    return adjudicate(country="DE")


def _verdict_with_warnings() -> dict:
    """Arbiter verdict requiring warnings."""
    return adjudicate(
        country="DE",
        truth_resolution={"truth_status": "DEGRADED", "n_conflicts": 3},
    )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: RANKING LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestRankingLaundering:
    """Ranking must not appear in output when arbiter forbids it."""

    def test_rank_in_output_caught(self):
        verdict = _verdict_forbidding_ranking()
        assert "ranking" in verdict["final_forbidden_claims"]
        output = {"rank": 5}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "ranking" for v in result["violations"])

    def test_ranking_eligible_in_output_caught(self):
        verdict = _verdict_forbidding_ranking()
        output = {"ranking_eligible": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False

    def test_rank_none_passes(self):
        verdict = _verdict_forbidding_ranking()
        output = {"rank": None, "ranking_eligible": False}
        result = validate_output_against_arbiter(output, verdict)
        # Check that ranking violations are absent
        rank_violations = [v for v in result["violations"] if v["field"] == "ranking"]
        assert len(rank_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: COMPARISON LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestComparisonLaundering:
    """Comparability must not appear in output when arbiter forbids it."""

    def test_cross_country_comparable_caught(self):
        verdict = _verdict_forbidding_ranking()
        assert "comparison" in verdict["final_forbidden_claims"]
        output = {"cross_country_comparable": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "comparison" for v in result["violations"])

    def test_comparable_false_passes(self):
        verdict = _verdict_forbidding_ranking()
        output = {"cross_country_comparable": False}
        result = validate_output_against_arbiter(output, verdict)
        comp_violations = [v for v in result["violations"] if v["field"] == "comparison"]
        assert len(comp_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: CONFIDENCE LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceLaundering:
    """Output confidence must not exceed arbiter cap."""

    def test_confidence_exceeding_cap_caught(self):
        verdict = _verdict_forbidding_ranking()
        cap = verdict["final_confidence_cap"]
        output = {"confidence": cap + 0.1}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "confidence" for v in result["violations"])

    def test_confidence_at_cap_passes(self):
        verdict = _verdict_forbidding_ranking()
        cap = verdict["final_confidence_cap"]
        output = {"confidence": cap}
        result = validate_output_against_arbiter(output, verdict)
        conf_violations = [v for v in result["violations"] if v["field"] == "confidence"]
        assert len(conf_violations) == 0

    def test_confidence_below_cap_passes(self):
        verdict = _verdict_forbidding_ranking()
        cap = verdict["final_confidence_cap"]
        output = {"confidence": cap - 0.1}
        result = validate_output_against_arbiter(output, verdict)
        conf_violations = [v for v in result["violations"] if v["field"] == "confidence"]
        assert len(conf_violations) == 0

    def test_no_confidence_passes(self):
        verdict = _verdict_forbidding_ranking()
        output = {}
        result = validate_output_against_arbiter(output, verdict)
        conf_violations = [v for v in result["violations"] if v["field"] == "confidence"]
        assert len(conf_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: REQUIRED WARNINGS LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestWarningsLaundering:
    """Required warnings must be present in output."""

    def test_missing_warnings_caught(self):
        verdict = _verdict_with_warnings()
        required = verdict["final_required_warnings"]
        assert len(required) > 0
        output = {"warnings": []}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "warnings" for v in result["violations"])

    def test_all_warnings_present_passes(self):
        verdict = _verdict_with_warnings()
        required = verdict["final_required_warnings"]
        output = {"warnings": list(required)}
        result = validate_output_against_arbiter(output, verdict)
        warning_violations = [v for v in result["violations"] if v["field"] == "warnings"]
        assert len(warning_violations) == 0

    def test_partial_warnings_fails(self):
        verdict = _verdict_with_warnings()
        required = verdict["final_required_warnings"]
        if len(required) > 0:
            output = {"warnings": [required[0]]}
            result = validate_output_against_arbiter(output, verdict)
            if len(required) > 1:
                assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: PUBLICATION LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestPublicationLaundering:
    """Blocked/suppressed outputs must not claim publication."""

    def test_blocked_output_marked_published_caught(self):
        verdict = _verdict_blocking_all()
        assert verdict["final_epistemic_status"] == ArbiterStatus.BLOCKED
        output = {"is_published": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "publication" for v in result["violations"])

    def test_blocked_output_not_published_passes(self):
        verdict = _verdict_blocking_all()
        output = {"is_published": False}
        result = validate_output_against_arbiter(output, verdict)
        pub_violations = [v for v in result["violations"] if v["field"] == "publication"]
        assert len(pub_violations) == 0

    def test_valid_output_marked_published_passes(self):
        verdict = _verdict_valid()
        output = {"is_published": True}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: COMPOSITE LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestCompositeLaundering:
    """Composite score must not appear when forbidden."""

    def test_composite_when_forbidden_caught(self):
        verdict = _verdict_blocking_all()
        assert "composite" in verdict["final_forbidden_claims"]
        output = {"composite_score": 0.72}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "composite" for v in result["violations"])

    def test_composite_none_passes(self):
        verdict = _verdict_blocking_all()
        output = {"composite_score": None}
        result = validate_output_against_arbiter(output, verdict)
        comp_violations = [v for v in result["violations"] if v["field"] == "composite"]
        assert len(comp_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: POLICY LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestPolicyLaundering:
    """Policy claims must not appear when forbidden."""

    def test_policy_when_forbidden_caught(self):
        verdict = _verdict_blocking_all()
        assert "policy_claim" in verdict["final_forbidden_claims"]
        output = {"policy_implications": ["Lower tariffs recommended"]}
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any(v["field"] == "policy_claim" for v in result["violations"])

    def test_no_policy_passes(self):
        verdict = _verdict_blocking_all()
        output = {"policy_implications": []}
        result = validate_output_against_arbiter(output, verdict)
        pol_violations = [v for v in result["violations"] if v["field"] == "policy_claim"]
        assert len(pol_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: CLEAN OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

class TestCleanOutput:
    """Completely clean output against valid verdict should pass."""

    def test_clean_output_passes(self):
        verdict = _verdict_valid()
        output = {
            "rank": 5,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "confidence": 0.85,
            "composite_score": 0.72,
            "is_published": True,
            "warnings": [],
        }
        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is True
        assert result["n_violations"] == 0

    def test_honesty_note_in_result(self):
        verdict = _verdict_valid()
        output = {}
        result = validate_output_against_arbiter(output, verdict)
        assert "honesty_note" in result
