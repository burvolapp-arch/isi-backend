#!/usr/bin/env python3
"""ISI v0.1 — Eurostat Comext Semiconductor Imports Manual Ingestion Gate

Validates presence and basic structure of the manually downloaded
Eurostat Comext bilateral semiconductor import CSV (CN8 level).

Expected raw file:
  data/raw/tech/eu_comext_semiconductors_cn8_2022_2024.csv

The file must be downloaded from:
  https://ec.europa.eu/eurostat
  → Comext / Easy Comext
  → Dataset: ds-045409
  → Reporters: all EU-27
  → Partners: all (bilateral)
  → Products: HS 8541 (CN8 subcodes), HS 8542
  → Flow: Imports (code 1)
  → Indicator: VALUE_IN_EUROS
  → Period: 2022, 2023, 2024
  → Format: CSV (flat, annual)
  → Granularity: CN8 for HS 8541, HS4 for HS 8542

This script does NOT download data.
This script does NOT modify data.

Known quirk: the raw CSV has a DUPLICATE TIME_PERIOD column
(index 15 = year data, index 16 = always empty). Validation
checks for this and reports it. Parser must use index-based
access for TIME_PERIOD.

Task: ISI-TECH-INGEST
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "tech" / "eu_comext_semiconductors_cn8_2022_2024.csv"

# Required field patterns (substring match, case-insensitive).
# These correspond to the Eurostat Comext ds-045409 CSV schema.
REQUIRED_FIELD_PATTERNS = [
    "reporter",       # REPORTER column (geo code)
    "partner",        # PARTNER column (geo code)
    "product",        # PRODUCT column (HS code)
    "flow",           # FLOW column (1 = imports)
    "indicators",     # INDICATORS column (VALUE_IN_EUROS)
    "obs_value",      # OBS_VALUE column (trade value)
    "time_period",    # TIME_PERIOD column (year)
]

# Key column indices (verified during inspection)
# Index 5 = REPORTER, 7 = PARTNER, 9 = PRODUCT, 11 = FLOW
# Index 15 = TIME_PERIOD (data), 16 = TIME_PERIOD (empty duplicate)
# Index 17 = OBS_VALUE
COL_REPORTER = 5
COL_PARTNER = 7
COL_PRODUCT = 9
COL_FLOW = 11
COL_TIME_PERIOD = 15
COL_TIME_PERIOD_DUP = 16
COL_OBS_VALUE = 17


def main():
    print(f"Checking: {RAW_FILE}")

    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found: {RAW_FILE}", file=sys.stderr)
        print()
        print("To obtain this file:", file=sys.stderr)
        print("  1. Go to https://ec.europa.eu/eurostat (Comext)", file=sys.stderr)
        print("  2. Dataset: ds-045409", file=sys.stderr)
        print("  3. Reporters: all EU-27 countries", file=sys.stderr)
        print("  4. Partners: all (bilateral)", file=sys.stderr)
        print("  5. Products: HS 8541 (CN8 subcodes), HS 8542", file=sys.stderr)
        print("  6. Flow: Imports (code 1)", file=sys.stderr)
        print("  7. Indicator: VALUE_IN_EUROS", file=sys.stderr)
        print("  8. Period: 2022, 2023, 2024", file=sys.stderr)
        print("  9. Export as CSV", file=sys.stderr)
        print(f" 10. Save as: {RAW_FILE}", file=sys.stderr)
        sys.exit(1)

    # Read header and count rows
    with open(RAW_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        header_lower = [h.strip().lower() for h in header]

        row_count = 0
        products_seen = set()
        for row in reader:
            row_count += 1
            products_seen.add(row[COL_PRODUCT].strip())

    print(f"  Header columns ({len(header)}): {header}")
    print(f"  Data rows: {row_count}")

    # Check required field patterns
    missing = []
    for pattern in REQUIRED_FIELD_PATTERNS:
        found = any(pattern in h for h in header_lower)
        if not found:
            missing.append(pattern)

    if missing:
        print(f"FATAL: missing required field patterns: {missing}", file=sys.stderr)
        print(f"  Found headers: {header}", file=sys.stderr)
        sys.exit(1)

    print(f"  All required field patterns found.")

    if row_count == 0:
        print("FATAL: file contains zero data rows.", file=sys.stderr)
        sys.exit(1)

    # Check for duplicate TIME_PERIOD column
    time_period_indices = [i for i, h in enumerate(header_lower) if "time_period" in h]
    if len(time_period_indices) > 1:
        print(f"  WARNING: duplicate TIME_PERIOD columns at indices {time_period_indices}")
        print(f"  Parser will use index {COL_TIME_PERIOD} (first occurrence with data).")
    elif len(time_period_indices) == 1:
        print(f"  TIME_PERIOD column at index {time_period_indices[0]}")

    # Verify expected column count
    if len(header) < COL_OBS_VALUE + 1:
        print(f"FATAL: expected at least {COL_OBS_VALUE + 1} columns, found {len(header)}", file=sys.stderr)
        sys.exit(1)

    # Report product codes found
    print(f"  Product codes found: {sorted(products_seen)}")
    valid_cn8 = {"85411000", "85412100", "85412900", "85413000",
                 "85416000", "85419000", "8542"}
    unexpected = products_seen - valid_cn8
    if unexpected:
        print(f"  WARNING: unexpected product codes: {sorted(unexpected)}")

    # DEFENSIVE: check for solar PV contamination
    solar_pv = [p for p in products_seen if p.startswith("854140")]
    if solar_pv:
        print(f"FATAL: solar PV product codes detected: {solar_pv}", file=sys.stderr)
        print(f"  CN 854140xx (photovoltaic cells) must NOT be in the data.", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"  Solar PV guard (854140xx): CLEAR — not present")

    # Spot-check: read first data row and verify key columns are plausible
    with open(RAW_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        first_row = next(reader)

    reporter = first_row[COL_REPORTER]
    partner = first_row[COL_PARTNER]
    product = first_row[COL_PRODUCT]
    flow = first_row[COL_FLOW]
    year = first_row[COL_TIME_PERIOD]
    value = first_row[COL_OBS_VALUE]

    print(f"  Spot check (row 1):")
    print(f"    reporter={reporter} partner={partner} product={product} flow={flow} year={year} value={value}")

    # Validate spot check
    if not reporter.isalpha():
        print(f"  WARNING: reporter '{reporter}' at index {COL_REPORTER} is not alphabetic — check column alignment")
    if not partner.isalpha():
        print(f"  WARNING: partner '{partner}' at index {COL_PARTNER} is not alphabetic — check column alignment")
    if product not in valid_cn8:
        print(f"  WARNING: product '{product}' at index {COL_PRODUCT} is not a valid CN8/HS4 code — check column alignment")
    if year not in ("2022", "2023", "2024"):
        print(f"  WARNING: year '{year}' at index {COL_TIME_PERIOD} is not 2022/2023/2024 — check column alignment")

    print()
    print(f"Ingestion gate: PASS")
    print(f"  File: {RAW_FILE}")
    print(f"  Size: {RAW_FILE.stat().st_size:,} bytes")
    print(f"  Rows: {row_count}")
    print(f"  Columns: {len(header)}")
    print(f"  Product codes: {sorted(products_seen)}")
    print(f"  Solar PV (854140xx): ABSENT ✓")


if __name__ == "__main__":
    main()
