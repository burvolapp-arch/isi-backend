# Critical Inputs / Raw Materials Dependency Axis — v0.1
# Pre-Implementation Design Validation

Status: LOCKED
Date: 2026-02-07
Axis: Critical Inputs / Raw Materials Dependency (Axis 5)
Project: Panargus / International Sovereignty Index (ISI)

---

## 1. Purpose of the Axis

The axis produces a single scalar score in [0, 1] per
EU-27 country. The score measures the degree to which a
country's imports of critical raw materials are
concentrated among a small number of foreign supplier
countries.

Higher values indicate greater supplier concentration
(more dependency). Lower values indicate greater
diversification (more autonomy).

The axis does not measure industrial capacity, domestic
production, strategic reserves, recycling, substitution
feasibility, processing capability, or geopolitical
alignment.

---

## 2. Measurement Definition

### 2.1 Core metric

Herfindahl-Hirschman Index (HHI), computed on supplier-
country import-value shares.

For any set of supplier shares s_{i,j}:

  HHI_i = SUM_j ( s_{i,j} )^2

HHI_i ∈ [0, 1].

### 2.2 Dependency definition

Dependency is defined as reliance on a small number of
foreign supplier countries for critical material imports,
measured by import value (EUR).

The definition is structural. It is blind to:
- Alliance membership
- Trade agreements
- Political alignment
- Sanctions status
- Geographic proximity

Intra-EU imports are included as real dependency. Austria
importing from Germany is dependency. Germany importing
from China is dependency. No safe-supplier exemption
exists.

### 2.3 Locked parameters

| Parameter               | Locked Value                                      |
|-------------------------|---------------------------------------------------|
| Axis name               | Critical Inputs / Raw Materials Dependency        |
| Version                 | 0.1                                               |
| Reference year          | 2024                                              |
| Data window             | 2022–2024 (3-year aggregation)                    |
| Geographic scope        | EU-27                                             |
| Unit of analysis        | Individual country (NOT the EU bloc)              |
| Score range             | [0, 1]                                            |
| Concentration metric    | Herfindahl-Hirschman Index (HHI)                  |
| Aggregation method      | Volume-weighted average across 2 channels         |
| Normalisation           | None                                              |
| Rescaling               | None                                              |
| Channels                | 2 (A: Aggregate, B: Material-Group)               |
| Material universe       | 66 CN8 codes in 5 groups                          |
| Data source             | Eurostat Comext (CN8, manual download)             |
| Value basis             | VALUE_IN_EUROS (import value)                     |
| Quantity basis           | Not used                                          |

---

## 3. Material Scope

### 3.1 Universe definition

The material universe consists of 66 unique CN8 codes
assigned to 5 material groups:

| Material group              | CN8 code count |
|-----------------------------|----------------|
| rare_earths                 | 15             |
| battery_metals              | 16             |
| defense_industrial_metals   | 20             |
| semiconductor_inputs        | 8              |
| fertilizer_chokepoints      | 7              |
| **Total**                   | **66**         |

Each CN8 code is assigned to exactly one material group.
No CN8 code appears in more than one group. No CN8 code
is unassigned.

### 3.2 Mapping authority

The authoritative CN8-to-material-group mapping is:

  docs/mappings/critical_materials_cn8_mapping_v01.csv

Schema:
  cn8_code, material_group, material_name, stage,
  sovereignty_rationale, contamination_risk, notes

This file is the single source of truth. The parser must
load this mapping at runtime and reject any CN8 code not
present in the mapping. No hardcoded code lists are
permitted in pipeline scripts beyond a defensive cross-
check against the CSV.

### 3.3 Scope boundary

Included:
- Ores
- Concentrates
- Refined metals
- Chemical precursors

Excluded:
- Finished products
- Manufactured articles
- Downstream goods (magnets, batteries, fertiliser blends)
- Semi-finished intermediate products beyond the
  precursor stage

### 3.4 Contamination controls

The mapping file documents contamination risk per CN8
code (LOW, MEDIUM, HIGH). Known contamination risks:

- 28256000 bundles germanium oxides with zirconium
  dioxide. Cannot be separated at CN8 level.
- 26159000 bundles niobium, tantalum, and vanadium ores.
  Cannot be separated at CN8 level.
- 28499050 bundles carbides of aluminium, chromium,
  molybdenum, vanadium, tantalum, and titanium. Cannot
  be separated at CN8 level.
- 81123100 bundles unwrought hafnium with waste, scrap,
  and powders in a single code.

These are documented limitations. No heuristic correction
is applied. No exclusion is warranted. The codes are
retained with their contamination risk labels.

### 3.5 Material universe freeze

The 66-code universe is FIXED for v0.1. No additions,
removals, or group reassignments are permitted without
incrementing the version number.

---

## 4. Channel Architecture

### 4.1 Channel A — Aggregate Supplier Concentration

All 66 CN8 codes are pooled. No material-group
decomposition is applied.

For each importing country i:

  V_{i,j}^{(A)} = total import value (EUR) from supplier
  country j, summed across all 66 CN8 codes and all years
  in the data window (2022–2024).

  s_{i,j}^{(A)} = V_{i,j}^{(A)} / SUM_j V_{i,j}^{(A)}

  C_i^{(A)} = SUM_j ( s_{i,j}^{(A)} )^2

  W_i^{(A)} = SUM_j V_{i,j}^{(A)}

C_i^{(A)} ∈ [0, 1].

### 4.2 Channel B — Material-Group Concentration

Supplier-country HHI is computed separately per material
group, then aggregated via import-value weighting.

For each importing country i and material group
k ∈ {rare_earths, battery_metals, defense_industrial_metals,
semiconductor_inputs, fertilizer_chokepoints}:

  V_{i,j}^{(B,k)} = total import value (EUR) from
  supplier j in group k, summed across all CN8 codes in
  group k and all years in the data window.

  s_{i,j}^{(B,k)} = V_{i,j}^{(B,k)} / SUM_j V_{i,j}^{(B,k)}

  C_i^{(B,k)} = SUM_j ( s_{i,j}^{(B,k)} )^2

  V_i^{(k)} = SUM_j V_{i,j}^{(B,k)}

Aggregate Channel B:

  C_i^{(B)} = SUM_k [ C_i^{(B,k)} * V_i^{(k)} ]
              / SUM_k V_i^{(k)}

  W_i^{(B)} = SUM_k V_i^{(k)}

Groups with zero import value for a given country are
excluded from the weighted average.

C_i^{(B)} ∈ [0, 1].

### 4.3 Cross-channel aggregation

  M_i = ( C_i^{(A)} * W_i^{(A)} + C_i^{(B)} * W_i^{(B)} )
        / ( W_i^{(A)} + W_i^{(B)} )

By construction, W_i^{(A)} = W_i^{(B)} for all importing
countries (both channels consume the same total import
value). The formula therefore reduces to:

  M_i = ( C_i^{(A)} + C_i^{(B)} ) / 2

The volume-weighted formula is retained for generality
and consistency with other ISI axes.

Edge cases:
- If W_i^{(A)} = 0, score collapses to C_i^{(B)}.
- If W_i^{(B)} = 0, score collapses to C_i^{(A)}.
- If both = 0, country is omitted (OMITTED_NO_DATA).

M_i ∈ [0, 1].

---

## 5. Data Source Specification

### 5.1 Source identity

| Property        | Value                                              |
|-----------------|----------------------------------------------------|
| Source           | Eurostat Comext                                    |
| Dataset          | ds-045409                                          |
| Granularity      | CN8 (Combined Nomenclature, 8-digit)               |
| Flow             | Imports only (flow code 1)                         |
| Indicator        | VALUE_IN_EUROS                                     |
| Reporter scope   | EU-27 member states                                |
| Partner scope    | All countries (intra-EU + extra-EU)                |
| Years            | 2022, 2023, 2024                                   |
| Format           | Bulk CSV, manual download                          |
| Access           | https://ec.europa.eu/eurostat/comext/               |

### 5.2 Raw file

Expected location:

  data/raw/critical_inputs/eu_comext_critical_materials_cn8_2022_2024.csv

Manual download. No API. No authentication required.

### 5.3 Required fields

| Field name (Comext)  | Required | Use in pipeline                          |
|----------------------|----------|------------------------------------------|
| DECLARANT_ISO        | YES      | Reporter / importing country (geo code)  |
| PARTNER_ISO          | YES      | Supplier country (partner geo code)      |
| PRODUCT_NC           | YES      | CN8 code — filter against mapping table  |
| FLOW                 | YES      | Must equal 1 (imports)                   |
| PERIOD               | YES      | Year — filter 2022, 2023, 2024           |
| VALUE_IN_EUROS       | YES      | Import value (EUR) — share basis         |
| QUANTITY_IN_KG       | NO       | Not used in v0.1                         |
| SUP_QUANTITY         | NO       | Not used in v0.1                         |

### 5.4 Exclusions applied during parsing

- Rows where FLOW ≠ 1 (imports)
- Rows where PERIOD ∉ {2022, 2023, 2024}
- Rows where PRODUCT_NC is not in the 66-code mapping
  table
- Rows where DECLARANT_ISO ∉ EU-27
- Rows where PARTNER_ISO = EU27_2020 or other aggregate
  partner codes
- Self-pairs (DECLARANT_ISO = PARTNER_ISO after code
  mapping)
- Rows with VALUE_IN_EUROS = 0, null, or missing
- Country code mapping: GR → EL

### 5.5 No supplementary data

No APIs, estimations, imputations, price adjustments,
exchange-rate conversions, or quantity-based corrections
are applied.

---

## 6. Computational Constraints

### 6.1 Share constraints

For every (reporter, channel/group) combination:

  SUM_j s_{i,j} = 1.0    (tolerance: 1e-9)

Hard-fail if any individual share < 0 or > 1.

### 6.2 HHI constraints

For every computed HHI value (Channel A, per-group
Channel B, aggregate Channel B):

  HHI ∈ [0, 1]

Hard-fail if violated.

### 6.3 Final score constraints

For every importing country in the output:

  M_i ∈ [0, 1]

Hard-fail if violated.

### 6.4 CN8 code validation

At parse time, the parser must:
- Load the 66-code mapping from the authoritative CSV
- Reject any PRODUCT_NC not present in the mapping
- Reject any PRODUCT_NC that appears in the raw data
  but has zero matching rows after filtering (log as
  warning, not fatal)
- Confirm that all 66 CN8 codes in the mapping are
  present in the raw data for at least one reporter
  (log missing codes as warnings)

### 6.5 EU-27 coverage check

After scoring, the pipeline must verify that all 27
EU member states produce a score or are explicitly
documented as OMITTED_NO_DATA.

No silent omissions are permitted.

---

## 7. Audit & Validation Requirements

### 7.1 Pipeline architecture

Following the project convention (5 sequential scripts):

| Script                                | Task ID                  |
|---------------------------------------|--------------------------|
| ingest_critical_inputs_comext.py      | ISI-CRIT-INGEST          |
| parse_critical_inputs_comext_raw.py   | ISI-CRIT-PARSE           |
| compute_critical_inputs_channel_a.py  | ISI-CRIT-CHANNEL-A       |
| compute_critical_inputs_channel_b.py  | ISI-CRIT-CHANNEL-B       |
| aggregate_critical_inputs_cross_channel.py | ISI-CRIT-AGGREGATE  |

### 7.2 Script 1: ingest_critical_inputs_comext.py

Purpose: Validate presence and structure of the manually
downloaded Comext CSV.
Input: data/raw/critical_inputs/eu_comext_critical_materials_cn8_2022_2024.csv
Output: Console output only (validation gate).
Actions:
- Verify file exists
- Read header row
- Verify required field names present
- Count data rows
- Report PASS/FAIL

### 7.3 Script 2: parse_critical_inputs_comext_raw.py

Purpose: Parse raw Comext CSV into flat bilateral import
table, applying all filters and the CN8-to-group mapping.
Input: Raw CSV + mapping CSV
Outputs:
- data/processed/critical_inputs/critical_inputs_2022_2024_flat.csv
  Schema: reporter, partner, cn8_code, material_group,
  year, value
- data/processed/critical_inputs/critical_inputs_2022_2024_audit.csv
  Schema: reporter, n_partners, total_value, n_cn8_codes,
  n_groups
- data/audit/critical_inputs_parser_waterfall_2024.csv
  Schema: stage, row_count

Actions:
- Read raw CSV (UTF-8)
- Filter FLOW = imports
- Filter PERIOD ∈ {2022, 2023, 2024}
- Load CN8 mapping table; filter PRODUCT_NC to 66 valid
  codes
- Map each retained CN8 code to its material_group
- Filter DECLARANT_ISO ∈ EU-27
- Map GR → EL
- Exclude aggregate partner codes (EU27_2020, WORLD, etc.)
- Exclude self-pairs
- Exclude zero/null/missing values
- Write flat output
- Write per-reporter audit summary
- Write parser waterfall (row counts at each stage)

### 7.4 Script 3: compute_critical_inputs_channel_a.py

Purpose: Compute aggregate supplier concentration across
all critical materials.
Input: Flat bilateral table
Outputs:
- data/processed/critical_inputs/critical_inputs_channel_a_shares.csv
  Schema: reporter, partner, share
- data/processed/critical_inputs/critical_inputs_channel_a_concentration.csv
  Schema: reporter, concentration
- data/processed/critical_inputs/critical_inputs_channel_a_volumes.csv
  Schema: reporter, total_value

Methodology:
- For each reporter i, sum all import value across all
  CN8 codes, all groups, and all years.
- Compute supplier shares and HHI.
- Apply all constraints from §6.

### 7.5 Script 4: compute_critical_inputs_channel_b.py

Purpose: Compute material-group-weighted supplier
concentration.
Input: Flat bilateral table
Outputs:
- data/processed/critical_inputs/critical_inputs_channel_b_group_shares.csv
  Schema: reporter, material_group, partner, share
- data/processed/critical_inputs/critical_inputs_channel_b_group_concentration.csv
  Schema: reporter, material_group, concentration,
  group_value
- data/processed/critical_inputs/critical_inputs_channel_b_concentration.csv
  Schema: reporter, concentration
- data/processed/critical_inputs/critical_inputs_channel_b_volumes.csv
  Schema: reporter, total_value

Methodology:
- For each reporter i and group k:
  - Compute supplier shares within group k
  - Compute per-group HHI
  - Record group import value
- Aggregate across groups via import-value weighting
- Groups with zero volume excluded from weighted average
- Apply all constraints from §6.

### 7.6 Script 5: aggregate_critical_inputs_cross_channel.py

Purpose: Volume-weighted cross-channel aggregation.
Inputs:
- Channel A concentration and volume CSVs
- Channel B concentration and volume CSVs
Outputs:
- data/processed/critical_inputs/critical_inputs_dependency_2024_eu27.csv
  Schema: geo, critical_inputs_dependency
- data/processed/critical_inputs/critical_inputs_dependency_2024_eu27_audit.csv
  Schema: geo, channel_a_concentration, channel_a_volume,
  channel_b_concentration, channel_b_volume,
  critical_inputs_dependency, score_basis

Methodology:
  M_i = ( C_i^{(A)} * W_i^{(A)} + C_i^{(B)} * W_i^{(B)} )
        / ( W_i^{(A)} + W_i^{(B)} )

Edge cases:
- One channel zero → collapse to other
- Both zero → OMITTED_NO_DATA
- Score must be in [0, 1]

### 7.7 Audit artifact inventory

| Script                                      | Artifact                                                                    | Content                                          |
|---------------------------------------------|-----------------------------------------------------------------------------|--------------------------------------------------|
| ingest_critical_inputs_comext.py            | Console output                                                              | File presence, columns, row count                |
| parse_critical_inputs_comext_raw.py         | data/audit/critical_inputs_parser_waterfall_2024.csv                        | Row counts at each filter stage                  |
| parse_critical_inputs_comext_raw.py         | data/processed/critical_inputs/critical_inputs_2022_2024_audit.csv          | Per-reporter summary                             |
| compute_critical_inputs_channel_a.py        | Inline hard-fail checks                                                    | Shares sum, HHI bounds                           |
| compute_critical_inputs_channel_b.py        | Inline hard-fail checks                                                    | Shares sum, per-group HHI, weighted HHI          |
| aggregate_critical_inputs_cross_channel.py  | data/processed/critical_inputs/critical_inputs_dependency_2024_eu27_audit.csv | Per-country channel breakdown, score basis       |

### 7.8 Final output

| File                                                                         | Schema                              |
|------------------------------------------------------------------------------|-------------------------------------|
| data/processed/critical_inputs/critical_inputs_dependency_2024_eu27.csv      | geo, critical_inputs_dependency     |

---

## 8. Known Structural Limitations

The following limitations are inherent to the v0.1 design.
They are documented, accepted, and carried forward. No
corrections or workarounds are proposed.

### L-1: Re-export blindness

Severity: HIGH

Eurostat Comext records the shipping country (country of
consignment or country of origin as declared), not the
country that controls the underlying resource. Countries
that act as entrepôt traders (e.g., the Netherlands,
Belgium, Singapore) may appear as suppliers of materials
they merely transit. This inflates apparent diversification
and masks true origin concentration.

The distortion is particularly acute for critical raw
materials, where a small number of origin countries
(China, DRC, Chile, Australia) dominate global production
but materials may be transhipped through intermediaries.

### L-2: Trade ≠ control

Severity: MEDIUM

Import concentration measures the structure of trade flows.
It does not capture who controls the supply chain at
extraction, processing, or refining stages. A country may
import from diverse trade partners while ultimate supply
control remains concentrated. Conversely, a country may
import from a single partner that sources from multiple
origins.

### L-3: Import value ≠ physical scarcity

Severity: MEDIUM

Concentration is computed on EUR import values. Value
reflects both quantity and unit price. A country importing
small quantities of gallium (high unit value per kg) and
large quantities of phosphate rock (low unit value per kg)
will have its concentration driven by whichever has higher
total EUR value, regardless of physical scarcity or
substitution difficulty.

### L-4: No domestic production visibility

Severity: HIGH

The axis measures import concentration only. A country
with significant domestic production of a critical
material (e.g., Finland for nickel, Poland for copper)
will score identically to a country with zero domestic
production if their import supplier distributions are the
same. Self-sufficiency is invisible.

### L-5: No processing-stage separation

Severity: LOW

The material universe includes ores, concentrates, refined
metals, and chemical precursors. These represent different
positions in the value chain. The axis treats a country
importing raw ore identically to one importing refined
metal. No stage-weighting or value-chain adjustment is
applied.

### L-6: Bundled CN8 codes

Severity: LOW

Several CN8 codes bundle multiple materials into a single
code (see §3.4). Trade flows under these codes cannot be
disaggregated further. This is a limitation of the CN
nomenclature itself.

### L-7: Three-year window effects

Severity: LOW

The 2022–2024 aggregation window may include pandemic-era
and post-invasion supply-chain disruptions that are not
representative of structural dependency. No temporal
adjustment is applied.

---

## 9. Go / No-Go Criteria for Implementation

Implementation proceeds if and only if ALL of the
following are satisfied:

| #  | Criterion                                              | Status       |
|----|--------------------------------------------------------|--------------|
| 1  | Material universe fixed at 66 CN8 codes, 5 groups     | CONFIRMED    |
| 2  | CN8 mapping CSV exists and validates (66 rows, no dups)| CONFIRMED    |
| 3  | Channel architecture locked (A + B, volume-weighted)   | CONFIRMED    |
| 4  | Data source confirmed as Eurostat Comext, CN8 level    | CONFIRMED    |
| 5  | Methodology document frozen (critical_inputs_axis_v01.md) | CONFIRMED |
| 6  | HHI formulation identical to prior axes                | CONFIRMED    |
| 7  | Audit artifact structure defined                       | CONFIRMED    |
| 8  | All known limitations documented (L-1 through L-7)     | CONFIRMED    |
| 9  | Parser waterfall and constraint checks specified       | CONFIRMED    |
| 10 | No unresolved STOP POINTs blocking implementation      | CONFIRMED    |

Decision: **GO**

All design parameters are locked. Implementation may
proceed to Script 1 (ingest).

---

## 10. Structural Alignment with Frozen Axes

| Dimension                       | Defense (Axis 3)          | Tech (Axis 4)              | Critical Inputs (Axis 5)       |
|---------------------------------|---------------------------|----------------------------|--------------------------------|
| Channels                        | 2 (A + B)                | 2 (A + B)                  | 2 (A + B)                      |
| Channel A                       | Supplier HHI (all TIV)   | Supplier HHI (all value)   | Supplier HHI (all value)       |
| Channel B                       | Block-weighted HHI (6)   | Category-weighted HHI (3)  | Group-weighted HHI (5)         |
| Block/group classification      | Regex on description      | CN8 → 3 categories         | CN8 → 5 material groups        |
| Cross-channel formula           | Volume-weighted avg       | Volume-weighted avg        | Volume-weighted avg            |
| W_A = W_B by construction       | Yes                       | Yes                        | Yes                            |
| Effective formula               | (C_A + C_B) / 2          | (C_A + C_B) / 2           | (C_A + C_B) / 2               |
| Scope enforcement               | EU-27 Eurostat codes      | EU-27 Eurostat codes       | EU-27 Eurostat codes           |
| Missing-data handling           | OMITTED_NO_DATA           | OMITTED_NO_DATA            | OMITTED_NO_DATA                |
| Inline constraint checks        | Hard-fail                 | Hard-fail                  | Hard-fail                      |
| Audit trail                     | Waterfall + per-country   | Waterfall + per-country    | Waterfall + per-country        |
| Data source                     | SIPRI Trade Register      | Eurostat Comext (CN8)      | Eurostat Comext (CN8)          |
| Value basis                     | TIV                       | EUR                        | EUR                            |

---

## 11. Directory Structure

```
data/
  raw/
    critical_inputs/
      eu_comext_critical_materials_cn8_2022_2024.csv   ← manual download
  processed/
    critical_inputs/
      critical_inputs_2022_2024_flat.csv
      critical_inputs_2022_2024_audit.csv
      critical_inputs_channel_a_shares.csv
      critical_inputs_channel_a_concentration.csv
      critical_inputs_channel_a_volumes.csv
      critical_inputs_channel_b_group_shares.csv
      critical_inputs_channel_b_group_concentration.csv
      critical_inputs_channel_b_concentration.csv
      critical_inputs_channel_b_volumes.csv
      critical_inputs_dependency_2024_eu27.csv
      critical_inputs_dependency_2024_eu27_audit.csv
  audit/
    critical_inputs_parser_waterfall_2024.csv
docs/
  mappings/
    critical_materials_cn8_mapping_v01.csv              ← authoritative mapping
  methodology/
    critical_inputs_axis_v01.md                         ← frozen methodology
    critical_inputs_axis_v01_design_validation.md       ← this document
scripts/
  ingest_critical_inputs_comext.py
  parse_critical_inputs_comext_raw.py
  compute_critical_inputs_channel_a.py
  compute_critical_inputs_channel_b.py
  aggregate_critical_inputs_cross_channel.py
```

---

## 12. 3-Year Aggregation Implementation

The specification requires a 2022–2024 data window.

- The parser outputs ALL rows for years 2022, 2023, 2024.
- Channel A and Channel B scripts aggregate values ACROSS
  all three years before computing shares.
- V_{i,j} = V_{i,j}^{2022} + V_{i,j}^{2023} + V_{i,j}^{2024}
- Shares are computed on the 3-year cumulative values.
- This is equivalent to treating 2022–2024 as a single
  observation period (identical to how Defense treats
  2019–2024 and Tech treats 2022–2024).
- No moving average is applied.
- No exponential smoothing is applied.
- No year-weighting is applied.

---

END OF DESIGN VALIDATION DOCUMENT
