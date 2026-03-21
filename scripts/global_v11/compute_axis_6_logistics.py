#!/usr/bin/env python3
"""ISI v1.1 — Axis 6: Logistics Sovereignty (Global Scope) — DEFERRED

This axis is structurally INVALID for all Phase 1 expansion countries.

Rationale (constraint spec LIM-003, LIM-004):
  The v1.0 logistics axis uses two EU-specific Eurostat datasets:
    - Channel A: tran_hv_frmod (freight mode shares: road/rail/IWW/maritime)
    - Channel B: road_go_ta_tcrg + rail_go_grpgood + mar_go_aa (bilateral
                 partner shares per mode)

  These datasets exist ONLY for EU/EFTA countries. Norway (NO) may have
  partial EFTA reporting for Channel A, but Channel B bilateral data is
  Eurostat-only.

  For AU, CN, GB, JP, KR, US: NO equivalent global data source exists
  that provides bilateral freight mode/partner granularity at the
  level required for the ISI methodology.

  Possible future sources (Phase 2+):
    - ITC Trade Map logistics indicators
    - World Bank Logistics Performance Index (ordinal, not bilateral)
    - National statistical office freight surveys (per-country, heterogeneous)
    - UNCTAD Review of Maritime Transport (maritime only)

  None of these provide the bilateral mode×partner granularity needed.

Action:
  This script produces INVALID AxisResult for all 7 expansion countries
  with explicit audit trail. The composite engine will exclude this axis
  from the denominator (variable axis count).

  This is honest, constraint-compliant, and documented. No fabrication.

Output:
  data/processed/global_v11/axis_6_logistics.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.axis_result import AxisResult, make_invalid_axis, validate_axis_result
from backend.scope import get_scope_sorted

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "global_v11"

SCOPE_ID = "PHASE1-7"
METHODOLOGY = "v1.1"
SOURCE = "NONE"


def compute_axis_6() -> list[AxisResult]:
    """Produce INVALID AxisResult for all Phase 1 countries.

    Logistics data is EU-only. No global equivalent exists.
    This is a structural data gap, not a computation error.
    """
    results: list[AxisResult] = []
    countries = get_scope_sorted(SCOPE_ID)

    for country in countries:
        warnings = [
            "LIM-003: No global freight mode/partner data source",
            "LIM-004: Eurostat tran_hv_frmod is EU/EFTA only",
        ]

        # Norway might have partial Channel A from EFTA reporting,
        # but without Channel B bilateral data, the axis is still
        # structurally incomplete. Mark as INVALID for consistency.
        if country == "NO":
            warnings.append(
                "NO: Partial EFTA freight mode data may exist, "
                "but bilateral partner data (Channel B) is unavailable"
            )

        result = make_invalid_axis(
            country=country,
            axis_id=6,
            source=SOURCE,
            warnings=tuple(warnings),
        )
        validate_axis_result(result)
        results.append(result)

    return results


def main() -> None:
    print("=" * 68)
    print("ISI v1.1 — Axis 6: Logistics Sovereignty (Global Phase 1)")
    print("           *** DEFERRED — ALL COUNTRIES INVALID ***")
    print("=" * 68)
    print()
    print("  Logistics axis requires Eurostat freight data (EU/EFTA only).")
    print("  No equivalent global data source exists.")
    print("  All Phase 1 expansion countries marked INVALID.")
    print()

    results = compute_axis_6()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "axis_6_logistics.json"

    output = {
        "axis_id": 6,
        "axis_slug": "logistics",
        "methodology_version": METHODOLOGY,
        "scope": SCOPE_ID,
        "source": SOURCE,
        "deferred": True,
        "deferral_reason": "No global freight mode/partner data source equivalent to Eurostat tran_hv_frmod",
        "countries": [r.to_dict() for r in results],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")

    print(f"Results written to {out_path}")
    print()

    for r in results:
        warns = f"  [{r.warnings[0]}]" if r.warnings else ""
        print(f"  {r.country}  score=INVALID  validity=INVALID{warns}")

    print()
    print("Summary: VALID=0  INVALID=7  (all deferred)")
    print()
    print("Composite engine will exclude Axis 6 from denominator.")
    print("Minimum 4 of remaining 5 axes required for composite eligibility.")


if __name__ == "__main__":
    main()
