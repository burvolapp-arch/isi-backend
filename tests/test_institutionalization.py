"""
tests/test_institutionalization.py — Tests for Institutionalization Pass

Covers:
    Section 1: Benchmark Authority Hierarchy
    Section 2: Contextual Decision Usability (dimensions + failure modes)
    Section 4: Failure Visibility Enforcement (wired into export)
    Section 7: Invariant Expansion (FAILURE_VISIBILITY, AUTHORITY_CONSISTENCY)
    Section 8: Export Honesty (visibility block in country JSON)
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: BENCHMARK AUTHORITY HIERARCHY
# ═══════════════════════════════════════════════════════════════════════════


class TestBenchmarkAuthorityHierarchy:
    """Tests for benchmark authority levels and weighted alignment."""

    def test_benchmark_authority_enum_values(self):
        from backend.benchmark_registry import BenchmarkAuthority
        assert BenchmarkAuthority.STRUCTURAL == "STRUCTURAL"
        assert BenchmarkAuthority.HIGH_CONFIDENCE == "HIGH_CONFIDENCE"
        assert BenchmarkAuthority.SUPPORTING == "SUPPORTING"

    def test_valid_authority_levels_frozenset(self):
        from backend.benchmark_registry import VALID_AUTHORITY_LEVELS
        assert len(VALID_AUTHORITY_LEVELS) == 3
        assert "STRUCTURAL" in VALID_AUTHORITY_LEVELS
        assert "HIGH_CONFIDENCE" in VALID_AUTHORITY_LEVELS
        assert "SUPPORTING" in VALID_AUTHORITY_LEVELS

    def test_all_benchmarks_have_authority(self):
        from backend.benchmark_registry import get_benchmark_registry
        for entry in get_benchmark_registry():
            bm_id = entry["benchmark_id"]
            assert "authority_level" in entry, (
                f"Benchmark {bm_id} missing authority_level"
            )
            assert "authority_justification" in entry, (
                f"Benchmark {bm_id} missing authority_justification"
            )
            assert entry["authority_level"] in (
                "STRUCTURAL", "HIGH_CONFIDENCE", "SUPPORTING"
            ), f"Benchmark {bm_id} has invalid authority_level: {entry['authority_level']}"
            assert len(entry["authority_justification"]) > 0, (
                f"Benchmark {bm_id} has empty authority_justification"
            )

    def test_structural_benchmarks_exist(self):
        """At least one STRUCTURAL benchmark must exist."""
        from backend.benchmark_registry import get_benchmark_registry
        structural = [
            entry["benchmark_id"] for entry in get_benchmark_registry()
            if entry["authority_level"] == "STRUCTURAL"
        ]
        assert len(structural) >= 1

    def test_supporting_benchmarks_exist(self):
        """At least one SUPPORTING benchmark must exist."""
        from backend.benchmark_registry import get_benchmark_registry
        supporting = [
            entry["benchmark_id"] for entry in get_benchmark_registry()
            if entry["authority_level"] == "SUPPORTING"
        ]
        assert len(supporting) >= 1

    def test_authority_weights_match_hierarchy(self):
        from backend.external_validation import AUTHORITY_WEIGHTS
        assert AUTHORITY_WEIGHTS["STRUCTURAL"] == 1.0
        assert AUTHORITY_WEIGHTS["HIGH_CONFIDENCE"] == 0.7
        assert AUTHORITY_WEIGHTS["SUPPORTING"] == 0.4
        # Hierarchy: STRUCTURAL > HIGH_CONFIDENCE > SUPPORTING
        assert AUTHORITY_WEIGHTS["STRUCTURAL"] > AUTHORITY_WEIGHTS["HIGH_CONFIDENCE"]
        assert AUTHORITY_WEIGHTS["HIGH_CONFIDENCE"] > AUTHORITY_WEIGHTS["SUPPORTING"]

    def test_authority_conflicts_in_alignment_result(self):
        """assess_country_alignment returns authority_conflicts field."""
        from backend.external_validation import assess_country_alignment
        axis_scores = {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.5, 5: 0.45, 6: 0.55}
        result = assess_country_alignment("DE", axis_scores)
        assert "authority_conflicts" in result
        assert isinstance(result["authority_conflicts"], list)

    def test_weighted_alignment_score_in_alignment_result(self):
        """assess_country_alignment returns weighted_alignment_score."""
        from backend.external_validation import assess_country_alignment
        axis_scores = {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.5, 5: 0.45, 6: 0.55}
        result = assess_country_alignment("DE", axis_scores)
        assert "weighted_alignment_score" in result
        ws = result["weighted_alignment_score"]
        assert isinstance(ws, dict) or ws is None

    def test_assess_country_alignment_includes_authority_fields(self):
        from backend.external_validation import assess_country_alignment
        axis_scores = {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.5, 5: 0.45, 6: 0.55}
        result = assess_country_alignment("DE", axis_scores)
        assert "weighted_alignment_score" in result
        assert "authority_conflicts" in result
        assert "alignment_confidence" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: CONTEXTUAL DECISION USABILITY
# ═══════════════════════════════════════════════════════════════════════════


class TestDecisionUsabilityDimensions:
    """Tests for per-dimension usability and failure modes."""

    def _make_governance(
        self,
        tier: str = "FULLY_COMPARABLE",
        ranking: bool = True,
        comparable: bool = True,
        n_inverted: int = 0,
        mean_conf: float = 0.75,
    ) -> dict[str, Any]:
        return {
            "governance_tier": tier,
            "ranking_eligible": ranking,
            "cross_country_comparable": comparable,
            "composite_defensible": True,
            "n_producer_inverted_axes": n_inverted,
            "n_axes_with_data": 6,
            "mean_axis_confidence": mean_conf,
            "n_low_confidence_axes": 0,
            "n_high_confidence_axes": 6,
            "producer_inverted_axes": [],
            "axis_confidences": [
                {
                    "axis_id": ax,
                    "confidence_level": "HIGH",
                    "confidence_score": mean_conf,
                    "penalties_applied": [],
                }
                for ax in range(1, 7)
            ],
        }

    def test_usability_includes_dimensions(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", gov)
        assert "decision_usability_dimensions" in result
        dims = result["decision_usability_dimensions"]
        assert isinstance(dims, dict)
        assert "ranking" in dims
        assert "directional_insight" in dims
        assert "policy_design" in dims
        assert "stress_testing" in dims

    def test_usability_includes_failure_modes(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", gov)
        assert "failure_modes" in result
        assert isinstance(result["failure_modes"], list)

    def test_trusted_comparable_all_dimensions_true(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", gov)
        assert result["decision_usability_class"] == "TRUSTED_COMPARABLE"
        dims = result["decision_usability_dimensions"]
        assert dims["ranking"] is True
        assert dims["directional_insight"] is True
        assert dims["policy_design"] is True
        assert dims["stress_testing"] is True

    def test_trusted_comparable_no_failure_modes(self):
        """TRUSTED_COMPARABLE should have zero or minimal failure modes."""
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", gov)
        # May have conditions like governance caveats, but no CRITICAL/ERROR
        for fm in result["failure_modes"]:
            assert fm["severity"] != "CRITICAL"

    def test_invalid_for_comparison_ranking_false(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance(
            tier="NON_COMPARABLE", ranking=False, comparable=False,
        )
        result = classify_decision_usability("DE", gov)
        dims = result["decision_usability_dimensions"]
        assert dims["ranking"] is False
        assert dims["directional_insight"] is False
        assert dims["stress_testing"] is False

    def test_structurally_limited_directional_true_ranking_false(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance(
            tier="LOW_CONFIDENCE", ranking=False, comparable=False,
            n_inverted=2, mean_conf=0.40,
        )
        result = classify_decision_usability("DE", gov)
        dims = result["decision_usability_dimensions"]
        assert dims["ranking"] is False
        assert dims["directional_insight"] is True

    def test_failure_modes_low_confidence(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance(
            tier="LOW_CONFIDENCE", ranking=False, comparable=False,
            mean_conf=0.35,
        )
        result = classify_decision_usability("DE", gov)
        fm = result["failure_modes"]
        # Should have a governance tier failure mode
        tier_modes = [
            m for m in fm if "LOW_CONFIDENCE" in m["condition"]
        ]
        assert len(tier_modes) >= 1

    def test_failure_modes_producer_inversion(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance(n_inverted=3, tier="NON_COMPARABLE",
                                     ranking=False, comparable=False)
        result = classify_decision_usability("DE", gov)
        fm = result["failure_modes"]
        inversion_modes = [
            m for m in fm if "inverted" in m["condition"].lower()
        ]
        assert len(inversion_modes) >= 1
        # 3 inversions should be CRITICAL
        assert any(m["severity"] == "CRITICAL" for m in inversion_modes)

    def test_failure_modes_structure(self):
        """Each failure mode must have condition, effect, severity."""
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance(
            tier="LOW_CONFIDENCE", ranking=False, comparable=False,
        )
        result = classify_decision_usability("DE", gov)
        for fm in result["failure_modes"]:
            assert "condition" in fm
            assert "effect" in fm
            assert "severity" in fm
            assert fm["severity"] in ("WARNING", "ERROR", "CRITICAL")

    def test_dimensions_hierarchy_ranking_requires_policy(self):
        """ranking=True implies policy_design=True (hierarchy)."""
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", gov)
        dims = result["decision_usability_dimensions"]
        if dims["ranking"]:
            assert dims["policy_design"] is True
            assert dims["directional_insight"] is True
            assert dims["stress_testing"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: FAILURE VISIBILITY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════


class TestFailureVisibilityEnforcement:
    """Tests that failure_visibility.py is wired into export."""

    def test_build_visibility_block_basic(self):
        from backend.failure_visibility import build_visibility_block
        result = build_visibility_block("DE")
        assert result["country"] == "DE"
        assert "trust_level" in result
        assert "severity_summary" in result
        assert "validity_warnings" in result
        assert "construct_flags" in result
        assert "alignment_flags" in result
        assert "invariant_violations" in result
        assert "honesty_note" in result

    def test_build_visibility_block_with_governance(self):
        from backend.failure_visibility import build_visibility_block
        gov = {
            "governance_tier": "NON_COMPARABLE",
            "n_producer_inverted_axes": 0,
        }
        result = build_visibility_block("DE", governance_result=gov)
        assert result["trust_level"] == "DO_NOT_USE"
        assert result["severity_summary"]["n_critical"] >= 1

    def test_build_visibility_block_fully_comparable(self):
        from backend.failure_visibility import build_visibility_block
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "n_producer_inverted_axes": 0,
        }
        result = build_visibility_block("DE", governance_result=gov)
        assert result["trust_level"] == "STRUCTURALLY_SOUND"

    def test_collect_validity_warnings_producer_inversion(self):
        from backend.failure_visibility import collect_validity_warnings
        gov = {
            "governance_tier": "PARTIALLY_COMPARABLE",
            "n_producer_inverted_axes": 2,
        }
        warnings = collect_validity_warnings("DE", governance_result=gov)
        inversion_warnings = [
            w for w in warnings if w["rule_id"] == "VW-004"
        ]
        assert len(inversion_warnings) >= 1

    def test_collect_alignment_flags_divergent(self):
        from backend.failure_visibility import collect_alignment_flags
        ext_val = {
            "overall_alignment": "DIVERGENT",
            "per_axis_summary": [],
        }
        flags = collect_alignment_flags("DE", external_validation=ext_val)
        assert any(f["rule_id"] == "AF-001" for f in flags)

    def test_should_downgrade_usability_critical_construct(self):
        from backend.failure_visibility import should_downgrade_usability
        vis = {
            "severity_summary": {"n_critical": 1, "n_error": 0},
            "validity_warnings": [],
            "construct_flags": [
                {"severity": "CRITICAL", "rule_id": "CF-003", "category": "construct",
                 "explanation": "test"}
            ],
            "alignment_flags": [],
            "invariant_violations": [],
        }
        result = should_downgrade_usability(vis, "TRUSTED_COMPARABLE")
        assert result["downgraded"] is True
        assert result["final_class"] == "INVALID_FOR_COMPARISON"

    def test_export_snapshot_includes_visibility(self):
        """build_country_json must include failure_visibility key."""
        from backend.export_snapshot import build_country_json
        # Use valid EU-27 scores
        all_scores = {
            ax: {"DE": 0.5} for ax in range(1, 7)
        }
        result = build_country_json(
            "DE", all_scores, "v1.0", 2024, "2022-2024",
        )
        assert "failure_visibility" in result
        vis = result["failure_visibility"]
        assert "trust_level" in vis
        assert "severity_summary" in vis

    def test_should_exclude_from_ranking(self):
        from backend.failure_visibility import should_exclude_from_ranking
        vis = {
            "trust_level": "DO_NOT_USE",
            "severity_summary": {"n_critical": 2, "n_error": 0,
                                 "n_warning": 0, "n_info": 0, "total_flags": 2},
        }
        result = should_exclude_from_ranking(vis)
        assert result["exclude_from_ranking"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: INVARIANT EXPANSION
# ═══════════════════════════════════════════════════════════════════════════


class TestInvariantExpansion:
    """Tests for new invariant types: FAILURE_VISIBILITY, AUTHORITY_CONSISTENCY."""

    def test_invariant_type_failure_visibility_exists(self):
        from backend.invariants import InvariantType
        assert hasattr(InvariantType, "FAILURE_VISIBILITY")
        assert InvariantType.FAILURE_VISIBILITY == "FAILURE_VISIBILITY"

    def test_invariant_type_authority_consistency_exists(self):
        from backend.invariants import InvariantType
        assert hasattr(InvariantType, "AUTHORITY_CONSISTENCY")
        assert InvariantType.AUTHORITY_CONSISTENCY == "AUTHORITY_CONSISTENCY"

    def test_valid_invariant_types_includes_new_types(self):
        from backend.invariants import VALID_INVARIANT_TYPES
        assert "FAILURE_VISIBILITY" in VALID_INVARIANT_TYPES
        assert "AUTHORITY_CONSISTENCY" in VALID_INVARIANT_TYPES

    def test_invariant_registry_has_fv_entries(self):
        from backend.invariants import INVARIANT_REGISTRY
        fv_entries = [
            e for e in INVARIANT_REGISTRY
            if e["type"] == "FAILURE_VISIBILITY"
        ]
        assert len(fv_entries) >= 2

    def test_invariant_registry_has_auth_entries(self):
        from backend.invariants import INVARIANT_REGISTRY
        auth_entries = [
            e for e in INVARIANT_REGISTRY
            if e["type"] == "AUTHORITY_CONSISTENCY"
        ]
        assert len(auth_entries) >= 2

    def test_invariant_registry_count(self):
        from backend.invariants import INVARIANT_REGISTRY
        # 28 + 5 pipeline integrity invariants from Final Closure Pass
        assert len(INVARIANT_REGISTRY) == 37

    def test_fv001_fires_when_block_empty(self):
        """FV-001: visibility block present but empty → no violation.
        FV-001 fires when block is None (only in export context via explicit passing).
        """
        from backend.invariants import check_failure_visibility_invariants
        result = check_failure_visibility_invariants("DE", visibility_block=None)
        # Should fire FV-001
        assert len(result) >= 1
        assert result[0]["invariant_id"] == "FV-001"
        assert result[0]["severity"] == "CRITICAL"

    def test_fv001_no_fire_with_valid_block(self):
        from backend.invariants import check_failure_visibility_invariants
        vis = {
            "trust_level": "STRUCTURALLY_SOUND",
            "severity_summary": {"n_critical": 0},
        }
        result = check_failure_visibility_invariants("DE", visibility_block=vis)
        fv001 = [v for v in result if v["invariant_id"] == "FV-001"]
        assert len(fv001) == 0

    def test_fv002_fires_on_trust_usability_mismatch(self):
        from backend.invariants import check_failure_visibility_invariants
        vis = {
            "trust_level": "DO_NOT_USE",
            "severity_summary": {"n_critical": 1},
        }
        result = check_failure_visibility_invariants(
            "DE",
            visibility_block=vis,
            decision_usability_class="TRUSTED_COMPARABLE",
        )
        fv002 = [v for v in result if v["invariant_id"] == "FV-002"]
        assert len(fv002) == 1

    def test_fv002_no_fire_when_consistent(self):
        from backend.invariants import check_failure_visibility_invariants
        vis = {
            "trust_level": "DO_NOT_USE",
            "severity_summary": {"n_critical": 1},
        }
        result = check_failure_visibility_invariants(
            "DE",
            visibility_block=vis,
            decision_usability_class="INVALID_FOR_COMPARISON",
        )
        fv002 = [v for v in result if v["invariant_id"] == "FV-002"]
        assert len(fv002) == 0

    def test_auth001_fires_on_structural_contradiction(self):
        from backend.invariants import check_authority_consistency_invariants
        alignment = {
            "authority_conflicts": [
                {
                    "severity": "CRITICAL",
                    "axis_id": 2,
                    "description": "STRUCTURAL contradicts HIGH_CONFIDENCE",
                }
            ],
            "weighted_alignment_score": {"weight_composition": {}},
        }
        result = check_authority_consistency_invariants(
            "DE", alignment_result=alignment,
        )
        auth001 = [v for v in result if v["invariant_id"] == "AUTH-001"]
        assert len(auth001) == 1

    def test_auth002_fires_on_wrong_weight(self):
        from backend.invariants import check_authority_consistency_invariants
        alignment = {
            "authority_conflicts": [],
            "weighted_alignment_score": {
                "weight_composition": {
                    "STRUCTURAL": 0.5,  # Wrong! Should be 1.0
                    "HIGH_CONFIDENCE": 0.7,
                    "SUPPORTING": 0.4,
                }
            },
        }
        result = check_authority_consistency_invariants(
            "DE", alignment_result=alignment,
        )
        auth002 = [v for v in result if v["invariant_id"] == "AUTH-002"]
        assert len(auth002) >= 1

    def test_auth002_no_fire_on_correct_weights(self):
        from backend.invariants import check_authority_consistency_invariants
        alignment = {
            "authority_conflicts": [],
            "weighted_alignment_score": {
                "weight_composition": {
                    "STRUCTURAL": 1.0,
                    "HIGH_CONFIDENCE": 0.7,
                    "SUPPORTING": 0.4,
                }
            },
        }
        result = check_authority_consistency_invariants(
            "DE", alignment_result=alignment,
        )
        auth002 = [v for v in result if v["invariant_id"] == "AUTH-002"]
        assert len(auth002) == 0

    def test_assess_country_invariants_with_visibility_block(self):
        """assess_country_invariants includes FV checks when block provided."""
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
        vis = {
            "trust_level": "STRUCTURALLY_SOUND",
            "severity_summary": {"n_critical": 0},
        }
        result = assess_country_invariants(
            "DE", scores, gov, visibility_block=vis,
        )
        assert result["n_violations"] == 0

    def test_assess_country_invariants_backward_compatible_no_visibility(self):
        """assess_country_invariants without visibility_block is backward-compatible."""
        from backend.invariants import assess_country_invariants
        scores = {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.5, 5: 0.45, 6: 0.55}
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.7,
            "axis_confidences": [
                {
                    "axis_id": ax,
                    "confidence_level": "HIGH",
                    "confidence_score": 0.7,
                    "penalties_applied": [],
                }
                for ax in range(1, 7)
            ],
        }
        result = assess_country_invariants("DE", scores, gov)
        # Should still work without visibility_block — no FV violations
        assert result["n_violations"] == 0

    def test_assess_country_invariants_with_authority_conflicts(self):
        """Authority invariants fire when alignment has conflicts."""
        from backend.invariants import assess_country_invariants
        scores = {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.5, 5: 0.45, 6: 0.55}
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_producer_inverted_axes": 0,
            "mean_axis_confidence": 0.7,
            "axis_confidences": [
                {
                    "axis_id": ax,
                    "confidence_level": "HIGH",
                    "confidence_score": 0.7,
                    "penalties_applied": [],
                }
                for ax in range(1, 7)
            ],
        }
        alignment = {
            "overall_alignment": "MIXED",
            "n_axes_compared": 2,
            "n_axes_divergent": 0,
            "n_axes_aligned": 2,
            "axis_alignments": [],
            "authority_conflicts": [
                {
                    "severity": "CRITICAL",
                    "axis_id": 2,
                    "description": "STRUCTURAL contradicts HIGH_CONFIDENCE",
                }
            ],
            "weighted_alignment_score": {
                "weighted_score": 0.5,
                "n_benchmarks_scored": 2,
                "weight_composition": {
                    "structural": 1.0,
                    "high_confidence": 0.7,
                },
            },
        }
        result = assess_country_invariants(
            "DE", scores, gov, alignment_result=alignment,
        )
        auth = [v for v in result["violations"] if v["invariant_id"] == "AUTH-001"]
        assert len(auth) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: EXPORT HONESTY HARDENING
# ═══════════════════════════════════════════════════════════════════════════


class TestExportHonestyHardening:
    """Tests that exported country JSON includes all required fields."""

    def test_country_json_has_required_layers(self):
        """build_country_json must include all structural layers."""
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_country_json("DE", all_scores, "v1.0", 2024, "2022-2024")

        required_keys = [
            "country", "country_name", "isi_composite", "governance",
            "axes", "falsification", "decision_usability",
            "external_validation", "failure_visibility",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

    def test_country_json_governance_has_tier(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_country_json("DE", all_scores, "v1.0", 2024, "2022-2024")
        gov = result["governance"]
        assert "governance_tier" in gov
        assert "ranking_eligible" in gov
        assert "structural_limitations" in gov

    def test_country_json_decision_usability_has_dimensions(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_country_json("DE", all_scores, "v1.0", 2024, "2022-2024")
        usab = result["decision_usability"]
        assert "decision_usability_class" in usab
        assert "decision_usability_dimensions" in usab
        assert "failure_modes" in usab

    def test_country_json_failure_visibility_has_trust(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_country_json("DE", all_scores, "v1.0", 2024, "2022-2024")
        vis = result["failure_visibility"]
        assert "trust_level" in vis
        assert "severity_summary" in vis

    def test_country_json_external_validation_has_alignment(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_country_json("DE", all_scores, "v1.0", 2024, "2022-2024")
        ext = result["external_validation"]
        assert "overall_alignment" in ext or "error" in ext

    def test_isi_json_has_usability_fields(self):
        """build_isi_json country rows include usability and policy."""
        from backend.export_snapshot import build_isi_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_isi_json(all_scores, "v1.0", 2024, "2022-2024")
        de_row = [c for c in result["countries"] if c["country"] == "DE"]
        assert len(de_row) == 1
        assert "decision_usability_class" in de_row[0]
        assert "policy_usability_class" in de_row[0]


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-CUTTING: INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestInstitutionalizationIntegration:
    """Cross-module integration tests for the institutionalization pass."""

    def test_full_pipeline_country_de(self):
        """Full pipeline for a clean country produces all layers."""
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = build_country_json("DE", all_scores, "v1.0", 2024, "2022-2024")

        # Composite computed
        assert result["isi_composite"] is not None

        # Governance present
        assert result["governance"]["governance_tier"] in (
            "FULLY_COMPARABLE", "PARTIALLY_COMPARABLE",
            "LOW_CONFIDENCE", "NON_COMPARABLE",
        )

        # Decision usability with dimensions
        usab = result["decision_usability"]
        assert usab["decision_usability_class"] in (
            "TRUSTED_COMPARABLE", "CONDITIONALLY_USABLE",
            "STRUCTURALLY_LIMITED", "INVALID_FOR_COMPARISON",
        )
        assert isinstance(usab["decision_usability_dimensions"], dict)
        assert isinstance(usab["failure_modes"], list)

        # Failure visibility present
        vis = result["failure_visibility"]
        assert vis["trust_level"] in (
            "STRUCTURALLY_SOUND", "USE_WITH_DOCUMENTED_CAVEATS",
            "USE_WITH_EXTREME_CAUTION", "DO_NOT_USE",
        )

    def test_full_pipeline_non_comparable_country(self):
        """Non-comparable country gets appropriate visibility."""
        from backend.export_snapshot import build_country_json
        # Give a country known to be producer-inverted
        all_scores = {ax: {"US": 0.1} for ax in range(1, 7)}
        result = build_country_json("US", all_scores, "v1.0", 2024, "2022-2024")

        # US has 3 inverted axes → NON_COMPARABLE
        gov = result["governance"]
        assert gov["governance_tier"] == "NON_COMPARABLE"
        assert gov["ranking_eligible"] is False

        # Decision usability should reflect this
        usab = result["decision_usability"]
        dims = usab.get("decision_usability_dimensions", {})
        if dims:
            assert dims.get("ranking") is False

    def test_authority_hierarchy_weights_are_correct(self):
        """Verify the mathematical hierarchy is respected."""
        from backend.external_validation import AUTHORITY_WEIGHTS
        w = AUTHORITY_WEIGHTS
        assert w["STRUCTURAL"] > w["HIGH_CONFIDENCE"] > w["SUPPORTING"]
        assert w["STRUCTURAL"] == 1.0
        assert w["HIGH_CONFIDENCE"] < 1.0
        assert w["SUPPORTING"] > 0.0

    def test_all_benchmark_entries_structurally_valid(self):
        """Every benchmark entry has all required fields."""
        from backend.benchmark_registry import get_benchmark_registry
        required = {
            "benchmark_id", "name", "data_source",
            "relevant_axes", "comparison_type", "status",
            "authority_level", "authority_justification",
        }
        for entry in get_benchmark_registry():
            bm_id = entry["benchmark_id"]
            for field in required:
                assert field in entry, (
                    f"Benchmark {bm_id} missing field: {field}"
                )

    def test_invariant_types_cover_all_registry_entries(self):
        """Every invariant in registry has a valid type."""
        from backend.invariants import INVARIANT_REGISTRY, VALID_INVARIANT_TYPES
        for entry in INVARIANT_REGISTRY:
            assert entry["type"] in VALID_INVARIANT_TYPES, (
                f"Invariant {entry['invariant_id']} has invalid type: "
                f"{entry['type']}"
            )

    def test_usability_dimensions_are_booleans(self):
        """All dimension values must be bool, not truthy/falsy."""
        from backend.eligibility import _compute_usability_dimensions
        dims = _compute_usability_dimensions(
            usability_class="TRUSTED_COMPARABLE",
            ranking_eligible=True,
            governance_tier="FULLY_COMPARABLE",
            conditions=[],
            falsification_flag="CONSISTENT",
            n_inverted=0,
            mean_confidence=0.75,
        )
        for key, val in dims.items():
            assert isinstance(val, bool), (
                f"Dimension {key} is {type(val)}, expected bool"
            )

    def test_failure_modes_severity_values(self):
        """All failure mode severities must be valid."""
        from backend.eligibility import _compute_failure_modes
        modes = _compute_failure_modes(
            usability_class="STRUCTURALLY_LIMITED",
            conditions=["test condition"],
            governance_tier="LOW_CONFIDENCE",
            falsification_flag="TENSION",
            n_inverted=2,
            mean_confidence=0.35,
            n_construct_sub=1,
        )
        valid_severities = {"WARNING", "ERROR", "CRITICAL"}
        for m in modes:
            assert m["severity"] in valid_severities, (
                f"Invalid severity: {m['severity']}"
            )
