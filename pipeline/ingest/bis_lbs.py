"""
pipeline.ingest.bis_lbs — BIS Locational Banking Statistics ingestion.

Input:
    data/raw/finance/bis_lbs_2024_raw.csv
    Pre-filtered SDMX-format CSV with fields:
        FREQ, L_MEASURE, L_POSITION, L_INSTR, L_DENOM, L_CURR_TYPE,
        L_PARENT_CTY, L_REP_BANK_TYPE, L_CP_SECTOR, L_POS_TYPE,
        L_REP_CTY, L_CP_COUNTRY, TIME_PERIOD, OBS_VALUE

Schema (BIS SDMX fields):
    L_REP_CTY     = reporting (creditor) country, ISO-2
    L_CP_COUNTRY  = counterparty (debtor) country, ISO-2
    OBS_VALUE     = claims value in USD millions

Perspective (ISI methodology Section 6):
    For ISI: reporter_i = debtor country (the one whose dependency we measure)
                          = L_CP_COUNTRY
             partner_j  = creditor country
                          = L_REP_CTY

    This is the INWARD perspective: for each ISI reporter, we want
    "who holds claims ON this country?" → creditor countries are the partners.

Output:
    BilateralDataset per reporter with axis="financial", source="bis_lbs"

Integrity checks:
    - Verifies SDMX pre-filter values on every row
    - Rejects aggregate/non-country codes
    - Rejects self-pairs
    - Zero/negative values dropped
    - Hard fail if zero rows survive
"""

from __future__ import annotations

import csv
import math
import logging
from pathlib import Path

from pipeline.config import (
    RAW_DIR,
    BIS_QUARTER,
    BIS_TO_ISO2,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import normalize_records, NormalizationAudit, is_aggregate_partner
from pipeline.status import IngestionStatus

logger = logging.getLogger("pipeline.ingest.bis_lbs")

# ---------------------------------------------------------------------------
# BIS SDMX field names and expected pre-filter values
# ---------------------------------------------------------------------------

COL_FREQ = "FREQ"
COL_MEASURE = "L_MEASURE"
COL_POSITION = "L_POSITION"
COL_INSTR = "L_INSTR"
COL_DENOM = "L_DENOM"
COL_CURR_TYPE = "L_CURR_TYPE"
COL_CP_SECTOR = "L_CP_SECTOR"
COL_REP_CTY = "L_REP_CTY"
COL_CP_COUNTRY = "L_CP_COUNTRY"
COL_TIME_PERIOD = "TIME_PERIOD"
COL_OBS_VALUE = "OBS_VALUE"

EXPECTED_FILTERS = {
    COL_FREQ: "Q",
    COL_MEASURE: "S",
    COL_POSITION: "C",
    COL_INSTR: "A",
    COL_DENOM: "TO1",
    COL_CURR_TYPE: "A",
    COL_CP_SECTOR: "A",
}


def _is_country_code(code: str) -> bool:
    """Return True if code looks like an ISO-2 country code."""
    return len(code) == 2 and code.isalpha()


def _is_aggregate(code: str) -> bool:
    """Check if a BIS code is an aggregate."""
    if code in BIS_TO_ISO2:
        return BIS_TO_ISO2[code] == "__AGGREGATE__"
    if is_aggregate_partner(code):
        return True
    if not _is_country_code(code):
        return True
    return False


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_bis_lbs(
    reporter_iso2: str,
    raw_path: Path | None = None,
    period: str | None = None,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest BIS LBS data for a single ISI reporter.

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter country.
        raw_path: Override path to raw BIS CSV. Default: data/raw/finance/bis_lbs_2024_raw.csv
        period: Override period filter. Default: config.BIS_QUARTER

    Returns:
        (BilateralDataset or None, stats_dict)
        None if no valid data found for this reporter.

    The BIS perspective is INWARD: we look for L_CP_COUNTRY == reporter_iso2
    and collect all L_REP_CTY values as partners (creditors).
    """
    if raw_path is None:
        raw_path = RAW_DIR / "finance" / "bis_lbs_2024_raw.csv"
    if period is None:
        period = BIS_QUARTER

    stats = {
        "source": "bis_lbs",
        "reporter": reporter_iso2,
        "raw_file": str(raw_path),
        "period": period,
        "rows_read": 0,
        "rows_integrity_fail": 0,
        "rows_period_mismatch": 0,
        "rows_aggregate_excluded": 0,
        "rows_self_pair": 0,
        "rows_missing_value": 0,
        "rows_negative": 0,
        "rows_zero": 0,
        "rows_reporter_mismatch": 0,
        "raw_records_extracted": 0,
        "final_records": 0,
        "status": IngestionStatus.PENDING,
    }

    if not raw_path.is_file():
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        logger.error("BIS LBS raw file not found: %s", raw_path)
        return None, stats

    # Parse year from period (e.g., "2024-Q4" → 2024)
    try:
        year = int(period.split("-")[0])
    except (ValueError, IndexError):
        year = 2024

    logger.info("Ingesting BIS LBS for %s, period=%s", reporter_iso2, period)

    # ---------------------------------------------------------------------------
    # Phase 1: Streaming parse — extract raw bilateral records
    # ---------------------------------------------------------------------------

    raw_records: list[BilateralRecord] = []

    try:
        f = open(raw_path, "r", encoding="utf-8", newline="")
    except (UnicodeDecodeError, OSError) as exc:
        stats["status"] = IngestionStatus.MALFORMED_FILE
        stats["error"] = str(exc)
        logger.error("BIS LBS: cannot open %s: %s", raw_path, exc)
        return None, stats

    try:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # Guard: verify required columns exist
        required_cols = {COL_REP_CTY, COL_CP_COUNTRY, COL_TIME_PERIOD, COL_OBS_VALUE}
        missing_cols = required_cols - set(fieldnames)
        if missing_cols:
            stats["status"] = IngestionStatus.MALFORMED_FILE
            stats["error"] = f"Missing required columns: {sorted(missing_cols)}"
            logger.error(
                "BIS LBS: malformed CSV — missing columns %s. Found: %s",
                sorted(missing_cols), fieldnames[:15],
            )
            return None, stats

        for row in reader:
            stats["rows_read"] += 1

            # Verify SDMX pre-filter values
            integrity_ok = True
            for col, expected in EXPECTED_FILTERS.items():
                if row.get(col, "").strip() != expected:
                    integrity_ok = False
                    break
            if not integrity_ok:
                stats["rows_integrity_fail"] += 1
                continue

            # Period filter
            row_period = row.get(COL_TIME_PERIOD, "").strip()
            if row_period != period:
                stats["rows_period_mismatch"] += 1
                continue

            # Extract country codes
            rep_cty = row.get(COL_REP_CTY, "").strip()  # creditor
            cp_country = row.get(COL_CP_COUNTRY, "").strip()  # debtor

            # Aggregate/invalid code check
            if _is_aggregate(rep_cty) or _is_aggregate(cp_country):
                stats["rows_aggregate_excluded"] += 1
                continue

            if not _is_country_code(rep_cty) or not _is_country_code(cp_country):
                stats["rows_aggregate_excluded"] += 1
                continue

            # Self-pair check
            if rep_cty == cp_country:
                stats["rows_self_pair"] += 1
                continue

            # ISI perspective: reporter = debtor = cp_country
            # We only want rows where cp_country == our reporter
            if cp_country != reporter_iso2:
                stats["rows_reporter_mismatch"] += 1
                continue

            # Value extraction
            raw_val = row.get(COL_OBS_VALUE, "").strip()
            if not raw_val:
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

            # Create canonical record
            # reporter = ISI reporter (debtor), partner = creditor
            raw_records.append(BilateralRecord(
                reporter=cp_country,   # the debtor (ISI reporter)
                partner=rep_cty,       # the creditor (ISI partner)
                value=value,
                year=year,
                source="bis_lbs",
                axis="financial",
                unit="USD_MN",
            ))
    except (csv.Error, UnicodeDecodeError) as exc:
        stats["status"] = IngestionStatus.MALFORMED_FILE
        stats["error"] = f"CSV parse error at row {stats['rows_read']}: {exc}"
        logger.error("BIS LBS: CSV parse error in %s: %s", raw_path, exc)
        return None, stats
    finally:
        f.close()

    stats["raw_records_extracted"] = len(raw_records)

    if not raw_records:
        stats["status"] = IngestionStatus.NO_DATA
        logger.warning(
            "BIS LBS: no records found for reporter %s in period %s",
            reporter_iso2, period,
        )
        return None, stats

    # ---------------------------------------------------------------------------
    # Phase 2: Normalize
    # ---------------------------------------------------------------------------

    normalized, norm_audit = normalize_records(
        raw_records,
        source="bis_lbs",
        axis="financial",
        reporter_filter=reporter_iso2,
    )

    # ---------------------------------------------------------------------------
    # Phase 3: Build BilateralDataset
    # ---------------------------------------------------------------------------

    dataset = BilateralDataset(
        reporter=reporter_iso2,
        axis="financial",
        source="bis_lbs",
        year_range=(year, year),
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
        "BIS LBS %s: %d records, %d partners, total=%.2f USD mn",
        reporter_iso2, len(dataset.records), dataset.n_partners, dataset.total_value,
    )

    return dataset, stats


# ---------------------------------------------------------------------------
# Batch ingestion — all reporters from one raw file
# ---------------------------------------------------------------------------

def ingest_bis_lbs_all_reporters(
    raw_path: Path | None = None,
    period: str | None = None,
) -> dict[str, list[BilateralRecord]]:
    """Parse ALL bilateral records from the BIS LBS raw file.

    Returns a dict: {counterparty_iso2: [BilateralRecord, ...]}
    This is useful for batch processing where we want to avoid
    reading the file once per reporter.
    """
    if raw_path is None:
        raw_path = RAW_DIR / "finance" / "bis_lbs_2024_raw.csv"
    if period is None:
        period = BIS_QUARTER

    if not raw_path.is_file():
        logger.error("BIS LBS raw file not found: %s", raw_path)
        return {}

    try:
        year = int(period.split("-")[0])
    except (ValueError, IndexError):
        year = 2024

    by_reporter: dict[str, list[BilateralRecord]] = {}

    try:
        with open(raw_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Quick integrity check
                if row.get(COL_FREQ, "").strip() != "Q":
                    continue
                if row.get(COL_TIME_PERIOD, "").strip() != period:
                    continue

                rep_cty = row.get(COL_REP_CTY, "").strip()
                cp_country = row.get(COL_CP_COUNTRY, "").strip()

                if _is_aggregate(rep_cty) or _is_aggregate(cp_country):
                    continue
                if not _is_country_code(rep_cty) or not _is_country_code(cp_country):
                    continue
                if rep_cty == cp_country:
                    continue

                raw_val = row.get(COL_OBS_VALUE, "").strip()
                if not raw_val:
                    continue
                try:
                    value = float(raw_val)
                except (ValueError, TypeError):
                    continue
                if math.isnan(value) or math.isinf(value) or value <= 0:
                    continue

                rec = BilateralRecord(
                    reporter=cp_country,
                    partner=rep_cty,
                    value=value,
                    year=year,
                    source="bis_lbs",
                    axis="financial",
                    unit="USD_MN",
                )
                by_reporter.setdefault(cp_country, []).append(rec)
    except (csv.Error, UnicodeDecodeError, OSError) as exc:
        logger.error("BIS LBS batch: CSV parse error in %s: %s", raw_path, exc)
        return by_reporter  # return whatever was parsed before the error

    logger.info(
        "BIS LBS batch: %d reporters, %d total records",
        len(by_reporter),
        sum(len(v) for v in by_reporter.values()),
    )

    return by_reporter
