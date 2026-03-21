#!/usr/bin/env python3
"""ISI v1.1 — Axis 5: Critical Inputs / Raw Materials (Global Scope)

Computes critical materials import dependency for expansion countries.

Data source:
  UN Comtrade (HS-6 level) via parse_comtrade.py → flat CSV.

CRITICAL LIMITATION (LIM-002):
  v1.0 uses Eurostat Comext CN8 (8-digit) codes with a 66-code material
  mapping. For expansion countries, only HS-6 (6-digit) is available
  from UN Comtrade. Material group assignment uses HS-6 prefix mapping
  instead of exact CN8 mapping. This loses some granularity.

Material groups (same 5 as v1.0):
  1. rare_earths
  2. battery_metals
  3. defense_industrial_metals
  4. semiconductor_inputs
  5. fertilizer_chokepoints

HS-6 prefix → material group mapping is derived from the CN8 mapping
by truncating to 6-digit prefixes. Where a single HS-6 prefix maps
to multiple material groups in CN8, the volume is split proportionally
based on the CN8 mapping structure (or assigned to the dominant group).

Methodology:
  Channel A: Aggregate supplier concentration (HHI on total shares)
  Channel B: Material-group weighted concentration (block-weighted HHI)
  Cross-channel: volume-weighted mean (by construction = arithmetic mean)

Producer inversion: CN, AU are major mineral exporters.

Input:
  data/processed/global_v11/critical_inputs/comtrade_critical_inputs_2022_2024_flat.csv
  docs/mappings/critical_materials_hs6_mapping_v11.csv (HS-6 to material group)

Output:
  data/processed/global_v11/axis_5_critical_inputs.json
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
COMTRADE_FLAT = (
    PROJECT_ROOT / "data" / "processed" / "global_v11" / "critical_inputs"
    / "comtrade_critical_inputs_2022_2024_flat.csv"
)
HS6_MAPPING_FILE = (
    PROJECT_ROOT / "docs" / "mappings"
    / "critical_materials_hs6_mapping_v11.csv"
)
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
SOURCE = "COMTRADE_CRIT_2022_2024"
BOUND_TOL = 1e-9

MATERIAL_GROUPS = [
    "rare_earths",
    "battery_metals",
    "defense_industrial_metals",
    "semiconductor_inputs",
    "fertilizer_chokepoints",
]

# Fallback HS-6 prefix → material group mapping
# Used ONLY when docs/mappings/critical_materials_hs6_mapping_v11.csv
# does not exist. These are the dominant HS-6 prefixes for each group.
HS6_FALLBACK_MAPPING: dict[str, str] = {
    # Rare earths
    "280530": "rare_earths",
    "284610": "rare_earths",
    # Battery metals (lithium, cobalt, nickel, manganese)
    "282520": "battery_metals",
    "282200": "battery_metals",
    "750110": "battery_metals",
    "750120": "battery_metals",
    "260500": "battery_metals",  # cobalt ores
    "261000": "battery_metals",  # chromium ores (proxy)
    # Defense industrial metals (titanium, tungsten, vanadium)
    "810810": "defense_industrial_metals",
    "810190": "defense_industrial_metals",
    "811291": "defense_industrial_metals",
    # Semiconductor inputs (silicon, gallium, germanium)
    "280461": "semiconductor_inputs",
    "280469": "semiconductor_inputs",
    "811292": "semiconductor_inputs",
    # Fertilizer chokepoints (potash, phosphates)
    "310420": "fertilizer_chokepoints",
    "310490": "fertilizer_chokepoints",
    "251010": "fertilizer_chokepoints",
}


def load_hs6_mapping() -> dict[str, str]:
    """Load HS-6 → material group mapping.

    Tries official mapping file first, falls back to built-in.
    """
    if HS6_MAPPING_FILE.is_file():
        mapping: dict[str, str] = {}
        with open(HS6_MAPPING_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                code = row["hs6_code"].strip()
                group = row["material_group"].strip()
                if group not in MATERIAL_GROUPS:
                    print(
                        f"WARNING: Unknown material group '{group}' for HS6 {code}",
                        file=sys.stderr,
                    )
                    continue
                mapping[code] = group
        print(f"  Loaded {len(mapping)} HS-6 codes from {HS6_MAPPING_FILE}")
        return mapping

    print(f"  WARNING: {HS6_MAPPING_FILE} not found, using fallback mapping "
          f"({len(HS6_FALLBACK_MAPPING)} codes)")
    return dict(HS6_FALLBACK_MAPPING)


def load_bilateral_data(
    hs6_map: dict[str, str],
) -> list[dict[str, str | float]]:
    """Load Comtrade flat file, filter to Phase 1 reporters and mapped HS-6 codes."""
    if not COMTRADE_FLAT.is_file():
        return []

    rows: list[dict[str, str | float]] = []
    with open(COMTRADE_FLAT, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            reporter = row["reporter"].strip()
            if reporter not in PHASE1_EXPANSION_CODES:
                continue

            code = row["product_code"].strip()[:6]
            group = hs6_map.get(code)
            if group is None:
                continue

            value = float(row["value"])
            if value <= 0:
                continue

            rows.append({
                "reporter": reporter,
                "partner": row["partner"].strip(),
                "code": code,
                "group": group,
                "value": value,
            })

    return rows


def compute_channel_a(
    data: list[dict],
) -> tuple[dict[str, float], dict[str, float]]:
    """Channel A: Aggregate HHI on total critical materials imports."""
    pair_values: defaultdict[tuple[str, str], float] = defaultdict(float)
    rec_totals: defaultdict[str, float] = defaultdict(float)

    for row in data:
        rec = row["reporter"]
        partner = row["partner"]
        val = row["value"]
        pair_values[(rec, partner)] += val
        rec_totals[rec] += val

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
    data: list[dict],
) -> tuple[dict[str, float], dict[str, float]]:
    """Channel B: Material-group weighted HHI."""
    # (rec, group, partner) → value
    triple: defaultdict[tuple[str, str, str], float] = defaultdict(float)
    for row in data:
        triple[(row["reporter"], row["group"], row["partner"])] += row["value"]

    # group totals
    group_totals: defaultdict[tuple[str, str], float] = defaultdict(float)
    for (rec, grp, _), val in triple.items():
        group_totals[(rec, grp)] += val

    # group HHI
    group_hhi: dict[tuple[str, str], float] = {}
    for (rec, grp), total in group_totals.items():
        if total <= 0:
            continue
        hhi = sum(
            (v / total) ** 2
            for (r, g, _), v in triple.items()
            if r == rec and g == grp
        )
        group_hhi[(rec, grp)] = hhi

    # weighted average
    conc: dict[str, float] = {}
    vol: dict[str, float] = {}
    reporters = {rec for (rec, _) in group_totals}

    for rec in reporters:
        numerator = 0.0
        denominator = 0.0
        for (r, grp), total in group_totals.items():
            if r == rec and (r, grp) in group_hhi:
                numerator += group_hhi[(r, grp)] * total
                denominator += total
        if denominator > 0:
            conc[rec] = numerator / denominator
            vol[rec] = denominator

    return conc, vol


def compute_axis_5() -> list[AxisResult]:
    """Compute Axis 5 for all Phase 1 countries."""
    hs6_map = load_hs6_mapping()
    data = load_bilateral_data(hs6_map)
    print(f"  Bilateral rows loaded: {len(data)}")

    if data:
        ca_conc, ca_vol = compute_channel_a(data)
        cb_conc, cb_vol = compute_channel_b(data)
    else:
        ca_conc, ca_vol = {}, {}
        cb_conc, cb_vol = {}, {}

    results: list[AxisResult] = []
    countries = get_scope_sorted(SCOPE_ID)

    for country in countries:
        warnings: list[str] = []

        # Producer inversion
        if is_producer_inverted(country, 5):
            warnings.append("W-PRODUCER-INVERSION")

        c_a = ca_conc.get(country)
        w_a = ca_vol.get(country, 0.0)
        c_b = cb_conc.get(country)
        w_b = cb_vol.get(country, 0.0)

        has_a = c_a is not None and w_a > 0.0
        has_b = c_b is not None and w_b > 0.0

        if not has_a and not has_b:
            result = make_invalid_axis(
                country=country,
                axis_id=5,
                source=SOURCE,
                warnings=tuple(warnings + ["No critical materials trade data available"]),
            )
            validate_axis_result(result)
            results.append(result)
            continue

        # HS-6 granularity warning
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
            print(
                f"FATAL: Axis 5 score out of bounds for {country}: {score}",
                file=sys.stderr,
            )
            sys.exit(1)
        score = round(max(0.0, min(1.0, score)), ROUND_PRECISION)

        result = AxisResult(
            country=country,
            axis_id=5,
            axis_slug="critical_inputs",
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
    print("ISI v1.1 — Axis 5: Critical Inputs (Global Phase 1)")
    print("=" * 68)
    print()

    results = compute_axis_5()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_5_critical_inputs.json"

    output = {
        "axis_id": 5,
        "axis_slug": "critical_inputs",
        "methodology_version": METHODOLOGY,
        "scope": SCOPE_ID,
        "source": SOURCE,
        "countries": [r.to_dict() for r in results],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    print()
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
