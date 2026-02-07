"""ISI v0.1 — Energy Dependency Axis Score (2024)"""

import csv
from collections import defaultdict
from pathlib import Path

INPUT_DIR = Path("data/processed/energy")
OUTPUT_DIR = Path("data/processed/energy")

FUEL_CONFIGS = [
    ("gas", "nrg_ti_gas_2024_fuel_concentration.csv", "nrg_ti_gas_2024_flat.csv"),
    ("oil", "nrg_ti_oil_2024_fuel_concentration.csv", "nrg_ti_oil_2024_flat.csv"),
    ("solid_fossil", "nrg_ti_sff_2024_fuel_concentration.csv", "nrg_ti_sff_2024_flat.csv"),
]

OUTPUT_FILE = OUTPUT_DIR / "energy_dependency_2024.csv"

CSV_COLUMNS = [
    "geo",
    "energy_dependency",
]


def load_fuel_concentrations(concentration_path):
    concentrations = {}

    with open(concentration_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            c_str = row["concentration"]
            if c_str is None or c_str.strip() == "":
                continue
            try:
                c = float(c_str)
            except ValueError:
                continue
            concentrations[row["geo"]] = c

    return concentrations


def load_geo_total_volumes(flat_path):
    volumes = defaultdict(float)

    with open(flat_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            val_str = row["value"]
            if val_str is None or val_str.strip() == "":
                continue
            try:
                val = float(val_str)
            except ValueError:
                continue
            volumes[row["geo"]] += val

    return volumes


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    geo_numerator = defaultdict(float)
    geo_denominator = defaultdict(float)

    for fuel, conc_filename, flat_filename in FUEL_CONFIGS:
        concentrations = load_fuel_concentrations(INPUT_DIR / conc_filename)
        volumes = load_geo_total_volumes(INPUT_DIR / flat_filename)

        for geo, c in concentrations.items():
            v = volumes.get(geo, 0.0)
            if v == 0.0:
                continue
            geo_numerator[geo] += c * v
            geo_denominator[geo] += v

    row_count = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for geo in sorted(geo_numerator.keys()):
            denom = geo_denominator[geo]
            if denom == 0.0:
                continue
            energy_dependency = geo_numerator[geo] / denom

            writer.writerow({
                "geo": geo,
                "energy_dependency": energy_dependency,
            })
            row_count += 1

    print(f"Energy dependency: {row_count} rows → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
