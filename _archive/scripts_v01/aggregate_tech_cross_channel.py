#!/usr/bin/env python3
"""ISI v0.1 — Technology Axis: Cross-Channel Aggregation (2022-2024)

Inputs:
  data/processed/tech/tech_channel_a_concentration.csv
  data/processed/tech/tech_channel_a_volumes.csv
  data/processed/tech/tech_channel_b_concentration.csv
  data/processed/tech/tech_channel_b_volumes.csv

Outputs:
  data/processed/tech/tech_dependency_2024_eu27.csv
  Schema: geo,tech_dependency

  data/processed/tech/tech_dependency_2024_eu27_audit.csv
  Schema: geo,channel_a_concentration,channel_a_volume,channel_b_concentration,channel_b_volume,
          tech_dependency,score_basis

Methodology (locked):
  T_i = (C_i^{A} * W_i^{A} + C_i^{B} * W_i^{B}) / (W_i^{A} + W_i^{B})

  If one channel has zero volume → reduce to the other channel.
  If both channels have zero volume → omit with audit reason.

  Note: By construction W_i^{A} = W_i^{B} for all reporters
  (both channels consume the same total import value), so
  the formula reduces to T_i = (C_i^{A} + C_i^{B}) / 2.
  The volume-weighted formula is retained for generality
  and consistency with other axes.

Constraints:
  - Tech dependency in [0, 1]
  - EU-27 only (Eurostat geo codes, EL for Greece)
  - Hard-fail if score out of bounds

Task: ISI-TECH-AGGREGATE
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROC_DIR = PROJECT_ROOT / "data" / "processed" / "tech"

CA_CONC_FILE = PROC_DIR / "tech_channel_a_concentration.csv"
CA_VOL_FILE = PROC_DIR / "tech_channel_a_volumes.csv"
CB_CONC_FILE = PROC_DIR / "tech_channel_b_concentration.csv"
CB_VOL_FILE = PROC_DIR / "tech_channel_b_volumes.csv"

OUT_FILE = PROC_DIR / "tech_dependency_2024_eu27.csv"
AUDIT_FILE = PROC_DIR / "tech_dependency_2024_eu27_audit.csv"

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
    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row[key_col]] = float(row[val_col])
    return result


def main():
    for fp in [CA_CONC_FILE, CA_VOL_FILE, CB_CONC_FILE, CB_VOL_FILE]:
        if not fp.exists():
            print(f"FATAL: input not found: {fp}", file=sys.stderr)
            sys.exit(1)

    ca_conc = load_csv_dict(CA_CONC_FILE, "reporter", "concentration")
    ca_vol = load_csv_dict(CA_VOL_FILE, "reporter", "total_value")
    cb_conc = load_csv_dict(CB_CONC_FILE, "reporter", "concentration")
    cb_vol = load_csv_dict(CB_VOL_FILE, "reporter", "total_value")

    print(f"Channel A: {len(ca_conc)} concentrations, {len(ca_vol)} volumes")
    print(f"Channel B: {len(cb_conc)} concentrations, {len(cb_vol)} volumes")

    PROC_DIR.mkdir(parents=True, exist_ok=True)

    scored = 0
    omitted = 0
    single_channel_a = 0
    single_channel_b = 0
    both_channels = 0

    with open(OUT_FILE, "w", newline="") as fo, \
         open(AUDIT_FILE, "w", newline="") as fa:

        ow = csv.writer(fo)
        ow.writerow(["geo", "tech_dependency"])

        aw = csv.writer(fa)
        aw.writerow([
            "geo",
            "channel_a_concentration",
            "channel_a_volume",
            "channel_b_concentration",
            "channel_b_volume",
            "tech_dependency",
            "score_basis",
        ])

        for geo in EU27:
            c_a = ca_conc.get(geo)
            w_a = ca_vol.get(geo, 0.0)
            c_b = cb_conc.get(geo)
            w_b = cb_vol.get(geo, 0.0)

            score = None
            basis = ""

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
                basis = "OMITTED_NO_DATA"
                omitted += 1

            if score is not None:
                if score < -BOUND_TOLERANCE or score > 1.0 + BOUND_TOLERANCE:
                    print(f"FATAL: score out of bounds ({score}) for {geo}", file=sys.stderr)
                    sys.exit(1)

                ow.writerow([geo, score])
                scored += 1

            aw.writerow([
                geo,
                c_a if c_a is not None else "",
                w_a,
                c_b if c_b is not None else "",
                w_b,
                score if score is not None else "",
                basis,
            ])

    print()
    print(f"Technology dependency results:")
    print(f"  Output:    {OUT_FILE}")
    print(f"  Audit:     {AUDIT_FILE}")
    print(f"  Scored:    {scored}/27")
    print(f"    Both channels:   {both_channels}")
    print(f"    Channel A only:  {single_channel_a}")
    print(f"    Channel B only:  {single_channel_b}")
    print(f"  Omitted:   {omitted}")

    if omitted > 0:
        omitted_geos = []
        with open(AUDIT_FILE, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["score_basis"] == "OMITTED_NO_DATA":
                    omitted_geos.append(row["geo"])
        print(f"  Omitted countries: {omitted_geos}")

    print()
    print("  All checks passed.")


if __name__ == "__main__":
    main()
