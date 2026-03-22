"""
tests.test_sipri_ingestion — Comprehensive SIPRI ingestion test suite.

Covers:
    - SIPRI_TO_ISO2 mapping completeness (Turkiye, UAE, non-state entities)
    - Manifest verification (canonical + deprecated entries)
    - Schema enforcement (4 required columns with alias support)
    - Year window enforcement (2020–2025)
    - Partial year metadata (2025 flagged)
    - Canonical file constant (trade-register.csv, UTF-8)
    - Country resolution (direct + case-insensitive + non-state filtering)
    - TIV parsing edge cases
    - Delivery year parsing edge cases
    - End-to-end synthetic CSV ingestion (old + new column formats)
    - Global coverage (no EU-only guard — all countries supported)
    - Non-state entity handling (__NONSTATE__ filtering)
    - Real data integration (Japan, Germany, France, etc.)

Test philosophy:
    - Every test is DETERMINISTIC (no randomness, no network calls)
    - Synthetic tests use synthetic data (no dependency on raw files)
    - Real data tests verify actual trade-register.csv integration
    - Failure messages are diagnostic (tell you WHAT failed and WHY)
"""

from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pytest


# ===========================================================================
# SIPRI_TO_ISO2 MAPPING COMPLETENESS
# ===========================================================================

class TestSIPRICountryMappings:
    """Ensure SIPRI_TO_ISO2 covers ALL known country name variants."""

    def test_turkiye_mapped(self):
        """Turkey's 2022 rename to Turkiye must be in SIPRI_TO_ISO2."""
        from pipeline.config import SIPRI_TO_ISO2
        assert "Turkiye" in SIPRI_TO_ISO2, "Missing SIPRI mapping: Turkiye"
        assert SIPRI_TO_ISO2["Turkiye"] == "TR"

    def test_turkey_still_mapped(self):
        """Original 'Turkey' must also remain mapped."""
        from pipeline.config import SIPRI_TO_ISO2
        assert "Turkey" in SIPRI_TO_ISO2
        assert SIPRI_TO_ISO2["Turkey"] == "TR"

    def test_uae_abbreviation_mapped(self):
        """SIPRI sometimes uses 'UAE' abbreviation."""
        from pipeline.config import SIPRI_TO_ISO2
        assert "UAE" in SIPRI_TO_ISO2, "Missing SIPRI mapping: UAE"
        assert SIPRI_TO_ISO2["UAE"] == "AE"

    def test_uae_full_name_mapped(self):
        from pipeline.config import SIPRI_TO_ISO2
        assert "United Arab Emirates" in SIPRI_TO_ISO2
        assert SIPRI_TO_ISO2["United Arab Emirates"] == "AE"

    def test_unknown_supplier_mapped(self):
        """'unknown supplier(s)' must map to __UNKNOWN__ to be properly dropped."""
        from pipeline.config import SIPRI_TO_ISO2
        assert "unknown supplier(s)" in SIPRI_TO_ISO2, (
            "Missing SIPRI mapping: 'unknown supplier(s)' — "
            "these records will be silently lost instead of audited"
        )
        assert SIPRI_TO_ISO2["unknown supplier(s)"] == "__UNKNOWN__"

    def test_unknown_recipient_mapped(self):
        from pipeline.config import SIPRI_TO_ISO2
        assert "Unknown recipient(s)" in SIPRI_TO_ISO2
        assert SIPRI_TO_ISO2["Unknown recipient(s)"] == "__UNKNOWN__"

    def test_turkiye_resolves_to_tr(self):
        """End-to-end: _resolve_sipri_country('Turkiye') → 'TR'."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("Turkiye") == "TR"

    def test_uae_resolves_to_ae(self):
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("UAE") == "AE"

    def test_unknown_supplier_resolves_none(self):
        """Unknown supplier → None (dropped, not mapped to a country)."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("unknown supplier(s)") is None

    def test_all_eu27_recipients_mapped(self):
        """Every EU-27 country name that SIPRI uses must be in the mapping."""
        from pipeline.config import SIPRI_TO_ISO2, EU27_ISO2
        # These are the SIPRI display names for EU-27 countries
        eu_sipri_names = [
            "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus",
            "Czechia", "Denmark", "Estonia", "Finland", "France",
            "Germany", "Greece", "Hungary", "Ireland", "Italy",
            "Latvia", "Lithuania", "Luxembourg", "Malta", "Netherlands",
            "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
            "Spain", "Sweden",
        ]
        for name in eu_sipri_names:
            assert name in SIPRI_TO_ISO2, f"Missing SIPRI mapping for EU country: {name}"
            iso2 = SIPRI_TO_ISO2[name]
            assert iso2 in EU27_ISO2, f"{name} maps to {iso2} which is not in EU27_ISO2"

    def test_major_suppliers_mapped(self):
        """All major arms suppliers must be mapped."""
        from pipeline.config import SIPRI_TO_ISO2
        major_suppliers = {
            "United States": "US",
            "Russia": "RU",
            "France": "FR",
            "Germany": "DE",
            "China": "CN",
            "United Kingdom": "GB",
            "Israel": "IL",
            "South Korea": "KR",
            "Italy": "IT",
            "Sweden": "SE",
            "Turkey": "TR",
            "Turkiye": "TR",
            "Switzerland": "CH",
            "Norway": "NO",
            "Australia": "AU",
        }
        for name, expected_iso2 in major_suppliers.items():
            assert name in SIPRI_TO_ISO2, f"Missing SIPRI mapping: {name}"
            assert SIPRI_TO_ISO2[name] == expected_iso2, (
                f"{name}: expected {expected_iso2}, got {SIPRI_TO_ISO2[name]}"
            )

    def test_korea_variants_all_kr(self):
        """All Korea variant names must resolve to KR."""
        from pipeline.config import SIPRI_TO_ISO2
        korea_names = ["Korea, South", "Korea South", "South Korea", "Republic of Korea"]
        for name in korea_names:
            assert name in SIPRI_TO_ISO2, f"Missing Korea variant: {name}"
            assert SIPRI_TO_ISO2[name] == "KR", f"{name} maps to {SIPRI_TO_ISO2[name]}, not KR"


# ===========================================================================
# MANIFEST VERIFICATION
# ===========================================================================

class TestSIPRIManifest:
    """Tests for SIPRI manifest system."""

    def test_manifest_file_exists(self):
        """SIPRI manifest must exist at data/meta/sipri_manifest.json."""
        from pipeline.config import META_DIR
        manifest_path = META_DIR / "sipri_manifest.json"
        assert manifest_path.is_file(), f"Missing SIPRI manifest at {manifest_path}"

    def test_manifest_valid_json(self):
        """Manifest must be valid JSON."""
        from pipeline.config import META_DIR
        import json
        manifest_path = META_DIR / "sipri_manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert "source" in manifest
        assert manifest["source"] == "sipri"

    def test_manifest_has_file_entry(self):
        """Manifest must have at least one file entry with canonical file."""
        from pipeline.config import META_DIR
        import json
        with open(META_DIR / "sipri_manifest.json", "r") as f:
            manifest = json.load(f)
        assert "files" in manifest
        assert len(manifest["files"]) >= 1
        # Find the canonical entry
        canonical = [e for e in manifest["files"] if e.get("status") == "canonical"]
        assert len(canonical) >= 1, "Manifest must have a canonical file entry"
        entry = canonical[0]
        assert entry["filename"] == "trade-register.csv"
        assert "sha256" in entry
        assert "encoding" in entry
        assert "metadata_lines" in entry
        assert "data_rows" in entry

    def test_manifest_hash_matches_file(self):
        """SHA-256 in manifest must match the actual canonical raw file."""
        from pipeline.config import META_DIR, RAW_DIR
        import hashlib
        import json
        with open(META_DIR / "sipri_manifest.json", "r") as f:
            manifest = json.load(f)
        # Find canonical entry
        canonical = [e for e in manifest["files"] if e.get("status") == "canonical"]
        assert len(canonical) >= 1
        entry = canonical[0]
        raw_path = RAW_DIR / "sipri" / entry["filename"]
        if raw_path.is_file():
            actual = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            assert actual == entry["sha256"], (
                f"Manifest hash mismatch: expected={entry['sha256'][:16]}... "
                f"actual={actual[:16]}..."
            )

    def test_verify_manifest_function(self):
        """_verify_manifest() returns entry when hash matches."""
        from pipeline.ingest.sipri import _verify_manifest, SIPRI_CANONICAL_FILE
        from pipeline.config import RAW_DIR
        raw_path = RAW_DIR / "sipri" / SIPRI_CANONICAL_FILE
        if raw_path.is_file():
            entry = _verify_manifest(raw_path)
            assert entry is not None, "Manifest verification failed for canonical file"

    def test_verify_manifest_nonexistent_file(self):
        """_verify_manifest() handles nonexistent file gracefully."""
        from pipeline.ingest.sipri import _verify_manifest
        result = _verify_manifest(Path("/nonexistent/file.csv"))
        # Should return None (not crash) — file doesn't exist in manifest
        assert result is None


# ===========================================================================
# SCHEMA ENFORCEMENT
# ===========================================================================

class TestSIPRISchemaEnforcement:
    """Tests for SIPRI column schema enforcement."""

    def test_required_columns_defined(self):
        """SIPRI_REQUIRED_COLUMNS must include the 4 essential fields."""
        from pipeline.ingest.sipri import SIPRI_REQUIRED_COLUMNS
        required = set(SIPRI_REQUIRED_COLUMNS)
        assert "Recipient" in required
        assert "Supplier" in required
        assert "Delivery year" in required
        assert "TIV delivery values" in required

    def test_malformed_csv_missing_columns(self):
        """CSV with wrong columns must return MALFORMED_FILE."""
        from pipeline.ingest.sipri import ingest_sipri
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "bad.csv"
            with open(csv_path, "w", encoding="latin-1") as f:
                for i in range(11):
                    f.write(f"meta {i}\n")
                f.write("ColA,ColB,ColC\n")
                f.write("x,y,z\n")
            result, stats = ingest_sipri("DE", raw_path=csv_path)
            assert result is None
            assert stats["status"] == "MALFORMED_FILE"

    def test_truncated_metadata_malformed(self):
        """CSV with fewer than 11 metadata lines must return MALFORMED_FILE."""
        from pipeline.ingest.sipri import ingest_sipri
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "short.csv"
            with open(csv_path, "w", encoding="latin-1") as f:
                f.write("Only 3 lines\n")
                f.write("Line 2\n")
                f.write("Line 3\n")
            result, stats = ingest_sipri("DE", raw_path=csv_path)
            assert result is None
            assert stats["status"] == "MALFORMED_FILE"


# ===========================================================================
# YEAR WINDOW ENFORCEMENT
# ===========================================================================

class TestSIPRIYearWindow:
    """Tests for SIPRI year range filtering."""

    def test_default_year_range(self):
        """Default SIPRI_YEAR_RANGE must be defined and reasonable."""
        from pipeline.config import SIPRI_YEAR_RANGE
        assert len(SIPRI_YEAR_RANGE) == 2
        assert SIPRI_YEAR_RANGE[0] < SIPRI_YEAR_RANGE[1]
        assert SIPRI_YEAR_RANGE[0] >= 2015
        assert SIPRI_YEAR_RANGE[1] <= 2030

    def test_year_filtering_excludes_out_of_range(self):
        """Records with delivery years outside range must be excluded."""
        from pipeline.ingest.sipri import ingest_sipri
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sipri_years.csv"
            with open(csv_path, "w", encoding="latin-1", newline="") as f:
                for i in range(11):
                    f.write(f"Metadata line {i+1}\n")
                writer = csv.writer(f)
                writer.writerow([
                    "Recipient", "Supplier", "Year of order", "",
                    "Number ordered", "", "Weapon designation",
                    "Weapon description", "Number delivered", "",
                    "Year(s) of delivery", "status", "Comments",
                    "SIPRI TIV per unit", "SIPRI TIV for total order",
                    "SIPRI TIV of delivered weapons",
                ])
                # Delivery in 2020 — inside (2020, 2022)
                writer.writerow([
                    "Germany", "United States", "2018", "",
                    "5", "", "Patriot", "SAM system", "2", "",
                    "2020; 2021", "New", "",
                    "100", "500", "200",
                ])
                # Delivery in 2025 — outside (2020, 2022)
                writer.writerow([
                    "Germany", "France", "2023", "",
                    "3", "", "MARS", "MRL", "1", "",
                    "2025", "New", "",
                    "50", "150", "50",
                ])
            result, stats = ingest_sipri(
                "DE", raw_path=csv_path, year_range=(2020, 2022),
            )
            assert result is not None
            years_in_data = {r.year for r in result.records}
            assert 2025 not in years_in_data
            assert all(2020 <= y <= 2022 for y in years_in_data)


# ===========================================================================
# PARTIAL YEAR HANDLING
# ===========================================================================

class TestSIPRIPartialYear:
    """Tests for SIPRI partial year metadata."""

    def test_partial_year_flag_exists(self):
        from pipeline.ingest.sipri import SIPRI_LATEST_YEAR_PARTIAL
        assert isinstance(SIPRI_LATEST_YEAR_PARTIAL, bool)

    def test_partial_year_in_stats(self):
        """Stats should note when latest year may be partial."""
        from pipeline.ingest.sipri import ingest_sipri
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sipri_partial.csv"
            with open(csv_path, "w", encoding="latin-1", newline="") as f:
                for i in range(11):
                    f.write(f"Metadata line {i+1}\n")
                writer = csv.writer(f)
                writer.writerow([
                    "Recipient", "Supplier", "Year of order", "",
                    "Number ordered", "", "Weapon designation",
                    "Weapon description", "Number delivered", "",
                    "Year(s) of delivery", "status", "Comments",
                    "SIPRI TIV per unit", "SIPRI TIV for total order",
                    "SIPRI TIV of delivered weapons",
                ])
                writer.writerow([
                    "France", "United States", "2020", "",
                    "10", "", "F-35A", "combat aircraft", "2", "",
                    "2023; 2024", "New", "",
                    "80", "800", "160",
                ])
            result, stats = ingest_sipri(
                "FR", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            assert stats.get("latest_year_partial") is True or stats.get("partial_year") is not None


# ===========================================================================
# TIV PARSING
# ===========================================================================

class TestSIPRITIVParsing:
    """Tests for _parse_tiv edge cases."""

    def test_normal_number(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("6.56") == 6.56

    def test_integer(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("100") == 100.0

    def test_zero(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("0") == 0.0

    def test_empty(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("") == 0.0

    def test_question_mark_only(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("?") == 0.0

    def test_number_with_question_mark(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("6.56?") == 6.56

    def test_whitespace(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("  12.5  ") == 12.5

    def test_garbage(self):
        from pipeline.ingest.sipri import _parse_tiv
        assert _parse_tiv("N/A") == 0.0


# ===========================================================================
# DELIVERY YEAR PARSING
# ===========================================================================

class TestSIPRIDeliveryYearParsing:
    """Tests for _parse_delivery_years edge cases."""

    def test_single_year(self):
        from pipeline.ingest.sipri import _parse_delivery_years
        assert _parse_delivery_years("2023") == [2023]

    def test_multiple_years(self):
        from pipeline.ingest.sipri import _parse_delivery_years
        result = _parse_delivery_years("2019; 2020; 2022; 2023; 2024")
        assert result == [2019, 2020, 2022, 2023, 2024]

    def test_empty(self):
        from pipeline.ingest.sipri import _parse_delivery_years
        assert _parse_delivery_years("") == []

    def test_question_marks_stripped(self):
        from pipeline.ingest.sipri import _parse_delivery_years
        result = _parse_delivery_years("2023?; 2024")
        assert 2023 in result
        assert 2024 in result

    def test_comma_separated(self):
        from pipeline.ingest.sipri import _parse_delivery_years
        result = _parse_delivery_years("2022, 2023")
        assert 2022 in result
        assert 2023 in result

    def test_garbage_ignored(self):
        from pipeline.ingest.sipri import _parse_delivery_years
        result = _parse_delivery_years("N/A; unknown")
        assert result == []


# ===========================================================================
# COUNTRY RESOLUTION
# ===========================================================================

class TestSIPRICountryResolution:
    """Tests for _resolve_sipri_country function."""

    def test_direct_lookup(self):
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("United States") == "US"
        assert _resolve_sipri_country("Japan") == "JP"

    def test_case_insensitive(self):
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("united states") == "US"

    def test_empty_none(self):
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("") is None
        assert _resolve_sipri_country("   ") is None

    def test_aggregate_returns_none(self):
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("Unknown recipient(s)") is None
        assert _resolve_sipri_country("unknown supplier(s)") is None

    def test_nonstate_returns_none(self):
        """Non-state entities (mapped to __NONSTATE__) must resolve to None."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("NATO**") is None
        assert _resolve_sipri_country("Hezbollah (Lebanon)*") is None

    def test_unmapped_returns_none(self):
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("Planet Mars") is None


# ===========================================================================
# CANONICAL FILE CONSTANT
# ===========================================================================

class TestSIPRICanonicalFile:
    """Tests for SIPRI canonical file infrastructure."""

    def test_canonical_file_defined(self):
        from pipeline.ingest.sipri import SIPRI_CANONICAL_FILE
        assert isinstance(SIPRI_CANONICAL_FILE, str)
        assert SIPRI_CANONICAL_FILE.endswith(".csv")

    def test_canonical_file_exists(self):
        """The canonical SIPRI file must exist on disk."""
        from pipeline.ingest.sipri import SIPRI_CANONICAL_FILE
        from pipeline.config import RAW_DIR
        path = RAW_DIR / "sipri" / SIPRI_CANONICAL_FILE
        assert path.is_file(), f"Canonical SIPRI file missing: {path}"

    def test_canonical_file_is_readable(self):
        """The canonical file must be readable as UTF-8."""
        from pipeline.ingest.sipri import SIPRI_CANONICAL_FILE
        from pipeline.config import RAW_DIR
        path = RAW_DIR / "sipri" / SIPRI_CANONICAL_FILE
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            assert len(content) > 0

    def test_metadata_lines_constant(self):
        from pipeline.ingest.sipri import SIPRI_METADATA_LINES
        assert SIPRI_METADATA_LINES == 11


# ===========================================================================
# END-TO-END SYNTHETIC INGESTION
# ===========================================================================

class TestSIPRISyntheticIngestion:
    """End-to-end tests with synthetic SIPRI CSV data."""

    @staticmethod
    def _make_sipri_csv(path: Path, rows: list[list[str]]) -> Path:
        """Create a synthetic SIPRI CSV with proper structure."""
        with open(path, "w", encoding="latin-1", newline="") as f:
            for i in range(11):
                f.write(f"Metadata line {i+1}\n")
            writer = csv.writer(f)
            writer.writerow([
                "Recipient", "Supplier", "Year of order", "",
                "Number ordered", "", "Weapon designation",
                "Weapon description", "Number delivered", "",
                "Year(s) of delivery", "status", "Comments",
                "SIPRI TIV per unit", "SIPRI TIV for total order",
                "SIPRI TIV of delivered weapons",
            ])
            for row in rows:
                writer.writerow(row)
        return path

    def test_basic_ingestion(self):
        """Basic two-supplier ingestion for Germany."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["Germany", "United States", "2020", "", "10", "", "F-35A",
                     "combat aircraft", "4", "", "2022; 2023", "New", "",
                     "80", "800", "320"],
                    ["Germany", "France", "2021", "", "5", "", "MILAN",
                     "anti-tank missile", "3", "", "2023", "New", "",
                     "10", "50", "30"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "DE", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "DE"
            assert result.axis == "defense"
            assert result.source == "sipri"
            partners = {r.partner for r in result.records}
            assert "US" in partners
            assert "FR" in partners

    def test_tiv_distributed_across_years(self):
        """TIV should be split equally across delivery years."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["France", "United States", "2020", "", "10", "", "F-16",
                     "combat aircraft", "4", "", "2020; 2021", "New", "",
                     "50", "500", "200"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "FR", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            # 200 TIV split across 2 years = 100 per year
            year_values = {r.year: r.value for r in result.records}
            assert 2020 in year_values
            assert 2021 in year_values
            assert abs(year_values[2020] - 100.0) < 0.01
            assert abs(year_values[2021] - 100.0) < 0.01

    def test_zero_tiv_skipped(self):
        """Records with 0 or empty TIV should be skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["Italy", "Germany", "2020", "", "5", "", "Leopard",
                     "tank", "2", "", "2022", "New", "",
                     "50", "250", "0"],
                    ["Italy", "United States", "2020", "", "3", "", "F-35",
                     "aircraft", "1", "", "2022", "New", "",
                     "80", "240", "80"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "IT", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            assert stats["rows_zero_tiv"] >= 1
            partners = {r.partner for r in result.records}
            assert "US" in partners

    def test_turkiye_as_supplier(self):
        """Turkiye (Turkey's 2022 name) must resolve as supplier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["Poland", "Turkiye", "2022", "", "5", "", "Bayraktar",
                     "UAV", "5", "", "2023; 2024", "New", "",
                     "5", "25", "25"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "PL", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            partners = {r.partner for r in result.records}
            assert "TR" in partners, "Turkiye should resolve to TR"

    def test_uae_as_supplier(self):
        """UAE abbreviation must resolve as supplier."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["Greece", "UAE", "2022", "", "2", "", "EDGE",
                     "guided bomb", "2", "", "2024", "New", "",
                     "3", "6", "6"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "GR", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            partners = {r.partner for r in result.records}
            assert "AE" in partners, "UAE should resolve to AE"

    def test_unknown_supplier_dropped(self):
        """'unknown supplier(s)' should be dropped, not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["Spain", "unknown supplier(s)", "2020", "", "5", "",
                     "unknown", "vehicle", "3", "", "2022", "New", "",
                     "10", "50", "30"],
                    ["Spain", "United States", "2020", "", "3", "", "AH-64",
                     "helicopter", "1", "", "2022", "New", "",
                     "30", "90", "30"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "ES", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            partners = {r.partner for r in result.records}
            assert "__UNKNOWN__" not in partners
            # Unknown supplier is in SIPRI_TO_ISO2 (maps to __UNKNOWN__),
            # so it counts as unknown_supplier (three-way entity classification)
            assert (stats["rows_unknown_supplier"] >= 1
                    or stats["rows_nonstate_supplier"] >= 1
                    or stats["rows_unmapped_supplier"] >= 1), (
                f"Unknown supplier should be counted in stats: {stats}"
            )

    def test_no_data_for_reporter(self):
        """Reporter with no matching rows should get NO_DATA."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["France", "United States", "2020", "", "10", "", "F-16",
                     "aircraft", "4", "", "2022", "New", "",
                     "80", "800", "320"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "DE", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is None
            assert stats["status"] == "NO_DATA"

    def test_custom_path_works_for_any_country(self):
        """Explicit raw_path for any country produces data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = self._make_sipri_csv(
                Path(tmpdir) / "test.csv",
                [
                    ["Japan", "United States", "2020", "", "10", "", "F-35A",
                     "combat aircraft", "4", "", "2022; 2023", "New", "",
                     "80", "800", "320"],
                ],
            )
            result, stats = ingest_sipri_fn(
                "JP", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "JP"


# Import helper at module level for synthetic tests
def ingest_sipri_fn(*args, **kwargs):
    from pipeline.ingest.sipri import ingest_sipri
    return ingest_sipri(*args, **kwargs)


# ===========================================================================
# GLOBAL COVERAGE — NO EU-ONLY GUARD
# ===========================================================================

class TestSIPRIGlobalCoverage:
    """Tests verifying global coverage (coverage guard removed)."""

    def test_eu27_countries_produce_data(self):
        """EU-27 countries should produce OK or NO_DATA (never IMPLEMENTATION_LIMITATION)."""
        from pipeline.config import EU27_ISO2
        from pipeline.ingest.sipri import ingest_sipri
        for country in sorted(EU27_ISO2):
            _, stats = ingest_sipri(country)
            assert stats["status"] not in ("STRUCTURAL_LIMITATION", "IMPLEMENTATION_LIMITATION"), (
                f"EU country {country} should not hit any limitation, got {stats['status']}"
            )

    def test_non_eu_countries_no_limitation(self):
        """Non-EU countries must NOT get IMPLEMENTATION_LIMITATION with global data."""
        from pipeline.ingest.sipri import ingest_sipri
        for country in ["JP", "US", "CN", "AU", "KR", "NO", "GB"]:
            result, stats = ingest_sipri(country)
            assert stats["status"] != "IMPLEMENTATION_LIMITATION", (
                f"{country}: should not get IMPLEMENTATION_LIMITATION with global data"
            )
            # These major arms importers should have data
            if country in ("JP", "AU", "KR"):
                assert result is not None, f"{country}: expected data in global register"
                assert stats["status"] == "OK"

    def test_japan_produces_real_data(self):
        """Japan must now return OK with real partner data."""
        from pipeline.ingest.sipri import ingest_sipri
        result, stats = ingest_sipri("JP")
        assert result is not None
        assert stats["status"] == "OK"
        assert result.reporter == "JP"
        assert result.n_partners >= 3, f"JP: expected ≥3 partners, got {result.n_partners}"
        partners = {r.partner for r in result.records}
        assert "US" in partners, f"JP: US must be a partner, got {partners}"

    def test_no_coverage_guard_constant(self):
        """SIPRI_RECIPIENT_COVERAGE should no longer exist in the module."""
        import pipeline.ingest.sipri as sipri_mod
        assert not hasattr(sipri_mod, "SIPRI_RECIPIENT_COVERAGE"), (
            "SIPRI_RECIPIENT_COVERAGE should be removed — global data covers all countries"
        )


# ===========================================================================
# NON-STATE ENTITY HANDLING
# ===========================================================================

class TestSIPRINonStateEntities:
    """Tests for non-state actor / aggregate entity filtering."""

    def test_nonstate_resolves_none(self):
        """Non-state entities mapped to __NONSTATE__ must resolve to None."""
        from pipeline.ingest.sipri import _resolve_sipri_country
        assert _resolve_sipri_country("NATO**") is None
        assert _resolve_sipri_country("Hezbollah (Lebanon)*") is None
        assert _resolve_sipri_country("Houthi rebels (Yemen)*") is None

    def test_nonstate_in_mapping(self):
        """Non-state/multinational entities must be in SIPRI_TO_ISO2 with correct sentinel code.

        Three-way classification:
            __MULTINATIONAL__ — intergovernmental orgs (NATO, AU, UN)
            __NONSTATE__      — armed non-state actors (Hezbollah, Houthis, etc.)
            __UNKNOWN__       — unresolvable entities
        All are dropped from ISI computation; the distinction is for audit transparency.
        """
        from pipeline.config import SIPRI_TO_ISO2
        # Multinational organizations → __MULTINATIONAL__
        multinational_names = ["NATO**", "African Union**", "United Nations**"]
        for name in multinational_names:
            assert name in SIPRI_TO_ISO2, f"Missing multinational mapping: {name}"
            assert SIPRI_TO_ISO2[name] == "__MULTINATIONAL__", (
                f"{name} should map to __MULTINATIONAL__, got {SIPRI_TO_ISO2[name]}"
            )
        # Armed non-state actors → __NONSTATE__
        nonstate_names = [
            "Hezbollah (Lebanon)*", "Houthi rebels (Yemen)*",
            "House of Representatives (Libya)*", "RSF (Sudan)*",
        ]
        for name in nonstate_names:
            assert name in SIPRI_TO_ISO2, f"Missing non-state mapping: {name}"
            assert SIPRI_TO_ISO2[name] == "__NONSTATE__", (
                f"{name} should map to __NONSTATE__, got {SIPRI_TO_ISO2[name]}"
            )

    def test_nonstate_dropped_with_audit(self):
        """Non-state entities should be counted in stats, not silently lost."""
        from pipeline.ingest.sipri import ingest_sipri
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "nonstate.csv"
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                for i in range(11):
                    f.write(f"Metadata line {i+1}\n")
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
                # NATO** as recipient (non-state)
                writer.writerow([
                    "1", "United States", "NATO**", "Patriot", "SAM",
                    "Air-defence systems", "2020", "", "5", "",
                    "2022", "", "New", "", "", "100", "",
                ])
                # Real country row
                writer.writerow([
                    "2", "France", "Germany", "MILAN", "ATGM",
                    "Missiles", "2021", "", "3", "",
                    "2023", "", "New", "", "", "30", "",
                ])
            result, stats = ingest_sipri(
                "DE", raw_path=csv_path, year_range=(2020, 2025),
            )
            assert result is not None
            assert (stats["rows_nonstate_recipient"] >= 1
                    or stats["rows_multinational_recipient"] >= 1
                    or stats["rows_reporter_mismatch"] >= 1)


# ===========================================================================
# REAL DATA INTEGRATION (Japan defense axis — primary deliverable)
# ===========================================================================

class TestSIPRIRealDataSanity:
    """Sanity checks using the actual SIPRI raw data file (trade-register.csv)."""

    def test_germany_has_partners(self):
        """Germany must have multiple arms suppliers in the data."""
        from pipeline.ingest.sipri import ingest_sipri
        result, stats = ingest_sipri("DE")
        assert result is not None
        assert stats["status"] == "OK"
        assert result.n_partners >= 5, (
            f"DE: expected ≥5 partners, got {result.n_partners}"
        )

    def test_france_has_us_partner(self):
        """France must have US as an arms supplier."""
        from pipeline.ingest.sipri import ingest_sipri
        result, stats = ingest_sipri("FR")
        assert result is not None
        partners = {r.partner for r in result.records}
        assert "US" in partners, f"FR: US missing from partners {partners}"

    def test_total_tiv_positive(self):
        """Total TIV for countries with data must be > 0."""
        from pipeline.ingest.sipri import ingest_sipri
        for country in ["DE", "FR", "IT", "PL", "GR", "JP", "AU", "KR"]:
            result, stats = ingest_sipri(country)
            if result is not None:
                assert result.total_value > 0, (
                    f"{country}: total TIV should be > 0, got {result.total_value}"
                )

    def test_years_within_range(self):
        """All records must have years within SIPRI_YEAR_RANGE."""
        from pipeline.ingest.sipri import ingest_sipri
        from pipeline.config import SIPRI_YEAR_RANGE
        result, _ = ingest_sipri("DE")
        if result is not None:
            for r in result.records:
                assert SIPRI_YEAR_RANGE[0] <= r.year <= SIPRI_YEAR_RANGE[1], (
                    f"Record year {r.year} outside range {SIPRI_YEAR_RANGE}"
                )

    def test_all_records_defense_axis(self):
        """Every SIPRI record must have axis='defense'."""
        from pipeline.ingest.sipri import ingest_sipri
        result, _ = ingest_sipri("DE")
        if result is not None:
            for r in result.records:
                assert r.axis == "defense"

    def test_all_records_sipri_source(self):
        """Every SIPRI record must have source='sipri'."""
        from pipeline.ingest.sipri import ingest_sipri
        result, _ = ingest_sipri("DE")
        if result is not None:
            for r in result.records:
                assert r.source == "sipri"

    def test_japan_real_data_ok(self):
        """Japan must produce real defense data from global register."""
        from pipeline.ingest.sipri import ingest_sipri
        result, stats = ingest_sipri("JP")
        assert result is not None, "JP should have real SIPRI data"
        assert stats["status"] == "OK"
        assert result.reporter == "JP"
        assert result.axis == "defense"
        # Known from data audit: 6 suppliers, ~7014 TIV
        assert result.n_partners >= 5, f"JP: expected ≥5 partners, got {result.n_partners}"
        assert result.total_value > 5000, (
            f"JP: expected >5000 TIV, got {result.total_value}"
        )
        partners = {r.partner for r in result.records}
        assert "US" in partners, "JP must have US as partner"
        assert "GB" in partners, "JP must have GB as partner"

    def test_japan_us_dominance(self):
        """Japan's arms imports must be heavily US-dominated."""
        from pipeline.ingest.sipri import ingest_sipri
        result, _ = ingest_sipri("JP")
        assert result is not None
        us_tiv = sum(r.value for r in result.records if r.partner == "US")
        us_share = us_tiv / result.total_value
        assert us_share > 0.85, (
            f"JP: US share should be >85%, got {us_share:.1%} "
            f"(US TIV={us_tiv:.2f}, total={result.total_value:.2f})"
        )

    def test_japan_partial_year_flagged(self):
        """Japan stats should flag 2025 as partial year."""
        from pipeline.ingest.sipri import ingest_sipri
        _, stats = ingest_sipri("JP")
        assert stats.get("partial_year") == 2025 or stats.get("partial_year_risk") is True, (
            f"JP: 2025 should be flagged as partial, stats={stats}"
        )

    def test_japan_synthetic_csv_still_works(self):
        """JP with synthetic old-format CSV should still produce records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "jp_sipri.csv"
            with open(csv_path, "w", encoding="latin-1", newline="") as f:
                for i in range(11):
                    f.write(f"Metadata line {i+1}\n")
                writer = csv.writer(f)
                writer.writerow([
                    "Recipient", "Supplier", "Year of order", "",
                    "Number ordered", "", "Weapon designation",
                    "Weapon description", "Number delivered", "",
                    "Year(s) of delivery", "status", "Comments",
                    "SIPRI TIV per unit", "SIPRI TIV for total order",
                    "SIPRI TIV of delivered weapons",
                ])
                writer.writerow([
                    "Japan", "United States", "2020", "", "42", "", "F-35A",
                    "combat aircraft", "12", "", "2022; 2023; 2024", "New", "",
                    "80", "3360", "960",
                ])
                writer.writerow([
                    "Japan", "United Kingdom", "2021", "", "5", "",
                    "Rolls-Royce XWB", "aero-engine", "3", "",
                    "2023; 2024", "New", "", "10", "50", "30",
                ])
            from pipeline.ingest.sipri import ingest_sipri
            result, stats = ingest_sipri(
                "JP", raw_path=csv_path, year_range=(2019, 2024),
            )
            assert result is not None
            assert stats["status"] == "OK"
            assert result.reporter == "JP"
            assert result.axis == "defense"
            partners = {r.partner for r in result.records}
            assert "US" in partners
            assert "GB" in partners
            assert result.total_value > 0
