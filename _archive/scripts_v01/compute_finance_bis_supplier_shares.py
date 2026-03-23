#!/usr/bin/env python3
"""ISI v0.1 — Channel A: Cross-Border Banking Creditor Shares (2024-Q4)

Input:
  data/processed/finance/bis_lbs_inward_2024_flat.csv
  Schema: counterparty_country,reporting_country,period,value_usd_mn

Outputs:
  data/processed/finance/bis_lbs_inward_2024_shares.csv
  Schema: counterparty_country,reporting_country,share

  data/processed/finance/bis_lbs_inward_2024_volumes.csv
  Schema: counterparty_country,total_value_usd_mn

Methodology (frozen, Section 6):
  s_{i,j}^(A) = V_{i,j}^(A) / SUM_j V_{i,j}^(A)
  W_i^(A)     = SUM_j V_{i,j}^(A)

  where i = counterparty_country (debtor), j = reporting_country (creditor)

Constraints:
  - Shares sum to 1.0 per counterparty_country (tolerance 1e-9)
  - Hard-fail if any share < 0 or > 1
  - Skip counterparty_country where total_volume == 0 (log warning)
  - No pandas; csv.reader / csv.writer only

Task: ISI-FINANCE-BIS-SHARES
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "finance" / "bis_lbs_inward_2024_flat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "finance"
SHARES_FILE = OUT_DIR / "bis_lbs_inward_2024_shares.csv"
VOLUMES_FILE = OUT_DIR / "bis_lbs_inward_2024_volumes.csv"

SHARES_FIELDNAMES = [
    "counterparty_country",
    "reporting_country",
    "share",
]

VOLUMES_FIELDNAMES = [
    "counterparty_country",
    "total_value_usd_mn",
]

SHARE_SUM_TOLERANCE = 1e-9


def main():
    # ── Verify input ──
    if not INPUT_FILE.exists():
        print(f"FATAL: input file not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Input:   {INPUT_FILE}")
    print(f"Shares:  {SHARES_FILE}")
    print(f"Volumes: {VOLUMES_FILE}")

    # ── Accumulate volumes per (cp, rep) and totals per cp ──
    pair_values = defaultdict(float)
    cp_totals = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            cp = row["counterparty_country"]
            rep = row["reporting_country"]
            val_str = row["value_usd_mn"]

            try:
                val = float(val_str)
            except (ValueError, TypeError):
                print(f"FATAL: non-numeric value at row {rows_read}: {val_str}", file=sys.stderr)
                sys.exit(1)

            pair_values[(cp, rep)] += val
            cp_totals[cp] += val

    print(f"  Rows read: {rows_read}")
    print(f"  Counterparty countries: {len(cp_totals)}")

    # ── Check for zero-volume counterparty countries ──
    zero_vol = sorted([c for c, t in cp_totals.items() if t == 0.0])
    if zero_vol:
        print(f"  WARNING: {len(zero_vol)} counterparty countries with zero total volume (skipped):")
        for c in zero_vol:
            print(f"    {c}")

    # ── Write shares and volumes ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    share_rows_written = 0
    min_share = float("inf")
    max_share = float("-inf")

    with open(SHARES_FILE, "w", newline="") as fs, \
         open(VOLUMES_FILE, "w", newline="") as fv:

        sw = csv.writer(fs)
        sw.writerow(SHARES_FIELDNAMES)

        vw = csv.writer(fv)
        vw.writerow(VOLUMES_FIELDNAMES)

        for cp in sorted(cp_totals.keys()):
            total = cp_totals[cp]

            # Write volume row
            vw.writerow([cp, total])

            # Skip zero-volume countries
            if total == 0.0:
                continue

            # Collect reporting countries for this counterparty
            rep_pairs = sorted(
                [(rep, val) for (c, rep), val in pair_values.items() if c == cp],
                key=lambda x: x[0],
            )

            share_sum = 0.0

            for rep, val in rep_pairs:
                share = val / total

                # Hard-fail bounds check
                if share < 0.0:
                    print(f"FATAL: negative share {share} for {cp} <- {rep}", file=sys.stderr)
                    sys.exit(1)
                if share > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: share > 1 ({share}) for {cp} <- {rep}", file=sys.stderr)
                    sys.exit(1)

                sw.writerow([cp, rep, share])
                share_rows_written += 1
                share_sum += share

                if share < min_share:
                    min_share = share
                if share > max_share:
                    max_share = share

            # Verify shares sum to 1.0
            if abs(share_sum - 1.0) > SHARE_SUM_TOLERANCE:
                print(f"FATAL: shares for {cp} sum to {share_sum}, not 1.0", file=sys.stderr)
                sys.exit(1)

    # ── Report ──
    countries_with_shares = len(cp_totals) - len(zero_vol)

    print()
    print(f"Done.")
    print(f"  Counterparty countries processed: {countries_with_shares}")
    print(f"  Share rows written: {share_rows_written}")
    print(f"  Volume rows written: {len(cp_totals)}")
    print(f"  Min share: {min_share}")
    print(f"  Max share: {max_share}")
    print(f"  Zero-volume countries skipped: {len(zero_vol)}")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
