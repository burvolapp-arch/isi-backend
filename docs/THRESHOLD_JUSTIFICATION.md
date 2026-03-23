# Threshold Justification Registry

> **Module:** `backend/threshold_registry.py`  
> **Layer:** 1 of 4 — Institutional Upgrade  
> **Status:** COMPLETE — 27 thresholds registered, 0 empirically calibrated

---

## Purpose

Every numerical threshold in ISI now has a machine-readable justification.  
An institutional reviewer (BIS/ECB/IMF level) can query:

1. **Why this value?** → `justification` field  
2. **What if it's wrong?** → `risk_if_misspecified`, `risk_level`, `breakpoints`  
3. **What else is plausible?** → `alternative_plausible_values`, `sensitivity_band`  
4. **Where does it come from?** → `rationale_type`, `source_module`

---

## Registry Schema

Each entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `threshold_id` | str | Unique identifier (e.g. `GOV_BASELINE_AX1`) |
| `name` | str | Human-readable name |
| `current_value` | float/int | The value currently used in production |
| `functional_role` | str | What this threshold controls |
| `rationale_type` | enum | `EMPIRICAL`, `SEMI_EMPIRICAL`, `HEURISTIC`, `STRUCTURAL_NORMATIVE` |
| `justification` | str | Plain-language explanation of why this value |
| `sensitivity_band` | dict | `{low, high}` — plausible range |
| `breakpoints` | list | Threshold values where system behavior changes qualitatively |
| `alternative_plausible_values` | list | Other defensible values with rationale |
| `risk_if_misspecified` | str | What goes wrong if this threshold is wrong |
| `risk_level` | enum | `LOW`, `MODERATE`, `HIGH`, `CRITICAL` |
| `source_module` | str | Which Python module owns this threshold |
| `affects` | list | System behaviors affected by this threshold |

---

## Rationale Types

| Type | Count | Meaning |
|------|-------|---------|
| `EMPIRICAL` | 0 | Externally calibrated against observed data |
| `SEMI_EMPIRICAL` | varies | Informed by data patterns, not formally fitted |
| `HEURISTIC` | varies | Expert judgment, structurally motivated |
| `STRUCTURAL_NORMATIVE` | varies | Defined by the model's architecture |

### Honesty Note

ISI currently has **zero purely empirical thresholds**. All thresholds are
heuristic or structural. This is explicitly stated in the registry and tested:

```python
def test_no_empirical_thresholds(self):
    empirical = get_thresholds_by_rationale(RationaleType.EMPIRICAL)
    assert len(empirical) == 0  # ISI has no externally calibrated thresholds
```

---

## Critical Thresholds

Two thresholds are flagged `CRITICAL` risk:

### `GOV_MIN_MEAN_CONF_RANKING` (0.45)
- **Role:** Minimum mean confidence across axes for ranking eligibility
- **Risk:** If too low, rankings include countries whose scores are noise. If too high, rankings exclude borderline-but-informative countries.

### `GOV_MAX_INVERTED_COMPARABLE` (2)
- **Role:** Maximum producer-inverted axes for cross-country comparability
- **Risk:** If too permissive, structurally distorted countries enter comparisons. If too strict, only pristine EU members remain.

---

## Coverage by Source Module

| Source Module | Thresholds | Categories |
|--------------|-----------|------------|
| `governance.py` | ~19 | Axis baselines, confidence penalties, confidence levels, composite/ranking gates |
| `severity.py` | ~8 | Severity weights for degradation flags |

---

## Query API

```python
from backend.threshold_registry import (
    get_threshold_justification_registry,  # Full registry
    get_threshold_by_id,                   # Single lookup
    get_thresholds_by_source,              # By source module
    get_thresholds_by_rationale,           # By rationale type
    get_thresholds_by_risk,                # By risk level
    get_registry_summary,                  # Aggregate statistics
)
```

---

## Test Coverage

82 tests in `tests/test_institutional_upgrade.py` cover:
- Registry completeness (all governance baselines, penalties, severity weights)
- Registry consistency (values match actual source modules)
- Schema validation (all required fields present)
- Query function correctness
- Honesty constraints (no false empirical claims)
