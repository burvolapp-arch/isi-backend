# Critical Inputs / Raw Materials Dependency Axis — v0.1
# Data Acquisition: SDMX Assessment & Bulk Download Strategy

Status: REFERENCE
Date: 2026-02-08
Axis: Critical Inputs / Raw Materials Dependency (Axis 5)
Project: Panargus / International Sovereignty Index (ISI)

---

## Section 1: SDMX Mechanics for DS-045409 — What Actually Works

### 1.1 The Hard Truth: DS-045409 Is Not on the SDMX API

DS-045409 (EU trade since 1988 by HS2-4-6 and CN8) is
**not available** via either Eurostat dissemination API.

Verified 2026-02-08 against both endpoints:

```
# SDMX 2.1 endpoint — returns ERR_NOT_FOUND_4
GET https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/dataflow/ESTAT/DS-045409
→ faultstring: "DS-045409 (DATA_FLOW:ESTAT,*) is not available for dissemination."

# JSON/CSV statistics API — returns 404
GET https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/DS-045409
→ {"error": [{"status": 404, "id": 100,
   "label": "ERR_NOT_FOUND_4: DS-045409 (DATA_FLOW:ALL,1.0) is not available for dissemination."}]}

# Data Structure Definition — also not found
GET https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/datastructure/ESTAT/DS-045409
→ faultstring: "DS-045409 (DATA_STRUCTURE:ESTAT,*) is not available for dissemination."
```

This is not a bug. Comext detailed trade data has **never**
been exposed via the standard Eurostat SDMX dissemination
API. The `DS-*` namespace is a Comext-internal identifier.
Only aggregated statistical tables (e.g. `ext_lt_maineu`,
`nama_10_gdp`) are available via SDMX.

### 1.2 Easy Comext Web Application

The Easy Comext application at
`https://ec.europa.eu/eurostat/comext/newxtweb/` provides
interactive data extraction but:

- Has a 750,000-cell hard limit per query
- Infinite-loads on large CN8 × partner × year queries
- Has no documented REST API for programmatic access
- The `setupdataextraction.do` endpoint returns server
  errors when called without a browser session
- Requires EU Login (ECAS) authentication for some
  features

This path is unusable for our scope (66 CN8 codes ×
27 reporters × ~240 partner countries × 3 years × 2
trade types).

### 1.3 The Eurostat Data Browser

The Data Browser at
`https://ec.europa.eu/eurostat/databrowser/view/ds-045409/`
renders a JavaScript SPA that cannot be scraped
programmatically. It also enforces the same cell limits.

### 1.4 What Actually Works: Comext Bulk Download Facility

The only reliable programmatic access to CN8-level
bilateral trade data is the **Comext Bulk Download
Facility**, which provides pre-built monthly and annual
files via a directory-listing HTTP endpoint:

```
Base URL: https://ec.europa.eu/eurostat/api/dissemination/files/
Comext root: ?sort=1&dir=comext/COMEXT_DATA/PRODUCTS
Direct file: ?file=comext/COMEXT_DATA/PRODUCTS/<filename>
```

No authentication required. No rate limits documented.
Standard HTTP GET downloads. Files are `.7z` compressed.

### 1.5 Bulk Download File Format (v2, December 2024+)

As of December 2024, Eurostat transitioned to v2 format.
The v1 format files (without `_v2_` in the name) were
maintained in parallel until February 2025 and have since
been removed for periods after 2001.

#### File naming convention

```
full_v2_YYYYMM.7z          — Full data (intra + extra EU), all products
full_partxixu_v2_YYYYMM.7z — Extra-EU only (smaller, ~2 MB)
```

Where MM:
- 01–12: monthly data for that month
- 52: **annual aggregation** (sum of all 12 months)

#### v2 column schema (17 columns)

| # | Column               | Type    | Description                                           |
|---|----------------------|---------|-------------------------------------------------------|
| 1 | REPORTER             | string  | Reporter country (ISO alpha-2 for Comext)             |
| 2 | PARTNER              | string  | Partner country (ISO alpha-2)                         |
| 3 | TRADE_TYPE           | string  | I=Intra-EU, E=Extra-EU, L/M=UK special               |
| 4 | PRODUCT_NC           | string  | CN8 product code (8 digits, 'X' for special)          |
| 5 | PRODUCT_SITC         | string  | SITC Rev.4 code                                       |
| 6 | PRODUCT_CPA21        | string  | CPA 2.1 code                                          |
| 7 | PRODUCT_BEC          | string  | BEC Rev.4 code                                        |
| 8 | PRODUCT_BEC5         | string  | BEC Rev.5 code                                        |
| 9 | PRODUCT_SECTION      | string  | CN Section (Roman numeral)                            |
|10 | FLOW                 | integer | 1=Import, 2=Export                                    |
|11 | STAT_PROCEDURE       | integer | 1=Normal, 2=Inward proc, 3=Outward proc, 9=Not rec.  |
|12 | SUPPL_UNIT           | string  | Supplementary unit code                               |
|13 | PERIOD               | integer | YYYYMM (monthly) or YYYY52 (annual)                   |
|14 | VALUE_EUR            | integer | Trade value in euros                                  |
|15 | VALUE_NAC            | integer | Trade value in national currency                      |
|16 | QUANTITY_KG          | integer | Quantity in kilograms                                 |
|17 | QUANTITY_SUPPL_UNIT  | integer | Quantity in supplementary units                       |

**Critical naming difference**: The v2 bulk files use
`REPORTER` and `PARTNER` (not `DECLARANT_ISO` and
`PARTNER_ISO`), and `VALUE_EUR` (not `VALUE_IN_EUROS`).
The column `PERIOD` uses `YYYY52` for annual data (not
just `YYYY`).

#### REPORTER codes in v2 bulk files

The v2 format uses the Comext-internal REPORTER codes
which are **ISO alpha-2** for current EU members. The
correspondence with our EU-27 set:

| Comext REPORTER | Country          | ISI geo code |
|-----------------|------------------|--------------|
| AT              | Austria          | AT           |
| BE              | Belgium          | BE           |
| BG              | Bulgaria         | BG           |
| CY              | Cyprus           | CY (600)     |
| CZ              | Czechia          | CZ           |
| DE              | Germany          | DE           |
| DK              | Denmark          | DK           |
| EE              | Estonia          | EE           |
| ES              | Spain            | ES           |
| FI              | Finland          | FI           |
| FR              | France           | FR           |
| GR              | Greece           | GR → EL      |
| HR              | Croatia          | HR           |
| HU              | Hungary          | HU           |
| IE              | Ireland          | IE           |
| IT              | Italy            | IT           |
| LT              | Lithuania        | LT           |
| LU              | Luxembourg       | LU           |
| LV              | Latvia           | LV           |
| MT              | Malta            | MT           |
| NL              | Netherlands      | NL           |
| PL              | Poland           | PL           |
| PT              | Portugal         | PT           |
| RO              | Romania          | RO           |
| SE              | Sweden           | SE           |
| SI              | Slovenia         | SI           |
| SK              | Slovakia         | SK           |

**GR→EL mapping**: Comext uses `GR` for Greece.
The ISI standard code is `EL`. This mapping is
applied during parsing, not during ingestion.

#### FLOW values (verified from FLOW.txt metadata)

```
1  Import
2  Export
```

#### TRADE_TYPE values (verified from TRADE_TYPE.txt metadata)

```
I  Intra-EU Trade (excluding partner GB from Feb 2020)
E  Extra-EU Trade (excluding partner GB regardless of period)
L  Trade with partner XI (UK Northern Ireland) from Jan 2021
M  Trade with partner XU (UK excl. NI) from Jan 2021
```

For ISI purposes, ALL trade types are relevant. We need
both intra-EU and extra-EU imports to compute total
supplier concentration. A country that imports cerium
oxide from Germany (intra-EU, TRADE_TYPE=I) is still
dependent on Germany.

#### STAT_PROCEDURE values (verified from STATISTICAL_PROCEDURES.txt)

```
1  Normal (standard customs declaration)
2  Inward processing (since 2010)
3  Outward processing
9  Not recorded from customs declarations (since 2010)
```

For ISI v0.1, we use `STAT_PROCEDURE = 1` (Normal) only.
Inward/outward processing creates double-counting risk
(goods temporarily imported for processing and
re-exported). This is a conservative choice.

---

## Section 2: API Slicing Strategy

### 2.1 Why Bulk Download Works Where SDMX Fails

The Eurostat SDMX API is designed for pre-aggregated
statistical tables. Comext CN8-level bilateral data is
too granular — it contains ~10 million rows per month
across all products, reporters, and partners.

The bulk download facility sidesteps this by providing
pre-built compressed files. Each annual file
(`full_v2_YYYY52.7z`) is ~93 MB compressed and contains
the complete annual bilateral trade data for ALL
products, ALL reporters, ALL partners, ALL flows, ALL
statistical procedures.

### 2.2 Download Strategy: Annual Files Only

We download exactly 3 files:

| File                      | Size (7z) | Content                    |
|---------------------------|-----------|----------------------------|
| full_v2_202252.7z         | 93.33 MB  | All 2022 annual trade data |
| full_v2_202352.7z         | 92.26 MB  | All 2023 annual trade data |
| full_v2_202452.7z         | 92.52 MB  | All 2024 annual trade data |

Why annual (52) files, not monthly?

1. Our methodology aggregates across the full 3-year
   window. Monthly granularity is not needed.
2. Annual files are pre-summed by Eurostat — no risk of
   double-counting from our side.
3. 3 downloads instead of 36.
4. Each annual file is ~93 MB compressed. Decompressed,
   each CSV is ~500-700 MB — still very manageable.

### 2.3 Post-Download Filtering

Each annual file contains ALL products (~10,000 CN8
codes). We filter at parse time:

- PRODUCT_NC ∈ {66 CN8 codes from mapping}
- FLOW = 1 (Import)
- STAT_PROCEDURE = 1 (Normal)
- REPORTER ∈ EU-27 set (excluding aggregates)
- PARTNER: keep ALL individual countries (this is the
  bilateral resolution needed for HHI)

This reduces ~10 million rows per file to roughly
~50,000–100,000 rows per year (27 reporters × 66
products × ~30-50 active partners per combination).

### 2.4 Why This Avoids the 750k-Cell Limitation

The 750k-cell limit is enforced by the Easy Comext and
Data Browser web applications, which paginate query
results. The bulk download facility has no such limit —
each file is a complete, pre-built CSV.

We download the entire universe and filter locally.
This is:
- Faster than paginated API queries
- More reliable (no pagination bugs, no session timeouts)
- Reproducible (files are versioned by date)
- Auditable (SHA-256 hash of each download)

### 2.5 Partner-Country Resolution

The bulk files contain individual ISO alpha-2 partner
codes for every country in the world (~240 active
countries). No aggregation is applied — each row
represents a bilateral reporter→partner trade flow for
one product, one statistical procedure, one period.

Special partner codes in the data:

| Code | Meaning                                          | Action    |
|------|--------------------------------------------------|-----------|
| QQ   | Stores and provisions                            | DROP      |
| QR   | Stores and provisions (intra-EU)                 | DROP      |
| QS   | Stores and provisions (extra-EU)                 | DROP      |
| QU   | Countries not determined                         | DROP      |
| QV   | Not specified (intra-EU)                          | DROP      |
| QW   | Not specified (extra-EU)                          | DROP      |
| QX   | Not specified (military/commercial reasons)      | DROP      |
| QY   | Secret countries (intra-EU)                       | DROP      |
| QZ   | Secret countries (extra-EU)                       | DROP      |
| QP   | High seas                                        | DROP      |

All Q-prefixed partner codes represent confidential,
unallocated, or non-geographic trade. They are dropped
during parsing. This is standard Eurostat practice.

### 2.6 Missing and Confidential Values

In Comext bulk files, missing values appear as:

- Empty cells (no data reported)
- Zero values (reported as 0)
- `:` character (suppressed for confidentiality)

Our handling:
- Empty → treated as 0 (no import value)
- Zero → kept (real zero-value trade records exist)
- `:` → treated as 0 (confidential suppression;
  documented limitation)

Zero-value records are kept but flagged in the audit
summary. They typically represent trade relationships
where quantity was reported but value was suppressed,
or rounding to zero.

---

## Section 3: Full Python Ingestion Script

### 3.1 Script Architecture

The script performs three stages:
1. **Download** — Fetch 3 annual `.7z` files from
   Eurostat bulk download facility
2. **Extract** — Decompress to CSV
3. **Filter** — Stream-parse each CSV, extract only
   rows matching our 66 CN8 codes / EU-27 reporters /
   imports / normal procedure, write consolidated
   output CSV

The output CSV uses the column schema expected by the
existing ingest gate
(`ingest_critical_inputs_comext_manual.py`):

```
DECLARANT_ISO,PARTNER_ISO,PRODUCT_NC,FLOW,PERIOD,VALUE_IN_EUROS
```

This is a deliberate column-name translation from the
bulk download v2 format to the ISI-internal format
established by the methodology and ingest gate.

### 3.2 The Script

See: `scripts/download_critical_inputs_comext.py`

### 3.3 Dependencies

- Python 3.10+
- `httpx` (HTTP client with retry, timeout, HTTP/2)
- `py7zr` (pure-Python 7z decompression)

Both are pip-installable. No system-level dependencies.

### 3.4 Running

```bash
cd /path/to/Panargus-isi
pip install httpx py7zr
python scripts/download_critical_inputs_comext.py
```

The script is idempotent. If a `.7z` file already exists
and matches the expected size, it is not re-downloaded.
If the output CSV already exists, it is overwritten
(fresh build on each run).

---

## Section 4: Validation Checklist

### 4.1 Download Validation

| Check                                    | Expected                          |
|------------------------------------------|-----------------------------------|
| 3 files downloaded                       | full_v2_2022/23/2452.7z           |
| Each file >50 MB compressed              | ~92-93 MB each                    |
| HTTP status 200 for all downloads        | No 404, 500, or timeout           |
| SHA-256 hashes logged                    | Reproducibility audit trail       |

### 4.2 Extraction Validation

| Check                                    | Expected                          |
|------------------------------------------|-----------------------------------|
| Each 7z decompresses without error       | CRC check passes                  |
| CSV inside 7z has 17 columns             | v2 schema                         |
| Header row matches expected column names | REPORTER,PARTNER,...              |
| Total rows per file >5 million           | Typical annual file               |

### 4.3 Filter Validation

| Check                                    | Expected                          |
|------------------------------------------|-----------------------------------|
| Output CSV has 6 columns                 | ISI internal schema               |
| All PRODUCT_NC values are 8-digit        | No 2/4/6-digit codes              |
| All PRODUCT_NC in mapping (66 codes)     | No extra codes leaked             |
| All 66 mapping codes present in output   | Complete coverage                 |
| FLOW = 1 everywhere                      | Imports only                      |
| All DECLARANT_ISO ∈ EU-27 (incl GR→EL)  | 27 unique reporters               |
| PERIOD ∈ {202252, 202352, 202452}        | Annual periods only               |
| No Q-prefix partners in output           | Confidential partners dropped     |
| VALUE_IN_EUROS all numeric               | No `:` or empty strings           |
| Zero-value rows counted but kept         | Audit trail                       |

### 4.4 Downstream Compatibility

| Check                                    | Expected                          |
|------------------------------------------|-----------------------------------|
| ingest_critical_inputs_comext_manual.py   | PASS on output CSV                |
| Column names match ingest expectations   | DECLARANT_ISO, etc.               |
| PERIOD values pass temporal validation   | 2022, 2023, 2024 (after mapping)  |

### 4.5 Known Limitations

1. Annual files are published with a lag. The 2024
   annual file (full_v2_202452.7z) may not contain
   December 2024 data until ~March 2025. As of Feb
   2026, all 2024 data should be final.

2. Confidential trade flows (`:` values) are treated
   as zero. This may undercount imports for sensitive
   defense materials. This is a documented limitation
   of all Comext-based analyses.

3. The v2 format transition (Dec 2024) changed column
   names. The script handles v2 only. v1 files (pre-
   2002 data) use a different schema and are not
   relevant to our 2022-2024 scope.

4. Greece appears as `GR` in Comext REPORTER column.
   The script maps this to `EL` for ISI consistency.
   Both codes refer to the same country.

5. STAT_PROCEDURE filtering to `1` (Normal) excludes
   inward processing imports. For some materials
   (e.g., titanium for aerospace processing), this
   may undercount total import dependency. This is
   the conservative choice for v0.1.
