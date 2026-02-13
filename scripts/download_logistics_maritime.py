#!/usr/bin/env python3
"""Download Eurostat maritime freight data and split into per-country files.

Tries several Eurostat dataset codes for maritime freight.
Writes per-country files as mar_go_am_{iso2}.csv.
"""
import csv
import io
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "logistics"
RAW_DIR.mkdir(parents=True, exist_ok=True)

EUROSTAT_BASE = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data"
TIMEOUT = 300

# Maritime reporters (non-landlocked EU-27)
MARITIME_ISO2 = {
    "BE": "be", "BG": "bg", "CY": "cy", "DE": "de", "DK": "dk",
    "EE": "ee", "EL": "el", "ES": "es", "FI": "fi", "FR": "fr",
    "HR": "hr", "IE": "ie", "IT": "it", "LT": "lt", "LV": "lv",
    "MT": "mt", "NL": "nl", "PL": "pl", "PT": "pt", "RO": "ro",
    "SE": "se", "SI": "si",
}

# Dataset codes to try (in order of preference)
MARITIME_DATASETS = [
    "mar_sg_am_cw",  # Short-sea shipping - goods by coastline/weight
    "mar_go_am",     # Maritime transport - goods - main ports
    "mar_go_aa",     # Maritime transport - goods - all ports
]


def try_download(dataset_code, params=None):
    """Try to download a dataset. Returns text or None."""
    url = f"{EUROSTAT_BASE}/{dataset_code}/"
    default_params = {
        "format": "SDMX-CSV",
        "compressed": "false",
    }
    if params:
        default_params.update(params)
    
    print(f"  Trying {dataset_code}...")
    try:
        resp = requests.get(url, params=default_params, timeout=TIMEOUT)
        if resp.status_code == 200:
            lines = resp.text.strip().split("\n")
            print(f"    OK: {len(lines)-1} rows, {len(resp.text):,} bytes")
            return resp.text
        else:
            print(f"    HTTP {resp.status_code}")
            return None
    except requests.Timeout:
        print(f"    TIMEOUT after {TIMEOUT}s")
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


def split_maritime_by_country(csv_text, geo_col="geo"):
    """Split a maritime CSV by country code, write per-country files."""
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames
    
    if fieldnames is None:
        print("  ERROR: no header in maritime CSV")
        return 0
    
    # Find the geo column
    geo_column = None
    for col in fieldnames:
        if col.lower().strip() in ("geo", "rep_mar", "reporter"):
            geo_column = col
            break
    
    if geo_column is None:
        print(f"  ERROR: no geo column found. Headers: {fieldnames}")
        return 0
    
    # Group rows by country
    by_country = {}
    for row in reader:
        geo = row[geo_column].strip().upper()
        if geo == "GR":
            geo = "EL"
        if geo not in MARITIME_ISO2:
            continue
        if geo not in by_country:
            by_country[geo] = []
        by_country[geo].append(row)
    
    # Write per-country files
    count = 0
    for geo, rows in sorted(by_country.items()):
        iso_lower = MARITIME_ISO2[geo]
        filepath = RAW_DIR / f"mar_go_am_{iso_lower}.csv"
        with open(filepath, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"    {geo}: {len(rows)} rows → {filepath.name}")
        count += 1
    
    return count


def main():
    print("=" * 64)
    print("Maritime Freight Data Download")
    print("=" * 64)
    
    for ds_code in MARITIME_DATASETS:
        text = try_download(ds_code)
        if text:
            print(f"\n  Splitting {ds_code} by country...")
            n = split_maritime_by_country(text)
            if n > 0:
                print(f"\n  Wrote {n} per-country maritime files")
                break
            else:
                print(f"  No EU-27 maritime rows found in {ds_code}")
        time.sleep(2)
    else:
        print("\nWARNING: No maritime dataset could be downloaded.")
        print("The parser will proceed without maritime data (with warnings).")
    
    # List final state
    print("\n" + "=" * 64)
    print("Files in data/raw/logistics/:")
    for f in sorted(RAW_DIR.glob("*.csv")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")
    print("=" * 64)


if __name__ == "__main__":
    main()
