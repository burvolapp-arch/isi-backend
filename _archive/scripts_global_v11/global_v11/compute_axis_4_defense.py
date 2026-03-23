#!/usr/bin/env python3
"""ISI v1.1 — Axis 4: Defense Sovereignty (Global Scope)

Computes defense dependency for expansion countries using:
  Channel A: Aggregate supplier concentration (HHI on TIV shares)
  Channel B: Capability-weighted supplier concentration (block-weighted HHI)

This script reads the SAME intermediate SIPRI bilateral flat CSV
produced by the existing v1.0 parser (parse_defense_sipri_raw.py).
The flat file contains ALL recipient/supplier pairs in the SIPRI
database, not just EU-27. The EU-27 filter is only in the v1.0
channel computation scripts (compute_defense_channel_a.py, _b.py).

This script computes both channels from the raw flat CSV, filters
to the Phase 1 scope, then aggregates cross-channel per the same
weighted-mean methodology as v1.0.

CRITICAL SEMANTIC RULES:
  - Zero-bilateral-suppliers → score = 0.0, basis = "NO_BILATERAL_SUPPLIERS"
    (same locked semantic as v1.0 — no bilateral imports = zero concentration)
  - Major exporters (US, CN) get W-PRODUCER-INVERSION warning
    (does NOT modify score — flag only)

Input:
  data/processed/defense/sipri_bilateral_2019_2024_flat.csv
  Schema: recipient_country,supplier_country,capability_block,year,tiv

Output:
  data/processed/global_v11/axis_4_defense.json

Constraint spec references:
  - Section 5.1 (axis validity framework)
  - Section 8.2 (cross-channel aggregation)
  - Section 8.3 (HHI formula — not percentile)
  - Section 10 (producer inversion)
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.axis_result import AxisResult, validate_axis_result
from backend.constants import ROUND_PRECISION
from backend.scope import (
    PHASE1_EXPANSION_CODES,
    SIPRI_TO_CANONICAL_EXPANSION,
    get_scope_sorted,
    is_producer_inverted,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROC_DIR = PROJECT_ROOT / "data" / "processed" / "defense"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

INPUT_FILE = PROC_DIR / "sipri_bilateral_2019_2024_flat.csv"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
SOURCE = "SIPRI_TIV_2019_2024"
BOUND_TOL = 1e-9
SHARE_SUM_TOL = 1e-9


def compute_channel_a(
    flat_rows: list[dict[str, str]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Channel A: Aggregate supplier concentration (HHI on total TIV shares).

    Returns (concentration_by_country, volume_by_country).
    """
    pair_values: defaultdict[tuple[str, str], float] = defaultdict(float)
    rec_totals: defaultdict[str, float] = defaultdict(float)

    for row in flat_rows:
        rec = row["recipient_country"]
        sup = row["supplier_country"]
        tiv = float(row["tiv"])
        pair_values[(rec, sup)] += tiv
        rec_totals[rec] += tiv

    conc: dict[str, float] = {}
    vol: dict[str, float] = {}

    for rec in rec_totals:
        total = rec_totals[rec]
        vol[rec] = total
        if total == 0.0:
            continue
        hhi = 0.0
        for (r, s), v in pair_values.items():
            if r == rec:
                share = v / total
                hhi += share ** 2
        conc[rec] = hhi

    return conc, vol


def compute_channel_b(
    flat_rows: list[dict[str, str]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Channel B: Capability-weighted supplier concentration.

    Per block: HHI on supplier shares within block.
    Cross-block: Volume-weighted average of block HHIs.

    Returns (concentration_by_country, volume_by_country).
    """
    # (rec, block, sup) → TIV
    triple_tiv: defaultdict[tuple[str, str, str], float] = defaultdict(float)

    for row in flat_rows:
        rec = row["recipient_country"]
        sup = row["supplier_country"]
        blk = row["capability_block"]
        tiv = float(row["tiv"])
        triple_tiv[(rec, blk, sup)] += tiv

    # block totals: (rec, blk) → total
    block_totals: defaultdict[tuple[str, str], float] = defaultdict(float)
    for (rec, blk, sup), val in triple_tiv.items():
        block_totals[(rec, blk)] += val

    # per-recipient totals and block HHIs
    rec_totals: defaultdict[str, float] = defaultdict(float)
    block_hhis: dict[tuple[str, str], float] = {}

    for (rec, blk), bt in block_totals.items():
        rec_totals[rec] += bt
        if bt == 0.0:
            continue
        hhi = 0.0
        for (r, b, s), v in triple_tiv.items():
            if r == rec and b == blk:
                share = v / bt
                hhi += share ** 2
        block_hhis[(rec, blk)] = hhi

    conc: dict[str, float] = {}
    vol: dict[str, float] = {}

    for rec in rec_totals:
        total = rec_totals[rec]
        vol[rec] = total
        if total == 0.0:
            continue
        weighted_sum = 0.0
        weight_sum = 0.0
        for (r, blk), bt in block_totals.items():
            if r == rec and bt > 0.0 and (r, blk) in block_hhis:
                weighted_sum += block_hhis[(r, blk)] * bt
                weight_sum += bt
        if weight_sum > 0.0:
            conc[rec] = weighted_sum / weight_sum

    return conc, vol


def load_flat_csv_for_scope(filepath: Path) -> list[dict[str, str]]:
    """Load SIPRI flat CSV, filtering to Phase 1 recipient countries.

    The flat CSV uses canonical ISO-2 codes produced by
    parse_defense_sipri_raw.py. The SIPRI parser maps SIPRI recipient
    names to Eurostat codes for EU-27, but the flat file also contains
    entries for non-EU countries if they were mapped in SUPPLIER_NAME_TO_CODE.

    For expansion countries, we need to check if the flat file uses
    SIPRI country names or ISO-2 codes in recipient_country.
    The existing parser maps recipients via SIPRI_TO_EUROSTAT → ISO-2.
    """
    rows: list[dict[str, str]] = []

    # Build reverse lookup: ISO-2 codes that are in Phase 1 scope
    scope_codes = PHASE1_EXPANSION_CODES

    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = row["recipient_country"].strip()
            # The flat file may contain ISO-2 codes directly, or we may
            # need SIPRI name → canonical mapping
            if rec in scope_codes:
                rows.append(row)
            else:
                # Try SIPRI name mapping
                canonical = SIPRI_TO_CANONICAL_EXPANSION.get(rec)
                if canonical is not None:
                    row["recipient_country"] = canonical
                    rows.append(row)

    return rows


def compute_axis_4() -> list[AxisResult]:
    """Compute Axis 4 for all Phase 1 countries."""
    if not INPUT_FILE.is_file():
        print(f"FATAL: SIPRI flat CSV not found: {INPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    flat_rows = load_flat_csv_for_scope(INPUT_FILE)
    print(f"  SIPRI rows for Phase 1 scope: {len(flat_rows)}")

    ca_conc, ca_vol = compute_channel_a(flat_rows)
    cb_conc, cb_vol = compute_channel_b(flat_rows)

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

        # Producer inversion check
        if is_producer_inverted(country, 4):
            warnings.append("W-PRODUCER-INVERSION")

        if has_a and has_b:
            score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
            basis = "BOTH"
            validity = "VALID"
        elif has_a and not has_b:
            score = c_a
            basis = "A_ONLY"
            validity = "A_ONLY"
        elif has_b and not has_a:
            score = c_b
            basis = "B_ONLY"
            validity = "A_ONLY"
        else:
            # ZERO-DEPENDENCY SEMANTIC (same as v1.0 locked rule):
            # Country has NO bilateral SIPRI supplier entries.
            # This means zero external supplier concentration → score = 0.0
            # NOT missing data, NOT estimated.
            score = 0.0
            basis = "BOTH"  # structural zero, fully defined
            validity = "VALID"
            warnings.append("D-5")
            print(f"  INFO: {country} has no bilateral SIPRI suppliers — "
                  f"defense dependency := 0.0 (zero external concentration)")

        if score < -BOUND_TOL or score > 1.0 + BOUND_TOL:
            print(
                f"FATAL: Axis 4 score out of bounds for {country}: {score}",
                file=sys.stderr,
            )
            sys.exit(1)
        score = round(max(0.0, min(1.0, score)), ROUND_PRECISION)

        # Validity override for producer inversion + low score
        if is_producer_inverted(country, 4) and score < 0.05:
            validity = "DEGRADED"
            warnings.append("W-SANCTIONS-DISTORTION")

        result = AxisResult(
            country=country,
            axis_id=4,
            axis_slug="defense",
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
    print("ISI v1.1 — Axis 4: Defense Sovereignty (Global Phase 1)")
    print("=" * 68)
    print()

    results = compute_axis_4()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_4_defense.json"

    output = {
        "axis_id": 4,
        "axis_slug": "defense",
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
    degraded = sum(1 for r in results if r.validity == "DEGRADED")
    invalid = sum(1 for r in results if r.validity == "INVALID")
    print()
    print(f"Summary: VALID={valid}  A_ONLY={a_only}  DEGRADED={degraded}  INVALID={invalid}")


if __name__ == "__main__":
    main()
