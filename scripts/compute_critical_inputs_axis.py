#!/usr/bin/env python3
"""ISI v0.1 — Axis 5: Critical Inputs / Raw Materials Dependency
Full Computation Script (Channel A + Channel B + Aggregation)

Reads the filtered bilateral Comext CN8 trade data and the CN8-to-
material-group mapping, computes both channels, and produces all
output CSVs.

Input:
  data/raw/critical_inputs/eu_comext_critical_inputs_cn8_2022_2024.csv
  Schema: DECLARANT_ISO,PARTNER_ISO,PRODUCT_NC,FLOW,PERIOD,VALUE_IN_EUROS

  docs/mappings/critical_materials_cn8_mapping_v01.csv
  Schema: cn8_code,material_group,...

Outputs:
  data/processed/critical_inputs/critical_inputs_channel_a_shares.csv
  Schema: geo,partner,share

  data/processed/critical_inputs/critical_inputs_channel_a_concentration.csv
  Schema: geo,concentration

  data/processed/critical_inputs/critical_inputs_channel_a_volumes.csv
  Schema: geo,total_value

  data/processed/critical_inputs/critical_inputs_channel_b_group_shares.csv
  Schema: geo,material_group,partner,share

  data/processed/critical_inputs/critical_inputs_channel_b_group_concentration.csv
  Schema: geo,material_group,concentration,group_value

  data/processed/critical_inputs/critical_inputs_channel_b_concentration.csv
  Schema: geo,concentration

  data/processed/critical_inputs/critical_inputs_channel_b_volumes.csv
  Schema: geo,total_value

  data/processed/critical_inputs/critical_inputs_dependency_2024_eu27.csv
  Schema: geo,critical_inputs_dependency

  data/processed/critical_inputs/critical_inputs_dependency_2024_eu27_audit.csv
  Schema: geo,channel_a_concentration,channel_a_volume,channel_b_concentration,channel_b_volume,critical_inputs_dependency,score_basis

Methodology (locked, §§5-8 of critical_inputs_axis_v01_frozen.md):

  Channel A — Aggregate Supplier Concentration:
    V_{i,j}^{(A)} = SUM over all CN8 codes and years of import value
    s_{i,j}^{(A)} = V_{i,j}^{(A)} / SUM_j V_{i,j}^{(A)}
    C_i^{(A)} = SUM_j (s_{i,j}^{(A)})^2

  Channel B — Material-Group Weighted Concentration:
    For each group k:
      V_{i,j}^{(B,k)} = SUM over CN8 codes in group k and all years
      s_{i,j}^{(B,k)} = V_{i,j}^{(B,k)} / SUM_j V_{i,j}^{(B,k)}
      C_i^{(B,k)} = SUM_j (s_{i,j}^{(B,k)})^2
      V_i^{(k)} = SUM_j V_{i,j}^{(B,k)}
    C_i^{(B)} = SUM_k [C_i^{(B,k)} * V_i^{(k)}] / SUM_k V_i^{(k)}

  Cross-channel aggregation:
    M_i = 0.5 * C_i^{(A)} + 0.5 * C_i^{(B)}
    (W_A = W_B by construction, so volume-weighted = arithmetic mean)

Exactly 27 rows (EU-27). No NaN. No negatives. Score in [0, 1].

Task: ISI-CRIT-COMPUTE
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Inputs ───────────────────────────────────────────────────
RAW_FILE = (
    PROJECT_ROOT / "data" / "raw" / "critical_inputs"
    / "eu_comext_critical_inputs_cn8_2022_2024.csv"
)
MAPPING_FILE = (
    PROJECT_ROOT / "docs" / "mappings"
    / "critical_materials_cn8_mapping_v01.csv"
)

# ── Output directory ─────────────────────────────────────────
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "critical_inputs"

# ── EU-27 ────────────────────────────────────────────────────
EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])
EU27_SET = frozenset(EU27)

# ── Material groups (frozen) ────────────────────────────────
MATERIAL_GROUPS = [
    "rare_earths",
    "battery_metals",
    "defense_industrial_metals",
    "semiconductor_inputs",
    "fertilizer_chokepoints",
]

# ── Fatal error ──────────────────────────────────────────────
def fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


# ── Load CN8 mapping ────────────────────────────────────────
def load_cn8_mapping() -> dict[str, str]:
    """Returns {cn8_code: material_group}."""
    if not MAPPING_FILE.is_file():
        fatal(f"Mapping file not found: {MAPPING_FILE}")
    mapping: dict[str, str] = {}
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["cn8_code"].strip()
            group = row["material_group"].strip()
            if group not in MATERIAL_GROUPS:
                fatal(f"Unknown material group '{group}' for CN8 {code}")
            mapping[code] = group
    if len(mapping) != 66:
        fatal(f"Expected 66 CN8 codes in mapping, got {len(mapping)}")
    return mapping


# ── Load raw bilateral data ─────────────────────────────────
def load_bilateral_data(cn8_map: dict[str, str]) -> list[dict]:
    """
    Load and validate raw bilateral trade data.
    Returns list of {reporter, partner, cn8, group, value} dicts.
    """
    if not RAW_FILE.is_file():
        fatal(f"Raw data file not found: {RAW_FILE}")

    rows = []
    with open(RAW_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            reporter = row["DECLARANT_ISO"].strip()
            partner = row["PARTNER_ISO"].strip()
            cn8 = row["PRODUCT_NC"].strip()
            value = float(row["VALUE_IN_EUROS"])

            # Only EU-27 reporters
            if reporter not in EU27_SET:
                continue

            # Only CN8 codes in our universe
            if cn8 not in cn8_map:
                continue

            # Skip zero values
            if value <= 0:
                continue

            rows.append({
                "reporter": reporter,
                "partner": partner,
                "cn8": cn8,
                "group": cn8_map[cn8],
                "value": value,
            })

    return rows


# ── Channel A: Aggregate Supplier Concentration ─────────────
def compute_channel_a(data: list[dict]) -> tuple[
    dict[str, float],   # {geo: hhi}
    dict[str, float],   # {geo: total_value}
    dict[str, list],    # {geo: [{partner, share}, ...]}
]:
    """
    Channel A: pool ALL CN8 codes, compute supplier shares and HHI.
    """
    # Accumulate V_{i,j} across all products and years
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in data:
        totals[row["reporter"]][row["partner"]] += row["value"]

    concentrations: dict[str, float] = {}
    volumes: dict[str, float] = {}
    shares_by_geo: dict[str, list] = {}

    for geo in EU27:
        partner_vals = totals.get(geo, {})
        total = sum(partner_vals.values())

        if total == 0:
            fatal(f"Channel A: zero total import value for {geo}")

        volumes[geo] = total

        # Compute shares and HHI
        shares = []
        hhi = 0.0
        for partner, val in partner_vals.items():
            s = val / total
            hhi += s * s
            shares.append({"partner": partner, "share": s})

        # Validate
        share_sum = sum(x["share"] for x in shares)
        if abs(share_sum - 1.0) > 1e-9:
            fatal(f"Channel A: shares for {geo} sum to {share_sum}")
        if hhi < 0.0 or hhi > 1.0 + 1e-9:
            fatal(f"Channel A: HHI for {geo} = {hhi}, out of [0,1]")

        concentrations[geo] = min(hhi, 1.0)
        shares.sort(key=lambda x: -x["share"])
        shares_by_geo[geo] = shares

    return concentrations, volumes, shares_by_geo


# ── Channel B: Material-Group Weighted Concentration ─────────
def compute_channel_b(data: list[dict]) -> tuple[
    dict[str, float],   # {geo: weighted_hhi}
    dict[str, float],   # {geo: total_value}
    dict[str, dict],    # {geo: {group: {concentration, volume}}}
]:
    """
    Channel B: compute per-group supplier HHI, then aggregate
    across groups using import-value weights.
    """
    # Accumulate V_{i,j}^{(B,k)} per (reporter, group, partner)
    group_partner_vals: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )

    for row in data:
        group_partner_vals[row["reporter"]][row["group"]][row["partner"]] += row["value"]

    concentrations: dict[str, float] = {}
    volumes: dict[str, float] = {}
    group_details: dict[str, dict] = {}

    for geo in EU27:
        geo_groups = group_partner_vals.get(geo, {})

        weighted_sum = 0.0
        total_group_value = 0.0
        geo_group_detail: dict[str, dict] = {}

        for group_name in MATERIAL_GROUPS:
            partner_vals = geo_groups.get(group_name, {})
            group_total = sum(partner_vals.values())

            if group_total == 0:
                # Group excluded from weighted average (methodology §7.2)
                continue

            # Compute group-level HHI
            group_hhi = 0.0
            for partner, val in partner_vals.items():
                s = val / group_total
                group_hhi += s * s

            if group_hhi < 0.0 or group_hhi > 1.0 + 1e-9:
                fatal(f"Channel B: group HHI for {geo}/{group_name} = {group_hhi}")

            group_hhi = min(group_hhi, 1.0)
            weighted_sum += group_hhi * group_total
            total_group_value += group_total

            geo_group_detail[group_name] = {
                "concentration": group_hhi,
                "volume": group_total,
            }

        if total_group_value == 0:
            fatal(f"Channel B: zero total group value for {geo}")

        weighted_hhi = weighted_sum / total_group_value

        if weighted_hhi < 0.0 or weighted_hhi > 1.0 + 1e-9:
            fatal(f"Channel B: weighted HHI for {geo} = {weighted_hhi}")

        concentrations[geo] = min(weighted_hhi, 1.0)
        volumes[geo] = total_group_value
        group_details[geo] = geo_group_detail

    return concentrations, volumes, group_details


# ── Cross-channel aggregation ────────────────────────────────
def aggregate_channels(
    ch_a_conc: dict[str, float],
    ch_a_vol: dict[str, float],
    ch_b_conc: dict[str, float],
    ch_b_vol: dict[str, float],
) -> dict[str, dict]:
    """
    M_i = (C_A * W_A + C_B * W_B) / (W_A + W_B)
    By construction W_A = W_B, so M_i = 0.5 * C_A + 0.5 * C_B.
    """
    results: dict[str, dict] = {}

    for geo in EU27:
        ca = ch_a_conc[geo]
        wa = ch_a_vol[geo]
        cb = ch_b_conc[geo]
        wb = ch_b_vol[geo]

        if wa + wb == 0:
            fatal(f"Aggregation: zero total weight for {geo}")

        score = (ca * wa + cb * wb) / (wa + wb)

        if score < 0.0 or score > 1.0 + 1e-9:
            fatal(f"Aggregation: score for {geo} = {score}, out of [0,1]")

        # Determine basis
        if wa > 0 and wb > 0:
            basis = "BOTH"
        elif wa > 0:
            basis = "A_ONLY"
        elif wb > 0:
            basis = "B_ONLY"
        else:
            basis = "NONE"

        results[geo] = {
            "channel_a_concentration": ca,
            "channel_a_volume": wa,
            "channel_b_concentration": cb,
            "channel_b_volume": wb,
            "score": min(score, 1.0),
            "basis": basis,
        }

    return results


# ── Write CSV helper ─────────────────────────────────────────
def write_csv(filepath: Path, fieldnames: list[str], rows: list[dict]) -> None:
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Main ─────────────────────────────────────────────────────
def main() -> None:
    print("=" * 64)
    print("ISI v0.1 — Axis 5: Critical Inputs Compute Pipeline")
    print("=" * 64)
    print()

    # Load mapping
    cn8_map = load_cn8_mapping()
    print(f"Mapping: {len(cn8_map)} CN8 codes in {len(set(cn8_map.values()))} groups")

    # Load bilateral data
    data = load_bilateral_data(cn8_map)
    print(f"Bilateral rows loaded: {len(data):,}")
    reporters = sorted(set(r["reporter"] for r in data))
    print(f"Reporters: {len(reporters)}")
    if set(reporters) != EU27_SET:
        missing = EU27_SET - set(reporters)
        fatal(f"Missing EU-27 reporters: {sorted(missing)}")
    print()

    # ── Channel A ────────────────────────────────────────────
    print("Computing Channel A (aggregate supplier concentration)...")
    ch_a_conc, ch_a_vol, ch_a_shares = compute_channel_a(data)
    print(f"  HHI range: [{min(ch_a_conc.values()):.6f}, {max(ch_a_conc.values()):.6f}]")
    print()

    # Write Channel A outputs
    # Shares
    shares_rows = []
    for geo in EU27:
        for entry in ch_a_shares[geo]:
            shares_rows.append({
                "geo": geo,
                "partner": entry["partner"],
                "share": f"{entry['share']:.12f}",
            })
    write_csv(
        OUT_DIR / "critical_inputs_channel_a_shares.csv",
        ["geo", "partner", "share"],
        shares_rows,
    )
    print(f"  Wrote: critical_inputs_channel_a_shares.csv ({len(shares_rows)} rows)")

    # Concentration
    conc_rows = [
        {"geo": geo, "concentration": f"{ch_a_conc[geo]:.12f}"}
        for geo in EU27
    ]
    write_csv(
        OUT_DIR / "critical_inputs_channel_a_concentration.csv",
        ["geo", "concentration"],
        conc_rows,
    )
    print(f"  Wrote: critical_inputs_channel_a_concentration.csv ({len(conc_rows)} rows)")

    # Volumes
    vol_rows = [
        {"geo": geo, "total_value": f"{ch_a_vol[geo]:.2f}"}
        for geo in EU27
    ]
    write_csv(
        OUT_DIR / "critical_inputs_channel_a_volumes.csv",
        ["geo", "total_value"],
        vol_rows,
    )
    print(f"  Wrote: critical_inputs_channel_a_volumes.csv ({len(vol_rows)} rows)")
    print()

    # ── Channel B ────────────────────────────────────────────
    print("Computing Channel B (material-group weighted concentration)...")
    ch_b_conc, ch_b_vol, ch_b_groups = compute_channel_b(data)
    print(f"  HHI range: [{min(ch_b_conc.values()):.6f}, {max(ch_b_conc.values()):.6f}]")
    print()

    # Write Channel B group shares
    group_shares_rows = []
    for geo in EU27:
        geo_groups = defaultdict(lambda: defaultdict(float))
        for row in data:
            if row["reporter"] == geo:
                geo_groups[row["group"]][row["partner"]] += row["value"]
        for group_name in MATERIAL_GROUPS:
            partner_vals = geo_groups.get(group_name, {})
            group_total = sum(partner_vals.values())
            if group_total == 0:
                continue
            for partner, val in sorted(partner_vals.items(),
                                        key=lambda x: -x[1]):
                s = val / group_total
                if s > 0:
                    group_shares_rows.append({
                        "geo": geo,
                        "material_group": group_name,
                        "partner": partner,
                        "share": f"{s:.12f}",
                    })
    write_csv(
        OUT_DIR / "critical_inputs_channel_b_group_shares.csv",
        ["geo", "material_group", "partner", "share"],
        group_shares_rows,
    )
    print(f"  Wrote: critical_inputs_channel_b_group_shares.csv ({len(group_shares_rows)} rows)")

    # Group concentration
    group_conc_rows = []
    for geo in EU27:
        for group_name in MATERIAL_GROUPS:
            detail = ch_b_groups[geo].get(group_name)
            if detail is None:
                continue
            group_conc_rows.append({
                "geo": geo,
                "material_group": group_name,
                "concentration": f"{detail['concentration']:.12f}",
                "group_value": f"{detail['volume']:.2f}",
            })
    write_csv(
        OUT_DIR / "critical_inputs_channel_b_group_concentration.csv",
        ["geo", "material_group", "concentration", "group_value"],
        group_conc_rows,
    )
    print(f"  Wrote: critical_inputs_channel_b_group_concentration.csv ({len(group_conc_rows)} rows)")

    # Channel B concentration (aggregate)
    b_conc_rows = [
        {"geo": geo, "concentration": f"{ch_b_conc[geo]:.12f}"}
        for geo in EU27
    ]
    write_csv(
        OUT_DIR / "critical_inputs_channel_b_concentration.csv",
        ["geo", "concentration"],
        b_conc_rows,
    )
    print(f"  Wrote: critical_inputs_channel_b_concentration.csv ({len(b_conc_rows)} rows)")

    # Channel B volumes
    b_vol_rows = [
        {"geo": geo, "total_value": f"{ch_b_vol[geo]:.2f}"}
        for geo in EU27
    ]
    write_csv(
        OUT_DIR / "critical_inputs_channel_b_volumes.csv",
        ["geo", "total_value"],
        b_vol_rows,
    )
    print(f"  Wrote: critical_inputs_channel_b_volumes.csv ({len(b_vol_rows)} rows)")
    print()

    # ── Cross-channel aggregation ────────────────────────────
    print("Computing cross-channel aggregation...")
    results = aggregate_channels(ch_a_conc, ch_a_vol, ch_b_conc, ch_b_vol)

    # Verify W_A = W_B equivalence
    for geo in EU27:
        wa = ch_a_vol[geo]
        wb = ch_b_vol[geo]
        if abs(wa - wb) > 0.01:
            print(f"  WARNING: W_A != W_B for {geo}: {wa:.2f} vs {wb:.2f}")

    # Final scores
    final_rows = [
        {"geo": geo, "critical_inputs_dependency": f"{results[geo]['score']:.12f}"}
        for geo in EU27
    ]
    write_csv(
        OUT_DIR / "critical_inputs_dependency_2024_eu27.csv",
        ["geo", "critical_inputs_dependency"],
        final_rows,
    )
    print(f"  Wrote: critical_inputs_dependency_2024_eu27.csv ({len(final_rows)} rows)")

    # Audit file
    audit_rows = []
    for geo in EU27:
        r = results[geo]
        audit_rows.append({
            "geo": geo,
            "channel_a_concentration": f"{r['channel_a_concentration']:.12f}",
            "channel_a_volume": f"{r['channel_a_volume']:.2f}",
            "channel_b_concentration": f"{r['channel_b_concentration']:.12f}",
            "channel_b_volume": f"{r['channel_b_volume']:.2f}",
            "critical_inputs_dependency": f"{r['score']:.12f}",
            "score_basis": r["basis"],
        })
    write_csv(
        OUT_DIR / "critical_inputs_dependency_2024_eu27_audit.csv",
        ["geo", "channel_a_concentration", "channel_a_volume",
         "channel_b_concentration", "channel_b_volume",
         "critical_inputs_dependency", "score_basis"],
        audit_rows,
    )
    print(f"  Wrote: critical_inputs_dependency_2024_eu27_audit.csv ({len(audit_rows)} rows)")
    print()

    # ── Summary ──────────────────────────────────────────────
    print("=" * 64)
    print("AXIS 5 SUMMARY")
    print("=" * 64)

    scores = [(geo, results[geo]["score"]) for geo in EU27]
    scores.sort(key=lambda x: -x[1])

    print(f"  Countries scored: {len(scores)}/27")
    print(f"  Min:  {scores[-1][1]:.6f} ({scores[-1][0]})")
    print(f"  Max:  {scores[0][1]:.6f} ({scores[0][0]})")
    mean_score = sum(s for _, s in scores) / len(scores)
    print(f"  Mean: {mean_score:.6f}")
    print()

    for geo, s in scores:
        ca = results[geo]["channel_a_concentration"]
        cb = results[geo]["channel_b_concentration"]
        print(f"  {geo}  {s:.6f}  (A={ca:.4f}  B={cb:.4f}  {results[geo]['basis']})")

    print()

    # Validation
    fail = False
    for geo in EU27:
        s = results[geo]["score"]
        if s < 0.0 or s > 1.0:
            print(f"  FAIL: {geo} score {s} out of [0,1]")
            fail = True

    if len(scores) != 27:
        print(f"  FAIL: {len(scores)} countries, expected 27")
        fail = True

    if fail:
        fatal("Validation failed")
    else:
        print("  PASS: all 27 countries, all scores in [0,1]")
        print()
        print("Axis 5 computation complete.")


if __name__ == "__main__":
    main()
