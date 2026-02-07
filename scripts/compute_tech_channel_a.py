#!/usr/bin/env python3
"""ISI v0.1 — Technology Channel A: Aggregate Supplier Concentration (2022-2024)

Input:
  data/processed/tech/comext_semiconductor_2022_2024_flat.csv
  Schema: reporter,partner,product_nc,hs_category,year,value

Outputs:
  data/processed/tech/tech_channel_a_shares.csv
  Schema: reporter,partner,share

  data/processed/tech/tech_channel_a_concentration.csv
  Schema: reporter,concentration

  data/processed/tech/tech_channel_a_volumes.csv
  Schema: reporter,total_value

Methodology (locked):
  For each reporter i, aggregate ALL import value across
  both HS codes (8541, 8542) and all 3 years (2022-2024).
  s_{i,j}^(A) = V_{i,j}^(A) / SUM_j V_{i,j}^(A)
  C_i^(A) = SUM_j (s_{i,j}^(A))^2
  W_i^(A) = SUM_j V_{i,j}^(A)

Constraints:
  - Shares sum to 1.0 per reporter (tolerance 1e-9)
  - Hard-fail if any share < 0 or > 1
  - Hard-fail if any HHI not in [0, 1]
  - EU-27 only in output

Task: ISI-TECH-CHANNEL-A
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "tech" / "comext_semiconductor_2022_2024_flat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "tech"

SHARES_FILE = OUT_DIR / "tech_channel_a_shares.csv"
CONC_FILE = OUT_DIR / "tech_channel_a_concentration.csv"
VOL_FILE = OUT_DIR / "tech_channel_a_volumes.csv"

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

    # Accumulate total value per (reporter, partner) across all HS codes/years
    pair_values = defaultdict(float)
    rec_totals = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            rec = row["reporter"]
            sup = row["partner"]
            val = float(row["value"])

            if rec not in EU27:
                continue

            pair_values[(rec, sup)] += val
            rec_totals[rec] += val

    print(f"  Rows read: {rows_read}")
    print(f"  EU-27 reporters: {len(rec_totals)}")

    # Check zero-volume reporters
    zero_vol = [r for r, t in rec_totals.items() if t == 0.0]
    if zero_vol:
        print(f"  WARNING: zero-volume reporters: {sorted(zero_vol)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    share_rows_written = 0

    with open(SHARES_FILE, "w", newline="") as fs, \
         open(CONC_FILE, "w", newline="") as fc, \
         open(VOL_FILE, "w", newline="") as fv:

        sw = csv.writer(fs)
        sw.writerow(["reporter", "partner", "share"])

        cw = csv.writer(fc)
        cw.writerow(["reporter", "concentration"])

        vw = csv.writer(fv)
        vw.writerow(["reporter", "total_value"])

        for rec in sorted(rec_totals.keys()):
            total = rec_totals[rec]
            vw.writerow([rec, total])

            if total == 0.0:
                continue

            # Collect partners for this reporter
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
    print(f"  Concentration: {CONC_FILE} ({len(rec_totals)} reporters)")
    print(f"  Volumes:       {VOL_FILE}")
    print(f"  EU-27 present: {len(present)}/27")
    if missing:
        print(f"  EU-27 missing: {missing}")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
