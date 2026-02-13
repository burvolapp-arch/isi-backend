#!/usr/bin/env python3
"""Download the correct Eurostat maritime bilateral freight dataset.

The correct dataset for bilateral maritime freight is mar_go_am
(Maritime transport - goods - annual data - main ports aggregate).
This has a par_mar (partner maritime country) dimension.

Alternative: mar_go_aa (all ports) — may also have par_mar.

The mar_sg_am_cw dataset (short-sea shipping by coastline weight)
does NOT have bilateral partner data and is NOT suitable.
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

MARITIME_ISO2 = {
    "BE": "be", "BG": "bg", "CY": "cy", "DE": "de", "DK": "dk",
    "EE": "ee", "EL": "el", "ES": "es", "FI": "fi", "FR": "fr",
    "HR": "hr", "IE": "ie", "IT": "it", "LT": "lt", "LV": "lv",
    "MT": "mt", "NL": "nl", "PL": "pl", "PT": "pt", "RO": "ro",
    "SE": "se", "SI": "si",
}

# Datasets to try, in order. We need one with par_mar column.
DATASETS_TO_TRY = [
    "mar_go_am",     # Main ports - has par_mar
    "mar_go_aa",     # All ports - may have par_mar
    "mar_mg_am_cwh", # Main goods by coastline/weight/direction
]


def download_and_check(ds_code):
    """Download dataset and check if it has a partner column."""
    url = f"{EUROSTAT_BASE}/{ds_code}/"
    params = {"format": "SDMX-CSV", "compressed": "false"}
    print(f"\n  Trying {ds_code}...")
    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        print(f"    HTTP {resp.status_code}, size={len(resp.text):,}")
        if resp.status_code != 200:
            return None
        
        lines = resp.text.strip().split("\n")
        header = lines[0]
        print(f"    Header: {header}")
        
        # Check for partner column
        header_lower = header.lower()
        has_partner = any(p in header_lower for p in ["par_mar", "partner"])
        has_reporter = any(p in header_lower for p in ["rep_mar", "geo", "reporter"])
        has_direction = any(p in header_lower for p in ["direct", "flow", "direction"])
        
        print(f"    Has partner: {has_partner}")
        print(f"    Has reporter: {has_reporter}")
        print(f"    Has direction: {has_direction}")
        print(f"    Rows: {len(lines)-1}")
        
        if has_partner:
            return resp.text
        else:
            print(f"    SKIP: no partner column")
            return None
            
    except requests.Timeout:
        print(f"    TIMEOUT")
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


def split_by_country(csv_text):
    """Split CSV by reporter country, write per-country files."""
    reader = csv.DictReader(io.StringIO(csv_text))
    fieldnames = reader.fieldnames
    
    # Find reporter column
    reporter_col = None
    for col in fieldnames:
        if col.lower().strip() in ("rep_mar", "geo", "reporter"):
            reporter_col = col
            break
    
    if not reporter_col:
        print(f"  No reporter column found")
        return 0
    
    # Group by country
    by_country = {}
    for row in reader:
        geo = row[reporter_col].strip().upper()
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
    print("Maritime Bilateral Freight Download (corrected)")
    print("=" * 64)
    
    for ds_code in DATASETS_TO_TRY:
        text = download_and_check(ds_code)
        if text:
            n = split_by_country(text)
            if n > 0:
                print(f"\n  SUCCESS: {n} per-country files from {ds_code}")
                break
        time.sleep(2)
    else:
        print("\nFAILED: No bilateral maritime dataset found.")
        print("Parser will proceed without maritime data.")
    
    print("\n" + "=" * 64)
    print("Maritime files:")
    for f in sorted(RAW_DIR.glob("mar_*.csv")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")
    print("=" * 64)


if __name__ == "__main__":
    main()
