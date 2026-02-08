# ISI Axis 4 — Freeze Declaration

Version: 0.1
Status: **FROZEN**
Date: 2026-02-07
Axis: Technology / Semiconductor Dependency
Project: Panargus / International Sovereignty Index (ISI)

---

## 1. Identification

| Field | Value |
|---|---|
| Axis number | 4 |
| Axis name | Technology / Semiconductor Dependency |
| Version | 0.1 |
| Scope | EU-27 (27 member states) |
| Reference window | 2022–2024, aggregated to a single 2024-labelled score |
| Score range | [0, 1] |
| Concentration metric | Herfindahl-Hirschman Index (HHI) |
| Aggregation | Volume-weighted average across two channels |

---

## 2. Lock Declarations

### 2.1 Methodology: LOCKED

The methodology document is `docs/methodology/tech_axis_v01_design_validation.md`.
The close-off note is `docs/methodology/tech_axis_v01_closeoff.md`.
No further amendments to v0.1 methodology are permitted.

### 2.2 Data sources: LOCKED

| Property | Locked value |
|---|---|
| Source | Eurostat Comext, dataset ds-045409 |
| Granularity | CN8-level for HS 8541; HS4-level for HS 8542 |
| Format | Bilateral partner CSV, manual download |
| Raw file | `data/raw/tech/eu_comext_semiconductors_cn8_2022_2024.csv` |
| Product codes | 85411000, 85412100, 85412900, 85413000, 85416000, 85419000, 8542 |
| Structural exclusion | CN 854140xx (solar photovoltaic cells) — absent from data |
| Flow | Imports only (flow code 1) |
| Indicator | VALUE_IN_EUROS |

### 2.3 Parser logic: LOCKED

| Property | Locked value |
|---|---|
| CN8 → category mapping | `docs/audit/tech_cn8_category_mapping_v01.csv` |
| Mapping validated at runtime | Yes — hardcoded map cross-checked against file |
| Defensive 854140 guard | Fatal abort if any product code starts with `854140` |
| Country code mapping | GR → EL |
| Exclusions | EU27_2020 aggregate; self-pairs; zero/missing values |
| Column access | Index-based (accommodates duplicate TIME_PERIOD column) |

### 2.4 Channel definitions: LOCKED

**Channel A — Aggregate Supplier Concentration**

For each reporter $i$, aggregate all import value across all product codes
and all years. Compute supplier shares and HHI.

$$C_i^{(A)} = \sum_j \left( s_{i,j}^{(A)} \right)^2$$

**Channel B — Category-Weighted Supplier Concentration**

For each reporter $i$ and category $k \in \{\text{legacy\_discrete}, \text{legacy\_components}, \text{integrated\_circuits}\}$,
compute per-category HHI, then volume-weight across categories.

$$C_i^{(B)} = \frac{\sum_k C_i^{(B,k)} \cdot V_i^{(k)}}{\sum_k V_i^{(k)}}$$

**Cross-channel aggregation**

$$T_i = \frac{C_i^{(A)} \cdot W_i^{(A)} + C_i^{(B)} \cdot W_i^{(B)}}{W_i^{(A)} + W_i^{(B)}}$$

By construction $W_i^{(A)} = W_i^{(B)}$, so $T_i = (C_i^{(A)} + C_i^{(B)}) / 2$.

---

## 3. Documented Warnings (Carried Forward)

These warnings are non-fatal, documented, and accepted for v0.1.
No fixes are proposed or permitted under this version.

| ID | Warning | Severity |
|---|---|---|
| W-2 | Re-export blindness: bilateral trade records shipping country, not country of origin | MEDIUM |
| W-3 | Trade ≠ sovereignty: import concentration does not capture domestic fabrication capacity | LOW |
| W-4 | HS 8542 at HS4 aggregate: integrated circuits not decomposed into subcategories | LOW |
| W-5 | Intra-EU trade included: EU partners appear as suppliers (by design) | LOW |
| W-6 | Three-year window: 2022–2024 period may include pandemic-era distortions | LOW |

W-1 (solar PV contamination) was HIGH severity and is **RESOLVED** via CN8 migration.

---

## 4. Version Boundary

### What v0.2+ MAY change

- Data source (e.g., switching to UN Comtrade, adding CN8 subcodes for HS 8542)
- Reference window (e.g., extending to 2025 data)
- Category mapping (e.g., adding new CN8 subcodes, splitting `integrated_circuits`)
- Number of categories in Channel B
- Adding a Channel C (e.g., origin-adjusted trade data to address W-2)

### What is INVARIANT across all versions

- Axis measures **semiconductor import supplier concentration** per EU-27 country
- Score is a scalar in [0, 1], higher = more concentrated = more dependent
- HHI is the concentration metric
- Channel A is always aggregate supplier concentration (no product decomposition)
- Channel B is always product/category-weighted supplier concentration
- Cross-channel aggregation is always volume-weighted
- Unit of analysis is a country, not the EU as a bloc
- Intra-EU dependency is real dependency

---

## 5. Pipeline and Outputs

| Script | Purpose |
|---|---|
| `scripts/ingest_tech_comext_manual.py` | Raw file presence and structure validation |
| `scripts/parse_tech_comext_raw.py` | Parse, filter, map, emit flat bilateral table |
| `scripts/compute_tech_channel_a.py` | Channel A: aggregate HHI |
| `scripts/compute_tech_channel_b.py` | Channel B: category-weighted HHI |
| `scripts/aggregate_tech_cross_channel.py` | Cross-channel aggregation → final score |

| Output | Location |
|---|---|
| Final scores | `data/processed/tech/tech_dependency_2024_eu27.csv` |
| Full audit trail | `data/processed/tech/tech_dependency_2024_eu27_audit.csv` |
| Hostile validation | `docs/audit/tech_axis_v01_hostile_validation.md` |
| Category mapping | `docs/audit/tech_cn8_category_mapping_v01.csv` |

27/27 EU member states scored. Both channels active for all 27.

---

## 6. Freeze Statement

Axis 4 (Technology / Semiconductor Dependency) v0.1 is formally frozen.

No further methodological, data, parser, or formula changes are permitted
without incrementing the version number to v0.2 or higher.

This declaration supersedes all prior draft and interim status markers
for Axis 4.
