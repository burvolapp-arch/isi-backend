# ISI Axis 6 — Freeze Declaration

Version: 0.1
Status: **FROZEN**
Date: 2026-02-08
Axis: Logistics / Freight Dependency
Project: Panargus / International Sovereignty Index (ISI)

---

## 1. Identification

| Field | Value |
|---|---|
| Axis number | 6 |
| Axis name | Logistics / Freight Dependency |
| Version | 0.1 |
| Scope | EU-27 (27 member states) |
| Reference window | 2022–2024, pooled to a single score per country |
| Score range | [0, 1] |
| Concentration metric | Herfindahl-Hirschman Index (HHI) |
| Unit of measurement | Thousand tonnes (THS_T) |
| Aggregation | Volume-weighted average across two channels |
| Channels | A (transport mode concentration), B (partner concentration per mode) |

---

## 2. Lock Declarations

### 2.1 Conceptual definition: LOCKED

The axis measures the degree to which a country's international freight is concentrated across (a) a limited number of transport modes, and (b) a limited number of bilateral freight partners within each transport mode. It produces a single scalar per country. Higher values indicate greater structural concentration. It does not measure route concentration, infrastructure quality, supply chain resilience, transit country dependence, logistics performance, or policy adequacy.

### 2.2 Scope: LOCKED

| Property | Locked value |
|---|---|
| Geographic | EU-27: AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU, IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK |
| Temporal | 2022–2024, tonnage pooled across all three years |
| Mode set (Channel A) | {road, rail, maritime, IWW} |
| Mode set (Channel B) | {road, rail, maritime} |
| Intra-EU treatment | Intra-EU freight is counted as dependency |
| Flow direction | Reporter-declared flows; maritime filtered to inward (imports) |
| Partner dimension | Country-level (MCA-to-country aggregation for maritime) |

### 2.3 Data sources: LOCKED

| # | Dataset | Eurostat code | Role |
|---|---------|---------------|------|
| 1 | International road freight — loaded goods by country of unloading | `road_go_ia_lgtt` | Channel B: road partner concentration (outward) |
| 2 | International road freight — unloaded goods by country of loading | `road_go_ia_ugtt` | Channel B: road partner concentration (inward) |
| 3 | International rail goods transport — from reporting country to country of unloading | `rail_go_intgong` | Channel B: rail partner concentration |
| 4 | Maritime goods transport — main ports, by partner Maritime Coastal Area (22 per-country tables) | `mar_go_am_{iso2}` | Channel B: maritime partner concentration |
| 5 | Modal split of inland freight transport | `tran_hv_frmod` | Channel A: mode shares (road, rail, IWW percentages) |

No third-party, composite, qualitative, or survey data sources are used.

### 2.4 Channel definitions: LOCKED

**Channel A — Transport Mode Concentration**

For each reporter $i$, compute mode shares across active modes $m \in M_i$ where $M_i \subseteq \{\text{road}, \text{rail}, \text{maritime}, \text{IWW}\}$, determined by data availability per country.

$$s_i^{m} = \frac{T_i^{m}}{\sum_{m} T_i^{m}}$$

$$C_i^{(A)} = \sum_{m} \left( s_i^{m} \right)^2$$

Channel A weight: $W_i^{(A)} = \sum_{m} T_i^{m}$ (total tonnage across all active modes, including IWW).

**Channel B — Partner Concentration per Mode**

For each reporter $i$ and each mode $m \in \{\text{road}, \text{rail}, \text{maritime}\}$ with bilateral data, compute partner shares and per-mode HHI:

$$s_{i,j}^{m} = \frac{V_{i,j}^{m}}{\sum_{j} V_{i,j}^{m}}$$

$$C_i^{(B,m)} = \sum_{j} \left( s_{i,j}^{m} \right)^2$$

Aggregate across modes by tonnage weighting:

$$C_i^{(B)} = \frac{\sum_{m} C_i^{(B,m)} \cdot V_i^{m}}{\sum_{m} V_i^{m}}$$

Channel B weight: $W_i^{(B)} = \sum_{m} V_i^{m}$ (total bilateral tonnage across road, rail, maritime only).

IWW is excluded from Channel B because the Eurostat IWW dataset has no bilateral partner dimension.

**Cross-channel aggregation**

$$L_i = \frac{C_i^{(A)} \cdot W_i^{(A)} + C_i^{(B)} \cdot W_i^{(B)}}{W_i^{(A)} + W_i^{(B)}}$$

$W_i^{(A)} \geq W_i^{(B)}$ for all countries because Channel A includes IWW tonnage and Channel B does not. The formula is not equivalent to a simple arithmetic mean when IWW tonnage is non-zero.

Edge cases: if $W_i^{(A)} = 0$, score reduces to $C_i^{(B)}$. If $W_i^{(B)} = 0$, score reduces to $C_i^{(A)}$. If both are zero, the country is omitted (OMITTED_NO_DATA). In practice, all 27 EU-27 countries produce valid scores.

### 2.5 Pipeline architecture: LOCKED

| Script | File | Lines | Purpose |
|---|---|---|---|
| 1 | `scripts/ingest_logistics_freight_manual.py` | 812 | Validate presence and structure of raw CSVs |
| 2 | `scripts/parse_logistics_freight_raw.py` | 658 | Normalize schemas, produce flat bilateral CSV |
| 3 | `scripts/compute_logistics_channel_a.py` | 279 | Channel A: mode concentration HHI |
| 4 | `scripts/compute_logistics_channel_b.py` | 460 | Channel B: partner concentration per mode, volume-weighted aggregate |
| 5 | `scripts/aggregate_logistics_freight_axis.py` | 385 | Cross-channel aggregation, final score |

All scripts are stdlib-only Python (csv, sys, pathlib, collections, math). No external dependencies. Scripts communicate via CSV files. No script imports another. Output is deterministic and reproducible.

### 2.6 Outputs: LOCKED

| Output | Location |
|---|---|
| Flat bilateral file | `data/processed/logistics/logistics_freight_bilateral_flat.csv` |
| Channel A scores | `data/processed/logistics/logistics_channel_a_mode_concentration.csv` |
| Channel B mode shares | `data/processed/logistics/logistics_channel_b_mode_shares.csv` |
| Channel B mode concentration | `data/processed/logistics/logistics_channel_b_mode_concentration.csv` |
| Channel B aggregate | `data/processed/logistics/logistics_channel_b_concentration.csv` |
| Channel B volumes | `data/processed/logistics/logistics_channel_b_volumes.csv` |
| Final scores | `data/processed/logistics/logistics_freight_axis_score.csv` |

Final score schema: `reporter, axis6_logistics_score, channel_a_mode_hhi, channel_b_partner_hhi, weight_a_tonnes, weight_b_tonnes, modes_used, aggregation_case`.

27/27 EU member states scored. Both channels active for all 27.

### 2.7 Coverage structure: LOCKED

| Country set | Channel A modes | Channel B modes |
|---|---|---|
| MT | {maritime} | {maritime} |
| CY | {road, maritime} | {road, maritime} |
| AT, CZ, HU, LU, SK | {road, rail} + IWW where available | {road, rail} |
| Remaining 20 | {road, rail, maritime} + IWW where available | {road, rail, maritime} |

---

## 3. Documented Warnings (Carried Forward)

These warnings are non-fatal, documented, and accepted for v0.1. No fixes are proposed or permitted under this version.

| ID | Warning | Severity |
|---|---|---|
| W-1 | Entrepot/hub masking: NL and BE scores understate their systemic importance as continental freight hubs; countries trading through NL/BE have inflated partner concentration masking true origin | HIGH |
| W-2 | Geographic determinism: MT (Channel A HHI = 1.0), CY, and landlocked countries have structurally constrained scores reflecting geography, not policy choices; no correction is appropriate | MEDIUM |
| W-3 | Maritime-energy overlap: maritime tonnage includes energy commodity transport, creating partial redundancy with Axis 3 (Energy) | MEDIUM |
| W-4 | Tonnage blindness: all freight is treated equally per tonne regardless of commodity type; strategic commodity differentiation is absent | MEDIUM |
| W-5 | No route/chokepoint data: the axis cannot detect Suez, Bosporus, or any physical corridor dependency; the original route/corridor channel concept was killed during feasibility after 25+ API probes confirmed no public data exists | LOW |

---

## 4. GO Decision

The hostile audit (`docs/audit/axis_vi_hostile_audit_v01.md`) returned the following results:

| Audit area | Verdict |
|---|---|
| Scope Verification | PASS |
| Structural Integrity | PASS |
| Small-Economy Amplification | PASS WITH WARNING |
| Mode-Dominance Artifacts | PASS |
| Entrepot Masking | PASS WITH WARNING |
| Landlocked Distortions | PASS |
| IWW Asymmetry | PASS WITH WARNING |
| Channel Interaction | PASS |
| Cross-Axis Contamination | PASS WITH WARNING |
| Interpretive Failure Modes | PASS WITH WARNING |

Overall audit verdict: **GO**.

Conditions satisfied for freeze:

1. All 27 EU-27 countries scored.
2. All scores in [0, 1], enforced by pipeline validation.
3. All share vectors sum to 1.0 within tolerance 1e-9.
4. No NaN, null, or infinite values pass through the pipeline.
5. Single-mode countries (MT) handled correctly.
6. Landlocked countries have no maritime data (structurally correct).
7. IWW asymmetry documented and quantitatively bounded.
8. All five mandatory warnings carried forward without proposed fixes.
9. No audit section returned FAIL.

---

## 5. What MAY Change in v0.2+

The following elements are version-scoped to v0.1 and may be revised in future versions:

1. Mode set expansion — if bilateral partner data for air freight, IWW, or pipeline becomes publicly available.
2. Reference window extension — to include years beyond 2024.
3. Partner dimension granularity — higher-resolution partner data if Eurostat publishes sub-country freight breakdowns for road or rail.
4. Maritime MCA-to-country mapping refinements.
5. Commodity disaggregation of freight tonnage, if commodity-by-partner-by-mode data becomes available.
6. Number of modes entering each channel.

Any such change requires incrementing the version to v0.2 or higher and re-executing the hostile audit.

---

## 6. What is INVARIANT Across All Versions

The following elements are permanent architectural commitments for Axis 6 and may not be changed in any future version:

1. The axis measures **logistics / freight dependency** as bilateral freight concentration per EU-27 country.
2. The score is a scalar in [0, 1]. Higher values indicate greater concentration.
3. HHI is the concentration metric.
4. The axis decomposes into exactly **two channels**: mode concentration (Channel A) and partner concentration per mode (Channel B).
5. Cross-channel aggregation is volume-weighted.
6. The unit of analysis is a country, not the EU as a bloc.
7. Intra-EU dependency is real dependency.
8. The axis measures structural concentration, not policy quality or strategic alignment.

---

## 7. Supporting Documents

| Document | Location |
|---|---|
| Methodology specification | `docs/methodology/logistics_freight_axis_v01.md` |
| Data availability matrix | `docs/methodology/axis_vi_data_availability_matrix.md` |
| Pipeline design | `docs/methodology/axis_vi_pipeline_design.md` |
| Hostile validation plan | `docs/methodology/axis_vi_hostile_validation_plan.md` |
| Feasibility assessment | `docs/methodology/axis_vi_feasibility_assessment.md` |
| Hostile audit results | `docs/audit/axis_vi_hostile_audit_v01.md` |
| Freeze declaration | This document |

---

## 8. Freeze Statement

Axis 6 (Logistics / Freight Dependency) v0.1 is formally frozen.

No further methodological, data, formula, weighting, pipeline, or scope changes are permitted without incrementing the version number to v0.2 or higher.

This declaration supersedes all prior draft and interim status markers for Axis 6. The methodology document (`logistics_freight_axis_v01.md`) retains its DRAFT header for archival fidelity but is now governed by this freeze.

All work on Axis 6 v0.1 is complete. Any future modification constitutes a new version.

---

End of document.
