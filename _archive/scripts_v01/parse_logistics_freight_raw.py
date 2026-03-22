#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Script 2: Parser

Reads raw Eurostat freight CSV files (validated by Script 1),
normalises schemas across transport modes, and produces a single
canonical flat CSV for Channel A and Channel B computation.

Inputs (raw files, pre-validated by ingest gate):
  data/raw/logistics/road_go_ia_lgtt.csv
  data/raw/logistics/road_go_ia_ugtt.csv
  data/raw/logistics/rail_go_intgong.csv
  data/raw/logistics/iww_go_atygo.csv
  data/raw/logistics/mar_go_am_{iso2}.csv  (22 maritime files)

Output (flat):
  data/processed/logistics/logistics_freight_bilateral_flat.csv
  Schema: reporter,partner,mode,year,tonnes

Output (audit per reporter):
  data/processed/logistics/logistics_freight_bilateral_audit.csv
  Schema: reporter,mode,n_partners,total_tonnes,n_years

Output (waterfall):
  data/audit/logistics_parser_waterfall.csv
  Schema: stage,count

This script does NOT aggregate.
This script does NOT compute HHI.
This script does NOT implement channels.

Scope:
  Reporters: EU-27 only
  Partners: bilateral only (no aggregates)
  Years: 2022, 2023, 2024
  Flow: imports only
  Modes: road, rail, maritime, iww
  Unit: tonnes (THS_T or derived)

Task: ISI-LOGISTICS-PARSE
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "logistics"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "logistics"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"

OUT_FILE = OUT_DIR / "logistics_freight_bilateral_flat.csv"
AUDIT_FILE = OUT_DIR / "logistics_freight_bilateral_audit.csv"
WATERFALL_FILE = AUDIT_DIR / "logistics_parser_waterfall.csv"

# ──────────────────────────────────────────────────────────────
# Canonical output schema
# ──────────────────────────────────────────────────────────────

FLAT_FIELDNAMES = [
    "reporter",
    "partner",
    "mode",
    "year",
    "tonnes",
]

AUDIT_FIELDNAMES = [
    "reporter",
    "mode",
    "n_partners",
    "total_tonnes",
    "n_years",
]

# ──────────────────────────────────────────────────────────────
# EU-27 canonical set (ISI standard)
# ──────────────────────────────────────────────────────────────

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

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
# Maritime file mapping
# ──────────────────────────────────────────────────────────────

MARITIME_ISO2_FILE = {
    "BE": "be", "BG": "bg", "CY": "cy", "DE": "de", "DK": "dk",
    "EE": "ee", "EL": "el", "ES": "es", "FI": "fi", "FR": "fr",
    "HR": "hr", "IE": "ie", "IT": "it", "LT": "lt", "LV": "lv",
    "MT": "mt", "NL": "nl", "PL": "pl", "PT": "pt", "RO": "ro",
    "SE": "se", "SI": "si",
}

# ──────────────────────────────────────────────────────────────
# Column detection (reuses ingest patterns)
# ──────────────────────────────────────────────────────────────

REPORTER_PATTERNS = ["geo", "reporter", "rep_mar", "declarant"]
PARTNER_PATTERNS = ["c_unload", "c_load", "partner", "par_mar"]
VALUE_PATTERNS = ["obs_value", "value", "values"]
TIME_PATTERNS = ["time", "time_period", "period", "year"]
FLOW_PATTERNS = ["flow", "direct", "direction"]
UNIT_PATTERNS = ["unit"]


def detect_column(fieldnames, patterns):
    """Return the first fieldname matching any pattern (case-insensitive)."""
    lower_fields = {f: f.lower().strip() for f in fieldnames}
    for pattern in patterns:
        for original, lower in lower_fields.items():
            if pattern in lower:
                return original
    return None


def normalise_geo(code):
    """Normalise Eurostat geo codes to ISI convention (GR → EL)."""
    code = code.strip().upper()
    if code == "GR":
        return "EL"
    return code


def is_aggregate(code):
    """Check if a geo code is an aggregate or non-country code."""
    code = code.strip().upper()
    if code in REJECT_AGGREGATES:
        return True
    if code.startswith("EU") and len(code) > 2:
        return True
    if code.startswith("EA") and len(code) > 2:
        return True
    return False


def is_annual(year_str):
    """Check if a time value is a 4-digit annual period."""
    year_str = year_str.strip()
    return len(year_str) == 4 and year_str.isdigit()


def parse_value(val_str):
    """Parse a freight volume value.
    Returns (float, error_reason). On success: (value, None)."""
    val_str = val_str.strip()
    if val_str == "" or val_str == ":" or val_str == "c" or val_str == "n":
        return (None, "missing_or_confidential")
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
# Per-file parsing
# ──────────────────────────────────────────────────────────────

def parse_mode_file(filepath, mode_label, partner_col_patterns, waterfall,
                    import_flow_filter=None):
    """Parse a single mode CSV file into canonical rows.

    Args:
        filepath: Path to raw CSV.
        mode_label: Mode tag for output (road, rail, maritime, iww).
        partner_col_patterns: Ordered list of column name patterns
            for the partner dimension.
        waterfall: dict to accumulate drop counts.
        import_flow_filter: If set, tuple of (accepted, rejected) flow
            values. accepted = set of values that mean imports.
            rejected = set of values that mean exports/total.

    Returns:
        List of tuples: (reporter, partner, mode, year, tonnes)
    """
    rows_out = []

    try:
        f = open(filepath, "r", encoding="utf-8", newline="")
    except Exception as exc:
        print(f"FATAL: cannot open {filepath}: {exc}", file=sys.stderr)
        sys.exit(1)

    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames

    if fieldnames is None or len(fieldnames) == 0:
        f.close()
        print(f"FATAL: {filepath.name} has no header.", file=sys.stderr)
        sys.exit(1)

    col_reporter = detect_column(fieldnames, REPORTER_PATTERNS)
    col_partner = detect_column(fieldnames, partner_col_patterns)
    col_value = detect_column(fieldnames, VALUE_PATTERNS)
    col_time = detect_column(fieldnames, TIME_PATTERNS)
    col_flow = detect_column(fieldnames, FLOW_PATTERNS)
    col_unit = detect_column(fieldnames, UNIT_PATTERNS)

    if col_reporter is None:
        f.close()
        print(f"FATAL: {filepath.name}: no reporter column. "
              f"Headers: {fieldnames}", file=sys.stderr)
        sys.exit(1)

    if col_partner is None:
        f.close()
        print(f"FATAL: {filepath.name}: no partner column. "
              f"Headers: {fieldnames}", file=sys.stderr)
        sys.exit(1)

    if col_value is None:
        f.close()
        print(f"FATAL: {filepath.name}: no value column. "
              f"Headers: {fieldnames}", file=sys.stderr)
        sys.exit(1)

    if col_time is None:
        f.close()
        print(f"FATAL: {filepath.name}: no time column. "
              f"Headers: {fieldnames}", file=sys.stderr)
        sys.exit(1)

    scanned = 0

    for row in reader:
        scanned += 1

        # --- Reporter ---
        raw_reporter = row.get(col_reporter, "").strip()
        if raw_reporter == "":
            waterfall["dropped_reporter_empty"] += 1
            continue

        if is_aggregate(raw_reporter):
            waterfall["dropped_reporter_aggregate"] += 1
            continue

        reporter = normalise_geo(raw_reporter)

        if reporter not in EU27:
            waterfall["dropped_reporter_not_eu27"] += 1
            continue

        # --- Partner ---
        raw_partner = row.get(col_partner, "").strip()
        if raw_partner == "":
            waterfall["dropped_partner_empty"] += 1
            continue

        if is_aggregate(raw_partner):
            waterfall["dropped_partner_aggregate"] += 1
            continue

        partner = normalise_geo(raw_partner)

        # --- Time ---
        raw_time = row.get(col_time, "").strip()
        if not is_annual(raw_time):
            waterfall["dropped_time_not_annual"] += 1
            continue

        if raw_time not in VALID_YEARS:
            waterfall["dropped_year_outside_window"] += 1
            continue

        year = raw_time

        # --- Flow filter (imports only) ---
        if col_flow is not None and import_flow_filter is not None:
            raw_flow = row.get(col_flow, "").strip().upper()
            accepted, rejected = import_flow_filter
            if raw_flow in rejected:
                waterfall["dropped_flow_not_import"] += 1
                continue
            if accepted and raw_flow not in accepted and raw_flow != "":
                waterfall["dropped_flow_not_import"] += 1
                continue

        # --- Unit filter (tonnes only) ---
        if col_unit is not None:
            raw_unit = row.get(col_unit, "").strip().upper()
            if raw_unit in ("PC", "PC_TOT", "NR", "EUR", "MIO_EUR"):
                waterfall["dropped_unit_not_tonnes"] += 1
                continue

        # --- Value ---
        raw_value = row.get(col_value, "").strip()
        value, err = parse_value(raw_value)
        if err == "missing_or_confidential":
            waterfall["dropped_value_missing"] += 1
            continue
        if err == "non_numeric":
            waterfall["dropped_value_non_numeric"] += 1
            continue
        if err == "negative":
            waterfall["dropped_value_negative"] += 1
            continue

        if value == 0.0:
            waterfall["zero_value_kept"] += 1

        rows_out.append((reporter, partner, mode_label, year, value))

    f.close()
    waterfall["raw_rows_scanned"] += scanned
    return rows_out


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("ISI v0.1 — Axis 6: Logistics / Freight Dependency — Parser")
    print("=" * 68)
    print()

    # ── Verify raw directory ─────────────────────────────────
    if not RAW_DIR.exists():
        print(f"FATAL: raw data directory not found: {RAW_DIR}", file=sys.stderr)
        print(f"Run ingest_logistics_freight_manual.py first.", file=sys.stderr)
        sys.exit(1)

    # ── Waterfall counters ───────────────────────────────────
    waterfall = defaultdict(int)

    all_rows = []

    # ══════════════════════════════════════════════════════════
    # ROAD — loaded goods (road_go_ia_lgtt)
    # road_go_ia_lgtt: reporter loads goods → partner unloads
    # From reporter perspective: these are EXPORTS (loaded at reporter)
    # Partner column: c_unload
    # ══════════════════════════════════════════════════════════

    road_lgtt_file = RAW_DIR / "road_go_ia_lgtt.csv"
    if not road_lgtt_file.exists():
        print(f"FATAL: missing {road_lgtt_file.name}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {road_lgtt_file.name} (road, loaded goods)")
    road_lgtt_rows = parse_mode_file(
        road_lgtt_file,
        "road",
        ["c_unload", "partner", "c_load"],
        waterfall,
    )
    print(f"  Rows extracted: {len(road_lgtt_rows):,}")
    all_rows.extend(road_lgtt_rows)

    # ══════════════════════════════════════════════════════════
    # ROAD — unloaded goods (road_go_ia_ugtt)
    # road_go_ia_ugtt: partner loads goods → reporter unloads
    # From reporter perspective: these are IMPORTS (unloaded at reporter)
    # Partner column: c_load
    # ══════════════════════════════════════════════════════════

    road_ugtt_file = RAW_DIR / "road_go_ia_ugtt.csv"
    if not road_ugtt_file.exists():
        print(f"FATAL: missing {road_ugtt_file.name}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {road_ugtt_file.name} (road, unloaded goods)")
    road_ugtt_rows = parse_mode_file(
        road_ugtt_file,
        "road",
        ["c_load", "c_unload", "partner"],
        waterfall,
    )
    print(f"  Rows extracted: {len(road_ugtt_rows):,}")
    all_rows.extend(road_ugtt_rows)

    # ══════════════════════════════════════════════════════════
    # RAIL — international goods (rail_go_intgong)
    # Partner column: c_unload
    # ══════════════════════════════════════════════════════════

    rail_file = RAW_DIR / "rail_go_intgong.csv"
    if not rail_file.exists():
        print(f"FATAL: missing {rail_file.name}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {rail_file.name} (rail)")
    rail_rows = parse_mode_file(
        rail_file,
        "rail",
        ["c_unload", "partner"],
        waterfall,
    )
    print(f"  Rows extracted: {len(rail_rows):,}")
    all_rows.extend(rail_rows)

    # ══════════════════════════════════════════════════════════
    # IWW — inland waterways (iww_go_atygo)
    # Partner column: c_unload
    # ══════════════════════════════════════════════════════════

    iww_file = RAW_DIR / "iww_go_atygo.csv"
    if not iww_file.exists():
        print(f"FATAL: missing {iww_file.name}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing: {iww_file.name} (iww)")
    iww_rows = parse_mode_file(
        iww_file,
        "iww",
        ["c_unload", "partner", "c_load"],
        waterfall,
    )
    print(f"  Rows extracted: {len(iww_rows):,}")
    all_rows.extend(iww_rows)

    # ══════════════════════════════════════════════════════════
    # MARITIME — per-country tables (mar_go_am_{iso2})
    # Partner column: par_mar
    # Flow dimension: direct (INWARD = imports, OUTWARD = exports)
    # ══════════════════════════════════════════════════════════

    maritime_total = 0
    maritime_files_parsed = 0

    # Maritime flow filter: accept INWARD only (imports)
    maritime_flow_filter = (
        frozenset(["INWARD", "IMP", "IN", "1"]),   # accepted
        frozenset(["OUTWARD", "OUT", "EXP", "2", "TOTAL"]),  # rejected
    )

    for isi_code, iso2 in sorted(MARITIME_ISO2_FILE.items()):
        mar_file = RAW_DIR / f"mar_go_am_{iso2}.csv"
        if not mar_file.exists():
            print(f"  WARNING: missing {mar_file.name} (maritime {isi_code})")
            continue

        mar_rows = parse_mode_file(
            mar_file,
            "maritime",
            ["par_mar", "partner", "c_unload"],
            waterfall,
            import_flow_filter=maritime_flow_filter,
        )
        maritime_total += len(mar_rows)
        maritime_files_parsed += 1
        all_rows.extend(mar_rows)

    print(f"Parsing: {maritime_files_parsed} maritime files")
    print(f"  Rows extracted: {maritime_total:,}")

    # ══════════════════════════════════════════════════════════
    # Post-parse checks
    # ══════════════════════════════════════════════════════════

    total_kept = len(all_rows)
    waterfall["kept"] = total_kept

    print()
    print("-" * 68)
    print("POST-PARSE VALIDATION")
    print("-" * 68)
    print()

    if total_kept == 0:
        print("FATAL: zero rows survived parsing.", file=sys.stderr)
        sys.exit(1)

    # Verify all reporters are EU-27
    reporters_seen = set()
    partners_seen = set()
    years_seen = set()
    modes_seen = set()
    total_tonnes = 0.0

    for reporter, partner, mode, year, tonnes in all_rows:
        reporters_seen.add(reporter)
        partners_seen.add(partner)
        years_seen.add(year)
        modes_seen.add(mode)
        total_tonnes += tonnes

    non_eu27_reporters = reporters_seen - EU27
    if non_eu27_reporters:
        print(f"FATAL: non-EU-27 reporters in output: "
              f"{sorted(non_eu27_reporters)}", file=sys.stderr)
        sys.exit(1)

    print(f"  Total rows:         {total_kept:>12,}")
    print(f"  Total tonnes:       {total_tonnes:>16,.1f}")
    print(f"  Unique reporters:   {len(reporters_seen):>12} "
          f"({sorted(reporters_seen)})")
    print(f"  Unique partners:    {len(partners_seen):>12}")
    print(f"  Modes:              {sorted(modes_seen)}")
    print(f"  Years:              {sorted(years_seen)}")
    print()

    # Per-mode reporter coverage
    mode_reporters = defaultdict(set)
    for reporter, partner, mode, year, tonnes in all_rows:
        mode_reporters[mode].add(reporter)

    for mode in sorted(modes_seen):
        reps = mode_reporters[mode] & EU27
        print(f"  {mode:10s} reporters: {len(reps):>3}/27  "
              f"{sorted(reps)}")
    print()

    # ══════════════════════════════════════════════════════════
    # Sort and write flat output
    # ══════════════════════════════════════════════════════════

    all_rows.sort(key=lambda r: (r[0], r[2], r[1], r[3]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUT_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FLAT_FIELDNAMES)
        for row in all_rows:
            w.writerow(row)

    print(f"Flat output:  {OUT_FILE}")
    print(f"  Rows: {total_kept:,}")

    # ══════════════════════════════════════════════════════════
    # Audit per reporter × mode
    # ══════════════════════════════════════════════════════════

    audit_key_partners = defaultdict(set)
    audit_key_tonnes = defaultdict(float)
    audit_key_years = defaultdict(set)

    for reporter, partner, mode, year, tonnes in all_rows:
        key = (reporter, mode)
        audit_key_partners[key].add(partner)
        audit_key_tonnes[key] += tonnes
        audit_key_years[key].add(year)

    with open(AUDIT_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(AUDIT_FIELDNAMES)
        for key in sorted(audit_key_partners.keys()):
            reporter, mode = key
            w.writerow([
                reporter,
                mode,
                len(audit_key_partners[key]),
                audit_key_tonnes[key],
                len(audit_key_years[key]),
            ])

    audit_entries = len(audit_key_partners)
    print(f"Audit:        {AUDIT_FILE}")
    print(f"  Entries: {audit_entries} (reporter x mode)")

    # ══════════════════════════════════════════════════════════
    # Waterfall
    # ══════════════════════════════════════════════════════════

    waterfall_stages = [
        ("raw_rows_scanned", waterfall["raw_rows_scanned"]),
        ("dropped_reporter_empty", waterfall["dropped_reporter_empty"]),
        ("dropped_reporter_aggregate", waterfall["dropped_reporter_aggregate"]),
        ("dropped_reporter_not_eu27", waterfall["dropped_reporter_not_eu27"]),
        ("dropped_partner_empty", waterfall["dropped_partner_empty"]),
        ("dropped_partner_aggregate", waterfall["dropped_partner_aggregate"]),
        ("dropped_time_not_annual", waterfall["dropped_time_not_annual"]),
        ("dropped_year_outside_window", waterfall["dropped_year_outside_window"]),
        ("dropped_flow_not_import", waterfall["dropped_flow_not_import"]),
        ("dropped_unit_not_tonnes", waterfall["dropped_unit_not_tonnes"]),
        ("dropped_value_missing", waterfall["dropped_value_missing"]),
        ("dropped_value_non_numeric", waterfall["dropped_value_non_numeric"]),
        ("dropped_value_negative", waterfall["dropped_value_negative"]),
        ("zero_value_kept", waterfall["zero_value_kept"]),
        ("kept", waterfall["kept"]),
    ]

    with open(WATERFALL_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "count"])
        for stage, count in waterfall_stages:
            w.writerow([stage, count])

    print(f"Waterfall:    {WATERFALL_FILE}")

    # ══════════════════════════════════════════════════════════
    # Print waterfall summary
    # ══════════════════════════════════════════════════════════

    print()
    print("-" * 68)
    print("PARSER WATERFALL")
    print("-" * 68)
    for stage, count in waterfall_stages:
        print(f"  {stage:40s} {count:>12,}")

    # ══════════════════════════════════════════════════════════
    # Final checks
    # ══════════════════════════════════════════════════════════

    print()
    print("=" * 68)

    if total_kept == 0:
        print("Parser: FAIL — zero rows in output.", file=sys.stderr)
        sys.exit(1)

    # Verify no GR leaked through
    gr_leak = [r for r in all_rows if r[0] == "GR" or r[1] == "GR"]
    if gr_leak:
        print(f"FATAL: GR (Greece) code leaked into output. "
              f"Expected EL. Rows: {len(gr_leak)}", file=sys.stderr)
        sys.exit(1)

    print("Parser: PASS")
    print("=" * 68)
    print()
    print(f"  Output:     {OUT_FILE}")
    print(f"  Rows:       {total_kept:,}")
    print(f"  Reporters:  {len(reporters_seen)} EU-27 members")
    print(f"  Partners:   {len(partners_seen)}")
    print(f"  Modes:      {sorted(modes_seen)}")
    print(f"  Years:      {sorted(years_seen)}")
    print(f"  Tonnes:     {total_tonnes:,.1f}")
    print()


if __name__ == "__main__":
    main()
