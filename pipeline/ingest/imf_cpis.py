"""
pipeline.ingest.imf_cpis — IMF CPIS Portfolio Investment ingestion.

Input:
    data/raw/imf/imf_cpis_raw_full_assets_debt_annual.csv
    Wide-format CSV with:
        - Metadata columns: DATASET, SERIES_CODE, OBS_MEASURE, COUNTRY,
          ACCOUNTING_ENTRY, INDICATOR, SECTOR, COUNTERPART_SECTOR,
          COUNTERPART_COUNTRY, FREQUENCY, SCALE, ..., SERIES_NAME
        - Year columns: 1997, 1997-S1, 1997-S2, ..., 2024, 2024-S1, 2024-S2

Schema mapping:
    COUNTRY             = holder country (ISO-3 name or code embedded in SERIES_CODE)
    COUNTERPART_COUNTRY = issuer/debtor counterpart (name)
    ACCOUNTING_ENTRY    = "Assets" (outward) or "Liabilities" (derived)
    INDICATOR           = instrument breakdown
    Year columns        = position values in USD millions

ISI perspective:
    For ISI financial axis: reporter_i = holder of assets
    We want OUTWARD positions: "Assets" accounting entry
    partner_j = counterpart country (where assets are held)

    This gives us: "For reporter JP, how much portfolio investment
    does JP hold in each partner country?"

Country code extraction:
    SERIES_CODE format: "JPN.A.P_F3_S_P_USD.S12QU.S1.AND.S"
    First 3 chars = ISO-3 code of reporter
    The counterpart ISO-3 is embedded at position [5] when split by '.'

Output:
    BilateralDataset per reporter with axis="financial", source="imf_cpis"
"""

from __future__ import annotations

import csv
import math
import logging
from pathlib import Path

from pipeline.config import (
    RAW_DIR,
    CPIS_YEAR,
    ISO3_TO_ISO2,
    AGGREGATE_PARTNER_ISO2,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import normalize_records, NormalizationAudit, is_aggregate_partner
from pipeline.status import IngestionStatus

logger = logging.getLogger("pipeline.ingest.imf_cpis")

# ---------------------------------------------------------------------------
# CPIS CSV column names
# ---------------------------------------------------------------------------

COL_SERIES_CODE = "SERIES_CODE"
COL_COUNTRY = "COUNTRY"
COL_COUNTERPART_COUNTRY = "COUNTERPART_COUNTRY"
COL_ACCOUNTING_ENTRY = "ACCOUNTING_ENTRY"
COL_INDICATOR = "INDICATOR"
COL_SCALE = "SCALE"
COL_FREQUENCY = "FREQUENCY"

# We want total portfolio investment or specific debt instruments
# The "Assets" entry tells us outward holdings
REQUIRED_ACCOUNTING_ENTRY = "Assets"


def _extract_iso3_from_series_code(series_code: str) -> tuple[str | None, str | None]:
    """Extract reporter and counterpart ISO-3 codes from SERIES_CODE.

    Format: "TUR.A.P_F3_S_P_USD.S12QU.S1.AND.S"
    Index:    0   1  2            3     4  5   6

    Returns (reporter_iso3, counterpart_iso3) or (None, None).
    """
    parts = series_code.split(".")
    if len(parts) < 6:
        return None, None

    reporter_iso3 = parts[0].strip()
    counterpart_iso3 = parts[5].strip()

    # Validate they look like ISO-3 codes
    if len(reporter_iso3) < 2 or len(counterpart_iso3) < 2:
        return None, None

    return reporter_iso3, counterpart_iso3


def _resolve_iso3_to_iso2(iso3: str) -> str | None:
    """Resolve ISO-3 code to ISO-2. Returns None for aggregates/unmapped."""
    if not iso3 or len(iso3) < 2:
        return None

    # Direct mapping
    if iso3 in ISO3_TO_ISO2:
        return ISO3_TO_ISO2[iso3]

    # Already ISO-2?
    if len(iso3) == 2 and iso3.isalpha():
        return iso3.upper()

    # Aggregate codes (often numeric or multi-char special codes)
    if not iso3.isalpha():
        return None

    return None


def _is_aggregate_counterpart(name: str) -> bool:
    """Check if a counterpart country name is an aggregate.

    Delegates to the central is_aggregate_partner() in normalize.py.
    """
    return is_aggregate_partner(name)


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_imf_cpis(
    reporter_iso2: str,
    raw_path: Path | None = None,
    target_year: int | None = None,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest IMF CPIS data for a single ISI reporter.

    The CPIS CSV is wide-format: metadata columns + year columns.
    We extract the value for the target year from the year column.

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter.
        raw_path: Override path to raw CPIS CSV.
        target_year: Year to extract. Default: config.CPIS_YEAR (2024).

    Returns:
        (BilateralDataset or None, stats_dict)
    """
    if raw_path is None:
        raw_path = RAW_DIR / "imf" / "imf_cpis_raw_full_assets_debt_annual.csv"
    if target_year is None:
        target_year = CPIS_YEAR

    # Convert reporter ISO-2 to ISO-3 for matching
    from pipeline.config import ISO2_TO_ISO3
    reporter_iso3 = ISO2_TO_ISO3.get(reporter_iso2, "")

    stats = {
        "source": "imf_cpis",
        "reporter": reporter_iso2,
        "reporter_iso3": reporter_iso3,
        "raw_file": str(raw_path),
        "target_year": target_year,
        "rows_read": 0,
        "rows_not_assets": 0,
        "rows_reporter_mismatch": 0,
        "rows_aggregate_counterpart": 0,
        "rows_unmapped_counterpart": 0,
        "rows_missing_value": 0,
        "rows_negative": 0,
        "rows_zero": 0,
        "raw_records_extracted": 0,
        "final_records": 0,
        "status": IngestionStatus.PENDING,
    }

    if not raw_path.is_file():
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        logger.error("CPIS raw file not found: %s", raw_path)
        return None, stats

    if not reporter_iso3:
        stats["status"] = IngestionStatus.MALFORMED_FILE
        logger.error(
            "Cannot map reporter ISO-2 '%s' to ISO-3 for CPIS lookup",
            reporter_iso2,
        )
        return None, stats

    logger.info("Ingesting IMF CPIS for %s (%s), year=%d", reporter_iso2, reporter_iso3, target_year)

    # The target year column name in the wide-format CSV
    year_col = str(target_year)

    # ---------------------------------------------------------------------------
    # Phase 1: Parse wide-format CSV
    # ---------------------------------------------------------------------------

    raw_records: list[BilateralRecord] = []

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Verify year column exists
        if year_col not in fieldnames:
            # Try with quotes
            year_col_candidates = [fn for fn in fieldnames if fn.strip().strip('"') == str(target_year)]
            if year_col_candidates:
                year_col = year_col_candidates[0]
            else:
                stats["status"] = IngestionStatus.MALFORMED_FILE
                logger.error(
                    "Year column '%s' not found in CPIS CSV. Available: %s",
                    target_year, fieldnames[:20],
                )
                return None, stats

        for row in reader:
            stats["rows_read"] += 1

            # Filter: Assets only (outward positions)
            acct_entry = row.get(COL_ACCOUNTING_ENTRY, "").strip()
            if acct_entry != REQUIRED_ACCOUNTING_ENTRY:
                stats["rows_not_assets"] += 1
                continue

            # Extract country codes from SERIES_CODE
            series_code = row.get(COL_SERIES_CODE, "").strip()
            rep_iso3, cp_iso3 = _extract_iso3_from_series_code(series_code)

            if not rep_iso3:
                continue

            # Reporter match
            if rep_iso3.upper() != reporter_iso3.upper():
                stats["rows_reporter_mismatch"] += 1
                continue

            # Counterpart resolution
            if not cp_iso3:
                stats["rows_unmapped_counterpart"] += 1
                continue

            # Check if counterpart is aggregate by name
            cp_name = row.get(COL_COUNTERPART_COUNTRY, "").strip()
            if _is_aggregate_counterpart(cp_name):
                stats["rows_aggregate_counterpart"] += 1
                continue

            # Resolve counterpart ISO-3 → ISO-2
            cp_iso2 = _resolve_iso3_to_iso2(cp_iso3)
            if not cp_iso2:
                stats["rows_unmapped_counterpart"] += 1
                continue

            if cp_iso2 in AGGREGATE_PARTNER_ISO2:
                stats["rows_aggregate_counterpart"] += 1
                continue

            # Self-pair check
            if cp_iso2 == reporter_iso2:
                continue

            # Value extraction from year column
            raw_val = row.get(year_col, "").strip()
            if not raw_val or raw_val in ("", "...", "n/a", "C"):
                stats["rows_missing_value"] += 1
                continue

            try:
                value = float(raw_val)
            except (ValueError, TypeError):
                stats["rows_missing_value"] += 1
                continue

            if math.isnan(value) or math.isinf(value):
                stats["rows_missing_value"] += 1
                continue

            if value < 0:
                stats["rows_negative"] += 1
                continue

            if value == 0:
                stats["rows_zero"] += 1
                continue

            # Determine sub-category from INDICATOR
            indicator = row.get(COL_INDICATOR, "").strip()

            raw_records.append(BilateralRecord(
                reporter=reporter_iso2,
                partner=cp_iso2,
                value=value,
                year=target_year,
                source="imf_cpis",
                axis="financial",
                product_desc=indicator,
                unit="USD_MN",
            ))

    stats["raw_records_extracted"] = len(raw_records)

    if not raw_records:
        stats["status"] = IngestionStatus.NO_DATA
        logger.warning(
            "IMF CPIS: no records found for reporter %s (%s) in year %d",
            reporter_iso2, reporter_iso3, target_year,
        )
        return None, stats

    # ---------------------------------------------------------------------------
    # Phase 2: Normalize
    # ---------------------------------------------------------------------------

    normalized, norm_audit = normalize_records(
        raw_records,
        source="imf_cpis",
        axis="financial",
        reporter_filter=reporter_iso2,
    )

    # ---------------------------------------------------------------------------
    # Phase 3: Build BilateralDataset
    # ---------------------------------------------------------------------------

    dataset = BilateralDataset(
        reporter=reporter_iso2,
        axis="financial",
        source="imf_cpis",
        year_range=(target_year, target_year),
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
        "IMF CPIS %s: %d records, %d partners, total=%.2f USD mn",
        reporter_iso2, len(dataset.records), dataset.n_partners, dataset.total_value,
    )

    return dataset, stats
