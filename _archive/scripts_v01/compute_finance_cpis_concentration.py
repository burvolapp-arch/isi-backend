#!/usr/bin/env python3
"""ISI v0.1 — Channel B: Portfolio Debt Securities Concentration / HHI (2024)

Input:
  data/processed/finance/cpis_debt_inward_2024_shares.csv
  Schema: reference_country,counterparty_country,share

Output:
  data/processed/finance/cpis_debt_inward_2024_concentration.csv
  Schema: reference_country,concentration

Methodology (frozen, Section 7):
  C_i^(B) = SUM_j ( s_{i,j}^(B) )^2

  C_i^(B) is in [0, 1].
  C_i^(B) = 0 when exposure is uniformly spread across infinitely many holders.
  C_i^(B) = 1 when all exposure is to a single holder.

Constraints:
  - concentration ∈ [0, 1]
  - Hard-fail if any value is outside bounds
  - One row per reference_country
  - No pandas; csv.reader / csv.writer only

Task: ISI-FINANCE-CPIS-CONCENTRATION
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "finance" / "cpis_debt_inward_2024_shares.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "finance"
OUT_FILE = OUT_DIR / "cpis_debt_inward_2024_concentration.csv"

OUT_FIELDNAMES = [
    "reference_country",
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

    # ── Accumulate sum of squared shares per reference_country ──
    hhi = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            ref = row["reference_country"]
            share_str = row["share"]

            try:
                share = float(share_str)
            except (ValueError, TypeError):
                print(f"FATAL: non-numeric share at row {rows_read}: {share_str}", file=sys.stderr)
                sys.exit(1)

            hhi[ref] += share * share

    print(f"  Share rows read: {rows_read}")
    print(f"  Reference countries: {len(hhi)}")

    # ── Write output ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    min_conc = float("inf")
    max_conc = float("-inf")
    rows_written = 0

    with open(OUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(OUT_FIELDNAMES)

        for ref in sorted(hhi.keys()):
            concentration = hhi[ref]

            # Hard-fail bounds check
            if concentration < 0.0 - BOUND_TOLERANCE:
                print(f"FATAL: concentration < 0 ({concentration}) for {ref}", file=sys.stderr)
                sys.exit(1)
            if concentration > 1.0 + BOUND_TOLERANCE:
                print(f"FATAL: concentration > 1 ({concentration}) for {ref}", file=sys.stderr)
                sys.exit(1)

            writer.writerow([ref, concentration])
            rows_written += 1

            if concentration < min_conc:
                min_conc = concentration
            if concentration > max_conc:
                max_conc = concentration

    # ── Report ──
    print()
    print(f"Done.")
    print(f"  Reference countries processed: {rows_written}")
    print(f"  Min concentration (HHI): {min_conc}")
    print(f"  Max concentration (HHI): {max_conc}")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
