# ISI Global Data Ingestion Pipeline — Architecture Reference

**Version:** 1.1 (hardened)
**Last updated:** 2026-03

## 1. Pipeline Layers

```
RAW → STAGING → VALIDATED → META
```

| Layer       | Path                  | Purpose                                     |
|-------------|-----------------------|---------------------------------------------|
| RAW         | `data/raw/`           | Untouched source files, API cache           |
| STAGING     | `data/staging/`       | Normalized `BilateralRecord` lists          |
| VALIDATED   | `data/validated/`     | Records that passed all 12 validation checks|
| META        | `data/meta/`          | Pipeline audit trails, run summaries        |
| AUDIT       | `data/audit/pipeline/`| Per-country pipeline execution logs         |

## 2. Module Map

| Module                   | Role                                          | Lines |
|--------------------------|-----------------------------------------------|-------|
| `pipeline/config.py`     | Central configuration, ALL constants          | ~596  |
| `pipeline/status.py`     | Canonical status enums (3 enums)              | ~98   |
| `pipeline/schema.py`     | `BilateralRecord` + `BilateralDataset`        | ~308  |
| `pipeline/normalize.py`  | Country code normalization, aggregate filter  | ~371  |
| `pipeline/validate.py`   | 12 structural + economic validation checks    | ~745  |
| `pipeline/orchestrator.py`| Multi-axis pipeline orchestration            | ~426  |
| `pipeline/ingest/comtrade.py` | UN Comtrade API + CSV ingestion          | ~651  |
| `pipeline/ingest/bis_lbs.py`  | BIS Locational Banking Statistics        | ~403  |
| `pipeline/ingest/imf_cpis.py` | IMF CPIS investment positions            | ~344  |
| `pipeline/ingest/sipri.py`    | SIPRI arms transfers                     | ~627  |
| `pipeline/ingest/logistics.py`| Eurostat freight (maritime/rail/road/IWW)| ~451  |

## 3. Status Taxonomy

### IngestionStatus (pipeline/status.py)

| Value                      | Meaning                                              |
|----------------------------|------------------------------------------------------|
| `OK`                       | Data ingested successfully                           |
| `WARNING`                  | Data ingested with caveats                           |
| `NO_DATA`                  | Source has no data for this reporter/period           |
| `EMPTY`                    | File/response exists but contains no usable records  |
| `FILE_NOT_FOUND`           | Expected raw file does not exist                     |
| `API_FAILED`               | API request failed (network, auth, rate limit)       |
| `API_EMPTY`                | API returned success but no data                     |
| `NO_REPORTER_CODE`         | Cannot resolve reporter to source-specific code      |
| `UNMAPPED_REPORTER`        | Reporter code not in source mapping                  |
| `STRUCTURAL_LIMITATION`    | Source genuinely cannot cover this reporter           |
| `IMPLEMENTATION_LIMITATION`| Data exists but pipeline doesn't yet download it     |
| `EXCEPTION`                | Unhandled exception during ingestion                 |
| `NO_BILATERAL_DATA`        | Source exists but has no bilateral partner dimension  |

### ValidationStatus

| Value     | Meaning                        |
|-----------|--------------------------------|
| `PASS`    | All checks passed              |
| `WARNING` | Passed with caveats            |
| `FAIL`    | One or more checks failed      |
| `PENDING` | Not yet validated              |

### AxisStatus

| Value                      | Meaning                                       |
|----------------------------|-----------------------------------------------|
| `PASS`                     | Axis fully operational                        |
| `WARNING`                  | Axis operational with caveats                 |
| `FAILED`                   | Axis failed validation                        |
| `STRUCTURAL_LIMITATION`    | No source covers this axis for this reporter  |
| `IMPLEMENTATION_LIMITATION`| Source exists but not yet connected            |
| `NO_DATA`                  | No data available for this axis                |

## 4. Axis Registry

| ID | Slug             | Channel A       | Channel B     | Sources                    |
|----|------------------|-----------------|---------------|----------------------------|
| 1  | financial        | BIS LBS         | IMF CPIS      | bis_lbs, imf_cpis          |
| 2  | energy           | UN Comtrade     | UN Comtrade   | un_comtrade, eurostat_nrg  |
| 3  | technology       | UN Comtrade     | UN Comtrade   | un_comtrade, eurostat_comext|
| 4  | defense          | SIPRI           | SIPRI         | sipri                      |
| 5  | critical_inputs  | UN Comtrade     | UN Comtrade   | un_comtrade, eurostat_comext|
| 6  | logistics        | national_stats  | national_stats| oecd_logistics, national_stats|

## 5. Country Code Convention

**Canonical standard:** ISO 3166-1 alpha-2

| Convention     | Used by          | Greece | UK  | Handling                       |
|----------------|------------------|--------|-----|--------------------------------|
| ISO-3166 (canonical) | Pipeline   | GR     | GB  | All pipeline code uses this    |
| Eurostat       | Raw Eurostat data| EL     | UK  | `EUROSTAT_TO_ISO2` adapter     |
| Backend v01    | Shipped API      | EL     | —   | Legacy, will migrate in v02    |

The `EUROSTAT_TO_ISO2` mapping in `config.py` normalizes Eurostat conventions
to ISO standard at the ingestion boundary.

## 6. Validation Engine (12 Checks)

1. **Schema compliance** — all required fields present and typed correctly
2. **Self-trade detection** — reporter ≠ partner
3. **Aggregate detection** — rejects World, Other, Total, etc. with mass tracking
4. **Sum integrity** — value sum > 0
5. **Partner count** — minimum bilateral partners (source-aware thresholds)
6. **Dominance / extreme concentration** — no single partner > threshold
7. **Missing key partners** — expected trade partners present
8. **Duplicate records** — no duplicate reporter-partner-year tuples
9. **Year coverage** — data spans expected year range
10. **Economic sanity** — plausible totals, expected partners for major economies
11. **Coverage ratio** — top-10 partner share within expected bounds
12. **Defense plausibility** — scope-aware concentration annotation for defense axis

## 7. Data Flow

```
Source API/File → ingest_*(reporter) → list[BilateralRecord]
                                           ↓
                              normalize_records(records, source, axis)
                                           ↓
                                    BilateralDataset
                                           ↓
                              validate_dataset(dataset)
                                           ↓
                              PASS → VALIDATED layer
                              FAIL → rejected + audit log
```

## 8. Shared Infrastructure

| Function                          | Module          | Used by              |
|-----------------------------------|-----------------|----------------------|
| `is_aggregate_partner(partner)`   | normalize.py    | All ingestion modules|
| `normalize_country_code(code)`    | normalize.py    | normalize_records()  |
| `normalize_records(records, ...)`  | normalize.py    | All ingestion modules|
| `validate_dataset(dataset)`       | validate.py     | orchestrator.py      |

## 9. Consistency Guarantee (Task 12)

The test suite includes architectural invariant tests (`TestPipelineConsistencyGuarantee`)
that prevent regression on all hardening work:

| Test | Enforces |
|------|----------|
| `test_all_axes_have_ingestion_functions` | Every axis in AXIS_REGISTRY has orchestrator mapping |
| `test_all_ingestion_functions_callable` | No dead references in AXIS_INGEST_MAP |
| `test_status_enums_are_str_subclass` | Enums are `(str, Enum)` for safe `==` comparison |
| `test_acceptable_statuses_complete` | ACCEPTABLE_STATUSES covers all non-failure states |
| `test_no_string_status_literals_in_pipeline_modules` | **Scan** — no raw `"OK"`, `"NO_DATA"`, etc. in pipeline code |
| `test_eu27_iso2_uses_gr_not_el` | Greece is "GR" not "EL" in pipeline |
| `test_eurostat_adapter_exists` | EUROSTAT_TO_ISO2 adapter maps EL→GR, UK→GB |
| `test_all_isi_countries_have_iso2` | All ISI countries are valid 2-char ISO codes |
| `test_ingestion_modules_import_status_enum` | Every `ingest/*.py` imports from `pipeline.status` |
| `test_axis_registry_has_required_fields` | Every axis has slug, sources |

These tests run on every `pytest` invocation. Any future change that breaks
architectural invariants will fail immediately.

## 10. SIPRI Arms Transfers — Data Lineage

### Raw Data
| Field               | Value                                            |
|---------------------|--------------------------------------------------|
| File                | `data/raw/sipri/trade-register.csv`              |
| Encoding            | UTF-8 (ASCII text)                               |
| Preamble lines      | 11 (skipped)                                     |
| Columns             | 17                                               |
| Data rows           | 5532                                             |
| Recipients          | 172 unique names (global coverage)               |
| Suppliers           | 69 unique names (global coverage)                |
| TIV unit            | Millions (SIPRI Trend Indicator Values)           |
| Delivery years      | 2020–2025                                        |
| Manifest            | `data/meta/sipri_manifest.json`                  |

### Deprecated File
| Field               | Value                                            |
|---------------------|--------------------------------------------------|
| File                | `data/raw/sipri/sipri_trade_register_2019_2024.csv` |
| Status              | **DEPRECATED** — not used by pipeline            |
| Encoding            | Latin-1                                          |
| Data rows           | 426 (EU-27 only, 2019–2024)                     |

### Ingestion Flow
1. **Manifest verification** — SHA-256 hash check against `sipri_manifest.json`
2. **Schema enforcement** — 4 required columns verified (Recipient, Supplier, Delivery year, TIV delivery values) with alias support for old column names
3. **Country resolution** — `SIPRI_TO_ISO2` mapping (174 entries: Turkiye, UAE, Viet Nam, eSwatini, non-state actors, etc.)
4. **Non-state filtering** — Entities mapped to `__NONSTATE__` (NATO\*\*, Hezbollah, Houthi rebels, etc.) are dropped with audit
5. **Year window** — `SIPRI_YEAR_RANGE` from config (delivery years 2020–2025)
6. **Self-trade guard** — Rows where supplier == recipient are dropped
7. **TIV distribution** — split equally across delivery years per order (single-year in global register)
8. **Normalization** — standard `normalize_records()` pipeline
9. **No coverage guard** — Global register covers ALL countries (EU-27-only guard removed)

### Partial Year Handling
The latest year in `SIPRI_YEAR_RANGE` (2025) may have incomplete data.
`SIPRI_LATEST_YEAR_PARTIAL = True` flags this in ingestion stats.
Stats include `partial_year_risk: true` and explanatory note.

### Country Name Variants
| SIPRI name           | ISO-2             | Note                              |
|----------------------|-------------------|-----------------------------------|
| Turkiye              | TR                | Turkey renamed 2022               |
| Turkey               | TR                | Pre-2022 name                     |
| UAE                  | AE                | Abbreviation                      |
| Viet Nam             | VN                | SIPRI spelling                    |
| eSwatini             | SZ                | Formerly Swaziland                |
| DR Congo             | CD                | Democratic Republic of Congo      |
| unknown supplier(s)  | __UNKNOWN__       | Dropped — unresolvable entity     |
| NATO**               | __MULTINATIONAL__ | Dropped — intergovernmental org   |
| African Union**      | __MULTINATIONAL__ | Dropped — intergovernmental org   |
| United Nations**     | __MULTINATIONAL__ | Dropped — intergovernmental org   |
| Hezbollah (Lebanon)* | __NONSTATE__      | Dropped — armed non-state actor   |
| Houthi rebels (Yemen)* | __NONSTATE__    | Dropped — armed non-state actor   |
| RSF (Sudan)*         | __NONSTATE__      | Dropped — armed non-state actor   |

### Entity Classification (Three-Way)
Non-sovereign entities in SIPRI data are classified into three categories
for audit transparency:

- **MULTINATIONAL** (`__MULTINATIONAL__`): Intergovernmental organizations
  with recognized legal status (NATO, AU, UN). Dropped because they lack
  a single ISO-2 sovereign code, but their procurement represents
  legitimate state-backed activity.
- **NONSTATE** (`__NONSTATE__`): Armed non-state actors and sub-national
  factions (Hezbollah, Houthis, RSF). Dropped because they are not
  sovereign entities.
- **UNKNOWN** (`__UNKNOWN__`): Unresolvable entities in SIPRI data.

All three categories are dropped from ISI computation. Each is tracked
separately in ingestion statistics (`entity_classification` dict in stats).

### Test Coverage
`tests/test_sipri_ingestion.py` — comprehensive tests covering:
- Mapping completeness (12+ tests: Turkiye, UAE, non-state entities, etc.)
- Manifest verification (6 tests)
- Schema enforcement (3 tests with alias support)
- Year window filtering (2 tests)
- Partial year metadata (2 tests)
- TIV parsing edge cases (8 tests)
- Delivery year parsing (6 tests)
- Country resolution including non-state (7+ tests)
- Canonical file infrastructure (4 tests)
- Synthetic end-to-end ingestion (8+ tests)
- Real data integration: Japan, Germany, France (10+ tests)
- Non-state entity handling (3+ tests)
- Global coverage verification (2+ tests)

`tests/test_methodological_hardening.py` — 46 tests covering:
- Defense axis interpretation hardening (7 tests)
- Time window discipline (6 tests)
- Non-state entity three-way classification (8 tests)
- Cross-axis comparability metadata (7 tests)
- Output interpretation safeguards (3 tests)
- Defense validation sanity check (5 tests)
- SIPRI ingestion final hardening (4 tests)
- Documentation existence (2 tests)
- No-overbuild constraint (3 tests)
- Axis constraints propagation through composite (2 tests)

## 11. Known Limitations

**This section is honest. No marketing language. No hedging.**

### 11.1 Defense Axis (SIPRI) — Structural Scope Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **SIPRI covers only major conventional weapons** | Small arms, ammunition, dual-use technology, cyber, services, training, and MRO contracts are EXCLUDED. The defense axis measures only a partial slice of military supply chain dependency. | `axis_constraints.exclusions` lists all excluded categories. Every defense output carries this disclaimer. |
| **TIV is NOT a monetary value** | SIPRI's Trend Indicator Value measures military capability transferred, based on production cost of a core weapon set. TIV cannot be compared to USD trade values on other axes. | `value_type=TIV_MN` is explicit in every defense output. `interpretation_note` warns against cross-axis comparison. |
| **Arms procurement is inherently lumpy** | A single multi-billion fighter jet order can dominate a 6-year window. Year-to-year volatility reflects delivery schedules, not changing dependency. | `window_type=rolling_delivery_window`, `temporal_sensitivity=high` encoded in axis metadata. |
| **High concentration is structurally normal** | Most countries import major weapons from 2-6 suppliers. Japan's 95% US concentration is normal within SIPRI scope, not a data quality failure. | `check_defense_plausibility()` annotates (does not fail) extreme concentration with scope context. |
| **Licensed production partially captured** | SIPRI tracks some licensed production but the Local Production flag is inconsistent across entries. | Acknowledged as limitation; no workaround in current version. |

### 11.2 Cross-Axis Comparability

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **Different value types across axes** | Defense=TIV, Trade=USD, Logistics=mixed. The ISI composite averages HHI scores derived from incommensurable units. | Each axis carries `value_type` and `interpretation_note` in `axis_constraints`. Composite output includes per-axis metadata. |
| **Different temporal windows** | Financial=snapshot, Trade=annual flow, Defense=6-year rolling. Time semantics differ across axes. | `window_type` and `window_semantics` encoded per axis. |
| **Different confidence baselines** | Defense has lower inherent data reliability (confidence_baseline=0.55) than trade axes (0.75-0.80). | `confidence_baseline` per axis feeds severity model. |

### 11.3 Data Source Coverage Gaps

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **BIS LBS: ~30 reporting countries** | Partner universe is structurally limited for the financial axis. Non-reporting countries appear as zero. | `SOURCE_PARTNER_COUNT_OVERRIDE` adjusts validation thresholds. |
| **IMF CPIS: ~80 participants** | Missing for many non-OECD countries. Eliminates Channel B for financial axis. | `CPIS_NON_PARTICIPANT` flag with severity weight 0.5. |
| **Logistics: no non-EU bilateral source** | Logistics axis is EU-only in current implementation. | `STRUCTURAL_LIMITATION` status for non-EU countries. |
| **SIPRI 2025 partial year** | 2025 deliveries may be incomplete (SIPRI updates continuously). | `partial_year_risk=True` in stats; `partial_year_note` explains. |

### 11.4 Methodological Boundaries

| Boundary | Implication |
|----------|-------------|
| **ISI measures import concentration, not dependency** | High HHI = concentrated imports. Low HHI ≠ low dependency (may have domestic production). Producer-inverted countries have low import concentration but may still be strategically exposed. |
| **Composite is unweighted mean of 6 HHI scores** | No axis weighting by economic significance. A country with concentrated defense and diversified trade gets the same composite weight for both. |
| **4-axis minimum for composite** | Countries with <4 computable axes get no composite score. This is a hard cutoff, not a gradual degradation. |
| **No supply chain depth** | ISI captures only bilateral imports, not upstream supply chain dependencies (e.g., who makes the components of what a country imports). |

### 11.5 Non-State Entity Policy

All non-sovereign entities (multinational organizations, armed groups, unknown
recipients/suppliers) are dropped from ISI computation. This means:
- Arms transfers TO NATO (as an organization) are invisible in any member state's defense score.
- Arms flows involving sub-national actors are excluded entirely.
- This is a policy choice, not a data limitation. The ISI construct measures
  sovereign-to-sovereign bilateral concentration.

## 12. What ISI Does NOT Measure

This section exists to prevent misuse. ISI is a bilateral import concentration
index. It does NOT measure:

1. **Strategic vulnerability** — Concentration is one dimension of vulnerability, not the whole picture.
2. **Resilience** — Stockpiles, substitution capacity, and domestic production are excluded.
3. **Political intent** — Concentrated imports from an ally (US→Japan defense) have different risk profiles than from a rival.
4. **Future risk** — ISI is backward-looking (realized deliveries/trade), not predictive.
5. **Total defense capability** — SIPRI covers only major conventional weapons, not the full military supply chain.
6. **Absolute dependency levels** — ISI measures concentration (who), not volume (how much).
7. **Supply chain fragility** — Upstream dependencies and chokepoints are invisible.

Any interpretation of ISI scores that claims to measure the above is
methodologically unsound and not supported by this system.
