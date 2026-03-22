#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Script 1: Ingest Gate

Validates pre-downloaded Eurostat freight CSV files for structural
integrity BEFORE any parsing, aggregation, or scoring occurs.

Expected raw files:
  data/raw/logistics/road_go_ia_lgtt.csv
  data/raw/logistics/road_go_ia_ugtt.csv
  data/raw/logistics/rail_go_intgong.csv
  data/raw/logistics/iww_go_atygo.csv
  data/raw/logistics/mar_go_am_{iso2}.csv  (one per maritime reporter)

Maritime reporters (22):
  BE, BG, CY, DE, DK, EE, EL, ES, FI, FR,
  HR, IE, IT, LT, LV, MT, NL, PL, PT, RO, SE, SI

Data sources:
  Eurostat transport statistics
  https://ec.europa.eu/eurostat/databrowser/

This script does NOT download data.
This script does NOT modify data.
This script does NOT write output files.
All reporting is to stdout/stderr.

If ANY structural validation fails, exit with non-zero status.

Task: ISI-LOGISTICS-INGEST
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "logistics"

# ──────────────────────────────────────────────────────────────
# EU-27 canonical set (ISI standard)
# ──────────────────────────────────────────────────────────────

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

# GR is Eurostat's code for Greece; ISI uses EL.
EU27_WITH_GR = EU27 | {"GR"}

# ──────────────────────────────────────────────────────────────
# Aggregate codes to reject (reporters and partners)
# ──────────────────────────────────────────────────────────────

REJECT_AGGREGATES = frozenset([
    "EU27_2020", "EU28", "EU27_2007", "EU25", "EU15",
    "EA19", "EA20", "EFTA", "TOTAL", "WORLD",
    "EU_V", "EU_E", "EXT_EU27_2020",
    "NSP", "NSP_E", "UNK",
])

# ──────────────────────────────────────────────────────────────
# Valid years
# ──────────────────────────────────────────────────────────────

VALID_YEARS = frozenset(["2022", "2023", "2024"])

# ──────────────────────────────────────────────────────────────
# Maritime EU-27 reporters (non-landlocked)
# ──────────────────────────────────────────────────────────────

LANDLOCKED = frozenset(["AT", "CZ", "HU", "LU", "SK"])

MARITIME_REPORTERS = EU27 - LANDLOCKED  # 22 countries

# Eurostat maritime tables use lowercase iso2 in the table name.
# File naming: mar_go_am_{iso2}.csv
# For Greece, Eurostat uses GR (not EL) in table names.
MARITIME_ISO2_FILE = {
    "BE": "be", "BG": "bg", "CY": "cy", "DE": "de", "DK": "dk",
    "EE": "ee", "EL": "el", "ES": "es", "FI": "fi", "FR": "fr",
    "HR": "hr", "IE": "ie", "IT": "it", "LT": "lt", "LV": "lv",
    "MT": "mt", "NL": "nl", "PL": "pl", "PT": "pt", "RO": "ro",
    "SE": "se", "SI": "si",
}

# ──────────────────────────────────────────────────────────────
# Coverage thresholds
# ──────────────────────────────────────────────────────────────

# Road: 26/27 minimum (MT allowed missing — island, no road freight)
ROAD_ALLOWED_MISSING = frozenset(["MT"])
ROAD_MIN_REPORTERS = 26

# Rail: 25/27 minimum (CY, MT allowed missing — no rail)
RAIL_ALLOWED_MISSING = frozenset(["CY", "MT"])
RAIL_MIN_REPORTERS = 25

# Maritime: 22/27 minimum (5 landlocked missing)
MARITIME_MIN_REPORTERS = 22

# IWW: partial coverage allowed, but logged
IWW_MIN_REPORTERS = 0  # no hard threshold

# ──────────────────────────────────────────────────────────────
# Prohibited modes (hard fail if encountered)
# ──────────────────────────────────────────────────────────────

PROHIBITED_MODE_KEYWORDS = frozenset([
    "air", "avia", "aviation", "pipeline", "pipe",
])

# ──────────────────────────────────────────────────────────────
# Column detection
# ──────────────────────────────────────────────────────────────

# Each mode's CSV may use different column names depending on
# the Eurostat download format. We detect columns by scanning
# the header for known patterns (case-insensitive substring).

REPORTER_PATTERNS = ["geo", "reporter", "rep_mar", "declarant"]
PARTNER_PATTERNS = ["c_unload", "c_load", "partner", "par_mar"]
VALUE_PATTERNS = ["obs_value", "value", "values"]
TIME_PATTERNS = ["time", "time_period", "period", "year"]
FLOW_PATTERNS = ["flow", "direct", "direction"]
UNIT_PATTERNS = ["unit"]


def detect_column(fieldnames, patterns, label):
    """Return the first fieldname matching any pattern (case-insensitive).
    Returns None if no match found."""
    lower_fields = {f: f.lower().strip() for f in fieldnames}
    for pattern in patterns:
        for original, lower in lower_fields.items():
            if pattern in lower:
                return original
    return None


def normalise_geo(code):
    """Normalise Eurostat geo codes to ISI convention."""
    code = code.strip().upper()
    if code == "GR":
        return "EL"
    return code


def is_aggregate(code):
    """Check if a geo code is an aggregate or non-country code."""
    code = code.strip().upper()
    if code in REJECT_AGGREGATES:
        return True
    # Reject codes starting with EU, EA (but not country codes)
    if code.startswith("EU") and len(code) > 2:
        return True
    if code.startswith("EA") and len(code) > 2:
        return True
    return False


def looks_like_prohibited_mode(filepath):
    """Check if a filepath suggests air or pipeline data."""
    name_lower = filepath.name.lower()
    for keyword in PROHIBITED_MODE_KEYWORDS:
        if keyword in name_lower:
            return True
    return False


def is_annual(year_str):
    """Check if a time value looks like an annual period (4-digit year).
    Reject monthly (2023M01), quarterly (2023Q1), etc."""
    year_str = year_str.strip()
    if len(year_str) == 4 and year_str.isdigit():
        return True
    return False


def parse_value(val_str):
    """Parse a freight volume value. Returns (float, error_reason) tuple.
    On success: (value, None). On failure: (None, reason)."""
    val_str = val_str.strip()
    if val_str == "" or val_str == ":" or val_str == "c" or val_str == "n":
        return (None, "missing_or_confidential")
    # Remove trailing flags (Eurostat uses suffixes like 'p', 'e', 'b', 'd')
    cleaned = val_str.rstrip("pebd ").strip()
    if cleaned == "":
        return (None, "missing_or_confidential")
    try:
        value = float(cleaned)
    except (ValueError, TypeError):
        return (None, "non_numeric")
    if value < 0:
        return (None, "negative")
    return (value, None)


# ──────────────────────────────────────────────────────────────
# Per-mode validation
# ──────────────────────────────────────────────────────────────

def validate_mode_file(filepath, mode_name, partner_patterns_override=None):
    """Validate a single mode CSV file. Returns a result dict or None on fatal."""

    result = {
        "mode": mode_name,
        "file": str(filepath),
        "rows_scanned": 0,
        "rows_kept": 0,
        "rows_dropped": 0,
        "drop_reasons": {},
        "reporters": set(),
        "partners": set(),
        "years": set(),
        "total_tonnage": 0.0,
        "zero_value_rows": 0,
        "fatal": False,
        "fatal_reason": None,
    }

    def drop(reason):
        result["rows_dropped"] += 1
        result["drop_reasons"][reason] = result["drop_reasons"].get(reason, 0) + 1

    # ── Prohibited mode check ────────────────────────────────
    if looks_like_prohibited_mode(filepath):
        result["fatal"] = True
        result["fatal_reason"] = (
            f"File name '{filepath.name}' suggests air or pipeline data. "
            f"Axis 6 includes only road, rail, maritime, IWW."
        )
        return result

    # ── Open and detect columns ──────────────────────────────
    try:
        f = open(filepath, "r", encoding="utf-8", newline="")
    except Exception as exc:
        result["fatal"] = True
        result["fatal_reason"] = f"Cannot open file: {exc}"
        return result

    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames

    if fieldnames is None or len(fieldnames) == 0:
        f.close()
        result["fatal"] = True
        result["fatal_reason"] = "File has no header or is empty."
        return result

    p_patterns = partner_patterns_override if partner_patterns_override else PARTNER_PATTERNS

    col_reporter = detect_column(fieldnames, REPORTER_PATTERNS, "reporter")
    col_partner = detect_column(fieldnames, p_patterns, "partner")
    col_value = detect_column(fieldnames, VALUE_PATTERNS, "value")
    col_time = detect_column(fieldnames, TIME_PATTERNS, "time")
    col_flow = detect_column(fieldnames, FLOW_PATTERNS, "flow")
    col_unit = detect_column(fieldnames, UNIT_PATTERNS, "unit")

    # ── Partner dimension: HARD FAIL if missing ──────────────
    if col_partner is None:
        f.close()
        result["fatal"] = True
        result["fatal_reason"] = (
            f"No partner dimension found in columns: {fieldnames}. "
            f"Searched patterns: {p_patterns}. "
            f"Axis 6 requires bilateral partner data."
        )
        return result

    # ── Reporter column: HARD FAIL if missing ────────────────
    if col_reporter is None:
        f.close()
        result["fatal"] = True
        result["fatal_reason"] = (
            f"No reporter column found in columns: {fieldnames}. "
            f"Searched patterns: {REPORTER_PATTERNS}."
        )
        return result

    # ── Value column: HARD FAIL if missing ───────────────────
    if col_value is None:
        f.close()
        result["fatal"] = True
        result["fatal_reason"] = (
            f"No value column found in columns: {fieldnames}. "
            f"Searched patterns: {VALUE_PATTERNS}."
        )
        return result

    # ── Time column: HARD FAIL if missing ────────────────────
    if col_time is None:
        f.close()
        result["fatal"] = True
        result["fatal_reason"] = (
            f"No time column found in columns: {fieldnames}. "
            f"Searched patterns: {TIME_PATTERNS}."
        )
        return result

    # ── Row-level validation ─────────────────────────────────
    for row in reader:
        result["rows_scanned"] += 1

        # --- Reporter ---
        raw_reporter = row.get(col_reporter, "").strip()
        if raw_reporter == "":
            drop("reporter_empty")
            continue

        reporter = normalise_geo(raw_reporter)

        if is_aggregate(raw_reporter):
            drop("reporter_aggregate")
            continue

        if reporter not in EU27:
            drop("reporter_not_eu27")
            continue

        # --- Partner ---
        raw_partner = row.get(col_partner, "").strip()
        if raw_partner == "":
            drop("partner_empty")
            continue

        if is_aggregate(raw_partner):
            drop("partner_aggregate")
            continue

        # --- Time ---
        raw_time = row.get(col_time, "").strip()
        if not is_annual(raw_time):
            # Check if this is monthly/quarterly → FAIL mode
            if raw_time and not raw_time.isdigit():
                drop("time_not_annual")
                continue
            if raw_time and len(raw_time) != 4:
                drop("time_not_annual")
                continue
            if raw_time == "":
                drop("time_empty")
                continue
            drop("time_not_annual")
            continue

        if raw_time not in VALID_YEARS:
            drop("year_outside_window")
            continue

        # --- Flow (if present) ---
        if col_flow is not None:
            raw_flow = row.get(col_flow, "").strip().upper()
            # Eurostat flow codes vary:
            #   road/rail: no explicit flow (data is directional by table)
            #   maritime: direct dimension (INWARD, OUTWARD, TOTAL)
            #   Some tables use numeric codes: 1=import, 2=export
            # We accept: empty, INWARD, IMP, 1, IN
            # We reject: OUTWARD, EXP, 2, OUT, TOTAL (aggregate)
            if raw_flow in ("OUTWARD", "OUT", "EXP", "2"):
                drop("flow_export")
                continue
            if raw_flow in ("TOTAL",):
                drop("flow_aggregate")
                continue

        # --- Unit (if present, verify tonnes) ---
        if col_unit is not None:
            raw_unit = row.get(col_unit, "").strip().upper()
            # Accept: THS_T (thousand tonnes), T (tonnes), THS_T (Eurostat)
            # Also accept MIO_TKM for rail if THS_T absent, but log
            # Reject: PC (percentage), NR (number), EUR
            if raw_unit in ("PC", "PC_TOT", "NR", "EUR", "MIO_EUR"):
                drop("unit_not_tonnes")
                continue

        # --- Value ---
        raw_value = row.get(col_value, "").strip()
        value, err = parse_value(raw_value)
        if err is not None:
            drop(f"value_{err}")
            continue

        if value == 0.0:
            result["zero_value_rows"] += 1

        # ── Row passes all checks ───────────────────────────
        result["rows_kept"] += 1
        result["reporters"].add(reporter)
        result["partners"].add(normalise_geo(raw_partner))
        result["years"].add(raw_time)
        result["total_tonnage"] += value

    f.close()
    return result


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("ISI v0.1 — Axis 6: Logistics / Freight Dependency — Ingest Gate")
    print("=" * 68)
    print()

    fatal_errors = []

    # ──────────────────────────────────────────────────────────
    # 0. Check raw directory exists
    # ──────────────────────────────────────────────────────────
    print(f"Raw data directory: {RAW_DIR}")
    if not RAW_DIR.exists():
        print(f"FATAL: raw data directory does not exist: {RAW_DIR}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Create the directory and place raw CSV files:", file=sys.stderr)
        print(f"  mkdir -p {RAW_DIR}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Required files:", file=sys.stderr)
        print(f"  road_go_ia_lgtt.csv", file=sys.stderr)
        print(f"  road_go_ia_ugtt.csv", file=sys.stderr)
        print(f"  rail_go_intgong.csv", file=sys.stderr)
        print(f"  iww_go_atygo.csv", file=sys.stderr)
        print(f"  mar_go_am_{{iso2}}.csv  (22 maritime files)", file=sys.stderr)
        sys.exit(1)
    print()

    # ──────────────────────────────────────────────────────────
    # 1. Check all expected files exist
    # ──────────────────────────────────────────────────────────
    print("-" * 68)
    print("FILE EXISTENCE CHECK")
    print("-" * 68)
    print()

    expected_files = {}

    # Road
    expected_files["road_loaded"] = RAW_DIR / "road_go_ia_lgtt.csv"
    expected_files["road_unloaded"] = RAW_DIR / "road_go_ia_ugtt.csv"

    # Rail
    expected_files["rail"] = RAW_DIR / "rail_go_intgong.csv"

    # IWW
    expected_files["iww"] = RAW_DIR / "iww_go_atygo.csv"

    # Maritime (22 per-country files)
    for isi_code, iso2 in sorted(MARITIME_ISO2_FILE.items()):
        key = f"maritime_{isi_code}"
        expected_files[key] = RAW_DIR / f"mar_go_am_{iso2}.csv"

    missing_files = []
    for key, fpath in sorted(expected_files.items()):
        exists = fpath.exists()
        status = "FOUND" if exists else "MISSING"
        size_str = f"{fpath.stat().st_size:,} bytes" if exists else ""
        print(f"  [{status:7s}] {fpath.name:30s} {size_str}")
        if not exists:
            missing_files.append((key, fpath))

    print()

    if missing_files:
        # Determine which missing files are fatal
        for key, fpath in missing_files:
            if key in ("road_loaded", "road_unloaded", "rail", "iww"):
                fatal_errors.append(f"Missing required mode file: {fpath.name}")
            elif key.startswith("maritime_"):
                # Maritime files are expected for non-landlocked countries
                fatal_errors.append(f"Missing maritime file: {fpath.name}")

    # ──────────────────────────────────────────────────────────
    # 2. Validate each mode
    # ──────────────────────────────────────────────────────────

    mode_results = {}

    # -- ROAD (loaded) --
    if expected_files["road_loaded"].exists():
        print("-" * 68)
        print("ROAD — loaded goods (road_go_ia_lgtt)")
        print("-" * 68)
        r = validate_mode_file(
            expected_files["road_loaded"],
            "road_loaded",
            partner_patterns_override=["c_unload", "partner", "c_load"],
        )
        mode_results["road_loaded"] = r
        print_mode_result(r)
        if r["fatal"]:
            fatal_errors.append(f"ROAD loaded: {r['fatal_reason']}")

    # -- ROAD (unloaded) --
    if expected_files["road_unloaded"].exists():
        print("-" * 68)
        print("ROAD — unloaded goods (road_go_ia_ugtt)")
        print("-" * 68)
        r = validate_mode_file(
            expected_files["road_unloaded"],
            "road_unloaded",
            partner_patterns_override=["c_load", "c_unload", "partner"],
        )
        mode_results["road_unloaded"] = r
        print_mode_result(r)
        if r["fatal"]:
            fatal_errors.append(f"ROAD unloaded: {r['fatal_reason']}")

    # -- RAIL --
    if expected_files["rail"].exists():
        print("-" * 68)
        print("RAIL — international goods (rail_go_intgong)")
        print("-" * 68)
        r = validate_mode_file(
            expected_files["rail"],
            "rail",
            partner_patterns_override=["c_unload", "partner"],
        )
        mode_results["rail"] = r
        print_mode_result(r)
        if r["fatal"]:
            fatal_errors.append(f"RAIL: {r['fatal_reason']}")

    # -- IWW --
    if expected_files["iww"].exists():
        print("-" * 68)
        print("IWW — inland waterways (iww_go_atygo)")
        print("-" * 68)
        r = validate_mode_file(
            expected_files["iww"],
            "iww",
            partner_patterns_override=["c_unload", "partner", "c_load"],
        )
        mode_results["iww"] = r
        print_mode_result(r)
        if r["fatal"]:
            fatal_errors.append(f"IWW: {r['fatal_reason']}")

    # -- MARITIME (22 per-country files) --
    maritime_combined_reporters = set()
    maritime_combined_partners = set()
    maritime_combined_years = set()
    maritime_combined_tonnage = 0.0
    maritime_combined_rows_scanned = 0
    maritime_combined_rows_kept = 0
    maritime_combined_rows_dropped = 0
    maritime_combined_drop_reasons = {}
    maritime_combined_zero = 0
    maritime_file_count = 0
    maritime_fatals = []

    for isi_code, iso2 in sorted(MARITIME_ISO2_FILE.items()):
        key = f"maritime_{isi_code}"
        fpath = expected_files[key]
        if not fpath.exists():
            continue

        maritime_file_count += 1
        r = validate_mode_file(
            fpath,
            f"maritime_{isi_code}",
            partner_patterns_override=["par_mar", "partner", "c_unload"],
        )
        mode_results[key] = r

        if r["fatal"]:
            maritime_fatals.append(f"Maritime {isi_code}: {r['fatal_reason']}")
            continue

        maritime_combined_reporters.update(r["reporters"])
        maritime_combined_partners.update(r["partners"])
        maritime_combined_years.update(r["years"])
        maritime_combined_tonnage += r["total_tonnage"]
        maritime_combined_rows_scanned += r["rows_scanned"]
        maritime_combined_rows_kept += r["rows_kept"]
        maritime_combined_rows_dropped += r["rows_dropped"]
        maritime_combined_zero += r["zero_value_rows"]
        for reason, count in r["drop_reasons"].items():
            maritime_combined_drop_reasons[reason] = (
                maritime_combined_drop_reasons.get(reason, 0) + count
            )

    if maritime_file_count > 0:
        print("-" * 68)
        print(f"MARITIME — combined ({maritime_file_count} files)")
        print("-" * 68)
        print(f"  Files processed:           {maritime_file_count:>12}")
        print(f"  Rows scanned:              {maritime_combined_rows_scanned:>12,}")
        print(f"  Rows kept:                 {maritime_combined_rows_kept:>12,}")
        print(f"  Rows dropped:              {maritime_combined_rows_dropped:>12,}")
        if maritime_combined_drop_reasons:
            print(f"  Drop reasons:")
            for reason, count in sorted(maritime_combined_drop_reasons.items()):
                print(f"    {reason:35s} {count:>10,}")
        print(f"  Unique reporters:          {len(maritime_combined_reporters):>12}")
        if maritime_combined_reporters:
            print(f"    {sorted(maritime_combined_reporters)}")
        print(f"  Unique partners:           {len(maritime_combined_partners):>12}")
        print(f"  Years:                     {sorted(maritime_combined_years)}")
        print(f"  Total tonnage:             {maritime_combined_tonnage:>16,.1f}")
        print(f"  Zero-value rows:           {maritime_combined_zero:>12,}")
        print()

    if maritime_fatals:
        for msg in maritime_fatals:
            fatal_errors.append(msg)

    # ──────────────────────────────────────────────────────────
    # 3. Coverage checks
    # ──────────────────────────────────────────────────────────
    print("-" * 68)
    print("EU-27 COVERAGE MATRIX")
    print("-" * 68)
    print()

    # Collect reporters per mode
    reporters_road = set()
    if "road_loaded" in mode_results and not mode_results["road_loaded"]["fatal"]:
        reporters_road.update(mode_results["road_loaded"]["reporters"])
    if "road_unloaded" in mode_results and not mode_results["road_unloaded"]["fatal"]:
        reporters_road.update(mode_results["road_unloaded"]["reporters"])

    reporters_rail = set()
    if "rail" in mode_results and not mode_results["rail"]["fatal"]:
        reporters_rail = mode_results["rail"]["reporters"]

    reporters_iww = set()
    if "iww" in mode_results and not mode_results["iww"]["fatal"]:
        reporters_iww = mode_results["iww"]["reporters"]

    reporters_maritime = maritime_combined_reporters

    # Print matrix
    header_line = f"  {'Country':<10s} {'Road':>6s} {'Rail':>6s} {'Marit':>6s} {'IWW':>6s}"
    print(header_line)
    print("  " + "-" * len(header_line.strip()))

    for country in sorted(EU27):
        road_ok = "YES" if country in reporters_road else "---"
        rail_ok = "YES" if country in reporters_rail else "---"
        mar_ok = "YES" if country in reporters_maritime else "---"
        iww_ok = "YES" if country in reporters_iww else "---"
        print(f"  {country:<10s} {road_ok:>6s} {rail_ok:>6s} {mar_ok:>6s} {iww_ok:>6s}")

    print()

    # Coverage enforcement
    # Road
    missing_road = EU27 - reporters_road
    unexpected_missing_road = missing_road - ROAD_ALLOWED_MISSING
    print(f"  Road reporters:    {len(reporters_road & EU27)}/27")
    if missing_road:
        print(f"    Missing: {sorted(missing_road)}")
        if unexpected_missing_road:
            for m in sorted(unexpected_missing_road):
                print(f"    UNEXPECTED missing road reporter: {m}")
    if len(reporters_road & EU27) < ROAD_MIN_REPORTERS:
        fatal_errors.append(
            f"Road coverage: {len(reporters_road & EU27)}/27 reporters, "
            f"minimum required: {ROAD_MIN_REPORTERS}/27"
        )

    # Rail
    missing_rail = EU27 - reporters_rail
    unexpected_missing_rail = missing_rail - RAIL_ALLOWED_MISSING
    print(f"  Rail reporters:    {len(reporters_rail & EU27)}/27")
    if missing_rail:
        print(f"    Missing: {sorted(missing_rail)}")
        if unexpected_missing_rail:
            for m in sorted(unexpected_missing_rail):
                print(f"    UNEXPECTED missing rail reporter: {m}")
    if len(reporters_rail & EU27) < RAIL_MIN_REPORTERS:
        fatal_errors.append(
            f"Rail coverage: {len(reporters_rail & EU27)}/27 reporters, "
            f"minimum required: {RAIL_MIN_REPORTERS}/27"
        )

    # Maritime
    missing_maritime = MARITIME_REPORTERS - reporters_maritime
    print(f"  Maritime reporters: {len(reporters_maritime & EU27)}/27 "
          f"(22 expected, 5 landlocked excluded)")
    if missing_maritime:
        print(f"    Missing maritime: {sorted(missing_maritime)}")
    if len(reporters_maritime & MARITIME_REPORTERS) < MARITIME_MIN_REPORTERS:
        fatal_errors.append(
            f"Maritime coverage: {len(reporters_maritime & MARITIME_REPORTERS)}/22 "
            f"maritime reporters, minimum required: {MARITIME_MIN_REPORTERS}/22"
        )

    # IWW
    print(f"  IWW reporters:     {len(reporters_iww & EU27)}/27 (partial expected)")
    if reporters_iww:
        print(f"    Present: {sorted(reporters_iww & EU27)}")
    missing_iww = EU27 - reporters_iww
    if missing_iww:
        print(f"    Missing: {sorted(missing_iww)}")

    print()

    # ──────────────────────────────────────────────────────────
    # 4. Global summary
    # ──────────────────────────────────────────────────────────
    print("-" * 68)
    print("GLOBAL SUMMARY")
    print("-" * 68)
    print()

    total_scanned = 0
    total_kept = 0
    total_dropped = 0
    total_tonnage = 0.0
    total_zero = 0
    all_drop_reasons = {}

    for key, r in sorted(mode_results.items()):
        if r["fatal"]:
            continue
        total_scanned += r["rows_scanned"]
        total_kept += r["rows_kept"]
        total_dropped += r["rows_dropped"]
        total_tonnage += r["total_tonnage"]
        total_zero += r["zero_value_rows"]
        for reason, count in r["drop_reasons"].items():
            all_drop_reasons[reason] = all_drop_reasons.get(reason, 0) + count

    print(f"  Total rows scanned:        {total_scanned:>12,}")
    print(f"  Total rows kept:           {total_kept:>12,}")
    print(f"  Total rows dropped:        {total_dropped:>12,}")
    print(f"  Total tonnage:             {total_tonnage:>16,.1f}")
    print(f"  Zero-value rows (kept):    {total_zero:>12,}")
    print()

    if all_drop_reasons:
        print(f"  All drop reasons:")
        for reason, count in sorted(all_drop_reasons.items()):
            print(f"    {reason:35s} {count:>10,}")
        print()

    # Fatal count
    non_fatal_drops = total_dropped
    print(f"  Fatal errors:              {len(fatal_errors):>12}")
    print(f"  Non-fatal drops:           {non_fatal_drops:>12,}")
    print()

    # ──────────────────────────────────────────────────────────
    # 5. Verdict
    # ──────────────────────────────────────────────────────────
    print("=" * 68)

    if fatal_errors:
        print("Ingest gate: FAIL")
        print("=" * 68)
        print()
        print("FATAL ERRORS:", file=sys.stderr)
        for i, err in enumerate(fatal_errors, 1):
            print(f"  {i}. {err}", file=sys.stderr)
        print()
        sys.exit(1)

    if total_kept == 0:
        print("Ingest gate: FAIL", file=sys.stderr)
        print("=" * 68)
        print("FATAL: zero rows survived validation across all modes.", file=sys.stderr)
        sys.exit(1)

    print("Ingest gate: PASS")
    print("=" * 68)
    print()
    print(f"  Directory:         {RAW_DIR}")
    print(f"  Modes validated:   road, rail, maritime, iww")
    print(f"  Total rows kept:   {total_kept:,}")
    print(f"  Road reporters:    {len(reporters_road & EU27)}/27")
    print(f"  Rail reporters:    {len(reporters_rail & EU27)}/27")
    print(f"  Maritime reporters: {len(reporters_maritime & MARITIME_REPORTERS)}/22")
    print(f"  IWW reporters:     {len(reporters_iww & EU27)}/27")
    print(f"  Years:             2022, 2023, 2024")
    print()


def print_mode_result(r):
    """Print the audit summary for a single mode validation result."""
    print()
    if r["fatal"]:
        print(f"  FATAL: {r['fatal_reason']}")
        print()
        return

    print(f"  Rows scanned:              {r['rows_scanned']:>12,}")
    print(f"  Rows kept:                 {r['rows_kept']:>12,}")
    print(f"  Rows dropped:              {r['rows_dropped']:>12,}")
    if r["drop_reasons"]:
        print(f"  Drop reasons:")
        for reason, count in sorted(r["drop_reasons"].items()):
            print(f"    {reason:35s} {count:>10,}")
    print(f"  Unique reporters:          {len(r['reporters']):>12}")
    if r["reporters"]:
        print(f"    {sorted(r['reporters'])}")
    print(f"  Unique partners:           {len(r['partners']):>12}")
    print(f"  Years:                     {sorted(r['years'])}")
    print(f"  Total tonnage:             {r['total_tonnage']:>16,.1f}")
    print(f"  Zero-value rows:           {r['zero_value_rows']:>12,}")
    print()


if __name__ == "__main__":
    main()
