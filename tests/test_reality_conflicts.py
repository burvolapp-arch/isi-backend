"""
tests/test_reality_conflicts.py — Tests for Reality Conflict Detection Engine

Covers Section 3 of the Institutionalization Pass:
    - Governance-alignment mismatch detection
    - Confidence-alignment mismatch detection
    - Usability-alignment mismatch detection
    - Ranking eligibility divergence detection
    - Full detection engine integration
    - Export integration (reality_conflicts key in country JSON)
    - Invariant enforcement for reality conflicts (RC-001, RC-002, RC-003)
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.1: CONFLICT TYPES AND SEVERITY
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictClassifications:
    """Tests for conflict type and severity enumerations."""

    def test_conflict_severity_values(self):
        from backend.reality_conflicts import ConflictSeverity
        assert ConflictSeverity.WARNING == "WARNING"
        assert ConflictSeverity.ERROR == "ERROR"
        assert ConflictSeverity.CRITICAL == "CRITICAL"

    def test_valid_conflict_severities(self):
        from backend.reality_conflicts import VALID_CONFLICT_SEVERITIES
        assert "WARNING" in VALID_CONFLICT_SEVERITIES
        assert "ERROR" in VALID_CONFLICT_SEVERITIES
        assert "CRITICAL" in VALID_CONFLICT_SEVERITIES
        assert len(VALID_CONFLICT_SEVERITIES) == 3

    def test_conflict_type_values(self):
        from backend.reality_conflicts import ConflictType
        assert ConflictType.GOVERNANCE_ALIGNMENT_MISMATCH == "GOVERNANCE_ALIGNMENT_MISMATCH"
        assert ConflictType.CONFIDENCE_ALIGNMENT_MISMATCH == "CONFIDENCE_ALIGNMENT_MISMATCH"
        assert ConflictType.USABILITY_ALIGNMENT_MISMATCH == "USABILITY_ALIGNMENT_MISMATCH"
        assert ConflictType.RANKING_ELIGIBILITY_DIVERGENCE == "RANKING_ELIGIBILITY_DIVERGENCE"

    def test_valid_conflict_types(self):
        from backend.reality_conflicts import VALID_CONFLICT_TYPES
        assert len(VALID_CONFLICT_TYPES) == 4

    def test_conflict_record_structure(self):
        from backend.reality_conflicts import _conflict
        record = _conflict(
            conflict_id="TEST-001",
            conflict_type="TEST_TYPE",
            severity="WARNING",
            internal_state={"key": "val"},
            external_state={"key2": "val2"},
            explanation="test explanation",
            resolution_guidance="test guidance",
        )
        assert record["conflict_id"] == "TEST-001"
        assert record["conflict_type"] == "TEST_TYPE"
        assert record["severity"] == "WARNING"
        assert record["internal_state"] == {"key": "val"}
        assert record["external_state"] == {"key2": "val2"}
        assert "explanation" in record
        assert "resolution_guidance" in record


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.2: GOVERNANCE-ALIGNMENT MISMATCH
# ═══════════════════════════════════════════════════════════════════════════


class TestGovernanceAlignmentMismatch:
    """Tests for governance tier vs external alignment conflicts."""

    def test_fully_comparable_divergent_is_critical(self):
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "DE", "FULLY_COMPARABLE", "DIVERGENT", 3,
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "CRITICAL"
        assert conflicts[0]["conflict_type"] == "GOVERNANCE_ALIGNMENT_MISMATCH"
        assert "DE" in conflicts[0]["conflict_id"]

    def test_partially_comparable_divergent_is_error(self):
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "FR", "PARTIALLY_COMPARABLE", "DIVERGENT", 2,
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "ERROR"
        assert conflicts[0]["conflict_type"] == "GOVERNANCE_ALIGNMENT_MISMATCH"

    def test_non_comparable_strongly_aligned_is_warning(self):
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "CY", "NON_COMPARABLE", "STRONGLY_ALIGNED", 4,
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "WARNING"
        assert "overly conservative" in conflicts[0]["explanation"].lower()

    def test_fully_comparable_strongly_aligned_no_conflict(self):
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "DE", "FULLY_COMPARABLE", "STRONGLY_ALIGNED", 5,
        )
        assert len(conflicts) == 0

    def test_low_confidence_divergent_no_conflict(self):
        """LOW_CONFIDENCE + DIVERGENT is not a conflict — already degraded."""
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "MT", "LOW_CONFIDENCE", "DIVERGENT", 3,
        )
        assert len(conflicts) == 0

    def test_no_data_no_conflict(self):
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "DE", "FULLY_COMPARABLE", "NO_DATA", 0,
        )
        assert len(conflicts) == 0

    def test_zero_compared_no_conflict(self):
        from backend.reality_conflicts import detect_governance_alignment_mismatch
        conflicts = detect_governance_alignment_mismatch(
            "DE", "FULLY_COMPARABLE", "DIVERGENT", 0,
        )
        assert len(conflicts) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.3: CONFIDENCE-ALIGNMENT MISMATCH
# ═══════════════════════════════════════════════════════════════════════════


class TestConfidenceAlignmentMismatch:
    """Tests for high internal confidence vs divergent external alignment."""

    def test_high_confidence_divergent_is_error(self):
        from backend.reality_conflicts import detect_confidence_alignment_mismatch
        conflicts = detect_confidence_alignment_mismatch(
            "DE", 0.85, "DIVERGENT", 4,
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "ERROR"
        assert conflicts[0]["conflict_type"] == "CONFIDENCE_ALIGNMENT_MISMATCH"

    def test_low_confidence_strongly_aligned_is_warning(self):
        from backend.reality_conflicts import detect_confidence_alignment_mismatch
        conflicts = detect_confidence_alignment_mismatch(
            "CY", 0.2, "STRONGLY_ALIGNED", 3,
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "WARNING"

    def test_medium_confidence_no_conflict(self):
        from backend.reality_conflicts import detect_confidence_alignment_mismatch
        conflicts = detect_confidence_alignment_mismatch(
            "FR", 0.5, "DIVERGENT", 3,
        )
        assert len(conflicts) == 0

    def test_high_confidence_aligned_no_conflict(self):
        from backend.reality_conflicts import detect_confidence_alignment_mismatch
        conflicts = detect_confidence_alignment_mismatch(
            "DE", 0.9, "STRONGLY_ALIGNED", 5,
        )
        assert len(conflicts) == 0

    def test_zero_compared_no_conflict(self):
        from backend.reality_conflicts import detect_confidence_alignment_mismatch
        conflicts = detect_confidence_alignment_mismatch(
            "DE", 0.9, "DIVERGENT", 0,
        )
        assert len(conflicts) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.4: USABILITY-ALIGNMENT MISMATCH
# ═══════════════════════════════════════════════════════════════════════════


class TestUsabilityAlignmentMismatch:
    """Tests for decision usability vs empirical alignment conflicts."""

    def test_trusted_contradicted_is_critical(self):
        from backend.reality_conflicts import detect_usability_alignment_mismatch
        conflicts = detect_usability_alignment_mismatch(
            "DE", "TRUSTED_COMPARABLE", "EMPIRICALLY_CONTRADICTED",
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "CRITICAL"
        assert "USABILITY_ALIGNMENT_MISMATCH" == conflicts[0]["conflict_type"]

    def test_trusted_weak_is_error(self):
        from backend.reality_conflicts import detect_usability_alignment_mismatch
        conflicts = detect_usability_alignment_mismatch(
            "FR", "TRUSTED_COMPARABLE", "EMPIRICALLY_WEAK",
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "ERROR"

    def test_invalid_grounded_is_warning(self):
        from backend.reality_conflicts import detect_usability_alignment_mismatch
        conflicts = detect_usability_alignment_mismatch(
            "CY", "INVALID_FOR_COMPARISON", "EMPIRICALLY_GROUNDED",
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "WARNING"

    def test_trusted_grounded_no_conflict(self):
        from backend.reality_conflicts import detect_usability_alignment_mismatch
        conflicts = detect_usability_alignment_mismatch(
            "DE", "TRUSTED_COMPARABLE", "EMPIRICALLY_GROUNDED",
        )
        assert len(conflicts) == 0

    def test_none_usability_no_conflict(self):
        from backend.reality_conflicts import detect_usability_alignment_mismatch
        conflicts = detect_usability_alignment_mismatch(
            "DE", None, "EMPIRICALLY_GROUNDED",
        )
        assert len(conflicts) == 0

    def test_none_empirical_no_conflict(self):
        from backend.reality_conflicts import detect_usability_alignment_mismatch
        conflicts = detect_usability_alignment_mismatch(
            "DE", "TRUSTED_COMPARABLE", None,
        )
        assert len(conflicts) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.5: RANKING ELIGIBILITY DIVERGENCE
# ═══════════════════════════════════════════════════════════════════════════


class TestRankingEligibilityDivergence:
    """Tests for ranking-eligible countries with divergent alignment."""

    def test_ranking_eligible_divergent_is_error(self):
        from backend.reality_conflicts import detect_ranking_eligibility_divergence
        conflicts = detect_ranking_eligibility_divergence(
            "DE", True, "DIVERGENT", 4,
        )
        assert len(conflicts) == 1
        assert conflicts[0]["severity"] == "ERROR"
        assert conflicts[0]["conflict_type"] == "RANKING_ELIGIBILITY_DIVERGENCE"

    def test_not_eligible_divergent_no_conflict(self):
        from backend.reality_conflicts import detect_ranking_eligibility_divergence
        conflicts = detect_ranking_eligibility_divergence(
            "CY", False, "DIVERGENT", 3,
        )
        assert len(conflicts) == 0

    def test_eligible_aligned_no_conflict(self):
        from backend.reality_conflicts import detect_ranking_eligibility_divergence
        conflicts = detect_ranking_eligibility_divergence(
            "DE", True, "STRONGLY_ALIGNED", 5,
        )
        assert len(conflicts) == 0

    def test_zero_compared_no_conflict(self):
        from backend.reality_conflicts import detect_ranking_eligibility_divergence
        conflicts = detect_ranking_eligibility_divergence(
            "DE", True, "DIVERGENT", 0,
        )
        assert len(conflicts) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.6: FULL DETECTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectRealityConflicts:
    """Tests for the main detect_reality_conflicts() engine."""

    def _make_governance(
        self,
        tier: str = "FULLY_COMPARABLE",
        confidence: float = 0.8,
        ranking: bool = True,
    ) -> dict[str, Any]:
        return {
            "governance_tier": tier,
            "mean_axis_confidence": confidence,
            "ranking_eligible": ranking,
        }

    def _make_alignment(
        self,
        overall: str = "STRONGLY_ALIGNED",
        n_compared: int = 5,
        n_aligned: int = 4,
        n_divergent: int = 1,
    ) -> dict[str, Any]:
        return {
            "overall_alignment": overall,
            "n_axes_compared": n_compared,
            "n_axes_aligned": n_aligned,
            "n_axes_divergent": n_divergent,
        }

    def test_no_alignment_no_conflicts(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "DE",
            governance_result=self._make_governance(),
            alignment_result=None,
        )
        assert result["n_conflicts"] == 0
        assert result["conflicts"] == []
        assert result["country"] == "DE"
        assert "honesty_note" in result

    def test_consistent_state_no_conflicts(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "DE",
            governance_result=self._make_governance(),
            alignment_result=self._make_alignment(),
        )
        assert result["n_conflicts"] == 0
        assert result["has_critical"] is False

    def test_full_conflict_scenario(self):
        """FULLY_COMPARABLE + ranking_eligible + high confidence + DIVERGENT
        should produce multiple conflicts."""
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "DE",
            governance_result=self._make_governance(
                tier="FULLY_COMPARABLE",
                confidence=0.85,
                ranking=True,
            ),
            alignment_result=self._make_alignment(
                overall="DIVERGENT",
                n_compared=4,
                n_aligned=1,
                n_divergent=3,
            ),
        )
        # Should have:
        # 1. GOVERNANCE_ALIGNMENT_MISMATCH (CRITICAL)
        # 2. CONFIDENCE_ALIGNMENT_MISMATCH (ERROR)
        # 3. RANKING_ELIGIBILITY_DIVERGENCE (ERROR)
        assert result["n_conflicts"] >= 3
        assert result["has_critical"] is True
        assert result["n_critical"] >= 1
        assert result["n_errors"] >= 2

        conflict_types = {c["conflict_type"] for c in result["conflicts"]}
        assert "GOVERNANCE_ALIGNMENT_MISMATCH" in conflict_types
        assert "CONFIDENCE_ALIGNMENT_MISMATCH" in conflict_types
        assert "RANKING_ELIGIBILITY_DIVERGENCE" in conflict_types

    def test_usability_contradiction_detected(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "DE",
            governance_result=self._make_governance(),
            alignment_result=self._make_alignment(
                overall="STRONGLY_ALIGNED",
                n_compared=4,
            ),
            decision_usability={"decision_usability_class": "TRUSTED_COMPARABLE"},
            empirical_alignment={"empirical_class": "EMPIRICALLY_CONTRADICTED"},
        )
        conflict_types = {c["conflict_type"] for c in result["conflicts"]}
        assert "USABILITY_ALIGNMENT_MISMATCH" in conflict_types

    def test_result_structure(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "FR",
            governance_result=self._make_governance(),
        )
        required_keys = {
            "country", "n_conflicts", "n_warnings", "n_errors",
            "n_critical", "has_critical", "conflicts", "interpretation",
            "honesty_note",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_interpretation_no_conflicts(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "DE",
            governance_result=self._make_governance(),
        )
        assert "No reality conflicts" in result["interpretation"]

    def test_interpretation_critical(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "DE",
            governance_result=self._make_governance(),
            alignment_result=self._make_alignment(
                overall="DIVERGENT", n_compared=3,
            ),
        )
        if result["has_critical"]:
            assert "CRITICAL" in result["interpretation"]

    def test_inverse_conflict_non_comparable_aligned(self):
        from backend.reality_conflicts import detect_reality_conflicts
        result = detect_reality_conflicts(
            "CY",
            governance_result=self._make_governance(
                tier="NON_COMPARABLE", confidence=0.3, ranking=False,
            ),
            alignment_result=self._make_alignment(
                overall="STRONGLY_ALIGNED", n_compared=4,
            ),
        )
        # Should have a WARNING for NON_COMPARABLE + STRONGLY_ALIGNED
        assert result["n_warnings"] >= 1
        assert any(
            c["conflict_type"] == "GOVERNANCE_ALIGNMENT_MISMATCH"
            for c in result["conflicts"]
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.7: INVARIANT ENFORCEMENT (RC-001, RC-002, RC-003)
# ═══════════════════════════════════════════════════════════════════════════


class TestRealityConflictInvariants:
    """Tests for reality conflict invariants in invariants.py."""

    def test_reality_conflict_invariant_type_exists(self):
        from backend.invariants import InvariantType, VALID_INVARIANT_TYPES
        assert hasattr(InvariantType, "REALITY_CONFLICT")
        assert InvariantType.REALITY_CONFLICT == "REALITY_CONFLICT"
        assert "REALITY_CONFLICT" in VALID_INVARIANT_TYPES

    def test_reality_conflict_invariants_in_registry(self):
        from backend.invariants import INVARIANT_REGISTRY
        rc_ids = [
            inv["invariant_id"] for inv in INVARIANT_REGISTRY
            if inv["type"] == "REALITY_CONFLICT"
        ]
        assert "RC-001" in rc_ids
        assert "RC-002" in rc_ids
        assert "RC-003" in rc_ids

    def test_invariant_registry_count(self):
        from backend.invariants import INVARIANT_REGISTRY
        # 28 + 5 pipeline integrity + 4 runtime + 10 epistemic monotonicity
        assert len(INVARIANT_REGISTRY) == 47

    def test_rc001_fires_when_no_reality_block(self):
        """RC-001: High governance + DIVERGENT + no reality_conflicts block → CRITICAL."""
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 4,
                "n_axes_divergent": 3,
            },
            reality_conflicts_block=None,
        )
        rc001 = [v for v in violations if v["invariant_id"] == "RC-001"]
        assert len(rc001) == 1
        assert rc001[0]["severity"] == "CRITICAL"

    def test_rc001_passes_when_conflict_present(self):
        """RC-001: No violation when reality_conflicts block correctly contains the conflict."""
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 4,
                "n_axes_divergent": 3,
            },
            reality_conflicts_block={
                "conflicts": [
                    {"conflict_type": "GOVERNANCE_ALIGNMENT_MISMATCH"},
                    {"conflict_type": "RANKING_ELIGIBILITY_DIVERGENCE"},
                ],
            },
        )
        rc001 = [v for v in violations if v["invariant_id"] == "RC-001"]
        assert len(rc001) == 0

    def test_rc001_fires_when_conflict_missing_from_block(self):
        """RC-001: ERROR when block exists but doesn't contain the mismatch."""
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="FR",
            governance_result={
                "governance_tier": "PARTIALLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 3,
                "n_axes_divergent": 2,
            },
            reality_conflicts_block={
                "conflicts": [
                    {"conflict_type": "RANKING_ELIGIBILITY_DIVERGENCE"},
                    # Missing GOVERNANCE_ALIGNMENT_MISMATCH
                ],
            },
        )
        rc001 = [v for v in violations if v["invariant_id"] == "RC-001"]
        assert len(rc001) == 1
        assert rc001[0]["severity"] == "ERROR"

    def test_rc002_fires_when_ranking_divergent_no_block(self):
        """RC-002: ranking_eligible + DIVERGENT + no block → ERROR."""
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 4,
                "n_axes_divergent": 3,
            },
            reality_conflicts_block=None,
        )
        rc002 = [v for v in violations if v["invariant_id"] == "RC-002"]
        assert len(rc002) == 1
        assert rc002[0]["severity"] == "ERROR"

    def test_rc002_passes_when_red_present(self):
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 4,
                "n_axes_divergent": 3,
            },
            reality_conflicts_block={
                "conflicts": [
                    {"conflict_type": "GOVERNANCE_ALIGNMENT_MISMATCH"},
                    {"conflict_type": "RANKING_ELIGIBILITY_DIVERGENCE"},
                ],
            },
        )
        rc002 = [v for v in violations if v["invariant_id"] == "RC-002"]
        assert len(rc002) == 0

    def test_rc003_fires_trusted_majority_divergent_no_block(self):
        """RC-003: TRUSTED_COMPARABLE + majority divergent + no block → CRITICAL."""
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 4,
                "n_axes_divergent": 3,
            },
            decision_usability_class="TRUSTED_COMPARABLE",
            reality_conflicts_block=None,
        )
        rc003 = [v for v in violations if v["invariant_id"] == "RC-003"]
        assert len(rc003) == 1
        assert rc003[0]["severity"] == "CRITICAL"

    def test_rc_no_violations_when_aligned(self):
        """No RC violations when governance and alignment agree."""
        from backend.invariants import check_reality_conflict_invariants
        violations = check_reality_conflict_invariants(
            country="DE",
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
            },
            alignment_result={
                "overall_alignment": "STRONGLY_ALIGNED",
                "n_axes_compared": 5,
                "n_axes_divergent": 0,
            },
        )
        assert len(violations) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.8: EXPORT INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


class TestExportIntegration:
    """Tests for reality_conflicts wiring into export_snapshot.py."""

    def test_compute_reality_conflicts_helper_exists(self):
        from backend.export_snapshot import _compute_reality_conflicts
        assert callable(_compute_reality_conflicts)

    def test_compute_reality_conflicts_graceful_error(self):
        """Helper should not raise on bad input."""
        from backend.export_snapshot import _compute_reality_conflicts
        result = _compute_reality_conflicts(
            "INVALID",
            governance={},
        )
        # Should return structured result, not raise
        assert "country" in result
        assert "n_conflicts" in result or "error" in result

    def test_compute_reality_conflicts_normal(self):
        from backend.export_snapshot import _compute_reality_conflicts
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "mean_axis_confidence": 0.8,
            "ranking_eligible": True,
        }
        result = _compute_reality_conflicts("DE", gov)
        assert result["country"] == "DE"
        assert result["n_conflicts"] == 0

    def test_build_country_json_has_reality_conflicts_key(self):
        """build_country_json() must include 'reality_conflicts' in output."""
        from backend.export_snapshot import build_country_json
        # Need to construct minimal valid input
        # DE is a known EU27 country
        all_scores = {i: {"DE": 0.5} for i in range(1, 7)}
        result = build_country_json(
            country="DE",
            all_scores=all_scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2022-2024",
        )
        assert "reality_conflicts" in result
        rc = result["reality_conflicts"]
        assert "country" in rc
        assert "n_conflicts" in rc
        assert "conflicts" in rc

    def test_reality_conflicts_block_no_false_positives(self):
        """With all-aligned scores, reality_conflicts should be empty."""
        from backend.export_snapshot import build_country_json
        all_scores = {i: {"DE": 0.5} for i in range(1, 7)}
        result = build_country_json(
            country="DE",
            all_scores=all_scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2022-2024",
        )
        rc = result["reality_conflicts"]
        assert rc["n_conflicts"] == 0
        assert rc["conflicts"] == []


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3.9: ASSESS_COUNTRY_INVARIANTS INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


class TestAssessCountryInvariantsIntegration:
    """Tests that reality conflict invariants are wired into assess_country_invariants."""

    def test_reality_conflicts_block_param_accepted(self):
        """assess_country_invariants accepts reality_conflicts_block param."""
        from backend.invariants import assess_country_invariants
        # Should not raise
        result = assess_country_invariants(
            country="DE",
            axis_scores={i: 0.5 for i in range(1, 7)},
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "n_producer_inverted_axes": 0,
                "producer_inverted_axes": [],
                "mean_axis_confidence": 0.8,
                "composite_defensible": True,
                "cross_country_comparable": True,
                "n_axes_with_data": 6,
                "n_low_confidence_axes": 0,
                "axis_confidences": {},
                "structural_limitations": [],
            },
            reality_conflicts_block={
                "conflicts": [],
                "n_conflicts": 0,
            },
        )
        assert "n_violations" in result

    def test_rc_invariants_fire_in_assess(self):
        """RC invariants fire through assess_country_invariants when conditions met."""
        from backend.invariants import assess_country_invariants
        result = assess_country_invariants(
            country="DE",
            axis_scores={i: 0.5 for i in range(1, 7)},
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "n_producer_inverted_axes": 0,
                "producer_inverted_axes": [],
                "mean_axis_confidence": 0.8,
                "composite_defensible": True,
                "cross_country_comparable": True,
                "n_axes_with_data": 6,
                "n_low_confidence_axes": 0,
                "axis_confidences": {},
                "structural_limitations": [],
            },
            alignment_result={
                "overall_alignment": "DIVERGENT",
                "n_axes_compared": 4,
                "n_axes_divergent": 3,
                "n_axes_aligned": 1,
                "weighted_alignment_score": {
                    "weighted_score": 0.3,
                    "n_benchmarks_scored": 2,
                    "weight_composition": {
                        "STRUCTURAL": 1.0,
                        "HIGH_CONFIDENCE": 0.7,
                        "SUPPORTING": 0.4,
                    },
                    "tier_counts": {
                        "structural": 0,
                        "high_confidence": 0,
                        "supporting": 0,
                    },
                },
                "authority_conflicts": [],
                "alignment_confidence": 0.5,
            },
            reality_conflicts_block=None,  # no block → should fire RC-001
        )
        rc_violations = [
            v for v in result["violations"]
            if v["invariant_id"].startswith("RC-")
        ]
        assert len(rc_violations) > 0
        assert any(v["invariant_id"] == "RC-001" for v in rc_violations)

    def test_no_rc_violations_without_alignment(self):
        """No RC violations when alignment_result is None (backward compatible)."""
        from backend.invariants import assess_country_invariants
        result = assess_country_invariants(
            country="DE",
            axis_scores={i: 0.5 for i in range(1, 7)},
            governance_result={
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "n_producer_inverted_axes": 0,
                "producer_inverted_axes": [],
                "mean_axis_confidence": 0.8,
                "composite_defensible": True,
                "cross_country_comparable": True,
                "n_axes_with_data": 6,
                "n_low_confidence_axes": 0,
                "axis_confidences": {},
                "structural_limitations": [],
            },
            alignment_result=None,
        )
        rc_violations = [
            v for v in result["violations"]
            if v["invariant_id"].startswith("RC-")
        ]
        assert len(rc_violations) == 0
