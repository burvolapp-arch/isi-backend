# Technology / Semiconductor Dependency Axis — v0.1
# Pre-Implementation Design Validation

Status: PENDING CONFIRMATION
Date: 2026-02-07
Axis: Technology / Semiconductor Dependency (Axis 4)
Project: Panargus / International Sovereignty Index (ISI)

---

## 1. Design Lock Verification

All parameters below are LOCKED per the axis specification.
No modifications are proposed. This section confirms
alignment between the specification and the planned
implementation.

| Parameter               | Locked Value                              |
|-------------------------|-------------------------------------------|
| Axis name               | Technology / Semiconductor Dependency     |
| Version                 | 0.1                                       |
| Reference year          | 2024                                      |
| Measurement window      | 2022–2024 (3-year smoothing)              |
| Geographic scope        | EU-27                                     |
| Score range             | [0, 1]                                    |
| Concentration metric    | Herfindahl-Hirschman Index (HHI)          |
| Aggregation method      | Volume-weighted average across channels   |
| Normalization           | None                                      |
| Rescaling               | None                                      |
| Channels                | 2 (A: Total semiconductor, B: Category)   |
| HS codes                | 8541 (legacy), 8542 (advanced/IC)         |
| Data source             | Eurostat Comext (preferred) or UN Comtrade |
| Data format             | Bulk CSV (manual download)                |

---

## 2. Data Source Decision — STOP POINT #1

### The Ambiguity

The specification states:
> "UN Comtrade bulk CSV OR Eurostat Comext (preferred if cleaner)"

Both sources report bilateral trade flows at HS 4-digit level.
They differ in:

| Dimension           | Eurostat Comext                    | UN Comtrade                         |
|---------------------|------------------------------------|-------------------------------------|
| Reporter scope      | EU-27 members only (as reporters)  | ~200 countries                      |
| Partner scope       | World (including extra-EU)         | World                               |
| HS nomenclature     | Combined Nomenclature (CN) ⊃ HS   | HS direct                           |
| Trade value unit    | EUR (Comext default)               | USD (Comtrade default)              |
| Country codes       | Eurostat geo codes (EL for Greece) | ISO-3 (GRC for Greece)              |
| Bulk access         | Eurostat bulk download, no auth    | Comtrade API requires token for bulk|
| Intra-EU trade      | Reported (Intrastat + Extrastat)   | May be patchy for intra-EU          |
| Timeliness for 2024 | Typically available by mid-2025    | May lag                             |
| Encoding            | UTF-8 (standard Eurostat)          | UTF-8                               |

### Recommendation: Eurostat Comext

Rationale:
1. Consistency with Axis 1 (Energy), which already uses
   Eurostat as its data source.
2. Eurostat geo codes (EL for Greece) are the project
   standard — no mapping layer needed.
3. No API authentication required for bulk download.
4. Intra-EU semiconductor trade is captured (Intrastat),
   which is relevant since EU members import from other
   EU members (e.g., NL→DE for ASML-adjacent flows).
5. The specification states Comext is "preferred if
   cleaner."

### ⛔ STOP POINT #1 — Confirmation Required

**Decision needed**: Confirm Eurostat Comext as the sole
data source for the Technology / Semiconductor Dependency
Axis v0.1.

If Comext is confirmed:
- Raw file expected: `data/raw/eurostat/comext_semiconductor_2022_2024.csv`
- Manual download from Eurostat Easy Comext or bulk facility
- Filter: HS 8541 + HS 8542, reporters = EU-27,
  partners = world, years = 2022–2024, flow = imports

If UN Comtrade is preferred instead:
- Raw file expected: `data/raw/comtrade/comtrade_semiconductor_2022_2024.csv`
- Additional ISO-3 → Eurostat geo mapping layer required
- USD → EUR conversion NOT applied (axis is unit-agnostic
  for concentration; HHI depends on shares, not levels)

---

## 3. Exact Data Fields Required from Raw CSV

### Eurostat Comext Bulk CSV (expected schema)

| Field name (Comext) | Required | Use in pipeline                       |
|---------------------|----------|---------------------------------------|
| DECLARANT_ISO       | YES      | Reporter / importer (EU-27 geo code)  |
| PARTNER_ISO         | YES      | Supplier country (partner geo code)   |
| PRODUCT_NC          | YES      | CN/HS code — filter 8541, 8542        |
| FLOW                | YES      | Must equal 1 (imports) or "IMP"       |
| PERIOD              | YES      | Year — filter 2022, 2023, 2024        |
| VALUE_IN_EUROS      | YES      | Trade value (EUR) — used for shares   |
| QUANTITY_IN_KG      | NO       | Not used in v0.1                      |
| SUP_QUANTITY        | NO       | Not used in v0.1                      |

Notes:
- PRODUCT_NC at 4-digit level captures both HS 8541 and
  HS 8542. If Comext reports at 8-digit CN level, the
  parser must truncate to 4 digits for aggregation.
- FLOW must be filtered to imports only. Exports and
  re-exports are excluded.
- VALUE_IN_EUROS is the concentration basis. All shares
  are computed from import values, not quantities.
- Quantity fields are ignored. No unit conversion is
  needed since HHI depends on shares, which are
  dimensionless.

### ⛔ STOP POINT #2 — Confirmation Required

**Decision needed**: After data source selection, the raw
CSV must be inspected for actual column names, encoding,
and header structure before the parser is written. The
ingest script will validate structure and report findings.

---

## 4. Pipeline Architecture — Script List

Following the established project pattern (cf. Defense,
Finance axes), the pipeline consists of 5 scripts executed
sequentially.

### Script 1: ingest_tech_comext_manual.py

Task: ISI-TECH-INGEST
Purpose: Validate presence and structure of the manually
downloaded Comext CSV.
Input: data/raw/eurostat/comext_semiconductor_2022_2024.csv
Output: None (validation gate only)
Actions:
- Check file exists
- Read header row
- Verify required field patterns present
- Count data rows
- Report and PASS/FAIL

### Script 2: parse_tech_comext_raw.py

Task: ISI-TECH-PARSE
Purpose: Parse raw Comext CSV into flat bilateral import
table.
Input: data/raw/eurostat/comext_semiconductor_2022_2024.csv
Outputs:
- data/processed/tech/comext_semiconductor_2022_2024_flat.csv
  Schema: reporter,partner,hs4,year,value
- data/processed/tech/comext_semiconductor_2022_2024_audit.csv
  Schema: reporter,n_partners,total_value,n_hs_codes
- data/audit/tech_parser_waterfall_2024.csv
  Schema: stage,count

Actions:
- Read CSV (encoding TBD after inspection — likely UTF-8)
- Filter FLOW = imports only
- Filter PERIOD ∈ {2022, 2023, 2024}
- Filter PRODUCT_NC starts with "8541" or "8542"
  (truncate to 4 digits if 8-digit CN)
- Map HS code to category label:
  - 8541 → "legacy"
  - 8542 → "advanced"
- Filter DECLARANT_ISO ∈ EU-27
- Exclude self-pairs (reporter = partner)
- Exclude rows with zero or missing value
- Write flat output
- Write audit summary per reporter
- Write parser waterfall

### Script 3: compute_tech_channel_a.py

Task: ISI-TECH-CHANNEL-A
Purpose: Compute aggregate supplier concentration (all
semiconductors combined).
Input: data/processed/tech/comext_semiconductor_2022_2024_flat.csv
Outputs:
- data/processed/tech/tech_channel_a_shares.csv
  Schema: reporter,partner,share
- data/processed/tech/tech_channel_a_concentration.csv
  Schema: reporter,concentration
- data/processed/tech/tech_channel_a_volumes.csv
  Schema: reporter,total_value

Methodology:
- For each reporter i, aggregate ALL import value across
  both HS codes and all 3 years (2022–2024).
- s_{i,j}^{(A)} = V_{i,j} / SUM_j V_{i,j}
- C_i^{(A)} = SUM_j ( s_{i,j}^{(A)} )^2
- W_i^{(A)} = SUM_j V_{i,j}

Constraints:
- Shares sum to 1.0 per reporter (tolerance 1e-9)
- Hard-fail if share < 0 or > 1
- Hard-fail if HHI not in [0, 1]
- EU-27 only

### Script 4: compute_tech_channel_b.py

Task: ISI-TECH-CHANNEL-B
Purpose: Compute category-weighted supplier concentration
(separate HHI per HS category, then value-weighted
aggregate).
Input: data/processed/tech/comext_semiconductor_2022_2024_flat.csv
Outputs:
- data/processed/tech/tech_channel_b_category_shares.csv
  Schema: reporter,hs_category,partner,share
- data/processed/tech/tech_channel_b_category_concentration.csv
  Schema: reporter,hs_category,concentration,category_value
- data/processed/tech/tech_channel_b_concentration.csv
  Schema: reporter,concentration
- data/processed/tech/tech_channel_b_volumes.csv
  Schema: reporter,total_value

Methodology:
- For each reporter i and category k ∈ {advanced, legacy}:
  - s_{i,j}^{(B,k)} = V_{i,j}^{k} / SUM_j V_{i,j}^{k}
  - C_i^{(B,k)} = SUM_j ( s_{i,j}^{(B,k)} )^2
  - V_i^{(k)} = SUM_j V_{i,j}^{k}
- Aggregate:
  - C_i^{(B)} = SUM_k [ C_i^{(B,k)} * V_i^{(k)} ]
                / SUM_k V_i^{(k)}
  - W_i^{(B)} = SUM_k V_i^{(k)}
- Categories with zero value for a reporter are excluded
  from the weighted average.

Constraints:
- Shares sum to 1.0 per (reporter, category) — tolerance 1e-9
- Hard-fail if share < 0 or > 1
- Hard-fail if category HHI not in [0, 1]
- Hard-fail if weighted HHI not in [0, 1]
- EU-27 only

### Script 5: aggregate_tech_cross_channel.py

Task: ISI-TECH-AGGREGATE
Purpose: Volume-weighted cross-channel aggregation.
Inputs:
- data/processed/tech/tech_channel_a_concentration.csv
- data/processed/tech/tech_channel_a_volumes.csv
- data/processed/tech/tech_channel_b_concentration.csv
- data/processed/tech/tech_channel_b_volumes.csv
Outputs:
- data/processed/tech/tech_dependency_2024_eu27.csv
  Schema: geo,tech_dependency
- data/processed/tech/tech_dependency_2024_eu27_audit.csv
  Schema: geo,channel_a_concentration,channel_a_volume,
          channel_b_concentration,channel_b_volume,
          tech_dependency,score_basis

Methodology:
  T_i = ( C_i^{(A)} * W_i^{(A)} + C_i^{(B)} * W_i^{(B)} )
        / ( W_i^{(A)} + W_i^{(B)} )

  If one channel has zero volume → reduce to other channel.
  If both zero → OMITTED_NO_DATA.

Constraints:
- Score in [0, 1]
- EU-27 only (Eurostat geo codes, EL for Greece)
- Hard-fail if score out of bounds

Note: By construction, W_i^{(A)} = W_i^{(B)} for all
reporters (both channels consume the same total import
value). The formula therefore reduces to a simple
arithmetic average: T_i = ( C_i^{(A)} + C_i^{(B)} ) / 2.
The volume-weighted formula is retained for generality
and consistency with other axes.

---

## 5. Audit Artifacts List

### Per-pipeline-step artifacts

| Script                        | Audit artifact                                      | Content                                   |
|-------------------------------|-----------------------------------------------------|-------------------------------------------|
| ingest_tech_comext_manual.py  | (console output only)                               | File presence, column check, row count    |
| parse_tech_comext_raw.py      | data/audit/tech_parser_waterfall_2024.csv            | Row counts at each filter stage           |
| parse_tech_comext_raw.py      | data/processed/tech/comext_semiconductor_2022_2024_audit.csv | Per-reporter summary               |
| compute_tech_channel_a.py     | (inline validation — hard-fail on constraint breach) | Shares sum, HHI bounds                   |
| compute_tech_channel_b.py     | (inline validation — hard-fail on constraint breach) | Shares sum, category HHI, weighted HHI   |
| aggregate_tech_cross_channel.py | data/processed/tech/tech_dependency_2024_eu27_audit.csv | Per-country channel breakdown, score basis |

### Final output

| File                                                    | Schema                  |
|---------------------------------------------------------|-------------------------|
| data/processed/tech/tech_dependency_2024_eu27.csv       | geo,tech_dependency     |

---

## 6. Directory Structure (New)

```
data/
  raw/
    eurostat/
      comext_semiconductor_2022_2024.csv    ← manual download
  processed/
    tech/
      comext_semiconductor_2022_2024_flat.csv
      comext_semiconductor_2022_2024_audit.csv
      tech_channel_a_shares.csv
      tech_channel_a_concentration.csv
      tech_channel_a_volumes.csv
      tech_channel_b_category_shares.csv
      tech_channel_b_category_concentration.csv
      tech_channel_b_concentration.csv
      tech_channel_b_volumes.csv
      tech_dependency_2024_eu27.csv
      tech_dependency_2024_eu27_audit.csv
  audit/
    tech_parser_waterfall_2024.csv
  scopes/
    energy_eurostat_scope_eu27.csv          ← existing, reused
```

---

## 7. Structural Alignment with Frozen Axes

| Dimension                        | Defense (Axis 3)         | Tech (Axis 4)            |
|----------------------------------|--------------------------|--------------------------|
| Channels                         | 2 (A + B)               | 2 (A + B)                |
| Channel A                        | Supplier HHI (all TIV)  | Supplier HHI (all value) |
| Channel B                        | Block-weighted HHI (6)  | Category-weighted HHI (2)|
| Block/category classification    | Regex on description     | HS 4-digit code (8541/8542) |
| Cross-channel formula            | Volume-weighted avg      | Volume-weighted avg      |
| Scope enforcement                | EU-27 Eurostat codes     | EU-27 Eurostat codes     |
| Missing-data handling            | OMITTED_NO_DATA          | OMITTED_NO_DATA          |
| Inline constraint checks         | Hard-fail                | Hard-fail                |
| Audit trail                      | Waterfall + per-country  | Waterfall + per-country  |
| Methodology document             | defense_axis_v01.md      | tech_axis_v01.md         |

Key difference: Defense Channel B classifies items into
6 capability blocks via regex on free-text descriptions.
Tech Channel B classifies items into 2 categories via
deterministic HS code mapping (8541 → legacy, 8542 →
advanced). This is simpler and introduces zero
classification ambiguity.

---

## 8. 3-Year Smoothing Implementation

The specification requires a 2022–2024 measurement window.
Implementation approach:

- The parser outputs ALL rows for years 2022, 2023, 2024.
- Channel A and Channel B scripts aggregate values ACROSS
  all three years before computing shares.
- This means V_{i,j} = V_{i,j}^{2022} + V_{i,j}^{2023}
  + V_{i,j}^{2024}.
- Shares are computed on the 3-year cumulative values.
- This is equivalent to treating 2022–2024 as a single
  observation period (identical to how Defense treats
  2019–2024 as a single delivery window).
- No moving average or exponential smoothing is applied.
- No year-weighting is applied.

---

## 9. Known Ambiguities and Risks

### 9a. Comext column names

Eurostat Comext bulk CSVs have varied header conventions
across download methods (Easy Comext web, bulk facility,
SDMX). Exact column names will be determined at STOP
POINT #2 after the raw file is obtained and inspected.

### 9b. CN 8-digit vs HS 4-digit

Comext may report at CN 8-digit level (e.g., 85423110).
The parser must truncate to 4 digits and aggregate.
This is unambiguous: first 4 digits of any CN 8541xxxx
code map to HS 8541; first 4 digits of 8542xxxx map to
HS 8542.

### 9c. Partner codes

Eurostat uses special partner codes for aggregates
(e.g., "EU27_2020" for intra-EU, "WORLD" for total).
These must be excluded from bilateral partner-level
computations. Only individual country codes are retained
as partners.

### 9d. Re-exports and entrepôt effects

The Netherlands and Belgium may show elevated import
values due to port-of-entry effects (Rotterdam,
Antwerp). No correction is applied. This is documented
as a known limitation in the methodology document.

### 9e. Intra-EU vs extra-EU

Both intra-EU (Intrastat) and extra-EU (Extrastat) imports
are included. An EU member importing semiconductors from
another EU member (e.g., DE importing from NL) is treated
as a bilateral supplier relationship. This is consistent
with the importer-dependency perspective: the question is
who supplies country i, regardless of whether the supplier
is inside or outside the EU.

---

## 10. Stop Points Summary

| #  | Gate                                  | Blocks                              |
|----|---------------------------------------|--------------------------------------|
| 1  | Data source confirmation              | Comext vs Comtrade                   |
| 2  | Raw CSV structure inspection          | Column names, encoding, header rows  |
| 3  | Parser output validation              | Row counts, EU-27 coverage, HS codes |
| 4  | Channel A + B validation              | Shares, HHI bounds, volumes          |
| 5  | Final score review                    | 27-country table, outlier inspection |

No script proceeds past a STOP POINT without explicit
confirmation.

---

## 11. Methodology Document

After pipeline freeze, a methodology document will be
produced:

  docs/methodology/tech_axis_v01.md

It will follow the exact same 10-section structure as:
- finance_axis_v01.md
- energy_axis_v01.md
- defense_axis_v01.md

It will be written AFTER implementation, documenting
only what was actually built. No speculative content.

---

END OF DESIGN VALIDATION DOCUMENT
