#!/usr/bin/env python3
"""ISI v1.1 — Axis 2: Energy Sovereignty (Global Scope)

Computes energy import dependency for expansion countries.

Data source strategy:
  - Norway (NO): May appear in Eurostat energy data (EFTA reporting).
    If present in the existing v1.0 energy pipeline output, use it directly.
  - AU, CN, GB, JP, KR, US: Require UN Comtrade fuel import data
    parsed via parse_comtrade.py → energy fuel flat files.

The existing v1.0 energy pipeline (aggregate_energy_fuel_concentration.py,
compute_energy_axis_score.py) is fully country-agnostic — it processes ALL
geo codes in its input without EU-27 filtering. Therefore:
  - If Eurostat covers a country, its score appears in energy_dependency_2024.csv
  - For non-Eurostat countries, we compute from Comtrade flat data

Energy methodology:
  For each country i, for each fuel type f:
    C_i^{f} = HHI on supplier shares for fuel f imports
    W_i^{f} = total import volume for fuel f
  EnergyDependency_i = SUM_f [C_i^f * W_i^f] / SUM_f W_i^f

  Single-channel axis (no A/B distinction).
  basis = "BOTH" (single formula, fully determined).

Producer inversion applies: US, AU, NO are major energy exporters.

Inputs:
  data/processed/energy/energy_dependency_2024.csv (Eurostat path, if countries present)
  data/processed/global_v11/energy/comtrade_energy_fuels_2022_2024_flat.csv (Comtrade path)

Output:
  data/processed/global_v11/axis_2_energy.json
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
    is_producer_inverted,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EUROSTAT_ENERGY_FILE = PROJECT_ROOT / "data" / "processed" / "energy" / "energy_dependency_2024.csv"
COMTRADE_FLAT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11" / "energy"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
BOUND_TOL = 1e-9


def load_eurostat_energy_scores() -> dict[str, float]:
    """Load pre-computed energy scores from v1.0 pipeline output.

    Returns dict: geo → energy_dependency score.
    Only includes Phase 1 countries that happen to be in Eurostat data.
    """
    scores: dict[str, float] = {}

    if not EUROSTAT_ENERGY_FILE.is_file():
        return scores

    with open(EUROSTAT_ENERGY_FILE, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            geo = row["geo"].strip()
            if geo in PHASE1_EXPANSION_CODES:
                scores[geo] = float(row["energy_dependency"])

    return scores


def compute_energy_from_comtrade(flat_path: Path) -> dict[str, float]:
    """Compute energy dependency from Comtrade flat file.

    Uses the same weighted-HHI methodology as v1.0.
    Groups by HS-4 prefix as fuel type proxy:
      2701 → coal, 2709 → crude, 2710 → petroleum products,
      2711 → natural gas, 2716 → electricity.

    Returns dict: geo → energy_dependency score.
    """
    if not flat_path.is_file():
        return {}

    # Accumulate (reporter, fuel_group, partner) → value
    triple: defaultdict[tuple[str, str, str], float] = defaultdict(float)

    HS4_TO_FUEL = {
        "2701": "coal",
        "2709": "crude_oil",
        "2710": "petroleum_products",
        "2711": "natural_gas",
        "2716": "electricity",
    }

    with open(flat_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            reporter = row["reporter"].strip()
            partner = row["partner"].strip()
            code = row["product_code"].strip()
            value = float(row["value"])

            if reporter not in PHASE1_EXPANSION_CODES:
                continue
            if value <= 0:
                continue

            # Map HS-6 code to fuel group via HS-4 prefix
            hs4 = code[:4]
            fuel = HS4_TO_FUEL.get(hs4)
            if fuel is None:
                continue

            triple[(reporter, fuel, partner)] += value

    # Compute per-fuel HHI and volume, then weighted average
    # fuel_totals: (reporter, fuel) → total import value
    fuel_totals: defaultdict[tuple[str, str], float] = defaultdict(float)
    for (rep, fuel, _partner), val in triple.items():
        fuel_totals[(rep, fuel)] += val

    # fuel HHI: (reporter, fuel) → HHI
    fuel_hhi: dict[tuple[str, str], float] = {}
    for (rep, fuel), total in fuel_totals.items():
        if total <= 0:
            continue
        hhi = 0.0
        for (r, f, p), val in triple.items():
            if r == rep and f == fuel:
                share = val / total
                hhi += share ** 2
        fuel_hhi[(rep, fuel)] = hhi

    # Weighted average across fuels
    scores: dict[str, float] = {}
    reporters = {rep for (rep, _) in fuel_totals}

    for rep in reporters:
        numerator = 0.0
        denominator = 0.0
        for (r, f), total in fuel_totals.items():
            if r == rep and (r, f) in fuel_hhi:
                numerator += fuel_hhi[(r, f)] * total
                denominator += total
        if denominator > 0:
            scores[rep] = numerator / denominator

    return scores


def compute_axis_2() -> list[AxisResult]:
    """Compute Axis 2 for all Phase 1 countries."""
    # Strategy: try Eurostat first, then Comtrade
    eurostat_scores = load_eurostat_energy_scores()

    comtrade_flat = COMTRADE_FLAT_DIR / "comtrade_energy_fuels_2022_2024_flat.csv"
    comtrade_scores = compute_energy_from_comtrade(comtrade_flat)

    results: list[AxisResult] = []
    countries = get_scope_sorted(SCOPE_ID)

    for country in countries:
        warnings: list[str] = []

        # Producer inversion
        if is_producer_inverted(country, 2):
            warnings.append("W-PRODUCER-INVERSION")

        # Determine score and source
        score = None
        source = ""

        if country in eurostat_scores:
            score = eurostat_scores[country]
            source = "EUROSTAT_ENERGY_2024"
        elif country in comtrade_scores:
            score = comtrade_scores[country]
            source = "COMTRADE_ENERGY_2022_2024"
            warnings.append("W-HS6-GRANULARITY")  # Comtrade = HS6, not full Eurostat detail
        else:
            # No data from either source
            result = make_invalid_axis(
                country=country,
                axis_id=2,
                source="NONE",
                warnings=tuple(warnings + ["No energy import data available"]),
            )
            validate_axis_result(result)
            results.append(result)
            continue

        # Bound check
        if score < -BOUND_TOL or score > 1.0 + BOUND_TOL:
            print(
                f"FATAL: Axis 2 score out of bounds for {country}: {score}",
                file=sys.stderr,
            )
            sys.exit(1)
        score = round(max(0.0, min(1.0, score)), ROUND_PRECISION)

        # Energy is single-channel → basis is always BOTH if data exists
        result = AxisResult(
            country=country,
            axis_id=2,
            axis_slug="energy",
            score=score,
            basis="BOTH",
            validity="VALID",
            coverage=None,
            source=source,
            warnings=tuple(warnings),
            channel_a_concentration=round(score, ROUND_PRECISION),  # single channel = score
            channel_b_concentration=None,
        )
        validate_axis_result(result)
        results.append(result)

    return results


def main() -> None:
    print("=" * 68)
    print("ISI v1.1 — Axis 2: Energy Sovereignty (Global Phase 1)")
    print("=" * 68)
    print()

    results = compute_axis_2()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_2_energy.json"

    output = {
        "axis_id": 2,
        "axis_slug": "energy",
        "methodology_version": METHODOLOGY,
        "scope": SCOPE_ID,
        "source": "EUROSTAT_ENERGY_2024+COMTRADE_ENERGY_2022_2024",
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
        print(f"  {r.country}  score={status}  basis={r.basis}  validity={r.validity}  src={r.source}{warns}")

    valid = sum(1 for r in results if r.validity == "VALID")
    invalid = sum(1 for r in results if r.validity == "INVALID")
    print()
    print(f"Summary: VALID={valid}  INVALID={invalid}")


if __name__ == "__main__":
    main()
