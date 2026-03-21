# ISI GLOBAL EXPANSION — ENGINEERING & METHODOLOGY CONSTRAINT SPECIFICATION

> **Document Class:** Binding constraint specification
>
> **Scope:** All ISI computation, data handling, pipeline engineering, and output generation
>
> **Effective:** 2026-03-21
>
> **Supersedes:** Developer discretion on all matters covered herein
>
> **Enforcement:** Violation of any requirement in this document invalidates affected outputs

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Core Principles](#2-core-principles)
3. [Prohibited Practices](#3-prohibited-practices)
4. [Data Requirements](#4-data-requirements)
5. [Axis Validity Framework](#5-axis-validity-framework)
6. [Global Expansion Rules](#6-global-expansion-rules)
7. [Known Structural Limitations](#7-known-structural-limitations)
8. [Computation Rules](#8-computation-rules)
9. [Output Requirements](#9-output-requirements)
10. [Failure Conditions](#10-failure-conditions)
11. [Version Control](#11-version-control)
12. [Enforcement](#12-enforcement)

---

## 1. Purpose

### 1.1 Binding Status

This document is a binding constraint specification. It governs all engineering decisions, methodology implementations, and data processing operations within the International Sovereignty Index system.

This document overrides:

- Developer intuition
- Ad hoc problem-solving
- Convenience-driven design decisions
- Performance optimizations that alter outputs
- Any undocumented practice, regardless of precedent

### 1.2 Threat Model

This specification exists to prevent:

| Threat | Description |
|--------|-------------|
| **Silent methodology drift** | Incremental changes to computation logic that cumulatively alter the construct being measured, without formal methodology versioning |
| **Inconsistent data handling** | Application of different transformation rules, fallback logic, or coverage standards to different countries, axes, or time periods |
| **Non-deterministic outputs** | Any condition where identical inputs produce differing outputs across runs, environments, or pipeline versions |
| **Implicit assumption embedding** | Introduction of unstated assumptions into code (weighting choices, imputation strategies, edge-case handlers) that alter results without explicit declaration |
| **Comparability erosion** | Changes that make scores produced under one scope or version non-comparable to scores produced under another, without formal declaration of incomparability |

### 1.3 Audience

This specification is addressed to:

- Pipeline engineers modifying ingestion, computation, or export code
- Data engineers adding new sources or countries
- Reviewers assessing pull requests that touch any ISI computation path
- Any automated system generating or transforming ISI artifacts

---

## 2. Core Principles

These principles are non-negotiable. No exception mechanism exists for principles P-1 through P-5.

### P-1 — Determinism

**Requirement:** Given identical input artifacts, the pipeline MUST produce byte-identical output artifacts across all runs, environments, and platforms.

**Constraints:**

- No stochastic processes at any stage (no random sampling, no Monte Carlo, no probabilistic imputation)
- No floating-point operations whose ordering is platform-dependent (aggregation order MUST be fixed)
- Sorting MUST use a deterministic tie-breaking rule (alphabetical by country code, then by axis number)
- Rounding MUST use Python `round()` (banker's rounding / round-half-to-even) at precision 8
- Rounding MUST occur exactly once per value, at the earliest point of finalization
- Hash computation MUST use canonical float formatting (fixed-point, 8 decimal places)

**Verification:** SHA-256 hashes of all output files MUST be reproducible given the same input file set.

### P-2 — Transparency

**Requirement:** Every transformation from raw input to final output MUST be traceable through code and documented in output metadata.

**Constraints:**

- No implicit type conversions that alter precision
- No implicit filtering (every row exclusion MUST be logged or counted)
- No implicit defaults (every parameter MUST have an explicit declaration in code or configuration)
- Every fallback path MUST produce a visible flag in the output (`basis`, `coverage`, or `warnings` field)
- Source file paths and column names MUST be declared as constants, not constructed dynamically from user input

### P-3 — Structural Consistency

**Requirement:** ISI measures geographic concentration of bilateral flows. Every axis MUST operate on the same mathematical construct.

**Invariants:**

- ISI measures **concentration**, not volume, not importance, not quality, not risk
- The unit of measurement is the Herfindahl-Hirschman Index (HHI) computed over partner share vectors
- A share vector is a set of non-negative values summing to 1.0 (within tolerance 1e-9), where each element represents one bilateral partner's fraction of the total
- HHI ∈ [0.0, 1.0] — hard bounds, enforced by assertion
- A higher HHI indicates higher concentration on fewer partners
- A higher ISI composite indicates higher overall bilateral dependency concentration

**No axis may measure a different construct.** If a proposed data source cannot produce a partner → share → HHI pipeline, it is incompatible with ISI methodology.

### P-4 — No Silent Degradation

**Requirement:** Missing, incomplete, or degraded data MUST be explicitly flagged in outputs. No fallback may execute without producing a visible marker.

**Constraints:**

- If Channel B data is unavailable, `basis` MUST be set to `A_ONLY`
- If an axis cannot be computed, it MUST be excluded from the composite AND listed in the output's `excluded_axes` field
- If partner coverage is incomplete (known partners excluded), a `coverage` field MUST state the estimated coverage percentage or `UNKNOWN`
- If data quality is structurally compromised (sanctions distortion, reporting suspension, methodology inversion), a `warnings` array MUST contain a specific warning code and human-readable description
- No output field may contain a silently imputed value

### P-5 — Source Fidelity

**Requirement:** Raw data MUST NOT be altered beyond the minimum transformations required to produce a share vector.

**Permitted transformations:**

| Transformation | Condition |
|---------------|-----------|
| Country code remapping (e.g., `GR` → `EL`) | Documented in a static mapping table |
| Currency conversion for share computation | Not applicable — shares are unit-invariant within a single reporter |
| Row filtering (self-pairs, aggregates, confidential codes) | Exclusion rule documented as constant |
| Period alignment (e.g., `202452` → `2024`) | Documented mapping |
| Unit normalization within a single fuel/mode/category | Only if required for intra-reporter share computation |

**Prohibited transformations:**

| Transformation | Reason |
|---------------|--------|
| Cross-country normalization | Alters the concentration measure |
| Temporal interpolation | Introduces estimated data |
| Mirror data substitution without flag | Hides data provenance |
| Value imputation for missing partners | Fabricates bilateral relationships |
| Outlier trimming or winsorization | Alters empirical distribution |

---

## 3. Prohibited Practices

Each prohibition is identified by a code (PRO-NNN), a description, a rationale for why it violates ISI integrity, and the consequence of violation.

### PRO-001 — Imputation of Missing Partner Data

**Description:** Estimating, interpolating, or guessing values for bilateral partners not present in the source data.

**Violation mechanism:** Introduces fictitious bilateral relationships into the share vector. HHI computed over a fabricated share vector does not measure empirical concentration.

**Consequence:** Any axis score computed using imputed partner data is INVALID. The country's composite score is INVALID if the imputed axis was included.

### PRO-002 — Gap-Filling With Averages

**Description:** Replacing missing values with mean, median, or other aggregate statistics derived from other countries, other years, or other axes.

**Violation mechanism:** Conflates the concentration profile of one country with the statistical properties of a group. Destroys the bilateral specificity that HHI requires.

**Consequence:** Same as PRO-001.

### PRO-003 — Cross-Year Partner Mixing

**Description:** Combining partner-level data from different reference years within the same axis computation without explicit documentation and methodology versioning.

**Violation mechanism:** A share vector mixing 2022 partners with 2024 partners does not represent any real point-in-time bilateral structure. Concentration measured over such a vector is temporally incoherent.

**Consequence:** Axis score is DEGRADED. Must be flagged with warning code `W-TEMPORAL-MIX` and the specific years involved.

### PRO-004 — Partial Partner Lists Without Coverage Flags

**Description:** Computing HHI from an incomplete partner list (known partners excluded due to confidentiality, data gaps, or filtering) without declaring the coverage gap.

**Violation mechanism:** HHI over a subset of partners may be higher or lower than HHI over the full set, depending on the distribution of excluded partners. Without a coverage flag, the user cannot assess reliability.

**Consequence:** Axis output MUST include `coverage` field. If coverage is below 80% of total value, axis MUST be labeled `DEGRADED`.

### PRO-005 — Ad Hoc Weight Introduction

**Description:** Introducing axis weights, partner weights, or channel weights that differ from the methodology specification to "correct" perceived anomalies in results.

**Violation mechanism:** ISI v1.0 specifies unweighted arithmetic mean of 6 axes, with equal 0.5/0.5 cross-channel weighting. Any weight change constitutes a methodology change and MUST be versioned as such.

**Consequence:** If weights differ from the registered methodology version, all outputs produced under those weights are INVALID under that version label.

### PRO-006 — Formula Modification for Edge Cases

**Description:** Altering the HHI formula, composite formula, or classification thresholds to handle specific countries or data configurations.

**Violation mechanism:** Country-specific formula variants destroy cross-country comparability. The ISI's value proposition depends on identical mathematical treatment of all countries.

**Consequence:** Any country processed with a modified formula MUST be excluded from comparative analysis with countries processed under the standard formula. If the modification is not declared, all outputs are INVALID.

### PRO-007 — Hidden Fallback Logic

**Description:** Implementing fallback behavior (e.g., substituting Channel A for Channel B, using mirror data, defaulting to zero) without producing a visible output flag.

**Violation mechanism:** Downstream consumers cannot distinguish between a measured value and a fallback value. Analysis built on such outputs may draw incorrect conclusions about bilateral structure.

**Consequence:** Outputs missing required fallback flags are INVALID. The `basis` field MUST reflect the actual computation path taken.

### PRO-008 — Country-Specific Logic

**Description:** Implementing conditional branches in computation code that execute different logic based on country code (e.g., `if country == "CN": use_alternative_formula()`).

**Violation mechanism:** Destroys methodological uniformity. If Country A is processed differently from Country B, their scores are not comparable.

**Consequence:** Any country-specific branch in computation code (excluding country code remapping in parsers) renders the affected outputs INVALID.

**Exception:** Parser-level country code remapping tables (e.g., `GR` → `EL`, SIPRI name → ISO-2) are permitted because they normalize inputs to a common schema before computation begins.

### PRO-009 — Manual Output Overrides

**Description:** Manually editing, patching, or overriding computed output values after pipeline execution.

**Violation mechanism:** Breaks the deterministic chain from input to output. Invalidates integrity hashes. Makes reproduction impossible.

**Consequence:** Any manually altered output file is INVALID. Integrity verification will fail (SHA-256 mismatch).

### PRO-010 — Undocumented Source Substitution

**Description:** Replacing a registered data source with an alternative source without updating the methodology registry and output metadata.

**Violation mechanism:** Source differences (coverage, methodology, classification, time window) alter the construct being measured. A score computed from UN Comtrade and a score computed from Eurostat Comext measure slightly different things due to HS6/CN8 granularity differences, coverage discrepancies, and value reporting conventions.

**Consequence:** Outputs produced from unregistered sources are INVALID under the methodology version that specifies the original source.

---

## 4. Data Requirements

### 4.1 Universal Input Requirements

Every axis computation REQUIRES the following input structure:

| Field | Requirement |
|-------|-------------|
| **Reporter** | ISO-2 country code identifying the importing country |
| **Partner** | ISO-2 country code (or standardized partner identifier) identifying the bilateral counterpart |
| **Value** | Non-negative numeric value representing the magnitude of the bilateral flow |
| **Period** | Year or quarter identifying the temporal reference |
| **Flow direction** | Must be imports (inward flows to the reporter). Exports are excluded from ISI computation |

### 4.2 Share Vector Requirements

For each reporter, the set of (partner, value) pairs MUST satisfy:

| Constraint | Rule | Tolerance |
|-----------|------|-----------|
| Non-negativity | All values ≥ 0 | Exact |
| Total > 0 | Sum of values for reporter MUST be positive | Exact (zero-total reporters are excluded) |
| Share computation | $s_{i,j} = v_{i,j} / \sum_k v_{i,k}$ | — |
| Share sum | $\sum_j s_{i,j} = 1.0$ | ±1e-9 |
| No self-pairs | Reporter ≠ Partner | Exact |

### 4.3 Axis-Specific Requirements

| Axis | Minimum Partner Count | Special Requirements |
|------|----------------------|---------------------|
| 1 — Financial | ≥ 2 creditor countries (Ch A) or ≥ 2 investor countries (Ch B) | BIS LBS counterparty perspective; CPIS investor perspective |
| 2 — Energy | ≥ 2 supplier countries per fuel type | At least 2 of 3 fuel types (gas, oil, solid fossil) must have data |
| 3 — Technology | ≥ 2 supplier countries | HS 8541 + 8542 import flows only |
| 4 — Defence | ≥ 1 supplier country | Zero-supplier case → score = 0.0 (domestic production), flagged as `D-5` |
| 5 — Critical Inputs | ≥ 2 supplier countries | All mapped CN8/HS6 codes; ≥ 3 of 5 material groups must have data |
| 6 — Logistics | ≥ 2 transport modes (Ch A) or ≥ 2 partner countries per mode (Ch B) | Channel A = mode concentration; Channel B = partner concentration per mode |

### 4.4 Failure Conditions

| Condition | Consequence |
|-----------|------------|
| No partner-level breakdown available for a given axis | Axis is **INVALID** for that country |
| Partner coverage below 50% of total value (known exclusions) | Axis is **INVALID** |
| Partner coverage between 50% and 80% of total value | Axis is **DEGRADED** — included in composite but flagged |
| Mixed time windows (partners from different years without declared policy) | Axis is **INVALID** unless PRO-003 exception is formally declared |
| Share vector does not sum to 1.0 within tolerance | Pipeline MUST abort — hard failure |
| HHI outside [0.0, 1.0] | Pipeline MUST abort — hard failure |
| Total bilateral value ≤ 0 for a reporter | Reporter excluded from that axis |

---

## 5. Axis Validity Framework

### 5.1 Validity Labels

Each axis for each country MUST be assigned exactly one validity label:

| Label | Definition | Composite Inclusion |
|-------|-----------|-------------------|
| **VALID** | Both channels computed from registered sources with full partner coverage | YES |
| **A_ONLY** | Single-channel computation due to Channel B data absence. Score = Channel A concentration | YES (flagged) |
| **DEGRADED** | Structural limitation affects interpretability: methodology inversion (exporter scored on imports), partial coverage (50–80%), or data quality compromise | YES (flagged) |
| **INVALID** | Cannot be computed: no partner data, coverage below 50%, data source unavailable, or sanctions-distorted beyond reliability | NO — excluded from composite |

### 5.2 Assignment Rules

| Condition | Label |
|-----------|-------|
| Both channels present, coverage ≥ 80%, no structural issues | VALID |
| Channel A present, Channel B absent, coverage ≥ 80% | A_ONLY |
| Any channel present, coverage 50–80% | DEGRADED |
| Country is a dominant exporter of the measured commodity (top-5 global exporter by value) and the axis measures import concentration | DEGRADED + warning `W-PRODUCER-INVERSION` |
| BIS reporting suspended or CPIS non-participant (Axis 1, Channel B) | A_ONLY for Channel B absence |
| Sanctions regime distorts trade data during measurement window | DEGRADED or INVALID depending on severity assessment |
| No bilateral partner data available | INVALID |
| Coverage below 50% | INVALID |

### 5.3 Composite Eligibility

A country's ISI composite MAY be computed if and only if:

$$N_{\text{computable}} = N_{\text{VALID}} + N_{\text{A\_ONLY}} + N_{\text{DEGRADED}} \geq 4$$

The composite formula for a country with $N_{\text{computable}}$ valid axes:

$$\text{ISI}_i = \frac{\sum_{a \in \text{computable}} A_{i,a}}{N_{\text{computable}}}$$

**Additional constraint:** A country with more than 2 DEGRADED axes MUST be flagged as `LOW_CONFIDENCE` in the output, even if $N_{\text{computable}} \geq 4$.

### 5.4 Composite Denominator Rule

The composite denominator is the number of **included** axes, not a fixed 6. If a country has 5 computable axes (1 INVALID excluded), the composite is the mean of 5 scores.

**This is a methodology change from v1.0** (which requires exactly 6 axes). It MUST be registered as such in the methodology version that introduces global expansion.

---

## 6. Global Expansion Rules

### 6.1 Scope Abstraction

**REQUIREMENT:** All references to `EU27_CODES`, `EU27_SORTED`, or any hardcoded 27-country set in pipeline scripts and backend code MUST be replaced with a configurable scope parameter.

**Implementation constraints:**

| Constraint | Rule |
|-----------|------|
| Scope definition | A frozen set of ISO-2 country codes, loaded from a configuration file or registry |
| Scope validation | Every script MUST validate that all expected countries are present in input data, and reject unexpected countries |
| Scope count assertion | Current `assert len(countries) == 27` style checks MUST be replaced with `assert len(countries) == len(SCOPE_CODES)` |
| Scope isolation | Different scopes (EU-27, EU-27+expansion, custom) MUST produce outputs in separate directory trees |
| Scope declaration | Every output artifact MUST include a `scope` field listing the country set used |

### 6.2 New Data Source Requirements

Any data source introduced for global expansion MUST satisfy:

| Requirement | Test |
|-------------|------|
| Partner-level bilateral data | Source provides reporter × partner × value triples |
| Reproducible access | Source can be re-downloaded or re-extracted to produce identical data |
| Schema compatibility | Data can be transformed into `reporter, partner, value, period` without estimation |
| Temporal alignment | Data covers the ISI measurement window (2022–2024) or a declared alternative window |
| Coverage declaration | The set of reporters and partners covered by the source MUST be documented |
| Granularity compatibility | Product/commodity classification must map to ISI axis definitions without ambiguity, or mapping must be explicitly declared |

### 6.3 Pipeline Uniformity

**REQUIREMENT:** The same computation code MUST process all countries in a given scope.

| Rule | Implication |
|------|------------|
| No country-specific branches in computation | One code path for all reporters |
| Parser-level adaptation permitted | Different parsers for Comext vs Comtrade are permitted because they normalize to the same intermediate schema |
| Intermediate schema invariant | After parsing, all data MUST conform to the same column structure regardless of source |
| Same HHI formula for all countries | No per-country formula variants |
| Same classification thresholds for all countries | No per-country threshold adjustments |
| Same rounding rules for all countries | ROUND_PRECISION = 8, banker's rounding, applied once |

### 6.4 Axis Equivalence Constraint

**REQUIREMENT:** A global axis MUST measure the same construct as the corresponding EU-27 axis.

| Axis | Construct | Equivalence Test |
|------|-----------|-----------------|
| 1 — Financial | Concentration of foreign financial claims on the reporter | Bilateral creditor share vector → HHI |
| 2 — Energy | Concentration of energy import suppliers | Bilateral energy import share vector per fuel → HHI → average across fuels |
| 3 — Technology | Concentration of semiconductor import suppliers | Bilateral semiconductor import share vector → HHI (aggregate + category-weighted) |
| 4 — Defence | Concentration of major arms import suppliers | Bilateral arms transfer share vector (TIV) → HHI (aggregate + capability-weighted) |
| 5 — Critical Inputs | Concentration of critical materials import suppliers | Bilateral critical materials import share vector → HHI (aggregate + group-weighted) |
| 6 — Logistics | Concentration of freight transport mode + partner structure | Mode share HHI + per-mode partner HHI → weighted average |

If a replacement data source changes the granularity (CN8 → HS6), the set of included products, or the partner universe in a way that alters the measured construct, this MUST be declared as a methodology variant and version-tagged accordingly.

---

## 7. Known Structural Limitations

Each limitation is assigned a code (LIM-NNN), a description, its implication for ISI scores, and the permitted handling.

### LIM-001 — Producer Penalty

**Description:** ISI measures import concentration. Countries that are dominant producers or exporters of a commodity class will have low or near-zero import volumes. Their HHI may be mechanically low (few imports) or undefined (zero imports).

**Affected axes and countries:**

| Axis | Affected Countries | Mechanism |
|------|-------------------|-----------|
| 2 — Energy | Russia, Saudi Arabia, Norway, Australia (partial) | Net energy exporter → minimal energy imports → low HHI |
| 4 — Defence | United States, Russia, China | Dominant domestic arms producer → minimal arms imports → HHI ≈ 0 |
| 5 — Critical Inputs | China, Russia, South Africa, Brazil, Australia | Dominant exporter of specific materials → low import concentration for those materials |

**Implication:** ISI composite scores for producer countries will be systematically lower than for consumer countries. Cross-group comparison (producer vs consumer) is methodologically problematic.

**Permitted handling:** Flag with warning `W-PRODUCER-INVERSION`. Label affected axis as `DEGRADED`. Do NOT modify the score, the formula, or the weighting to compensate.

### LIM-002 — Defence Import Asymmetry

**Description:** The defence axis measures import concentration of major conventional arms (SIPRI TIV). It does not measure domestic production capacity, licensed production, dual-use technology transfer, or small arms.

**Implication:** Countries with large domestic defence industries (US, Russia, China, France, UK) will score near-zero regardless of their actual defence dependency profile. A score of 0.0 on this axis means "does not import major conventional arms from foreign suppliers" — it does NOT mean "defence-independent."

**Permitted handling:** Flag with warning `D-5` (existing ISI warning for zero-supplier case). Label as `DEGRADED` if the country is a top-10 global arms exporter. Do NOT impute domestic production data.

### LIM-003 — Logistics Bilateral Data Gap

**Description:** No globally standardized source provides bilateral freight partner data (which country ships freight to/from reporter X, by transport mode) outside the Eurostat coverage area.

**Affected component:** Axis 6, Channel B (partner concentration per mode).

**Implication:** For non-EU countries, Channel B may be unavailable or fragmentary. Axis 6 will frequently operate in `A_ONLY` mode (Channel A = mode concentration only) for expansion countries.

**Permitted handling:** Use `A_ONLY` basis. If Channel B data is sourced from national statistics, declare the source explicitly. Do NOT construct synthetic bilateral partner data. Do NOT use trade value as a proxy for freight tonnage.

### LIM-004 — HS6 vs CN8 Granularity Loss

**Description:** EU-27 pipeline uses Eurostat CN8 (8-digit Combined Nomenclature). Global expansion pipeline uses UN Comtrade HS6 (6-digit Harmonized System). CN8 is a subdivision of HS6 — multiple CN8 codes may map to the same HS6 parent.

**Affected axes:** Axis 3 (Technology), Axis 5 (Critical Inputs).

**Implication for Axis 3:** The CN8 category mapping distinguishes 7 semiconductor subcategories. At HS6, this collapses to approximately 3 categories. Channel B (category-weighted HHI) will have fewer categories, potentially altering the score.

**Implication for Axis 5:** 66 CN8 codes map to approximately 40–50 HS6 codes. Material group assignments MUST be re-validated at HS6 level. Some groups may lose specificity.

**Permitted handling:** Create explicit HS6 mapping files. Document the exact CN8 → HS6 concordance. Flag any axis computed from HS6 data with warning `W-HS6-GRANULARITY`. Do NOT mix CN8-derived and HS6-derived scores in the same comparative analysis without declaration.

### LIM-005 — CPIS Non-Participation

**Description:** IMF Coordinated Portfolio Investment Survey participation is voluntary. China and Saudi Arabia do not participate. India and Russia have uncertain/incomplete participation.

**Affected axis:** Axis 1, Channel B (portfolio debt concentration).

**Implication:** Countries without CPIS data cannot compute Channel B. Axis 1 operates in `A_ONLY` mode, reflecting only banking claims concentration.

**Permitted handling:** `A_ONLY` basis. Flag with warning `F-CPIS-ABSENT`. Do NOT estimate portfolio debt from other sources.

### LIM-006 — Sanctions-Era Data Distortion

**Description:** Post-2022 economic sanctions against Russia have fundamentally altered trade patterns, financial flows, and data reporting. Official statistics from or about Russia during 2022–2024 may be incomplete, delayed, or non-representative of steady-state conditions.

**Affected country:** Russia (primary). Secondary effects on countries with significant Russia trade.

**Implication:** Any ISI score computed for Russia using 2022–2024 data reflects a sanctions-distorted regime, not a normal bilateral structure. Scores are technically computable for some axes but are not comparable to scores computed for non-sanctioned countries.

**Permitted handling:** If Russia is included, ALL axes MUST carry warning `W-SANCTIONS-DISTORTION`. The composite MUST be flagged as `LOW_CONFIDENCE`. Do NOT attempt to "correct" for sanctions effects.

---

## 8. Computation Rules

### 8.1 HHI Computation

$$C_i = \sum_{j} s_{i,j}^2$$

where:

- $i$ = reporter country
- $j$ = partner country
- $s_{i,j}$ = partner $j$'s share of reporter $i$'s total bilateral flow

**Constraints:**

| Rule | Specification |
|------|--------------|
| Share computation | $s_{i,j} = v_{i,j} / \sum_k v_{i,k}$ |
| Self-pair exclusion | $j \neq i$ — enforced before share computation |
| Aggregate code exclusion | World totals, regional aggregates, and confidential partner codes MUST be excluded before share computation |
| Share validation | $\sum_j s_{i,j} \in [1 - 10^{-9}, 1 + 10^{-9}]$ — hard assertion |
| HHI bounds | $C_i \in [0.0, 1.0]$ — hard assertion with tolerance $10^{-9}$ |

### 8.2 Cross-Channel Aggregation

For dual-channel axes:

$$M_i = \frac{C_i^{(A)} \cdot W_i^{(A)} + C_i^{(B)} \cdot W_i^{(B)}}{W_i^{(A)} + W_i^{(B)}}$$

By construction, $W^{(A)} = W^{(B)}$ for axes 1, 3, 4, 5. Therefore $M_i = 0.5 \cdot C_i^{(A)} + 0.5 \cdot C_i^{(B)}$.

**Axis 6 exception:** $W^{(A)} \neq W^{(B)}$ by design (IWW tonnage included in Channel A, excluded from Channel B). Volume-weighted formula applies.

**Fallback rules:**

| Condition | Score | Basis |
|-----------|-------|-------|
| Both channels present | $M_i$ as above | `BOTH` |
| Channel A present, Channel B absent | $C_i^{(A)}$ | `A_ONLY` |
| Channel B present, Channel A absent | $C_i^{(B)}$ | `B_ONLY` |
| Neither channel present | — | `INVALID` |

### 8.3 Composite Aggregation

For methodology v1.0 (EU-27):

$$\text{ISI}_i = \frac{1}{6} \sum_{a=1}^{6} A_{i,a}$$

All 6 axes MUST be present. No exceptions under v1.0.

For methodology v1.1+ (global expansion):

$$\text{ISI}_i = \frac{1}{N_{\text{computable}}} \sum_{a \in \text{computable}} A_{i,a}$$

where $N_{\text{computable}} \geq 4$ (Section 5.3).

### 8.4 Prohibited Computation Practices

| Practice | Status |
|----------|--------|
| Smoothing across countries | **PROHIBITED** |
| Normalization across countries (z-scores, min-max, etc.) | **PROHIBITED** |
| Composite reweighting (axis weights ≠ 1.0) | **PROHIBITED** under v1.0/v1.1. Requires new methodology version |
| Score clamping (beyond [0.0, 1.0] bounds enforcement) | **PROHIBITED** |
| Geometric mean as composite formula | **PROHIBITED** under v1.x |
| Rank-based scoring | **PROHIBITED** |

### 8.5 Rounding

| Parameter | Value |
|-----------|-------|
| Precision | 8 decimal places |
| Method | Python `round()` — banker's rounding (round-half-to-even) |
| Timing | Once, at earliest finalization point |
| Sequencing | Round → classify → sort → hash → serialize |

---

## 9. Output Requirements

### 9.1 Per-Axis Output

Every axis output for every country MUST include:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `axis_id` | integer | YES | Axis number (1–6) |
| `axis_slug` | string | YES | Canonical axis identifier |
| `score` | float | YES | HHI-based axis score, rounded to 8 decimals |
| `classification` | string | YES | Threshold-based label |
| `basis` | string | YES | `BOTH`, `A_ONLY`, `B_ONLY`, or `INVALID` |
| `validity` | string | YES | `VALID`, `A_ONLY`, `DEGRADED`, or `INVALID` |
| `coverage` | float or null | CONDITIONAL | Estimated coverage as fraction [0.0, 1.0]; null if full coverage confirmed |
| `source` | string | YES | Registered data source identifier |
| `warnings` | array | YES (may be empty) | List of warning codes with descriptions |
| `channel_a_concentration` | float or null | YES | Channel A HHI; null if unavailable |
| `channel_b_concentration` | float or null | YES | Channel B HHI; null if unavailable |

### 9.2 Composite Output

Every composite output for every country MUST include:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `isi_composite` | float | YES | Arithmetic mean of computable axes, rounded to 8 decimals |
| `classification` | string | YES | Threshold-based label |
| `axes_included` | integer | YES | Number of axes in composite denominator |
| `axes_excluded` | array | YES (may be empty) | List of axis IDs excluded from composite, with reason |
| `confidence` | string | YES | `FULL`, `REDUCED`, or `LOW_CONFIDENCE` |
| `scope` | string | YES | Scope identifier (e.g., `EU-27`, `GLOBAL-39`) |
| `methodology_version` | string | YES | Version tag (e.g., `v1.0`, `v1.1`) |
| `warnings` | array | YES (may be empty) | Country-level warnings |

### 9.3 Confidence Labels

| Label | Condition |
|-------|-----------|
| `FULL` | All 6 axes VALID or A_ONLY, 0 DEGRADED |
| `REDUCED` | $N_{\text{computable}} \geq 4$ and 1–2 DEGRADED axes, or $N_{\text{computable}} = 5$ |
| `LOW_CONFIDENCE` | $N_{\text{computable}} = 4$, or > 2 DEGRADED axes, or sanctions/distortion warnings present |

### 9.4 Audit Trail Output

Every pipeline run MUST produce:

| Artifact | Content |
|----------|---------|
| `run_manifest.json` | SHA-256 hashes of all input files, all output files, pipeline version, timestamp, scope |
| `validation_report.md` | Automated validation results: share sum checks, HHI bounds, coverage counts, axis validity summary |
| `HASH_SUMMARY.json` | Per-country SHA-256 hashes computed from canonical float representations |

---

## 10. Failure Conditions

### 10.1 Country Rejection Criteria

A country MUST be rejected (excluded from ISI output) if any of the following conditions hold:

| Code | Condition | Action |
|------|-----------|--------|
| **F-COV** | Fewer than 4 computable axes ($N_{\text{VALID}} + N_{\text{A\_ONLY}} + N_{\text{DEGRADED}} < 4$) | Country excluded entirely |
| **F-DEG** | More than 2 axes labeled DEGRADED | Country included but labeled `LOW_CONFIDENCE`; exclusion recommended |
| **F-SRC** | No registered data source available for ≥ 3 axes | Country excluded entirely |
| **F-SAN** | Active comprehensive sanctions regime affecting all bilateral data sources during measurement window | Country excluded or labeled `NON_COMPARABLE` |
| **F-MET** | Methodology cannot be applied cleanly (e.g., no bilateral partner data exists for any axis) | Country excluded entirely |

### 10.2 Axis Rejection Criteria

An axis MUST be labeled INVALID if:

| Condition | Threshold |
|-----------|-----------|
| No partner-level bilateral data available | Absolute |
| Total value ≤ 0 across all partners | Absolute |
| Partner coverage < 50% of known total | 50% |
| Share vector fails validation (does not sum to 1.0 within tolerance) | ±1e-9 |
| HHI falls outside [0.0, 1.0] | ±1e-9 |
| Data source is unregistered | Absolute |

### 10.3 Pipeline Abort Conditions

The pipeline MUST abort (terminate with non-zero exit code, no output produced) if:

| Condition |
|-----------|
| Any share vector sums to exactly 0.0 (division by zero) |
| Any HHI computation produces NaN or Inf |
| Any country code not in the declared scope appears in computation |
| Any output file fails SHA-256 verification against its computation |
| Input file manifest does not match expected file set |

---

## 11. Version Control

### 11.1 Immutability of v1.0

Methodology version v1.0 is frozen. The following are immutable:

| Component | Frozen Value |
|-----------|-------------|
| Scope | EU-27 (27 countries) |
| Axes | 6, all required |
| Aggregation | Unweighted arithmetic mean |
| Weights | All 1.0 |
| Classification thresholds | [0.50, 0.25, 0.15] |
| Rounding | 8 decimals, banker's rounding |
| Data sources | Eurostat Comext, BIS LBS, IMF CPIS, SIPRI, Eurostat energy, Eurostat transport |
| Snapshot | `snapshots/v1.0/2024/` — byte-immutable |

No retroactive changes to v1.0 are permitted. If an error is discovered in v1.0 data, it MUST be documented in an errata file, not corrected in the snapshot.

### 11.2 Global Expansion Versioning

Global expansion MUST be introduced under a new methodology version:

| Version | Scope | Changes from v1.0 |
|---------|-------|-------------------|
| v1.1 | EU-27 + Phase 1 (GB, JP, KR, NO, AU) | Configurable scope; UN Comtrade as additional source; HS6 mapping; variable axis count (4–6); A_ONLY/DEGRADED labeling |
| v1.2 | v1.1 + Phase 2 (US, BR, ZA, IN) | National transport data sources; expanded SIPRI recipient mapping |
| v1.3 | v1.2 + Phase 3 (CN, SA) | Producer-inversion handling; CPIS non-participant protocol |

Each version increment MUST be registered in `registry.json` with:

- `version` tag
- `frozen_at` timestamp
- `scope` (list of country codes)
- `axis_count` (required minimum)
- `sources` (registered data source list per axis)
- `known_limitations` (list of LIM codes applicable)

### 11.3 Backward Compatibility

Scores produced under v1.0 and scores produced under v1.1+ are NOT directly comparable due to:

1. Different data sources (Comext vs Comtrade)
2. Different granularity (CN8 vs HS6)
3. Variable composite denominator (fixed 6 vs variable 4–6)
4. Different country scope

Any comparative analysis across methodology versions MUST declare the version difference.

---

## 12. Enforcement

### 12.1 Violation Classification

| Severity | Definition | Consequence |
|----------|-----------|-------------|
| **CRITICAL** | Violation of Core Principles (P-1 through P-5) or Prohibited Practices (PRO-001 through PRO-010) | All outputs produced under the violating code are INVALID. Pipeline must be halted until corrected. |
| **MAJOR** | Violation of Data Requirements (Section 4), Computation Rules (Section 8), or Output Requirements (Section 9) | Affected outputs are INVALID. Non-affected outputs may remain valid if isolation is verifiable. |
| **MINOR** | Violation of labeling, flagging, or documentation requirements | Outputs are DEGRADED (not INVALID) but must be corrected before publication. |

### 12.2 Detection Mechanisms

| Mechanism | What It Catches |
|-----------|----------------|
| SHA-256 hash verification | Manual overrides (PRO-009), non-determinism (P-1) |
| Automated share-sum assertions | Invalid share vectors (Section 4.2) |
| HHI bounds assertions | Formula errors (Section 8.1) |
| Output schema validation | Missing required fields (Section 9) |
| Scope validation | Unexpected country codes (Section 6.1) |
| Regression test suite | Silent methodology drift |
| Source registry check | Undocumented source substitution (PRO-010) |

### 12.3 Exception Protocol

No exceptions to this specification are permitted without:

1. Written declaration of the specific section(s) being deviated from
2. Technical justification explaining why the deviation is necessary
3. Impact assessment on output comparability
4. Explicit listing of all outputs affected by the deviation
5. Version tag assignment for outputs produced under the deviation
6. Approval documented in the repository (commit message or dedicated file)

An undeclared deviation is a CRITICAL violation regardless of intent.

### 12.4 Document Authority

In case of conflict between this specification and any other document, code comment, or developer practice:

1. This specification takes precedence over code comments
2. This specification takes precedence over developer convention
3. This specification takes precedence over performance considerations
4. `registry.json` frozen values take precedence over this specification for parameters registered therein
5. If this specification conflicts with `registry.json`, the conflict MUST be resolved before any pipeline execution

---

*End of Constraint Specification.*
