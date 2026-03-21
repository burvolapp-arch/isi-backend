#!/usr/bin/env python3
"""ISI v1.1 — Axis 6: Logistics Sovereignty (Global Scope)

Computes Axis 6 for Phase 1 expansion countries using the same
two-channel framework as v1.0:

  Channel A — Transport Mode Concentration (HHI over mode shares)
  Channel B — Bilateral Partner Concentration per Mode (partner HHI)
  Cross-channel: volume-weighted mean when both exist; A_ONLY / B_ONLY
                 fallback when one channel is missing.

Channel A data availability (constraint spec correction):
  Channel A measures HOW CONCENTRATED a country's international freight
  is across transport modes (road, rail, maritime, IWW/pipeline/air).
  This metric is computable from national transport statistics, ITF/OECD
  inland transport statistics, or UNCTAD Review of Maritime Transport.
  It is NOT limited to Eurostat.

  Expected file: data/processed/global_v11/logistics_channel_a_global.csv
  Schema: reporter,channel_a_mode_hhi,total_tonnes,n_modes_used

  This file is populated from ITF/OECD + national statistical offices.
  Countries without Channel A data fall through to INVALID.

Channel B data availability:
  Channel B requires bilateral freight flows per mode (partner × mode
  matrix). This is Eurostat-specific (road_go_ta_tcrg, rail_go_grpgood,
  mar_go_aa). Only EU/EFTA countries have this data.
  Norway (NO) may have partial EFTA bilateral data.

  Expected file: data/processed/global_v11/logistics_channel_b_global.csv
  Schema: reporter,channel_b_partner_hhi,total_tonnes

  Countries without Channel B data get A_ONLY if Channel A exists.

Per-country validity:
  has_A and has_B → VALID,   basis=BOTH
  has_A only      → A_ONLY,  basis=A_ONLY     (degraded but computable)
  has_B only      → A_ONLY,  basis=B_ONLY     (unlikely but handled)
  neither         → INVALID, basis=INVALID

Output:
  data/processed/global_v11/axis_6_logistics.json
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.axis_result import AxisResult, make_invalid_axis, validate_axis_result
from backend.constants import ROUND_PRECISION
from backend.scope import get_scope_sorted

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

# Channel data files — global scope
CHANNEL_A_FILE = OUT_DIR / "logistics_channel_a_global.csv"
CHANNEL_B_FILE = OUT_DIR / "logistics_channel_b_global.csv"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
SOURCE_A = "ITF/OECD + national statistics"
SOURCE_B = "Eurostat/EFTA bilateral freight"
SOURCE_NONE = "NONE"

BOUND_TOLERANCE = 1e-9


def _load_channel_a() -> dict[str, dict]:
    """Load Channel A CSV: reporter → {hhi, weight, modes_used}.

    Returns empty dict if file does not exist (no data available).
    """
    if not CHANNEL_A_FILE.exists():
        return {}

    result: dict[str, dict] = {}
    with open(CHANNEL_A_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reporter = row["reporter"].strip()
            hhi = float(row["channel_a_mode_hhi"])
            weight = float(row["total_tonnes"])
            modes = int(row["n_modes_used"])

            # Validate
            if math.isnan(hhi) or hhi < 0.0 or hhi > 1.0 + BOUND_TOLERANCE:
                raise ValueError(
                    f"Channel A: invalid HHI {hhi} for {reporter}"
                )
            if weight < 0.0:
                raise ValueError(
                    f"Channel A: negative weight {weight} for {reporter}"
                )

            result[reporter] = {
                "hhi": hhi,
                "weight": weight,
                "modes_used": modes,
            }

    return result


def _load_channel_b() -> dict[str, dict]:
    """Load Channel B CSV: reporter → {hhi, weight}.

    Returns empty dict if file does not exist (no data available).
    """
    if not CHANNEL_B_FILE.exists():
        return {}

    result: dict[str, dict] = {}
    with open(CHANNEL_B_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reporter = row["reporter"].strip()
            hhi_str = row["channel_b_partner_hhi"].strip()
            weight = float(row["total_tonnes"])

            # Channel B HHI can be empty (no bilateral data)
            if not hhi_str:
                continue

            hhi = float(hhi_str)

            if math.isnan(hhi) or hhi < 0.0 or hhi > 1.0 + BOUND_TOLERANCE:
                raise ValueError(
                    f"Channel B: invalid HHI {hhi} for {reporter}"
                )
            if weight < 0.0:
                raise ValueError(
                    f"Channel B: negative weight {weight} for {reporter}"
                )

            result[reporter] = {
                "hhi": hhi,
                "weight": weight,
            }

    return result


def compute_axis_6() -> list[AxisResult]:
    """Compute Axis 6 (Logistics) for Phase 1 expansion countries.

    Follows the v1.0 two-channel methodology with data-availability-
    driven validity:
      - Channel A exists globally (mode concentration HHI)
      - Channel B is partial (bilateral partner HHI, EU/EFTA only)
      - A_ONLY is a valid degraded result, NOT INVALID
    """
    channel_a = _load_channel_a()
    channel_b = _load_channel_b()

    countries = get_scope_sorted(SCOPE_ID)
    results: list[AxisResult] = []

    n_loaded_a = len(channel_a)
    n_loaded_b = len(channel_b)
    print(f"  Channel A loaded: {n_loaded_a} countries")
    print(f"  Channel B loaded: {n_loaded_b} countries")

    for country in countries:
        has_a = country in channel_a and channel_a[country]["weight"] > 0.0
        has_b = country in channel_b and channel_b[country]["weight"] > 0.0

        warnings: list[str] = []

        if has_a and has_b:
            # ── BOTH channels available ──
            c_a = channel_a[country]["hhi"]
            w_a = channel_a[country]["weight"]
            c_b = channel_b[country]["hhi"]
            w_b = channel_b[country]["weight"]

            # Volume-weighted cross-channel aggregation (v1.0 formula)
            score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
            basis = "BOTH"
            validity = "VALID"
            source = f"{SOURCE_A} + {SOURCE_B}"
            ch_a_val = c_a
            ch_b_val = c_b

        elif has_a and not has_b:
            # ── Channel A only — degraded but computable ──
            c_a = channel_a[country]["hhi"]
            score = c_a
            basis = "A_ONLY"
            validity = "A_ONLY"
            source = SOURCE_A
            ch_a_val = c_a
            ch_b_val = None
            warnings.append(
                "LIM-004: Channel B (bilateral partner HHI) unavailable — "
                "score derived from Channel A (mode concentration) only"
            )

        elif has_b and not has_a:
            # ── Channel B only — unlikely but handled for completeness ──
            c_b = channel_b[country]["hhi"]
            score = c_b
            basis = "B_ONLY"
            validity = "DEGRADED"
            source = SOURCE_B
            ch_a_val = None
            ch_b_val = c_b
            warnings.append(
                "Channel A (mode concentration) unavailable — "
                "score derived from Channel B (partner concentration) only"
            )

        else:
            # ── Neither channel available → INVALID ──
            result = make_invalid_axis(
                country=country,
                axis_id=6,
                source=SOURCE_NONE,
                warnings=(
                    "LIM-003: No freight mode/partner data available",
                ),
            )
            validate_axis_result(result)
            results.append(result)
            continue

        # Validate computed score
        if math.isnan(score) or math.isinf(score):
            raise ValueError(
                f"Axis 6 score is NaN/Inf for {country}"
            )
        if score < 0.0 or score > 1.0 + BOUND_TOLERANCE:
            raise ValueError(
                f"Axis 6 score out of [0, 1] for {country}: {score}"
            )

        result = AxisResult(
            country=country,
            axis_id=6,
            axis_slug="logistics",
            score=round(score, ROUND_PRECISION),
            basis=basis,
            validity=validity,
            coverage=None,
            source=source,
            warnings=tuple(warnings),
            channel_a_concentration=ch_a_val,
            channel_b_concentration=ch_b_val,
        )
        validate_axis_result(result)
        results.append(result)

    return results


def main() -> None:
    print("=" * 68)
    print("ISI v1.1 — Axis 6: Logistics Sovereignty (Global Phase 1)")
    print("=" * 68)
    print()
    print("  Two-channel methodology (v1.0 compatible):")
    print("    Channel A: Transport mode concentration (HHI)")
    print("    Channel B: Bilateral partner concentration (HHI)")
    print("  Cross-channel: volume-weighted mean (BOTH), or fallback")
    print()

    results = compute_axis_6()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_6_logistics.json"

    # Tally validity states
    n_valid = sum(1 for r in results if r.validity == "VALID")
    n_a_only = sum(1 for r in results if r.validity == "A_ONLY")
    n_degraded = sum(1 for r in results if r.validity == "DEGRADED")
    n_invalid = sum(1 for r in results if r.validity == "INVALID")

    output = {
        "axis_id": 6,
        "axis_slug": "logistics",
        "methodology_version": METHODOLOGY,
        "scope": SCOPE_ID,
        "sources": [SOURCE_A, SOURCE_B],
        "channel_a_available": CHANNEL_A_FILE.exists(),
        "channel_b_available": CHANNEL_B_FILE.exists(),
        "validity_summary": {
            "VALID": n_valid,
            "A_ONLY": n_a_only,
            "DEGRADED": n_degraded,
            "INVALID": n_invalid,
        },
        "countries": [r.to_dict() for r in results],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    print(f"Results written to {out_path}")
    print()

    for r in results:
        score_str = f"{r.score:.6f}" if r.score is not None else "N/A"
        basis_str = r.basis
        warns = f"  [{r.warnings[0][:60]}...]" if r.warnings else ""
        print(f"  {r.country}  score={score_str}  "
              f"validity={r.validity}  basis={basis_str}{warns}")

    print()
    print(f"Summary: VALID={n_valid}  A_ONLY={n_a_only}  "
          f"DEGRADED={n_degraded}  INVALID={n_invalid}")
    print()

    if n_valid + n_a_only + n_degraded > 0:
        print("Axis 6 contributes to composite for countries with data.")
    if n_invalid > 0:
        print(f"Composite engine will exclude Axis 6 for {n_invalid} "
              f"INVALID countries (variable axis count).")


if __name__ == "__main__":
    main()
