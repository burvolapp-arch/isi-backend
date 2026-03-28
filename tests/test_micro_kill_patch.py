"""
tests.test_micro_kill_patch — ISI FINAL MICRO KILL-PATCH tests.

Validates the two surgical fixes:
  Issue 1: Pre-arbiter narrowing disclosure — TRANSFORM modules that
           narrow the epistemic input space must be explicitly disclosed
           in the arbiter verdict.
  Issue 2: Multi-factor dominant constraint — the dominant constraint
           is identified by (severity, output-binding breadth, primary-
           path bonus), not severity alone.
"""

from __future__ import annotations

from typing import Any

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════════════════════════════

from backend.epistemic_arbiter import adjudicate as arbiter_adjudicate
from backend.export_snapshot import _compute_pre_arbiter_narrowing
from backend.epistemic_invariants import check_pre_arbiter_disclosure


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _verdict(
    country: str = "DE",
    *,
    runtime_status: dict[str, Any] | None = None,
    truth_resolution: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    failure_visibility: dict[str, Any] | None = None,
    invariant_report: dict[str, Any] | None = None,
    reality_conflicts: dict[str, Any] | None = None,
    publishability_result: dict[str, Any] | None = None,
    pre_arbiter_narrowing: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Helper to call arbiter_adjudicate with minimal boilerplate."""
    return arbiter_adjudicate(
        country=country,
        runtime_status=runtime_status,
        truth_resolution=truth_resolution,
        governance=governance,
        failure_visibility=failure_visibility,
        invariant_report=invariant_report,
        reality_conflicts=reality_conflicts,
        publishability_result=publishability_result,
        pre_arbiter_narrowing=pre_arbiter_narrowing,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 1: PRE-ARBITER NARROWING DISCLOSURE
# ═══════════════════════════════════════════════════════════════════════════

class TestPreArbiterNarrowingComputation:
    """Tests for _compute_pre_arbiter_narrowing helper."""

    def test_no_narrowing_returns_empty(self):
        """No inputs = no narrowing."""
        result = _compute_pre_arbiter_narrowing()
        assert result == []

    def test_no_narrowing_with_clean_inputs(self):
        """All modules at full strength = no narrowing."""
        result = _compute_pre_arbiter_narrowing(
            governance={"governance_tier": "FULLY_COMPARABLE"},
            failure_visibility={"trust_level": "STRUCTURALLY_SOUND"},
            reality_conflicts={"has_critical": False, "n_conflicts": 0},
            construct_enforcement={"n_failures": 0},
            sensitivity_result={"is_unstable": False},
            decision_usability={"usability_class": "FULLY_USABLE"},
        )
        assert result == []

    def test_governance_tier_narrowing(self):
        """NON_COMPARABLE governance tier triggers disclosure."""
        result = _compute_pre_arbiter_narrowing(
            governance={"governance_tier": "NON_COMPARABLE"},
        )
        assert len(result) == 1
        assert result[0]["module"] == "governance"
        assert result[0]["narrowing_type"] == "tier_downgrade"

    def test_governance_low_confidence_narrowing(self):
        """LOW_CONFIDENCE governance tier triggers disclosure."""
        result = _compute_pre_arbiter_narrowing(
            governance={"governance_tier": "LOW_CONFIDENCE"},
        )
        assert len(result) == 1
        assert result[0]["module"] == "governance"

    def test_failure_visibility_no_trust(self):
        """DO_NOT_USE trust triggers disclosure."""
        result = _compute_pre_arbiter_narrowing(
            failure_visibility={"trust_level": "DO_NOT_USE"},
        )
        assert len(result) == 1
        assert result[0]["module"] == "failure_visibility"
        assert result[0]["narrowing_type"] == "trust_degradation"

    def test_failure_visibility_extreme_caution(self):
        """USE_WITH_EXTREME_CAUTION triggers disclosure."""
        result = _compute_pre_arbiter_narrowing(
            failure_visibility={"trust_level": "USE_WITH_EXTREME_CAUTION"},
        )
        assert len(result) == 1
        assert result[0]["module"] == "failure_visibility"

    def test_failure_visibility_no_narrowing_for_documented_caveats(self):
        """USE_WITH_DOCUMENTED_CAVEATS does NOT trigger disclosure."""
        result = _compute_pre_arbiter_narrowing(
            failure_visibility={"trust_level": "USE_WITH_DOCUMENTED_CAVEATS"},
        )
        assert result == []

    def test_reality_conflicts_critical(self):
        """Critical reality conflicts trigger disclosure."""
        result = _compute_pre_arbiter_narrowing(
            reality_conflicts={"has_critical": True, "n_conflicts": 3},
        )
        assert len(result) == 1
        assert result[0]["module"] == "reality_conflicts"
        assert result[0]["narrowing_type"] == "critical_contradiction"

    def test_reality_conflicts_non_critical_no_narrowing(self):
        """Non-critical reality conflicts do NOT trigger disclosure."""
        result = _compute_pre_arbiter_narrowing(
            reality_conflicts={"has_critical": False, "n_conflicts": 2},
        )
        assert result == []

    def test_construct_enforcement_failures(self):
        """Construct enforcement failures trigger disclosure."""
        result = _compute_pre_arbiter_narrowing(
            construct_enforcement={"n_failures": 2},
        )
        assert len(result) == 1
        assert result[0]["module"] == "construct_enforcement"
        assert result[0]["narrowing_type"] == "structural_failure"

    def test_alignment_sensitivity_instability(self):
        """Alignment instability triggers disclosure."""
        result = _compute_pre_arbiter_narrowing(
            sensitivity_result={"is_unstable": True},
        )
        assert len(result) == 1
        assert result[0]["module"] == "alignment_sensitivity"
        assert result[0]["narrowing_type"] == "instability"

    def test_decision_usability_downgrade(self):
        """Non-full usability triggers disclosure."""
        result = _compute_pre_arbiter_narrowing(
            decision_usability={"usability_class": "NOT_USABLE"},
        )
        assert len(result) == 1
        assert result[0]["module"] == "decision_usability"
        assert result[0]["narrowing_type"] == "usability_downgrade"

    def test_multiple_narrowing_sources(self):
        """Multiple TRANSFORM modules narrowing produces multiple disclosures."""
        result = _compute_pre_arbiter_narrowing(
            governance={"governance_tier": "NON_COMPARABLE"},
            failure_visibility={"trust_level": "DO_NOT_USE"},
            reality_conflicts={"has_critical": True, "n_conflicts": 1},
        )
        modules = {r["module"] for r in result}
        assert modules == {"governance", "failure_visibility", "reality_conflicts"}
        assert len(result) == 3


class TestArbiterNarrowingInVerdict:
    """Tests that arbiter verdict includes pre_arbiter_narrowing."""

    def test_verdict_contains_narrowing_key(self):
        """Arbiter verdict always has pre_arbiter_narrowing."""
        v = _verdict()
        assert "pre_arbiter_narrowing" in v

    def test_verdict_empty_narrowing_when_none(self):
        """No narrowing → empty list in verdict."""
        v = _verdict()
        assert v["pre_arbiter_narrowing"] == []

    def test_verdict_includes_passed_narrowing(self):
        """Narrowing disclosures forwarded into verdict."""
        narrowing = [
            {"module": "governance", "narrowing_type": "tier_downgrade",
             "detail": "Governance is NON_COMPARABLE"},
        ]
        v = _verdict(pre_arbiter_narrowing=narrowing)
        assert v["pre_arbiter_narrowing"] == narrowing

    def test_verdict_narrowing_matches_governance_input(self):
        """If governance is NON_COMPARABLE and narrowing is disclosed,
        verdict should carry both the narrowing AND the governance reason."""
        narrowing = [
            {"module": "governance", "narrowing_type": "tier_downgrade",
             "detail": "test narrowing"},
        ]
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
            pre_arbiter_narrowing=narrowing,
        )
        assert v["pre_arbiter_narrowing"] == narrowing
        assert v["final_epistemic_status"] == "SUPPRESSED"


class TestArbiterDisclosureInvariant:
    """Tests for ARB-004: pre-arbiter narrowing disclosure invariant."""

    def test_no_narrowing_no_violation(self):
        """Clean verdict with no narrowing → passes."""
        verdicts = {"DE": _verdict()}
        result = check_pre_arbiter_disclosure(verdicts)
        assert result["passed"] is True
        assert result["n_violations"] == 0

    def test_narrowing_disclosed_passes(self):
        """Narrowing present when governance SUPPRESSED → passes."""
        narrowing = [
            {"module": "governance", "narrowing_type": "tier_downgrade",
             "detail": "disclosed"},
        ]
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
            pre_arbiter_narrowing=narrowing,
        )
        result = check_pre_arbiter_disclosure({"DE": v})
        assert result["passed"] is True

    def test_hidden_narrowing_violates(self):
        """Governance SUPPRESSED but no narrowing disclosure → ARB-004 violation."""
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
            pre_arbiter_narrowing=None,
        )
        result = check_pre_arbiter_disclosure({"DE": v})
        assert result["passed"] is False
        assert result["n_violations"] == 1
        assert result["violations"][0]["invariant_id"] == "ARB-004"

    def test_multiple_countries_mixed(self):
        """One country with disclosure, one without → 1 violation."""
        v_ok = _verdict(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE"},
            pre_arbiter_narrowing=[{"module": "governance",
                                    "narrowing_type": "tier_downgrade",
                                    "detail": "ok"}],
        )
        v_bad = _verdict(
            country="FR",
            failure_visibility={"trust_level": "NO_TRUST"},
            pre_arbiter_narrowing=None,
        )
        result = check_pre_arbiter_disclosure({"DE": v_ok, "FR": v_bad})
        assert result["passed"] is False
        assert result["n_violations"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 2: MULTI-FACTOR DOMINANT CONSTRAINT
# ═══════════════════════════════════════════════════════════════════════════

class TestDominantConstraintMultiFactor:
    """Tests that dominant constraint uses multi-factor scoring."""

    def test_single_reason_is_dominant(self):
        """Single reason always wins."""
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
        )
        assert v["dominant_constraint_source"] == "governance"

    def test_severity_wins_when_clear(self):
        """BLOCKED beats FLAGGED in severity."""
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
            reality_conflicts={"has_critical": False, "n_conflicts": 1},
        )
        assert v["dominant_constraint_source"] == "runtime_status"

    def test_primary_path_beats_side_path_on_tie(self):
        """Governance (primary path) SUPPRESSED beats reality_conflicts
        SUPPRESSED because governance forbids 3 claims vs reality_conflicts
        forbids 0 claims directly, plus primary path bonus."""
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
            reality_conflicts={"has_critical": True, "n_conflicts": 1},
        )
        # Both are SUPPRESSED (severity=3). Governance: 3*3 + 3*2 + 1 = 16.
        # reality_conflicts: 3*3 + 0*2 + 0 = 9.
        assert v["dominant_constraint_source"] == "governance"

    def test_truth_blocked_beats_governance_suppressed(self):
        """Truth BLOCKED (severity 4, 5 claims, primary) beats governance
        SUPPRESSED (severity 3, 3 claims, primary)."""
        v = _verdict(
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
            governance={"governance_tier": "NON_COMPARABLE"},
        )
        # Truth: 4*3 + 5*2 + 1 = 23. Governance: 3*3 + 3*2 + 1 = 16.
        assert v["dominant_constraint_source"] == "truth_resolution"

    def test_invariant_blocked_beats_failure_visibility_suppressed(self):
        """Invariant BLOCKED (severity 4, 3 claims) beats failure_visibility
        SUPPRESSED (severity 3, 0 claims). Even though both are non-primary."""
        v = _verdict(
            invariant_report={
                "passed": False,
                "n_violations": 1,
                "violation_ids": ["EMI-001"],
            },
            failure_visibility={"trust_level": "NO_TRUST"},
        )
        # Invariant: 4*3 + 3*2 + 0 = 18. FV: 3*3 + 0*2 + 0 = 9.
        assert v["dominant_constraint_source"] == "invariant_report"

    def test_output_binding_breadth_breaks_severity_tie(self):
        """When two reasons have the same severity but different claim counts,
        the one forbidding more claims wins."""
        # Truth BLOCKED (5 claims) vs runtime BLOCKED (5 claims) — tie;
        # runtime is first in eval order so wins.
        # But truth BLOCKED (5 claims) vs invariant BLOCKED (3 claims):
        # truth wins via breadth.
        v = _verdict(
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
            invariant_report={
                "passed": False,
                "n_violations": 1,
                "violation_ids": ["EMI-001"],
            },
        )
        # Truth: 4*3 + 5*2 + 1 = 23. Invariant: 4*3 + 3*2 + 0 = 18.
        assert v["dominant_constraint_source"] == "truth_resolution"

    def test_earliest_wins_on_full_tie(self):
        """If two sources score identically, earliest in evaluation order wins."""
        # Use runtime BLOCKED (score = 4*3+5*2+1 = 23) vs truth BLOCKED
        # (score = 4*3+5*2+1 = 23). Runtime is section 1, truth is section 2.
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
        )
        assert v["dominant_constraint_source"] == "runtime_status"

    def test_no_reasons_no_dominant(self):
        """No reasons → no dominant constraint."""
        v = _verdict()
        assert v["dominant_constraint"] is None
        assert v["dominant_constraint_source"] is None

    def test_flagged_side_path_never_beats_blocked_primary(self):
        """A FLAGGED side-path reason can never outrank a BLOCKED primary."""
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
            failure_visibility={"trust_level": "LOW_TRUST"},
        )
        # runtime BLOCKED: 4*3+5*2+1=23. FV FLAGGED: 2*3+0*2+0=6.
        assert v["dominant_constraint_source"] == "runtime_status"

    def test_governance_restricted_vs_publishability_suppressed(self):
        """Publishability SUPPRESSED (severity 3) vs governance RESTRICTED
        (severity 1). Publishability has higher severity despite fewer
        claims (1 vs 3). Score: pub=3*3+1*2+0=11, gov=1*3+3*2+1=10.
        Publishability wins."""
        v = _verdict(
            governance={"governance_tier": "LOW_CONFIDENCE"},
            publishability_result={
                "publishability_status": "NOT_PUBLISHABLE",
            },
        )
        assert v["dominant_constraint_source"] == "publishability"
