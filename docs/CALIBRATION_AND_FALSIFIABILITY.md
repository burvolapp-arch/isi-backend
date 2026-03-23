# ISI Calibration and Falsifiability Framework

**Version:** 1.0  
**Module:** `backend/calibration.py`  
**Test suite:** `tests/test_calibration_falsifiability.py` (87 tests)  
**Status:** ENFORCED — every threshold is registered, classified, and falsifiable.

---

## 1. Purpose

This framework exists because:

- **A well-structured model that rests on hidden arbitrary thresholds is dishonest.** Every numeric threshold in the ISI governance and severity models now has an explicit calibration classification.
- **Declared rigor without empirical grounding is performative.** This framework makes the system's epistemic status transparent.
- **Falsifiability without testing is incomplete.** Every governance mechanism has falsification criteria, and the system is honest about which criteria have been tested (none, yet).

This document covers 13 mandatory tasks from the calibration + falsifiability directive.

---

## 2. Threshold Calibration Registry (Tasks 1-2)

Every numeric threshold in `backend/governance.py` and `backend/severity.py` is registered in `backend/calibration.py` with:

| Field | Purpose |
|-------|---------|
| `name` | Unique identifier (e.g., `SEVERITY_WEIGHT:PRODUCER_INVERSION`) |
| `value` | The threshold value |
| `module` | Origin module (`severity` or `governance`) |
| `calibration_class` | EMPIRICAL / SEMI_EMPIRICAL / HEURISTIC / STRUCTURAL_NORMATIVE |
| `evidence_basis` | What justifies this value |
| `sensitivity_note` | What happens if perturbed ±10-20% |
| `upgrade_path` | What would need to happen to improve calibration |
| `falsifiable_by` | What evidence would change this threshold |

### Calibration Classes

| Class | Meaning | Count |
|-------|---------|-------|
| **EMPIRICAL** | Derived from data with documented reproducible procedure | 0 |
| **SEMI_EMPIRICAL** | Informed by data but with judgmental component in magnitude | ~12 |
| **HEURISTIC** | Expert judgment, not directly calibrated to data | ~18 |
| **STRUCTURAL_NORMATIVE** | Design choice that defines the construct | ~8 |

**Honesty note:** Zero thresholds are classified as EMPIRICAL. This is correct. No threshold in the current system has a fully reproducible empirical calibration procedure. Labeling anything as EMPIRICAL would be dishonest.

### Key Threshold Inventory

#### Severity Weights (backend/severity.py)

| Weight | Value | Class | Evidence Summary |
|--------|-------|-------|-----------------|
| HS6_GRANULARITY | 0.2 | SEMI_EMPIRICAL | EU-27 CN8→HS6 shows <5% HHI deviation |
| TEMPORAL_MISMATCH | 0.3 | HEURISTIC | Judgment: bilateral trade has high year-on-year autocorrelation |
| SINGLE_CHANNEL_A/B | 0.4 | SEMI_EMPIRICAL | Channel loss narrows construct ~40-60% |
| SOURCE_HETEROGENEITY | 0.4 | HEURISTIC | Cross-source compositing reduces interpretability |
| CPIS_NON_PARTICIPANT | 0.5 | SEMI_EMPIRICAL | Eliminates portfolio investment — halves financial construct |
| ZERO_BILATERAL_SUPPLIERS | 0.6 | STRUCTURAL_NORMATIVE | Construct ambiguity: 0.0 HHI ≠ low concentration |
| PRODUCER_INVERSION | 0.7 | STRUCTURAL_NORMATIVE | Construct inapplicable for major exporters |
| SANCTIONS_DISTORTION | 1.0 | STRUCTURAL_NORMATIVE | Crisis-regime data, never comparable |

#### Severity Tier Boundaries

| Tier | Threshold | Class | Note |
|------|-----------|-------|------|
| TIER_1 | < 0.5 | HEURISTIC | Permits one moderate flag |
| TIER_2 | < 1.5 | HEURISTIC | Wide middle band by design |
| TIER_3 | < 3.0 | HEURISTIC | Compound severe issues |
| TIER_4 | ≥ 3.0 | HEURISTIC | Beyond interpretive recovery |

#### Governance Confidence Baselines

| Axis | Baseline | Class | Source Quality |
|------|----------|-------|---------------|
| 1. Financial | 0.75 | SEMI_EMPIRICAL | BIS+CPIS dual-channel, ~30 reporters |
| 2. Energy | 0.80 | SEMI_EMPIRICAL | Comtrade HS27, broad coverage |
| 3. Technology | 0.80 | SEMI_EMPIRICAL | Comtrade HS8541/8542, HS6 risk |
| 4. Defense | 0.55 | SEMI_EMPIRICAL | SIPRI TIV, narrow scope, lumpy |
| 5. Critical Inputs | 0.75 | SEMI_EMPIRICAL | Comtrade CRM chapters |
| 6. Logistics | 0.60 | HEURISTIC | Mixed sources, weakest axis |

No baseline exceeds 0.90. Defense at 0.55 is the lowest — reflecting SIPRI's inherent narrow scope.

#### Governance Composite Eligibility

| Threshold | Value | Class |
|-----------|-------|-------|
| Min axes for composite | 4 | STRUCTURAL_NORMATIVE |
| Min axes for ranking | 5 | STRUCTURAL_NORMATIVE |
| Min mean confidence for ranking | 0.45 | HEURISTIC |
| Max low-confidence axes for ranking | 2 | HEURISTIC |
| Max inverted axes for comparable | 2 | STRUCTURAL_NORMATIVE |
| Composite defensibility floor | 0.30 | HEURISTIC |

---

## 3. Falsifiability Framework (Task 3)

Every governance mechanism has explicit criteria for what evidence would **support**, **weaken**, or **falsify** it.

### Producer-Inversion Registry

- **Support:** Country's net export position on relevant commodity is positive and substantial (>20% global market)
- **Weaken:** Export dominance declining below 10%; import concentration actually high (>0.3)
- **Falsify:** Expert panel shows country IS strategically vulnerable despite export position; historical crisis proves export dominance didn't protect against supply disruption

### Governance Tier Rules

- **Support:** Output quality degrades monotonically across tiers; face-valid for reference countries
- **Weaken:** PARTIALLY and FULLY countries have indistinguishable output quality
- **Falsify:** No correlation between tier and output quality/stability; expert panel consistently disagrees

### Axis Confidence Model

- **Support:** Baselines reflect known source coverage; penalties are monotonic
- **Weaken:** Penalties are additive but issues may interact non-linearly; baselines don't account for country-specific coverage
- **Falsify:** Confidence scores show no correlation with output reliability; additive model produces systematically wrong orderings

### Composite Eligibility Rules

- **Support:** Fewer axes → higher rank volatility; mean confidence floor ensures minimum quality
- **Weaken:** Specific thresholds (4, 5, 0.45, 2) are round-number heuristics
- **Falsify:** No difference between 3-axis and 5-axis composites in rank stability

---

## 4. Circularity Audit (Task 4)

### Data Flow (Strictly Linear)

```
1. Data Ingestion (pipeline/)
   → Validated bilateral records + data_quality_flags
   
2. Axis Computation (backend/axis_result.py)  
   → AxisResult objects (HHI scores, flags, validity)
   
3. Severity Assessment (backend/severity.py)
   → total_severity, comparability_tier
   
4. Governance Assessment (backend/governance.py)
   → governance_tier, axis_confidences, eligibility flags
   
5. Export Gating (backend/export_snapshot.py)
   → Gated JSON exports
```

**Circularity status: NONE.** No downstream stage feeds back into an upstream stage. Governance does NOT modify scores — it governs interpretation only.

### Known Design Tension

The governance module uses **additive penalties** for axis confidence, while the severity module uses **degradation-group MAX** for the same flags. This is intentional:

- **Severity** (group-MAX): Prevents double-counting the SAME underlying degradation
- **Confidence** (additive): Multiple independent quality issues DO compound for epistemic confidence

This is a defensible but debatable design choice, explicitly documented here.

---

## 5. Per-Axis Calibration Notes (Task 5)

Each axis has detailed calibration notes in `backend/calibration.py` covering:
- Source coverage and quality
- Known gaps
- Construct validity (what is measured, what is NOT measured)
- Sensitivity to specific penalties
- Falsifiable claims

### Summary of Falsifiable Claims

| Axis | Claim | Falsifiable By |
|------|-------|---------------|
| 1. Financial | BIS+CPIS captures >60% of bilateral financial exposure | Compare with national BoP bilateral breakdowns |
| 2. Energy | Comtrade HS27 captures >75% of bilateral energy trade | Compare with IEA bilateral energy statistics |
| 3. Technology | HS6 captures same concentration as CN8 for >75% of countries | Compare HS6 vs CN8 HHI for EU-27 |
| 4. Defense | SIPRI TIV captures >50% of bilateral arms transfer value | Compare with national defense procurement reports |
| 5. Critical Inputs | Comtrade captures >70% of bilateral critical input flows | Compare with USGS/EU CRM studies |
| 6. Logistics | Maritime data captures >60% of bilateral freight for coastal countries | Compare with national transport statistics |

---

## 6. Country Eligibility Registry (Tasks 6-7)

### Who Can Be Confidently Compiled and Rated NOW?

#### CONFIDENTLY_RATEABLE

Large and medium EU members without producer inversions, plus UK, JP, KR:

IT, ES, NL, PL + AT, BE, CZ, DK, FI, EL, HU, IE, PT, RO, SE, SK + UK, JP, KR

**These countries have:** comprehensive Comtrade data, BIS LBS reporting, CPIS participation, no producer inversions on critical axes. Data architecture supports meaningful comparison.

#### RATEABLE_WITH_CAVEATS

- **FR, DE**: Large EU, but defense axis producer-inverted
- **NO**: Energy axis producer-inverted
- **Small EU**: BG, CY, EE, HR, LT, LU, LV, MT, SI (sparse SIPRI, logistics gaps)
- **BR, IN, ZA**: Good data but partial BIS coverage, logistics gaps
- **SA**: Energy inversion, partial BIS

#### PARTIALLY_RATEABLE

- **AU**: 2 producer inversions (energy + critical inputs) → LOW_CONFIDENCE
- **CN**: CPIS non-participant + 2 inversions (defense + critical inputs)
- **US**: 3 producer inversions (energy, defense, critical inputs) → NON_COMPARABLE

**The US is NOT confidently rateable by ISI.** With 3 producer-inverted axes, the ISI construct measures the wrong thing for the US on half its dimensions. This is not a data problem — it is a construct limitation.

#### NOT_CURRENTLY_RATEABLE

- **RU**: Sanctions distortion (post-2022) + 3 producer inversions. Double structural disqualification.

### Honesty Note

"Confidently rateable" means the data sources and construct are appropriate for comparison. It does NOT mean the ISI score is "correct" in any absolute sense. All ISI outputs remain estimates with documented uncertainty.

---

## 7. Sensitivity Analysis (Task 8)

`run_sensitivity_analysis()` in `backend/calibration.py` perturbs governance thresholds by ±15% (configurable) and measures:

- How many country-axis combinations change confidence levels
- How many countries change ranking eligibility
- How governance tier boundaries shift

This is a **static analysis** — it does not re-run the full pipeline. It simulates threshold changes against existing governance outputs.

### What It Reveals

- Which thresholds are "consequential" (many countries near the boundary)
- Which are "stable" (few countries affected by perturbation)
- Whether the governance model is robust or fragile to threshold choice

---

## 8. External Benchmark Hooks (Task 9)

Four external benchmarks are registered for future integration:

| Benchmark | Source | ISI Axis | Status |
|-----------|--------|----------|--------|
| EU CRM Supply Study | EU Commission | 5 (Critical Inputs) | NOT_INTEGRATED |
| IEA Energy Security | IEA | 2 (Energy) | NOT_INTEGRATED |
| SIPRI MILEX | SIPRI | 4 (Defense) | NOT_INTEGRATED |
| BIS Consolidated Banking | BIS | 1 (Financial) | NOT_INTEGRATED |

**All benchmarks are NOT_INTEGRATED.** This is honest. The infrastructure exists for future validation, but no external validation has been performed. Declaring benchmarks as "available" without integration would be misleading.

---

## 9. Governance Explanation Object (Task 10)

`build_governance_explanation()` in `backend/calibration.py` creates an enhanced explanation object that includes:

- Governance tier with plain-language meaning
- Per-axis calibration quality (baseline class, construct validity, falsifiable claim)
- Calibration disclosure (what fraction of thresholds are heuristic)
- Country eligibility class and rationale
- Falsifiability reference
- Explicit honesty statement

Every user-facing output can now carry not just what the governance tier IS, but WHY it is what it is, and what level of confidence the system itself has in its own assessment.

---

## 10. Pseudo-Rigor Self-Audit (Task 13)

### Identified Risks

| Risk | Residual Level |
|------|---------------|
| Confidence scores look precise but are heuristic | MEDIUM |
| Governance tiers suggest objective classification | MEDIUM |
| Severity weights suggest calibrated measurement | LOW |
| Country eligibility creates false binary | LOW |
| Composite thresholds are round numbers | LOW |
| Thoroughness of documentation creates false confidence | MEDIUM |
| **Falsifiability criteria exist but are not tested** | **HIGH** |

### Highest Priority Action

> Declared falsifiability without testing is performative. Integrating at least one external benchmark (EU CRM or IEA energy) is the single highest-priority action item for upgrading from "structurally honest" to "empirically grounded."

### Overall Assessment

The system has **strong structural honesty** — every threshold is labeled, every mechanism has falsification criteria, every country has an explicit eligibility classification. But it has **weak empirical grounding** — no external benchmarks are integrated, no output validation against expert panels has been conducted. This is HONEST but NOT YET EMPIRICALLY ANCHORED.

---

## 11. Governing Principle

> If the output looks rigorous but rests on hidden arbitrary thresholds, the system has failed. If the output looks rigorous and ACKNOWLEDGES that its thresholds are heuristic, the system is honest. Honest is the minimum. Empirically anchored is the goal.

Thoroughly documented uncertainty is still uncertainty. Documentation ≠ precision.

---

## 12. Audit Trail

| Date | Change | Tests |
|------|--------|-------|
| 2025 | Initial calibration + falsifiability framework — threshold registry, falsifiability criteria, circularity audit, per-axis calibration notes, country eligibility registry, sensitivity analysis, external benchmarks, governance explanation, pseudo-rigor audit | 87 tests |

---

## 13. Module Reference

| Module | Purpose |
|--------|---------|
| `backend/calibration.py` | Calibration registry, falsifiability framework, country eligibility, sensitivity analysis, explanation objects, self-audit |
| `backend/governance.py` | Governance model (now with calibration annotations) |
| `backend/severity.py` | Severity model (thresholds registered in calibration) |
| `tests/test_calibration_falsifiability.py` | 87 tests covering all 13 tasks |
| `docs/CALIBRATION_AND_FALSIFIABILITY.md` | This document |
| `docs/GOVERNANCE_MODEL.md` | Governance model documentation (predecessor) |
