# ISI Backend Structure — Complete Cartography

> **Generated**: Audit-grade hardening pass (Tasks 2.1–2.9) +
> External Validation & Benchmark Integration pass +
> Final Adversarial Hardening pass +
> Institutionalization pass +
> Final Error/Problem Audit pass.
> **Updated**: Final Error/Problem Audit — all counts verified against code.
> **Scope**: Every file, its role, its dependencies, and its position
> in the execution and governance architecture.
>
> **If this document disagrees with the code, the code is authoritative.**

---

## 1. Repository Layout

```
Panargus-isi/
├── backend/                      # Score computation, governance, export, API
│   ├── __init__.py               # Empty — package marker
│   ├── constants.py              # (121 lines) Canonical constants — single source of truth
│   ├── axis_result.py            # (803 lines) AxisResult/CompositeResult data classes + composite computation
│   ├── severity.py               # (1598 lines) Severity scoring, comparability, sensitivity analysis
│   ├── governance.py             # (919 lines) Governance tier rules, confidence, export gating
│   ├── calibration.py            # (2848 lines) Threshold registry, falsifiability, sensitivity, eligibility metadata (SUPPLEMENTARY — see eligibility.py)
│   ├── eligibility.py            # (2485 lines) AUTHORITATIVE eligibility + readiness + decision usability + empirical alignment + policy usability
│   ├── threshold_registry.py     # (1154 lines) Machine-readable threshold justification registry (27 thresholds)
│   ├── falsification.py          # (~540 lines) External contradiction testing — structural falsification engine
│   ├── benchmark_registry.py     # (872 lines) External benchmark definitions — 11 benchmarks across 6 axes
│   ├── external_validation.py    # (1078 lines) Alignment engine — compares ISI vs external benchmarks
│   ├── invariants.py             # (1611 lines) 28 structural invariants across 8 types (CROSS_AXIS, GOVERNANCE, TEMPORAL, EXTERNAL_VALIDITY, CONSTRUCT_ENFORCEMENT, FAILURE_VISIBILITY, AUTHORITY_CONSISTENCY, REALITY_CONFLICT)
│   ├── construct_enforcement.py  # (439 lines) Construct validity enforcement — degrades/excludes invalid constructs from composite
│   ├── benchmark_mapping_audit.py # (769 lines) Formal mapping audit for all 11 benchmarks — VALID/WEAK/INVALID classification
│   ├── alignment_sensitivity.py  # (546 lines) Alignment robustness testing — leave-one-out, noise, shift, aggregation swap
│   ├── failure_visibility.py     # (662 lines) Anti-bullshit layer — visibility flags, trust levels, usability hardening
│   ├── provenance.py             # (580 lines) Computation provenance tracking
│   ├── reality_conflicts.py      # (650 lines) Reality conflict detection — governance vs alignment contradictions
│   ├── snapshot_diff.py          # (992 lines) Snapshot difference computation + policy impact assessment
│   ├── methodology.py            # (305 lines) Methodology version registry + classification
│   ├── export_snapshot.py        # (1317 lines) JSON snapshot materialization + hashing (full pipeline: falsification, decision usability, external validation, construct enforcement, alignment sensitivity, failure visibility, reality conflicts, invariants)
│   ├── isi_api_v01.py            # (1503 lines) FastAPI serving layer — 17 REST endpoints
│   ├── scenario.py               # (391 lines) What-if scenario simulation engine
│   ├── scope.py                  # (233 lines) Country/axis scope management
│   ├── hardening.py              # (105 lines) Input validation utilities (path, float, JSON)
│   ├── hashing.py                # (124 lines) Deterministic canonical hashing
│   ├── signing.py                # (312 lines) Ed25519 snapshot signing/verification
│   ├── security.py               # (323 lines) Security hardening (CORS, rate-limit, headers)
│   ├── immutability.py           # (76 lines) Immutability enforcement for snapshots
│   ├── log_sanitizer.py          # (72 lines) PII/secret scrubbing for logs
│   ├── snapshot_integrity.py     # (703 lines) Snapshot hash-chain + Merkle tree integrity
│   ├── snapshot_cache.py         # (361 lines) In-memory snapshot caching layer
│   ├── snapshot_resolver.py      # (287 lines) Multi-version snapshot resolution
│   ├── reproduce_snapshot.py     # (235 lines) Reproducibility verification
│   ├── verify_snapshot.py        # (134 lines) CLI snapshot verification tool
│   ├── config/
│   │   └── public_keys.json      # Ed25519 public keys for signature verification
│   ├── snapshots/
│   │   ├── registry.json         # Snapshot version registry
│   │   └── v1.0/                 # Materialized snapshot artifacts
│   └── v01/                      # Frozen v01 snapshot JSON files
│       ├── MANIFEST.json         # Snapshot manifest with hashes
│       ├── meta.json             # Snapshot metadata
│       ├── isi.json              # ISI composite ranking
│       ├── countries.json        # Country list
│       ├── axes.json             # Axis list
│       ├── axis/                 # Per-axis JSON (1.json – 6.json)
│       └── country/              # Per-country JSON (AT.json – SK.json)
│
├── pipeline/                     # Data ingestion, validation, orchestration
│   ├── __init__.py               # (34 lines) Package init
│   ├── config.py                 # (596 lines) AXIS_REGISTRY, HS code mappings, paths
│   ├── orchestrator.py           # (426 lines) Pipeline orchestration — ingest → validate → export
│   ├── validate.py               # (842 lines) Data validation rules per axis
│   ├── normalize.py              # (371 lines) Score normalization (min-max, z-score, etc.)
│   ├── schema.py                 # (308 lines) Data schema definitions + validation
│   ├── rebuild.py                # (255 lines) Full pipeline rebuild from raw data
│   ├── status.py                 # (98 lines) Pipeline status tracking
│   └── ingest/                   # Per-source ingestion modules
│       ├── __init__.py           # (16 lines) Package init
│       ├── bis_lbs.py            # (403 lines) BIS Locational Banking Statistics ingestion
│       ├── imf_cpis.py           # (344 lines) IMF CPIS portfolio investment ingestion
│       ├── comtrade.py           # (651 lines) UN Comtrade bilateral trade ingestion
│       ├── sipri.py              # (627 lines) SIPRI arms transfers ingestion
│       └── logistics.py          # (451 lines) Eurostat bilateral logistics ingestion
│
├── tests/                        # 1715 tests (22 test files)
│   ├── test_institutional_upgrade.py  # (82 tests) 4-layer institutional upgrade: threshold registry, falsification, decision usability, authority unification
│   ├── test_eligibility_hardening.py  # (104 tests) Eligibility + readiness registry
│   ├── test_external_validation.py    # (100 tests) External validation + benchmark registry + alignment engine + construct validity
│   ├── test_empirical_alignment.py    # (38 tests) Empirical alignment dimension + policy usability classification + export integration
│   ├── test_final_hardening.py        # (102 tests) Final adversarial hardening: construct enforcement, mapping audit, alignment sensitivity, policy impact, failure visibility, CE-INV invariants
│   ├── test_systems_hardening.py      # Systems hardening: invariants, provenance, snapshot diff
│   ├── test_ingestion_pipeline.py     # Ingestion pipeline tests
│   ├── test_elevation.py              # Elevation/governance tests
│   ├── test_correctness_hardening.py  # Correctness invariants
│   ├── test_calibration_falsifiability.py  # Calibration + falsifiability
│   ├── test_institutional_governance.py    # Institutional governance rules
│   ├── test_sipri_ingestion.py        # SIPRI-specific ingestion tests
│   ├── test_institutional_hardening.py # Institutional hardening
│   ├── test_scenario.py              # Scenario simulation tests
│   ├── test_nsa_finish.py            # NSA finish/completion tests
│   ├── test_methodological_hardening.py # Methodological hardening
│   ├── test_crypto_auth.py           # Cryptographic authentication tests
│   ├── test_hardening.py             # General hardening tests
│   ├── test_serving_layer.py         # API serving layer tests
│   ├── test_trust_hardening.py       # Trust model tests
│   ├── test_axis_result.py           # AxisResult/CompositeResult tests
│   └── test_scope.py                 # Scope management tests
│
├── scripts/
│   ├── generate_manifest.py     # (96 lines) Snapshot manifest generator
│   └── smoke_test.py            # (174 lines) End-to-end smoke test
│
├── docs/                        # Documentation
│   ├── THEORETICAL_READINESS.md # Eligibility + readiness documentation
│   ├── BACKEND_STRUCTURE.md     # This document
│   ├── THRESHOLD_JUSTIFICATION.md # Machine-readable threshold justification registry (Layer 1)
│   ├── FALSIFICATION_FRAMEWORK.md # External contradiction testing framework (Layer 2)
│   ├── AUTHORITY_UNIFICATION.md   # Single source of truth — authority hierarchy (Layer 4)
│   ├── AGENT_RULES.md             # Agent-facing codebase rules and constraints
│   ├── ISI_METHODOLOGY_SPECIFICATION.md
│   ├── ISI_V01_SPECIFICATION.md
│   ├── ISI_CONSTRAINT_SPECIFICATION.md
│   ├── GOVERNANCE_MODEL.md
│   ├── CALIBRATION_AND_FALSIFIABILITY.md
│   ├── CORRECTNESS_GUARANTEES.md
│   ├── PIPELINE_ARCHITECTURE.md
│   ├── SECURITY_MODEL.md
│   ├── LIMITATIONS.md
│   ├── ISI_HARDENED_INFRASTRUCTURE_BLUEPRINT.md
│   ├── MATH_CONSISTENCY_REPORT.md
│   ├── METHODOLOGY_EVIDENCE_PACK.md
│   ├── GLOBAL_EXPANSION_FEASIBILITY_ASSESSMENT.md
│   ├── TIME_DIMENSION_V2_ARCHITECTURE.md
│   ├── api/
│   │   ├── isi_api_contract_v01.md   # API contract specification
│   │   └── openapi_v01.json          # OpenAPI spec
│   ├── audit/                         # Per-axis audit reports + known gaps
│   ├── methodology/                   # Per-axis methodology documents (17 files)
│   └── mappings/                      # HS code mapping CSVs
│
├── data/                        # Data directories (not code)
│   ├── raw/                     # Raw source data (BIS, CPIS, Comtrade, SIPRI, Eurostat)
│   ├── staging/                 # Intermediate processing
│   ├── validated/               # Post-validation data
│   ├── processed/               # Final processed scores
│   ├── scopes/                  # Scope definitions
│   ├── meta/                    # Metadata
│   └── audit/                   # Audit artifacts
│
├── ISI_Paper/                   # Academic paper assets
├── _archive/                    # Archived/deprecated files
├── .github/                     # GitHub Actions CI
├── Dockerfile                   # Container build
├── Makefile                     # Build automation
├── pyproject.toml               # Python project config
├── requirements.txt             # Production dependencies
├── requirements-dev.txt         # Development dependencies
├── VERSION                      # Version file
└── README.md                    # Project README
```

## 2. File-by-File Role Classification

### 2.1 Core Computation Layer

| File | Role | Key Exports | Lines |
|------|------|-------------|-------|
| `backend/constants.py` | **Canonical constants** — ROUND_PRECISION, NUM_AXES, EU27_CODES, AXIS_WEIGHTS, valid_country_code() | All shared constants | 121 |
| `backend/axis_result.py` | **Data classes** — AxisResult (per-country per-axis), CompositeResult (per-country composite), compute_composite_v11() | AxisResult, CompositeResult, compute_composite_v11 | 803 |
| `backend/methodology.py` | **Methodology registry** — version-pinned classification bands, composite formula, thresholds | get_methodology, classify, compute_composite | 305 |
| `backend/severity.py` | **Severity engine** — data quality severity scoring, comparability tiering, sensitivity analysis, stability, shock simulation | compute_axis_severity, assign_comparability_tier, compute_adjusted_composite, compute_sensitivity_analysis | 1598 |

### 2.2 Governance & Validation Layer

| File | Role | Key Exports | Lines |
|------|------|-------------|-------|
| `backend/governance.py` | **Governance model** — axis confidence assessment, governance tier determination, ranking eligibility, export gating, truthfulness contract | assess_axis_confidence, assess_country_governance, gate_export, enforce_truthfulness_contract | 919 |
| `backend/calibration.py` | **Calibration registry** — 100+ threshold entries with CalibrationClass tags, falsifiability registry, circularity audit, sensitivity analysis, country eligibility metadata (SUPPLEMENTARY) | get_threshold_registry, get_falsifiability_registry, get_circularity_audit, run_sensitivity_analysis | 2848 |
| `backend/eligibility.py` | **Eligibility model** — theoretical country classification, 4-question hierarchy, axis-by-country readiness, construct substitution, decision usability, empirical alignment, policy usability | classify_country, classify_decision_usability, classify_empirical_alignment, classify_policy_usability, build_axis_readiness_matrix, can_compile/rate/rank/compare | 2485 |
| `backend/benchmark_registry.py` | **Benchmark registry** — 11 external benchmark definitions across 6 axes with comparison types, alignment thresholds, integration status, BenchmarkAuthority hierarchy | get_benchmark_registry, get_benchmarks_for_axis, get_benchmark_by_id, AlignmentClass, ComparisonType | 872 |
| `backend/external_validation.py` | **Alignment engine** — compares ISI output against external benchmarks, produces per-axis and overall alignment assessments, weighted alignment with authority hierarchy | compare_to_benchmark, assess_country_alignment, build_external_validation_block | 1078 |
| `backend/invariants.py` | **Invariant system** — 28 structural invariants across 8 types (CROSS_AXIS, GOVERNANCE, TEMPORAL, EXTERNAL_VALIDITY, CONSTRUCT_ENFORCEMENT, FAILURE_VISIBILITY, AUTHORITY_CONSISTENCY, REALITY_CONFLICT), violation detection, severity classification | assess_country_invariants, check_external_validity_invariants, INVARIANT_REGISTRY | 1611 |
| `backend/falsification.py` | **Falsification engine** — structural contradiction testing against known economic facts | assess_country_falsification, STRUCTURAL_FACTS, BENCHMARK_REGISTRY | ~540 |
| `backend/provenance.py` | **Provenance tracking** — computation trace recording and audit trail | provenance tracking utilities | 580 |
| `backend/reality_conflicts.py` | **Reality conflict detection** — governance vs alignment contradictions, structural entries not flags | detect_reality_conflicts, detect_governance_alignment_mismatch | 650 |
| `backend/construct_enforcement.py` | **Construct enforcement** — degrades/excludes invalid constructs, weight adjustment for composite | enforce_all_axes, enforce_construct_validity, should_exclude_from_ranking | 438 |
| `backend/benchmark_mapping_audit.py` | **Mapping audit** — formal validity classification for benchmark-to-ISI mappings | validate_benchmark_mapping, should_downgrade_alignment | 769 |
| `backend/alignment_sensitivity.py` | **Alignment sensitivity** — robustness testing (leave-one-out, noise, shift) | run_alignment_sensitivity, should_downgrade_for_instability | 545 |
| `backend/failure_visibility.py` | **Anti-bullshit layer** — aggregates ALL flags into unified visibility block with trust levels | build_visibility_block, collect_validity_warnings | 662 |
| `backend/snapshot_diff.py` | **Snapshot diffing** — structural comparison between snapshot versions, tracks governance/visibility/enforcement/sensitivity changes | diff_country, compare_snapshots | 992 |

### 2.3 Export & Serving Layer

| File | Role | Key Exports | Lines |
|------|------|-------------|-------|
| `backend/export_snapshot.py` | **Snapshot materialization** — builds isi.json, country/*.json, axis/*.json; integrates ALL layers (governance, falsification, decision usability, external validation, construct enforcement, alignment sensitivity, failure visibility, reality conflicts, invariants); computes hashes; makes snapshots read-only | build_isi_json, build_country_json, build_axis_json, materialize_snapshot | 1317 |
| `backend/isi_api_v01.py` | **REST API** — FastAPI app with 17 endpoints; serves frozen snapshots; scenario simulation; methodology versioning | app (FastAPI), all endpoint handlers | 1503 |
| `backend/scenario.py` | **Scenario engine** — what-if simulation for supplier removal/shift | ScenarioRequest, ScenarioResponse, simulate | 391 |
| `backend/scope.py` | **Scope management** — country and axis scope definitions for selective computation | scope-related utilities | 233 |

### 2.4 Integrity & Security Layer

| File | Role | Key Exports | Lines |
|------|------|-------------|-------|
| `backend/hashing.py` | **Canonical hashing** — deterministic SHA-256 for JSON objects | canonical_hash, hash_json | 124 |
| `backend/signing.py` | **Cryptographic signing** — Ed25519 signature generation/verification | sign_snapshot, verify_signature | 312 |
| `backend/security.py` | **Security hardening** — CORS, rate limiting, security headers, request validation | configure_security (applied to FastAPI app) | 323 |
| `backend/hardening.py` | **Input validation** — path safety, float safety, JSON float validation | validate_path_length, is_safe_float, validate_json_floats | 105 |
| `backend/immutability.py` | **Immutability** — prevents modification of frozen snapshots | immutability enforcement | 76 |
| `backend/log_sanitizer.py` | **Log safety** — PII/secret scrubbing | sanitize log output | 72 |
| `backend/snapshot_integrity.py` | **Hash-chain integrity** — Merkle tree verification for snapshots | verify_snapshot_integrity | 703 |
| `backend/snapshot_cache.py` | **Caching** — in-memory snapshot cache with LRU-like management | snapshot_cache utilities | 361 |
| `backend/snapshot_resolver.py` | **Version resolution** — resolves snapshot versions from registry | resolve_snapshot | 287 |
| `backend/reproduce_snapshot.py` | **Reproducibility** — verifies that a snapshot can be reproduced from inputs | verify_reproducibility | 235 |
| `backend/verify_snapshot.py` | **CLI verification** — command-line snapshot verification tool | CLI entry point | 134 |

### 2.5 Pipeline Layer

| File | Role | Key Exports | Lines |
|------|------|-------------|-------|
| `pipeline/config.py` | **Pipeline configuration** — AXIS_REGISTRY (6 axes with full metadata), HS code mappings, paths | AXIS_REGISTRY, AXIS_SLUGS, paths | 596 |
| `pipeline/orchestrator.py` | **Orchestration** — drives ingest → validate → normalize → export; AXIS_INGEST_MAP routes axes to ingest modules | run_pipeline, ingest_one, export_dataset | 426 |
| `pipeline/validate.py` | **Validation** — per-axis data quality checks, flag generation | validation rules | 842 |
| `pipeline/normalize.py` | **Normalization** — min-max, z-score, rank-based normalization | normalization functions | 371 |
| `pipeline/schema.py` | **Schema** — data schema definitions for each pipeline stage | schema definitions | 308 |
| `pipeline/rebuild.py` | **Rebuild** — full pipeline rebuild from raw source data | rebuild_all | 255 |
| `pipeline/status.py` | **Status** — pipeline progress tracking | status utilities | 98 |

### 2.6 Ingest Modules

| File | Source | Axes Fed | Lines |
|------|--------|----------|-------|
| `pipeline/ingest/bis_lbs.py` | BIS Locational Banking Statistics | Axis 1 (financial) | 403 |
| `pipeline/ingest/imf_cpis.py` | IMF Coordinated Portfolio Investment Survey | Axis 1 (financial) | 344 |
| `pipeline/ingest/comtrade.py` | UN Comtrade bilateral trade | Axes 2, 3, 5 (energy, technology, critical inputs) | 651 |
| `pipeline/ingest/sipri.py` | SIPRI Arms Transfers Database | Axis 4 (defense) | 627 |
| `pipeline/ingest/logistics.py` | Eurostat bilateral logistics (EU-27 only) | Axis 6 (logistics) | 451 |

## 3. Execution Flow

### 3.1 Pipeline Execution (Data Processing)

```
raw data files
    │
    ▼
pipeline/orchestrator.py::run_pipeline()
    │
    ├──→ pipeline/ingest/bis_lbs.py      ─→ axis 1 (financial)
    ├──→ pipeline/ingest/imf_cpis.py     ─→ axis 1 (financial)
    ├──→ pipeline/ingest/comtrade.py     ─→ axes 2, 3, 5
    ├──→ pipeline/ingest/sipri.py        ─→ axis 4 (defense)
    └──→ pipeline/ingest/logistics.py    ─→ axis 6 (logistics)
           │
           ▼
    pipeline/validate.py                 (data quality checks + flag generation)
           │
           ▼
    pipeline/normalize.py                (score normalization)
           │
           ▼
    backend/axis_result.py               (AxisResult construction)
           │
           ▼
    backend/severity.py                  (severity scoring per axis/country)
           │
           ▼
    backend/axis_result.py::compute_composite_v11()  (composite ISI score)
           │
           ▼
    backend/governance.py                (governance tier + confidence + gating)
           │
           ▼
    backend/eligibility.py               (decision usability + readiness matrix + empirical alignment)
           │
           ▼
    backend/export_snapshot.py           (JSON materialization — full pipeline below)
           │
           ├──→ falsification            (structural contradiction testing)
           ├──→ decision_usability       (usability classification)
           ├──→ external_validation      (alignment with external benchmarks)
           ├──→ construct_enforcement    (construct validity per axis)
           ├──→ benchmark_mapping_audit  (mapping validity classification)
           ├──→ alignment_sensitivity    (robustness testing)
           ├──→ empirical_alignment      (empirical grounding classification)
           ├──→ invariant_assessment     (28 structural invariant checks)
           ├──→ failure_visibility       (anti-bullshit layer — receives ALL upstream data)
           └──→ reality_conflicts        (governance vs alignment contradictions)
           │
           ▼
    backend/v01/ (frozen snapshot)
```

### 3.2 API Serving (Runtime)

```
HTTP request
    │
    ▼
backend/isi_api_v01.py (FastAPI)
    │
    ├──→ backend/security.py             (CORS, rate limit, headers)
    ├──→ backend/snapshot_resolver.py     (version resolution)
    ├──→ backend/snapshot_cache.py        (cache lookup)
    ├──→ backend/v01/*.json              (frozen snapshot data)
    ├──→ backend/scenario.py             (POST /scenario)
    ├──→ backend/methodology.py          (GET /methodology/versions)
    └──→ backend/governance.py           (governance metadata in responses)
```

### 3.3 Eligibility Assessment (Static Analysis)

```
backend/eligibility.py::classify_country(code)
    │
    ├──→ can_compile()
    │       └──→ build_axis_readiness_matrix()
    │               └──→ _assess_axis_readiness() × 6  [per-axis]
    │                       ├──→ BIS_REPORTERS / CPIS_PARTICIPANTS  (axis 1)
    │                       ├──→ COMTRADE_REPORTERS                 (axes 2,3,5)
    │                       ├──→ SIPRI_LIKELY_IMPORTERS              (axis 4)
    │                       ├──→ EUROSTAT_LOGISTICS_COUNTRIES         (axis 6)
    │                       ├──→ PRODUCER_INVERSION_REGISTRY         (cross-axis)
    │                       └──→ SANCTIONS_DISTORTED                 (cross-axis)
    │
    ├──→ can_rate()
    │       └──→ _simulate_governance()
    │               └──→ governance.assess_country_governance()
    │
    ├──→ can_rank()
    │       └──→ _simulate_governance()
    │
    └──→ can_compare()
            └──→ _simulate_governance()
```

## 4. Data Dependency Graph (DAG)

### Upstream Constants

```
backend/constants.py
    │
    ├──→ backend/governance.py       (EU27_CODES, NUM_AXES, ROUND_PRECISION)
    ├──→ backend/eligibility.py      (EU27_CODES, NUM_AXES)
    ├──→ backend/axis_result.py      (NUM_AXES, ROUND_PRECISION, AXIS_WEIGHTS)
    ├──→ backend/severity.py         (ROUND_PRECISION, constants)
    ├──→ backend/calibration.py      (thresholds reference governance constants)
    ├──→ backend/export_snapshot.py  (constants for export)
    └──→ pipeline/config.py          (AXIS_REGISTRY uses axis count)
```

### Module Dependency Chains

```
constants.py ──→ governance.py ──→ eligibility.py
                      │                 │
                      ▼                 ▼
              severity.py ──→ export_snapshot.py
                      │                 │
                      ▼                 ▼
             axis_result.py      isi_api_v01.py
                      │
                      ▼
              calibration.py
```

### Governance Architecture

```
                   ┌─────────────────────────────────┐
                   │   backend/calibration.py         │
                   │   (threshold registry, classes,  │
                   │    falsifiability, sensitivity)   │
                   └──────────────┬──────────────────┘
                                  │ references thresholds from
                                  ▼
                   ┌─────────────────────────────────┐
                   │   backend/governance.py          │
                   │   (tiers, confidence baselines,  │
                   │    penalties, truthfulness)       │
                   └──────────────┬──────────────────┘
                                  │ used by
                                  ▼
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│ eligibility.py  │  │ export_snapshot.py   │  │ isi_api_v01.py      │
│ (classification │  │ (gate_export,        │  │ (governance fields  │
│  + readiness)   │  │  gov fields in JSON) │  │  in API responses)  │
└─────────────────┘  └─────────────────────┘  └─────────────────────┘
```

## 5. API Endpoints

| Method | Path | Purpose | Schema |
|--------|------|---------|--------|
| GET | `/` | Root — system info + available endpoints | — |
| GET | `/health` | Health check (internal) | — |
| GET | `/ready` | Readiness probe | — |
| GET | `/countries` | List all countries with metadata | — |
| GET | `/country/{code}` | Full country detail with governance | — |
| GET | `/country/{code}/axes` | All axis scores for a country | — |
| GET | `/country/{code}/axis/{axis_id}` | Single axis detail | — |
| GET | `/country/{code}/history` | Historical ISI scores | — |
| GET | `/axes` | List all axes with metadata | — |
| GET | `/axis/{axis_id}` | Axis detail across countries | — |
| GET | `/isi` | Full ISI ranking with governance tiers | — |
| GET | `/scenario` | Scenario simulation info (internal) | — |
| GET | `/scenario/schema` | Scenario request schema | — |
| POST | `/scenario` | What-if scenario simulation | ScenarioRequest → ScenarioResponse |
| GET | `/methodology/versions` | Available methodology versions | — |
| GET | `/_internal/snapshot/verify` | Snapshot integrity verification (internal) | — |

## 6. Governance Tier Architecture

```
FULLY_COMPARABLE      (14 rules in _determine_governance_tier)
    ↑
PARTIALLY_COMPARABLE  (mean_confidence ≥ threshold, ≤ max low axes)
    ↑
LOW_CONFIDENCE        (composite defensible but ranking excluded)
    ↑
NON_COMPARABLE        (sanctions, excessive inversions, insufficient data)
```

Key thresholds (from `governance.py`):
- `AXIS_CONFIDENCE_BASELINES`: 6 per-axis baselines
- `CONFIDENCE_PENALTIES`: 9 penalty types
- `CONFIDENCE_THRESHOLDS`: level boundaries
- `MIN_AXES_FOR_COMPOSITE`: 4
- `MIN_AXES_FOR_RANKING`: 5
- `MIN_MEAN_CONFIDENCE_FOR_RANKING`: 0.45
- `LOGISTICS_PROXY_CONFIDENCE_CAP`: 0.40
- `PRODUCER_INVERSION_REGISTRY`: 8 countries with specific inverted axes
- `MAX_INVERTED_AXES_FOR_COMPARABLE`: comparability boundary

## 7. Structural Notes and Known Confusion Points

### 7.1 Dual Eligibility Registries

`backend/calibration.py` contains an older `EligibilityClass` and
`get_country_eligibility_registry()` (from the calibration hardening pass).
`backend/eligibility.py` contains the newer, audit-grade `TheoreticalEligibility`
and `classify_country()` (from the eligibility hardening pass).

**The authoritative eligibility model is `backend/eligibility.py`.**
The calibration.py version is preserved for backward compatibility and
should be treated as a secondary reference.

### 7.2 Comtrade Powers Three Axes

`pipeline/ingest/comtrade.py` feeds axes 2, 3, AND 5 — each with
different HS code scopes. The construct is different per axis even though
the source is the same. Do not treat these axes as interchangeable.

### 7.3 Axis 6 Construct Substitution

For non-EU countries, axis 6 ("logistics") uses the same Comtrade data
as axes 2/3/5. This is CONSTRUCT SUBSTITUTION — the measurement is
"bilateral trade value" pretending to be "logistics capacity."
See `docs/THEORETICAL_READINESS.md` §4.

### 7.4 Frozen Snapshots Are Read-Only

`backend/v01/` contains the materialized v01 snapshot. These files are
generated by `export_snapshot.py`, signed by `signing.py`, and made
read-only by `immutability.py`. They are NOT edited manually.

### 7.5 Test Coverage Is Comprehensive But Not Exhaustive

1860 tests cover all major invariants, governance rules, eligibility
classifications, API contracts, cryptographic integrity, external
validation alignment, empirical alignment classification, policy
usability derivation, integration wiring, reality conflicts, and
institutionalization. Tests verify both internal consistency AND that
all hardening layers are actually wired into the production export
pipeline (not just tested in isolation). Tests do NOT claim the
benchmarks themselves are correct — they verify that the system's
handling of benchmarks is structurally sound.

## 8. File Count Summary

| Directory | Python Files | Lines of Code | Purpose |
|-----------|-------------|---------------|----------|
| `backend/` | 35 | ~25,100 | Computation + governance + validation + export + API |
| `pipeline/` | 14 | ~5,400 | Ingestion + validation + normalization |
| `pipeline/ingest/` | 6 | ~2,500 | Per-source data ingestion |
| `tests/` | 25 | ~22,500 | 1860 tests |
| `scripts/` | 2 | ~270 | Manifest generation + smoke test |
| **Total** | **76** | **~53,300** | |

## 9. Self-Audit: What This Document Does NOT Cover

- **Runtime configuration**: Environment variables, Docker secrets, deployment config
- **Data file contents**: The actual CSV/JSON data in `data/` directories
- **CI/CD pipeline**: GitHub Actions workflow details (in `.github/`)
- **Academic paper**: Contents of `ISI_Paper/`
- **Archived code**: Contents of `_archive/`
- **External dependencies**: See `requirements.txt` and `requirements-dev.txt`

This document covers the **code architecture** — what each file does,
how they connect, and what the execution and governance flow looks like.
It does NOT claim to be exhaustive about every helper function or constant.
For function-level detail, read the source files directly.
