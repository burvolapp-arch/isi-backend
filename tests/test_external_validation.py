"""
tests.test_external_validation — Tests for External Validation & Benchmark System

Covers:
    1. benchmark_registry.py — registry integrity, query API, validation
    2. external_validation.py — alignment engine, rank correlation, structural
       consistency, construct validity, export block, grounding answer
    3. invariants.py — EXTERNAL_VALIDITY invariant type and checks
    4. Integration — end-to-end alignment assessment flow

Test count target: comprehensive coverage of the entire external validation layer.
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: BENCHMARK REGISTRY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestBenchmarkRegistry:
    """Tests for backend.benchmark_registry module."""

    def test_registry_is_non_empty(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        assert len(EXTERNAL_BENCHMARK_REGISTRY) >= 10

    def test_all_benchmarks_have_required_fields(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        required_fields = {
            "benchmark_id", "name", "relevant_axes", "comparison_type",
            "status", "construct_description", "construct_overlap_with_isi",
            "construct_divergence_from_isi", "data_source",
            "geographic_coverage", "alignment_thresholds",
            "divergence_interpretation", "integration_requirements",
        }
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            missing = required_fields - set(b.keys())
            assert not missing, (
                f"Benchmark {b.get('benchmark_id', '??')} missing: {missing}"
            )

    def test_all_benchmarks_have_unique_ids(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        ids = [b["benchmark_id"] for b in EXTERNAL_BENCHMARK_REGISTRY]
        assert len(ids) == len(set(ids)), "Duplicate benchmark IDs found"

    def test_all_axes_have_at_least_one_benchmark(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        for axis_id in range(1, 7):
            benchmarks = get_benchmarks_for_axis(axis_id)
            assert len(benchmarks) >= 1, (
                f"Axis {axis_id} has no benchmarks defined"
            )

    def test_alignment_thresholds_are_valid(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            thresholds = b["alignment_thresholds"]
            assert "strong_alignment_min" in thresholds
            assert "weak_alignment_min" in thresholds
            # Strong threshold must be >= weak threshold
            assert thresholds["strong_alignment_min"] >= thresholds["weak_alignment_min"], (
                f"Benchmark {b['benchmark_id']}: strong < weak"
            )

    def test_valid_comparison_types(self):
        from backend.benchmark_registry import (
            EXTERNAL_BENCHMARK_REGISTRY,
            VALID_COMPARISON_TYPES,
        )
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            assert b["comparison_type"] in VALID_COMPARISON_TYPES, (
                f"Invalid comparison type for {b['benchmark_id']}"
            )

    def test_valid_integration_statuses(self):
        from backend.benchmark_registry import (
            EXTERNAL_BENCHMARK_REGISTRY,
            VALID_INTEGRATION_STATUSES,
        )
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            assert b["status"] in VALID_INTEGRATION_STATUSES, (
                f"Invalid status for {b['benchmark_id']}"
            )

    def test_valid_axis_ids(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            for ax in b["relevant_axes"]:
                assert 1 <= ax <= 6, (
                    f"Invalid axis {ax} in {b['benchmark_id']}"
                )

    def test_get_benchmark_by_id_found(self):
        from backend.benchmark_registry import get_benchmark_by_id
        result = get_benchmark_by_id("EXT_IEA_ENERGY")
        assert result is not None
        assert result["benchmark_id"] == "EXT_IEA_ENERGY"
        assert 2 in result["relevant_axes"]

    def test_get_benchmark_by_id_not_found(self):
        from backend.benchmark_registry import get_benchmark_by_id
        result = get_benchmark_by_id("NONEXISTENT_BENCHMARK")
        assert result is None

    def test_get_benchmarks_for_axis_returns_correct_axes(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        axis2 = get_benchmarks_for_axis(2)
        for b in axis2:
            assert 2 in b["relevant_axes"]

    def test_get_benchmarks_by_status(self):
        from backend.benchmark_registry import (
            get_benchmarks_by_status,
            IntegrationStatus,
        )
        defined = get_benchmarks_by_status(IntegrationStatus.STRUCTURALLY_DEFINED)
        assert len(defined) >= 5  # Most benchmarks are structurally defined

    def test_coverage_summary_structure(self):
        from backend.benchmark_registry import get_benchmark_coverage_summary
        summary = get_benchmark_coverage_summary()
        assert "total_benchmarks" in summary
        assert "per_axis_coverage" in summary
        assert "honesty_note" in summary
        for ax in range(1, 7):
            assert ax in summary["per_axis_coverage"]
            ax_cov = summary["per_axis_coverage"][ax]
            assert "n_benchmarks" in ax_cov
            assert "benchmark_ids" in ax_cov

    def test_validate_benchmark_registry_clean(self):
        from backend.benchmark_registry import validate_benchmark_registry
        issues = validate_benchmark_registry()
        assert len(issues) == 0, f"Registry validation issues: {issues}"

    def test_registry_returns_copies(self):
        """Query functions should return copies, not mutable references."""
        from backend.benchmark_registry import get_benchmark_registry
        reg1 = get_benchmark_registry()
        reg2 = get_benchmark_registry()
        assert reg1 is not reg2

    def test_axis_1_has_bis_cbs(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        axis1 = get_benchmarks_for_axis(1)
        ids = [b["benchmark_id"] for b in axis1]
        assert "EXT_BIS_CBS" in ids

    def test_axis_2_has_energy_benchmarks(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        axis2 = get_benchmarks_for_axis(2)
        ids = [b["benchmark_id"] for b in axis2]
        assert "EXT_IEA_ENERGY" in ids
        assert "EXT_EUROSTAT_ENERGY" in ids

    def test_axis_4_has_defense_benchmarks(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        axis4 = get_benchmarks_for_axis(4)
        ids = [b["benchmark_id"] for b in axis4]
        assert "EXT_SIPRI_MILEX" in ids

    def test_axis_5_has_crm(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        axis5 = get_benchmarks_for_axis(5)
        ids = [b["benchmark_id"] for b in axis5]
        assert "EXT_EU_CRM" in ids

    def test_axis_6_has_logistics_benchmarks(self):
        from backend.benchmark_registry import get_benchmarks_for_axis
        axis6 = get_benchmarks_for_axis(6)
        ids = [b["benchmark_id"] for b in axis6]
        assert "EXT_UNCTAD_LSCI" in ids
        assert "EXT_WORLD_BANK_LPI" in ids

    def test_construct_descriptions_are_non_empty(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            assert len(b["construct_description"]) > 20, (
                f"{b['benchmark_id']} has too-short construct description"
            )
            assert len(b["construct_overlap_with_isi"]) > 10
            assert len(b["construct_divergence_from_isi"]) > 10

    def test_integration_requirements_non_empty(self):
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        for b in EXTERNAL_BENCHMARK_REGISTRY:
            assert len(b["integration_requirements"]) >= 2, (
                f"{b['benchmark_id']} needs >= 2 integration requirements"
            )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: ALIGNMENT CLASSES AND CLASSIFICATION TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestAlignmentClasses:
    """Tests for alignment classification logic."""

    def test_alignment_class_values(self):
        from backend.benchmark_registry import AlignmentClass
        assert AlignmentClass.STRONGLY_ALIGNED == "STRONGLY_ALIGNED"
        assert AlignmentClass.WEAKLY_ALIGNED == "WEAKLY_ALIGNED"
        assert AlignmentClass.DIVERGENT == "DIVERGENT"
        assert AlignmentClass.STRUCTURALLY_INCOMPARABLE == "STRUCTURALLY_INCOMPARABLE"
        assert AlignmentClass.NO_DATA == "NO_DATA"

    def test_valid_alignment_classes_complete(self):
        from backend.benchmark_registry import (
            AlignmentClass,
            VALID_ALIGNMENT_CLASSES,
        )
        assert len(VALID_ALIGNMENT_CLASSES) == 5

    def test_comparison_type_values(self):
        from backend.benchmark_registry import ComparisonType
        assert ComparisonType.RANK_CORRELATION == "RANK_CORRELATION"
        assert ComparisonType.STRUCTURAL_CONSISTENCY == "STRUCTURAL_CONSISTENCY"
        assert ComparisonType.DIRECTIONAL_AGREEMENT == "DIRECTIONAL_AGREEMENT"
        assert ComparisonType.LEVEL_COMPARISON == "LEVEL_COMPARISON"

    def test_integration_status_values(self):
        from backend.benchmark_registry import IntegrationStatus
        assert IntegrationStatus.INTEGRATED == "INTEGRATED"
        assert IntegrationStatus.STRUCTURALLY_DEFINED == "STRUCTURALLY_DEFINED"
        assert IntegrationStatus.NOT_INTEGRATED == "NOT_INTEGRATED"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: COMPARE_TO_BENCHMARK TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestCompareToBenchmark:
    """Tests for the core compare_to_benchmark function."""

    def test_unknown_benchmark_returns_no_data(self):
        from backend.external_validation import compare_to_benchmark
        result = compare_to_benchmark("FAKE_BENCHMARK", {}, {})
        assert result["alignment_class"] == "NO_DATA"
        assert "error" in result

    def test_none_isi_values_returns_no_data(self):
        from backend.external_validation import compare_to_benchmark
        result = compare_to_benchmark("EXT_IEA_ENERGY", None, {"DE": 0.5})
        assert result["alignment_class"] == "NO_DATA"
        assert "ISI data not provided" in result["reason"]

    def test_none_external_values_returns_no_data(self):
        from backend.external_validation import compare_to_benchmark
        result = compare_to_benchmark("EXT_IEA_ENERGY", {"DE": 0.5}, None)
        assert result["alignment_class"] == "NO_DATA"
        assert "External benchmark data not provided" in result["reason"]

    def test_empty_isi_values_returns_no_data(self):
        from backend.external_validation import compare_to_benchmark
        result = compare_to_benchmark("EXT_IEA_ENERGY", {}, {"DE": 0.5})
        assert result["alignment_class"] == "NO_DATA"

    def test_insufficient_overlap_returns_incomparable(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"DE": 0.5, "FR": 0.4, "IT": 0.3}
        ext = {"US": 0.5, "CN": 0.4, "JP": 0.3}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert result["alignment_class"] == "STRUCTURALLY_INCOMPARABLE"

    def test_four_overlap_countries_still_incomparable(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"DE": 0.5, "FR": 0.4, "IT": 0.3, "ES": 0.2}
        ext = {"DE": 0.5, "FR": 0.4, "IT": 0.3, "ES": 0.2}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        # 4 countries < 5 minimum
        assert result["alignment_class"] == "STRUCTURALLY_INCOMPARABLE"

    def test_perfect_rank_correlation_strongly_aligned(self):
        from backend.external_validation import compare_to_benchmark
        # Same ranking, different absolute values
        isi = {"DE": 0.9, "FR": 0.7, "IT": 0.5, "ES": 0.3, "NL": 0.1}
        ext = {"DE": 0.8, "FR": 0.6, "IT": 0.4, "ES": 0.2, "NL": 0.05}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert result["alignment_class"] == "STRONGLY_ALIGNED"
        assert result["metric_value"] is not None
        assert result["metric_value"] > 0.9

    def test_inverse_rank_correlation(self):
        from backend.external_validation import compare_to_benchmark
        # Perfect inverse ranking
        isi = {"DE": 0.9, "FR": 0.7, "IT": 0.5, "ES": 0.3, "NL": 0.1}
        ext = {"DE": 0.1, "FR": 0.3, "IT": 0.5, "ES": 0.7, "NL": 0.9}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        # IEA expects strong_alignment_min=0.65, so |rho|=1.0 → STRONGLY_ALIGNED
        # because we use absolute value for rank correlation
        assert result["metric_value"] is not None
        assert abs(result["metric_value"] + 1.0) < 0.01  # rho ≈ -1.0
        assert result["alignment_class"] == "STRONGLY_ALIGNED"  # |rho| = 1.0

    def test_random_ranking_divergent(self):
        from backend.external_validation import compare_to_benchmark
        # Rankings that genuinely don't correlate (scrambled, not inverse)
        isi = {"DE": 0.9, "FR": 0.7, "IT": 0.5, "ES": 0.3, "NL": 0.1}
        ext = {"DE": 0.5, "FR": 0.1, "IT": 0.9, "ES": 0.3, "NL": 0.7}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        # ISI rank: DE=1, FR=2, IT=3, ES=4, NL=5
        # EXT rank: IT=1, NL=2, DE=3, ES=4, FR=5 → rho should be low
        assert result["alignment_class"] in ("DIVERGENT", "WEAKLY_ALIGNED")

    def test_result_has_honesty_note(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"DE": 0.9, "FR": 0.7, "IT": 0.5, "ES": 0.3, "NL": 0.1}
        ext = {"DE": 0.8, "FR": 0.6, "IT": 0.4, "ES": 0.2, "NL": 0.05}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert "honesty_note" in result

    def test_result_has_construct_notes(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"DE": 0.9, "FR": 0.7, "IT": 0.5, "ES": 0.3, "NL": 0.1}
        ext = {"DE": 0.8, "FR": 0.6, "IT": 0.4, "ES": 0.2, "NL": 0.05}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert "construct_overlap_note" in result
        assert "construct_divergence_note" in result
        assert "divergence_interpretation" in result

    def test_result_has_per_country_detail(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"DE": 0.9, "FR": 0.7, "IT": 0.5, "ES": 0.3, "NL": 0.1}
        ext = {"DE": 0.8, "FR": 0.6, "IT": 0.4, "ES": 0.2, "NL": 0.05}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert "per_country_detail" in result
        assert len(result["per_country_detail"]) == 5


class TestStructuralConsistency:
    """Tests for structural consistency comparison (SIPRI MILEX-type)."""

    def test_sipri_milex_consistency_check(self):
        from backend.external_validation import compare_to_benchmark
        # High MILEX + low ISI → producer inversion signal
        isi = {"US": 0.1, "FR": 0.15, "DE": 0.12, "IT": 0.4, "ES": 0.35}
        ext = {"US": 0.8, "FR": 0.6, "DE": 0.4, "IT": 0.2, "ES": 0.15}
        result = compare_to_benchmark("EXT_SIPRI_MILEX", isi, ext)
        assert result["benchmark_id"] == "EXT_SIPRI_MILEX"
        assert result["comparison_type"] == "STRUCTURAL_CONSISTENCY"
        assert "metric_value" in result

    def test_fully_consistent_structural_check(self):
        from backend.external_validation import compare_to_benchmark
        # No inconsistencies
        isi = {"DE": 0.5, "FR": 0.4, "IT": 0.3, "ES": 0.2, "NL": 0.6}
        ext = {"DE": 0.2, "FR": 0.15, "IT": 0.1, "ES": 0.1, "NL": 0.3}
        result = compare_to_benchmark("EXT_SIPRI_MILEX", isi, ext)
        assert result["metric_value"] is not None
        # All consistent (no high ext + low isi)
        assert result["metric_value"] == 1.0


class TestDirectionalAgreement:
    """Tests for directional agreement comparison."""

    def test_directional_agreement_with_agreement(self):
        from backend.external_validation import compare_to_benchmark
        # Same top-half countries
        isi = {"DE": 0.9, "FR": 0.8, "IT": 0.3, "ES": 0.2, "NL": 0.1}
        ext = {"DE": 0.95, "FR": 0.85, "IT": 0.35, "ES": 0.25, "NL": 0.15}
        result = compare_to_benchmark("EXT_USGS_MINERALS", isi, ext)
        assert result["comparison_type"] == "DIRECTIONAL_AGREEMENT"
        assert result["metric_value"] is not None
        assert result["metric_value"] >= 0.8  # High agreement


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: RANK CORRELATION INTERNALS
# ═══════════════════════════════════════════════════════════════════════════


class TestRankComputation:
    """Tests for internal rank computation."""

    def test_compute_ranks_simple(self):
        from backend.external_validation import _compute_ranks
        values = [10.0, 20.0, 30.0, 40.0]
        ranks = _compute_ranks(values)
        assert ranks == [1.0, 2.0, 3.0, 4.0]

    def test_compute_ranks_reverse(self):
        from backend.external_validation import _compute_ranks
        values = [40.0, 30.0, 20.0, 10.0]
        ranks = _compute_ranks(values)
        assert ranks == [4.0, 3.0, 2.0, 1.0]

    def test_compute_ranks_ties(self):
        from backend.external_validation import _compute_ranks
        values = [10.0, 20.0, 20.0, 30.0]
        ranks = _compute_ranks(values)
        assert ranks[0] == 1.0
        assert ranks[1] == 2.5  # Average of 2 and 3
        assert ranks[2] == 2.5
        assert ranks[3] == 4.0

    def test_compute_ranks_all_tied(self):
        from backend.external_validation import _compute_ranks
        values = [5.0, 5.0, 5.0]
        ranks = _compute_ranks(values)
        assert ranks == [2.0, 2.0, 2.0]

    def test_compute_ranks_single_value(self):
        from backend.external_validation import _compute_ranks
        values = [42.0]
        ranks = _compute_ranks(values)
        assert ranks == [1.0]


class TestAlignmentClassification:
    """Tests for the _classify_alignment function."""

    def test_classify_strong_alignment(self):
        from backend.external_validation import _classify_alignment
        from backend.benchmark_registry import ComparisonType, AlignmentClass
        result = _classify_alignment(0.8, 0.65, 0.35, ComparisonType.RANK_CORRELATION)
        assert result == AlignmentClass.STRONGLY_ALIGNED

    def test_classify_weak_alignment(self):
        from backend.external_validation import _classify_alignment
        from backend.benchmark_registry import ComparisonType, AlignmentClass
        result = _classify_alignment(0.5, 0.65, 0.35, ComparisonType.RANK_CORRELATION)
        assert result == AlignmentClass.WEAKLY_ALIGNED

    def test_classify_divergent(self):
        from backend.external_validation import _classify_alignment
        from backend.benchmark_registry import ComparisonType, AlignmentClass
        result = _classify_alignment(0.1, 0.65, 0.35, ComparisonType.RANK_CORRELATION)
        assert result == AlignmentClass.DIVERGENT

    def test_classify_no_data(self):
        from backend.external_validation import _classify_alignment
        from backend.benchmark_registry import ComparisonType, AlignmentClass
        result = _classify_alignment(None, 0.65, 0.35, ComparisonType.RANK_CORRELATION)
        assert result == AlignmentClass.NO_DATA

    def test_classify_negative_correlation_uses_absolute(self):
        from backend.external_validation import _classify_alignment
        from backend.benchmark_registry import ComparisonType, AlignmentClass
        # -0.8 should be treated as |0.8| for rank correlation
        result = _classify_alignment(-0.8, 0.65, 0.35, ComparisonType.RANK_CORRELATION)
        assert result == AlignmentClass.STRONGLY_ALIGNED


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: COUNTRY ALIGNMENT ASSESSMENT TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestCountryAlignment:
    """Tests for assess_country_alignment."""

    def _make_axis_scores(self, **kwargs):
        """Create axis_scores dict with defaults."""
        defaults = {1: 0.5, 2: 0.4, 3: 0.3, 4: 0.2, 5: 0.6, 6: 0.35}
        defaults.update(kwargs)
        return defaults

    def test_no_external_data_returns_no_data(self):
        from backend.external_validation import assess_country_alignment
        from backend.benchmark_registry import AlignmentClass
        result = assess_country_alignment(
            "DE", self._make_axis_scores(), external_data=None,
        )
        assert result["overall_alignment"] == AlignmentClass.NO_DATA
        assert result["n_axes_compared"] == 0

    def test_result_structure(self):
        from backend.external_validation import assess_country_alignment
        result = assess_country_alignment(
            "DE", self._make_axis_scores(), external_data=None,
        )
        assert "country" in result
        assert "overall_alignment" in result
        assert "n_axes_compared" in result
        assert "n_axes_aligned" in result
        assert "n_axes_divergent" in result
        assert "axis_alignments" in result
        assert "honesty_note" in result

    def test_axis_alignments_cover_all_six(self):
        from backend.external_validation import assess_country_alignment
        result = assess_country_alignment(
            "DE", self._make_axis_scores(), external_data=None,
        )
        assert len(result["axis_alignments"]) == 6
        axis_ids = [aa["axis_id"] for aa in result["axis_alignments"]]
        assert axis_ids == [1, 2, 3, 4, 5, 6]

    def test_missing_isi_score_flagged(self):
        from backend.external_validation import assess_country_alignment
        scores = self._make_axis_scores()
        scores[3] = None  # Missing axis 3
        result = assess_country_alignment("DE", scores, external_data=None)
        axis3 = result["axis_alignments"][2]
        assert axis3["alignment_status"] == "ISI_SCORE_MISSING"

    def test_with_external_data_compares(self):
        from backend.external_validation import assess_country_alignment
        ext_data = {
            "EXT_IEA_ENERGY": {
                "DE": 0.4, "FR": 0.35, "IT": 0.45, "ES": 0.3, "NL": 0.25,
            },
        }
        result = assess_country_alignment(
            "DE", self._make_axis_scores(), external_data=ext_data,
        )
        # Should have compared at least one benchmark
        axis2 = result["axis_alignments"][1]
        assert len(axis2["benchmark_results"]) > 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: CONSTRUCT VALIDITY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestConstructValidity:
    """Tests for assess_construct_validity."""

    def test_no_external_data_all_not_assessed(self):
        from backend.external_validation import assess_construct_validity
        all_scores = {
            ax: {"DE": 0.5, "FR": 0.4, "IT": 0.3}
            for ax in range(1, 7)
        }
        result = assess_construct_validity(all_scores, external_data=None)
        assert "per_axis_validity" in result
        assert "summary" in result
        assert result["summary"]["n_axes_not_assessed"] == 6

    def test_system_validity_status_without_data(self):
        from backend.external_validation import assess_construct_validity
        all_scores = {ax: {} for ax in range(1, 7)}
        result = assess_construct_validity(all_scores, external_data=None)
        assert result["system_validity_status"] == "NOT_ASSESSED"

    def test_result_has_honesty_note(self):
        from backend.external_validation import assess_construct_validity
        all_scores = {ax: {} for ax in range(1, 7)}
        result = assess_construct_validity(all_scores, external_data=None)
        assert "honesty_note" in result


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: EXTERNAL VALIDATION BLOCK TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestExternalValidationBlock:
    """Tests for build_external_validation_block."""

    def test_block_structure_without_data(self):
        from backend.external_validation import build_external_validation_block
        scores = {ax: 0.5 for ax in range(1, 7)}
        block = build_external_validation_block("DE", scores, external_data=None)
        assert "overall_alignment" in block
        assert "benchmark_coverage" in block
        assert "per_axis_summary" in block
        assert "honesty_note" in block
        assert "empirical_grounding_answer" in block

    def test_grounding_answer_without_data(self):
        from backend.external_validation import build_external_validation_block
        scores = {ax: 0.5 for ax in range(1, 7)}
        block = build_external_validation_block("DE", scores, external_data=None)
        answer = block["empirical_grounding_answer"]
        assert "CANNOT ANSWER" in answer

    def test_per_axis_summary_has_six_entries(self):
        from backend.external_validation import build_external_validation_block
        scores = {ax: 0.5 for ax in range(1, 7)}
        block = build_external_validation_block("DE", scores, external_data=None)
        assert len(block["per_axis_summary"]) == 6

    def test_benchmark_coverage_reflects_registry(self):
        from backend.external_validation import build_external_validation_block
        from backend.benchmark_registry import EXTERNAL_BENCHMARK_REGISTRY
        scores = {ax: 0.5 for ax in range(1, 7)}
        block = build_external_validation_block("DE", scores, external_data=None)
        total_defined = block["benchmark_coverage"]["total_benchmarks_defined"]
        assert total_defined == len(EXTERNAL_BENCHMARK_REGISTRY)


class TestEmpiricalGroundingAnswer:
    """Tests for the explicit YES/NO answer function."""

    def test_no_data_says_cannot_answer(self):
        from backend.external_validation import _empirical_grounding_answer
        alignment = {"overall_alignment": "NO_DATA", "n_axes_compared": 0}
        answer = _empirical_grounding_answer(alignment)
        assert "CANNOT ANSWER" in answer

    def test_strongly_aligned_says_yes(self):
        from backend.external_validation import _empirical_grounding_answer
        alignment = {
            "overall_alignment": "STRONGLY_ALIGNED",
            "n_axes_compared": 4,
        }
        answer = _empirical_grounding_answer(alignment)
        assert answer.startswith("YES")

    def test_weakly_aligned_says_partially(self):
        from backend.external_validation import _empirical_grounding_answer
        alignment = {
            "overall_alignment": "WEAKLY_ALIGNED",
            "n_axes_compared": 3,
        }
        answer = _empirical_grounding_answer(alignment)
        assert "PARTIALLY" in answer

    def test_divergent_says_no(self):
        from backend.external_validation import _empirical_grounding_answer
        alignment = {
            "overall_alignment": "DIVERGENT",
            "n_axes_compared": 3,
        }
        answer = _empirical_grounding_answer(alignment)
        assert answer.startswith("NO")

    def test_incomparable_says_cannot_answer(self):
        from backend.external_validation import _empirical_grounding_answer
        alignment = {
            "overall_alignment": "STRUCTURALLY_INCOMPARABLE",
            "n_axes_compared": 0,
        }
        answer = _empirical_grounding_answer(alignment)
        assert "CANNOT ANSWER" in answer


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: EXTERNAL VALIDATION STATUS TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestExternalValidationStatus:
    """Tests for get_external_validation_status."""

    def test_status_structure(self):
        from backend.external_validation import get_external_validation_status
        status = get_external_validation_status()
        assert "validation_status" in status
        assert "does_this_align_with_reality" in status
        assert "benchmark_coverage" in status
        assert "honesty_note" in status

    def test_current_status_reflects_zero_integration(self):
        """Currently no benchmarks are INTEGRATED (all STRUCTURALLY_DEFINED)."""
        from backend.external_validation import get_external_validation_status
        status = get_external_validation_status()
        # No benchmarks have status=INTEGRATED yet
        assert status["validation_status"] == "NOT_EXTERNALLY_VALIDATED"
        assert "NO" in status["does_this_align_with_reality"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: INVARIANTS EXTERNAL VALIDITY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestExternalValidityInvariants:
    """Tests for EXTERNAL_VALIDITY invariant type in invariants.py."""

    def test_external_validity_type_exists(self):
        from backend.invariants import InvariantType, VALID_INVARIANT_TYPES
        assert InvariantType.EXTERNAL_VALIDITY == "EXTERNAL_VALIDITY"
        assert "EXTERNAL_VALIDITY" in VALID_INVARIANT_TYPES

    def test_external_validity_invariants_in_registry(self):
        from backend.invariants import INVARIANT_REGISTRY, InvariantType
        ext_invariants = [
            i for i in INVARIANT_REGISTRY
            if i["type"] == InvariantType.EXTERNAL_VALIDITY
        ]
        assert len(ext_invariants) >= 4
        ids = {i["invariant_id"] for i in ext_invariants}
        assert "EXT-001" in ids
        assert "EXT-002" in ids
        assert "EXT-003" in ids
        assert "EXT-004" in ids

    def test_check_external_validity_no_alignment(self):
        """No alignment data → no violations."""
        from backend.invariants import check_external_validity_invariants
        violations = check_external_validity_invariants(
            "DE", {"governance_tier": "FULLY_COMPARABLE"},
            alignment_result=None,
        )
        assert len(violations) == 0

    def test_ext_001_high_confidence_divergent_alignment(self):
        from backend.invariants import check_external_validity_invariants
        gov = {
            "governance_tier": "FULLY_COMPARABLE",
            "axis_confidences": [
                {"axis_id": 2, "confidence_level": "HIGH", "confidence_score": 0.75},
            ],
        }
        alignment = {
            "overall_alignment": "DIVERGENT",
            "n_axes_compared": 1,
            "n_axes_divergent": 1,
            "n_axes_aligned": 0,
            "axis_alignments": [
                {
                    "axis_id": 2,
                    "benchmark_results": [
                        {
                            "benchmark_id": "EXT_IEA_ENERGY",
                            "alignment_class": "DIVERGENT",
                            "metric_value": 0.1,
                        },
                    ],
                },
            ],
        }
        violations = check_external_validity_invariants(
            "DE", gov, alignment_result=alignment,
        )
        ext_001 = [v for v in violations if v["invariant_id"] == "EXT-001"]
        assert len(ext_001) == 1
        assert ext_001[0]["severity"] == "WARNING"

    def test_ext_002_trusted_without_empirical(self):
        from backend.invariants import check_external_validity_invariants
        gov = {"governance_tier": "FULLY_COMPARABLE", "axis_confidences": []}
        alignment = {
            "overall_alignment": "NO_DATA",
            "n_axes_compared": 0,
            "n_axes_divergent": 0,
            "n_axes_aligned": 0,
            "axis_alignments": [],
        }
        violations = check_external_validity_invariants(
            "DE", gov, alignment_result=alignment,
            decision_usability_class="TRUSTED_COMPARABLE",
        )
        ext_002 = [v for v in violations if v["invariant_id"] == "EXT-002"]
        assert len(ext_002) == 1
        assert ext_002[0]["severity"] == "WARNING"

    def test_ext_002_not_triggered_for_conditionally_usable(self):
        from backend.invariants import check_external_validity_invariants
        gov = {"governance_tier": "PARTIALLY_COMPARABLE", "axis_confidences": []}
        alignment = {
            "overall_alignment": "NO_DATA",
            "n_axes_compared": 0,
            "n_axes_divergent": 0,
            "n_axes_aligned": 0,
            "axis_alignments": [],
        }
        violations = check_external_validity_invariants(
            "DE", gov, alignment_result=alignment,
            decision_usability_class="CONDITIONALLY_USABLE",
        )
        ext_002 = [v for v in violations if v["invariant_id"] == "EXT-002"]
        assert len(ext_002) == 0

    def test_ext_004_majority_divergent(self):
        from backend.invariants import check_external_validity_invariants
        gov = {"governance_tier": "PARTIALLY_COMPARABLE", "axis_confidences": []}
        alignment = {
            "overall_alignment": "DIVERGENT",
            "n_axes_compared": 4,
            "n_axes_divergent": 3,
            "n_axes_aligned": 1,
            "axis_alignments": [],
        }
        violations = check_external_validity_invariants(
            "DE", gov, alignment_result=alignment,
        )
        ext_004 = [v for v in violations if v["invariant_id"] == "EXT-004"]
        assert len(ext_004) == 1
        assert ext_004[0]["severity"] == "ERROR"

    def test_ext_004_not_triggered_when_aligned(self):
        from backend.invariants import check_external_validity_invariants
        gov = {"governance_tier": "FULLY_COMPARABLE", "axis_confidences": []}
        alignment = {
            "overall_alignment": "STRONGLY_ALIGNED",
            "n_axes_compared": 4,
            "n_axes_divergent": 0,
            "n_axes_aligned": 4,
            "axis_alignments": [],
        }
        violations = check_external_validity_invariants(
            "DE", gov, alignment_result=alignment,
        )
        ext_004 = [v for v in violations if v["invariant_id"] == "EXT-004"]
        assert len(ext_004) == 0

    def test_assess_country_invariants_with_alignment(self):
        """assess_country_invariants now accepts alignment_result."""
        from backend.invariants import assess_country_invariants
        axis_scores = {ax: 0.5 for ax in range(1, 7)}
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
            "overall_alignment": "NO_DATA",
            "n_axes_compared": 0,
            "n_axes_divergent": 0,
            "n_axes_aligned": 0,
            "axis_alignments": [],
        }
        result = assess_country_invariants(
            "DE", axis_scores, gov,
            alignment_result=alignment,
            decision_usability_class="TRUSTED_COMPARABLE",
        )
        assert result["n_violations"] >= 1  # EXT-002 should fire
        ext_002 = [
            v for v in result["violations"]
            if v["invariant_id"] == "EXT-002"
        ]
        assert len(ext_002) == 1

    def test_assess_country_invariants_backward_compatible(self):
        """assess_country_invariants works without new optional params."""
        from backend.invariants import assess_country_invariants
        # Use varied scores to avoid CA-004 (uniform score anomaly, range < 0.02)
        axis_scores = {1: 0.4, 2: 0.5, 3: 0.6, 4: 0.5, 5: 0.45, 6: 0.55}
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
        # Call without alignment_result — backward compatible
        result = assess_country_invariants("DE", axis_scores, gov)
        assert result["n_violations"] == 0  # No violations expected

    def test_invariant_registry_total_count(self):
        from backend.invariants import INVARIANT_REGISTRY
        # Was 13, then 17 (4 external validity), then 21 (4 construct enforcement),
        # then 25 (2 failure visibility + 2 authority consistency),
        # then 28 (3 reality conflict), 33 (5 pipeline integrity from Final Closure Pass),
        # then 37 (4 runtime invariants from Production Hardening Pass),
        # now 47 (10 epistemic monotonicity invariants from Endgame Pass v2)
        assert len(INVARIANT_REGISTRY) == 47


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10: SPEARMAN RHO MATHEMATICAL CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════════


class TestSpearmanRhoCorrectness:
    """Verify Spearman rho computation against known results."""

    def test_perfect_positive_correlation(self):
        from backend.external_validation import _compute_rank_correlation
        isi = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}
        ext = {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "E": 50.0}
        overlap = sorted(isi.keys())
        result = _compute_rank_correlation(isi, ext, overlap)
        assert abs(result["metric"] - 1.0) < 1e-6

    def test_perfect_negative_correlation(self):
        from backend.external_validation import _compute_rank_correlation
        isi = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}
        ext = {"A": 50.0, "B": 40.0, "C": 30.0, "D": 20.0, "E": 10.0}
        overlap = sorted(isi.keys())
        result = _compute_rank_correlation(isi, ext, overlap)
        assert abs(result["metric"] + 1.0) < 1e-6

    def test_zero_correlation(self):
        """Orthogonal rankings should give rho near 0."""
        from backend.external_validation import _compute_rank_correlation
        # Ranks: 1,2,3,4,5 vs 3,5,2,1,4 → d²: 4,9,1,9,1 → Σ=24
        # rho = 1 - 6*24/(5*24) = 1 - 1.2 = -0.2
        isi = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0}
        ext = {"A": 3.0, "B": 5.0, "C": 2.0, "D": 1.0, "E": 4.0}
        overlap = sorted(isi.keys())
        result = _compute_rank_correlation(isi, ext, overlap)
        assert abs(result["metric"] - (-0.2)) < 1e-6

    def test_with_tied_values(self):
        from backend.external_validation import _compute_rank_correlation
        isi = {"A": 1.0, "B": 2.0, "C": 2.0, "D": 4.0, "E": 5.0}
        ext = {"A": 10.0, "B": 20.0, "C": 30.0, "D": 40.0, "E": 50.0}
        overlap = sorted(isi.keys())
        result = _compute_rank_correlation(isi, ext, overlap)
        # Should be high positive but not exactly 1.0 due to tie handling
        assert result["metric"] > 0.8
        assert result["metric"] <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11: LEVEL COMPARISON TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestLevelComparison:
    """Tests for level comparison metric."""

    def test_perfect_level_match(self):
        from backend.external_validation import _compute_level_comparison
        isi = {"A": 0.5, "B": 0.3, "C": 0.8, "D": 0.2, "E": 0.6}
        ext = {"A": 0.5, "B": 0.3, "C": 0.8, "D": 0.2, "E": 0.6}
        overlap = sorted(isi.keys())
        result = _compute_level_comparison(isi, ext, overlap)
        assert result["metric"] == 1.0
        assert result["mean_absolute_difference"] == 0.0

    def test_max_divergence(self):
        from backend.external_validation import _compute_level_comparison
        isi = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0, "E": 0.0}
        ext = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0, "E": 1.0}
        overlap = sorted(isi.keys())
        result = _compute_level_comparison(isi, ext, overlap)
        assert result["metric"] == 0.0
        assert result["mean_absolute_difference"] == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 12: INTEGRATION FLOW TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegrationFlow:
    """End-to-end integration tests."""

    def test_full_comparison_flow(self):
        """Run a complete comparison from benchmark to alignment class."""
        from backend.external_validation import compare_to_benchmark
        from backend.benchmark_registry import AlignmentClass

        # Simulate ISI Axis 2 scores for EU countries
        isi = {
            "DE": 0.65, "FR": 0.55, "IT": 0.70, "ES": 0.50,
            "NL": 0.45, "BE": 0.40, "AT": 0.60, "PL": 0.58,
        }
        # Simulate IEA energy dependency data (different scale but same ordering)
        ext = {
            "DE": 0.62, "FR": 0.50, "IT": 0.78, "ES": 0.48,
            "NL": 0.42, "BE": 0.38, "AT": 0.55, "PL": 0.52,
        }

        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert result["alignment_class"] in (
            AlignmentClass.STRONGLY_ALIGNED,
            AlignmentClass.WEAKLY_ALIGNED,
        )
        assert result["n_overlap_countries"] == 8
        assert result["metric_name"] == "spearman_rho"

    def test_full_country_alignment_flow(self):
        """Run country alignment with actual benchmark data."""
        from backend.external_validation import assess_country_alignment

        scores = {1: 0.5, 2: 0.6, 3: 0.4, 4: 0.2, 5: 0.7, 6: 0.35}
        ext_data = {
            "EXT_IEA_ENERGY": {
                "DE": 0.62, "FR": 0.50, "IT": 0.78, "ES": 0.48,
                "NL": 0.42, "BE": 0.38, "AT": 0.55, "PL": 0.52,
            },
        }
        result = assess_country_alignment("DE", scores, ext_data)
        assert result["country"] == "DE"
        assert "overall_alignment" in result

    def test_construct_validity_flow(self):
        """Run construct validity check across all axes."""
        from backend.external_validation import assess_construct_validity

        all_scores = {
            ax: {
                "DE": 0.5, "FR": 0.4, "IT": 0.6, "ES": 0.3,
                "NL": 0.45, "BE": 0.35, "AT": 0.55, "PL": 0.48,
            }
            for ax in range(1, 7)
        }
        ext_data = {
            "EXT_IEA_ENERGY": {
                "DE": 0.55, "FR": 0.45, "IT": 0.65, "ES": 0.35,
                "NL": 0.50, "BE": 0.40, "AT": 0.60, "PL": 0.52,
            },
        }
        result = assess_construct_validity(all_scores, ext_data)
        assert result["per_axis_validity"][2]["n_benchmarks_compared"] >= 1

    def test_external_validation_status_api(self):
        """get_external_validation_status is callable and structured."""
        from backend.external_validation import get_external_validation_status
        status = get_external_validation_status()
        assert status["validation_status"] == "NOT_EXTERNALLY_VALIDATED"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 13: EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_single_country_overlap(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"DE": 0.5}
        ext = {"DE": 0.5}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert result["alignment_class"] == "STRUCTURALLY_INCOMPARABLE"

    def test_identical_values_all_countries(self):
        from backend.external_validation import compare_to_benchmark
        isi = {"A": 0.5, "B": 0.5, "C": 0.5, "D": 0.5, "E": 0.5}
        ext = {"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3, "E": 0.3}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        # All tied → rank correlation may be undefined or degenerate
        assert result["alignment_class"] is not None

    def test_very_large_overlap(self):
        from backend.external_validation import compare_to_benchmark
        countries = [f"C{i:02d}" for i in range(100)]
        isi = {c: i / 100.0 for i, c in enumerate(countries)}
        ext = {c: i / 100.0 for i, c in enumerate(countries)}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert result["alignment_class"] == "STRONGLY_ALIGNED"
        assert result["n_overlap_countries"] == 100

    def test_axis_scores_with_none_values(self):
        from backend.external_validation import assess_country_alignment
        scores = {1: None, 2: None, 3: None, 4: None, 5: None, 6: None}
        result = assess_country_alignment("DE", scores, external_data=None)
        # All axes missing → no comparisons
        assert result["n_axes_compared"] == 0

    def test_negative_isi_values_handled(self):
        """ISI scores should be 0-1, but engine shouldn't crash on negatives."""
        from backend.external_validation import compare_to_benchmark
        isi = {"A": -0.1, "B": 0.2, "C": 0.5, "D": 0.8, "E": 1.1}
        ext = {"A": 0.1, "B": 0.3, "C": 0.5, "D": 0.7, "E": 0.9}
        result = compare_to_benchmark("EXT_IEA_ENERGY", isi, ext)
        assert result["alignment_class"] is not None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 14: CONSISTENCY WITH EXISTING SYSTEMS
# ═══════════════════════════════════════════════════════════════════════════


class TestConsistencyWithExistingSystems:
    """Verify new external validation integrates with existing modules."""

    def test_benchmark_registry_consistent_with_falsification(self):
        """benchmark_registry covers the same axes as falsification.py's
        BENCHMARK_REGISTRY (legacy)."""
        from backend.benchmark_registry import get_benchmarks_for_axis
        from backend.falsification import BENCHMARK_REGISTRY as LEGACY_REG

        # Every legacy benchmark axis should have a new registry entry
        for legacy_b in LEGACY_REG:
            for ax in legacy_b["relevant_axes"]:
                new_benchmarks = get_benchmarks_for_axis(ax)
                assert len(new_benchmarks) >= 1, (
                    f"Legacy benchmark {legacy_b['benchmark_id']} covers axis "
                    f"{ax} but new registry has no benchmarks for it"
                )

    def test_alignment_classes_are_strings(self):
        """AlignmentClass values must be strings for JSON serialization."""
        from backend.benchmark_registry import AlignmentClass
        assert isinstance(AlignmentClass.STRONGLY_ALIGNED, str)
        assert isinstance(AlignmentClass.NO_DATA, str)

    def test_invariant_types_include_external(self):
        from backend.invariants import InvariantType, VALID_INVARIANT_TYPES
        assert InvariantType.EXTERNAL_VALIDITY in VALID_INVARIANT_TYPES

    def test_invariant_registry_ids_unique(self):
        from backend.invariants import INVARIANT_REGISTRY
        ids = [i["invariant_id"] for i in INVARIANT_REGISTRY]
        assert len(ids) == len(set(ids)), "Duplicate invariant IDs"
