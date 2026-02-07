#!/usr/bin/env python3
"""ISI v0.1 — Channel A: Cross-Border Banking Concentration / HHI (2024-Q4)

Input:
  data/processed/finance/bis_lbs_inward_2024_shares.csv
  Schema: counterparty_country,reporting_country,share

Output:
  data/processed/finance/bis_lbs_inward_2024_concentration.csv
  Schema: counterparty_country,concentration

Methodology (frozen, Section 6):
  C_i^(A) = SUM_j ( s_{i,j}^(A) )^2

  C_i^(A) is in [0, 1].
  C_i^(A) = 0 when exposure is uniformly spread across infinitely many creditors.
  C_i^(A) = 1 when all exposure is to a single creditor.

Constraints:
  - concentration ∈ [0, 1]
  - Hard-fail if any value is outside bounds
  - One row per counterparty_country
  - No pandas; csv.reader / csv.writer only

Task: ISI-FINANCE-BIS-CONCENTRATION
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "finance" / "bis_lbs_inward_2024_shares.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "finance"
OUT_FILE = OUT_DIR / "bis_lbs_inward_2024_concentration.csv"

OUT_FIELDNAMES = [
    "counterparty_country",
    "concentration",
]

BOUND_TOLERANCE = 1e-9


def main():
    # ── Verify input ──
    if not INPUT_FILE.exists():
        print(f"FATAL: input file not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Input:  {INPUT_FILE}")
    print(f"Output: {OUT_FILE}")

    # ── Accumulate sum of squared shares per counterparty_country ──
    hhi = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            cp = row["counterparty_country"]
            share_str = row["share"]

            try:
                share = float(share_str)
            except (ValueError, TypeError):
                print(f"FATAL: non-numeric share at row {rows_read}: {share_str}", file=sys.stderr)
                sys.exit(1)

            hhi[cp] += share * share

    print(f"  Share rows read: {rows_read}")
    print(f"  Counterparty countries: {len(hhi)}")

    # ── Write output ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    min_conc = float("inf")
    max_conc = float("-inf")
    rows_written = 0

    with open(OUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(OUT_FIELDNAMES)

        for cp in sorted(hhi.keys()):
            concentration = hhi[cp]

            # Hard-fail bounds check
            if concentration < 0.0 - BOUND_TOLERANCE:
                print(f"FATAL: concentration < 0 ({concentration}) for {cp}", file=sys.stderr)
                sys.exit(1)
            if concentration > 1.0 + BOUND_TOLERANCE:
                print(f"FATAL: concentration > 1 ({concentration}) for {cp}", file=sys.stderr)
                sys.exit(1)

            writer.writerow([cp, concentration])
            rows_written += 1

            if concentration < min_conc:
                min_conc = concentration
            if concentration > max_conc:
                max_conc = concentration

    # ── Report ──
    print()
    print(f"Done.")
    print(f"  Counterparty countries processed: {rows_written}")
    print(f"  Min concentration (HHI): {min_conc}")
    print(f"  Max concentration (HHI): {max_conc}")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
