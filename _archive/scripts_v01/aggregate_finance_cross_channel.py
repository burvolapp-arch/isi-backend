"""ISI v0.1 — Financial Dependency Axis Cross-Channel Aggregation (2024)

Implements methodology Section 8:

  F_i = (C_i^(A) * W_i^(A) + C_i^(B) * W_i^(B))
        / (W_i^(A) + W_i^(B))

Inputs (Channel A — BIS LBS, ISO-2 country codes):
  data/processed/finance/bis_lbs_inward_2024_concentration.csv
  data/processed/finance/bis_lbs_inward_2024_volumes.csv

Inputs (Channel B — IMF CPIS, ISO-3 country codes):
  data/processed/finance/cpis_debt_inward_2024_concentration.csv
  data/processed/finance/cpis_debt_inward_2024_volumes.csv

Outputs:
  data/processed/finance/finance_dependency_2024_eu27.csv
  data/processed/finance/finance_dependency_2024_eu27_audit.csv

Output is EU-27 only.  Uses Eurostat geo codes (ISO-2,
with EL for Greece) in the final output to match the
energy axis convention.
"""

import csv
from pathlib import Path

# ── paths ────────────────────────────────────────────────

INPUT_DIR = Path("data/processed/finance")

CHA_CONC = INPUT_DIR / "bis_lbs_inward_2024_concentration.csv"
CHA_VOL = INPUT_DIR / "bis_lbs_inward_2024_volumes.csv"
CHB_CONC = INPUT_DIR / "cpis_debt_inward_2024_concentration.csv"
CHB_VOL = INPUT_DIR / "cpis_debt_inward_2024_volumes.csv"

OUTPUT_DIR = INPUT_DIR
OUTPUT_FILE = OUTPUT_DIR / "finance_dependency_2024_eu27.csv"
OUTPUT_AUDIT = OUTPUT_DIR / "finance_dependency_2024_eu27_audit.csv"

# ── EU-27 mappings ───────────────────────────────────────
# Canonical key: Eurostat geo code (ISO-2, EL for Greece)
# BIS uses standard ISO-2 (GR for Greece)
# CPIS uses ISO-3

EU27_EUROSTAT = [
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
]

# BIS ISO-2 → Eurostat geo
BIS_TO_EUROSTAT = {
    "AT": "AT", "BE": "BE", "BG": "BG", "CY": "CY",
    "CZ": "CZ", "DE": "DE", "DK": "DK", "EE": "EE",
    "ES": "ES", "FI": "FI", "FR": "FR", "GR": "EL",
    "HR": "HR", "HU": "HU", "IE": "IE", "IT": "IT",
    "LT": "LT", "LU": "LU", "LV": "LV", "MT": "MT",
    "NL": "NL", "PL": "PL", "PT": "PT", "RO": "RO",
    "SE": "SE", "SI": "SI", "SK": "SK",
}
EUROSTAT_TO_BIS = {v: k for k, v in BIS_TO_EUROSTAT.items()}

# CPIS ISO-3 → Eurostat geo
CPIS_TO_EUROSTAT = {
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "CYP": "CY",
    "CZE": "CZ", "DEU": "DE", "DNK": "DK", "EST": "EE",
    "ESP": "ES", "FIN": "FI", "FRA": "FR", "GRC": "EL",
    "HRV": "HR", "HUN": "HU", "IRL": "IE", "ITA": "IT",
    "LTU": "LT", "LUX": "LU", "LVA": "LV", "MLT": "MT",
    "NLD": "NL", "POL": "PL", "PRT": "PT", "ROU": "RO",
    "SWE": "SE", "SVN": "SI", "SVK": "SK",
}
EUROSTAT_TO_CPIS = {v: k for k, v in CPIS_TO_EUROSTAT.items()}

# ── loaders ──────────────────────────────────────────────


def load_bis_dict(path, value_col):
    """Load BIS CSV into {eurostat_geo: float} for EU-27 only."""
    out = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bis_code = row["counterparty_country"]
            eurostat = BIS_TO_EUROSTAT.get(bis_code)
            if eurostat is None:
                continue
            out[eurostat] = float(row[value_col])
    return out


def load_cpis_dict(path, value_col):
    """Load CPIS CSV into {eurostat_geo: float} for EU-27 only."""
    out = {}
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cpis_code = row["reference_country"]
            eurostat = CPIS_TO_EUROSTAT.get(cpis_code)
            if eurostat is None:
                continue
            out[eurostat] = float(row[value_col])
    return out


# ── main ─────────────────────────────────────────────────


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load all four inputs (EU-27 only)
    c_a = load_bis_dict(CHA_CONC, "concentration")
    w_a = load_bis_dict(CHA_VOL, "total_value_usd_mn")
    c_b = load_cpis_dict(CHB_CONC, "concentration")
    w_b = load_cpis_dict(CHB_VOL, "total_value_usd_mn")

    print(f"Channel A: {len(c_a)} EU-27 countries loaded")
    print(f"Channel B: {len(c_b)} EU-27 countries loaded")

    # Aggregate per Section 8
    results = []
    audit_rows = []

    for geo in sorted(EU27_EUROSTAT):
        ca = c_a.get(geo)
        wa = w_a.get(geo, 0.0)
        cb = c_b.get(geo)
        wb = w_b.get(geo, 0.0)

        has_a = ca is not None and wa > 0.0
        has_b = cb is not None and wb > 0.0

        if has_a and has_b:
            f_i = (ca * wa + cb * wb) / (wa + wb)
            source = "BOTH"
        elif has_a and not has_b:
            f_i = ca
            source = "A_ONLY"
        elif not has_a and has_b:
            f_i = cb
            source = "B_ONLY"
        else:
            # Both missing or zero volume
            f_i = None
            source = "OMITTED"

        audit_rows.append({
            "geo": geo,
            "channel_a_concentration": f"{ca:.10f}" if ca is not None else "",
            "channel_a_volume_usd_mn": f"{wa:.3f}" if has_a else "",
            "channel_b_concentration": f"{cb:.10f}" if cb is not None else "",
            "channel_b_volume_usd_mn": f"{wb:.3f}" if has_b else "",
            "finance_dependency": f"{f_i:.10f}" if f_i is not None else "",
            "source": source,
        })

        if f_i is not None:
            # Sanity check
            assert 0.0 <= f_i <= 1.0, (
                f"F_i out of range for {geo}: {f_i}"
            )
            results.append({"geo": geo, "finance_dependency": f_i})

    # Write main output
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["geo", "finance_dependency"]
        )
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"\nFinance dependency: {len(results)} EU-27 rows → {OUTPUT_FILE}")

    # Write audit
    audit_fields = [
        "geo", "channel_a_concentration", "channel_a_volume_usd_mn",
        "channel_b_concentration", "channel_b_volume_usd_mn",
        "finance_dependency", "source",
    ]
    with open(OUTPUT_AUDIT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=audit_fields)
        writer.writeheader()
        for row in audit_rows:
            writer.writerow(row)

    print(f"Audit: {len(audit_rows)} rows → {OUTPUT_AUDIT}")

    # Summary
    both = sum(1 for r in audit_rows if r["source"] == "BOTH")
    a_only = sum(1 for r in audit_rows if r["source"] == "A_ONLY")
    b_only = sum(1 for r in audit_rows if r["source"] == "B_ONLY")
    omitted = sum(1 for r in audit_rows if r["source"] == "OMITTED")

    print(f"\nBreakdown: BOTH={both}  A_ONLY={a_only}  "
          f"B_ONLY={b_only}  OMITTED={omitted}")

    if results:
        scores = [r["finance_dependency"] for r in results]
        print(f"Score range: [{min(scores):.6f}, {max(scores):.6f}]")

    # Print full table
    print(f"\n{'Geo':>4}  {'Ch.A HHI':>10}  {'Ch.A Vol':>14}  "
          f"{'Ch.B HHI':>10}  {'Ch.B Vol':>14}  "
          f"{'F_i':>10}  {'Source':>8}")
    print("-" * 82)
    for row in audit_rows:
        ca_str = row["channel_a_concentration"][:8] if row["channel_a_concentration"] else "   —"
        wa_str = row["channel_a_volume_usd_mn"][:12] if row["channel_a_volume_usd_mn"] else "      —"
        cb_str = row["channel_b_concentration"][:8] if row["channel_b_concentration"] else "   —"
        wb_str = row["channel_b_volume_usd_mn"][:12] if row["channel_b_volume_usd_mn"] else "      —"
        fi_str = row["finance_dependency"][:8] if row["finance_dependency"] else "   —"
        print(f"{row['geo']:>4}  {ca_str:>10}  {wa_str:>14}  "
              f"{cb_str:>10}  {wb_str:>14}  "
              f"{fi_str:>10}  {row['source']:>8}")


if __name__ == "__main__":
    main()
