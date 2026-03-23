"""
tests/test_systems_hardening.py — Tests for the final 3-system hardening layer

SYSTEM 1: Structural Invariants Engine (backend.invariants)
SYSTEM 2: Full Provenance Trace System (backend.provenance)
SYSTEM 3: Snapshot Differential Analysis (backend.snapshot_diff)

Coverage:
    - All invariant types (CROSS_AXIS, GOVERNANCE, TEMPORAL)
    - All severity levels (WARNING, ERROR, CRITICAL)
    - Provenance record construction and validation
    - Snapshot diff computation and root cause analysis
    - Edge cases, boundary conditions, adversarial inputs
    - Integration between systems (critical invariant → usability downgrade)
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM 1: INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════

class TestInvariantRegistry:
    """Verify the invariant registry is structurally sound."""

    def test_registry_not_empty(self):
        from backend.invariants import INVARIANT_REGISTRY
        assert len(INVARIANT_REGISTRY) > 0

    def test_all_registry_entries_have_required_fields(self):
        from backend.invariants import INVARIANT_REGISTRY
        for entry in INVARIANT_REGISTRY:
            assert "invariant_id" in entry
            assert "type" in entry
            assert "name" in entry
            assert "description" in entry

    def test_all_invariant_ids_unique(self):
        from backend.invariants import INVARIANT_REGISTRY
        ids = [e["invariant_id"] for e in INVARIANT_REGISTRY]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_all_types_valid(self):
        from backend.invariants import INVARIANT_REGISTRY, VALID_INVARIANT_TYPES
        for entry in INVARIANT_REGISTRY:
            assert entry["type"] in VALID_INVARIANT_TYPES

    def test_registry_getter_returns_copy(self):
        from backend.invariants import get_invariant_registry
        reg1 = get_invariant_registry()
        reg2 = get_invariant_registry()
        assert reg1 == reg2
        assert reg1 is not reg2  # Must be a copy

    def test_registry_has_all_three_types(self):
        from backend.invariants import INVARIANT_REGISTRY, InvariantType
        types = {e["type"] for e in INVARIANT_REGISTRY}
        assert InvariantType.CROSS_AXIS in types
        assert InvariantType.GOVERNANCE in types
        assert InvariantType.TEMPORAL in types


class TestCrossAxisInvariants:
    """Test cross-axis structural invariant checks."""

    def test_no_violation_normal_data(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        violations = check_cross_axis_invariants("DE", scores)
        assert violations == []

    def test_insufficient_data_skips_checks(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.4, 2: None, 3: None, 4: None, 5: None, 6: None}
        violations = check_cross_axis_invariants("DE", scores)
        assert violations == []

    def test_ca001_logistics_divergence(self):
        from backend.invariants import check_cross_axis_invariants
        # Logistics high, goods-based axes very low
        scores = {1: 0.5, 2: 0.02, 3: 0.05, 4: 0.4, 5: 0.03, 6: 0.45}
        violations = check_cross_axis_invariants("DE", scores)
        ca001 = [v for v in violations if v["invariant_id"] == "CA-001"]
        assert len(ca001) == 1
        assert ca001[0]["severity"] == "WARNING"
        assert ca001[0]["type"] == "CROSS_AXIS"

    def test_ca001_no_divergence_normal_goods(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.5, 2: 0.35, 3: 0.30, 4: 0.4, 5: 0.38, 6: 0.32}
        violations = check_cross_axis_invariants("DE", scores)
        ca001 = [v for v in violations if v["invariant_id"] == "CA-001"]
        assert ca001 == []

    def test_ca002_producer_high_import(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.5, 2: 0.75, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        gov = {"producer_inverted_axes": [2, 4]}
        violations = check_cross_axis_invariants("US", scores, gov)
        ca002 = [v for v in violations if v["invariant_id"] == "CA-002"]
        assert len(ca002) == 1  # axis 2 > 0.60
        assert ca002[0]["severity"] == "ERROR"
        assert ca002[0]["evidence"]["axis_id"] == 2

    def test_ca002_no_violation_low_score(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.5, 2: 0.30, 3: 0.3, 4: 0.25, 5: 0.45, 6: 0.35}
        gov = {"producer_inverted_axes": [2, 4]}
        violations = check_cross_axis_invariants("US", scores, gov)
        ca002 = [v for v in violations if v["invariant_id"] == "CA-002"]
        assert ca002 == []

    def test_ca003_low_majority_high_composite(self):
        from backend.invariants import check_cross_axis_invariants
        # 4 axes < 0.15, two axes high enough to push mean > 0.25
        # Mean = (0.05 + 0.10 + 0.02 + 0.03 + 0.60 + 0.90) / 6 = 0.2833
        scores = {1: 0.05, 2: 0.10, 3: 0.02, 4: 0.03, 5: 0.60, 6: 0.90}
        violations = check_cross_axis_invariants("DE", scores)
        ca003 = [v for v in violations if v["invariant_id"] == "CA-003"]
        assert len(ca003) == 1
        assert ca003[0]["severity"] == "ERROR"
        assert ca003[0]["evidence"]["n_low_axes"] == 4

    def test_ca003_no_violation_normal_spread(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.3, 2: 0.4, 3: 0.5, 4: 0.35, 5: 0.45, 6: 0.38}
        violations = check_cross_axis_invariants("DE", scores)
        ca003 = [v for v in violations if v["invariant_id"] == "CA-003"]
        assert ca003 == []

    def test_ca004_uniform_scores(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.50, 2: 0.50, 3: 0.50, 4: 0.50, 5: 0.50, 6: 0.51}
        violations = check_cross_axis_invariants("DE", scores)
        ca004 = [v for v in violations if v["invariant_id"] == "CA-004"]
        assert len(ca004) == 1
        assert ca004[0]["severity"] == "WARNING"

    def test_ca004_no_violation_sufficient_spread(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.50, 2: 0.50, 3: 0.50, 4: 0.50, 5: 0.50, 6: 0.53}
        violations = check_cross_axis_invariants("DE", scores)
        ca004 = [v for v in violations if v["invariant_id"] == "CA-004"]
        assert ca004 == []

    def test_violation_record_structure(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.50, 2: 0.50, 3: 0.50, 4: 0.50, 5: 0.50, 6: 0.51}
        violations = check_cross_axis_invariants("DE", scores)
        assert len(violations) >= 1
        v = violations[0]
        assert "invariant_id" in v
        assert "type" in v
        assert "severity" in v
        assert "description" in v
        assert "affected_country" in v
        assert "evidence" in v
        assert v["affected_country"] == "DE"


class TestGovernanceInvariants:
    """Test governance consistency invariant checks."""

    def _make_gov(self, **kwargs) -> dict[str, Any]:
        """Build a governance result with sane defaults."""
        base = {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.75,
            "axis_confidences": [],
        }
        base.update(kwargs)
        return base

    def test_no_violation_consistent_governance(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov()
        violations = check_governance_invariants("DE", gov)
        assert violations == []

    def test_gov001_ranking_eligible_wrong_tier(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="LOW_CONFIDENCE",
            ranking_eligible=True,
        )
        violations = check_governance_invariants("DE", gov)
        gov001 = [v for v in violations if v["invariant_id"] == "GOV-001"]
        assert len(gov001) >= 1
        assert gov001[0]["severity"] == "CRITICAL"

    def test_gov001_no_violation_partially_comparable(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="PARTIALLY_COMPARABLE",
            ranking_eligible=True,
        )
        violations = check_governance_invariants("DE", gov)
        gov001 = [v for v in violations if v["invariant_id"] == "GOV-001"]
        assert gov001 == []

    def test_gov002_comparable_excessive_inversions(self):
        from backend.invariants import check_governance_invariants
        from backend.governance import MAX_INVERTED_AXES_FOR_COMPARABLE
        gov = self._make_gov(
            cross_country_comparable=True,
            n_producer_inverted_axes=MAX_INVERTED_AXES_FOR_COMPARABLE + 1,
        )
        violations = check_governance_invariants("US", gov)
        gov002 = [v for v in violations if v["invariant_id"] == "GOV-002"]
        assert len(gov002) == 1
        assert gov002[0]["severity"] == "CRITICAL"

    def test_gov003_low_confidence_ranked(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="LOW_CONFIDENCE",
            ranking_eligible=True,
        )
        violations = check_governance_invariants("DE", gov)
        gov003 = [v for v in violations if v["invariant_id"] == "GOV-003"]
        assert len(gov003) >= 1
        assert gov003[0]["severity"] == "CRITICAL"

    def test_gov003_non_comparable_ranked(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="NON_COMPARABLE",
            ranking_eligible=True,
        )
        violations = check_governance_invariants("DE", gov)
        gov003 = [v for v in violations if v["invariant_id"] == "GOV-003"]
        assert len(gov003) >= 1

    def test_gov004_composite_defensible_non_comparable(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="NON_COMPARABLE",
            ranking_eligible=False,
            cross_country_comparable=False,
            composite_defensible=True,
        )
        violations = check_governance_invariants("DE", gov)
        gov004 = [v for v in violations if v["invariant_id"] == "GOV-004"]
        assert len(gov004) == 1
        assert gov004[0]["severity"] == "CRITICAL"

    def test_gov005_confidence_tier_mismatch(self):
        from backend.invariants import check_governance_invariants
        from backend.governance import MIN_MEAN_CONFIDENCE_FOR_RANKING
        gov = self._make_gov(
            governance_tier="FULLY_COMPARABLE",
            mean_axis_confidence=MIN_MEAN_CONFIDENCE_FOR_RANKING - 0.10,
        )
        violations = check_governance_invariants("DE", gov)
        gov005 = [v for v in violations if v["invariant_id"] == "GOV-005"]
        assert len(gov005) == 1
        assert gov005[0]["severity"] == "ERROR"

    def test_gov006_sanctions_high_tier(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="FULLY_COMPARABLE",
            axis_confidences=[
                {"axis_id": 1, "penalties_applied": [{"flag": "SANCTIONS_DISTORTION", "penalty_amount": 0.50}]},
            ],
        )
        violations = check_governance_invariants("RU", gov)
        gov006 = [v for v in violations if v["invariant_id"] == "GOV-006"]
        assert len(gov006) == 1
        assert gov006[0]["severity"] == "CRITICAL"

    def test_gov006_no_violation_low_confidence(self):
        from backend.invariants import check_governance_invariants
        gov = self._make_gov(
            governance_tier="LOW_CONFIDENCE",
            ranking_eligible=False,
            cross_country_comparable=False,
            axis_confidences=[
                {"axis_id": 1, "penalties_applied": [{"flag": "SANCTIONS_DISTORTION", "penalty_amount": 0.50}]},
            ],
        )
        violations = check_governance_invariants("RU", gov)
        gov006 = [v for v in violations if v["invariant_id"] == "GOV-006"]
        assert gov006 == []


class TestTemporalInvariants:
    """Test temporal/snapshot invariant checks."""

    def _make_snapshot(
        self,
        composite: float = 0.5,
        rank: int = 10,
        axes: list[dict] | None = None,
        gov_tier: str = "FULLY_COMPARABLE",
        mean_conf: float = 0.7,
        n_inverted: int = 0,
    ) -> dict[str, Any]:
        if axes is None:
            axes = [
                {"axis_id": i, "score": 0.5}
                for i in range(1, 7)
            ]
        return {
            "isi_composite": composite,
            "rank": rank,
            "axes": axes,
            "governance": {
                "governance_tier": gov_tier,
                "mean_axis_confidence": mean_conf,
                "n_producer_inverted_axes": n_inverted,
            },
        }

    def test_no_violation_identical_snapshots(self):
        from backend.invariants import check_temporal_invariants
        snap = self._make_snapshot()
        violations = check_temporal_invariants("DE", snap, snap)
        assert violations == []

    def test_temp001_large_rank_shift_without_input_change(self):
        from backend.invariants import check_temporal_invariants
        snap_a = self._make_snapshot(composite=0.50, rank=10)
        snap_b = self._make_snapshot(composite=0.51, rank=2)
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        temp001 = [v for v in violations if v["invariant_id"] == "TEMP-001"]
        assert len(temp001) == 1
        assert temp001[0]["severity"] == "ERROR"
        assert temp001[0]["evidence"]["rank_shift"] == 8

    def test_temp001_no_violation_small_rank_shift(self):
        from backend.invariants import check_temporal_invariants
        snap_a = self._make_snapshot(rank=10)
        snap_b = self._make_snapshot(rank=8)
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        temp001 = [v for v in violations if v["invariant_id"] == "TEMP-001"]
        assert temp001 == []

    def test_temp002_composite_change_without_axis_change(self):
        from backend.invariants import check_temporal_invariants
        snap_a = self._make_snapshot(composite=0.40)
        snap_b = self._make_snapshot(composite=0.50)
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        temp002 = [v for v in violations if v["invariant_id"] == "TEMP-002"]
        assert len(temp002) == 1
        assert temp002[0]["severity"] == "CRITICAL"

    def test_temp002_no_violation_axes_moved(self):
        from backend.invariants import check_temporal_invariants
        snap_a = self._make_snapshot(
            composite=0.40,
            axes=[
                {"axis_id": 1, "score": 0.30}, {"axis_id": 2, "score": 0.50},
                {"axis_id": 3, "score": 0.40}, {"axis_id": 4, "score": 0.40},
                {"axis_id": 5, "score": 0.40}, {"axis_id": 6, "score": 0.40},
            ],
        )
        snap_b = self._make_snapshot(
            composite=0.50,
            axes=[
                {"axis_id": 1, "score": 0.30}, {"axis_id": 2, "score": 0.80},
                {"axis_id": 3, "score": 0.40}, {"axis_id": 4, "score": 0.40},
                {"axis_id": 5, "score": 0.40}, {"axis_id": 6, "score": 0.40},
            ],
        )
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        temp002 = [v for v in violations if v["invariant_id"] == "TEMP-002"]
        assert temp002 == []

    def test_temp003_governance_tier_change_without_structural_cause(self):
        from backend.invariants import check_temporal_invariants
        snap_a = self._make_snapshot(gov_tier="FULLY_COMPARABLE")
        snap_b = self._make_snapshot(gov_tier="LOW_CONFIDENCE")
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        temp003 = [v for v in violations if v["invariant_id"] == "TEMP-003"]
        assert len(temp003) == 1
        assert temp003[0]["severity"] == "ERROR"

    def test_temp003_no_violation_confidence_delta(self):
        from backend.invariants import check_temporal_invariants
        snap_a = self._make_snapshot(gov_tier="FULLY_COMPARABLE", mean_conf=0.75)
        snap_b = self._make_snapshot(gov_tier="LOW_CONFIDENCE", mean_conf=0.30)
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        temp003 = [v for v in violations if v["invariant_id"] == "TEMP-003"]
        assert temp003 == []


class TestUnifiedInvariantAssessment:
    """Test the unified invariant assessment function."""

    def test_assess_country_invariants_clean(self):
        from backend.invariants import assess_country_invariants
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.75,
            "axis_confidences": [],
        }
        result = assess_country_invariants("DE", scores, gov)
        assert result["country"] == "DE"
        assert result["n_violations"] == 0
        assert result["has_critical"] is False
        assert "honesty_note" in result

    def test_assess_country_invariants_with_violations(self):
        from backend.invariants import assess_country_invariants
        scores = {1: 0.05, 2: 0.10, 3: 0.02, 4: 0.03, 5: 0.01, 6: 0.90}
        gov = {
            "governance_tier": "LOW_CONFIDENCE",
            "ranking_eligible": True,  # Inconsistent!
            "cross_country_comparable": False,
            "composite_defensible": False,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.35,
            "axis_confidences": [],
        }
        result = assess_country_invariants("DE", scores, gov)
        assert result["n_violations"] > 0
        assert result["has_critical"] is True

    def test_assess_all_invariants(self):
        from backend.invariants import assess_all_invariants
        all_scores = {i: {"DE": 0.5, "FR": 0.4} for i in range(1, 7)}
        gov_results = {
            "DE": {
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "cross_country_comparable": True,
                "composite_defensible": True,
                "n_producer_inverted_axes": 0,
                "mean_axis_confidence": 0.75,
                "axis_confidences": [],
            },
            "FR": {
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "cross_country_comparable": True,
                "composite_defensible": True,
                "n_producer_inverted_axes": 0,
                "mean_axis_confidence": 0.75,
                "axis_confidences": [],
            },
        }
        results = assess_all_invariants(all_scores, gov_results)
        assert "DE" in results
        assert "FR" in results

    def test_get_invariant_summary(self):
        from backend.invariants import assess_all_invariants, get_invariant_summary
        all_scores = {i: {"DE": 0.5} for i in range(1, 7)}
        gov_results = {
            "DE": {
                "governance_tier": "FULLY_COMPARABLE",
                "ranking_eligible": True,
                "cross_country_comparable": True,
                "composite_defensible": True,
                "n_producer_inverted_axes": 0,
                "mean_axis_confidence": 0.75,
                "axis_confidences": [],
            },
        }
        results = assess_all_invariants(all_scores, gov_results)
        summary = get_invariant_summary(results)
        assert "total_countries_assessed" in summary
        assert "total_violations" in summary
        assert "system_consistent" in summary
        assert "honesty_note" in summary

    def test_should_downgrade_usability_critical(self):
        from backend.invariants import should_downgrade_usability
        result_with_critical = {"has_critical": True, "n_critical": 2}
        assert should_downgrade_usability(result_with_critical) is True

    def test_should_not_downgrade_usability_no_critical(self):
        from backend.invariants import should_downgrade_usability
        result_clean = {"has_critical": False, "n_critical": 0}
        assert should_downgrade_usability(result_clean) is False


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM 2: PROVENANCE
# ═══════════════════════════════════════════════════════════════════════════

class TestTransformationTypes:
    """Verify transformation type constants."""

    def test_all_types_are_strings(self):
        from backend.provenance import VALID_TRANSFORMATION_TYPES
        for t in VALID_TRANSFORMATION_TYPES:
            assert isinstance(t, str)

    def test_minimum_types_present(self):
        from backend.provenance import TransformationType
        assert hasattr(TransformationType, "RAW_INGEST")
        assert hasattr(TransformationType, "COMPOSITE_COMPUTATION")
        assert hasattr(TransformationType, "GOVERNANCE_ASSESSMENT")
        assert hasattr(TransformationType, "INVARIANT_CHECK")


class TestAxisProvenance:
    """Test axis-level provenance trace construction."""

    def test_basic_axis_provenance(self):
        from backend.provenance import build_axis_provenance
        prov = build_axis_provenance(
            country="DE",
            axis_id=1,
            score=0.45,
            year=2024,
            data_window="2022–2024",
            methodology_version="v1.0",
        )
        assert prov["country"] == "DE"
        assert prov["axis_id"] == 1
        assert prov["score"] == 0.45
        assert prov["is_complete"] is True
        assert "source_data" in prov
        assert "transformation_chain" in prov
        assert len(prov["transformation_chain"]) >= 2  # RAW_INGEST + NORMALIZATION

    def test_axis_provenance_none_score(self):
        from backend.provenance import build_axis_provenance
        prov = build_axis_provenance(
            country="DE", axis_id=6, score=None,
            year=2024, data_window="2022–2024",
            methodology_version="v1.0",
        )
        assert prov["score"] is None
        assert prov["is_complete"] is False

    def test_axis_provenance_with_severity(self):
        from backend.provenance import build_axis_provenance
        sev = {"flags": ["SINGLE_CHANNEL_A", "TEMPORAL_MISMATCH"]}
        prov = build_axis_provenance(
            country="FR", axis_id=2, score=0.55,
            year=2024, data_window="2022–2024",
            methodology_version="v1.0",
            severity_result=sev,
        )
        assert any(
            step["step"] == "SEVERITY_ASSESSMENT"
            for step in prov["transformation_chain"]
        )
        assert any("SEVERITY_FLAG" in r for r in prov["rules_applied"])

    def test_axis_provenance_with_governance_confidence(self):
        from backend.provenance import build_axis_provenance
        gov_conf = {
            "axis_id": 2,
            "penalties_applied": [
                {"flag": "PRODUCER_INVERSION", "penalty_amount": 0.30},
            ],
            "is_producer_inverted": True,
        }
        prov = build_axis_provenance(
            country="US", axis_id=2, score=0.40,
            year=2024, data_window="2022–2024",
            methodology_version="v1.0",
            governance_axis_confidence=gov_conf,
        )
        assert any(
            step["step"] == "CONFIDENCE_PENALTY"
            for step in prov["transformation_chain"]
        )
        assert any(
            step["step"] == "PRODUCER_INVERSION"
            for step in prov["transformation_chain"]
        )
        assert "PRODUCER_INVERSION_REGISTRY" in prov["rules_applied"]
        assert len(prov["adjustments"]) >= 1
        assert prov["adjustments"][0]["type"] == "confidence_penalty"

    def test_axis_provenance_source_data(self):
        from backend.provenance import build_axis_provenance
        prov = build_axis_provenance(
            country="AT", axis_id=3, score=0.6,
            year=2024, data_window="2022–2024",
            methodology_version="v1.0",
        )
        src = prov["source_data"]
        assert src["country"] == "AT"
        assert src["axis_id"] == 3
        assert src["year"] == 2024


class TestCompositeProvenance:
    """Test composite-level provenance trace construction."""

    def test_basic_composite_provenance(self):
        from backend.provenance import build_composite_provenance
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        composite = sum(scores.values()) / len(scores)
        prov = build_composite_provenance(
            country="DE",
            composite_score=composite,
            axis_scores=scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
        )
        assert prov["country"] == "DE"
        assert prov["composite_score"] == composite
        assert prov["is_complete"] is True
        assert prov["source_data"]["n_contributing_axes"] == 6

    def test_composite_provenance_with_governance(self):
        from backend.provenance import build_composite_provenance
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        gov = {"governance_tier": "FULLY_COMPARABLE"}
        prov = build_composite_provenance(
            country="DE",
            composite_score=0.43,
            axis_scores=scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
            governance_result=gov,
        )
        assert any("GOVERNANCE_TIER:" in r for r in prov["rules_applied"])

    def test_composite_provenance_with_falsification(self):
        from backend.provenance import build_composite_provenance
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        falsif = {
            "falsification_flag": "CONSISTENT",
            "checks": [{"check_id": "STRUCTURAL_1"}],
        }
        prov = build_composite_provenance(
            country="DE",
            composite_score=0.43,
            axis_scores=scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
            falsification_result=falsif,
        )
        assert any("FALSIFICATION:" in r for r in prov["rules_applied"])
        assert any("FALSIFICATION_CHECK:" in r for r in prov["rules_applied"])

    def test_composite_provenance_missing_axes(self):
        from backend.provenance import build_composite_provenance
        scores = {1: 0.4, 2: None, 3: 0.3, 4: None, 5: 0.45, 6: None}
        prov = build_composite_provenance(
            country="DE",
            composite_score=None,
            axis_scores=scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
        )
        assert prov["composite_score"] is None
        assert prov["is_complete"] is False
        assert prov["source_data"]["n_contributing_axes"] == 3


class TestGovernanceProvenance:
    """Test governance provenance trace construction."""

    def test_governance_provenance(self):
        from backend.provenance import build_governance_provenance
        gov = {
            "governance_tier": "PARTIALLY_COMPARABLE",
            "governance_interpretation": "Moderate confidence across axes",
            "structural_limitations": ["PRODUCER_INVERSION", "LOGISTICS_PROXY"],
            "n_axes_with_data": 6,
            "mean_axis_confidence": 0.55,
            "n_producer_inverted_axes": 2,
        }
        prov = build_governance_provenance("US", gov)
        assert prov["governance_tier"] == "PARTIALLY_COMPARABLE"
        assert any("GOVERNANCE_TIER_RESULT" in r for r in prov["rules_applied"])
        assert any("STRUCTURAL_LIMITATION" in r for r in prov["rules_applied"])
        assert len(prov["thresholds_used"]) > 0


class TestUsabilityProvenance:
    """Test usability class provenance."""

    def test_usability_provenance_basic(self):
        from backend.provenance import build_usability_provenance
        prov = build_usability_provenance(
            country="DE",
            usability_class="TRUSTED_COMPARABLE",
        )
        assert prov["usability_class"] == "TRUSTED_COMPARABLE"
        assert any("USABILITY_CLASS" in r for r in prov["rules_applied"])

    def test_usability_provenance_with_invariant_downgrade(self):
        from backend.provenance import build_usability_provenance
        inv = {"n_critical": 3}
        prov = build_usability_provenance(
            country="DE",
            usability_class="STRUCTURALLY_LIMITED",
            invariant_result=inv,
        )
        assert any("INVARIANT_DOWNGRADE" in r for r in prov["rules_applied"])


class TestCountryProvenance:
    """Test full country provenance bundle."""

    def test_full_provenance_bundle(self):
        from backend.provenance import build_country_provenance
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        composite = sum(scores.values()) / len(scores)
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "governance_interpretation": "High confidence",
            "structural_limitations": [],
            "n_axes_with_data": 6,
            "mean_axis_confidence": 0.75,
            "n_producer_inverted_axes": 0,
        }
        prov = build_country_provenance(
            country="DE",
            axis_scores=scores,
            composite_score=composite,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
            governance_result=gov,
            usability_class="TRUSTED_COMPARABLE",
        )
        assert prov["country"] == "DE"
        assert prov["provenance_version"] == "1.0"
        assert len(prov["axes"]) == 6
        assert prov["composite"] is not None
        assert prov["governance"] is not None
        assert prov["usability"] is not None
        assert prov["completeness"]["n_axes_traced"] == 6
        assert prov["completeness"]["n_complete"] == 6
        assert "honesty_note" in prov

    def test_provenance_missing_axes(self):
        from backend.provenance import build_country_provenance
        scores = {1: 0.4, 2: None, 3: 0.3, 4: None, 5: None, 6: None}
        prov = build_country_provenance(
            country="DE",
            axis_scores=scores,
            composite_score=None,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
        )
        assert prov["completeness"]["n_complete"] == 2


class TestProvenanceValidation:
    """Test provenance validation."""

    def test_valid_provenance(self):
        from backend.provenance import build_country_provenance, validate_provenance
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        prov = build_country_provenance(
            country="DE",
            axis_scores=scores,
            composite_score=0.43,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
        )
        validation = validate_provenance(prov)
        assert validation["is_valid"] is True
        assert validation["missing_fields"] == []
        assert validation["n_axes_traced"] == 6

    def test_invalid_provenance_missing_country(self):
        from backend.provenance import validate_provenance
        prov = {
            "provenance_version": "1.0",
            "axes": {},
            "composite": {},
        }
        validation = validate_provenance(prov)
        assert validation["is_valid"] is False
        assert "country" in validation["missing_fields"]

    def test_invalid_provenance_missing_composite(self):
        from backend.provenance import validate_provenance
        prov = {
            "country": "DE",
            "provenance_version": "1.0",
            "axes": {1: {"source_data": {}, "transformation_chain": []}},
        }
        validation = validate_provenance(prov)
        assert validation["is_valid"] is False
        assert "composite" in validation["missing_fields"]


# ═══════════════════════════════════════════════════════════════════════════
# SYSTEM 3: SNAPSHOT DIFF
# ═══════════════════════════════════════════════════════════════════════════

class TestChangeType:
    """Verify change type constants."""

    def test_all_types_are_strings(self):
        from backend.snapshot_diff import VALID_CHANGE_TYPES
        for t in VALID_CHANGE_TYPES:
            assert isinstance(t, str)

    def test_expected_types_present(self):
        from backend.snapshot_diff import ChangeType
        assert ChangeType.DATA_CHANGE == "DATA_CHANGE"
        assert ChangeType.METHODOLOGY_CHANGE == "METHODOLOGY_CHANGE"
        assert ChangeType.GOVERNANCE_CHANGE == "GOVERNANCE_CHANGE"
        assert ChangeType.NO_CHANGE == "NO_CHANGE"


class TestDiffCountry:
    """Test per-country diff computation."""

    def _make_entry(
        self,
        country: str = "DE",
        composite: float = 0.45,
        rank: int = 10,
        tier: str = "FULLY_COMPARABLE",
        usability: str = "TRUSTED_COMPARABLE",
    ) -> dict[str, Any]:
        return {
            "country": country,
            "isi_composite": composite,
            "rank": rank,
            "governance_tier": tier,
            "decision_usability_class": usability,
        }

    def test_no_change(self):
        from backend.snapshot_diff import diff_country, ChangeType
        entry = self._make_entry()
        result = diff_country("DE", entry, entry)
        assert result["status"] == "UNCHANGED"
        assert ChangeType.NO_CHANGE in result["change_types"]
        assert result["composite_delta"] == 0
        assert result["rank_delta"] == 0

    def test_composite_change(self):
        from backend.snapshot_diff import diff_country, ChangeType
        entry_a = self._make_entry(composite=0.40)
        entry_b = self._make_entry(composite=0.50)
        detail_a = {"axes": [{"axis_id": 1, "score": 0.30}, {"axis_id": 2, "score": 0.50}]}
        detail_b = {"axes": [{"axis_id": 1, "score": 0.40}, {"axis_id": 2, "score": 0.60}]}
        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        assert result["status"] == "CHANGED"
        assert ChangeType.DATA_CHANGE in result["change_types"]
        assert result["composite_delta"] == 0.10

    def test_rank_change(self):
        from backend.snapshot_diff import diff_country
        entry_a = self._make_entry(rank=5)
        entry_b = self._make_entry(rank=12)
        result = diff_country("DE", entry_a, entry_b)
        assert result["rank_delta"] == 7

    def test_governance_change(self):
        from backend.snapshot_diff import diff_country, ChangeType
        entry_a = self._make_entry(tier="FULLY_COMPARABLE")
        entry_b = self._make_entry(tier="LOW_CONFIDENCE")
        result = diff_country("DE", entry_a, entry_b)
        assert result["governance_change"]["changed"] is True
        assert ChangeType.GOVERNANCE_CHANGE in result["change_types"]

    def test_usability_change(self):
        from backend.snapshot_diff import diff_country
        entry_a = self._make_entry(usability="TRUSTED_COMPARABLE")
        entry_b = self._make_entry(usability="STRUCTURALLY_LIMITED")
        result = diff_country("DE", entry_a, entry_b)
        assert result["usability_change"]["changed"] is True

    def test_country_added(self):
        from backend.snapshot_diff import diff_country
        entry_b = self._make_entry()
        result = diff_country("DE", None, entry_b)
        assert result["status"] == "ADDED"

    def test_country_removed(self):
        from backend.snapshot_diff import diff_country
        entry_a = self._make_entry()
        result = diff_country("DE", entry_a, None)
        assert result["status"] == "REMOVED"

    def test_methodology_change_detected(self):
        from backend.snapshot_diff import diff_country, ChangeType
        entry = self._make_entry()
        result = diff_country(
            "DE", entry, entry,
            methodology_a="v1.0",
            methodology_b="v2.0",
        )
        assert ChangeType.METHODOLOGY_CHANGE in result["change_types"]

    def test_axis_deltas_computed(self):
        from backend.snapshot_diff import diff_country
        entry_a = self._make_entry()
        entry_b = self._make_entry()
        detail_a = {"axes": [
            {"axis_id": 1, "score": 0.30},
            {"axis_id": 2, "score": 0.50},
        ]}
        detail_b = {"axes": [
            {"axis_id": 1, "score": 0.35},
            {"axis_id": 2, "score": 0.50},
        ]}
        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        assert 1 in result["axis_deltas"]
        assert result["axis_deltas"][1]["delta"] == 0.05
        assert result["axis_deltas"][2]["delta"] == 0

    def test_root_causes_generated(self):
        from backend.snapshot_diff import diff_country
        entry_a = self._make_entry(composite=0.40, tier="FULLY_COMPARABLE")
        entry_b = self._make_entry(composite=0.50, tier="LOW_CONFIDENCE")
        detail_a = {"axes": [{"axis_id": 1, "score": 0.30}]}
        detail_b = {"axes": [{"axis_id": 1, "score": 0.40}]}
        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        assert len(result["root_causes"]) > 0


class TestCompareSnapshots:
    """Test full snapshot comparison."""

    def _make_isi(
        self,
        methodology: str = "v1.0",
        year: int = 2024,
        countries: list[dict] | None = None,
    ) -> dict[str, Any]:
        if countries is None:
            countries = [
                {"country": "DE", "isi_composite": 0.45, "rank": 1,
                 "governance_tier": "FULLY_COMPARABLE",
                 "decision_usability_class": "TRUSTED_COMPARABLE"},
                {"country": "FR", "isi_composite": 0.42, "rank": 2,
                 "governance_tier": "FULLY_COMPARABLE",
                 "decision_usability_class": "TRUSTED_COMPARABLE"},
            ]
        return {
            "methodology_version": methodology,
            "year": year,
            "data_window": "2022–2024",
            "ranking": countries,
        }

    def test_identical_snapshots(self):
        from backend.snapshot_diff import compare_snapshots
        snap = self._make_isi()
        result = compare_snapshots(snap, snap)
        assert result["diff_version"] == "1.0"
        gs = result["global_summary"]
        assert gs["n_changed"] == 0
        assert gs["n_unchanged"] == 2

    def test_changed_snapshots(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = self._make_isi(year=2023, countries=[
            {"country": "DE", "isi_composite": 0.40, "rank": 2,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
            {"country": "FR", "isi_composite": 0.42, "rank": 1,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
        ])
        snap_b = self._make_isi(year=2024, countries=[
            {"country": "DE", "isi_composite": 0.50, "rank": 1,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
            {"country": "FR", "isi_composite": 0.42, "rank": 2,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
        ])
        # Provide country detail dicts so axis-level diffs can detect data changes
        details_a = {
            "DE": {"axes": [{"axis_id": 1, "score": 0.35}]},
            "FR": {"axes": [{"axis_id": 1, "score": 0.42}]},
        }
        details_b = {
            "DE": {"axes": [{"axis_id": 1, "score": 0.50}]},
            "FR": {"axes": [{"axis_id": 1, "score": 0.42}]},
        }
        result = compare_snapshots(snap_a, snap_b, details_a, details_b)
        gs = result["global_summary"]
        assert gs["n_changed"] >= 1
        assert "DE" in result["per_country"]
        assert result["per_country"]["DE"]["composite_delta"] == 0.10

    def test_country_added_in_snapshot(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = self._make_isi(countries=[
            {"country": "DE", "isi_composite": 0.45, "rank": 1,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
        ])
        snap_b = self._make_isi(countries=[
            {"country": "DE", "isi_composite": 0.45, "rank": 1,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
            {"country": "FR", "isi_composite": 0.42, "rank": 2,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
        ])
        result = compare_snapshots(snap_a, snap_b)
        assert result["per_country"]["FR"]["status"] == "ADDED"
        assert result["global_summary"]["n_added"] == 1

    def test_methodology_change_in_diff(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = self._make_isi(methodology="v1.0")
        snap_b = self._make_isi(methodology="v2.0")
        result = compare_snapshots(snap_a, snap_b)
        assert result["global_summary"]["methodology_changed"] is True

    def test_global_summary_statistics(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = self._make_isi(countries=[
            {"country": "DE", "isi_composite": 0.40, "rank": 2,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
            {"country": "FR", "isi_composite": 0.45, "rank": 1,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
        ])
        snap_b = self._make_isi(countries=[
            {"country": "DE", "isi_composite": 0.50, "rank": 1,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
            {"country": "FR", "isi_composite": 0.43, "rank": 2,
             "governance_tier": "FULLY_COMPARABLE",
             "decision_usability_class": "TRUSTED_COMPARABLE"},
        ])
        result = compare_snapshots(snap_a, snap_b)
        gs = result["global_summary"]
        assert "rank_movement" in gs
        assert "composite_movement" in gs
        assert "change_type_distribution" in gs
        assert gs["n_total_countries"] == 2

    def test_diff_honesty_note(self):
        from backend.snapshot_diff import compare_snapshots
        snap = self._make_isi()
        result = compare_snapshots(snap, snap)
        assert "honesty_note" in result


class TestDiffSummaryText:
    """Test human-readable diff summary."""

    def test_summary_text_format(self):
        from backend.snapshot_diff import compare_snapshots, get_diff_summary_text
        snap_a = {
            "methodology_version": "v1.0",
            "year": 2023,
            "data_window": "2021–2023",
            "ranking": [
                {"country": "DE", "isi_composite": 0.40, "rank": 1,
                 "governance_tier": "FULLY_COMPARABLE",
                 "decision_usability_class": "TRUSTED_COMPARABLE"},
            ],
        }
        snap_b = {
            "methodology_version": "v1.0",
            "year": 2024,
            "data_window": "2022–2024",
            "ranking": [
                {"country": "DE", "isi_composite": 0.50, "rank": 1,
                 "governance_tier": "FULLY_COMPARABLE",
                 "decision_usability_class": "TRUSTED_COMPARABLE"},
            ],
        }
        diff = compare_snapshots(snap_a, snap_b)
        text = get_diff_summary_text(diff)
        assert "Snapshot Differential Summary" in text
        assert "v1.0" in text
        assert "Changed" in text


class TestIsiCountryMap:
    """Test the _isi_country_map helper."""

    def test_ranking_format(self):
        from backend.snapshot_diff import _isi_country_map
        isi = {"ranking": [
            {"country": "DE", "isi_composite": 0.45},
            {"country": "FR", "isi_composite": 0.42},
        ]}
        result = _isi_country_map(isi)
        assert "DE" in result
        assert "FR" in result

    def test_countries_dict_format(self):
        from backend.snapshot_diff import _isi_country_map
        isi = {"countries": {
            "DE": {"isi_composite": 0.45},
            "FR": {"isi_composite": 0.42},
        }}
        result = _isi_country_map(isi)
        assert "DE" in result
        assert "FR" in result

    def test_countries_list_format(self):
        from backend.snapshot_diff import _isi_country_map
        isi = {"countries": [
            {"country": "DE", "isi_composite": 0.45},
            {"country": "FR", "isi_composite": 0.42},
        ]}
        result = _isi_country_map(isi)
        assert "DE" in result
        assert "FR" in result

    def test_empty_isi(self):
        from backend.snapshot_diff import _isi_country_map
        result = _isi_country_map({})
        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-SYSTEM INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestInvariantUsabilityIntegration:
    """Test that critical invariant violations trigger usability downgrade."""

    def test_critical_invariant_triggers_downgrade(self):
        from backend.invariants import (
            assess_country_invariants,
            should_downgrade_usability,
        )
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        gov = {
            "governance_tier": "LOW_CONFIDENCE",
            "ranking_eligible": True,  # CRITICAL: GOV-001 + GOV-003
            "cross_country_comparable": False,
            "composite_defensible": False,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.35,
            "axis_confidences": [],
        }
        result = assess_country_invariants("DE", scores, gov)
        assert result["has_critical"] is True
        assert should_downgrade_usability(result) is True

    def test_clean_invariant_no_downgrade(self):
        from backend.invariants import (
            assess_country_invariants,
            should_downgrade_usability,
        )
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.75,
            "axis_confidences": [],
        }
        result = assess_country_invariants("DE", scores, gov)
        assert should_downgrade_usability(result) is False


class TestProvenanceInvariantIntegration:
    """Test provenance traces for invariant-triggered downgrades."""

    def test_provenance_records_invariant_downgrade(self):
        from backend.provenance import build_usability_provenance
        inv = {"n_critical": 2}
        prov = build_usability_provenance(
            country="DE",
            usability_class="STRUCTURALLY_LIMITED",
            invariant_result=inv,
        )
        assert any("INVARIANT_DOWNGRADE" in r for r in prov["rules_applied"])
        has_invariant_step = any(
            step["step"] == "INVARIANT_CHECK"
            for step in prov["transformation_chain"]
        )
        assert has_invariant_step


class TestDiffWithInvariants:
    """Test that diff can detect governance-level changes."""

    def test_diff_governance_tier_change_detected(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = {
            "methodology_version": "v1.0",
            "year": 2023,
            "data_window": "2021–2023",
            "ranking": [
                {"country": "RU", "isi_composite": 0.30, "rank": 1,
                 "governance_tier": "LOW_CONFIDENCE",
                 "decision_usability_class": "STRUCTURALLY_LIMITED"},
            ],
        }
        snap_b = {
            "methodology_version": "v1.0",
            "year": 2024,
            "data_window": "2022–2024",
            "ranking": [
                {"country": "RU", "isi_composite": 0.30, "rank": 1,
                 "governance_tier": "NON_COMPARABLE",
                 "decision_usability_class": "INVALID_FOR_COMPARISON"},
            ],
        }
        diff = compare_snapshots(snap_a, snap_b)
        ru_diff = diff["per_country"]["RU"]
        assert ru_diff["governance_change"]["changed"] is True
        assert ru_diff["governance_change"]["from"] == "LOW_CONFIDENCE"
        assert ru_diff["governance_change"]["to"] == "NON_COMPARABLE"


# ═══════════════════════════════════════════════════════════════════════════
# ADVERSARIAL / EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialInputs:
    """Test with unusual or edge-case inputs."""

    def test_invariants_all_none_scores(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: None, 2: None, 3: None, 4: None, 5: None, 6: None}
        violations = check_cross_axis_invariants("DE", scores)
        assert violations == []

    def test_invariants_partial_scores(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 0.5, 2: 0.4, 3: 0.3, 4: None, 5: None, 6: None}
        violations = check_cross_axis_invariants("DE", scores)
        # Should not crash
        assert isinstance(violations, list)

    def test_governance_invariants_empty_gov(self):
        from backend.invariants import check_governance_invariants
        gov = {}
        violations = check_governance_invariants("DE", gov)
        # Should not crash, just no violations
        assert isinstance(violations, list)

    def test_temporal_invariants_missing_fields(self):
        from backend.invariants import check_temporal_invariants
        snap_a = {}
        snap_b = {}
        violations = check_temporal_invariants("DE", snap_a, snap_b)
        assert isinstance(violations, list)

    def test_provenance_empty_governance(self):
        from backend.provenance import build_country_provenance
        scores = {1: 0.5, 2: 0.5, 3: 0.5, 4: 0.5, 5: 0.5, 6: 0.5}
        prov = build_country_provenance(
            country="DE",
            axis_scores=scores,
            composite_score=0.5,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
        )
        assert prov["governance"] is None  # No governance result provided
        assert prov["completeness"]["is_fully_traced"] is True

    def test_diff_country_both_none(self):
        """When both entries are None, isi_entry_a is None triggers ADDED path."""
        from backend.snapshot_diff import diff_country
        result = diff_country("DE", None, None)
        # isi_entry_a is None → returns ADDED (first branch)
        assert result["status"] == "ADDED"

    def test_diff_empty_snapshots(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = {"methodology_version": "v1.0", "year": 2023, "data_window": "x", "ranking": []}
        snap_b = {"methodology_version": "v1.0", "year": 2024, "data_window": "x", "ranking": []}
        result = compare_snapshots(snap_a, snap_b)
        assert result["global_summary"]["n_total_countries"] == 0

    def test_score_exactly_at_boundaries(self):
        from backend.invariants import check_cross_axis_invariants
        # All scores exactly 0
        scores = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
        violations = check_cross_axis_invariants("DE", scores)
        # Should trigger CA-004 (uniform) since range is 0
        ca004 = [v for v in violations if v["invariant_id"] == "CA-004"]
        assert len(ca004) == 1

    def test_score_exactly_at_1(self):
        from backend.invariants import check_cross_axis_invariants
        scores = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}
        violations = check_cross_axis_invariants("DE", scores)
        ca004 = [v for v in violations if v["invariant_id"] == "CA-004"]
        assert len(ca004) == 1


class TestDeterminism:
    """Verify that all functions are deterministic."""

    def test_invariant_determinism(self):
        from backend.invariants import assess_country_invariants
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.75,
            "axis_confidences": [],
        }
        r1 = assess_country_invariants("DE", scores, gov)
        r2 = assess_country_invariants("DE", scores, gov)
        assert r1 == r2

    def test_provenance_determinism(self):
        from backend.provenance import build_country_provenance
        scores = {1: 0.4, 2: 0.5, 3: 0.3, 4: 0.6, 5: 0.45, 6: 0.35}
        kwargs = dict(
            country="DE",
            axis_scores=scores,
            composite_score=0.43,
            methodology_version="v1.0",
            year=2024,
            data_window="2022–2024",
        )
        p1 = build_country_provenance(**kwargs)
        p2 = build_country_provenance(**kwargs)
        assert p1 == p2

    def test_diff_determinism(self):
        from backend.snapshot_diff import compare_snapshots
        snap_a = {
            "methodology_version": "v1.0", "year": 2023,
            "data_window": "x",
            "ranking": [
                {"country": "DE", "isi_composite": 0.40, "rank": 1,
                 "governance_tier": "FULLY_COMPARABLE",
                 "decision_usability_class": "TRUSTED_COMPARABLE"},
            ],
        }
        snap_b = {
            "methodology_version": "v1.0", "year": 2024,
            "data_window": "x",
            "ranking": [
                {"country": "DE", "isi_composite": 0.50, "rank": 1,
                 "governance_tier": "FULLY_COMPARABLE",
                 "decision_usability_class": "TRUSTED_COMPARABLE"},
            ],
        }
        d1 = compare_snapshots(snap_a, snap_b)
        d2 = compare_snapshots(snap_a, snap_b)
        assert d1 == d2
