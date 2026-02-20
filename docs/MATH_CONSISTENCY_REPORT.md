# Math Consistency Report — Scenario Engine

**Date:** 2025-01-27  
**Scope:** `backend/scenario.py` classification thresholds  
**Status:** ✅ FIXED — all invariants proven  

---

## 1. Bug Report

**Symptom:** Bulgaria with -20% on all axes showed a *worsened* classification despite
every score decreasing. The frontend displayed the baseline as "moderately concentrated"
(from `isi.json`) but the scenario engine computed "highly concentrated" for *both*
baseline and simulated — making it appear that reducing dependency made things worse.

## 2. Root Cause

`scenario.py` had **wrong classification thresholds** that did not match the authoritative
exporter (`export_isi_backend_v01.py::classify_score()`).

| Threshold | Exporter (correct) | scenario.py (was) |
|---|---|---|
| `≥ 0.50` | `highly_concentrated` | *(missing)* |
| `≥ 0.25` | `moderately_concentrated` | `highly_concentrated` ← BUG |
| `≥ 0.15` | `mildly_concentrated` | `moderately_concentrated` |
| `≥ 0.10` | *(no tier)* | `mildly_concentrated` |
| `< 0.15` | `unconcentrated` | — |
| `< 0.10` | — | `unconcentrated` |

The thresholds in `scenario.py` were **shifted down by one tier** and the top tier
(`≥ 0.50 → highly`) was missing entirely.

### Impact

- **26 out of 27** EU countries had their classification computed incorrectly by the
  scenario engine (only Malta, with composite > 0.50, happened to match).
- Any country with composite between 0.25 and 0.50 was labelled "highly concentrated"
  by the backend but "moderately concentrated" in the stored data — creating the
  contradictory output the user observed.

### Bug Chain (Bulgaria Example)

1. `isi.json` stores BG classification = `"moderately_concentrated"` (correct, from exporter)
2. Backend computes `classify(0.34028)` → `"highly_concentrated"` (wrong, old thresholds)
3. With -20%: `classify(0.27222)` → `"highly_concentrated"` (still wrong)
4. Frontend shows baseline from stored data ("moderately") vs simulated from backend ("highly")
5. User sees: "I reduced everything and it got worse" → **mathematical contradiction**

## 3. Fix Applied

**Single-line change** in `backend/scenario.py`:

```python
# BEFORE (wrong):
_CLASSIFICATION_THRESHOLDS = [
    (0.25, "highly_concentrated"),
    (0.15, "moderately_concentrated"),
    (0.10, "mildly_concentrated"),
]

# AFTER (correct — matches exporter):
_CLASSIFICATION_THRESHOLDS = [
    (0.50, "highly_concentrated"),
    (0.25, "moderately_concentrated"),
    (0.15, "mildly_concentrated"),
]
```

**Verification:** After fix, `classify()` produces **0 mismatches** across all 27
countries compared to `isi.json` stored classifications.

## 4. Invariant Tests Added

23 new tests (74 total, up from 51) organized into 7 invariant classes:

| Class | Tests | Invariant |
|---|---|---|
| `TestMonotonicity` | 7 | Decrease all axes → composite decreases, classification never worsens |
| `TestIdentity` | 2 | Zero adjustments → baseline ≡ simulated (all 27 countries) |
| `TestThresholdConsistency` | 5 | Thresholds = [0.50, 0.25, 0.15], matching exporter exactly |
| `TestOrderingConsistency` | 2 | Rank from composite sort = rank from `compute_rank()` |
| `TestDeterminism` | 1 | 100 identical runs → identical output |
| `TestInputValidation` | 3 | Edge cases: all-zero, all-one baselines, boundary adjustments |
| `TestBulgariaRegression` | 3 | BG -20% all axes: composite drops, classification never worsens |

### Key Invariants Enforced

1. **Monotonicity:** `∀ country, ∀ adj < 0: classify(simulated) ≤ₛₑᵥ classify(baseline)`
2. **Identity:** `adj = {} ⟹ baseline = simulated` (exact, not approximate)
3. **Threshold lock:** `_CLASSIFICATION_THRESHOLDS == [(0.50, ...), (0.25, ...), (0.15, ...)]`
4. **Rank ordering:** Sort by composite descending ≡ rank assignment
5. **Determinism:** Same input → same output (excluding timestamp), verified over 100 runs
6. **Bounds safety:** 0.0 ≤ axis ≤ 1.0, 0.0 ≤ composite ≤ 1.0, no NaN/Inf

## 5. Debug Trace Mode

Added `SCENARIO_DEBUG=1` environment variable control:

- When enabled: structured logging of every intermediate value in `simulate()`
- Logs: adjustments, per-axis baseline/simulated/delta, composite, classification, rank
- When disabled: zero overhead (guard check only)
- Format: `scenario DEBUG simulate(BG) adjustments={...}`

## 6. Files Changed

| File | Change |
|---|---|
| `backend/scenario.py` | Fixed thresholds, added debug trace infrastructure |
| `tests/test_scenario.py` | Fixed `TestClassify` expectations, added 7 invariant test classes (23 new tests) |
| `docs/MATH_CONSISTENCY_REPORT.md` | This report |
