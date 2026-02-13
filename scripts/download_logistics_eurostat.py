#!/usr/bin/env python3
"""ISI v0.1 — Axis 6: Logistics / Freight Dependency
Data Acquisition Script

Downloads Eurostat transport freight statistics and writes them as
CSV files to data/raw/logistics/ in the format expected by the
ingest gate (Script 1) and parser (Script 2).

Datasets downloaded:
  road_go_ia_lgtt   — Road freight, loaded goods by reporting country
  road_go_ia_ugtt   — Road freight, unloaded goods by reporting country
  rail_go_intgong   — Rail freight, international goods
  iww_go_atygo      — Inland waterway freight by type of goods

  mar_go_am_{iso2}  — Maritime freight goods (main ports) per EU-27
                       maritime reporter. Uses mar_go_am_xx tables.

Source: Eurostat SDMX 2.1 API
  https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/

This script downloads raw data. It does NOT parse, filter, or
compute any scores. All output is to data/raw/logistics/.

Requirements: requests (already in venv)

Task: ISI-LOGISTICS-DOWNLOAD
"""

import csv
import io
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "logistics"

# Eurostat SDMX CSV endpoint
EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data"

# Timeout for HTTP requests (seconds)
TIMEOUT = 180

# ── Maritime reporters (22 non-landlocked EU-27) ─────────────
MARITIME_REPORTERS = [
    "BE", "BG", "CY", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "IE", "IT", "LT", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI",
]


def fetch_eurostat_csv(dataset_code: str, params: dict | None = None) -> str:
    """Fetch a dataset from Eurostat in SDMX-CSV format."""
    url = f"{EUROSTAT_BASE}/{dataset_code}/"
    default_params = {
        "format": "SDMX-CSV",
        "compressed": "false",
    }
    if params:
        default_params.update(params)

    print(f"  GET {url}")
    response = requests.get(url, params=default_params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def save_csv(raw_text: str, filepath: Path) -> int:
    """Save raw CSV text to file. Returns row count (excluding header)."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(raw_text)

    # Count rows
    lines = raw_text.strip().split("\n")
    return max(0, len(lines) - 1)


def fetch_and_save(dataset_code: str, filename: str,
                    params: dict | None = None) -> None:
    """Fetch a Eurostat dataset and save as CSV."""
    filepath = RAW_DIR / filename
    print(f"\n  Dataset: {dataset_code}")
    print(f"  Output:  {filepath}")

    try:
        raw_text = fetch_eurostat_csv(dataset_code, params)
        rows = save_csv(raw_text, filepath)
        size_kb = filepath.stat().st_size / 1024
        print(f"  Rows:    {rows:,}")
        print(f"  Size:    {size_kb:.1f} KB")
    except requests.RequestException as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        raise


def main() -> None:
    print("=" * 64)
    print("ISI v0.1 — Axis 6: Logistics Data Acquisition")
    print("=" * 64)
    print(f"Output directory: {RAW_DIR}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()

    # ── 1. Road freight ──────────────────────────────────────
    print("\n── Road Freight ──")
    fetch_and_save("road_go_ia_lgtt", "road_go_ia_lgtt.csv")
    time.sleep(1)
    fetch_and_save("road_go_ia_ugtt", "road_go_ia_ugtt.csv")
    time.sleep(1)

    # ── 2. Rail freight ──────────────────────────────────────
    print("\n── Rail Freight ──")
    fetch_and_save("rail_go_intgong", "rail_go_intgong.csv")
    time.sleep(1)

    # ── 3. IWW freight ───────────────────────────────────────
    print("\n── Inland Waterway Freight ──")
    fetch_and_save("iww_go_atygo", "iww_go_atygo.csv")
    time.sleep(1)

    # ── 4. Maritime freight ──────────────────────────────────
    print("\n── Maritime Freight ──")
    # Eurostat maritime goods statistics use mar_go_am table
    # The full dataset is mar_go_am — single table covering all reporters
    # Individual country tables may not exist; try the aggregate table first
    fetch_and_save("mar_go_am", "mar_go_am_all.csv")

    # Also try per-country tables if the aggregate is too large
    # or doesn't have partner-level bilateral data
    for iso2 in MARITIME_REPORTERS:
        iso_lower = iso2.lower()
        if iso2 == "EL":
            iso_lower = "el"
        filename = f"mar_go_am_{iso_lower}.csv"
        try:
            fetch_and_save(f"mar_go_am_{iso_lower}", filename)
        except Exception:
            print(f"  Skipped mar_go_am_{iso_lower} (not available)")
        time.sleep(0.5)

    dt = time.time() - t_start
    print()
    print("=" * 64)
    print(f"Download complete in {dt:.0f}s")
    print("=" * 64)
    print()

    # List what we got
    files = sorted(RAW_DIR.glob("*.csv"))
    print(f"Files downloaded: {len(files)}")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name}: {size_kb:.1f} KB")

    print()
    print("Next: python scripts/ingest_logistics_freight_manual.py")


if __name__ == "__main__":
    main()
