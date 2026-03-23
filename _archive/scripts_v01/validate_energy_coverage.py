"""ISI v0.1 — Energy Import Coverage Validation (2024)"""

import csv
from collections import OrderedDict
from pathlib import Path

INPUT_DIR = Path("data/processed/energy")

DATASETS = [
    ("nrg_ti_gas", "nrg_ti_gas_2024_flat.csv"),
    ("nrg_ti_oil", "nrg_ti_oil_2024_flat.csv"),
    ("nrg_ti_sff", "nrg_ti_sff_2024_flat.csv"),
]


def validate_dataset(dataset_id, input_path):
    geo_set = set()
    partner_set = set()
    product_set = set()
    unit_set = set()
    missing_count = 0
    total_value = 0.0
    row_count = 0

    with open(input_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_count += 1
            geo_set.add(row["geo"])
            partner_set.add(row["partner"])
            product_set.add(row["product"])
            unit_set.add(row["unit"])

            val = row["value"]
            if val is None or val.strip() == "":
                missing_count += 1
            else:
                total_value += float(val)

    print(f"=== {dataset_id} ({input_path}) ===")
    print(f"  Total rows:              {row_count}")
    print(f"  Unique geo (importers):  {len(geo_set)}")
    print(f"  Unique partners:         {len(partner_set)}")
    print(f"  Unique products:         {len(product_set)}")
    print(f"  Unique units:            {len(unit_set)}")
    print(f"  Rows with missing value: {missing_count}")
    print(f"  Total summed value:      {total_value}")
    print()


def main():
    for dataset_id, filename in DATASETS:
        input_path = INPUT_DIR / filename
        validate_dataset(dataset_id, input_path)


if __name__ == "__main__":
    main()
