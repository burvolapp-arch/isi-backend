"""ISI v0.1 — Energy Import Supplier Shares (2024)"""

import csv
from collections import defaultdict
from pathlib import Path

INPUT_DIR = Path("data/processed/energy")
OUTPUT_DIR = Path("data/processed/energy")

DATASETS = [
    ("nrg_ti_gas", "nrg_ti_gas_2024_flat.csv", "nrg_ti_gas_2024_shares.csv"),
    ("nrg_ti_oil", "nrg_ti_oil_2024_flat.csv", "nrg_ti_oil_2024_shares.csv"),
    ("nrg_ti_sff", "nrg_ti_sff_2024_flat.csv", "nrg_ti_sff_2024_shares.csv"),
]

CSV_COLUMNS = [
    "dataset_id",
    "geo",
    "product",
    "unit",
    "partner",
    "share",
]


def compute_shares(dataset_id, input_path, output_path):
    partner_sums = defaultdict(lambda: defaultdict(float))
    group_totals = defaultdict(float)

    with open(input_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            val_str = row["value"]
            if val_str is None or val_str.strip() == "":
                continue
            try:
                val = float(val_str)
            except ValueError:
                continue

            geo = row["geo"]
            product = row["product"]
            unit = row["unit"]
            partner = row["partner"]

            group_key = (geo, product, unit)
            partner_sums[group_key][partner] += val
            group_totals[group_key] += val

    row_count = 0

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for group_key in sorted(partner_sums.keys()):
            geo, product, unit = group_key
            total = group_totals[group_key]

            for partner in sorted(partner_sums[group_key].keys()):
                partner_val = partner_sums[group_key][partner]

                if total == 0.0:
                    share = 0.0
                else:
                    share = partner_val / total

                writer.writerow({
                    "dataset_id": dataset_id,
                    "geo": geo,
                    "product": product,
                    "unit": unit,
                    "partner": partner,
                    "share": share,
                })
                row_count += 1

    print(f"{dataset_id}: {row_count} share rows → {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_id, input_filename, output_filename in DATASETS:
        input_path = INPUT_DIR / input_filename
        output_path = OUTPUT_DIR / output_filename
        compute_shares(dataset_id, input_path, output_path)


if __name__ == "__main__":
    main()
