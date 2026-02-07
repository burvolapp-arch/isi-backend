"""ISI v0.1 — Energy Import Supplier Concentration (2024)"""

import csv
from collections import defaultdict
from pathlib import Path

INPUT_DIR = Path("data/processed/energy")
OUTPUT_DIR = Path("data/processed/energy")

DATASETS = [
    ("nrg_ti_gas", "nrg_ti_gas_2024_shares.csv", "nrg_ti_gas_2024_concentration.csv"),
    ("nrg_ti_oil", "nrg_ti_oil_2024_shares.csv", "nrg_ti_oil_2024_concentration.csv"),
    ("nrg_ti_sff", "nrg_ti_sff_2024_shares.csv", "nrg_ti_sff_2024_concentration.csv"),
]

CSV_COLUMNS = [
    "dataset_id",
    "geo",
    "product",
    "unit",
    "concentration",
]


def compute_concentration(dataset_id, input_path, output_path):
    group_sum_sq = defaultdict(float)

    with open(input_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            share_str = row["share"]
            if share_str is None or share_str.strip() == "":
                continue
            try:
                share = float(share_str)
            except ValueError:
                continue

            group_key = (row["geo"], row["product"], row["unit"])
            group_sum_sq[group_key] += share * share

    row_count = 0

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for group_key in sorted(group_sum_sq.keys()):
            geo, product, unit = group_key
            concentration = group_sum_sq[group_key]

            writer.writerow({
                "dataset_id": dataset_id,
                "geo": geo,
                "product": product,
                "unit": unit,
                "concentration": concentration,
            })
            row_count += 1

    print(f"{dataset_id}: {row_count} concentration rows → {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_id, input_filename, output_filename in DATASETS:
        input_path = INPUT_DIR / input_filename
        output_path = OUTPUT_DIR / output_filename
        compute_concentration(dataset_id, input_path, output_path)


if __name__ == "__main__":
    main()
