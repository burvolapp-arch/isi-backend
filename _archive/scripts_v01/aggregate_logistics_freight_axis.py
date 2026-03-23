#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Script 5: Cross-Channel Aggregation

Combines Channel A (mode concentration) and Channel B (partner
concentration per mode) into the final Axis 6 score.

Inputs:
  data/processed/logistics/logistics_channel_a_mode_concentration.csv
  Schema: reporter, channel_a_mode_hhi, total_tonnes, n_modes_used

  data/processed/logistics/logistics_channel_b_concentration.csv
  Schema: reporter, concentration

  data/processed/logistics/logistics_channel_b_volumes.csv
  Schema: reporter, total_tonnes

Output:
  data/processed/logistics/logistics_freight_axis_score.csv
  Schema: reporter, axis6_logistics_score, channel_a_mode_hhi,
          channel_b_partner_hhi, weight_a_tonnes, weight_b_tonnes,
          modes_used, aggregation_case

Exactly 27 rows (EU-27).

Formula (locked, §7 of logistics_freight_axis_v01.md):

  Axis6_i = ( C_i(A) · W_i(A) + C_i(B) · W_i(B) )
            / ( W_i(A) + W_i(B) )

Where:
  C_i(A) = channel_a_mode_hhi  (mode concentration HHI)
  W_i(A) = total_tonnes from Channel A (all modes incl. IWW)
  C_i(B) = concentration from Channel B (partner HHI)
  W_i(B) = total_tonnes from Channel B volumes ({road,rail,maritime} ONLY)

STRUCTURAL ASYMMETRY (documented and intentional):
  W_i(A) includes IWW tonnage (from tran_hv_frmod / parser).
  W_i(B) excludes IWW (no bilateral partner data — §6.3).
  Therefore W_i(A) ≠ W_i(B) by construction for countries
  with non-zero IWW freight. This is NOT a bug. The cross-
  channel formula is a volume-weighted average where each
  channel contributes proportionally to its own freight base.
  Countries with large IWW shares (NL, DE, BE) will have
  W_A > W_B, giving Channel A slightly more weight.

Edge cases:
  W_A > 0, W_B > 0 → full formula        (BOTH)
  W_A > 0, W_B == 0 → Axis6 = C_A        (A_ONLY)
  W_A == 0, W_B > 0 → Axis6 = C_B        (B_ONLY)
  W_A == 0, W_B == 0 → HARD FAIL

Task: ISI-LOGISTICS-AGGREGATE
"""

import csv
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROC_DIR = PROJECT_ROOT / "data" / "processed" / "logistics"

CA_FILE = PROC_DIR / "logistics_channel_a_mode_concentration.csv"
CB_CONC_FILE = PROC_DIR / "logistics_channel_b_concentration.csv"
CB_VOL_FILE = PROC_DIR / "logistics_channel_b_volumes.csv"

OUT_FILE = PROC_DIR / "logistics_freight_axis_score.csv"

OUT_FIELDNAMES = [
    "reporter",
    "axis6_logistics_score",
    "channel_a_mode_hhi",
    "channel_b_partner_hhi",
    "weight_a_tonnes",
    "weight_b_tonnes",
    "modes_used",
    "aggregation_case",
]

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

BOUND_TOLERANCE = 1e-9


def load_channel_a(filepath):
    """Load Channel A CSV into dict keyed by reporter.

    Returns dict: reporter → {hhi, weight, modes_used}
    """
    result = {}
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reporter = row["reporter"].strip()
            result[reporter] = {
                "hhi": float(row["channel_a_mode_hhi"]),
                "weight": float(row["total_tonnes"]),
                "modes_used": int(row["n_modes_used"]),
            }
    return result


def load_channel_b_concentration(filepath):
    """Load Channel B concentration CSV into dict: reporter → hhi."""
    result = {}
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reporter = row["reporter"].strip()
            result[reporter] = float(row["concentration"])
    return result


def load_channel_b_volumes(filepath):
    """Load Channel B volumes CSV into dict: reporter → total_tonnes."""
    result = {}
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reporter = row["reporter"].strip()
            result[reporter] = float(row["total_tonnes"])
    return result


def main():
    print("=" * 68)
    print("ISI v0.1 — Axis 6: Cross-Channel Aggregation")
    print("=" * 68)
    print()

    # ── 1. Load inputs ───────────────────────────────────────
    for fp in [CA_FILE, CB_CONC_FILE, CB_VOL_FILE]:
        if not fp.exists():
            print(f"FATAL: input not found: {fp}", file=sys.stderr)
            sys.exit(1)

    ca = load_channel_a(CA_FILE)
    cb_conc = load_channel_b_concentration(CB_CONC_FILE)
    cb_vol = load_channel_b_volumes(CB_VOL_FILE)

    print(f"Channel A: {len(ca)} reporters loaded")
    print(f"Channel B: {len(cb_conc)} concentrations, "
          f"{len(cb_vol)} volumes loaded")
    print()

    # ── 2. Verify EU-27 coverage ─────────────────────────────
    ca_reporters = frozenset(ca.keys())
    cb_conc_reporters = frozenset(cb_conc.keys())
    cb_vol_reporters = frozenset(cb_vol.keys())

    # Check all three files have exactly EU-27
    for label, reporters in [("Channel A", ca_reporters),
                             ("Channel B conc", cb_conc_reporters),
                             ("Channel B vol", cb_vol_reporters)]:
        missing = EU27 - reporters
        extra = reporters - EU27
        if missing:
            print(f"FATAL: {label} missing EU-27 reporters: "
                  f"{sorted(missing)}", file=sys.stderr)
            sys.exit(1)
        if extra:
            print(f"FATAL: {label} has non-EU-27 reporters: "
                  f"{sorted(extra)}", file=sys.stderr)
            sys.exit(1)
        if len(reporters) != 27:
            print(f"FATAL: {label} has {len(reporters)} reporters, "
                  f"expected 27", file=sys.stderr)
            sys.exit(1)

    print("  All inputs have exactly 27 EU-27 reporters: PASS")
    print()

    # ── 3. Compute Axis 6 scores ─────────────────────────────
    results = []

    for reporter in sorted(EU27):
        c_a = ca[reporter]["hhi"]
        w_a = ca[reporter]["weight"]      # Total tonnes incl. IWW
        modes_used = ca[reporter]["modes_used"]

        c_b = cb_conc[reporter]
        w_b = cb_vol[reporter]            # Bilateral tonnes excl. IWW

        # Validate individual channel values
        for label, val in [("C_A", c_a), ("C_B", c_b)]:
            if math.isnan(val) or math.isinf(val):
                print(f"FATAL: {label} is NaN/inf for {reporter}",
                      file=sys.stderr)
                sys.exit(1)
            if val < 0.0 or val > 1.0 + BOUND_TOLERANCE:
                print(f"FATAL: {label} out of [0, 1] for {reporter}: "
                      f"{val}", file=sys.stderr)
                sys.exit(1)

        for label, val in [("W_A", w_a), ("W_B", w_b)]:
            if math.isnan(val) or math.isinf(val):
                print(f"FATAL: {label} is NaN/inf for {reporter}",
                      file=sys.stderr)
                sys.exit(1)
            if val < 0.0:
                print(f"FATAL: {label} is negative for {reporter}: "
                      f"{val}", file=sys.stderr)
                sys.exit(1)

        # Aggregation formula with edge-case handling
        # W_A includes IWW; W_B excludes IWW — asymmetry is by design
        has_a = w_a > 0.0
        has_b = w_b > 0.0

        if has_a and has_b:
            score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
            case = "BOTH"
        elif has_a and not has_b:
            score = c_a
            case = "A_ONLY"
        elif has_b and not has_a:
            score = c_b
            case = "B_ONLY"
        else:
            print(f"FATAL: both W_A and W_B are zero for {reporter}",
                  file=sys.stderr)
            sys.exit(1)

        # Validate final score
        if math.isnan(score) or math.isinf(score):
            print(f"FATAL: Axis 6 score is NaN/inf for {reporter}",
                  file=sys.stderr)
            sys.exit(1)

        if score < 0.0 or score > 1.0 + BOUND_TOLERANCE:
            print(f"FATAL: Axis 6 score out of [0, 1] for {reporter}: "
                  f"{score}", file=sys.stderr)
            sys.exit(1)

        results.append({
            "reporter": reporter,
            "axis6_logistics_score": score,
            "channel_a_mode_hhi": c_a,
            "channel_b_partner_hhi": c_b,
            "weight_a_tonnes": w_a,
            "weight_b_tonnes": w_b,
            "modes_used": modes_used,
            "aggregation_case": case,
        })

    # ── 4. Write output ──────────────────────────────────────
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDNAMES)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "reporter": r["reporter"],
                "axis6_logistics_score":
                    f"{r['axis6_logistics_score']:.10f}",
                "channel_a_mode_hhi":
                    f"{r['channel_a_mode_hhi']:.10f}",
                "channel_b_partner_hhi":
                    f"{r['channel_b_partner_hhi']:.10f}",
                "weight_a_tonnes":
                    f"{r['weight_a_tonnes']:.1f}",
                "weight_b_tonnes":
                    f"{r['weight_b_tonnes']:.1f}",
                "modes_used": r["modes_used"],
                "aggregation_case": r["aggregation_case"],
            })

    # ── 5. Validation ────────────────────────────────────────
    print("-" * 68)
    print("VALIDATION")
    print("-" * 68)
    print()

    # A. Row count
    if len(results) != 27:
        print(f"FATAL: expected 27 output rows, got {len(results)}",
              file=sys.stderr)
        sys.exit(1)
    print(f"A. Row count: {len(results)} (expected 27) — PASS")
    print()

    # B. Aggregation case distribution
    case_counts = {"BOTH": 0, "A_ONLY": 0, "B_ONLY": 0}
    for r in results:
        case_counts[r["aggregation_case"]] += 1
    print("B. Aggregation cases")
    print(f"   BOTH:   {case_counts['BOTH']}")
    print(f"   A_ONLY: {case_counts['A_ONLY']}")
    print(f"   B_ONLY: {case_counts['B_ONLY']}")
    print()

    # C. Score bounds
    scores = [r["axis6_logistics_score"] for r in results]
    score_min = min(scores)
    score_max = max(scores)
    score_mean = sum(scores) / len(scores)

    print("C. Summary statistics")
    print(f"   Min:  {score_min:.10f}")
    print(f"   Max:  {score_max:.10f}")
    print(f"   Mean: {score_mean:.10f}")

    for r in results:
        s = r["axis6_logistics_score"]
        if s < 0.0 or s > 1.0:
            print(f"FATAL: score out of [0, 1] for "
                  f"{r['reporter']}: {s}", file=sys.stderr)
            sys.exit(1)
    print(f"   All scores in [0, 1]: PASS")
    print()

    # D. Flags
    print("D. Flags")

    # IWW-heavy: W_B / W_A < 0.5
    iww_heavy = [(r["reporter"],
                  r["weight_b_tonnes"] / r["weight_a_tonnes"])
                 for r in results
                 if r["weight_a_tonnes"] > 0.0
                 and (r["weight_b_tonnes"] / r["weight_a_tonnes"]) < 0.5]
    if iww_heavy:
        print("   IWW-heavy (W_B / W_A < 0.5):")
        for reporter, ratio in sorted(iww_heavy, key=lambda x: x[1]):
            print(f"     {reporter}: ratio = {ratio:.4f}")
    else:
        print("   IWW-heavy (W_B / W_A < 0.5): none")

    # High concentration: Axis6 >= 0.4
    high_conc = [(r["reporter"], r["axis6_logistics_score"])
                 for r in results
                 if r["axis6_logistics_score"] >= 0.4]
    if high_conc:
        print("   High concentration (Axis6 >= 0.4):")
        for reporter, score in sorted(high_conc, key=lambda x: -x[1]):
            print(f"     {reporter}: {score:.6f}")
    else:
        print("   High concentration (Axis6 >= 0.4): none")
    print()

    # ── 6. Ranked table (descending by Axis 6 score) ─────────
    print("-" * 68)
    print(f"  {'#':>3s} {'Reporter':<8s} {'Axis6':>10s} "
          f"{'Ch.A':>10s} {'Ch.B':>10s} "
          f"{'W_A':>14s} {'W_B':>14s} "
          f"{'M':>2s} {'Case':<8s}")
    print("  " + "-" * 70)

    ranked = sorted(results,
                    key=lambda r: -r["axis6_logistics_score"])

    for rank, r in enumerate(ranked, 1):
        print(f"  {rank:>3d} {r['reporter']:<8s} "
              f"{r['axis6_logistics_score']:>10.6f} "
              f"{r['channel_a_mode_hhi']:>10.6f} "
              f"{r['channel_b_partner_hhi']:>10.6f} "
              f"{r['weight_a_tonnes']:>14,.1f} "
              f"{r['weight_b_tonnes']:>14,.1f} "
              f"{r['modes_used']:>2d} "
              f"{r['aggregation_case']:<8s}")

    print()

    # ── 7. Final verdict ─────────────────────────────────────
    print("=" * 68)
    print("Axis 6 — Logistics / Freight Dependency: PASS")
    print("=" * 68)
    print()
    print(f"  Output:     {OUT_FILE}")
    print(f"  Reporters:  {len(results)}")
    print(f"  Score range: [{score_min:.6f}, {score_max:.6f}]")
    print(f"  Mean:        {score_mean:.6f}")
    print()


if __name__ == "__main__":
    main()
