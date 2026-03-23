# Authority Unification

> **Layer:** 4 of 4 — Institutional Upgrade  
> **Status:** COMPLETE — Single source of truth established

---

## Problem

Before this upgrade, ISI had a **dual-authority problem**:

| Module | Class | Purpose |
|--------|-------|---------|
| `calibration.py` | `EligibilityClass` | Hand-curated eligibility metadata for 39 countries |
| `eligibility.py` | `TheoreticalEligibility` | Rule-based eligibility classification for 39 countries |

Both modules independently classified countries into eligibility tiers.  
Neither was designated as authoritative. A reviewer could legitimately ask:

> *"Which classification should I trust when they disagree?"*

---

## Resolution

### Authoritative System: `backend/eligibility.py`

The **single source of truth** for eligibility classification is now
`backend/eligibility.py`, which provides:

| System | Class | Purpose |
|--------|-------|---------|
| **Eligibility** (authoritative) | `TheoreticalEligibility` | Structural eligibility from governance pipeline |
| **Decision Usability** (authoritative) | `DecisionUsabilityClass` | Decision-grade classification combining eligibility + governance + falsification |
| **Calibration** (supplementary) | `EligibilityClass` | Metadata — expert-curated reference data, NOT the deciding classification |

### What Changed

1. **`calibration.py` `EligibilityClass`** — Docstring updated to state:
   > *"This is the calibration module's METADATA classification. The AUTHORITATIVE eligibility system is in backend/eligibility.py."*

2. **`calibration.py` `get_eligibility_summary()`** — Now returns `authority_note` field:
   > *"This summary is from calibration.py's METADATA registry. The AUTHORITATIVE eligibility system is in backend/eligibility.py."*

3. **`eligibility.py`** — Designated as the single authority with:
   - `TheoreticalEligibility` — structural classification (5 levels)
   - `DecisionUsabilityClass` — decision-grade classification (4 levels)
   - `classify_country()` — authoritative eligibility determination
   - `classify_decision_usability()` — authoritative usability determination

### What Did NOT Change

- `calibration.py` `COUNTRY_ELIGIBILITY_REGISTRY` — **PRESERVED** as supplementary metadata
- `calibration.py` `EligibilityClass` — **PRESERVED** for backward compatibility
- All existing imports and function signatures — **UNCHANGED**

---

## Hierarchy

```
backend/eligibility.py  ← AUTHORITATIVE
    TheoreticalEligibility (5 levels)
    DecisionUsabilityClass (4 levels)
    classify_country()
    classify_decision_usability()
    ↓
backend/calibration.py  ← SUPPLEMENTARY METADATA
    EligibilityClass (4 levels)
    COUNTRY_ELIGIBILITY_REGISTRY
    get_eligibility_summary()
```

---

## Decision Usability Classification

The new `DecisionUsabilityClass` (Layer 3) synthesizes:
- Eligibility classification (from `classify_country()`)
- Governance tier and confidence
- Producer inversion count
- Falsification results

| Class | Meaning | Policy Implication |
|-------|---------|-------------------|
| `TRUSTED_COMPARABLE` | Full cross-country comparison valid | Use for benchmarking and ranking |
| `CONDITIONALLY_USABLE` | Usable with documented caveats | Use with explicit limitations noted |
| `STRUCTURALLY_LIMITED` | Structural data issues limit utility | Use only for within-country trends |
| `INVALID_FOR_COMPARISON` | Cannot be meaningfully compared | Exclude from cross-country analysis |

---

## Cross-Module Consistency Tests

The test suite verifies:

1. **Coverage:** All countries in `calibration.py` are also in `eligibility.py`
2. **Direction:** `CONFIDENTLY_RATEABLE` (calibration) maps to `RATEABLE+` (eligibility)
3. **Direction:** `NOT_CURRENTLY_RATEABLE` (calibration) maps to `NOT_READY/COMPILE_READY` (eligibility)
4. **Authority note present** in `get_eligibility_summary()` output
5. **Known alias handling:** `UK` (calibration) ↔ `GB` (eligibility/ISO 3166)
