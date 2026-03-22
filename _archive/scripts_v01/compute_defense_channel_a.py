#!/usr/bin/env python3
"""ISI v0.1 — Defense Channel A: Aggregate Supplier Concentration (2019-2024)

Input:
  data/processed/defense/sipri_bilateral_2019_2024_flat.csv
  Schema: recipient_country,supplier_country,capability_block,year,tiv

Outputs:
  data/processed/defense/sipri_channel_a_shares.csv
  Schema: recipient_country,supplier_country,share

  data/processed/defense/sipri_channel_a_concentration.csv
  Schema: recipient_country,concentration

  data/processed/defense/sipri_channel_a_volumes.csv
  Schema: recipient_country,total_tiv

Methodology (locked):
  For each recipient i, aggregate ALL TIV across all blocks and years.
  s_{i,j}^(A) = V_{i,j}^(A) / SUM_j V_{i,j}^(A)
  C_i^(A) = SUM_j (s_{i,j}^(A))^2
  W_i^(A) = SUM_j V_{i,j}^(A)

Constraints:
  - Shares sum to 1.0 per recipient (tolerance 1e-9)
  - Hard-fail if any share < 0 or > 1
  - Hard-fail if any HHI not in [0, 1]
  - EU-27 only in output

Task: ISI-DEFENSE-CHANNEL-A
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "defense" / "sipri_bilateral_2019_2024_flat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "defense"

SHARES_FILE = OUT_DIR / "sipri_channel_a_shares.csv"
CONC_FILE = OUT_DIR / "sipri_channel_a_concentration.csv"
VOL_FILE = OUT_DIR / "sipri_channel_a_volumes.csv"

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

SHARE_SUM_TOLERANCE = 1e-9


def main():
    if not INPUT_FILE.exists():
        print(f"FATAL: input not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Input:   {INPUT_FILE}")

    # Accumulate total TIV per (recipient, supplier) across all blocks/years
    pair_values = defaultdict(float)
    rec_totals = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            rec = row["recipient_country"]
            sup = row["supplier_country"]
            tiv = float(row["tiv"])

            if rec not in EU27:
                continue

            pair_values[(rec, sup)] += tiv
            rec_totals[rec] += tiv

    print(f"  Rows read: {rows_read}")
    print(f"  EU-27 recipients: {len(rec_totals)}")

    # Check zero-volume recipients
    zero_vol = [r for r, t in rec_totals.items() if t == 0.0]
    if zero_vol:
        print(f"  WARNING: zero-volume recipients: {sorted(zero_vol)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    share_rows_written = 0

    with open(SHARES_FILE, "w", newline="") as fs, \
         open(CONC_FILE, "w", newline="") as fc, \
         open(VOL_FILE, "w", newline="") as fv:

        sw = csv.writer(fs)
        sw.writerow(["recipient_country", "supplier_country", "share"])

        cw = csv.writer(fc)
        cw.writerow(["recipient_country", "concentration"])

        vw = csv.writer(fv)
        vw.writerow(["recipient_country", "total_tiv"])

        for rec in sorted(rec_totals.keys()):
            total = rec_totals[rec]
            vw.writerow([rec, total])

            if total == 0.0:
                continue

            # Collect suppliers for this recipient
            sup_pairs = sorted(
                [(sup, val) for (r, sup), val in pair_values.items() if r == rec],
                key=lambda x: x[0],
            )

            share_sum = 0.0
            hhi = 0.0

            for sup, val in sup_pairs:
                share = val / total

                if share < 0.0:
                    print(f"FATAL: negative share {share} for {rec} <- {sup}", file=sys.stderr)
                    sys.exit(1)
                if share > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: share > 1 ({share}) for {rec} <- {sup}", file=sys.stderr)
                    sys.exit(1)

                sw.writerow([rec, sup, share])
                share_rows_written += 1
                share_sum += share
                hhi += share ** 2

            # Verify shares sum
            if abs(share_sum - 1.0) > SHARE_SUM_TOLERANCE:
                print(f"FATAL: shares sum to {share_sum} for {rec}", file=sys.stderr)
                sys.exit(1)

            # Verify HHI bounds
            if hhi < 0.0 or hhi > 1.0 + SHARE_SUM_TOLERANCE:
                print(f"FATAL: HHI out of bounds ({hhi}) for {rec}", file=sys.stderr)
                sys.exit(1)

            cw.writerow([rec, hhi])

    # EU-27 coverage
    present = sorted(EU27 & set(rec_totals.keys()))
    missing = sorted(EU27 - set(rec_totals.keys()))

    print()
    print(f"Channel A results:")
    print(f"  Shares:        {SHARES_FILE} ({share_rows_written} rows)")
    print(f"  Concentration: {CONC_FILE} ({len(rec_totals)} recipients)")
    print(f"  Volumes:       {VOL_FILE}")
    print(f"  EU-27 present: {len(present)}/27")
    if missing:
        print(f"  EU-27 missing: {missing}")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
