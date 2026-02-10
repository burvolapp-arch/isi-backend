# ISI API Contract v0.1 — Frontend-Facing Interface Specification

**Status:** FROZEN
**Version:** v0.1
**Base URL:** `http://{host}:8000`
**Protocol:** HTTP/1.1, JSON over REST
**Methods:** GET only (read-only API)
**Auth:** None (public)
**CORS:** `*` (all origins)
**Server:** FastAPI + Uvicorn
**Computation:** ZERO. Every response is a file read from `backend/v01/`. No server-side computation ever occurs at request time.
**Source of truth:** `backend/isi_api_v01.py` (router) + `backend/export_isi_backend_v01.py` (materializer)

---

## 1. Endpoint Index

| # | Method | Path | Purpose | Response Type |
|---|--------|------|---------|---------------|
| 1 | GET | `/` | API metadata and versioning | `object` |
| 2 | GET | `/health` | Backend data availability check | `object` |
| 3 | GET | `/countries` | All 27 countries with summary scores | `array` |
| 4 | GET | `/country/{code}` | Full detail for one country (all axes, channels, partners, warnings) | `object` |
| 5 | GET | `/country/{code}/axes` | All axis scores for one country (lightweight) | `object` |
| 6 | GET | `/country/{code}/axis/{axis_id}` | Single axis detail for one country | `object` |
| 7 | GET | `/axes` | Axis registry (all 6 axes with metadata) | `array` |
| 8 | GET | `/axis/{axis_id}` | Full axis detail across all 27 countries | `object` |
| 9 | GET | `/isi` | Composite ISI scores for all countries | `object` |

**Auto-generated docs:**
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`

---

## 2. Data Pipeline Architecture

```
CSV on disk (frozen)
        │
        ▼
export_isi_backend_v01.py  ──►  backend/v01/*.json  (PRECOMPUTED, STATIC)
                                        │
                                        ▼
                               isi_api_v01.py  ──►  JSON responses (FILE READ ONLY)
```

| Layer | What happens | When |
|-------|-------------|------|
| Axis pipelines | Compute HHI scores from raw Eurostat/BIS/SIPRI/Comext data | Offline, once |
| Aggregator | Compute ISI composite = mean(A1..A6) | Offline, once |
| Exporter | Read CSVs → write structured JSON to `backend/v01/` | Offline, once |
| API server | Read JSON files from disk → serve to frontend | At request time |

**What is PRECOMPUTED (CSV-backed):** All axis scores, all channel concentrations, all partner shares, all subcategory breakdowns, all audit data.

**What is COMPUTED server-side at export time:** ISI composite (arithmetic mean of 6 axes), classifications, driver statements, rankings, statistics (min/max/mean). These are baked into the JSON artifacts.

**What is COMPUTED at request time:** Nothing. Zero. The `/country/{code}/axes` endpoint slices a cached JSON object — no arithmetic.

**What will NEVER be computed on the frontend:** Scores, rankings, classifications, HHI values, partner shares. The frontend renders what the API gives it.

---

## 3. Endpoint Specifications

---

### 3.1 `GET /`

**Purpose:** Returns ISI project metadata, version, scope, and aggregation formula.

**Parameters:** None.

**Response shape:**

```jsonc
{
  "project":           string,   // "Panargus / International Sovereignty Index (ISI)"
  "version":           string,   // "v0.1"
  "reference_window":  string,   // "2022–2024"
  "scope":             string,   // "EU-27"
  "num_axes":          number,   // 6 — always 6
  "num_countries":     number,   // 27 — always 27
  "aggregation_rule":  string,   // "unweighted_arithmetic_mean"
  "aggregation_formula": string, // "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6"
  "score_range":       [number, number], // [0.0, 1.0]
  "interpretation":    string,   // "higher = more concentrated = more dependent"
  "generated_by":      string    // "export_isi_backend_v01.py"
}
```

**Invariants:**
- `num_axes` is always `6`.
- `num_countries` is always `27`.
- `score_range` is always `[0.0, 1.0]`.
- All values are static. They do not change between requests.

**Data origin:** `backend/v01/meta.json` — STATIC.

**Error:** `503` if `meta.json` is missing (exporter not run).

**Example response:**

```json
{
  "project": "Panargus / International Sovereignty Index (ISI)",
  "version": "v0.1",
  "reference_window": "2022–2024",
  "scope": "EU-27",
  "num_axes": 6,
  "num_countries": 27,
  "aggregation_rule": "unweighted_arithmetic_mean",
  "aggregation_formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
  "score_range": [0.0, 1.0],
  "interpretation": "higher = more concentrated = more dependent",
  "generated_by": "export_isi_backend_v01.py"
}
```

---

### 3.2 `GET /health`

**Purpose:** Returns backend data availability status for monitoring.

**Parameters:** None.

**Response shape:**

```jsonc
{
  "status":               string,  // "ok" | "degraded"
  "backend_root":         string,  // absolute path to backend/v01/
  "meta":                 boolean, // true if meta.json exists
  "countries_summary":    boolean, // true if countries.json exists
  "isi_composite":        boolean, // true if isi.json exists
  "country_detail_files": number,  // count of country/*.json files (target: 27)
  "axis_detail_files":    number   // count of axis/*.json files (target: 6)
}
```

**Invariants:**
- `status` is `"ok"` iff `meta` AND `countries_summary` AND `isi_composite` are all `true`.
- Otherwise `status` is `"degraded"`.
- This endpoint never returns an error status code. It always responds `200`.

**Data origin:** Filesystem stat checks — DYNAMIC (reflects current disk state).

**Example response:**

```json
{
  "status": "ok",
  "backend_root": "/Users/user/Panargus-isi/backend/v01",
  "meta": true,
  "countries_summary": true,
  "isi_composite": true,
  "country_detail_files": 27,
  "axis_detail_files": 6
}
```

---

### 3.3 `GET /countries`

**Purpose:** Returns all 27 EU countries with per-axis scores and ISI composite — the primary summary table.

**Parameters:** None.

**Response type:** `array` of 27 objects. Not wrapped in an envelope.

**Response shape (each element):**

```jsonc
{
  "country":              string,        // ISO 3166-1 alpha-2 (Eurostat variant), e.g. "AT", "EL"
  "country_name":         string,        // English name, e.g. "Austria", "Greece"
  "axis_1_financial":     number | null,  // Axis 1 score ∈ [0, 1]
  "axis_2_energy":        number | null,  // Axis 2 score ∈ [0, 1]
  "axis_3_technology":    number | null,  // Axis 3 score ∈ [0, 1]
  "axis_4_defense":       number | null,  // Axis 4 score ∈ [0, 1]
  "axis_5_critical_inputs": number | null, // Axis 5 score ∈ [0, 1]
  "axis_6_logistics":     number | null,  // Axis 6 score ∈ [0, 1]
  "isi_composite":        number | null   // Arithmetic mean of all 6 axis scores ∈ [0, 1]
}
```

**Field semantics:**

| Field | Type | Meaning |
|-------|------|---------|
| `country` | string | Eurostat-standard 2-letter code. Greece = `"EL"` (not `"GR"`). |
| `country_name` | string | Static English name. |
| `axis_1_financial` | number ∈ [0,1] | HHI-based concentration of inward banking claims + portfolio debt. |
| `axis_2_energy` | number ∈ [0,1] | Volume-weighted concentration of gas, oil, solid fossil fuel imports. |
| `axis_3_technology` | number ∈ [0,1] | Concentration of semiconductor imports (HS 8541/8542) across suppliers. |
| `axis_4_defense` | number ∈ [0,1] | Concentration of major conventional arms imports (SIPRI TIV) across suppliers. |
| `axis_5_critical_inputs` | number ∈ [0,1] | Concentration of critical raw material imports (66 CN8 codes) across suppliers. |
| `axis_6_logistics` | number ∈ [0,1] | Concentration of international freight across transport modes and bilateral partners. |
| `isi_composite` | number ∈ [0,1] | `(A1 + A2 + A3 + A4 + A5 + A6) / 6`. `null` only if any axis is `null`. |

**Invariants:**
- Array length is always exactly `27`.
- No sort order is guaranteed on this endpoint. Frontend must sort if needed.
- All 27 EU member states present. No duplicates.
- Country codes: `AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU, IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK`.
- In v0.1, all axis scores and `isi_composite` are non-null for all 27 countries.
- Scores are rounded to 8 decimal places.

**Data origin:** `backend/v01/countries.json` — PRECOMPUTED, STATIC.

**Error:** `503` if `countries.json` is missing.

**Example response (truncated to 3 entries — actual response has 27):**

```json
[
  {
    "country": "AT",
    "country_name": "Austria",
    "axis_1_financial": 0.14900000,
    "axis_2_energy": 0.45580000,
    "axis_3_technology": 0.26060000,
    "axis_4_defense": 0.58510000,
    "axis_5_critical_inputs": 0.31860000,
    "axis_6_logistics": 0.52590000,
    "isi_composite": 0.38250000
  },
  {
    "country": "MT",
    "country_name": "Malta",
    "axis_1_financial": 0.13998786,
    "axis_2_energy": 0.35068126,
    "axis_3_technology": 0.20546991,
    "axis_4_defense": 1.00000000,
    "axis_5_critical_inputs": 0.40874987,
    "axis_6_logistics": 1.00000000,
    "isi_composite": 0.51748148
  },
  {
    "country": "FR",
    "country_name": "France",
    "axis_1_financial": 0.10039135,
    "axis_2_energy": 0.30911838,
    "axis_3_technology": 0.12001059,
    "axis_4_defense": 0.37034617,
    "axis_5_critical_inputs": 0.16122463,
    "axis_6_logistics": 0.35293643,
    "isi_composite": 0.23567126
  }
]
```

---

### 3.4 `GET /country/{code}`

**Purpose:** Returns the complete detail object for one country: ISI composite, all 6 axis scores with per-channel breakdowns, top partners, subcategory decompositions, audit data, and warnings.

**Path parameters:**

| Param | Type | Constraints | Description |
|-------|------|------------|-------------|
| `code` | string | One of 27 EU country codes (case-insensitive) | Eurostat 2-letter code |

**Response shape:**

```jsonc
{
  "country":            string,        // "AT"
  "country_name":       string,        // "Austria"
  "version":            string,        // "v0.1"
  "window":             string,        // "2022–2024"
  "isi_composite":      number | null, // ∈ [0, 1]
  "isi_classification": string | null, // "unconcentrated" | "mildly_concentrated" | "moderately_concentrated" | "highly_concentrated"
  "axes_available":     number,        // count of axes with data (target: 6)
  "axes_required":      number,        // always 6
  "axes":               AxisDetail[]   // array of 6 axis detail objects
}
```

**`AxisDetail` object:**

```jsonc
{
  "axis_id":            number,        // 1–6
  "axis_slug":          string,        // "financial" | "energy" | "technology" | "defense" | "critical_inputs" | "logistics"
  "axis_name":          string,        // human-readable name
  "score":              number | null, // ∈ [0, 1]
  "classification":     string | null, // same 4-level scale
  "driver_statement":   string,        // deterministic factual sentence
  "audit":              AuditBreakdown | undefined, // present if audit data exists
  "channels":           ChannelDetail[] | undefined, // per-channel breakdowns
  "fuel_concentrations": FuelConcentrations | undefined, // Axis 2 only
  "warnings":           Warning[]      // always present
}
```

**`AuditBreakdown` object (when present):**

```jsonc
{
  "channel_a_concentration": number,   // HHI for Channel A ∈ [0, 1]
  "channel_a_volume":        number,   // total volume (units vary by axis)
  "channel_b_concentration": number,   // HHI for Channel B ∈ [0, 1]
  "channel_b_volume":        number,   // total volume
  "score":                   number,   // final axis score = mean(Ch.A, Ch.B)
  "basis":                   string    // "BOTH" | "BOTH_CHANNELS" | "A_ONLY" | data provenance tag
}
```

**`ChannelDetail` object:**

```jsonc
{
  "channel_id":       string,          // "A" | "B" | "gas" | "oil" | "solid_fossil"
  "channel_name":     string,          // human-readable
  "source":           string,          // data source reference
  "top_partners":     PartnerShare[] | undefined,  // up to 10 entries, sorted by share desc
  "total_partners":   number | undefined,          // total partner count before truncation
  "subcategories":    Subcategory[] | undefined     // capability blocks / HS categories / modes
}
```

**`PartnerShare` object:**

```jsonc
{
  "partner": string,   // country code or entity code (e.g. "DE", "CN", "US", "NSP")
  "share":   number    // ∈ [0, 1], sum across all partners ≈ 1.0
}
```

**`Subcategory` object:**

```jsonc
{
  "category":      string, // subcategory name (e.g. "integrated_circuits", "combat_aircraft", "road")
  "concentration": number, // HHI for this subcategory ∈ [0, 1]
  "volume":        number | undefined // value/volume in axis-specific units
}
```

**`FuelConcentrations` object (Axis 2 only):**

```jsonc
{
  "gas":          number,  // HHI for gas imports ∈ [0, 1]
  "oil":          number,  // HHI for oil imports ∈ [0, 1]
  "solid_fossil": number   // HHI for solid fossil fuel imports ∈ [0, 1]
}
```

**`Warning` object:**

```jsonc
{
  "id":       string,  // e.g. "L-1", "W-2"
  "severity": string,  // "HIGH" | "MEDIUM" | "LOW"
  "text":     string   // factual limitation statement
}
```

**Classification thresholds (server-computed, never recompute on frontend):**

| Score range | Classification |
|------------|---------------|
| `[0.00, 0.15)` | `"unconcentrated"` |
| `[0.15, 0.25)` | `"mildly_concentrated"` |
| `[0.25, 0.50)` | `"moderately_concentrated"` |
| `[0.50, 1.00]` | `"highly_concentrated"` |

**Invariants:**
- `axes` array always has exactly 6 elements, sorted by `axis_id` ascending (1–6).
- `top_partners` is sorted by `share` descending. Max 10 entries.
- `warnings` is always present and non-empty for every axis.
- `isi_composite` is `null` only if any axis `score` is `null` (does not occur in v0.1).
- `axes_available` = 6 and `axes_required` = 6 in v0.1.
- `fuel_concentrations` key exists ONLY on the axis where `axis_id` = 2.
- `audit` key is absent (not `null`) when no audit data exists for that axis.
- `channels` key is absent (not `null`) when no channel detail exists.

**Errors:**
- `404` if `code` is not in EU-27.
- `503` if country JSON file is not materialized.

**Data origin:** `backend/v01/country/{CODE}.json` — PRECOMPUTED, STATIC.

**Example response (Austria, abbreviated — real response is larger):**

```json
{
  "country": "AT",
  "country_name": "Austria",
  "version": "v0.1",
  "window": "2022–2024",
  "isi_composite": 0.38250000,
  "isi_classification": "moderately_concentrated",
  "axes_available": 6,
  "axes_required": 6,
  "axes": [
    {
      "axis_id": 1,
      "axis_slug": "financial",
      "axis_name": "Financial Sovereignty",
      "score": 0.14900000,
      "classification": "mildly_concentrated",
      "driver_statement": "Austria scores 0.1490 on financial sovereignty (mildly concentrated). This reflects the concentration of inward banking claims and portfolio debt holdings across foreign creditor countries.",
      "audit": {
        "channel_a_concentration": 0.2369,
        "channel_a_volume": 173403.293,
        "channel_b_concentration": 0.0713,
        "channel_b_volume": 195822.261,
        "score": 0.149,
        "basis": "BOTH"
      },
      "channels": [
        {
          "channel_id": "A",
          "channel_name": "Banking Claims Concentration",
          "source": "BIS Locational Banking Statistics (LBS)",
          "top_partners": [
            {"partner": "DE", "share": 0.43604132},
            {"partner": "IT", "share": 0.17105752},
            {"partner": "FR", "share": 0.08272623},
            {"partner": "NL", "share": 0.05293551},
            {"partner": "JP", "share": 0.05205248}
          ],
          "total_partners": 30
        },
        {
          "channel_id": "B",
          "channel_name": "Portfolio Debt Concentration",
          "source": "IMF CPIS",
          "top_partners": [
            {"partner": "DE", "share": 0.22518400},
            {"partner": "FR", "share": 0.10940000},
            {"partner": "IT", "share": 0.08120000}
          ],
          "total_partners": 25
        }
      ],
      "warnings": [
        {"id": "L-1", "severity": "MEDIUM", "text": "BIS creditor coverage gap: non-BIS-reporting countries absent as creditors; concentration may be biased upward."},
        {"id": "L-2", "severity": "MEDIUM", "text": "IMF CPIS participation is voluntary; China does not participate. Portfolio debt concentration may understate true exposure."},
        {"id": "L-3", "severity": "LOW", "text": "Partial overlap between Channel A (bank claims) and Channel B (portfolio debt securities held by banks)."},
        {"id": "L-4", "severity": "LOW", "text": "Croatia (HR) absent from Channel B (IMF CPIS). Score reduces to Channel A only."}
      ]
    },
    {
      "axis_id": 2,
      "axis_slug": "energy",
      "axis_name": "Energy Dependency",
      "score": 0.45580000,
      "classification": "moderately_concentrated",
      "driver_statement": "Austria scores 0.4558 on energy dependency (moderately concentrated). This reflects the concentration of fossil fuel imports (gas, oil, solid fossil fuels) across supplier countries.",
      "fuel_concentrations": {
        "gas": 0.5000,
        "oil": 0.2800,
        "solid_fossil": 0.3500
      },
      "channels": [
        {
          "channel_id": "gas",
          "channel_name": "Natural Gas Import Concentration",
          "source": "Eurostat nrg_ti_gas",
          "top_partners": [
            {"partner": "RU", "share": 0.50000000}
          ],
          "total_partners": 5
        }
      ],
      "warnings": [
        {"id": "L-1", "severity": "MEDIUM", "text": "Pipeline gas and LNG not separated. A country importing 50% pipeline gas from Russia and 50% LNG from multiple sources scores as if partially diversified."},
        {"id": "L-2", "severity": "MEDIUM", "text": "Re-exports and transit flows may distort bilateral attribution across all fuel types."},
        {"id": "L-3", "severity": "LOW", "text": "No price or contract-duration effects captured. Volume-based concentration only."}
      ]
    },
    {
      "axis_id": 3,
      "axis_slug": "technology",
      "axis_name": "Technology / Semiconductor Dependency",
      "score": 0.26060000,
      "classification": "moderately_concentrated",
      "driver_statement": "Austria scores 0.2606 on technology/semiconductor dependency (moderately concentrated). This reflects the concentration of semiconductor imports across supplier countries.",
      "audit": {
        "channel_a_concentration": 0.2456,
        "channel_a_volume": 4760052556.0,
        "channel_b_concentration": 0.2756,
        "channel_b_volume": 4760052556.0,
        "score": 0.2606,
        "basis": "BOTH_CHANNELS"
      },
      "channels": [
        {
          "channel_id": "B",
          "channel_name": "Category-Weighted Supplier Concentration",
          "source": "Eurostat Comext ds-045409",
          "subcategories": [
            {"category": "legacy_discrete", "concentration": 0.5470, "volume": 1176733740.0},
            {"category": "legacy_components", "concentration": 0.2599, "volume": 151125259.0},
            {"category": "integrated_circuits", "concentration": 0.1832, "volume": 3432193557.0}
          ]
        }
      ],
      "warnings": [
        {"id": "W-2", "severity": "MEDIUM", "text": "Re-export blindness: bilateral trade records shipping country, not country of origin."},
        {"id": "W-3", "severity": "LOW", "text": "Trade concentration does not capture domestic fabrication capacity."},
        {"id": "W-4", "severity": "LOW", "text": "HS 8542 at HS4 aggregate: integrated circuits not decomposed into subcategories."},
        {"id": "W-5", "severity": "LOW", "text": "Intra-EU trade included: EU partners appear as suppliers (by design)."},
        {"id": "W-6", "severity": "LOW", "text": "Three-year window (2022–2024) may include pandemic-era distortions."}
      ]
    },
    {
      "axis_id": 4,
      "axis_slug": "defense",
      "axis_name": "Defense Industrial Dependency",
      "score": 0.58510000,
      "classification": "highly_concentrated",
      "driver_statement": "Austria scores 0.5851 on defense industrial dependency (highly concentrated). This reflects the concentration of major conventional arms imports across supplier countries.",
      "audit": {
        "channel_a_concentration": 0.4968,
        "channel_a_volume": 101.16,
        "channel_b_concentration": 0.6734,
        "channel_b_volume": 101.16,
        "score": 0.5851,
        "basis": "BOTH_CHANNELS"
      },
      "warnings": [
        {"id": "L-1", "severity": "MEDIUM", "text": "SIPRI TIV is a volume indicator, not a financial value. Comparability across weapon types is approximate."},
        {"id": "L-2", "severity": "MEDIUM", "text": "SIPRI covers major conventional weapons only. Small arms, ammunition, MRO, and sustainment contracts are excluded."},
        {"id": "L-3", "severity": "LOW", "text": "Six-year delivery window (2019–2024) may include legacy contracts not reflecting current strategic posture."},
        {"id": "L-4", "severity": "LOW", "text": "Regex-based weapon classification may cause edge-case misclassification across capability blocks."}
      ]
    },
    {
      "axis_id": 5,
      "axis_slug": "critical_inputs",
      "axis_name": "Critical Inputs / Raw Materials Dependency",
      "score": 0.31860000,
      "classification": "moderately_concentrated",
      "driver_statement": "Austria scores 0.3186 on critical inputs dependency (moderately concentrated). This reflects the concentration of critical raw material imports across supplier countries.",
      "audit": {
        "channel_a_concentration": 0.2282,
        "channel_a_volume": 1276461154.0,
        "channel_b_concentration": 0.4089,
        "channel_b_volume": 1276461154.0,
        "score": 0.3186,
        "basis": "BOTH"
      },
      "warnings": [
        {"id": "L-1", "severity": "HIGH", "text": "Re-export and entrepot masking: bilateral trade records shipping country, not origin. 13 of 27 reporters source >50% from EU partners."},
        {"id": "L-2", "severity": "MEDIUM", "text": "Small-economy amplification: CY, MT, LU produce mechanically high HHI values due to low total import volumes."},
        {"id": "L-3", "severity": "MEDIUM", "text": "CN8 scope covers upstream materials only. Midstream processing and downstream products excluded. China's role understated."},
        {"id": "L-4", "severity": "LOW", "text": "Confidential trade suppression: Q-prefix partner codes excluded. May cause underestimation for some partners."}
      ]
    },
    {
      "axis_id": 6,
      "axis_slug": "logistics",
      "axis_name": "Logistics / Freight Dependency",
      "score": 0.52590000,
      "classification": "highly_concentrated",
      "driver_statement": "Austria scores 0.5259 on logistics/freight dependency (highly concentrated). This reflects the concentration of international freight across transport modes and bilateral partners.",
      "audit": {
        "channel_a_concentration": 0.651,
        "channel_a_volume": 304333.0,
        "channel_b_concentration": 0.3943,
        "channel_b_volume": 289266.0,
        "score": 0.5259,
        "basis": "BOTH"
      },
      "channels": [
        {
          "channel_id": "A",
          "channel_name": "Transport Mode Concentration",
          "source": "Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw"
        },
        {
          "channel_id": "B",
          "channel_name": "Partner Concentration per Transport Mode",
          "source": "Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw",
          "subcategories": [
            {"category": "road", "concentration": 0.4267, "volume": 240109.0},
            {"category": "rail", "concentration": 0.2363, "volume": 49157.0}
          ]
        }
      ],
      "warnings": [
        {"id": "W-1", "severity": "HIGH", "text": "Entrepot/hub masking: NL and BE scores understate their systemic importance as continental freight hubs; countries trading through NL/BE have inflated partner concentration masking true origin."},
        {"id": "W-2", "severity": "MEDIUM", "text": "Geographic determinism: MT (Channel A HHI = 1.0), CY, and landlocked countries have structurally constrained scores reflecting geography, not policy choices."},
        {"id": "W-3", "severity": "MEDIUM", "text": "Maritime-energy overlap: maritime tonnage includes energy commodity transport, creating partial redundancy with Axis 3 (Energy)."},
        {"id": "W-4", "severity": "MEDIUM", "text": "Tonnage blindness: all freight is treated equally per tonne regardless of commodity type; strategic commodity differentiation is absent."},
        {"id": "W-5", "severity": "LOW", "text": "No route/chokepoint data: the axis cannot detect Suez, Bosporus, or any physical corridor dependency."}
      ]
    }
  ]
}
```

---

### 3.5 `GET /country/{code}/axes`

**Purpose:** Returns lightweight axis summary for one country (scores + classifications only, no channel/partner detail).

**Path parameters:**

| Param | Type | Constraints |
|-------|------|------------|
| `code` | string | One of 27 EU country codes (case-insensitive) |

**Response shape:**

```jsonc
{
  "country":       string,        // "AT"
  "country_name":  string,        // "Austria"
  "isi_composite": number | null, // ∈ [0, 1]
  "axes": [                       // always 6 elements
    {
      "axis_id":        number,        // 1–6
      "axis_slug":      string,        // slug
      "score":          number | null, // ∈ [0, 1]
      "classification": string | null  // 4-level scale
    }
  ]
}
```

**Invariants:**
- `axes` array always has exactly 6 elements.
- Sorted by `axis_id` ascending.
- This is a strict subset of `GET /country/{code}` — no channels, no partners, no audit, no warnings.

**Data origin:** Derived by slicing `backend/v01/country/{CODE}.json` at request time (no separate file). Still zero computation — just field selection.

**Errors:**
- `404` if `code` is not in EU-27.
- `503` if country JSON file is not materialized.

**Example response:**

```json
{
  "country": "MT",
  "country_name": "Malta",
  "isi_composite": 0.51748148,
  "axes": [
    {"axis_id": 1, "axis_slug": "financial", "score": 0.13998786, "classification": "unconcentrated"},
    {"axis_id": 2, "axis_slug": "energy", "score": 0.35068126, "classification": "moderately_concentrated"},
    {"axis_id": 3, "axis_slug": "technology", "score": 0.20546991, "classification": "mildly_concentrated"},
    {"axis_id": 4, "axis_slug": "defense", "score": 1.00000000, "classification": "highly_concentrated"},
    {"axis_id": 5, "axis_slug": "critical_inputs", "score": 0.40874987, "classification": "moderately_concentrated"},
    {"axis_id": 6, "axis_slug": "logistics", "score": 1.00000000, "classification": "highly_concentrated"}
  ]
}
```

---

### 3.6 `GET /country/{code}/axis/{axis_id}`

**Purpose:** Returns full detail for a single axis for a single country.

**Path parameters:**

| Param | Type | Constraints |
|-------|------|------------|
| `code` | string | One of 27 EU country codes (case-insensitive) |
| `axis_id` | integer | 1–6 |

**Response shape:**

```jsonc
{
  "country":      string,     // "AT"
  "country_name": string,     // "Austria"
  "axis":         AxisDetail  // same AxisDetail object as in GET /country/{code}
}
```

**Invariants:**
- `axis` is a single AxisDetail object (not an array).
- Contains the same channel/partner/audit/warning data as the corresponding element in `GET /country/{code}`.

**Errors:**
- `404` if `code` is not in EU-27.
- `404` if `axis_id` is not 1–6.
- `503` if country JSON file is not materialized.

**Data origin:** Derived by slicing `backend/v01/country/{CODE}.json` at request time.

**Example response:**

```json
{
  "country": "AT",
  "country_name": "Austria",
  "axis": {
    "axis_id": 4,
    "axis_slug": "defense",
    "axis_name": "Defense Industrial Dependency",
    "score": 0.58510000,
    "classification": "highly_concentrated",
    "driver_statement": "Austria scores 0.5851 on defense industrial dependency (highly concentrated). This reflects the concentration of major conventional arms imports across supplier countries.",
    "audit": {
      "channel_a_concentration": 0.4968,
      "channel_a_volume": 101.16,
      "channel_b_concentration": 0.6734,
      "channel_b_volume": 101.16,
      "score": 0.5851,
      "basis": "BOTH_CHANNELS"
    },
    "channels": [
      {
        "channel_id": "A",
        "channel_name": "Aggregate Supplier Concentration",
        "source": "SIPRI Arms Transfers Database",
        "top_partners": [
          {"partner": "DE", "share": 0.45000000},
          {"partner": "US", "share": 0.25000000},
          {"partner": "IT", "share": 0.15000000}
        ],
        "total_partners": 8
      },
      {
        "channel_id": "B",
        "channel_name": "Capability-Block Weighted Concentration",
        "source": "SIPRI Arms Transfers Database",
        "subcategories": [
          {"category": "combat_aircraft", "concentration": 0.8500, "volume": 45.0},
          {"category": "armoured_vehicles", "concentration": 0.6200, "volume": 30.0}
        ]
      }
    ],
    "warnings": [
      {"id": "L-1", "severity": "MEDIUM", "text": "SIPRI TIV is a volume indicator, not a financial value. Comparability across weapon types is approximate."},
      {"id": "L-2", "severity": "MEDIUM", "text": "SIPRI covers major conventional weapons only. Small arms, ammunition, MRO, and sustainment contracts are excluded."},
      {"id": "L-3", "severity": "LOW", "text": "Six-year delivery window (2019–2024) may include legacy contracts not reflecting current strategic posture."},
      {"id": "L-4", "severity": "LOW", "text": "Regex-based weapon classification may cause edge-case misclassification across capability blocks."}
    ]
  }
}
```

---

### 3.7 `GET /axes`

**Purpose:** Returns the axis registry — metadata for all 6 axes (no per-country scores).

**Parameters:** None.

**Response type:** `array` of 6 objects.

**Response shape (each element):**

```jsonc
{
  "id":           number,    // 1–6
  "slug":         string,    // "financial" | "energy" | "technology" | "defense" | "critical_inputs" | "logistics"
  "name":         string,    // human-readable axis name
  "description":  string,    // one-sentence description
  "unit":         string,    // measurement unit (e.g. "USD millions", "EUR", "SIPRI TIV", "THS_T (thousand tonnes)")
  "version":      string,    // "v0.1"
  "status":       string,    // always "FROZEN"
  "materialized": boolean,   // true if data exists on disk
  "channels": [              // array of channel summaries
    {
      "id":     string,      // "A" | "B" | "gas" | "oil" | "solid_fossil"
      "name":   string,      // channel description
      "source": string       // data source reference
    }
  ],
  "warnings":     Warning[]  // array of Warning objects
}
```

**Invariants:**
- Array length is always exactly `6`.
- Sorted by `id` ascending (1–6).
- `status` is always `"FROZEN"` in v0.1.
- `materialized` is `true` for all 6 axes in v0.1.
- `channels` array length varies: Axis 2 has 3 channels (gas/oil/solid_fossil), all others have 2 (A/B).

**Data origin:** `backend/v01/axes.json` — PRECOMPUTED, STATIC.

**Error:** `503` if `axes.json` is missing.

**Example response (truncated to 2 axes — actual has 6):**

```json
[
  {
    "id": 1,
    "slug": "financial",
    "name": "Financial Sovereignty",
    "description": "Concentration of inward banking claims and portfolio debt holdings across foreign creditor countries.",
    "unit": "USD millions",
    "version": "v0.1",
    "status": "FROZEN",
    "materialized": true,
    "channels": [
      {"id": "A", "name": "Banking Claims Concentration", "source": "BIS Locational Banking Statistics (LBS)"},
      {"id": "B", "name": "Portfolio Debt Concentration", "source": "IMF CPIS"}
    ],
    "warnings": [
      {"id": "L-1", "severity": "MEDIUM", "text": "BIS creditor coverage gap: non-BIS-reporting countries absent as creditors; concentration may be biased upward."},
      {"id": "L-2", "severity": "MEDIUM", "text": "IMF CPIS participation is voluntary; China does not participate. Portfolio debt concentration may understate true exposure."},
      {"id": "L-3", "severity": "LOW", "text": "Partial overlap between Channel A (bank claims) and Channel B (portfolio debt securities held by banks)."},
      {"id": "L-4", "severity": "LOW", "text": "Croatia (HR) absent from Channel B (IMF CPIS). Score reduces to Channel A only."}
    ]
  },
  {
    "id": 6,
    "slug": "logistics",
    "name": "Logistics / Freight Dependency",
    "description": "Concentration of international freight across transport modes and bilateral freight partners per mode.",
    "unit": "THS_T (thousand tonnes)",
    "version": "v0.1",
    "status": "FROZEN",
    "materialized": true,
    "channels": [
      {"id": "A", "name": "Transport Mode Concentration", "source": "Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw"},
      {"id": "B", "name": "Partner Concentration per Transport Mode", "source": "Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw"}
    ],
    "warnings": [
      {"id": "W-1", "severity": "HIGH", "text": "Entrepot/hub masking: NL and BE scores understate their systemic importance as continental freight hubs; countries trading through NL/BE have inflated partner concentration masking true origin."},
      {"id": "W-2", "severity": "MEDIUM", "text": "Geographic determinism: MT (Channel A HHI = 1.0), CY, and landlocked countries have structurally constrained scores reflecting geography, not policy choices."},
      {"id": "W-3", "severity": "MEDIUM", "text": "Maritime-energy overlap: maritime tonnage includes energy commodity transport, creating partial redundancy with Axis 3 (Energy)."},
      {"id": "W-4", "severity": "MEDIUM", "text": "Tonnage blindness: all freight is treated equally per tonne regardless of commodity type; strategic commodity differentiation is absent."},
      {"id": "W-5", "severity": "LOW", "text": "No route/chokepoint data: the axis cannot detect Suez, Bosporus, or any physical corridor dependency."}
    ]
  }
]
```

---

### 3.8 `GET /axis/{axis_id}`

**Purpose:** Returns full detail for one axis across all 27 countries — scores, rankings, statistics, audit breakdowns, and warnings.

**Path parameters:**

| Param | Type | Constraints |
|-------|------|------------|
| `axis_id` | integer | 1–6 |

**Response shape:**

```jsonc
{
  "axis_id":          number,    // 1–6
  "axis_slug":        string,    // slug
  "axis_name":        string,    // human-readable name
  "description":      string,    // one-sentence description
  "version":          string,    // "v0.1"
  "status":           string,    // "FROZEN"
  "materialized":     boolean,   // true
  "unit":             string,    // measurement unit
  "countries_scored": number,    // 27 in v0.1
  "statistics": {
    "min":  number | null,       // lowest score across EU-27
    "max":  number | null,       // highest score across EU-27
    "mean": number | null        // arithmetic mean across EU-27
  },
  "channels": [                  // channel metadata (same as /axes)
    { "id": string, "name": string, "source": string }
  ],
  "warnings":   Warning[],      // axis-level warnings
  "countries":  CountryAxisScore[] // 27 entries, sorted by score DESC
}
```

**`CountryAxisScore` object:**

```jsonc
{
  "country":        string,        // "MT"
  "country_name":   string,        // "Malta"
  "score":          number | null,  // ∈ [0, 1]
  "classification": string | null,  // 4-level scale
  "audit":          AuditBreakdown | undefined // present if audit data exists
}
```

**Invariants:**
- `countries` array always has exactly 27 elements.
- **Sorted by `score` descending** (most concentrated first). Nulls last.
- `statistics.min`, `statistics.max`, `statistics.mean` are computed across all non-null scores.
- `countries_scored` = 27 in v0.1.

**Errors:**
- `404` if `axis_id` is not 1–6.
- `503` if axis JSON file is not materialized.

**Data origin:** `backend/v01/axis/{axis_id}.json` — PRECOMPUTED, STATIC.

**Example response (Axis 4, truncated countries to 3):**

```json
{
  "axis_id": 4,
  "axis_slug": "defense",
  "axis_name": "Defense Industrial Dependency",
  "description": "Concentration of major conventional arms imports across supplier countries and capability blocks.",
  "version": "v0.1",
  "status": "FROZEN",
  "materialized": true,
  "unit": "SIPRI TIV",
  "countries_scored": 27,
  "statistics": {
    "min": 0.34080000,
    "max": 1.00000000,
    "mean": 0.59500000
  },
  "channels": [
    {"id": "A", "name": "Aggregate Supplier Concentration", "source": "SIPRI Arms Transfers Database"},
    {"id": "B", "name": "Capability-Block Weighted Concentration", "source": "SIPRI Arms Transfers Database"}
  ],
  "warnings": [
    {"id": "L-1", "severity": "MEDIUM", "text": "SIPRI TIV is a volume indicator, not a financial value. Comparability across weapon types is approximate."},
    {"id": "L-2", "severity": "MEDIUM", "text": "SIPRI covers major conventional weapons only. Small arms, ammunition, MRO, and sustainment contracts are excluded."},
    {"id": "L-3", "severity": "LOW", "text": "Six-year delivery window (2019–2024) may include legacy contracts not reflecting current strategic posture."},
    {"id": "L-4", "severity": "LOW", "text": "Regex-based weapon classification may cause edge-case misclassification across capability blocks."}
  ],
  "countries": [
    {
      "country": "MT",
      "country_name": "Malta",
      "score": 1.00000000,
      "classification": "highly_concentrated",
      "audit": {
        "channel_a_concentration": 1.0,
        "channel_a_volume": 5.0,
        "channel_b_concentration": 1.0,
        "channel_b_volume": 5.0,
        "score": 1.0,
        "basis": "BOTH_CHANNELS"
      }
    },
    {
      "country": "NL",
      "country_name": "Netherlands",
      "score": 0.95960000,
      "classification": "highly_concentrated"
    },
    {
      "country": "LV",
      "country_name": "Latvia",
      "score": 0.34080000,
      "classification": "moderately_concentrated"
    }
  ]
}
```

---

### 3.9 `GET /isi`

**Purpose:** Returns ISI composite scores for all 27 countries with per-axis breakdowns, aggregation metadata, and EU-27 statistics.

**Parameters:** None.

**Response shape:**

```jsonc
{
  "version":            string,   // "v0.1"
  "window":             string,   // "2022–2024"
  "aggregation_rule":   string,   // "unweighted_arithmetic_mean"
  "formula":            string,   // "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6"
  "countries_complete": number,   // count of countries with all 6 axes scored (27 in v0.1)
  "countries_total":    number,   // 27
  "statistics": {
    "min":  number | null,        // lowest ISI composite
    "max":  number | null,        // highest ISI composite
    "mean": number | null         // mean ISI composite
  },
  "countries": ISICountryRow[]    // 27 entries, sorted by isi_composite DESC
}
```

**`ISICountryRow` object:**

```jsonc
{
  "country":              string,        // "MT"
  "country_name":         string,        // "Malta"
  "axis_1_financial":     number | null, // ∈ [0, 1]
  "axis_2_energy":        number | null, // ∈ [0, 1]
  "axis_3_technology":    number | null, // ∈ [0, 1]
  "axis_4_defense":       number | null, // ∈ [0, 1]
  "axis_5_critical_inputs": number | null, // ∈ [0, 1]
  "axis_6_logistics":     number | null, // ∈ [0, 1]
  "isi_composite":        number | null, // ∈ [0, 1]
  "classification":       string | null, // 4-level scale
  "complete":             boolean        // true if all 6 axes are non-null
}
```

**Invariants:**
- `countries` array always has exactly 27 elements.
- **Sorted by `isi_composite` descending** (most dependent first). Nulls last.
- `countries_complete` = `countries_total` = 27 in v0.1.
- All `complete` values are `true` in v0.1.
- `statistics` computed from non-null `isi_composite` values.
- The `axis_2_energy` field name (not `axis_2_trade`) reflects the canonical axis slug.

**Data origin:** `backend/v01/isi.json` — PRECOMPUTED, STATIC.

**Error:** `503` if `isi.json` is missing.

**Example response (truncated to 3 countries — actual has 27):**

```json
{
  "version": "v0.1",
  "window": "2022–2024",
  "aggregation_rule": "unweighted_arithmetic_mean",
  "formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
  "countries_complete": 27,
  "countries_total": 27,
  "statistics": {
    "min": 0.23567126,
    "max": 0.51748148,
    "mean": 0.34806600
  },
  "countries": [
    {
      "country": "MT",
      "country_name": "Malta",
      "axis_1_financial": 0.13998786,
      "axis_2_energy": 0.35068126,
      "axis_3_technology": 0.20546991,
      "axis_4_defense": 1.00000000,
      "axis_5_critical_inputs": 0.40874987,
      "axis_6_logistics": 1.00000000,
      "isi_composite": 0.51748148,
      "classification": "highly_concentrated",
      "complete": true
    },
    {
      "country": "CY",
      "country_name": "Cyprus",
      "axis_1_financial": 0.12407171,
      "axis_2_energy": 0.34768252,
      "axis_3_technology": 0.22438354,
      "axis_4_defense": 0.74847998,
      "axis_5_critical_inputs": 0.42359750,
      "axis_6_logistics": 0.94106062,
      "isi_composite": 0.46821264,
      "classification": "moderately_concentrated",
      "complete": true
    },
    {
      "country": "FR",
      "country_name": "France",
      "axis_1_financial": 0.10039135,
      "axis_2_energy": 0.30911838,
      "axis_3_technology": 0.12001059,
      "axis_4_defense": 0.37034617,
      "axis_5_critical_inputs": 0.16122463,
      "axis_6_logistics": 0.35293643,
      "isi_composite": 0.23567126,
      "classification": "mildly_concentrated",
      "complete": true
    }
  ]
}
```

---

## 4. Error Responses

All error responses follow FastAPI's default `HTTPException` format:

```jsonc
{
  "detail": string  // human-readable error message
}
```

| Status | Condition |
|--------|-----------|
| `404` | Country code not in EU-27, or axis_id not in 1–6 |
| `503` | Backend JSON artifact not materialized (exporter not run) |

There are no `400`, `401`, `403`, or `500` errors in normal operation.

---

## 5. Country Code Reference

The API uses Eurostat-standard ISO 3166-1 alpha-2 codes. **Greece is `EL`, not `GR`.**

```
AT  Austria          EE  Estonia          IE  Ireland          MT  Malta            RO  Romania
BE  Belgium          EL  Greece           IT  Italy            NL  Netherlands      SE  Sweden
BG  Bulgaria         ES  Spain            LT  Lithuania        PL  Poland           SI  Slovenia
CY  Cyprus           FI  Finland          LU  Luxembourg       PT  Portugal         SK  Slovakia
CZ  Czechia          FR  France           LV  Latvia           
DE  Germany          HR  Croatia          
DK  Denmark          HU  Hungary          
```

Country codes in path parameters are **case-insensitive** — `at`, `AT`, and `At` all resolve to Austria.

---

## 6. Axis Reference

| ID | Slug | Name | Unit | Channels | Source |
|----|------|------|------|----------|--------|
| 1 | `financial` | Financial Sovereignty | USD millions | A: Banking Claims, B: Portfolio Debt | BIS LBS, IMF CPIS |
| 2 | `energy` | Energy Dependency | MIO_M3 / THS_T | gas, oil, solid_fossil | Eurostat nrg_ti_* |
| 3 | `technology` | Technology / Semiconductor Dependency | EUR | A: Aggregate Supplier, B: Category-Weighted | Eurostat Comext |
| 4 | `defense` | Defense Industrial Dependency | SIPRI TIV | A: Aggregate Supplier, B: Capability-Block | SIPRI |
| 5 | `critical_inputs` | Critical Inputs / Raw Materials Dependency | EUR | A: Aggregate Supplier, B: Material-Group | Eurostat Comext CN8 |
| 6 | `logistics` | Logistics / Freight Dependency | THS_T | A: Transport Mode, B: Partner per Mode | Eurostat freight |

---

## 7. OpenAPI 3.0.3 Specification

```json
{
  "openapi": "3.0.3",
  "info": {
    "title": "ISI API",
    "description": "International Sovereignty Index — Read-Only API v0.1",
    "version": "0.1.0"
  },
  "servers": [
    {
      "url": "http://localhost:8000",
      "description": "Local development"
    }
  ],
  "paths": {
    "/": {
      "get": {
        "operationId": "root",
        "summary": "API metadata",
        "responses": {
          "200": {
            "description": "ISI project metadata",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/Meta" }
              }
            }
          },
          "503": {
            "description": "Backend data not materialized",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/health": {
      "get": {
        "operationId": "health",
        "summary": "Health check",
        "responses": {
          "200": {
            "description": "Backend data availability",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/HealthCheck" }
              }
            }
          }
        }
      }
    },
    "/countries": {
      "get": {
        "operationId": "list_countries",
        "summary": "All EU-27 countries with summary scores",
        "responses": {
          "200": {
            "description": "Array of 27 country summaries",
            "content": {
              "application/json": {
                "schema": {
                  "type": "array",
                  "items": { "$ref": "#/components/schemas/CountrySummary" },
                  "minItems": 27,
                  "maxItems": 27
                }
              }
            }
          },
          "503": {
            "description": "countries.json not found",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/country/{code}": {
      "get": {
        "operationId": "get_country",
        "summary": "Full country detail with all axes, channels, partners, warnings",
        "parameters": [
          {
            "name": "code",
            "in": "path",
            "required": true,
            "schema": { "type": "string", "pattern": "^[A-Za-z]{2}$" },
            "description": "EU-27 country code (case-insensitive)"
          }
        ],
        "responses": {
          "200": {
            "description": "Full country detail",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/CountryDetail" }
              }
            }
          },
          "404": {
            "description": "Country not in EU-27",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          },
          "503": {
            "description": "Country file not materialized",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/country/{code}/axes": {
      "get": {
        "operationId": "get_country_axes",
        "summary": "All axis scores for one country (lightweight)",
        "parameters": [
          {
            "name": "code",
            "in": "path",
            "required": true,
            "schema": { "type": "string", "pattern": "^[A-Za-z]{2}$" },
            "description": "EU-27 country code (case-insensitive)"
          }
        ],
        "responses": {
          "200": {
            "description": "Country axis summary",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/CountryAxesSummary" }
              }
            }
          },
          "404": {
            "description": "Country not in EU-27",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          },
          "503": {
            "description": "Country file not materialized",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/country/{code}/axis/{axis_id}": {
      "get": {
        "operationId": "get_country_axis",
        "summary": "Single axis detail for one country",
        "parameters": [
          {
            "name": "code",
            "in": "path",
            "required": true,
            "schema": { "type": "string", "pattern": "^[A-Za-z]{2}$" },
            "description": "EU-27 country code (case-insensitive)"
          },
          {
            "name": "axis_id",
            "in": "path",
            "required": true,
            "schema": { "type": "integer", "minimum": 1, "maximum": 6 },
            "description": "Axis number (1–6)"
          }
        ],
        "responses": {
          "200": {
            "description": "Single axis detail for country",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/CountryAxisResponse" }
              }
            }
          },
          "404": {
            "description": "Country not in EU-27 or axis_id not in 1–6",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          },
          "503": {
            "description": "Country file not materialized",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/axes": {
      "get": {
        "operationId": "list_axes",
        "summary": "Axis registry with metadata, channels, warnings",
        "responses": {
          "200": {
            "description": "Array of 6 axis registry entries",
            "content": {
              "application/json": {
                "schema": {
                  "type": "array",
                  "items": { "$ref": "#/components/schemas/AxisRegistryEntry" },
                  "minItems": 6,
                  "maxItems": 6
                }
              }
            }
          },
          "503": {
            "description": "axes.json not found",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/axis/{axis_id}": {
      "get": {
        "operationId": "get_axis",
        "summary": "Full axis detail across all 27 countries",
        "parameters": [
          {
            "name": "axis_id",
            "in": "path",
            "required": true,
            "schema": { "type": "integer", "minimum": 1, "maximum": 6 },
            "description": "Axis number (1–6)"
          }
        ],
        "responses": {
          "200": {
            "description": "Full axis detail with all country scores",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/AxisDetail" }
              }
            }
          },
          "404": {
            "description": "axis_id not in 1–6",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          },
          "503": {
            "description": "Axis detail not materialized",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    },
    "/isi": {
      "get": {
        "operationId": "get_isi",
        "summary": "Composite ISI scores for all countries",
        "responses": {
          "200": {
            "description": "ISI composite with per-country breakdowns",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ISIComposite" }
              }
            }
          },
          "503": {
            "description": "isi.json not found",
            "content": {
              "application/json": {
                "schema": { "$ref": "#/components/schemas/ErrorDetail" }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "ErrorDetail": {
        "type": "object",
        "required": ["detail"],
        "properties": {
          "detail": { "type": "string" }
        }
      },
      "Meta": {
        "type": "object",
        "required": ["project", "version", "reference_window", "scope", "num_axes", "num_countries", "aggregation_rule", "aggregation_formula", "score_range", "interpretation", "generated_by"],
        "properties": {
          "project": { "type": "string" },
          "version": { "type": "string" },
          "reference_window": { "type": "string" },
          "scope": { "type": "string" },
          "num_axes": { "type": "integer", "enum": [6] },
          "num_countries": { "type": "integer", "enum": [27] },
          "aggregation_rule": { "type": "string", "enum": ["unweighted_arithmetic_mean"] },
          "aggregation_formula": { "type": "string" },
          "score_range": {
            "type": "array",
            "items": { "type": "number" },
            "minItems": 2,
            "maxItems": 2
          },
          "interpretation": { "type": "string" },
          "generated_by": { "type": "string" }
        }
      },
      "HealthCheck": {
        "type": "object",
        "required": ["status", "backend_root", "meta", "countries_summary", "isi_composite", "country_detail_files", "axis_detail_files"],
        "properties": {
          "status": { "type": "string", "enum": ["ok", "degraded"] },
          "backend_root": { "type": "string" },
          "meta": { "type": "boolean" },
          "countries_summary": { "type": "boolean" },
          "isi_composite": { "type": "boolean" },
          "country_detail_files": { "type": "integer", "minimum": 0, "maximum": 27 },
          "axis_detail_files": { "type": "integer", "minimum": 0, "maximum": 6 }
        }
      },
      "CountrySummary": {
        "type": "object",
        "required": ["country", "country_name"],
        "properties": {
          "country": { "type": "string", "pattern": "^[A-Z]{2}$" },
          "country_name": { "type": "string" },
          "axis_1_financial": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_2_energy": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_3_technology": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_4_defense": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_5_critical_inputs": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_6_logistics": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "isi_composite": { "type": ["number", "null"], "minimum": 0, "maximum": 1 }
        }
      },
      "Warning": {
        "type": "object",
        "required": ["id", "severity", "text"],
        "properties": {
          "id": { "type": "string" },
          "severity": { "type": "string", "enum": ["HIGH", "MEDIUM", "LOW"] },
          "text": { "type": "string" }
        }
      },
      "PartnerShare": {
        "type": "object",
        "required": ["partner", "share"],
        "properties": {
          "partner": { "type": "string" },
          "share": { "type": "number", "minimum": 0, "maximum": 1 }
        }
      },
      "Subcategory": {
        "type": "object",
        "required": ["category", "concentration"],
        "properties": {
          "category": { "type": "string" },
          "concentration": { "type": "number", "minimum": 0, "maximum": 1 },
          "volume": { "type": "number" }
        }
      },
      "ChannelDetail": {
        "type": "object",
        "required": ["channel_id", "channel_name", "source"],
        "properties": {
          "channel_id": { "type": "string" },
          "channel_name": { "type": "string" },
          "source": { "type": "string" },
          "top_partners": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/PartnerShare" },
            "maxItems": 10
          },
          "total_partners": { "type": "integer", "minimum": 0 },
          "subcategories": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/Subcategory" }
          }
        }
      },
      "AuditBreakdown": {
        "type": "object",
        "required": ["channel_a_concentration", "channel_a_volume", "channel_b_concentration", "channel_b_volume", "score", "basis"],
        "properties": {
          "channel_a_concentration": { "type": "number", "minimum": 0, "maximum": 1 },
          "channel_a_volume": { "type": "number" },
          "channel_b_concentration": { "type": "number", "minimum": 0, "maximum": 1 },
          "channel_b_volume": { "type": "number" },
          "score": { "type": "number", "minimum": 0, "maximum": 1 },
          "basis": { "type": "string" }
        }
      },
      "FuelConcentrations": {
        "type": "object",
        "required": ["gas", "oil", "solid_fossil"],
        "properties": {
          "gas": { "type": "number", "minimum": 0, "maximum": 1 },
          "oil": { "type": "number", "minimum": 0, "maximum": 1 },
          "solid_fossil": { "type": "number", "minimum": 0, "maximum": 1 }
        }
      },
      "AxisDetailEntry": {
        "type": "object",
        "required": ["axis_id", "axis_slug", "axis_name", "warnings"],
        "properties": {
          "axis_id": { "type": "integer", "minimum": 1, "maximum": 6 },
          "axis_slug": { "type": "string", "enum": ["financial", "energy", "technology", "defense", "critical_inputs", "logistics"] },
          "axis_name": { "type": "string" },
          "score": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "classification": { "type": ["string", "null"], "enum": ["unconcentrated", "mildly_concentrated", "moderately_concentrated", "highly_concentrated", null] },
          "driver_statement": { "type": "string" },
          "audit": { "$ref": "#/components/schemas/AuditBreakdown" },
          "channels": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/ChannelDetail" }
          },
          "fuel_concentrations": { "$ref": "#/components/schemas/FuelConcentrations" },
          "warnings": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/Warning" }
          }
        }
      },
      "CountryDetail": {
        "type": "object",
        "required": ["country", "country_name", "version", "window", "isi_composite", "isi_classification", "axes_available", "axes_required", "axes"],
        "properties": {
          "country": { "type": "string", "pattern": "^[A-Z]{2}$" },
          "country_name": { "type": "string" },
          "version": { "type": "string" },
          "window": { "type": "string" },
          "isi_composite": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "isi_classification": { "type": ["string", "null"], "enum": ["unconcentrated", "mildly_concentrated", "moderately_concentrated", "highly_concentrated", null] },
          "axes_available": { "type": "integer", "minimum": 0, "maximum": 6 },
          "axes_required": { "type": "integer", "enum": [6] },
          "axes": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/AxisDetailEntry" },
            "minItems": 6,
            "maxItems": 6
          }
        }
      },
      "CountryAxesSummary": {
        "type": "object",
        "required": ["country", "country_name", "isi_composite", "axes"],
        "properties": {
          "country": { "type": "string", "pattern": "^[A-Z]{2}$" },
          "country_name": { "type": "string" },
          "isi_composite": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axes": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["axis_id", "axis_slug", "score", "classification"],
              "properties": {
                "axis_id": { "type": "integer", "minimum": 1, "maximum": 6 },
                "axis_slug": { "type": "string" },
                "score": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
                "classification": { "type": ["string", "null"] }
              }
            },
            "minItems": 6,
            "maxItems": 6
          }
        }
      },
      "CountryAxisResponse": {
        "type": "object",
        "required": ["country", "country_name", "axis"],
        "properties": {
          "country": { "type": "string", "pattern": "^[A-Z]{2}$" },
          "country_name": { "type": "string" },
          "axis": { "$ref": "#/components/schemas/AxisDetailEntry" }
        }
      },
      "AxisRegistryEntry": {
        "type": "object",
        "required": ["id", "slug", "name", "description", "unit", "version", "status", "materialized", "channels", "warnings"],
        "properties": {
          "id": { "type": "integer", "minimum": 1, "maximum": 6 },
          "slug": { "type": "string", "enum": ["financial", "energy", "technology", "defense", "critical_inputs", "logistics"] },
          "name": { "type": "string" },
          "description": { "type": "string" },
          "unit": { "type": "string" },
          "version": { "type": "string" },
          "status": { "type": "string", "enum": ["FROZEN"] },
          "materialized": { "type": "boolean" },
          "channels": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "name", "source"],
              "properties": {
                "id": { "type": "string" },
                "name": { "type": "string" },
                "source": { "type": "string" }
              }
            }
          },
          "warnings": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/Warning" }
          }
        }
      },
      "CountryAxisScore": {
        "type": "object",
        "required": ["country", "country_name"],
        "properties": {
          "country": { "type": "string", "pattern": "^[A-Z]{2}$" },
          "country_name": { "type": "string" },
          "score": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "classification": { "type": ["string", "null"] },
          "audit": { "$ref": "#/components/schemas/AuditBreakdown" }
        }
      },
      "AxisDetail": {
        "type": "object",
        "required": ["axis_id", "axis_slug", "axis_name", "description", "version", "status", "materialized", "unit", "countries_scored", "statistics", "channels", "warnings", "countries"],
        "properties": {
          "axis_id": { "type": "integer", "minimum": 1, "maximum": 6 },
          "axis_slug": { "type": "string" },
          "axis_name": { "type": "string" },
          "description": { "type": "string" },
          "version": { "type": "string" },
          "status": { "type": "string", "enum": ["FROZEN"] },
          "materialized": { "type": "boolean" },
          "unit": { "type": "string" },
          "countries_scored": { "type": "integer", "minimum": 0, "maximum": 27 },
          "statistics": {
            "type": "object",
            "properties": {
              "min": { "type": ["number", "null"] },
              "max": { "type": ["number", "null"] },
              "mean": { "type": ["number", "null"] }
            }
          },
          "channels": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["id", "name", "source"],
              "properties": {
                "id": { "type": "string" },
                "name": { "type": "string" },
                "source": { "type": "string" }
              }
            }
          },
          "warnings": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/Warning" }
          },
          "countries": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/CountryAxisScore" },
            "minItems": 27,
            "maxItems": 27
          }
        }
      },
      "ISICountryRow": {
        "type": "object",
        "required": ["country", "country_name", "complete"],
        "properties": {
          "country": { "type": "string", "pattern": "^[A-Z]{2}$" },
          "country_name": { "type": "string" },
          "axis_1_financial": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_2_energy": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_3_technology": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_4_defense": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_5_critical_inputs": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "axis_6_logistics": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "isi_composite": { "type": ["number", "null"], "minimum": 0, "maximum": 1 },
          "classification": { "type": ["string", "null"], "enum": ["unconcentrated", "mildly_concentrated", "moderately_concentrated", "highly_concentrated", null] },
          "complete": { "type": "boolean" }
        }
      },
      "ISIComposite": {
        "type": "object",
        "required": ["version", "window", "aggregation_rule", "formula", "countries_complete", "countries_total", "statistics", "countries"],
        "properties": {
          "version": { "type": "string" },
          "window": { "type": "string" },
          "aggregation_rule": { "type": "string", "enum": ["unweighted_arithmetic_mean"] },
          "formula": { "type": "string" },
          "countries_complete": { "type": "integer", "minimum": 0, "maximum": 27 },
          "countries_total": { "type": "integer", "enum": [27] },
          "statistics": {
            "type": "object",
            "properties": {
              "min": { "type": ["number", "null"] },
              "max": { "type": ["number", "null"] },
              "mean": { "type": ["number", "null"] }
            }
          },
          "countries": {
            "type": "array",
            "items": { "$ref": "#/components/schemas/ISICountryRow" },
            "minItems": 27,
            "maxItems": 27
          }
        }
      }
    }
  }
}
```

---

## 8. Global Invariants

1. **Completeness:** Every response that contains country data covers exactly 27 countries. No exceptions.
2. **Score bounds:** All scores ∈ [0.0, 1.0]. Enforced at export time; the API server does not validate.
3. **Determinism:** Identical requests return identical responses. No randomness, no time-dependence.
4. **Immutability:** Data changes only when `export_isi_backend_v01.py` is re-run. Between exports, all responses are byte-identical.
5. **No pagination:** No endpoint is paginated. All data is returned in a single response.
6. **No query parameters:** No endpoint accepts query parameters. All filtering is by path.
7. **No write operations:** The API is strictly read-only. No POST, PUT, PATCH, DELETE.
8. **No authentication:** All endpoints are public.
9. **Precision:** Scores are rounded to 8 decimal places.
10. **Sort guarantee:** `/isi` countries sorted by `isi_composite` DESC. `/axis/{n}` countries sorted by `score` DESC. All other endpoints: no sort guarantee.

---

## 9. Naming Convention: Axis 2

**Important discrepancy:** The aggregator CSV uses column name `axis_2_trade` while the exporter uses `axis_2_energy`. Both refer to the same axis (Energy Dependency). The API contract uses `axis_2_energy` which matches the axis slug. The `countries.json` summary and `isi.json` both use `axis_2_energy` as the field name.

---

## 10. Files Backing Each Endpoint

| Endpoint | JSON artifact | Generated by |
|----------|--------------|-------------|
| `GET /` | `backend/v01/meta.json` | `build_meta()` |
| `GET /health` | None (filesystem stat) | inline |
| `GET /countries` | `backend/v01/countries.json` | inline in `main()` |
| `GET /country/{code}` | `backend/v01/country/{CODE}.json` | `build_country_detail()` |
| `GET /country/{code}/axes` | `backend/v01/country/{CODE}.json` (sliced) | `build_country_detail()` |
| `GET /country/{code}/axis/{n}` | `backend/v01/country/{CODE}.json` (sliced) | `build_country_detail()` |
| `GET /axes` | `backend/v01/axes.json` | `build_axes_registry()` |
| `GET /axis/{n}` | `backend/v01/axis/{n}.json` | `build_axis_detail()` |
| `GET /isi` | `backend/v01/isi.json` | `build_isi_composite()` |

**Total artifacts:** 1 (`meta`) + 1 (`axes`) + 1 (`countries`) + 1 (`isi`) + 27 (`country/`) + 6 (`axis/`) = **36 JSON files**.
