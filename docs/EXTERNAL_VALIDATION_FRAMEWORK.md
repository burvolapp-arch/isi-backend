# External Validation Framework — Architecture & Design

> **Created**: March 2026.
> **Scope**: How the ISI system answers "Does this align with reality?"
> — explicitly, with evidence, and without faking.
>
> **If this document disagrees with the code, the code is authoritative.**

---

## 1. Purpose

The External Validation Framework upgrades the ISI system from
"internally consistent" to "externally grounded." Before this
framework, the system could answer:

- _Are the scores structurally sound?_ → Yes/No (governance layer)
- _Can this country be ranked?_ → Yes/No (eligibility layer)
- _Is this threshold justified?_ → Yes/No (threshold registry + falsification)

After this framework, it can ALSO answer:

- **Does this align with reality?** → Yes / No / Partially / Unknown
  (explicitly, with metrics and evidence)

This is the difference between an internally consistent model and an
externally interpretable system.

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────────┐
│                 ISI Score Pipeline                │
│  severity.py → governance.py → eligibility.py    │
└───────────────────┬──────────────────────────────┘
                    │ axis_scores per country
                    ▼
┌──────────────────────────────────────────────────┐
│           benchmark_registry.py                   │
│  8 benchmarks × 6 axes — formal definitions       │
│  AlignmentClass, ComparisonType, IntegrationStatus│
└───────────────────┬──────────────────────────────┘
                    │ benchmark definitions
                    ▼
┌──────────────────────────────────────────────────┐
│           external_validation.py                  │
│  compare_to_benchmark()    — per-benchmark        │
│  assess_country_alignment() — per-country         │
│  assess_construct_validity() — per-axis           │
│  build_external_validation_block() — for export   │
└───────────────────┬──────────────────────────────┘
                    │ alignment results
                    ▼
      ┌─────────────┼──────────────┐
      ▼             ▼              ▼
┌──────────┐ ┌────────────┐ ┌────────────────┐
│invariants│ │eligibility │ │export_snapshot  │
│.py       │ │.py         │ │.py             │
│EV-001    │ │Empirical   │ │external_       │
│EV-002    │ │Alignment   │ │validation      │
│EV-003    │ │+ Policy    │ │block in        │
│          │ │Usability   │ │country JSON    │
└──────────┘ └────────────┘ └────────────────┘
```

---

## 3. Benchmark Registry (`benchmark_registry.py`)

### 3.1 Design Principles

- Every benchmark has an **explicit construct description** — what it
  actually measures, not what we wish it measured.
- No benchmark is assumed to measure exactly the same thing as ISI.
- `STRUCTURALLY_INCOMPARABLE` is a first-class outcome, not a fallback.
- Missing data produces `NO_DATA`, never silent omission.

### 3.2 Registered Benchmarks

| ID | Name | ISI Axis | Comparison Type | Integration Status |
|----|------|----------|-----------------|-------------------|
| `BM_IEA_ENERGY` | IEA Energy Security Indicators | 2 | RANK_CORRELATION | STRUCTURALLY_DEFINED |
| `BM_COMTRADE_ENERGY_XVAL` | Comtrade Energy Cross-Validation | 2 | STRUCTURAL_CONSISTENCY | STRUCTURALLY_DEFINED |
| `BM_EU_CRM` | EU Critical Raw Materials | 5 | RANK_CORRELATION | STRUCTURALLY_DEFINED |
| `BM_SIPRI_MILEX` | SIPRI Military Expenditure | 4 | DIRECTIONAL_AGREEMENT | STRUCTURALLY_DEFINED |
| `BM_BIS_CBS` | BIS Consolidated Banking Statistics | 1 | RANK_CORRELATION | STRUCTURALLY_DEFINED |
| `BM_UNCTAD_LSCI` | UNCTAD Liner Shipping Connectivity | 6 | RANK_CORRELATION | STRUCTURALLY_DEFINED |
| `BM_WB_LPI` | World Bank Logistics Performance | 6 | RANK_CORRELATION | STRUCTURALLY_DEFINED |
| `BM_EUROSTAT_LOGISTICS` | Eurostat Transport Statistics | 6 | STRUCTURAL_CONSISTENCY | STRUCTURALLY_DEFINED |

### 3.3 Alignment Classes

| Class | Meaning |
|-------|---------|
| `STRONGLY_ALIGNED` | ISI and benchmark agree substantially (ρ ≥ 0.7 or equivalent) |
| `WEAKLY_ALIGNED` | Partial agreement (0.4 ≤ ρ < 0.7) |
| `DIVERGENT` | Active disagreement (ρ < 0.4) |
| `STRUCTURALLY_INCOMPARABLE` | Constructs differ too much for meaningful comparison |
| `NO_DATA` | Data missing — comparison impossible |

### 3.4 Query API

```python
get_benchmark_registry()         # → full registry dict
get_benchmarks_for_axis(axis_id) # → list of benchmarks for one axis
get_benchmarks_by_status(status) # → filter by IntegrationStatus
get_benchmark_by_id(bm_id)      # → single benchmark dict or None
get_benchmark_coverage_summary() # → {axis_id: [benchmark_ids]}
validate_benchmark_registry()    # → list of structural errors
```

---

## 4. Alignment Engine (`external_validation.py`)

### 4.1 Core Functions

#### `compare_to_benchmark(benchmark_id, isi_values, external_values)`

Compares ISI axis scores to one external benchmark. Returns:

```python
{
    "benchmark_id": "BM_IEA_ENERGY",
    "benchmark_name": "IEA Energy Security Indicators",
    "alignment_class": "STRONGLY_ALIGNED",  # or WEAKLY/DIVERGENT/etc.
    "comparison_type": "RANK_CORRELATION",
    "metric_value": 0.82,
    "n_countries_compared": 14,
    "interpretation": "...",
}
```

Comparison methods depend on `ComparisonType`:

| Type | Method | Metric |
|------|--------|--------|
| `RANK_CORRELATION` | Spearman ρ (no scipy dependency) | −1 to +1 |
| `STRUCTURAL_CONSISTENCY` | Sign agreement on key structural patterns | 0 to 1 |
| `DIRECTIONAL_AGREEMENT` | Whether high/low rankings agree in direction | 0 to 1 |
| `LEVEL_COMPARISON` | Absolute value proximity | 0 to 1 |

#### `assess_country_alignment(country, axis_scores, external_data)`

Runs all applicable benchmarks for a single country. Returns per-axis
alignment results plus an overall summary.

#### `assess_construct_validity(axis_id, isi_values, external_data)`

Tests whether a specific ISI axis measures what it claims to, based on
correlation with all benchmarks mapped to that axis.

#### `build_external_validation_block(country, axis_scores, external_data)`

Produces the export-ready block that gets embedded in country JSON.
Includes the **empirical grounding answer** — the explicit YES/NO.

### 4.2 The Empirical Grounding Answer

`_empirical_grounding_answer()` generates the explicit response to
"Does this align with reality?" based on aggregate alignment:

| Answer | Condition |
|--------|-----------|
| `"YES"` | Majority of compared axes are STRONGLY_ALIGNED or WEAKLY_ALIGNED |
| `"PARTIALLY"` | Mixed results — some aligned, some divergent |
| `"NO"` | Majority of compared axes are DIVERGENT |
| `"UNKNOWN"` | No benchmark data available |

This answer is never faked. If data is missing, it says `"UNKNOWN"`.

### 4.3 Spearman ρ Implementation

The engine computes Spearman rank correlation without scipy to avoid
dependency bloat. The implementation:

1. Converts values to ranks (with tie handling via average ranks)
2. Computes Pearson correlation on ranks
3. Handles edge cases: N < 3, zero variance, identical rankings

Threshold classification:
- |ρ| ≥ 0.7 → `STRONGLY_ALIGNED`
- 0.4 ≤ |ρ| < 0.7 → `WEAKLY_ALIGNED`
- |ρ| < 0.4 → `DIVERGENT`

---

## 5. Validation Invariants

Three invariants in `invariants.py` guard against external validation
failures:

### EV-001: Benchmark Alignment Contradiction (CRITICAL)

**Fires when**: A country is classified as `DIVERGENT` on a majority of
compared benchmarks. This means ISI output actively contradicts external
data.

**Severity**: CRITICAL — investigation required.

### EV-002: Missing External Grounding (WARNING)

**Fires when**: No benchmark data is available for a country, making
empirical alignment unassessable.

**Severity**: WARNING — the country's scores may be correct but cannot
be externally validated.

### EV-003: Benchmark Coverage Gap (WARNING)

**Fires when**: Fewer than half of ISI axes have at least one applicable
benchmark for a country.

**Severity**: WARNING — limited external grounding even when some data
exists.

---

## 6. Decision Layer Upgrade (`eligibility.py`)

### 6.1 Empirical Alignment Classification

`classify_empirical_alignment()` maps external validation results to:

| Class | Meaning |
|-------|---------|
| `EMPIRICALLY_GROUNDED` | Majority of compared axes are aligned |
| `EMPIRICALLY_MIXED` | Some aligned, some divergent |
| `EMPIRICALLY_WEAK` | Comparisons exist but alignment is low |
| `EMPIRICALLY_CONTRADICTED` | Majority of compared axes diverge |
| `NOT_EMPIRICALLY_ASSESSED` | No external data available |

### 6.2 Policy Usability Classification

`classify_policy_usability()` combines structural soundness (from
`DecisionUsabilityClass`) with empirical alignment:

| Policy Class | Structural | Empirical |
|-------------|-----------|-----------|
| `STRUCTURALLY_SOUND_EMPIRICALLY_ALIGNED` | Sound | Grounded |
| `STRUCTURALLY_SOUND_EMPIRICALLY_WEAK` | Sound | Weak/Mixed/Unassessed |
| `EMPIRICALLY_CONTRADICTED` | Any non-invalid | Contradicted |
| `STRUCTURALLY_LIMITED` | Limited | Any non-contradicted |
| `INVALID_FOR_POLICY_USE` | Invalid | Any (or Limited + Contradicted) |
| `NOT_ASSESSED` | Unknown | Unknown |

**Key rule**: Structural invalidity is absolute — empirical alignment
cannot override structural disqualification.

**Key rule**: Empirical contradiction is a hard warning — even
structurally sound countries get flagged if benchmarks disagree.

### 6.3 Integration with `classify_decision_usability()`

The existing `classify_decision_usability()` function now accepts an
optional `external_validation_result` parameter. When provided, the
return dict includes:

- `empirical_alignment` — full classification dict
- `empirical_alignment_class` — the `EmpiricalAlignmentClass` value
- `policy_usability_class` — the `PolicyUsabilityClass` value
- `policy_usability_justification` — human-readable explanation

When not provided, these fields default to "not assessed."

---

## 7. Export Integration (`export_snapshot.py`)

### 7.1 Country JSON

Each country's exported JSON now includes an `external_validation`
block produced by `build_external_validation_block()`. This block
contains:

- Per-axis alignment results
- Per-benchmark comparison metrics
- Overall alignment summary
- The explicit empirical grounding answer (YES/NO/PARTIALLY/UNKNOWN)

### 7.2 ISI Ranking JSON

- Each row in the ISI rankings includes `policy_usability_class`
- ISI metadata includes `external_validation_status` summarizing
  benchmark registry coverage

---

## 8. Honesty Guarantees

The framework enforces several honesty constraints:

1. **No faked alignment.** Missing data → `NO_DATA` or `UNKNOWN`, never
   a synthetic correlation.

2. **No assumed correlation.** Even high correlation does not prove
   causation or correctness. Interpretations explicitly state this.

3. **Structural incomparability is explicit.** When constructs differ
   too much for meaningful comparison, the system says so rather than
   reporting a misleading metric.

4. **Divergence is informative, not automatically wrong.** ISI may
   diverge from a benchmark because: (a) ISI is wrong, (b) the
   benchmark measures something different, or (c) both. All
   interpretations are reported.

5. **No silent fallbacks.** Every function that encounters missing data,
   errors, or edge cases returns an explicit status rather than
   degrading silently.

---

## 9. Test Coverage

| Test File | Tests | Scope |
|-----------|-------|-------|
| `test_external_validation.py` | 100 | Benchmark registry, alignment engine, construct validity, invariants, Spearman ρ, export blocks |
| `test_empirical_alignment.py` | 38 | Empirical alignment classes, policy usability, decision layer integration, export integration |

Total: **138 tests** covering the external validation framework.

---

## 10. Limitations & Future Work

1. **Benchmarks are STRUCTURALLY_DEFINED, not INTEGRATED.**
   Benchmark definitions exist, but actual external data pipelines
   are not yet connected. When real data flows in, the alignment
   engine is ready to process it.

2. **No temporal external validation.** Benchmarks are compared as
   static snapshots. Temporal trend comparison (does ISI track external
   trends over time?) is not yet implemented.

3. **Construct overlap is partial by design.** ISI measures bilateral
   import concentration (HHI). External datasets measure related but
   different things (energy security, supply risk, logistics capacity).
   Perfect alignment is not expected and would be suspicious.

4. **Threshold calibration is heuristic.** The 0.7/0.4 thresholds for
   STRONGLY_ALIGNED/WEAKLY_ALIGNED classification are reasonable but
   not empirically derived. They should be validated against domain
   expert judgment when real data is available.
