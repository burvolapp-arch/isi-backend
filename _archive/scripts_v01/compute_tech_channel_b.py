#!/usr/bin/env python3
"""ISI v0.1 — Technology Channel B: Category-Weighted Supplier Concentration (2022-2024)

Input:
  data/processed/tech/comext_semiconductor_2022_2024_flat.csv
  Schema: reporter,partner,product_nc,hs_category,year,value

Outputs:
  data/processed/tech/tech_channel_b_category_shares.csv
  Schema: reporter,hs_category,partner,share

  data/processed/tech/tech_channel_b_category_concentration.csv
  Schema: reporter,hs_category,concentration,category_value

  data/processed/tech/tech_channel_b_concentration.csv
  Schema: reporter,concentration

  data/processed/tech/tech_channel_b_volumes.csv
  Schema: reporter,total_value

Methodology (locked):
  For each reporter i and category k in {legacy_discrete,
  legacy_components, integrated_circuits}:
    s_{i,j}^{B,k} = V_{i,j}^{B,k} / SUM_j V_{i,j}^{B,k}
    C_i^{B,k}     = SUM_j (s_{i,j}^{B,k})^2
    V_i^{k}       = SUM_j V_{i,j}^{B,k}

  Aggregate:
    C_i^{B} = SUM_k [C_i^{B,k} * V_i^{k}] / SUM_k V_i^{k}
    W_i^{B} = SUM_k V_i^{k}

  Categories with zero value for a reporter are excluded
  from the weighted average.

Categories (CN8 → capability, authoritative v0.1):
  85411000, 85412100, 85412900, 85413000 → "legacy_discrete"
  85416000, 85419000                     → "legacy_components"
  8542                                   → "integrated_circuits"

Constraints:
  - Shares sum to 1.0 per (reporter, category) — tolerance 1e-9
  - Hard-fail if share < 0 or > 1
  - Hard-fail if category HHI not in [0, 1]
  - Hard-fail if weighted HHI not in [0, 1]

Task: ISI-TECH-CHANNEL-B
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = PROJECT_ROOT / "data" / "processed" / "tech" / "comext_semiconductor_2022_2024_flat.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "tech"

CAT_SHARES_FILE = OUT_DIR / "tech_channel_b_category_shares.csv"
CAT_CONC_FILE = OUT_DIR / "tech_channel_b_category_concentration.csv"
CONC_FILE = OUT_DIR / "tech_channel_b_concentration.csv"
VOL_FILE = OUT_DIR / "tech_channel_b_volumes.csv"

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

HS_CATEGORIES = ["legacy_discrete", "legacy_components", "integrated_circuits"]

SHARE_SUM_TOLERANCE = 1e-9


def main():
    if not INPUT_FILE.exists():
        print(f"FATAL: input not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Input:   {INPUT_FILE}")

    # Accumulate value per (reporter, category, partner)
    triple_val = defaultdict(float)
    rows_read = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_read += 1
            rec = row["reporter"]
            sup = row["partner"]
            cat = row["hs_category"]
            val = float(row["value"])

            if rec not in EU27:
                continue

            triple_val[(rec, cat, sup)] += val

    print(f"  Rows read: {rows_read}")

    # Derive category totals: V_i^{k}
    cat_totals = defaultdict(float)  # (rec, cat) -> total
    for (rec, cat, sup), val in triple_val.items():
        cat_totals[(rec, cat)] += val

    # Derive reporter totals: W_i^{B}
    rec_totals = defaultdict(float)
    for (rec, cat), val in cat_totals.items():
        rec_totals[rec] += val

    print(f"  EU-27 reporters with data: {len(rec_totals)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    cat_share_rows = 0
    cat_conc_rows = 0

    # Per-reporter weighted concentration
    rec_weighted_conc = {}  # rec -> C_i^{B}

    with open(CAT_SHARES_FILE, "w", newline="") as fcs, \
         open(CAT_CONC_FILE, "w", newline="") as fcc:

        csw = csv.writer(fcs)
        csw.writerow(["reporter", "hs_category", "partner", "share"])

        ccw = csv.writer(fcc)
        ccw.writerow(["reporter", "hs_category", "concentration", "category_value"])

        for rec in sorted(rec_totals.keys()):
            numerator = 0.0   # SUM_k [C_i^{B,k} * V_i^{k}]
            denominator = 0.0  # SUM_k V_i^{k}

            for cat in HS_CATEGORIES:
                ct = cat_totals.get((rec, cat), 0.0)
                if ct == 0.0:
                    continue

                # Collect partners for this (rec, cat)
                sup_list = sorted(
                    [(sup, val) for (r, c, sup), val in triple_val.items()
                     if r == rec and c == cat],
                    key=lambda x: x[0],
                )

                share_sum = 0.0
                hhi_cat = 0.0

                for sup, val in sup_list:
                    share = val / ct

                    if share < 0.0:
                        print(f"FATAL: negative share {share} for {rec}/{cat} <- {sup}", file=sys.stderr)
                        sys.exit(1)
                    if share > 1.0 + SHARE_SUM_TOLERANCE:
                        print(f"FATAL: share > 1 ({share}) for {rec}/{cat} <- {sup}", file=sys.stderr)
                        sys.exit(1)

                    csw.writerow([rec, cat, sup, share])
                    cat_share_rows += 1
                    share_sum += share
                    hhi_cat += share ** 2

                if abs(share_sum - 1.0) > SHARE_SUM_TOLERANCE:
                    print(f"FATAL: shares sum to {share_sum} for {rec}/{cat}", file=sys.stderr)
                    sys.exit(1)

                if hhi_cat < 0.0 or hhi_cat > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: category HHI out of bounds ({hhi_cat}) for {rec}/{cat}", file=sys.stderr)
                    sys.exit(1)

                ccw.writerow([rec, cat, hhi_cat, ct])
                cat_conc_rows += 1

                numerator += hhi_cat * ct
                denominator += ct

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
        cw.writerow(["reporter", "concentration"])

        vw = csv.writer(fv)
        vw.writerow(["reporter", "total_value"])

        for rec in sorted(rec_totals.keys()):
            vw.writerow([rec, rec_totals[rec]])

            if rec in rec_weighted_conc:
                cw.writerow([rec, rec_weighted_conc[rec]])

    # Coverage
    present = sorted(EU27 & set(rec_totals.keys()))
    missing = sorted(EU27 - set(rec_totals.keys()))

    # Category coverage per reporter
    print()
    print(f"Channel B results:")
    print(f"  Category shares:        {CAT_SHARES_FILE} ({cat_share_rows} rows)")
    print(f"  Category concentration: {CAT_CONC_FILE} ({cat_conc_rows} rows)")
    print(f"  Concentration:          {CONC_FILE} ({len(rec_weighted_conc)} reporters)")
    print(f"  Volumes:                {VOL_FILE}")
    print(f"  EU-27 present: {len(present)}/27")
    if missing:
        print(f"  EU-27 missing: {missing}")

    # Report category coverage per reporter
    print()
    print("  Category coverage per reporter:")
    for rec in sorted(rec_totals.keys()):
        covered = [cat for cat in HS_CATEGORIES if cat_totals.get((rec, cat), 0.0) > 0.0]
        not_covered = [cat for cat in HS_CATEGORIES if cat_totals.get((rec, cat), 0.0) == 0.0]
        status = f"{len(covered)}/{len(HS_CATEGORIES)}"
        if not_covered:
            status += f"  missing: {not_covered}"
        print(f"    {rec}: {status}")

    print()
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
