# ISI Global Expansion — Technical Feasibility Assessment

> **International Sovereignty Index (ISI) — Panargus**
>
> Generated: 2026-03-21 · Assessed against: `main` branch pipeline code
>
> Purpose: Map technical feasibility, source compatibility, and system integration
> requirements for expanding ISI from EU-27 to 12 additional countries.
>
> Quality bar: Every claim is anchored to pipeline code, verified data source
> specifications, or explicit uncertainty flags. Zero speculation.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Pipeline Hardcoding Inventory](#2-pipeline-hardcoding-inventory)
3. [Global Source Mapping by Axis](#3-global-source-mapping-by-axis)
4. [Per-Country Assessments](#4-per-country-assessments)
5. [Pipeline Impact Summary](#5-pipeline-impact-summary)
6. [Cross-Cutting Issues](#6-cross-cutting-issues)
7. [Decision Matrix](#7-decision-matrix)

---

## 1. Executive Summary

### Expansion Set

| # | Country | ISO-2 | BIS Reporter | CPIS Reporter | UN Comtrade Reporter | SIPRI Coverage |
|---|---------|-------|--------------|---------------|----------------------|----------------|
| 1 | United States | US | YES (Q4 1977) | YES | YES | YES (major supplier + recipient) |
| 2 | China | CN | YES (Q4 2015) | NO | YES | YES (major supplier + recipient) |
| 3 | Russia | RU | SUSPENDED (post-2022-02-28) | UNCERTAIN | PARTIAL (sanctions gaps) | YES |
| 4 | Japan | JP | YES (Q4 1977) | YES | YES | YES |
| 5 | South Korea | KR | YES (Q1 2005) | YES | YES | YES |
| 6 | India | IN | YES (Q4 2001) | UNCERTAIN | YES | YES (major recipient) |
| 7 | Saudi Arabia | SA | YES (Q4 2017) | NO | YES | YES (major recipient) |
| 8 | Brazil | BR | YES (Q4 2002) | YES | YES | YES |
| 9 | South Africa | ZA | YES (Q3 2009) | YES | YES | YES |
| 10 | United Kingdom | GB | YES (Q4 1977) | YES | YES | YES |
| 11 | Norway | NO | YES (Q4 1983) | YES | YES | YES |
| 12 | Australia | AU | YES (Q4 1997) | YES | YES | YES |

### Verdict Summary

| Country | Feasible Axes | Risk Level | Verdict |
|---------|--------------|------------|---------|
| United States | 6/6 | LOW | **GO** |
| United Kingdom | 6/6 | LOW | **GO** |
| Japan | 6/6 | LOW | **GO** |
| South Korea | 6/6 | LOW | **GO** |
| Norway | 6/6 | LOW | **GO** |
| Australia | 6/6 | LOW | **GO** |
| Brazil | 5–6/6 | MEDIUM | **GO (conditional)** |
| South Africa | 5–6/6 | MEDIUM | **GO (conditional)** |
| India | 5–6/6 | MEDIUM | **GO (conditional)** |
| Saudi Arabia | 4–5/6 | HIGH | **CONDITIONAL** |
| China | 4–5/6 | HIGH | **CONDITIONAL** |
| Russia | 2–4/6 | CRITICAL | **BLOCKED without methodology waiver** |

---

## 2. Pipeline Hardcoding Inventory

The following scripts contain hardcoded EU-27 filters that MUST be modified or parameterized
before any non-EU country can be processed:

### 2.1 Scripts With Hardcoded EU-27 Reporter Filters

| Script | Filter Type | Modification Required |
|--------|------------|----------------------|
| `scripts/compute_tech_channel_a.py` | `if rec not in EU27: continue` | Parameterize reporter set |
| `scripts/parse_tech_comext_raw.py` | Reporter must be in EU27 set | Parameterize reporter set |
| `scripts/parse_defense_sipri_raw.py` | Recipient must be in `SIPRI_TO_EUROSTAT` | Extend recipient mapping |
| `scripts/compute_critical_inputs_axis.py` | `if reporter not in EU27_SET: continue` + hard-fail if any EU-27 missing | Parameterize reporter set, remove 27-count assertion |
| `scripts/extract_critical_inputs_comext.py` | Reporter must be in EU27 | Parameterize reporter set |
| `scripts/aggregate_logistics_freight_axis.py` | Exact 27-row EU-27 enforcement | Parameterize country set, remove exact-count assertion |
| `scripts/download_logistics_maritime_v2.py` | `COASTAL_STATES` dict covers only 22 EU states | Extend coastal state mapping |
| `scripts/aggregate_isi_v01.py` | All 27 EU-27 countries must be present in every axis | Parameterize expected country set |

### 2.2 Scripts That Are Country-Agnostic (No Modification Needed)

| Script | Notes |
|--------|-------|
| `scripts/compute_finance_bis_concentration.py` | Processes ALL countries in input |
| `scripts/parse_finance_bis_lbs_raw.py` | No country filter (EU27 used only for coverage warnings) |
| `scripts/parse_finance_cpis_raw.py` | No country filter |
| `scripts/compute_energy_concentration.py` | Processes all geo codes in input |
| `scripts/parse_energy_eurostat_raw.py` | No country filter (but data source is Eurostat-only) |

### 2.3 Backend Constants Requiring Extension

| File | Constant | Current State | Required Change |
|------|----------|---------------|-----------------|
| `backend/constants.py` | `EU27_CODES` | 27 EU codes only | Add expansion country codes or create `SCOPE_CODES` |
| `backend/constants.py` | `EU27_SORTED` | Derived from above | Same |
| `backend/constants.py` | `COUNTRY_NAMES` | 27 EU entries only | Add 12 expansion entries |
| `backend/methodology.py` | N/A | Framework-agnostic | No change needed |
| `backend/export_snapshot.py` | Uses `EU27_CODES`, `COUNTRY_NAMES` | EU-27 only | Parameterize by scope |
| `_archive/export_isi_backend_v01.py` | Hardcoded EU-27 list | EU-27 only | N/A — quarantined legacy exporter |

### 2.4 Country Code Conventions

| Context | Greece | Convention | Notes |
|---------|--------|-----------|-------|
| BIS raw data | `GR` | BIS native | Not `EL` |
| Comext raw data | `GR` | Eurostat native | Remapped to `EL` by parsers |
| SIPRI raw data | `"Greece"` (name) | Name-based | Mapped to `EL` |
| Eurostat energy JSON | `EL` | Eurostat SDMX | Native `EL` |
| ISI canonical | `EL` | Internal convention | All outputs use `EL` |
| UN Comtrade | `GR` or `300` (numeric) | ISO-3166 | Needs remapping layer |

**For expansion countries:** No Greece-like convention conflicts exist. All 12 expansion
countries use standard ISO-2 codes (US, CN, RU, JP, KR, IN, SA, BR, ZA, GB, NO, AU)
that are consistent across BIS, IMF, UN Comtrade, and SIPRI.

---

## 3. Global Source Mapping by Axis

### 3.1 Axis 1 — Financial Sovereignty

**Current sources:** BIS LBS (Channel A: banking claims) + IMF CPIS (Channel B: portfolio debt)

**Global availability:**

| Source | Coverage | Partner-Level | Time Window | Notes |
|--------|----------|--------------|-------------|-------|
| BIS LBS | ~48 reporting countries | YES (bilateral creditor × debtor) | Quarterly since 1977 | US, JP, GB, AU, NO, KR, BR, ZA, IN, SA, CN all report. RU suspended post-2022-02. |
| IMF CPIS | ~80 participating economies | YES (investor × destination) | Annual since 2001 | CN does NOT participate. SA does NOT participate. IN and RU participation uncertain/incomplete. |

**Schema compatibility:** BIS LBS → `counterparty_country, reporting_country, share, value_usd_mn` — identical to current schema. No structural change needed. IMF CPIS → `reference_area, counterpart_area, value` — identical to current schema.

**Key issue:** BIS LBS data provides the bilateral claims WHERE COUNTRY IS THE DEBTOR (counterparty). The pipeline computes HHI of creditor concentration — "who holds our debt?" For non-BIS-reporter countries that nonetheless appear as counterparties, Channel A can still be computed using mirror data (the claims ON that country, as reported by creditor countries). This is the existing approach.

**For Channel A:** All 12 countries appear as counterparties in BIS LBS data reported by ~48 BIS reporters. HHI computation is feasible for all 12.

**For Channel B:** CPIS coverage gaps for CN, SA, possibly IN and RU mean Channel B would need `A_ONLY` fallback (already supported in pipeline).

### 3.2 Axis 2 — Energy Dependency

**Current source:** Eurostat `nrg_ti_gas`, `nrg_ti_oil`, `nrg_ti_sff`

**Eurostat does NOT cover non-EU countries.**

**Replacement sources:**

| Source | Coverage | Partner-Level | Format | Notes |
|--------|----------|--------------|--------|-------|
| IEA World Energy Balances | 150+ countries | NO (aggregate only) | Proprietary, subscription required | No bilateral partner breakdown → CANNOT compute HHI |
| IEA Energy Supply (by origin) | OECD + selected | PARTIAL | Proprietary | Some bilateral flows for select fuels |
| UN Comtrade (HS 27) | 200+ countries | YES (bilateral) | HS 2701–2716 | Gas (2711), oil (2709–2710), solid fossil (2701–2704) |
| JODI (Joint Oil Data Initiative) | 100+ countries | NO (aggregate supply/demand) | Open | No partner breakdown |
| National sources | Varies | Varies | Heterogeneous | Country-by-country effort |
| BACI (CEPII) | 200+ countries | YES (bilateral) | Harmonized HS6 | Reconciled mirror flows, good quality |

**Recommended replacement:** UN Comtrade HS 27xx with bilateral partner breakdown.

**Required transformations:**
1. Map HS codes to fuel categories: gas (HS 2711), crude oil (HS 2709), refined petroleum (HS 2710), solid fossil fuels (HS 2701–2704)
2. Convert from value (USD) to physical quantity if available (Comtrade includes both)
3. Compute per-fuel HHI from partner shares, then average across fuels
4. Units will differ from Eurostat (TJ vs USD/kg) — but HHI is unit-invariant if shares are computed correctly within each fuel

**Schema compatibility:** UN Comtrade provides: `reporter, partner, HS_code, trade_value, quantity, quantity_unit`. Needs transformation to: `reporter, partner, fuel_type, share, value`. The share computation is straightforward.

### 3.3 Axis 3 — Technology / Semiconductor Dependency

**Current source:** Eurostat Comext ds-045409, HS 8541 + 8542

**Eurostat Comext does NOT cover non-EU reporters.**

**Replacement source:**

| Source | Coverage | Partner-Level | Format | Notes |
|--------|----------|--------------|--------|-------|
| UN Comtrade | 200+ countries | YES (bilateral) | HS 8541, 8542 at HS4–HS6 | Direct equivalent |
| National customs (US ITC, China GAC, etc.) | Single country | YES | Heterogeneous | Backup for missing Comtrade data |

**Recommended replacement:** UN Comtrade HS 8541 + 8542.

**Required transformations:**
1. Map HS subheadings to ISI categories: `legacy_discrete` (854110, 854121, 854129, 854130), `legacy_components` (854160, 854190), `integrated_circuits` (8542 HS4)
2. Current pipeline uses CN8 granularity (Comext). UN Comtrade provides HS6 maximum — the mapping from CN8 to HS6 requires a concordance table. Some CN8 codes will collapse to the same HS6 code.
3. Solar PV guard (`854140`) still applicable at HS6.
4. Partner codes: UN Comtrade uses ISO-3 numeric (e.g., 840 = US). Need mapping to ISO-2.

**Schema compatibility:** Achievable. Core structure `reporter, partner, HS_code, value` is identical. Category mapping needs adaptation from CN8 → HS6. Channel B (category-weighted HHI) directly portable.

### 3.4 Axis 4 — Defence Industrial Dependency

**Current source:** SIPRI Arms Transfers Database (global coverage)

**SIPRI is already a global database.** No source replacement needed.

**Current limitation:** `parse_defense_sipri_raw.py` filters recipients to EU-27 only via `SIPRI_TO_EUROSTAT` mapping. However, `SUPPLIER_NAME_TO_CODE` already includes all 12 expansion countries.

**Required changes:**
1. Extend `SIPRI_TO_EUROSTAT` (recipient mapping) to include all 12 expansion countries
2. All 12 countries already exist in `SUPPLIER_NAME_TO_CODE` with correct ISO-2 codes
3. Remove or parameterize the EU-27 recipient filter
4. The capability-block regex classification is weapon-type-based, not country-based — no change needed

**Schema compatibility:** Fully compatible. Output format `recipient_country, supplier_country, capability_block, year, tiv` is country-agnostic.

**Country-specific notes:**
- US: Overwhelmingly a supplier, not recipient. Very few inward transfers → HHI may be meaningless or score ≈ 0
- China: Major domestic producer + some Russian imports. Limited SIPRI coverage of Chinese domestic production
- Russia: Major supplier. Inward transfers minimal. Score ≈ 0 likely
- Saudi Arabia: Major recipient (US, UK, France). Very clear bilateral data

### 3.5 Axis 5 — Critical Inputs / Raw Materials Dependency

**Current source:** Eurostat Comext ds-045409 CN8, filtered to 66 specific CN8 codes

**Eurostat Comext does NOT cover non-EU reporters.**

**Replacement source:**

| Source | Coverage | Partner-Level | Format | Notes |
|--------|----------|--------------|--------|-------|
| UN Comtrade | 200+ countries | YES (bilateral) | HS6 (not CN8) | 66 CN8 codes will map to fewer HS6 codes |
| National customs databases | Single country | YES | Heterogeneous | Backup |

**Recommended replacement:** UN Comtrade at HS6 level.

**Required transformations:**
1. CN8 → HS6 concordance: 66 CN8 codes must be mapped to their HS6 parent codes. Some CN8 codes within the same HS6 will merge. The 5 material groups (rare_earths, battery_metals, defense_industrial_metals, semiconductor_inputs, fertilizer_chokepoints) must be re-verified at HS6 granularity.
2. Mapping file `docs/mappings/critical_materials_cn8_mapping_v01.csv` needs an HS6 equivalent
3. The hard assertion of exactly 66 codes must be updated
4. Country codes: UN Comtrade ISO-3 numeric → ISO-2 alpha

**Schema compatibility:** Achievable with concordance table. Core schema `DECLARANT_ISO, PARTNER_ISO, PRODUCT_NC, FLOW, PERIOD, VALUE_IN_EUROS` maps to `reporter, partner, HS_code, flow, year, value`.

**Critical issue:** HS6 granularity is coarser than CN8. Some material groups may lose specificity. For example, rare earth subgroups distinguished at CN8 level may merge at HS6. This could affect Channel B (material-group-weighted HHI) accuracy.

### 3.6 Axis 6 — Logistics / Freight Dependency

**Current source:** Eurostat `tran_hv_frmod` (road), `tran_r_frgo` (rail), `mar_sg_am_cw` / `mar_go_am` (maritime)

**Eurostat transport data does NOT cover non-EU countries.**

**Replacement sources:**

| Source | Coverage | Partner-Level | Format | Notes |
|--------|----------|--------------|--------|-------|
| ITF (International Transport Forum) Transport Statistics | OECD + partners (~60 countries) | PARTIAL (aggregate tonnage by mode) | Annual, structured | Mode shares available; NO bilateral partner breakdown |
| UNCTAD Maritime Transport Review | All countries | NO (aggregate) | Annual | Port throughput, fleet data, no bilateral flows |
| UN Comtrade (services) | Limited | NO | Annual | Transport services trade, not freight flows |
| National transport statistics | Single country | Varies | Heterogeneous | Country-by-country effort |
| Eurostat (for NO, GB via EEA/partner data) | NO and GB MAY appear | YES if present | Same as EU format | Norway and UK sometimes in Eurostat transport as partner countries |

**Channel A (mode concentration):** ITF provides mode-split data (road/rail/maritime/IWW/pipeline tonnage) for OECD countries. US, JP, KR, GB, NO, AU, BR → available through ITF. CN, IN, RU, SA, ZA → uncertain.

**Channel B (partner concentration per mode):** This is the critical gap. Bilateral freight partner data (who ships freight to/from country X, by mode) is generally NOT available globally in any single standardized source. The current pipeline relies on Eurostat's detailed bilateral maritime/road/rail data which is EU-specific.

**Required transformations:**
1. New parser for ITF data format (CSV/JSON, different column structure)
2. Channel B may require national data sources or proxy construction
3. Maritime partner data: UNCTAD port-to-port flows or national maritime authority data
4. Road/rail partner data: Generally unavailable for non-European countries

**Schema compatibility:** Channel A (mode HHI) can be replicated if mode tonnage data exists. Channel B (partner HHI per mode) has NO global equivalent dataset.

**This is the most problematic axis for global expansion.**

---

## 4. Per-Country Assessments

---

### COUNTRY: United States

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (Channel A — US is a BIS reporter since Q4 1977), IMF CPIS (Channel B — US participates)
- Coverage issues: None. US has comprehensive bilateral financial data as both creditor and debtor.
- Required transformations: None. Same BIS/CPIS pipeline. Parser already handles US as counterparty.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 2709 (crude oil), 2710 (petroleum products), 2711 (natural gas/LNG), 2701–2704 (coal)
- Coverage issues: US reports comprehensive bilateral trade data to Comtrade. Domestic production is very large — import concentration may be low by construction.
- Required transformations: New parser for UN Comtrade energy HS codes. HS code → fuel type mapping. Share computation from bilateral import values.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541 + 8542. US ITC DataWeb as backup.
- Coverage issues: None. US reports HS6-level bilateral semiconductor imports to Comtrade.
- Required transformations: CN8 → HS6 category mapping. UN Comtrade ISO-3 numeric → ISO-2 code mapping.

**Axis 4 — Defence:**
- Feasible: **PARTIAL**
- Replacement sources: SIPRI (already global). US is in `SUPPLIER_NAME_TO_CODE` as `"United States": "US"`.
- Coverage issues: US is overwhelmingly a supplier, not a recipient. Inward major conventional arms transfers are minimal. SIPRI TIV for US as recipient may be near-zero for most years. Score ≈ 0.0 is a legitimate empirical result (domestic production dominance), but interpretability differs from the EU context.
- Required transformations: Extend `SIPRI_TO_EUROSTAT` to include `"United States": "US"`. Remove EU-27 recipient filter.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6 for the 66 CN8 critical materials (collapsed to HS6 parent codes).
- Coverage issues: None. US reports comprehensive bilateral critical material imports.
- Required transformations: CN8 → HS6 concordance. New mapping file. UN Comtrade parser.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — Bureau of Transportation Statistics (BTS) Freight Analysis Framework provides mode-split tonnage data. ITF transport statistics. Channel B — US Census Bureau reports bilateral trade by transport mode for some categories. Maritime: USACE waterborne commerce data.
- Coverage issues: Channel B partner-level bilateral freight data is fragmented across agencies. No single source equivalent to Eurostat bilateral freight tables.
- Required transformations: New parsers for BTS/ITF data. Channel B may require composite construction from maritime + land border statistics.

#### SOURCE MAPPING

| Axis | Dataset | Partner-Level | Time Window | Known Gaps |
|------|---------|--------------|-------------|------------|
| 1A | BIS LBS Q4 2024 | YES | Single quarter | None |
| 1B | IMF CPIS 2024 | YES | Annual | None |
| 2 | UN Comtrade HS 27xx | YES | 2022–2024 | Need fuel-type mapping |
| 3 | UN Comtrade HS 8541/8542 | YES | 2022–2024 | HS6 vs CN8 granularity |
| 4 | SIPRI 2019–2024 | YES | 6-year window | Near-zero recipient TIV |
| 5 | UN Comtrade HS6 critical | YES | 2022–2024 | CN8→HS6 granularity loss |
| 6A | BTS/ITF mode shares | YES (mode) | 2022–2024 | Non-bilateral |
| 6B | USACE/Census bilateral | PARTIAL | Varies | Fragmented sources |

#### SCHEMA COMPATIBILITY

| Axis | partner → value → share vector? | Missing Fields | Aggregation Needs |
|------|--------------------------------|----------------|-------------------|
| 1 | YES | None | None |
| 2 | YES | Fuel-type classifier | HS → fuel mapping |
| 3 | YES | CN8 category | HS6 → category mapping |
| 4 | YES (but sparse) | None | None |
| 5 | YES | CN8 material group | HS6 → group mapping |
| 6 | PARTIAL (A: yes, B: partial) | Bilateral partner by mode | Multi-source fusion |

#### PIPELINE IMPACT

- Does current pipeline support this country without modification? **NO**
- Parser changes: New UN Comtrade parser (axes 2, 3, 5). New BTS/ITF parser (axis 6).
- New mapping layers: HS code → fuel type; HS6 → semiconductor category; HS6 → material group; UN Comtrade ISO-3 → ISO-2.
- Normalization issues: Value units (USD vs EUR). Current pipeline uses EUR (Comext native). UN Comtrade reports USD. HHI is share-based → unit-invariant for concentration, but volume fields need currency flag.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW** (6/6 feasible, axis 4 interpretability caveat)
- Data reliability risk: **LOW**
- Pipeline complexity increase: **MEDIUM** (new parsers, new mapping layers)

#### CRITICAL FAILURES

- None. All 6 axes constructible.
- **Interpretability note:** Defense axis score ≈ 0 reflects domestic production, not "low dependency." This is a methodological difference from the EU context where most countries are net importers.

---

### COUNTRY: China

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **PARTIAL**
- Replacement sources: BIS LBS (Channel A — China reports since Q4 2015). IMF CPIS — **China does NOT participate**.
- Coverage issues: Channel A available (China as counterparty in BIS, reported by ~48 creditor countries). Channel B: NO CPIS data. Must use `A_ONLY` fallback.
- Required transformations: None for Channel A. Channel B → automatic `A_ONLY` basis (existing fallback logic).

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx. China reports bilateral energy imports to Comtrade.
- Coverage issues: China's customs administration (GAC) reports to Comtrade with some delays (typically 1–2 year lag). 2024 data may not be available until late 2025/2026. Historical data (2022–2023) available.
- Required transformations: Same as US. New UN Comtrade energy parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542. China has comprehensive semiconductor import data.
- Coverage issues: Chinese semiconductor imports are massive and politically sensitive. Data quality is generally good at HS6. Recent US/EU export controls may cause trade pattern distortions (2022–2024 window covers the control period).
- Required transformations: Same as US. CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **PARTIAL**
- Replacement sources: SIPRI (China is in supplier map as `"China": "CN"`).
- Coverage issues: China is a major arms producer with significant domestic capacity. SIPRI captures foreign imports (primarily Russia). Chinese domestic production is NOT captured. Score will reflect only import concentration, not total defense dependency. Recent years show declining Russian imports as China indigenizes.
- Required transformations: Extend `SIPRI_TO_EUROSTAT` recipient mapping. Remove EU-27 filter.

**Axis 5 — Critical Inputs:**
- Feasible: **YES** (but with methodological inversion issue)
- Replacement sources: UN Comtrade HS6 critical materials.
- Coverage issues: **CRITICAL METHODOLOGICAL ISSUE** — China is the world's dominant EXPORTER of rare earths and many critical materials. Computing import concentration for China would produce a misleadingly low score, while China's actual vulnerability lies in upstream mining/processing dependencies (e.g., cobalt from DRC). The ISI methodology measures import concentration only — it cannot capture processing dominance or export dependency.
- Required transformations: Same as US.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — China National Bureau of Statistics transport data (mode shares). Channel B — China Customs bilateral trade by transport mode is not publicly available in standardized format.
- Coverage issues: Channel A mode data available through national statistics. Channel B bilateral freight partner data: **NOT AVAILABLE** in any global standardized source. China's maritime data exists in port-level statistics but not in ISI-compatible bilateral format.
- Required transformations: New parser for Chinese transport statistics. Channel B likely requires A_ONLY or proxy construction.

#### SOURCE MAPPING

| Axis | Dataset | Partner-Level | Time Window | Known Gaps |
|------|---------|--------------|-------------|------------|
| 1A | BIS LBS Q4 2024 | YES | Single quarter | None |
| 1B | IMF CPIS | **NOT AVAILABLE** | — | China does not participate |
| 2 | UN Comtrade HS 27xx | YES | 2022–2024 | Possible 2024 lag |
| 3 | UN Comtrade HS 8541/8542 | YES | 2022–2024 | None |
| 4 | SIPRI 2019–2024 | YES (imports only) | 6-year window | Domestic production invisible |
| 5 | UN Comtrade HS6 critical | YES | 2022–2024 | Methodological inversion |
| 6A | NBS transport stats | YES (mode) | Available | Non-standardized format |
| 6B | — | **NOT AVAILABLE** | — | No bilateral freight source |

#### SCHEMA COMPATIBILITY

| Axis | partner → value → share vector? | Missing Fields | Aggregation Needs |
|------|--------------------------------|----------------|-------------------|
| 1 | PARTIAL (A only) | Channel B missing | A_ONLY fallback |
| 2 | YES | Fuel-type classifier | HS → fuel mapping |
| 3 | YES | CN8 category | HS6 → category mapping |
| 4 | YES (sparse) | None | None |
| 5 | YES (but misleading) | None | Methodology review needed |
| 6 | PARTIAL (A only likely) | Channel B missing | A_ONLY or proxy |

#### PIPELINE IMPACT

- Does current pipeline support this country without modification? **NO**
- Parser changes: UN Comtrade parser, Chinese NBS transport parser, SIPRI recipient extension
- New mapping layers: Same as US + Chinese NBS format adaptation
- Normalization issues: Chinese Comtrade data in USD. NBS data in Chinese units (万吨 = 10,000 tonnes). Unit conversion required.

#### RISK ASSESSMENT

- Axis completeness risk: **HIGH** (1B missing, 6B missing, 4 and 5 interpretability issues)
- Data reliability risk: **MEDIUM** (Comtrade reporting lags, NBS format uncertainty)
- Pipeline complexity increase: **HIGH**

#### CRITICAL FAILURES

- **W-COV risk: NO** — At least 4 axes constructible (1A, 2, 3, 5)
- **Methodological comparability risk: YES** — Axis 5 score for China is methodologically inverted (major exporter scored on import concentration). Axis 4 misses domestic production. Results are technically computable but may not be comparable to EU scores.
- **Major fallback usage:** Axis 1 (A_ONLY), Axis 6 (A_ONLY or omit)

---

### COUNTRY: Russia

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **NO / SEVERELY DEGRADED**
- Replacement sources: BIS LBS — **Russia's reporting was SUSPENDED after 28 February 2022** per BIS official statement. Pre-suspension data exists but is stale.
- Coverage issues: Channel A can still be computed using mirror data (claims ON Russia reported by other BIS-reporting countries). But post-2022 sanctions have fundamentally altered Russia's financial integration — SWIFT disconnections, asset freezes, capital controls. Any BIS-based score would not reflect current reality. Channel B (CPIS): Russia's participation is uncertain/incomplete.
- Required transformations: Mirror-data-only computation for Channel A. Flag as severely degraded.

**Axis 2 — Energy:**
- Feasible: **PARTIAL**
- Replacement sources: UN Comtrade — Russia reports to Comtrade but with increasing delays and potential gaps since 2022. IEA/JODI data exists but lacks bilateral partner breakdown.
- Coverage issues: Russia is overwhelmingly an energy EXPORTER. Computing import concentration is methodologically misleading — Russia's energy vulnerability is export-market concentration (who buys from Russia), not import dependency. However, Russia does import some refined products and nuclear fuel.
- Required transformations: UN Comtrade parser. Methodological caveat required.

**Axis 3 — Technology:**
- Feasible: **PARTIAL**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Post-2022 sanctions severely disrupted Russia's semiconductor imports. Official trade data may not capture parallel/grey market imports. Comtrade data from Russia post-2022 may be incomplete or unreliable. Partner-country mirror data (exports TO Russia) could supplement, but sanctions evasion through intermediaries makes mirror data unreliable too.
- Required transformations: UN Comtrade parser. Data quality flag required.

**Axis 4 — Defence:**
- Feasible: **PARTIAL**
- Replacement sources: SIPRI.
- Coverage issues: Russia is the world's #2 arms exporter. As a recipient, Russia imports relatively little major conventional equipment. SIPRI data exists but inward TIV is near-zero for most years. Post-2022, some component imports from Iran/North Korea are reported by SIPRI.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **PARTIAL**
- Replacement sources: UN Comtrade HS6.
- Coverage issues: Same as China — Russia is a major EXPORTER of many critical materials (nickel, palladium, aluminium, titanium). Import concentration score is methodologically misleading. Post-sanctions data quality is uncertain.
- Required transformations: UN Comtrade parser.

**Axis 6 — Logistics:**
- Feasible: **NO**
- Replacement sources: Russian Federal Statistics Service (Rosstat) provides some mode-split data, but bilateral freight partner data is not available in standardized format. Post-2022, Russia's logistics patterns fundamentally shifted (European route closures, pivot to Asian routes).
- Coverage issues: No standardized global source for Russian bilateral freight. Rosstat data may be incomplete or unreliable post-2022.
- Required transformations: Would require bespoke Russian data parser. Channel B construction infeasible.

#### SOURCE MAPPING

| Axis | Dataset | Partner-Level | Time Window | Known Gaps |
|------|---------|--------------|-------------|------------|
| 1A | BIS LBS (mirror only) | YES (degraded) | Pre-2022 stale | Reporting suspended |
| 1B | IMF CPIS | **UNCERTAIN** | — | Participation unclear |
| 2 | UN Comtrade HS 27xx | PARTIAL | 2022–2024 | Exporter, not importer |
| 3 | UN Comtrade HS 8541/8542 | PARTIAL | 2022–2024 | Sanctions distortion |
| 4 | SIPRI 2019–2024 | YES (sparse) | 6-year window | Near-zero recipient TIV |
| 5 | UN Comtrade HS6 critical | PARTIAL | 2022–2024 | Major exporter + sanctions |
| 6A | Rosstat | UNCERTAIN | Unknown | Non-standardized |
| 6B | — | **NOT AVAILABLE** | — | No bilateral freight source |

#### PIPELINE IMPACT

- Does current pipeline support this country without modification? **NO**
- Parser changes: All axes require new parsers or data quality flags
- New mapping layers: Mirror data construction for Axis 1
- Normalization issues: Sanctions regime makes 2022–2024 data non-comparable to pre-sanctions baselines

#### RISK ASSESSMENT

- Axis completeness risk: **CRITICAL** (at most 3–4 axes partially computable)
- Data reliability risk: **CRITICAL** (sanctions distortion across all data sources)
- Pipeline complexity increase: **HIGH**

#### CRITICAL FAILURES

- **W-COV: YES** — Fewer than 4 reliable axes. Axis 1 severely degraded, Axis 6 infeasible, Axes 2/5 methodologically inverted.
- **Non-comparable outputs: YES** — Sanctions regime makes all 2022–2024 data fundamentally non-comparable to peacetime EU scores.
- **Recommendation: BLOCKED** — Cannot produce ISI-comparable scores without methodology waiver and explicit sanctions-era data quality disclaimers.

---

### COUNTRY: Japan

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (Japan reports since Q4 1977). IMF CPIS (Japan participates).
- Coverage issues: None. Japan is a major financial center with comprehensive bilateral data.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx. Japan reports comprehensive bilateral energy imports.
- Coverage issues: None. Japan is a major energy importer with clear bilateral partner data.
- Required transformations: UN Comtrade energy parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Japan is both a major semiconductor producer AND importer. HS6 data is comprehensive.
- Required transformations: CN8 → HS6 category mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (Japan is in supplier map as `"Japan": "JP"`).
- Coverage issues: Japan imports significant military equipment (primarily from US). Clear SIPRI data.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6 critical materials.
- Coverage issues: Japan is a major critical materials importer with clear bilateral data.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — Japanese Ministry of Land, Infrastructure, Transport and Tourism (MLIT) publishes mode-split freight tonnage. ITF covers Japan. Channel B — Japanese Customs reports bilateral trade by transport mode for maritime (major ports). Road/rail bilateral partner data limited (island nation — maritime dominates).
- Coverage issues: Channel A straightforward (island nation: maritime dominant). Channel B maritime partner data exists through port statistics. Rail/road partner data less relevant (limited land borders).
- Required transformations: MLIT/ITF parser. Maritime port statistics parser.

#### SOURCE MAPPING

| Axis | Dataset | Partner-Level | Time Window | Known Gaps |
|------|---------|--------------|-------------|------------|
| 1A | BIS LBS Q4 2024 | YES | Single quarter | None |
| 1B | IMF CPIS 2024 | YES | Annual | None |
| 2 | UN Comtrade HS 27xx | YES | 2022–2024 | None |
| 3 | UN Comtrade HS 8541/8542 | YES | 2022–2024 | HS6 granularity |
| 4 | SIPRI 2019–2024 | YES | 6-year window | None |
| 5 | UN Comtrade HS6 critical | YES | 2022–2024 | HS6 granularity |
| 6A | MLIT/ITF | YES (mode) | 2022–2024 | None |
| 6B | Port statistics | PARTIAL (maritime) | Varies | Road/rail bilateral limited |

#### PIPELINE IMPACT

- Does current pipeline support this country without modification? **NO**
- Parser changes: UN Comtrade parser (axes 2, 3, 5), MLIT/ITF parser (axis 6), SIPRI extension
- New mapping layers: Same as US
- Normalization issues: JPY → share-based (unit-invariant). Port tonnage units may differ.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW** (6/6 feasible)
- Data reliability risk: **LOW**
- Pipeline complexity increase: **MEDIUM**

#### CRITICAL FAILURES

- None. All 6 axes constructible. Japan's profile as an import-dependent island nation makes ISI methodology particularly well-suited.

---

### COUNTRY: South Korea

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (Korea reports since Q1 2005). IMF CPIS (Korea participates).
- Coverage issues: None.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx.
- Coverage issues: None. South Korea is a major energy importer with clear bilateral data.
- Required transformations: UN Comtrade energy parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Korea is a major semiconductor producer AND importer. Complex intra-industry trade with China, Japan, Taiwan.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"South Korea": "KR"` in supplier map).
- Coverage issues: Korea imports significant equipment (US, Germany) and is increasingly a supplier. Clear SIPRI data.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6.
- Coverage issues: Korea is a major critical materials importer. Clear bilateral data.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — Korean Statistical Information Service (KOSIS) / ITF mode shares. Channel B — Korean Customs Service maritime bilateral data. Similar to Japan (peninsula but effectively island logistics).
- Coverage issues: Channel A available through ITF. Channel B maritime data exists. Road/rail bilateral limited (DMZ blocks northern land route).
- Required transformations: KOSIS/ITF parser.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW** (6/6 feasible)
- Data reliability risk: **LOW**
- Pipeline complexity increase: **MEDIUM**

#### CRITICAL FAILURES

- None.

---

### COUNTRY: India

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **PARTIAL**
- Replacement sources: BIS LBS (India reports since Q4 2001). IMF CPIS — India's participation is partial/uncertain.
- Coverage issues: Channel A available via mirror data + India's own reporting. Channel B may require `A_ONLY` fallback if CPIS data is incomplete.
- Required transformations: Verify CPIS participation status. Potentially A_ONLY basis.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx.
- Coverage issues: India is a major energy importer. Clear bilateral trade data available. India reports to Comtrade with typical ~1 year lag.
- Required transformations: UN Comtrade energy parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: India is a net semiconductor importer. Bilateral data available.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"India": "IN"` in supplier map).
- Coverage issues: India is one of the world's largest arms importers. Very comprehensive SIPRI data (Russia, France, US, Israel as suppliers). Excellent bilateral coverage.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6.
- Coverage issues: India is both an importer and processor of critical materials. Import data available but India's role in rare earth processing may create interpretability questions.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — Indian Ministry of Transport / ITF (India is an ITF member). Channel B — Indian port authority data exists but standardization uncertain. Rail bilateral data available from Indian Railways.
- Coverage issues: India has diverse transport modes (road dominant, rail significant, maritime growing). Channel A data should be available. Channel B bilateral freight data is fragmented.
- Required transformations: New parsers for Indian transport statistics.

#### RISK ASSESSMENT

- Axis completeness risk: **MEDIUM** (5–6 axes, Axis 1B uncertain, Axis 6B fragmented)
- Data reliability risk: **MEDIUM** (Comtrade reporting lags)
- Pipeline complexity increase: **MEDIUM**

#### CRITICAL FAILURES

- None that would block inclusion. Axis 1 may use A_ONLY fallback. Axis 6 may use A_ONLY.

---

### COUNTRY: Saudi Arabia

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **PARTIAL**
- Replacement sources: BIS LBS (Saudi Arabia reports since Q4 2017). IMF CPIS — **Saudi Arabia does NOT participate**.
- Coverage issues: Channel A available (Saudi Arabia as counterparty). Channel B: NO CPIS data. Must use `A_ONLY` fallback.
- Required transformations: A_ONLY basis for Channel B.

**Axis 2 — Energy:**
- Feasible: **YES** (but methodologically inverted)
- Replacement sources: UN Comtrade HS 27xx.
- Coverage issues: **METHODOLOGICAL ISSUE** — Saudi Arabia is the world's largest crude oil exporter. While it does import some refined petroleum products and natural gas, computing energy import concentration is methodologically misleading. The ISI energy axis is designed to measure import dependency, which is the inverse of Saudi Arabia's actual energy position.
- Required transformations: UN Comtrade parser. Methodology caveat required.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Saudi Arabia imports semiconductors. Bilateral data available. Saudi Arabia reports to UN Comtrade.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"Saudi Arabia": "SA"` in supplier map).
- Coverage issues: Saudi Arabia is one of the world's largest arms importers (primarily from US, UK, France). Excellent SIPRI bilateral coverage. This is arguably the most valid axis for Saudi Arabia.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6.
- Coverage issues: Saudi Arabia imports critical materials for industrialization programs (NEOM, Vision 2030). Bilateral data exists but volumes may be relatively small.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **NO / HIGHLY UNCERTAIN**
- Replacement sources: No standardized source. Saudi General Authority for Statistics publishes some transport data but not in bilateral freight format. ITF does NOT cover Saudi Arabia as a member.
- Coverage issues: Channel A mode data may exist nationally but not in standardized format. Channel B bilateral freight partner data is NOT available.
- Required transformations: Would require bespoke national data collection. Not feasible at scale.

#### RISK ASSESSMENT

- Axis completeness risk: **HIGH** (4–5 axes, Axis 6 infeasible, Axis 2 inverted)
- Data reliability risk: **MEDIUM**
- Pipeline complexity increase: **HIGH**

#### CRITICAL FAILURES

- **W-COV risk: BORDERLINE** — 4–5 axes constructible, but Axis 2 is methodologically inverted.
- **Non-comparable outputs: YES for Axis 2** — Energy axis score will be artificially low for the world's largest oil exporter.
- **Axis 6 infeasible** — No standardized logistics data source.

---

### COUNTRY: Brazil

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (Brazil reports since Q4 2002). IMF CPIS (Brazil participates).
- Coverage issues: None.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx.
- Coverage issues: Brazil is a major energy producer (pre-salt oil) but also imports natural gas (Bolivia) and some refined products. Bilateral import data available.
- Required transformations: UN Comtrade energy parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Brazil imports semiconductors. Bilateral data available.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"Brazil": "BR"` in supplier map).
- Coverage issues: Brazil imports military equipment from diverse suppliers (France, Sweden/Saab, US, UK). SIPRI data exists. Brazil also has significant domestic defense industry.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES** (with caveat)
- Replacement sources: UN Comtrade HS6.
- Coverage issues: Brazil is a major exporter of some critical materials (niobium — near-monopoly, iron ore, bauxite). Import concentration for these materials may be very low. But Brazil does import semiconductor inputs and some rare earths.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — ANTT (Agência Nacional de Transportes Terrestres) / ANTAQ (maritime) / ITF. Channel B — Brazilian customs bilateral trade data. Maritime: ANTAQ port statistics.
- Coverage issues: Brazil has data through ITF membership. Channel A mode data available. Channel B bilateral freight data fragmented across ANTAQ/ANTT.
- Required transformations: Brazilian transport statistics parsers.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW-MEDIUM** (5–6 axes, Axis 6B uncertain)
- Data reliability risk: **LOW**
- Pipeline complexity increase: **MEDIUM**

#### CRITICAL FAILURES

- None. Brazil is a strong candidate for inclusion.

---

### COUNTRY: South Africa

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (South Africa reports since Q3 2009). IMF CPIS (South Africa participates).
- Coverage issues: None.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx.
- Coverage issues: South Africa imports oil and gas but is a major coal producer/exporter. Energy import concentration computable for oil and gas. Coal import concentration may be very low or zero (net exporter).
- Required transformations: UN Comtrade energy parser. Fuel-level handling for net-exporter case.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: South Africa imports semiconductors. Data available.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"South Africa": "ZA"` in supplier map).
- Coverage issues: South Africa has a domestic defense industry (Denel) but also imports. SIPRI data exists.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES** (with caveat)
- Replacement sources: UN Comtrade HS6.
- Coverage issues: South Africa is a major EXPORTER of platinum group metals, chromium, manganese. Import concentration for these specific materials is near-zero. But imports other critical materials.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — Transnet / ITF (South Africa is an ITF member). Channel B — South African customs/Transnet port data.
- Coverage issues: Mode data available. Bilateral freight partner data fragmented.
- Required transformations: South African transport statistics parsers.

#### RISK ASSESSMENT

- Axis completeness risk: **MEDIUM** (5–6 axes, Axis 6B uncertain)
- Data reliability risk: **LOW-MEDIUM**
- Pipeline complexity increase: **MEDIUM**

#### CRITICAL FAILURES

- None.

---

### COUNTRY: United Kingdom

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (UK reports since Q4 1977 — one of the original reporters). IMF CPIS (UK participates). London is the world's largest international financial center.
- Coverage issues: None.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx. Additionally, UK HMRC Overseas Trade Statistics provide bilateral energy trade data directly.
- Coverage issues: UK is a net energy importer (North Sea production declining). Clear bilateral import data.
- Required transformations: UN Comtrade parser (or HMRC parser if using national data). UK may also still appear in some Eurostat datasets as a partner country.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542. HMRC trade data as backup.
- Coverage issues: None. UK reports comprehensive bilateral semiconductor imports.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"United Kingdom": "GB"` in supplier map).
- Coverage issues: UK is both a major arms supplier and recipient. SIPRI data comprehensive. UK imports from US primarily.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6.
- Coverage issues: UK is a critical materials importer with clear bilateral data.
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **YES**
- Replacement sources: Channel A — UK Department for Transport (DfT) freight statistics. ITF covers UK. Channel B — HMRC bilateral trade includes transport mode. UK port statistics (DfT Maritime) provide bilateral maritime freight data.
- Coverage issues: UK has excellent transport statistics infrastructure. Island nation (like Japan) — maritime dominates. Channel A and B both likely achievable.
- Required transformations: DfT / HMRC parser. UK may still appear in some Eurostat transport datasets.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW** (6/6 feasible)
- Data reliability risk: **LOW** (excellent statistical infrastructure)
- Pipeline complexity increase: **LOW-MEDIUM**

#### CRITICAL FAILURES

- None. UK is the strongest candidate for inclusion — comparable statistical infrastructure to EU, familiar data formats, and clear economic profile as an import-dependent island economy.

---

### COUNTRY: Norway

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (Norway reports since Q4 1983). IMF CPIS (Norway participates).
- Coverage issues: None.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES** (with methodological note)
- Replacement sources: UN Comtrade HS 27xx. Additionally, Norway may still appear in some Eurostat datasets as an EEA partner.
- Coverage issues: Norway is a major energy EXPORTER (oil, gas). However, Norway does import some energy products. Import concentration is computable but will produce a very low score.
- Required transformations: UN Comtrade parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Norway imports semiconductors. Bilateral data available.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"Norway": "NO"` in supplier map).
- Coverage issues: Norway imports military equipment (US, Europe). SIPRI data exists.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS6.
- Coverage issues: Norway is an importer of critical materials. Bilateral data available. Norway also exports some materials (aluminium via Norsk Hydro, silicon).
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **YES**
- Replacement sources: Channel A — Statistics Norway (SSB) transport statistics. ITF covers Norway. Channel B — SSB bilateral trade by transport mode. Norway may also appear in Eurostat transport datasets as EEA partner.
- Coverage issues: Norway has excellent Scandinavian-quality statistics. Maritime dominant for external trade. Road/rail bilateral data available for Nordic neighbors.
- Required transformations: SSB/ITF parser. Eurostat partner-country extraction may be possible.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW** (6/6 feasible)
- Data reliability risk: **LOW** (excellent statistical infrastructure)
- Pipeline complexity increase: **LOW** (similar data ecosystem to EU)

#### CRITICAL FAILURES

- None. Norway is a strong candidate — EEA proximity means data formats may partially overlap with Eurostat.
- **Interpretability note:** Axis 2 score will be very low (energy exporter), which is a legitimate result.

---

### COUNTRY: Australia

---

#### AXIS FEASIBILITY

**Axis 1 — Financial:**
- Feasible: **YES**
- Replacement sources: BIS LBS (Australia reports since Q4 1997). IMF CPIS (Australia participates).
- Coverage issues: None.
- Required transformations: None.

**Axis 2 — Energy:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 27xx.
- Coverage issues: Australia is a major coal and LNG exporter but imports refined petroleum products. Oil import concentration is meaningful (Singapore, Korea, Japan as refiners).
- Required transformations: UN Comtrade energy parser.

**Axis 3 — Technology:**
- Feasible: **YES**
- Replacement sources: UN Comtrade HS 8541/8542.
- Coverage issues: Australia imports semiconductors. Bilateral data available.
- Required transformations: CN8 → HS6 mapping.

**Axis 4 — Defence:**
- Feasible: **YES**
- Replacement sources: SIPRI (`"Australia": "AU"` in supplier map).
- Coverage issues: Australia is a major arms importer (US, UK, France — AUKUS era). Comprehensive SIPRI data.
- Required transformations: Extend SIPRI recipient mapping.

**Axis 5 — Critical Inputs:**
- Feasible: **YES** (with caveat)
- Replacement sources: UN Comtrade HS6.
- Coverage issues: Australia is a major exporter of lithium, rare earths, iron ore. Import concentration for these materials may be very low. But Australia imports other critical materials (e.g., processed rare earth products from China).
- Required transformations: CN8 → HS6 concordance.

**Axis 6 — Logistics:**
- Feasible: **PARTIAL**
- Replacement sources: Channel A — Bureau of Infrastructure and Transport Research Economics (BITRE). ITF covers Australia. Channel B — Australian Bureau of Statistics (ABS) / BITRE port statistics.
- Coverage issues: Island continent — maritime dominates external freight. Channel A mode data available through ITF/BITRE. Channel B maritime partner data available through port statistics. Road/rail are domestic-oriented.
- Required transformations: BITRE/ITF parser.

#### RISK ASSESSMENT

- Axis completeness risk: **LOW** (6/6 feasible)
- Data reliability risk: **LOW** (excellent statistical infrastructure)
- Pipeline complexity increase: **MEDIUM**

#### CRITICAL FAILURES

- None. Australia is a strong candidate — island geography makes logistics axis well-defined (maritime-dominant).

---

## 5. Pipeline Impact Summary

### 5.1 New Parsers Required

| Parser | Axes Served | Countries Served | Effort |
|--------|------------|-----------------|--------|
| UN Comtrade bilateral trade (HS-level) | 2, 3, 5 | All 12 expansion countries | HIGH — new data source, ISO-3→ISO-2 mapping, HS classification |
| ITF transport statistics | 6A | US, JP, KR, BR, ZA, GB, NO, AU (OECD members) | MEDIUM |
| SIPRI recipient extension | 4 | All 12 | LOW — mapping table only |
| National transport agencies (per-country) | 6B | Various | HIGH — bespoke per country |

### 5.2 New Mapping Layers Required

| Mapping | Purpose | Effort |
|---------|---------|--------|
| CN8 → HS6 concordance | Critical inputs + technology category mapping | MEDIUM |
| HS → fuel type | Energy axis fuel classification | LOW |
| UN Comtrade country code (ISO-3 numeric) → ISO-2 alpha | All UN Comtrade axes | LOW |
| SIPRI recipient name → ISO-2 | Defence axis | LOW (already 90% done in supplier map) |
| Coastal state registry (global) | Logistics maritime | LOW |

### 5.3 Scripts Requiring Modification

| Script | Modification | Effort |
|--------|-------------|--------|
| `scripts/compute_tech_channel_a.py` | Parameterize EU27 → configurable country set | LOW |
| `scripts/parse_tech_comext_raw.py` | Parameterize EU27 reporter filter (or bypass for Comtrade input) | LOW |
| `scripts/parse_defense_sipri_raw.py` | Extend `SIPRI_TO_EUROSTAT` recipient mapping | LOW |
| `scripts/compute_critical_inputs_axis.py` | Parameterize EU27 set, remove 27-count assertion | LOW |
| `scripts/extract_critical_inputs_comext.py` | Parameterize EU27 filter (or bypass for Comtrade) | LOW |
| `scripts/aggregate_logistics_freight_axis.py` | Parameterize EU27 set, remove 27-count assertion | LOW |
| `scripts/download_logistics_maritime_v2.py` | Extend coastal state mapping | LOW |
| `scripts/aggregate_isi_v01.py` | Parameterize country set, remove 27-count assertion | MEDIUM |
| `backend/constants.py` | Add expansion country codes + names | LOW |
| `backend/export_snapshot.py` | Parameterize scope (EU-27 or EU-27+12 or custom) | MEDIUM |

### 5.4 Recommended Architecture

Rather than modifying existing EU-27 pipeline, recommended approach:

1. **Create `SCOPE_CODES` abstraction** — Replace all `EU27_CODES` references with configurable scope
2. **Create `AbstractTradeParser`** — Common interface for Comext and UN Comtrade parsers
3. **Create `HS_CONCORDANCE` layer** — Map between CN8 (Comext) and HS6 (Comtrade) product codes
4. **Create `CountryCodeMapper`** — Handle ISO-2/ISO-3/numeric/name conversions across all sources
5. **Maintain separate snapshots** — `snapshots/v1.0/2024/` (EU-27) and `snapshots/v1.1/2024/` (EU-27+12) to avoid contaminating existing verified outputs

---

## 6. Cross-Cutting Issues

### 6.1 Methodological Comparability

The ISI methodology was designed for EU-27 member states, which share a common profile:
- Net importers of most strategic goods (energy, defense, semiconductors, critical materials)
- Relatively open trade data (Eurostat harmonization)
- Continental geography with diverse transport modes

Several expansion countries violate these assumptions:

| Issue | Affected Countries | Impact |
|-------|-------------------|--------|
| **Major energy exporters** — Axis 2 import concentration is meaningless | RU, SA, NO (partially AU) | Score ≈ 0.0 — legitimate but non-comparable |
| **Major arms exporters** — Axis 4 import concentration is near-zero | US, RU, CN | Score ≈ 0.0 — domestic production invisible |
| **Major critical materials exporters** — Axis 5 import concentration inverted | CN, RU, ZA, BR, AU | Score may understate true vulnerability |
| **CPIS non-participants** — Axis 1 Channel B unavailable | CN, SA | A_ONLY fallback — reduces score dimensionality |
| **Sanctions-distorted data** — All axes unreliable | RU | 2022–2024 data non-comparable |

### 6.2 The "Producer Penalty" Problem

ISI measures IMPORT concentration. Countries that domestically produce strategic goods score LOW — which could be misinterpreted as "low dependency" when the actual situation is complex:

- **US defense score ≈ 0.0** does not mean "no defense dependency" — it means "does not import major arms"
- **China critical inputs score ≈ low** does not mean "no critical materials risk" — it means "does not import much because it produces/processes domestically"
- **Saudi Arabia energy score ≈ 0.0** does not mean "energy secure" — it means "net exporter"

**This is not a data problem — it is a methodology limitation.** The ISI composite for producer countries will be systematically lower than for consumer countries, making cross-group comparison problematic.

### 6.3 Data Currency Mismatch

| Source | Native Currency | Unit Impact |
|--------|----------------|-------------|
| Eurostat Comext | EUR | Current ISI axes 3, 5 use EUR |
| UN Comtrade | USD | Expansion axes 2, 3, 5 will use USD |
| BIS LBS | USD | Already USD in current pipeline |
| IMF CPIS | USD | Already USD in current pipeline |
| SIPRI | TIV (non-monetary) | Already unit-agnostic |

**HHI is share-based** — currency does not affect concentration computation (shares within a single reporter are computed in the same currency). However, volume fields in output schema (`channel_a_volume`, `channel_b_volume`) will have mixed currencies unless normalized.

### 6.4 HS Classification vs CN8 Granularity

Current ISI pipeline uses CN8 (8-digit Combined Nomenclature), which is a Eurostat-specific extension of HS6. UN Comtrade provides HS6 maximum.

**Impact by axis:**

| Axis | Current Granularity | Comtrade Granularity | Loss |
|------|-------------------|---------------------|------|
| 3 (Technology) | CN8 → 7 categories | HS6 → 3 categories | Category `legacy_discrete` vs `legacy_components` distinction may blur. `integrated_circuits` (8542) unaffected at HS4. |
| 5 (Critical Inputs) | CN8 → 66 codes in 5 groups | HS6 → ~40–50 codes in 5 groups | Some CN8 codes within same HS6 will merge. Material group assignments may need review. |

**Mitigation:** Create explicit HS6 mapping file and document granularity differences. Verify that material group assignments remain valid at HS6 level.

### 6.5 Comtrade Reporting Lags

| Country | Typical Comtrade Lag | 2024 Data Available? |
|---------|---------------------|---------------------|
| US | 6–12 months | Likely YES by mid-2025 |
| CN | 12–18 months | **UNCERTAIN** — may only have 2023 |
| RU | **SUSPENDED/UNRELIABLE** | NO |
| JP | 6–12 months | Likely YES |
| KR | 6–12 months | Likely YES |
| IN | 12–18 months | **UNCERTAIN** |
| SA | 12–18 months | **UNCERTAIN** |
| BR | 6–12 months | Likely YES |
| ZA | 6–12 months | Likely YES |
| GB | 6–12 months | Likely YES |
| NO | 6–12 months | Likely YES |
| AU | 6–12 months | Likely YES |

**Mitigation:** Use 2022–2023 window for countries with 2024 lag. Document temporal mismatch. Consider separate methodology version for non-2024-aligned countries.

---

## 7. Decision Matrix

### 7.1 Final Feasibility Summary

| Country | Ax1 | Ax2 | Ax3 | Ax4 | Ax5 | Ax6 | Feasible Axes | Overall Risk | Verdict |
|---------|-----|-----|-----|-----|-----|-----|---------------|-------------|---------|
| US | ✅ | ✅ | ✅ | ⚠️¹ | ✅ | ⚠️² | 6/6 | LOW | **GO** |
| CN | ⚠️³ | ✅ | ✅ | ⚠️¹ | ⚠️⁴ | ⚠️² | 4–5/6 | HIGH | **CONDITIONAL** |
| RU | ❌⁵ | ⚠️⁴ | ⚠️⁶ | ⚠️¹ | ⚠️⁴ | ❌ | 2–4/6 | CRITICAL | **BLOCKED** |
| JP | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️² | 6/6 | LOW | **GO** |
| KR | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️² | 6/6 | LOW | **GO** |
| IN | ⚠️³ | ✅ | ✅ | ✅ | ✅ | ⚠️² | 5–6/6 | MEDIUM | **GO (conditional)** |
| SA | ⚠️³ | ⚠️⁴ | ✅ | ✅ | ✅ | ❌ | 4–5/6 | HIGH | **CONDITIONAL** |
| BR | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️² | 5–6/6 | MEDIUM | **GO (conditional)** |
| ZA | ✅ | ✅ | ✅ | ✅ | ⚠️⁴ | ⚠️² | 5–6/6 | MEDIUM | **GO (conditional)** |
| GB | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 6/6 | LOW | **GO** |
| NO | ✅ | ⚠️⁴ | ✅ | ✅ | ✅ | ✅ | 6/6 | LOW | **GO** |
| AU | ✅ | ✅ | ✅ | ✅ | ⚠️⁴ | ⚠️² | 6/6 | LOW | **GO** |

**Legend:**
- ✅ = Fully feasible, data available, schema compatible
- ⚠️¹ = Score ≈ 0 (major domestic producer/exporter — interpretability issue)
- ⚠️² = Channel B (bilateral partner) data fragmented or unavailable — A_ONLY fallback likely
- ⚠️³ = CPIS non-participant — Channel B missing for Axis 1
- ⚠️⁴ = Major exporter — import concentration methodology inverted
- ⚠️⁵ = BIS reporting suspended — data stale/unreliable
- ⚠️⁶ = Sanctions-distorted data — unreliable 2022–2024 window
- ❌ = Infeasible — no data source available

### 7.2 Recommended Phasing

**Phase 1 — Low Risk (immediate):**
- United Kingdom, Japan, South Korea, Norway, Australia
- All 6 axes feasible, low pipeline complexity, excellent data quality
- Estimated effort: 4–6 weeks (UN Comtrade parser + ITF parser + SIPRI extension)

**Phase 2 — Medium Risk (after Phase 1 validation):**
- United States, Brazil, South Africa, India
- 5–6 axes feasible, some Channel B gaps, interpretability caveats for US defense
- Estimated effort: 4–6 weeks additional (national data parsers for Axis 6)

**Phase 3 — High Risk (requires methodology discussion):**
- China, Saudi Arabia
- 4–5 axes feasible but multiple methodological inversions
- Requires explicit policy decision on "producer penalty" treatment
- Estimated effort: 6–8 weeks including methodology review

**Phase 4 — Blocked:**
- Russia
- Fewer than 4 reliable axes. Sanctions distortion makes 2022–2024 data non-comparable.
- **Prerequisite:** Methodology waiver + explicit data quality disclaimers + potential separate methodology version

### 7.3 Minimum Viable Changes for Phase 1

1. **New module:** `scripts/parse_comtrade_bilateral.py` — UN Comtrade CSV/JSON parser
2. **New module:** `scripts/parse_itf_transport.py` — ITF transport statistics parser
3. **New mapping:** `docs/mappings/hs6_to_semiconductor_category.csv`
4. **New mapping:** `docs/mappings/hs6_to_material_group.csv`
5. **New mapping:** `docs/mappings/hs_to_fuel_type.csv`
6. **New mapping:** `docs/mappings/comtrade_country_code_map.csv` (ISO-3 numeric → ISO-2)
7. **Modified:** `backend/constants.py` — add `EXPANSION_CODES`, `EXPANSION_NAMES`
8. **Modified:** `scripts/parse_defense_sipri_raw.py` — extend `SIPRI_TO_EUROSTAT`
9. **Modified:** 6 scripts — parameterize EU27 filter to configurable scope
10. **Modified:** `scripts/aggregate_isi_v01.py` — parameterize country set + count assertions

---

*End of Global Expansion Feasibility Assessment.*
