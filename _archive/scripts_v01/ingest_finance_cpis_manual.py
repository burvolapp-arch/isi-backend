#!/usr/bin/env python3
"""ISI v0.1 — Validate presence of manually downloaded IMF CPIS raw file.

This script does NOT download anything.
It validates that the raw CPIS Excel file exists, is readable,
and contains at least one sheet.

Input:  data/raw/finance/cpis_2024_raw.xlsx  (manually placed)
Output: None (validation only)

Task: ISI-FINANCE-INGEST-CPIS-MANUAL
"""

import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("FATAL: openpyxl is not installed. Run: pip install openpyxl", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "finance" / "cpis_2024_raw.xlsx"


def main():
    # ── Check 1: file exists ──
    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found: {RAW_FILE}", file=sys.stderr)
        print(
            "Place the IMF CPIS export at data/raw/finance/cpis_2024_raw.xlsx",
            file=sys.stderr,
        )
        sys.exit(1)

    if not RAW_FILE.is_file():
        print(f"FATAL: path exists but is not a file: {RAW_FILE}", file=sys.stderr)
        sys.exit(1)

    # ── Check 2: file is readable as xlsx ──
    try:
        wb = openpyxl.load_workbook(RAW_FILE, read_only=True, data_only=True)
    except Exception as exc:
        print(f"FATAL: cannot read file as xlsx: {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Check 3: at least one sheet ──
    sheet_names = wb.sheetnames
    if len(sheet_names) == 0:
        print("FATAL: workbook contains zero sheets", file=sys.stderr)
        wb.close()
        sys.exit(1)

    wb.close()

    # ── Report ──
    print(f"OK: raw file validated: {RAW_FILE}")
    print(f"    file size: {RAW_FILE.stat().st_size} bytes")
    print(f"    sheets ({len(sheet_names)}): {sheet_names}")


if __name__ == "__main__":
    main()
