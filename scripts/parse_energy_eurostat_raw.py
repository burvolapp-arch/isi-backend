"""ISI v0.1 — Eurostat Energy Import Parsing (Flat, Raw)"""

import csv
import json
from pathlib import Path

INPUT_DIR = Path("data/raw/eurostat")
OUTPUT_DIR = Path("data/processed/energy")

DATASETS = [
    ("nrg_ti_gas", "nrg_ti_gas_2024.json", "nrg_ti_gas_2024_flat.csv"),
    ("nrg_ti_oil", "nrg_ti_oil_2024.json", "nrg_ti_oil_2024_flat.csv"),
    ("nrg_ti_sff", "nrg_ti_sff_2024.json", "nrg_ti_sff_2024_flat.csv"),
]

CSV_COLUMNS = [
    "dataset_id",
    "freq",
    "partner",
    "product",
    "flow",
    "unit",
    "geo",
    "time",
    "value",
]

SDMX_DIM_TO_CSV = {
    "freq": "freq",
    "siec": "product",
    "partner": "partner",
    "unit": "unit",
    "geo": "geo",
    "time": "time",
}


def parse_dataset(dataset_id, input_path, output_path):
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    dim_ids = data["id"]
    sizes = data["size"]
    dimensions = data["dimension"]

    pos_to_code = {}
    for dim_name in dim_ids:
        cat_index = dimensions[dim_name]["category"]["index"]
        pos_to_code[dim_name] = {v: k for k, v in cat_index.items()}

    strides = []
    for i in range(len(sizes)):
        stride = 1
        for j in range(i + 1, len(sizes)):
            stride *= sizes[j]
        strides.append(stride)

    observations = data.get("value", {})

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for flat_key, value in observations.items():
            flat_index = int(flat_key)

            dim_indices = []
            remaining = flat_index
            for i in range(len(sizes)):
                dim_indices.append(remaining // strides[i])
                remaining = remaining % strides[i]

            row = {"dataset_id": dataset_id, "flow": "IMP", "value": value}
            for i, dim_name in enumerate(dim_ids):
                csv_col = SDMX_DIM_TO_CSV[dim_name]
                row[csv_col] = pos_to_code[dim_name][dim_indices[i]]

            writer.writerow(row)

    print(f"Parsed {len(observations)} observations → {output_path}")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_id, input_filename, output_filename in DATASETS:
        input_path = INPUT_DIR / input_filename
        output_path = OUTPUT_DIR / output_filename
        parse_dataset(dataset_id, input_path, output_path)


if __name__ == "__main__":
    main()
