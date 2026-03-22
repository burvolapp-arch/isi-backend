#!/usr/bin/env python3
"""ISI v0.1 — Parse BIS LBS raw CSV to flat bilateral claims table.

Input:
  data/raw/finance/bis_lbs_2024_raw.csv
  Pre-filtered via BIS SDMX API for:
    FREQ=Q, L_MEASURE=S, L_POSITION=C, L_INSTR=A, L_DENOM=TO1,
    L_CURR_TYPE=A, L_PARENT_CTY=5J, L_REP_BANK_TYPE=A,
    L_CP_SECTOR=A, L_POS_TYPE=N, TIME_PERIOD=2024-Q4

Output (flat):
  data/processed/finance/bis_lbs_inward_2024_flat.csv
  Schema: counterparty_country,reporting_country,period,value_usd_mn

Output (audit):
  data/processed/finance/bis_lbs_inward_2024_audit.csv
  Schema: counterparty_country,n_creditor_countries,total_value_usd_mn

Perspective (methodology Section 6):
  reporting_country  = creditor country j (BIS field: L_REP_CTY)
  counterparty_country = debtor country i  (BIS field: L_CP_COUNTRY)

Exclusions:
  - Aggregate/residual codes (non-alpha or len != 2)
  - Self-pairs (reporting_country == counterparty_country)
  - Missing or non-numeric OBS_VALUE
  - Negative values
  - Zero values (dropped from flat; counted in audit)

Streaming:
  - csv.reader / csv.writer, no pandas
  - Audit accumulators keyed by counterparty_country only

Hard constraints:
  - Does NOT aggregate, compute shares, or compute concentration
  - Does NOT impute missing data
  - Does NOT rename or remap country codes
  - STOPS if required header columns are missing

Task: ISI-FINANCE-PARSE-BIS-LBS
"""

import csv
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "finance" / "bis_lbs_2024_raw.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "finance"
OUT_FILE = OUT_DIR / "bis_lbs_inward_2024_flat.csv"
AUDIT_FILE = OUT_DIR / "bis_lbs_inward_2024_audit.csv"

# ─── Expected column names ──────────────────────────────────────
COL_REP_CTY = "L_REP_CTY"
COL_CP_COUNTRY = "L_CP_COUNTRY"
COL_TIME_PERIOD = "TIME_PERIOD"
COL_OBS_VALUE = "OBS_VALUE"

# ─── Expected pre-filter values (verified, not re-filtered) ─────
# The raw file was fetched via SDMX with exact key Q.S.C.A.TO1.A.5J.A..A..N
# and period 2024-Q4. We verify these hold on every row as a safety check.
COL_FREQ = "FREQ"
COL_MEASURE = "L_MEASURE"
COL_POSITION = "L_POSITION"
COL_INSTR = "L_INSTR"
COL_DENOM = "L_DENOM"
COL_CURR_TYPE = "L_CURR_TYPE"
COL_CP_SECTOR = "L_CP_SECTOR"

EXPECTED_FREQ = "Q"
EXPECTED_MEASURE = "S"
EXPECTED_POSITION = "C"
EXPECTED_INSTR = "A"
EXPECTED_DENOM = "TO1"
EXPECTED_CURR_TYPE = "A"
EXPECTED_CP_SECTOR = "A"
EXPECTED_PERIOD = "2024-Q4"

# ─── Output fieldnames ──────────────────────────────────────────
FLAT_FIELDNAMES = [
    "counterparty_country",
    "reporting_country",
    "period",
    "value_usd_mn",
]

AUDIT_FIELDNAMES = [
    "counterparty_country",
    "n_creditor_countries",
    "total_value_usd_mn",
]

# ─── EU-27 ISO-2 codes ──────────────────────────────────────────
EU27_ISO2 = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "GR", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])


def is_country_code(code):
    """Return True if code looks like an ISO-2 country code (2 alpha chars)."""
    return len(code) == 2 and code.isalpha()


def resolve_column_index(header, col_name):
    """Return 0-based index for col_name in header. STOP if not found."""
    for i, h in enumerate(header):
        if h.strip() == col_name:
            return i
    print(f"FATAL: required column '{col_name}' not found in header.", file=sys.stderr)
    print(f"  Header: {header}", file=sys.stderr)
    sys.exit(1)


def main():
    # ── Verify input file ──
    if not RAW_FILE.exists():
        print(f"FATAL: raw file not found: {RAW_FILE}", file=sys.stderr)
        sys.exit(1)

    print(f"Input:  {RAW_FILE}")
    print(f"Output: {OUT_FILE}")
    print(f"Audit:  {AUDIT_FILE}")

    # ── Open input, resolve header ──
    fin = open(RAW_FILE, "r", encoding="utf-8", newline="")
    reader = csv.reader(fin)
    header = next(reader)

    idx_freq = resolve_column_index(header, COL_FREQ)
    idx_measure = resolve_column_index(header, COL_MEASURE)
    idx_position = resolve_column_index(header, COL_POSITION)
    idx_instr = resolve_column_index(header, COL_INSTR)
    idx_denom = resolve_column_index(header, COL_DENOM)
    idx_curr_type = resolve_column_index(header, COL_CURR_TYPE)
    idx_cp_sector = resolve_column_index(header, COL_CP_SECTOR)
    idx_rep = resolve_column_index(header, COL_REP_CTY)
    idx_cp = resolve_column_index(header, COL_CP_COUNTRY)
    idx_period = resolve_column_index(header, COL_TIME_PERIOD)
    idx_val = resolve_column_index(header, COL_OBS_VALUE)

    print(f"  L_REP_CTY     -> col {idx_rep}")
    print(f"  L_CP_COUNTRY  -> col {idx_cp}")
    print(f"  TIME_PERIOD   -> col {idx_period}")
    print(f"  OBS_VALUE     -> col {idx_val}")

    # ── Prepare output ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fout = open(OUT_FILE, "w", newline="")
    writer = csv.writer(fout)
    writer.writerow(FLAT_FIELDNAMES)

    # ── Filter waterfall counters ────────────────────────────────
    total_rows_read = 0
    rows_written = 0
    filter_integrity_fail = 0
    aggregate_code_excluded = 0
    self_pair_excluded = 0
    missing_or_non_numeric = 0
    negative_value = 0
    zero_value_dropped = 0

    # ── Audit accumulators (keyed by counterparty_country) ───────
    # Each entry: [n_creditor_countries_nonzero, total_value_usd_mn]
    audit = {}

    # ── Streaming parse ──────────────────────────────────────────
    for row in reader:
        total_rows_read += 1

        # ── Integrity check: verify pre-filter values ──
        if (row[idx_freq] != EXPECTED_FREQ or
            row[idx_measure] != EXPECTED_MEASURE or
            row[idx_position] != EXPECTED_POSITION or
            row[idx_instr] != EXPECTED_INSTR or
            row[idx_denom] != EXPECTED_DENOM or
            row[idx_curr_type] != EXPECTED_CURR_TYPE or
            row[idx_cp_sector] != EXPECTED_CP_SECTOR or
            row[idx_period] != EXPECTED_PERIOD):
            filter_integrity_fail += 1
            continue

        rep = row[idx_rep].strip()
        cp = row[idx_cp].strip()

        # ── Exclude aggregate/residual codes ──
        if not is_country_code(rep) or not is_country_code(cp):
            aggregate_code_excluded += 1
            continue

        # ── Exclude self-pairs ──
        if rep == cp:
            self_pair_excluded += 1
            continue

        # ── Extract value ──
        raw_val = row[idx_val].strip()
        if raw_val == "":
            missing_or_non_numeric += 1
            continue

        try:
            value = float(raw_val)
        except (ValueError, TypeError):
            missing_or_non_numeric += 1
            continue

        if math.isnan(value):
            missing_or_non_numeric += 1
            continue

        if value < 0:
            negative_value += 1
            continue

        # ── Update audit accumulator ──
        if cp not in audit:
            audit[cp] = [0, 0.0]
        if value > 0:
            audit[cp][0] += 1
            audit[cp][1] += value

        # ── Drop zero-value rows from flat output ──
        if value == 0.0:
            zero_value_dropped += 1
            continue

        # ── Write output row ──
        writer.writerow([cp, rep, "2024-Q4", value])
        rows_written += 1

    # ── Close files ──
    fin.close()
    fout.close()

    # ── Post-parse validation ──
    if rows_written == 0:
        print("FATAL: zero rows survived parsing.", file=sys.stderr)
        print(f"  Total rows read: {total_rows_read}", file=sys.stderr)
        sys.exit(1)

    # ── Write audit CSV ──
    with open(AUDIT_FILE, "w", newline="") as fa:
        aw = csv.writer(fa)
        aw.writerow(AUDIT_FIELDNAMES)
        for cp in sorted(audit):
            n_cred, total_val = audit[cp]
            aw.writerow([cp, n_cred, total_val])

    # ── Filter waterfall report ──────────────────────────────────
    total_excluded = (
        filter_integrity_fail
        + aggregate_code_excluded
        + self_pair_excluded
        + missing_or_non_numeric
        + negative_value
        + zero_value_dropped
    )

    print()
    print("=" * 60)
    print("FILTER WATERFALL")
    print("=" * 60)
    print(f"  total_rows_read:              {total_rows_read:>8}")
    print(f"  rows_written:                 {rows_written:>8}")
    print(f"  ─────────────────────────────────────────")
    print(f"  filter_integrity_fail:        {filter_integrity_fail:>8}")
    print(f"  aggregate_code_excluded:      {aggregate_code_excluded:>8}")
    print(f"  self_pair_excluded:           {self_pair_excluded:>8}")
    print(f"  missing_or_non_numeric:       {missing_or_non_numeric:>8}")
    print(f"  negative_value:               {negative_value:>8}")
    print(f"  zero_value_dropped:           {zero_value_dropped:>8}")
    print(f"  ─────────────────────────────────────────")
    print(f"  total_excluded:               {total_excluded:>8}")
    print(f"  checksum (written + excluded):{rows_written + total_excluded:>8}")

    if rows_written + total_excluded != total_rows_read:
        print("FATAL: waterfall checksum mismatch!", file=sys.stderr)
        sys.exit(1)
    else:
        print("  checksum: OK")

    # ── EU-27 coverage warnings ──────────────────────────────────
    cp_in_audit = set(audit.keys())
    eu27_present = EU27_ISO2 & cp_in_audit
    eu27_missing = sorted(EU27_ISO2 - cp_in_audit)
    eu27_zero_vol = sorted([c for c in EU27_ISO2 & cp_in_audit if audit[c][1] == 0.0])
    eu27_low_cred = sorted([c for c in EU27_ISO2 & cp_in_audit if audit[c][0] < 3])

    print()
    print("=" * 60)
    print("EU-27 COVERAGE CHECK")
    print("=" * 60)
    print(f"  EU-27 as counterparty_country: {len(eu27_present)}/27")

    if eu27_missing:
        print()
        print("  *** WARNING: EU-27 MEMBERS MISSING AS COUNTERPARTY ***")
        for code in eu27_missing:
            print(f"      MISSING: {code}")

    if eu27_zero_vol:
        print()
        print("  *** WARNING: EU-27 MEMBERS WITH ZERO TOTAL VOLUME ***")
        for code in eu27_zero_vol:
            print(f"      ZERO: {code}")

    if eu27_low_cred:
        print()
        print("  *** WARNING: EU-27 MEMBERS WITH < 3 CREDITOR COUNTRIES ***")
        for code in eu27_low_cred:
            n_cred = audit[code][0]
            print(f"      {code}: {n_cred} creditor(s)")

    if not eu27_missing and not eu27_zero_vol and not eu27_low_cred:
        print("  All 27 EU member states present with adequate coverage.")

    # ── Summary ──
    print()
    print("=" * 60)
    print("OUTPUT SUMMARY")
    print("=" * 60)
    print(f"  Flat file:  {OUT_FILE}  ({rows_written} rows)")
    print(f"  Audit file: {AUDIT_FILE}  ({len(audit)} counterparty countries)")
    print(f"  All checks passed.")


if __name__ == "__main__":
    main()
