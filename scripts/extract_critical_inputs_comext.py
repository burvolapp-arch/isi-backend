#!/usr/bin/env python3
"""ISI v0.1 — Axis 5: Critical Inputs / Raw Materials Dependency
Extract & Filter Script (local execution)

Reads the 3 annual .7z files already present in
data/raw/comext_bulk/, extracts and filters to the 66-CN8
material universe, and writes a consolidated CSV.

This is the execution-only version — no download stage.

Task: ISI-CRIT-EXTRACT
"""

import csv
import hashlib
import sys
import time
from pathlib import Path

import py7zr

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BULK_DIR = PROJECT_ROOT / "data" / "raw" / "comext_bulk"
EXTRACT_DIR = BULK_DIR / "extracted"
OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "critical_inputs"
    / "eu_comext_critical_inputs_cn8_2022_2024.csv"
)
MAPPING_FILE = (
    PROJECT_ROOT
    / "docs"
    / "mappings"
    / "critical_materials_cn8_mapping_v01.csv"
)

ANNUAL_FILES = {
    2022: "full_v2_202252.7z",
    2023: "full_v2_202352.7z",
    2024: "full_v2_202452.7z",
}

# ── Column names in Comext v2 bulk .dat files ────────────────────
COL_REPORTER = "REPORTER"
COL_PARTNER = "PARTNER"
COL_PRODUCT = "PRODUCT_NC"
COL_FLOW = "FLOW"
COL_PERIOD = "PERIOD"
COL_VALUE = "VALUE_EUR"
COL_STAT_PROC = "STAT_PROCEDURE"

REQUIRED_COLS = [COL_REPORTER, COL_PARTNER, COL_PRODUCT,
                 COL_FLOW, COL_PERIOD, COL_VALUE, COL_STAT_PROC]

OUTPUT_COLS = ["DECLARANT_ISO", "PARTNER_ISO", "PRODUCT_NC",
               "FLOW", "PERIOD", "VALUE_IN_EUROS"]

# ── EU-27 reporters (Comext uses GR for Greece) ──────────────────
EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])
GEO_REMAP = {"GR": "EL"}

# Partner codes to drop (confidential / non-geographic)
DROP_PARTNERS = frozenset([
    "QP", "QQ", "QR", "QS", "QU", "QV", "QW", "QX", "QY", "QZ",
])

PERIOD_REMAP = {"202252": "2022", "202352": "2023", "202452": "2024"}


def load_cn8_codes() -> frozenset:
    codes = set()
    with open(MAPPING_FILE, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            codes.add(row["cn8_code"].strip())
    assert len(codes) == 66, f"Expected 66 CN8 codes, got {len(codes)}"
    return frozenset(codes)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def extract_and_filter(archive: Path, cn8: frozenset, year: int) -> list:
    """Extract one .7z, stream-filter its .dat, return kept rows."""
    t0 = time.time()
    year_dir = EXTRACT_DIR / str(year)
    year_dir.mkdir(parents=True, exist_ok=True)

    # ── Check if already extracted ───────────────────────────
    existing_dats = list(year_dir.glob("*.dat")) + list(year_dir.glob("*.csv"))
    if existing_dats:
        dat_path = existing_dats[0]
        print(f"  Using existing: {dat_path.name} "
              f"({dat_path.stat().st_size / (1024**2):.0f} MB)")
    else:
        print(f"  Extracting: {archive.name} ...", flush=True)
        with py7zr.SevenZipFile(archive, mode="r") as z:
            names = z.getnames()
            dat_names = [n for n in names
                         if n.lower().endswith((".dat", ".csv"))]
            if not dat_names:
                print(f"FATAL: no .dat/.csv in {archive.name}: {names}",
                      file=sys.stderr)
                sys.exit(1)
            z.extractall(path=year_dir)
        dat_path = year_dir / dat_names[0]
        dt = time.time() - t0
        print(f"    Extracted: {dat_path.name} "
              f"({dat_path.stat().st_size / (1024**2):.0f} MB) "
              f"in {dt:.0f}s")

    # ── Detect separator ─────────────────────────────────────
    with open(dat_path, "r", encoding="utf-8") as f:
        hdr = f.readline()
    sep = "\t" if "\t" in hdr else (";" if ";" in hdr else ",")

    # ── Stream filter ────────────────────────────────────────
    print(f"  Filtering: {dat_path.name} (year={year}, sep={repr(sep)})",
          flush=True)
    t1 = time.time()

    total = 0
    kept = 0
    d_flow = 0
    d_proc = 0
    d_geo = 0
    d_prod = 0
    d_partner = 0
    d_val = 0
    zeros = 0
    rows = []

    with open(dat_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=sep)

        # ── Validate columns ─────────────────────────────────
        missing = [c for c in REQUIRED_COLS if c not in reader.fieldnames]
        if missing:
            print(f"FATAL: missing columns: {missing}", file=sys.stderr)
            print(f"  Found: {reader.fieldnames}", file=sys.stderr)
            sys.exit(1)
        print(f"    Columns: {reader.fieldnames[:8]}...")

        for row in reader:
            total += 1
            if total % 2_000_000 == 0:
                print(f"    ... {total:>10,} scanned, {kept:>8,} kept",
                      flush=True)

            # Flow: imports only (1)
            if row[COL_FLOW].strip() != "1":
                d_flow += 1
                continue

            # Stat procedure: normal only (1)
            if row[COL_STAT_PROC].strip() != "1":
                d_proc += 1
                continue

            # Reporter: EU-27
            reporter = row[COL_REPORTER].strip()
            if reporter not in EU27:
                d_geo += 1
                continue

            # Product: 66 CN8 codes
            product = row[COL_PRODUCT].strip()
            if product not in cn8:
                d_prod += 1
                continue

            # Partner: drop Q-prefix confidential
            partner = row[COL_PARTNER].strip()
            if partner in DROP_PARTNERS:
                d_partner += 1
                continue

            # Value
            val_s = row[COL_VALUE].strip()
            if val_s in ("", ":", "c"):
                val_s = "0"
            try:
                val = float(val_s)
            except (ValueError, TypeError):
                d_val += 1
                continue
            if val < 0:
                d_val += 1
                continue
            if val == 0:
                zeros += 1

            # ── Remap and emit ───────────────────────────────
            period_raw = row[COL_PERIOD].strip()
            rows.append({
                "DECLARANT_ISO": GEO_REMAP.get(reporter, reporter),
                "PARTNER_ISO": partner,
                "PRODUCT_NC": product,
                "FLOW": "1",
                "PERIOD": PERIOD_REMAP.get(period_raw, str(year)),
                "VALUE_IN_EUROS": str(int(val)) if val == int(val) else str(val),
            })
            kept += 1

    dt = time.time() - t1
    print(f"    Done: {total:,} total → {kept:,} kept  ({dt:.0f}s)")
    print(f"      flow:{d_flow:,}  proc:{d_proc:,}  geo:{d_geo:,}  "
          f"prod:{d_prod:,}  partner:{d_partner:,}  val:{d_val:,}  "
          f"zeros:{zeros:,}")
    return rows


def main():
    print("=" * 64)
    print("ISI v0.1 — Axis 5: Critical Inputs Extract & Filter")
    print("=" * 64)
    t_start = time.time()

    cn8 = load_cn8_codes()
    print(f"Mapping: {len(cn8)} CN8 codes loaded")
    print()

    # ── Verify archives exist ────────────────────────────────
    for year, fname in sorted(ANNUAL_FILES.items()):
        p = BULK_DIR / fname
        if not p.exists():
            print(f"FATAL: {p} not found", file=sys.stderr)
            sys.exit(1)
        print(f"  {fname}: {p.stat().st_size / (1024**2):.1f} MB")
    print()

    # ── Extract & Filter each year ───────────────────────────
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for year, fname in sorted(ANNUAL_FILES.items()):
        print(f"── Year {year} ──")
        rows = extract_and_filter(BULK_DIR / fname, cn8, year)
        all_rows.extend(rows)
        print()

    # ── Write output ─────────────────────────────────────────
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLS)
        w.writeheader()
        w.writerows(all_rows)

    h = sha256(OUTPUT_FILE)

    # ── Summary ──────────────────────────────────────────────
    reporters = set()
    partners = set()
    products = set()
    periods = set()
    total_eur = 0.0
    for r in all_rows:
        reporters.add(r["DECLARANT_ISO"])
        partners.add(r["PARTNER_ISO"])
        products.add(r["PRODUCT_NC"])
        periods.add(r["PERIOD"])
        total_eur += float(r["VALUE_IN_EUROS"])

    dt_total = time.time() - t_start

    print("=" * 64)
    print("OUTPUT")
    print("=" * 64)
    print(f"  File:     {OUTPUT_FILE}")
    print(f"  Size:     {OUTPUT_FILE.stat().st_size:,} bytes")
    print(f"  SHA-256:  {h}")
    print(f"  Rows:     {len(all_rows):,}")
    print(f"  Reporters:{len(reporters)} {sorted(reporters)}")
    print(f"  Partners: {len(partners)}")
    print(f"  CN8 codes:{len(products)}/66")
    print(f"  Periods:  {sorted(periods)}")
    print(f"  Total EUR:{total_eur:,.0f}")
    print(f"  Runtime:  {dt_total:.0f}s")
    print()

    missing_cn8 = cn8 - products
    if missing_cn8:
        print(f"  WARNING: {len(missing_cn8)} CN8 codes with NO data:")
        for c in sorted(missing_cn8):
            print(f"    {c}")
    else:
        print("  All 66 CN8 codes present: OK")

    eu27_expected = frozenset([
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
        "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
        "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
        "SE", "SI", "SK",
    ])
    missing_geo = eu27_expected - reporters
    if missing_geo:
        print(f"  WARNING: {len(missing_geo)} reporters missing: "
              f"{sorted(missing_geo)}")
    else:
        print("  All 27 EU reporters present: OK")

    print()
    print("=" * 64)
    print("Next: python scripts/ingest_critical_inputs_comext_manual.py")
    print("=" * 64)


if __name__ == "__main__":
    main()
