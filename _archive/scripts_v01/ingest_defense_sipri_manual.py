#!/usr/bin/env python3
"""ISI v0.1 — SIPRI Arms Transfers Manual Ingestion Gate

Validates presence and basic structure of the manually downloaded
SIPRI Trade Register CSV.

Expected raw file:
  data/raw/sipri/sipri_trade_register_2019_2024.csv

The file must be downloaded from:
  https://armstransfers.sipri.org/
  → Trade Register
  → Recipients: select all EU-27 individually
  → Suppliers: all
  → Armament category: all
  → Year range: 2019–2024 (deliveries)
  → Export to CSV

This script does NOT download data.
This script does NOT modify data.

Task: ISI-DEFENSE-INGEST
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "sipri" / "sipri_trade_register_2019_2024.csv"

# Minimum expected columns (SIPRI Trade Register CSV format).
# The actual column names may vary slightly across export versions.
# We check for the presence of essential fields.
# SIPRI CSV compatibility fix (2024 format) — substring patterns
REQUIRED_FIELDS_PATTERNS = [
    "recipient",
    "supplier",
    "description",
    "number delivered",
    "tiv per unit",
    "year(s) of deliver",
]


def main():
    print(f"Checking: {RAW_FILE}")

    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found: {RAW_FILE}", file=sys.stderr)
        print()
        print("To obtain this file:", file=sys.stderr)
        print("  1. Go to https://armstransfers.sipri.org/", file=sys.stderr)
        print("  2. Select 'Trade Register'", file=sys.stderr)
        print("  3. Recipients: all EU-27 countries", file=sys.stderr)
        print("  4. Suppliers: all", file=sys.stderr)
        print("  5. Armament category: all", file=sys.stderr)
        print("  6. Year range: 2019–2024", file=sys.stderr)
        print("  7. Export to CSV", file=sys.stderr)
        print(f"  8. Save as: {RAW_FILE}", file=sys.stderr)
        sys.exit(1)

    # Read header and count rows
    # SIPRI CSV encoding fix: file contains Latin-1 chars (e.g. Wärtsilä, Göteborg)
    with open(RAW_FILE, "r", encoding="latin-1", newline="") as f:
        reader = csv.reader(f)
        # SIPRI CSV compatibility fix (2024 format): skip 11 metadata lines
        for _ in range(11):
            next(reader)
        header = next(reader)
        header_lower = [h.strip().lower() for h in header]

        row_count = 0
        for _ in reader:
            row_count += 1

    print(f"  Header columns ({len(header)}): {header}")
    print(f"  Data rows: {row_count}")

    # Check required fields
    missing = []
    for pattern in REQUIRED_FIELDS_PATTERNS:
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

    print()
    print(f"Ingestion gate: PASS")
    print(f"  File: {RAW_FILE}")
    print(f"  Columns: {len(header)}")
    print(f"  Rows: {row_count}")


if __name__ == "__main__":
    main()
