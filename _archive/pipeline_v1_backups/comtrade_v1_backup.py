"""
pipeline.ingest.comtrade — UN Comtrade bilateral trade data ingestion.

Input:
    data/raw/comtrade/ directory containing bulk download CSVs:
        - comtrade_semiconductors_2022_2024.csv (tech)
        - comtrade_critical_materials_2022_2024.csv (critical_inputs)
        - comtrade_energy_fuels_2022_2024.csv (energy)

UN Comtrade CSV schema (bulk download):
    Classification, Year, Period, PeriodDesc, AggLevel,
    IsLeaf, ReporterCode, ReporterISO, ReporterDesc,
    PartnerCode, PartnerISO, PartnerDesc,
    FlowCode, FlowDesc, CmdCode, CmdDesc,
    QtyUnitCode, QtyUnitAbbr, Qty, AltQtyUnitCode,
    AltQtyUnitAbbr, AltQty, NetWgt, GrossWgt,
    Cifvalue, Fobvalue, PrimaryValue, LegacyEstimation,
    IsReported

Key fields:
    ReporterISO  = reporter country (ISO-3 alpha)
    PartnerISO   = partner country (ISO-3 alpha)
    FlowCode     = M (imports) or X (exports)
    CmdCode      = HS commodity code
    PrimaryValue = trade value in USD

ISI perspective:
    Import flows (FlowCode=M): reporter imports FROM partner
    This gives bilateral import dependency.

Parameterization:
    Each axis uses different HS code sets:
    - energy:          {2701, 2709, 2710, 2711, 2716}
    - technology:      {8541, 8542}
    - critical_inputs: {2504, 2602, 2605, 2610, 2611, 2612, 2614,
                        2615, 2804, 2825, 2836, 2846, 7110, 8105, 8108}

Output:
    BilateralDataset per reporter/axis with source="un_comtrade"
"""

from __future__ import annotations

import csv
import math
import logging
from pathlib import Path

from pipeline.config import (
    RAW_DIR,
    DEFAULT_YEAR_RANGE,
    ISO3_TO_ISO2,
    ENERGY_HS_CODES,
    TECH_HS_CODES,
    CRITICAL_INPUTS_HS_CODES,
    AGGREGATE_PARTNER_NAMES,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import (
    normalize_records,
    NormalizationAudit,
    map_hs_to_category,
)

logger = logging.getLogger("pipeline.ingest.comtrade")

# ---------------------------------------------------------------------------
# Comtrade field names (case-insensitive lookup)
# ---------------------------------------------------------------------------

# Primary field names (Comtrade bulk CSV)
FLD_REPORTER_ISO = "ReporterISO"
FLD_PARTNER_ISO = "PartnerISO"
FLD_FLOW_CODE = "FlowCode"
FLD_CMD_CODE = "CmdCode"
FLD_CMD_DESC = "CmdDesc"
FLD_YEAR = "Year"
FLD_PRIMARY_VALUE = "PrimaryValue"
FLD_CIF_VALUE = "Cifvalue"

# Flow code for imports
FLOW_IMPORTS = "M"
FLOW_IMPORTS_NUMERIC = "1"


def _resolve_comtrade_field(row: dict, field_name: str) -> str:
    """Case-insensitive field lookup for Comtrade CSVs."""
    # Try exact match first
    if field_name in row:
        return row[field_name].strip()
    # Try lowercase variants
    lower = field_name.lower()
    for key in row:
        if key.lower() == lower:
            return row[key].strip()
    return ""


def _iso3_to_iso2(iso3: str) -> str | None:
    """Resolve ISO-3 to ISO-2. Returns None for unmapped/aggregate."""
    if not iso3 or len(iso3) < 2:
        return None

    iso3_upper = iso3.upper()

    # Direct mapping
    if iso3_upper in ISO3_TO_ISO2:
        return ISO3_TO_ISO2[iso3_upper]

    # Already ISO-2?
    if len(iso3) == 2 and iso3.isalpha():
        return iso3.upper()

    # Known aggregate codes
    if iso3_upper in ("WLD", "W00", "ALL", "XXX"):
        return None

    return None


def _matches_hs_set(cmd_code: str, hs_codes: frozenset[str]) -> bool:
    """Check if a commodity code matches any prefix in the HS code set."""
    for prefix in hs_codes:
        if cmd_code.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# Axis-specific configuration
# ---------------------------------------------------------------------------

AXIS_CONFIG = {
    "energy": {
        "hs_codes": ENERGY_HS_CODES,
        "raw_filename": "comtrade_energy_fuels_2022_2024.csv",
        "flow": "M",
    },
    "technology": {
        "hs_codes": TECH_HS_CODES,
        "raw_filename": "comtrade_semiconductors_2022_2024.csv",
        "flow": "M",
    },
    "critical_inputs": {
        "hs_codes": CRITICAL_INPUTS_HS_CODES,
        "raw_filename": "comtrade_critical_materials_2022_2024.csv",
        "flow": "M",
    },
}


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_comtrade(
    reporter_iso2: str,
    axis: str,
    raw_path: Path | None = None,
    year_range: tuple[int, int] | None = None,
    hs_codes: frozenset[str] | None = None,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest UN Comtrade data for a single reporter and axis.

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter.
        axis: Axis slug ("energy", "technology", "critical_inputs").
        raw_path: Override path to raw Comtrade CSV.
        year_range: (min_year, max_year) inclusive.
        hs_codes: Override HS code prefix set.

    Returns:
        (BilateralDataset or None, stats_dict)
    """
    if axis not in AXIS_CONFIG:
        raise ValueError(f"Unsupported axis for Comtrade: {axis}")

    cfg = AXIS_CONFIG[axis]

    if raw_path is None:
        raw_path = RAW_DIR / "comtrade" / cfg["raw_filename"]
    if year_range is None:
        year_range = DEFAULT_YEAR_RANGE
    if hs_codes is None:
        hs_codes = cfg["hs_codes"]

    # Convert reporter ISO-2 to ISO-3 for matching
    from pipeline.config import ISO2_TO_ISO3
    reporter_iso3 = ISO2_TO_ISO3.get(reporter_iso2, "")

    stats = {
        "source": "un_comtrade",
        "reporter": reporter_iso2,
        "reporter_iso3": reporter_iso3,
        "axis": axis,
        "raw_file": str(raw_path),
        "year_range": list(year_range),
        "hs_code_count": len(hs_codes),
        "rows_read": 0,
        "rows_flow_filtered": 0,
        "rows_year_filtered": 0,
        "rows_hs_filtered": 0,
        "rows_reporter_mismatch": 0,
        "rows_unmapped_partner": 0,
        "rows_aggregate_partner": 0,
        "rows_missing_value": 0,
        "rows_zero_negative": 0,
        "raw_records_extracted": 0,
        "final_records": 0,
        "status": "PENDING",
    }

    if not raw_path.is_file():
        stats["status"] = "FILE_NOT_FOUND"
        logger.error("Comtrade raw file not found: %s", raw_path)
        return None, stats

    logger.info(
        "Ingesting Comtrade for %s (%s), axis=%s, years=%s",
        reporter_iso2, reporter_iso3, axis, year_range,
    )

    raw_records: list[BilateralRecord] = []

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats["rows_read"] += 1

            # Flow filter (imports only)
            flow_code = _resolve_comtrade_field(row, FLD_FLOW_CODE)
            if flow_code not in (FLOW_IMPORTS, FLOW_IMPORTS_NUMERIC):
                stats["rows_flow_filtered"] += 1
                continue

            # Year filter
            year_str = _resolve_comtrade_field(row, FLD_YEAR)
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < year_range[0] or year > year_range[1]:
                stats["rows_year_filtered"] += 1
                continue

            # HS code filter
            cmd_code = _resolve_comtrade_field(row, FLD_CMD_CODE)
            if hs_codes and not _matches_hs_set(cmd_code, hs_codes):
                stats["rows_hs_filtered"] += 1
                continue

            # Reporter match
            reporter_iso3_raw = _resolve_comtrade_field(row, FLD_REPORTER_ISO)
            rep_iso2 = _iso3_to_iso2(reporter_iso3_raw)

            if rep_iso2 != reporter_iso2:
                stats["rows_reporter_mismatch"] += 1
                continue

            # Partner resolution
            partner_iso3_raw = _resolve_comtrade_field(row, FLD_PARTNER_ISO)
            partner_iso2 = _iso3_to_iso2(partner_iso3_raw)

            if partner_iso2 is None:
                stats["rows_unmapped_partner"] += 1
                continue

            # Self-pair check
            if partner_iso2 == reporter_iso2:
                continue

            # Value extraction
            value_str = _resolve_comtrade_field(row, FLD_PRIMARY_VALUE)
            if not value_str:
                value_str = _resolve_comtrade_field(row, FLD_CIF_VALUE)
            try:
                value = float(value_str) if value_str else 0.0
            except (ValueError, TypeError):
                value = 0.0

            if math.isnan(value) or math.isinf(value) or value <= 0:
                stats["rows_zero_negative"] += 1
                continue

            # Map HS code to sub-category
            sub_cat = map_hs_to_category(cmd_code, axis)
            cmd_desc = _resolve_comtrade_field(row, FLD_CMD_DESC)

            raw_records.append(BilateralRecord(
                reporter=reporter_iso2,
                partner=partner_iso2,
                value=value,
                year=year,
                source="un_comtrade",
                axis=axis,
                product_code=cmd_code[:6],
                product_desc=cmd_desc[:100] if cmd_desc else None,
                unit="USD",
                sub_category=sub_cat,
            ))

    stats["raw_records_extracted"] = len(raw_records)

    if not raw_records:
        stats["status"] = "NO_DATA"
        logger.warning(
            "Comtrade: no records for %s, axis=%s, years=%s",
            reporter_iso2, axis, year_range,
        )
        return None, stats

    # ---------------------------------------------------------------------------
    # Normalize
    # ---------------------------------------------------------------------------

    normalized, norm_audit = normalize_records(
        raw_records,
        source="un_comtrade",
        axis=axis,
        reporter_filter=reporter_iso2,
    )

    # ---------------------------------------------------------------------------
    # Build BilateralDataset
    # ---------------------------------------------------------------------------

    dataset = BilateralDataset(
        reporter=reporter_iso2,
        axis=axis,
        source="un_comtrade",
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
        "Comtrade %s/%s: %d records, %d partners, total=%.2f",
        reporter_iso2, axis, len(dataset.records), dataset.n_partners, dataset.total_value,
    )

    return dataset, stats
