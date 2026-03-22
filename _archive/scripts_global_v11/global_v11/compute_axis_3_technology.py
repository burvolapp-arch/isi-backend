#!/usr/bin/env python3
"""ISI v1.1 — Axis 3: Technology Sovereignty (Global Scope)

Computes technology import dependency for expansion countries using:
  Channel A: Aggregate supplier concentration (HHI on total semiconductor imports)
  Channel B: Category-weighted supplier concentration (by HS sub-category)

Data source:
  EU-27 uses Eurostat Comext (CN8 granularity → both channels).
  Expansion countries use UN Comtrade (HS-6 granularity).

CRITICAL LIMITATION (LIM-002):
  UN Comtrade provides HS-6 codes, not CN8. The v1.0 Channel B uses CN8
  codes to map semiconductors into sub-categories (legacy_discrete,
  legacy_components, integrated_circuits). With only HS-6, the category
  split is:
    - HS 8541 (all of it) → "discrete_and_components" (merged)
    - HS 8542 → "integrated_circuits"
  This reduces from 3 sub-categories to 2, which affects the
  category-weighted HHI. The W-HS6-GRANULARITY warning is applied.

  For countries where ONLY Channel A is computable (e.g., if HS sub-
  category data is insufficient), basis = A_ONLY, validity = A_ONLY.

Input:
  data/processed/global_v11/tech/comtrade_semiconductor_2022_2024_flat.csv
  Schema: reporter,partner,product_code,hs_level,year,value

Output:
  data/processed/global_v11/axis_3_technology.json
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.axis_result import AxisResult, make_invalid_axis, validate_axis_result
from backend.constants import ROUND_PRECISION
from backend.scope import (
    PHASE1_EXPANSION_CODES,
    get_scope_sorted,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMTRADE_FLAT = (
    PROJECT_ROOT / "data" / "processed" / "global_v11" / "tech"
    / "comtrade_semiconductor_2022_2024_flat.csv"
)
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
SOURCE = "COMTRADE_SEMI_2022_2024"
BOUND_TOL = 1e-9
SHARE_SUM_TOL = 1e-9

# HS-6 to category mapping (reduced granularity)
# 8541xx → discrete_and_components (merged from CN8 sub-categories)
# 8542xx → integrated_circuits
HS6_CATEGORIES = {
    "8541": "discrete_and_components",
    "8542": "integrated_circuits",
}


def compute_channel_a(
    flat_rows: list[dict[str, str]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Channel A: Aggregate HHI on total semiconductor imports."""
    pair_values: defaultdict[tuple[str, str], float] = defaultdict(float)
    rec_totals: defaultdict[str, float] = defaultdict(float)

    for row in flat_rows:
        rec = row["reporter"]
        partner = row["partner"]
        value = float(row["value"])
        pair_values[(rec, partner)] += value
        rec_totals[rec] += value

    conc: dict[str, float] = {}
    vol: dict[str, float] = {}

    for rec in rec_totals:
        total = rec_totals[rec]
        vol[rec] = total
        if total <= 0:
            continue
        hhi = sum(
            (v / total) ** 2
            for (r, _), v in pair_values.items()
            if r == rec
        )
        conc[rec] = hhi

    return conc, vol


def compute_channel_b(
    flat_rows: list[dict[str, str]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Channel B: Category-weighted HHI (HS-4 level categories).

    Maps HS-6 codes to categories via HS-4 prefix.
    """
    triple: defaultdict[tuple[str, str, str], float] = defaultdict(float)

    for row in flat_rows:
        rec = row["reporter"]
        partner = row["partner"]
        code = row["product_code"].strip()
        value = float(row["value"])

        hs4 = code[:4]
        cat = HS6_CATEGORIES.get(hs4)
        if cat is None:
            continue

        triple[(rec, cat, partner)] += value

    # category totals
    cat_totals: defaultdict[tuple[str, str], float] = defaultdict(float)
    for (rec, cat, _), val in triple.items():
        cat_totals[(rec, cat)] += val

    # category HHI
    cat_hhi: dict[tuple[str, str], float] = {}
    for (rec, cat), total in cat_totals.items():
        if total <= 0:
            continue
        hhi = sum(
            (v / total) ** 2
            for (r, c, _), v in triple.items()
            if r == rec and c == cat
        )
        cat_hhi[(rec, cat)] = hhi

    # weighted average
    conc: dict[str, float] = {}
    vol: dict[str, float] = {}
    reporters = {rec for (rec, _) in cat_totals}

    for rec in reporters:
        numerator = 0.0
        denominator = 0.0
        for (r, cat), total in cat_totals.items():
            if r == rec and (r, cat) in cat_hhi:
                numerator += cat_hhi[(r, cat)] * total
                denominator += total
        if denominator > 0:
            conc[rec] = numerator / denominator
            vol[rec] = denominator

    return conc, vol


def load_comtrade_rows() -> list[dict[str, str]]:
    """Load Comtrade flat file, filtering to Phase 1 reporters."""
    if not COMTRADE_FLAT.is_file():
        return []

    rows: list[dict[str, str]] = []
    with open(COMTRADE_FLAT, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["reporter"].strip() in PHASE1_EXPANSION_CODES:
                rows.append(row)
    return rows


def compute_axis_3() -> list[AxisResult]:
    """Compute Axis 3 for all Phase 1 countries."""
    flat_rows = load_comtrade_rows()

    if flat_rows:
        ca_conc, ca_vol = compute_channel_a(flat_rows)
        cb_conc, cb_vol = compute_channel_b(flat_rows)
    else:
        ca_conc, ca_vol = {}, {}
        cb_conc, cb_vol = {}, {}

    results: list[AxisResult] = []
    countries = get_scope_sorted(SCOPE_ID)

    for country in countries:
        warnings: list[str] = []

        c_a = ca_conc.get(country)
        w_a = ca_vol.get(country, 0.0)
        c_b = cb_conc.get(country)
        w_b = cb_vol.get(country, 0.0)

        has_a = c_a is not None and w_a > 0.0
        has_b = c_b is not None and w_b > 0.0

        if not has_a and not has_b:
            result = make_invalid_axis(
                country=country,
                axis_id=3,
                source=SOURCE,
                warnings=("No semiconductor trade data available",),
            )
            validate_axis_result(result)
            results.append(result)
            continue

        # HS-6 granularity warning (always applies for Comtrade data)
        warnings.append("W-HS6-GRANULARITY")

        if has_a and has_b:
            score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
            basis = "BOTH"
            validity = "VALID"
        elif has_a:
            score = c_a
            basis = "A_ONLY"
            validity = "A_ONLY"
        else:
            score = c_b
            basis = "B_ONLY"
            validity = "A_ONLY"

        if score < -BOUND_TOL or score > 1.0 + BOUND_TOL:
            print(f"FATAL: Axis 3 score out of bounds for {country}: {score}", file=sys.stderr)
            sys.exit(1)
        score = round(max(0.0, min(1.0, score)), ROUND_PRECISION)

        result = AxisResult(
            country=country,
            axis_id=3,
            axis_slug="technology",
            score=score,
            basis=basis,
            validity=validity,
            coverage=None,
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
    print("ISI v1.1 — Axis 3: Technology Sovereignty (Global Phase 1)")
    print("=" * 68)
    print()

    results = compute_axis_3()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_3_technology.json"

    output = {
        "axis_id": 3,
        "axis_slug": "technology",
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

    valid = sum(1 for r in results if r.validity == "VALID")
    a_only = sum(1 for r in results if r.validity == "A_ONLY")
    invalid = sum(1 for r in results if r.validity == "INVALID")
    print()
    print(f"Summary: VALID={valid}  A_ONLY={a_only}  INVALID={invalid}")


if __name__ == "__main__":
    main()
