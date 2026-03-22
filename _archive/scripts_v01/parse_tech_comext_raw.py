#!/usr/bin/env python3
"""ISI v0.1 — Parse Eurostat Comext bilateral semiconductor imports to flat table.

Input:
  data/raw/tech/eu_comext_semiconductors_cn8_2022_2024.csv

Output (flat):
  data/processed/tech/comext_semiconductor_2022_2024_flat.csv
  Schema: reporter,partner,product_nc,hs_category,year,value

Output (audit per reporter):
  data/processed/tech/comext_semiconductor_2022_2024_audit.csv
  Schema: reporter,n_partners,total_value,n_product_codes

Output (waterfall):
  data/audit/tech_parser_waterfall_2024.csv
  Schema: stage,count

Raw CSV structure (Eurostat Comext ds-045409, CN8 level):
  19 columns, UTF-8, flat bilateral.
  DUPLICATE TIME_PERIOD column: index 15 has year data,
  index 16 is always empty. Parser uses index-based access.
  Mixed granularity: CN8 for HS 8541 subcodes, HS4 for 8542.

Key column indices:
  [5]  = REPORTER   (Eurostat geo code, but GR for Greece)
  [7]  = PARTNER    (bilateral partner geo code)
  [9]  = PRODUCT    (CN8 8-digit or HS4 4-digit)
  [11] = FLOW       (1 = imports)
  [15] = TIME_PERIOD (year: 2022, 2023, 2024)
  [17] = OBS_VALUE   (trade value in EUR)

Country code mapping:
  Comext uses GR for Greece; ISI project standard is EL.
  GR → EL applied to BOTH reporter and partner fields.

CN8 → Category mapping (authoritative v0.1):
  85411000 → legacy_discrete      (diodes)
  85412100 → legacy_discrete      (transistors < 1W)
  85412900 → legacy_discrete      (transistors ≥ 1W)
  85413000 → legacy_discrete      (thyristors/diacs/triacs)
  85416000 → legacy_components    (piezoelectric crystals)
  85419000 → legacy_components    (parts/other)
  8542     → integrated_circuits  (ICs, HS4 aggregate)

Defensive guard:
  ANY row with PRODUCT_NC starting with "854140" triggers
  a FATAL error. Solar PV cells must never enter the pipeline.

Exclusions:
  - Reporter EU27_2020 (aggregate, not a country)
  - Self-pairs (reporter == partner after code mapping)
  - Rows with zero or missing OBS_VALUE
  - Rows outside year range 2022-2024
  - Rows with PRODUCT_NC not in the authoritative mapping
  - Rows with FLOW != 1

Task: ISI-TECH-PARSE
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "tech" / "eu_comext_semiconductors_cn8_2022_2024.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "tech"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"
MAPPING_FILE = PROJECT_ROOT / "docs" / "audit" / "tech_cn8_category_mapping_v01.csv"
OUT_FILE = OUT_DIR / "comext_semiconductor_2022_2024_flat.csv"
AUDIT_FILE = OUT_DIR / "comext_semiconductor_2022_2024_audit.csv"
WATERFALL_FILE = AUDIT_DIR / "tech_parser_waterfall_2024.csv"

# Column indices (verified during inspection)
COL_REPORTER = 5
COL_PARTNER = 7
COL_PRODUCT = 9
COL_FLOW = 11
COL_TIME_PERIOD = 15  # first occurrence — has data
COL_OBS_VALUE = 17

VALID_YEARS = {"2022", "2023", "2024"}
VALID_FLOWS = {"1"}

# Authoritative CN8 → semiconductor capability category mapping (v0.1)
# Mixed granularity: 8-digit CN8 codes for HS 8541, 4-digit for HS 8542.
# This is deterministic — every product code must appear here or be rejected.
CN8_CATEGORY_MAP = {
    "85411000": "legacy_discrete",       # Diodes
    "85412100": "legacy_discrete",       # Transistors < 1W
    "85412900": "legacy_discrete",       # Transistors ≥ 1W
    "85413000": "legacy_discrete",       # Thyristors/diacs/triacs
    "85416000": "legacy_components",     # Mounted piezoelectric crystals
    "85419000": "legacy_components",     # Parts/semiconductor n.e.s.
    "8542":     "integrated_circuits",   # Electronic integrated circuits (HS4 aggregate)
}

# Solar PV defensive guard prefix
SOLAR_PV_PREFIX = "854140"

EU27 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

# Country code fixes: Comext uses GR, ISI uses EL
CODE_MAP = {
    "GR": "EL",
}

EXCLUDE_REPORTERS = {"EU27_2020"}

FLAT_FIELDNAMES = [
    "reporter",
    "partner",
    "product_nc",
    "hs_category",
    "year",
    "value",
]

AUDIT_FIELDNAMES = [
    "reporter",
    "n_partners",
    "total_value",
    "n_product_codes",
]


def map_code(code):
    """Apply country code mapping (GR → EL)."""
    return CODE_MAP.get(code, code)


def main():
    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found: {RAW_FILE}", file=sys.stderr)
        print(f"Run ingest_tech_comext_manual.py first.", file=sys.stderr)
        sys.exit(1)

    if not MAPPING_FILE.exists():
        print(f"FATAL: CN8 category mapping not found: {MAPPING_FILE}", file=sys.stderr)
        sys.exit(1)

    # Load and validate the authoritative mapping file
    mapping_from_file = {}
    with open(MAPPING_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping_from_file[row["product_nc"]] = row["category"]

    if mapping_from_file != CN8_CATEGORY_MAP:
        print(f"FATAL: mapping file does not match hardcoded CN8_CATEGORY_MAP", file=sys.stderr)
        print(f"  File: {mapping_from_file}", file=sys.stderr)
        print(f"  Code: {CN8_CATEGORY_MAP}", file=sys.stderr)
        sys.exit(1)

    print(f"CN8 category mapping loaded: {len(CN8_CATEGORY_MAP)} codes")
    for code, cat in sorted(CN8_CATEGORY_MAP.items()):
        print(f"  {code} → {cat}")

    print(f"Input:  {RAW_FILE}")

    # Waterfall counters
    total_raw = 0
    dropped_flow = 0
    dropped_year = 0
    dropped_product_unmapped = 0
    fatal_solar_pv = 0
    dropped_reporter_aggregate = 0
    dropped_reporter_not_eu27 = 0
    dropped_self_pair = 0
    dropped_zero_value = 0
    kept = 0

    # Flat output rows (accumulated, then written)
    flat_rows = []

    with open(RAW_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)

        for parts in reader:
            total_raw += 1

            # Extract fields by index
            reporter_raw = parts[COL_REPORTER].strip()
            partner_raw = parts[COL_PARTNER].strip()
            product = parts[COL_PRODUCT].strip()
            flow = parts[COL_FLOW].strip()
            year = parts[COL_TIME_PERIOD].strip()
            value_str = parts[COL_OBS_VALUE].strip()

            # Filter: flow must be imports (1)
            if flow not in VALID_FLOWS:
                dropped_flow += 1
                continue

            # Filter: year must be in range
            if year not in VALID_YEARS:
                dropped_year += 1
                continue

            # DEFENSIVE GUARD: solar PV must never enter the pipeline
            if product.startswith(SOLAR_PV_PREFIX):
                print(f"FATAL: solar PV product code detected: {product}", file=sys.stderr)
                print(f"  Row {total_raw}: reporter={reporter_raw} partner={partner_raw}", file=sys.stderr)
                print(f"  CN 854140xx (photovoltaic cells) must NOT be in the data.", file=sys.stderr)
                sys.exit(1)

            # Filter: product must be in CN8 category mapping
            if product not in CN8_CATEGORY_MAP:
                dropped_product_unmapped += 1
                continue

            # Exclude aggregate reporters
            if reporter_raw in EXCLUDE_REPORTERS:
                dropped_reporter_aggregate += 1
                continue

            # Map country codes
            reporter = map_code(reporter_raw)
            partner = map_code(partner_raw)

            # Filter: reporter must be EU-27
            if reporter not in EU27:
                dropped_reporter_not_eu27 += 1
                continue

            # Exclude self-pairs
            if reporter == partner:
                dropped_self_pair += 1
                continue

            # Parse value
            if not value_str:
                dropped_zero_value += 1
                continue

            value = float(value_str)
            if value <= 0.0:
                dropped_zero_value += 1
                continue

            hs_category = CN8_CATEGORY_MAP[product]
            flat_rows.append((reporter, partner, product, hs_category, year, value))
            kept += 1

    print(f"  Total raw rows: {total_raw}")
    print(f"  Kept:           {kept}")

    # Sort output: reporter, partner, product_nc, year
    flat_rows.sort(key=lambda r: (r[0], r[1], r[2], r[4]))

    # Write flat output
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUT_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(FLAT_FIELDNAMES)
        for row in flat_rows:
            w.writerow(row)

    print(f"  Flat output: {OUT_FILE} ({kept} rows)")

    # Audit summary per reporter
    reporter_partners = defaultdict(set)
    reporter_values = defaultdict(float)
    reporter_products = defaultdict(set)

    for reporter, partner, product_nc, hs_cat, year, value in flat_rows:
        reporter_partners[reporter].add(partner)
        reporter_values[reporter] += value
        reporter_products[reporter].add(product_nc)

    with open(AUDIT_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(AUDIT_FIELDNAMES)
        for rep in sorted(reporter_partners.keys()):
            w.writerow([
                rep,
                len(reporter_partners[rep]),
                reporter_values[rep],
                len(reporter_products[rep]),
            ])

    print(f"  Audit:       {AUDIT_FILE} ({len(reporter_partners)} reporters)")

    # Waterfall
    waterfall = [
        ("raw_rows", total_raw),
        ("dropped_flow_not_import", dropped_flow),
        ("dropped_year_out_of_range", dropped_year),
        ("dropped_product_unmapped", dropped_product_unmapped),
        ("dropped_reporter_aggregate", dropped_reporter_aggregate),
        ("dropped_reporter_not_eu27", dropped_reporter_not_eu27),
        ("dropped_self_pair", dropped_self_pair),
        ("dropped_zero_or_missing_value", dropped_zero_value),
        ("kept", kept),
    ]

    with open(WATERFALL_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stage", "count"])
        for stage, count in waterfall:
            w.writerow([stage, count])

    print(f"  Waterfall:   {WATERFALL_FILE}")

    # Print waterfall summary
    print()
    print("  Parser waterfall:")
    for stage, count in waterfall:
        print(f"    {stage}: {count}")

    # EU-27 coverage check
    reporters_present = set(reporter_partners.keys())
    present = sorted(EU27 & reporters_present)
    missing = sorted(EU27 - reporters_present)

    print()
    print(f"  EU-27 reporters present: {len(present)}/27")
    if missing:
        print(f"  EU-27 reporters missing: {missing}")

    # Sanity checks
    if kept == 0:
        print("FATAL: zero rows kept after filtering.", file=sys.stderr)
        sys.exit(1)

    if len(present) < 27:
        print(f"WARNING: only {len(present)}/27 EU-27 reporters have data.")

    print()
    print("  Parse complete. All checks passed.")


if __name__ == "__main__":
    main()
