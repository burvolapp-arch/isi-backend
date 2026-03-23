"""ISI v0.1 — Energy Axis Scope Enforcement (EU-27, 2024)"""

import csv
from pathlib import Path

INPUT_ENERGY = Path("data/processed/energy/energy_dependency_2024.csv")
INPUT_SCOPE = Path("data/scopes/energy_eurostat_scope_eu27.csv")
OUTPUT_DIR = Path("data/processed/energy")
OUTPUT_EU27 = OUTPUT_DIR / "energy_dependency_2024_eu27.csv"
OUTPUT_AUDIT = OUTPUT_DIR / "energy_dependency_2024_scope_audit.csv"


def load_scope(scope_path):
    geo_set = set()
    with open(scope_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            geo_set.add(row["geo"])
    return geo_set


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    eu27_geos = load_scope(INPUT_SCOPE)

    rows = []
    with open(INPUT_ENERGY, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    included = []
    audit = []

    for row in sorted(rows, key=lambda r: r["geo"]):
        geo = row["geo"]
        if geo in eu27_geos:
            included.append(row)
            audit.append({"geo": geo, "status": "INCLUDED_EU27"})
        else:
            audit.append({"geo": geo, "status": "EXCLUDED_NOT_EU27"})

    with open(OUTPUT_EU27, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["geo", "energy_dependency"])
        writer.writeheader()
        for row in included:
            writer.writerow(row)

    print(f"EU-27 filtered: {len(included)} rows → {OUTPUT_EU27}")

    with open(OUTPUT_AUDIT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["geo", "status"])
        writer.writeheader()
        for row in audit:
            writer.writerow(row)

    print(f"Scope audit: {len(audit)} rows → {OUTPUT_AUDIT}")


if __name__ == "__main__":
    main()
