#!/usr/bin/env python3
"""ISI v0.1 — Axis 5: Critical Inputs / Raw Materials Dependency
Data Acquisition Script

Downloads Eurostat Comext bulk files for 2022–2024 (annual),
decompresses, filters to our 66-CN8 material universe, and
writes a consolidated CSV ready for the ingest gate.

Architecture:
  1. Download 3 annual .7z files from Eurostat Bulk Download Facility
  2. Decompress each to CSV
  3. Stream-filter: 66 CN8 codes × EU-27 reporters × imports × normal procedure
  4. Write consolidated output CSV with ISI-internal column names

Source:
  Eurostat Comext Bulk Download Facility
  https://ec.europa.eu/eurostat/api/dissemination/files/

Files:
  full_v2_202252.7z  — 2022 annual data
  full_v2_202352.7z  — 2023 annual data
  full_v2_202452.7z  — 2024 annual data

Output:
  data/raw/critical_inputs/eu_comext_critical_inputs_cn8_2022_2024.csv

Dependencies:
  pip install httpx py7zr

Task: ISI-CRIT-DOWNLOAD
"""

import csv
import hashlib
import io
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("FATAL: httpx not installed. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

try:
    import py7zr
except ImportError:
    print("FATAL: py7zr not installed. Run: pip install py7zr", file=sys.stderr)
    sys.exit(1)


# ── Project Layout ───────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DOWNLOAD_DIR = PROJECT_ROOT / "data" / "raw" / "comext_bulk"
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


# ── Eurostat Bulk Download Configuration ─────────────────────────

BULK_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/files/"

# Annual files: suffix 52 = annual aggregation
ANNUAL_FILES = {
    2022: "full_v2_202252.7z",
    2023: "full_v2_202352.7z",
    2024: "full_v2_202452.7z",
}


# ── Column Mapping: Bulk v2 → ISI Internal ──────────────────────

# Bulk v2 columns (17 total):
#   REPORTER, PARTNER, TRADE_TYPE, PRODUCT_NC, PRODUCT_SITC,
#   PRODUCT_CPA21, PRODUCT_BEC, PRODUCT_BEC5, PRODUCT_SECTION,
#   FLOW, STAT_PROCEDURE, SUPPL_UNIT, PERIOD,
#   VALUE_EUR, VALUE_NAC, QUANTITY_KG, QUANTITY_SUPPL_UNIT
#
# ISI internal output columns (6):
#   DECLARANT_ISO, PARTNER_ISO, PRODUCT_NC, FLOW, PERIOD, VALUE_IN_EUROS

BULK_COL_REPORTER = "REPORTER"
BULK_COL_PARTNER = "PARTNER"
BULK_COL_PRODUCT = "PRODUCT_NC"
BULK_COL_FLOW = "FLOW"
BULK_COL_PERIOD = "PERIOD"
BULK_COL_VALUE = "VALUE_EUR"
BULK_COL_STAT_PROC = "STAT_PROCEDURE"

REQUIRED_BULK_COLUMNS = [
    BULK_COL_REPORTER,
    BULK_COL_PARTNER,
    BULK_COL_PRODUCT,
    BULK_COL_FLOW,
    BULK_COL_PERIOD,
    BULK_COL_VALUE,
    BULK_COL_STAT_PROC,
]

OUTPUT_COLUMNS = [
    "DECLARANT_ISO",
    "PARTNER_ISO",
    "PRODUCT_NC",
    "FLOW",
    "PERIOD",
    "VALUE_IN_EUROS",
]


# ── Geographic Constants ─────────────────────────────────────────

# EU-27 reporter codes as they appear in Comext bulk files.
# Comext uses GR for Greece; ISI uses EL.
EU27_REPORTERS = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
    "ES", "FI", "FR", "GR", "HR", "HU", "IE", "IT",
    "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
    "SE", "SI", "SK",
])

# GR → EL normalisation for ISI output
GEO_REMAP = {"GR": "EL"}

# Partner codes to DROP (confidential/non-geographic)
DROP_PARTNERS = frozenset([
    "QP", "QQ", "QR", "QS", "QU", "QV", "QW", "QX", "QY", "QZ",
])


# ── Filter Constants ─────────────────────────────────────────────

FLOW_IMPORT = "1"
STAT_PROCEDURE_NORMAL = "1"

# Period mapping: bulk annual uses YYYY52, ISI uses YYYY
PERIOD_REMAP = {
    "202252": "2022",
    "202352": "2023",
    "202452": "2024",
}


# ── HTTP Configuration ──────────────────────────────────────────

CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 600.0   # 10 minutes — files are 93 MB
MAX_RETRIES = 5
RETRY_BACKOFF_BASE = 5.0   # seconds, exponential backoff
CHUNK_SIZE = 1024 * 1024   # 1 MB download chunks
RATE_LIMIT_DELAY = 2.0     # seconds between file downloads


# ═════════════════════════════════════════════════════════════════
# Functions
# ═════════════════════════════════════════════════════════════════

def load_mapping_codes() -> frozenset:
    """Load the 66 authoritative CN8 codes from the mapping CSV."""
    if not MAPPING_FILE.exists():
        print(f"FATAL: mapping file not found: {MAPPING_FILE}", file=sys.stderr)
        sys.exit(1)

    codes = set()
    with open(MAPPING_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if "cn8_code" not in reader.fieldnames:
            print("FATAL: mapping file missing 'cn8_code' column", file=sys.stderr)
            sys.exit(1)
        for row in reader:
            codes.add(row["cn8_code"].strip())

    if len(codes) != 66:
        print(
            f"FATAL: mapping has {len(codes)} CN8 codes, expected 66",
            file=sys.stderr,
        )
        sys.exit(1)

    return frozenset(codes)


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def download_file(filename: str, dest_path: Path) -> None:
    """Download a single file from the Eurostat bulk download facility.

    Uses exponential backoff retry. Skips if file already exists
    with non-zero size.
    """
    if dest_path.exists() and dest_path.stat().st_size > 0:
        size_mb = dest_path.stat().st_size / (1024 * 1024)
        print(f"  SKIP (exists): {dest_path.name} ({size_mb:.1f} MB)")
        return

    url = f"{BULK_BASE_URL}?file=comext/COMEXT_DATA/PRODUCTS/{filename}"
    print(f"  Downloading: {url}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.stream(
                "GET",
                url,
                timeout=httpx.Timeout(
                    connect=CONNECT_TIMEOUT,
                    read=READ_TIMEOUT,
                    write=READ_TIMEOUT,
                    pool=CONNECT_TIMEOUT,
                ),
                follow_redirects=True,
            ) as response:
                response.raise_for_status()

                total = int(response.headers.get("content-length", 0))
                downloaded = 0

                dest_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = dest_path.with_suffix(".tmp")

                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = (downloaded / total) * 100
                            print(
                                f"\r    {downloaded / (1024*1024):.1f} / "
                                f"{total / (1024*1024):.1f} MB ({pct:.0f}%)",
                                end="",
                                flush=True,
                            )

                print()  # newline after progress

                # Atomic rename
                tmp_path.rename(dest_path)

                size_mb = dest_path.stat().st_size / (1024 * 1024)
                file_hash = sha256_file(dest_path)
                print(f"    OK: {size_mb:.1f} MB, SHA-256: {file_hash[:16]}...")
                return

        except (httpx.HTTPStatusError, httpx.TransportError, OSError) as e:
            wait = RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
            print(f"    Attempt {attempt}/{MAX_RETRIES} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"    Retrying in {wait:.0f}s...")
                time.sleep(wait)
            else:
                print(f"FATAL: download failed after {MAX_RETRIES} attempts", file=sys.stderr)
                # Clean up partial file
                tmp_path = dest_path.with_suffix(".tmp")
                if tmp_path.exists():
                    tmp_path.unlink()
                sys.exit(1)


def extract_7z(archive_path: Path, extract_dir: Path) -> Path:
    """Extract a .7z archive and return the path to the CSV inside.

    Expects exactly one CSV file inside the archive.
    """
    print(f"  Extracting: {archive_path.name}")

    with py7zr.SevenZipFile(archive_path, mode="r") as z:
        names = z.getnames()
        csv_names = [n for n in names if n.lower().endswith(".csv") or n.lower().endswith(".dat")]

        if not csv_names:
            print(f"FATAL: no CSV/DAT file found in {archive_path.name}", file=sys.stderr)
            print(f"  Archive contents: {names}", file=sys.stderr)
            sys.exit(1)

        # Extract all files
        z.extractall(path=extract_dir)

    # Use the first (typically only) CSV/DAT file
    csv_path = extract_dir / csv_names[0]
    size_mb = csv_path.stat().st_size / (1024 * 1024)
    print(f"    Extracted: {csv_names[0]} ({size_mb:.1f} MB)")
    return csv_path


def detect_separator(csv_path: Path) -> str:
    """Auto-detect CSV separator from the first line.

    Comext files have historically used comma, but some
    older versions used tab or semicolon.
    """
    with open(csv_path, "r", encoding="utf-8") as f:
        header = f.readline()

    if "\t" in header:
        return "\t"
    if ";" in header:
        return ";"
    return ","


def filter_csv(
    csv_path: Path,
    cn8_codes: frozenset,
    year: int,
) -> list:
    """Stream-filter a Comext bulk CSV, returning rows matching our criteria.

    Returns list of dicts with ISI-internal column names.
    """
    print(f"  Filtering: {csv_path.name} for year {year}")

    sep = detect_separator(csv_path)

    total_rows = 0
    kept_rows = 0
    dropped_flow = 0
    dropped_stat_proc = 0
    dropped_reporter = 0
    dropped_product = 0
    dropped_partner = 0
    dropped_value = 0
    zero_value = 0

    results = []

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=sep)

        # Validate required columns exist
        if reader.fieldnames is None:
            print(f"FATAL: could not read header from {csv_path.name}", file=sys.stderr)
            sys.exit(1)

        missing = [c for c in REQUIRED_BULK_COLUMNS if c not in reader.fieldnames]
        if missing:
            print(f"FATAL: missing columns in {csv_path.name}: {missing}", file=sys.stderr)
            print(f"  Found columns: {reader.fieldnames}", file=sys.stderr)
            sys.exit(1)

        print(f"    Columns ({len(reader.fieldnames)}): {reader.fieldnames[:7]}...")
        print(f"    Separator: {repr(sep)}")

        for row in reader:
            total_rows += 1

            # Print progress every 2M rows
            if total_rows % 2_000_000 == 0:
                print(f"    ... {total_rows:,} rows scanned, {kept_rows:,} kept")

            # ── Flow filter: imports only ────────────────────
            flow = row[BULK_COL_FLOW].strip()
            if flow != FLOW_IMPORT:
                dropped_flow += 1
                continue

            # ── Stat procedure filter: normal only ───────────
            stat_proc = row[BULK_COL_STAT_PROC].strip()
            if stat_proc != STAT_PROCEDURE_NORMAL:
                dropped_stat_proc += 1
                continue

            # ── Reporter filter: EU-27 only ──────────────────
            reporter = row[BULK_COL_REPORTER].strip()
            if reporter not in EU27_REPORTERS:
                dropped_reporter += 1
                continue

            # ── Product filter: our 66 CN8 codes ─────────────
            product = row[BULK_COL_PRODUCT].strip()
            if product not in cn8_codes:
                dropped_product += 1
                continue

            # ── Partner filter: drop confidential ─────────────
            partner = row[BULK_COL_PARTNER].strip()
            if partner in DROP_PARTNERS:
                dropped_partner += 1
                continue

            # ── Value parsing ─────────────────────────────────
            value_str = row[BULK_COL_VALUE].strip()
            if value_str in ("", ":", "c"):
                value_str = "0"

            try:
                value = float(value_str)
            except (ValueError, TypeError):
                dropped_value += 1
                continue

            if value < 0:
                dropped_value += 1
                continue

            if value == 0:
                zero_value += 1

            # ── Apply remappings ──────────────────────────────
            declarant = GEO_REMAP.get(reporter, reporter)

            # Period: bulk uses YYYY52 for annual, we output YYYY
            period_raw = row[BULK_COL_PERIOD].strip()
            period = PERIOD_REMAP.get(period_raw, str(year))

            results.append({
                "DECLARANT_ISO": declarant,
                "PARTNER_ISO": partner,
                "PRODUCT_NC": product,
                "FLOW": "1",
                "PERIOD": period,
                "VALUE_IN_EUROS": str(int(value)) if value == int(value) else str(value),
            })
            kept_rows += 1

    # ── Audit ─────────────────────────────────────────────────
    print(f"    Scan complete: {total_rows:,} total rows")
    print(f"    Kept:          {kept_rows:,}")
    print(f"    Dropped flow:  {dropped_flow:,}")
    print(f"    Dropped proc:  {dropped_stat_proc:,}")
    print(f"    Dropped geo:   {dropped_reporter:,}")
    print(f"    Dropped prod:  {dropped_product:,}")
    print(f"    Dropped partn: {dropped_partner:,}")
    print(f"    Dropped value: {dropped_value:,}")
    print(f"    Zero-value:    {zero_value:,}")

    return results


# ═════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print("ISI v0.1 — Axis 5: Critical Inputs Data Acquisition")
    print("=" * 64)
    print()

    # ── 0. Load mapping ──────────────────────────────────────
    cn8_codes = load_mapping_codes()
    print(f"Mapping loaded: {len(cn8_codes)} CN8 codes")
    print()

    # ── 1. Download annual files ─────────────────────────────
    print("Stage 1: Download")
    print("-" * 40)
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for year, filename in sorted(ANNUAL_FILES.items()):
        dest = DOWNLOAD_DIR / filename
        download_file(filename, dest)
        time.sleep(RATE_LIMIT_DELAY)

    print()

    # ── 2. Extract and filter ────────────────────────────────
    print("Stage 2: Extract & Filter")
    print("-" * 40)

    all_rows = []
    extract_base = DOWNLOAD_DIR / "extracted"
    extract_base.mkdir(parents=True, exist_ok=True)

    for year, filename in sorted(ANNUAL_FILES.items()):
        archive = DOWNLOAD_DIR / filename
        if not archive.exists():
            print(f"FATAL: archive not found: {archive}", file=sys.stderr)
            sys.exit(1)

        year_dir = extract_base / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)

        csv_path = extract_7z(archive, year_dir)
        rows = filter_csv(csv_path, cn8_codes, year)
        all_rows.extend(rows)
        print()

    # ── 3. Write consolidated output ─────────────────────────
    print("Stage 3: Write Output")
    print("-" * 40)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    output_size = OUTPUT_FILE.stat().st_size
    output_hash = sha256_file(OUTPUT_FILE)

    print(f"  Output: {OUTPUT_FILE}")
    print(f"  Rows:   {len(all_rows):,}")
    print(f"  Size:   {output_size:,} bytes")
    print(f"  SHA256: {output_hash[:32]}...")
    print()

    # ── 4. Summary ───────────────────────────────────────────
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)

    # Count unique values
    reporters = set()
    partners = set()
    products = set()
    periods = set()
    total_value = 0.0

    for row in all_rows:
        reporters.add(row["DECLARANT_ISO"])
        partners.add(row["PARTNER_ISO"])
        products.add(row["PRODUCT_NC"])
        periods.add(row["PERIOD"])
        try:
            total_value += float(row["VALUE_IN_EUROS"])
        except (ValueError, TypeError):
            pass

    print(f"  Total rows:       {len(all_rows):,}")
    print(f"  Unique reporters: {len(reporters)} {sorted(reporters)}")
    print(f"  Unique partners:  {len(partners)}")
    print(f"  Unique CN8 codes: {len(products)}/66")
    print(f"  Periods:          {sorted(periods)}")
    print(f"  Total value (EUR):{total_value:,.0f}")
    print()

    # ── Coverage cross-check ─────────────────────────────────
    missing_cn8 = cn8_codes - products
    if missing_cn8:
        print(f"  WARNING: {len(missing_cn8)} CN8 codes from mapping have NO data:")
        for code in sorted(missing_cn8):
            print(f"    {code}")
    else:
        print(f"  All 66 CN8 codes have data: OK")

    expected_reporters = frozenset([
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE",
        "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT",
        "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO",
        "SE", "SI", "SK",
    ])
    missing_reporters = expected_reporters - reporters
    if missing_reporters:
        print(f"  WARNING: {len(missing_reporters)} EU-27 reporters missing:")
        for geo in sorted(missing_reporters):
            print(f"    {geo}")
    else:
        print(f"  All 27 EU reporters present: OK")

    print()
    print("=" * 64)
    print("Data acquisition complete.")
    print(f"Next step: python scripts/ingest_critical_inputs_comext_manual.py")
    print("=" * 64)


if __name__ == "__main__":
    main()
