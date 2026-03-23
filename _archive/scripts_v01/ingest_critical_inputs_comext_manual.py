#!/usr/bin/env python3
"""ISI v0.1 — Axis 5: Critical Inputs / Raw Materials Dependency
Script 1: Ingest Gate

Validates the manually downloaded Eurostat Comext CSV for critical
raw materials BEFORE any parsing or computation.

Expected raw file:
  data/raw/critical_inputs/eu_comext_critical_inputs_cn8_2022_2024.csv

Authoritative CN8 mapping:
  docs/mappings/critical_materials_cn8_mapping_v01.csv

This script does NOT download data.
This script does NOT modify data.
This script does NOT write output files.
All reporting is to stdout/stderr.

If ANY validation fails, exit with non-zero status.

Task: ISI-CRIT-INGEST
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "critical_inputs"
    / "eu_comext_critical_inputs_cn8_2022_2024.csv"
)

MAPPING_FILE = (
    PROJECT_ROOT
    / "docs"
    / "mappings"
    / "critical_materials_cn8_mapping_v01.csv"
)

REQUIRED_COLUMNS = [
    "DECLARANT_ISO",
    "PARTNER_ISO",
    "PRODUCT_NC",
    "FLOW",
    "PERIOD",
    "VALUE_IN_EUROS",
]

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

# GR is Eurostat's code for Greece; ISI uses EL.
# Both are accepted as valid EU-27 reporters.
EU27_WITH_GR = EU27 | {"GR"}

VALID_YEARS = {"2022", "2023", "2024"}

REJECT_REPORTER_PATTERNS = {
    "EU27_2020", "EU28", "EU27_2007", "EU25", "EU15",
    "EA19", "EA20", "EFTA",
}


def load_mapping_codes():
    """Load the 66 authoritative CN8 codes from the mapping CSV."""
    if not MAPPING_FILE.exists():
        print(f"FATAL: mapping file not found: {MAPPING_FILE}", file=sys.stderr)
        sys.exit(1)

    codes = set()
    with open(MAPPING_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "cn8_code" not in reader.fieldnames:
            print(f"FATAL: mapping file missing 'cn8_code' column", file=sys.stderr)
            sys.exit(1)
        for row in reader:
            code = row["cn8_code"].strip()
            codes.add(code)

    if len(codes) != 66:
        print(
            f"FATAL: mapping file contains {len(codes)} unique CN8 codes, expected 66",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Mapping loaded: {len(codes)} CN8 codes from {MAPPING_FILE.name}")
    return codes


def main():
    print("=" * 64)
    print("ISI v0.1 — Axis 5: Critical Inputs Ingest Gate")
    print("=" * 64)
    print()

    # ── 0. Load authoritative mapping ────────────────────────────
    mapping_codes = load_mapping_codes()

    # ── 1. File existence ────────────────────────────────────────
    print(f"Raw file: {RAW_FILE}")
    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found.", file=sys.stderr)
        print(f"Run the automated download script first:", file=sys.stderr)
        print(f"  python scripts/download_critical_inputs_comext.py", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Or download manually from Eurostat Comext (ds-045409):", file=sys.stderr)
        print(f"  Reporters: EU-27", file=sys.stderr)
        print(f"  Partners: all (bilateral)", file=sys.stderr)
        print(f"  Products: 66 CN8 codes per mapping", file=sys.stderr)
        print(f"  Flow: Imports", file=sys.stderr)
        print(f"  Indicator: VALUE_IN_EUROS", file=sys.stderr)
        print(f"  Period: 2022, 2023, 2024", file=sys.stderr)
        print(f"  Save as: {RAW_FILE}", file=sys.stderr)
        sys.exit(1)
    print(f"  File exists: {RAW_FILE.stat().st_size:,} bytes")
    print()

    # ── 2. Column validation ─────────────────────────────────────
    with open(RAW_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

    if fieldnames is None:
        print("FATAL: could not read CSV header.", file=sys.stderr)
        sys.exit(1)

    print(f"Columns found ({len(fieldnames)}): {fieldnames}")
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing_cols:
        print(f"FATAL: missing required columns: {missing_cols}", file=sys.stderr)
        sys.exit(1)
    print(f"  All {len(REQUIRED_COLUMNS)} required columns present.")
    print()

    # ── 3–7. Row-level validation ────────────────────────────────
    total_rows = 0
    rows_kept = 0
    zero_value_count = 0

    # Drop-reason counters
    dropped_flow = 0
    dropped_year_invalid = 0
    dropped_product_not_8digit = 0
    dropped_product_not_in_mapping = 0
    dropped_reporter_aggregate = 0
    dropped_reporter_not_eu27 = 0
    dropped_value_non_numeric = 0
    dropped_value_negative = 0

    reporters_seen = set()
    cn8_codes_seen = set()
    partners_seen = set()
    years_seen = set()

    with open(RAW_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total_rows += 1

            declarant = row["DECLARANT_ISO"].strip()
            partner = row["PARTNER_ISO"].strip()
            product = row["PRODUCT_NC"].strip()
            flow = row["FLOW"].strip()
            period = row["PERIOD"].strip()
            value_str = row["VALUE_IN_EUROS"].strip()

            # ── 6. Flow validation ───────────────────────────────
            if flow != "1":
                dropped_flow += 1
                continue

            # ── 5. Temporal validation ───────────────────────────
            if period not in VALID_YEARS:
                dropped_year_invalid += 1
                continue
            years_seen.add(period)

            # ── 3. CN8 code validation ───────────────────────────
            if len(product) != 8 or not product.isdigit():
                dropped_product_not_8digit += 1
                continue

            if product not in mapping_codes:
                dropped_product_not_in_mapping += 1
                continue

            # ── 4. Geographic validation ─────────────────────────
            if declarant in REJECT_REPORTER_PATTERNS:
                dropped_reporter_aggregate += 1
                continue

            if declarant not in EU27_WITH_GR:
                dropped_reporter_not_eu27 += 1
                continue

            # ── 7. Value validation ──────────────────────────────
            try:
                value = float(value_str)
            except (ValueError, TypeError):
                dropped_value_non_numeric += 1
                continue

            if value < 0:
                dropped_value_negative += 1
                continue

            if value == 0:
                zero_value_count += 1

            # Row passes all checks
            rows_kept += 1
            reporters_seen.add(declarant)
            cn8_codes_seen.add(product)
            partners_seen.add(partner)

    # ── Compute totals ───────────────────────────────────────────
    total_dropped = (
        dropped_flow
        + dropped_year_invalid
        + dropped_product_not_8digit
        + dropped_product_not_in_mapping
        + dropped_reporter_aggregate
        + dropped_reporter_not_eu27
        + dropped_value_non_numeric
        + dropped_value_negative
    )

    # ── CN8 coverage check ───────────────────────────────────────
    mapping_missing = mapping_codes - cn8_codes_seen
    data_only = cn8_codes_seen - mapping_codes  # should be 0 by filter logic

    # ── Reporter coverage check ──────────────────────────────────
    # Normalise GR → EL for coverage comparison
    reporters_normalised = set()
    for r in reporters_seen:
        reporters_normalised.add("EL" if r == "GR" else r)
    eu27_missing = EU27 - reporters_normalised

    # ── 8. Audit summary ─────────────────────────────────────────
    print("=" * 64)
    print("AUDIT SUMMARY")
    print("=" * 64)
    print()
    print(f"Total rows read:              {total_rows:>10,}")
    print(f"Rows kept (pass all checks):  {rows_kept:>10,}")
    print(f"Rows dropped:                 {total_dropped:>10,}")
    print()
    print("Drop reasons:")
    print(f"  Flow != 1 (not import):     {dropped_flow:>10,}")
    print(f"  Year not in 2022-2024:      {dropped_year_invalid:>10,}")
    print(f"  Product not 8-digit:        {dropped_product_not_8digit:>10,}")
    print(f"  Product not in mapping:     {dropped_product_not_in_mapping:>10,}")
    print(f"  Reporter is aggregate:      {dropped_reporter_aggregate:>10,}")
    print(f"  Reporter not EU-27:         {dropped_reporter_not_eu27:>10,}")
    print(f"  Value non-numeric:          {dropped_value_non_numeric:>10,}")
    print(f"  Value negative:             {dropped_value_negative:>10,}")
    print()
    print(f"Zero-value rows (kept):       {zero_value_count:>10,}")
    print()
    print(f"Unique reporters:             {len(reporters_seen):>10}")
    print(f"  Reporters: {sorted(reporters_seen)}")
    print(f"Unique CN8 codes observed:    {len(cn8_codes_seen):>10}")
    print(f"Unique partners:              {len(partners_seen):>10}")
    print(f"Years present:                {sorted(years_seen)}")
    print()

    # ── Hard-fail checks ─────────────────────────────────────────
    fatal = False

    if total_rows == 0:
        print("FATAL: file contains zero data rows.", file=sys.stderr)
        fatal = True

    if rows_kept == 0:
        print("FATAL: zero rows survived validation.", file=sys.stderr)
        fatal = True

    if mapping_missing:
        print(
            f"FATAL: {len(mapping_missing)} mapping CN8 codes missing from raw data:",
            file=sys.stderr,
        )
        for code in sorted(mapping_missing):
            print(f"  {code}", file=sys.stderr)
        fatal = True

    if data_only:
        print(
            f"FATAL: {len(data_only)} CN8 codes in data but not in mapping:",
            file=sys.stderr,
        )
        for code in sorted(data_only):
            print(f"  {code}", file=sys.stderr)
        fatal = True

    if eu27_missing:
        print(
            f"FATAL: {len(eu27_missing)} EU-27 members missing as reporters:",
            file=sys.stderr,
        )
        for geo in sorted(eu27_missing):
            print(f"  {geo}", file=sys.stderr)
        fatal = True

    missing_years = VALID_YEARS - years_seen
    if missing_years:
        print(
            f"FATAL: required years missing from data: {sorted(missing_years)}",
            file=sys.stderr,
        )
        fatal = True

    if fatal:
        print()
        print("Ingest gate: FAIL", file=sys.stderr)
        sys.exit(1)

    # ── PASS ─────────────────────────────────────────────────────
    print("=" * 64)
    print("Ingest gate: PASS")
    print("=" * 64)
    print(f"  File:       {RAW_FILE}")
    print(f"  Size:       {RAW_FILE.stat().st_size:,} bytes")
    print(f"  Rows kept:  {rows_kept:,}")
    print(f"  Reporters:  {len(reporters_seen)} EU-27 members")
    print(f"  CN8 codes:  {len(cn8_codes_seen)}/66")
    print(f"  Partners:   {len(partners_seen)}")
    print(f"  Years:      {sorted(years_seen)}")


if __name__ == "__main__":
    main()
