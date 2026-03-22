"""
ISI v0.1 — Eurostat Energy Import Ingestion (Raw, 2024)
"""

import json
from pathlib import Path
import requests

EUROSTAT_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data"

REFERENCE_YEAR = 2024

DATASETS = {
    "nrg_ti_gas": "nrg_ti_gas_2024.json",
    "nrg_ti_oil": "nrg_ti_oil_2024.json",
    "nrg_ti_sff": "nrg_ti_sff_2024.json",
}

# SDMX key structure:
# {dataset}/{freq}.{siec}.{partner}.{unit}.{geo}
# Wildcarding is done by leaving dimension values empty (consecutive dots).
# A.... corresponds to annual frequency with all other dimensions wildcarded.
SDMX_KEY = "A...."

QUERY_PARAMS = {
    "format": "JSON",
    "lang": "EN",
    "startPeriod": str(REFERENCE_YEAR),
    "endPeriod": str(REFERENCE_YEAR),
}

OUTPUT_DIR = Path("data/raw/eurostat")


def fetch_dataset(dataset_id: str) -> dict:
    url = f"{EUROSTAT_BASE_URL}/{dataset_id}/{SDMX_KEY}"
    response = requests.get(url, params=QUERY_PARAMS, timeout=120)
    response.raise_for_status()
    return response.json()


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for dataset_id, filename in DATASETS.items():
        print(f"Fetching {dataset_id} ...")
        raw = fetch_dataset(dataset_id)
        output_path = OUTPUT_DIR / filename
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        print(f"Saved {output_path}")


if __name__ == "__main__":
    main()