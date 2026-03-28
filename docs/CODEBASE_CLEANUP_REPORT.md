# Codebase Cleanup Report

> **Date**: March 2026.
> **Scope**: Full codebase audit and cleanup performed as part of the
> External Validation & Benchmark Integration pass.
>
> **Baseline**: 1475 tests passing before this pass.
> **Final**: 1613 tests passing after this pass.

---

## 1. Summary of Changes

| Category | Action | Impact |
|----------|--------|--------|
| New modules | 2 created (benchmark_registry.py, external_validation.py) | +1,674 lines |
| Modified modules | 4 (invariants.py, eligibility.py, export_snapshot.py, calibration.py) | ~800 lines added |
| New test files | 2 (test_external_validation.py, test_empirical_alignment.py) | +1,656 lines, 138 tests |
| Documentation | 3 files created/updated | BACKEND_STRUCTURE.md, EXTERNAL_VALIDATION_FRAMEWORK.md, this file |
| Bug fixes | 1 (UK→GB country code) | Consistency fix |
| Deprecation markers | 2 sections in calibration.py | Authority clarification |

---

## 2. Duplication Analysis & Resolution

### 2.1 `calibration.py` Authority Audit

`calibration.py` (2,848 lines) was analyzed for duplication against
newer authoritative modules. Finding:

| Section | Status | Authority |
|---------|--------|-----------|
| `EXTERNAL_BENCHMARK_REGISTRY` | **DEPRECATED** → `benchmark_registry.py` | benchmark_registry.py is authoritative |
| `EligibilityClass` | **DEPRECATED** → `eligibility.py` | eligibility.py is authoritative |
| `CalibrationClass` | UNIQUE | calibration.py owns this |
| `SEVERITY_WEIGHT_CALIBRATIONS` | UNIQUE | calibration.py owns this |
| `GOVERNANCE_THRESHOLD_CALIBRATIONS` | UNIQUE | calibration.py owns this |
| `FALSIFIABILITY_REGISTRY` | UNIQUE | calibration.py owns this |
| `CIRCULARITY_AUDIT` | UNIQUE | calibration.py owns this |
| `AXIS_CALIBRATION_NOTES` | UNIQUE | calibration.py owns this |
| `PSEUDO_RIGOR_AUDIT` | UNIQUE | calibration.py owns this |
| `build_governance_explanation()` | UNIQUE | calibration.py owns this |
| Sensitivity analysis | UNIQUE | calibration.py owns this |

**Decision**: Deprecation markers added (not deletion) because:
1. Deprecated sections still function as supplementary metadata.
2. Other modules may reference them during transition.
3. Deletion would break backward compatibility without clear benefit.
4. The unique content in calibration.py is substantial (~2,000 lines)
   and not replicated elsewhere.

### 2.2 Deprecation Markers Added

```
⚠️ DEPRECATED — SUPPLEMENTARY METADATA ONLY
Authority: backend/benchmark_registry.py
```

```
⚠️ DEPRECATED (SUPPLEMENTARY METADATA ONLY)
Authority: backend/eligibility.py
```

Both markers include the authoritative module path for clear redirection.

---

## 3. Consistency Fixes

### 3.1 UK → GB Country Code

**Problem**: `calibration.py` `COUNTRY_ELIGIBILITY_REGISTRY` used `"UK"`
for the United Kingdom, while the rest of the codebase uses `"GB"`
(ISO 3166-1 alpha-2).

**Fix**: Changed `"UK"` to `"GB"` in calibration.py and updated
`test_calibration_falsifiability.py` to match.

**Verification**: All 1,613 tests pass after the fix.

---

## 4. Dead Code Analysis

### 4.1 Methodology

A sub-agent performed deep analysis of `calibration.py` to determine
which sections were duplicated vs. unique. The analysis examined:

- Every class, constant, function, and data structure in calibration.py
- Cross-references to all other backend modules
- Whether each section's content was replicated elsewhere

### 4.2 Finding

Most code in `calibration.py` that appeared to be "dead" or "duplicated"
turned out to be **unique content** with no equivalent elsewhere:

- `CIRCULARITY_AUDIT` — documents which ISI constructs are self-referential
- `AXIS_CALIBRATION_NOTES` — per-axis methodological notes
- `PSEUDO_RIGOR_AUDIT` — flags where the system looks rigorous but isn't
- `FALSIFIABILITY_REGISTRY` — per-claim testable predictions
- Sensitivity analysis functions — unique threshold sensitivity testing

**Decision**: No code was deleted. Only deprecation markers were added
to the two sections genuinely superseded by newer modules.

---

## 5. Structural Simplification

### 5.1 Assessment

The codebase was assessed for structural simplification opportunities.
Finding: the module boundaries are already well-defined and minimal.

| Module | Responsibility | Overlaps? |
|--------|---------------|-----------|
| `severity.py` | Score computation | No |
| `governance.py` | Governance tiers + confidence | No |
| `calibration.py` | Thresholds + falsifiability + metadata | Partial (deprecated sections) |
| `eligibility.py` | Country classification + decision usability | No |
| `threshold_registry.py` | Machine-readable threshold justification | No |
| `falsification.py` | Structural falsification engine | No |
| `benchmark_registry.py` | External benchmark definitions | No |
| `external_validation.py` | Alignment engine | No |
| `invariants.py` | Structural invariants | No |
| `export_snapshot.py` | JSON export + signing | No |

No modules were merged or split. The existing separation of concerns
is appropriate.

---

## 6. Contract Enforcement

### 6.1 Type Hints

All new functions use full type annotations:

```python
def compare_to_benchmark(
    benchmark_id: str,
    isi_values: dict[str, float] | None,
    external_values: dict[str, float] | None,
) -> dict[str, Any]: ...

def classify_empirical_alignment(
    external_validation_result: dict[str, Any] | None = None,
) -> dict[str, Any]: ...

def classify_policy_usability(
    structural_class: str,
    empirical_class: str,
) -> dict[str, Any]: ...
```

### 6.2 Explicit Optional Parameters

Functions that gained external validation capability use optional
parameters with None defaults, preserving backward compatibility:

- `classify_decision_usability(..., external_validation_result=None)`
- `assess_country_invariants(..., external_validation_result=None)`

Callers that don't pass external validation data get the same behavior
as before.

### 6.3 Frozensets for Valid Values

Every classification enum has a corresponding `VALID_*` frozenset:

- `VALID_ALIGNMENT_CLASSES`
- `VALID_COMPARISON_TYPES`
- `VALID_EMPIRICAL_CLASSES`
- `VALID_POLICY_CLASSES`

These enable runtime validation of classification values.

---

## 7. Test Coverage

### 7.1 New Test Files

| File | Tests | Coverage |
|------|-------|---------|
| `test_external_validation.py` | 100 | Benchmark registry (11), alignment classes (2), compare_to_benchmark (9), country validation (4), construct validity (3), all-countries (2), invariants (6), Spearman ρ (5+), export blocks, edge cases |
| `test_empirical_alignment.py` | 38 | Empirical alignment classes (4), policy usability classes (4), classify_empirical_alignment (8), classify_policy_usability (7), decision usability integration (6), export integration (5), validation status (4) |

### 7.2 Test Progression

| Milestone | Tests |
|-----------|-------|
| Before this pass | 1,475 |
| After external validation module | 1,575 (+100) |
| After empirical alignment tests | 1,613 (+38) |

### 7.3 All Tests Pass

```
1613 passed, 14 warnings
```

The 14 warnings are pre-existing (unrelated to this pass).

---

## 8. Authority Hierarchy

The codebase now has a clear authority hierarchy for overlapping
concepts:

```
SCORES:         severity.py (authoritative)
GOVERNANCE:     governance.py (authoritative)
THRESHOLDS:     threshold_registry.py (authoritative)
                calibration.py (supplementary — GOVERNANCE_THRESHOLD_CALIBRATIONS)
ELIGIBILITY:    eligibility.py (authoritative)
                calibration.py (supplementary — EligibilityClass DEPRECATED)
BENCHMARKS:     benchmark_registry.py (authoritative)
                calibration.py (supplementary — EXTERNAL_BENCHMARK_REGISTRY DEPRECATED)
VALIDATION:     external_validation.py (authoritative)
INVARIANTS:     invariants.py (authoritative)
FALSIFICATION:  falsification.py (authoritative)
                calibration.py (supplementary — FALSIFIABILITY_REGISTRY)
PROVENANCE:     provenance.py (authoritative)
EXPORT:         export_snapshot.py (authoritative)
```

`calibration.py` retains unique content (sensitivity analysis,
circularity audit, axis calibration notes, pseudo-rigor audit,
governance explanation builder) that is not replicated elsewhere.

---

## 9. What Was NOT Changed

1. **No modules were deleted.** Deprecation markers are more appropriate
   than deletion for a production codebase.

2. **No function signatures were broken.** All new parameters are
   optional with backward-compatible defaults.

3. **No test assertions were weakened.** All test fixes corrected
   incorrect test data, not loosened assertions.

4. **No thresholds were changed.** Alignment thresholds (0.7/0.4)
   are new additions, not modifications of existing thresholds.

5. **No governance rules were modified.** The governance layer is
   untouched. External validation is an additional dimension, not a
   replacement.

---

## 10. File Count Impact

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Python files | ~60 | 67 | +7 |
| Lines of code | ~38,000 | ~44,800 | +~6,800 |
| Tests | 1,475 | 1,613 | +138 |
| Test files | 19 | 21 | +2 |
| Documentation files | 5 | 8 | +3 |
