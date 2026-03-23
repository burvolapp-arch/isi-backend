# Falsification Framework

> **Module:** `backend/falsification.py`  
> **Layer:** 2 of 4 — Institutional Upgrade  
> **Status:** STRUCTURAL falsification operational, EMPIRICAL benchmarks defined but NOT integrated

---

## Purpose

A credible index must be falsifiable. The ISI falsification framework answers:

> *"Where does the system's output contradict independently known facts about the world?"*

If the ISI classifies a known major arms exporter as "FULLY_COMPARABLE" with no
inversions, that is a **structural contradiction** — and the system must flag it.

---

## Architecture

### Falsification Flags

| Flag | Meaning |
|------|---------|
| `CONSISTENT` | System output aligns with known structural facts |
| `TENSION` | Minor misalignment — not a hard contradiction but warrants attention |
| `CONTRADICTION` | System output directly contradicts known facts |
| `NOT_ASSESSED` | No structural facts available for this country |

### Two Categories of Checks

#### 1. Structural Falsification (OPERATIONAL)

Uses `STRUCTURAL_FACTS` — a registry of independently known characteristics:

| Country | Known Properties |
|---------|-----------------|
| US | 3 known exporter axes, no sanctions, expected NON_COMPARABLE |
| RU | 3 known exporter axes, sanctions active, expected NON_COMPARABLE |
| CN | 2 known exporter axes, no sanctions, expected LOW_CONFIDENCE |
| NO | 1 known exporter axis, no sanctions, expected PARTIALLY_COMPARABLE |
| AU | 1 known exporter axis, no sanctions, expected PARTIALLY_COMPARABLE |
| FR | 1 known exporter axis, no sanctions, expected PARTIALLY_COMPARABLE |
| DE | 1 known exporter axis, no sanctions, expected FULLY_COMPARABLE |
| SA | 0 known exporter axes, no sanctions, expected LOW_CONFIDENCE |

**Four structural checks:**

1. **Producer inversion governance consistency** — Does the governance tier match expectations for known exporters?
2. **Sanctions consistency** — Are sanctioned countries correctly classified as NON_COMPARABLE or LOW_CONFIDENCE?
3. **Producer inversion registry completeness** — Are all known exporter axes actually registered as inverted?
4. **EU-27 data architecture advantage** — Do clean EU-27 countries correctly achieve PARTIALLY_COMPARABLE or better?

#### 2. Empirical Benchmarks (DEFINED, NOT INTEGRATED)

| Benchmark ID | Source | Status |
|-------------|--------|--------|
| `EXTERNAL_IEA_ENERGY` | IEA Energy Balances | NOT_INTEGRATED |
| `EXTERNAL_EU_CRM` | EU Critical Raw Materials | NOT_INTEGRATED |
| `EXTERNAL_SIPRI_MILEX` | SIPRI Military Expenditure | NOT_INTEGRATED |
| `EXTERNAL_BIS_CBS` | BIS Consolidated Banking | NOT_INTEGRATED |

These benchmarks are architecturally ready but require external data feeds.

---

## Honesty Commitment

Every falsification result includes:

```json
{
    "honesty_note": "ISI falsification is currently STRUCTURAL, not empirical...",
    "external_data_status": "NOT_INTEGRATED"
}
```

The system does not claim empirical validation it does not have.

---

## Usage

```python
from backend.falsification import (
    assess_country_falsification,      # Single country
    assess_all_countries_falsification, # All countries
    get_falsification_summary,          # Aggregate statistics
    get_benchmark_registry,             # All benchmarks (integrated + pending)
)

# Assess a single country
result = assess_country_falsification("US", governance_result)
# → {"overall_flag": "CONTRADICTION", "n_contradictions": 2, ...}
```

---

## Integration

Falsification results are materialized in:
- `build_country_json()` → `country.falsification` field
- `build_isi_json()` → available through country detail endpoints
- `classify_decision_usability()` → a CONTRADICTION forces INVALID_FOR_COMPARISON

---

## Roadmap

1. **Phase 1 (COMPLETE):** Structural falsification against known country profiles
2. **Phase 2 (PLANNED):** IEA Energy Balances cross-validation for Axis 1
3. **Phase 3 (PLANNED):** SIPRI cross-validation for Axis 5/6
4. **Phase 4 (PLANNED):** BIS CBS cross-validation for Axis 1
