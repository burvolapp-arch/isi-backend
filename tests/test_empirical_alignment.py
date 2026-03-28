"""
Tests for empirical alignment dimension, policy usability classification,
and external validation integration into export_snapshot.py.

Validates:
- EmpiricalAlignmentClass constants
- PolicyUsabilityClass constants
- classify_empirical_alignment() logic
- classify_policy_usability() combined dimension
- classify_decision_usability() with external_validation_result
- export_snapshot.py external_validation integration
"""

from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: EMPIRICAL ALIGNMENT CLASS
# ═══════════════════════════════════════════════════════════════════════════


class TestEmpiricalAlignmentClass:
    """Verify EmpiricalAlignmentClass constants and registry."""

    def test_all_classes_defined(self):
        from backend.eligibility import EmpiricalAlignmentClass
        assert hasattr(EmpiricalAlignmentClass, "EMPIRICALLY_GROUNDED")
        assert hasattr(EmpiricalAlignmentClass, "EMPIRICALLY_MIXED")
        assert hasattr(EmpiricalAlignmentClass, "EMPIRICALLY_WEAK")
        assert hasattr(EmpiricalAlignmentClass, "EMPIRICALLY_CONTRADICTED")
        assert hasattr(EmpiricalAlignmentClass, "NOT_EMPIRICALLY_ASSESSED")

    def test_valid_empirical_classes_complete(self):
        from backend.eligibility import VALID_EMPIRICAL_CLASSES, EmpiricalAlignmentClass
        assert len(VALID_EMPIRICAL_CLASSES) == 5
        for attr in ("EMPIRICALLY_GROUNDED", "EMPIRICALLY_MIXED",
                      "EMPIRICALLY_WEAK", "EMPIRICALLY_CONTRADICTED",
                      "NOT_EMPIRICALLY_ASSESSED"):
            assert getattr(EmpiricalAlignmentClass, attr) in VALID_EMPIRICAL_CLASSES

    def test_empirical_rank_ordering(self):
        from backend.eligibility import _EMPIRICAL_RANK, EmpiricalAlignmentClass
        assert _EMPIRICAL_RANK[EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED] < \
               _EMPIRICAL_RANK[EmpiricalAlignmentClass.EMPIRICALLY_WEAK] < \
               _EMPIRICAL_RANK[EmpiricalAlignmentClass.EMPIRICALLY_MIXED] < \
               _EMPIRICAL_RANK[EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED]
        # NOT_EMPIRICALLY_ASSESSED is special — -1
        assert _EMPIRICAL_RANK[EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED] == -1


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: POLICY USABILITY CLASS
# ═══════════════════════════════════════════════════════════════════════════


class TestPolicyUsabilityClass:
    """Verify PolicyUsabilityClass constants."""

    def test_all_classes_defined(self):
        from backend.eligibility import PolicyUsabilityClass
        assert hasattr(PolicyUsabilityClass, "SOUND_AND_ALIGNED")
        assert hasattr(PolicyUsabilityClass, "SOUND_BUT_WEAK")
        assert hasattr(PolicyUsabilityClass, "EMPIRICALLY_CONTRADICTED")
        assert hasattr(PolicyUsabilityClass, "STRUCTURALLY_LIMITED")
        assert hasattr(PolicyUsabilityClass, "INVALID_FOR_POLICY_USE")
        assert hasattr(PolicyUsabilityClass, "NOT_ASSESSED")

    def test_valid_policy_classes_complete(self):
        from backend.eligibility import VALID_POLICY_CLASSES
        assert len(VALID_POLICY_CLASSES) == 6

    def test_values_are_descriptive_strings(self):
        from backend.eligibility import PolicyUsabilityClass
        assert "STRUCTURALLY_SOUND" in PolicyUsabilityClass.SOUND_AND_ALIGNED
        assert "EMPIRICALLY_ALIGNED" in PolicyUsabilityClass.SOUND_AND_ALIGNED
        assert "INVALID" in PolicyUsabilityClass.INVALID_FOR_POLICY_USE


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: classify_empirical_alignment
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifyEmpiricalAlignment:
    """Test empirical alignment classification logic."""

    def test_none_input_returns_not_assessed(self):
        from backend.eligibility import (
            classify_empirical_alignment,
            EmpiricalAlignmentClass,
        )
        result = classify_empirical_alignment(None)
        assert result["empirical_class"] == EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED
        assert result["n_axes_compared"] == 0

    def test_no_data_returns_not_assessed(self):
        from backend.eligibility import (
            classify_empirical_alignment,
            EmpiricalAlignmentClass,
        )
        result = classify_empirical_alignment({
            "overall_alignment": "NO_DATA",
            "n_axes_compared": 0,
            "n_axes_aligned": 0,
            "n_axes_divergent": 0,
        })
        assert result["empirical_class"] == EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED

    def test_majority_aligned_returns_grounded(self):
        from backend.eligibility import (
            classify_empirical_alignment,
            EmpiricalAlignmentClass,
        )
        result = classify_empirical_alignment({
            "overall_alignment": "STRONGLY_ALIGNED",
            "n_axes_compared": 4,
            "n_axes_aligned": 3,
            "n_axes_divergent": 0,
        })
        assert result["empirical_class"] == EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED

    def test_majority_divergent_returns_contradicted(self):
        from backend.eligibility import (
            classify_empirical_alignment,
            EmpiricalAlignmentClass,
        )
        result = classify_empirical_alignment({
            "overall_alignment": "DIVERGENT",
            "n_axes_compared": 4,
            "n_axes_aligned": 1,
            "n_axes_divergent": 3,
        })
        assert result["empirical_class"] == EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED

    def test_mixed_alignment(self):
        from backend.eligibility import (
            classify_empirical_alignment,
            EmpiricalAlignmentClass,
        )
        result = classify_empirical_alignment({
            "overall_alignment": "WEAKLY_ALIGNED",
            "n_axes_compared": 4,
            "n_axes_aligned": 2,
            "n_axes_divergent": 2,
        })
        assert result["empirical_class"] == EmpiricalAlignmentClass.EMPIRICALLY_MIXED

    def test_weak_alignment(self):
        from backend.eligibility import (
            classify_empirical_alignment,
            EmpiricalAlignmentClass,
        )
        # No axes aligned or divergent — just weak comparisons
        result = classify_empirical_alignment({
            "overall_alignment": "WEAKLY_ALIGNED",
            "n_axes_compared": 3,
            "n_axes_aligned": 0,
            "n_axes_divergent": 0,
        })
        assert result["empirical_class"] == EmpiricalAlignmentClass.EMPIRICALLY_WEAK

    def test_result_has_interpretation(self):
        from backend.eligibility import classify_empirical_alignment
        result = classify_empirical_alignment({
            "overall_alignment": "STRONGLY_ALIGNED",
            "n_axes_compared": 4,
            "n_axes_aligned": 4,
            "n_axes_divergent": 0,
        })
        assert "interpretation" in result
        assert len(result["interpretation"]) > 10


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: classify_policy_usability
# ═══════════════════════════════════════════════════════════════════════════


class TestClassifyPolicyUsability:
    """Test combined structural + empirical usability logic."""

    def test_invalid_structural_always_invalid_policy(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.INVALID_FOR_COMPARISON,
            EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.INVALID_FOR_POLICY_USE

    def test_trusted_and_grounded_is_best(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.SOUND_AND_ALIGNED

    def test_trusted_but_contradicted_is_warning(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.EMPIRICALLY_CONTRADICTED

    def test_conditional_and_not_assessed_is_weak(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
            EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.SOUND_BUT_WEAK

    def test_structurally_limited_dominates(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.STRUCTURALLY_LIMITED,
            EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.STRUCTURALLY_LIMITED

    def test_structurally_limited_plus_weak_is_invalid(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.STRUCTURALLY_LIMITED,
            EmpiricalAlignmentClass.EMPIRICALLY_WEAK,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.INVALID_FOR_POLICY_USE

    def test_all_results_have_guidance(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
        )
        for sc in (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
            DecisionUsabilityClass.STRUCTURALLY_LIMITED,
            DecisionUsabilityClass.INVALID_FOR_COMPARISON,
        ):
            for ec in (
                EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
                EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED,
            ):
                result = classify_policy_usability(sc, ec)
                assert "policy_guidance" in result
                assert len(result["policy_guidance"]) > 20

    def test_result_includes_both_inputs(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
        )
        result = classify_policy_usability(
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
        )
        assert result["structural_class"] == DecisionUsabilityClass.TRUSTED_COMPARABLE
        assert result["empirical_class"] == EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: classify_decision_usability WITH external_validation_result
# ═══════════════════════════════════════════════════════════════════════════


class TestDecisionUsabilityWithEmpirical:
    """Test classify_decision_usability with the new empirical dimension."""

    def _make_governance(self, tier="FULLY_COMPARABLE", n_high=6):
        return {
            "country": "DE",
            "governance_tier": tier,
            "mean_axis_confidence": 0.70,
            "n_producer_inverted_axes": 0,
            "n_valid_axes": 6,
            "n_axes_with_data": 6,
            "ranking_eligible": True,
            "cross_country_comparable": True,
            "composite_defensible": True,
            "n_low_confidence_axes": 0,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.70,
                 "confidence_level": "HIGH" if i <= n_high else "LOW",
                 "penalties_applied": []}
                for i in range(1, 7)
            ],
        }

    def test_backward_compatible_without_external(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", governance_result=gov)
        assert "decision_usability_class" in result
        # Should now also have empirical fields
        assert "empirical_alignment_class" in result
        assert "policy_usability_class" in result

    def test_with_external_grounded(self):
        from backend.eligibility import (
            classify_decision_usability,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        gov = self._make_governance()
        ext = {
            "overall_alignment": "STRONGLY_ALIGNED",
            "n_axes_compared": 4,
            "n_axes_aligned": 4,
            "n_axes_divergent": 0,
        }
        result = classify_decision_usability(
            "DE", governance_result=gov, external_validation_result=ext,
        )
        assert result["empirical_alignment_class"] == EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED
        assert result["policy_usability_class"] == PolicyUsabilityClass.SOUND_AND_ALIGNED

    def test_with_external_contradicted(self):
        from backend.eligibility import (
            classify_decision_usability,
            PolicyUsabilityClass,
        )
        gov = self._make_governance()
        ext = {
            "overall_alignment": "DIVERGENT",
            "n_axes_compared": 4,
            "n_axes_aligned": 0,
            "n_axes_divergent": 3,
        }
        result = classify_decision_usability(
            "DE", governance_result=gov, external_validation_result=ext,
        )
        assert result["policy_usability_class"] == PolicyUsabilityClass.EMPIRICALLY_CONTRADICTED

    def test_without_external_defaults_to_not_assessed(self):
        from backend.eligibility import (
            classify_decision_usability,
            EmpiricalAlignmentClass,
        )
        gov = self._make_governance()
        result = classify_decision_usability("DE", governance_result=gov)
        assert result["empirical_alignment_class"] == EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED

    def test_empirical_alignment_detail_included(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", governance_result=gov)
        assert "empirical_alignment" in result
        assert "empirical_class" in result["empirical_alignment"]

    def test_policy_usability_detail_included(self):
        from backend.eligibility import classify_decision_usability
        gov = self._make_governance()
        result = classify_decision_usability("DE", governance_result=gov)
        assert "policy_usability" in result
        assert "policy_guidance" in result["policy_usability"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: EXPORT INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


class TestExportExternalValidation:
    """Test export_snapshot.py external validation integration."""

    def test_compute_external_validation_wrapper(self):
        from backend.export_snapshot import _compute_external_validation
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        result = _compute_external_validation("DE", all_scores)
        assert isinstance(result, dict)
        assert "overall_alignment" in result or "error" in result

    def test_compute_external_validation_missing_country(self):
        from backend.export_snapshot import _compute_external_validation
        all_scores = {ax: {"FR": 0.5} for ax in range(1, 7)}
        result = _compute_external_validation("XX", all_scores)
        # Should not raise, should return a valid dict
        assert isinstance(result, dict)

    def test_get_external_validation_status(self):
        from backend.export_snapshot import _get_external_validation_status
        result = _get_external_validation_status()
        assert isinstance(result, dict)

    def test_build_country_json_has_external_validation(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        country_json = build_country_json(
            country="DE",
            all_scores=all_scores,
            methodology_version="v1.1",
            year=2024,
            data_window="2019-2024",
        )
        assert "external_validation" in country_json
        ext = country_json["external_validation"]
        assert "overall_alignment" in ext or "error" in ext

    def test_build_country_json_has_decision_usability_with_empirical(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        country_json = build_country_json(
            country="DE",
            all_scores=all_scores,
            methodology_version="v1.1",
            year=2024,
            data_window="2019-2024",
        )
        du = country_json["decision_usability"]
        assert "policy_usability_class" in du
        assert "empirical_alignment_class" in du

    def test_build_isi_json_has_external_validation_status(self):
        from backend.export_snapshot import build_isi_json
        all_scores = {ax: {"DE": 0.5, "FR": 0.6} for ax in range(1, 7)}
        isi_json = build_isi_json(
            all_scores=all_scores,
            methodology_version="v1.1",
            year=2024,
            data_window="2019-2024",
        )
        assert "external_validation_status" in isi_json

    def test_build_isi_json_rows_have_policy_usability(self):
        from backend.export_snapshot import build_isi_json
        all_scores = {ax: {"DE": 0.5, "FR": 0.6} for ax in range(1, 7)}
        isi_json = build_isi_json(
            all_scores=all_scores,
            methodology_version="v1.1",
            year=2024,
            data_window="2019-2024",
        )
        for row in isi_json["countries"]:
            if row["isi_composite"] is not None:
                assert "policy_usability_class" in row

    def test_external_validation_has_empirical_grounding_answer(self):
        from backend.export_snapshot import build_country_json
        all_scores = {ax: {"DE": 0.5} for ax in range(1, 7)}
        country_json = build_country_json(
            country="DE",
            all_scores=all_scores,
            methodology_version="v1.1",
            year=2024,
            data_window="2019-2024",
        )
        ext = country_json["external_validation"]
        if "error" not in ext:
            assert "empirical_grounding_answer" in ext


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: EDGE CASES & ORTHOGONALITY
# ═══════════════════════════════════════════════════════════════════════════


class TestEmpiricalOrthogonality:
    """Verify empirical dimension is truly orthogonal to structural."""

    def test_all_structural_x_empirical_combinations_produce_valid_policy(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            VALID_POLICY_CLASSES,
        )
        for sc in (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
            DecisionUsabilityClass.STRUCTURALLY_LIMITED,
            DecisionUsabilityClass.INVALID_FOR_COMPARISON,
        ):
            for ec in (
                EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
                EmpiricalAlignmentClass.EMPIRICALLY_MIXED,
                EmpiricalAlignmentClass.EMPIRICALLY_WEAK,
                EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED,
                EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED,
            ):
                result = classify_policy_usability(sc, ec)
                assert result["policy_usability_class"] in VALID_POLICY_CLASSES, \
                    f"Invalid policy class for {sc} x {ec}: {result['policy_usability_class']}"

    def test_empirical_contradicted_never_produces_sound_and_aligned(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        for sc in (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
            DecisionUsabilityClass.STRUCTURALLY_LIMITED,
            DecisionUsabilityClass.INVALID_FOR_COMPARISON,
        ):
            result = classify_policy_usability(
                sc, EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED,
            )
            assert result["policy_usability_class"] != PolicyUsabilityClass.SOUND_AND_ALIGNED

    def test_sound_and_aligned_requires_both_good(self):
        from backend.eligibility import (
            classify_policy_usability,
            DecisionUsabilityClass,
            EmpiricalAlignmentClass,
            PolicyUsabilityClass,
        )
        # Only these combinations should produce SOUND_AND_ALIGNED
        good_structural = (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
        )
        good_empirical = (EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,)
        for sc in good_structural:
            for ec in good_empirical:
                result = classify_policy_usability(sc, ec)
                assert result["policy_usability_class"] == PolicyUsabilityClass.SOUND_AND_ALIGNED
