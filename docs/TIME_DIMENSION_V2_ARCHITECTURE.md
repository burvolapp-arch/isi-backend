# ISI Time Dimension Integration — v2 Architecture Specification

**Document class:** Technical Design Document — Backend Architecture  
**Author:** Systems Architecture (automated)  
**Date:** 2026-02-21  
**Status:** DRAFT — Pre-implementation discovery  
**Scope:** Backend only. No frontend. No cosmetic changes.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Phase 1 — Data Model Audit](#2-phase-1--data-model-audit)
3. [Phase 2 — Methodology Versioning](#3-phase-2--methodology-versioning)
4. [Phase 3 — Time Series Requirements](#4-phase-3--time-series-requirements)
5. [Phase 4 — Scenario Engine Compatibility](#5-phase-4--scenario-engine-compatibility)
6. [Phase 5 — Storage Strategy](#6-phase-5--storage-strategy)
7. [Phase 6 — Structural Trend Logic](#7-phase-6--structural-trend-logic)
8. [Phase 7 — Migration Plan](#8-phase-7--migration-plan)
9. [Phase 8 — Output Requirements](#9-phase-8--output-requirements)

---

## 1. Executive Summary

The ISI backend currently operates as a **static cross-sectional model**:

- One data window: `2022–2024`
- One methodology version: `v0.1`
- No historical scores, no trend analysis, no year-specific baselines
- Pre-materialized JSON artifacts in `backend/v01/`
- Scenario engine references a single `isi.json` snapshot

This document specifies the architecture for upgrading to a **fully time-aware structural model** that supports multi-year historical axis scores, versioned methodology, reproducible recomputation, structural trend analysis, historical classification tracking, year-specific scenario simulation, and deterministic archival snapshots — **without breaking any existing API contract, frontend, or scenario engine**.

---

## 2. Phase 1 — Data Model Audit

### 2.1 Current Persistence Architecture

The ISI backend has **zero database** and **zero on-the-fly computation** at serving time. The entire data flow is:

```
Source CSVs (data/processed/{axis_dir}/)
    → export_isi_backend_v01.py (materializer)
        → Pre-computed JSON (backend/v01/)
            → isi_api_v01.py (read-only FastAPI server, memory cache)
```

#### 2.1.1 Axis Score Storage

Axis scores are **not stored in a database**. They exist in three locations:

| Layer | Path | Format | Role |
|-------|------|--------|------|
| Source CSV | `data/processed/{axis_dir}/{final_file}` | CSV | Authoritative computed scores from upstream pipelines |
| Materialized JSON (per-country) | `backend/v01/country/{CODE}.json` | JSON | Full detail per country with all axes, channels, partners |
| Materialized JSON (composite) | `backend/v01/isi.json` | JSON | All 27 countries × 6 axis scores + composite + rank + classification |

**Example — `isi.json` country entry:**
```json
{
  "country": "SE",
  "country_name": "Sweden",
  "axis_1_financial": 0.11646504,
  "axis_2_energy": 0.52024771,
  "axis_3_technology": 0.13093459,
  "axis_4_defense": 0.8424498,
  "axis_5_critical_inputs": 0.37908069,
  "axis_6_logistics": 0.40312409,
  "isi_composite": 0.39871532,
  "classification": "moderately_concentrated",
  "complete": true
}
```

#### 2.1.2 HHI Inputs — Persisted or Computed?

**Persisted.** HHI concentration scores are computed by upstream axis pipeline scripts (`scripts/`) and written to CSV files in `data/processed/`. The exporter (`export_isi_backend_v01.py`) performs **zero computation** — it reads pre-computed scores via `load_axis_scores(axis_num)` and reformats to JSON. Each axis pipeline script (e.g., `scripts/compute_finance.py`) reads raw data, computes HHI, and writes the final CSV.

The **intermediate HHI inputs** (bilateral trade shares, volumes, raw partner data) are also persisted as CSVs:
- Concentration files: `{axis}_channel_{a|b}_concentration.csv`
- Share files: `{axis}_channel_{a|b}_shares.csv`
- Volume files: `{axis}_channel_{a|b}_volumes.csv`

#### 2.1.3 Composite / Rank / Classification — Cached or Recomputed?

**Pre-computed at export time, then cached in memory at runtime.**

- **Composite:** Computed in `build_isi_composite()` during export as `sum(6_axes) / 6`. Written to `isi.json`.
- **Rank:** Implicit in the sorted order of `isi.json.countries[]` (descending by composite, ties alphabetical).
- **Classification:** Computed in `classify_score()` during export: `≥0.50 → highly_concentrated`, `≥0.25 → moderately_concentrated`, `≥0.15 → mildly_concentrated`, `<0.15 → unconcentrated`.
- **Runtime caching:** `_get_or_load()` in `isi_api_v01.py` loads each JSON file once into `_cache: dict[str, Any]`, serves from memory for all subsequent requests.

#### 2.1.4 EU Mean Derivation

The EU-27 mean is computed at export time in `build_isi_composite()` and stored in `isi.json`:

```json
"statistics": {
  "min": 0.23567126,
  "max": 0.51748148,
  "mean": 0.34439144
}
```

Per-axis EU means are similarly computed and stored in `backend/v01/axis/{n}.json` under `statistics.mean`.

**There is no runtime EU mean calculation.** All statistics are materialized.

#### 2.1.5 Scenario Shift Application

The scenario engine (`scenario.py`) applies shifts to the **live `isi.json` data**:

1. API handler loads `_get_or_load("isi", ...)` — same cache as GET /isi
2. Finds the target country's entry in `isi.json.countries[]`
3. For each axis: `simulated = clamp(baseline * (1 + adjustment), 0, 1)`
4. Recomputes composite, rank (among all 27), and classification

**Critical observation:** The scenario engine has **no concept of year**. It always operates on whatever single snapshot is loaded in `isi.json`.

#### 2.1.6 Complete Persistence Layer Inventory

| Artifact | Path Pattern | Count | Content |
|----------|-------------|-------|---------|
| Axis source CSVs | `data/processed/{axis_dir}/{file}.csv` | ~45 files across 6 axes | Raw/computed scores, shares, concentrations, volumes, audits |
| meta.json | `backend/v01/meta.json` | 1 | Version, window, formula metadata |
| axes.json | `backend/v01/axes.json` | 1 | AXIS_REGISTRY as JSON (6 axis definitions) |
| countries.json | `backend/v01/countries.json` | 1 | Summary list: 27 countries × 6 axis scores + composite |
| isi.json | `backend/v01/isi.json` | 1 | Composite ISI: 27 countries with all scores, sorted descending |
| Country detail | `backend/v01/country/{CODE}.json` | 27 | Full country detail: axes, channels, partners, audit, warnings |
| Axis detail | `backend/v01/axis/{n}.json` | 6 | Per-axis detail: all 27 country scores + statistics |
| MANIFEST.json | `backend/v01/MANIFEST.json` | 1 | SHA-256 integrity hashes for all above files |
| **Total** | | **~82 files** | |

### 2.2 Proposed Time-Aware Schema

#### 2.2.1 Canonical Entities

```sql
-- =============================================================
-- ENTITY: isi_snapshot
-- =============================================================
-- One row per (country, year, methodology_version).
-- This is the atomic unit of ISI data.
-- All downstream artifacts (isi.json, country detail) are projections of this table.

CREATE TABLE isi_snapshot (
    -- Primary key
    country_code        CHAR(2)         NOT NULL,   -- ISO 3166-1 alpha-2 (EU-27)
    year                SMALLINT        NOT NULL,   -- Reference year (e.g. 2022, 2023, 2024)
    methodology_version VARCHAR(16)     NOT NULL,   -- e.g. "v1.0", "v2.0"

    -- Axis scores (all HHI-based, [0.0, 1.0])
    axis_1_financial    DOUBLE PRECISION NOT NULL,
    axis_2_energy       DOUBLE PRECISION NOT NULL,
    axis_3_technology   DOUBLE PRECISION NOT NULL,
    axis_4_defense      DOUBLE PRECISION NOT NULL,
    axis_5_critical_inputs DOUBLE PRECISION NOT NULL,
    axis_6_logistics    DOUBLE PRECISION NOT NULL,

    -- Derived fields (deterministic from axes + methodology)
    isi_composite       DOUBLE PRECISION NOT NULL,  -- mean(6 axes), or weighted per methodology
    rank_in_year        SMALLINT        NOT NULL,   -- 1 = highest dependency, among EU-27 for same (year, methodology)
    classification      VARCHAR(32)     NOT NULL,   -- "highly_concentrated" | "moderately_concentrated" | "mildly_concentrated" | "unconcentrated"

    -- Reproducibility
    data_window         VARCHAR(32)     NOT NULL,   -- e.g. "2020–2022", "2022–2024"
    computation_hash    CHAR(64)        NOT NULL,   -- SHA-256 of deterministic input vector (see §2.2.3)

    -- Audit
    computed_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    computed_by         VARCHAR(128)    NOT NULL,    -- script version or pipeline run ID

    -- Constraints
    PRIMARY KEY (country_code, year, methodology_version),
    CHECK (year >= 2000 AND year <= 2100),
    CHECK (isi_composite >= 0.0 AND isi_composite <= 1.0),
    CHECK (rank_in_year >= 1 AND rank_in_year <= 27),
    CHECK (classification IN ('highly_concentrated', 'moderately_concentrated',
                               'mildly_concentrated', 'unconcentrated'))
);

-- =============================================================
-- ENTITY: axis_score
-- =============================================================
-- Normalized axis scores for flexible querying.
-- Denormalized copy of isi_snapshot axis columns — maintained by trigger or export.

CREATE TABLE axis_score (
    country_code        CHAR(2)         NOT NULL,
    year                SMALLINT        NOT NULL,
    methodology_version VARCHAR(16)     NOT NULL,
    axis_slug           VARCHAR(32)     NOT NULL,   -- "financial", "energy", "technology", "defense", "critical_inputs", "logistics"
    axis_score          DOUBLE PRECISION NOT NULL,
    classification      VARCHAR(32)     NOT NULL,   -- Per-axis classification
    data_window         VARCHAR(32)     NOT NULL,

    PRIMARY KEY (country_code, year, methodology_version, axis_slug),
    FOREIGN KEY (country_code, year, methodology_version)
        REFERENCES isi_snapshot(country_code, year, methodology_version),
    CHECK (axis_score >= 0.0 AND axis_score <= 1.0)
);

-- =============================================================
-- ENTITY: methodology_registry
-- =============================================================
-- Frozen definition of each methodology version.

CREATE TABLE methodology_registry (
    methodology_version VARCHAR(16)     PRIMARY KEY,
    label               VARCHAR(128)    NOT NULL,   -- Human-readable name
    aggregation_rule    VARCHAR(64)     NOT NULL,   -- "unweighted_arithmetic_mean"
    aggregation_formula VARCHAR(256)    NOT NULL,   -- "ISI_i = (A1 + A2 + ... + A6) / 6"
    axis_weights        JSONB           NOT NULL,   -- {axis_slug: weight} — all 1.0 for v1.0
    classification_thresholds JSONB     NOT NULL,   -- [[0.50, "highly_concentrated"], ...]
    score_range         JSONB           NOT NULL DEFAULT '[0.0, 1.0]',
    num_axes            SMALLINT        NOT NULL DEFAULT 6,
    frozen_at           TIMESTAMP WITH TIME ZONE NOT NULL,
    notes               TEXT,

    CHECK (num_axes > 0)
);

-- =============================================================
-- ENTITY: eu_aggregate
-- =============================================================
-- Pre-computed EU-27 aggregate statistics per year/methodology.
-- Avoids recomputing mean/min/max on every request.

CREATE TABLE eu_aggregate (
    year                SMALLINT        NOT NULL,
    methodology_version VARCHAR(16)     NOT NULL,
    axis_slug           VARCHAR(32),    -- NULL = composite level
    eu_mean             DOUBLE PRECISION NOT NULL,
    eu_min              DOUBLE PRECISION NOT NULL,
    eu_max              DOUBLE PRECISION NOT NULL,
    eu_median           DOUBLE PRECISION,
    eu_std_dev          DOUBLE PRECISION,

    PRIMARY KEY (year, methodology_version, axis_slug)
);

-- =============================================================
-- ENTITY: snapshot_manifest
-- =============================================================
-- Integrity record for each materialized snapshot.

CREATE TABLE snapshot_manifest (
    year                SMALLINT        NOT NULL,
    methodology_version VARCHAR(16)     NOT NULL,
    artifact_path       VARCHAR(512)    NOT NULL,   -- e.g. "backend/v01/2023/isi.json"
    sha256              CHAR(64)        NOT NULL,
    file_count          SMALLINT        NOT NULL,
    materialized_at     TIMESTAMP WITH TIME ZONE NOT NULL,

    PRIMARY KEY (year, methodology_version)
);
```

#### 2.2.2 Indexing Strategy

```sql
-- Primary access pattern: single country time series
CREATE INDEX idx_snapshot_country_year
    ON isi_snapshot(country_code, year);

-- Ranking queries: all countries for a given (year, methodology)
CREATE INDEX idx_snapshot_year_methodology
    ON isi_snapshot(year, methodology_version);

-- Axis-level time series
CREATE INDEX idx_axis_score_country_axis
    ON axis_score(country_code, axis_slug, year);

-- EU aggregate lookups
CREATE INDEX idx_eu_agg_year
    ON eu_aggregate(year, methodology_version);

-- Methodology lookups (small table, PK is sufficient)
-- No additional index needed.
```

#### 2.2.3 Computation Hash

The `computation_hash` guarantees bit-exact reproducibility. It is the SHA-256 of a **deterministic input vector**:

```
computation_hash = SHA-256(
    country_code || "|" ||
    year || "|" ||
    methodology_version || "|" ||
    axis_1_financial (16 decimal places) || "|" ||
    axis_2_energy || "|" ||
    axis_3_technology || "|" ||
    axis_4_defense || "|" ||
    axis_5_critical_inputs || "|" ||
    axis_6_logistics || "|" ||
    data_window || "|" ||
    aggregation_rule || "|" ||
    json(classification_thresholds) || "|" ||
    json(axis_weights)
)
```

This hash is computed at materialization time and stored. Any future recomputation must produce the same hash or the snapshot is flagged as divergent.

#### 2.2.4 Versioning Logic

- **Immutability rule:** Once a row exists in `isi_snapshot` for a given `(country_code, year, methodology_version)`, it is **never updated**. If methodology changes, a new `methodology_version` row is inserted.
- **Methodology-version scoping:** All queries are scoped to a methodology version. The API defaults to the **latest** methodology version unless explicitly specified.
- **Backfill compatibility:** Historical years (2020, 2021) can be backfilled by running the export pipeline against historical CSV data. Each backfill creates rows with the correct year + methodology version. Existing rows for other years/methodologies are never touched.

### 2.3 Entity Relationship Diagram (Text)

```
┌─────────────────────────┐       ┌──────────────────────────┐
│   methodology_registry  │       │      eu_aggregate        │
│─────────────────────────│       │──────────────────────────│
│ PK methodology_version  │◄──┐   │ PK year                  │
│    aggregation_rule     │   │   │ PK methodology_version   │
│    aggregation_formula  │   │   │ PK axis_slug             │
│    axis_weights (JSONB) │   │   │    eu_mean, min, max     │
│    classification_thr.  │   │   │    eu_median, std_dev    │
│    frozen_at            │   │   └──────────────────────────┘
└─────────────────────────┘   │
                              │
                              │
┌─────────────────────────┐   │   ┌──────────────────────────┐
│      isi_snapshot       │   │   │    snapshot_manifest     │
│─────────────────────────│   │   │──────────────────────────│
│ PK country_code         │───┘   │ PK year                  │
│ PK year                 │       │ PK methodology_version   │
│ PK methodology_version  │       │    artifact_path         │
│    axis_1..6 scores     │       │    sha256                │
│    isi_composite        │       │    materialized_at       │
│    rank_in_year         │       └──────────────────────────┘
│    classification       │
│    data_window          │
│    computation_hash     │
│    computed_at          │
└────────┬────────────────┘
         │ 1:N
         ▼
┌─────────────────────────┐
│      axis_score         │
│─────────────────────────│
│ PK country_code         │
│ PK year                 │
│ PK methodology_version  │
│ PK axis_slug            │
│    axis_score           │
│    classification       │
│    data_window          │
└─────────────────────────┘
```

---

## 3. Phase 2 — Methodology Versioning

### 3.1 Methodology Registry Design

Each methodology version is a **frozen, self-contained definition** of how ISI scores are computed. The registry stores:

```json
{
  "methodology_version": "v1.0",
  "label": "ISI Baseline Methodology — Unweighted HHI Mean",
  "aggregation_rule": "unweighted_arithmetic_mean",
  "aggregation_formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
  "axis_weights": {
    "financial": 1.0,
    "energy": 1.0,
    "technology": 1.0,
    "defense": 1.0,
    "critical_inputs": 1.0,
    "logistics": 1.0
  },
  "classification_thresholds": [
    [0.50, "highly_concentrated"],
    [0.25, "moderately_concentrated"],
    [0.15, "mildly_concentrated"]
  ],
  "default_classification": "unconcentrated",
  "score_range": [0.0, 1.0],
  "num_axes": 6,
  "frozen_at": "2026-02-21T00:00:00+00:00",
  "notes": "Initial methodology. All axes equally weighted. Classification thresholds from standard HHI interpretation."
}
```

### 3.2 Frozen Historical Recomputation Logic

**Problem:** If methodology v2.0 changes the aggregation formula (e.g., introduces axis weights), we must still be able to serve v1.0 results for any historical year.

**Solution: Methodology-keyed snapshot immutability.**

1. **Every `isi_snapshot` row is triple-keyed:** `(country_code, year, methodology_version)`.
2. **Materialized snapshots are immutable.** Once `(SE, 2022, v1.0)` is written, it is never modified.
3. **New methodologies create new rows.** If v2.0 is introduced, the export pipeline runs against the same source CSVs but with v2.0 parameters, producing `(SE, 2022, v2.0)` as a new row.
4. **The computation logic for each methodology is code-versioned.** The exporter must be able to run any registered methodology. This is achieved via a `MethodologyRunner` dispatch:

```python
# Pseudocode — not implementation
class MethodologyRunner:
    """Dispatches computation to the correct frozen logic per version."""

    _registry: dict[str, Callable] = {
        "v1.0": _compute_v1_0,  # unweighted mean, thresholds [0.50, 0.25, 0.15]
    }

    @classmethod
    def compute(cls, version: str, axis_scores: dict[str, float]) -> ComputedResult:
        fn = cls._registry.get(version)
        if fn is None:
            raise ValueError(f"Unknown methodology version: {version}")
        return fn(axis_scores)

def _compute_v1_0(axis_scores: dict[str, float]) -> ComputedResult:
    composite = sum(axis_scores.values()) / 6
    classification = classify_v1_0(composite)  # thresholds frozen
    return ComputedResult(composite=composite, classification=classification)
```

### 3.3 Reproducible Hash for Each Yearly Snapshot

Each snapshot includes a `computation_hash` (§2.2.3). This hash:

1. **Is computed deterministically** from the input axis scores + methodology parameters.
2. **Is stored alongside the snapshot** in `isi_snapshot.computation_hash`.
3. **Is verified on recomputation.** If rerunning the pipeline for `(SE, 2022, v1.0)` produces a different hash, the system flags a **reproducibility violation** and refuses to overwrite.

**Verification flow:**
```
1. Load source CSVs for year=2022
2. Compute axis scores using v1.0 methodology
3. Compute hash from (scores + methodology params)
4. Compare against stored computation_hash
5. MATCH → snapshot is reproducible ✓
6. MISMATCH → flag error, do NOT overwrite, log divergence
```

### 3.4 Protection Against Retroactive Drift

**Threat model:** An upstream CSV is silently corrected (e.g., a data provider revises 2022 figures). Rerunning the pipeline would produce different scores for `(SE, 2022, v1.0)`, breaking reproducibility.

**Protections:**

| Layer | Mechanism |
|-------|-----------|
| Source data | Source CSVs are versioned in git. Any change is a tracked commit. |
| Computation hash | `computation_hash` detects any change in inputs or methodology. |
| Snapshot immutability | `INSERT ... ON CONFLICT DO NOTHING` — existing snapshots cannot be overwritten. |
| Manifest integrity | `snapshot_manifest.sha256` verifies materialized JSON files on startup (existing `verify_manifest()` pattern). |
| Audit trail | `computed_at` + `computed_by` fields trace when and by what pipeline version the snapshot was created. |

### 3.5 Immutable Historical Retrieval Guarantee

> **Requirement:** `GET /country/SE?year=2022&methodology=v1.0` returns the same result 5 years from now.

**Guarantee mechanism:**

1. The snapshot `(SE, 2022, v1.0)` is written once to `isi_snapshot` and to `backend/v01/2022/country/SE.json`.
2. The row has a `computation_hash`. The JSON file has a SHA-256 in `snapshot_manifest`.
3. Neither the row nor the file is ever mutated.
4. If the source CSV is later corrected, a **new methodology version** (e.g., `v1.0-rev1`) is registered, and new snapshots are created under that version. The original `v1.0` snapshots remain frozen.
5. The API resolves `methodology=v1.0` to the immutable snapshot. No recomputation occurs at serve time.

This is the same architectural pattern used by central bank statistical databases (ECB SDW, BIS SDMX): **revisions create new series, not mutations**.

---

## 4. Phase 3 — Time Series Requirements

### 4.1 New Endpoints

All new endpoints are **additive** — existing endpoints retain identical behavior.

#### 4.1.1 `GET /country/{code}/history`

Returns the full ISI time series for one country.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `code` | path | required | 2-letter ISO country code |
| `methodology` | query | latest | Methodology version filter |
| `from_year` | query | earliest | Start year (inclusive) |
| `to_year` | query | latest | End year (inclusive) |

**Response schema:**
```json
{
  "country": "SE",
  "country_name": "Sweden",
  "methodology_version": "v1.0",
  "years": [
    {
      "year": 2022,
      "data_window": "2020–2022",
      "isi_composite": 0.38124,
      "rank": 14,
      "classification": "moderately_concentrated",
      "axes": {
        "financial": 0.1102,
        "energy": 0.4981,
        "technology": 0.1244,
        "defense": 0.8501,
        "critical_inputs": 0.3612,
        "logistics": 0.3624
      }
    },
    {
      "year": 2023,
      "data_window": "2021–2023",
      "isi_composite": 0.39012,
      "rank": 15,
      "classification": "moderately_concentrated",
      "axes": { ... }
    },
    {
      "year": 2024,
      "data_window": "2022–2024",
      "isi_composite": 0.39871,
      "rank": 16,
      "classification": "moderately_concentrated",
      "axes": { ... }
    }
  ],
  "meta": {
    "years_available": 3,
    "earliest_year": 2022,
    "latest_year": 2024
  }
}
```

#### 4.1.2 `GET /country/{code}/axis/{axis_slug}/history`

Returns per-axis score time series for one country.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `code` | path | required | 2-letter ISO country code |
| `axis_slug` | path | required | Axis slug: `financial`, `energy`, `technology`, `defense`, `critical_inputs`, `logistics` |
| `methodology` | query | latest | Methodology version filter |

**Response schema:**
```json
{
  "country": "SE",
  "country_name": "Sweden",
  "axis_slug": "energy",
  "axis_name": "Energy Dependency",
  "methodology_version": "v1.0",
  "years": [
    {
      "year": 2022,
      "score": 0.4981,
      "classification": "moderately_concentrated",
      "delta_vs_previous": null,
      "delta_vs_eu_mean": 0.0712,
      "eu_mean": 0.4269
    },
    {
      "year": 2023,
      "score": 0.5102,
      "classification": "highly_concentrated",
      "delta_vs_previous": 0.0121,
      "delta_vs_eu_mean": 0.0834,
      "eu_mean": 0.4268
    }
  ],
  "trend": {
    "direction": "worsening",
    "total_change": 0.0241,
    "annualized_change": 0.0121,
    "classification_changes": [
      {
        "from_year": 2022,
        "to_year": 2023,
        "from": "moderately_concentrated",
        "to": "highly_concentrated"
      }
    ]
  }
}
```

#### 4.1.3 `GET /eu/history`

Returns EU-27 aggregate statistics time series.

**Parameters:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `methodology` | query | latest | Methodology version |
| `axis_slug` | query | null | If provided, returns EU stats for that axis only. If null, returns composite. |

**Response schema:**
```json
{
  "scope": "EU-27",
  "methodology_version": "v1.0",
  "level": "composite",
  "years": [
    {
      "year": 2022,
      "eu_mean": 0.3389,
      "eu_min": 0.2301,
      "eu_max": 0.5098,
      "eu_median": 0.3344,
      "eu_std_dev": 0.0612
    },
    {
      "year": 2023,
      "eu_mean": 0.3412,
      "eu_min": 0.2312,
      "eu_max": 0.5124,
      "eu_median": 0.3390,
      "eu_std_dev": 0.0598
    }
  ]
}
```

#### 4.1.4 `GET /methodology/versions`

Returns the methodology registry.

**Response schema:**
```json
{
  "versions": [
    {
      "version": "v1.0",
      "label": "ISI Baseline Methodology — Unweighted HHI Mean",
      "aggregation_rule": "unweighted_arithmetic_mean",
      "num_axes": 6,
      "classification_thresholds": [[0.50, "highly"], [0.25, "moderately"], [0.15, "mildly"]],
      "frozen_at": "2026-02-21T00:00:00+00:00",
      "is_latest": true
    }
  ],
  "latest": "v1.0"
}
```

### 4.2 Backward Compatibility

Existing endpoints are **unaffected**:

| Existing Endpoint | v2 Behavior |
|-------------------|-------------|
| `GET /isi` | Returns the **latest year × latest methodology** snapshot. Identical response shape. |
| `GET /country/{code}` | Returns the latest snapshot. Identical response shape. |
| `POST /scenario` | Defaults to latest year × latest methodology. See Phase 4. |

The existing response schemas have `"version"` and `"window"` fields already. These will continue to reflect the latest snapshot.

---

## 5. Phase 4 — Scenario Engine Compatibility

### 5.1 Current Scenario Engine Architecture

The current scenario engine (`scenario.py`) is a **pure function** with this signature:

```python
simulate(
    country_code: str,               # "SE"
    adjustments: dict[str, float],   # {canonical_key: [-0.20, +0.20]}
    all_baselines: list[dict],       # isi.json["countries"]
) -> ScenarioResponse
```

It has:
- **Zero I/O** — receives baselines as a parameter
- **Zero global state** — pure computation
- **Zero year awareness** — operates on whatever baselines are passed in

### 5.2 Year-Specific Scenario Simulation Design

#### 5.2.1 Extended Request Schema

```python
class ScenarioRequest(BaseModel):
    country: str          # Required. 2-letter ISO code.
    adjustments: dict[str, float]  # Required. Canonical axis keys.
    year: int | None = None        # NEW. Optional. Defaults to latest year.
    methodology: str | None = None # NEW. Optional. Defaults to latest methodology.
```

**Backward compatibility:** Both new fields default to `None`, which resolves to the latest year/methodology. Existing clients sending `{"country": "SE", "adjustments": {...}}` get identical behavior.

#### 5.2.2 Extended Response Schema

```python
class MetaBlock(BaseModel):
    version: str           # "scenario-v1"
    timestamp: str         # ISO 8601
    bounds: dict           # {"min": -0.2, "max": 0.2}
    year: int              # NEW — which year's baseline was used
    methodology: str       # NEW — which methodology version was applied
    data_window: str       # NEW — "2022–2024"
```

**Backward compatibility:** New fields are **additive**. The JSON key `version` (currently `"scenario-v1"`) remains unchanged. Existing clients that ignore unknown keys are unaffected.

#### 5.2.3 How Simulation References Historical Data

```python
# Pseudocode for the updated API handler (isi_api_v01.py)

async def scenario(request: Request, body: dict) -> JSONResponse:
    req = ScenarioRequest(**body)

    # Resolve year and methodology
    year = req.year or get_latest_year()
    methodology = req.methodology or get_latest_methodology()

    # Load the correct year-specific baseline
    # KEY CHANGE: instead of _get_or_load("isi", ...),
    # we load the year-specific snapshot
    baselines = load_snapshot_baselines(year, methodology)

    # The simulate() function is UNCHANGED
    result = simulate(
        country_code=req.country,
        adjustments=req.adjustments,
        all_baselines=baselines,
    )

    # Attach year/methodology to meta
    result.meta.year = year
    result.meta.methodology = methodology
    result.meta.data_window = get_data_window(year, methodology)

    return JSONResponse(content=result.model_dump(mode="json"))
```

#### 5.2.4 Correct Methodology Application

When a scenario simulation requests `year=2021, methodology=v1.0`:

1. The system loads the `isi_snapshot` rows for `(year=2021, methodology=v1.0)`.
2. The `methodology_registry` entry for `v1.0` provides the classification thresholds `[0.50, 0.25, 0.15]`.
3. The `simulate()` function uses these thresholds for `classify()`.
4. The composite formula is `unweighted_arithmetic_mean` as defined in v1.0.
5. **The simulate() function itself does not change.** The methodology is already embedded in the thresholds and formula used. For v1.0, the current `scenario.py` logic is correct as-is.

**If v2.0 introduces weighted means**, the `simulate()` function must dispatch to the correct `compute_composite()` variant. This is handled by making `compute_composite()` methodology-aware:

```python
def compute_composite(axis_values: dict[str, float], methodology: str) -> float:
    """ISI composite — dispatches to correct formula per methodology."""
    meta = load_methodology(methodology)
    weights = meta["axis_weights"]
    if meta["aggregation_rule"] == "unweighted_arithmetic_mean":
        return sum(axis_values.values()) / len(axis_values)
    elif meta["aggregation_rule"] == "weighted_arithmetic_mean":
        return sum(axis_values[k] * weights[k] for k in axis_values) / sum(weights.values())
    else:
        raise ValueError(f"Unknown aggregation rule: {meta['aggregation_rule']}")
```

#### 5.2.5 Invariant: Simulation Never Mutates Historical Records

**Rule:** `simulate()` is a pure function. It reads baselines and produces a response. It has zero write access to any storage layer. This is already true in v1 and must remain true in v2.

The scenario response is **ephemeral** — it exists only in the HTTP response. It is never persisted.

---

## 6. Phase 5 — Storage Strategy

### 6.1 Options Evaluated

| | Option A: Pre-computed Snapshots | Option B: On-demand Recomputation | Option C: Hybrid |
|--|--|--|--|
| **Architecture** | Export pipeline materializes JSON per (year, methodology). API serves from disk/memory. | API computes from raw CSVs on every request. | Pre-compute snapshots + verify hash on recomputation. |
| **Determinism** | ✅ Byte-exact (JSON files are static) | ⚠️ Depends on floating-point determinism of pipeline | ✅ Hash-verified |
| **Latency** | ✅ <5ms (memory cache) | ❌ 2-10s (CSV parse + HHI computation) | ✅ <5ms read, recompute is offline |
| **Cost** | ✅ Low (static files, no compute at runtime) | ❌ High (CPU per request) | ✅ Low read, moderate batch |
| **Complexity** | ✅ Low (existing pattern) | ❌ High (pipeline in hot path) | ⚠️ Medium (two code paths) |
| **Data window expansion** | ✅ Run pipeline for new year, add new JSON directory | ⚠️ Must keep all raw CSVs accessible at runtime | ✅ Same as A |
| **Reproducibility** | ✅ Snapshot + SHA-256 manifest | ⚠️ Must pin all dependencies, floating-point order | ✅ Hash-validated |

### 6.2 Recommendation: Option C — Hybrid (Pre-compute + Hash Validation)

**Rationale:**

Option A alone is what we have today and works well. However, for temporal integrity, we need the ability to **verify** that a snapshot is still reproducible from source data. Pure Option A gives no mechanism to detect if source CSVs have drifted since the snapshot was materialized.

Option C adds one capability on top of A:

1. **Primary path (hot):** Serve from pre-materialized JSON snapshots (identical to current architecture).
2. **Verification path (cold, batch-only):** A CI/CD job or manual command can re-run the pipeline for any `(year, methodology)` and verify the `computation_hash` matches the stored snapshot. If it doesn't, a divergence alert fires.

**This does NOT add on-demand computation to the hot path.** The API remains read-only, serving from memory. The recomputation path is offline/batch only.

### 6.3 Storage Layout (v2)

```
backend/
├── v01/                          # Legacy: single-window (2022–2024, v1.0)
│   ├── meta.json                 # Unchanged — backward compat
│   ├── isi.json                  # Unchanged — latest year symlink target
│   ├── countries.json
│   ├── axes.json
│   ├── country/{CODE}.json
│   ├── axis/{n}.json
│   └── MANIFEST.json
│
├── snapshots/                    # NEW: year × methodology snapshots
│   ├── v1.0/
│   │   ├── 2022/
│   │   │   ├── isi.json
│   │   │   ├── country/{CODE}.json
│   │   │   ├── axis/{n}.json
│   │   │   └── MANIFEST.json
│   │   ├── 2023/
│   │   │   └── ...
│   │   └── 2024/                 # Identical content to v01/ for initial release
│   │       └── ...
│   └── registry.json             # Methodology registry
│
└── latest -> snapshots/v1.0/2024/  # Symlink to current default
```

**Key points:**
- `backend/v01/` is **retained** for backward compatibility. It becomes an alias for the latest snapshot.
- New time-series endpoints read from `backend/snapshots/{methodology}/{year}/`.
- The `_get_or_load()` cache is extended to key by `(year, methodology, artifact)` instead of just `(artifact)`.
- Total storage: ~82 files × N years × M methodology versions. For 3 years × 1 methodology = ~246 files = ~3 MB. Minimal.

---

## 7. Phase 6 — Structural Trend Logic

All trend computations are performed **server-side** at materialization time (export pipeline) and/or at serve time for time-series endpoints. Never on the frontend.

### 7.1 Axis Trend Direction (Δ vs Previous Year)

```python
def compute_axis_delta(
    country: str, axis_slug: str, year: int, methodology: str
) -> dict:
    """Compute year-over-year axis score change."""
    current = get_axis_score(country, axis_slug, year, methodology)
    previous = get_axis_score(country, axis_slug, year - 1, methodology)

    if previous is None:
        return {"delta": None, "direction": None, "previous_year": None}

    delta = current - previous
    direction = "worsening" if delta > 0 else "improving" if delta < 0 else "stable"

    return {
        "delta": round(delta, 10),
        "direction": direction,
        "previous_year": year - 1,
        "previous_score": previous,
        "current_score": current,
    }
```

**Interpretation convention:** Higher score = more concentrated = more dependent. Therefore:
- `delta > 0` → **worsening** (dependency increasing)
- `delta < 0` → **improving** (dependency decreasing)
- `delta == 0` → **stable**

### 7.2 Classification Upgrade/Downgrade Detection

```python
def detect_classification_change(
    country: str, year: int, methodology: str
) -> dict | None:
    """Detect if classification tier changed vs previous year."""
    current_class = get_classification(country, year, methodology)
    previous_class = get_classification(country, year - 1, methodology)

    if previous_class is None:
        return None

    TIER_ORDER = {
        "unconcentrated": 0,
        "mildly_concentrated": 1,
        "moderately_concentrated": 2,
        "highly_concentrated": 3,
    }

    current_tier = TIER_ORDER[current_class]
    previous_tier = TIER_ORDER[previous_class]

    if current_tier == previous_tier:
        return None

    return {
        "type": "upgrade" if current_tier < previous_tier else "downgrade",
        "from": previous_class,
        "to": current_class,
        "from_year": year - 1,
        "to_year": year,
        "tier_change": current_tier - previous_tier,
    }
```

**Terminology:**
- **Upgrade:** Tier decreases (less concentrated). E.g., moderately → mildly.
- **Downgrade:** Tier increases (more concentrated). E.g., mildly → moderately.

### 7.3 Structural Volatility Measure

Volatility measures how unstable a country's scores are over the available time series.

```python
def compute_volatility(
    country: str, axis_slug: str | None, methodology: str
) -> dict:
    """Compute score volatility over available years.

    If axis_slug is None, computes composite volatility.
    Uses coefficient of variation (CV = std_dev / mean).
    """
    scores = get_all_year_scores(country, axis_slug, methodology)

    if len(scores) < 2:
        return {"volatility": None, "cv": None, "years": len(scores)}

    values = [s["score"] for s in scores]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std_dev = variance ** 0.5
    cv = std_dev / mean if mean > 0 else None

    return {
        "volatility_std_dev": round(std_dev, 10),
        "volatility_cv": round(cv, 10) if cv else None,
        "mean": round(mean, 10),
        "years_measured": len(values),
        "interpretation": _classify_volatility(cv),
    }

def _classify_volatility(cv: float | None) -> str:
    if cv is None:
        return "insufficient_data"
    if cv < 0.05:
        return "stable"
    if cv < 0.15:
        return "moderate"
    return "volatile"
```

### 7.4 Axis Convergence/Divergence vs EU Mean

```python
def compute_eu_deviation_trend(
    country: str, axis_slug: str | None, methodology: str
) -> dict:
    """Track whether a country is converging toward or diverging from EU mean."""
    years = get_available_years(methodology)
    deviations = []

    for year in sorted(years):
        country_score = get_score(country, axis_slug, year, methodology)
        eu_mean = get_eu_mean(axis_slug, year, methodology)
        if country_score is not None and eu_mean is not None:
            deviations.append({
                "year": year,
                "score": country_score,
                "eu_mean": eu_mean,
                "deviation": round(country_score - eu_mean, 10),
                "deviation_pct": round((country_score - eu_mean) / eu_mean, 10) if eu_mean > 0 else None,
            })

    if len(deviations) < 2:
        return {"trend": None, "deviations": deviations}

    # Direction: is the gap growing or shrinking?
    first_dev = abs(deviations[0]["deviation"])
    last_dev = abs(deviations[-1]["deviation"])

    trend = "converging" if last_dev < first_dev else "diverging" if last_dev > first_dev else "stable"

    return {
        "trend": trend,
        "deviations": deviations,
        "gap_change": round(last_dev - first_dev, 10),
    }
```

### 7.5 Pre-computation vs On-demand

All trend metrics from §7.1–7.4 can be:

- **Pre-computed at export time** and stored in each snapshot's country/axis JSON files — zero cost at serve time.
- **Computed on-demand** from the cached snapshots at API response time — minimal cost (simple arithmetic on <30 data points per country).

**Recommendation:** Pre-compute `delta_vs_previous`, `classification_change`, and `eu_deviation` at export time (they're deterministic from stored data). Compute `volatility` on-demand since it spans all years and benefits from the latest available data.

---

## 8. Phase 7 — Migration Plan

### 8.1 Principles

1. **Zero downtime.** The existing API must remain available throughout migration.
2. **Zero data loss.** Current v01 artifacts are preserved.
3. **Feature-flagged rollout.** New endpoints are enabled behind a flag before becoming default.
4. **Rollback is always possible.** The v01 directory remains the fallback.

### 8.2 Step-by-Step Migration Plan

#### Step 1: Register v1.0 Methodology (Week 1)

- Create `backend/snapshots/registry.json` with the v1.0 methodology definition.
- Add `methodology_registry` support to the exporter.
- No API changes. No behavior changes.
- **Verification:** `registry.json` exists and is loadable.

#### Step 2: Backfill 2024 Snapshot (Week 1)

- Run the existing exporter with year=2024 flag.
- Output to `backend/snapshots/v1.0/2024/`.
- Compute and store `computation_hash` for each country.
- Verify: snapshot content is **byte-identical** to `backend/v01/`.
- **Verification:** `diff -r backend/v01/ backend/snapshots/v1.0/2024/` produces no output (excluding MANIFEST.json paths).

#### Step 3: Prepare Historical Source Data (Weeks 2–4)

- Identify which upstream CSVs contain 2022 and 2023 data (or can be filtered by year).
- Some axes use multi-year windows (defense uses 2019–2024). These need year-specific extraction.
- For each axis, create year-specific CSVs in `data/processed/{axis_dir}/` with year-tagged filenames: `finance_dependency_2022_eu27.csv`, `finance_dependency_2023_eu27.csv`.
- **Risk:** Some source data may not be available at year granularity. See §8.5.

#### Step 4: Backfill 2022 and 2023 Snapshots (Weeks 3–5)

- Extend `export_isi_backend_v01.py` to accept `--year` and `--methodology` CLI arguments.
- Run exporter for each `(year, methodology)` pair.
- Each run produces a complete snapshot directory under `backend/snapshots/v1.0/{year}/`.
- Compute and store `computation_hash` for all snapshots.
- **Verification:** All 27 countries × 6 axes present in each snapshot. Hash values stored.

#### Step 5: Extend API Cache Layer (Week 4)

- Modify `_get_or_load()` to support year/methodology-keyed cache:
  ```python
  _cache: dict[str, Any] = {}  # key: "isi" → key: "v1.0:2024:isi"
  ```
- Add `_resolve_snapshot_path(year, methodology, artifact)` helper.
- **All existing endpoints continue to use the unkeyed "latest" path.** No behavior change.
- **Verification:** All 74 existing tests pass unchanged.

#### Step 6: Add Time-Series Endpoints Behind Feature Flag (Weeks 5–6)

- Add `ENABLE_TIME_SERIES` env var (default: `"0"`).
- Implement `/country/{code}/history`, `/country/{code}/axis/{slug}/history`, `/eu/history`, `/methodology/versions`.
- All new endpoints return 404 when `ENABLE_TIME_SERIES != "1"`.
- **Verification:** New endpoint tests pass with flag on. Existing tests pass with flag off.

#### Step 7: Extend Scenario Engine (Week 6)

- Add `year` and `methodology` to `ScenarioRequest` (optional, defaults to None).
- In API handler, resolve `year` and `methodology` before calling `simulate()`.
- Load year-specific baselines instead of the single `isi.json`.
- **Verification:** Existing scenario tests pass without `year`/`methodology` in request. New tests verify year-specific behavior.

#### Step 8: Enable Time-Series in Production (Week 7)

- Set `ENABLE_TIME_SERIES=1` in Railway env.
- Monitor error rates and latency for 48 hours.
- If issues: set flag back to `0` (instant rollback).
- **Verification:** Zero errors in structured logs. Latency within 2× of current p99.

#### Step 9: Promote and Clean Up (Week 8)

- Remove feature flag. New endpoints are always available.
- Update `meta.json` to reflect v2 capabilities.
- Update API documentation and schema endpoint.
- **`backend/v01/` is NOT deleted.** It continues to serve as the "latest" symlink target.

### 8.3 Data Backfill Plan

| Axis | 2022 Source Availability | 2023 Source Availability | Backfill Difficulty |
|------|-------------------------|-------------------------|-------------------|
| 1. Financial | BIS LBS + IMF CPIS: Available via API with year param | Same | Low |
| 2. Energy | Eurostat nrg_ti_*: Available with TIME_PERIOD filter | Same | Low |
| 3. Technology | Eurostat Comext: Available with year filter | Same | Low |
| 4. Defense | SIPRI: 6-year rolling window. 2019–2024 → need 2017–2022 and 2018–2023 | Complex | High |
| 5. Critical Inputs | Eurostat Comext: Available with year filter | Same | Low |
| 6. Logistics | Eurostat tran_*: Available with year filter | Same | Low |

**Defense axis (Axis 4) risk:** SIPRI uses a 6-year delivery window. The 2022 snapshot should use 2017–2022 deliveries, but the current pipeline hardcodes 2019–2024. This requires parameterizing the SIPRI query window. Flag this for Phase 3 data preparation.

### 8.4 Feature Flag Strategy

```python
# In isi_api_v01.py

ENABLE_TIME_SERIES = os.getenv("ENABLE_TIME_SERIES", "0").strip() == "1"

# Applied per-endpoint:
@app.get("/country/{code}/history")
async def country_history(code: str, request: Request):
    if not ENABLE_TIME_SERIES:
        raise HTTPException(status_code=404, detail="Not found.")
    # ... implementation ...
```

**Flag matrix:**

| Flag Value | Existing Endpoints | New Endpoints | Scenario Engine |
|------------|-------------------|---------------|-----------------|
| `0` (default) | ✅ Normal | ❌ 404 | ✅ Latest year only |
| `1` | ✅ Normal | ✅ Active | ✅ Year-specific |

### 8.5 Rollback Plan

| Failure Scenario | Rollback Action | Recovery Time |
|-----------------|-----------------|---------------|
| New endpoints returning errors | Set `ENABLE_TIME_SERIES=0` | <1 min (env var redeploy) |
| Cache memory exhaustion from multi-year data | Reduce loaded years via `MAX_CACHED_YEARS` env var | <1 min |
| Scenario engine regression | Revert scenario.py to pre-year-aware commit | <5 min (git revert + deploy) |
| Data integrity issue in backfilled snapshots | Delete affected snapshot directories. v01/ unchanged. | <10 min |
| Full architectural failure | Revert entire deploy to previous Railway release. v01/ and all existing endpoints are unchanged. | <2 min (Railway rollback) |

---

## 9. Phase 8 — Output Requirements

### 9.1 Full Proposed Schema (SQL-Style)

See §2.2.1 for the complete schema definition. Summary:

| Table | Columns | PK | Rows (estimated, 3 years × 1 methodology) |
|-------|---------|----|--------------------------------------------|
| `isi_snapshot` | 15 | `(country_code, year, methodology_version)` | 81 (27 × 3) |
| `axis_score` | 7 | `(country_code, year, methodology_version, axis_slug)` | 486 (27 × 3 × 6) |
| `methodology_registry` | 10 | `(methodology_version)` | 1 |
| `eu_aggregate` | 8 | `(year, methodology_version, axis_slug)` | 21 (3 × 7) |
| `snapshot_manifest` | 6 | `(year, methodology_version)` | 3 |

**Note:** These tables define the **logical model**. The physical implementation remains pre-materialized JSON files (see §6.3). The SQL schema serves as the canonical data contract. A future migration to PostgreSQL would use these tables directly.

### 9.2 Entity Relationship Summary

```
methodology_registry (1) ←──── (N) isi_snapshot (1) ────→ (N) axis_score
                                        │
                                        └──── (1) snapshot_manifest
                                        │
                                        └──── (N) eu_aggregate
```

- One methodology version governs many snapshots.
- One snapshot (country × year × methodology) has exactly 6 axis_score rows.
- One (year × methodology) pair has one snapshot_manifest and multiple eu_aggregate rows.

### 9.3 API Endpoint Design

#### 9.3.1 New Endpoints

| Method | Path | Parameters | Rate Limit | Response |
|--------|------|-----------|------------|----------|
| GET | `/country/{code}/history` | `?methodology=&from_year=&to_year=` | 30/min | Full ISI time series for one country |
| GET | `/country/{code}/axis/{slug}/history` | `?methodology=` | 30/min | Per-axis time series for one country |
| GET | `/eu/history` | `?methodology=&axis_slug=` | 30/min | EU-27 aggregate statistics time series |
| GET | `/methodology/versions` | — | 60/min | Methodology registry |

#### 9.3.2 Modified Endpoints

| Method | Path | Change | Backward Compatible? |
|--------|------|--------|---------------------|
| POST | `/scenario` | Accept optional `year` and `methodology` in request body | ✅ Yes — defaults to latest |
| GET | `/scenario/schema` | Add `year` and `methodology` to example request | ✅ Yes — additive |

#### 9.3.3 Unchanged Endpoints (13 total)

```
GET /                       GET /health
GET /ready                  GET /countries
GET /country/{code}         GET /country/{code}/axes
GET /country/{code}/axis/{n}
GET /axes                   GET /axis/{n}
GET /isi                    GET /scenario (405)
GET /scenario/schema
```

All existing endpoints return **identical response schemas**. They implicitly serve the latest year × latest methodology. Zero change to any existing consumer.

### 9.4 Simulation Compatibility Summary

| Concern | Resolution |
|---------|-----------|
| Existing `POST /scenario` without `year` | Defaults to latest year. Behavior identical to v1. |
| `year=2021` simulation request | Loads 2021 baseline from snapshot. Uses v1.0 thresholds. |
| `methodology=v1.0` explicit | Loads v1.0 classification thresholds + aggregation formula. |
| Mutation of historical data | Impossible. `simulate()` is a pure function with zero write access. |
| Methodology-version mismatch | If requested `(year, methodology)` snapshot doesn't exist → 404. |
| Ranking correctness per year | `compute_rank()` operates on the year-specific baselines, not cross-year. |

### 9.5 Migration Roadmap

```
Week 1  ─── Methodology registry + 2024 snapshot backfill
Week 2  ─── Historical source data preparation (Axes 1,2,3,5,6)
Week 3  ─── Historical source data preparation (Axis 4 — SIPRI parameterization)
Week 4  ─── 2022 + 2023 snapshot backfill + cache layer extension
Week 5  ─── Time-series endpoint implementation (behind flag)
Week 6  ─── Scenario engine year-awareness + comprehensive testing
Week 7  ─── Production enable (flag on) + monitoring
Week 8  ─── Flag removal + documentation + v2 version bump
```

**Total elapsed:** 8 weeks  
**Total engineering effort:** ~120–160 hours  
**Risk-adjusted estimate:** 10 weeks (accounting for SIPRI window parameterization complexity)

### 9.6 Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Axis 4 (Defense) historical window unavailability** | Medium | High — blocks 2022/2023 defense backfill | Parameterize SIPRI query window early (Week 2). If 2017–2022 data unavailable, mark Axis 4 as `null` for 2022 snapshot and flag incomplete. |
| **Floating-point non-determinism across platforms** | Low | Medium — computation_hash mismatches | Round all scores to 8 decimal places at computation time (already done). Use identical Python version. Hash rounding is part of the methodology spec. |
| **Memory pressure from multi-year cache** | Low | Medium — increased RSS, potential OOM on 512 MB Railway instance | Each year adds ~1 MB of cached JSON. 10 years = 10 MB. Current baseline is ~3 MB. Well within limits. Add `MAX_CACHED_YEARS` env var as safety valve. |
| **Source CSV revision breaking immutability** | Medium | High — retroactive drift | Git-track all CSVs. `computation_hash` detects drift. CI job re-verifies hashes weekly. |
| **Methodology v2.0 requires axis addition or removal** | Low | High — schema change, all consumers affected | `methodology_registry.num_axes` supports variable axis count. `axis_score` table is normalized. Schema handles it. API versioning (v01 → v02) provides escape hatch. |
| **Frontend breaks on new meta fields** | Very Low | Low — additive fields only | Frontend ignores unknown JSON keys (standard practice). New fields in `MetaBlock` are additive. Zero breaking change. |
| **Backfill produces different scores than expected** | Medium | Medium — data quality concern | This is not a bug — it means the 2022 structural reality was different from 2024. Document the expected divergence. Classification changes across years are features, not errors. |

### 9.7 Recommended Implementation Order

```
Priority 1 (Foundation — must be done first):
  1. Methodology registry (registry.json + loader)
  2. Exporter parameterization (--year, --methodology)
  3. 2024 snapshot backfill + hash verification

Priority 2 (Data — unblocks time series):
  4. Year-specific CSV preparation (Axes 1,2,3,5,6)
  5. SIPRI window parameterization (Axis 4)
  6. 2022 + 2023 backfill

Priority 3 (API — user-facing):
  7. Cache layer extension (year/methodology-keyed)
  8. Time-series endpoints (behind flag)
  9. Trend computation logic

Priority 4 (Scenario — highest complexity):
  10. ScenarioRequest year/methodology extension
  11. Year-specific baseline loading in API handler
  12. Scenario invariant tests for year-specific behavior

Priority 5 (Launch):
  13. Feature flag enable in production
  14. Monitoring + validation
  15. Flag removal + version bump
```

---

## Appendix A: Constants Reference

| Constant | Value | Source |
|----------|-------|--------|
| `NUM_AXES` | 6 | `scenario.py`, `export_isi_backend_v01.py` |
| `MAX_ADJUSTMENT` | 0.20 | `scenario.py` |
| `CLASSIFICATION_THRESHOLDS` | `[(0.50, "highly"), (0.25, "moderately"), (0.15, "mildly")]` | `scenario.py`, `export_isi_backend_v01.py` |
| `COMPOSITE_FORMULA` | `ISI_i = (A1 + A2 + A3 + A4 + A5 + A6) / 6` | Both |
| `EU27_CODES` | 27 countries | Both |
| `SCENARIO_VERSION` | `"scenario-v1"` | `scenario.py` |
| `VERSION` | `"v0.1"` | `export_isi_backend_v01.py` |
| `WINDOW` | `"2022–2024"` | `export_isi_backend_v01.py` |

## Appendix B: File Inventory Affected by Migration

| File | Change Type | Description |
|------|------------|-------------|
| `backend/export_isi_backend_v01.py` | **Major** | Add `--year`, `--methodology` CLI args. Output to `snapshots/{version}/{year}/`. Compute + store `computation_hash`. |
| `backend/scenario.py` | **Minor** | Add optional `year`/`methodology` to `ScenarioRequest` and `MetaBlock`. `simulate()` unchanged. |
| `backend/isi_api_v01.py` | **Major** | Year-keyed cache. New time-series endpoints. Scenario handler resolves year/methodology. Feature flags. |
| `backend/security.py` | **None** | No changes. Middleware applies uniformly. |
| `backend/v01/` | **None** | Retained as-is. Backward compatibility. |
| `backend/snapshots/` | **New** | Year × methodology snapshot directories. |
| `tests/test_scenario.py` | **Extension** | Add year-specific scenario tests. Existing 74 tests unchanged. |
| `tests/test_time_series.py` | **New** | Time-series endpoint tests. |
| `tests/test_methodology.py` | **New** | Methodology registry + hash verification tests. |

---

*End of document.*
