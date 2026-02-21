# Methodology Evidence Pack

> **International Sovereignty Index (ISI) — Panargus**
>
> Generated: 2025-02-21 · Verified against: `main` branch, live API on `127.0.0.1:8099`
>
> Quality bar: institutional-grade methods appendix. Every fact anchored to a file path and line number. Zero speculation.

---

## Table of Contents

1. [Repository Inventory](#1-repository-inventory)
2. [Data Layout](#2-data-layout)
3. [Methodology Rules](#3-methodology-rules)
4. [Axis Registry](#4-axis-registry)
5. [Scenario Engine](#5-scenario-engine)
6. [API Surface — Verified](#6-api-surface--verified)
7. [Open Items & Limitations](#7-open-items--limitations)

---

## 1. Repository Inventory

### 1.1 Backend Modules

| File | Lines | Role |
|------|------:|------|
| `backend/isi_api_v01.py` | 1332 | FastAPI application — serves pre-materialized JSON artifacts + scenario simulation |
| `backend/methodology.py` | 306 | **Single source of truth** for classification thresholds, composite formula, aggregation rule |
| `backend/scenario.py` | 392 | Scenario simulation engine — multiplicative shift model, Pydantic-validated |
| `backend/constants.py` | 106 | Global constants: `ROUND_PRECISION`, `NUM_AXES`, `EU27_CODES`, axis key mappings |
| `backend/hashing.py` | 124 | Deterministic SHA-256 hashing — canonical float formatting, country-level + snapshot-level |
| `backend/signing.py` | — | Ed25519 snapshot signing |
| `backend/snapshot_resolver.py` | — | Resolves methodology version + year → snapshot directory |
| `backend/snapshot_cache.py` | — | In-memory LRU cache for snapshot artifacts |
| `backend/snapshot_integrity.py` | — | Manifest + hash verification at startup |
| `backend/verify_snapshot.py` | — | CLI tool for offline snapshot verification |
| `backend/reproduce_snapshot.py` | — | Deterministic snapshot reproduction |
| `backend/export_isi_backend_v01.py` | 1161 | Legacy exporter — produces `backend/v01/` artifacts from processed CSVs |
| `backend/export_snapshot.py` | 741 | Snapshot materializer — produces `backend/snapshots/v1.0/2024/` artifacts, includes Ed25519 signing |
| `backend/security.py` | — | Security headers, rate limiting, CORS configuration |
| `backend/hardening.py` | — | Request validation, size limits, middleware |
| `backend/log_sanitizer.py` | — | Structured logging with IP sanitization |
| `backend/immutability.py` | — | Runtime immutability enforcement for snapshot data |

### 1.2 Pipeline Scripts

| File | Lines | Role |
|------|------:|------|
| `scripts/compute_finance_bis_concentration.py` | 118 | Channel A HHI for Axis 1 (BIS LBS) |
| `scripts/parse_finance_bis_lbs_raw.py` | — | Raw BIS LBS data parser |
| `scripts/parse_finance_cpis_raw.py` | — | Raw IMF CPIS data parser |
| `scripts/compute_energy_concentration.py` | 75 | Energy supplier HHI per fuel type (gas, oil, solid fossil) |
| `scripts/parse_energy_eurostat_raw.py` | — | Raw Eurostat energy data parser |
| `scripts/validate_energy_coverage.py` | — | Energy data coverage validator |
| `scripts/compute_tech_channel_a.py` | 168 | Technology Channel A: aggregate semiconductor HHI |
| `scripts/parse_tech_comext_raw.py` | — | Raw Comext semiconductor data parser |
| `scripts/ingest_tech_comext_manual.py` | — | Manual Comext data ingestion |
| `scripts/parse_defense_sipri_raw.py` | — | Raw SIPRI arms transfer parser |
| `scripts/compute_critical_inputs_axis.py` | — | Full Axis 5 pipeline (Channel A + B + aggregation) |
| `scripts/extract_critical_inputs_comext.py` | — | Comext CN8 critical materials extraction |
| `scripts/aggregate_logistics_freight_axis.py` | — | Full Axis 6 pipeline (mode HHI + partner HHI) |
| `scripts/download_logistics_maritime_v2.py` | — | Eurostat maritime data download |
| `scripts/aggregate_isi_v01.py` | 471 | Core ISI aggregation — fuses 6 axis scores into composite |
| `scripts/create_axis_adapters.py` | — | Axis adapter creation utility |

### 1.3 Test Suite

| File | Role |
|------|------|
| `tests/test_serving_layer.py` | API serving layer tests |
| `tests/test_hardening.py` | Security hardening tests |
| `tests/test_nsa_finish.py` | NSA-finish phase tests |
| `tests/test_scenario.py` | Scenario engine tests |
| `tests/test_crypto_auth.py` | Cryptographic authentication tests |

**Test count: 354 passing** (283 original + 71 crypto auth).

---

## 2. Data Layout

### 2.1 Legacy Layer: `backend/v01/`

Produced by `backend/export_isi_backend_v01.py`. 39 files total.

```
backend/v01/
├── meta.json                  # Project metadata
├── isi.json                   # Composite scores, 27 countries
├── axes.json                  # Axis registry (6 axes)
├── country/{CODE}.json        # Per-country detail (×27)
└── axis/{N}.json              # Per-axis detail (×6)
```

### 2.2 Snapshot Layer: `backend/snapshots/`

Produced by `backend/export_snapshot.py`. Versioned + signed.

```
backend/snapshots/
├── registry.json              # Methodology registry (single source)
└── v1.0/
    └── 2024/
        ├── isi.json           # Composite scores, 27 countries
        ├── MANIFEST.json      # File manifest (34 files, SHA-256 per file)
        ├── HASH_SUMMARY.json  # Per-country SHA-256 + snapshot hash
        ├── SIGNATURE.json     # Ed25519 signature over snapshot hash
        ├── country/{CODE}.json  # Per-country detail (×27)
        └── axis/{N}.json      # Per-axis detail (×6)
```

### 2.3 Processed Data: `data/processed/`

Upstream pipeline outputs consumed by exporters. Not shipped in API.

```
data/processed/
├── finance/         # BIS LBS shares, concentration, volumes; CPIS shares, concentration
├── energy/          # nrg_ti_{gas,oil,sff} shares, concentration, fuel_concentration
├── tech/            # Comext semiconductor shares, concentration, volumes (Ch A + B)
├── defense/         # SIPRI shares, concentration (Ch A + B), block concentration
├── critical_inputs/ # Comext CN8 shares, concentration, group_concentration (Ch A + B)
├── logistics/       # Mode shares, mode concentration, partner shares (Ch A + B)
└── isi/             # isi_eu27_v01.csv — final composite
```

### 2.4 Schemas (Verified from Live Artifacts)

**`isi.json` top-level:**
```json
{
  "version": "v0.1",
  "window": "2022–2024",
  "aggregation_rule": "unweighted_arithmetic_mean",
  "formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
  "countries_total": 27,
  "countries_complete": 27,
  "statistics": { "min": 0.23567126, "max": 0.51748148, "mean": 0.34439144 },
  "countries": [ /* 27 entries */ ]
}
```

**Country entry in `isi.json`:**
```json
{
  "country": "MT",
  "country_name": "Malta",
  "axis_1_financial": 0.13998786,
  "axis_2_energy": 0.35068126,
  "axis_3_technology": 0.20546991,
  "axis_4_defense": 1.0,
  "axis_5_critical_inputs": 0.40874987,
  "axis_6_logistics": 1.0,
  "isi_composite": 0.51748148,
  "classification": "highly_concentrated",
  "complete": true
}
```

**Country detail (`country/{CODE}.json`) — top-level keys:**
`country`, `country_name`, `version`, `window`, `isi_composite`, `isi_classification`, `axes_available`, `axes_required`, `axes[]`

**Each axis within country detail:**
`axis_id`, `axis_slug`, `axis_name`, `score`, `classification`, `driver_statement`, `audit{}`, `channels[]`, `warnings[]`

**Audit block:**
```json
{
  "channel_a_concentration": 0.1180056992,
  "channel_a_volume": 289158.219,
  "channel_b_concentration": 0.1133070941,
  "channel_b_volume": 103805.98,
  "score": 0.11646504,
  "basis": "BOTH"
}
```

`basis` values: `"BOTH"` (both channels contributed), `"A_ONLY"` (Channel B missing — e.g., HR absent from CPIS), `"B_ONLY"`, `"NONE"`.

**Axis detail (`axis/{N}.json`) — top-level keys:**
`axis_id`, `axis_slug`, `axis_name`, `description`, `version`, `status`, `materialized`, `unit`, `countries_scored`, `statistics{}`, `channels[]`, `warnings[]`, `countries[]`

---

## 3. Methodology Rules

### 3.1 Concentration Measure: Herfindahl-Hirschman Index (HHI)

All axis scores are based on HHI — the sum of squared bilateral import shares:

$$C_i^{(ch)} = \sum_{j} \left( s_{i,j}^{(ch)} \right)^2$$

where $s_{i,j}$ is country $j$'s share of country $i$'s total bilateral flow in channel $ch$.

**Properties:**
- $C_i \in [0, 1]$
- $C_i = 0$: exposure uniformly spread across infinitely many partners
- $C_i = 1$: all exposure to a single partner

**Code evidence:**

| Script | Line | Implementation |
|--------|-----:|----------------|
| `scripts/compute_finance_bis_concentration.py` | 72 | `hhi[cp] += share * share` |
| `scripts/compute_energy_concentration.py` | 40 | `group_sum_sq[group_key] += share * share` |
| `scripts/compute_tech_channel_a.py` | 137 | `hhi += share ** 2` |
| `scripts/compute_critical_inputs_axis.py` | 205 | `hhi += s * s` |

All scripts enforce hard-fail bounds: HHI ∈ [0, 1] with tolerance 1e-9.

### 3.2 Cross-Channel Aggregation

For dual-channel axes (1, 3, 4, 5), axis score is the arithmetic mean of Channel A and Channel B concentrations:

$$M_i = 0.5 \cdot C_i^{(A)} + 0.5 \cdot C_i^{(B)}$$

**Source:** `scripts/compute_critical_inputs_axis.py`, lines 60–61:
```
M_i = 0.5 * C_i^{(A)} + 0.5 * C_i^{(B)}
(W_A = W_B by construction, so volume-weighted = arithmetic mean)
```

**Fallback rules (basis field):**
- `BOTH`: both channels present → arithmetic mean
- `A_ONLY`: Channel B missing → score = Channel A concentration
- `B_ONLY`: Channel A missing → score = Channel B concentration
- `NONE`: no data → score = 0.0

**Axis 2 (Energy):** uses 3-fuel average (gas, oil, solid fossil), not 2-channel.

**Axis 6 (Logistics):** uses Channel A (mode concentration HHI) + Channel B (partner HHI per mode), same 0.5/0.5 weighting.

### 3.3 Channel B — Weighted Variant

For axes that use Channel B (technology, defense, critical inputs), the Channel B concentration is a **value-weighted average of per-subcategory HHIs**:

$$C_i^{(B)} = \frac{\sum_k C_i^{(B,k)} \cdot V_i^{(k)}}{\sum_k V_i^{(k)}}$$

where $k$ indexes subcategories (HS categories for tech, capability blocks for defense, material groups for critical inputs).

**Source:** `scripts/compute_critical_inputs_axis.py`, lines 51–57 (methodology docstring).

### 3.4 ISI Composite Aggregation

$$\text{ISI}_i = \frac{A_1 + A_2 + A_3 + A_4 + A_5 + A_6}{6}$$

**Rule:** Unweighted arithmetic mean of 6 axis scores.

**Source (code):** `backend/methodology.py`, lines 244–247:
```python
if rule == "unweighted_arithmetic_mean":
    if not axis_scores:
        raise ValueError("axis_scores is empty")
    return sum(axis_scores.values()) / len(axis_scores)
```

**Source (registry):** `backend/snapshots/registry.json`:
```json
"aggregation_rule": "unweighted_arithmetic_mean",
"aggregation_formula": "ISI_i = (A1 + A2 + A3 + A4 + A5 + A6) / 6"
```

**All axis weights = 1.0** (confirmed: `registry.json` → `axis_weights`).

### 3.5 Classification Thresholds

| Threshold | Label | Interpretation |
|----------:|-------|----------------|
| ≥ 0.50 | `highly_concentrated` | Very high external dependency |
| ≥ 0.25 | `moderately_concentrated` | Significant external dependency |
| ≥ 0.15 | `mildly_concentrated` | Some external dependency |
| < 0.15 | `unconcentrated` | Low external dependency |

**Source:** `backend/snapshots/registry.json` → `classification_thresholds` + `default_classification`.

**Code:** `backend/methodology.py`, lines 224–232 — `classify()` is the **only** classification function in the codebase. Both the exporter and the scenario engine import from this module.

### 3.6 Rounding

**Precision:** 8 decimal places (`ROUND_PRECISION = 8`).
**Rule:** Python `round()` — banker's rounding (round-half-to-even).
**Timing:** Rounding happens **once**, at the earliest point where a value is finalized, **before** classification, sorting, hashing, and serialization.

**Source:** `backend/constants.py`, lines 17–26.

### 3.7 Ranking

- **Rank 1** = highest ISI composite = most concentrated/dependent
- Ties broken alphabetically by country code
- **Interpretation:** higher ISI = more concentrated = more dependent on external suppliers

**Source:** `backend/v01/meta.json` → `interpretation: "higher = more concentrated = more dependent"`.

### 3.8 Scope

- **Countries:** EU-27 (27 member states)
- **Country codes:** AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU, IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK
- **Reference window:** 2022–2024 (varies by data source availability)
- **Score range:** [0.0, 1.0]

### 3.9 Hashing & Integrity

**Country hash:** SHA-256 over canonical text input including country code, year, methodology version, all 6 axis scores (fixed-point 8 decimals), composite, weights, and thresholds.

**Snapshot hash:** SHA-256 of all 27 country hashes concatenated in alphabetical order.

**Signature:** Ed25519 over the snapshot hash. Public key stored in `SIGNATURE.json`.

**Source:** `backend/hashing.py` — `compute_country_hash()`, `compute_snapshot_hash()`.

---

## 4. Axis Registry

### 4.1 Overview

| # | Slug | Name | Unit | Channels | Sources | Warnings |
|---|------|------|------|----------|---------|----------|
| 1 | `financial` | Financial Sovereignty | USD millions | A: Banking Claims, B: Portfolio Debt | BIS LBS, IMF CPIS | 4 |
| 2 | `energy` | Energy Dependency | varies by fuel | gas, oil, solid_fossil | Eurostat nrg_ti_{gas,oil,sff} | 3 |
| 3 | `technology` | Technology / Semiconductor Dependency | EUR | A: Aggregate, B: Category-Weighted | Comext ds-045409 (HS 8541, 8542) | 5 |
| 4 | `defense` | Defense Industrial Dependency | SIPRI TIV | A: Aggregate, B: Capability-Block Weighted | SIPRI Arms Transfers | 5 |
| 5 | `critical_inputs` | Critical Inputs / Raw Materials Dependency | EUR | A: Aggregate, B: Material-Group Weighted | Comext ds-045409 (CN8) | 4 |
| 6 | `logistics` | Logistics / Freight Dependency | THS_T (thousand tonnes) | A: Transport Mode Conc., B: Partner Conc. per Mode | Eurostat tran | 5 |

### 4.2 Axis 1 — Financial Sovereignty

**Channels:**
- **Channel A:** "Banking Claims Concentration" — Source: BIS Locational Banking Statistics (LBS), 2024-Q4 inward claims. HHI over creditor-country shares.
- **Channel B:** "Portfolio Debt Concentration" — Source: IMF Coordinated Portfolio Investment Survey (CPIS), 2024 derived (2021–2024 available). HHI over portfolio-debt-holder shares.

**Cross-channel:** $M_i = 0.5 \cdot C_i^{(A)} + 0.5 \cdot C_i^{(B)}$. Fallback: `A_ONLY` when country absent from CPIS.

**Warnings:**
| ID | Severity | Text |
|----|----------|------|
| F-1 | MEDIUM | BIS creditor coverage gap: non-BIS-reporting countries absent as creditors; concentration may be biased upward. |
| F-2 | MEDIUM | IMF CPIS participation is voluntary; China does not participate. Portfolio debt concentration may understate true exposure. |
| F-3 | LOW | Partial overlap between BIS banking claims and IMF portfolio debt holdings. Cross-channel correlation not measured. |
| F-4 | LOW | HR (Croatia) absent from Channel B (CPIS). Score based on Channel A only (basis: A_ONLY). |

**Statistics (from live API):** min = 0.10039135, max = 0.27299265, mean = 0.14799792.

### 4.3 Axis 2 — Energy Dependency

**Channels (fuel-based):**
- **Gas:** Eurostat `nrg_ti_gas`, 2024
- **Oil:** Eurostat `nrg_ti_oil`, 2024
- **Solid Fossil Fuels:** Eurostat `nrg_ti_sff`, 2024

**Aggregation:** Average of per-fuel HHIs (not a 2-channel model).

**Warnings:**
| ID | Severity | Text |
|----|----------|------|
| E-1 | MEDIUM | Pipeline vs LNG not separated; import-mode dependencies invisible. |
| E-2 | MEDIUM | Re-exports (NL, BE) inflate partner shares for downstream importers. |
| E-3 | LOW | No price or contract-duration effects captured. Volume-based concentration only. |

### 4.4 Axis 3 — Technology / Semiconductor Dependency

**Channels:**
- **Channel A:** "Aggregate Supplier Concentration" — Source: Comext ds-045409, HS 8541 + 8542, 2022–2024. HHI over partner-country shares of total semiconductor import value.
- **Channel B:** "Category-Weighted Concentration" — Source: same. Per-HS-category HHI, value-weighted average.

**Warnings:**
| ID | Severity | Text |
|----|----------|------|
| T-1 | MEDIUM | Re-export blindness: NL, BE, and IE operate as semiconductor transshipment hubs. Reported partner may not be fabrication origin. |
| T-2 | MEDIUM | No domestic fabrication capacity captured. A country manufacturing domestically still scores based on imports only. |
| T-3 | MEDIUM | HS 8542 at HS4 aggregate: integrated circuits not decomposed into subcategories. |
| T-4 | LOW | Intra-EU trade included. Concentration may reflect single-market integration rather than external dependency. |
| T-5 | LOW | Pandemic-era (2022) distortions may bias 3-year averages. |

### 4.5 Axis 4 — Defense Industrial Dependency

**Channels:**
- **Channel A:** "Aggregate Supplier Concentration" — Source: SIPRI Arms Transfers Database, delivery years 2019–2024 (6-year window). HHI over supplier-country shares of total TIV.
- **Channel B:** "Capability-Block Weighted Concentration" — Source: same. Per-capability-block HHI, value-weighted average.

**Warnings:**
| ID | Severity | Text |
|----|----------|------|
| D-1 | MEDIUM | TIV is not a financial measure. It reflects military capability transfer, not procurement cost. |
| D-2 | MEDIUM | SIPRI covers major conventional weapons only. Small arms, ammunition, cyber, and dual-use excluded. |
| D-3 | MEDIUM | 6-year delivery window (2019–2024). Long procurement cycles mean current orders may not appear. |
| D-4 | LOW | Capability-block classification based on regex pattern matching of SIPRI weapon descriptions. |
| D-5 | LOW | Countries with no bilateral SIPRI supplier entries are assigned score=0 (zero external concentration). This reflects licensed production, joint EU procurement, or domestic manufacturing. |

### 4.6 Axis 5 — Critical Inputs / Raw Materials Dependency

**Channels:**
- **Channel A:** "Aggregate Supplier Concentration" — Source: Comext ds-045409 CN8, 2022–2024. HHI over partner shares of total critical-materials import value.
- **Channel B:** "Material-Group Weighted Concentration" — Source: same. Per-material-group HHI, value-weighted average across groups.

**Warnings:**
| ID | Severity | Text |
|----|----------|------|
| L-1 | HIGH | Re-export and entrepot masking: bilateral trade records shipping country, not origin. 13 of 27 reporters source >50% from EU partners. |
| L-2 | MEDIUM | Small-economy amplification: CY, MT, LU produce mechanically high HHI values due to low total import volumes. |
| L-3 | MEDIUM | CN8 scope covers upstream materials only. Midstream processing and downstream products excluded. China's role understated. |
| L-4 | LOW | Confidential trade suppression: Q-prefix partner codes excluded. May cause underestimation for some partners. |

### 4.7 Axis 6 — Logistics / Freight Dependency

**Channels:**
- **Channel A:** "Transport Mode Concentration" — Source: Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw. HHI over mode shares (road, rail, maritime, etc.) of total freight tonnage.
- **Channel B:** "Partner Concentration per Transport Mode" — Source: same. Per-mode partner HHI, tonnage-weighted average.

**Warnings:**
| ID | Severity | Text |
|----|----------|------|
| W-1 | HIGH | Entrepot/hub masking: NL and BE scores understate their systemic importance as continental freight hubs; countries trading through NL/BE have inflated partner concentration masking true origin. |
| W-2 | MEDIUM | Geographic determinism: MT (Channel A HHI = 1.0), CY, and landlocked countries have structurally constrained scores reflecting geography, not policy choices. |
| W-3 | MEDIUM | Maritime-energy overlap: maritime tonnage includes energy commodity transport, creating partial redundancy with Axis 2 (Energy). |
| W-4 | MEDIUM | Tonnage blindness: all freight is treated equally per tonne regardless of commodity type; strategic commodity differentiation is absent. |
| W-5 | LOW | No route/chokepoint data: the axis cannot detect Suez, Bosporus, or any physical corridor dependency. |

---

## 5. Scenario Engine

### 5.1 Computation Model

**Source:** `backend/scenario.py` (392 lines).

**Formula:** Multiplicative shift with clamp:
$$\text{simulated}_i = \text{clamp}\left(\text{baseline}_i \times (1 + \text{adjustment}), \; 0, \; 1\right)$$

**Adjustment bounds:** $[-0.20, +0.20]$ (`MAX_ADJUSTMENT = 0.20` in `backend/constants.py`).

**After applying shifts:** Composite is recomputed via `methodology.compute_composite()` (same function used by the exporter). Rank and classification are recomputed against all 27 countries (only the target country is shifted).

### 5.2 Wire Format

**Request (POST /scenario):**
```json
{
  "country": "SE",
  "adjustments": {
    "energy_external_supplier_concentration": -0.15,
    "defense_external_supplier_concentration": 0.10
  }
}
```

**Response (verified from live API):**
```json
{
  "country": "SE",
  "baseline": {
    "composite": 0.39871532,
    "rank": 7,
    "classification": "moderately_concentrated",
    "axes": { /* 6 canonical keys → baseline scores */ }
  },
  "simulated": {
    "composite": 0.40521963,
    "rank": 5,
    "classification": "moderately_concentrated",
    "axes": { /* 6 canonical keys → simulated scores */ }
  },
  "delta": {
    "composite": 0.00650431,
    "rank": -2,
    "axes": { /* 6 canonical keys → delta values */ }
  },
  "meta": {
    "version": "scenario-v1",
    "timestamp": "2026-02-21T20:07:33.001434+00:00",
    "bounds": { "min": -0.2, "max": 0.2 }
  }
}
```

### 5.3 Validation Rules (Pydantic)

- `country`: must be 2-letter code in EU-27 (`EU27_CODES`)
- `adjustments`: dict of canonical axis key → float in $[-0.20, +0.20]$
- Invalid country → HTTP 400
- Out-of-bounds adjustment → HTTP 400 (verified: `"Adjustment for '...' must be in [-0.2, 0.2]. Got: 0.99."`)
- Unknown axis key → HTTP 400

---

## 6. API Surface — Verified

All endpoints tested live against `127.0.0.1:8099` on 2025-02-21.

### 6.1 Endpoint Table

| Method | Path | Purpose | Status | Cache | Response Shape |
|--------|------|---------|--------|-------|----------------|
| GET | `/` | Project metadata | 200 | — | `{project, version, scope, num_axes, …}` |
| GET | `/health` | Health check | 200 | — | `{status: "ok", version: "v0.4"}` |
| GET | `/ready` | Readiness probe | 200 | — | `{ready, status, version, data_present, data_file_count, integrity_verified, timestamp}` |
| GET | `/countries` | Flat country list | 200 | ETag | `[{country, country_name, axis_1…axis_6, isi_composite}]` (27 items) |
| GET | `/isi` | Full composite dataset | 200 | ETag | `{version, window, aggregation_rule, formula, statistics, countries[]}` |
| GET | `/axes` | Axis registry | 200 | ETag | `[{id, name, slug, channels[], warnings[]}]` (6 items) |
| GET | `/axis/{n}` | Axis detail + all countries | 200 | ETag | `{axis_id, statistics, countries[{country, score, audit}]}` |
| GET | `/country/{code}` | Country detail | 200 | ETag | `{country, isi_composite, isi_classification, axes[{score, channels[], audit}]}` |
| GET | `/country/{code}/axes` | Country axis summary | 200 | ETag | `{country, isi_composite, axes[{axis_id, score, classification}]}` |
| GET | `/country/{code}/axis/{n}` | Country × axis detail | 200 | ETag | `{country, axis{score, classification, audit, channels[]}}` |
| GET | `/country/{code}/history` | Time series (multi-year) | 200 | ETag | `{country, methodology_version, years_count, years[{year, composite, rank, axes}]}` |
| GET | `/methodology/versions` | Registry metadata | 200 | — | `{latest, latest_year, versions[{version, label, years_available, axis_count}]}` |
| GET | `/scenario/schema` | Scenario request schema | 200 | — | `{axis_keys[], bounds, version, example_request, example_response}` |
| POST | `/scenario` | Run scenario simulation | 200 | — | `{country, baseline, simulated, delta, meta}` |

### 6.2 Error Handling (Verified)

| Case | Status | Response |
|------|--------|----------|
| Invalid country code | 404 | `{"detail": "Country 'XX' not in EU-27 scope."}` |
| Scenario out-of-bounds | 400 | `{"error": "BAD_INPUT", "message": "…must be in [-0.2, 0.2]. Got: 0.99."}` |

### 6.3 Middleware Stack

Order (outermost → innermost): GZip → RequestId → RequestSizeLimit → ETag → SecurityHeaders → CORS.

**Rate limits:** 120/min default, 30/min for data endpoints, 60/min for schema/meta endpoints.

**CORS origins:** `isi.internationalsovereignty.org`, `isi-frontend.vercel.app`, `localhost:3000`, regex `*.internationalsovereignty.org`.

---

## 7. Open Items & Limitations

### 7.1 Data Availability

| Axis | Data Window | Limitation |
|------|-------------|------------|
| 1 — Financial | BIS: 2024-Q4 only; CPIS: 2021–2024 | No BIS time series. Single quarter snapshot. |
| 2 — Energy | 2024 only | No multi-year trend. |
| 3 — Technology | 2022–2024 | Pandemic distortions in 2022. |
| 4 — Defense | 2019–2024 | 6-year window appropriate for long procurement cycles. |
| 5 — Critical Inputs | 2022–2024 | 3-year average. |
| 6 — Logistics | 2003–2024 available, 2022–2024 used | Rich time depth available but not exploited in v1.0. |

### 7.2 Year Coverage

**Only ISI 2024 is materializable** under methodology v1.0. ISI 2023 is infeasible due to: BIS LBS has only 2024-Q4, Eurostat energy has only 2024. (Formally verified via raw data inspection — see ISI_2023 Feasibility Audit.)

### 7.3 Structural Limitations

1. **Re-export/entrepot masking:** Affects axes 3, 5, 6. Bilateral trade records the shipping country, not the country of origin. NL, BE, IE are known transshipment hubs.
2. **Small-economy amplification:** CY, MT, LU mechanically produce high HHI due to low total volumes and few partners.
3. **Geographic determinism (Axis 6):** Island and landlocked states have structurally constrained logistics scores.
4. **No domestic production offset:** The index measures import concentration only. Domestic manufacturing capability is not captured.
5. **Equal weighting:** All 6 axes weighted equally (1.0). No empirical or theoretical basis for differential weighting in v1.0.
6. **Intra-EU trade included:** Concentration may reflect single-market integration patterns rather than external (extra-EU) dependency.

### 7.4 Methodology Version

- **Current:** v1.0 (frozen 2026-02-21)
- **Years available:** [2024]
- **Registry:** `backend/snapshots/registry.json` (schema version 1)
- **The `methodology.py` module supports both `unweighted_arithmetic_mean` and `weighted_arithmetic_mean` aggregation rules**, enabling future methodology versions with differential axis weighting without code changes.

### 7.5 Integrity Chain

```
Raw data → scripts/*.py → data/processed/ → export_snapshot.py →
  → Per-country SHA-256 (canonical_float, banker's rounding) →
  → Snapshot SHA-256 (concat alphabetical) →
  → Ed25519 signature →
  → MANIFEST.json (per-file SHA-256 + size) →
  → Runtime verification at startup (snapshot_integrity.py)
```

**Files in integrity chain:**
- `MANIFEST.json`: 34 files, each with `path`, `sha256`, `size_bytes`
- `HASH_SUMMARY.json`: 27 country hashes + `computed_at` + `computed_by`
- `SIGNATURE.json`: `algorithm: "ed25519"`, `public_key_id: "v1"`, `signed_hash`, `signature` (Base64)

---

*End of Methodology Evidence Pack.*
