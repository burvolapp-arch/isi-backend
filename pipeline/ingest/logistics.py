"""
pipeline.ingest.logistics — Logistics freight data ingestion.

Data source coverage:
    EU-27 countries → Eurostat (maritime, rail, road, IWW)
    Non-EU countries → STRUCTURAL_LIMITATION (no bilateral logistics source)

Eurostat SDMX-format CSVs:
    - mar_go_am_XX.csv   — maritime goods by partner and reporting country
    - rail_go_intgong.csv — rail international goods by partner
    - road_go_ia_lgtt.csv — road international goods (loaded)
    - road_go_ia_ugtt.csv — road international goods (unloaded)
    - iww_go_atygo.csv   — inland waterway goods

CRITICAL CONSTRAINT:
    Eurostat ONLY covers EU member states. For non-EU countries (JP, US, CN,
    AU, GB, KR, NO), there is no equivalent bilateral logistics source
    available for free download. This is a STRUCTURAL_LIMITATION, not a data
    error. The pipeline explicitly documents this rather than failing silently
    or returning bogus data.

Output:
    BilateralDataset per reporter with axis="logistics", source appropriate
"""

from __future__ import annotations

import csv
import math
import logging
from pathlib import Path

from pipeline.config import (
    RAW_DIR,
    DEFAULT_YEAR_RANGE,
    EU27_ISO2,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import normalize_records, is_aggregate_partner
from pipeline.status import IngestionStatus

logger = logging.getLogger("pipeline.ingest.logistics")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGISTICS_RAW_DIR = RAW_DIR / "logistics"
MARITIME_PATTERN = "mar_go_am_{reporter}.csv"

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
    if is_aggregate_partner(code):
        return False
    if len(code) == 2 and code.isalpha():
        return True
    return False


def _parse_eurostat_value(val_str: str) -> float | None:
    """Parse an Eurostat OBS_VALUE, handling flags and special values."""
    val_str = val_str.strip()
    if not val_str or val_str in (":", "c", "n", "u", "d"):
        return None
    val_str = val_str.split()[0] if " " in val_str else val_str
    try:
        val = float(val_str)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# EU coverage guard
# ---------------------------------------------------------------------------

def _is_eu_country(iso2: str) -> bool:
    """Check if a country is covered by Eurostat logistics data."""
    return iso2.upper() in EU27_ISO2


# ---------------------------------------------------------------------------
# Maritime ingestion
# ---------------------------------------------------------------------------

def _ingest_maritime(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest maritime freight data from Eurostat (per-reporter files)."""
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
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        return records, stats

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows_read"] += 1

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

            # Maritime files contain mode shares, not bilateral partner data
            # (they aggregate shipping by type, not by origin/destination country)

    stats["rows_extracted"] = len(records)
    stats["status"] = IngestionStatus.OK if records else IngestionStatus.NO_BILATERAL_DATA
    return records, stats


# ---------------------------------------------------------------------------
# Rail ingestion
# ---------------------------------------------------------------------------

def _ingest_rail(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest rail freight data from Eurostat rail_go_intgong.csv."""
    raw_path = LOGISTICS_RAW_DIR / "rail_go_intgong.csv"

    stats = {
        "mode": "rail",
        "raw_file": str(raw_path),
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    if not raw_path.is_file():
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        return records, stats

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows_read"] += 1

            geo = row.get("geo", "").strip().upper()
            if geo != reporter_iso2:
                continue

            year_str = row.get("TIME_PERIOD", "").strip()
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < year_range[0] or year > year_range[1]:
                continue

            partner = row.get("c_unload", "").strip().upper()
            if not _is_valid_partner(partner):
                continue
            if partner == reporter_iso2:
                continue

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
    stats["status"] = IngestionStatus.OK if records else IngestionStatus.NO_DATA
    return records, stats


# ---------------------------------------------------------------------------
# Road ingestion
# ---------------------------------------------------------------------------

def _ingest_road(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest road freight data from Eurostat."""
    stats = {
        "mode": "road",
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    for filename in ("road_go_ia_lgtt.csv", "road_go_ia_ugtt.csv"):
        raw_path = LOGISTICS_RAW_DIR / filename
        if not raw_path.is_file():
            continue

        with open(raw_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats["rows_read"] += 1

                geo = row.get("geo", "").strip().upper()
                if geo != reporter_iso2:
                    continue

                year_str = row.get("TIME_PERIOD", "").strip()
                try:
                    year = int(year_str)
                except (ValueError, TypeError):
                    continue
                if year < year_range[0] or year > year_range[1]:
                    continue

                partner = row.get("c_unload", "").strip().upper()
                if not _is_valid_partner(partner):
                    continue
                if partner == reporter_iso2:
                    continue

                unit = row.get("unit", "").strip()
                value = _parse_eurostat_value(row.get("OBS_VALUE", ""))
                if value is None or value <= 0:
                    continue

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
    stats["status"] = IngestionStatus.OK if records else IngestionStatus.NO_DATA
    return records, stats


# ---------------------------------------------------------------------------
# Inland waterway ingestion
# ---------------------------------------------------------------------------

def _ingest_iww(
    reporter_iso2: str,
    year_range: tuple[int, int],
) -> tuple[list[BilateralRecord], dict]:
    """Ingest inland waterway freight data from Eurostat."""
    raw_path = LOGISTICS_RAW_DIR / "iww_go_atygo.csv"

    stats = {
        "mode": "iww",
        "raw_file": str(raw_path),
        "rows_read": 0,
        "rows_extracted": 0,
    }

    records: list[BilateralRecord] = []

    if not raw_path.is_file():
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        return records, stats

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows_read"] += 1

            geo = row.get("geo", "").strip().upper()
            if geo != reporter_iso2:
                continue

            tra_cov = row.get("tra_cov", "").strip()
            if tra_cov != "INTL":
                continue

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

            # IWW data: international traffic volumes (no bilateral partner)

    stats["rows_extracted"] = len(records)
    stats["status"] = IngestionStatus.OK if records else IngestionStatus.NO_BILATERAL_DATA
    return records, stats


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_logistics(
    reporter_iso2: str,
    year_range: tuple[int, int] | None = None,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest logistics data for a single ISI reporter.

    COVERAGE GUARD: Eurostat only covers EU-27. For non-EU countries,
    this function returns (None, stats) with status=STRUCTURAL_LIMITATION
    instead of returning NO_DATA or FILE_NOT_FOUND.

    Combines data from available transport modes:
    - Rail (Eurostat rail_go_intgong)
    - Road (Eurostat road_go_ia)
    - Maritime (Eurostat mar_go_am — mode shares only, no bilateral)
    - IWW (Eurostat iww_go_atygo — no bilateral partner data)

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter.
        year_range: (min_year, max_year) inclusive.

    Returns:
        (BilateralDataset or None, stats_dict)
    """
    if year_range is None:
        year_range = DEFAULT_YEAR_RANGE

    stats: dict = {
        "source": "eurostat_logistics",
        "reporter": reporter_iso2,
        "year_range": list(year_range),
        "modes": {},
        "raw_records_extracted": 0,
        "final_records": 0,
        "status": IngestionStatus.PENDING,
    }

    # ── EU-only coverage guard ─────────────────────────────────────────────
    if not _is_eu_country(reporter_iso2):
        stats["status"] = IngestionStatus.STRUCTURAL_LIMITATION
        stats["limitation_reason"] = (
            f"Eurostat logistics data covers EU-27 only. "
            f"{reporter_iso2} is not an EU member state. "
            f"No freely available bilateral logistics source exists "
            f"for this country. This is a known structural gap, not a pipeline error."
        )
        logger.info(
            "Logistics %s: STRUCTURAL_LIMITATION — Eurostat covers EU-27 only",
            reporter_iso2,
        )
        return None, stats

    # ── EU country: proceed with Eurostat ingestion ────────────────────────
    logger.info("Ingesting logistics for %s (EU), years=%s", reporter_iso2, year_range)

    all_records: list[BilateralRecord] = []

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
        stats["status"] = IngestionStatus.NO_DATA
        logger.warning("Logistics: no bilateral records for %s", reporter_iso2)
        return None, stats

    # Normalize
    normalized, norm_audit = normalize_records(
        all_records,
        source="eurostat_logistics",
        axis="logistics",
        reporter_filter=reporter_iso2,
    )

    # Build dataset
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
    stats["status"] = IngestionStatus.OK if dataset.records else IngestionStatus.NO_DATA

    logger.info(
        "Logistics %s: %d records, %d partners",
        reporter_iso2, len(dataset.records), dataset.n_partners,
    )

    return dataset, stats
