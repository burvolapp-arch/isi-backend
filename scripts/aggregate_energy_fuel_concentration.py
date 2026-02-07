"""ISI v0.1 — Fuel-Level Energy Import Concentration (2024)"""

import csv
from collections import defaultdict
from pathlib import Path

INPUT_DIR = Path("data/processed/energy")
OUTPUT_DIR = Path("data/processed/energy")

DATASETS = [
    (
        "nrg_ti_gas",
        "gas",
        "nrg_ti_gas_2024_flat.csv",
        "nrg_ti_gas_2024_concentration.csv",
        "nrg_ti_gas_2024_fuel_concentration.csv",
    ),
    (
        "nrg_ti_oil",
        "oil",
        "nrg_ti_oil_2024_flat.csv",
        "nrg_ti_oil_2024_concentration.csv",
        "nrg_ti_oil_2024_fuel_concentration.csv",
    ),
    (
        "nrg_ti_sff",
        "solid_fossil",
        "nrg_ti_sff_2024_flat.csv",
        "nrg_ti_sff_2024_concentration.csv",
        "nrg_ti_sff_2024_fuel_concentration.csv",
    ),
]

CSV_COLUMNS = [
    "dataset_id",
    "geo",
    "fuel",
    "concentration",
]


def load_group_volumes(flat_path):
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

            group_key = (row["geo"], row["product"], row["unit"])
            volumes[group_key] += val

    return volumes


def load_group_concentrations(concentration_path):
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

            group_key = (row["geo"], row["product"], row["unit"])
            concentrations[group_key] = c

    return concentrations


def compute_fuel_concentration(dataset_id, fuel, flat_path, concentration_path, output_path):
    volumes = load_group_volumes(flat_path)
    concentrations = load_group_concentrations(concentration_path)

    geo_numerator = defaultdict(float)
    geo_denominator = defaultdict(float)

    for group_key, c in concentrations.items():
        geo = group_key[0]
        v = volumes.get(group_key, 0.0)
        if v == 0.0:
            continue
        geo_numerator[geo] += c * v
        geo_denominator[geo] += v

    row_count = 0

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for geo in sorted(geo_numerator.keys()):
            denom = geo_denominator[geo]
            if denom == 0.0:
                continue
            fuel_concentration = geo_numerator[geo] / denom

            writer.writerow({
                "dataset_id": dataset_id,
                "geo": geo,
                "fuel": fuel,
                "concentration": fuel_concentration,
            })
            row_count += 1

    print(f"{dataset_id} ({fuel}): {row_count} fuel-level rows → {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_id, fuel, flat_filename, conc_filename, output_filename in DATASETS:
        flat_path = INPUT_DIR / flat_filename
        concentration_path = INPUT_DIR / conc_filename
        output_path = OUTPUT_DIR / output_filename
        compute_fuel_concentration(dataset_id, fuel, flat_path, concentration_path, output_path)


if __name__ == "__main__":
    main()
