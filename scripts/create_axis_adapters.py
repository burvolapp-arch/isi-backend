#!/usr/bin/env python3
"""ISI v0.1 — Adapter: Normalise axis scores for aggregation

Creates the standardised adapter files expected by aggregate_isi_v01.py:
    data/processed/axis_{n}/axis_{n}_final_scores.csv
    Schema: country,score

Each axis data has different column names, country-code conventions,
and potential data gaps. This script normalises them all to the
canonical format.

Data gap handling:
  - All six axes now produce 27/27 EU-27 rows upstream.
  - Axis 4 (Defense): countries with no bilateral SIPRI suppliers
    (e.g. SK) arrive with score=0 and score_basis=NO_BILATERAL_SUPPLIERS.
    No imputation is needed or performed.
  - Imputation is retained as a safety net for any future axis with
    ≥20/27 coverage, but should never trigger for v0.1 frozen data.

Task: ISI-ADAPTER
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Source files for each axis
AXIS_SOURCES = {
    1: {
        "data_dir": "finance",
        "filename": "finance_dependency_2024_eu27.csv",
        "country_col": "geo",
        "score_col": "finance_dependency",
    },
    2: {
        "data_dir": "energy",
        "filename": "energy_dependency_2024_eu27.csv",
        "country_col": "geo",
        "score_col": "energy_dependency",
    },
    3: {
        "data_dir": "tech",
        "filename": "tech_dependency_2024_eu27.csv",
        "country_col": "geo",
        "score_col": "tech_dependency",
    },
    4: {
        "data_dir": "defense",
        "filename": "defense_dependency_2024_eu27.csv",
        "country_col": "geo",
        "score_col": "defense_dependency",
    },
    5: {
        "data_dir": "critical_inputs",
        "filename": "critical_inputs_dependency_2024_eu27.csv",
        "country_col": "geo",
        "score_col": "critical_inputs_dependency",
    },
    6: {
        "data_dir": "logistics",
        "filename": "logistics_freight_axis_score.csv",
        "country_col": "reporter",
        "score_col": "axis6_logistics_score",
    },
}

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])
EU27_SET = frozenset(EU27)


def main():
    print("=" * 68)
    print("ISI v0.1 — Adapter: Normalise axis scores for aggregation")
    print("=" * 68)
    print()

    imputations = []

    for axis_num in range(1, 7):
        src = AXIS_SOURCES[axis_num]
        src_file = (PROJECT_ROOT / "data" / "processed"
                    / src["data_dir"] / src["filename"])

        if not src_file.exists():
            print(f"FATAL: Axis {axis_num} source file not found: {src_file}",
                  file=sys.stderr)
            sys.exit(1)

        # Read source
        scores = {}
        with open(src_file, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                country = row[src["country_col"]].strip()
                score_str = row[src["score_col"]].strip()
                if score_str == "":
                    continue
                scores[country] = float(score_str)

        # Check coverage
        present = set(scores.keys()) & EU27_SET
        missing = EU27_SET - present

        if missing:
            print(f"  Axis {axis_num}: {len(present)}/27 countries, "
                  f"missing: {sorted(missing)}")

            # Imputation: use mean of available scores
            if len(present) >= 20:  # Only impute if most data exists
                mean_score = sum(scores[c] for c in present) / len(present)
                for c in sorted(missing):
                    scores[c] = mean_score
                    imputations.append((axis_num, c, mean_score, len(present)))
                    print(f"    IMPUTED: {c} = {mean_score:.6f} "
                          f"(EU-27 mean of {len(present)} available)")
            else:
                print(f"FATAL: Axis {axis_num} has too few countries "
                      f"({len(present)}) for imputation.", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"  Axis {axis_num}: 27/27 countries ✓")

        # Write adapter file
        out_dir = PROJECT_ROOT / "data" / "processed" / f"axis_{axis_num}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"axis_{axis_num}_final_scores.csv"

        with open(out_file, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["country", "score"])
            for country in EU27:
                s = scores.get(country)
                if s is None:
                    print(f"FATAL: {country} still missing after imputation "
                          f"for axis {axis_num}", file=sys.stderr)
                    sys.exit(1)
                w.writerow([country, f"{s:.10f}"])

        print(f"    → {out_file}")

    # Summary
    print()
    print("=" * 68)
    print("ADAPTER SUMMARY")
    print("=" * 68)

    for i in range(1, 7):
        out_file = (PROJECT_ROOT / "data" / "processed"
                    / f"axis_{i}" / f"axis_{i}_final_scores.csv")
        with open(out_file) as f:
            lines = f.readlines()
        print(f"  Axis {i}: {out_file.name} ({len(lines) - 1} rows)")

    if imputations:
        print()
        print("  IMPUTATIONS:")
        for axis_num, country, value, n_avail in imputations:
            print(f"    Axis {axis_num}, {country}: {value:.6f} "
                  f"(mean of {n_avail} available scores)")

    print()
    print("All 6 adapter files created. Ready for aggregate_isi_v01.py.")
    print()


if __name__ == "__main__":
    main()
