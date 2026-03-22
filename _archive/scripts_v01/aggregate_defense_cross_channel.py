#!/usr/bin/env python3
"""ISI v0.1 — Defense Axis: Cross-Channel Aggregation (2019-2024)

Inputs:
  data/processed/defense/sipri_channel_a_concentration.csv
  data/processed/defense/sipri_channel_a_volumes.csv
  data/processed/defense/sipri_channel_b_concentration.csv
  data/processed/defense/sipri_channel_b_volumes.csv

Outputs:
  data/processed/defense/defense_dependency_2024_eu27.csv
  Schema: geo,defense_dependency

  data/processed/defense/defense_dependency_2024_eu27_audit.csv
  Schema: geo,channel_a_concentration,channel_a_volume,channel_b_concentration,channel_b_volume,
          defense_dependency,score_basis

Methodology (locked):
  DefenseDependency_i = (C_i^{A} * W_i^{A} + C_i^{B} * W_i^{B}) / (W_i^{A} + W_i^{B})

  If one channel has zero volume → reduce to the other channel.

  ZERO-DEPENDENCY SEMANTIC RULE (LOCKED):
  If an EU-27 country has NO bilateral SIPRI supplier entries
  (both channels have zero volume), its external defense dependency
  is defined as ZERO (score = 0), NOT missing, NOT estimated.
  This represents zero external supplier concentration and maximal
  sovereignty on defense supply. Academically defensible: a country
  with no recorded arms imports has no import concentration.
  Applies to countries whose arms procurement occurs via licensed
  production, joint EU procurement, or domestic manufacturing.
  Machine-readable flag: score_basis = "NO_BILATERAL_SUPPLIERS"

Constraints:
  - Defense dependency in [0, 1]
  - EU-27 only (Eurostat geo codes, EL for Greece)
  - Hard-fail if score out of bounds
  - Must produce exactly 27 rows (one per EU-27 country)

Task: ISI-DEFENSE-AGGREGATE
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR = PROJECT_ROOT / "data" / "processed" / "defense"

CA_CONC_FILE = PROC_DIR / "sipri_channel_a_concentration.csv"
CA_VOL_FILE = PROC_DIR / "sipri_channel_a_volumes.csv"
CB_CONC_FILE = PROC_DIR / "sipri_channel_b_concentration.csv"
CB_VOL_FILE = PROC_DIR / "sipri_channel_b_volumes.csv"

OUT_FILE = PROC_DIR / "defense_dependency_2024_eu27.csv"
AUDIT_FILE = PROC_DIR / "defense_dependency_2024_eu27_audit.csv"

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

BOUND_TOLERANCE = 1e-9


def load_csv_dict(filepath, key_col, val_col):
    """Load a CSV into a dict: key_col -> float(val_col)."""
    result = {}
    with open(filepath, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row[key_col]] = float(row[val_col])
    return result


def main():
    for fp in [CA_CONC_FILE, CA_VOL_FILE, CB_CONC_FILE, CB_VOL_FILE]:
        if not fp.exists():
            print(f"FATAL: input not found: {fp}", file=sys.stderr)
            sys.exit(1)

    ca_conc = load_csv_dict(CA_CONC_FILE, "recipient_country", "concentration")
    ca_vol = load_csv_dict(CA_VOL_FILE, "recipient_country", "total_tiv")
    cb_conc = load_csv_dict(CB_CONC_FILE, "recipient_country", "concentration")
    cb_vol = load_csv_dict(CB_VOL_FILE, "recipient_country", "total_tiv")

    print(f"Channel A: {len(ca_conc)} concentrations, {len(ca_vol)} volumes")
    print(f"Channel B: {len(cb_conc)} concentrations, {len(cb_vol)} volumes")

    PROC_DIR.mkdir(parents=True, exist_ok=True)

    scored = 0
    single_channel_a = 0
    single_channel_b = 0
    both_channels = 0
    zero_bilateral = 0

    with open(OUT_FILE, "w", newline="") as fo, \
         open(AUDIT_FILE, "w", newline="") as fa:

        ow = csv.writer(fo)
        ow.writerow(["geo", "defense_dependency"])

        aw = csv.writer(fa)
        aw.writerow([
            "geo",
            "channel_a_concentration",
            "channel_a_volume",
            "channel_b_concentration",
            "channel_b_volume",
            "defense_dependency",
            "score_basis",
            "dependency_semantic",
        ])

        for geo in EU27:
            c_a = ca_conc.get(geo)
            w_a = ca_vol.get(geo, 0.0)
            c_b = cb_conc.get(geo)
            w_b = cb_vol.get(geo, 0.0)

            score = None
            basis = ""
            semantic = ""

            has_a = c_a is not None and w_a > 0.0
            has_b = c_b is not None and w_b > 0.0

            if has_a and has_b:
                score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
                basis = "BOTH_CHANNELS"
                both_channels += 1
            elif has_a and not has_b:
                score = c_a
                basis = "CHANNEL_A_ONLY"
                single_channel_a += 1
            elif has_b and not has_a:
                score = c_b
                basis = "CHANNEL_B_ONLY"
                single_channel_b += 1
            else:
                # ZERO-DEPENDENCY SEMANTIC (LOCKED RULE):
                # Country has NO bilateral SIPRI supplier entries.
                # This is NOT missing data — it is a definitive zero:
                #   - zero external supplier concentration
                #   - maximal sovereignty on defense supply
                # Applies to countries with licensed production,
                # joint EU procurement, or domestic manufacturing.
                score = 0.0
                basis = "NO_BILATERAL_SUPPLIERS"
                semantic = "no_bilateral_suppliers"
                zero_bilateral += 1
                print(f"  INFO: {geo} has no bilateral SIPRI suppliers — "
                      f"defense dependency := 0 (zero external concentration)")

            if score < -BOUND_TOLERANCE or score > 1.0 + BOUND_TOLERANCE:
                print(f"FATAL: score out of bounds ({score}) for {geo}", file=sys.stderr)
                sys.exit(1)

            ow.writerow([geo, score])
            scored += 1

            aw.writerow([
                geo,
                c_a if c_a is not None else 0.0,
                w_a,
                c_b if c_b is not None else 0.0,
                w_b,
                score,
                basis,
                semantic,
            ])

    print()
    print("Defense dependency results:")
    print(f"  Output:    {OUT_FILE}")
    print(f"  Audit:     {AUDIT_FILE}")
    print(f"  Scored:    {scored}/27")
    print(f"    Both channels:          {both_channels}")
    print(f"    Channel A only:         {single_channel_a}")
    print(f"    Channel B only:         {single_channel_b}")
    print(f"    Zero bilateral (score=0): {zero_bilateral}")

    if zero_bilateral > 0:
        zero_geos = []
        with open(AUDIT_FILE, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["score_basis"] == "NO_BILATERAL_SUPPLIERS":
                    zero_geos.append(row["geo"])
        print(f"  Zero-bilateral countries: {zero_geos}")
        print("  Semantic: no bilateral SIPRI suppliers → defense dependency := 0")

    # Hard-fail if we don't have exactly 27 countries
    if scored != 27:
        print(f"FATAL: expected 27 scored countries, got {scored}", file=sys.stderr)
        sys.exit(1)

    print()
    print("  All checks passed (27/27 EU-27 countries scored).")


if __name__ == "__main__":
    main()
