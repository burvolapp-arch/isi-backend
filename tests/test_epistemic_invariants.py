"""
tests.test_epistemic_invariants — Tests for Epistemic Monotonicity Invariants

Verifies:
    - EMI-001: Confidence inflation is detected and fails.
    - EMI-002: Publishability upgrade is detected and fails.
    - EMI-003: Rank resurrection is detected and fails.
    - EMI-004: Comparability resurrection is detected and fails.
    - EMI-005: API output stronger than internal state fails.
    - EMI-006: Caveat laundering (removal) is detected and fails.
    - EMI-007: Missing authority → confidence upgrade fails.
    - EMI-008: Unresolved contradictions → VALID claim fails.
    - EMI-009: Non-deterministic replay fails.
    - EMI-010: Missed diff changes fail.
    - Enforcement clamps state correctly.
    - Report consolidation works.
"""

from __future__ import annotations

from backend.epistemic_invariants import (
    EMI_INVARIANTS,
    build_epistemic_invariant_report,
    check_api_monotonicity,
    check_diff_sensitivity,
    check_epistemic_monotonicity,
    check_replay_determinism,
    enforce_epistemic_monotonicity,
)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: EMI REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestEMIRegistry:
    """EMI invariant registry must contain all 10 invariants."""

    def test_emi_registry_has_10_invariants(self):
        assert len(EMI_INVARIANTS) == 10

    def test_emi_ids_are_sequential(self):
        ids = [inv["invariant_id"] for inv in EMI_INVARIANTS]
        for i in range(1, 11):
            assert f"EMI-{i:03d}" in ids

    def test_all_emi_are_epistemic_monotonicity_type(self):
        for inv in EMI_INVARIANTS:
            assert inv["type"] == "EPISTEMIC_MONOTONICITY"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: CONFIDENCE MONOTONICITY (EMI-001)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI001ConfidenceMonotonicity:
    """EMI-001: Confidence must not inflate downstream."""

    def test_confidence_inflation_fails(self):
        before = {"confidence": 0.6}
        after = {"confidence": 0.8}
        result = check_epistemic_monotonicity(before, after)
        assert result["passed"] is False
        assert any(
            v["invariant_id"] == "EMI-001" for v in result["violations"]
        )

    def test_confidence_decrease_passes(self):
        before = {"confidence": 0.8}
        after = {"confidence": 0.5}
        result = check_epistemic_monotonicity(before, after)
        conf_violations = [
            v for v in result["violations"] if v["invariant_id"] == "EMI-001"
        ]
        assert len(conf_violations) == 0

    def test_confidence_unchanged_passes(self):
        before = {"confidence": 0.6}
        after = {"confidence": 0.6}
        result = check_epistemic_monotonicity(before, after)
        conf_violations = [
            v for v in result["violations"] if v["invariant_id"] == "EMI-001"
        ]
        assert len(conf_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: PUBLISHABILITY MONOTONICITY (EMI-002)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI002PublishabilityMonotonicity:
    """EMI-002: Publishability must not upgrade downstream."""

    def test_publishability_upgrade_fails(self):
        before = {"publishability_status": "NOT_PUBLISHABLE"}
        after = {"publishability_status": "PUBLISHABLE_WITH_CAVEATS"}
        result = check_epistemic_monotonicity(before, after)
        assert result["passed"] is False
        assert any(
            v["invariant_id"] == "EMI-002" for v in result["violations"]
        )

    def test_publishability_downgrade_passes(self):
        before = {"publishability_status": "PUBLISHABLE"}
        after = {"publishability_status": "NOT_PUBLISHABLE"}
        result = check_epistemic_monotonicity(before, after)
        pub_violations = [
            v for v in result["violations"] if v["invariant_id"] == "EMI-002"
        ]
        assert len(pub_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: RANKING RESURRECTION (EMI-003)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI003RankingResurrection:
    """EMI-003: Ranking cannot be resurrected once killed."""

    def test_rank_resurrection_fails(self):
        before = {"ranking_eligible": False}
        after = {"ranking_eligible": True}
        result = check_epistemic_monotonicity(before, after)
        assert result["passed"] is False
        assert any(
            v["invariant_id"] == "EMI-003" for v in result["violations"]
        )

    def test_rank_stays_dead_passes(self):
        before = {"ranking_eligible": False}
        after = {"ranking_eligible": False}
        result = check_epistemic_monotonicity(before, after)
        rank_violations = [
            v for v in result["violations"] if v["invariant_id"] == "EMI-003"
        ]
        assert len(rank_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: API MONOTONICITY (EMI-005)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI005APIMonotonicity:
    """EMI-005: API output must not exceed internal state."""

    def test_api_higher_confidence_fails(self):
        internal = {"confidence": 0.6}
        api = {"confidence": 0.9}
        result = check_api_monotonicity(internal, api)
        assert result["passed"] is False

    def test_api_lower_confidence_passes(self):
        internal = {"confidence": 0.8}
        api = {"confidence": 0.5}
        result = check_api_monotonicity(internal, api)
        assert result["passed"] is True

    def test_api_ranking_resurrection_fails(self):
        internal = {"ranking_eligible": False}
        api = {"ranking_eligible": True}
        result = check_api_monotonicity(internal, api)
        assert result["passed"] is False

    def test_api_clean_output_fails(self):
        """API cannot show comparability when internal says no."""
        internal = {"cross_country_comparable": False}
        api = {"cross_country_comparable": True}
        result = check_api_monotonicity(internal, api)
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: CAVEAT LAUNDERING (EMI-006)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI006CaveatLaundering:
    """EMI-006: Caveats cannot be removed downstream."""

    def test_caveat_removal_fails(self):
        before = {"required_caveats": ["caveat_1", "caveat_2"]}
        after = {"required_caveats": ["caveat_1"]}
        result = check_epistemic_monotonicity(before, after)
        assert result["passed"] is False
        assert any(
            v["invariant_id"] == "EMI-006" for v in result["violations"]
        )

    def test_caveat_addition_passes(self):
        before = {"required_caveats": ["caveat_1"]}
        after = {"required_caveats": ["caveat_1", "caveat_2"]}
        result = check_epistemic_monotonicity(before, after)
        caveat_violations = [
            v for v in result["violations"] if v["invariant_id"] == "EMI-006"
        ]
        assert len(caveat_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: MISSING AUTHORITY (EMI-007)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI007MissingAuthority:
    """EMI-007: Missing authority prevents confidence upgrade."""

    def test_missing_authority_confidence_upgrade_fails(self):
        before = {"missing_authorities": ["BIS"], "confidence": 0.5}
        after = {"confidence": 0.7}
        result = check_epistemic_monotonicity(before, after)
        assert result["passed"] is False
        assert any(
            v["invariant_id"] == "EMI-007" for v in result["violations"]
        )

    def test_no_missing_authority_allows_no_upgrade(self):
        """Even without missing authorities, EMI-001 catches inflation."""
        before = {"missing_authorities": [], "confidence": 0.5}
        after = {"confidence": 0.7}
        result = check_epistemic_monotonicity(before, after)
        # EMI-001 catches this
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: CONTRADICTION NON-UPGRADING (EMI-008)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI008ContradictionNonUpgrading:
    """EMI-008: Contradictions prevent VALID claims without resolution."""

    def test_contradictions_without_resolution_fails(self):
        before = {"contradictions": ["c1", "c2"]}
        after = {"truth_status": "VALID", "contradiction_resolutions": []}
        result = check_epistemic_monotonicity(before, after)
        assert result["passed"] is False
        assert any(
            v["invariant_id"] == "EMI-008" for v in result["violations"]
        )

    def test_all_contradictions_resolved_passes(self):
        before = {"contradictions": ["c1", "c2"]}
        after = {
            "truth_status": "VALID",
            "contradiction_resolutions": ["r1", "r2"],
        }
        result = check_epistemic_monotonicity(before, after)
        contra_violations = [
            v for v in result["violations"] if v["invariant_id"] == "EMI-008"
        ]
        assert len(contra_violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: REPLAY DETERMINISM (EMI-009)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI009ReplayDeterminism:
    """EMI-009: Same input must produce identical epistemic state."""

    def test_deterministic_replay_passes(self):
        replay_a = {"confidence": 0.6, "ranking_eligible": True}
        replay_b = {"confidence": 0.6, "ranking_eligible": True}
        result = check_replay_determinism(replay_a, replay_b)
        assert result["passed"] is True

    def test_non_deterministic_replay_fails(self):
        replay_a = {"confidence": 0.6, "ranking_eligible": True}
        replay_b = {"confidence": 0.7, "ranking_eligible": False}
        result = check_replay_determinism(replay_a, replay_b)
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10: DIFF SENSITIVITY (EMI-010)
# ═══════════════════════════════════════════════════════════════════════════

class TestEMI010DiffSensitivity:
    """EMI-010: Diffs must catch all epistemic state changes."""

    def test_diff_catches_all_changes_passes(self):
        old = {"confidence": 0.8}
        new = {"confidence": 0.5}
        diff = {"epistemic_changes_detected": ["confidence"]}
        result = check_diff_sensitivity(old, new, diff)
        assert result["passed"] is True

    def test_diff_misses_changes_fails(self):
        old = {"confidence": 0.8, "ranking_eligible": True}
        new = {"confidence": 0.5, "ranking_eligible": False}
        diff = {"epistemic_changes_detected": ["confidence"]}
        result = check_diff_sensitivity(old, new, diff)
        assert result["passed"] is False

    def test_no_changes_no_violations(self):
        old = {"confidence": 0.5}
        new = {"confidence": 0.5}
        diff = {"epistemic_changes_detected": []}
        result = check_diff_sensitivity(old, new, diff)
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11: ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════

class TestEpistemicEnforcement:
    """enforce_epistemic_monotonicity() must clamp correctly."""

    def test_clamps_inflated_confidence(self):
        before = {"confidence": 0.6}
        after = {"confidence": 0.9}
        result = enforce_epistemic_monotonicity(before, after)
        assert result["corrected_state"]["confidence"] == 0.6
        assert result["was_modified"] is True

    def test_clamps_resurrected_ranking(self):
        before = {"ranking_eligible": False}
        after = {"ranking_eligible": True}
        result = enforce_epistemic_monotonicity(before, after)
        assert result["corrected_state"]["ranking_eligible"] is False

    def test_restores_dropped_caveats(self):
        before = {"required_caveats": ["c1", "c2"]}
        after = {"required_caveats": ["c1"]}
        result = enforce_epistemic_monotonicity(before, after)
        assert "c2" in result["corrected_state"]["required_caveats"]

    def test_no_correction_when_monotonic(self):
        before = {"confidence": 0.8}
        after = {"confidence": 0.5}
        result = enforce_epistemic_monotonicity(before, after)
        assert result["was_modified"] is False
        assert result["n_corrections"] == 0

    def test_clamps_upgraded_publishability(self):
        before = {"publishability_status": "NOT_PUBLISHABLE"}
        after = {"publishability_status": "PUBLISHABLE"}
        result = enforce_epistemic_monotonicity(before, after)
        assert result["corrected_state"]["publishability_status"] == "NOT_PUBLISHABLE"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 12: REPORT CONSOLIDATION
# ═══════════════════════════════════════════════════════════════════════════

class TestEpistemicInvariantReport:
    """build_epistemic_invariant_report() consolidates all checks."""

    def test_all_pass_report(self):
        mono = check_epistemic_monotonicity(
            {"confidence": 0.8}, {"confidence": 0.5},
        )
        api = check_api_monotonicity(
            {"confidence": 0.5}, {"confidence": 0.3},
        )
        report = build_epistemic_invariant_report(
            monotonicity_result=mono,
            api_result=api,
        )
        assert report["passed"] is True
        assert report["n_violations"] == 0

    def test_violation_report(self):
        mono = check_epistemic_monotonicity(
            {"confidence": 0.5}, {"confidence": 0.9},
        )
        report = build_epistemic_invariant_report(monotonicity_result=mono)
        assert report["passed"] is False
        assert report["n_violations"] > 0
        assert "EMI-001" in report["violation_ids"]

    def test_report_has_honesty_note(self):
        report = build_epistemic_invariant_report()
        assert "honesty_note" in report
