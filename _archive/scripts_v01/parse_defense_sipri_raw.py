#!/usr/bin/env python3
"""ISI v0.1 — Parse SIPRI Trade Register to flat bilateral TIV table.

Input:
  data/raw/sipri/sipri_trade_register_2019_2024.csv

Output (flat):
  data/processed/defense/sipri_bilateral_2019_2024_flat.csv
  Schema: recipient_country,supplier_country,capability_block,year,tiv

Output (audit):
  data/processed/defense/sipri_bilateral_2019_2024_audit.csv
  Schema: recipient_country,n_suppliers,total_tiv,n_blocks_covered,missing_blocks

Output (capability mapping log):
  data/audit/defense_capability_block_mapping_v01.csv
  Schema: weapon_description,assigned_block,match_rule

Output (waterfall):
  data/audit/defense_parser_waterfall_2024.csv
  Schema: stage,count

SIPRI Trade Register CSV has one row per DEAL (order).
A single deal may span multiple delivery years.

TIV per delivery is computed as:
  tiv_per_unit = TIV_deal_unit  (per-unit TIV from SIPRI)
  For each delivery year, we need the number delivered.

SIPRI Trade Register format provides:
  - "No. delivered/produced" = total delivered under the deal
  - "Year(s) of deliveries" = year range or list (e.g., "2019-2022" or "2020")
  - "TIV deal unit" = TIV per unit

We compute total deal TIV = no_delivered * tiv_per_unit
and distribute evenly across delivery years within our window.

Capability block mapping uses keyword matching on the
"Weapon description" field. Every unique description is logged
with its assigned block and the matching rule.

SIPRI country names are mapped to Eurostat geo codes.

Exclusions:
  - Deals with zero or missing TIV
  - Deals with zero or missing deliveries
  - Deals with no delivery years within 2019-2024
  - Self-pairs (recipient == supplier after code mapping)
  - Recipients not in EU-27
  - Ammunition, consumables, maintenance, MRO, training (excluded
    by SIPRI scope — the Trade Register covers major weapons only)

Task: ISI-DEFENSE-PARSE
"""

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "sipri" / "sipri_trade_register_2019_2024.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "defense"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"
OUT_FILE = OUT_DIR / "sipri_bilateral_2019_2024_flat.csv"
AUDIT_FILE = OUT_DIR / "sipri_bilateral_2019_2024_audit.csv"
MAPPING_FILE = AUDIT_DIR / "defense_capability_block_mapping_v01.csv"
WATERFALL_FILE = AUDIT_DIR / "defense_parser_waterfall_2024.csv"

FLAT_FIELDNAMES = [
    "recipient_country",
    "supplier_country",
    "capability_block",
    "year",
    "tiv",
]

AUDIT_FIELDNAMES = [
    "recipient_country",
    "n_suppliers",
    "total_tiv",
    "n_blocks_covered",
    "missing_blocks",
]

YEAR_MIN = 2019
YEAR_MAX = 2024

ALL_BLOCKS = [
    "air_power",
    "land_combat",
    "air_missile_defense",
    "naval_combat",
    "strike_missile",
    "isr_support",
]

# ── SIPRI country name → Eurostat geo code ───────────────────────
# EU-27 members as named in SIPRI Trade Register exports.
SIPRI_TO_EUROSTAT = {
    "Austria": "AT",
    "Belgium": "BE",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Czech Republic": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "EL",
    "Hungary": "HU",
    "Ireland": "IE",
    "Italy": "IT",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Netherlands": "NL",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
}

EU27_EUROSTAT = frozenset(SIPRI_TO_EUROSTAT.values())

# Supplier names also need mapping. We map all known supplier
# countries to a short code. For non-EU suppliers, we use
# ISO-2 codes. This is a comprehensive list of likely suppliers.
SUPPLIER_NAME_TO_CODE = {
    # EU-27 (same mapping)
    **SIPRI_TO_EUROSTAT,
    # Major non-EU suppliers
    "United States": "US",
    "Russia": "RU",
    "China": "CN",
    "United Kingdom": "GB",
    "Israel": "IL",
    "South Korea": "KR",
    "Turkey": "TR",
    "Turkiye": "TR",  # SIPRI 2024 spelling
    "Switzerland": "CH",
    "Norway": "NO",
    "Canada": "CA",
    "Brazil": "BR",
    "South Africa": "ZA",
    "India": "IN",
    "Japan": "JP",
    "Australia": "AU",
    "Ukraine": "UA",
    "Belarus": "BY",
    "Serbia": "RS",
    "Singapore": "SG",
    "Indonesia": "ID",
    "Pakistan": "PK",
    "Iran": "IR",
    "UAE": "AE",
    "United Arab Emirates": "AE",
    "Saudi Arabia": "SA",
    "Jordan": "JO",
    "Egypt": "EG",
    "Taiwan": "TW",
    "Thailand": "TH",
    "Vietnam": "VN",
    "Argentina": "AR",
    "Chile": "CL",
    "Colombia": "CO",
    "Mexico": "MX",
    "Peru": "PE",
    "New Zealand": "NZ",
    "Iceland": "IS",
    "North Macedonia": "MK",
    "Montenegro": "ME",
    "Albania": "AL",
    "Bosnia-Herzegovina": "BA",
    "Bosnia and Herzegovina": "BA",
    "Georgia": "GE",
    "Moldova": "MD",
    "North Korea": "KP",
    "Soviet Union": "SU",
    "Uzbekistan": "UZ",
    "Kazakhstan": "KZ",
    "Unknown": "XX",
    "unknown supplier(s)": "XX",  # SIPRI 2024 convention
    "Multiple": "MULTI",
}


# ── Capability block classification ──────────────────────────────
# Each rule is (block_name, compiled_regex_pattern).
# Rules are evaluated in ORDER. First match wins.
# The regex is matched against the FULL weapon description string
# (case-insensitive).

CAPABILITY_RULES = [
    # Block 3: Air & missile defense — must come BEFORE missiles
    # to capture SAM, MANPADS, SPAAG, AAA, CIWS
    ("air_missile_defense", re.compile(
        r"SAM system|SAM|MANPADS|SPAAG|anti-aircraft|AAA|AAV|"
        r"air defence|air defense|AD system|CIWS|"
        r"SHORADS|Patriot|S-300|S-400|NASAMS|IRIS-T.SLM|"
        r"Gepard|surface-to-air",
        re.IGNORECASE
    )),

    # Block 1: Air power — aircraft of all types
    ("air_power", re.compile(
        r"aircraft|helicopter|FGA|fighter|trainer.*ac|"
        r"transport.*ac|tanker.*ac|AEW|AWACS|"
        r"maritime patrol.*ac|MP.*aircraft|"
        r"ASW.*aircraft|combat.*ac|"
        r"UAV|UCAV|drone|"
        r"turbofan|turboprop|turboshaft|"
        r"jet engine|ac engine",
        re.IGNORECASE
    )),

    # Block 2: Land combat systems — armoured vehicles, artillery
    ("land_combat", re.compile(
        r"tank|IFV|AIFV|APC|armoured|armored|"
        r"AFSV|ARV|AEV|AMV|APV|ACRV|"
        r"infantry fighting|"
        r"howitzer|mortar|artillery|SPG|MRL|"
        r"self-propelled gun|towed gun|"
        r"multiple rocket|"
        r"armoured vehicle engine|"
        r"turret.*armoured|turret.*vehicle",
        re.IGNORECASE
    )),

    # Block 4: Naval combat platforms — ships and naval engines
    ("naval_combat", re.compile(
        r"frigate|corvette|submarine|destroyer|"
        r"aircraft carrier|cruiser|"
        r"fast attack craft|\bFAC\b|OPV|"
        r"offshore patrol|patrol vessel|"
        r"patrol boat|patrol ship|"
        r"MCM|mine countermeasure|minesweep|minehunter|"
        r"landing ship|landing craft|AALS|"
        r"support ship|replenishment|transport ship|"
        r"ship engine|naval engine|naval gun|"
        r"torpedo|sonar|"
        r"ASW weapon|anti-submarine",
        re.IGNORECASE
    )),

    # Block 5: Strike / missile systems (non-SAM missiles)
    ("strike_missile", re.compile(
        r"air-to-surface missile|surface-to-surface missile|"
        r"guided rocket|guided shell|loitering munition|"
        r"missile|ASM|SSM|ARM|ALCM|SLCM|"
        r"anti-ship|anti-tank.*guided|"
        r"guided.*bomb|cruise missile|"
        r"ballistic missile|"
        r"ShShM|SuShM|ShSuM|"
        r"BVRAAM|SRAAM|"
        r"stand-off|"
        r"rocket launcher(?!.*multiple)",
        re.IGNORECASE
    )),

    # Block 6: ISR & support — sensors, satellites, other
    # This is the FALLBACK block. Anything not matched above
    # goes here.
    ("isr_support", re.compile(
        r"radar|sensor|EO|electro-optical|"
        r"SIGINT|ELINT|surveillance|"
        r"reconnaissance|satellite|"
        r"air refuel|tanker|"
        r"fire control|"
        r"turret|"
        r"other|engine|"
        r".",  # catch-all: matches anything
        re.IGNORECASE
    )),
]


def classify_weapon(description):
    """Return (block_name, match_rule) for a weapon description."""
    desc = description.strip()
    if not desc:
        return "isr_support", "empty_description"

    for block, pattern in CAPABILITY_RULES:
        if pattern.search(desc):
            # Extract the specific sub-pattern that matched
            match = pattern.search(desc)
            return block, match.group(0)

    # Should never reach here due to catch-all in isr_support
    return "isr_support", "fallback"


def parse_delivery_years(year_str):
    """Parse SIPRI delivery year field into list of integer years.

    Examples:
      "2020" → [2020]
      "2019-2022" → [2019, 2020, 2021, 2022]
      "(2020)" → [2020]  (parentheses = uncertain)
      "2019-2020; 2022" → [2019, 2020, 2022]
      "" → []
    """
    if not year_str or year_str.strip() == "":
        return []

    # Remove parentheses (SIPRI uncertainty markers)
    cleaned = year_str.replace("(", "").replace(")", "").strip()

    years = set()

    # Split on semicolons and commas
    parts = re.split(r"[;,]", cleaned)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Try range: "2019-2022"
        range_match = re.match(r"(\d{4})\s*[-–]\s*(\d{4})", part)
        if range_match:
            y1 = int(range_match.group(1))
            y2 = int(range_match.group(2))
            for y in range(y1, y2 + 1):
                years.add(y)
            continue

        # Try single year
        single_match = re.match(r"(\d{4})", part)
        if single_match:
            years.add(int(single_match.group(1)))

    return sorted(years)


def parse_number(s):
    """Parse a number from SIPRI field, handling parentheses and blanks."""
    if not s:
        return None
    cleaned = s.replace("(", "").replace(")", "").replace(",", "").strip()
    if cleaned == "" or cleaned == "..":
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def resolve_column(header_lower, patterns):
    """Find column index matching any of the given patterns."""
    for i, h in enumerate(header_lower):
        for p in patterns:
            if p in h:
                return i
    return None


def main():
    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found: {RAW_FILE}", file=sys.stderr)
        print("Run ingest_defense_sipri_manual.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"Input:  {RAW_FILE}")
    print(f"Output: {OUT_FILE}")
    print(f"Audit:  {AUDIT_FILE}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Open input, resolve header ──
    # SIPRI CSV encoding fix: file contains Latin-1 chars (e.g. Wärtsilä, Göteborg)
    fin = open(RAW_FILE, "r", encoding="latin-1", newline="")
    reader = csv.reader(fin)
    # SIPRI CSV compatibility fix (2024 format): skip 11 metadata lines
    for _ in range(11):
        next(reader)
    header = next(reader)
    header_lower = [h.strip().lower() for h in header]

    idx_recipient = resolve_column(header_lower, ["recipient"])
    idx_supplier = resolve_column(header_lower, ["supplier"])
    idx_desc = resolve_column(header_lower, ["weapon description", "description"])  # SIPRI CSV compatibility fix (2024 format)
    idx_delivered = resolve_column(header_lower, ["no. delivered", "number delivered"])
    idx_tiv_unit = resolve_column(header_lower, ["tiv deal unit", "tiv per unit"])
    idx_years = resolve_column(header_lower, ["year(s) of deliveries", "year of deliveries", "delivery year", "year(s) of deliver"])  # SIPRI CSV compatibility fix (2024 format)
    idx_ordered = resolve_column(header_lower, ["no. ordered", "number ordered"])

    for name, idx in [("recipient", idx_recipient), ("supplier", idx_supplier),
                       ("weapon description", idx_desc),
                       ("no. delivered", idx_delivered),
                       ("tiv deal unit", idx_tiv_unit),
                       ("year(s) of deliveries", idx_years)]:
        if idx is None:
            print(f"FATAL: required column '{name}' not found.", file=sys.stderr)
            print(f"  Header: {header}", file=sys.stderr)
            sys.exit(1)
        print(f"  {name:30s} -> col {idx}")

    # ── Prepare output ──
    fout = open(OUT_FILE, "w", newline="")
    writer = csv.writer(fout)
    writer.writerow(FLAT_FIELDNAMES)

    # ── Waterfall counters ──
    total_deals_read = 0
    rows_written = 0
    recipient_not_eu27 = 0
    supplier_unknown_name = 0
    no_deliveries = 0
    no_tiv = 0
    no_delivery_years = 0
    no_years_in_window = 0
    self_pair_excluded = 0
    zero_tiv_computed = 0

    # ── Capability mapping log ──
    # {description: (block, rule)}
    mapping_log = {}

    # ── Audit accumulators ──
    # {recipient_geo: {supplier_geo: {block: total_tiv}}}
    audit_data = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

    # ── Process deals ──
    for row in reader:
        total_deals_read += 1

        if len(row) <= max(idx_recipient, idx_supplier, idx_desc,
                           idx_delivered, idx_tiv_unit, idx_years):
            continue

        recipient_name = row[idx_recipient].strip()
        supplier_name = row[idx_supplier].strip()
        weapon_desc = row[idx_desc].strip()

        # Map recipient
        recipient_geo = SIPRI_TO_EUROSTAT.get(recipient_name)
        if recipient_geo is None:
            recipient_not_eu27 += 1
            continue

        # Map supplier
        supplier_code = SUPPLIER_NAME_TO_CODE.get(supplier_name)
        if supplier_code is None:
            supplier_unknown_name += 1
            # Log unmapped supplier but still try to process
            # Use cleaned name as code
            supplier_code = supplier_name.upper().replace(" ", "_")[:10]
            SUPPLIER_NAME_TO_CODE[supplier_name] = supplier_code

        # Parse deliveries
        n_delivered = parse_number(row[idx_delivered].strip() if idx_delivered < len(row) else "")
        tiv_per_unit = parse_number(row[idx_tiv_unit].strip() if idx_tiv_unit < len(row) else "")

        if n_delivered is None or n_delivered <= 0:
            no_deliveries += 1
            continue

        if tiv_per_unit is None or tiv_per_unit <= 0:
            no_tiv += 1
            continue

        # Parse delivery years
        year_str = row[idx_years].strip() if idx_years < len(row) else ""
        delivery_years = parse_delivery_years(year_str)

        if not delivery_years:
            no_delivery_years += 1
            continue

        # Filter to window
        years_in_window = [y for y in delivery_years if YEAR_MIN <= y <= YEAR_MAX]
        if not years_in_window:
            no_years_in_window += 1
            continue

        # Self-pair check
        if recipient_geo == supplier_code:
            self_pair_excluded += 1
            continue

        # Classify weapon
        block, rule = classify_weapon(weapon_desc)
        if weapon_desc not in mapping_log:
            mapping_log[weapon_desc] = (block, rule)

        # Compute TIV per year
        # Total deal TIV = n_delivered * tiv_per_unit
        # Distribute evenly across delivery years in window
        total_deal_tiv = n_delivered * tiv_per_unit
        # Proportion of delivery years falling in our window
        frac_in_window = len(years_in_window) / len(delivery_years)
        tiv_in_window = total_deal_tiv * frac_in_window
        tiv_per_year = tiv_in_window / len(years_in_window)

        if tiv_per_year <= 0:
            zero_tiv_computed += 1
            continue

        for year in years_in_window:
            writer.writerow([
                recipient_geo,
                supplier_code,
                block,
                year,
                tiv_per_year,
            ])
            rows_written += 1
            audit_data[recipient_geo][supplier_code][block] += tiv_per_year

    fin.close()
    fout.close()

    # ── Post-parse checks ──
    if rows_written == 0:
        print("FATAL: zero rows survived parsing.", file=sys.stderr)
        sys.exit(1)

    # ── Write audit CSV ──
    with open(AUDIT_FILE, "w", newline="") as fa:
        aw = csv.writer(fa)
        aw.writerow(AUDIT_FIELDNAMES)
        for geo in sorted(audit_data.keys()):
            suppliers = audit_data[geo]
            n_suppliers = len(suppliers)
            total_tiv = sum(
                sum(blocks.values())
                for blocks in suppliers.values()
            )
            blocks_present = set()
            for s_blocks in suppliers.values():
                blocks_present.update(s_blocks.keys())
            n_blocks = len(blocks_present)
            missing = sorted(set(ALL_BLOCKS) - blocks_present)
            missing_str = "; ".join(missing) if missing else ""
            aw.writerow([geo, n_suppliers, total_tiv, n_blocks, missing_str])

    # ── Write capability mapping log ──
    with open(MAPPING_FILE, "w", newline="") as fm:
        mw = csv.writer(fm)
        mw.writerow(["weapon_description", "assigned_block", "match_rule"])
        for desc in sorted(mapping_log.keys()):
            block, rule = mapping_log[desc]
            mw.writerow([desc, block, rule])

    # ── Write waterfall ──
    total_excluded = (
        recipient_not_eu27
        + no_deliveries
        + no_tiv
        + no_delivery_years
        + no_years_in_window
        + self_pair_excluded
        + zero_tiv_computed
    )

    waterfall_rows = [
        ("total_deals_read", total_deals_read),
        ("rows_written", rows_written),
        ("recipient_not_eu27", recipient_not_eu27),
        ("no_deliveries", no_deliveries),
        ("no_tiv", no_tiv),
        ("no_delivery_years", no_delivery_years),
        ("no_years_in_window", no_years_in_window),
        ("self_pair_excluded", self_pair_excluded),
        ("zero_tiv_computed", zero_tiv_computed),
        ("total_excluded_deals", total_excluded),
        ("supplier_unknown_name_remapped", supplier_unknown_name),
    ]

    with open(WATERFALL_FILE, "w", newline="") as fw:
        ww = csv.writer(fw)
        ww.writerow(["stage", "count"])
        for stage, count in waterfall_rows:
            ww.writerow([stage, count])

    # ── Print report ──
    print()
    print("=" * 60)
    print("FILTER WATERFALL")
    print("=" * 60)
    for stage, count in waterfall_rows:
        print(f"  {stage:40s} {count:>8}")

    print()
    print("=" * 60)
    print("EU-27 COVERAGE")
    print("=" * 60)
    recipients_found = set(audit_data.keys())
    eu27_present = sorted(EU27_EUROSTAT & recipients_found)
    eu27_missing = sorted(EU27_EUROSTAT - recipients_found)
    print(f"  EU-27 as recipient: {len(eu27_present)}/27")
    if eu27_missing:
        print(f"  MISSING: {eu27_missing}")
    else:
        print(f"  All 27 present.")

    print()
    print("=" * 60)
    print("CAPABILITY BLOCK COVERAGE")
    print("=" * 60)
    for geo in sorted(audit_data.keys()):
        if geo not in EU27_EUROSTAT:
            continue
        suppliers = audit_data[geo]
        blocks_present = set()
        for s_blocks in suppliers.values():
            blocks_present.update(s_blocks.keys())
        missing = sorted(set(ALL_BLOCKS) - blocks_present)
        if missing:
            print(f"  {geo}: missing {missing}")

    print()
    print("=" * 60)
    print("OUTPUT SUMMARY")
    print("=" * 60)
    print(f"  Flat:     {OUT_FILE} ({rows_written} rows)")
    print(f"  Audit:    {AUDIT_FILE} ({len(audit_data)} recipients)")
    print(f"  Mapping:  {MAPPING_FILE} ({len(mapping_log)} descriptions)")
    print(f"  Waterfall:{WATERFALL_FILE}")


if __name__ == "__main__":
    main()
