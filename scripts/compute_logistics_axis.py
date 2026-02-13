#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Unified Computation Script

Reads raw Eurostat freight CSV files and computes the complete
Axis 6 score from raw data through to final output.

Data availability (as downloaded from Eurostat APIs):
  Road:     road_go_ia_lgtt.csv  — bilateral (geo × c_unload)
            road_go_ia_ugtt.csv  — bilateral (geo × c_load)
  Rail:     rail_go_intgong.csv  — bilateral (geo × c_unload)
  IWW:      iww_go_atygo.csv     — AGGREGATE ONLY (geo, no partner)
  Maritime: mar_go_am_{iso2}.csv — AGGREGATE ONLY (mar_sg_am_cw,
            coastline weight by seaship type, no par_mar partner)

Structural constraints:
  - IWW has no bilateral partner data in Eurostat
    (§6.3 of methodology, documented exclusion from Channel B)
  - Maritime bilateral data (mar_go_am) is discontinued in
    Eurostat dissemination API. mar_go_am_pt (port-level) exists
    but only serves one country per request. No API path to
    country-level bilateral maritime data.
  - Maritime is therefore treated identically to IWW:
    aggregate tonnage contributes to Channel A (mode concentration),
    but is EXCLUDED from Channel B (partner concentration).

Channel A — Transport Mode Concentration:
  Uses TOTAL freight tonnage per reporter per mode (all 4 modes).
  Road+Rail: sum of bilateral flows from raw files.
  IWW: aggregate international freight from iww_go_atygo.csv.
  Maritime: aggregate total freight from mar_sg_am_cw files.
  HHI_A = SUM_m (s_m)^2 where s_m = T_m / T_total

Channel B — Partner Concentration per Transport Mode:
  Uses bilateral flows for {road, rail} ONLY.
  IWW and maritime excluded (no bilateral partner data).
  Per-mode partner HHI, weighted by mode tonnage.

Final Axis 6 Score:
  Axis6_i = (C_A · W_A + C_B · W_B) / (W_A + W_B)
  W_A = total tonnage across all modes (road+rail+iww+maritime)
  W_B = total bilateral tonnage (road+rail only)

Outputs:
  data/processed/logistics/logistics_freight_bilateral_flat.csv
  data/processed/logistics/logistics_channel_a_mode_concentration.csv
  data/processed/logistics/logistics_channel_b_mode_shares.csv
  data/processed/logistics/logistics_channel_b_mode_concentration.csv
  data/processed/logistics/logistics_channel_b_concentration.csv
  data/processed/logistics/logistics_channel_b_volumes.csv
  data/processed/logistics/logistics_freight_axis_score.csv

Task: ISI-LOGISTICS-COMPUTE
"""

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "logistics"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "logistics"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"

# ──────────────────────────────────────────────────────────────
# EU-27 canonical set
# ──────────────────────────────────────────────────────────────

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])
EU27_SET = frozenset(EU27)

# Aggregate codes to reject
REJECT_AGGREGATES = frozenset([
    "EU27_2020", "EU28", "EU27_2007", "EU25", "EU15",
    "EA19", "EA20", "EFTA", "TOTAL", "WORLD",
    "EU_V", "EU_E", "EXT_EU27_2020",
    "NSP", "NSP_E", "UNK",
])

VALID_YEARS = frozenset(["2022", "2023", "2024"])

# Maritime files (from mar_sg_am_cw — aggregate, no partner)
MARITIME_ISO2 = {
    "BE": "be", "BG": "bg", "CY": "cy", "DE": "de", "DK": "dk",
    "EE": "ee", "EL": "el", "ES": "es", "FI": "fi", "FR": "fr",
    "HR": "hr", "IE": "ie", "IT": "it", "LT": "lt", "LV": "lv",
    "MT": "mt", "NL": "nl", "PL": "pl", "PT": "pt", "RO": "ro",
    "SE": "se", "SI": "si",
}

SHARE_TOLERANCE = 1e-9


def normalise_geo(code):
    """Normalise Eurostat geo codes (GR → EL)."""
    code = code.strip().upper()
    return "EL" if code == "GR" else code


def is_aggregate(code):
    code = code.strip().upper()
    if code in REJECT_AGGREGATES:
        return True
    if code.startswith("EU") and len(code) > 2:
        return True
    if code.startswith("EA") and len(code) > 2:
        return True
    return False


def parse_value(val_str):
    """Parse Eurostat value. Returns float or None."""
    val_str = val_str.strip()
    if val_str in ("", ":", "c", "n"):
        return None
    cleaned = val_str.rstrip("pebd ").strip()
    if cleaned == "":
        return None
    try:
        value = float(cleaned)
    except (ValueError, TypeError):
        return None
    return value if value >= 0 else None


# ══════════════════════════════════════════════════════════════
# STAGE 1: Parse raw files
# ══════════════════════════════════════════════════════════════

def parse_bilateral_file(filepath, mode_label, reporter_col_patterns,
                         partner_col_patterns, unit_filter_out=None):
    """Parse a bilateral freight CSV. Returns list of (reporter, partner, mode, year, tonnes)."""
    rows_out = []

    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames

        # Detect columns
        def detect(patterns):
            lower_map = {fld: fld.lower().strip() for fld in fields}
            for pat in patterns:
                for orig, low in lower_map.items():
                    if pat in low:
                        return orig
            return None

        col_reporter = detect(reporter_col_patterns)
        col_partner = detect(partner_col_patterns)
        col_value = detect(["obs_value", "value"])
        col_time = detect(["time_period", "time", "period", "year"])
        col_unit = detect(["unit"])

        if not col_reporter:
            print(f"FATAL: {filepath.name}: no reporter column. Headers: {fields}", file=sys.stderr)
            sys.exit(1)
        if not col_partner:
            print(f"FATAL: {filepath.name}: no partner column. Headers: {fields}", file=sys.stderr)
            sys.exit(1)
        if not col_value:
            print(f"FATAL: {filepath.name}: no value column. Headers: {fields}", file=sys.stderr)
            sys.exit(1)
        if not col_time:
            print(f"FATAL: {filepath.name}: no time column. Headers: {fields}", file=sys.stderr)
            sys.exit(1)

        for row in reader:
            # Reporter
            raw_r = row.get(col_reporter, "").strip()
            if not raw_r or is_aggregate(raw_r):
                continue
            reporter = normalise_geo(raw_r)
            if reporter not in EU27_SET:
                continue

            # Partner
            raw_p = row.get(col_partner, "").strip()
            if not raw_p or is_aggregate(raw_p):
                continue
            partner = normalise_geo(raw_p)

            # Time
            raw_t = row.get(col_time, "").strip()
            if len(raw_t) != 4 or not raw_t.isdigit():
                continue
            if raw_t not in VALID_YEARS:
                continue

            # Unit filter
            if col_unit and unit_filter_out:
                raw_u = row.get(col_unit, "").strip().upper()
                if raw_u in unit_filter_out:
                    continue

            # Value
            val = parse_value(row.get(col_value, ""))
            if val is None or val == 0.0:
                continue

            rows_out.append((reporter, partner, mode_label, raw_t, val))

    return rows_out


def parse_iww_aggregate(filepath):
    """Parse IWW aggregate data. Returns dict: reporter → total THS_T."""
    totals = defaultdict(float)

    with open(filepath, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geo = normalise_geo(row.get("geo", ""))
            if geo not in EU27_SET:
                continue
            tra_cov = row.get("tra_cov", "").strip()
            unit = row.get("unit", "").strip()
            time_p = row.get("TIME_PERIOD", "").strip()
            nst07 = row.get("nst07", "").strip()
            typpack = row.get("typpack", "").strip()
            obs = row.get("OBS_VALUE", "").strip()

            # International, tonnes, annual, total goods, total packaging
            if tra_cov != "INTL":
                continue
            if unit != "THS_T":
                continue
            if len(time_p) != 4 or not time_p.isdigit():
                continue
            if time_p not in VALID_YEARS:
                continue
            if nst07 != "TOTAL":
                continue
            if typpack != "TOTAL":
                continue

            val = parse_value(obs)
            if val is not None and val > 0:
                totals[geo] += val

    return dict(totals)


def parse_maritime_aggregate(raw_dir):
    """Parse maritime aggregate data from mar_sg_am_cw files.
    Returns dict: reporter → total THS_T."""
    totals = {}

    for isi_code, iso2 in sorted(MARITIME_ISO2.items()):
        fp = raw_dir / f"mar_go_am_{iso2}.csv"
        if not fp.exists():
            continue

        country_total = 0.0
        with open(fp, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                unit = row.get("unit", "").strip()
                seaship = row.get("seaship", "").strip()
                time_p = row.get("TIME_PERIOD", "").strip()
                obs = row.get("OBS_VALUE", "").strip()

                if unit != "THS_T":
                    continue
                if seaship != "TOTAL":
                    continue
                if time_p not in VALID_YEARS:
                    continue

                val = parse_value(obs)
                if val is not None and val > 0:
                    country_total += val

        if country_total > 0:
            totals[isi_code] = country_total

    return totals


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("ISI v0.1 — Axis 6: Logistics / Freight Dependency")
    print("Unified Computation Pipeline")
    print("=" * 72)
    print()

    if not RAW_DIR.exists():
        print(f"FATAL: raw data directory not found: {RAW_DIR}", file=sys.stderr)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Parse bilateral data (road, rail) ─────────────────
    print("STAGE 1: Parsing bilateral freight data")
    print("-" * 72)

    # Road — unloaded goods (imports to reporter)
    road_ugtt_file = RAW_DIR / "road_go_ia_ugtt.csv"
    if not road_ugtt_file.exists():
        print(f"FATAL: missing {road_ugtt_file}", file=sys.stderr)
        sys.exit(1)
    print(f"  Parsing: {road_ugtt_file.name} (road, unloaded = imports)")
    road_ugtt = parse_bilateral_file(
        road_ugtt_file, "road",
        ["geo"], ["c_load", "c_unload", "partner"],
        unit_filter_out={"PC", "PC_TOT", "NR", "EUR", "MIO_EUR"},
    )
    print(f"    Rows: {len(road_ugtt):,}")

    # Road — loaded goods (exports from reporter)
    road_lgtt_file = RAW_DIR / "road_go_ia_lgtt.csv"
    if not road_lgtt_file.exists():
        print(f"FATAL: missing {road_lgtt_file}", file=sys.stderr)
        sys.exit(1)
    print(f"  Parsing: {road_lgtt_file.name} (road, loaded = exports)")
    road_lgtt = parse_bilateral_file(
        road_lgtt_file, "road",
        ["geo"], ["c_unload", "c_load", "partner"],
        unit_filter_out={"PC", "PC_TOT", "NR", "EUR", "MIO_EUR"},
    )
    print(f"    Rows: {len(road_lgtt):,}")

    # Rail — international goods
    rail_file = RAW_DIR / "rail_go_intgong.csv"
    if not rail_file.exists():
        print(f"FATAL: missing {rail_file}", file=sys.stderr)
        sys.exit(1)
    print(f"  Parsing: {rail_file.name} (rail)")
    rail_rows = parse_bilateral_file(
        rail_file, "rail",
        ["geo"], ["c_unload", "partner"],
        unit_filter_out={"PC", "PC_TOT", "NR", "EUR", "MIO_EUR", "MIO_TKM"},
    )
    print(f"    Rows: {len(rail_rows):,}")

    # Combine all bilateral rows
    bilateral_rows = road_ugtt + road_lgtt + rail_rows
    print(f"\n  Total bilateral rows: {len(bilateral_rows):,}")

    # Check reporter coverage
    bilateral_reporters = set()
    for r, p, m, y, t in bilateral_rows:
        bilateral_reporters.add(r)
    print(f"  Reporters with bilateral data: {len(bilateral_reporters)}/27")

    missing_bilateral = EU27_SET - bilateral_reporters
    if missing_bilateral:
        print(f"  WARNING: missing bilateral data for: {sorted(missing_bilateral)}")

    # ── 2. Parse aggregate data (IWW, maritime) ──────────────
    print()
    print("STAGE 2: Parsing aggregate freight data")
    print("-" * 72)

    # IWW aggregate
    iww_file = RAW_DIR / "iww_go_atygo.csv"
    if iww_file.exists():
        iww_totals = parse_iww_aggregate(iww_file)
        print(f"  IWW: {len(iww_totals)} reporters with data")
        for geo in sorted(iww_totals.keys()):
            print(f"    {geo}: {iww_totals[geo]:,.1f} THS_T")
    else:
        iww_totals = {}
        print(f"  IWW: MISSING (no file)")

    # Maritime aggregate
    maritime_totals = parse_maritime_aggregate(RAW_DIR)
    print(f"  Maritime: {len(maritime_totals)} reporters with data")
    for geo in sorted(maritime_totals.keys()):
        print(f"    {geo}: {maritime_totals[geo]:,.1f} THS_T")

    # ── 3. Build bilateral aggregates ────────────────────────
    print()
    print("STAGE 3: Computing bilateral aggregates")
    print("-" * 72)

    # Aggregate bilateral data: (reporter, mode, partner) → total tonnes
    bilateral_triple = defaultdict(float)
    for reporter, partner, mode, year, tonnes in bilateral_rows:
        bilateral_triple[(reporter, mode, partner)] += tonnes

    # Mode totals from bilateral data
    bilateral_mode_totals = defaultdict(float)  # (reporter, mode) → tonnes
    for (reporter, mode, partner), val in bilateral_triple.items():
        bilateral_mode_totals[(reporter, mode)] += val

    # Reporter totals from bilateral data
    bilateral_reporter_totals = defaultdict(float)  # reporter → tonnes
    for (reporter, mode), val in bilateral_mode_totals.items():
        bilateral_reporter_totals[reporter] += val

    print(f"  Unique (reporter, mode, partner) triples: {len(bilateral_triple):,}")
    print(f"  Unique (reporter, mode) pairs: {len(bilateral_mode_totals)}")

    # ── 4. Write bilateral flat file ─────────────────────────
    flat_file = OUT_DIR / "logistics_freight_bilateral_flat.csv"
    bilateral_rows.sort(key=lambda r: (r[0], r[2], r[1], r[3]))
    with open(flat_file, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["reporter", "partner", "mode", "year", "tonnes"])
        for row in bilateral_rows:
            w.writerow(row)
    print(f"  Flat file: {flat_file} ({len(bilateral_rows):,} rows)")

    # ── 5. Channel A — Transport Mode Concentration ──────────
    print()
    print("STAGE 4: Channel A — Transport Mode Concentration")
    print("-" * 72)

    # Build total tonnage per (reporter, mode) across ALL modes
    # Road + Rail: from bilateral sums
    # IWW + Maritime: from aggregate data
    mode_tonnes_all = defaultdict(lambda: defaultdict(float))

    # Road and rail from bilateral
    for (reporter, mode), val in bilateral_mode_totals.items():
        mode_tonnes_all[reporter][mode] = val

    # IWW from aggregate
    for reporter, val in iww_totals.items():
        mode_tonnes_all[reporter]["iww"] = val

    # Maritime from aggregate
    for reporter, val in maritime_totals.items():
        mode_tonnes_all[reporter]["maritime"] = val

    # Compute Channel A HHI
    ca_results = {}
    ca_file = OUT_DIR / "logistics_channel_a_mode_concentration.csv"

    with open(ca_file, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "reporter", "channel_a_mode_hhi", "total_tonnes", "n_modes_used",
        ])
        w.writeheader()

        for reporter in EU27:
            modes = mode_tonnes_all.get(reporter, {})
            total = sum(modes.values())
            n_modes = sum(1 for v in modes.values() if v > 0)

            if total == 0 or n_modes == 0:
                print(f"  FATAL: reporter {reporter} has zero freight tonnage.", file=sys.stderr)
                sys.exit(1)

            hhi = 0.0
            for mode_val in modes.values():
                if mode_val > 0:
                    share = mode_val / total
                    hhi += share * share

            if hhi > 1.0 + SHARE_TOLERANCE:
                print(f"  FATAL: HHI > 1 for {reporter}: {hhi}", file=sys.stderr)
                sys.exit(1)
            hhi = min(hhi, 1.0)

            ca_results[reporter] = {
                "hhi": hhi,
                "weight": total,
                "modes_used": n_modes,
            }

            w.writerow({
                "reporter": reporter,
                "channel_a_mode_hhi": f"{hhi:.10f}",
                "total_tonnes": f"{total:.1f}",
                "n_modes_used": n_modes,
            })

    hhi_vals = [v["hhi"] for v in ca_results.values()]
    print(f"  Output: {ca_file}")
    print(f"  Reporters: {len(ca_results)}")
    print(f"  HHI range: [{min(hhi_vals):.6f}, {max(hhi_vals):.6f}]")
    print()

    # Per-reporter Channel A detail
    for reporter in EU27:
        r = ca_results[reporter]
        modes = mode_tonnes_all.get(reporter, {})
        mode_str = ", ".join(f"{m}={v:,.0f}" for m, v in sorted(modes.items()) if v > 0)
        print(f"    {reporter}: HHI={r['hhi']:.6f}  modes={r['modes_used']}  "
              f"total={r['weight']:,.0f}  ({mode_str})")

    # ── 6. Channel B — Partner Concentration ─────────────────
    print()
    print("STAGE 5: Channel B — Partner Concentration per Mode")
    print("-" * 72)

    # Channel B modes: road, rail only
    # (Maritime and IWW excluded — no bilateral partner data)
    CHANNEL_B_MODES = ["road", "rail"]

    shares_file = OUT_DIR / "logistics_channel_b_mode_shares.csv"
    mode_conc_file = OUT_DIR / "logistics_channel_b_mode_concentration.csv"
    conc_file = OUT_DIR / "logistics_channel_b_concentration.csv"
    vol_file = OUT_DIR / "logistics_channel_b_volumes.csv"

    cb_results = {}
    mode_share_rows = 0
    mode_conc_rows = 0

    with open(shares_file, "w", encoding="utf-8", newline="") as fms, \
         open(mode_conc_file, "w", encoding="utf-8", newline="") as fmc:

        msw = csv.writer(fms)
        msw.writerow(["reporter", "mode", "partner", "share"])

        mcw = csv.writer(fmc)
        mcw.writerow(["reporter", "mode", "concentration", "mode_tonnes"])

        for reporter in EU27:
            numerator = 0.0
            denominator = 0.0

            for mode in CHANNEL_B_MODES:
                mt = bilateral_mode_totals.get((reporter, mode), 0.0)
                if mt == 0.0:
                    continue

                # Collect partners
                partners = sorted(
                    [(p, v) for (r, m, p), v in bilateral_triple.items()
                     if r == reporter and m == mode],
                    key=lambda x: x[0],
                )

                hhi_mode = 0.0
                share_sum = 0.0

                for partner, val in partners:
                    share = val / mt
                    if share < 0.0 or share > 1.0 + SHARE_TOLERANCE:
                        print(f"FATAL: share out of bounds for "
                              f"{reporter}/{mode}/{partner}: {share}", file=sys.stderr)
                        sys.exit(1)

                    msw.writerow([reporter, mode, partner, f"{share:.10f}"])
                    mode_share_rows += 1
                    share_sum += share
                    hhi_mode += share * share

                if abs(share_sum - 1.0) > SHARE_TOLERANCE:
                    print(f"FATAL: shares sum to {share_sum:.15f} for "
                          f"{reporter}/{mode}", file=sys.stderr)
                    sys.exit(1)

                mcw.writerow([reporter, mode, f"{hhi_mode:.10f}", f"{mt:.1f}"])
                mode_conc_rows += 1

                numerator += hhi_mode * mt
                denominator += mt

            if denominator > 0:
                weighted_hhi = numerator / denominator
                if weighted_hhi > 1.0 + SHARE_TOLERANCE:
                    print(f"FATAL: weighted HHI > 1 for {reporter}", file=sys.stderr)
                    sys.exit(1)
                weighted_hhi = min(weighted_hhi, 1.0)
                cb_results[reporter] = weighted_hhi
            else:
                # Reporter has NO bilateral freight data at all
                # This would be MT (island, road/rail impossible) or
                # CY (island, rail impossible, road only to where?)
                print(f"  WARNING: {reporter} has zero bilateral "
                      f"tonnage in Channel B modes {CHANNEL_B_MODES}")
                cb_results[reporter] = None

    # Write concentration and volume files
    with open(conc_file, "w", encoding="utf-8", newline="") as fc, \
         open(vol_file, "w", encoding="utf-8", newline="") as fv:

        cw = csv.writer(fc)
        cw.writerow(["reporter", "concentration"])

        vw = csv.writer(fv)
        vw.writerow(["reporter", "total_tonnes"])

        for reporter in EU27:
            bt = bilateral_reporter_totals.get(reporter, 0.0)
            vw.writerow([reporter, f"{bt:.1f}"])

            if cb_results.get(reporter) is not None:
                cw.writerow([reporter, f"{cb_results[reporter]:.10f}"])
            else:
                cw.writerow([reporter, ""])

    print(f"  Mode shares:        {shares_file} ({mode_share_rows:,} rows)")
    print(f"  Mode concentration: {mode_conc_file} ({mode_conc_rows:,} rows)")
    print(f"  Concentration:      {conc_file}")
    print(f"  Volumes:            {vol_file}")

    cb_valid = [v for v in cb_results.values() if v is not None]
    if cb_valid:
        print(f"  HHI range: [{min(cb_valid):.6f}, {max(cb_valid):.6f}]")
    print(f"  Reporters with Channel B data: {len(cb_valid)}/27")

    reporters_no_cb = [r for r in EU27 if cb_results.get(r) is None]
    if reporters_no_cb:
        print(f"  Reporters WITHOUT Channel B: {reporters_no_cb}")
    print()

    # Per-reporter Channel B detail
    for reporter in EU27:
        hhi = cb_results.get(reporter)
        bt = bilateral_reporter_totals.get(reporter, 0.0)
        modes_str = ", ".join(
            f"{m}={bilateral_mode_totals.get((reporter, m), 0.0):,.0f}"
            for m in CHANNEL_B_MODES
            if bilateral_mode_totals.get((reporter, m), 0.0) > 0
        )
        hhi_str = f"{hhi:.6f}" if hhi is not None else "N/A"
        print(f"    {reporter}: HHI={hhi_str}  bilateral_t={bt:,.0f}  ({modes_str})")

    # ── 7. Cross-Channel Aggregation ─────────────────────────
    print()
    print("STAGE 6: Cross-Channel Aggregation")
    print("-" * 72)

    score_file = OUT_DIR / "logistics_freight_axis_score.csv"

    results = []
    for reporter in EU27:
        c_a = ca_results[reporter]["hhi"]
        w_a = ca_results[reporter]["weight"]
        modes_used = ca_results[reporter]["modes_used"]

        c_b = cb_results.get(reporter)
        w_b = bilateral_reporter_totals.get(reporter, 0.0)

        # Validate
        for label, val in [("C_A", c_a)]:
            if math.isnan(val) or math.isinf(val) or val < 0.0 or val > 1.0 + SHARE_TOLERANCE:
                print(f"FATAL: {label} invalid for {reporter}: {val}", file=sys.stderr)
                sys.exit(1)

        if c_b is not None:
            if math.isnan(c_b) or math.isinf(c_b) or c_b < 0.0 or c_b > 1.0 + SHARE_TOLERANCE:
                print(f"FATAL: C_B invalid for {reporter}: {c_b}", file=sys.stderr)
                sys.exit(1)

        has_a = w_a > 0.0
        has_b = c_b is not None and w_b > 0.0

        if has_a and has_b:
            score = (c_a * w_a + c_b * w_b) / (w_a + w_b)
            case = "BOTH"
        elif has_a and not has_b:
            score = c_a
            case = "A_ONLY"
        elif has_b and not has_a:
            score = c_b
            case = "B_ONLY"
        else:
            print(f"FATAL: both channels empty for {reporter}", file=sys.stderr)
            sys.exit(1)

        if math.isnan(score) or math.isinf(score) or score < 0.0 or score > 1.0 + SHARE_TOLERANCE:
            print(f"FATAL: score invalid for {reporter}: {score}", file=sys.stderr)
            sys.exit(1)
        score = min(score, 1.0)

        results.append({
            "reporter": reporter,
            "axis6_logistics_score": score,
            "channel_a_mode_hhi": c_a,
            "channel_b_partner_hhi": c_b if c_b is not None else 0.0,
            "weight_a_tonnes": w_a,
            "weight_b_tonnes": w_b,
            "modes_used": modes_used,
            "aggregation_case": case,
        })

    # Write final scores
    with open(score_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "reporter", "axis6_logistics_score", "channel_a_mode_hhi",
            "channel_b_partner_hhi", "weight_a_tonnes", "weight_b_tonnes",
            "modes_used", "aggregation_case",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "reporter": r["reporter"],
                "axis6_logistics_score": f"{r['axis6_logistics_score']:.10f}",
                "channel_a_mode_hhi": f"{r['channel_a_mode_hhi']:.10f}",
                "channel_b_partner_hhi": f"{r['channel_b_partner_hhi']:.10f}",
                "weight_a_tonnes": f"{r['weight_a_tonnes']:.1f}",
                "weight_b_tonnes": f"{r['weight_b_tonnes']:.1f}",
                "modes_used": r["modes_used"],
                "aggregation_case": r["aggregation_case"],
            })

    # ── 8. Validation & Audit ────────────────────────────────
    print()
    print("=" * 72)
    print("VALIDATION")
    print("=" * 72)
    print()

    # A. Row count
    if len(results) != 27:
        print(f"FATAL: expected 27 rows, got {len(results)}", file=sys.stderr)
        sys.exit(1)
    print(f"A. Row count: {len(results)} — PASS")

    # B. Aggregation cases
    cases = defaultdict(int)
    for r in results:
        cases[r["aggregation_case"]] += 1
    print(f"B. Aggregation cases: {dict(cases)}")

    # C. Score bounds
    scores = [r["axis6_logistics_score"] for r in results]
    s_min, s_max, s_mean = min(scores), max(scores), sum(scores) / len(scores)
    print(f"C. Score range: [{s_min:.6f}, {s_max:.6f}], mean={s_mean:.6f}")
    for r in results:
        s = r["axis6_logistics_score"]
        if s < 0.0 or s > 1.0:
            print(f"FATAL: score out of [0,1] for {r['reporter']}: {s}", file=sys.stderr)
            sys.exit(1)
    print(f"   All scores in [0, 1]: PASS")

    # D. Data limitation documentation
    print()
    print("D. Data limitations")
    print("   - IWW bilateral data: NOT AVAILABLE (Eurostat iww_go_atygo")
    print("     has no partner dimension). Aggregate tonnage used for")
    print("     Channel A. Excluded from Channel B. (§6.3)")
    print("   - Maritime bilateral data: NOT AVAILABLE via Eurostat API.")
    print("     mar_go_am discontinued. mar_go_am_pt exists but only")
    print("     serves one country per API request (port-level).")
    print("     Aggregate tonnage from mar_sg_am_cw used for Channel A.")
    print("     Excluded from Channel B (same treatment as IWW).")
    a_only = [r["reporter"] for r in results if r["aggregation_case"] == "A_ONLY"]
    if a_only:
        print(f"   - A_ONLY reporters (no bilateral data): {a_only}")
    print()

    # E. Ranked table
    print("-" * 72)
    print(f"  {'#':>3s} {'Reporter':<8s} {'Axis6':>10s} "
          f"{'Ch.A':>10s} {'Ch.B':>10s} "
          f"{'W_A':>14s} {'W_B':>14s} "
          f"{'M':>2s} {'Case':<8s}")
    print("  " + "-" * 70)

    ranked = sorted(results, key=lambda r: -r["axis6_logistics_score"])
    for rank, r in enumerate(ranked, 1):
        print(f"  {rank:>3d} {r['reporter']:<8s} "
              f"{r['axis6_logistics_score']:>10.6f} "
              f"{r['channel_a_mode_hhi']:>10.6f} "
              f"{r['channel_b_partner_hhi']:>10.6f} "
              f"{r['weight_a_tonnes']:>14,.1f} "
              f"{r['weight_b_tonnes']:>14,.1f} "
              f"{r['modes_used']:>2d} "
              f"{r['aggregation_case']:<8s}")

    print()
    print("=" * 72)
    print("Axis 6 — Logistics / Freight Dependency: PASS")
    print("=" * 72)
    print()
    print(f"  Output:      {score_file}")
    print(f"  Reporters:   {len(results)}")
    print(f"  Score range: [{s_min:.6f}, {s_max:.6f}]")
    print(f"  Mean:        {s_mean:.6f}")
    print()

    # Write audit waterfall
    waterfall_file = AUDIT_DIR / "logistics_compute_waterfall.csv"
    with open(waterfall_file, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["bilateral_rows_total", len(bilateral_rows)])
        w.writerow(["bilateral_reporters", len(bilateral_reporters)])
        w.writerow(["iww_reporters", len(iww_totals)])
        w.writerow(["maritime_reporters", len(maritime_totals)])
        w.writerow(["channel_a_reporters", len(ca_results)])
        w.writerow(["channel_b_reporters", len(cb_valid)])
        w.writerow(["axis6_reporters", len(results)])
        w.writerow(["score_min", f"{s_min:.10f}"])
        w.writerow(["score_max", f"{s_max:.10f}"])
        w.writerow(["score_mean", f"{s_mean:.10f}"])
        w.writerow(["cases_BOTH", cases.get("BOTH", 0)])
        w.writerow(["cases_A_ONLY", cases.get("A_ONLY", 0)])
        w.writerow(["data_limitation", "maritime+iww excluded from Channel B"])

    print(f"  Waterfall:   {waterfall_file}")
    print()


if __name__ == "__main__":
    main()
