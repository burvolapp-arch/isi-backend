"""
tests.test_calibration_falsifiability — Test suite for calibration +
falsifiability layer (backend/calibration.py) and governance enhancements.

Tests cover:
    TASK 1:  Threshold inventory completeness
    TASK 2:  Calibration framework structure
    TASK 3:  Falsifiability registry completeness
    TASK 4:  Circularity audit
    TASK 5:  Per-axis calibration notes
    TASK 6:  Country eligibility registry
    TASK 7:  Explicit rateability answer
    TASK 8:  Sensitivity analysis engine
    TASK 9:  External benchmark hooks
    TASK 10: Governance explanation object
    TASK 11: Governance module calibration labels
    TASK 13: Pseudo-rigor self-audit
"""

from __future__ import annotations

import pytest
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# TASK 1: THRESHOLD INVENTORY COMPLETENESS
# ═══════════════════════════════════════════════════════════════════════════

class TestThresholdInventory:
    """Every threshold in governance.py and severity.py must be in the registry."""

    def test_registry_is_nonempty(self) -> None:
        from backend.calibration import THRESHOLD_REGISTRY
        assert len(THRESHOLD_REGISTRY) > 0

    def test_severity_weights_all_covered(self) -> None:
        """Every severity weight in SEVERITY_WEIGHTS must appear."""
        from backend.severity import SEVERITY_WEIGHTS
        from backend.calibration import SEVERITY_WEIGHT_CALIBRATIONS

        calibrated_names = {
            c["name"].split(":")[1] for c in SEVERITY_WEIGHT_CALIBRATIONS
        }
        for flag in SEVERITY_WEIGHTS:
            assert flag in calibrated_names, (
                f"Severity weight '{flag}' is not in calibration registry"
            )

    def test_severity_tier_thresholds_covered(self) -> None:
        """All severity tier thresholds must appear."""
        from backend.severity import TIER_THRESHOLDS
        from backend.calibration import SEVERITY_TIER_CALIBRATIONS

        calibrated_values = {c["value"] for c in SEVERITY_TIER_CALIBRATIONS}
        for threshold, _ in TIER_THRESHOLDS:
            assert threshold in calibrated_values, (
                f"Severity tier threshold {threshold} not in calibration registry"
            )

    def test_governance_confidence_baselines_covered(self) -> None:
        """All axis confidence baselines must appear."""
        from backend.governance import AXIS_CONFIDENCE_BASELINES
        from backend.calibration import GOVERNANCE_THRESHOLD_CALIBRATIONS

        cal_names = {c["name"] for c in GOVERNANCE_THRESHOLD_CALIBRATIONS}
        axis_names = {
            "financial", "energy", "technology",
            "defense", "critical_inputs", "logistics"
        }
        for name in axis_names:
            assert f"AXIS_BASELINE:{name}" in cal_names, (
                f"Axis baseline '{name}' not in calibration registry"
            )

    def test_governance_confidence_penalties_covered(self) -> None:
        """All confidence penalties must appear."""
        from backend.governance import CONFIDENCE_PENALTIES
        from backend.calibration import GOVERNANCE_THRESHOLD_CALIBRATIONS

        cal_names = {c["name"] for c in GOVERNANCE_THRESHOLD_CALIBRATIONS}
        for flag in CONFIDENCE_PENALTIES:
            assert f"CONFIDENCE_PENALTY:{flag}" in cal_names, (
                f"Confidence penalty '{flag}' not in calibration registry"
            )

    def test_governance_confidence_levels_covered(self) -> None:
        """All confidence level thresholds must appear."""
        from backend.governance import CONFIDENCE_THRESHOLDS
        from backend.calibration import GOVERNANCE_THRESHOLD_CALIBRATIONS

        cal_names = {c["name"] for c in GOVERNANCE_THRESHOLD_CALIBRATIONS}
        for _, level in CONFIDENCE_THRESHOLDS:
            assert f"CONFIDENCE_LEVEL:{level}" in cal_names, (
                f"Confidence level '{level}' not in calibration registry"
            )

    def test_composite_eligibility_thresholds_covered(self) -> None:
        """All composite eligibility thresholds must appear."""
        from backend.calibration import GOVERNANCE_THRESHOLD_CALIBRATIONS

        cal_names = {c["name"] for c in GOVERNANCE_THRESHOLD_CALIBRATIONS}
        required = [
            "COMPOSITE:MIN_AXES",
            "COMPOSITE:MIN_AXES_RANKING",
            "COMPOSITE:MIN_MEAN_CONFIDENCE_RANKING",
            "COMPOSITE:MAX_LOW_CONFIDENCE_AXES_RANKING",
            "COMPOSITE:MAX_INVERTED_COMPARABLE",
            "COMPOSITE:DEFENSIBILITY_FLOOR",
        ]
        for name in required:
            assert name in cal_names, (
                f"Composite threshold '{name}' not in calibration registry"
            )

    def test_logistics_thresholds_covered(self) -> None:
        """Logistics proxy confidence cap must appear."""
        from backend.calibration import GOVERNANCE_THRESHOLD_CALIBRATIONS
        cal_names = {c["name"] for c in GOVERNANCE_THRESHOLD_CALIBRATIONS}
        assert "LOGISTICS:PROXY_CONFIDENCE_CAP" in cal_names

    def test_cross_country_thresholds_covered(self) -> None:
        """Cross-country severity thresholds must appear."""
        from backend.calibration import GOVERNANCE_THRESHOLD_CALIBRATIONS
        cal_names = {c["name"] for c in GOVERNANCE_THRESHOLD_CALIBRATIONS}
        assert "CROSS_COUNTRY:DIFF_THRESHOLD" in cal_names
        assert "CROSS_COUNTRY:RATIO_THRESHOLD" in cal_names

    def test_total_threshold_count_reasonable(self) -> None:
        """Registry should have at least 30 entries."""
        from backend.calibration import THRESHOLD_REGISTRY
        assert len(THRESHOLD_REGISTRY) >= 30


# ═══════════════════════════════════════════════════════════════════════════
# TASK 2: CALIBRATION FRAMEWORK STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

class TestCalibrationFramework:
    """Each threshold entry must have required fields and valid calibration class."""

    def test_all_entries_have_required_fields(self) -> None:
        from backend.calibration import THRESHOLD_REGISTRY
        required_fields = {
            "name", "value", "module", "calibration_class",
            "evidence_basis", "sensitivity_note", "upgrade_path",
            "falsifiable_by",
        }
        for entry in THRESHOLD_REGISTRY:
            missing = required_fields - set(entry.keys())
            assert not missing, (
                f"Threshold '{entry.get('name', '?')}' missing fields: {missing}"
            )

    def test_all_calibration_classes_valid(self) -> None:
        from backend.calibration import THRESHOLD_REGISTRY, VALID_CALIBRATION_CLASSES
        for entry in THRESHOLD_REGISTRY:
            assert entry["calibration_class"] in VALID_CALIBRATION_CLASSES, (
                f"Invalid calibration_class for '{entry['name']}': "
                f"{entry['calibration_class']}"
            )

    def test_no_empty_evidence_basis(self) -> None:
        from backend.calibration import THRESHOLD_REGISTRY
        for entry in THRESHOLD_REGISTRY:
            assert len(entry["evidence_basis"]) > 10, (
                f"Threshold '{entry['name']}' has empty/trivial evidence_basis"
            )

    def test_no_empty_falsifiable_by(self) -> None:
        from backend.calibration import THRESHOLD_REGISTRY
        for entry in THRESHOLD_REGISTRY:
            assert len(entry["falsifiable_by"]) > 5, (
                f"Threshold '{entry['name']}' has empty/trivial falsifiable_by"
            )

    def test_calibration_summary_structure(self) -> None:
        from backend.calibration import get_calibration_summary
        summary = get_calibration_summary()
        assert "total_thresholds" in summary
        assert "by_class" in summary
        assert "by_class_pct" in summary
        assert "honesty_note" in summary
        assert summary["total_thresholds"] > 0

    def test_no_threshold_labeled_empirical(self) -> None:
        """Current system has NO truly empirical thresholds — this is honest."""
        from backend.calibration import get_thresholds_by_class, CalibrationClass
        empirical = get_thresholds_by_class(CalibrationClass.EMPIRICAL)
        assert len(empirical) == 0, (
            f"Found {len(empirical)} EMPIRICAL thresholds — this is incorrect. "
            f"No threshold in the current system is purely empirically calibrated."
        )

    def test_calibration_classes_distribution(self) -> None:
        """Verify distribution is realistic."""
        from backend.calibration import get_calibration_summary
        summary = get_calibration_summary()
        counts = summary["by_class"]
        # We should have at least HEURISTIC and STRUCTURAL_NORMATIVE
        assert "HEURISTIC" in counts
        assert "STRUCTURAL_NORMATIVE" in counts
        # Heuristic should be the largest class
        assert counts["HEURISTIC"] >= counts.get("SEMI_EMPIRICAL", 0)

    def test_filter_by_module(self) -> None:
        from backend.calibration import get_thresholds_by_module
        severity = get_thresholds_by_module("severity")
        governance = get_thresholds_by_module("governance")
        assert len(severity) > 0
        assert len(governance) > 0

    def test_values_match_source(self) -> None:
        """Verify that registry values match actual module values."""
        from backend.calibration import THRESHOLD_REGISTRY
        from backend.governance import (
            AXIS_CONFIDENCE_BASELINES,
            CONFIDENCE_PENALTIES,
            CONFIDENCE_THRESHOLDS,
            MIN_AXES_FOR_COMPOSITE,
            MIN_AXES_FOR_RANKING,
            MIN_MEAN_CONFIDENCE_FOR_RANKING,
            MAX_LOW_CONFIDENCE_AXES_FOR_RANKING,
            MAX_INVERTED_AXES_FOR_COMPARABLE,
            LOGISTICS_PROXY_CONFIDENCE_CAP,
        )
        from backend.severity import SEVERITY_WEIGHTS, TIER_THRESHOLDS

        # Build lookup
        reg = {e["name"]: e["value"] for e in THRESHOLD_REGISTRY}

        # Check severity weights
        for flag, weight in SEVERITY_WEIGHTS.items():
            key = f"SEVERITY_WEIGHT:{flag}"
            if key in reg:
                assert reg[key] == weight, f"{key}: registry={reg[key]}, actual={weight}"

        # Check confidence penalties
        for flag, penalty in CONFIDENCE_PENALTIES.items():
            key = f"CONFIDENCE_PENALTY:{flag}"
            assert reg[key] == penalty, f"{key}: registry={reg[key]}, actual={penalty}"

        # Check composite thresholds
        assert reg["COMPOSITE:MIN_AXES"] == MIN_AXES_FOR_COMPOSITE
        assert reg["COMPOSITE:MIN_AXES_RANKING"] == MIN_AXES_FOR_RANKING
        assert reg["COMPOSITE:MIN_MEAN_CONFIDENCE_RANKING"] == MIN_MEAN_CONFIDENCE_FOR_RANKING
        assert reg["COMPOSITE:MAX_LOW_CONFIDENCE_AXES_RANKING"] == MAX_LOW_CONFIDENCE_AXES_FOR_RANKING
        assert reg["COMPOSITE:MAX_INVERTED_COMPARABLE"] == MAX_INVERTED_AXES_FOR_COMPARABLE
        assert reg["LOGISTICS:PROXY_CONFIDENCE_CAP"] == LOGISTICS_PROXY_CONFIDENCE_CAP


# ═══════════════════════════════════════════════════════════════════════════
# TASK 3: FALSIFIABILITY REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestFalsifiabilityRegistry:
    """Every governance mechanism must have explicit falsification criteria."""

    def test_registry_nonempty(self) -> None:
        from backend.calibration import FALSIFIABILITY_REGISTRY
        assert len(FALSIFIABILITY_REGISTRY) >= 5

    def test_all_entries_have_required_fields(self) -> None:
        from backend.calibration import FALSIFIABILITY_REGISTRY
        required = {
            "mechanism", "module", "description",
            "support_evidence", "weaken_evidence",
            "falsify_evidence", "current_status",
        }
        for entry in FALSIFIABILITY_REGISTRY:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Falsifiability entry '{entry.get('mechanism', '?')}' "
                f"missing: {missing}"
            )

    def test_all_evidence_lists_nonempty(self) -> None:
        from backend.calibration import FALSIFIABILITY_REGISTRY
        for entry in FALSIFIABILITY_REGISTRY:
            assert len(entry["support_evidence"]) > 0, (
                f"{entry['mechanism']}: empty support_evidence"
            )
            assert len(entry["weaken_evidence"]) > 0, (
                f"{entry['mechanism']}: empty weaken_evidence"
            )
            assert len(entry["falsify_evidence"]) > 0, (
                f"{entry['mechanism']}: empty falsify_evidence"
            )

    def test_key_mechanisms_covered(self) -> None:
        from backend.calibration import FALSIFIABILITY_REGISTRY
        mechanisms = {e["mechanism"] for e in FALSIFIABILITY_REGISTRY}
        required = {
            "Producer-Inversion Registry",
            "Governance Tier Ordering Rules",
            "Axis Confidence Baseline + Penalty Model",
            "Logistics Structural Limitation",
            "Composite Eligibility Rules",
            "Truthfulness Contract Enforcement",
        }
        missing = required - mechanisms
        assert not missing, f"Missing falsifiability entries for: {missing}"

    def test_get_falsifiability_registry(self) -> None:
        from backend.calibration import get_falsifiability_registry
        registry = get_falsifiability_registry()
        assert isinstance(registry, list)
        assert len(registry) >= 5


# ═══════════════════════════════════════════════════════════════════════════
# TASK 4: CIRCULARITY AUDIT
# ═══════════════════════════════════════════════════════════════════════════

class TestCircularityAudit:
    """Data flow must be strictly linear with no circular dependencies."""

    def test_audit_structure(self) -> None:
        from backend.calibration import CIRCULARITY_AUDIT
        assert "flow_description" in CIRCULARITY_AUDIT
        assert "data_flow_nodes" in CIRCULARITY_AUDIT
        assert "circularity_status" in CIRCULARITY_AUDIT
        assert "circularity_analysis" in CIRCULARITY_AUDIT
        assert "known_tension" in CIRCULARITY_AUDIT
        assert "defense" in CIRCULARITY_AUDIT

    def test_no_circularity(self) -> None:
        from backend.calibration import CIRCULARITY_AUDIT
        assert CIRCULARITY_AUDIT["circularity_status"] == "NO_CIRCULARITY"

    def test_data_flow_is_ordered(self) -> None:
        from backend.calibration import CIRCULARITY_AUDIT
        nodes = CIRCULARITY_AUDIT["data_flow_nodes"]
        assert len(nodes) >= 4
        # First nodes should NOT depend on governance
        assert not nodes[0]["depends_on_governance"]
        assert not nodes[1]["depends_on_governance"]
        assert not nodes[2]["depends_on_governance"]

    def test_governance_does_not_feed_back(self) -> None:
        """Governance node must not feed back into earlier stages."""
        from backend.calibration import CIRCULARITY_AUDIT
        nodes = CIRCULARITY_AUDIT["data_flow_nodes"]
        gov_node = None
        for n in nodes:
            if "governance" in n["module"].lower():
                gov_node = n
                break
        assert gov_node is not None
        assert not gov_node["depends_on_governance"]

    def test_get_circularity_audit(self) -> None:
        from backend.calibration import get_circularity_audit
        audit = get_circularity_audit()
        assert isinstance(audit, dict)
        assert audit["circularity_status"] == "NO_CIRCULARITY"

    def test_known_tension_documented(self) -> None:
        """The confidence-vs-severity design tension must be documented."""
        from backend.calibration import CIRCULARITY_AUDIT
        tension = CIRCULARITY_AUDIT["known_tension"]
        assert "additive" in tension.lower() or "penalty" in tension.lower()
        assert "severity" in tension.lower()


# ═══════════════════════════════════════════════════════════════════════════
# TASK 5: PER-AXIS CALIBRATION NOTES
# ═══════════════════════════════════════════════════════════════════════════

class TestAxisCalibrationNotes:
    """Each of 6 axes must have comprehensive calibration notes."""

    def test_all_6_axes_covered(self) -> None:
        from backend.calibration import AXIS_CALIBRATION_NOTES
        for axis_id in range(1, 7):
            assert axis_id in AXIS_CALIBRATION_NOTES, (
                f"Axis {axis_id} missing from calibration notes"
            )

    def test_required_fields_per_axis(self) -> None:
        from backend.calibration import AXIS_CALIBRATION_NOTES
        required = {
            "axis_name", "baseline", "baseline_class",
            "source_coverage", "known_gaps", "construct_validity",
            "sensitivity_to_penalties", "falsifiable_claim",
        }
        for axis_id, notes in AXIS_CALIBRATION_NOTES.items():
            missing = required - set(notes.keys())
            assert not missing, (
                f"Axis {axis_id} calibration notes missing: {missing}"
            )

    def test_baselines_match_governance(self) -> None:
        from backend.calibration import AXIS_CALIBRATION_NOTES
        from backend.governance import AXIS_CONFIDENCE_BASELINES
        for axis_id in range(1, 7):
            assert AXIS_CALIBRATION_NOTES[axis_id]["baseline"] == \
                AXIS_CONFIDENCE_BASELINES[axis_id], (
                    f"Axis {axis_id} baseline mismatch between "
                    f"calibration notes and governance"
                )

    def test_known_gaps_nonempty(self) -> None:
        from backend.calibration import AXIS_CALIBRATION_NOTES
        for axis_id, notes in AXIS_CALIBRATION_NOTES.items():
            assert len(notes["known_gaps"]) > 0, (
                f"Axis {axis_id} has no known gaps documented"
            )

    def test_falsifiable_claims_nonempty(self) -> None:
        from backend.calibration import AXIS_CALIBRATION_NOTES
        for axis_id, notes in AXIS_CALIBRATION_NOTES.items():
            claim = notes["falsifiable_claim"]
            assert len(claim) > 20, (
                f"Axis {axis_id} has trivial falsifiable claim"
            )
            assert "CLAIM:" in claim or "claim" in claim.lower()
            assert "FALSIFIABLE" in claim or "falsifiable" in claim.lower()

    def test_construct_validity_per_axis(self) -> None:
        from backend.calibration import AXIS_CALIBRATION_NOTES
        for axis_id, notes in AXIS_CALIBRATION_NOTES.items():
            cv = notes["construct_validity"]
            assert "VALID" in cv or "valid" in cv.lower(), (
                f"Axis {axis_id} construct_validity doesn't state validity"
            )
            # Each should also state limitations (NOT, incomplete, weaker, partial, etc.)
            limitation_markers = ["NOT", "not", "DOES NOT", "incomplete", "weaker", "partial"]
            has_limitation = any(m in cv for m in limitation_markers)
            assert has_limitation, (
                f"Axis {axis_id} construct_validity doesn't state limitations"
            )

    def test_defense_axis_has_lowest_baseline(self) -> None:
        """Defense (SIPRI TIV) should have the lowest baseline."""
        from backend.calibration import AXIS_CALIBRATION_NOTES
        defense_baseline = AXIS_CALIBRATION_NOTES[4]["baseline"]
        for axis_id, notes in AXIS_CALIBRATION_NOTES.items():
            if axis_id != 4:
                assert notes["baseline"] >= defense_baseline, (
                    f"Axis {axis_id} has baseline {notes['baseline']} < "
                    f"defense baseline {defense_baseline}"
                )

    def test_get_axis_calibration_notes(self) -> None:
        from backend.calibration import get_axis_calibration_notes
        notes = get_axis_calibration_notes()
        assert isinstance(notes, dict)
        assert len(notes) == 6


# ═══════════════════════════════════════════════════════════════════════════
# TASK 6: COUNTRY ELIGIBILITY REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestCountryEligibilityRegistry:
    """Country eligibility registry must be complete and well-structured."""

    def test_registry_nonempty(self) -> None:
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        assert len(COUNTRY_ELIGIBILITY_REGISTRY) >= 27  # At least EU-27

    def test_all_entries_have_required_fields(self) -> None:
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        required = {
            "country", "name", "eligibility_class",
            "expected_governance_tier", "rationale",
            "data_strengths", "data_weaknesses",
            "axes_at_risk", "upgrade_conditions",
        }
        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Country '{entry.get('country', '?')}' missing: {missing}"
            )

    def test_all_eligibility_classes_valid(self) -> None:
        from backend.calibration import (
            COUNTRY_ELIGIBILITY_REGISTRY,
            VALID_ELIGIBILITY_CLASSES,
        )
        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            assert entry["eligibility_class"] in VALID_ELIGIBILITY_CLASSES, (
                f"Invalid eligibility class for {entry['country']}: "
                f"{entry['eligibility_class']}"
            )

    def test_eu27_all_covered(self) -> None:
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        from backend.constants import EU27_CODES
        covered = {e["country"] for e in COUNTRY_ELIGIBILITY_REGISTRY}
        missing = EU27_CODES - covered
        assert not missing, f"EU-27 countries missing from eligibility: {missing}"

    def test_reference_countries_covered(self) -> None:
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        covered = {e["country"] for e in COUNTRY_ELIGIBILITY_REGISTRY}
        required_refs = {"GB", "JP", "KR", "NO", "AU", "US", "CN", "SA", "RU", "BR", "IN", "ZA"}
        missing = required_refs - covered
        assert not missing, f"Reference countries missing: {missing}"

    def test_us_is_non_comparable_or_partially(self) -> None:
        """US with 3 producer inversions should NOT be confidently rateable."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass
        us_entry = None
        for e in COUNTRY_ELIGIBILITY_REGISTRY:
            if e["country"] == "US":
                us_entry = e
                break
        assert us_entry is not None
        assert us_entry["eligibility_class"] in (
            EligibilityClass.PARTIALLY_RATEABLE,
            EligibilityClass.NOT_CURRENTLY_RATEABLE,
        )

    def test_russia_not_currently_rateable(self) -> None:
        """Russia with sanctions should be NOT_CURRENTLY_RATEABLE."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass
        ru_entry = None
        for e in COUNTRY_ELIGIBILITY_REGISTRY:
            if e["country"] == "RU":
                ru_entry = e
                break
        assert ru_entry is not None
        assert ru_entry["eligibility_class"] == EligibilityClass.NOT_CURRENTLY_RATEABLE

    def test_large_eu_mostly_confidently_rateable(self) -> None:
        """Large EU members without inversions should be confidently rateable."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass
        for code in ["IT", "ES", "NL", "PL"]:
            entry = None
            for e in COUNTRY_ELIGIBILITY_REGISTRY:
                if e["country"] == code:
                    entry = e
                    break
            assert entry is not None, f"{code} not found"
            assert entry["eligibility_class"] == EligibilityClass.CONFIDENTLY_RATEABLE, (
                f"{code} should be CONFIDENTLY_RATEABLE but is {entry['eligibility_class']}"
            )

    def test_producer_countries_have_caveats(self) -> None:
        """Countries with producer inversions should have caveats or worse."""
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY, EligibilityClass
        producer_countries = {"FR", "DE", "NO", "AU", "CN", "US", "SA", "RU"}
        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            if entry["country"] in producer_countries:
                assert entry["eligibility_class"] != EligibilityClass.CONFIDENTLY_RATEABLE, (
                    f"Producer country {entry['country']} should not be "
                    f"CONFIDENTLY_RATEABLE"
                )

    def test_no_empty_rationale(self) -> None:
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            assert len(entry["rationale"]) > 10, (
                f"Country {entry['country']} has trivial rationale"
            )

    def test_data_strengths_nonempty(self) -> None:
        from backend.calibration import COUNTRY_ELIGIBILITY_REGISTRY
        for entry in COUNTRY_ELIGIBILITY_REGISTRY:
            assert len(entry["data_strengths"]) > 0, (
                f"Country {entry['country']} has no data strengths"
            )


# ═══════════════════════════════════════════════════════════════════════════
# TASK 7: EXPLICIT RATEABILITY ANSWER
# ═══════════════════════════════════════════════════════════════════════════

class TestRateabilityAnswer:
    """The system must answer: who can be confidently rated NOW?"""

    def test_eligibility_summary_structure(self) -> None:
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        assert "total_countries_assessed" in summary
        assert "by_class" in summary
        assert "answer_to_who_is_rateable_now" in summary
        assert "honesty_note" in summary

    def test_confidently_rateable_countries_exist(self) -> None:
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        confidently = summary["answer_to_who_is_rateable_now"]["confidently_rateable"]
        assert len(confidently) > 0, "No confidently rateable countries!"

    def test_not_currently_rateable_includes_russia(self) -> None:
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        not_rateable = summary["answer_to_who_is_rateable_now"]["not_currently_rateable"]
        assert "RU" in not_rateable

    def test_all_classes_represented(self) -> None:
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        answer = summary["answer_to_who_is_rateable_now"]
        # At least confidently and not_currently should have entries
        assert len(answer["confidently_rateable"]) > 0
        assert len(answer["not_currently_rateable"]) > 0

    def test_honesty_note_present(self) -> None:
        from backend.calibration import get_eligibility_summary
        summary = get_eligibility_summary()
        note = summary["honesty_note"]
        assert "correct" in note.lower() or "estimate" in note.lower()

    def test_filter_by_eligibility_class(self) -> None:
        from backend.calibration import get_countries_by_eligibility, EligibilityClass
        conf = get_countries_by_eligibility(EligibilityClass.CONFIDENTLY_RATEABLE)
        assert isinstance(conf, list)
        assert len(conf) > 0
        for entry in conf:
            assert entry["eligibility_class"] == EligibilityClass.CONFIDENTLY_RATEABLE

    def test_total_assessed_matches_registry(self) -> None:
        from backend.calibration import (
            get_eligibility_summary,
            COUNTRY_ELIGIBILITY_REGISTRY,
        )
        summary = get_eligibility_summary()
        assert summary["total_countries_assessed"] == len(COUNTRY_ELIGIBILITY_REGISTRY)


# ═══════════════════════════════════════════════════════════════════════════
# TASK 8: SENSITIVITY ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════════

class TestSensitivityAnalysis:
    """Sensitivity analysis engine must function correctly."""

    @pytest.fixture
    def sample_governance_results(self) -> dict[str, dict[str, Any]]:
        """Create sample governance results for testing."""
        from backend.governance import assess_country_governance
        # Create a representative set of test countries
        results = {}

        # Clean country (no flags)
        clean_axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        results["XX"] = assess_country_governance(
            country="XX",
            axis_results=clean_axes,
            severity_total=0.1,
            strict_comparability_tier="TIER_1",
        )

        # Moderately degraded country
        moderate_axes = [
            {"axis_id": 1, "data_quality_flags": ["SINGLE_CHANNEL_A"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 2, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 3, "data_quality_flags": ["REDUCED_PRODUCT_GRANULARITY"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 4, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 5, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 6, "data_quality_flags": [], "is_proxy": True, "validity": "VALID"},
        ]
        results["YY"] = assess_country_governance(
            country="YY",
            axis_results=moderate_axes,
            severity_total=0.6,
            strict_comparability_tier="TIER_2",
        )

        return results

    def test_sensitivity_analysis_runs(self, sample_governance_results) -> None:
        from backend.calibration import run_sensitivity_analysis
        result = run_sensitivity_analysis(sample_governance_results)
        assert "threshold_sensitivities" in result
        assert "overall_sensitivity" in result
        assert "interpretation" in result

    def test_sensitivity_has_confidence_thresholds(self, sample_governance_results) -> None:
        from backend.calibration import run_sensitivity_analysis
        result = run_sensitivity_analysis(sample_governance_results)
        names = {s["threshold"] for s in result["threshold_sensitivities"]}
        assert "CONFIDENCE_LEVEL:HIGH" in names
        assert "CONFIDENCE_LEVEL:MODERATE" in names
        assert "RANKING:MIN_MEAN_CONFIDENCE" in names
        assert "GOVERNANCE:MAX_INVERTED_AXES_COMPARABLE" in names

    def test_sensitivity_overall_assessment_valid(self, sample_governance_results) -> None:
        from backend.calibration import run_sensitivity_analysis
        result = run_sensitivity_analysis(sample_governance_results)
        assert result["overall_sensitivity"] in ("HIGH", "MODERATE", "LOW")

    def test_sensitivity_with_different_perturbation(self, sample_governance_results) -> None:
        from backend.calibration import run_sensitivity_analysis
        result_10 = run_sensitivity_analysis(sample_governance_results, perturbation_pct=0.10)
        result_20 = run_sensitivity_analysis(sample_governance_results, perturbation_pct=0.20)
        assert result_10["perturbation_pct"] == 0.10
        assert result_20["perturbation_pct"] == 0.20

    def test_sensitivity_empty_input(self) -> None:
        from backend.calibration import run_sensitivity_analysis
        result = run_sensitivity_analysis({})
        assert result["n_countries_analyzed"] == 0
        assert result["overall_sensitivity"] == "LOW"

    def test_sensitivity_threshold_detail_structure(self, sample_governance_results) -> None:
        from backend.calibration import run_sensitivity_analysis
        result = run_sensitivity_analysis(sample_governance_results)
        for s in result["threshold_sensitivities"]:
            assert "threshold" in s
            assert "current_value" in s
            assert "interpretation" in s
            assert "countries_affected_up" in s
            assert "countries_affected_down" in s


# ═══════════════════════════════════════════════════════════════════════════
# TASK 9: EXTERNAL BENCHMARK HOOKS
# ═══════════════════════════════════════════════════════════════════════════

class TestExternalBenchmarks:
    """External benchmark infrastructure must be present."""

    def test_benchmark_registry_nonempty(self) -> None:
        from backend.calibration import EXTERNAL_BENCHMARK_REGISTRY
        assert len(EXTERNAL_BENCHMARK_REGISTRY) >= 3

    def test_benchmark_entries_structure(self) -> None:
        from backend.calibration import EXTERNAL_BENCHMARK_REGISTRY
        required = {
            "benchmark_id", "name", "description",
            "relevant_axes", "comparison_type", "status",
            "integration_requirements", "expected_correlation",
            "validation_threshold",
        }
        for entry in EXTERNAL_BENCHMARK_REGISTRY:
            missing = required - set(entry.keys())
            assert not missing, (
                f"Benchmark '{entry.get('benchmark_id', '?')}' missing: {missing}"
            )

    def test_all_benchmarks_have_not_integrated_status(self) -> None:
        """Currently all benchmarks should be NOT_INTEGRATED (honest)."""
        from backend.calibration import get_benchmark_integration_status
        status = get_benchmark_integration_status()
        for bench_id, s in status.items():
            assert s == "NOT_INTEGRATED", (
                f"Benchmark {bench_id} claims status '{s}' but none "
                f"are actually integrated yet"
            )

    def test_energy_benchmark_exists(self) -> None:
        from backend.calibration import EXTERNAL_BENCHMARK_REGISTRY
        energy = [b for b in EXTERNAL_BENCHMARK_REGISTRY if 2 in b["relevant_axes"]]
        assert len(energy) > 0, "No energy benchmark defined"

    def test_financial_benchmark_exists(self) -> None:
        from backend.calibration import EXTERNAL_BENCHMARK_REGISTRY
        financial = [b for b in EXTERNAL_BENCHMARK_REGISTRY if 1 in b["relevant_axes"]]
        assert len(financial) > 0, "No financial benchmark defined"

    def test_defense_benchmark_exists(self) -> None:
        from backend.calibration import EXTERNAL_BENCHMARK_REGISTRY
        defense = [b for b in EXTERNAL_BENCHMARK_REGISTRY if 4 in b["relevant_axes"]]
        assert len(defense) > 0, "No defense benchmark defined"

    def test_critical_inputs_benchmark_exists(self) -> None:
        from backend.calibration import EXTERNAL_BENCHMARK_REGISTRY
        crit = [b for b in EXTERNAL_BENCHMARK_REGISTRY if 5 in b["relevant_axes"]]
        assert len(crit) > 0, "No critical inputs benchmark defined"


# ═══════════════════════════════════════════════════════════════════════════
# TASK 10: GOVERNANCE EXPLANATION OBJECT
# ═══════════════════════════════════════════════════════════════════════════

class TestGovernanceExplanation:
    """Enhanced governance explanation must include calibration metadata."""

    def test_build_explanation_structure(self) -> None:
        from backend.governance import assess_country_governance
        from backend.calibration import build_governance_explanation

        axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        gov = assess_country_governance(
            country="DE",
            axis_results=axes,
            severity_total=0.3,
            strict_comparability_tier="TIER_1",
        )
        explanation = build_governance_explanation(gov)

        assert "country" in explanation
        assert "governance_tier" in explanation
        assert "tier_meaning" in explanation
        assert "axis_calibration_quality" in explanation
        assert "calibration_disclosure" in explanation
        assert "eligibility_class" in explanation
        assert "falsifiability_note" in explanation
        assert "honesty_statement" in explanation

    def test_explanation_has_axis_calibration(self) -> None:
        from backend.governance import assess_country_governance
        from backend.calibration import build_governance_explanation

        axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        gov = assess_country_governance(
            country="IT",
            axis_results=axes,
            severity_total=0.1,
            strict_comparability_tier="TIER_1",
        )
        explanation = build_governance_explanation(gov)
        axis_cal = explanation["axis_calibration_quality"]
        assert len(axis_cal) == 6
        for ac in axis_cal:
            assert "axis_id" in ac
            assert "baseline_calibration_class" in ac
            assert "construct_validity_note" in ac
            assert "falsifiable_claim" in ac

    def test_explanation_eligibility_for_registered_country(self) -> None:
        from backend.governance import assess_country_governance
        from backend.calibration import build_governance_explanation

        axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        gov = assess_country_governance(
            country="JP",
            axis_results=axes,
            severity_total=0.1,
            strict_comparability_tier="TIER_1",
        )
        explanation = build_governance_explanation(gov)
        assert explanation["eligibility_class"] != "NOT_ASSESSED"

    def test_explanation_eligibility_for_unregistered_country(self) -> None:
        from backend.governance import assess_country_governance
        from backend.calibration import build_governance_explanation

        axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        gov = assess_country_governance(
            country="XX",  # Not in registry
            axis_results=axes,
            severity_total=0.1,
            strict_comparability_tier="TIER_1",
        )
        explanation = build_governance_explanation(gov)
        assert explanation["eligibility_class"] == "NOT_ASSESSED"

    def test_explanation_honesty_statement_nonempty(self) -> None:
        from backend.governance import assess_country_governance
        from backend.calibration import build_governance_explanation

        axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        gov = assess_country_governance(
            country="FR",
            axis_results=axes,
            severity_total=0.3,
            strict_comparability_tier="TIER_1",
        )
        explanation = build_governance_explanation(gov)
        assert len(explanation["honesty_statement"]) > 50
        assert "judgment" in explanation["honesty_statement"].lower() or \
               "assessment" in explanation["honesty_statement"].lower()

    def test_tier_meaning_for_all_tiers(self) -> None:
        from backend.calibration import _tier_meaning
        for tier in ["FULLY_COMPARABLE", "PARTIALLY_COMPARABLE",
                      "LOW_CONFIDENCE", "NON_COMPARABLE"]:
            meaning = _tier_meaning(tier)
            assert len(meaning) > 20, f"Tier meaning for {tier} is trivial"


# ═══════════════════════════════════════════════════════════════════════════
# TASK 11: GOVERNANCE MODULE CALIBRATION LABELS
# ═══════════════════════════════════════════════════════════════════════════

class TestGovernanceCalibrationLabels:
    """Governance module must include calibration references."""

    def test_governance_result_has_calibration_note(self) -> None:
        from backend.governance import assess_country_governance

        axes = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        result = assess_country_governance(
            country="DE",
            axis_results=axes,
            severity_total=0.1,
            strict_comparability_tier="TIER_1",
        )
        assert "calibration_note" in result
        assert "calibration" in result["calibration_note"].lower()

    def test_governance_module_has_calibration_comments(self) -> None:
        """Check that governance.py has calibration class annotations."""
        import inspect
        import backend.governance as gov_module
        source = inspect.getsource(gov_module)
        assert "Calibration class:" in source or "calibration_class" in source
        assert "HEURISTIC" in source or "SEMI_EMPIRICAL" in source
        assert "backend/calibration.py" in source


# ═══════════════════════════════════════════════════════════════════════════
# TASK 13: PSEUDO-RIGOR SELF-AUDIT
# ═══════════════════════════════════════════════════════════════════════════

class TestPseudoRigorAudit:
    """Self-audit for pseudo-rigor must be comprehensive."""

    def test_audit_nonempty(self) -> None:
        from backend.calibration import PSEUDO_RIGOR_AUDIT
        assert len(PSEUDO_RIGOR_AUDIT) >= 5

    def test_audit_entry_structure(self) -> None:
        from backend.calibration import PSEUDO_RIGOR_AUDIT
        required = {"risk", "location", "mitigation", "residual_risk", "recommendation"}
        for entry in PSEUDO_RIGOR_AUDIT:
            missing = required - set(entry.keys())
            assert not missing, f"Audit entry missing: {missing}"

    def test_high_residual_risks_exist(self) -> None:
        """At least one HIGH residual risk should be documented (honesty)."""
        from backend.calibration import PSEUDO_RIGOR_AUDIT
        high_risks = [e for e in PSEUDO_RIGOR_AUDIT if "HIGH" in e["residual_risk"]]
        assert len(high_risks) > 0, (
            "No HIGH residual risks documented — this is suspiciously optimistic"
        )

    def test_falsifiability_without_testing_flagged(self) -> None:
        """The audit must flag that falsifiability criteria are declared but not tested."""
        from backend.calibration import PSEUDO_RIGOR_AUDIT
        found = False
        for entry in PSEUDO_RIGOR_AUDIT:
            if "falsifiab" in entry["risk"].lower() and "test" in entry["risk"].lower():
                found = True
                break
        assert found, (
            "Audit must flag that falsifiability criteria exist but are not tested"
        )

    def test_summary_structure(self) -> None:
        from backend.calibration import get_pseudo_rigor_summary
        summary = get_pseudo_rigor_summary()
        assert "total_risks_identified" in summary
        assert "by_residual_risk_level" in summary
        assert "highest_residual_risk" in summary
        assert "overall_assessment" in summary

    def test_summary_overall_assessment_honest(self) -> None:
        from backend.calibration import get_pseudo_rigor_summary
        summary = get_pseudo_rigor_summary()
        assessment = summary["overall_assessment"]
        # Should acknowledge lack of empirical grounding
        assert "empiric" in assessment.lower() or "calibrat" in assessment.lower()

    def test_get_pseudo_rigor_audit(self) -> None:
        from backend.calibration import get_pseudo_rigor_audit
        audit = get_pseudo_rigor_audit()
        assert isinstance(audit, list)
        assert len(audit) >= 5


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCalibrationIntegration:
    """Integration tests verifying calibration module works with governance."""

    def test_full_pipeline_governance_to_explanation(self) -> None:
        """Full flow: governance → calibration explanation."""
        from backend.governance import assess_country_governance
        from backend.calibration import build_governance_explanation

        axes = [
            {"axis_id": 1, "data_quality_flags": ["CPIS_NON_PARTICIPANT"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 2, "data_quality_flags": ["PRODUCER_INVERSION"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 3, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 4, "data_quality_flags": ["PRODUCER_INVERSION"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 5, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 6, "data_quality_flags": [], "is_proxy": True, "validity": "VALID"},
        ]
        gov = assess_country_governance(
            country="CN",
            axis_results=axes,
            severity_total=1.2,
            strict_comparability_tier="TIER_2",
        )
        explanation = build_governance_explanation(gov)

        # CN should be LOW_CONFIDENCE (2 inversions)
        assert gov["governance_tier"] == "LOW_CONFIDENCE"
        assert explanation["governance_tier"] == "LOW_CONFIDENCE"
        assert explanation["eligibility_class"] in (
            "PARTIALLY_RATEABLE", "RATEABLE_WITH_CAVEATS", "LOW_CONFIDENCE"
        )

    def test_sensitivity_analysis_with_real_governance(self) -> None:
        """Sensitivity analysis with governance output."""
        from backend.governance import assess_country_governance
        from backend.calibration import run_sensitivity_analysis

        # Create two countries
        results = {}

        clean = [
            {"axis_id": i, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"}
            for i in range(1, 7)
        ]
        results["CLEAN"] = assess_country_governance(
            country="CLEAN", axis_results=clean,
            severity_total=0.1, strict_comparability_tier="TIER_1",
        )

        degraded = [
            {"axis_id": 1, "data_quality_flags": ["SINGLE_CHANNEL_A"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 2, "data_quality_flags": ["TEMPORAL_MISMATCH"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 3, "data_quality_flags": ["REDUCED_PRODUCT_GRANULARITY"], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 4, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 5, "data_quality_flags": [], "is_proxy": False, "validity": "VALID"},
            {"axis_id": 6, "data_quality_flags": [], "is_proxy": True, "validity": "VALID"},
        ]
        results["DEGRADED"] = assess_country_governance(
            country="DEGRADED", axis_results=degraded,
            severity_total=0.8, strict_comparability_tier="TIER_2",
        )

        sensitivity = run_sensitivity_analysis(results)
        assert sensitivity["n_countries_analyzed"] == 2
        assert len(sensitivity["threshold_sensitivities"]) > 0

    def test_calibration_module_importable(self) -> None:
        """Verify the entire module imports cleanly."""
        import backend.calibration as cal
        assert hasattr(cal, "THRESHOLD_REGISTRY")
        assert hasattr(cal, "FALSIFIABILITY_REGISTRY")
        assert hasattr(cal, "CIRCULARITY_AUDIT")
        assert hasattr(cal, "AXIS_CALIBRATION_NOTES")
        assert hasattr(cal, "COUNTRY_ELIGIBILITY_REGISTRY")
        assert hasattr(cal, "EXTERNAL_BENCHMARK_REGISTRY")
        assert hasattr(cal, "PSEUDO_RIGOR_AUDIT")
        assert hasattr(cal, "get_threshold_registry")
        assert hasattr(cal, "get_calibration_summary")
        assert hasattr(cal, "build_governance_explanation")
        assert hasattr(cal, "run_sensitivity_analysis")
