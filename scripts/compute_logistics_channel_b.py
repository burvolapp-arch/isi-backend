#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Script 4: Channel B — Partner Concentration per Transport Mode

Computes per-reporter, per-mode HHI across bilateral partner
countries, then aggregates across modes using tonnage weights.

Channel B answers:
  "How concentrated are a country's freight partners,
   conditional on transport mode?"

Input:
  data/processed/logistics/logistics_freight_bilateral_flat.csv
  Schema: reporter,partner,mode,year,tonnes

Outputs:
  data/processed/logistics/logistics_channel_b_mode_shares.csv
  Schema: reporter,mode,partner,share

  data/processed/logistics/logistics_channel_b_mode_concentration.csv
  Schema: reporter,mode,concentration,mode_tonnes

  data/processed/logistics/logistics_channel_b_concentration.csv
  Schema: reporter,concentration

  data/processed/logistics/logistics_channel_b_volumes.csv
  Schema: reporter,total_tonnes

Methodology (locked, §6 of logistics_freight_axis_v01.md):
  For each reporter i and mode m ∈ {road, rail, maritime}:
    s_{i,j}^{m} = V_{i,j}^{m} / SUM_j V_{i,j}^{m}
    C_i^{(B,m)} = SUM_j (s_{i,j}^{m})^2       (partner HHI)
    V_i^{m}     = SUM_j V_{i,j}^{m}            (mode tonnage)

  Aggregate:
    C_i^{(B)} = SUM_m [C_i^{(B,m)} * V_i^{m}] / SUM_m V_i^{m}
    W_i^{(B)} = SUM_m V_i^{m}

  IWW is EXCLUDED from Channel B (no bilateral partner data
  in the original Eurostat dataset — §6.3). Even though the
  parser may emit IWW rows, Channel B ignores mode == "iww".

  Modes with zero tonnage for a reporter are excluded from
  the weighted average.

Constraints:
  - Shares sum to 1.0 per (reporter, mode) — tolerance 1e-9
  - Hard-fail if share < 0 or > 1
  - Hard-fail if mode HHI not in [0, 1]
  - Hard-fail if weighted HHI not in [0, 1]

Coverage constraints (structurally inherent):
  MT:                      {maritime}        — island, no road/rail
  CY:                      {road, maritime}  — no rail
  AT, CZ, HU, LU, SK:     {road, rail}      — landlocked, no maritime
  20 remaining countries:  {road, rail, maritime}

This script does NOT compute mode concentration (Channel A).
This script does NOT aggregate across channels.

Task: ISI-LOGISTICS-CHANNEL-B
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = (
    PROJECT_ROOT / "data" / "processed" / "logistics"
    / "logistics_freight_bilateral_flat.csv"
)
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "logistics"

MODE_SHARES_FILE = OUT_DIR / "logistics_channel_b_mode_shares.csv"
MODE_CONC_FILE = OUT_DIR / "logistics_channel_b_mode_concentration.csv"
CONC_FILE = OUT_DIR / "logistics_channel_b_concentration.csv"
VOL_FILE = OUT_DIR / "logistics_channel_b_volumes.csv"

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

# Channel B modes — IWW is EXCLUDED (§6.3)
CHANNEL_B_MODES = ["road", "rail", "maritime"]

SHARE_SUM_TOLERANCE = 1e-9


def main():
    print("=" * 68)
    print("ISI v0.1 — Axis 6: Channel B — Partner Concentration per Mode")
    print("=" * 68)
    print()

    # ── 1. Read input ────────────────────────────────────────
    if not INPUT_FILE.exists():
        print(f"FATAL: input file not found: {INPUT_FILE}", file=sys.stderr)
        print(f"Run parse_logistics_freight_raw.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Input: {INPUT_FILE}")

    # Accumulate tonnage per (reporter, mode, partner)
    triple_tonnes = defaultdict(float)  # (reporter, mode, partner) → tonnes
    rows_read = 0
    rows_skipped_iww = 0

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        # Validate header
        required = {"reporter", "partner", "mode", "year", "tonnes"}
        if not required.issubset(set(reader.fieldnames)):
            missing = required - set(reader.fieldnames)
            print(f"FATAL: input missing columns: {missing}", file=sys.stderr)
            sys.exit(1)

        for row in reader:
            rows_read += 1

            reporter = row["reporter"].strip()
            mode = row["mode"].strip()
            partner = row["partner"].strip()
            tonnes_str = row["tonnes"].strip()

            # Validate reporter
            if reporter not in EU27:
                print(f"FATAL: non-EU-27 reporter in input: "
                      f"'{reporter}' (row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            # Skip IWW — excluded from Channel B (§6.3)
            if mode == "iww":
                rows_skipped_iww += 1
                continue

            # Validate mode
            if mode not in CHANNEL_B_MODES:
                print(f"FATAL: invalid mode '{mode}' for Channel B, "
                      f"reporter {reporter} (row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            # Skip empty partner
            if partner == "":
                continue

            # Parse tonnes
            try:
                tonnes = float(tonnes_str)
            except (ValueError, TypeError):
                print(f"FATAL: non-numeric tonnes '{tonnes_str}' for "
                      f"{reporter}/{mode}/{partner} "
                      f"(row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            if tonnes < 0:
                print(f"FATAL: negative tonnes {tonnes} for "
                      f"{reporter}/{mode}/{partner} "
                      f"(row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            if tonnes == 0:
                continue  # skip zero-tonnage bilateral flows

            triple_tonnes[(reporter, mode, partner)] += tonnes

    print(f"  Rows read:        {rows_read:,}")
    print(f"  Rows skipped IWW: {rows_skipped_iww:,}")
    print(f"  Non-zero triples: {len(triple_tonnes):,}")
    print()

    if rows_read == 0:
        print("FATAL: input file contains zero data rows.", file=sys.stderr)
        sys.exit(1)

    # ── 2. Derive mode totals and reporter totals ────────────
    # mode_totals[(reporter, mode)] = total bilateral tonnes
    mode_totals = defaultdict(float)
    for (reporter, mode, partner), val in triple_tonnes.items():
        mode_totals[(reporter, mode)] += val

    # reporter_totals[reporter] = total bilateral tonnes across all Channel B modes
    reporter_totals = defaultdict(float)
    for (reporter, mode), val in mode_totals.items():
        reporter_totals[reporter] += val

    reporters_with_data = frozenset(reporter_totals.keys())
    print(f"  Reporters with Channel B data: {len(reporters_with_data)}")

    # ── 3. Verify all 27 EU reporters present ────────────────
    missing_reporters = EU27 - reporters_with_data
    extra_reporters = reporters_with_data - EU27

    if missing_reporters:
        print(f"FATAL: {len(missing_reporters)} EU-27 reporters missing "
              f"from Channel B: {sorted(missing_reporters)}", file=sys.stderr)
        sys.exit(1)

    if extra_reporters:
        print(f"FATAL: non-EU-27 reporters in Channel B: "
              f"{sorted(extra_reporters)}", file=sys.stderr)
        sys.exit(1)

    print(f"  All 27 EU-27 reporters present: PASS")
    print()

    # ── 4. Compute per-mode partner shares and HHI ───────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    mode_share_rows = 0
    mode_conc_rows = 0

    # Per-reporter weighted concentration
    rec_weighted_conc = {}  # reporter → C_i^{(B)}

    with open(MODE_SHARES_FILE, "w", encoding="utf-8", newline="") as fms, \
         open(MODE_CONC_FILE, "w", encoding="utf-8", newline="") as fmc:

        msw = csv.writer(fms)
        msw.writerow(["reporter", "mode", "partner", "share"])

        mcw = csv.writer(fmc)
        mcw.writerow(["reporter", "mode", "concentration", "mode_tonnes"])

        for reporter in sorted(EU27):
            numerator = 0.0    # SUM_m [C_i^{(B,m)} * V_i^{m}]
            denominator = 0.0  # SUM_m V_i^{m}

            for mode in CHANNEL_B_MODES:
                mt = mode_totals.get((reporter, mode), 0.0)
                if mt == 0.0:
                    continue  # mode not available for this reporter

                # Collect partners for this (reporter, mode)
                partners = sorted(
                    [(partner, val) for (r, m, partner), val
                     in triple_tonnes.items()
                     if r == reporter and m == mode],
                    key=lambda x: x[0],
                )

                share_sum = 0.0
                hhi_mode = 0.0

                for partner, val in partners:
                    share = val / mt

                    if share < 0.0:
                        print(f"FATAL: negative share {share:.10f} for "
                              f"{reporter}/{mode} <- {partner}",
                              file=sys.stderr)
                        sys.exit(1)

                    if share > 1.0 + SHARE_SUM_TOLERANCE:
                        print(f"FATAL: share > 1 ({share:.10f}) for "
                              f"{reporter}/{mode} <- {partner}",
                              file=sys.stderr)
                        sys.exit(1)

                    msw.writerow([reporter, mode, partner,
                                  f"{share:.10f}"])
                    mode_share_rows += 1
                    share_sum += share
                    hhi_mode += share * share

                # Validate shares sum to 1.0
                if abs(share_sum - 1.0) > SHARE_SUM_TOLERANCE:
                    print(f"FATAL: shares sum to {share_sum:.15f} for "
                          f"{reporter}/{mode} (expected 1.0)",
                          file=sys.stderr)
                    sys.exit(1)

                # Validate mode HHI
                if hhi_mode < 0.0 or hhi_mode > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: mode HHI out of bounds "
                          f"({hhi_mode:.10f}) for {reporter}/{mode}",
                          file=sys.stderr)
                    sys.exit(1)

                mcw.writerow([reporter, mode,
                              f"{hhi_mode:.10f}",
                              f"{mt:.1f}"])
                mode_conc_rows += 1

                numerator += hhi_mode * mt
                denominator += mt

            # Weighted aggregate HHI for this reporter
            if denominator > 0.0:
                weighted_hhi = numerator / denominator

                if weighted_hhi < 0.0 or weighted_hhi > 1.0 + SHARE_SUM_TOLERANCE:
                    print(f"FATAL: weighted HHI out of bounds "
                          f"({weighted_hhi:.10f}) for {reporter}",
                          file=sys.stderr)
                    sys.exit(1)

                rec_weighted_conc[reporter] = weighted_hhi
            else:
                print(f"FATAL: reporter {reporter} has zero bilateral "
                      f"tonnage across all Channel B modes.",
                      file=sys.stderr)
                sys.exit(1)

    # ── 5. Write aggregated concentration and volumes ────────
    with open(CONC_FILE, "w", encoding="utf-8", newline="") as fc, \
         open(VOL_FILE, "w", encoding="utf-8", newline="") as fv:

        cw = csv.writer(fc)
        cw.writerow(["reporter", "concentration"])

        vw = csv.writer(fv)
        vw.writerow(["reporter", "total_tonnes"])

        for reporter in sorted(EU27):
            vw.writerow([reporter, f"{reporter_totals[reporter]:.1f}"])

            if reporter in rec_weighted_conc:
                cw.writerow([reporter,
                             f"{rec_weighted_conc[reporter]:.10f}"])

    # ── 6. Validation & Audit ────────────────────────────────
    print("-" * 68)
    print("VALIDATION & AUDIT")
    print("-" * 68)
    print()

    # A. Output file summary
    print("A. Output files")
    print(f"   Mode shares:        {MODE_SHARES_FILE}")
    print(f"     Rows:             {mode_share_rows:,}")
    print(f"   Mode concentration: {MODE_CONC_FILE}")
    print(f"     Rows:             {mode_conc_rows:,}")
    print(f"   Concentration:      {CONC_FILE}")
    print(f"     Reporters:        {len(rec_weighted_conc)}")
    print(f"   Volumes:            {VOL_FILE}")
    print()

    # B. Coverage
    print("B. Coverage")
    print(f"   EU-27 reporters:        {len(rec_weighted_conc)}/27")
    if len(rec_weighted_conc) != 27:
        print(f"FATAL: expected 27 reporters with concentration, "
              f"got {len(rec_weighted_conc)}", file=sys.stderr)
        sys.exit(1)
    print(f"   All 27 present:         PASS")
    print()

    # C. Mode coverage per reporter
    print("C. Mode coverage per reporter")
    for reporter in sorted(EU27):
        covered = [m for m in CHANNEL_B_MODES
                   if mode_totals.get((reporter, m), 0.0) > 0.0]
        not_covered = [m for m in CHANNEL_B_MODES
                       if mode_totals.get((reporter, m), 0.0) == 0.0]
        status = f"{len(covered)}/{len(CHANNEL_B_MODES)}"
        if not_covered:
            status += f"  missing: {not_covered}"
        print(f"   {reporter}: {status}")
    print()

    # D. Numerical checks
    hhi_values = list(rec_weighted_conc.values())
    hhi_min = min(hhi_values)
    hhi_max = max(hhi_values)

    print("D. Numerical checks")
    print(f"   Min weighted HHI:   {hhi_min:.10f}")
    print(f"   Max weighted HHI:   {hhi_max:.10f}")

    for reporter, hhi in rec_weighted_conc.items():
        if hhi < 0.0 or hhi > 1.0:
            print(f"FATAL: weighted HHI out of range [0,1] for "
                  f"{reporter}: {hhi}", file=sys.stderr)
            sys.exit(1)
    print(f"   All HHI in [0, 1]:  PASS")
    print()

    # E. Sanity flags
    print("E. Sanity flags")

    reporters_hhi_high = [(r, h) for r, h in rec_weighted_conc.items()
                          if h >= 0.50]
    if reporters_hhi_high:
        print(f"   HHI >= 0.50 (high concentration):")
        for r, h in sorted(reporters_hhi_high, key=lambda x: -x[1]):
            print(f"     {r}: {h:.6f}")
    else:
        print(f"   HHI >= 0.50: none")

    single_mode = [(r, m) for r in sorted(EU27)
                   for m in CHANNEL_B_MODES
                   if mode_totals.get((r, m), 0.0) > 0.0
                   if sum(1 for mm in CHANNEL_B_MODES
                          if mode_totals.get((r, mm), 0.0) > 0.0) == 1]
    if single_mode:
        print(f"   Single-mode reporters (Channel B):")
        for r, m in single_mode:
            print(f"     {r}: {m} only")
    else:
        print(f"   Single-mode reporters: none")
    print()

    # F. Per-reporter detail table
    print("-" * 68)
    print(f"  {'Reporter':<8s} {'Wt HHI':>10s} "
          f"{'Total t':>14s} {'Modes':>6s} "
          f"{'road':>10s} {'rail':>10s} {'marit':>10s}")
    print("  " + "-" * 60)

    for reporter in sorted(EU27):
        wt_hhi = rec_weighted_conc.get(reporter, 0.0)
        total_t = reporter_totals.get(reporter, 0.0)
        n_modes = sum(1 for m in CHANNEL_B_MODES
                      if mode_totals.get((reporter, m), 0.0) > 0.0)

        # Per-mode HHI (recompute for display — cheap)
        per_mode_hhi = {}
        for mode in CHANNEL_B_MODES:
            mt = mode_totals.get((reporter, mode), 0.0)
            if mt == 0.0:
                per_mode_hhi[mode] = "    —"
                continue
            hhi_m = 0.0
            for (r, m, p), v in triple_tonnes.items():
                if r == reporter and m == mode:
                    share = v / mt
                    hhi_m += share * share
            per_mode_hhi[mode] = f"{hhi_m:.6f}"

        print(f"  {reporter:<8s} {wt_hhi:>10.6f} "
              f"{total_t:>14,.1f} {n_modes:>6d} "
              f"{per_mode_hhi['road']:>10s} "
              f"{per_mode_hhi['rail']:>10s} "
              f"{per_mode_hhi['maritime']:>10s}")

    print()

    # ── 7. Final verdict ─────────────────────────────────────
    print("=" * 68)
    print("Channel B: PASS")
    print("=" * 68)
    print()
    print(f"  Mode shares:        {MODE_SHARES_FILE} ({mode_share_rows:,} rows)")
    print(f"  Mode concentration: {MODE_CONC_FILE} ({mode_conc_rows:,} rows)")
    print(f"  Concentration:      {CONC_FILE} ({len(rec_weighted_conc)} reporters)")
    print(f"  Volumes:            {VOL_FILE}")
    print(f"  HHI range:          [{hhi_min:.6f}, {hhi_max:.6f}]")
    print()


if __name__ == "__main__":
    main()
