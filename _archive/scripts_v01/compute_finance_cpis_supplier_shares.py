#!/usr/bin/env python3
"""ISI v0.1 — Channel B: Portfolio Debt Securities Holder Shares (2024)

Input:
  data/processed/finance/cpis_debt_inward_2024_flat.csv
  Schema: reference_country,counterparty_country,instrument,period,value_usd_mn

Outputs:
  data/processed/finance/cpis_debt_inward_2024_shares.csv
  Schema: reference_country,counterparty_country,share

  data/processed/finance/cpis_debt_inward_2024_volumes.csv
  Schema: reference_country,total_value_usd_mn

Methodology (frozen, Section 7):
  s_{i,j}^(B) = V_{i,j}^(B) / SUM_j V_{i,j}^(B)
  W_i^(B)     = SUM_j V_{i,j}^(B)

Constraints:
  - Shares sum to 1.0 per reference_country (within float tolerance)
  - Hard-fail if any share < 0 or > 1
  - Skip reference_country where total_volume == 0 (log warning)
  - No pandas; csv.reader / csv.writer only

Task: ISI-FINANCE-CPIS-SHARES
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "finance" / "cpis_debt_inward_2024_flat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "finance"
SHARES_FILE = OUT_DIR / "cpis_debt_inward_2024_shares.csv"
VOLUMES_FILE = OUT_DIR / "cpis_debt_inward_2024_volumes.csv"

SHARES_FIELDNAMES = [
    "reference_country",
    "counterparty_country",
    "share",
]

VOLUMES_FIELDNAMES = [
    "reference_country",
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

    # ── Pass 1: accumulate volumes per (ref, cp) and totals per ref ──
    # Memory: bounded by number of bilateral pairs (~5-6k from flat file)
    pair_values = defaultdict(float)
    ref_totals = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            ref = row["reference_country"]
            cp = row["counterparty_country"]
            val_str = row["value_usd_mn"]

            try:
                val = float(val_str)
            except (ValueError, TypeError):
                print(f"FATAL: non-numeric value at row {rows_read}: {val_str}", file=sys.stderr)
                sys.exit(1)

            pair_values[(ref, cp)] += val
            ref_totals[ref] += val

    print(f"  Rows read: {rows_read}")
    print(f"  Reference countries: {len(ref_totals)}")

    # ── Check for zero-volume reference countries ──
    zero_vol_refs = sorted([r for r, t in ref_totals.items() if t == 0.0])
    if zero_vol_refs:
        print(f"  WARNING: {len(zero_vol_refs)} reference countries with zero total volume (skipped):")
        for r in zero_vol_refs:
            print(f"    {r}")

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

        for ref in sorted(ref_totals.keys()):
            total = ref_totals[ref]

            # Write volume row
            vw.writerow([ref, total])

            # Skip zero-volume countries
            if total == 0.0:
                continue

            # Collect counterparties for this ref
            cp_pairs = sorted(
                [(cp, val) for (r, cp), val in pair_values.items() if r == ref],
                key=lambda x: x[0],
            )

            share_sum = 0.0

            for cp, val in cp_pairs:
                share = val / total

                # Hard-fail bounds check
                if share < 0.0:
                    print(f"FATAL: negative share {share} for {ref} -> {cp}", file=sys.stderr)
                    sys.exit(1)
                if share > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: share > 1 ({share}) for {ref} -> {cp}", file=sys.stderr)
                    sys.exit(1)

                sw.writerow([ref, cp, share])
                share_rows_written += 1
                share_sum += share

                if share < min_share:
                    min_share = share
                if share > max_share:
                    max_share = share

            # Verify shares sum to 1.0
            if abs(share_sum - 1.0) > SHARE_SUM_TOLERANCE:
                print(f"FATAL: shares for {ref} sum to {share_sum}, not 1.0", file=sys.stderr)
                sys.exit(1)

    # ── Report ──
    countries_with_shares = len(ref_totals) - len(zero_vol_refs)

    print()
    print(f"Done.")
    print(f"  Reference countries processed: {countries_with_shares}")
    print(f"  Share rows written: {share_rows_written}")
    print(f"  Volume rows written: {len(ref_totals)}")
    print(f"  Min share: {min_share}")
    print(f"  Max share: {max_share}")
    print(f"  Zero-volume countries skipped: {len(zero_vol_refs)}")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
