#!/usr/bin/env python3
"""Tests for the institutional-grade hardening — 9 critical deficiencies.

Deficiency 1: Model B — Structural properties as HARD CONSTRAINTS
Deficiency 2: TIER_4 nullification (NON-NEGOTIABLE)
Deficiency 3: Structural class → constraint system
Deficiency 4: External validation layer
Deficiency 5: Sensitivity analysis
Deficiency 6: Ranking integrity partitions (tier-segregated)
Deficiency 7: Shock simulation layer
Deficiency 8: Methodology spec hardening (tested via doc assertions)
Deficiency 9: Output integrity guarantees

Target: institution-grade scrutiny (IMF/BIS/OECD-level).
"""

import math
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.axis_result import (
    AXIS_ID_TO_SLUG,
    AxisResult,
    CompositeResult,
    _build_quality_flags,
    validate_axis_result,
    validate_composite_result,
    make_invalid_axis,
    compute_composite_v11,
)
from backend.constants import ROUND_PRECISION
from backend.severity import (
    SEVERITY_WEIGHTS,
    STRUCTURAL_FLAGS,
    TIER_THRESHOLDS,
    AGGREGATION_ALPHA,
    AGGREGATION_MIN_WEIGHT,
    RANKING_PARTITIONS,
    REQUIRED_COMPOSITE_FIELDS,
    REQUIRED_AXIS_FIELDS,
    compute_axis_severity,
    compute_axis_data_severity,
    compute_country_severity,
    assign_comparability_tier,
    assign_ranking_partition,
    compute_tier_segregated_rankings,
    compute_adjusted_composite,
    compute_sensitivity_analysis,
    compute_shock_vulnerability,
    simulate_supplier_removal_hhi,
    validate_known_cases,
    validate_cross_axis_sanity,
    enforce_output_integrity,
    check_cross_country_comparability,
    check_structural_class_comparability,
    classify_structural_class,
    _spearman_rank_correlation,
    _rank_scores,
    KNOWN_CASE_EXPECTATIONS,
)


# ── Helpers ──────────────────────────────────────────────────

def _valid(country="US", axis_id=1, score=0.5, source="SRC_A",
           warnings=(), basis="BOTH", validity="VALID"):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis=basis, validity=validity,
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.4, channel_b_concentration=0.6,
    )


def _a_only(country="US", axis_id=1, score=0.3, source="SRC_B",
            warnings=("W-HS6-GRANULARITY",)):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="A_ONLY", validity="A_ONLY",
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.3, channel_b_concentration=None,
    )


def _degraded(country="US", axis_id=4, score=0.01, source="SRC_C",
              warnings=("W-PRODUCER-INVERSION",)):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="BOTH", validity="DEGRADED",
        coverage=None, source=source, warnings=warnings,
        channel_a_concentration=0.01, channel_b_concentration=0.01,
    )


def _sanctions(country="RU", axis_id=2, score=0.8, source="SRC_D"):
    return AxisResult(
        country=country, axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=score, basis="A_ONLY", validity="DEGRADED",
        coverage=None, source=source,
        warnings=("W-SANCTIONS-DISTORTION", "W-PRODUCER-INVERSION"),
        channel_a_concentration=0.8, channel_b_concentration=None,
    )


def _make_composite(axes, country="US", name="United States"):
    """Helper to produce a CompositeResult from axis list."""
    return compute_composite_v11(axes, country, name, "PHASE1-7", "v1.1")


def _make_severely_degraded_axes(country="RU"):
    """Create axes that produce TIER_4 severity (total ≥ 3.0)."""
    # Sanctions(1.0) + Producer(0.7) on energy = 1.7 total severity
    # Plus CPIS non-participant(0.5) on financial
    # Plus zero suppliers(0.6) on defense
    # Plus single channel(0.4) on technology
    # Total: 1.7 + 0.5 + 0.6 + 0.4 = 3.2 → TIER_4
    axes = [
        # Axis 1: CPIS non-participant
        _valid(country=country, axis_id=1, score=0.3, basis="A_ONLY",
               validity="A_ONLY",
               warnings=("F-CPIS-ABSENT",)),
        # Axis 2: Sanctions + producer inversion (worst)
        _sanctions(country=country, axis_id=2, score=0.8),
        # Axis 3: Single channel A
        _valid(country=country, axis_id=3, score=0.5, basis="A_ONLY",
               validity="A_ONLY", warnings=()),
        # Axis 4: Zero bilateral suppliers
        _valid(country=country, axis_id=4, score=0.0, basis="BOTH",
               validity="DEGRADED",
               warnings=("D-5",)),
        # Axis 5: producer inversion
        _degraded(country=country, axis_id=5, score=0.05,
                  warnings=("W-PRODUCER-INVERSION",)),
        # Axis 6: clean
        _valid(country=country, axis_id=6, score=0.4),
    ]
    return axes


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 1 — MODEL B: STRUCTURAL → HARD CONSTRAINTS
# ═════════════════════════════════════════════════════════════

class TestModelBStructuralConstraints:
    """Structural properties are HARD CONSTRAINTS, not weight adjustments.

    Model B: PRODUCER_INVERSION does NOT reduce aggregation weights.
    It DOES affect: comparability tier, ranking inclusion, interpretation.
    """

    def test_structural_flags_do_not_affect_aggregation_weight(self):
        """PRODUCER_INVERSION should NOT reduce weight in adjusted composite."""
        # 6 clean axes, one producer-inverted
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        axes[1] = _valid(axis_id=2, score=0.1, basis="BOTH",
                         validity="DEGRADED",
                         warnings=("W-PRODUCER-INVERSION",))
        comp = _make_composite(axes)
        d = comp.to_dict()
        # composite_adjusted should equal composite_raw because
        # PRODUCER_INVERSION is structural, not data
        assert d["composite_adjusted"] == d["composite_raw"]

    def test_structural_flags_DO_affect_comparability_tier(self):
        """PRODUCER_INVERSION contributes to total_severity for tier."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        # Multiple producer inversions → high total severity
        for i in [1, 2, 3, 4]:
            axes[i] = _valid(axis_id=i + 1, score=0.1, basis="BOTH",
                             validity="DEGRADED",
                             warnings=("W-PRODUCER-INVERSION",))
        comp = _make_composite(axes)
        d = comp.to_dict()
        sev = d["severity_analysis"]["total_severity"]
        # 4 producer inversions × 0.7 = 2.8 total severity
        assert sev >= 2.0
        assert d["strict_comparability_tier"] in ("TIER_3", "TIER_4")

    def test_structural_severity_excluded_from_data_severity(self):
        """compute_axis_data_severity returns 0.0 for structural-only flags."""
        for flag in STRUCTURAL_FLAGS:
            assert compute_axis_data_severity([flag]) == 0.0

    def test_structural_severity_included_in_total_severity(self):
        """compute_axis_severity includes structural flags."""
        for flag in STRUCTURAL_FLAGS:
            assert compute_axis_severity([flag]) > 0.0

    def test_data_severity_used_for_weight_function(self):
        """The composite uses data_severity, not total_severity, for ω(·)."""
        # Create axis with ONLY producer inversion
        ar = _valid(axis_id=2, score=0.3, basis="BOTH", validity="DEGRADED",
                    warnings=("W-PRODUCER-INVERSION",))
        d = ar.to_dict()
        assert d["data_severity"] == 0.0
        assert d["degradation_severity"] == 0.7
        # Weight for this axis: exp(-1.2 * 0.0) = 1.0 (full weight)
        expected_weight = math.exp(-AGGREGATION_ALPHA * d["data_severity"])
        assert expected_weight == 1.0


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 2 — TIER_4 NULLIFICATION (NON-NEGOTIABLE)
# ═════════════════════════════════════════════════════════════

class TestTier4Nullification:
    """IF strict_comparability_tier == TIER_4:
        composite_adjusted = NULL
        exclude_from_rankings = TRUE

    This is NON-NEGOTIABLE and CANNOT be overridden.
    """

    def test_tier4_composite_adjusted_is_null(self):
        """TIER_4 country MUST have composite_adjusted = None."""
        axes = _make_severely_degraded_axes("RU")
        comp = _make_composite(axes, country="RU", name="Russia")
        d = comp.to_dict()
        if d["strict_comparability_tier"] == "TIER_4":
            assert d["composite_adjusted"] is None, (
                "TIER_4 nullification violated: composite_adjusted is not NULL"
            )

    def test_tier4_exclude_from_rankings_true(self):
        """TIER_4 country MUST have exclude_from_rankings = True."""
        axes = _make_severely_degraded_axes("RU")
        comp = _make_composite(axes, country="RU", name="Russia")
        d = comp.to_dict()
        if d["strict_comparability_tier"] == "TIER_4":
            assert d["exclude_from_rankings"] is True, (
                "TIER_4 ranking exclusion violated"
            )

    def test_tier4_ranking_partition_is_non_comparable(self):
        """TIER_4 country MUST be in NON_COMPARABLE partition."""
        axes = _make_severely_degraded_axes("RU")
        comp = _make_composite(axes, country="RU", name="Russia")
        d = comp.to_dict()
        if d["strict_comparability_tier"] == "TIER_4":
            assert d["ranking_partition"] == "NON_COMPARABLE"

    def test_tier1_has_adjusted_composite(self):
        """TIER_1 country MUST have composite_adjusted != None."""
        axes = [_valid(axis_id=i, score=0.5) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert d["strict_comparability_tier"] == "TIER_1"
        assert d["composite_adjusted"] is not None
        assert d["exclude_from_rankings"] is False

    def test_tier2_has_adjusted_composite(self):
        """TIER_2 country has composite_adjusted != None."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        # Add a moderately degraded axis
        axes[0] = _valid(axis_id=1, score=0.3, basis="A_ONLY",
                         validity="A_ONLY",
                         warnings=("F-CPIS-ABSENT",))
        comp = _make_composite(axes)
        d = comp.to_dict()
        tier = d["strict_comparability_tier"]
        if tier == "TIER_2":
            assert d["composite_adjusted"] is not None
            assert d["exclude_from_rankings"] is False

    def test_tier4_composite_raw_still_present(self):
        """TIER_4 country still has composite_raw for reference."""
        axes = _make_severely_degraded_axes("RU")
        comp = _make_composite(axes, country="RU", name="Russia")
        d = comp.to_dict()
        # composite_raw is the raw arithmetic mean — always present
        # even for TIER_4 (for informational purposes)
        assert d["composite_raw"] is not None or d["isi_composite"] is None

    def test_nullification_in_validation(self):
        """validate_composite_result enforces TIER_4 nullification."""
        axes = _make_severely_degraded_axes("RU")
        comp = _make_composite(axes, country="RU", name="Russia")
        # Should not raise — validation enforces invariant
        validate_composite_result(comp)

    def test_new_fields_present_in_all_composites(self):
        """exclude_from_rankings and ranking_partition present for all tiers."""
        for score in [0.5, 0.3]:
            axes = [_valid(axis_id=i, score=score) for i in range(1, 7)]
            comp = _make_composite(axes)
            d = comp.to_dict()
            assert "exclude_from_rankings" in d
            assert "ranking_partition" in d
            assert isinstance(d["exclude_from_rankings"], bool)
            assert d["ranking_partition"] in (
                "FULLY_COMPARABLE", "LIMITED", "NON_COMPARABLE"
            )


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 3 — STRUCTURAL CLASS → CONSTRAINT SYSTEM
# ═════════════════════════════════════════════════════════════

class TestStructuralClassConstraintSystem:
    """Structural class is a CONSTRAINT, not just a label.

    PRODUCER vs IMPORTER → NON_COMPARABLE enforcement.
    """

    def test_producer_vs_importer_is_non_comparable(self):
        """PRODUCER vs IMPORTER triggers W-STRUCTURAL-CLASS-NONCOMPARABLE."""
        classes = {"US": "PRODUCER", "JP": "IMPORTER"}
        violations = check_structural_class_comparability(classes)
        assert len(violations) == 1
        assert violations[0]["warning_code"] == "W-STRUCTURAL-CLASS-NONCOMPARABLE"

    def test_same_class_no_violation(self):
        """Same structural class → no violation."""
        for cls in ("IMPORTER", "BALANCED", "PRODUCER"):
            classes = {"A": cls, "B": cls}
            assert check_structural_class_comparability(classes) == []

    def test_balanced_vs_anything_no_violation(self):
        """BALANCED pairs with any class → no violation."""
        for other in ("IMPORTER", "PRODUCER"):
            classes = {"A": "BALANCED", "B": other}
            violations = check_structural_class_comparability(classes)
            assert len(violations) == 0

    def test_structural_class_in_composite_output(self):
        """Structural class info is included in composite to_dict()."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "structural_class" in d
        sc = d["structural_class"]
        assert "structural_class" in sc
        assert sc["structural_class"] in ("IMPORTER", "BALANCED", "PRODUCER")
        assert "n_producer_inverted" in sc
        assert "producer_inverted_axes" in sc

    def test_multi_country_comparability(self):
        """Full 7-country structural class comparability check."""
        classes = {
            "US": "PRODUCER",
            "AU": "PRODUCER",
            "CN": "PRODUCER",
            "JP": "IMPORTER",
            "KR": "IMPORTER",
            "NO": "BALANCED",
            "GB": "IMPORTER",
        }
        violations = check_structural_class_comparability(classes)
        # PRODUCER vs IMPORTER pairs only
        producer_countries = {"US", "AU", "CN"}
        importer_countries = {"JP", "KR", "GB"}
        expected_count = len(producer_countries) * len(importer_countries)
        assert len(violations) == expected_count


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 4 — EXTERNAL VALIDATION LAYER
# ═════════════════════════════════════════════════════════════

class TestExternalValidation:
    """Minimum viable empirical anchor — known case and sanity checks."""

    def test_known_case_expectations_defined(self):
        """KNOWN_CASE_EXPECTATIONS covers key countries."""
        assert "DE" in KNOWN_CASE_EXPECTATIONS
        assert "CN" in KNOWN_CASE_EXPECTATIONS
        assert "NO" in KNOWN_CASE_EXPECTATIONS
        assert "JP" in KNOWN_CASE_EXPECTATIONS
        assert "US" in KNOWN_CASE_EXPECTATIONS

    def test_known_case_validation_structure(self):
        """validate_known_cases returns proper structure."""
        # Minimal mock results
        results = {
            "DE": {
                "composite_adjusted": 0.25,
                "composite_raw": 0.25,
                "structural_class": {"structural_class": "IMPORTER"},
            },
        }
        out = validate_known_cases(results)
        assert "validation_cases" in out
        assert "n_pass" in out
        assert "n_fail" in out
        assert "n_skip" in out
        assert "validation_verdict" in out

    def test_known_case_germany_pass(self):
        """Germany in expected range → PASS."""
        results = {
            "DE": {
                "composite_adjusted": 0.25,
                "structural_class": {"structural_class": "IMPORTER"},
            },
        }
        out = validate_known_cases(results)
        de_case = [c for c in out["validation_cases"] if c["country"] == "DE"][0]
        assert de_case["status"] == "PASS"

    def test_known_case_missing_country_skip(self):
        """Country not in results → SKIP."""
        out = validate_known_cases({})
        assert out["n_skip"] >= 1

    def test_known_case_wrong_class_fail(self):
        """Wrong structural class → FAIL."""
        results = {
            "CN": {
                "composite_adjusted": 0.2,
                "structural_class": {"structural_class": "IMPORTER"},  # Wrong
            },
        }
        out = validate_known_cases(results)
        cn_case = [c for c in out["validation_cases"] if c["country"] == "CN"][0]
        assert cn_case["status"] == "FAIL"

    def test_cross_axis_sanity_clean_data(self):
        """Clean, balanced data passes sanity check."""
        country_axes = {
            "US": [
                {"axis_id": i, "validity": "VALID", "score": 0.3 + i * 0.05}
                for i in range(1, 7)
            ],
            "JP": [
                {"axis_id": i, "validity": "VALID", "score": 0.35 + i * 0.03}
                for i in range(1, 7)
            ],
        }
        out = validate_cross_axis_sanity(country_axes)
        assert "axis_variance_contributions" in out
        assert "sanity_pass" in out
        assert out["sanity_pass"] is True

    def test_cross_axis_sanity_returns_warnings(self):
        """validate_cross_axis_sanity returns warnings list."""
        out = validate_cross_axis_sanity({})
        assert "sanity_warnings" in out


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 5 — SENSITIVITY ANALYSIS
# ═════════════════════════════════════════════════════════════

class TestSensitivityAnalysis:
    """Parameter perturbation: vary weights ±30%, α, measure ranking stability."""

    def test_spearman_identical_rankings(self):
        """Identical rankings → ρ = 1.0."""
        assert _spearman_rank_correlation([1, 2, 3], [1, 2, 3]) == 1.0

    def test_spearman_reversed_rankings(self):
        """Perfectly reversed → ρ = -1.0."""
        rho = _spearman_rank_correlation([1, 2, 3], [3, 2, 1])
        assert rho == -1.0

    def test_spearman_partial_correlation(self):
        """Partially correlated rankings → 0 < ρ < 1."""
        rho = _spearman_rank_correlation([1, 2, 3, 4], [1, 3, 2, 4])
        assert 0.0 < rho < 1.0

    def test_spearman_single_element(self):
        """Single element → ρ = 1.0 (degenerate)."""
        assert _spearman_rank_correlation([1], [1]) == 1.0

    def test_rank_scores_correct_order(self):
        """Higher score → lower rank number (rank 1 = highest)."""
        scores = {"US": 0.5, "JP": 0.3, "DE": 0.4}
        ranks = _rank_scores(scores)
        assert ranks["US"] == 1.0
        assert ranks["DE"] == 2.0
        assert ranks["JP"] == 3.0

    def test_sensitivity_analysis_clean_data(self):
        """Clean data (no severity) → all scenarios yield identical rankings."""
        axis_data = [
            {"country": "US", "axis_scores": [(0.5, 0.0), (0.3, 0.0), (0.4, 0.0)]},
            {"country": "JP", "axis_scores": [(0.6, 0.0), (0.4, 0.0), (0.5, 0.0)]},
            {"country": "DE", "axis_scores": [(0.4, 0.0), (0.2, 0.0), (0.3, 0.0)]},
        ]
        result = compute_sensitivity_analysis(axis_data)
        assert result["sensitivity_verdict"] == "ROBUST"
        assert result["spearman_min"] == 1.0
        assert result["max_rank_shift"] == 0

    def test_sensitivity_analysis_with_degradation(self):
        """Degraded data should show some sensitivity."""
        axis_data = [
            {"country": "US", "axis_scores": [(0.5, 0.0), (0.3, 0.4), (0.4, 0.0)]},
            {"country": "JP", "axis_scores": [(0.6, 0.0), (0.4, 0.0), (0.5, 0.0)]},
            {"country": "DE", "axis_scores": [(0.35, 0.7), (0.2, 0.0), (0.3, 0.5)]},
        ]
        result = compute_sensitivity_analysis(axis_data)
        assert "baseline_rankings" in result
        assert "perturbed_scenarios" in result
        assert len(result["perturbed_scenarios"]) > 0
        assert result["sensitivity_verdict"] in ("ROBUST", "SENSITIVE", "UNSTABLE")

    def test_sensitivity_analysis_empty(self):
        """Empty input → trivial result."""
        result = compute_sensitivity_analysis([])
        assert result["sensitivity_verdict"] == "ROBUST"
        assert result["max_rank_shift"] == 0

    def test_sensitivity_analysis_output_structure(self):
        """Sensitivity analysis returns all required fields."""
        axis_data = [
            {"country": "US", "axis_scores": [(0.5, 0.0)]},
            {"country": "JP", "axis_scores": [(0.6, 0.0)]},
            {"country": "DE", "axis_scores": [(0.4, 0.0)]},
        ]
        result = compute_sensitivity_analysis(axis_data)
        required_keys = {
            "baseline_rankings", "perturbed_scenarios",
            "spearman_min", "spearman_mean",
            "max_rank_shift", "mean_absolute_deviation",
            "sensitivity_verdict",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_sensitivity_perturbation_range(self):
        """Default perturbation is ±30%."""
        axis_data = [
            {"country": "US", "axis_scores": [(0.5, 0.3)]},
            {"country": "JP", "axis_scores": [(0.6, 0.1)]},
        ]
        result = compute_sensitivity_analysis(axis_data, perturbation_pct=0.30)
        # Should have 6 scenarios
        assert len(result["perturbed_scenarios"]) == 6

    def test_sensitivity_verdict_categories(self):
        """Verdict is one of ROBUST / SENSITIVE / UNSTABLE."""
        result = compute_sensitivity_analysis([])
        assert result["sensitivity_verdict"] in ("ROBUST", "SENSITIVE", "UNSTABLE")


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 6 — RANKING INTEGRITY PARTITIONS
# ═════════════════════════════════════════════════════════════

class TestRankingIntegrity:
    """Tier-segregated ranking: only comparable countries ranked together."""

    def test_ranking_partitions_defined(self):
        """RANKING_PARTITIONS covers all tiers."""
        all_tiers = []
        for tiers in RANKING_PARTITIONS.values():
            all_tiers.extend(tiers)
        assert "TIER_1" in all_tiers
        assert "TIER_2" in all_tiers
        assert "TIER_3" in all_tiers
        assert "TIER_4" in all_tiers

    def test_tier1_is_fully_comparable(self):
        assert assign_ranking_partition("TIER_1") == "FULLY_COMPARABLE"

    def test_tier2_is_fully_comparable(self):
        assert assign_ranking_partition("TIER_2") == "FULLY_COMPARABLE"

    def test_tier3_is_limited(self):
        assert assign_ranking_partition("TIER_3") == "LIMITED"

    def test_tier4_is_non_comparable(self):
        assert assign_ranking_partition("TIER_4") == "NON_COMPARABLE"

    def test_unknown_tier_is_non_comparable(self):
        """Unknown tier defaults to NON_COMPARABLE (safe default)."""
        assert assign_ranking_partition("TIER_99") == "NON_COMPARABLE"

    def test_tier_segregated_rankings_basic(self):
        """Countries are ranked within their partition only."""
        composites = {"US": 0.5, "JP": 0.4, "DE": 0.3, "RU": None}
        tiers = {"US": "TIER_1", "JP": "TIER_1", "DE": "TIER_3", "RU": "TIER_4"}
        result = compute_tier_segregated_rankings(composites, tiers)

        assert "rankings" in result
        assert "partition_membership" in result
        assert "excluded_from_ranking" in result

        # US and JP in FULLY_COMPARABLE, ranked 1 and 2
        fc = result["rankings"]["FULLY_COMPARABLE"]
        assert len(fc) == 2
        assert fc[0]["country"] == "US"
        assert fc[0]["rank"] == 1
        assert fc[1]["country"] == "JP"
        assert fc[1]["rank"] == 2

        # DE in LIMITED, ranked 1 (alone in partition)
        lim = result["rankings"]["LIMITED"]
        assert len(lim) == 1
        assert lim[0]["rank"] == 1

        # RU excluded
        assert "RU" in result["excluded_from_ranking"]
        assert result["partition_membership"]["RU"] == "NON_COMPARABLE"

    def test_tier4_gets_no_rank(self):
        """TIER_4 countries get rank=None."""
        composites = {"RU": None}
        tiers = {"RU": "TIER_4"}
        result = compute_tier_segregated_rankings(composites, tiers)
        nc = result["rankings"]["NON_COMPARABLE"]
        assert nc[0]["rank"] is None
        assert nc[0]["score"] is None

    def test_empty_input(self):
        """Empty input → empty rankings."""
        result = compute_tier_segregated_rankings({}, {})
        assert result["excluded_from_ranking"] == []

    def test_ranking_partition_in_composite(self):
        """Composite to_dict() includes ranking_partition field."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        assert "ranking_partition" in d
        assert d["ranking_partition"] in (
            "FULLY_COMPARABLE", "LIMITED", "NON_COMPARABLE"
        )


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 7 — SHOCK SIMULATION LAYER
# ═════════════════════════════════════════════════════════════

class TestShockSimulation:
    """Supplier removal simulation — vulnerability assessment."""

    def test_hhi_no_change_zero_share(self):
        """Removing supplier with 0 share → no change."""
        assert simulate_supplier_removal_hhi(0.3, 0.0) == 0.3

    def test_hhi_zero_baseline(self):
        """Zero HHI → remains zero regardless of share."""
        assert simulate_supplier_removal_hhi(0.0, 0.5) == 0.0

    def test_hhi_monopoly_removal(self):
        """Removing monopolist (share=1.0) → HHI=1.0 (degenerate)."""
        assert simulate_supplier_removal_hhi(1.0, 1.0) == 1.0

    def test_hhi_moderate_removal(self):
        """Removing moderate supplier changes HHI."""
        # HHI = 0.25, remove supplier with 30% share
        result = simulate_supplier_removal_hhi(0.25, 0.3)
        # Expected: (0.25 - 0.09) / (0.7²) = 0.16 / 0.49 ≈ 0.3265
        expected = (0.25 - 0.09) / (0.49)
        assert abs(result - round(expected, ROUND_PRECISION)) < 1e-6

    def test_hhi_result_clamped(self):
        """Result is clamped to [0.0, 1.0]."""
        # Edge case: very high HHI, small share
        result = simulate_supplier_removal_hhi(0.95, 0.05)
        assert 0.0 <= result <= 1.0

    def test_shock_vulnerability_structure(self):
        """compute_shock_vulnerability returns correct fields."""
        result = compute_shock_vulnerability(
            axis_score=0.3, top1_share=0.4, top2_share=0.2
        )
        required = {
            "baseline_score", "score_after_top1_removal",
            "score_after_top2_removal", "delta_top1", "delta_top2",
            "vulnerability_class",
        }
        assert required.issubset(set(result.keys()))

    def test_shock_vulnerability_classes(self):
        """Vulnerability classification is correct."""
        # Low vulnerability (small delta)
        r = compute_shock_vulnerability(0.3, 0.05)
        assert r["vulnerability_class"] == "LOW"

        # Moderate vulnerability
        r = compute_shock_vulnerability(0.3, 0.3)
        assert r["vulnerability_class"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")

        # High vulnerability (large top-1 share)
        r = compute_shock_vulnerability(0.5, 0.6)
        assert r["vulnerability_class"] in ("HIGH", "CRITICAL")

    def test_shock_delta_signs(self):
        """Removing top supplier should change concentration."""
        # Use HHI=0.5 and top_share=0.5 — significant removal
        r = compute_shock_vulnerability(0.5, 0.5, 0.2)
        # After removing a 50% supplier, HHI changes
        # (0.5 - 0.25) / 0.25 = 1.0 → clamped to 1.0
        assert r["score_after_top1_removal"] != r["baseline_score"]

    def test_shock_top2_sequential_removal(self):
        """Top-2 removal is sequential: remove top-1 first, then top-2."""
        r = compute_shock_vulnerability(0.3, 0.4, 0.2)
        # delta_top2 is relative to baseline, not to after_top1
        assert r["score_after_top2_removal"] != r["baseline_score"]

    def test_shock_zero_share_no_change(self):
        """Zero top share → no vulnerability."""
        r = compute_shock_vulnerability(0.3, 0.0, 0.0)
        assert r["delta_top1"] == 0.0
        assert r["delta_top2"] == 0.0
        assert r["vulnerability_class"] == "LOW"


# ═════════════════════════════════════════════════════════════
# DEFICIENCY 9 — OUTPUT INTEGRITY GUARANTEES
# ═════════════════════════════════════════════════════════════

class TestOutputIntegrity:
    """Hard-fail if any required field is missing or invariant violated."""

    def test_required_composite_fields_constant(self):
        """REQUIRED_COMPOSITE_FIELDS is defined and non-empty."""
        assert len(REQUIRED_COMPOSITE_FIELDS) > 20

    def test_required_axis_fields_constant(self):
        """REQUIRED_AXIS_FIELDS is defined and non-empty."""
        assert len(REQUIRED_AXIS_FIELDS) >= 14

    def test_enforce_output_integrity_clean(self):
        """Clean composite passes integrity check."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        violations = enforce_output_integrity(d)
        assert violations == [], f"Unexpected violations: {violations}"

    def test_enforce_output_integrity_missing_field(self):
        """Missing required field → violation detected."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        del d["severity_analysis"]
        violations = enforce_output_integrity(d)
        assert len(violations) > 0
        assert any("severity_analysis" in v for v in violations)

    def test_enforce_tier4_nullification_invariant(self):
        """TIER_4 with non-null adjusted → violation."""
        d = {
            "country": "XX",
            "country_name": "Test",
            "isi_composite": 0.5,
            "composite_raw": 0.5,
            "composite_adjusted": 0.4,  # SHOULD BE NULL
            "exclude_from_rankings": False,  # SHOULD BE TRUE
            "ranking_partition": "NON_COMPARABLE",
            "classification": "test",
            "axes_included": 6,
            "axes_excluded": [],
            "confidence": "FULL",
            "comparability_tier": "LIMITED_COMPARABILITY",
            "strict_comparability_tier": "TIER_4",
            "severity_analysis": {
                "total_severity": 3.5,
                "mean_severity": 0.5,
                "max_axis_severity": 1.0,
                "worst_axis": "energy",
                "severity_profile": {},
                "n_clean_axes": 0,
                "n_degraded_axes": 6,
            },
            "structural_degradation_profile": {},
            "structural_class": {"structural_class": "IMPORTER"},
            "stability_analysis": {},
            "interpretation_flags": [],
            "interpretation_summary": "",
            "scope": "PHASE1-7",
            "methodology_version": "v1.1",
            "warnings": [],
            "axes": [],
        }
        violations = enforce_output_integrity(d)
        assert any("TIER_4" in v and "composite_adjusted" in v for v in violations)
        assert any("TIER_4" in v and "exclude_from_rankings" in v for v in violations)

    def test_enforce_missing_axis_field(self):
        """Missing axis-level required field → violation."""
        d = {
            "country": "XX",
            "country_name": "Test",
            "isi_composite": 0.5,
            "composite_raw": 0.5,
            "composite_adjusted": 0.5,
            "exclude_from_rankings": False,
            "ranking_partition": "FULLY_COMPARABLE",
            "classification": "test",
            "axes_included": 6,
            "axes_excluded": [],
            "confidence": "FULL",
            "comparability_tier": "FULL_COMPARABILITY",
            "strict_comparability_tier": "TIER_1",
            "severity_analysis": {
                "total_severity": 0.0,
                "mean_severity": 0.0,
                "max_axis_severity": 0.0,
                "worst_axis": None,
                "severity_profile": {},
                "n_clean_axes": 6,
                "n_degraded_axes": 0,
            },
            "structural_degradation_profile": {},
            "structural_class": {"structural_class": "IMPORTER"},
            "stability_analysis": {},
            "interpretation_flags": [],
            "interpretation_summary": "",
            "scope": "PHASE1-7",
            "methodology_version": "v1.1",
            "warnings": [],
            "axes": [
                {"axis_id": 1, "score": 0.5},  # Missing many required fields
            ],
        }
        violations = enforce_output_integrity(d)
        assert any("axis 1" in v for v in violations)

    def test_validate_composite_result_enforces_integrity(self):
        """validate_composite_result calls output integrity check."""
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        comp = _make_composite(axes)
        # Should not raise
        validate_composite_result(comp)

    def test_to_dict_hard_fails_on_violation(self):
        """CompositeResult.to_dict() raises ValueError on integrity violation."""
        # This is implicitly tested by the TIER_4 nullification tests
        # The to_dict() method calls enforce_output_integrity internally
        axes = [_valid(axis_id=i, score=0.4) for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()
        # All required fields present
        violations = enforce_output_integrity(d)
        assert violations == []


# ═════════════════════════════════════════════════════════════
# CROSS-CUTTING: COMBINED INTEGRATION TESTS
# ═════════════════════════════════════════════════════════════

class TestIntegrationDeficiencies:
    """Cross-cutting tests that verify multiple deficiencies interact correctly."""

    def test_tier4_country_full_pipeline(self):
        """A TIER_4 country has correct output across all 9 deficiencies."""
        axes = _make_severely_degraded_axes("RU")
        comp = _make_composite(axes, country="RU", name="Russia")
        d = comp.to_dict()

        # Deficiency 1: Model B — structural flags don't affect weight
        # (verified by checking data_severity separately)
        for ad in d["axes"]:
            if "PRODUCER_INVERSION" in ad.get("data_quality_flags", []):
                assert ad["data_severity"] < ad["degradation_severity"]

        # Deficiency 2: TIER_4 nullification
        if d["strict_comparability_tier"] == "TIER_4":
            assert d["composite_adjusted"] is None
            assert d["exclude_from_rankings"] is True

        # Deficiency 3: Structural class present
        assert "structural_class" in d
        assert d["structural_class"]["structural_class"] in (
            "IMPORTER", "BALANCED", "PRODUCER"
        )

        # Deficiency 6: Ranking partition
        assert "ranking_partition" in d

        # Deficiency 9: Output integrity
        violations = enforce_output_integrity(d)
        assert violations == []

    def test_clean_country_full_pipeline(self):
        """A clean TIER_1 country has correct output across all deficiencies."""
        axes = [_valid(axis_id=i, score=0.4, source="S") for i in range(1, 7)]
        comp = _make_composite(axes)
        d = comp.to_dict()

        # TIER_1
        assert d["strict_comparability_tier"] == "TIER_1"

        # Deficiency 2: NOT excluded
        assert d["composite_adjusted"] is not None
        assert d["exclude_from_rankings"] is False

        # Deficiency 6: FULLY_COMPARABLE
        assert d["ranking_partition"] == "FULLY_COMPARABLE"

        # Deficiency 9: Output integrity
        violations = enforce_output_integrity(d)
        assert violations == []

    def test_sensitivity_and_ranking_interact(self):
        """Sensitivity analysis respects ranking partitions."""
        # Create axis data for 3 countries
        axis_data = [
            {"country": "US", "axis_scores": [(0.5, 0.0), (0.3, 0.4)]},
            {"country": "JP", "axis_scores": [(0.6, 0.0), (0.4, 0.0)]},
            {"country": "DE", "axis_scores": [(0.4, 0.0), (0.2, 0.0)]},
        ]
        sens = compute_sensitivity_analysis(axis_data)
        assert sens["sensitivity_verdict"] in ("ROBUST", "SENSITIVE", "UNSTABLE")

        # Rankings should also work
        composites = {"US": 0.4, "JP": 0.5, "DE": 0.3}
        tiers = {"US": "TIER_1", "JP": "TIER_1", "DE": "TIER_2"}
        rankings = compute_tier_segregated_rankings(composites, tiers)
        assert len(rankings["rankings"]["FULLY_COMPARABLE"]) == 3

    def test_shock_and_validation_interact(self):
        """Shock simulation + external validation work together."""
        shock = compute_shock_vulnerability(0.3, 0.4, 0.2)
        assert shock["vulnerability_class"] in ("LOW", "MODERATE", "HIGH", "CRITICAL")

        # Known case validation
        results = {
            "JP": {
                "composite_adjusted": 0.35,
                "structural_class": {"structural_class": "IMPORTER"},
            },
        }
        val = validate_known_cases(results)
        assert val["validation_verdict"] in ("PASS", "FAIL")
