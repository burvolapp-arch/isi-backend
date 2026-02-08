#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Script 3a: Channel A — Transport Mode Concentration

Computes per-reporter HHI across transport modes (road, rail,
maritime, iww). Measures how concentrated a country's international
freight is across modes.

Input:
  data/processed/logistics/logistics_freight_bilateral_flat.csv
  Schema: reporter,partner,mode,year,tonnes

Output:
  data/processed/logistics/logistics_channel_a_mode_concentration.csv
  Schema: reporter,channel_a_mode_hhi,total_tonnes,n_modes_used

One row per EU-27 reporter. Exactly 27 rows.

Channel A answers: how dependent is country i on a single
transport mode for its international freight?

HHI = SUM_m (s_m)^2 where s_m = T_m / T_total
  s_m is the share of mode m in total freight tonnage.
  HHI ∈ [0, 1]. HHI = 1.0 when all freight is on one mode.

This script does NOT compute partner concentration (Channel B).
This script does NOT aggregate across channels.

Task: ISI-LOGISTICS-CHANNEL-A
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
OUT_FILE = OUT_DIR / "logistics_channel_a_mode_concentration.csv"

OUT_FIELDNAMES = [
    "reporter",
    "channel_a_mode_hhi",
    "total_tonnes",
    "n_modes_used",
]

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

VALID_MODES = frozenset(["road", "rail", "maritime", "iww"])


def main():
    print("=" * 68)
    print("ISI v0.1 — Axis 6: Channel A — Transport Mode Concentration")
    print("=" * 68)
    print()

    # ── 1. Read input ────────────────────────────────────────
    if not INPUT_FILE.exists():
        print(f"FATAL: input file not found: {INPUT_FILE}", file=sys.stderr)
        print(f"Run parse_logistics_freight_raw.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Input: {INPUT_FILE}")

    # Accumulate tonnage per (reporter, mode)
    # reporter → mode → total tonnes
    reporter_mode_tonnes = defaultdict(lambda: defaultdict(float))
    rows_read = 0
    modes_observed = set()

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
            tonnes_str = row["tonnes"].strip()

            # Validate reporter
            if reporter not in EU27:
                print(f"FATAL: non-EU-27 reporter in input: "
                      f"'{reporter}' (row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            # Validate mode
            if mode not in VALID_MODES:
                print(f"FATAL: invalid mode '{mode}' for reporter "
                      f"{reporter} (row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            # Parse tonnes
            try:
                tonnes = float(tonnes_str)
            except (ValueError, TypeError):
                print(f"FATAL: non-numeric tonnes '{tonnes_str}' for "
                      f"{reporter}/{mode} (row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            if tonnes < 0:
                print(f"FATAL: negative tonnes {tonnes} for "
                      f"{reporter}/{mode} (row {rows_read + 1})", file=sys.stderr)
                sys.exit(1)

            reporter_mode_tonnes[reporter][mode] += tonnes
            modes_observed.add(mode)

    print(f"  Rows read: {rows_read:,}")
    print(f"  Reporters in input: {len(reporter_mode_tonnes)}")
    print(f"  Modes observed: {sorted(modes_observed)}")
    print()

    if rows_read == 0:
        print("FATAL: input file contains zero data rows.", file=sys.stderr)
        sys.exit(1)

    # ── 2. Verify all 27 EU reporters present ────────────────
    reporters_present = frozenset(reporter_mode_tonnes.keys())
    missing_reporters = EU27 - reporters_present
    extra_reporters = reporters_present - EU27

    if missing_reporters:
        print(f"FATAL: {len(missing_reporters)} EU-27 reporters missing "
              f"from input: {sorted(missing_reporters)}", file=sys.stderr)
        sys.exit(1)

    if extra_reporters:
        print(f"FATAL: non-EU-27 reporters in input: "
              f"{sorted(extra_reporters)}", file=sys.stderr)
        sys.exit(1)

    # ── 3. Compute Channel A HHI per reporter ────────────────
    results = []

    for reporter in sorted(EU27):
        mode_tonnes = reporter_mode_tonnes[reporter]

        # Total tonnage across all modes
        total_tonnes = sum(mode_tonnes.values())

        # Count modes with positive volume
        modes_used = [m for m, t in mode_tonnes.items() if t > 0]
        n_modes_used = len(modes_used)

        if total_tonnes == 0 or n_modes_used == 0:
            print(f"FATAL: reporter {reporter} has zero total tonnage "
                  f"across all modes.", file=sys.stderr)
            sys.exit(1)

        # Mode shares and HHI
        hhi = 0.0
        for mode in modes_used:
            share = mode_tonnes[mode] / total_tonnes
            hhi += share * share

        results.append({
            "reporter": reporter,
            "channel_a_mode_hhi": hhi,
            "total_tonnes": total_tonnes,
            "n_modes_used": n_modes_used,
        })

    # ── 4. Write output ──────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDNAMES)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "reporter": r["reporter"],
                "channel_a_mode_hhi": f"{r['channel_a_mode_hhi']:.10f}",
                "total_tonnes": f"{r['total_tonnes']:.1f}",
                "n_modes_used": r["n_modes_used"],
            })

    print(f"Output: {OUT_FILE}")
    print(f"  Rows: {len(results)}")
    print()

    # ── 5. Validation & Audit ────────────────────────────────
    print("-" * 68)
    print("VALIDATION & AUDIT")
    print("-" * 68)
    print()

    # A. Coverage
    print("A. Coverage")
    print(f"   Unique reporters:    {len(results)}")
    if len(results) != 27:
        print(f"FATAL: expected 27 reporters, got {len(results)}", file=sys.stderr)
        sys.exit(1)
    print(f"   Expected:            27")
    print(f"   Modes observed:      {sorted(modes_observed)}")
    print()

    # B. Numerical checks
    hhi_values = [r["channel_a_mode_hhi"] for r in results]
    hhi_min = min(hhi_values)
    hhi_max = max(hhi_values)

    print("B. Numerical checks")
    print(f"   Min HHI:             {hhi_min:.10f}")
    print(f"   Max HHI:             {hhi_max:.10f}")

    for r in results:
        hhi = r["channel_a_mode_hhi"]
        if hhi < 0.0 or hhi > 1.0:
            print(f"FATAL: HHI out of range [0, 1] for {r['reporter']}: "
                  f"{hhi}", file=sys.stderr)
            sys.exit(1)

    print(f"   All HHI in [0, 1]:   PASS")
    print()

    # C. Sanity flags
    print("C. Sanity flags")

    reporters_hhi_1 = [r["reporter"] for r in results
                       if r["channel_a_mode_hhi"] == 1.0]
    if reporters_hhi_1:
        print(f"   HHI == 1.0 (single mode): {reporters_hhi_1}")
    else:
        print(f"   HHI == 1.0 (single mode): none")

    reporters_all_4 = [r["reporter"] for r in results
                       if r["n_modes_used"] == 4]
    if reporters_all_4:
        print(f"   All 4 modes used:         {reporters_all_4}")
    else:
        print(f"   All 4 modes used:         none")

    print()

    # Per-reporter detail table
    print("-" * 68)
    print(f"  {'Reporter':<10s} {'HHI':>12s} {'Total tonnes':>16s} {'Modes':>6s}")
    print("  " + "-" * 46)
    for r in results:
        print(f"  {r['reporter']:<10s} "
              f"{r['channel_a_mode_hhi']:>12.6f} "
              f"{r['total_tonnes']:>16,.1f} "
              f"{r['n_modes_used']:>6d}")
    print()

    # ── 6. Final verdict ─────────────────────────────────────
    print("=" * 68)
    print("Channel A: PASS")
    print("=" * 68)
    print()
    print(f"  Output:     {OUT_FILE}")
    print(f"  Reporters:  {len(results)}")
    print(f"  HHI range:  [{hhi_min:.6f}, {hhi_max:.6f}]")
    print()


if __name__ == "__main__":
    main()
