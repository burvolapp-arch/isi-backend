"""
tests.test_methodological_hardening — Post–real-data integration hardening tests.

Covers all 9 tasks from the Methodological Hardening Pass:
    Task 1: Defense Axis Interpretation Hardening
    Task 2: Time Window Discipline
    Task 3: Non-State Entity Classification
    Task 4: Cross-Axis Comparability Hardening
    Task 5: Output Interpretation Safeguards
    Task 6: Defense Axis Validation Sanity Check
    Task 7: SIPRI Ingestion Final Hardening
    Task 8: Document True Limitations (docs — verified by existence)
    Task 9: DO NOT OVERBUILD (constraint — no new sources)
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest


# ===========================================================================
# TASK 1 — DEFENSE AXIS INTERPRETATION HARDENING
# ===========================================================================

class TestDefenseAxisInterpretation:
    """Every defense output must carry scope/TIV/exclusion metadata."""

    def test_axis_registry_defense_has_value_type(self):
        """Defense axis must declare value_type = TIV_MN."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        assert defense["value_type"] == "TIV_MN", (
            "Defense axis value_type must be TIV_MN (SIPRI Trend Indicator Value)"
        )

    def test_axis_registry_defense_has_interpretation_note(self):
        """Defense axis must have explicit interpretation_note about TIV != monetary."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        note = defense["interpretation_note"]
        assert "TIV" in note
        assert "NOT" in note or "not" in note
        assert "monetary" in note.lower() or "usd" in note.upper()

    def test_axis_registry_defense_has_exclusions(self):
        """Defense axis must list what SIPRI does NOT cover."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        exclusions = defense["exclusions"]
        assert len(exclusions) >= 5, (
            f"Defense axis must list ≥5 exclusions, got {len(exclusions)}"
        )
        exclusion_text = " ".join(exclusions).lower()
        assert "small arms" in exclusion_text
        assert "ammunition" in exclusion_text or "ordnance" in exclusion_text
        assert "cyber" in exclusion_text or "electronic warfare" in exclusion_text

    def test_axis_registry_defense_has_scope(self):
        """Defense axis must have a scope description."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        assert "scope" in defense
        assert "major conventional weapons" in defense["scope"].lower()

    def test_axis_registry_defense_confidence_baseline(self):
        """Defense axis confidence_baseline must be lower than trade axes."""
        from pipeline.config import AXIS_REGISTRY
        defense_cb = AXIS_REGISTRY[4]["confidence_baseline"]
        energy_cb = AXIS_REGISTRY[2]["confidence_baseline"]
        tech_cb = AXIS_REGISTRY[3]["confidence_baseline"]
        assert defense_cb < energy_cb, (
            f"Defense confidence ({defense_cb}) should be < energy ({energy_cb})"
        )
        assert defense_cb < tech_cb, (
            f"Defense confidence ({defense_cb}) should be < technology ({tech_cb})"
        )

    def test_axis_result_to_dict_includes_axis_constraints(self):
        """AxisResult.to_dict() must include axis_constraints field."""
        from backend.axis_result import AxisResult
        ar = AxisResult(
            country="JP", axis_id=4, axis_slug="defense",
            score=0.95, basis="BOTH", validity="VALID",
            coverage=1.0, source="sipri", warnings=(),
            channel_a_concentration=0.95, channel_b_concentration=0.90,
        )
        d = ar.to_dict()
        assert "axis_constraints" in d
        c = d["axis_constraints"]
        assert c["value_type"] == "TIV_MN"
        assert "TIV" in c["interpretation_note"]
        assert len(c["exclusions"]) >= 5

    def test_defense_axis_constraints_tiv_warning(self):
        """Defense axis_constraints must warn that TIV != monetary value."""
        from backend.axis_result import AxisResult
        ar = AxisResult(
            country="JP", axis_id=4, axis_slug="defense",
            score=0.95, basis="BOTH", validity="VALID",
            coverage=1.0, source="sipri", warnings=(),
            channel_a_concentration=0.95, channel_b_concentration=0.90,
        )
        d = ar.to_dict()
        note = d["axis_constraints"]["interpretation_note"]
        assert "incommensurable" in note.lower() or "cannot be compared" in note.lower()


# ===========================================================================
# TASK 2 — TIME WINDOW DISCIPLINE
# ===========================================================================

class TestTimeWindowDiscipline:
    """Window semantics, procurement lumpiness, temporal sensitivity encoded."""

    def test_defense_window_type_is_rolling(self):
        """Defense axis must declare rolling_delivery_window, not annual_flow."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        assert defense["window_type"] == "rolling_delivery_window"

    def test_defense_temporal_sensitivity_is_high(self):
        """Defense axis temporal_sensitivity must be 'high'."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        assert defense["temporal_sensitivity"] == "high"

    def test_defense_window_semantics_mentions_lumpiness(self):
        """Defense window_semantics must explain procurement lumpiness."""
        from pipeline.config import AXIS_REGISTRY
        defense = AXIS_REGISTRY[4]
        ws = defense["window_semantics"]
        assert "lumpy" in ws.lower() or "lumpiness" in ws.lower()

    def test_trade_axes_annual_flow(self):
        """Trade axes (energy, technology, critical_inputs) must use annual_flow."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id in [2, 3, 5]:
            info = AXIS_REGISTRY[axis_id]
            assert info["window_type"] == "annual_flow", (
                f"Axis {info['slug']} should use annual_flow, got {info['window_type']}"
            )

    def test_financial_axis_snapshot(self):
        """Financial axis must use snapshot window (positions, not flows)."""
        from pipeline.config import AXIS_REGISTRY
        assert AXIS_REGISTRY[1]["window_type"] == "snapshot"

    def test_all_axes_have_window_semantics(self):
        """Every axis must declare window_type and window_semantics."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            assert "window_type" in info, f"Axis {info['slug']} missing window_type"
            assert "window_semantics" in info, f"Axis {info['slug']} missing window_semantics"
            assert info["window_semantics"], f"Axis {info['slug']} has empty window_semantics"


# ===========================================================================
# TASK 3 — NON-STATE ENTITY CLASSIFICATION
# ===========================================================================

class TestNonStateEntityClassification:
    """STATE / MULTINATIONAL / NONSTATE / UNKNOWN — no blanket drop."""

    def test_multinational_orgs_classified_correctly(self):
        """NATO, AU, UN must map to __MULTINATIONAL__, not __NONSTATE__."""
        from pipeline.config import SIPRI_TO_ISO2
        assert SIPRI_TO_ISO2["NATO**"] == "__MULTINATIONAL__"
        assert SIPRI_TO_ISO2["African Union**"] == "__MULTINATIONAL__"
        assert SIPRI_TO_ISO2["United Nations**"] == "__MULTINATIONAL__"

    def test_armed_groups_classified_correctly(self):
        """Hezbollah, Houthis, RSF must remain __NONSTATE__."""
        from pipeline.config import SIPRI_TO_ISO2
        assert SIPRI_TO_ISO2["Hezbollah (Lebanon)*"] == "__NONSTATE__"
        assert SIPRI_TO_ISO2["Houthi rebels (Yemen)*"] == "__NONSTATE__"
        assert SIPRI_TO_ISO2["RSF (Sudan)*"] == "__NONSTATE__"

    def test_unknown_entities_classified_correctly(self):
        """Unknown recipients/suppliers must map to __UNKNOWN__."""
        from pipeline.config import SIPRI_TO_ISO2
        assert SIPRI_TO_ISO2["Unknown recipient(s)"] == "__UNKNOWN__"

    def test_classify_sipri_entity_function(self):
        """_classify_sipri_entity returns correct category."""
        from pipeline.ingest.sipri import _classify_sipri_entity
        assert _classify_sipri_entity("NATO**") == "MULTINATIONAL"
        assert _classify_sipri_entity("Hezbollah (Lebanon)*") == "NONSTATE"
        assert _classify_sipri_entity("Unknown recipient(s)") == "UNKNOWN"
        assert _classify_sipri_entity("Japan") == "STATE"
        assert _classify_sipri_entity("Nonexistent Country XYZ") == "UNMAPPED"
        assert _classify_sipri_entity("") == "UNMAPPED"

    def test_resolve_sipri_country_drops_all_sentinel_codes(self):
        """All sentinel codes (__NONSTATE__, __MULTINATIONAL__, __UNKNOWN__) resolve to None."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("NATO**") is None
        assert _resolve_sipri_country("Hezbollah (Lebanon)*") is None
        assert _resolve_sipri_country("Unknown recipient(s)") is None
        assert _resolve_sipri_country("African Union**") is None

    def test_entity_classification_in_stats(self):
        """Ingestion stats must include entity_classification breakdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _make_test_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    # NATO recipient (multinational)
                    ["1", "United States", "NATO**", "Patriot", "SAM",
                     "Air-defence systems", "2020", "", "5", "",
                     "2022", "", "New", "", "", "100", ""],
                    # Hezbollah supplier (nonstate)
                    ["2", "Hezbollah (Lebanon)*", "Germany", "ATGM", "missile",
                     "Missiles", "2021", "", "1", "",
                     "2022", "", "New", "", "", "50", ""],
                    # Real state row
                    ["3", "France", "Germany", "MILAN", "ATGM",
                     "Missiles", "2021", "", "3", "",
                     "2023", "", "New", "", "", "30", ""],
                ],
            )
            from pipeline.ingest.sipri import ingest_sipri
            result, stats = ingest_sipri(
                "DE", raw_path=csv_path, year_range=(2020, 2025),
            )
            ec = stats["entity_classification"]
            assert "recipients_multinational" in ec
            assert "recipients_nonstate" in ec
            assert "suppliers_state" in ec
            assert "suppliers_multinational" in ec

    def test_aggregate_partner_iso2_includes_multinational(self):
        """AGGREGATE_PARTNER_ISO2 must include __MULTINATIONAL__ sentinel."""
        from pipeline.config import AGGREGATE_PARTNER_ISO2
        assert "__MULTINATIONAL__" in AGGREGATE_PARTNER_ISO2
        assert "__NONSTATE__" in AGGREGATE_PARTNER_ISO2
        assert "__UNKNOWN__" in AGGREGATE_PARTNER_ISO2


# ===========================================================================
# TASK 4 — CROSS-AXIS COMPARABILITY HARDENING
# ===========================================================================

class TestCrossAxisComparability:
    """Axis-level metadata: value_type, confidence score, scope limitations."""

    def test_all_axes_have_value_type(self):
        """Every axis must declare its value_type."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            assert "value_type" in info, f"Axis {info['slug']} missing value_type"
            assert info["value_type"] in ("USD_MN", "TIV_MN", "MIXED"), (
                f"Axis {info['slug']} has unexpected value_type: {info['value_type']}"
            )

    def test_all_axes_have_confidence_baseline(self):
        """Every axis must declare a confidence_baseline ∈ (0, 1]."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            cb = info["confidence_baseline"]
            assert 0.0 < cb <= 1.0, (
                f"Axis {info['slug']} confidence_baseline={cb} out of (0,1]"
            )

    def test_all_axes_have_scope(self):
        """Every axis must have a non-empty scope description."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            assert info.get("scope"), f"Axis {info['slug']} has empty/missing scope"

    def test_all_axes_have_interpretation_note(self):
        """Every axis must have a non-empty interpretation_note."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            assert info.get("interpretation_note"), (
                f"Axis {info['slug']} has empty/missing interpretation_note"
            )

    def test_all_axes_have_exclusions(self):
        """Every axis must list at least 2 exclusions."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            excl = info.get("exclusions", [])
            assert len(excl) >= 2, (
                f"Axis {info['slug']} has <2 exclusions: {excl}"
            )

    def test_axis_constraints_in_axis_result_all_axes(self):
        """AxisResult.to_dict() includes axis_constraints for every axis."""
        from backend.axis_result import AxisResult, AXIS_ID_TO_SLUG
        for axis_id in range(1, 7):
            ar = AxisResult(
                country="JP", axis_id=axis_id,
                axis_slug=AXIS_ID_TO_SLUG[axis_id],
                score=0.5, basis="BOTH", validity="VALID",
                coverage=1.0, source="test", warnings=(),
                channel_a_concentration=0.5, channel_b_concentration=0.5,
            )
            d = ar.to_dict()
            c = d["axis_constraints"]
            assert c["value_type"] in ("USD_MN", "TIV_MN", "MIXED"), (
                f"Axis {axis_id} ({AXIS_ID_TO_SLUG[axis_id]}): "
                f"unexpected value_type {c['value_type']}"
            )
            assert c["interpretation_note"], (
                f"Axis {axis_id}: empty interpretation_note in constraints"
            )

    def test_defense_value_type_differs_from_trade_axes(self):
        """Defense (TIV_MN) must have different value_type from trade axes (USD_MN)."""
        from pipeline.config import AXIS_REGISTRY
        assert AXIS_REGISTRY[4]["value_type"] == "TIV_MN"
        assert AXIS_REGISTRY[2]["value_type"] == "USD_MN"
        assert AXIS_REGISTRY[3]["value_type"] == "USD_MN"
        assert AXIS_REGISTRY[5]["value_type"] == "USD_MN"


# ===========================================================================
# TASK 5 — OUTPUT INTERPRETATION SAFEGUARDS
# ===========================================================================

class TestOutputInterpretationSafeguards:
    """Every output must include caveats/limitations."""

    def test_bilateral_dataset_metadata_has_caveats(self):
        """BilateralDataset.to_metadata_json() must include interpretation_caveats."""
        from pipeline.schema import BilateralDataset, BilateralRecord
        ds = BilateralDataset(
            reporter="JP", axis="defense", source="sipri",
            year_range=(2020, 2025),
        )
        ds.add_record(BilateralRecord(
            reporter="JP", partner="US", value=100.0, year=2022,
            source="sipri", axis="defense", unit="TIV_MN",
        ))
        ds.compute_metadata()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "meta.json"
            ds.to_metadata_json(path)
            with open(path) as f:
                meta = json.load(f)
            assert "interpretation_caveats" in meta
            assert "axis_constraints" in meta
            caveats = meta["interpretation_caveats"]
            assert len(caveats) >= 1, "Defense axis should have caveats"
            # TIV caveat must be present for defense axis
            caveat_text = " ".join(caveats).lower()
            assert "tiv" in caveat_text

    def test_energy_axis_metadata_has_caveats(self):
        """Energy axis metadata must also include interpretation_caveats."""
        from pipeline.schema import BilateralDataset, BilateralRecord
        ds = BilateralDataset(
            reporter="JP", axis="energy", source="un_comtrade",
            year_range=(2022, 2024),
        )
        ds.add_record(BilateralRecord(
            reporter="JP", partner="SA", value=50000.0, year=2023,
            source="un_comtrade", axis="energy", unit="USD_MN",
        ))
        ds.compute_metadata()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "meta.json"
            ds.to_metadata_json(path)
            with open(path) as f:
                meta = json.load(f)
            assert "interpretation_caveats" in meta
            assert "axis_constraints" in meta
            c = meta["axis_constraints"]
            assert c["value_type"] == "USD_MN"

    def test_axis_result_to_dict_constraints_always_present(self):
        """axis_constraints must be present even for INVALID results."""
        from backend.axis_result import make_invalid_axis
        ar = make_invalid_axis("JP", 4, "sipri", warnings=("D-5",))
        d = ar.to_dict()
        assert "axis_constraints" in d
        assert d["axis_constraints"]["value_type"] == "TIV_MN"


# ===========================================================================
# TASK 6 — DEFENSE AXIS VALIDATION SANITY CHECK
# ===========================================================================

class TestDefenseValidationSanityCheck:
    """Extreme concentration detection, plausibility warnings for defense."""

    def test_defense_plausibility_check_exists(self):
        """check_defense_plausibility must be in ALL_CHECKS."""
        from pipeline.validate import ALL_CHECKS, check_defense_plausibility
        assert check_defense_plausibility in ALL_CHECKS

    def test_defense_plausibility_skips_non_defense(self):
        """check_defense_plausibility returns PASS for non-defense datasets."""
        from pipeline.validate import check_defense_plausibility
        from pipeline.schema import BilateralDataset, BilateralRecord
        ds = BilateralDataset(
            reporter="JP", axis="energy", source="un_comtrade",
            year_range=(2022, 2024),
        )
        ds.add_record(BilateralRecord(
            reporter="JP", partner="SA", value=50000.0, year=2023,
            source="un_comtrade", axis="energy",
        ))
        ds.compute_metadata()
        result = check_defense_plausibility(ds)
        assert result.passed
        assert result.details.get("skipped") is True

    def test_defense_plausibility_flags_concentration(self):
        """High defense concentration (>90%) must be flagged as WARNING, not FAIL."""
        from pipeline.validate import check_defense_plausibility
        from pipeline.schema import BilateralDataset, BilateralRecord
        ds = BilateralDataset(
            reporter="JP", axis="defense", source="sipri",
            year_range=(2020, 2025),
        )
        # 95% from US, 5% from GB
        ds.add_record(BilateralRecord(
            reporter="JP", partner="US", value=950.0, year=2022,
            source="sipri", axis="defense", unit="TIV_MN",
        ))
        ds.add_record(BilateralRecord(
            reporter="JP", partner="GB", value=50.0, year=2022,
            source="sipri", axis="defense", unit="TIV_MN",
        ))
        ds.compute_metadata()
        result = check_defense_plausibility(ds)
        # WARNING, not FAIL — defense concentration is structurally normal
        assert result.passed, "Defense concentration should be WARNING, not FAIL"
        assert any("W-DEFENSE-CONCENTRATION" in w for w in result.warnings)
        # Warning must explain SIPRI scope
        assert any("SIPRI" in w for w in result.warnings)

    def test_defense_plausibility_flags_sparsity(self):
        """Defense dataset with ≤3 partners must carry sparsity annotation."""
        from pipeline.validate import check_defense_plausibility
        from pipeline.schema import BilateralDataset, BilateralRecord
        ds = BilateralDataset(
            reporter="JP", axis="defense", source="sipri",
            year_range=(2020, 2025),
        )
        ds.add_record(BilateralRecord(
            reporter="JP", partner="US", value=500.0, year=2022,
            source="sipri", axis="defense", unit="TIV_MN",
        ))
        ds.add_record(BilateralRecord(
            reporter="JP", partner="GB", value=50.0, year=2022,
            source="sipri", axis="defense", unit="TIV_MN",
        ))
        ds.compute_metadata()
        result = check_defense_plausibility(ds)
        assert any("W-DEFENSE-SPARSE" in w for w in result.warnings)

    def test_defense_plausibility_flags_wrong_unit(self):
        """Defense records with unit=USD_MN must be flagged."""
        from pipeline.validate import check_defense_plausibility
        from pipeline.schema import BilateralDataset, BilateralRecord
        ds = BilateralDataset(
            reporter="JP", axis="defense", source="sipri",
            year_range=(2020, 2025),
        )
        ds.add_record(BilateralRecord(
            reporter="JP", partner="US", value=500.0, year=2022,
            source="sipri", axis="defense", unit="USD_MN",
        ))
        ds.compute_metadata()
        result = check_defense_plausibility(ds)
        assert any("W-DEFENSE-UNIT-MISMATCH" in w for w in result.warnings)


# ===========================================================================
# TASK 7 — SIPRI INGESTION FINAL HARDENING
# ===========================================================================

class TestSIPRIIngestionHardening:
    """Strict schema, deterministic parsing, full lineage tracking."""

    def test_sipri_records_use_tiv_unit(self):
        """SIPRI ingestion must produce records with unit='TIV_MN'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _make_test_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["1", "France", "Japan", "Rafale", "combat aircraft",
                     "Aircraft", "2020", "", "4", "",
                     "2022", "", "New", "", "", "320", ""],
                ],
            )
            from pipeline.ingest.sipri import ingest_sipri
            result, stats = ingest_sipri(
                "JP", raw_path=csv_path, year_range=(2020, 2025),
            )
            assert result is not None
            for r in result.records:
                assert r.unit == "TIV_MN", (
                    f"SIPRI record has unit='{r.unit}', expected 'TIV_MN'"
                )

    def test_sipri_stats_include_entity_classification(self):
        """Stats must include entity_classification breakdown."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _make_test_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["1", "France", "Japan", "Rafale", "combat aircraft",
                     "Aircraft", "2020", "", "4", "",
                     "2022", "", "New", "", "", "320", ""],
                ],
            )
            from pipeline.ingest.sipri import ingest_sipri
            _, stats = ingest_sipri(
                "JP", raw_path=csv_path, year_range=(2020, 2025),
            )
            ec = stats["entity_classification"]
            assert "recipients_state" in ec
            assert "recipients_multinational" in ec
            assert "recipients_nonstate" in ec
            assert "recipients_unknown" in ec
            assert "recipients_unmapped" in ec
            assert "suppliers_state" in ec

    def test_sipri_stats_include_multinational_counters(self):
        """Stats must include separate rows_multinational_* counters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _make_test_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["1", "France", "Japan", "Rafale", "combat aircraft",
                     "Aircraft", "2020", "", "4", "",
                     "2022", "", "New", "", "", "320", ""],
                ],
            )
            from pipeline.ingest.sipri import ingest_sipri
            _, stats = ingest_sipri(
                "JP", raw_path=csv_path, year_range=(2020, 2025),
            )
            assert "rows_multinational_recipient" in stats
            assert "rows_multinational_supplier" in stats
            assert "rows_unknown_recipient" in stats
            assert "rows_unknown_supplier" in stats

    def test_sipri_all_records_axis_defense(self):
        """Every SIPRI record must have axis='defense'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = _make_test_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["1", "United States", "Japan", "F-35A", "combat aircraft",
                     "Aircraft", "2020", "", "4", "",
                     "2022", "", "New", "", "", "800", ""],
                ],
            )
            from pipeline.ingest.sipri import ingest_sipri
            result, _ = ingest_sipri(
                "JP", raw_path=csv_path, year_range=(2020, 2025),
            )
            assert result is not None
            for r in result.records:
                assert r.axis == "defense"
                assert r.source == "sipri"


# ===========================================================================
# TASK 8 — DOCUMENT TRUE LIMITATIONS (structural tests)
# ===========================================================================

class TestDocumentationExists:
    """Verify documentation completeness."""

    def test_pipeline_architecture_doc_exists(self):
        """PIPELINE_ARCHITECTURE.md must exist."""
        doc_path = Path(__file__).parent.parent / "docs" / "PIPELINE_ARCHITECTURE.md"
        assert doc_path.is_file(), f"Missing: {doc_path}"

    def test_agent_rules_doc_exists(self):
        """AGENT_RULES.md must exist."""
        doc_path = Path(__file__).parent.parent / "docs" / "AGENT_RULES.md"
        assert doc_path.is_file(), f"Missing: {doc_path}"


# ===========================================================================
# TASK 9 — DO NOT OVERBUILD (constraint verification)
# ===========================================================================

class TestNoOverbuild:
    """Verify no new data sources or axes were added."""

    def test_axis_count_unchanged(self):
        """Must still be exactly 6 axes."""
        from pipeline.config import AXIS_REGISTRY
        assert len(AXIS_REGISTRY) == 6

    def test_source_count_unchanged(self):
        """SOURCES tuple must not have new entries."""
        from pipeline.config import SOURCES
        assert len(SOURCES) == 8  # 8 canonical sources

    def test_no_new_axis_slugs(self):
        """Axis slugs must be the canonical 6."""
        from pipeline.config import AXIS_SLUGS
        expected = {1: "financial", 2: "energy", 3: "technology",
                    4: "defense", 5: "critical_inputs", 6: "logistics"}
        assert AXIS_SLUGS == expected


# ===========================================================================
# INTEGRATION — AXIS CONSTRAINTS PROPAGATION
# ===========================================================================

class TestAxisConstraintsPropagation:
    """Verify axis_constraints propagate through the full output chain."""

    def test_composite_result_axes_have_constraints(self):
        """CompositeResult.to_dict()['axes'] must each include axis_constraints."""
        from backend.axis_result import (
            AxisResult, CompositeResult, compute_composite_v11,
            AXIS_ID_TO_SLUG,
        )
        axes = []
        for i in range(1, 7):
            axes.append(AxisResult(
                country="JP", axis_id=i, axis_slug=AXIS_ID_TO_SLUG[i],
                score=0.5, basis="BOTH", validity="VALID",
                coverage=1.0, source="test", warnings=(),
                channel_a_concentration=0.5, channel_b_concentration=0.5,
            ))
        composite = compute_composite_v11(
            axes, "JP", "Japan", "global", "v1.0",
        )
        d = composite.to_dict()
        for ax in d["axes"]:
            assert "axis_constraints" in ax, (
                f"Axis {ax['axis_slug']} missing axis_constraints in composite output"
            )
            c = ax["axis_constraints"]
            assert "value_type" in c
            assert "interpretation_note" in c
            assert "exclusions" in c

    def test_defense_axis_in_composite_has_tiv_warning(self):
        """Defense axis within composite must carry TIV interpretation warning."""
        from backend.axis_result import (
            AxisResult, compute_composite_v11, AXIS_ID_TO_SLUG,
        )
        axes = []
        for i in range(1, 7):
            axes.append(AxisResult(
                country="JP", axis_id=i, axis_slug=AXIS_ID_TO_SLUG[i],
                score=0.5, basis="BOTH", validity="VALID",
                coverage=1.0, source="test", warnings=(),
                channel_a_concentration=0.5, channel_b_concentration=0.5,
            ))
        composite = compute_composite_v11(
            axes, "JP", "Japan", "global", "v1.0",
        )
        d = composite.to_dict()
        defense_ax = [a for a in d["axes"] if a["axis_slug"] == "defense"][0]
        assert defense_ax["axis_constraints"]["value_type"] == "TIV_MN"
        assert "TIV" in defense_ax["axis_constraints"]["interpretation_note"]


# ===========================================================================
# Helpers
# ===========================================================================

def _make_test_sipri_csv(path: Path, rows: list[list[str]]) -> Path:
    """Create a synthetic SIPRI CSV with 11-line preamble and 17-column header.

    Row format (17 fields):
        ID, Supplier, Recipient, Designation, Description, Armament category,
        Order date, Order date is estimate, Numbers delivered, Numbers delivered is estimate,
        Delivery year, Delivery year is estimate, Status, SIPRI estimate,
        TIV deal unit, TIV delivery values, Local production
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        for i in range(11):
            f.write(f"Metadata line {i + 1}\n")
        writer = csv.writer(f)
        writer.writerow([
            "SIPRI AT Database ID", "Supplier", "Recipient",
            "Designation", "Description", "Armament category",
            "Order date", "Order date is estimate",
            "Numbers delivered", "Numbers delivered is estimate",
            "Delivery year", "Delivery year is estimate",
            "Status", "SIPRI estimate", "TIV deal unit",
            "TIV delivery values", "Local production",
        ])
        for row in rows:
            # Caller provides 17 values matching the header above
            writer.writerow(row)
    return path
