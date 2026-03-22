"""
tests.test_ingestion_pipeline — Test suite for the ISI data ingestion pipeline.

Covers:
    - Schema construction and validation (BilateralRecord, BilateralDataset)
    - Normalization engine (ISO mapping, aggregate filtering, dedup)
    - Validation engine (all 9 checks)
    - Ingestion modules (structural tests with synthetic data)
    - Pipeline orchestrator (integration smoke tests)

Test philosophy:
    - Every test is DETERMINISTIC (no randomness, no network calls)
    - Every test uses synthetic data (no dependency on raw files)
    - Failure messages are diagnostic (tell you WHAT failed and WHY)
"""

from __future__ import annotations

import csv
import json
import tempfile
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.schema import BilateralRecord, BilateralDataset, IngestionManifest
from pipeline.validate import (
    check_partner_count,
    check_aggregate_detection,
    check_sum_integrity,
    check_dominance,
    check_missing_key_partners,
    check_schema_compliance,
    check_self_trade,
    check_duplicate_records,
    check_year_coverage,
    validate_dataset,
    validate_and_report,
    ValidationResult,
)
from pipeline.normalize import (
    normalize_country_code,
    is_aggregate_partner,
    normalize_records,
    map_hs_to_category,
    NormalizationAudit,
)
from pipeline.config import (
    ISO3_TO_ISO2,
    SIPRI_TO_ISO2,
    BIS_TO_ISO2,
    AGGREGATE_PARTNER_NAMES,
    AXIS_REGISTRY,
    ALL_ISI_COUNTRIES,
)


# ===========================================================================
# HELPERS — synthetic data factories
# ===========================================================================

def make_record(
    reporter: str = "JP",
    partner: str = "US",
    value: float = 100.0,
    year: int = 2024,
    source: str = "test",
    axis: str = "financial",
    **kwargs,
) -> BilateralRecord:
    """Create a BilateralRecord with sensible defaults."""
    return BilateralRecord(
        reporter=reporter,
        partner=partner,
        value=value,
        year=year,
        source=source,
        axis=axis,
        **kwargs,
    )


def make_dataset(
    reporter: str = "JP",
    axis: str = "financial",
    source: str = "test",
    n_partners: int = 25,
    year: int = 2024,
    include_majors: bool = True,
) -> BilateralDataset:
    """Create a BilateralDataset with N synthetic partners."""
    ds = BilateralDataset(
        reporter=reporter,
        axis=axis,
        source=source,
        year_range=(year, year),
    )

    # Major partners first (for missing_key_partners check)
    major_partners = ["US", "CN", "DE", "GB", "FR", "IN"]
    if include_majors:
        for p in major_partners[:min(n_partners, len(major_partners))]:
            if p == reporter:
                continue
            ds.add_record(make_record(
                reporter=reporter, partner=p, value=100.0,
                year=year, source=source, axis=axis,
            ))

    # Fill remaining with synthetic partners
    alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    used = {reporter} | set(major_partners)
    count = len(ds.records)
    for i in range(26):
        if count >= n_partners:
            break
        # Generate 2-letter codes that aren't already used
        code = f"{alpha[i % 26]}{alpha[(i + 7) % 26]}"
        if code in used or len(code) != 2:
            continue
        used.add(code)
        ds.add_record(make_record(
            reporter=reporter, partner=code, value=50.0 + i,
            year=year, source=source, axis=axis,
        ))
        count += 1

    ds.compute_metadata()
    return ds


# ===========================================================================
# SCHEMA TESTS
# ===========================================================================

class TestBilateralRecord:
    """Tests for BilateralRecord dataclass."""

    def test_valid_construction(self):
        r = make_record()
        assert r.reporter == "JP"
        assert r.partner == "US"
        assert r.value == 100.0
        assert r.year == 2024
        assert r.source == "test"
        assert r.axis == "financial"

    def test_frozen(self):
        r = make_record()
        with pytest.raises(AttributeError):
            r.value = 200.0  # type: ignore

    def test_invalid_reporter(self):
        with pytest.raises(ValueError, match="Invalid reporter"):
            BilateralRecord(
                reporter="", partner="US", value=100.0,
                year=2024, source="test", axis="fin",
            )

    def test_invalid_partner(self):
        with pytest.raises(ValueError, match="Invalid partner"):
            BilateralRecord(
                reporter="JP", partner="X", value=100.0,
                year=2024, source="test", axis="fin",
            )

    def test_negative_value(self):
        with pytest.raises(ValueError, match="Negative value"):
            make_record(value=-1.0)

    def test_year_out_of_range(self):
        with pytest.raises(ValueError, match="Year out of range"):
            make_record(year=1800)
        with pytest.raises(ValueError, match="Year out of range"):
            make_record(year=2050)

    def test_empty_source(self):
        with pytest.raises(ValueError, match="Source must not be empty"):
            make_record(source="")

    def test_empty_axis(self):
        with pytest.raises(ValueError, match="Axis must not be empty"):
            make_record(axis="")

    def test_zero_value_allowed(self):
        """Zero value should be allowed (validation handles zero rejection)."""
        r = make_record(value=0.0)
        assert r.value == 0.0

    def test_to_dict(self):
        r = make_record()
        d = r.to_dict()
        assert d["reporter"] == "JP"
        assert d["partner"] == "US"
        assert d["value"] == 100.0
        assert isinstance(d, dict)


class TestBilateralDataset:
    """Tests for BilateralDataset."""

    def test_empty_dataset(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        assert len(ds.records) == 0
        ds.compute_metadata()
        assert ds.n_partners == 0
        assert ds.total_value == 0.0

    def test_add_record(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        ds.add_record(make_record())
        assert len(ds.records) == 1

    def test_add_record_reporter_mismatch(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        with pytest.raises(ValueError, match="does not match"):
            ds.add_record(make_record(reporter="US"))

    def test_add_record_axis_mismatch(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        with pytest.raises(ValueError, match="does not match"):
            ds.add_record(make_record(axis="energy"))

    def test_compute_metadata(self):
        ds = make_dataset(n_partners=10)
        assert ds.n_partners >= 5
        assert ds.total_value > 0
        assert len(ds.partners) == ds.n_partners

    def test_deterministic_hash(self):
        ds1 = make_dataset(n_partners=5)
        ds2 = make_dataset(n_partners=5)
        assert ds1.data_hash == ds2.data_hash

    def test_csv_export(self):
        ds = make_dataset(n_partners=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.csv"
            ds.to_csv(path)
            assert path.exists()
            with open(path) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == len(ds.records)
            assert "reporter" in rows[0]
            assert "partner" in rows[0]
            assert "value" in rows[0]

    def test_metadata_json_export(self):
        ds = make_dataset(n_partners=5)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "meta.json"
            ds.to_metadata_json(path)
            assert path.exists()
            with open(path) as f:
                meta = json.load(f)
            assert meta["reporter"] == "JP"
            assert meta["n_partners"] == ds.n_partners
            assert "data_hash" in meta


class TestIngestionManifest:
    """Tests for IngestionManifest."""

    def test_record_ingestion(self):
        m = IngestionManifest(
            run_id="test_001",
            start_time="2024-01-01T00:00:00Z",
        )
        m.record_ingestion("JP", "financial", "bis_lbs", 100, "OK")
        assert len(m.datasets_ingested) == 1
        assert m.datasets_ingested[0]["reporter"] == "JP"

    def test_finalize(self):
        m = IngestionManifest(
            run_id="test_001",
            start_time="2024-01-01T00:00:00Z",
        )
        m.finalize()
        assert m.status == "COMPLETED"
        assert m.end_time != ""


# ===========================================================================
# NORMALIZATION TESTS
# ===========================================================================

class TestCountryCodeNormalization:
    """Tests for normalize_country_code."""

    def test_iso3_to_iso2(self):
        assert normalize_country_code("JPN") == "JP"
        assert normalize_country_code("USA") == "US"
        assert normalize_country_code("DEU") == "DE"
        assert normalize_country_code("GBR") == "GB"

    def test_already_iso2(self):
        assert normalize_country_code("JP") == "JP"
        assert normalize_country_code("us") == "US"

    def test_bis_aggregate_rejected(self):
        assert normalize_country_code("5J", source="bis_lbs") is None
        assert normalize_country_code("5A", source="bis_lbs") is None

    def test_empty_rejected(self):
        assert normalize_country_code("") is None
        assert normalize_country_code("   ") is None

    def test_sipri_mapping(self):
        assert normalize_country_code("Japan", source="sipri") == "JP"
        assert normalize_country_code("United States", source="sipri") == "US"
        assert normalize_country_code("South Korea", source="sipri") == "KR"

    def test_sipri_unknown_rejected(self):
        assert normalize_country_code("Unknown recipient(s)", source="sipri") is None

    def test_unmapped_code_tracked(self):
        audit = NormalizationAudit()
        result = normalize_country_code("ZZZZZ", audit=audit)
        assert result is None
        assert "ZZZZZ" in audit.unmapped_codes

    def test_aggregate_iso2_rejected(self):
        assert normalize_country_code("XX") is None
        assert normalize_country_code("XZ") is None


class TestAggregatePartnerDetection:
    """Tests for is_aggregate_partner."""

    def test_world_rejected(self):
        assert is_aggregate_partner("World") is True
        assert is_aggregate_partner("WORLD") is True

    def test_total_rejected(self):
        assert is_aggregate_partner("Total") is True

    def test_other_rejected(self):
        assert is_aggregate_partner("Other") is True

    def test_country_accepted(self):
        assert is_aggregate_partner("US") is False
        assert is_aggregate_partner("JP") is False

    def test_areas_nes_rejected(self):
        assert is_aggregate_partner("Areas, nes") is True

    def test_rest_of_world_rejected(self):
        assert is_aggregate_partner("Rest of world") is True


class TestNormalizeRecords:
    """Tests for normalize_records pipeline."""

    def test_basic_normalization(self):
        records = [
            make_record(reporter="JP", partner="US", value=100.0),
            make_record(reporter="JP", partner="CN", value=200.0),
        ]
        normalized, audit = normalize_records(records, source="test", axis="financial")
        assert len(normalized) == 2
        assert audit.records_input == 2
        assert audit.records_output == 2

    def test_self_trade_removal(self):
        records = [
            make_record(reporter="JP", partner="JP", value=100.0),
            make_record(reporter="JP", partner="US", value=200.0),
        ]
        normalized, audit = normalize_records(records, source="test", axis="financial")
        assert len(normalized) == 1
        assert audit.self_trades_removed == 1

    def test_zero_value_removal(self):
        records = [
            make_record(reporter="JP", partner="US", value=0.0),
            make_record(reporter="JP", partner="CN", value=100.0),
        ]
        normalized, audit = normalize_records(records, source="test", axis="financial")
        assert len(normalized) == 1
        assert audit.zero_values_removed == 1

    def test_duplicate_aggregation(self):
        records = [
            make_record(reporter="JP", partner="US", value=100.0),
            make_record(reporter="JP", partner="US", value=50.0),
        ]
        normalized, audit = normalize_records(records, source="test", axis="financial")
        assert len(normalized) == 1
        assert normalized[0].value == 150.0
        assert audit.duplicates_aggregated == 1

    def test_reporter_filter(self):
        records = [
            make_record(reporter="JP", partner="US", value=100.0),
            make_record(reporter="US", partner="CN", value=200.0),
        ]
        normalized, audit = normalize_records(
            records, source="test", axis="financial", reporter_filter="JP",
        )
        assert len(normalized) == 1
        assert normalized[0].reporter == "JP"


class TestHSCategoryMapping:
    """Tests for map_hs_to_category."""

    def test_energy_coal(self):
        assert map_hs_to_category("2701", "energy") == "coal"

    def test_energy_crude(self):
        assert map_hs_to_category("2709", "energy") == "crude_oil"

    def test_energy_lng(self):
        assert map_hs_to_category("271111", "energy") == "lng"

    def test_tech_semiconductor(self):
        assert map_hs_to_category("8541", "technology") == "semiconductor_devices"

    def test_tech_ic(self):
        assert map_hs_to_category("8542", "technology") == "integrated_circuits"

    def test_critical_lithium(self):
        assert map_hs_to_category("2825", "critical_inputs") == "lithium_compounds"

    def test_unknown_axis(self):
        assert map_hs_to_category("2701", "defense") is None

    def test_unknown_hs_code(self):
        assert map_hs_to_category("9999", "energy") is None


# ===========================================================================
# VALIDATION TESTS
# ===========================================================================

class TestPartnerCount:
    """Tests for check_partner_count."""

    def test_sufficient_partners(self):
        ds = make_dataset(n_partners=25)
        result = check_partner_count(ds)
        assert result.status == "PASS"

    def test_insufficient_partners_warning(self):
        ds = make_dataset(n_partners=5)
        result = check_partner_count(ds)
        # For major reporter JP, needs >= 20, but 5 triggers warning/fail
        assert result.status in ("FAIL", "WARNING")

    def test_minimum_absolute_fail(self):
        ds = make_dataset(n_partners=2, include_majors=False)
        result = check_partner_count(ds)
        assert result.status == "FAIL"


class TestAggregateDetection:
    """Tests for check_aggregate_detection."""

    def test_no_aggregates(self):
        ds = make_dataset(n_partners=10)
        result = check_aggregate_detection(ds)
        assert result.status == "PASS"

    def test_detects_aggregate_iso2(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        ds.add_record(make_record(partner="US"))
        ds.add_record(make_record(partner="XX"))  # aggregate
        ds.compute_metadata()
        result = check_aggregate_detection(ds)
        assert result.status == "FAIL"
        assert len(result.errors) > 0


class TestSumIntegrity:
    """Tests for check_sum_integrity."""

    def test_positive_sum(self):
        ds = make_dataset(n_partners=5)
        result = check_sum_integrity(ds)
        assert result.status == "PASS"

    def test_zero_sum_fails(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        ds.add_record(make_record(value=0.0))
        ds.compute_metadata()
        result = check_sum_integrity(ds)
        assert result.status == "FAIL"


class TestDominance:
    """Tests for check_dominance."""

    def test_no_dominance(self):
        ds = make_dataset(n_partners=10)
        result = check_dominance(ds)
        assert result.status == "PASS"

    def test_single_partner_dominance(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        ds.add_record(make_record(partner="US", value=9600.0))
        ds.add_record(make_record(partner="CN", value=100.0))
        ds.add_record(make_record(partner="DE", value=100.0))
        ds.add_record(make_record(partner="GB", value=100.0))
        ds.add_record(make_record(partner="FR", value=100.0))
        ds.compute_metadata()
        result = check_dominance(ds)
        assert result.status == "WARNING"


class TestMissingKeyPartners:
    """Tests for check_missing_key_partners."""

    def test_majors_present(self):
        ds = make_dataset(n_partners=25, include_majors=True)
        result = check_missing_key_partners(ds)
        assert result.status == "PASS"

    def test_majors_missing(self):
        ds = make_dataset(n_partners=10, include_majors=False)
        result = check_missing_key_partners(ds)
        assert result.status in ("FAIL", "WARNING")


class TestSchemaCompliance:
    """Tests for check_schema_compliance."""

    def test_valid_schema(self):
        ds = make_dataset(n_partners=5)
        result = check_schema_compliance(ds)
        assert result.status == "PASS"


class TestSelfTrade:
    """Tests for check_self_trade."""

    def test_no_self_trade(self):
        ds = make_dataset(n_partners=5)
        result = check_self_trade(ds)
        assert result.status == "PASS"

    def test_detects_self_trade(self):
        ds = BilateralDataset(
            reporter="JP", axis="financial", source="test",
            year_range=(2024, 2024),
        )
        ds.add_record(make_record(reporter="JP", partner="JP"))
        ds.compute_metadata()
        result = check_self_trade(ds)
        assert result.status == "FAIL"


class TestDuplicateRecords:
    """Tests for check_duplicate_records."""

    def test_no_duplicates(self):
        ds = make_dataset(n_partners=5)
        result = check_duplicate_records(ds)
        assert result.status == "PASS"


class TestYearCoverage:
    """Tests for check_year_coverage."""

    def test_valid_years(self):
        ds = make_dataset(n_partners=5, year=2024)
        result = check_year_coverage(ds)
        assert result.status == "PASS"


class TestValidateDataset:
    """Tests for validate_dataset orchestrator."""

    def test_valid_dataset_passes(self):
        ds = make_dataset(n_partners=25, include_majors=True)
        results = validate_dataset(ds)
        assert ds.validation_status in ("PASS", "WARNING")
        assert len(results) >= 5  # at least the core checks

    def test_report_generation(self):
        ds = make_dataset(n_partners=25, include_majors=True)
        report = validate_and_report(ds)
        assert "overall_status" in report
        assert "checks" in report
        assert len(report["checks"]) > 0


# ===========================================================================
# CONFIG TESTS
# ===========================================================================

class TestConfig:
    """Tests for pipeline configuration."""

    def test_iso3_to_iso2_complete(self):
        """All EU-27 ISO-3 codes must map to valid ISO-2."""
        eu27_iso3 = [
            "AUT", "BEL", "BGR", "CYP", "CZE", "DEU", "DNK", "EST",
            "GRC", "ESP", "FIN", "FRA", "HRV", "HUN", "IRL", "ITA",
            "LTU", "LUX", "LVA", "MLT", "NLD", "POL", "PRT", "ROU",
            "SWE", "SVN", "SVK",
        ]
        for iso3 in eu27_iso3:
            assert iso3 in ISO3_TO_ISO2, f"Missing ISO-3→ISO-2 mapping: {iso3}"
            iso2 = ISO3_TO_ISO2[iso3]
            assert len(iso2) == 2, f"Invalid ISO-2 for {iso3}: {iso2}"

    def test_phase1_countries_mapped(self):
        phase1 = ["AUS", "CHN", "GBR", "JPN", "KOR", "NOR", "USA"]
        for iso3 in phase1:
            assert iso3 in ISO3_TO_ISO2, f"Missing Phase 1 mapping: {iso3}"

    def test_sipri_mapping_coverage(self):
        """Key SIPRI country names must be mapped."""
        required = [
            "United States", "China", "Russia", "France",
            "Germany", "United Kingdom", "Japan",
        ]
        for name in required:
            assert name in SIPRI_TO_ISO2, f"Missing SIPRI mapping: {name}"

    def test_axis_registry_complete(self):
        assert len(AXIS_REGISTRY) == 6
        for axis_id in range(1, 7):
            assert axis_id in AXIS_REGISTRY
            assert "slug" in AXIS_REGISTRY[axis_id]
            assert "sources" in AXIS_REGISTRY[axis_id]

    def test_all_isi_countries_nonempty(self):
        assert len(ALL_ISI_COUNTRIES) >= 34  # EU-27 + 7 Phase 1


# ===========================================================================
# INGESTION MODULE STRUCTURAL TESTS
# ===========================================================================

class TestBISLBSIngestion:
    """Structural tests for BIS LBS ingestion module."""

    def test_import(self):
        from pipeline.ingest.bis_lbs import ingest_bis_lbs
        assert callable(ingest_bis_lbs)

    def test_file_not_found(self):
        from pipeline.ingest.bis_lbs import ingest_bis_lbs
        result, stats = ingest_bis_lbs("JP", raw_path=Path("/nonexistent/file.csv"))
        assert result is None
        assert stats["status"] == "FILE_NOT_FOUND"

    def test_synthetic_bis_csv(self):
        """Test BIS ingestion with a synthetic CSV file."""
        from pipeline.ingest.bis_lbs import ingest_bis_lbs

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bis_test.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "FREQ", "L_MEASURE", "L_POSITION", "L_INSTR", "L_DENOM",
                    "L_CURR_TYPE", "L_CP_SECTOR", "L_REP_CTY", "L_CP_COUNTRY",
                    "TIME_PERIOD", "OBS_VALUE",
                ])
                # JP is counterparty (debtor), US is reporter (creditor)
                writer.writerow(["Q", "S", "C", "A", "TO1", "A", "A", "US", "JP", "2024-Q4", "1500.5"])
                writer.writerow(["Q", "S", "C", "A", "TO1", "A", "A", "GB", "JP", "2024-Q4", "800.3"])
                writer.writerow(["Q", "S", "C", "A", "TO1", "A", "A", "DE", "JP", "2024-Q4", "600.1"])
                # Self-pair (should be excluded)
                writer.writerow(["Q", "S", "C", "A", "TO1", "A", "A", "JP", "JP", "2024-Q4", "999.0"])
                # Different counterparty (not JP)
                writer.writerow(["Q", "S", "C", "A", "TO1", "A", "A", "US", "DE", "2024-Q4", "400.0"])

            result, stats = ingest_bis_lbs("JP", raw_path=csv_path)
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "JP"
            assert len(result.records) == 3
            assert result.n_partners == 3
            # Check partners are creditor countries
            partner_set = {r.partner for r in result.records}
            assert "US" in partner_set
            assert "GB" in partner_set
            assert "DE" in partner_set
            # JP should NOT be a partner (self-pair excluded)
            assert "JP" not in partner_set

    def test_malformed_csv_missing_columns(self):
        """CSV with wrong columns should return MALFORMED_FILE."""
        from pipeline.ingest.bis_lbs import ingest_bis_lbs

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bis_bad.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["col_a", "col_b", "col_c"])
                writer.writerow(["1", "2", "3"])
            result, stats = ingest_bis_lbs("JP", raw_path=csv_path)
            assert result is None
            assert stats["status"] == "MALFORMED_FILE"

    def test_empty_csv_header_only(self):
        """CSV with only headers but no data should return NO_DATA."""
        from pipeline.ingest.bis_lbs import ingest_bis_lbs

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bis_empty.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "FREQ", "L_MEASURE", "L_POSITION", "L_INSTR", "L_DENOM",
                    "L_CURR_TYPE", "L_CP_SECTOR", "L_REP_CTY", "L_CP_COUNTRY",
                    "TIME_PERIOD", "OBS_VALUE",
                ])
            result, stats = ingest_bis_lbs("JP", raw_path=csv_path)
            assert result is None
            assert stats["status"] == "NO_DATA"


class TestIMFCPISIngestion:
    """Structural tests for IMF CPIS ingestion module."""

    def test_import(self):
        from pipeline.ingest.imf_cpis import ingest_imf_cpis
        assert callable(ingest_imf_cpis)

    def test_file_not_found(self):
        from pipeline.ingest.imf_cpis import ingest_imf_cpis
        result, stats = ingest_imf_cpis("JP", raw_path=Path("/nonexistent/file.csv"))
        assert result is None
        assert stats["status"] == "FILE_NOT_FOUND"

    def test_synthetic_cpis_csv(self):
        """Test CPIS ingestion with a synthetic wide-format CSV."""
        from pipeline.ingest.imf_cpis import ingest_imf_cpis

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "cpis_test.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "DATASET", "SERIES_CODE", "OBS_MEASURE", "COUNTRY",
                    "ACCOUNTING_ENTRY", "INDICATOR", "SECTOR",
                    "COUNTERPART_SECTOR", "COUNTERPART_COUNTRY",
                    "FREQUENCY", "SCALE", "SERIES_NAME", "2024",
                ])
                # JP → US
                writer.writerow([
                    "IMF.STA:PIP(4.0.0)", "JPN.A.P_F_P_USD.S1.S1.USA.S",
                    "OBS_VALUE", "Japan", "Assets",
                    "Portfolio investment, Total", "Total economy",
                    "Total economy", "United States",
                    "Annual", "Millions", "test", "5000.0",
                ])
                # JP → GB
                writer.writerow([
                    "IMF.STA:PIP(4.0.0)", "JPN.A.P_F_P_USD.S1.S1.GBR.S",
                    "OBS_VALUE", "Japan", "Assets",
                    "Portfolio investment, Total", "Total economy",
                    "Total economy", "United Kingdom",
                    "Annual", "Millions", "test", "3000.0",
                ])
                # JP → DE
                writer.writerow([
                    "IMF.STA:PIP(4.0.0)", "JPN.A.P_F_P_USD.S1.S1.DEU.S",
                    "OBS_VALUE", "Japan", "Assets",
                    "Portfolio investment, Total", "Total economy",
                    "Total economy", "Germany",
                    "Annual", "Millions", "test", "2000.0",
                ])
                # Not Assets (should be excluded)
                writer.writerow([
                    "IMF.STA:PIP(4.0.0)", "JPN.A.P_F_P_USD.S1.S1.FRA.S",
                    "OBS_VALUE", "Japan", "Liabilities",
                    "Portfolio investment, Total", "Total economy",
                    "Total economy", "France",
                    "Annual", "Millions", "test", "1000.0",
                ])

            result, stats = ingest_imf_cpis("JP", raw_path=csv_path, target_year=2024)
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "JP"
            assert len(result.records) == 3
            partner_set = {r.partner for r in result.records}
            assert "US" in partner_set
            assert "GB" in partner_set
            assert "DE" in partner_set


class TestComtradeIngestion:
    """Structural tests for Comtrade ingestion module."""

    def test_import(self):
        from pipeline.ingest.comtrade import ingest_comtrade
        assert callable(ingest_comtrade)

    def test_file_not_found(self):
        from pipeline.ingest.comtrade import ingest_comtrade
        result, stats = ingest_comtrade(
            "JP", axis="energy", raw_path=Path("/nonexistent/file.csv"),
            use_api=False,
        )
        assert result is None
        assert stats["status"] == "FILE_NOT_FOUND"

    def test_synthetic_comtrade_csv(self):
        """Test Comtrade ingestion with synthetic CSV."""
        from pipeline.ingest.comtrade import ingest_comtrade

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "comtrade_test.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Classification", "Year", "Period", "PeriodDesc",
                    "AggLevel", "IsLeaf", "ReporterCode", "ReporterISO",
                    "ReporterDesc", "PartnerCode", "PartnerISO",
                    "PartnerDesc", "FlowCode", "FlowDesc",
                    "CmdCode", "CmdDesc", "QtyUnitCode", "QtyUnitAbbr",
                    "Qty", "AltQtyUnitCode", "AltQtyUnitAbbr", "AltQty",
                    "NetWgt", "GrossWgt", "Cifvalue", "Fobvalue",
                    "PrimaryValue", "LegacyEstimation", "IsReported",
                ])
                # JP imports energy from Saudi Arabia
                writer.writerow([
                    "H6", "2023", "2023", "2023", "6", "1",
                    "392", "JPN", "Japan",
                    "682", "SAU", "Saudi Arabia",
                    "M", "Imports", "270900", "Crude oil",
                    "", "", "", "", "", "", "", "",
                    "50000000", "48000000", "50000000", "", "",
                ])
                # JP imports energy from Australia
                writer.writerow([
                    "H6", "2023", "2023", "2023", "6", "1",
                    "392", "JPN", "Japan",
                    "36", "AUS", "Australia",
                    "M", "Imports", "270112", "Coal",
                    "", "", "", "", "", "", "", "",
                    "30000000", "28000000", "30000000", "", "",
                ])
                # Export (should be excluded)
                writer.writerow([
                    "H6", "2023", "2023", "2023", "6", "1",
                    "392", "JPN", "Japan",
                    "840", "USA", "United States",
                    "X", "Exports", "270900", "Crude oil",
                    "", "", "", "", "", "", "", "",
                    "10000000", "9000000", "10000000", "", "",
                ])

            result, stats = ingest_comtrade(
                "JP", axis="energy", raw_path=csv_path,
                year_range=(2022, 2024),
            )
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "JP"
            assert len(result.records) == 2
            partner_set = {r.partner for r in result.records}
            assert "SA" in partner_set
            assert "AU" in partner_set


class TestSIPRIIngestion:
    """Structural tests for SIPRI ingestion module."""

    def test_import(self):
        from pipeline.ingest.sipri import ingest_sipri
        assert callable(ingest_sipri)

    def test_file_not_found(self):
        """An EU reporter with a missing file should get FILE_NOT_FOUND."""
        from pipeline.ingest.sipri import ingest_sipri
        result, stats = ingest_sipri("DE", raw_path=Path("/nonexistent/file.csv"))
        assert result is None
        assert stats["status"] == "FILE_NOT_FOUND"

    def test_non_eu_countries_produce_data(self):
        """Non-EU countries now produce real data with global SIPRI register."""
        from pipeline.ingest.sipri import ingest_sipri
        result, stats = ingest_sipri("JP")
        assert result is not None, "JP should have real SIPRI data from global register"
        assert stats["status"] == "OK"

    def test_synthetic_sipri_csv(self):
        """Test SIPRI ingestion with synthetic CSV."""
        from pipeline.ingest.sipri import ingest_sipri

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sipri_test.csv"
            with open(csv_path, "w", encoding="latin-1", newline="") as f:
                # Write 11 metadata lines
                for i in range(11):
                    f.write(f"Metadata line {i+1}\n")
                # Write header
                writer = csv.writer(f)
                writer.writerow([
                    "Recipient", "Supplier", "Year of order", "",
                    "Number ordered", "", "Weapon designation",
                    "Weapon description", "Number delivered", "",
                    "Year(s) of delivery", "status", "Comments",
                    "SIPRI TIV per unit", "SIPRI TIV for total order",
                    "SIPRI TIV of delivered weapons",
                ])
                # Japan receives from US
                writer.writerow([
                    "Japan", "United States", "2020", "",
                    "10", "", "F-35A", "combat aircraft", "4", "",
                    "2022; 2023", "New", "test",
                    "80", "800", "320",
                ])
                # Japan receives from UK
                writer.writerow([
                    "Japan", "United Kingdom", "2021", "",
                    "5", "", "Rolls Royce", "aero-engine", "3", "",
                    "2023", "New", "test",
                    "10", "50", "30",
                ])

            result, stats = ingest_sipri(
                "JP", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "JP"
            assert result.n_partners >= 2
            partner_set = {r.partner for r in result.records}
            assert "US" in partner_set
            assert "GB" in partner_set


class TestLogisticsIngestion:
    """Structural tests for logistics ingestion module."""

    def test_import(self):
        from pipeline.ingest.logistics import ingest_logistics
        assert callable(ingest_logistics)

    def test_structural_limitation_noneu(self):
        """Non-EU countries get STRUCTURAL_LIMITATION (not an error)."""
        from pipeline.ingest.logistics import ingest_logistics
        result, stats = ingest_logistics("JP")
        assert result is None
        assert stats["status"] == "STRUCTURAL_LIMITATION"
        assert "limitation_reason" in stats


# ===========================================================================
# ORCHESTRATOR TESTS
# ===========================================================================

class TestOrchestrator:
    """Tests for the pipeline orchestrator."""

    def test_import(self):
        from pipeline.orchestrator import run_pipeline
        assert callable(run_pipeline)

    def test_ensure_directories(self):
        from pipeline.orchestrator import ensure_directories
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override paths
            import pipeline.config as cfg
            orig_staging = cfg.STAGING_DIR
            orig_validated = cfg.VALIDATED_DIR
            orig_meta = cfg.META_DIR
            orig_audit = cfg.AUDIT_DIR

            try:
                cfg.STAGING_DIR = Path(tmpdir) / "staging"
                cfg.VALIDATED_DIR = Path(tmpdir) / "validated"
                cfg.META_DIR = Path(tmpdir) / "meta"
                cfg.AUDIT_DIR = Path(tmpdir) / "audit"

                # Re-import to pick up changes
                import pipeline.orchestrator as orch
                orch.STAGING_DIR = cfg.STAGING_DIR
                orch.VALIDATED_DIR = cfg.VALIDATED_DIR
                orch.META_DIR = cfg.META_DIR
                orch.AUDIT_DIR = cfg.AUDIT_DIR

                dirs = orch.ensure_directories("JP")
                assert len(dirs) > 0
                for path in dirs.values():
                    assert path.is_dir()
            finally:
                cfg.STAGING_DIR = orig_staging
                cfg.VALIDATED_DIR = orig_validated
                cfg.META_DIR = orig_meta
                cfg.AUDIT_DIR = orig_audit


# ===========================================================================
# NEW VALIDATION CHECKS — ECONOMIC SANITY + COVERAGE + AGGREGATE MASS
# ===========================================================================

class TestEconomicSanityValidation:
    """Tests for CHECK 10: Economic sanity validation."""

    def _make_dataset(self, source, axis="financial", n_partners=20, total_per=1000.0,
                      partners=None):
        from pipeline.schema import BilateralRecord, BilateralDataset
        ds = BilateralDataset(reporter="JP", axis=axis, source=source,
                              year_range=(2023, 2023))
        if partners is None:
            partners = [f"{chr(65+i)}{chr(65+j)}" for i in range(n_partners)
                        for j in range(1) if i < n_partners]
            # Ensure US, CN, DE, GB, FR are in the partner list for major economy tests
            partners = ["US", "CN", "DE", "GB", "FR"] + [
                p for p in partners if p not in {"US", "CN", "DE", "GB", "FR"}
            ]
            partners = partners[:n_partners]
        for p in partners:
            ds.add_record(BilateralRecord(
                reporter="JP", partner=p, value=total_per,
                year=2023, source=source, axis=axis,
            ))
        ds.compute_metadata()
        return ds

    def test_pass_for_normal_dataset(self):
        from pipeline.validate import check_economic_sanity
        ds = self._make_dataset("un_comtrade", axis="energy", total_per=500_000)
        result = check_economic_sanity(ds)
        assert result.status == "PASS"

    def test_fail_for_implausible_total(self):
        from pipeline.validate import check_economic_sanity
        ds = self._make_dataset("un_comtrade", axis="energy", total_per=10)
        # total = 10 * 20 = 200, below min of 1_000_000
        result = check_economic_sanity(ds)
        assert result.status == "FAIL"
        assert "IMPLAUSIBLE_TOTAL" in result.errors[0]

    def test_fail_missing_all_expected_partners(self):
        from pipeline.validate import check_economic_sanity
        ds = self._make_dataset("un_comtrade", axis="energy", total_per=500_000,
                                partners=["SA", "AE", "QA", "KW", "IQ", "RU",
                                          "NG", "AO", "MY", "ID", "AU", "NO",
                                          "CA", "BR", "MX", "TH", "VN", "IN",
                                          "PH", "SG"])
        # No US, CN, DE in partners
        result = check_economic_sanity(ds)
        assert result.status == "FAIL"
        assert "MISSING_EXPECTED_PARTNERS" in result.errors[0]

    def test_warn_missing_some_expected(self):
        from pipeline.validate import check_economic_sanity
        # US present but CN and DE missing
        ds = self._make_dataset("un_comtrade", axis="energy", total_per=500_000,
                                partners=["US", "SA", "AE", "QA", "KW", "IQ",
                                          "RU", "NG", "AO", "MY", "ID", "AU",
                                          "NO", "CA", "BR", "TH", "VN", "IN",
                                          "PH", "SG"])
        result = check_economic_sanity(ds)
        assert result.status == "WARNING"

    def test_sipri_low_total_ok(self):
        from pipeline.validate import check_economic_sanity
        ds = self._make_dataset("sipri", axis="defense", total_per=1.0,
                                n_partners=3)
        # total = 3.0, above min of 0.1
        result = check_economic_sanity(ds)
        assert result.status in ("PASS", "WARNING")


class TestCoverageRatioValidation:
    """Tests for CHECK 11: Coverage ratio validation."""

    def test_pass_normal_distribution(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_coverage_ratio
        ds = BilateralDataset(reporter="JP", axis="energy", source="un_comtrade",
                              year_range=(2023, 2023))
        # 20 partners with declining values
        for i in range(20):
            ds.add_record(BilateralRecord(
                reporter="JP", partner=f"{chr(65+i//26)}{chr(65+i%26)}",
                value=1000.0 / (i + 1), year=2023, source="un_comtrade",
                axis="energy",
            ))
        ds.compute_metadata()
        result = check_coverage_ratio(ds)
        assert result.status == "PASS"

    def test_warn_fragmented_distribution(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_coverage_ratio
        ds = BilateralDataset(reporter="JP", axis="energy", source="un_comtrade",
                              year_range=(2023, 2023))
        # 100 partners all with equal tiny values → top-10 = 10%
        for i in range(100):
            ds.add_record(BilateralRecord(
                reporter="JP", partner=f"{chr(65+i//26)}{chr(65+i%26)}",
                value=100.0, year=2023, source="un_comtrade", axis="energy",
            ))
        ds.compute_metadata()
        result = check_coverage_ratio(ds)
        assert result.status == "WARNING"
        assert "LOW-COVERAGE" in result.warnings[0]

    def test_warn_truncated_distribution(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_coverage_ratio
        ds = BilateralDataset(reporter="JP", axis="energy", source="un_comtrade",
                              year_range=(2023, 2023))
        # Only 5 partners → top-10 = 100%
        for i in range(5):
            code = f"{chr(65+i)}A"
            ds.add_record(BilateralRecord(
                reporter="JP", partner=code, value=1000.0,
                year=2023, source="un_comtrade", axis="energy",
            ))
        ds.compute_metadata()
        result = check_coverage_ratio(ds)
        assert result.status == "WARNING"
        assert "TRUNCATED" in result.warnings[0]


class TestAggregateDetectionMassTracking:
    """Tests for CHECK 3 with mass tracking (TASK 6)."""

    def test_no_aggregates_pass(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_aggregate_detection
        ds = BilateralDataset(reporter="JP", axis="financial", source="bis_lbs",
                              year_range=(2024, 2024))
        ds.add_record(BilateralRecord(
            reporter="JP", partner="US", value=1000.0, year=2024,
            source="bis_lbs", axis="financial",
        ))
        ds.compute_metadata()
        result = check_aggregate_detection(ds)
        assert result.status == "PASS"

    def test_aggregate_detected_and_mass_tracked(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_aggregate_detection
        ds = BilateralDataset(reporter="JP", axis="financial", source="bis_lbs",
                              year_range=(2024, 2024))
        # Good partner
        ds.add_record(BilateralRecord(
            reporter="JP", partner="US", value=1000.0, year=2024,
            source="bis_lbs", axis="financial",
        ))
        # Aggregate partner (World)
        ds.add_record(BilateralRecord(
            reporter="JP", partner="World", value=500.0, year=2024,
            source="bis_lbs", axis="financial",
        ))
        ds.compute_metadata()
        result = check_aggregate_detection(ds)
        assert result.status == "FAIL"
        assert "aggregate_share" in result.details


class TestSourceAwarePartnerCount:
    """Tests for CHECK 5 with source-aware thresholds (TASK 2)."""

    def test_bis_override_threshold(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_partner_count
        ds = BilateralDataset(reporter="JP", axis="financial", source="bis_lbs",
                              year_range=(2024, 2024))
        # 20 partners — below generic threshold (20) but above BIS override (15)
        for i in range(20):
            ds.add_record(BilateralRecord(
                reporter="JP", partner=f"{chr(65+i)}X",
                value=100.0, year=2024, source="bis_lbs", axis="financial",
            ))
        ds.compute_metadata()
        result = check_partner_count(ds)
        assert result.status == "PASS"
        assert result.details.get("threshold_type") == "source_override"

    def test_bis_below_override_fails(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_partner_count
        ds = BilateralDataset(reporter="JP", axis="financial", source="bis_lbs",
                              year_range=(2024, 2024))
        # Only 10 partners — below BIS override (15)
        for i in range(10):
            ds.add_record(BilateralRecord(
                reporter="JP", partner=f"{chr(65+i)}X",
                value=100.0, year=2024, source="bis_lbs", axis="financial",
            ))
        ds.compute_metadata()
        result = check_partner_count(ds)
        assert result.status == "FAIL"

    def test_generic_threshold_for_comtrade(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_partner_count
        ds = BilateralDataset(reporter="JP", axis="energy", source="un_comtrade",
                              year_range=(2023, 2023))
        # 25 partners — above major threshold (20)
        for i in range(25):
            ds.add_record(BilateralRecord(
                reporter="JP", partner=f"{chr(65+i//26)}{chr(65+i%26)}",
                value=100.0, year=2023, source="un_comtrade", axis="energy",
            ))
        ds.compute_metadata()
        result = check_partner_count(ds)
        assert result.status == "PASS"
        assert result.details.get("threshold_type") == "major_economy"


class TestComtradeApiStrategy:
    """Tests for Comtrade API fallback strategy."""

    def test_local_csv_preferred(self):
        """When a local CSV exists, it should be used."""
        from pipeline.ingest.comtrade import ingest_comtrade
        import tempfile, csv
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Classification", "Year", "Period", "PeriodDesc",
                    "AggLevel", "IsLeaf", "ReporterCode", "ReporterISO",
                    "ReporterDesc", "PartnerCode", "PartnerISO",
                    "PartnerDesc", "FlowCode", "FlowDesc",
                    "CmdCode", "CmdDesc", "QtyUnitCode", "QtyUnitAbbr",
                    "Qty", "AltQtyUnitCode", "AltQtyUnitAbbr", "AltQty",
                    "NetWgt", "GrossWgt", "Cifvalue", "Fobvalue",
                    "PrimaryValue", "LegacyEstimation", "IsReported",
                ])
                writer.writerow([
                    "H6", "2023", "2023", "2023", "6", "1",
                    "392", "JPN", "Japan",
                    "682", "SAU", "Saudi Arabia",
                    "M", "Imports", "270900", "Crude oil",
                    "", "", "", "", "", "", "", "",
                    "50000000", "48000000", "50000000", "", "",
                ])
            result, stats = ingest_comtrade("JP", axis="energy", raw_path=csv_path)
            assert stats["data_method"] == "local_csv"

    def test_api_disabled_returns_file_not_found(self):
        """When API is disabled and no local file, return FILE_NOT_FOUND."""
        from pipeline.ingest.comtrade import ingest_comtrade
        result, stats = ingest_comtrade(
            "JP", axis="energy",
            raw_path=Path("/nonexistent/path.csv"),
            use_api=False,
        )
        assert result is None
        assert stats["status"] == "FILE_NOT_FOUND"

    def test_axis_validation(self):
        """Invalid axis should raise ValueError."""
        from pipeline.ingest.comtrade import ingest_comtrade
        import pytest
        with pytest.raises(ValueError, match="Unsupported axis"):
            ingest_comtrade("JP", axis="nonexistent", use_api=False)


class TestLogisticsEUGuard:
    """Tests for logistics EU-only coverage guard."""

    def test_eu_country_proceeds(self):
        """EU countries should proceed to Eurostat ingestion."""
        from pipeline.ingest.logistics import ingest_logistics
        result, stats = ingest_logistics("DE")
        # DE should either have data or NO_DATA, but NOT STRUCTURAL_LIMITATION
        assert stats["status"] != "STRUCTURAL_LIMITATION"

    def test_non_eu_gets_structural_limitation(self):
        from pipeline.ingest.logistics import ingest_logistics
        for country in ["JP", "US", "CN", "AU", "GB", "KR", "NO"]:
            result, stats = ingest_logistics(country)
            assert result is None
            assert stats["status"] == "STRUCTURAL_LIMITATION", f"Failed for {country}"

    def test_structural_limitation_has_reason(self):
        from pipeline.ingest.logistics import ingest_logistics
        _, stats = ingest_logistics("JP")
        assert "limitation_reason" in stats
        assert "EU-27" in stats["limitation_reason"]


class TestSIPRICoverageGuard:
    """Tests for SIPRI recipient coverage guard."""

    def test_eu_country_proceeds(self):
        """EU countries should proceed to SIPRI file parsing."""
        from pipeline.ingest.sipri import ingest_sipri
        # DE is in EU and in the SIPRI file
        result, stats = ingest_sipri("DE")
        # Should either get data or NO_DATA, not a limitation status
        assert stats["status"] not in ("STRUCTURAL_LIMITATION", "IMPLEMENTATION_LIMITATION")

    def test_non_eu_no_implementation_limitation(self):
        """Non-EU countries must NOT get IMPLEMENTATION_LIMITATION with global data."""
        from pipeline.ingest.sipri import ingest_sipri
        for country in ["JP", "AU", "KR"]:
            result, stats = ingest_sipri(country)
            assert stats["status"] != "IMPLEMENTATION_LIMITATION", (
                f"{country}: should not get IMPLEMENTATION_LIMITATION with global data"
            )
            assert result is not None, f"{country}: should produce data from global register"

    def test_custom_path_bypasses_guard(self):
        """Explicit raw_path should bypass the coverage guard."""
        from pipeline.ingest.sipri import ingest_sipri
        # JP with custom path should NOT get STRUCTURAL_LIMITATION
        # (it should get FILE_NOT_FOUND instead)
        result, stats = ingest_sipri("JP", raw_path=Path("/nonexistent/file.csv"))
        assert stats["status"] == "FILE_NOT_FOUND"


class TestValidateAllChecksCount:
    """Verify the validation engine has exactly the expected number of checks."""

    def test_all_checks_count(self):
        from pipeline.validate import ALL_CHECKS
        assert len(ALL_CHECKS) == 13  # 9 original + 3 new + output_plausibility

    def test_all_checks_callable(self):
        from pipeline.validate import ALL_CHECKS
        for check in ALL_CHECKS:
            assert callable(check)


# ===========================================================================
# TASK 12 — PIPELINE CONSISTENCY GUARANTEE
# ===========================================================================

class TestPipelineConsistencyGuarantee:
    """Architectural invariant tests that prevent regression.

    These tests enforce that:
    1. All pipeline modules use canonical status enums
    2. All axes are registered and have ingestion functions
    3. Country code mappings are self-consistent
    4. No stale string literals leak into status fields
    """

    def test_all_axes_have_ingestion_functions(self):
        """Every axis in AXIS_REGISTRY must have a mapping in the orchestrator."""
        from pipeline.config import AXIS_REGISTRY
        from pipeline.orchestrator import AXIS_INGEST_MAP
        for axis_id in AXIS_REGISTRY:
            assert axis_id in AXIS_INGEST_MAP, (
                f"Axis {axis_id} ({AXIS_REGISTRY[axis_id]['slug']}) is registered "
                f"but has no ingestion function in orchestrator.AXIS_INGEST_MAP"
            )
            assert len(AXIS_INGEST_MAP[axis_id]) > 0, (
                f"Axis {axis_id} has empty source list in AXIS_INGEST_MAP"
            )

    def test_all_ingestion_functions_callable(self):
        """Every function in AXIS_INGEST_MAP must be callable."""
        from pipeline.orchestrator import AXIS_INGEST_MAP
        for axis_id, sources in AXIS_INGEST_MAP.items():
            for source_name, fn in sources:
                assert callable(fn), (
                    f"Axis {axis_id}, source '{source_name}': "
                    f"ingestion function is not callable: {fn}"
                )

    def test_status_enums_are_str_subclass(self):
        """Status enums must be (str, Enum) so == comparison with strings works."""
        from pipeline.status import IngestionStatus, ValidationStatus, AxisStatus
        for enum_cls in (IngestionStatus, ValidationStatus, AxisStatus):
            assert issubclass(enum_cls, str), (
                f"{enum_cls.__name__} must be a str subclass for safe comparison"
            )
            for member in enum_cls:
                assert isinstance(member, str), (
                    f"{enum_cls.__name__}.{member.name} is not a str instance"
                )
                assert member == member.value, (
                    f"{enum_cls.__name__}.{member.name}: "
                    f"enum value '{member.value}' != str(member) '{str(member)}'"
                )

    def test_acceptable_statuses_complete(self):
        """ACCEPTABLE_STATUSES must contain all non-failure axis statuses."""
        from pipeline.status import AxisStatus, ACCEPTABLE_STATUSES
        # Must include
        assert AxisStatus.PASS in ACCEPTABLE_STATUSES
        assert AxisStatus.WARNING in ACCEPTABLE_STATUSES
        assert AxisStatus.STRUCTURAL_LIMITATION in ACCEPTABLE_STATUSES
        assert AxisStatus.IMPLEMENTATION_LIMITATION in ACCEPTABLE_STATUSES
        # Must NOT include
        assert AxisStatus.FAILED not in ACCEPTABLE_STATUSES

    def test_no_string_status_literals_in_pipeline_modules(self):
        """Scan pipeline/*.py for raw status string assignments.

        This catches regressions where someone writes status = "OK"
        instead of status = IngestionStatus.OK.
        """
        import re
        pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
        # Patterns that indicate raw string status assignment
        # We look for: ["status"] = "SOME_STATUS" or status = "SOME_STATUS"
        # but NOT inside docstrings, comments, or test assertions
        forbidden_statuses = {
            "OK", "NO_DATA", "FILE_NOT_FOUND", "API_FAILED",
            "STRUCTURAL_LIMITATION", "IMPLEMENTATION_LIMITATION",
            "MALFORMED_FILE", "EXCEPTION", "NO_BILATERAL_DATA", "PENDING",
        }
        pattern = re.compile(
            r'\["status"\]\s*=\s*"(' + "|".join(forbidden_statuses) + r')"'
        )

        violations: list[str] = []
        for py_file in sorted(pipeline_dir.rglob("*.py")):
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.lstrip()
                # Skip comments and docstrings
                if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'"):
                    continue
                if pattern.search(line):
                    rel = py_file.relative_to(pipeline_dir)
                    violations.append(f"{rel}:{i}: {line.strip()}")

        assert not violations, (
            f"Found raw string status literals in pipeline code "
            f"(use IngestionStatus.X instead):\n" +
            "\n".join(violations)
        )

    def test_eu27_iso2_uses_gr_not_el(self):
        """Pipeline must use ISO-standard 'GR' for Greece, not Eurostat 'EL'."""
        from pipeline.config import EU27_ISO2, ISO3_TO_ISO2
        assert "GR" in EU27_ISO2, "Greece must be 'GR' in EU27_ISO2"
        assert "EL" not in EU27_ISO2, "Eurostat 'EL' must NOT be in EU27_ISO2"
        assert ISO3_TO_ISO2.get("GRC") == "GR", "GRC must map to GR"

    def test_eurostat_adapter_exists(self):
        """EUROSTAT_TO_ISO2 adapter must exist for EL→GR conversion."""
        from pipeline.config import EUROSTAT_TO_ISO2
        assert EUROSTAT_TO_ISO2["EL"] == "GR"
        assert EUROSTAT_TO_ISO2["UK"] == "GB"

    def test_all_isi_countries_have_iso2(self):
        """Every country in ALL_ISI_COUNTRIES must be a valid 2-char code."""
        from pipeline.config import ALL_ISI_COUNTRIES
        for code in ALL_ISI_COUNTRIES:
            assert len(code) == 2 and code.isalpha() and code.isupper(), (
                f"Invalid ISI country code: '{code}'"
            )

    def test_ingestion_modules_import_status_enum(self):
        """All ingestion modules must import from pipeline.status."""
        pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline" / "ingest"
        for py_file in sorted(pipeline_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text(encoding="utf-8")
            assert "from pipeline.status import" in content, (
                f"{py_file.name} does not import from pipeline.status"
            )

    def test_axis_registry_has_required_fields(self):
        """Every axis in AXIS_REGISTRY must have slug, name, and sources."""
        from pipeline.config import AXIS_REGISTRY
        for axis_id, info in AXIS_REGISTRY.items():
            assert "slug" in info, f"Axis {axis_id} missing 'slug'"
            assert "sources" in info, f"Axis {axis_id} missing 'sources'"
            assert isinstance(info["slug"], str), f"Axis {axis_id} slug not str"
            assert isinstance(info["sources"], (list, tuple)), (
                f"Axis {axis_id} sources not list/tuple"
            )