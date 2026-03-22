"""
pipeline.ingest.sipri — SIPRI Arms Transfers ingestion (production).

Canonical source:
    data/raw/sipri/trade-register.csv
    SIPRI Trade Register CSV export — GLOBAL (all suppliers, all recipients).
    Generated: 22 Mar 2026. Covers deliveries 2020–2025.

    DEPRECATED (do not use):
    data/raw/sipri/sipri_trade_register_2019_2024.csv
    (EU-27 recipients only, old 16-column schema, 2019–2024 year range)

Raw file schema (17 columns, comma-delimited, UTF-8):
    0:  SIPRI AT Database ID
    1:  Supplier                  → partner (arms exporter)
    2:  Recipient                 → reporter (arms importer)
    3:  Designation               → weapon designation (retained)
    4:  Description               → weapon description (retained)
    5:  Armament category         → sub_category (retained)
    6:  Order date
    7:  Order date is estimate
    8:  Numbers delivered
    9:  Numbers delivered is estimate
    10: Delivery year             → year (single integer per row)
    11: Delivery year is estimate
    12: Status                    → New / Second hand / Second hand but modernized
    13: SIPRI estimate
    14: TIV deal unit
    15: TIV delivery values       → value (realized TIV for this delivery row)
    16: Local production

Encoding: UTF-8 (ASCII text).
Preamble: 11 lines of metadata text (lines 0–10), CSV header on line 11.

Transformation contract:
    1. Skip 11 preamble lines, parse CSV header from line 11.
    2. For each data row: extract Recipient, Supplier, Delivery year, TIV delivery values.
    3. Resolve Recipient/Supplier names to ISO-2 via SIPRI_TO_ISO2.
    4. Drop rows where:
       - Recipient or Supplier resolves to None (unmapped / aggregate / non-state)
       - Recipient != requested reporter
       - TIV delivery values <= 0 or unparseable
       - Delivery year outside [2020, 2025]
       - Self-trade (reporter == partner)
    5. Each row = one bilateral record (one delivery year, one TIV value).
       No year splitting needed — the global register has one year per row.
    6. Normalize via standard normalize_records() pipeline.
    7. Output: BilateralDataset per reporter, axis="defense", source="sipri".

ISI perspective:
    reporter = Recipient (country whose defense dependency we measure)
    partner  = Supplier  (who supplies arms)

Year window: 2020–2025 inclusive (from SIPRI_YEAR_RANGE in config.py).
    2025 is flagged as partial-risk (SIPRI data updated continuously).

Manifest:
    data/meta/sipri_manifest.json — tracks file hash, row count, schema version.
    Verified on every ingestion for reproducibility.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
from pathlib import Path

from pipeline.config import (
    RAW_DIR,
    META_DIR,
    SIPRI_YEAR_RANGE,
    SIPRI_TO_ISO2,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import normalize_records, NormalizationAudit
from pipeline.status import IngestionStatus

logger = logging.getLogger("pipeline.ingest.sipri")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Number of preamble lines before the CSV column header
SIPRI_PREAMBLE_LINES = 11

# Backward-compat alias used by some tests
SIPRI_METADATA_LINES = SIPRI_PREAMBLE_LINES

# Canonical raw file — SINGLE source of truth (global register, all countries)
SIPRI_CANONICAL_FILE = "trade-register.csv"

# DEPRECATED old file — kept as constant so code can detect and warn
_SIPRI_DEPRECATED_FILE = "sipri_trade_register_2019_2024.csv"

# Manifest path — verified on every ingestion for reproducibility
SIPRI_MANIFEST_PATH = META_DIR / "sipri_manifest.json"

# Required columns — exact header names from the global register
SIPRI_REQUIRED_COLUMNS: tuple[str, ...] = (
    "Supplier",
    "Recipient",
    "Delivery year",
    "TIV delivery values",
)

# Partial year flag: the last year in the range may have incomplete deliveries.
# SIPRI data is updated continuously; 2025 rows may not reflect full-year totals.
SIPRI_LATEST_YEAR_PARTIAL: bool = True


# ---------------------------------------------------------------------------
# Manifest verification
# ---------------------------------------------------------------------------

def _verify_manifest(raw_path: Path) -> dict | None:
    """Verify raw file against manifest for reproducibility.

    Returns manifest file entry if verified, None if no manifest or mismatch.
    Logs warning on hash mismatch (does NOT block ingestion).
    """
    if not SIPRI_MANIFEST_PATH.is_file():
        logger.debug("No SIPRI manifest at %s — skipping verification", SIPRI_MANIFEST_PATH)
        return None

    try:
        with open(SIPRI_MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Cannot read SIPRI manifest: %s", e)
        return None

    filename = raw_path.name
    for entry in manifest.get("files", []):
        if entry.get("filename") == filename:
            expected_hash = entry.get("sha256", "")
            if expected_hash and raw_path.is_file():
                actual_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
                if actual_hash != expected_hash:
                    logger.warning(
                        "SIPRI manifest hash mismatch for %s: "
                        "expected=%s actual=%s — file may have been modified",
                        filename, expected_hash[:16], actual_hash[:16],
                    )
                else:
                    logger.info("SIPRI manifest verified: %s hash OK", filename)
            return entry

    logger.debug("File %s not found in SIPRI manifest", filename)
    return None


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_tiv(val: str) -> float:
    """Parse a SIPRI TIV value.

    Handles: normal floats, zero, empty → 0, question marks stripped.
    """
    val = val.strip().replace("?", "").strip()
    if not val:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_delivery_year(val: str) -> int | None:
    """Parse a single delivery year integer.

    In the global register each row has exactly one delivery year.
    Returns None if unparseable.
    """
    val = val.strip().replace("?", "").strip()
    try:
        y = int(val)
        if 1990 <= y <= 2030:
            return y
    except (ValueError, TypeError):
        pass
    return None


def _parse_delivery_years(year_str: str) -> list[int]:
    """Parse delivery years — handles both single-year and semicolon-separated.

    The global register uses single years per row, but this function
    also supports the old semicolon format for synthetic test CSVs.
    """
    years = []
    for part in year_str.replace(",", ";").split(";"):
        y = _parse_delivery_year(part)
        if y is not None:
            years.append(y)
    return years


def _resolve_sipri_country(name: str) -> str | None:
    """Resolve SIPRI country name to ISO-2 code.

    Returns None for unknown, aggregate, multinational, or non-state entries.
    Codes starting with '__' are sentinel values:
        __UNKNOWN__       — unresolvable entity
        __NONSTATE__      — armed non-state actor / sub-national faction
        __MULTINATIONAL__ — intergovernmental organization (NATO, AU, UN)

    All are dropped from ISI computation; the calling function tracks
    each category separately for audit transparency.
    """
    name = name.strip()
    if not name:
        return None

    # Direct lookup
    if name in SIPRI_TO_ISO2:
        code = SIPRI_TO_ISO2[name]
        if code.startswith("__"):
            return None  # aggregate / unknown / non-state / multinational
        return code

    # Case-insensitive fallback
    name_lower = name.lower()
    for sipri_name, code in SIPRI_TO_ISO2.items():
        if sipri_name.lower() == name_lower:
            if code.startswith("__"):
                return None
            return code

    return None


def _classify_sipri_entity(name: str) -> str:
    """Classify a SIPRI entity name into a category for audit tracking.

    Returns one of:
        "STATE"          — resolved to a sovereign ISO-2 code
        "MULTINATIONAL"  — intergovernmental organization (NATO, AU, UN)
        "NONSTATE"       — armed non-state actor / sub-national faction
        "UNKNOWN"        — explicit __UNKNOWN__ sentinel or unresolvable
        "UNMAPPED"       — not present in SIPRI_TO_ISO2 at all
    """
    name = name.strip()
    if not name:
        return "UNMAPPED"

    # Direct lookup
    if name in SIPRI_TO_ISO2:
        code = SIPRI_TO_ISO2[name]
        if code == "__MULTINATIONAL__":
            return "MULTINATIONAL"
        if code == "__NONSTATE__":
            return "NONSTATE"
        if code == "__UNKNOWN__":
            return "UNKNOWN"
        return "STATE"

    # Case-insensitive fallback
    name_lower = name.lower()
    for sipri_name, code in SIPRI_TO_ISO2.items():
        if sipri_name.lower() == name_lower:
            if code == "__MULTINATIONAL__":
                return "MULTINATIONAL"
            if code == "__NONSTATE__":
                return "NONSTATE"
            if code == "__UNKNOWN__":
                return "UNKNOWN"
            return "STATE"

    return "UNMAPPED"


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_sipri(
    reporter_iso2: str,
    raw_path: Path | None = None,
    year_range: tuple[int, int] | None = None,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest SIPRI Trade Register data for a single ISI reporter.

    Uses the global register (trade-register.csv) which covers ALL countries.
    No EU-only coverage guard — every country that appears as a Recipient
    in the SIPRI database will produce results.

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter (Recipient / arms importer).
        raw_path: Override path to raw SIPRI CSV. If None, uses canonical file.
        year_range: (min_year, max_year) inclusive filter for delivery years.

    Returns:
        (BilateralDataset or None, stats_dict)
    """
    user_supplied_path = raw_path is not None
    if raw_path is None:
        raw_path = RAW_DIR / "sipri" / SIPRI_CANONICAL_FILE
    if year_range is None:
        year_range = SIPRI_YEAR_RANGE

    stats: dict = {
        "source": "sipri",
        "reporter": reporter_iso2,
        "raw_file": str(raw_path),
        "year_range": list(year_range),
        "canonical_file": SIPRI_CANONICAL_FILE,
        "latest_year_partial": SIPRI_LATEST_YEAR_PARTIAL,
        "rows_read": 0,
        "rows_unmapped_recipient": 0,
        "rows_unmapped_supplier": 0,
        "rows_nonstate_recipient": 0,
        "rows_nonstate_supplier": 0,
        "rows_multinational_recipient": 0,
        "rows_multinational_supplier": 0,
        "rows_unknown_recipient": 0,
        "rows_unknown_supplier": 0,
        "rows_reporter_mismatch": 0,
        "rows_zero_tiv": 0,
        "rows_no_delivery_year": 0,
        "rows_year_out_of_range": 0,
        "rows_self_trade": 0,
        "raw_records_extracted": 0,
        "final_records": 0,
        "entity_classification": {
            "recipients_state": 0,
            "recipients_multinational": 0,
            "recipients_nonstate": 0,
            "recipients_unknown": 0,
            "recipients_unmapped": 0,
            "suppliers_state": 0,
            "suppliers_multinational": 0,
            "suppliers_nonstate": 0,
            "suppliers_unknown": 0,
            "suppliers_unmapped": 0,
        },
        "status": IngestionStatus.PENDING,
    }

    # ── Deprecation guard: warn if old file is being referenced ──────────
    if user_supplied_path and raw_path.name == _SIPRI_DEPRECATED_FILE:
        logger.warning(
            "SIPRI: using DEPRECATED file '%s' — switch to '%s'",
            _SIPRI_DEPRECATED_FILE, SIPRI_CANONICAL_FILE,
        )

    if not raw_path.is_file():
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        logger.error("SIPRI raw file not found: %s", raw_path)
        return None, stats

    # ── Manifest verification ────────────────────────────────────────────
    manifest_entry = _verify_manifest(raw_path)
    if manifest_entry:
        stats["manifest_verified"] = True
        stats["manifest_sha256"] = manifest_entry.get("sha256", "")[:16]
    else:
        stats["manifest_verified"] = False

    logger.info("Ingesting SIPRI for %s from %s, years=%s",
                reporter_iso2, raw_path.name, year_range)

    raw_records: list[BilateralRecord] = []

    # ── File encoding: try UTF-8 first (new file), fall back to Latin-1 ──
    encoding = "utf-8"
    try:
        raw_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        encoding = "latin-1"

    with open(raw_path, "r", encoding=encoding, newline="") as f:
        reader = csv.reader(f)

        # Skip preamble lines
        for _ in range(SIPRI_PREAMBLE_LINES):
            try:
                next(reader)
            except StopIteration:
                stats["status"] = IngestionStatus.MALFORMED_FILE
                logger.error("SIPRI file has fewer than %d preamble lines",
                             SIPRI_PREAMBLE_LINES)
                return None, stats

        # Read column header
        try:
            header = next(reader)
        except StopIteration:
            stats["status"] = IngestionStatus.MALFORMED_FILE
            logger.error("SIPRI file has no column header after preamble")
            return None, stats

        header_stripped = [h.strip() for h in header]
        header_map: dict[str, int] = {h: i for i, h in enumerate(header_stripped)}

        # ── Schema enforcement ───────────────────────────────────────────
        # Column name resolution: supports both the new global register
        # (exact column names) and the old EU-only file / synthetic test CSVs.
        #
        # Alias map: new canonical name → list of acceptable alternatives
        _COL_ALIASES: dict[str, list[str]] = {
            "Supplier": ["supplier"],
            "Recipient": ["recipient"],
            "Delivery year": ["year(s) of delivery", "year(s) of deliver",
                              "delivery year"],
            "TIV delivery values": ["tiv delivery values",
                                    "sipri tiv of delivered weapons",
                                    "tiv of delivered"],
        }

        def _find_col(canonical: str) -> int | None:
            """Find column index by canonical name or known aliases."""
            if canonical in header_map:
                return header_map[canonical]
            # Try aliases (case-insensitive substring against headers)
            aliases = _COL_ALIASES.get(canonical, [canonical.lower()])
            headers_lower = [h.lower() for h in header_stripped]
            for alias in aliases:
                for i, hl in enumerate(headers_lower):
                    if alias in hl:
                        return i
            return None

        # Resolve all required columns
        resolved: dict[str, int | None] = {
            col: _find_col(col) for col in SIPRI_REQUIRED_COLUMNS
        }
        still_missing = [col for col, idx in resolved.items() if idx is None]

        if still_missing:
            stats["status"] = IngestionStatus.MALFORMED_FILE
            logger.error(
                "SIPRI: missing required columns %s. Found: %s",
                still_missing, header_stripped,
            )
            return None, stats

        idx_recipient = resolved["Recipient"]
        idx_supplier = resolved["Supplier"]
        idx_tiv = resolved["TIV delivery values"]
        idx_delivery_year = resolved["Delivery year"]

        # Optional retained context fields
        idx_designation = header_map.get("Designation")
        if idx_designation is None:
            # Old schema: "Weapon designation"
            for h, i in header_map.items():
                if "designation" in h.lower():
                    idx_designation = i
                    break
        idx_description = header_map.get("Description")
        if idx_description is None:
            for h, i in header_map.items():
                if "description" in h.lower():
                    idx_description = i
                    break
        idx_category = header_map.get("Armament category")
        if idx_category is None:
            for h, i in header_map.items():
                if "category" in h.lower() or "description" in h.lower():
                    if i != idx_designation and i != idx_description:
                        idx_category = i
                        break

        # Parse data rows
        for row in reader:
            stats["rows_read"] += 1

            min_len = max(idx_recipient, idx_supplier, idx_tiv)
            if idx_delivery_year is not None:
                min_len = max(min_len, idx_delivery_year)
            if len(row) <= min_len:
                continue

            # ── Recipient (ISI reporter / arms importer) ─────────────────
            recipient_name = row[idx_recipient].strip()
            recipient_class = _classify_sipri_entity(recipient_name)
            stats["entity_classification"][f"recipients_{recipient_class.lower()}"] += 1
            recipient_iso2 = _resolve_sipri_country(recipient_name)

            if recipient_iso2 is None:
                if recipient_class == "NONSTATE":
                    stats["rows_nonstate_recipient"] += 1
                elif recipient_class == "MULTINATIONAL":
                    stats["rows_multinational_recipient"] += 1
                elif recipient_class == "UNKNOWN":
                    stats["rows_unknown_recipient"] += 1
                else:
                    stats["rows_unmapped_recipient"] += 1
                continue

            if recipient_iso2 != reporter_iso2:
                stats["rows_reporter_mismatch"] += 1
                continue

            # ── Supplier (ISI partner / arms exporter) ───────────────────
            supplier_name = row[idx_supplier].strip()
            supplier_class = _classify_sipri_entity(supplier_name)
            stats["entity_classification"][f"suppliers_{supplier_class.lower()}"] += 1
            supplier_iso2 = _resolve_sipri_country(supplier_name)

            if supplier_iso2 is None:
                if supplier_class == "NONSTATE":
                    stats["rows_nonstate_supplier"] += 1
                elif supplier_class == "MULTINATIONAL":
                    stats["rows_multinational_supplier"] += 1
                elif supplier_class == "UNKNOWN":
                    stats["rows_unknown_supplier"] += 1
                else:
                    stats["rows_unmapped_supplier"] += 1
                continue

            # ── Self-trade guard ─────────────────────────────────────────
            if recipient_iso2 == supplier_iso2:
                stats["rows_self_trade"] += 1
                continue

            # ── Delivery year ────────────────────────────────────────────
            if idx_delivery_year is not None:
                year_str = row[idx_delivery_year].strip()
            else:
                stats["rows_no_delivery_year"] += 1
                continue

            # The global register has one year per row.
            # Old-format files may have semicolon-separated years.
            delivery_years = _parse_delivery_years(year_str)

            if not delivery_years:
                stats["rows_no_delivery_year"] += 1
                continue

            # Filter to year range
            relevant_years = [
                y for y in delivery_years
                if year_range[0] <= y <= year_range[1]
            ]

            if not relevant_years:
                stats["rows_year_out_of_range"] += 1
                continue

            # ── TIV delivery value ───────────────────────────────────────
            tiv = _parse_tiv(row[idx_tiv])
            if tiv <= 0:
                stats["rows_zero_tiv"] += 1
                continue

            # ── Optional context fields ──────────────────────────────────
            designation = ""
            if idx_designation is not None and len(row) > idx_designation:
                designation = row[idx_designation].strip()
            category = ""
            if idx_category is not None and len(row) > idx_category:
                category = row[idx_category].strip()

            # Distribute TIV across delivery years (for multi-year rows)
            tiv_per_year = tiv / len(relevant_years)

            for year in relevant_years:
                raw_records.append(BilateralRecord(
                    reporter=recipient_iso2,
                    partner=supplier_iso2,
                    value=round(tiv_per_year, 8),
                    year=year,
                    source="sipri",
                    axis="defense",
                    product_desc=designation[:100] if designation else None,
                    unit="TIV_MN",
                    sub_category=category[:80] if category else None,
                ))

    stats["raw_records_extracted"] = len(raw_records)

    if not raw_records:
        stats["status"] = IngestionStatus.NO_DATA
        logger.warning("SIPRI: no records for %s in years %s", reporter_iso2, year_range)
        return None, stats

    # ── Partial year metadata ────────────────────────────────────────────
    if SIPRI_LATEST_YEAR_PARTIAL:
        years_in_data = set(r.year for r in raw_records)
        max_year = max(years_in_data) if years_in_data else year_range[1]
        if max_year == year_range[1]:
            stats["partial_year"] = max_year
            stats["partial_year_note"] = (
                f"Year {max_year} may have incomplete deliveries "
                f"(SIPRI data is updated continuously). "
                f"Do not treat {max_year} totals as equivalent to prior years."
            )
            stats["partial_year_risk"] = True

    # ── Normalize ────────────────────────────────────────────────────────
    normalized, norm_audit = normalize_records(
        raw_records,
        source="sipri",
        axis="defense",
        reporter_filter=reporter_iso2,
    )

    # ── Build BilateralDataset ───────────────────────────────────────────
    dataset = BilateralDataset(
        reporter=reporter_iso2,
        axis="defense",
        source="sipri",
        year_range=year_range,
    )
    for rec in normalized:
        dataset.add_record(rec)

    dataset.compute_metadata()
    stats["final_records"] = len(dataset.records)
    stats["n_partners"] = dataset.n_partners
    stats["total_value"] = dataset.total_value
    stats["normalization"] = norm_audit.to_dict()
    stats["status"] = IngestionStatus.OK if dataset.records else IngestionStatus.NO_DATA

    logger.info(
        "SIPRI %s: %d records, %d partners, total=%.2f TIV mn",
        reporter_iso2, len(dataset.records), dataset.n_partners, dataset.total_value,
    )

    return dataset, stats
