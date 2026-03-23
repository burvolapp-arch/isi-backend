"""
pipeline.ingest.logistics — Eurostat logistics data ingestion.

Input:
    data/raw/logistics/ directory containing Eurostat SDMX-format CSVs:
        - mar_go_am_XX.csv   — maritime goods by partner and reporting country
        - rail_go_intgong.csv — rail international goods by partner
        - road_go_ia_lgtt.csv — road international goods (loaded/unloaded)
        - road_go_ia_ugtt.csv — road international goods (unloaded)
        - iww_go_atygo.csv   — inland waterway goods

Eurostat SDMX-format:
    DATAFLOW, LAST UPDATE, freq, unit, [mode-specific], geo, TIME_PERIOD, OBS_VALUE, OBS_FLAG

Maritime (mar_go_am_XX.csv):
    Fields: DATAFLOW, LAST UPDATE, freq, unit, seaship, rep_mar, TIME_PERIOD, OBS_VALUE, OBS_FLAG, CONF_STATUS
    - rep_mar = reporting maritime country (ISO-2)
    - seaship = ship type code
    - unit = PC_TOT (share) or THS_T (tonnes)
    - Each file covers one reporter

Rail (rail_go_intgong.csv):
    Fields: DATAFLOW, LAST UPDATE, freq, unit, c_unload, geo, TIME_PERIOD, OBS_VALUE, OBS_FLAG, CONF_STATUS
    - geo = reporting country (ISO-2)
    - c_unload = unloading/partner country (ISO-2)
    - unit = MIO_TKM (million tonne-km) or THS_T

Road (road_go_ia_lgtt.csv / road_go_ia_ugtt.csv):
    Fields: DATAFLOW, LAST UPDATE, freq, tra_type, c_unload, nst07, unit, geo, TIME_PERIOD, OBS_VALUE, OBS_FLAG
    - geo = reporting country (ISO-2)
    - c_unload = partner country (ISO-2)
    - nst07 = commodity group
    - tra_type = HIRE/OWN

Inland waterway (iww_go_atygo.csv):
    Fields: DATAFLOW, LAST UPDATE, freq, tra_cov, nst07, typpack, unit, geo, TIME_PERIOD, OBS_VALUE, OBS_FLAG
    - geo = reporting country (ISO-2)
    - tra_cov = INTL (international) / NAT (national)

ISI perspective:
    Logistics axis measures bilateral freight dependency.
    For each reporter, who are the main freight partners?

Output:
    BilateralDataset per reporter with axis="logistics", source appropriate
"""

from __future__ import annotations

import csv
import math
import logging
from pathlib import Path
from typing import Literal

from pipeline.config import (
    RAW_DIR,
    DEFAULT_YEAR_RANGE,
    AGGREGATE_PARTNER_ISO2,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import normalize_records, NormalizationAudit

logger = logging.getLogger("pipeline.ingest.logistics")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGISTICS_RAW_DIR = RAW_DIR / "logistics"

# Maritime file pattern: mar_go_am_XX.csv where XX is ISO-2 lowercase
MARITIME_PATTERN = "mar_go_am_{reporter}.csv"

# Known aggregate partner codes in Eurostat
EUROSTAT_AGGREGATES = frozenset({
    "EU27_2020", "EU28", "TOTAL", "EXT_EU27_2020", "EXT_EU28",
    "NSP", "UNK", "EFTA",
})


def _is_valid_partner(code: str) -> bool:
    """Check if an Eurostat partner code is a valid bilateral country."""
    if not code:
        return False
    code = code.strip().upper()
    if code in EUROSTAT_AGGREGATES:
        return False
    if code in AGGREGATE_PARTNER_ISO2:
        return False
    # Valid ISO-2: 2 alpha chars
    if len(code) == 2 and code.isalpha():
        return True
    return False


def _parse_eurostat_value(val_str: str) -> float | None:
    """Parse an Eurostat OBS_VALUE, handling flags and special values."""
    val_str = val_str.strip()
    if not val_str or val_str in (":", "c", "n", "u", "d"):
        return None
    # Remove trailing flags (e.g., "56 p" for provisional)
    val_str = val_str.split()[0] if " " in val_str else val_str
    try:
        val = float(val_str)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Maritime ingestion
# ---------------------------------------------------------------------------

def _ingest_maritime(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest maritime freight data from Eurostat.

    Maritime files are per-reporter: mar_go_am_XX.csv
    These contain mode shares and tonnage by partner.
    """
    reporter_lower = reporter_iso2.lower()
    raw_path = LOGISTICS_RAW_DIR / MARITIME_PATTERN.format(reporter=reporter_lower)

    stats = {
        "mode": "maritime",
        "raw_file": str(raw_path),
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    if not raw_path.is_file():
        stats["status"] = "FILE_NOT_FOUND"
        return records, stats

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats["rows_read"] += 1

            # Year filter
            year_str = row.get("TIME_PERIOD", "").strip()
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < year_range[0] or year > year_range[1]:
                continue

            # The maritime files use rep_mar as the reporter
            # and seaship as the ship/partner indicator
            # For bilateral data, we need partner country info
            # These files contain mode shares, not bilateral partner data
            # We extract the reporting country's maritime profile

            unit = row.get("unit", "").strip()
            value = _parse_eurostat_value(row.get("OBS_VALUE", ""))

            if value is None or value <= 0:
                continue

            # Maritime files don't have bilateral partner data directly
            # They contain mode shares (PC_TOT) for the reporter
            # This is used for the logistics mode-share structure
            # Skip bilateral extraction for maritime (handled at mode-share level)

    stats["rows_extracted"] = len(records)
    stats["status"] = "OK" if records else "NO_BILATERAL_DATA"
    return records, stats


# ---------------------------------------------------------------------------
# Rail ingestion
# ---------------------------------------------------------------------------

def _ingest_rail(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest rail freight data from Eurostat rail_go_intgong.csv.

    Schema: freq, unit, c_unload (partner), geo (reporter), TIME_PERIOD, OBS_VALUE
    """
    raw_path = LOGISTICS_RAW_DIR / "rail_go_intgong.csv"

    stats = {
        "mode": "rail",
        "raw_file": str(raw_path),
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    if not raw_path.is_file():
        stats["status"] = "FILE_NOT_FOUND"
        return records, stats

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats["rows_read"] += 1

            # Reporter filter
            geo = row.get("geo", "").strip().upper()
            if geo != reporter_iso2:
                continue

            # Year filter
            year_str = row.get("TIME_PERIOD", "").strip()
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < year_range[0] or year > year_range[1]:
                continue

            # Partner
            partner = row.get("c_unload", "").strip().upper()
            if not _is_valid_partner(partner):
                continue
            if partner == reporter_iso2:
                continue

            # Unit preference: MIO_TKM
            unit = row.get("unit", "").strip()

            value = _parse_eurostat_value(row.get("OBS_VALUE", ""))
            if value is None or value <= 0:
                continue

            records.append(BilateralRecord(
                reporter=reporter_iso2,
                partner=partner,
                value=value,
                year=year,
                source="eurostat_rail",
                axis="logistics",
                unit=unit,
                sub_category="rail",
            ))

    stats["rows_extracted"] = len(records)
    stats["status"] = "OK" if records else "NO_DATA"
    return records, stats


# ---------------------------------------------------------------------------
# Road ingestion
# ---------------------------------------------------------------------------

def _ingest_road(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest road freight data from Eurostat road_go_ia_lgtt.csv and road_go_ia_ugtt.csv.

    Schema: freq, tra_type, c_unload, nst07, unit, geo, TIME_PERIOD, OBS_VALUE
    """
    stats = {
        "mode": "road",
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    # Process both loaded and unloaded files
    for filename in ("road_go_ia_lgtt.csv", "road_go_ia_ugtt.csv"):
        raw_path = LOGISTICS_RAW_DIR / filename

        if not raw_path.is_file():
            continue

        with open(raw_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)

            for row in reader:
                stats["rows_read"] += 1

                # Reporter filter
                geo = row.get("geo", "").strip().upper()
                if geo != reporter_iso2:
                    continue

                # Year filter
                year_str = row.get("TIME_PERIOD", "").strip()
                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    continue
                if year < year_range[0] or year > year_range[1]:
                    continue

                # Partner
                partner = row.get("c_unload", "").strip().upper()
                if not _is_valid_partner(partner):
                    continue
                if partner == reporter_iso2:
                    continue

                unit = row.get("unit", "").strip()
                value = _parse_eurostat_value(row.get("OBS_VALUE", ""))
                if value is None or value <= 0:
                    continue

                # Commodity group
                nst07 = row.get("nst07", "").strip()

                records.append(BilateralRecord(
                    reporter=reporter_iso2,
                    partner=partner,
                    value=value,
                    year=year,
                    source="eurostat_road",
                    axis="logistics",
                    product_code=nst07 if nst07 else None,
                    unit=unit,
                    sub_category="road",
                ))

    stats["rows_extracted"] = len(records)
    stats["status"] = "OK" if records else "NO_DATA"
    return records, stats


# ---------------------------------------------------------------------------
# Inland waterway ingestion
# ---------------------------------------------------------------------------

def _ingest_iww(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest inland waterway freight data from Eurostat iww_go_atygo.csv.

    Schema: freq, tra_cov, nst07, typpack, unit, geo, TIME_PERIOD, OBS_VALUE
    Only international traffic (tra_cov=INTL).
    """
    raw_path = LOGISTICS_RAW_DIR / "iww_go_atygo.csv"

    stats = {
        "mode": "iww",
        "raw_file": str(raw_path),
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    if not raw_path.is_file():
        stats["status"] = "FILE_NOT_FOUND"
        return records, stats

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats["rows_read"] += 1

            # Reporter filter
            geo = row.get("geo", "").strip().upper()
            if geo != reporter_iso2:
                continue

            # International traffic only
            tra_cov = row.get("tra_cov", "").strip()
            if tra_cov != "INTL":
                continue

            # Year filter
            year_str = row.get("TIME_PERIOD", "").strip()
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < year_range[0] or year > year_range[1]:
                continue

            unit = row.get("unit", "").strip()
            value = _parse_eurostat_value(row.get("OBS_VALUE", ""))
            if value is None or value <= 0:
                continue

            nst07 = row.get("nst07", "").strip()

            # IWW data doesn't always have bilateral partner info
            # It contains international traffic volumes for the reporter
            # This contributes to the mode-share structure

    stats["rows_extracted"] = len(records)
    stats["status"] = "OK" if records else "NO_BILATERAL_DATA"
    return records, stats


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_logistics(
    reporter_iso2: str,
    year_range: tuple[int, int] | None = None,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest logistics data for a single ISI reporter.

    Combines data from all available transport modes:
    - Maritime (Eurostat mar_go_am)
    - Rail (Eurostat rail_go_intgong)
    - Road (Eurostat road_go_ia)
    - Inland waterway (Eurostat iww_go_atygo)

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter.
        year_range: (min_year, max_year) inclusive.

    Returns:
        (BilateralDataset or None, stats_dict)
    """
    if year_range is None:
        year_range = DEFAULT_YEAR_RANGE

    stats = {
        "source": "eurostat_logistics",
        "reporter": reporter_iso2,
        "year_range": list(year_range),
        "modes": {},
        "raw_records_extracted": 0,
        "final_records": 0,
        "status": "PENDING",
    }

    logger.info("Ingesting logistics for %s, years=%s", reporter_iso2, year_range)

    all_records: list[BilateralRecord] = []

    # Collect from all modes
    for mode_name, ingest_fn in [
        ("maritime", _ingest_maritime),
        ("rail", _ingest_rail),
        ("road", _ingest_road),
        ("iww", _ingest_iww),
    ]:
        mode_records, mode_stats = ingest_fn(reporter_iso2, year_range)
        stats["modes"][mode_name] = mode_stats
        all_records.extend(mode_records)
        logger.info(
            "  %s: %d records (status=%s)",
            mode_name, len(mode_records), mode_stats.get("status", "?"),
        )

    stats["raw_records_extracted"] = len(all_records)

    if not all_records:
        stats["status"] = "NO_DATA"
        logger.warning("Logistics: no bilateral records for %s", reporter_iso2)
        return None, stats

    # ---------------------------------------------------------------------------
    # Normalize
    # ---------------------------------------------------------------------------

    normalized, norm_audit = normalize_records(
        all_records,
        source="eurostat_logistics",
        axis="logistics",
        reporter_filter=reporter_iso2,
    )

    # ---------------------------------------------------------------------------
    # Build BilateralDataset
    # ---------------------------------------------------------------------------

    dataset = BilateralDataset(
        reporter=reporter_iso2,
        axis="logistics",
        source="eurostat_logistics",
        year_range=year_range,
    )
    for rec in normalized:
        dataset.add_record(rec)

    dataset.compute_metadata()
    stats["final_records"] = len(dataset.records)
    stats["n_partners"] = dataset.n_partners
    stats["total_value"] = dataset.total_value
    stats["normalization"] = norm_audit.to_dict()
    stats["status"] = "OK" if dataset.records else "EMPTY"

    logger.info(
        "Logistics %s: %d records, %d partners",
        reporter_iso2, len(dataset.records), dataset.n_partners,
    )

    return dataset, stats
