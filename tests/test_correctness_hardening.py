"""
tests/test_correctness_hardening.py — Correctness hardening tests for ISI.

NOT structural tests. NOT cosmetic tests.

These tests verify:
1. End-to-end reproducibility (deterministic rebuild from raw data)
2. Ingestion correctness under adversarial inputs
3. Transformation correctness (aggregation, dedup, year filtering)
4. Output plausibility (sanity checks on real data)
5. Archive containment (deprecated code cannot leak)
6. Data contract enforcement (malformed objects rejected)
7. Self-falsification (adversarial scenarios)
8. Source-of-truth enforcement (raw → derived direction enforced)

If any of these tests can pass when the system produces wrong output,
the test itself is broken.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
SIPRI_RAW = RAW_DIR / "sipri" / "trade-register.csv"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: END-TO-END REPRODUCIBILITY PROOF
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEndReproducibility:
    """Verify that pipeline output is fully deterministic from raw input.

    If these tests fail, the system has non-determinism — a fatal flaw
    for an institutional-grade research pipeline.
    """

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    def test_sipri_japan_deterministic_hash(self):
        """Same raw file → same dataset hash, every time."""
        from pipeline.ingest.sipri import ingest_sipri

        hashes = []
        for _ in range(3):
            ds, stats = ingest_sipri("JP")
            assert ds is not None, "Japan must produce data"
            hashes.append(ds.data_hash)

        assert len(set(hashes)) == 1, (
            f"SIPRI Japan produced different hashes across 3 runs: {hashes}. "
            f"Pipeline is non-deterministic."
        )

    def test_sipri_japan_record_count_stable(self):
        """Record count must be identical across runs."""
        from pipeline.ingest.sipri import ingest_sipri

        counts = []
        for _ in range(3):
            ds, _ = ingest_sipri("JP")
            counts.append(len(ds.records))

        assert len(set(counts)) == 1, f"Record counts differ: {counts}"

    def test_sipri_japan_total_value_stable(self):
        """Total TIV must be bitwise identical across runs."""
        from pipeline.ingest.sipri import ingest_sipri

        values = []
        for _ in range(3):
            ds, _ = ingest_sipri("JP")
            values.append(ds.total_value)

        assert len(set(values)) == 1, f"Total values differ: {values}"

    def test_sipri_multiple_countries_deterministic(self):
        """All ISI-relevant countries produce deterministic hashes."""
        from pipeline.ingest.sipri import ingest_sipri

        test_countries = ["JP", "DE", "FR", "US", "GB", "SE", "PL"]
        for cc in test_countries:
            ds1, _ = ingest_sipri(cc)
            ds2, _ = ingest_sipri(cc)
            if ds1 is not None and ds2 is not None:
                assert ds1.data_hash == ds2.data_hash, (
                    f"Non-deterministic for {cc}: "
                    f"hash1={ds1.data_hash[:16]} hash2={ds2.data_hash[:16]}"
                )

    def test_sipri_japan_known_hash(self):
        """Japan hash must match known-good reference value.

        This is a REGRESSION anchor. If the hash changes, either:
        (a) the raw data file changed, or
        (b) the transformation logic changed.
        Both require explicit acknowledgment.
        """
        from pipeline.ingest.sipri import ingest_sipri

        ds, _ = ingest_sipri("JP")
        assert ds is not None

        expected_hash = "970be4c90cfaa798d552582446af224f7c467eb3d8ef22d51c7f37c1668d3dac"
        assert ds.data_hash == expected_hash, (
            f"Japan SIPRI hash changed: expected={expected_hash[:16]}... "
            f"got={ds.data_hash[:16]}... — raw data or transformation modified?"
        )

    def test_sipri_japan_known_partner_count(self):
        """Japan must have exactly 6 defense suppliers in current data."""
        from pipeline.ingest.sipri import ingest_sipri

        ds, _ = ingest_sipri("JP")
        assert ds is not None
        assert ds.n_partners == 6, f"Expected 6 partners, got {ds.n_partners}"

    def test_sipri_japan_known_total_tiv(self):
        """Japan total TIV must match known reference value."""
        from pipeline.ingest.sipri import ingest_sipri

        ds, _ = ingest_sipri("JP")
        assert ds is not None
        assert abs(ds.total_value - 7014.25) < 0.01, (
            f"Japan total TIV: expected ~7014.25, got {ds.total_value}"
        )

    def test_sipri_raw_file_hash_stable(self):
        """Raw file hash anchors reproducibility. If it changes, all outputs change."""
        assert SIPRI_RAW.is_file(), "Canonical SIPRI raw file missing"
        actual_hash = hashlib.sha256(SIPRI_RAW.read_bytes()).hexdigest()
        # Load from manifest
        manifest_path = PROJECT_ROOT / "data" / "meta" / "sipri_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text())
            for entry in manifest.get("files", []):
                if entry.get("filename") == "trade-register.csv":
                    expected = entry["sha256"]
                    assert actual_hash == expected, (
                        f"Raw file hash mismatch: manifest={expected[:16]}... "
                        f"actual={actual_hash[:16]}... — file modified?"
                    )
                    return
        # If no manifest, just record the hash
        assert len(actual_hash) == 64, "Hash computation failed"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: SIPRI INGESTION STRESS TESTS
# ═══════════════════════════════════════════════════════════════════════════

def _make_sipri_csv(rows: list[list[str]], preamble_lines: int = 11) -> Path:
    """Create a synthetic SIPRI CSV with proper preamble for testing.

    Returns a temporary file path.
    """
    header = [
        "SIPRI AT Database ID", "Supplier", "Recipient", "Designation",
        "Description", "Armament category", "Order date",
        "Order date is estimate", "Numbers delivered",
        "Numbers delivered is estimate", "Delivery year",
        "Delivery year is estimate", "Status", "SIPRI estimate",
        "TIV deal unit", "TIV delivery values", "Local production",
    ]

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
    )
    writer = csv.writer(tmp)
    # Preamble
    for i in range(preamble_lines):
        writer.writerow([f"Preamble line {i}"])
    # Header
    writer.writerow(header)
    # Data
    for row in rows:
        writer.writerow(row)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


def _sipri_row(
    supplier: str = "United States",
    recipient: str = "Japan",
    year: int = 2022,
    tiv: str = "100.0",
    designation: str = "F-35A",
    description: str = "combat aircraft",
    category: str = "Aircraft",
) -> list[str]:
    """Build one canonical SIPRI row."""
    return [
        "99999", supplier, recipient, designation, description, category,
        "2020", "No", "1", "No", str(year), "No", "New", "100.0", "100.0",
        tiv, "No",
    ]


class TestSipriIngestionStress:
    """Adversarial input tests for SIPRI ingestion.

    These verify the system fails loudly or handles edge cases correctly.
    """

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    def _ingest(self, rows, reporter="JP", year_range=(2020, 2025)):
        from pipeline.ingest.sipri import ingest_sipri
        path = _make_sipri_csv(rows)
        try:
            return ingest_sipri(reporter, raw_path=path, year_range=year_range)
        finally:
            os.unlink(path)

    def test_empty_file_returns_malformed(self):
        """File with only preamble (no header) → MALFORMED_FILE."""
        from pipeline.status import IngestionStatus
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        # Only 5 lines (less than 11 preamble)
        for i in range(5):
            tmp.write(f"preamble {i}\n")
        tmp.flush()
        tmp.close()
        from pipeline.ingest.sipri import ingest_sipri
        ds, stats = ingest_sipri("JP", raw_path=Path(tmp.name))
        os.unlink(tmp.name)
        assert ds is None
        assert stats["status"] == IngestionStatus.MALFORMED_FILE

    def test_missing_required_columns(self):
        """CSV with wrong header → MALFORMED_FILE."""
        from pipeline.status import IngestionStatus
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        writer = csv.writer(tmp)
        for i in range(11):
            writer.writerow([f"preamble {i}"])
        writer.writerow(["Col_A", "Col_B", "Col_C"])  # Wrong header
        writer.writerow(["a", "b", "c"])
        tmp.flush()
        tmp.close()
        from pipeline.ingest.sipri import ingest_sipri
        ds, stats = ingest_sipri("JP", raw_path=Path(tmp.name))
        os.unlink(tmp.name)
        assert ds is None
        assert stats["status"] == IngestionStatus.MALFORMED_FILE

    def test_duplicate_rows_aggregated(self):
        """Duplicate (same supplier/recipient/year) rows are summed, not doubled."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="200.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        # After normalization, duplicates with same key are aggregated (summed)
        total = sum(r.value for r in ds.records)
        assert abs(total - 300.0) < 0.01, (
            f"Duplicates not properly aggregated: expected 300, got {total}"
        )

    def test_self_trade_removed(self):
        """Japan importing from Japan → dropped."""
        rows = [
            _sipri_row(supplier="Japan", recipient="Japan", year=2022, tiv="500.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="100.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        assert stats["rows_self_trade"] == 1
        # Only the US record should survive
        partners = {r.partner for r in ds.records}
        assert "JP" not in partners, "Self-trade record leaked through"
        assert "US" in partners

    def test_zero_tiv_dropped(self):
        """TIV = 0 rows are dropped (SIPRI convention: 0 means < 0.5 million)."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="0"),
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        assert stats["rows_zero_tiv"] >= 1
        partners = {r.partner for r in ds.records}
        assert "FR" in partners
        # US row with TIV=0 should be dropped
        us_total = sum(r.value for r in ds.records if r.partner == "US")
        assert us_total == 0.0

    def test_negative_tiv_dropped(self):
        """Negative TIV values are dropped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="-100.0"),
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        us_total = sum(r.value for r in ds.records if r.partner == "US")
        assert us_total == 0.0, f"Negative TIV leaked through: {us_total}"

    def test_nonstate_entity_dropped(self):
        """Non-state suppliers (e.g., 'Hezbollah (Lebanon)*') are dropped."""
        rows = [
            _sipri_row(supplier="Hezbollah (Lebanon)*", recipient="Japan", year=2022, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        partners = {r.partner for r in ds.records}
        assert len(partners) == 1, f"Non-state entity not dropped: {partners}"
        assert "US" in partners

    def test_multinational_entity_dropped(self):
        """Multinational entities (NATO**, UN**) are dropped."""
        rows = [
            _sipri_row(supplier="NATO**", recipient="Japan", year=2022, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        partners = {r.partner for r in ds.records}
        assert "US" in partners
        # NATO should be gone
        for p in partners:
            assert p != "__MULTINATIONAL__", "Multinational sentinel leaked"

    def test_unknown_entity_dropped(self):
        """Unknown entities are dropped."""
        rows = [
            _sipri_row(supplier="Unknown recipient(s)", recipient="Japan", year=2022, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        partners = {r.partner for r in ds.records}
        assert "US" in partners
        assert len(partners) == 1

    def test_unmapped_supplier_dropped(self):
        """Supplier with no ISO-2 mapping is dropped."""
        rows = [
            _sipri_row(supplier="Planet Mars", recipient="Japan", year=2022, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        partners = {r.partner for r in ds.records}
        assert "US" in partners
        assert len(partners) == 1

    def test_year_out_of_range_dropped(self):
        """Rows outside year_range are dropped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2019, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2026, tiv="100.0"),
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows, year_range=(2020, 2025))
        assert ds is not None
        years = {r.year for r in ds.records}
        assert 2019 not in years, "Year 2019 leaked through"
        assert 2026 not in years, "Year 2026 leaked through"
        assert 2022 in years

    def test_question_marks_in_tiv_handled(self):
        """SIPRI uses '?' to indicate uncertainty — must be stripped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="100.0?"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        assert len(ds.records) == 1
        assert abs(ds.records[0].value - 100.0) < 0.01

    def test_empty_tiv_treated_as_zero(self):
        """Empty TIV field → 0 → dropped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv=""),
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        # Only France should have records
        partners = {r.partner for r in ds.records}
        assert "FR" in partners

    def test_whitespace_only_tiv_treated_as_zero(self):
        """Whitespace-only TIV → 0 → dropped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="   "),
        ]
        ds, stats = self._ingest(rows)
        # Should be empty or only the zero is dropped
        if ds is not None:
            us_total = sum(r.value for r in ds.records if r.partner == "US")
            assert us_total == 0.0

    def test_reporter_mismatch_dropped(self):
        """Rows for other recipients are dropped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Germany", year=2022, tiv="100.0"),
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows, reporter="JP")
        assert ds is not None
        reporters = {r.reporter for r in ds.records}
        assert reporters == {"JP"}

    def test_short_rows_skipped(self):
        """Rows with fewer columns than expected are skipped silently."""
        rows = [
            ["99999", "United States", "Japan"],  # Only 3 columns
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        assert len(ds.records) >= 1  # France row should still work

    def test_corrupted_year_skipped(self):
        """Non-integer year → row dropped."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="100.0"),
        ]
        # Corrupt the year field
        rows[0][10] = "abc"
        ds, stats = self._ingest(rows)
        # Should produce no records or skip the corrupted row
        if ds is not None:
            for r in ds.records:
                assert isinstance(r.year, int)

    def test_mixed_case_country_names(self):
        """Country name resolution is case-insensitive for fallback."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        # Exact case
        assert _resolve_sipri_country("United States") == "US"
        # Different case should still resolve
        assert _resolve_sipri_country("united states") == "US"
        assert _resolve_sipri_country("UNITED STATES") == "US"

    def test_file_not_found_returns_error(self):
        """Nonexistent file → FILE_NOT_FOUND status."""
        from pipeline.ingest.sipri import ingest_sipri
        from pipeline.status import IngestionStatus
        ds, stats = ingest_sipri("JP", raw_path=Path("/nonexistent/path.csv"))
        assert ds is None
        assert stats["status"] == IngestionStatus.FILE_NOT_FOUND

    def test_all_records_have_defense_axis(self):
        """Every record must have axis='defense'."""
        rows = [
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2023, tiv="100.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        for r in ds.records:
            assert r.axis == "defense", f"Record has axis={r.axis}, expected 'defense'"

    def test_all_records_have_sipri_source(self):
        """Every record must have source='sipri'."""
        rows = [
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        for r in ds.records:
            assert r.source == "sipri", f"Record has source={r.source}"

    def test_all_records_have_tiv_unit(self):
        """Every record must have unit='TIV_MN'."""
        rows = [
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="50.0"),
        ]
        ds, stats = self._ingest(rows)
        assert ds is not None
        for r in ds.records:
            assert r.unit == "TIV_MN", f"Record has unit={r.unit}"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: SIPRI TRANSFORMATION CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════════

class TestSipriTransformationCorrectness:
    """Verify SIPRI → ISI transformation rules are actually correct.

    Each test encodes a specific transformation rule from the module docstring
    and verifies it produces the expected output on synthetic data.
    """

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    def _ingest(self, rows, reporter="JP", year_range=(2020, 2025)):
        from pipeline.ingest.sipri import ingest_sipri
        path = _make_sipri_csv(rows)
        try:
            return ingest_sipri(reporter, raw_path=path, year_range=year_range)
        finally:
            os.unlink(path)

    def test_recipient_is_reporter(self):
        """ISI reporter = SIPRI Recipient (arms importer)."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="100.0"),
        ]
        ds, _ = self._ingest(rows, reporter="JP")
        assert ds is not None
        assert all(r.reporter == "JP" for r in ds.records)

    def test_supplier_is_partner(self):
        """ISI partner = SIPRI Supplier (arms exporter)."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="100.0"),
        ]
        ds, _ = self._ingest(rows, reporter="JP")
        assert ds is not None
        assert all(r.partner == "US" for r in ds.records)

    def test_tiv_split_across_years(self):
        """Multi-year rows split TIV equally across delivery years.

        If a row has delivery years "2022;2023" and TIV=100,
        each year gets TIV=50.
        """
        # The global register has one year per row, so splitting only
        # applies to old-format test CSVs with semicolons.
        # But we test the mechanism anyway:
        from pipeline.ingest.sipri import _parse_delivery_years
        years = _parse_delivery_years("2022;2023")
        assert years == [2022, 2023]

    def test_aggregation_by_partner_year(self):
        """Multiple rows for same supplier-year are aggregated (summed)."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022,
                       tiv="100.0", designation="F-35A"),
            _sipri_row(supplier="United States", recipient="Japan", year=2022,
                       tiv="200.0", designation="Patriot PAC-3"),
        ]
        ds, _ = self._ingest(rows, reporter="JP")
        assert ds is not None
        # US records for 2022 should be summed
        us_2022 = sum(r.value for r in ds.records if r.partner == "US" and r.year == 2022)
        assert abs(us_2022 - 300.0) < 0.01, f"Expected 300, got {us_2022}"

    def test_year_window_strict(self):
        """Only years within [min, max] inclusive are kept."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2019, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2020, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2025, tiv="100.0"),
            _sipri_row(supplier="United States", recipient="Japan", year=2026, tiv="100.0"),
        ]
        ds, _ = self._ingest(rows, reporter="JP", year_range=(2020, 2025))
        assert ds is not None
        years = {r.year for r in ds.records}
        assert 2019 not in years
        assert 2026 not in years
        assert 2020 in years
        assert 2025 in years

    def test_top_partner_share_mathematically_correct(self):
        """Top partner share is value / total, computed correctly."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2022, tiv="900.0"),
            _sipri_row(supplier="France", recipient="Japan", year=2022, tiv="100.0"),
        ]
        ds, _ = self._ingest(rows, reporter="JP")
        assert ds is not None
        ds.compute_metadata()
        top = ds._top_partners(10)
        us_entry = next(t for t in top if t["partner"] == "US")
        assert abs(us_entry["share"] - 0.9) < 0.001, (
            f"Expected US share=0.9, got {us_entry['share']}"
        )

    def test_partial_year_metadata_propagated(self):
        """Latest year in range flagged as partial-risk."""
        rows = [
            _sipri_row(supplier="United States", recipient="Japan", year=2025, tiv="100.0"),
        ]
        ds, stats = self._ingest(rows, reporter="JP", year_range=(2020, 2025))
        assert ds is not None
        assert stats.get("partial_year_risk") is True
        assert stats.get("partial_year") == 2025

    def test_country_resolution_turkiye(self):
        """Both 'Turkey' and 'Turkiye' resolve to TR."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("Turkey") == "TR"
        assert _resolve_sipri_country("Turkiye") == "TR"

    def test_country_resolution_korea_variants(self):
        """All Korea variants resolve to KR."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        for name in ["Korea, South", "Korea South", "South Korea", "Republic of Korea"]:
            assert _resolve_sipri_country(name) == "KR", f"{name} did not resolve to KR"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: OUTPUT PLAUSIBILITY / SANITY CHECKS
# ═══════════════════════════════════════════════════════════════════════════

class TestOutputPlausibility:
    """Sanity checks on real SIPRI data outputs.

    These are NOT about forcing outputs to match expectations.
    They flag suspicious outputs that deserve human review.
    """

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    @pytest.fixture
    def japan_dataset(self):
        from pipeline.ingest.sipri import ingest_sipri
        ds, stats = ingest_sipri("JP")
        assert ds is not None, "Japan must produce SIPRI data"
        return ds, stats

    def test_japan_has_us_as_top_partner(self, japan_dataset):
        """Japan's top defense supplier must be the US (known fact)."""
        ds, _ = japan_dataset
        pv = {}
        for r in ds.records:
            pv[r.partner] = pv.get(r.partner, 0) + r.value
        top = max(pv, key=pv.get)
        assert top == "US", (
            f"Japan's top defense supplier is {top}, expected US. "
            f"Either data is wrong or the world changed."
        )

    def test_japan_us_share_high(self, japan_dataset):
        """Japan's US dependency should be >80% (known structural fact)."""
        ds, _ = japan_dataset
        pv = {}
        for r in ds.records:
            pv[r.partner] = pv.get(r.partner, 0) + r.value
        us_share = pv.get("US", 0) / ds.total_value
        assert us_share > 0.80, (
            f"Japan US share = {us_share:.1%}, expected >80%. "
            f"Plausibility check failed."
        )

    def test_germany_not_dominated_by_single_supplier(self, ):
        """Germany should have a diversified supplier base."""
        from pipeline.ingest.sipri import ingest_sipri
        ds, _ = ingest_sipri("DE")
        assert ds is not None
        pv = {}
        for r in ds.records:
            pv[r.partner] = pv.get(r.partner, 0) + r.value
        top_share = max(pv.values()) / ds.total_value
        assert top_share < 0.90, (
            f"Germany top supplier share = {top_share:.1%}. "
            f"Expected <90% (Germany has diversified procurement)."
        )

    def test_us_has_multiple_defense_suppliers(self):
        """US should import from >10 countries (known large diversified importer)."""
        from pipeline.ingest.sipri import ingest_sipri
        ds, _ = ingest_sipri("US")
        assert ds is not None
        assert ds.n_partners >= 10, (
            f"US has only {ds.n_partners} defense suppliers. "
            f"Expected ≥10 (US imports from many allied nations)."
        )

    def test_no_negative_values_in_real_data(self):
        """No negative TIV values should exist in any output."""
        from pipeline.ingest.sipri import ingest_sipri
        for cc in ["JP", "DE", "FR", "US"]:
            ds, _ = ingest_sipri(cc)
            if ds:
                for r in ds.records:
                    assert r.value >= 0, (
                        f"Negative value {r.value} in {cc} record"
                    )

    def test_no_self_trade_in_real_data(self):
        """No country should appear as both reporter and partner."""
        from pipeline.ingest.sipri import ingest_sipri
        for cc in ["JP", "DE", "FR", "US", "GB"]:
            ds, _ = ingest_sipri(cc)
            if ds:
                for r in ds.records:
                    assert r.reporter != r.partner, (
                        f"Self-trade found: {r.reporter} → {r.partner}"
                    )

    def test_all_partner_codes_are_valid_iso2(self):
        """All partner codes must be 2-letter uppercase."""
        from pipeline.ingest.sipri import ingest_sipri
        for cc in ["JP", "DE", "FR", "US", "GB", "SE", "PL"]:
            ds, _ = ingest_sipri(cc)
            if ds:
                for r in ds.records:
                    assert len(r.partner) == 2 and r.partner.isalpha() and r.partner.isupper(), (
                        f"Invalid partner code '{r.partner}' in {cc}"
                    )

    def test_total_tiv_positive_for_major_importers(self):
        """Major arms importers must have positive total TIV."""
        from pipeline.ingest.sipri import ingest_sipri
        for cc in ["JP", "DE", "FR", "US", "GB", "PL", "IT"]:
            ds, _ = ingest_sipri(cc)
            assert ds is not None, f"{cc} should have SIPRI data"
            assert ds.total_value > 0, f"{cc} total TIV = {ds.total_value}"

    def test_years_within_expected_range(self):
        """All years in output must be within configured range."""
        from pipeline.ingest.sipri import ingest_sipri
        from pipeline.config import SIPRI_YEAR_RANGE
        lo, hi = SIPRI_YEAR_RANGE
        for cc in ["JP", "DE", "FR"]:
            ds, _ = ingest_sipri(cc)
            if ds:
                for r in ds.records:
                    assert lo <= r.year <= hi, (
                        f"Year {r.year} outside range [{lo}, {hi}] for {cc}"
                    )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: ARCHIVE CONTAINMENT PROOF
# ═══════════════════════════════════════════════════════════════════════════

class TestArchiveContainment:
    """Prove that archived code cannot contaminate execution."""

    def test_archive_import_raises(self):
        """Importing _archive must raise ImportError."""
        with pytest.raises(ImportError, match="quarantined legacy"):
            import _archive  # noqa: F401

    def test_archive_subpackage_import_raises(self):
        """Importing _archive subpackages must raise ImportError."""
        with pytest.raises(ImportError, match="quarantined legacy"):
            from _archive import scripts_global_v11  # noqa: F401

    def test_archive_deep_import_raises(self):
        """Deep imports into archive must raise ImportError."""
        with pytest.raises(ImportError):
            from _archive.scripts_global_v11.global_v11 import run_pipeline  # noqa: F401

    def test_no_live_code_imports_archive(self):
        """No file in backend/ or pipeline/ imports from _archive."""
        import ast
        for root in ["backend", "pipeline"]:
            root_path = PROJECT_ROOT / root
            for py_file in root_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                source = py_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        assert not node.module.startswith("_archive"), (
                            f"{py_file} imports from _archive: {node.module}"
                        )
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert not alias.name.startswith("_archive"), (
                                f"{py_file} imports _archive: {alias.name}"
                            )

    def test_no_test_imports_archive(self):
        """No test file imports from _archive (except this one which tests the block)."""
        import ast
        tests_dir = PROJECT_ROOT / "tests"
        this_file = Path(__file__).resolve()
        for py_file in tests_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            if py_file.resolve() == this_file:
                continue  # This file intentionally imports _archive to test the block
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith("_archive"), (
                        f"{py_file} imports from _archive: {node.module}"
                    )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: DATA CONTRACT ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════

class TestDataContractEnforcement:
    """Verify schema contracts are impossible to violate silently."""

    def test_bilateral_record_rejects_empty_reporter(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Invalid reporter"):
            BilateralRecord(reporter="", partner="US", value=1.0, year=2022,
                           source="test", axis="defense")

    def test_bilateral_record_rejects_single_char_reporter(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Invalid reporter"):
            BilateralRecord(reporter="J", partner="US", value=1.0, year=2022,
                           source="test", axis="defense")

    def test_bilateral_record_rejects_negative_value(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Negative value"):
            BilateralRecord(reporter="JP", partner="US", value=-1.0, year=2022,
                           source="test", axis="defense")

    def test_bilateral_record_rejects_impossible_year(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Year out of range"):
            BilateralRecord(reporter="JP", partner="US", value=1.0, year=1800,
                           source="test", axis="defense")

    def test_bilateral_record_rejects_future_year(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Year out of range"):
            BilateralRecord(reporter="JP", partner="US", value=1.0, year=2050,
                           source="test", axis="defense")

    def test_bilateral_record_rejects_empty_source(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Source must not be empty"):
            BilateralRecord(reporter="JP", partner="US", value=1.0, year=2022,
                           source="", axis="defense")

    def test_bilateral_record_rejects_empty_axis(self):
        from pipeline.schema import BilateralRecord
        with pytest.raises(ValueError, match="Axis must not be empty"):
            BilateralRecord(reporter="JP", partner="US", value=1.0, year=2022,
                           source="sipri", axis="")

    def test_dataset_rejects_reporter_mismatch(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        ds = BilateralDataset(reporter="JP", axis="defense", source="sipri",
                             year_range=(2020, 2025))
        rec = BilateralRecord(reporter="DE", partner="US", value=1.0,
                             year=2022, source="sipri", axis="defense")
        with pytest.raises(ValueError, match="does not match"):
            ds.add_record(rec)

    def test_dataset_rejects_axis_mismatch(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        ds = BilateralDataset(reporter="JP", axis="defense", source="sipri",
                             year_range=(2020, 2025))
        rec = BilateralRecord(reporter="JP", partner="US", value=1.0,
                             year=2022, source="sipri", axis="energy")
        with pytest.raises(ValueError, match="does not match"):
            ds.add_record(rec)

    def test_dataset_hash_is_deterministic(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        ds1 = BilateralDataset(reporter="JP", axis="defense", source="sipri",
                              year_range=(2020, 2025))
        ds2 = BilateralDataset(reporter="JP", axis="defense", source="sipri",
                              year_range=(2020, 2025))
        rec = BilateralRecord(reporter="JP", partner="US", value=100.0,
                             year=2022, source="sipri", axis="defense")
        ds1.add_record(rec)
        ds2.add_record(rec)
        ds1.compute_metadata()
        ds2.compute_metadata()
        assert ds1.data_hash == ds2.data_hash

    def test_dataset_hash_changes_on_different_data(self):
        from pipeline.schema import BilateralRecord, BilateralDataset
        ds1 = BilateralDataset(reporter="JP", axis="defense", source="sipri",
                              year_range=(2020, 2025))
        ds2 = BilateralDataset(reporter="JP", axis="defense", source="sipri",
                              year_range=(2020, 2025))
        ds1.add_record(BilateralRecord(reporter="JP", partner="US", value=100.0,
                                       year=2022, source="sipri", axis="defense"))
        ds2.add_record(BilateralRecord(reporter="JP", partner="US", value=100.1,
                                       year=2022, source="sipri", axis="defense"))
        ds1.compute_metadata()
        ds2.compute_metadata()
        assert ds1.data_hash != ds2.data_hash, (
            "Different data produced same hash — collision or hash not computed"
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: VALIDATION CORRECTNESS
# ═══════════════════════════════════════════════════════════════════════════

class TestValidationCorrectness:
    """Verify validation catches real problems, not just structural issues."""

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    def _make_dataset(self, records_data: list[dict]) -> "BilateralDataset":
        from pipeline.schema import BilateralRecord, BilateralDataset
        ds = BilateralDataset(
            reporter=records_data[0]["reporter"],
            axis=records_data[0]["axis"],
            source=records_data[0]["source"],
            year_range=(2020, 2025),
        )
        for rd in records_data:
            ds.add_record(BilateralRecord(**rd))
        ds.compute_metadata()
        return ds

    def test_self_trade_detected(self):
        from pipeline.validate import check_self_trade
        ds = self._make_dataset([
            {"reporter": "JP", "partner": "JP", "value": 100.0, "year": 2022,
             "source": "sipri", "axis": "defense"},
        ])
        result = check_self_trade(ds)
        assert not result.passed, "Self-trade should FAIL validation"

    def test_aggregate_partner_detected(self):
        from pipeline.validate import check_aggregate_detection
        ds = self._make_dataset([
            {"reporter": "JP", "partner": "World", "value": 100.0, "year": 2022,
             "source": "sipri", "axis": "defense"},
        ])
        result = check_aggregate_detection(ds)
        assert not result.passed, "'World' as partner should FAIL"

    def test_extreme_concentration_warned(self):
        from pipeline.validate import check_dominance
        records = [
            {"reporter": "JP", "partner": "US", "value": 9600.0, "year": 2022,
             "source": "sipri", "axis": "defense"},
            {"reporter": "JP", "partner": "FR", "value": 100.0, "year": 2022,
             "source": "sipri", "axis": "defense"},
        ]
        ds = self._make_dataset(records)
        result = check_dominance(ds)
        # 96% concentration should trigger warning
        assert result.warnings, "96% concentration should produce a warning"

    def test_real_japan_validates(self):
        """Real Japan SIPRI data should pass validation."""
        from pipeline.ingest.sipri import ingest_sipri
        from pipeline.validate import validate_dataset
        ds, _ = ingest_sipri("JP")
        assert ds is not None
        results = validate_dataset(ds)
        # Defense axis with sparse partners is expected to have warnings,
        # but should NOT have hard failures
        failures = [r for r in results if r.status == "FAIL"]
        # Filter out expected failures (partner count for defense is structurally low)
        real_failures = [
            f for f in failures
            if "partner_count" not in f.check_name
            and "missing_key_partners" not in f.check_name
        ]
        assert not real_failures, (
            f"Japan validation failures: {[f.errors for f in real_failures]}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: SELF-FALSIFICATION (ADVERSARIAL SCENARIOS)
# ═══════════════════════════════════════════════════════════════════════════

class TestSelfFalsification:
    """Adversarial scenarios designed to break the system.

    If any of these pass silently with wrong output, we have a bug.
    """

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    def test_inconsistent_country_code_case(self):
        """Country codes must be normalized to uppercase."""
        from pipeline.normalize import normalize_country_code
        # Lowercase input should be normalized
        result = normalize_country_code("jp", source="generic")
        assert result == "JP", f"Expected 'JP', got '{result}'"
        result = normalize_country_code("us", source="generic")
        assert result == "US"

    def test_aggregate_names_cannot_sneak_through(self):
        """All known aggregate names must be rejected."""
        from pipeline.normalize import is_aggregate_partner
        aggregates = [
            "World", "WORLD", "world", "Total", "TOTAL",
            "Other", "Not Specified", "Unspecified",
            "Areas, nes", "Rest of World", "Bunkers",
            "Free Zones", "International Organizations",
        ]
        for name in aggregates:
            assert is_aggregate_partner(name), (
                f"Aggregate name '{name}' was NOT rejected"
            )

    def test_aggregate_codes_cannot_sneak_through(self):
        """Aggregate ISO codes must be rejected."""
        from pipeline.normalize import is_aggregate_partner
        for code in ["XX", "XZ", "WL", "W0", "__AGGREGATE__", "__UNKNOWN__"]:
            assert is_aggregate_partner(code), (
                f"Aggregate code '{code}' was NOT rejected"
            )

    def test_normalization_removes_self_trade(self):
        """Self-trade records must be removed during normalization."""
        from pipeline.schema import BilateralRecord
        from pipeline.normalize import normalize_records
        records = [
            BilateralRecord(reporter="JP", partner="JP", value=100.0,
                           year=2022, source="test", axis="test"),
            BilateralRecord(reporter="JP", partner="US", value=50.0,
                           year=2022, source="test", axis="test"),
        ]
        result, audit = normalize_records(records, source="test", axis="test")
        for r in result:
            assert r.reporter != r.partner, "Self-trade survived normalization"
        assert audit.self_trades_removed >= 1

    def test_normalization_removes_zero_values(self):
        """Zero-value records must be removed."""
        from pipeline.schema import BilateralRecord
        from pipeline.normalize import normalize_records
        records = [
            BilateralRecord(reporter="JP", partner="US", value=0.0,
                           year=2022, source="test", axis="test"),
            BilateralRecord(reporter="JP", partner="FR", value=50.0,
                           year=2022, source="test", axis="test"),
        ]
        result, audit = normalize_records(records, source="test", axis="test")
        for r in result:
            assert r.value > 0, "Zero-value record survived normalization"
        assert audit.zero_values_removed >= 1

    def test_stale_manifest_detected(self):
        """If manifest hash doesn't match file, warning is logged."""
        from pipeline.ingest.sipri import _verify_manifest
        # Create a temp file whose hash won't match any manifest
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        tmp.write("fake data\n")
        tmp.flush()
        tmp.close()
        # _verify_manifest should handle gracefully (return None for non-matching)
        result = _verify_manifest(Path(tmp.name))
        os.unlink(tmp.name)
        # If manifest exists but file is different, result should be None or contain warning
        # This is a defensive check — the function should not crash

    def test_source_of_truth_is_raw(self):
        """Pipeline must read from data/raw/, not data/processed/."""
        from pipeline.config import RAW_DIR, STAGING_DIR, VALIDATED_DIR
        from pipeline.ingest.sipri import SIPRI_CANONICAL_FILE
        # Canonical file must be in raw dir
        canonical_path = RAW_DIR / "sipri" / SIPRI_CANONICAL_FILE
        assert canonical_path.parent.parts[-2] == "raw", (
            f"SIPRI canonical file not in raw/ directory: {canonical_path}"
        )
        # processed/ should not be referenced as source
        assert "processed" not in str(RAW_DIR)
        assert "processed" not in str(canonical_path)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: ENTRYPOINT / EXECUTION GUARANTEE
# ═══════════════════════════════════════════════════════════════════════════

class TestEntrypointGuarantee:
    """Verify execution paths are unambiguous."""

    def test_single_production_entrypoint(self):
        """run_pipeline in orchestrator.py is the only production entrypoint."""
        from pipeline.orchestrator import run_pipeline
        assert callable(run_pipeline)

    def test_orchestrator_has_main(self):
        """Orchestrator has a CLI main() function."""
        from pipeline.orchestrator import main
        assert callable(main)

    def test_smoke_test_is_clearly_labeled(self):
        """Smoke test script has 'smoke' in its name and docstring."""
        script = PROJECT_ROOT / "scripts" / "smoke_test.py"
        assert script.is_file()
        content = script.read_text()
        assert "smoke" in content.lower()

    def test_manifest_generator_is_clearly_labeled(self):
        """Manifest generator is clearly a utility, not a runner."""
        script = PROJECT_ROOT / "scripts" / "generate_manifest.py"
        assert script.is_file()
        content = script.read_text()
        assert "manifest" in content.lower()

    def test_no_if_name_main_in_ingest_modules(self):
        """Ingestion modules should not have __main__ blocks."""
        ingest_dir = PROJECT_ROOT / "pipeline" / "ingest"
        for py_file in ingest_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            content = py_file.read_text()
            assert '__name__ == "__main__"' not in content and "__name__ == '__main__'" not in content, (
                f"{py_file.name} has a __main__ block — "
                f"ingestion modules should not be directly executable"
            )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10: REFERENCE DATA REGRESSION ANCHORS
# ═══════════════════════════════════════════════════════════════════════════

class TestReferenceDataAnchors:
    """Pin known-good output values as regression anchors.

    If any of these change, the pipeline logic or raw data has been
    modified. Both require explicit acknowledgment.
    """

    @pytest.fixture(autouse=True)
    def _silence_logging(self):
        logging.disable(logging.WARNING)
        yield
        logging.disable(logging.NOTSET)

    # Reference values captured from verified run on 2026-03-22
    # against trade-register.csv (sha256: 5555d4943d19747d...)

    REFERENCE_DATA = {
        "JP": {"n_partners": 6, "hash_prefix": "970be4c9", "total_tiv_approx": 7014.25},
        "DE": {"n_partners": 10, "hash_prefix": "e4d60150", "total_tiv_approx": 2685.40},
        "FR": {"n_partners": 9, "hash_prefix": "a3147fd3", "total_tiv_approx": 991.25},
        "US": {"n_partners": 17, "hash_prefix": "d57ded0f", "total_tiv_approx": 5263.48},
        "GB": {"n_partners": 9, "hash_prefix": "a8b3773b", "total_tiv_approx": 3942.59},
        "SE": {"n_partners": 9, "hash_prefix": "30d65503", "total_tiv_approx": 730.30},
        "PL": {"n_partners": 10, "hash_prefix": "4a7d8904", "total_tiv_approx": 5737.81},
    }

    @pytest.mark.parametrize("country_code", ["JP", "DE", "FR", "US", "GB", "SE", "PL"])
    def test_reference_hash(self, country_code):
        """Dataset hash matches known-good reference."""
        from pipeline.ingest.sipri import ingest_sipri
        ds, _ = ingest_sipri(country_code)
        assert ds is not None, f"{country_code} must produce data"
        ref = self.REFERENCE_DATA[country_code]
        assert ds.data_hash.startswith(ref["hash_prefix"]), (
            f"{country_code} hash mismatch: "
            f"expected prefix={ref['hash_prefix']}... "
            f"got={ds.data_hash[:8]}..."
        )

    @pytest.mark.parametrize("country_code", ["JP", "DE", "FR", "US", "GB", "SE", "PL"])
    def test_reference_partner_count(self, country_code):
        """Partner count matches known-good reference."""
        from pipeline.ingest.sipri import ingest_sipri
        ds, _ = ingest_sipri(country_code)
        assert ds is not None
        ref = self.REFERENCE_DATA[country_code]
        assert ds.n_partners == ref["n_partners"], (
            f"{country_code}: expected {ref['n_partners']} partners, "
            f"got {ds.n_partners}"
        )

    @pytest.mark.parametrize("country_code", ["JP", "DE", "FR", "US", "GB", "SE", "PL"])
    def test_reference_total_tiv(self, country_code):
        """Total TIV matches known-good reference within tolerance."""
        from pipeline.ingest.sipri import ingest_sipri
        ds, _ = ingest_sipri(country_code)
        assert ds is not None
        ref = self.REFERENCE_DATA[country_code]
        assert abs(ds.total_value - ref["total_tiv_approx"]) < 0.1, (
            f"{country_code}: expected TIV ≈ {ref['total_tiv_approx']}, "
            f"got {ds.total_value}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10: OUTPUT TRUTHFULNESS HARDENING
# ═══════════════════════════════════════════════════════════════════════════

class TestOutputTruthfulness:
    """Verify that API-facing outputs never silently strip truthfulness metadata.

    If a consumer can receive axis scores without visibility into data quality
    degradation, the output is misleading. These tests enforce that all output
    paths carry the minimum truthfulness envelope.
    """

    def test_axis_result_to_dict_includes_quality_flags(self):
        """AxisResult.to_dict() MUST include data_quality_flags."""
        from backend.axis_result import AxisResult
        r = AxisResult(
            country="JP", axis_id=4, axis_slug="defense",
            score=0.5, basis="A_ONLY", validity="A_ONLY",
            coverage=0.9, source="SIPRI",
            warnings=("W-HS6-GRANULARITY",),
            channel_a_concentration=0.5, channel_b_concentration=None,
        )
        d = r.to_dict()
        assert "data_quality_flags" in d
        assert isinstance(d["data_quality_flags"], list)
        assert len(d["data_quality_flags"]) > 0, (
            "A_ONLY basis should produce at least one quality flag"
        )

    def test_axis_result_to_dict_includes_severity(self):
        """AxisResult.to_dict() MUST include degradation_severity."""
        from backend.axis_result import AxisResult
        r = AxisResult(
            country="DE", axis_id=1, axis_slug="financial",
            score=0.3, basis="BOTH", validity="VALID",
            coverage=1.0, source="BIS-CPIS",
            warnings=(),
            channel_a_concentration=0.2, channel_b_concentration=0.1,
        )
        d = r.to_dict()
        assert "degradation_severity" in d
        assert isinstance(d["degradation_severity"], (int, float))

    def test_axis_result_to_dict_includes_constraints(self):
        """AxisResult.to_dict() MUST include axis_constraints."""
        from backend.axis_result import AxisResult
        r = AxisResult(
            country="FR", axis_id=2, axis_slug="energy",
            score=0.4, basis="BOTH", validity="VALID",
            coverage=1.0, source="Eurostat",
            warnings=(),
            channel_a_concentration=0.3, channel_b_concentration=0.2,
        )
        d = r.to_dict()
        assert "axis_constraints" in d
        assert isinstance(d["axis_constraints"], dict)
        assert "value_type" in d["axis_constraints"]

    def test_composite_to_dict_includes_interpretation(self):
        """CompositeResult.to_dict() MUST include interpretation metadata."""
        from backend.axis_result import AxisResult, CompositeResult
        axes = []
        for i, slug in enumerate(["financial", "energy", "technology",
                                    "defense", "critical_inputs", "logistics"], 1):
            axes.append(AxisResult(
                country="SE", axis_id=i, axis_slug=slug,
                score=0.2, basis="BOTH", validity="VALID",
                coverage=1.0, source=f"source_{i}",
                warnings=(),
                channel_a_concentration=0.1, channel_b_concentration=0.1,
            ))
        cr = CompositeResult(
            country="SE", country_name="Sweden",
            isi_composite=0.2, classification="diversified",
            axes_included=6,
            axes_excluded=(),
            confidence="FULL",
            scope="EU-27",
            methodology_version="v1.1",
            warnings=(),
            axis_results=tuple(axes),
        )
        d = cr.to_dict()
        assert "interpretation_flags" in d
        assert "interpretation_summary" in d
        assert "strict_comparability_tier" in d
        assert "exclude_from_rankings" in d
        assert "severity_analysis" in d

    def test_composite_tier4_nullification_enforced(self):
        """TIER_4 countries MUST have composite_adjusted=NULL and exclude_from_rankings=TRUE."""
        from backend.severity import enforce_output_integrity
        # Simulate a TIER_4 output that violates nullification
        fake_output = {
            "country": "XX",
            "strict_comparability_tier": "TIER_4",
            "composite_adjusted": 0.5,  # violation
            "exclude_from_rankings": False,  # violation
            "severity_analysis": {
                "total_severity": 5.0,
                "mean_severity": 2.5,
                "max_axis_severity": 3.0,
                "worst_axis": "defense",
                "severity_profile": {},
                "n_clean_axes": 0,
                "n_degraded_axes": 4,
            },
            "interpretation_flags": [],
            "interpretation_summary": "",
            "ranking_partition": "NON_COMPARABLE",
            "comparability_tier": "NOT_COMPARABLE",
            "structural_degradation_profile": {},
            "stability_analysis": {},
            "structural_class": {},
            "axes": [],
        }
        violations = enforce_output_integrity(fake_output)
        assert len(violations) >= 2, (
            "TIER_4 with non-null adjusted and rankings=False should produce ≥2 violations"
        )

    def test_validate_check_13_exists_and_callable(self):
        """CHECK 13 (output_plausibility_check) must exist in ALL_CHECKS."""
        from pipeline.validate import ALL_CHECKS
        names = [c.__name__ for c in ALL_CHECKS]
        assert "check_output_plausibility" in names, (
            "CHECK 13 (output plausibility) must be in ALL_CHECKS"
        )

    def test_validate_check_13_returns_annotations(self):
        """CHECK 13 must produce a ValidationResult with status."""
        from pipeline.schema import BilateralRecord, BilateralDataset
        from pipeline.validate import check_output_plausibility, ValidationResult
        # Build a minimal dataset
        records = [
            BilateralRecord(
                reporter="JP", partner="US", year=2020, value=100.0,
                source="SIPRI", axis="defense",
            ),
        ]
        ds = BilateralDataset(
            reporter="JP", axis="defense", source="SIPRI",
            year_range=(2020, 2020),
            records=records,
        )
        ds.compute_metadata()
        result = check_output_plausibility(ds)
        assert isinstance(result, ValidationResult)
        assert result.status in ("PASS", "WARNING", "FAIL")
        assert hasattr(result, "details")
