# Systems Hardening Layer — Technical Documentation

## Overview

The final backend hardening layer adds three interconnected systems that answer four fundamental questions about ISI outputs:

1. **"Is this result internally consistent?"** → SYSTEM 1 (Invariants)
2. **"Where did this number come from?"** → SYSTEM 2 (Provenance)
3. **"Why did this country move in rank?"** → SYSTEM 3 (Snapshot Diff)
4. **"What exactly changed between versions?"** → SYSTEM 3 (Snapshot Diff)

These are **audit infrastructure** — they do not modify scores.

---

## SYSTEM 1: Structural Invariants Engine

**Module:** `backend/invariants.py`

### Purpose

Detects when the system produces internally inconsistent outputs, even when all individual computations are technically correct. Invariants verify *structural coherence*, not empirical correctness.

### Invariant Classes

| Type | Prefix | Count | Description |
|------|--------|-------|-------------|
| `CROSS_AXIS` | CA- | 4 | Logical contradictions across axes |
| `GOVERNANCE` | GOV- | 6 | Governance output consistency |
| `TEMPORAL` | TEMP- | 3 | Cross-version snapshot consistency |

### Severity Levels

| Level | Meaning | Action |
|-------|---------|--------|
| `WARNING` | Structurally unusual but not contradictory | Logged, no action |
| `ERROR` | Structural anomaly requiring attention | Flagged in export |
| `CRITICAL` | Internal contradiction | **Auto-downgrades DecisionUsabilityClass** |

### Cross-Axis Invariants

- **CA-001**: Logistics divergence from goods-based axes (logistics ↑ while goods ↓)
- **CA-002**: Producer country high-import anomaly (inverted axis with high dependency score)
- **CA-003**: Low axis majority with high composite (4+ axes < 0.15 but composite > 0.25)
- **CA-004**: Uniform score anomaly (all 6 axes within 0.02 — structurally improbable)

### Governance Consistency Invariants

- **GOV-001**: `ranking_eligible=True` but tier ≠ FULLY/PARTIALLY_COMPARABLE → CRITICAL
- **GOV-002**: `cross_country_comparable=True` with excessive inversions → CRITICAL
- **GOV-003**: LOW_CONFIDENCE/NON_COMPARABLE but `ranking_eligible=True` → CRITICAL
- **GOV-004**: `composite_defensible=True` with NON_COMPARABLE → CRITICAL
- **GOV-005**: FULLY_COMPARABLE but mean confidence below threshold → ERROR
- **GOV-006**: SANCTIONS_DISTORTION flag but high governance tier → CRITICAL

### Temporal Invariants

- **TEMP-001**: Rank shift > 5 without axis score change > 0.05 → ERROR
- **TEMP-002**: Composite change > 0.02 without any axis change > 0.01 → CRITICAL
- **TEMP-003**: Governance tier change without structural cause → ERROR

### Key Functions

```python
assess_country_invariants(country, axis_scores, governance_result, ...) → dict
assess_all_invariants(all_scores, governance_results, ...) → dict[str, dict]
get_invariant_summary(invariant_results) → dict
should_downgrade_usability(invariant_result) → bool
```

### Honesty Note

Invariant checks verify **internal consistency only**. Zero violations does NOT mean outputs are correct — it means they are structurally coherent.

---

## SYSTEM 2: Full Provenance Trace System

**Module:** `backend/provenance.py`

### Purpose

Every exported value must be traceable to its source data, transformation chain, rules applied, thresholds used, and adjustments made. Provenance traces WHERE a number came from, not WHETHER it is correct.

### Provenance Record Structure

```json
{
  "source_data": {"file": "...", "axis": 1, "year": 2024},
  "transformation_chain": [
    {"step": "RAW_INGEST", "module": "backend.export_snapshot", "function": "load_axis_scores"},
    {"step": "SCORE_NORMALIZATION", "module": "backend.methodology", "function": "classify"},
    {"step": "SEVERITY_ASSESSMENT", "module": "backend.severity", "function": "compute_axis_severity"}
  ],
  "rules_applied": ["SEVERITY_FLAG:SINGLE_CHANNEL_A", "GOV_PENALTY:PRODUCER_INVERSION"],
  "thresholds_used": ["CONFIDENCE_PENALTIES:PRODUCER_INVERSION"],
  "adjustments": [{"type": "confidence_penalty", "flag": "PRODUCER_INVERSION", "amount": -0.30}]
}
```

### Transformation Types

| Step | Description |
|------|-------------|
| `RAW_INGEST` | Data loaded from CSV |
| `SCORE_NORMALIZATION` | Methodology-specific score processing |
| `SEVERITY_ASSESSMENT` | Degradation flags assessed |
| `GOVERNANCE_ASSESSMENT` | Governance tier determination |
| `CONFIDENCE_PENALTY` | Axis confidence reduction |
| `PRODUCER_INVERSION` | Producer-inversion flag applied |
| `FALSIFICATION_CHECK` | Structural falsification assessment |
| `ELIGIBILITY_CLASSIFICATION` | Theoretical eligibility |
| `USABILITY_CLASSIFICATION` | Decision usability class |
| `COMPOSITE_COMPUTATION` | ISI composite aggregation |
| `INVARIANT_CHECK` | System 1 invariant check |
| `EXPORT_MATERIALIZATION` | Final export to JSON |

### Key Functions

```python
build_axis_provenance(country, axis_id, score, year, ...) → dict
build_composite_provenance(country, composite_score, axis_scores, ...) → dict
build_governance_provenance(country, governance_result) → dict
build_usability_provenance(country, usability_class, ...) → dict
build_country_provenance(country, ...) → dict  # Full bundle
validate_provenance(provenance) → dict  # Structural validation
```

### Design Properties

- **Deterministic**: Same inputs → same provenance trace
- **Machine-readable**: Structured JSON, parseable by auditors
- **Reconstructable**: From provenance, the computation can be replayed
- **Complete**: 6 axis traces + 1 composite trace + governance + usability per country

---

## SYSTEM 3: Snapshot Differential Analysis

**Module:** `backend/snapshot_diff.py`

### Purpose

Compares two materialized snapshots to produce per-country composite, rank, governance, and usability deltas with root cause analysis and change classification.

### Change Classification

| Type | Description |
|------|-------------|
| `DATA_CHANGE` | Input axis scores changed |
| `METHODOLOGY_CHANGE` | Methodology version or aggregation rules changed |
| `THRESHOLD_CHANGE` | Governance/severity thresholds changed |
| `GOVERNANCE_CHANGE` | Governance tier changed |
| `BUG_FIX` | Explicitly labeled correction |
| `NO_CHANGE` | No detectable difference |

### Per-Country Diff Output

```json
{
  "country": "DE",
  "status": "CHANGED",
  "change_types": ["DATA_CHANGE"],
  "composite_delta": 0.08,
  "rank_delta": -3,
  "governance_change": {"from": "FULLY_COMPARABLE", "to": "FULLY_COMPARABLE", "changed": false},
  "usability_change": {"from": "TRUSTED_COMPARABLE", "to": "TRUSTED_COMPARABLE", "changed": false},
  "axis_deltas": {
    "1": {"score_a": 0.35, "score_b": 0.43, "delta": 0.08, "abs_delta": 0.08}
  },
  "root_causes": ["Axis 1 score changed by +0.08000000"]
}
```

### Global Summary

```json
{
  "n_total_countries": 27,
  "n_changed": 12,
  "n_unchanged": 15,
  "pct_changed": 44.44,
  "methodology_changed": false,
  "rank_movement": {"avg_abs_rank_movement": 2.3, "max_abs_rank_movement": 7},
  "composite_movement": {"avg_abs_composite_delta": 0.045}
}
```

### API Endpoint

```
GET /diff/{version_a}/{version_b}?methodology=v1.0
```

- `version_a`, `version_b`: Integer years
- `methodology`: Optional, defaults to latest

### Key Functions

```python
diff_country(country, isi_entry_a, isi_entry_b, ...) → dict
compare_snapshots(snapshot_a, snapshot_b, ...) → dict
compare_snapshots_from_paths(path_a, path_b) → dict  # Filesystem-based
get_diff_summary_text(diff_result) → str  # Human-readable
```

### Honesty Note

Diffs show WHAT changed and classify change types **structurally**. Root cause attribution is structural, not causal — we can say "score changed" but not "why the underlying economic reality changed."

---

## Cross-System Integration

### Invariant → Usability Downgrade

When `assess_country_invariants()` produces CRITICAL violations, `should_downgrade_usability()` returns `True`. The export pipeline uses this to downgrade `DecisionUsabilityClass` before materialization.

### Invariant → Provenance

Invariant-triggered downgrades are recorded in provenance traces via `INVARIANT_CHECK` transformation steps and `INVARIANT_DOWNGRADE` rules.

### Diff → Invariants (Temporal)

Temporal invariants (TEMP-001 through TEMP-003) operate on pairs of country snapshots, detecting suspicious changes between versions. These can be checked at diff time.

---

## Test Coverage

**Test file:** `tests/test_systems_hardening.py`  
**Test count:** 98 tests  
**Total suite:** 1475 tests (1377 baseline + 98 new)

| Test Class | Count | System |
|------------|-------|--------|
| `TestInvariantRegistry` | 6 | S1 |
| `TestCrossAxisInvariants` | 12 | S1 |
| `TestGovernanceInvariants` | 10 | S1 |
| `TestTemporalInvariants` | 7 | S1 |
| `TestUnifiedInvariantAssessment` | 6 | S1 |
| `TestTransformationTypes` | 2 | S2 |
| `TestAxisProvenance` | 5 | S2 |
| `TestCompositeProvenance` | 4 | S2 |
| `TestGovernanceProvenance` | 1 | S2 |
| `TestUsabilityProvenance` | 2 | S2 |
| `TestCountryProvenance` | 2 | S2 |
| `TestProvenanceValidation` | 3 | S2 |
| `TestChangeType` | 2 | S3 |
| `TestDiffCountry` | 10 | S3 |
| `TestCompareSnapshots` | 6 | S3 |
| `TestDiffSummaryText` | 1 | S3 |
| `TestIsiCountryMap` | 4 | S3 |
| Cross-system integration | 5 | S1+S2+S3 |
| Adversarial/edge cases | 7 | All |
| Determinism | 3 | All |

---

## Files Modified/Created

| File | Action | System |
|------|--------|--------|
| `backend/invariants.py` | **Created** | S1 |
| `backend/provenance.py` | **Created** | S2 |
| `backend/snapshot_diff.py` | **Created** | S3 |
| `backend/isi_api_v01.py` | **Modified** — added `GET /diff/{version_a}/{version_b}` | S3 |
| `tests/test_systems_hardening.py` | **Created** | All |
| `docs/SYSTEMS_HARDENING.md` | **Created** | Docs |

---

## Design Constraints

- **No score modification**: All three systems are read-only / annotation-only
- **Full determinism**: Same inputs → same outputs, always
- **No randomness**: No random, no sampling, no probabilistic elements
- **Rule ID provenance**: Every decision traceable to a specific rule
- **Machine-readable**: All outputs are structured JSON
- **Backward compatible**: No existing API contracts broken
