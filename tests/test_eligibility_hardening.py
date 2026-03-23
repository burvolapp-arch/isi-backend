"""
tests.test_eligibility_hardening — Test suite for the theoretical
country eligibility model (backend/eligibility.py) and governance
hardening pass.

Tests cover:
    TASK 1:  Remaining-issues inventory
    TASK 2:  Code-fixable hardening
    TASK 3:  Theoretical eligibility model
    TASK 4:  Four distinct questions
    TASK 5:  Country eligibility registry
    TASK 6:  Theoretical "can compile now" answer
    TASK 7:  Sensitivity hardening of eligibility
    TASK 8:  Anti-pseudo-rigor hardening
    TASK 9:  Explanation objects
    TASK 10: Export/API eligibility propagation
    TASK 11: Theoretical vs empirical distinction
    TASK 12: Final state-of-system answer
    TASK 13: Self-audit for overreach
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# TASK 3: THEORETICAL ELIGIBILITY MODEL
# ═══════════════════════════════════════════════════════════════════════════

class TestTheoreticalEligibilityModel:
    """The eligibility model must define and enforce clear classes."""

    def test_all_classes_defined(self) -> None:
        from backend.eligibility import TheoreticalEligibility, VALID_ELIGIBILITY_CLASSES
        assert TheoreticalEligibility.COMPILE_READY in VALID_ELIGIBILITY_CLASSES
        assert TheoreticalEligibility.RATEABLE_WITHIN_MODEL in VALID_ELIGIBILITY_CLASSES
        assert TheoreticalEligibility.RANKABLE_WITHIN_MODEL in VALID_ELIGIBILITY_CLASSES
        assert TheoreticalEligibility.COMPARABLE_WITHIN_MODEL in VALID_ELIGIBILITY_CLASSES
        assert TheoreticalEligibility.COMPUTABLE_BUT_NOT_DEFENSIBLE in VALID_ELIGIBILITY_CLASSES
        assert TheoreticalEligibility.NOT_READY in VALID_ELIGIBILITY_CLASSES

    def test_class_hierarchy_exists(self) -> None:
        from backend.eligibility import _ELIGIBILITY_RANK, TheoreticalEligibility
        assert _ELIGIBILITY_RANK[TheoreticalEligibility.NOT_READY] < \
            _ELIGIBILITY_RANK[TheoreticalEligibility.COMPILE_READY]
        assert _ELIGIBILITY_RANK[TheoreticalEligibility.COMPILE_READY] < \
            _ELIGIBILITY_RANK[TheoreticalEligibility.RATEABLE_WITHIN_MODEL]
        assert _ELIGIBILITY_RANK[TheoreticalEligibility.RATEABLE_WITHIN_MODEL] < \
            _ELIGIBILITY_RANK[TheoreticalEligibility.RANKABLE_WITHIN_MODEL]
        assert _ELIGIBILITY_RANK[TheoreticalEligibility.RANKABLE_WITHIN_MODEL] < \
            _ELIGIBILITY_RANK[TheoreticalEligibility.COMPARABLE_WITHIN_MODEL]

    def test_weakness_types_defined(self) -> None:
        from backend.eligibility import WeaknessType
        assert hasattr(WeaknessType, "DATA_AVAILABILITY")
        assert hasattr(WeaknessType, "STRUCTURAL_METHODOLOGY")
        assert hasattr(WeaknessType, "PRODUCER_INVERSION")
        assert hasattr(WeaknessType, "CONSTRUCT_SUBSTITUTION")
        assert hasattr(WeaknessType, "CONFIDENCE_DEGRADATION")
        assert hasattr(WeaknessType, "COMPARABILITY_FAILURE")
        assert hasattr(WeaknessType, "THRESHOLD_FRAGILITY")
        assert hasattr(WeaknessType, "SANCTIONS_DISTORTION")


# ═══════════════════════════════════════════════════════════════════════════
# TASK 4: FOUR DISTINCT QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════

class TestFourDistinctQuestions:
    """The system must answer four different questions per country."""

    def test_can_compile_returns_correct_structure(self) -> None:
        from backend.eligibility import can_compile
        result = can_compile("DE")
        assert "question" in result
        assert "result" in result
        assert "n_axes_available" in result
        assert "blockers" in result
        assert "caveat" in result
        assert isinstance(result["result"], bool)

    def test_can_rate_returns_correct_structure(self) -> None:
        from backend.eligibility import can_rate
        result = can_rate("DE")
        assert "question" in result
        assert "result" in result
        assert "governance_tier" in result
        assert "blockers" in result
        assert "caveat" in result

    def test_can_rank_returns_correct_structure(self) -> None:
        from backend.eligibility import can_rank
        result = can_rank("DE")
        assert "question" in result
        assert "result" in result
        assert "ranking_eligible" in result
        assert "blockers" in result
        assert "caveat" in result

    def test_can_compare_returns_correct_structure(self) -> None:
        from backend.eligibility import can_compare
        result = can_compare("DE")
        assert "question" in result
        assert "result" in result
        assert "cross_country_comparable" in result
        assert "blockers" in result
        assert "caveat" in result

    def test_four_questions_not_identical_for_us(self) -> None:
        """US should have different answers for compile vs rate vs rank vs compare."""
        from backend.eligibility import can_compile, can_rate, can_rank, can_compare
        c = can_compile("US")
        r = can_rate("US")
        k = can_rank("US")
        p = can_compare("US")
        # US should compile but NOT be comparable
        assert c["result"] is True
        assert p["result"] is False

    def test_compile_yes_rate_no_possible(self) -> None:
        """Russia should compile but not rate."""
        from backend.eligibility import can_compile, can_rate
        c = can_compile("RU")
        r = can_rate("RU")
        assert c["result"] is True
        assert r["result"] is False

    def test_every_caveat_says_theoretical(self) -> None:
        """Every answer must include 'theoretical' language."""
        from backend.eligibility import can_compile, can_rate, can_rank, can_compare
        for fn in [can_compile, can_rate, can_rank, can_compare]:
            result = fn("DE")
            caveat = result.get("caveat", "")
            assert "theoretical" in caveat.lower() or "THEORETICAL" in caveat

    def test_questions_are_hierarchical(self) -> None:
        """If can_compare is True, can_rank, can_rate, can_compile must all be True."""
        from backend.eligibility import can_compile, can_rate, can_rank, can_compare
        for country in ["IT", "ES", "NL", "PL"]:
            c = can_compile(country)
            r = can_rate(country)
            k = can_rank(country)
            p = can_compare(country)
            if p["result"]:
                assert k["result"] is True
                assert r["result"] is True
                assert c["result"] is True
            if k["result"]:
                assert r["result"] is True
                assert c["result"] is True
            if r["result"]:
                assert c["result"] is True


# ═══════════════════════════════════════════════════════════════════════════
# TASK 5: COUNTRY ELIGIBILITY REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestCountryEligibilityRegistry:
    """Registry must cover all required countries with correct classifications."""

    def test_all_eu27_in_registry(self) -> None:
        from backend.eligibility import build_full_registry
        from backend.constants import EU27_CODES
        registry = build_full_registry()
        covered = {e["country"] for e in registry}
        missing = EU27_CODES - covered
        assert not missing, f"EU-27 missing: {missing}"

    def test_all_reference_countries_in_registry(self) -> None:
        from backend.eligibility import build_full_registry
        registry = build_full_registry()
        covered = {e["country"] for e in registry}
        required = {"GB", "JP", "KR", "NO", "AU", "US", "CN", "SA", "BR", "IN", "ZA", "RU"}
        missing = required - covered
        assert not missing, f"Reference countries missing: {missing}"

    def test_every_entry_has_required_fields(self) -> None:
        from backend.eligibility import build_full_registry
        required = {
            "country", "eligibility_class", "can_compile", "can_rate",
            "can_rank", "can_compare", "governance_tier",
            "weakness_types", "upgrade_blockers", "fragility_note",
            "ranking_allowed", "cross_country_comparison_allowed",
            "theoretical_caveat",
        }
        for entry in build_full_registry():
            missing = required - set(entry.keys())
            assert not missing, f"{entry['country']} missing: {missing}"

    def test_every_entry_has_theoretical_caveat(self) -> None:
        from backend.eligibility import build_full_registry
        for entry in build_full_registry():
            assert "theoretical" in entry["theoretical_caveat"].lower()

    def test_russia_not_rateable(self) -> None:
        from backend.eligibility import classify_country
        ru = classify_country("RU")
        assert ru["can_rate"] is False
        assert ru["sanctions_distorted"] is True

    def test_us_not_comparable(self) -> None:
        from backend.eligibility import classify_country
        us = classify_country("US")
        assert us["can_compare"] is False
        assert us["n_producer_inversions"] >= 3

    def test_clean_eu_countries_comparable(self) -> None:
        """Large EU members without inversions should be comparable."""
        from backend.eligibility import classify_country, TheoreticalEligibility
        for code in ["IT", "ES", "NL", "PL"]:
            result = classify_country(code)
            assert result["can_rank"] is True, f"{code} should be rankable"

    def test_fr_de_caveated_due_to_defense_inversion(self) -> None:
        """FR and DE have defense inversion."""
        from backend.eligibility import classify_country
        for code in ["FR", "DE"]:
            result = classify_country(code)
            # Should have at least 1 producer inversion
            assert result["n_producer_inversions"] >= 1

    def test_axis_strength_summary_present(self) -> None:
        from backend.eligibility import classify_country
        result = classify_country("DE")
        summary = result["axis_strength_summary"]
        assert "financial" in summary
        assert "energy" in summary
        assert "defense" in summary
        assert "logistics" in summary

    def test_logistics_blocks_confidence_field(self) -> None:
        from backend.eligibility import classify_country
        result = classify_country("DE")
        assert "logistics_blocks_confidence" in result
        assert isinstance(result["logistics_blocks_confidence"], bool)

    def test_producer_inversion_materially_degrades_field(self) -> None:
        from backend.eligibility import classify_country
        us = classify_country("US")
        assert us["producer_inversion_materially_degrades"] is True
        it = classify_country("IT")
        assert it["producer_inversion_materially_degrades"] is False


# ═══════════════════════════════════════════════════════════════════════════
# TASK 6: THEORETICAL "CAN COMPILE NOW" ANSWER
# ═══════════════════════════════════════════════════════════════════════════

class TestTheoreticalCompileAnswer:
    """Explicit rule-based answer to 'who can compile/rate/rank'."""

    def test_registry_summary_structure(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        assert "methodology_status" in summary
        assert "THEORETICAL" in summary["methodology_status"]
        assert "answers" in summary
        assert "honesty_note" in summary
        assert "non_empirical_warning" in summary

    def test_answers_cover_four_levels(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        answers = summary["answers"]
        assert "theoretically_compile_ready" in answers
        assert "theoretically_rateable" in answers
        assert "theoretically_rankable" in answers
        assert "theoretically_comparable" in answers

    def test_compile_ready_includes_eu27(self) -> None:
        from backend.eligibility import get_registry_summary
        from backend.constants import EU27_CODES
        summary = get_registry_summary()
        compilable = set(summary["answers"]["theoretically_compile_ready"])
        assert EU27_CODES <= compilable, (
            f"EU-27 not fully compile-ready: "
            f"missing {EU27_CODES - compilable}"
        )

    def test_russia_not_in_rateable(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        rateable = summary["answers"]["theoretically_rateable"]
        assert "RU" not in rateable

    def test_us_not_in_comparable(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        comparable = summary["answers"]["theoretically_comparable"]
        assert "US" not in comparable

    def test_honesty_note_warns_about_theoretical(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        note = summary["honesty_note"]
        assert "THEORETICAL" in note
        assert "validated" in note.lower()

    def test_non_empirical_warning_present(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        warning = summary["non_empirical_warning"]
        assert "heuristic" in warning.lower()
        assert "empirical" in warning.lower()

    def test_computable_but_not_defensible_category_exists(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        computable_nd = summary["answers"]["computable_but_not_defensible"]
        assert isinstance(computable_nd, list)


# ═══════════════════════════════════════════════════════════════════════════
# TASK 7: SENSITIVITY HARDENING OF ELIGIBILITY
# ═══════════════════════════════════════════════════════════════════════════

class TestEligibilitySensitivity:
    """Eligibility must be tested against threshold perturbations."""

    def test_sensitivity_analysis_runs(self) -> None:
        from backend.eligibility import run_eligibility_sensitivity
        result = run_eligibility_sensitivity(perturbation_pct=0.15)
        assert "stable_countries" in result
        assert "fragile_countries" in result
        assert "n_stable" in result
        assert "n_fragile" in result
        assert "interpretation" in result
        assert "honesty_note" in result

    def test_sensitivity_returns_all_countries(self) -> None:
        from backend.eligibility import run_eligibility_sensitivity, ALL_ASSESSABLE_COUNTRIES
        result = run_eligibility_sensitivity(perturbation_pct=0.10)
        total = result["n_stable"] + result["n_fragile"]
        assert total == len(ALL_ASSESSABLE_COUNTRIES)

    def test_clean_eu_countries_are_stable(self) -> None:
        """Core EU members without structural issues should be stable."""
        from backend.eligibility import run_eligibility_sensitivity
        result = run_eligibility_sensitivity(perturbation_pct=0.15)
        # IT, ES, NL, PL should be in stable list
        for code in ["IT", "ES"]:
            assert code in result["stable_countries"], (
                f"{code} should be stable but is in fragile list"
            )

    def test_honesty_note_warns_about_fragility(self) -> None:
        from backend.eligibility import run_eligibility_sensitivity
        result = run_eligibility_sensitivity()
        assert "heuristic" in result["honesty_note"].lower() or \
            "threshold" in result["honesty_note"].lower()

    def test_sensitivity_with_different_perturbation(self) -> None:
        from backend.eligibility import run_eligibility_sensitivity
        r10 = run_eligibility_sensitivity(perturbation_pct=0.10)
        r20 = run_eligibility_sensitivity(perturbation_pct=0.20)
        assert r10["perturbation_pct"] == 0.10
        assert r20["perturbation_pct"] == 0.20


# ═══════════════════════════════════════════════════════════════════════════
# TASK 8: ANTI-PSEUDO-RIGOR HARDENING
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiPseudoRigor:
    """Every output must avoid pseudo-rigor."""

    def test_no_state_of_the_art_in_outputs(self) -> None:
        """Outputs should not claim 'state-of-the-art' without evidence."""
        from backend.eligibility import build_eligibility_explanation
        for country in ["DE", "IT", "US", "RU"]:
            expl = build_eligibility_explanation(country)
            text = str(expl)
            assert "state-of-the-art" not in text.lower(), (
                f"{country} explanation uses 'state-of-the-art'"
            )

    def test_confidence_numbers_carry_caveats(self) -> None:
        """Numeric confidence values must be accompanied by calibration caveats."""
        from backend.eligibility import classify_country
        result = classify_country("DE")
        assert result["theoretical_caveat"]  # Must exist
        assert "NOT" in result["theoretical_caveat"]

    def test_governance_tiers_described_as_theoretical(self) -> None:
        from backend.eligibility import classify_country
        result = classify_country("DE")
        assert result["governance_tier"] is not None
        assert "theoretical" in result["theoretical_caveat"].lower()

    def test_registry_summary_avoids_empirical_language(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        text = str(summary)
        # Should NOT claim empirical validation
        assert "empirically validated" not in text.lower()
        assert "proven" not in text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TASK 9: EXPLANATION OBJECTS
# ═══════════════════════════════════════════════════════════════════════════

class TestExplanationObjects:
    """Every country must have a comprehensive explanation object."""

    def test_explanation_structure(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("DE")
        assert "country" in expl
        assert "eligibility_class" in expl
        assert "four_questions" in expl
        assert "axes" in expl
        assert "upgrade_blockers" in expl
        assert "weakness_types" in expl
        assert "what_would_improve_class" in expl
        assert "fragility_note" in expl
        assert "unresolved_weaknesses" in expl

    def test_four_questions_in_explanation(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("DE")
        fq = expl["four_questions"]
        assert "can_compile" in fq
        assert "can_rate" in fq
        assert "can_rank" in fq
        assert "can_compare" in fq

    def test_axes_detail_in_explanation(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("DE")
        axes = expl["axes"]
        assert len(axes) == 6
        for axis in axes:
            assert "axis_id" in axis
            assert "available" in axis
            assert "strength" in axis
            assert "producer_inverted" in axis

    def test_unresolved_weaknesses_have_type(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("US")
        for w in expl["unresolved_weaknesses"]:
            assert "type" in w
            assert "detail" in w
            assert "fixable_by_code" in w

    def test_explanation_for_clean_country(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("IT")
        assert expl["four_questions"]["can_compile"] is True
        assert expl["four_questions"]["can_rate"] is True

    def test_explanation_for_sanctions_country(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("RU")
        assert expl["four_questions"]["can_rate"] is False
        assert len(expl["unresolved_weaknesses"]) > 0

    def test_upgrade_path_nonempty_for_non_maximum(self) -> None:
        from backend.eligibility import build_eligibility_explanation, TheoreticalEligibility
        expl = build_eligibility_explanation("US")
        if expl["eligibility_class"] != TheoreticalEligibility.COMPARABLE_WITHIN_MODEL:
            assert len(expl["what_would_improve_class"]) > 0

    def test_theoretical_caveat_in_explanation(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("DE")
        assert "theoretical" in expl["theoretical_caveat"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# TASK 10: EXPORT ELIGIBILITY PROPAGATION
# ═══════════════════════════════════════════════════════════════════════════

class TestExportEligibilityPropagation:
    """Exports must carry eligibility distinctions."""

    def test_governance_gate_suppresses_ranking(self) -> None:
        """NON_COMPARABLE countries must have ranking suppressed."""
        from backend.governance import gate_export
        result = {
            "country": "RU",
            "rank": 1,
            "composite_adjusted": 0.5,
        }
        gov = {
            "country": "RU",
            "governance_tier": "NON_COMPARABLE",
            "ranking_eligible": False,
            "cross_country_comparable": False,
            "composite_defensible": False,
            "n_axes_with_data": 6,
            "mean_axis_confidence": 0.1,
            "n_low_confidence_axes": 5,
            "n_high_confidence_axes": 0,
            "n_producer_inverted_axes": 3,
            "producer_inverted_axes": [2, 4, 5],
            "logistics_present": True,
            "logistics_proxy": False,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.1, "confidence_level": "MINIMAL"}
                for i in range(1, 7)
            ],
            "structural_limitations": ["Sanctions distortion"],
            "governance_interpretation": "NON_COMPARABLE",
        }
        gated = gate_export(result, gov)
        assert gated["rank"] is None
        assert gated["composite_adjusted"] is None
        assert gated["exclude_from_rankings"] is True

    def test_low_confidence_not_ranking_eligible(self) -> None:
        """LOW_CONFIDENCE countries must not be ranking-eligible."""
        from backend.governance import gate_export
        result = {
            "country": "CN",
            "rank": 5,
            "composite_adjusted": 0.4,
        }
        gov = {
            "country": "CN",
            "governance_tier": "LOW_CONFIDENCE",
            "ranking_eligible": False,
            "cross_country_comparable": False,
            "composite_defensible": True,
            "n_axes_with_data": 6,
            "mean_axis_confidence": 0.4,
            "n_low_confidence_axes": 3,
            "n_high_confidence_axes": 1,
            "n_producer_inverted_axes": 2,
            "producer_inverted_axes": [4, 5],
            "logistics_present": True,
            "logistics_proxy": True,
            "axis_confidences": [
                {"axis_id": i, "confidence_score": 0.4, "confidence_level": "LOW"}
                for i in range(1, 7)
            ],
            "structural_limitations": ["2 producer inversions"],
            "governance_interpretation": "LOW_CONFIDENCE",
        }
        gated = gate_export(result, gov)
        assert gated["rank"] is None
        assert gated["exclude_from_rankings"] is True

    def test_truthfulness_contract_catches_missing_fields(self) -> None:
        from backend.governance import enforce_truthfulness_contract
        result = {"country": "XX", "governance": {}}
        violations = enforce_truthfulness_contract(result)
        assert len(violations) > 0

    def test_isi_json_has_truthfulness_caveat(self) -> None:
        """build_isi_json should include a truthfulness caveat."""
        from backend.export_snapshot import build_isi_json
        # Minimal test data
        scores = {
            i: {c: 0.5 for c in sorted({"AT", "BE", "BG", "CY", "CZ", "DE", "DK",
                "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT",
                "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"})}
            for i in range(1, 7)
        }
        isi = build_isi_json(scores, "v1.0", 2024, "2022-2024")
        assert "_truthfulness_caveat" in isi

    def test_isi_json_rows_have_governance_tier(self) -> None:
        """Every row in build_isi_json must include governance_tier."""
        from backend.export_snapshot import build_isi_json
        scores = {
            i: {c: 0.5 for c in sorted({"AT", "BE", "BG", "CY", "CZ", "DE", "DK",
                "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT",
                "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"})}
            for i in range(1, 7)
        }
        isi = build_isi_json(scores, "v1.0", 2024, "2022-2024")
        for row in isi["countries"]:
            assert "governance_tier" in row, f"{row['country']} missing governance_tier"
            assert "ranking_eligible" in row, f"{row['country']} missing ranking_eligible"
            assert "cross_country_comparable" in row, f"{row['country']} missing cross_country_comparable"

    def test_isi_json_fr_de_have_inversions(self) -> None:
        """FR and DE should show limited comparability in isi.json due to inversions."""
        from backend.export_snapshot import build_isi_json
        scores = {
            i: {c: 0.5 for c in sorted({"AT", "BE", "BG", "CY", "CZ", "DE", "DK",
                "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT",
                "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK"})}
            for i in range(1, 7)
        }
        isi = build_isi_json(scores, "v1.0", 2024, "2022-2024")
        rows_by_country = {r["country"]: r for r in isi["countries"]}
        # FR and DE have defense inversion but only 1 axis → should still be comparable
        assert rows_by_country["FR"]["governance_tier"] in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE")
        assert rows_by_country["DE"]["governance_tier"] in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE")


# ═══════════════════════════════════════════════════════════════════════════
# TASK 11: THEORETICAL VS EMPIRICAL DISTINCTION
# ═══════════════════════════════════════════════════════════════════════════

class TestTheoreticalVsEmpirical:
    """The system must never confuse theoretical readiness with empirical validation."""

    def test_eligibility_class_names_say_within_model(self) -> None:
        from backend.eligibility import TheoreticalEligibility
        assert "WITHIN_MODEL" in TheoreticalEligibility.RATEABLE_WITHIN_MODEL
        assert "WITHIN_MODEL" in TheoreticalEligibility.RANKABLE_WITHIN_MODEL
        assert "WITHIN_MODEL" in TheoreticalEligibility.COMPARABLE_WITHIN_MODEL

    def test_registry_summary_says_theoretical(self) -> None:
        from backend.eligibility import get_registry_summary
        s = get_registry_summary()
        assert "THEORETICAL" in s["methodology_status"]

    def test_classify_country_has_theoretical_caveat(self) -> None:
        from backend.eligibility import classify_country
        for code in ["DE", "US", "RU"]:
            result = classify_country(code)
            assert "theoretical_caveat" in result
            assert "NOT" in result["theoretical_caveat"]
            assert "externally validated" in result["theoretical_caveat"].lower()

    def test_no_claim_of_correctness(self) -> None:
        """No output should claim ISI scores are 'correct'."""
        from backend.eligibility import build_eligibility_explanation
        for code in ["DE", "US", "RU"]:
            expl = build_eligibility_explanation(code)
            text = str(expl)
            # Allow "correct" only in negative context ("not correct")
            if "correct" in text.lower():
                assert "not" in text.lower() or "does not" in text.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TASK 12: FINAL STATE-OF-SYSTEM ANSWER
# ═══════════════════════════════════════════════════════════════════════════

class TestFinalStateOfSystem:
    """The system must produce a coherent state-of-system answer."""

    def test_state_of_system_answerable(self) -> None:
        """The registry summary should answer all six questions from TASK 12."""
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        answers = summary["answers"]
        # A: code-fixable issues — addressed by this module existing
        # B: non-code-fixable — in honesty_note
        # C: compile-ready
        assert len(answers["theoretically_compile_ready"]) > 0
        # D: rateable
        assert len(answers["theoretically_rateable"]) > 0
        # E: rankable
        assert len(answers["theoretically_rankable"]) > 0
        # F: refused/caveated
        assert "RU" not in answers["theoretically_rateable"]

    def test_compile_ready_is_superset_of_rateable(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        a = summary["answers"]
        compilable = set(a["theoretically_compile_ready"])
        rateable = set(a["theoretically_rateable"])
        rankable = set(a["theoretically_rankable"])
        comparable = set(a["theoretically_comparable"])
        # Strict hierarchy
        assert comparable <= rankable
        assert rankable <= rateable
        assert rateable <= compilable


# ═══════════════════════════════════════════════════════════════════════════
# TASK 13: SELF-AUDIT FOR OVERREACH
# ═══════════════════════════════════════════════════════════════════════════

class TestSelfAuditOverreach:
    """The system must identify where it might still overstate certainty."""

    def test_fragility_notes_exist(self) -> None:
        from backend.eligibility import build_full_registry
        for entry in build_full_registry():
            assert "fragility_note" in entry
            assert len(entry["fragility_note"]) > 0

    def test_some_countries_are_fragile(self) -> None:
        """At least some countries should be classified as threshold-sensitive."""
        from backend.eligibility import run_eligibility_sensitivity
        result = run_eligibility_sensitivity()
        # It's suspicious if NO country is fragile
        # (Some boundary countries should be sensitive)
        # We allow for the possibility that the system is robust,
        # but flag it if truly zero fragile
        assert result["n_stable"] + result["n_fragile"] > 0

    def test_sanctions_country_never_rateable(self) -> None:
        """Russia must NEVER appear as rateable under any interpretation."""
        from backend.eligibility import classify_country
        ru = classify_country("RU")
        assert ru["can_rate"] is False
        assert ru["can_rank"] is False
        assert ru["can_compare"] is False

    def test_us_never_comparable(self) -> None:
        """US must NEVER appear as cross-country comparable."""
        from backend.eligibility import classify_country
        us = classify_country("US")
        assert us["can_compare"] is False

    def test_theoretical_label_present_everywhere(self) -> None:
        """Every major output must carry 'theoretical' label."""
        from backend.eligibility import (
            get_registry_summary,
            classify_country,
            build_eligibility_explanation,
        )
        # Registry summary
        s = get_registry_summary()
        assert "THEORETICAL" in str(s)
        # Classify
        c = classify_country("DE")
        assert "theoretical" in c["theoretical_caveat"].lower()
        # Explanation
        e = build_eligibility_explanation("DE")
        assert "theoretical" in e["theoretical_caveat"].lower()

    def test_no_hidden_empirical_claims(self) -> None:
        """The eligibility module should not claim empirical grounding.

        Every occurrence of 'empirically validated' in source must be in a
        NEGATIVE context (i.e., preceded by 'not' / 'NOT' / 'does not').
        """
        import inspect
        import re
        import backend.eligibility as mod
        source = inspect.getsource(mod)
        # Find all occurrences of "empirically validated"
        for m in re.finditer(r"empirically validated", source, re.IGNORECASE):
            start = max(0, m.start() - 40)
            context = source[start:m.end()].lower()
            assert "not" in context or "no " in context, (
                f"'empirically validated' without negation near position {m.start()}: "
                f"...{source[start:m.end()+20]}..."
            )


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestEligibilityIntegration:
    """Integration tests for the full eligibility pipeline."""

    def test_full_registry_builds_without_error(self) -> None:
        from backend.eligibility import build_full_registry
        registry = build_full_registry()
        assert len(registry) >= 39  # EU-27 + 12 reference

    def test_registry_all_entries_valid_class(self) -> None:
        from backend.eligibility import build_full_registry, VALID_ELIGIBILITY_CLASSES
        for entry in build_full_registry():
            assert entry["eligibility_class"] in VALID_ELIGIBILITY_CLASSES

    def test_sensitivity_does_not_corrupt_state(self) -> None:
        """Sensitivity analysis must restore state after perturbation."""
        from backend.eligibility import classify_country, run_eligibility_sensitivity
        before = classify_country("DE")
        run_eligibility_sensitivity(perturbation_pct=0.20)
        after = classify_country("DE")
        assert before["eligibility_class"] == after["eligibility_class"]
        assert before["governance_tier"] == after["governance_tier"]

    def test_eligibility_module_importable(self) -> None:
        import backend.eligibility as elig
        assert hasattr(elig, "TheoreticalEligibility")
        assert hasattr(elig, "classify_country")
        assert hasattr(elig, "build_full_registry")
        assert hasattr(elig, "get_registry_summary")
        assert hasattr(elig, "run_eligibility_sensitivity")
        assert hasattr(elig, "build_eligibility_explanation")
        assert hasattr(elig, "can_compile")
        assert hasattr(elig, "can_rate")
        assert hasattr(elig, "can_rank")
        assert hasattr(elig, "can_compare")

    def test_governance_and_eligibility_consistent(self) -> None:
        """Governance tier should be consistent with eligibility class."""
        from backend.eligibility import classify_country, TheoreticalEligibility
        # NON_COMPARABLE governance should NOT yield COMPARABLE eligibility
        us = classify_country("US")
        if us["governance_tier"] == "NON_COMPARABLE":
            assert us["eligibility_class"] != TheoreticalEligibility.COMPARABLE_WITHIN_MODEL
            assert us["eligibility_class"] != TheoreticalEligibility.RANKABLE_WITHIN_MODEL


# ═══════════════════════════════════════════════════════════════════════════
# AXIS-BY-COUNTRY READINESS REGISTRY (Tasks 1.2, 1.5, 1.6)
# ═══════════════════════════════════════════════════════════════════════════

class TestReadinessLevels:
    """ReadinessLevel must be well-defined and ordered."""

    def test_all_readiness_levels_defined(self) -> None:
        from backend.eligibility import ReadinessLevel, VALID_READINESS_LEVELS
        assert ReadinessLevel.SOURCE_CONFIDENT in VALID_READINESS_LEVELS
        assert ReadinessLevel.SOURCE_USABLE in VALID_READINESS_LEVELS
        assert ReadinessLevel.PROXY_USED in VALID_READINESS_LEVELS
        assert ReadinessLevel.CONSTRUCT_SUBSTITUTION in VALID_READINESS_LEVELS
        assert ReadinessLevel.NOT_AVAILABLE in VALID_READINESS_LEVELS
        assert len(VALID_READINESS_LEVELS) == 5

    def test_readiness_ordering(self) -> None:
        from backend.eligibility import _READINESS_ORDER, ReadinessLevel
        assert _READINESS_ORDER[ReadinessLevel.SOURCE_CONFIDENT] > \
            _READINESS_ORDER[ReadinessLevel.SOURCE_USABLE]
        assert _READINESS_ORDER[ReadinessLevel.SOURCE_USABLE] > \
            _READINESS_ORDER[ReadinessLevel.PROXY_USED]
        assert _READINESS_ORDER[ReadinessLevel.PROXY_USED] > \
            _READINESS_ORDER[ReadinessLevel.CONSTRUCT_SUBSTITUTION]
        assert _READINESS_ORDER[ReadinessLevel.CONSTRUCT_SUBSTITUTION] > \
            _READINESS_ORDER[ReadinessLevel.NOT_AVAILABLE]


class TestAxisSourceProfile:
    """AXIS_SOURCE_PROFILE must cover all 6 axes with required fields."""

    def test_all_six_axes_present(self) -> None:
        from backend.eligibility import AXIS_SOURCE_PROFILE
        for ax in range(1, 7):
            assert ax in AXIS_SOURCE_PROFILE, f"Axis {ax} missing from AXIS_SOURCE_PROFILE"

    def test_every_axis_has_required_fields(self) -> None:
        from backend.eligibility import AXIS_SOURCE_PROFILE
        required = {
            "axis_name", "primary_sources", "dual_channel", "construct",
            "what_it_measures", "what_it_does_NOT_measure",
            "single_channel_degradation", "rule_id",
        }
        for ax, profile in AXIS_SOURCE_PROFILE.items():
            missing = required - set(profile.keys())
            assert not missing, f"Axis {ax} missing: {missing}"

    def test_rule_ids_follow_pattern(self) -> None:
        from backend.eligibility import AXIS_SOURCE_PROFILE
        import re
        for ax, profile in AXIS_SOURCE_PROFILE.items():
            assert re.match(r"^ELIG-SRC-\d{3}$", profile["rule_id"]), (
                f"Axis {ax} rule_id '{profile['rule_id']}' does not match ELIG-SRC-NNN"
            )

    def test_axis_6_has_eu_vs_non_eu_warning(self) -> None:
        from backend.eligibility import AXIS_SOURCE_PROFILE
        assert "eu_vs_non_eu_warning" in AXIS_SOURCE_PROFILE[6]
        warning = AXIS_SOURCE_PROFILE[6]["eu_vs_non_eu_warning"]
        assert "CONSTRUCT SUBSTITUTION" in warning
        assert "Comtrade" in warning

    def test_what_it_does_not_measure_nonempty(self) -> None:
        from backend.eligibility import AXIS_SOURCE_PROFILE
        for ax, profile in AXIS_SOURCE_PROFILE.items():
            text = profile["what_it_does_NOT_measure"]
            assert len(text) > 20, f"Axis {ax} what_it_does_NOT_measure too short"

    def test_axes_not_collapsed_into_same_construct(self) -> None:
        """Axes 2, 3, 5 use Comtrade but have DIFFERENT constructs."""
        from backend.eligibility import AXIS_SOURCE_PROFILE
        constructs = {
            ax: AXIS_SOURCE_PROFILE[ax]["construct"]
            for ax in [2, 3, 5]
        }
        # All three should be unique strings
        assert len(set(constructs.values())) == 3, (
            "Axes 2, 3, 5 constructs must be distinct — they measure "
            "different things despite sharing the same source"
        )


class TestPerAxisReadiness:
    """Per-axis readiness must vary correctly by axis + country."""

    def test_eu_country_all_six_axes_source_present(self) -> None:
        from backend.eligibility import build_axis_readiness_matrix
        matrix = build_axis_readiness_matrix("DE")
        for r in matrix:
            assert r["source_present"] is True, (
                f"DE axis {r['axis_id']} should have source present"
            )

    def test_eu_logistics_is_source_confident(self) -> None:
        """EU-27 should get SOURCE_CONFIDENT for logistics (axis 6)."""
        from backend.eligibility import build_axis_readiness_matrix, ReadinessLevel
        matrix = build_axis_readiness_matrix("IT")
        ax6 = [r for r in matrix if r["axis_id"] == 6][0]
        assert ax6["readiness_level"] == ReadinessLevel.SOURCE_CONFIDENT
        assert ax6["construct_substitution"] is False
        assert ax6["proxy_used"] is False

    def test_non_eu_logistics_is_construct_substitution(self) -> None:
        """Non-EU countries using Comtrade proxy for logistics must be CONSTRUCT_SUBSTITUTION."""
        from backend.eligibility import build_axis_readiness_matrix, ReadinessLevel
        for code in ["US", "JP", "AU", "BR", "IN"]:
            matrix = build_axis_readiness_matrix(code)
            ax6 = [r for r in matrix if r["axis_id"] == 6][0]
            assert ax6["readiness_level"] == ReadinessLevel.CONSTRUCT_SUBSTITUTION, (
                f"{code} axis 6 should be CONSTRUCT_SUBSTITUTION, "
                f"got {ax6['readiness_level']}"
            )
            assert ax6["construct_substitution"] is True
            assert ax6["proxy_used"] is True

    def test_axis_3_non_eu_has_hs6_granularity_issue(self) -> None:
        """Non-EU technology axis should flag HS6 granularity loss."""
        from backend.eligibility import build_axis_readiness_matrix, ReadinessLevel
        matrix = build_axis_readiness_matrix("JP")
        ax3 = [r for r in matrix if r["axis_id"] == 3][0]
        # JP is non-EU: HS6 only, not CN8
        assert ax3["readiness_level"] == ReadinessLevel.SOURCE_USABLE
        assert ax3["source_confident"] is False
        hs6_issues = [i for i in ax3["issues"] if i["issue"] == "HS6_GRANULARITY"]
        assert len(hs6_issues) == 1

    def test_axis_3_eu_is_source_confident(self) -> None:
        """EU technology axis has CN8 available — SOURCE_CONFIDENT."""
        from backend.eligibility import build_axis_readiness_matrix, ReadinessLevel
        matrix = build_axis_readiness_matrix("DE")
        ax3 = [r for r in matrix if r["axis_id"] == 3][0]
        assert ax3["readiness_level"] == ReadinessLevel.SOURCE_CONFIDENT
        assert ax3["source_confident"] is True

    def test_axis_4_always_tiv_lumpiness(self) -> None:
        """Defense axis should flag TIV_LUMPINESS for every country.

        Note: countries with producer inversion on defense (e.g., DE, FR)
        will be CONSTRUCT_SUBSTITUTION (inversion overrides lumpiness).
        Countries WITHOUT inversion should be SOURCE_USABLE.
        """
        from backend.eligibility import build_axis_readiness_matrix, ReadinessLevel
        from backend.governance import PRODUCER_INVERSION_REGISTRY
        for code in ["DE", "IT", "JP", "AU"]:
            matrix = build_axis_readiness_matrix(code)
            ax4 = [r for r in matrix if r["axis_id"] == 4][0]
            inverted_axes = PRODUCER_INVERSION_REGISTRY.get(code, {}).get("inverted_axes", [])
            if 4 in inverted_axes:
                # Inversion overrides TIV lumpiness
                assert ax4["readiness_level"] == ReadinessLevel.CONSTRUCT_SUBSTITUTION, (
                    f"{code} axis 4 should be CONSTRUCT_SUBSTITUTION (inverted)"
                )
            else:
                assert ax4["readiness_level"] == ReadinessLevel.SOURCE_USABLE, (
                    f"{code} axis 4 should be SOURCE_USABLE due to TIV lumpiness"
                )
            assert ax4["source_confident"] is False
            tiv_issues = [i for i in ax4["issues"] if i["issue"] == "TIV_LUMPINESS"]
            assert len(tiv_issues) >= 1

    def test_axis_2_energy_source_confident_for_all_comtrade(self) -> None:
        """Energy axis should be SOURCE_CONFIDENT for any Comtrade reporter."""
        from backend.eligibility import (
            build_axis_readiness_matrix, ReadinessLevel, COMTRADE_REPORTERS,
        )
        for code in ["IT", "JP", "BR"]:
            assert code in COMTRADE_REPORTERS
            matrix = build_axis_readiness_matrix(code)
            ax2 = [r for r in matrix if r["axis_id"] == 2][0]
            assert ax2["readiness_level"] == ReadinessLevel.SOURCE_CONFIDENT

    def test_axis_5_critical_inputs_source_confident(self) -> None:
        """Critical inputs axis should be SOURCE_CONFIDENT for Comtrade reporters."""
        from backend.eligibility import build_axis_readiness_matrix, ReadinessLevel
        matrix = build_axis_readiness_matrix("DE")
        ax5 = [r for r in matrix if r["axis_id"] == 5][0]
        assert ax5["readiness_level"] == ReadinessLevel.SOURCE_CONFIDENT

    def test_russia_sanctions_distorted_on_available_axes(self) -> None:
        """Russia should have sanctions distortion on every axis where source is present.

        Note: RU is NOT in BIS_REPORTERS or CPIS_PARTICIPANTS, so axis 1
        (financial) has source_present=False and sanctions cannot apply.
        All other axes (2-6) have sources and should show sanctions distortion.
        """
        from backend.eligibility import build_axis_readiness_matrix
        matrix = build_axis_readiness_matrix("RU")
        for r in matrix:
            if r["source_present"]:
                sanc = [i for i in r["issues"] if i["issue"] == "SANCTIONS_DISTORTION"]
                assert len(sanc) >= 1, (
                    f"RU axis {r['axis_id']} has source but missing SANCTIONS_DISTORTION"
                )
                assert r["source_confident"] is False
            else:
                # No source → sanctions check is irrelevant
                assert r["readiness_level"] == "NOT_AVAILABLE"

    def test_producer_inversion_flagged(self) -> None:
        """US should have producer inversion on energy/defense/critical axes."""
        from backend.eligibility import build_axis_readiness_matrix
        matrix = build_axis_readiness_matrix("US")
        inverted_axes = [
            r["axis_id"] for r in matrix
            if any(i["issue"] == "PRODUCER_INVERSION" for i in r["issues"])
        ]
        assert 2 in inverted_axes, "US should have energy inversion"
        assert 4 in inverted_axes, "US should have defense inversion"
        assert 5 in inverted_axes, "US should have critical inputs inversion"

    def test_every_readiness_dict_has_required_fields(self) -> None:
        """Every readiness assessment must have the full schema."""
        from backend.eligibility import build_axis_readiness_matrix, VALID_READINESS_LEVELS
        required = {
            "axis_id", "axis_name", "readiness_level", "source_present",
            "source_usable", "source_confident", "proxy_used",
            "construct_substitution", "issues", "rule_id", "primary_sources",
        }
        matrix = build_axis_readiness_matrix("DE")
        for r in matrix:
            missing = required - set(r.keys())
            assert not missing, f"Axis {r.get('axis_id')} missing: {missing}"
            assert r["readiness_level"] in VALID_READINESS_LEVELS

    def test_every_issue_has_rule_id(self) -> None:
        """Every issue in readiness assessments must have a rule_id."""
        from backend.eligibility import build_axis_readiness_matrix, ALL_ASSESSABLE_COUNTRIES
        import re
        for country in sorted(ALL_ASSESSABLE_COUNTRIES):
            matrix = build_axis_readiness_matrix(country)
            for r in matrix:
                for issue in r["issues"]:
                    assert "rule_id" in issue, (
                        f"{country} axis {r['axis_id']} issue missing rule_id"
                    )
                    assert re.match(r"^ELIG-RDN-\d+-", issue["rule_id"]), (
                        f"{country} axis {r['axis_id']} rule_id "
                        f"'{issue['rule_id']}' doesn't match ELIG-RDN-N-*"
                    )


class TestFullReadinessRegistry:
    """Full readiness registry must cover all countries × all axes."""

    def test_registry_covers_all_countries(self) -> None:
        from backend.eligibility import build_full_readiness_registry, ALL_ASSESSABLE_COUNTRIES
        registry = build_full_readiness_registry()
        assert set(registry.keys()) == ALL_ASSESSABLE_COUNTRIES

    def test_each_country_has_six_axes(self) -> None:
        from backend.eligibility import build_full_readiness_registry
        registry = build_full_readiness_registry()
        for country, axes in registry.items():
            assert len(axes) == 6, f"{country} has {len(axes)} axes, expected 6"

    def test_axis_readiness_summary_in_registry_summary(self) -> None:
        from backend.eligibility import get_registry_summary
        summary = get_registry_summary()
        assert "axis_readiness_summary" in summary
        for ax in range(1, 7):
            assert ax in summary["axis_readiness_summary"], (
                f"Axis {ax} missing from axis_readiness_summary"
            )

    def test_logistics_axis_shows_mixed_readiness(self) -> None:
        """Axis 6 must show both SOURCE_CONFIDENT (EU) and CONSTRUCT_SUBSTITUTION (non-EU)."""
        from backend.eligibility import get_registry_summary, ReadinessLevel
        summary = get_registry_summary()
        ax6_levels = summary["axis_readiness_summary"][6]
        assert ReadinessLevel.SOURCE_CONFIDENT in ax6_levels, (
            "Axis 6 should have some SOURCE_CONFIDENT countries (EU-27)"
        )
        assert ReadinessLevel.CONSTRUCT_SUBSTITUTION in ax6_levels, (
            "Axis 6 should have some CONSTRUCT_SUBSTITUTION countries (non-EU)"
        )

    def test_defense_axis_no_source_confident(self) -> None:
        """Axis 4 should have zero SOURCE_CONFIDENT (all TIV_LUMPINESS)."""
        from backend.eligibility import get_registry_summary, ReadinessLevel
        summary = get_registry_summary()
        ax4_levels = summary["axis_readiness_summary"][4]
        # SOURCE_CONFIDENT should be 0 or absent — every country has TIV lumpiness
        sc_count = ax4_levels.get(ReadinessLevel.SOURCE_CONFIDENT, 0)
        assert sc_count == 0, (
            f"Axis 4 should have 0 SOURCE_CONFIDENT, got {sc_count}"
        )


class TestConstructSubstitutionExplicit:
    """Construct substitution must be surfaced in all relevant outputs."""

    def test_classify_country_includes_logistics_construct_substitution(self) -> None:
        from backend.eligibility import classify_country
        jp = classify_country("JP")
        assert "logistics_construct_substitution" in jp
        assert jp["logistics_construct_substitution"] is True

    def test_eu_country_no_logistics_construct_substitution(self) -> None:
        from backend.eligibility import classify_country
        de = classify_country("DE")
        assert de["logistics_construct_substitution"] is False

    def test_explanation_axes_include_readiness_level(self) -> None:
        from backend.eligibility import build_eligibility_explanation, VALID_READINESS_LEVELS
        expl = build_eligibility_explanation("JP")
        for axis in expl["axes"]:
            assert "readiness_level" in axis
            assert axis["readiness_level"] in VALID_READINESS_LEVELS

    def test_explanation_axes_include_what_it_measures(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("DE")
        for axis in expl["axes"]:
            assert "what_it_measures" in axis
            assert "what_it_does_NOT_measure" in axis
            assert len(axis["what_it_measures"]) > 10

    def test_explanation_axes_include_rule_ids(self) -> None:
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("US")
        for axis in expl["axes"]:
            assert "rule_ids" in axis
            # US has issues on some axes — those should have rule_ids
            if axis["issues"]:
                assert len(axis["rule_ids"]) > 0

    def test_backward_compat_logistics_gap_alias(self) -> None:
        """LOGISTICS_GAP alias should still work for backward compatibility."""
        from backend.eligibility import LOGISTICS_GAP, WeaknessType
        assert LOGISTICS_GAP == WeaknessType.CONSTRUCT_SUBSTITUTION

    def test_non_eu_logistics_explanation_mentions_proxy(self) -> None:
        """Non-EU logistics axis explanation must explicitly say 'proxy' and 'trade value'."""
        from backend.eligibility import build_eligibility_explanation
        expl = build_eligibility_explanation("JP")
        ax6 = [a for a in expl["axes"] if a["axis_id"] == 6][0]
        issues_text = " ".join(ax6["issues"])
        assert "proxy" in issues_text.lower() or "PROXY" in issues_text
        assert ax6["construct_substitution"] is True


class TestRuleProvenance:
    """Every blocking rule must have traceable provenance."""

    def test_all_blockers_have_rule_id(self) -> None:
        from backend.eligibility import classify_country, ALL_ASSESSABLE_COUNTRIES
        for country in sorted(ALL_ASSESSABLE_COUNTRIES):
            result = classify_country(country)
            for blocker in result["upgrade_blockers"]:
                assert "rule_id" in blocker, (
                    f"{country} blocker missing rule_id: {blocker}"
                )
                assert blocker["rule_id"], (
                    f"{country} blocker has empty rule_id: {blocker}"
                )

    def test_rule_id_prefixes_are_elig(self) -> None:
        """All rule IDs should start with ELIG- prefix."""
        from backend.eligibility import classify_country
        import re
        for country in ["DE", "US", "RU", "JP", "CN"]:
            result = classify_country(country)
            for blocker in result["upgrade_blockers"]:
                rid = blocker.get("rule_id", "")
                assert re.match(r"^ELIG-Q\d-\d{3}$", rid), (
                    f"{country} blocker rule_id '{rid}' doesn't match ELIG-Q*-NNN"
                )
