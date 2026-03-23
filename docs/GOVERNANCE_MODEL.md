# ISI Governance Model

**Version:** 1.0  
**Module:** `backend/governance.py`  
**Test suite:** `tests/test_institutional_governance.py` (74 tests)  
**Status:** ENFORCED — all exports, API responses, and ranking decisions pass through this model.

---

## 1. Purpose

The ISI governance model exists because:

- **Technically computable ≠ defensibly comparable.** A score can be arithmetically valid but methodologically meaningless.
- **A score ≠ a valid result.** Import concentration for a major exporter doesn't measure vulnerability — it measures the absence of import dependency.
- **Software correctness ≠ methodological validity.** Tests passing doesn't mean outputs are honest.

This model enforces **interpretation discipline, comparability gating, ranking eligibility, and export permission**. It does NOT modify scores.

---

## 2. Country Governance Tiers

Every country is classified into exactly one of four tiers. Classification is **deterministic** — same inputs always produce the same tier.

### FULLY_COMPARABLE

All structural requirements met:
- All 6 axes present with primary data
- Mean axis confidence ≥ 0.45
- No more than 2 axes with LOW/MINIMAL confidence
- No producer inversion on ≥ 2 axes
- Logistics axis present (not proxy-only)
- Severity tier ≤ TIER_1
- **Consequences:** Ranking-eligible. Cross-country comparison permitted. Composite defensible.

### PARTIALLY_COMPARABLE

Comparison is valid but requires awareness of structural limitations:
- 5+ axes with data, or logistics absent/proxy, or 1 producer-inverted axis, or TIER_2 severity
- **Consequences:** Ranking-eligible WITHIN PARTITION (additional checks). Cross-country comparison requires explicit caveat. Composite defensible but caveated.

### LOW_CONFIDENCE

ISI composite is computable but not defensible for ranking:
- ≥ 2 producer-inverted axes, or TIER_3 severity, or mean confidence < 0.45, or > 2 low-confidence axes
- **Consequences:** Composite computed but **ranking-ineligible**. Cross-country comparison **suppressed**. Published only with mandatory governance annotations. Directional insight only.

### NON_COMPARABLE

ISI output is either not computable or too structurally compromised:
- < 4 axes with data, or ≥ 3 producer-inverted axes, or TIER_4 severity
- **Consequences:** Composite **suppressed** (`composite_adjusted = None`). Ranking **excluded** (`rank = None`). Export requires explicit "non_comparable" framing. **Do NOT include in league tables or cross-country comparisons.**

---

## 3. Tier Determination Rules

Rules are applied in order (first match wins):

| Priority | Condition | Tier |
|----------|-----------|------|
| 1 | TIER_4 severity | NON_COMPARABLE |
| 2 | < 4 axes with data | NON_COMPARABLE |
| 3 | ≥ 3 producer-inverted axes | NON_COMPARABLE |
| 4 | ≥ 2 inverted + logistics absent | LOW_CONFIDENCE |
| 5 | ≥ 2 producer-inverted axes | LOW_CONFIDENCE |
| 6 | TIER_3 severity | LOW_CONFIDENCE |
| 7 | Mean confidence < 0.45 | LOW_CONFIDENCE |
| 8 | > 2 low/minimal confidence axes | LOW_CONFIDENCE |
| 9 | Logistics absent | PARTIALLY_COMPARABLE |
| 10 | Logistics proxy-only | PARTIALLY_COMPARABLE |
| 11 | 1 producer-inverted axis | PARTIALLY_COMPARABLE |
| 12 | 5 axes (not 6) | PARTIALLY_COMPARABLE |
| 13 | TIER_2 severity | PARTIALLY_COMPARABLE |
| 14 | All conditions met | FULLY_COMPARABLE |

---

## 4. Axis Confidence Model

Each axis receives an independent confidence assessment based on source coverage, data quality flags, and structural limitations.

### Confidence Baselines

| Axis | Baseline | Rationale |
|------|----------|-----------|
| 1. Financial | 0.75 | BIS+CPIS dual-channel, ~30 reporting countries |
| 2. Energy | 0.80 | Comtrade, good coverage |
| 3. Technology | 0.80 | Comtrade, good coverage (HS6 risk) |
| 4. Defense | 0.55 | SIPRI TIV, lumpy, major weapons only |
| 5. Critical Inputs | 0.75 | Comtrade, good coverage |
| 6. Logistics | 0.60 | Mixed sources, partial coverage |

No baseline exceeds 0.90. Nothing in this system is that reliable.

**Calibration note:** All baselines are classified as SEMI_EMPIRICAL — informed by source coverage data but with judgmental magnitude. See `docs/CALIBRATION_AND_FALSIFIABILITY.md` for full evidence basis and falsifiability criteria for each threshold.

### Confidence Penalties

| Flag | Penalty | Effect |
|------|---------|--------|
| SINGLE_CHANNEL_A/B | −0.20 | Dual-channel reduced to single |
| CPIS_NON_PARTICIPANT | −0.25 | Portfolio investment unavailable |
| REDUCED_PRODUCT_GRANULARITY | −0.10 | HS6 classification limitation |
| TEMPORAL_MISMATCH | −0.15 | Year mismatch in data |
| PRODUCER_INVERSION | −0.30 | Major exporter, construct inapplicable |
| SANCTIONS_DISTORTION | −0.50 | Trade data structurally compromised |
| ZERO_BILATERAL_SUPPLIERS | −0.25 | No measured imports ≠ low concentration |
| INVALID_AXIS | −1.00 | Axis absent, confidence = 0 |

### Confidence Levels

| Level | Threshold | Meaning |
|-------|-----------|---------|
| HIGH | ≥ 0.65 | Full scope, dual-channel, no proxy |
| MODERATE | ≥ 0.45 | Minor limitations |
| LOW | ≥ 0.25 | Major limitations |
| MINIMAL | < 0.25 | Structural unsuitability or absent |

### Proxy Data

Proxy data caps confidence at 0.40 regardless of other factors. Proxy-based axes are explicitly marked and carry interpretation constraints.

---

## 5. Producer-Inversion Governance

Import concentration for a major exporter does NOT measure strategic vulnerability. It measures the **absence of import dependency**, which is a fundamentally different construct.

### Registered Producer Countries

| Country | Inverted Axes | Structural Class |
|---------|---------------|-----------------|
| US | 2 (Energy), 4 (Defense), 5 (Critical Inputs) | PRODUCER |
| NO | 2 (Energy) | BALANCED |
| AU | 2 (Energy), 5 (Critical Inputs) | PRODUCER |
| FR | 4 (Defense) | BALANCED |
| DE | 4 (Defense) | BALANCED |
| CN | 4 (Defense), 5 (Critical Inputs) | PRODUCER |
| SA | 2 (Energy) | PRODUCER |
| RU | 2 (Energy), 4 (Defense), 5 (Critical Inputs) | PRODUCER |

### Governance Consequences

- 1 inverted axis → PARTIALLY_COMPARABLE (minimum)
- 2 inverted axes → LOW_CONFIDENCE (minimum)
- 3+ inverted axes → NON_COMPARABLE

Producer-inverted axes carry mandatory interpretation constraints in all exports.

---

## 6. Logistics Structural Limitation

Axis 6 (Logistics) is the system's structural weak point globally:
- Maritime data is most complete; rail and air cargo are partial
- Many countries lack any logistics data

### Rules

- Logistics **absent** → cannot be FULLY_COMPARABLE (capped at PARTIALLY_COMPARABLE or lower)
- Logistics **proxy-only** → confidence capped at 0.40, governance capped at PARTIALLY_COMPARABLE
- Logistics absent → mandatory structural limitation documented in all exports

---

## 7. Composite Eligibility

A composite score existing ≠ a composite score being defensible.

| Requirement | Threshold | Controls |
|-------------|-----------|----------|
| Minimum axes for computation | 4 | `composite_defensible` |
| Minimum axes for ranking | 5 | `ranking_eligible` |
| Minimum mean confidence for ranking | 0.45 | `ranking_eligible` |
| Maximum low-confidence axes for ranking | 2 | `ranking_eligible` |

### Eligibility Flags

- **`composite_defensible`**: Whether the composite can be published. `False` for NON_COMPARABLE, < 4 axes, or mean confidence < 0.30.
- **`ranking_eligible`**: Whether the country can be included in ranked comparisons. `False` for LOW_CONFIDENCE, NON_COMPARABLE, < 5 axes, low mean confidence, or too many low-confidence axes.
- **`cross_country_comparable`**: Whether direct comparison with other countries is meaningful. `False` for NON_COMPARABLE, LOW_CONFIDENCE, or ≥ 2 producer-inverted axes.

---

## 8. Truthfulness Contract

Every exported result MUST satisfy the truthfulness contract. This is not optional.

### Required Fields

Every governance block must contain:
- `governance_tier`
- `ranking_eligible`
- `cross_country_comparable`
- `composite_defensible`
- `axis_confidences`
- `structural_limitations`
- `governance_interpretation`
- `n_producer_inverted_axes`
- `logistics_present`
- `mean_axis_confidence`

### Enforcement Rules

1. **Missing governance block** → export blocked
2. **NON_COMPARABLE with rank ≠ NULL** → export blocked
3. **NON_COMPARABLE with composite_adjusted ≠ NULL** → export blocked
4. **LOW_CONFIDENCE with ranking_eligible = True** → export blocked
5. **Non-FULLY_COMPARABLE with empty structural_limitations** → export blocked
6. **Missing axis confidences** → export blocked

Violations raise `ValueError` and prevent export.

---

## 9. Export Gate

`gate_export()` is the final checkpoint before any result leaves the system:

1. Injects governance metadata into the result
2. Suppresses ranking for ineligible countries (`rank = None`, `exclude_from_rankings = True`)
3. Suppresses `composite_adjusted` for non-defensible cases
4. Enforces the truthfulness contract (raises on violation)

No result can bypass this gate.

---

## 10. Integration Points

### Export Layer (`backend/export_snapshot.py`)

- `build_country_json()`: Includes governance tier, axis confidence per axis, structural limitations, comparability status, truthfulness contract
- `build_isi_json()`: Includes governance notice, truthfulness caveat, per-country governance tier and ranking eligibility
- `build_axis_json()`: Includes per-country axis confidence metadata

### API Layer (`backend/isi_api_v01.py`)

- `/country/{code}/axes`: Returns `axis_confidence` per axis and `governance_tier`
- `/isi`: Returns `_governance_notice` and `_truthfulness_contract`

### Severity Model (`backend/severity.py`)

Governance consumes the severity model's outputs (severity_total, comparability_tier) but does not modify them. Governance adds an independent layer of interpretation discipline on top of severity.

---

## 11. What This Model Does NOT Do

- **Does not modify scores.** Governance governs interpretation, not computation.
- **Does not override the severity model.** It consumes severity outputs.
- **Does not create manual exceptions.** No override mechanism exists.
- **Does not guarantee accuracy.** It guarantees that outputs are honest about their limitations.
- **Does not make ISI suitable for all purposes.** It makes ISI honest about where it is NOT suitable.

---

## 12. Audit Trail

| Date | Change | Tests |
|------|--------|-------|
| 2025 | Initial governance model — 4 tiers, axis confidence, producer inversion, logistics limitation, composite eligibility, truthfulness contract, export gate | 74 tests |
| 2025 | Calibration + falsifiability layer — all thresholds classified (EMPIRICAL/SEMI_EMPIRICAL/HEURISTIC/STRUCTURAL_NORMATIVE), falsifiability criteria for all mechanisms, country eligibility registry, sensitivity analysis, external benchmark hooks, pseudo-rigor self-audit. See `docs/CALIBRATION_AND_FALSIFIABILITY.md` and `backend/calibration.py`. | +87 tests |

---

## 13. Governing Principle

> If the system can produce polished outputs that look more authoritative than the methodology justifies, the governance model has failed.

Every output must carry enough self-disclosure that a competent reader can assess its reliability. This is not a feature. It is a requirement.
