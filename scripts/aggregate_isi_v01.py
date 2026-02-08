#!/usr/bin/env python3
"""
aggregate_isi_v01.py — ISI Core Aggregation Layer v0.1

Fuses all six frozen ISI axis scores into a single canonical
ISI composite score per EU-27 country.

Aggregation rule: unweighted arithmetic mean of six axis scores.

    ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6

This script does not recompute any axis. It reads final scores
from disk, validates them, aggregates, and writes output.

Inputs:
    data/processed/axis_1/axis_1_final_scores.csv
    data/processed/axis_2/axis_2_final_scores.csv
    data/processed/axis_3/axis_3_final_scores.csv
    data/processed/axis_4/axis_4_final_scores.csv
    data/processed/axis_5/axis_5_final_scores.csv
    data/processed/axis_6/axis_6_final_scores.csv

Outputs:
    data/processed/isi/isi_eu27_v01.csv          — canonical snapshot
    data/audit/isi_v01_aggregation_audit.csv      — per-row audit trail
    stdout                                         — summary report

Hard-fails on any validation violation. No partial output.
"""

import csv
import math
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Canonical EU-27 set. Alphabetical. Immutable across all ISI axes.
EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

NUM_AXES = 6
VERSION = "v0.1"
WINDOW = "2022\u20132024"  # en-dash, matching freeze documents

# Project root is one level above scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Input file paths, keyed by axis number (1-indexed).
AXIS_FILES = {
    i: PROJECT_ROOT / "data" / "processed" / f"axis_{i}" / f"axis_{i}_final_scores.csv"
    for i in range(1, NUM_AXES + 1)
}

# Output paths
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "isi"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"
SNAPSHOT_PATH = OUTPUT_DIR / "isi_eu27_v01.csv"
AUDIT_PATH = AUDIT_DIR / "isi_v01_aggregation_audit.csv"

# Expected column names in each input file
EXPECTED_COLUMNS = {"country", "score"}

# Human-readable axis labels for output columns
AXIS_LABELS = {
    1: "axis_1_financial",
    2: "axis_2_trade",
    3: "axis_3_technology",
    4: "axis_4_defense",
    5: "axis_5_critical_inputs",
    6: "axis_6_logistics",
}


# ---------------------------------------------------------------------------
# Fatal error helper
# ---------------------------------------------------------------------------

def fatal(msg: str) -> None:
    """Print error and terminate. No recovery path exists."""
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Load and validate a single axis file
# ---------------------------------------------------------------------------

def load_axis(axis_num: int, filepath: Path) -> dict[str, float]:
    """
    Read one axis CSV. Returns {country: score}.

    Hard-fails if:
    - file does not exist
    - file has zero data rows
    - column names are not exactly {country, score}
    - any country code is not in EU-27
    - any country appears more than once
    - any EU-27 country is missing
    - any score is missing, non-numeric, NaN, negative, or > 1
    """

    if not filepath.is_file():
        fatal(f"Axis {axis_num}: input file not found: {filepath}")

    scores: dict[str, float] = {}
    seen_countries: set[str] = set()

    with open(filepath, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        # -- Column validation --
        if reader.fieldnames is None:
            fatal(f"Axis {axis_num}: file appears empty or has no header: {filepath}")

        actual_columns = set(reader.fieldnames)
        if actual_columns != EXPECTED_COLUMNS:
            extra = actual_columns - EXPECTED_COLUMNS
            missing = EXPECTED_COLUMNS - actual_columns
            fatal(
                f"Axis {axis_num}: unexpected columns in {filepath}. "
                f"Expected exactly {sorted(EXPECTED_COLUMNS)}. "
                f"Extra: {sorted(extra)}. Missing: {sorted(missing)}."
            )

        row_count = 0
        for row in reader:
            row_count += 1
            country = row["country"].strip()
            raw_score = row["score"].strip()

            # Country must be EU-27
            if country not in EU27:
                fatal(
                    f"Axis {axis_num}: country '{country}' is not in the "
                    f"EU-27 canonical set (row {row_count})."
                )

            # No duplicates
            if country in seen_countries:
                fatal(
                    f"Axis {axis_num}: duplicate country '{country}' "
                    f"(row {row_count})."
                )
            seen_countries.add(country)

            # Score must be a valid float
            if raw_score == "":
                fatal(
                    f"Axis {axis_num}: missing score for '{country}' "
                    f"(row {row_count})."
                )

            try:
                score = float(raw_score)
            except ValueError:
                fatal(
                    f"Axis {axis_num}: non-numeric score '{raw_score}' "
                    f"for '{country}' (row {row_count})."
                )

            # NaN / inf guard
            if math.isnan(score) or math.isinf(score):
                fatal(
                    f"Axis {axis_num}: score is NaN or Inf for "
                    f"'{country}' (row {row_count})."
                )

            # Bounds check
            if score < 0.0:
                fatal(
                    f"Axis {axis_num}: negative score {score} for "
                    f"'{country}' (row {row_count})."
                )
            if score > 1.0:
                fatal(
                    f"Axis {axis_num}: score {score} exceeds 1.0 for "
                    f"'{country}' (row {row_count})."
                )

            scores[country] = score

    # Zero rows check
    if row_count == 0:
        fatal(f"Axis {axis_num}: file has zero data rows: {filepath}")

    # All EU-27 countries must be present
    missing_countries = EU27 - seen_countries
    if missing_countries:
        fatal(
            f"Axis {axis_num}: missing EU-27 countries: "
            f"{sorted(missing_countries)}"
        )

    return scores


# ---------------------------------------------------------------------------
# Cross-axis consistency check
# ---------------------------------------------------------------------------

def validate_cross_axis(all_axes: dict[int, dict[str, float]]) -> None:
    """
    Verify that all six axes cover the identical set of countries.
    Hard-fails if any axis has a different country set.
    """

    # Use axis 1 as reference
    reference_set = set(all_axes[1].keys())

    for axis_num in range(2, NUM_AXES + 1):
        current_set = set(all_axes[axis_num].keys())
        if current_set != reference_set:
            only_in_ref = reference_set - current_set
            only_in_cur = current_set - reference_set
            fatal(
                f"Cross-axis mismatch: axis 1 vs axis {axis_num}. "
                f"Only in axis 1: {sorted(only_in_ref)}. "
                f"Only in axis {axis_num}: {sorted(only_in_cur)}."
            )

    # Every country must appear in exactly 6 axes
    for country in sorted(reference_set):
        count = sum(1 for ax in all_axes.values() if country in ax)
        if count != NUM_AXES:
            fatal(
                f"Country '{country}' appears in {count} axes, "
                f"expected {NUM_AXES}."
            )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def compute_composite(all_axes: dict[int, dict[str, float]]) -> list[dict]:
    """
    Compute ISI composite score per country.

    Returns list of dicts sorted by country code, each containing
    all axis scores, composite score, and metadata.
    """

    rows = []

    for country in sorted(EU27):
        axis_scores = {
            axis_num: all_axes[axis_num][country]
            for axis_num in range(1, NUM_AXES + 1)
        }

        composite = sum(axis_scores.values()) / NUM_AXES

        # Final bound check on composite — should be arithmetically
        # impossible to violate given per-axis [0,1] enforcement,
        # but defense in depth.
        if composite < -1e-12 or composite > 1.0 + 1e-12:
            fatal(
                f"Composite score {composite} for '{country}' is "
                f"outside [0, 1]. This should be impossible."
            )

        # Clamp to exact [0, 1] to handle floating-point dust
        composite = max(0.0, min(1.0, composite))

        rows.append({
            "country": country,
            "axis_1_financial": axis_scores[1],
            "axis_2_trade": axis_scores[2],
            "axis_3_technology": axis_scores[3],
            "axis_4_defense": axis_scores[4],
            "axis_5_critical_inputs": axis_scores[5],
            "axis_6_logistics": axis_scores[6],
            "isi_composite": composite,
            "version": VERSION,
            "window": WINDOW,
        })

    return rows


# ---------------------------------------------------------------------------
# Write canonical snapshot
# ---------------------------------------------------------------------------

def write_snapshot(rows: list[dict]) -> None:
    """Write data/processed/isi/isi_eu27_v01.csv."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "country",
        "axis_1_financial",
        "axis_2_trade",
        "axis_3_technology",
        "axis_4_defense",
        "axis_5_critical_inputs",
        "axis_6_logistics",
        "isi_composite",
        "version",
        "window",
    ]

    with open(SNAPSHOT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Snapshot written: {SNAPSHOT_PATH}")
    print(f"  Rows: {len(rows)}")


# ---------------------------------------------------------------------------
# Write audit file
# ---------------------------------------------------------------------------

def write_audit(rows: list[dict]) -> None:
    """Write data/audit/isi_v01_aggregation_audit.csv."""

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "country",
        "axis_1_financial",
        "axis_2_trade",
        "axis_3_technology",
        "axis_4_defense",
        "axis_5_critical_inputs",
        "axis_6_logistics",
        "isi_composite",
        "validation_status",
    ]

    with open(AUDIT_PATH, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            audit_row = {
                "country": row["country"],
                "axis_1_financial": row["axis_1_financial"],
                "axis_2_trade": row["axis_2_trade"],
                "axis_3_technology": row["axis_3_technology"],
                "axis_4_defense": row["axis_4_defense"],
                "axis_5_critical_inputs": row["axis_5_critical_inputs"],
                "axis_6_logistics": row["axis_6_logistics"],
                "isi_composite": row["isi_composite"],
                "validation_status": "PASS",
            }
            writer.writerow(audit_row)

    print(f"Audit written:    {AUDIT_PATH}")
    print(f"  Rows: {len(rows)}")


# ---------------------------------------------------------------------------
# Summary report (stdout)
# ---------------------------------------------------------------------------

def print_summary(rows: list[dict]) -> None:
    """Print structured summary to stdout."""

    composites = [r["isi_composite"] for r in rows]
    min_score = min(composites)
    max_score = max(composites)
    mean_score = sum(composites) / len(composites)

    # Identify min/max countries for reference
    min_country = [r["country"] for r in rows if r["isi_composite"] == min_score]
    max_country = [r["country"] for r in rows if r["isi_composite"] == max_score]

    print()
    print("=" * 60)
    print("ISI v0.1 — AGGREGATION SUMMARY")
    print("=" * 60)
    print()
    print(f"  Countries aggregated:    {len(rows)}")
    print(f"  Axes used:               {NUM_AXES}")
    print(f"  Aggregation rule:        unweighted arithmetic mean")
    print(f"  Version:                 {VERSION}")
    print(f"  Reference window:        {WINDOW}")
    print()
    print(f"  Composite min:           {min_score:.6f}  ({', '.join(min_country)})")
    print(f"  Composite max:           {max_score:.6f}  ({', '.join(max_country)})")
    print(f"  Composite mean:          {mean_score:.6f}")
    print()

    # Per-axis summary
    print("  Per-axis summary:")
    print(f"  {'Axis':<28s} {'Min':>10s} {'Max':>10s} {'Mean':>10s}")
    print(f"  {'-'*28} {'-'*10} {'-'*10} {'-'*10}")

    for axis_num in range(1, NUM_AXES + 1):
        label = AXIS_LABELS[axis_num]
        vals = [r[label] for r in rows]
        a_min = min(vals)
        a_max = max(vals)
        a_mean = sum(vals) / len(vals)
        print(f"  {label:<28s} {a_min:>10.6f} {a_max:>10.6f} {a_mean:>10.6f}")

    print()

    # Per-country table
    print("  Per-country ISI composite (sorted by country):")
    print(f"  {'Country':<10s} {'Composite':>12s}")
    print(f"  {'-'*10} {'-'*12}")
    for row in rows:
        print(f"  {row['country']:<10s} {row['isi_composite']:>12.6f}")

    print()
    print("  All 6 axes confirmed present and validated.")
    print("  All 27 EU-27 countries confirmed present in all axes.")
    print("  All scores in [0, 1]. No NaN, no missing values.")
    print("  All per-row validations: PASS.")
    print()
    print("  AGGREGATION PASS \u2014 ISI v0.1 COMPLETE")
    print()
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"aggregate_isi_v01.py")
    print(f"Loading {NUM_AXES} axis files...")
    print()

    # -- Phase 1: Load and validate each axis independently --
    all_axes: dict[int, dict[str, float]] = {}

    for axis_num in range(1, NUM_AXES + 1):
        filepath = AXIS_FILES[axis_num]
        print(f"  Axis {axis_num}: {filepath.name} ... ", end="")
        scores = load_axis(axis_num, filepath)
        all_axes[axis_num] = scores
        print(f"{len(scores)} countries loaded.")

    print()

    # -- Phase 2: Cross-axis consistency --
    print("Cross-axis consistency check ... ", end="")
    validate_cross_axis(all_axes)
    print("PASS")
    print()

    # -- Phase 3: Aggregate --
    print("Computing ISI composite scores ... ", end="")
    rows = compute_composite(all_axes)
    assert len(rows) == 27  # defense in depth
    print(f"{len(rows)} countries scored.")
    print()

    # -- Phase 4: Write outputs --
    write_snapshot(rows)
    write_audit(rows)

    # -- Phase 5: Summary --
    print_summary(rows)


if __name__ == "__main__":
    main()
