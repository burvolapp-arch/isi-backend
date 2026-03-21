#!/usr/bin/env python3
"""ISI v1.1 — Axis 1: Financial Sovereignty (Global Scope)

Computes financial dependency for expansion countries using:
  Channel A: BIS LBS (cross-border banking claims concentration)
  Channel B: IMF CPIS (portfolio debt concentration)

This script reads the SAME intermediate BIS/CPIS concentration and volume
files produced by the existing v1.0 parsers, which are country-agnostic.
It then produces structured AxisResult outputs for the Phase 1 scope.

The existing parsers (compute_finance_bis_concentration.py,
compute_finance_cpis_concentration.py) process ALL countries in their
input data — they do NOT filter to EU-27 at the concentration level.
The EU-27 filter is only in the cross-channel aggregation script
(aggregate_finance_cross_channel.py). Therefore, BIS/CPIS concentration
data for expansion countries is already available in the existing output
files if those countries appear in the raw data.

Inputs:
  data/processed/finance/bis_lbs_inward_2024_concentration.csv
  data/processed/finance/bis_lbs_inward_2024_volumes.csv
  data/processed/finance/cpis_debt_inward_2024_concentration.csv
  data/processed/finance/cpis_debt_inward_2024_volumes.csv

Output:
  data/processed/global_v11/axis_1_financial.json

Constraint spec references:
  - Section 8.2 (cross-channel aggregation)
  - Section 9.1 (per-axis output schema)
  - LIM-005 (CPIS non-participation: CN)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# Allow running as script from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.axis_result import AxisResult, validate_axis_result
from backend.constants import ROUND_PRECISION
from backend.scope import (
    CPIS_NON_PARTICIPANTS,
    CPIS_TO_CANONICAL_EXPANSION,
    BIS_TO_CANONICAL_EXPANSION,
    PHASE1_EXPANSION_CODES,
    get_scope_sorted,
    is_producer_inverted,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROC_DIR = PROJECT_ROOT / "data" / "processed" / "finance"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

# BIS uses ISO-2 codes. For expansion countries, no remapping needed
# except the standard BIS convention (which has no conflicts for Phase 1).
# The existing BIS parser uses "counterparty_country" as the key.

# CPIS uses ISO-3 codes. The existing CPIS parser uses "reference_country".

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
SOURCE = "BIS_LBS_2024+CPIS_2024"
BOUND_TOL = 1e-9


def load_bis_data(
    conc_path: Path, vol_path: Path
) -> tuple[dict[str, float], dict[str, float]]:
    """Load BIS concentration and volume data for expansion countries.

    BIS data uses counterparty_country (ISO-2).
    Returns (concentrations, volumes) dicts keyed by canonical ISO-2.
    """
    conc: dict[str, float] = {}
    vol: dict[str, float] = {}

    with open(conc_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            code = row["counterparty_country"].strip()
            canonical = BIS_TO_CANONICAL_EXPANSION.get(code)
            if canonical is not None:
                conc[canonical] = float(row["concentration"])

    with open(vol_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            code = row["counterparty_country"].strip()
            canonical = BIS_TO_CANONICAL_EXPANSION.get(code)
            if canonical is not None:
                vol[canonical] = float(row["total_value_usd_mn"])

    return conc, vol


def load_cpis_data(
    conc_path: Path, vol_path: Path
) -> tuple[dict[str, float], dict[str, float]]:
    """Load CPIS concentration and volume data for expansion countries.

    CPIS data uses reference_country (ISO-3).
    Returns (concentrations, volumes) dicts keyed by canonical ISO-2.
    """
    conc: dict[str, float] = {}
    vol: dict[str, float] = {}

    with open(conc_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            code = row["reference_country"].strip()
            canonical = CPIS_TO_CANONICAL_EXPANSION.get(code)
            if canonical is not None:
                conc[canonical] = float(row["concentration"])

    with open(vol_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            code = row["reference_country"].strip()
            canonical = CPIS_TO_CANONICAL_EXPANSION.get(code)
            if canonical is not None:
                vol[canonical] = float(row["total_value_usd_mn"])

    return conc, vol


def compute_axis_1() -> list[AxisResult]:
    """Compute Axis 1 for all Phase 1 countries."""
    bis_conc_path = PROC_DIR / "bis_lbs_inward_2024_concentration.csv"
    bis_vol_path = PROC_DIR / "bis_lbs_inward_2024_volumes.csv"
    cpis_conc_path = PROC_DIR / "cpis_debt_inward_2024_concentration.csv"
    cpis_vol_path = PROC_DIR / "cpis_debt_inward_2024_volumes.csv"

    for fp in [bis_conc_path, bis_vol_path]:
        if not fp.is_file():
            print(f"FATAL: BIS input not found: {fp}", file=sys.stderr)
            sys.exit(1)

    # CPIS files may not exist — that's a known limitation, not a fatal error
    cpis_available = cpis_conc_path.is_file() and cpis_vol_path.is_file()

    bis_conc, bis_vol = load_bis_data(bis_conc_path, bis_vol_path)

    if cpis_available:
        cpis_conc, cpis_vol = load_cpis_data(cpis_conc_path, cpis_vol_path)
    else:
        cpis_conc, cpis_vol = {}, {}

    results: list[AxisResult] = []
    countries = get_scope_sorted(SCOPE_ID)

    for country in countries:
        warnings: list[str] = []

        c_a = bis_conc.get(country)
        w_a = bis_vol.get(country, 0.0)
        c_b = cpis_conc.get(country)
        w_b = cpis_vol.get(country, 0.0)

        has_a = c_a is not None and w_a > 0.0
        has_b = c_b is not None and w_b > 0.0

        # CPIS non-participant check (constraint spec LIM-005)
        if country in CPIS_NON_PARTICIPANTS:
            has_b = False
            warnings.append("F-CPIS-ABSENT")

        if has_a and has_b:
            score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
            basis = "BOTH"
            validity = "VALID"
        elif has_a and not has_b:
            score = c_a
            basis = "A_ONLY"
            validity = "A_ONLY"
        elif not has_a and has_b:
            score = c_b
            basis = "B_ONLY"
            validity = "A_ONLY"  # B_ONLY is structurally unusual
        else:
            score = None
            basis = "INVALID"
            validity = "INVALID"
            warnings.append("No BIS or CPIS data available")

        if score is not None:
            if score < -BOUND_TOL or score > 1.0 + BOUND_TOL:
                print(
                    f"FATAL: Axis 1 score out of bounds for {country}: {score}",
                    file=sys.stderr,
                )
                sys.exit(1)
            score = round(max(0.0, min(1.0, score)), ROUND_PRECISION)

        result = AxisResult(
            country=country,
            axis_id=1,
            axis_slug="financial",
            score=score,
            basis=basis,
            validity=validity,
            coverage=None,  # BIS/CPIS coverage is full for reporting countries
            source=SOURCE,
            warnings=tuple(warnings),
            channel_a_concentration=round(c_a, ROUND_PRECISION) if c_a is not None else None,
            channel_b_concentration=round(c_b, ROUND_PRECISION) if c_b is not None else None,
        )
        validate_axis_result(result)
        results.append(result)

    return results


def main() -> None:
    print("=" * 68)
    print("ISI v1.1 — Axis 1: Financial Sovereignty (Global Phase 1)")
    print("=" * 68)
    print()

    results = compute_axis_1()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_1_financial.json"

    output = {
        "axis_id": 1,
        "axis_slug": "financial",
        "methodology_version": METHODOLOGY,
        "scope": SCOPE_ID,
        "source": SOURCE,
        "countries": [r.to_dict() for r in results],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    print(f"Results written to {out_path}")
    print()

    for r in results:
        status = f"{r.score:.8f}" if r.score is not None else "INVALID"
        warns = f"  [{', '.join(r.warnings)}]" if r.warnings else ""
        print(f"  {r.country}  score={status}  basis={r.basis}  validity={r.validity}{warns}")

    # Summary
    valid = sum(1 for r in results if r.validity == "VALID")
    a_only = sum(1 for r in results if r.validity == "A_ONLY")
    degraded = sum(1 for r in results if r.validity == "DEGRADED")
    invalid = sum(1 for r in results if r.validity == "INVALID")
    print()
    print(f"Summary: VALID={valid}  A_ONLY={a_only}  DEGRADED={degraded}  INVALID={invalid}")


if __name__ == "__main__":
    main()
