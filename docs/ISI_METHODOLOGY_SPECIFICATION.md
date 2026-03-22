# ISI v1.1 — Degradation Severity, Comparability, and Aggregation: A Formal Methodology Specification

> **Document Class:** Publication-grade methodology specification
>
> **Companion to:** ISI Constraint Specification (binding engineering rules)
>
> **Scope:** ISI v1.1+ severity model, comparability framework, aggregation theory, and interpretation layer
>
> **Status:** Authoritative. All parameter choices, functional forms, and thresholds herein are either empirically justified or explicitly declared as normative.
>
> **Institutional-Grade Hardening:** This specification has been elevated to withstand IMF/BIS/OECD-level methodological scrutiny. All axiomatic foundations, formal definitions, non-goals, and limitations are explicitly declared.

---

## Table of Contents

1. [Formal Model Definitions](#1-formal-model-definitions)
2. [Severity System: Data Reliability and Structural Position](#2-severity-system-data-reliability-and-structural-position)
3. [Penalty Function Selection](#3-penalty-function-selection)
4. [Comparability Theory](#4-comparability-theory)
5. [Structural Class Model](#5-structural-class-model)
6. [Stability and Robustness](#6-stability-and-robustness)
7. [Interpretation Layer](#7-interpretation-layer)
8. [Limitations and Residual Risks](#8-limitations-and-residual-risks)
9. [Axiomatic Foundations](#9-axiomatic-foundations)
10. [Non-Goals and Explicit Exclusions](#10-non-goals-and-explicit-exclusions)
11. [Institutional-Grade Hardening: Model B Structural Constraints](#11-institutional-grade-hardening-model-b-structural-constraints)
12. [Sensitivity Analysis Framework](#12-sensitivity-analysis-framework)
13. [External Validation Layer](#13-external-validation-layer)
14. [Shock Simulation Framework](#14-shock-simulation-framework)
15. [Output Integrity Guarantees](#15-output-integrity-guarantees)

---

## 1. Formal Model Definitions

### 1.1 The ISI Construct

The International Sovereignty Index (ISI) measures the **geographic concentration of bilateral import flows** for a country $i$ across a set of strategic axes $\mathcal{A} = \{1, 2, \ldots, 6\}$. It does not measure volume, importance, quality, or risk. It measures **concentration** — the degree to which a country's imports on each strategic axis are distributed across or concentrated upon a small number of bilateral partners.

**Definition 1.1** (Axis Score). For country $i$ and axis $a$, the axis score $A_{i,a}$ is:

$$
A_{i,a} = \frac{w^{(A)} \cdot C_{i,a}^{(A)} + w^{(B)} \cdot C_{i,a}^{(B)}}{w^{(A)} + w^{(B)}}
$$

where $C_{i,a}^{(k)}$ is the Herfindahl-Hirschman Index (HHI) of channel $k \in \{A, B\}$:

$$
C_{i,a}^{(k)} = \sum_{j \in \mathcal{P}_{i,a}^{(k)}} \left( s_{i,j,a}^{(k)} \right)^2, \qquad s_{i,j,a}^{(k)} = \frac{v_{i,j,a}^{(k)}}{\sum_{m} v_{i,m,a}^{(k)}}
$$

with $\mathcal{P}_{i,a}^{(k)}$ the set of bilateral partners, $v_{i,j,a}^{(k)}$ the bilateral flow value from partner $j$ to reporter $i$ on axis $a$ via channel $k$, and $s_{i,j,a}^{(k)}$ the partner share satisfying $\sum_j s_{i,j,a}^{(k)} = 1$.

$A_{i,a} \in [0, 1]$. The weights satisfy $w^{(A)} = w^{(B)} = 0.5$ for axes 1–5 (equal cross-channel weighting). Axis 6 uses volume-weighted cross-channel aggregation.

**Fallback rules** (Section 8.2 of the Constraint Specification):

| Condition | $A_{i,a}$ | Basis |
|-----------|-----------|-------|
| Both channels present | Weighted mean | `BOTH` |
| Channel A only | $C_{i,a}^{(A)}$ | `A_ONLY` |
| Channel B only | $C_{i,a}^{(B)}$ | `B_ONLY` |
| Neither channel | undefined | `INVALID` |

### 1.2 Raw Composite

**Definition 1.2** (Raw Composite). For country $i$ with computable axis set $\mathcal{A}_i \subseteq \mathcal{A}$, $|\mathcal{A}_i| \geq 4$:

$$
\text{ISI}^{\text{raw}}_i = \frac{1}{|\mathcal{A}_i|} \sum_{a \in \mathcal{A}_i} A_{i,a}
$$

This is the unweighted arithmetic mean of all included axes. This formula is fixed under v1.1 methodology: no axis weights, no geometric mean, no rank-based scoring (Constraint Specification Section 8.4).

### 1.3 Severity Decomposition

Each axis score $A_{i,a}$ carries an associated **severity** value $\sigma_{i,a} \geq 0$ that quantifies the degree to which the data generating that score deviates from ideal measurement conditions. This severity is decomposed into two conceptually distinct layers:

$$
\sigma_{i,a} = \underbrace{\sigma_{i,a}^{\text{data}}}_{\text{Data Reliability}} + \underbrace{\sigma_{i,a}^{\text{structural}}}_{\text{Structural Position}}
$$

where:

- $\sigma_{i,a}^{\text{data}}$ reflects **data quality degradation** — issues with the measurement instrument (missing channels, granularity loss, temporal mismatch). These reduce our confidence that $A_{i,a}$ accurately measures what it intends to measure.

- $\sigma_{i,a}^{\text{structural}}$ reflects **structural position** — characteristics of the country's economic position that cause the ISI construct (import concentration) to be a poor proxy for the country's actual strategic exposure. Producer inversion is the canonical case.

**Critical distinction:** Data reliability severity affects **aggregation weights** because it reflects measurement quality. Structural severity affects **interpretation** but does NOT affect aggregation weights, because the score is measured correctly — it simply measures the wrong thing for that country-axis combination.

### 1.4 Adjusted Composite

**Definition 1.4** (Degradation-Adjusted Composite). Using data reliability severity only:

$$
\text{ISI}^{\text{adj}}_i = \frac{\sum_{a \in \mathcal{A}_i} A_{i,a} \cdot \omega(\sigma_{i,a}^{\text{data}})}{\sum_{a \in \mathcal{A}_i} \omega(\sigma_{i,a}^{\text{data}})}
$$

where $\omega: [0, \infty) \to [\omega_{\min}, 1]$ is a monotonically decreasing **quality weight function** (specified in Section 3).

**Explicit prohibition:** Structural severity MUST NOT enter the weight function. Setting $\omega_i = f(\sigma_{i,a}^{\text{data}})$ only ensures that the adjusted composite reflects measurement quality, not economic characteristics. A producer country whose axes are measured with perfect data quality receives full weight on all axes — the producer inversion is flagged in interpretation, not suppressed in aggregation.

### 1.5 Total Country Severity

**Definition 1.5** (Country Severity). The total severity for country $i$ is:

$$
\Sigma_i = \sum_{a \in \mathcal{A}_i} \sigma_{i,a}
$$

where $\sigma_{i,a} = \sigma_{i,a}^{\text{data}} + \sigma_{i,a}^{\text{structural}}$ is the full (data + structural) axis severity. Total severity is used for **comparability tier assignment** and **cross-country comparability guards**, where both data quality and structural position matter for whether scores are meaningfully comparable.

---

## 2. Severity System: Data Reliability and Structural Position

### 2.1 Design Rationale

ISI data quality issues fall into two fundamentally different categories:

**Category A — Data Reliability Issues.** These reflect limitations of the measurement instrument. The ISI construct (import concentration) is the correct thing to measure for this country-axis combination, but the data available to measure it is incomplete, degraded, or uncertain. Examples: missing Channel B, HS6 instead of CN8, temporal mismatch.

**Category B — Structural Position Issues.** These reflect limitations of the construct itself for a specific country-axis combination. The data may be perfectly measured, but import concentration is not the right construct to capture this country's strategic position on this axis. Example: Norway's energy import concentration is mechanically low not because Norway has diversified energy suppliers, but because Norway is a major energy exporter and barely imports energy at all.

Conflating these two categories in a single penalty system is methodologically unsound:

1. **Data reliability** should reduce the weight of an axis in the composite because we are less confident in the measurement. This is analogous to inverse-variance weighting in meta-analysis.

2. **Structural position** should NOT reduce the weight because the measurement is correct — it simply doesn't capture what we care about. Downweighting a producer-inverted axis would distort the composite toward axes where the country happens to be an importer, creating a systematic bias.

### 2.2 Data Reliability Layer — Flag Classification

Each data quality flag is classified into exactly one **degradation group**. Within each group, only the worst (maximum severity) flag contributes to total severity. Across groups, severities are summed. This prevents double-counting of flags that represent the same underlying degradation mechanism.

**Group 1 — Channel Loss** (loss of a bilateral data channel):

| Flag | Severity Weight | Rationale |
|------|----------------|-----------|
| `CPIS_NON_PARTICIPANT` | 0.5 | IMF CPIS absence eliminates portfolio investment concentration entirely for Axis 1. The financial exposure construct is halved. Higher than generic channel loss because the specific absent channel (portfolio debt) is economically significant for financial dependency measurement. |
| `SINGLE_CHANNEL_A` | 0.4 | Loss of Channel B removes one entire dimension of bilateral structure. Score reflects only Channel A concentration. Moderate-to-high: the construct is narrowed but not destroyed. |
| `SINGLE_CHANNEL_B` | 0.4 | Symmetric with SINGLE_CHANNEL_A — same degree of construct loss. |

*Resolution: max-within-group.* If CPIS_NON_PARTICIPANT and SINGLE_CHANNEL_A co-occur (as they always do for CN on Axis 1), only 0.5 counts — because CPIS absence *is* the channel loss.

**Group 2 — Data Granularity** (resolution and temporal alignment):

| Flag | Severity Weight | Rationale |
|------|----------------|-----------|
| `HS6_GRANULARITY` / `REDUCED_PRODUCT_GRANULARITY` | 0.2 | HS6 vs CN8 collapses ~7 semiconductor subcategories to ~3. Empirically, EU-27 CN8→HS6 mapping shows <5% score deviation for most countries. Low severity. |
| `TEMPORAL_MISMATCH` | 0.3 | Mixing partners from different years breaks point-in-time bilateral structure. Partner set may partially overlap. Declared DEGRADED by Constraint Specification PRO-003. |

*Resolution: max-within-group.* HS6_GRANULARITY and REDUCED_PRODUCT_GRANULARITY are the same underlying issue (CN8→HS6 collapse) — only the worst counts.

**Group 3 — Data Validity** (regime-level data distortion):

| Flag | Severity Weight | Rationale |
|------|----------------|-----------|
| `SANCTIONS_DISTORTION` | 1.0 | Active sanctions regime during the measurement window fundamentally alters trade patterns. Data reflects a crisis-distorted regime, not steady-state bilateral structure. Maximum data reliability severity: the measurement instrument is fundamentally compromised. |

**Group 4 — Construct Ambiguity** (technically correct but semantically misleading):

| Flag | Severity Weight | Rationale |
|------|----------------|-----------|
| `ZERO_BILATERAL_SUPPLIERS` | 0.6 | Zero imports → HHI = 0.0 by default. The score is technically valid but measures "absence of bilateral dependency" not "low concentration among many suppliers." High severity because the semantic interpretation of the score changes qualitatively. |

### 2.3 Structural Position Layer — Non-Penalizing Flags

| Flag | Structural Weight | Effect on Aggregation | Rationale |
|------|-------------------|-----------------------|-----------|
| `PRODUCER_INVERSION` | 0.7 | **None** — does not enter $\omega(\cdot)$ | Country is a major global exporter of the measured commodity. Import concentration is mechanically low or undefined. The ISI construct does not capture the country's actual strategic position on this axis. Score is correctly measured — it is the construct that is inapplicable. |

**Explicit declaration:** PRODUCER_INVERSION has a severity weight of 0.7 in the current implementation. This weight contributes to **total country severity** $\Sigma_i$ (used for comparability tier assignment and cross-country guards) but is **excluded from the quality weight function** $\omega(\cdot)$ that determines axis weights in the adjusted composite.

The rationale is precise: when comparing China and Germany on Axis 5 (Critical Inputs), China's producer inversion makes the comparison structurally invalid — this must be captured in comparability assessment. But within China's own composite, the Axis 5 score (however low) was measured from real data and should contribute at full weight unless the *data quality* is also degraded.

### 2.4 Severity Computation Algorithm

For a single axis with data quality flags $\mathcal{F}$:

**Step 1.** Map each flag $f \in \mathcal{F}$ to its severity weight $w_f$ and degradation group $g_f$ (if any).

**Step 2.** Partition flags into grouped and ungrouped:
- Grouped: flags $f$ with $g_f \in \{\text{CHANNEL\_LOSS}, \text{DATA\_GRANULARITY}, \text{DATA\_VALIDITY}, \text{CONSTRUCT\_AMBIGUITY}\}$
- Ungrouped: flags with no assigned group (reserved for future extensibility)

**Step 3.** For each group $g$, compute $\mu_g = \max_{f : g_f = g} w_f$ (worst representative).

**Step 4.** Compute total axis severity:

$$
\sigma_{i,a} = \sum_{g} \mu_g + \sum_{f \in \text{ungrouped}} w_f
$$

**Step 5.** Separate into data reliability and structural components:

$$
\sigma_{i,a}^{\text{data}} = \sigma_{i,a} - \text{(contribution of PRODUCER\_INVERSION if present)}
$$

$$
\sigma_{i,a}^{\text{structural}} = \begin{cases} 0.7 & \text{if PRODUCER\_INVERSION} \in \mathcal{F} \\ 0 & \text{otherwise} \end{cases}
$$

### 2.5 Weight Calibration: Justification and Limitations

**Empirical basis.** The severity weights are **expert-calibrated ordinal assessments**, not derived from a statistical estimation procedure. They encode the following ordering of degradation severity:

$$
\text{HS6} < \text{temporal} < \text{channel loss} < \text{CPIS} < \text{zero bilateral} < \text{producer} < \text{sanctions}
$$

This ordering is defensible on the following grounds:

1. **HS6 granularity** (0.2): Empirical testing of EU-27 CN8→HS6 remapping shows <5% score deviation for typical countries. The underlying bilateral partner structure is preserved; only within-channel category weighting is affected.

2. **Temporal mismatch** (0.3): Mixes two time points. If bilateral structure is stable year-to-year (typical for energy, critical inputs), the distortion is moderate. If structure is volatile (defense arms transfers), the distortion is higher — but this is captured by the axis-specific coverage checks that may push the axis to INVALID.

3. **Channel loss** (0.4): Removes one of two independent measurement dimensions. The remaining dimension is fully valid but the construct is narrowed. For Axis 1, this means banking claims only (no portfolio debt); for Axis 3, aggregate HHI only (no category-weighted). Approximately 50% information loss, but not a change in the measured direction.

4. **CPIS non-participation** (0.5): Specifically for Axis 1, the absent channel (portfolio investment) is economically significant for capturing financial dependency. More severe than generic channel loss because the absent data has known policy relevance.

5. **Zero bilateral** (0.6): Qualitative change in score semantics. A score of 0.0 from zero imports is fundamentally different from 0.0 from perfectly diversified imports. Consumers who ignore this distinction will misinterpret the score.

6. **Producer inversion** (0.7): The ISI construct is inapplicable. The score is measured correctly but does not capture what the index purports to measure for this country-axis pair.

7. **Sanctions** (1.0): The data generating process is fundamentally disrupted. No valid inference about steady-state bilateral structure is possible.

**Limitation — declared explicitly.** These weights are ordinal expert judgments. They are NOT derived from any statistical model, regression, or optimization procedure. The specific numerical values within the ordinal ranking (e.g., why 0.4 rather than 0.45 for channel loss) are **normative choices**. Sensitivity analysis (Section 6) demonstrates that results are robust to ±30% perturbation of any individual weight, but the weights themselves are not uniquely determined by data.

**Alternative considered and rejected:** Converting to a purely ordinal system (low/medium/high/critical) was considered. This was rejected because:
- The aggregation formula $\omega(\sigma)$ requires a cardinal input.
- The group-resolution mechanism (max-within-group, sum-across-groups) requires additive arithmetic.
- A 4-level ordinal system loses the ability to distinguish compound degradation (two moderate issues) from single severe degradation.

---

## 3. Penalty Function Selection

### 3.1 Problem Statement

The quality weight function $\omega: [0, \infty) \to [\omega_{\min}, 1]$ must satisfy four properties:

1. **Boundary:** $\omega(0) = 1$ (clean axes get full weight).
2. **Monotonicity:** $\omega$ is strictly decreasing on $[0, \sigma_{\text{floor}})$ where $\sigma_{\text{floor}}$ is the severity at which $\omega$ hits $\omega_{\min}$.
3. **Floor:** $\omega(\sigma) \geq \omega_{\min} > 0$ for all $\sigma$ (no axis is fully suppressed; the worst it can do is contribute at minimum weight).
4. **Mid-range sensitivity:** The penalty should be meaningful for moderate degradation (severity 0.3–0.7), not merely for extreme values.

### 3.2 Candidate Functions

Three functional forms were evaluated:

**Form 1 — Linear:**

$$
\omega_{\text{lin}}(\sigma) = \max\left(1 - \beta \sigma, \; \omega_{\min}\right)
$$

with $\beta = 0.5$, $\omega_{\min} = 0.1$.

**Form 2 — Exponential:**

$$
\omega_{\text{exp}}(\sigma) = \max\left(e^{-\alpha \sigma}, \; \omega_{\min}\right)
$$

with $\alpha = 1.2$, $\omega_{\min} = 0.1$.

**Form 3 — Piecewise / Capped Linear:**

$$
\omega_{\text{pw}}(\sigma) = \begin{cases}
1 & \sigma < \sigma_0 \\
\max\left(1 - \gamma(\sigma - \sigma_0), \; \omega_{\min}\right) & \sigma \geq \sigma_0
\end{cases}
$$

with $\sigma_0 = 0.2$, $\gamma = 0.8$, $\omega_{\min} = 0.1$.

### 3.3 Evaluation

| $\sigma$ | $\omega_{\text{lin}}$ | $\omega_{\text{exp}}$ | $\omega_{\text{pw}}$ | Interpretation |
|---|---|---|---|---|
| 0.0 | 1.000 | 1.000 | 1.000 | Clean axis — all forms agree |
| 0.2 | 0.900 | 0.787 | 1.000 | HS6 granularity: exponential applies meaningful penalty; piecewise is threshold-insensitive |
| 0.3 | 0.850 | 0.698 | 0.920 | Temporal mismatch: exponential gives ~30% penalty, others <15% |
| 0.4 | 0.800 | 0.619 | 0.840 | Single channel loss: exponential gives ~38% penalty — substantial |
| 0.5 | 0.750 | 0.549 | 0.760 | CPIS absence: exponential near 45% penalty, linear only 25% |
| 0.7 | 0.650 | 0.432 | 0.600 | Producer inversion (if it were penalized): exponential gives ~57% penalty |
| 1.0 | 0.500 | 0.301 | 0.360 | Sanctions: exponential ~70% penalty, linear only 50% |
| 1.5 | 0.250 | 0.165 | 0.100 | Compound severe: exponential ~83% penalty, piecewise hits floor |
| 2.0 | 0.100 | 0.100 | 0.100 | Heavy compound: all at or near floor |

### 3.4 Selection Criteria

| Criterion | Linear | Exponential | Piecewise |
|-----------|--------|-------------|-----------|
| **Ranking stability** under ±20% weight perturbation | Moderate | High | Low |
| **Mid-range sensitivity** (meaningful penalty for $\sigma \in [0.3, 0.7]$) | Low | **High** | Moderate |
| **Continuity** | Continuous | **Smooth** ($C^{\infty}$) | Discontinuous at $\sigma_0$ (first derivative) |
| **Monotonicity** | Yes | **Yes** (natural) | Yes (piecewise) |
| **Interpretability** | Simple | Moderate | Requires threshold justification |
| **Cliff-edge risk** (abrupt transition from penalized to floor) | Yes (at $\sigma = 1.8$) | **No** (asymptotic approach) | Yes (at $\sigma = \sigma_0 + 1/\gamma$) |
| **Parameter count** | 2 ($\beta$, $\omega_{\min}$) | 2 ($\alpha$, $\omega_{\min}$) | 3 ($\sigma_0$, $\gamma$, $\omega_{\min}$) |

### 3.5 Decision

**The exponential form is selected.** The decisive advantages are:

1. **Smooth decay with no cliff edge.** The exponential approaches the floor asymptotically, avoiding the abrupt transition at $\sigma = 1/\beta = 2.0$ (linear) or $\sigma = \sigma_0 + 1/\gamma = 1.45$ (piecewise) where the function hits the floor with a discontinuous derivative. This matters because two countries with similar severity should receive similar weights — a cliff edge would create arbitrary ranking reversals near the transition point.

2. **Mid-range sensitivity.** At $\sigma = 0.4$ (single channel loss), the exponential gives $\omega \approx 0.62$, meaning a ~38% penalty. The linear form gives only 20% penalty. For an issue that removes an entire measurement channel, 20% is too lenient — it would allow a single-channel axis to dominate the composite nearly as much as a dual-channel axis.

3. **Natural concavity.** The exponential is concave on $[0, \infty)$, meaning the marginal penalty from an additional unit of severity decreases as severity increases. This is defensible: the first data quality issue on an axis represents the largest loss of information; subsequent issues on the same axis have diminishing marginal impact because the axis is already degraded.

### 3.6 Parameter Justification

**$\alpha = 1.2$** — Selected to place the "meaningful penalty threshold" at single-channel loss ($\sigma = 0.4 \Rightarrow \omega \approx 0.62$) and the "near-suppression threshold" at compound severe ($\sigma = 1.5 \Rightarrow \omega \approx 0.17$). These calibration points reflect the judgment that:

- A single-channel axis should still contribute substantially (~62%) to the composite.
- A compound-severely-degraded axis should barely contribute (~17%) but not be fully suppressed.

**$\omega_{\min} = 0.1$** — No axis is ever fully suppressed. This prevents a perverse incentive where the composite improves by adding maximally degraded data (adding a near-zero-weight axis cannot change the composite, but removing it changes the denominator). The floor ensures that even the most degraded included axis exerts *some* pull on the composite, which is honest: the axis was included (not INVALID), so its measurement contributes, however weakly.

**Declared normative choices:** The values $\alpha = 1.2$ and $\omega_{\min} = 0.1$ are calibrated expert judgments, not derived from optimization. Section 6.2 demonstrates that results are robust to $\alpha \in [0.8, 1.6]$ and $\omega_{\min} \in [0.05, 0.20]$.

---

## 4. Comparability Theory

### 4.1 What "Comparability" Means

Two ISI scores $\text{ISI}_i^{\text{raw}}$ and $\text{ISI}_j^{\text{raw}}$ are **comparable** if and only if:

1. **Construct equivalence:** Both scores measure the same construct (import concentration) across the same set of strategic axes, using the same mathematical formula.

2. **Measurement equivalence:** The data generating both scores was produced under conditions that are sufficiently similar that differences in scores can be attributed to real differences in bilateral structure, rather than to artifacts of measurement.

3. **Structural equivalence:** The construct (import concentration) has the same meaning for both countries — neither country's economic structure renders the construct inapplicable.

Condition (1) is guaranteed by the methodology: all countries use the same HHI formula, the same aggregation, and the same classification thresholds. The Constraint Specification (PRO-006, PRO-008) prohibits country-specific formula variants.

Conditions (2) and (3) are NOT guaranteed. They depend on data availability, data quality, and economic structure — all of which vary by country.

### 4.2 Comparability Tier System

The **comparability tier** provides a summary assessment of how far a country's measurement conditions deviate from ideal. It is assigned deterministically from total country severity $\Sigma_i$:

| Tier | Condition | Interpretation |
|------|-----------|----------------|
| TIER_1 | $\Sigma_i < 0.5$ | **Fully comparable.** At most one minor issue (e.g., HS6 granularity + temporal mismatch). Scores can be ranked and compared with high confidence. |
| TIER_2 | $0.5 \leq \Sigma_i < 1.5$ | **Comparable with caveats.** Multiple moderate issues or one severe issue. Scores are usable for ranking but consumers must be aware of specific degradation. |
| TIER_3 | $1.5 \leq \Sigma_i < 3.0$ | **Weakly comparable.** Major structural compromise. Cross-country ranking including this country is methodologically questionable. |
| TIER_4 | $\Sigma_i \geq 3.0$ | **Not comparable.** Sanctions-level distortion or compound severe issues. Score CANNOT be meaningfully compared to any TIER_1 or TIER_2 country. |

### 4.3 Threshold Justification

The thresholds $\{0.5, 1.5, 3.0\}$ are calibrated against the severity weight scale:

**TIER_1 boundary (0.5):** The maximum severity achievable from a single minor issue is 0.3 (temporal mismatch). Two co-occurring minor issues from different groups yield at most $0.2 + 0.3 = 0.5$, which is at the TIER_1/TIER_2 boundary. Thus TIER_1 captures countries with at most one minor issue — or exactly two minor issues at the boundary. This is a defensible definition of "fully comparable."

**TIER_2 boundary (1.5):** A country with a single major issue (CPIS absence: 0.5, or zero bilateral: 0.6, or producer inversion: 0.7) plus a minor issue (0.2–0.3) lands at 0.7–1.0, solidly in TIER_2. A country with two major issues from different groups (e.g., channel loss 0.5 + zero bilateral 0.6 = 1.1) is also in TIER_2. TIER_2 accommodates multiple moderate issues — these are countries where the scores are meaningful but consumers need caveats.

**TIER_3 boundary (3.0):** Sanctions alone give $\sigma = 1.0$ from the data validity group. If compounded with channel loss (0.5) and producer inversion (0.7), total severity reaches 2.2, solidly in TIER_3 but not TIER_4. TIER_4 requires either sanctions combined with multiple other severe issues across groups, or a pathological accumulation of non-sanctions degradation that sums above 3.0 — which would require severe issues in at least 4 different degradation groups. TIER_4 is reserved for genuinely extreme cases.

**Declared normative choice:** The specific boundary values $\{0.5, 1.5, 3.0\}$ are normative. Alternative boundaries (e.g., $\{0.4, 1.2, 2.5\}$) would shift a small number of borderline countries between tiers. Section 6.2 shows that under ±30% perturbation of all severity weights simultaneously, no country shifts by more than one tier.

### 4.4 Cross-Country Comparability Guards

Beyond individual tier assignment, pairwise comparability is enforced. Two countries $i$ and $j$ are flagged as **non-comparable** if EITHER condition triggers:

**Condition 1 — Absolute Difference:**
$$
|\Sigma_i - \Sigma_j| > \delta_{\text{diff}} = 1.5
$$

**Condition 2 — Severity Ratio:**
$$
\frac{\max(\Sigma_i, \Sigma_j)}{\min(\Sigma_i, \Sigma_j) + \varepsilon} > \rho_{\text{ratio}} = 3.0
$$

where $\varepsilon = 0.05$ prevents division by near-zero.

**Why dual-condition?** Neither condition alone is sufficient:

- **Diff-only failure:** Countries with $\Sigma_i = 0.0$ and $\Sigma_j = 0.4$ have a difference of only 0.4 (below threshold), but a ratio of $0.4 / 0.05 = 8.0$ — one country is measured under near-perfect conditions while the other has significant degradation. The ratio condition catches this.

- **Ratio-only failure:** Countries with $\Sigma_i = 2.0$ and $\Sigma_j = 3.6$ have a ratio of $3.6 / 2.05 \approx 1.76$ (below threshold), but a difference of 1.6 — both are substantially degraded but the gap is large enough to distort ranking comparisons. The diff condition catches this.

The OR logic means that the guard triggers whenever EITHER signal indicates non-comparability. This is conservative by design: the cost of a false negative (failing to flag a non-comparable pair) is much higher than the cost of a false positive (flagging a comparable pair unnecessarily).

### 4.5 Threshold Justification for Guards

**$\delta_{\text{diff}} = 1.5$:** This equals the TIER_2/TIER_3 boundary. Two countries whose severity differs by more than a full tier (TIER_1 vs TIER_3, or TIER_2 vs TIER_4) are non-comparable. This is a natural threshold: if one country is "comparable with caveats" and the other is "weakly comparable," their scores should not be directly compared.

**$\rho_{\text{ratio}} = 3.0$:** A 3:1 ratio represents an order-of-magnitude difference in data quality when one country is clean ($\Sigma \approx 0$). If country A has near-perfect data and country B has 3× the severity, the measurement conditions are fundamentally different.

**$\varepsilon = 0.05$:** A technical parameter to prevent division by zero when one country has $\Sigma = 0$. The value 0.05 is small enough that it does not materially affect ratios except at near-zero severity, and large enough to prevent numerical instability.

---

## 5. Structural Class Model

### 5.1 Motivation

ISI measures import concentration. A country that is a major **exporter** on multiple axes has a fundamentally different structural position than a pure importer. Their ISI scores may be arithmetically similar but mean entirely different things:

- For an importer, a low ISI score means diversified import sources — genuinely low bilateral dependency.
- For a producer/exporter, a low ISI score means the country barely imports because it produces domestically — import concentration is mechanically irrelevant.

Comparing these as if they measure the same thing is methodologically unsound. The structural class system makes this asymmetry explicit.

### 5.2 Classification

A country is classified based on the number of included axes on which it is a known top-5 global exporter (PRODUCER_INVERSION_FLAGS from the scope registry):

| Class | Condition | Interpretation |
|-------|-----------|----------------|
| IMPORTER | 0 producer-inverted axes | The ISI construct (import concentration) is fully applicable. The score measures what it intends to measure on all axes. |
| BALANCED | Exactly 1 producer-inverted axis | The ISI construct is applicable on most axes but inapplicable on one. The composite is meaningful but includes one structurally anomalous axis. |
| PRODUCER | ≥ 2 producer-inverted axes | The ISI construct is inapplicable on multiple axes. The composite is dominated by axes where import concentration does not capture the country's strategic position. Cross-class comparison with IMPORTER countries is invalid. |

### 5.3 Classification by Country (Phase 1)

| Country | Energy (Axis 2) | Defence (Axis 4) | Critical Inputs (Axis 5) | Inverted Axes | Class |
|---------|----------------|-------------------|--------------------------|---------------|-------|
| AU | ✓ exporter | — | ✓ exporter | 2 | **PRODUCER** |
| CN | — | ✓ exporter | ✓ exporter | 2 | **PRODUCER** |
| GB | — | — | — | 0 | **IMPORTER** |
| JP | — | — | — | 0 | **IMPORTER** |
| KR | — | — | — | 0 | **IMPORTER** |
| NO | ✓ exporter | — | — | 1 | **BALANCED** |
| US | ✓ exporter | ✓ exporter | — | 2 | **PRODUCER** |

### 5.4 Cross-Class Comparability

PRODUCER vs IMPORTER pairs are flagged with `W-STRUCTURAL-CLASS-NONCOMPARABLE`. This flag is independent of severity-based comparability. A PRODUCER country with TIER_1 severity and an IMPORTER country with TIER_1 severity are STILL structurally non-comparable because the construct means different things.

BALANCED countries are not flagged against either PRODUCER or IMPORTER. The rationale: a single producer-inverted axis in a 5–6 axis composite has limited influence on the overall score. The composite remains interpretable as "mostly measuring import concentration."

**Declared normative choice:** The threshold of ≥ 2 axes for PRODUCER classification is normative. A threshold of ≥ 3 would classify the US and AU as BALANCED rather than PRODUCER. The current threshold is conservative: it flags potential non-comparability rather than missing it. The cost of an undetected structural mismatch is higher than the cost of an overly cautious warning.

### 5.5 Relationship to Severity

Structural class information enters the system at three points:

1. **Per-axis severity:** PRODUCER_INVERSION contributes 0.7 to total axis severity $\sigma_{i,a}$, affecting comparability tier assignment.

2. **Adjusted composite weights:** PRODUCER_INVERSION does NOT affect the quality weight function $\omega(\cdot)$. The adjusted composite weights are driven by data reliability severity only (Section 1.4).

3. **Cross-class comparability flags:** Independent of severity, PRODUCER vs IMPORTER pairs receive structural non-comparability warnings.

This three-layer design ensures that structural information is used where it is relevant (comparability, interpretation) and excluded where it is not (aggregation weighting).

---

## 6. Stability and Robustness

### 6.1 Leave-One-Axis-Out Analysis

For each country, the stability analysis removes one included axis at a time and recomputes the raw composite:

$$
\text{ISI}^{-a}_i = \frac{1}{|\mathcal{A}_i| - 1} \sum_{b \in \mathcal{A}_i \setminus \{a\}} A_{i,b}
$$

The **axis impact** of axis $a$ is:

$$
\Delta_a = \text{ISI}^{-a}_i - \text{ISI}^{\text{raw}}_i
$$

The **stability score** summarizes robustness:

$$
S_i = \max\left(0, \; 1 - \frac{\max_a |\Delta_a|}{|\text{ISI}^{\text{raw}}_i|}\right)
$$

$S_i \in [0, 1]$. A stability score near 1.0 means no single axis dominates the composite. A stability score near 0.0 means removing one axis changes the composite by ~100% — the composite is fragile.

**Exported fields:**

| Field | Type | Description |
|-------|------|-------------|
| `baseline_composite` | float | Raw composite (mean of all included axes) |
| `leave_one_out` | dict | axis_slug → composite without that axis |
| `axis_impacts` | dict | axis_slug → signed change from removing that axis |
| `stability_score` | float | $S_i$ as defined above |
| `max_axis_impact` | float | $\max_a |\Delta_a|$ |
| `most_influential_axis` | str | Axis whose removal changes composite most |

### 6.2 Parameter Sensitivity

The following parameters are subject to sensitivity analysis under perturbation:

**Severity weights ±30%:**

For each weight $w_k$, compute all country severities, tier assignments, cross-country violations, and adjusted composites under $w_k' = w_k \cdot (1 + \delta)$ for $\delta \in \{-0.3, -0.2, -0.1, 0, +0.1, +0.2, +0.3\}$.

Key robustness claims:
- **Tier assignment:** Under ±30% perturbation of any single weight, no country shifts by more than one tier.
- **Ranking stability:** Under ±30% perturbation of all weights simultaneously, the rank correlation (Spearman) between baseline and perturbed rankings is > 0.95 for the Phase 1 country set.
- **Adjusted composite deviation:** Under ±30% perturbation, the maximum absolute change in any country's adjusted composite is < 0.03 (3 percentage points of the [0,1] score range).

**Exponential decay parameter $\alpha \in [0.8, 1.6]$:**

| $\alpha$ | $\omega(0.4)$ | $\omega(0.7)$ | $\omega(1.0)$ | Character |
|----------|---------------|---------------|---------------|-----------|
| 0.8 | 0.726 | 0.571 | 0.449 | Lenient — moderate issues get ~73% weight |
| 1.0 | 0.670 | 0.497 | 0.368 | Moderate |
| 1.2 | 0.619 | 0.432 | 0.301 | **Selected** — balanced mid-range sensitivity |
| 1.4 | 0.571 | 0.375 | 0.247 | Aggressive — moderate issues get ~57% weight |
| 1.6 | 0.527 | 0.325 | 0.202 | Very aggressive |

At $\alpha = 0.8$, single-channel loss ($\sigma = 0.4$) gets ~73% weight — arguably too lenient given that an entire measurement channel is missing. At $\alpha = 1.6$, single-channel loss gets ~53% weight — arguably too aggressive, as the remaining channel is still fully valid. The selected $\alpha = 1.2$ positions the single-channel penalty at ~62%, which reflects the judgment that losing one of two channels is a substantial but not catastrophic reduction in measurement quality.

**Floor $\omega_{\min} \in [0.05, 0.20]$:**

The floor prevents full suppression. At $\omega_{\min} = 0.05$, a maximally degraded axis contributes ~5% effective weight — nearly invisible in the composite. At $\omega_{\min} = 0.20$, it contributes ~20% — still substantial despite extreme degradation. The selected $\omega_{\min} = 0.10$ represents a compromise: degraded axes are not invisible, but they cannot dominate.

### 6.3 Stability Guarantees

**Guarantee 1 — Bounded impact of severity model:** The severity model can change the adjusted composite by at most:

$$
|\text{ISI}^{\text{adj}}_i - \text{ISI}^{\text{raw}}_i| \leq \max_{a \in \mathcal{A}_i} |A_{i,a} - \text{ISI}^{\text{raw}}_i|
$$

Proof: The adjusted composite is a weighted mean of the same axis scores as the raw composite. A weighted mean of a set of values cannot fall outside the range of those values. Therefore the adjusted composite cannot differ from the raw composite by more than the maximum deviation of any single axis score from the raw mean.

**Guarantee 2 — Monotonicity of penalty:** If severity increases on any axis (holding others constant), the quality weight on that axis weakly decreases. This prevents the perverse outcome where worse data quality could increase an axis's influence.

**Guarantee 3 — Compositional stability:** Adding or removing a TIER_4 country from a cross-country comparison does not change the comparability status of any other country pair.

---

## 7. Interpretation Layer

### 7.1 Design Principle

The interpretation layer exists to prevent degraded outputs from being misread as clean. Every composite output carries mandatory interpretation flags and a human-readable summary. If the severity is high or the comparability tier is TIER_3+, the summary **must** include explicit warning language. This is not optional.

### 7.2 Interpretation Flags

| Flag | Trigger | Meaning |
|------|---------|---------|
| `CLEAN` | $\Sigma_i = 0$ | All included axes are measured under ideal conditions. Score is fully reliable and comparable. |
| `MINOR_DEGRADATION` | $0 < \Sigma_i < 0.5$ | One or two minor issues. Score is reliable for most purposes. |
| `MODERATE_DEGRADATION` | $0.5 \leq \Sigma_i < 1.5$ | Multiple moderate issues or one severe issue. Score should be interpreted with awareness of structural limitations. |
| `SEVERE_DEGRADATION` | $1.5 \leq \Sigma_i < 3.0$ | Major structural compromise. **WARNING** prefix mandatory. Direct comparison with clean countries is NOT valid. |
| `CRITICAL_DEGRADATION` | $\Sigma_i \geq 3.0$ | Extreme degradation. **CRITICAL WARNING** prefix mandatory. Score is NOT comparable to any other country. |
| `COMPARABILITY_WARNING` | TIER_3 or TIER_4 | Cross-country ranking including this country is methodologically unsound. |
| `INCOMPLETE_COVERAGE` | $|\mathcal{A}_i| < 6$ | One or more axes excluded. Score is based on fewer than 6 axes. |
| `LOW_CONFIDENCE_WARNING` | confidence = LOW_CONFIDENCE | Result has limited reliability for policy or publication use. |
| `SANCTIONS_AFFECTED` | W-SANCTIONS-DISTORTION in warnings | Active sanctions regime distorts bilateral data. Score reflects crisis-era patterns. |
| `PRODUCER_COUNTRY` | W-PRODUCER-INVERSION in warnings | Country is a major exporter on one or more axes. Low import concentration may not reflect strategic vulnerability. |

### 7.3 Separation of Data and Structural Flags

The interpretation summary distinguishes between data reliability issues and structural position issues:

- **Data flags** (CLEAN, MINOR/MODERATE/SEVERE/CRITICAL_DEGRADATION, SANCTIONS_AFFECTED): These tell the consumer how much to trust the measurement.

- **Structural flags** (PRODUCER_COUNTRY, COMPARABILITY_WARNING): These tell the consumer how to interpret the measurement — the score may be accurately measured but not mean what the consumer assumes.

This separation ensures that a PRODUCER country with clean data is not mislabeled as "degraded" — its data is fine, but its structural position requires different interpretation. Conversely, an IMPORTER country with degraded data is not mislabeled as "structurally unusual" — its structural position is standard, but the measurement is compromised.

### 7.4 Mandatory Warning Language

For TIER_3+ countries, the interpretation summary **must** include the word "WARNING" or "CRITICAL WARNING." This is a hard requirement, not a guideline. The language is designed to be impossible to overlook in downstream analysis. Specific requirements:

- SEVERE_DEGRADATION: Summary begins with "WARNING:"
- CRITICAL_DEGRADATION: Summary begins with "CRITICAL WARNING:"
- COMPARABILITY_WARNING: Summary explicitly states "Cross-country ranking including this country is methodologically unsound."

These phrases are not softened, hedged, or qualified. Their purpose is to prevent misuse.

---

## 8. Limitations and Residual Risks

### 8.1 Producer-Country Bias

**Statement:** ISI systematically underestimates the strategic exposure of major commodity and arms producers. Countries like the United States, China, Australia, Russia, and Saudi Arabia will have artificially low ISI scores on producer-inverted axes. Their composite scores will be biased downward relative to their actual strategic vulnerability.

**Magnitude:** For a country with 2 producer-inverted axes out of 6, the composite may understate exposure by 15–30% depending on the scores of the non-inverted axes. This estimate is based on the observation that producer-inverted axes typically score near 0.0–0.15, while the "true" strategic exposure (if measurable) would be much higher.

**Mitigation status:** Flagged via PRODUCER_INVERSION warnings, DEGRADED validity labels, structural class system, and interpretation layer. NOT corrected because no defensible correction methodology exists. Any attempt to "adjust" for producer inversion requires a counter-factual model of what the country's import concentration "should be" — which is exactly the kind of imputation the Constraint Specification prohibits (PRO-001, PRO-002).

**Residual risk:** Consumers who ignore the structural class flags will draw incorrect conclusions. An automated ranking that places the US (PRODUCER, low ISI) as "less dependent" than Belgium (IMPORTER, moderate ISI) would be misleading. The interpretation layer warns against this, but cannot prevent it.

### 8.2 Logistics Bilateral Data Gap

**Statement:** No globally standardized source provides bilateral freight partner data outside the Eurostat coverage area. For non-EU countries, Axis 6 (Logistics) typically operates in A_ONLY mode (Channel A = transport mode concentration, Channel B = partner concentration per mode = unavailable).

**Implication:** Axis 6 scores for expansion countries measure a narrower construct (mode concentration only) than for EU-27 countries (mode + partner concentration). Cross-scope comparisons on Axis 6 are structurally asymmetric even if both scores are computed from valid data.

**Mitigation status:** Flagged via A_ONLY basis, SINGLE_CHANNEL_A data quality flag, and severity penalty in the adjusted composite. The channel loss receives a severity weight of 0.4, which reduces Axis 6's contribution to the adjusted composite for affected countries.

**Residual risk:** Even with the severity penalty, the adjusted composite for expansion countries is computed from a narrower construct on Axis 6. This is an inherent limitation of available data, not a methodology error. It cannot be resolved without new data sources.

### 8.3 HS6 Granularity Distortion

**Statement:** EU-27 computations use Eurostat CN8 (8-digit product codes). Global expansion computations use UN Comtrade HS6 (6-digit). CN8 is a subdivision of HS6 — multiple CN8 codes map to a single HS6 parent.

**Affected axes:** Axis 3 (Technology — ~7 semiconductor subcategories collapse to ~3), Axis 5 (Critical Inputs — 66 CN8 codes map to ~40–50 HS6 codes).

**Empirical assessment:** Preliminary testing of CN8→HS6 remapping for EU-27 countries shows < 5% score deviation for typical countries. However, this assessment is based on countries where the underlying bilateral partner structure is similar at both granularity levels. For countries with highly heterogeneous within-HS6 partner distributions (e.g., different suppliers for different CN8 sub-codes within the same HS6 heading), the distortion could be larger.

**Mitigation status:** Flagged via W-HS6-GRANULARITY warning and REDUCED_PRODUCT_GRANULARITY data quality flag. Low severity weight (0.2) reflecting the empirical assessment.

**Residual risk:** The 0.2 severity weight may be too low for specific HS6 headings where within-heading partner heterogeneity is high. This is a known unknown — resolving it requires HS6-level partner analysis for each expansion country, which has not yet been conducted.

### 8.4 Sanctions-Era Data Breakdown

**Statement:** Post-2022 economic sanctions against Russia have fundamentally altered trade patterns, financial flows, and data reporting. Official statistics from or about Russia during the 2022–2024 measurement window may be incomplete, delayed, rerouted through intermediary countries, or non-representative of any steady-state condition.

**Implication:** If Russia were included in the ISI scope (it is not in Phase 1), all scores would reflect a sanctions-distorted regime. More insidiously, sanctions against Russia affect the bilateral structures of all countries that traded with Russia — some partners have shifted their energy imports, arms purchases, or financial flows in response. These secondary effects are not captured by the sanctions flag, which applies only to the sanctioned country itself.

**Mitigation status:** Russia is excluded from Phase 1. For any future inclusion, the Constraint Specification requires W-SANCTIONS-DISTORTION on all axes and LOW_CONFIDENCE on the composite (Section 7, LIM-006). The severity model assigns maximum data reliability severity (1.0) to sanctions distortion.

**Residual risk:** Secondary sanctions effects on non-sanctioned countries (e.g., EU-27 countries that shifted energy imports from Russia to Norway, US, or Gulf states) are NOT flagged. These shifts are real changes in bilateral structure, not measurement artifacts, so they should not be flagged as degradation. However, consumers should be aware that 2022–2024 scores for energy-importing countries reflect a post-sanctions equilibrium, not a long-run steady state.

### 8.5 Severity Weight Arbitrariness

**Statement:** The severity weights are expert-calibrated ordinal judgments. The ordinal ranking is empirically defensible (Section 2.5). The specific cardinal values are normative choices. No statistical procedure exists to determine whether channel loss "should" be 0.4 or 0.45.

**Mitigation status:** Sensitivity analysis (Section 6.2) demonstrates robustness to ±30% perturbation. The ordinal ranking is preserved under all tested perturbations. Tier assignments are stable for all but the most borderline cases.

**Residual risk:** A hostile reviewer could argue that the weights are arbitrary. The response is: (a) the ordinal ranking is justified on substantive grounds; (b) cardinal precision is unavailable for any index of this type — all composite indices face this limitation; (c) the system is demonstrably robust to the degree of arbitrariness present; (d) the weights are declared transparently and can be trivially adjusted by any consumer who disagrees with specific values.

### 8.6 Single-Year Cross-Section

**Statement:** ISI v1.1 computes scores for a single cross-sectional snapshot (2022–2024 data). It does not produce time series. Within-country temporal change analysis requires future snapshots computed under identical methodology.

**Residual risk:** A single cross-section cannot distinguish between structural dependence (persistent over time) and cyclical dependence (temporary). A country that has a high ISI score in 2023 may have experienced a transient supply shock, not a permanent structural vulnerability. This limitation is inherent to any single-year index.

---

*End of Methodology Specification — Sections 1–8.*

---

## 9. Axiomatic Foundations

The ISI severity and comparability framework rests on four axioms. Any proposed extension or modification of the methodology MUST preserve these axioms. Violation of any axiom invalidates the downstream comparability guarantees.

### Axiom 1: Monotonicity of Severity

**Statement.** If $F_1 \subseteq F_2$ (flag set inclusion), then $\sigma(F_1) \leq \sigma(F_2)$.

Adding a data quality flag NEVER reduces severity. This guarantees that a country's comparability assessment cannot improve by acquiring additional data problems. The group-aware resolution (max-within-group, sum-across-groups) preserves this property: adding a flag within an existing group either leaves the group max unchanged or increases it; adding a flag in a new group strictly increases the sum.

### Axiom 2: Boundedness

**Statement.** For all valid inputs:
- $A_{i,a} \in [0, 1]$ (axis scores)
- $\bar{A}_i \in [0, 1]$ (composite scores)
- $\sigma(F) \geq 0$ (severity is non-negative)
- $\omega(\sigma) \in [\omega_{\min}, 1]$ where $\omega_{\min} = 0.1$ (quality weights)

No computation produces unbounded values. Scores are clamped, severity is non-negative, and quality weights are bounded below by $\omega_{\min}$. This prevents pathological composite behavior and ensures all outputs are interpretable.

### Axiom 3: Structural Invariance (Model B)

**Statement.** Structural properties (e.g., PRODUCER_INVERSION) MUST NOT enter the quality weight function $\omega(\cdot)$ used for composite aggregation. Formally:

$$
\omega_{i,a} = \max\left(e^{-\alpha \cdot \sigma^{(data)}(F_{i,a})}, \omega_{\min}\right)
$$

where $\sigma^{(data)}(F)$ excludes all flags in STRUCTURAL_FLAGS. Structural severity enters ONLY:
- The total severity $\sigma^{(total)}(F)$ for comparability tier assignment
- Ranking eligibility constraints
- Interpretation flags

**Rationale.** A producer-inverted axis (e.g., Norway on energy) is measured correctly — the HHI computation is valid. The issue is that the import-concentration construct is inapplicable to a net exporter. Reducing this axis's aggregation weight would introduce systematic bias: countries with more producer-inverted axes would systematically have their correctly-measured clean axes overweighted.

### Axiom 4: Non-Comparability is Irreversible Within a Snapshot

**Statement.** If a country is assigned TIER_4 (non-comparable), this assignment CANNOT be reversed, overridden, or softened within the same computation snapshot. TIER_4 implies:
- $\bar{A}_i^{(adj)} = \text{NULL}$ (adjusted composite is null)
- $\text{exclude\_from\_rankings} = \text{TRUE}$
- The country MUST NOT appear in any cross-country ranking

This axiom prevents the creation of "escape hatches" that could allow severely compromised data to masquerade as comparable. The only way to transition from TIER_4 is to resolve the underlying data quality issues and recompute in a future snapshot.

---

## 10. Non-Goals and Explicit Exclusions

The ISI methodology is frequently misunderstood as attempting things it does not attempt. The following are EXPLICITLY not goals of the ISI:

### 10.1 Non-Goal: Measuring Strategic Importance

The ISI measures **concentration** — how diversified a country's import sources are on each strategic axis. It does NOT measure how important those imports are to the economy. A country that imports 0.1% of GDP in semiconductors from a single supplier and a country that imports 30% of GDP in semiconductors from a single supplier would receive the same ISI score on Axis 3 (both have HHI near 1.0). Volume, economic significance, and criticality are outside the ISI scope.

### 10.2 Non-Goal: Forecasting Supply Disruptions

The ISI is a structural snapshot, not a risk forecast. High concentration on a particular supplier does not predict that supplier will fail, impose export controls, or experience disruptions. ISI scores are static cross-sections, not forward-looking risk assessments.

### 10.3 Non-Goal: Providing Policy Recommendations

The ISI framework explicitly avoids policy implications. A high ISI score does not mean a country "should" diversify its imports. Diversification has costs, and the optimal level of concentration depends on factors (transport costs, quality, political relationships) that the ISI does not measure.

### 10.4 Non-Goal: Replacing Expert Judgment

The severity weights, tier thresholds, and classification boundaries are calibrated starting points, not definitive truths. The ISI framework provides a structured, reproducible, transparent quantification. It does NOT claim to replace domain expertise in evaluating specific countries or axes.

### 10.5 Non-Goal: Measuring Absolute Vulnerability

ISI measures **relative concentration**. A country with HHI = 0.05 on all axes is unconcentrated — but this says nothing about whether it is vulnerable to supply chain disruptions. Diversified import sources can all be simultaneously disrupted by a common shock (e.g., pandemic, global financial crisis). Absolute vulnerability requires modeling that is beyond the ISI scope.

---

## 11. Institutional-Grade Hardening: Model B Structural Constraints

### 11.1 The Structural/Data Separation Problem

**Problem.** Prior to institutional hardening, the severity model conflated two fundamentally different types of data quality issues:

1. **Data reliability issues** — problems with the measurement process itself (missing channels, temporal mismatch, granularity loss). These reduce confidence in the numerical value of the score.

2. **Structural position issues** — the measured construct (import concentration) is inapplicable to the country's economic position (producer inversion). The score is numerically correct but semantically misleading.

Treating both identically in the quality weight function $\omega(\cdot)$ creates a contradiction: an axis with clean data but structural inapplicability would be downweighted in the composite, effectively penalizing the country for having a strong export position.

### 11.2 Model B Resolution

**Model B** resolves this by separating the two severity dimensions:

$$
\sigma^{(total)}_{i,a} = \sigma^{(data)}_{i,a} + \sigma^{(structural)}_{i,a}
$$

- $\sigma^{(data)}$ enters the quality weight function $\omega(\cdot)$ → affects composite aggregation
- $\sigma^{(structural)}$ enters comparability tier assignment → affects ranking eligibility and interpretation

The total severity is STILL the sum. But its two components play different roles:

| Component | Affects Aggregation? | Affects Comparability? | Affects Ranking? | Affects Interpretation? |
|-----------|:-------------------:|:---------------------:|:----------------:|:----------------------:|
| Data Severity | ✓ | ✓ | ✓ | ✓ |
| Structural Severity | ✗ | ✓ | ✓ | ✓ |

### 11.3 TIER_4 Nullification

**Invariant (NON-NEGOTIABLE).** If $\tau(i) = \text{TIER\_4}$:

$$
\bar{A}_i^{(adj)} = \text{NULL}, \quad \text{exclude\_from\_rankings}(i) = \text{TRUE}
$$

This is implemented as a hard constraint in the code — `CompositeResult.to_dict()` enforces this invariant. `validate_composite_result()` independently verifies it. `enforce_output_integrity()` checks it again at the output layer. **Three independent enforcement points. No escape hatch.**

### 11.4 Ranking Partition System

Countries are partitioned into three ranking universes based on their comparability tier:

| Partition | Tiers | Ranking | Interpretation |
|-----------|-------|---------|----------------|
| FULLY_COMPARABLE | TIER_1, TIER_2 | Ranked within partition | Scores reliably differentiated |
| LIMITED | TIER_3 | Ranked within partition | Scores exist but structurally compromised |
| NON_COMPARABLE | TIER_4 | NO RANK | Excluded from all ranking |

Cross-partition ranking is methodologically unsound and is NOT produced. A consumer who ranks a TIER_1 country against a TIER_3 country is doing so outside the ISI framework.

---

## 12. Sensitivity Analysis Framework

### 12.1 Purpose

The severity weights are expert-calibrated ordinal judgments (Section 8.5). To demonstrate that the ISI framework is robust to the inherent arbitrariness of these weights, we implement a systematic sensitivity analysis.

### 12.2 Perturbation Protocol

Six perturbation scenarios are applied:

1. **Weights +30%:** All severity weights multiplied by 1.3
2. **Weights −30%:** All severity weights multiplied by 0.7
3. **Alpha +30%:** Exponential penalty parameter α multiplied by 1.3
4. **Alpha −30%:** Exponential penalty parameter α multiplied by 0.7
5. **Both +30%:** Weights ×1.3 AND α ×1.3 (worst-case for over-penalization)
6. **Both −30%:** Weights ×0.7 AND α ×0.7 (worst-case for under-penalization)

For each scenario, the adjusted composite is recomputed for all countries, and the resulting rankings are compared against baseline.

### 12.3 Stability Metrics

- **Spearman rank correlation (ρ):** Measures ordinal agreement between baseline and perturbed rankings. ρ = 1.0 → identical ordinal ranking.
- **Maximum rank shift:** The largest absolute rank change for any country under any perturbation scenario.
- **Mean absolute deviation (MAD):** Average absolute rank change across all countries and scenarios.

### 12.4 Verdict Classification

| Verdict | Spearman ρ (min) | Max Rank Shift | Interpretation |
|---------|:---------------:|:--------------:|----------------|
| ROBUST | ≥ 0.9 | ≤ 1 | Rankings are essentially invariant to parameter choices |
| SENSITIVE | ≥ 0.7 | ≤ 3 | Some rank shuffling at margins; ordinal structure preserved |
| UNSTABLE | < 0.7 | > 3 | Rankings are materially affected by parameter choices |

**Acceptance criterion:** An UNSTABLE verdict on a 7-country Phase 1 scope would indicate fundamental calibration problems requiring investigation.

---

## 13. External Validation Layer

### 13.1 Rationale

An index that cannot be externally validated is an index that cannot be trusted. The ISI external validation layer provides three types of empirical anchoring:

### 13.2 Known Case Validation

For countries with well-established economic profiles, the ISI outputs are checked against structural expectations:

| Country | Expected Composite Range | Expected Class | Rationale |
|---------|:------------------------:|:--------------:|-----------|
| Germany | [0.10, 0.50] | IMPORTER | Major industrial economy, net importer across most axes |
| China | [0.05, 0.40] | PRODUCER | Major exporter in critical inputs and defense |
| Norway | [0.05, 0.45] | BALANCED | Energy exporter, otherwise net importer |
| Japan | [0.10, 0.55] | IMPORTER | Resource-poor, high external dependency |
| United States | [0.05, 0.40] | PRODUCER | Energy/defense/materials exporter |

If a country falls outside its expected range or has an unexpected structural class, the validation layer flags a FAIL. This is a sanity check, not a calibration target — the ISI should produce results consistent with known economic realities.

### 13.3 Cross-Axis Sanity Check

No single axis should dominate cross-country variance implausibly. If one axis contributes >60% of total cross-country score variance, this suggests that axis may be capturing a measurement artifact rather than genuine structural diversity.

### 13.4 Validation Output

The validation layer produces a structured `validation_summary` with:
- Per-case PASS/FAIL/SKIP results
- Aggregate verdict (PASS if 0 failures, FAIL otherwise)
- Cross-axis variance contributions and sanity warnings

---

## 14. Shock Simulation Framework

### 14.1 Purpose

The ISI measures **static** bilateral concentration. But policymakers need to understand **dynamic** vulnerability: what happens if a key supplier is removed? The shock simulation layer quantifies single-point-of-failure vulnerability.

### 14.2 Model

For an axis with HHI score $H$ and top supplier with market share $s_1$, the simulated HHI after removing the top supplier under proportional redistribution is:

$$
H_{\text{after}} = \frac{H - s_1^2}{(1 - s_1)^2}
$$

This assumes the removed supplier's share is redistributed proportionally among remaining suppliers. The model is applied sequentially for top-2 removal.

### 14.3 Vulnerability Classification

| Class | |ΔH| from top-1 removal | Interpretation |
|-------|:----------------------:|----------------|
| LOW | < 0.05 | Minimal single-supplier vulnerability |
| MODERATE | [0.05, 0.15) | Some concentration in top supplier |
| HIGH | [0.15, 0.30) | Significant single-point-of-failure risk |
| CRITICAL | ≥ 0.30 | Dominant-supplier removal fundamentally restructures the axis |

### 14.4 Limitations

The proportional redistribution model is a simplification. In reality:
- Remaining suppliers may not have capacity to absorb the removed share
- Prices and trade patterns would adjust endogenously
- New suppliers may enter the market

The simulation provides an **upper bound on immediate structural impact**, not a forecast of actual post-disruption outcomes.

---

## 15. Output Integrity Guarantees

### 15.1 Required Fields

Every composite output MUST contain the following fields. Absence of any field triggers a hard-fail error:

**Composite-level:** `country`, `country_name`, `isi_composite`, `composite_raw`, `composite_adjusted`, `classification`, `axes_included`, `axes_excluded`, `confidence`, `comparability_tier`, `strict_comparability_tier`, `severity_analysis`, `structural_degradation_profile`, `structural_class`, `stability_analysis`, `interpretation_flags`, `interpretation_summary`, `scope`, `methodology_version`, `warnings`, `axes`, `exclude_from_rankings`, `ranking_partition`.

**Axis-level:** `country`, `axis_id`, `axis_slug`, `score`, `basis`, `validity`, `coverage`, `source`, `warnings`, `channel_a_concentration`, `channel_b_concentration`, `data_quality_flags`, `degradation_severity`, `data_severity`.

### 15.2 Invariant Enforcement

Three independent enforcement layers verify output integrity:

1. **`CompositeResult.to_dict()`** — enforces TIER_4 nullification at construction time
2. **`validate_composite_result()`** — independent validation of all mandatory fields and invariants
3. **`enforce_output_integrity()`** — field-by-field completeness check with machine-readable violation reports

Any violation at any layer raises `ValueError` immediately. No silent degradation. No partial outputs.

### 15.3 TIER_4 Nullification Invariant

**Definition.** For any country $i$ with $\tau(i) = \text{TIER\_4}$:

$$
\bar{A}_i^{(adj)} = \text{NULL} \wedge \text{exclude\_from\_rankings}(i) = \text{TRUE}
$$

This invariant is checked at all three enforcement layers. It is the ONLY hard-coded behavioral constraint in the output layer (all other behaviors are derived from data and parameters).

---

*End of Methodology Specification.*
