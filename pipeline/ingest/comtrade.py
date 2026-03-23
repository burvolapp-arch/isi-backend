"""
pipeline.ingest.comtrade — UN Comtrade bilateral trade data ingestion.

Data acquisition strategy (priority order):
    1. Cached API responses in data/raw/comtrade_cache/
    2. Local CSV files in data/raw/comtrade/
    3. Live UN Comtrade API download (with caching + retry)

For EU-27 countries, Eurostat Comext bulk data is preferred (separate module).
For non-EU countries (JP, US, CN, etc.), this module downloads from the
UN Comtrade API or reads cached responses.

UN Comtrade API v1 (public tier):
    Base:    https://comtradeapi.un.org/public/v1/preview/C/A/HS
    Auth:    None (public) — rate-limited ~100 req/day
    Params:  reporterCode, period, cmdCode, flowCode
    Returns: JSON with {"data": [...], "count": N, ...}

Key response fields:
    reporterISO   = ISO-3 alpha
    partnerISO    = ISO-3 alpha
    flowCode      = M (imports) / X (exports)
    cmdCode       = HS commodity code
    cmdDesc       = commodity description
    primaryValue  = trade value in USD
    period        = year (int)

ISI perspective:
    Import flows (flowCode=M): reporter imports FROM partner
    → bilateral import dependency

Axis HS code sets:
    energy:          {2701, 2709, 2710, 2711, 2716}
    technology:      {8541, 8542}
    critical_inputs: {2504, 2602, 2605, 2610, 2611, 2612, 2614,
                      2615, 2804, 2825, 2836, 2846, 7110, 8105, 8108}

Output:
    BilateralDataset per reporter/axis with source="un_comtrade"
"""

from __future__ import annotations

import csv
import json
import math
import logging
import ssl
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

from pipeline.config import (
    RAW_DIR,
    DEFAULT_YEAR_RANGE,
    ISO3_TO_ISO2,
    ISO2_TO_ISO3,
    ENERGY_HS_CODES,
    TECH_HS_CODES,
    CRITICAL_INPUTS_HS_CODES,
    COMTRADE_NUM_TO_ISO2,
    COMTRADE_AGGREGATE_CODES,
)
from pipeline.schema import BilateralRecord, BilateralDataset
from pipeline.normalize import (
    normalize_records,
    map_hs_to_category,
)
from pipeline.status import IngestionStatus

logger = logging.getLogger("pipeline.ingest.comtrade")

# ---------------------------------------------------------------------------
# UN Comtrade API configuration
# ---------------------------------------------------------------------------

COMTRADE_API_BASE = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
COMTRADE_CACHE_DIR = RAW_DIR / "comtrade_cache"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 60
RATE_LIMIT_SLEEP = 1.5  # seconds between API requests

# SSL context — use certifi CA bundle if system certs are missing
def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context with proper CA certificates."""
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass  # fall back to system certs
    return ctx

_SSL_CTX = _build_ssl_context()

# Reverse mapping: ISO-2 → Comtrade numeric reporter code
ISO2_TO_COMTRADE_NUM: dict[str, int] = {v: k for k, v in COMTRADE_NUM_TO_ISO2.items()}


# ---------------------------------------------------------------------------
# Local CSV field names
# ---------------------------------------------------------------------------

FLD_REPORTER_ISO = "ReporterISO"
FLD_PARTNER_ISO = "PartnerISO"
FLD_FLOW_CODE = "FlowCode"
FLD_CMD_CODE = "CmdCode"
FLD_CMD_DESC = "CmdDesc"
FLD_YEAR = "Year"
FLD_PRIMARY_VALUE = "PrimaryValue"
FLD_CIF_VALUE = "Cifvalue"

FLOW_IMPORTS = "M"
FLOW_IMPORTS_NUMERIC = "1"


# ---------------------------------------------------------------------------
# Axis configuration
# ---------------------------------------------------------------------------

AXIS_CONFIG = {
    "energy": {
        "hs_codes": ENERGY_HS_CODES,
        "raw_filename": "comtrade_energy_fuels_2022_2024.csv",
        "flow": "M",
        "description": "Energy fuels (coal, oil, gas, electricity)",
    },
    "technology": {
        "hs_codes": TECH_HS_CODES,
        "raw_filename": "comtrade_semiconductors_2022_2024.csv",
        "flow": "M",
        "description": "Semiconductors and integrated circuits",
    },
    "critical_inputs": {
        "hs_codes": CRITICAL_INPUTS_HS_CODES,
        "raw_filename": "comtrade_critical_materials_2022_2024.csv",
        "flow": "M",
        "description": "Critical raw materials and rare earths",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_comtrade_field(row: dict, field_name: str) -> str:
    """Case-insensitive field lookup for Comtrade CSVs/JSON."""
    if field_name in row:
        val = row[field_name]
        return str(val).strip() if val is not None else ""
    lower = field_name.lower()
    for key in row:
        if key.lower() == lower:
            val = row[key]
            return str(val).strip() if val is not None else ""
    return ""


def _iso3_to_iso2(iso3: str) -> str | None:
    """Resolve ISO-3 to ISO-2. Returns None for unmapped/aggregate."""
    if not iso3 or len(iso3) < 2:
        return None
    iso3_upper = iso3.upper()
    if iso3_upper in ISO3_TO_ISO2:
        return ISO3_TO_ISO2[iso3_upper]
    if len(iso3) == 2 and iso3.isalpha():
        return iso3.upper()
    if iso3_upper in ("WLD", "W00", "ALL", "XXX", "NA", ""):
        return None
    return None


def _resolve_country(row: dict, iso_key: str, code_key: str) -> str | None:
    """Resolve a country from API row, trying ISO first then numeric code.

    The Comtrade preview API often returns null for ISO fields but always
    provides numeric codes.  We try the ISO field first; if that fails we
    fall back to the numeric code → COMTRADE_NUM_TO_ISO2 mapping.
    """
    # 1. Try ISO field (works for local CSVs and some API endpoints)
    iso_val = row.get(iso_key) or row.get(iso_key[0].upper() + iso_key[1:])
    if iso_val is not None:
        iso_str = str(iso_val).strip()
        resolved = _iso3_to_iso2(iso_str)
        if resolved:
            return resolved

    # 2. Fall back to numeric code → ISO-2 mapping
    code_val = row.get(code_key) or row.get(code_key[0].upper() + code_key[1:])
    if code_val is not None:
        try:
            num = int(code_val)
            # Reject known aggregate codes (World, Other, etc.)
            if num in COMTRADE_AGGREGATE_CODES:
                return None
            return COMTRADE_NUM_TO_ISO2.get(num)
        except (ValueError, TypeError):
            pass

    return None


def _matches_hs_set(cmd_code: str, hs_codes: frozenset[str]) -> bool:
    """Check if a commodity code matches any prefix in the HS code set."""
    for prefix in hs_codes:
        if cmd_code.startswith(prefix):
            return True
    return False


# ---------------------------------------------------------------------------
# UN Comtrade API download with retry + caching
# ---------------------------------------------------------------------------

def _build_comtrade_api_url(
    reporter_num: int,
    hs_codes: frozenset[str],
    year_range: tuple[int, int],
) -> str:
    """Build the public UN Comtrade API URL."""
    years = ",".join(str(y) for y in range(year_range[0], year_range[1] + 1))
    cmd_codes = ",".join(sorted(hs_codes))

    params = {
        "reporterCode": str(reporter_num),
        "period": years,
        "cmdCode": cmd_codes,
        "flowCode": "M",
        "partnerCode": "",
        "partner2Code": "",
        "motCode": "0",
    }
    return f"{COMTRADE_API_BASE}?{urllib.parse.urlencode(params)}"


def _fetch_comtrade_api(
    url: str,
    cache_path: Path | None = None,
) -> list[dict] | None:
    """Fetch from UN Comtrade API with retry. Returns records or None."""
    # Check cache first
    if cache_path and cache_path.is_file():
        logger.info("  Using cached Comtrade response: %s", cache_path.name)
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else data.get("data", [])
        except (json.JSONDecodeError, KeyError):
            logger.warning("  Cache file corrupted, re-downloading")

    logger.info("  Comtrade API URL: %s", url[:200])

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "ISI-Pipeline/1.1 (research)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS, context=_SSL_CTX) as resp:
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw)

            records = payload.get("data", []) if isinstance(payload, dict) else payload
            logger.info(
                "  Comtrade API: %d records (attempt %d/%d)",
                len(records), attempt, MAX_RETRIES,
            )

            # Cache successful response
            if cache_path and records:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(records, f)

            return records

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = RETRY_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    "  Rate-limited (429). Waiting %.1fs (attempt %d/%d)",
                    wait, attempt, MAX_RETRIES,
                )
                time.sleep(wait)
            elif e.code == 403:
                logger.error("  Comtrade 403 Forbidden — API key may be required.")
                return None
            else:
                logger.error(
                    "  Comtrade HTTP %d (attempt %d/%d): %s",
                    e.code, attempt, MAX_RETRIES, e.reason,
                )
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        except urllib.error.URLError as e:
            logger.error(
                "  Connection error (attempt %d/%d): %s",
                attempt, MAX_RETRIES, e.reason,
            )
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

        except Exception as e:
            logger.error(
                "  Unexpected error (attempt %d/%d): %s",
                attempt, MAX_RETRIES, e,
            )
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.error("  All %d Comtrade API attempts failed", MAX_RETRIES)
    return None


# ---------------------------------------------------------------------------
# Record parsing — shared between API and local CSV
# ---------------------------------------------------------------------------

def _parse_api_records(
    api_records: list[dict],
    reporter_iso2: str,
    axis: str,
    hs_codes: frozenset[str],
    year_range: tuple[int, int],
    stats: dict,
) -> list[BilateralRecord]:
    """Parse UN Comtrade API JSON records into BilateralRecords."""
    records: list[BilateralRecord] = []

    for row in api_records:
        stats["rows_read"] += 1

        # Flow filter
        flow_code = str(row.get("flowCode", "")).strip()
        if flow_code not in ("M", "1"):
            stats["rows_flow_filtered"] += 1
            continue

        # Year filter
        try:
            year = int(row.get("period", 0))
        except (ValueError, TypeError):
            continue
        if year < year_range[0] or year > year_range[1]:
            stats["rows_year_filtered"] += 1
            continue

        # HS code filter
        cmd_code = str(row.get("cmdCode", "")).strip()
        if hs_codes and not _matches_hs_set(cmd_code, hs_codes):
            stats["rows_hs_filtered"] += 1
            continue

        # Reporter match — try ISO field first, fall back to numeric code
        rep_iso2 = _resolve_country(row, "reporterISO", "reporterCode")
        if rep_iso2 != reporter_iso2:
            stats["rows_reporter_mismatch"] += 1
            continue

        # Partner — try ISO field first, fall back to numeric code
        partner_iso2 = _resolve_country(row, "partnerISO", "partnerCode")
        if partner_iso2 is None:
            stats["rows_unmapped_partner"] += 1
            continue
        if partner_iso2 == reporter_iso2:
            continue

        # Value
        value = 0.0
        for vk in ("primaryValue", "PrimaryValue", "cifvalue", "Cifvalue"):
            try:
                v = float(row.get(vk, 0) or 0)
                if v > 0:
                    value = v
                    break
            except (ValueError, TypeError):
                continue

        if math.isnan(value) or math.isinf(value) or value <= 0:
            stats["rows_zero_negative"] += 1
            continue

        sub_cat = map_hs_to_category(cmd_code, axis)
        cmd_desc = str(row.get("cmdDesc", row.get("CmdDesc", "")))[:100]

        records.append(BilateralRecord(
            reporter=reporter_iso2,
            partner=partner_iso2,
            value=value,
            year=year,
            source="un_comtrade",
            axis=axis,
            product_code=cmd_code[:6],
            product_desc=cmd_desc if cmd_desc else None,
            unit="USD",
            sub_category=sub_cat,
        ))

    return records


def _parse_local_csv(
    raw_path: Path,
    reporter_iso2: str,
    axis: str,
    hs_codes: frozenset[str],
    year_range: tuple[int, int],
    stats: dict,
) -> list[BilateralRecord]:
    """Parse a pre-downloaded Comtrade bulk CSV."""
    records: list[BilateralRecord] = []

    with open(raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows_read"] += 1

            flow_code = _resolve_comtrade_field(row, FLD_FLOW_CODE)
            if flow_code not in (FLOW_IMPORTS, FLOW_IMPORTS_NUMERIC):
                stats["rows_flow_filtered"] += 1
                continue

            year_str = _resolve_comtrade_field(row, FLD_YEAR)
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year < year_range[0] or year > year_range[1]:
                stats["rows_year_filtered"] += 1
                continue

            cmd_code = _resolve_comtrade_field(row, FLD_CMD_CODE)
            if hs_codes and not _matches_hs_set(cmd_code, hs_codes):
                stats["rows_hs_filtered"] += 1
                continue

            reporter_iso3_raw = _resolve_comtrade_field(row, FLD_REPORTER_ISO)
            rep_iso2 = _iso3_to_iso2(reporter_iso3_raw)
            if rep_iso2 != reporter_iso2:
                stats["rows_reporter_mismatch"] += 1
                continue

            partner_iso3_raw = _resolve_comtrade_field(row, FLD_PARTNER_ISO)
            partner_iso2 = _iso3_to_iso2(partner_iso3_raw)
            if partner_iso2 is None:
                stats["rows_unmapped_partner"] += 1
                continue
            if partner_iso2 == reporter_iso2:
                continue

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

            sub_cat = map_hs_to_category(cmd_code, axis)
            cmd_desc = _resolve_comtrade_field(row, FLD_CMD_DESC)

            records.append(BilateralRecord(
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

    return records


# ---------------------------------------------------------------------------
# Main ingestion function
# ---------------------------------------------------------------------------

def ingest_comtrade(
    reporter_iso2: str,
    axis: str,
    raw_path: Path | None = None,
    year_range: tuple[int, int] | None = None,
    hs_codes: frozenset[str] | None = None,
    use_api: bool = True,
) -> tuple[BilateralDataset | None, dict]:
    """Ingest UN Comtrade data for a single reporter and axis.

    Data acquisition strategy:
        1. If raw_path provided and exists → local CSV
        2. If default local CSV exists → local CSV
        3. If use_api=True → UN Comtrade API (with disk cache)
        4. All fail → (None, stats)

    Args:
        reporter_iso2: ISO-2 code of the ISI reporter.
        axis: Axis slug ("energy", "technology", "critical_inputs").
        raw_path: Override path to raw Comtrade CSV.
        year_range: (min_year, max_year) inclusive.
        hs_codes: Override HS code prefix set.
        use_api: Whether to attempt API download if no local file.

    Returns:
        (BilateralDataset or None, stats_dict)
    """
    if axis not in AXIS_CONFIG:
        raise ValueError(f"Unsupported axis for Comtrade: {axis}")

    cfg = AXIS_CONFIG[axis]

    if year_range is None:
        year_range = DEFAULT_YEAR_RANGE
    if hs_codes is None:
        hs_codes = cfg["hs_codes"]

    reporter_iso3 = ISO2_TO_ISO3.get(reporter_iso2, "")

    stats: dict = {
        "source": "un_comtrade",
        "reporter": reporter_iso2,
        "reporter_iso3": reporter_iso3,
        "axis": axis,
        "raw_file": "",
        "data_method": "",
        "year_range": list(year_range),
        "hs_code_count": len(hs_codes),
        "hs_codes": sorted(hs_codes),
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
        "status": IngestionStatus.PENDING,
    }

    # --- Strategy 1: Local CSV -------------------------------------------------
    if raw_path is None:
        raw_path = RAW_DIR / "comtrade" / cfg["raw_filename"]

    raw_records: list[BilateralRecord] = []

    if raw_path.is_file():
        stats["raw_file"] = str(raw_path)
        stats["data_method"] = "local_csv"
        logger.info(
            "Comtrade: local CSV for %s/%s: %s", reporter_iso2, axis, raw_path,
        )
        raw_records = _parse_local_csv(
            raw_path, reporter_iso2, axis, hs_codes, year_range, stats,
        )

    # --- Strategy 2: UN Comtrade API -------------------------------------------
    elif use_api:
        reporter_num = ISO2_TO_COMTRADE_NUM.get(reporter_iso2)
        if reporter_num is None:
            stats["status"] = IngestionStatus.NO_DATA
            stats["data_method"] = "api_failed"
            logger.warning("Comtrade: no numeric code for %s", reporter_iso2)
            return None, stats

        cache_file = (
            COMTRADE_CACHE_DIR / reporter_iso2
            / f"{axis}_{year_range[0]}_{year_range[1]}.json"
        )
        stats["data_method"] = "api_cached" if cache_file.is_file() else "api"

        url = _build_comtrade_api_url(reporter_num, hs_codes, year_range)
        stats["api_url"] = url
        logger.info(
            "Comtrade: API download for %s/%s (num=%d)", reporter_iso2, axis, reporter_num,
        )

        api_data = _fetch_comtrade_api(url, cache_path=cache_file)

        if api_data is None:
            stats["status"] = IngestionStatus.API_FAILED
            stats["data_method"] = "api_failed"
            logger.error("Comtrade API failed for %s/%s", reporter_iso2, axis)
            return None, stats

        if not api_data:
            stats["status"] = IngestionStatus.NO_DATA
            stats["data_method"] = "api_empty"
            logger.warning("Comtrade API returned 0 records for %s/%s", reporter_iso2, axis)
            return None, stats

        raw_records = _parse_api_records(
            api_data, reporter_iso2, axis, hs_codes, year_range, stats,
        )
        stats["raw_file"] = str(cache_file)
        time.sleep(RATE_LIMIT_SLEEP)

    else:
        stats["status"] = IngestionStatus.FILE_NOT_FOUND
        stats["data_method"] = "none"
        logger.error("Comtrade: no local file and API disabled for %s/%s", reporter_iso2, axis)
        return None, stats

    stats["raw_records_extracted"] = len(raw_records)

    if not raw_records:
        if stats["status"] == IngestionStatus.PENDING:
            stats["status"] = IngestionStatus.NO_DATA
        logger.warning(
            "Comtrade: 0 records for %s/%s (method=%s)",
            reporter_iso2, axis, stats["data_method"],
        )
        return None, stats

    # --- Normalize -------------------------------------------------------------
    normalized, norm_audit = normalize_records(
        raw_records, source="un_comtrade", axis=axis, reporter_filter=reporter_iso2,
    )

    # --- Build dataset ---------------------------------------------------------
    dataset = BilateralDataset(
        reporter=reporter_iso2, axis=axis, source="un_comtrade", year_range=year_range,
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
        "Comtrade %s/%s: %d records, %d partners, $%.0f (method=%s)",
        reporter_iso2, axis, len(dataset.records), dataset.n_partners,
        dataset.total_value, stats["data_method"],
    )

    return dataset, stats
