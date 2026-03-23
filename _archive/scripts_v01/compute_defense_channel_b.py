#!/usr/bin/env python3
"""ISI v0.1 — Defense Channel B: Capability-Weighted Supplier Concentration (2019-2024)

Input:
  data/processed/defense/sipri_bilateral_2019_2024_flat.csv
  Schema: recipient_country,supplier_country,capability_block,year,tiv

Outputs:
  data/processed/defense/sipri_channel_b_block_shares.csv
  Schema: recipient_country,capability_block,supplier_country,share

  data/processed/defense/sipri_channel_b_block_concentration.csv
  Schema: recipient_country,capability_block,concentration,block_tiv

  data/processed/defense/sipri_channel_b_concentration.csv
  Schema: recipient_country,concentration

  data/processed/defense/sipri_channel_b_volumes.csv
  Schema: recipient_country,total_tiv

Methodology (locked):
  For each recipient i and block k:
    s_{i,j}^{B,k} = V_{i,j}^{B,k} / SUM_j V_{i,j}^{B,k}
    C_i^{B,k}     = SUM_j (s_{i,j}^{B,k})^2
    V_i^{k}       = SUM_j V_{i,j}^{B,k}

  Aggregate:
    C_i^{B} = SUM_k [C_i^{B,k} * V_i^{k}] / SUM_k V_i^{k}
    W_i^{B} = SUM_k V_i^{k}

  Blocks with zero TIV are excluded from the weighted average.

Constraints:
  - Shares sum to 1.0 per (recipient, block) — tolerance 1e-9
  - Hard-fail if share < 0 or > 1
  - Hard-fail if block HHI not in [0, 1]
  - Hard-fail if weighted HHI not in [0, 1]

Task: ISI-DEFENSE-CHANNEL-B
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "defense" / "sipri_bilateral_2019_2024_flat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "defense"

BLOCK_SHARES_FILE = OUT_DIR / "sipri_channel_b_block_shares.csv"
BLOCK_CONC_FILE = OUT_DIR / "sipri_channel_b_block_concentration.csv"
CONC_FILE = OUT_DIR / "sipri_channel_b_concentration.csv"
VOL_FILE = OUT_DIR / "sipri_channel_b_volumes.csv"

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

CAPABILITY_BLOCKS = [
    "air_power",
    "land_combat",
    "air_missile_defense",
    "naval_combat",
    "strike_missile",
    "isr_support",
]

SHARE_SUM_TOLERANCE = 1e-9


def main():
    if not INPUT_FILE.exists():
        print(f"FATAL: input not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Input:   {INPUT_FILE}")

    # Accumulate TIV per (recipient, block, supplier)
    # triple_tiv[(rec, block, sup)] = total TIV
    triple_tiv = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            rec = row["recipient_country"]
            sup = row["supplier_country"]
            blk = row["capability_block"]
            tiv = float(row["tiv"])

            if rec not in EU27:
                continue

            triple_tiv[(rec, blk, sup)] += tiv

    print(f"  Rows read: {rows_read}")

    # Derive block totals: V_i^{k}
    block_totals = defaultdict(float)  # (rec, blk) -> total
    for (rec, blk, sup), val in triple_tiv.items():
        block_totals[(rec, blk)] += val

    # Derive recipient totals: W_i^{B}
    rec_totals = defaultdict(float)
    for (rec, blk), val in block_totals.items():
        rec_totals[rec] += val

    print(f"  EU-27 recipients with data: {len(rec_totals)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    block_share_rows = 0
    block_conc_rows = 0

    # Per-recipient weighted concentration
    rec_weighted_conc = {}  # rec -> C_i^{B}

    with open(BLOCK_SHARES_FILE, "w", newline="") as fbs, \
         open(BLOCK_CONC_FILE, "w", newline="") as fbc:

        bsw = csv.writer(fbs)
        bsw.writerow(["recipient_country", "capability_block", "supplier_country", "share"])

        bcw = csv.writer(fbc)
        bcw.writerow(["recipient_country", "capability_block", "concentration", "block_tiv"])

        for rec in sorted(rec_totals.keys()):
            numerator = 0.0   # SUM_k [C_i^{B,k} * V_i^{k}]
            denominator = 0.0  # SUM_k V_i^{k}

            for blk in CAPABILITY_BLOCKS:
                bt = block_totals.get((rec, blk), 0.0)
                if bt == 0.0:
                    continue

                # Collect suppliers for this (rec, blk)
                sup_list = sorted(
                    [(sup, val) for (r, b, sup), val in triple_tiv.items()
                     if r == rec and b == blk],
                    key=lambda x: x[0],
                )

                share_sum = 0.0
                hhi_block = 0.0

                for sup, val in sup_list:
                    share = val / bt

                    if share < 0.0:
                        print(f"FATAL: negative share {share} for {rec}/{blk} <- {sup}", file=sys.stderr)
                        sys.exit(1)
                    if share > 1.0 + SHARE_SUM_TOLERANCE:
                        print(f"FATAL: share > 1 ({share}) for {rec}/{blk} <- {sup}", file=sys.stderr)
                        sys.exit(1)

                    bsw.writerow([rec, blk, sup, share])
                    block_share_rows += 1
                    share_sum += share
                    hhi_block += share ** 2

                if abs(share_sum - 1.0) > SHARE_SUM_TOLERANCE:
                    print(f"FATAL: shares sum to {share_sum} for {rec}/{blk}", file=sys.stderr)
                    sys.exit(1)

                if hhi_block < 0.0 or hhi_block > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: block HHI out of bounds ({hhi_block}) for {rec}/{blk}", file=sys.stderr)
                    sys.exit(1)

                bcw.writerow([rec, blk, hhi_block, bt])
                block_conc_rows += 1

                numerator += hhi_block * bt
                denominator += bt

            if denominator > 0.0:
                weighted_hhi = numerator / denominator

                if weighted_hhi < 0.0 or weighted_hhi > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: weighted HHI out of bounds ({weighted_hhi}) for {rec}", file=sys.stderr)
                    sys.exit(1)

                rec_weighted_conc[rec] = weighted_hhi

    # Write aggregated concentration and volumes
    with open(CONC_FILE, "w", newline="") as fc, \
         open(VOL_FILE, "w", newline="") as fv:

        cw = csv.writer(fc)
        cw.writerow(["recipient_country", "concentration"])

        vw = csv.writer(fv)
        vw.writerow(["recipient_country", "total_tiv"])

        for rec in sorted(rec_totals.keys()):
            vw.writerow([rec, rec_totals[rec]])

            if rec in rec_weighted_conc:
                cw.writerow([rec, rec_weighted_conc[rec]])

    # Coverage
    present = sorted(EU27 & set(rec_totals.keys()))
    missing = sorted(EU27 - set(rec_totals.keys()))

    # Block coverage per country
    print()
    print(f"Channel B results:")
    print(f"  Block shares:        {BLOCK_SHARES_FILE} ({block_share_rows} rows)")
    print(f"  Block concentration: {BLOCK_CONC_FILE} ({block_conc_rows} rows)")
    print(f"  Concentration:       {CONC_FILE} ({len(rec_weighted_conc)} recipients)")
    print(f"  Volumes:             {VOL_FILE}")
    print(f"  EU-27 present: {len(present)}/27")
    if missing:
        print(f"  EU-27 missing: {missing}")

    # Report block coverage per recipient
    print()
    print("  Block coverage per recipient:")
    for rec in sorted(rec_totals.keys()):
        covered = [blk for blk in CAPABILITY_BLOCKS if block_totals.get((rec, blk), 0.0) > 0.0]
        not_covered = [blk for blk in CAPABILITY_BLOCKS if block_totals.get((rec, blk), 0.0) == 0.0]
        status = f"{len(covered)}/6"
        if not_covered:
            status += f"  missing: {not_covered}"
        print(f"    {rec}: {status}")

    print()
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
