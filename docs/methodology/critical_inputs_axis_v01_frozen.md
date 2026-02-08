# International Sovereignty Index (ISI)

# Critical Inputs / Raw Materials Dependency Axis — Methodology v0.1 (EU-27, 2022–2024)

Version: 0.1
Status: FROZEN
Freeze date: 2026-02-08
Axis: Critical Inputs / Raw Materials Dependency (Axis 5)
Project: Panargus / International Sovereignty Index (ISI)


## 1. Purpose

The Critical Inputs / Raw Materials Dependency Axis
measures the degree to which a country's imports of
critical raw materials are concentrated among a small
number of foreign supplier countries.

It quantifies structural exposure to potential denial,
disruption, or coercive leverage by dominant suppliers of
materials essential to industrial, defense, energy, and
agricultural systems.

It produces a single scalar score per country.

Higher values indicate greater supplier concentration
(more dependency). Lower values indicate greater
diversification (more autonomy).

The axis does not measure industrial processing capacity,
domestic extraction, strategic reserves, recycling
contributions, material substitutability, geopolitical
alignment, or policy adequacy. It measures import
concentration only.


## 2. Scope

### 2.1 Geographic scope

Countries scored: EU-27 member states as of 2024.

The 27 Eurostat geo codes are:
AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU,
IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK.

Countries outside the EU-27 are excluded from scored
output. They may appear as supplier countries in bilateral
breakdowns but are not themselves scored.

### 2.2 Temporal scope

Reference window: 2022–2024 (three calendar years).

Import values across all three years are aggregated to
produce a single score per country. No year-level
decomposition is applied in the final output. The three-
year window smooths annual trade volatility and reduces
sensitivity to single-year disruptions.

The annual Comext bulk files use period code YYYY52 to
denote the full-year aggregation (sum of all 12 monthly
periods).

### 2.3 Material scope

The material universe consists of 66 unique CN8 codes
(Combined Nomenclature, 8-digit product classification)
organised into 5 material groups:

1. rare_earths (15 CN8 codes)
2. battery_metals (16 CN8 codes)
3. defense_industrial_metals (20 CN8 codes)
4. semiconductor_inputs (8 CN8 codes)
5. fertilizer_chokepoints (7 CN8 codes)

The material universe covers ores, concentrates, refined
metals, and chemical precursors. Finished products,
manufactured goods, and downstream articles are excluded.

Each CN8 code is assigned to exactly one material group.
No CN8 code appears in more than one group. The complete
CN8-to-material-group mapping is defined in a separate,
versioned audit file:
critical_materials_cn8_mapping_v01.csv

That file contains 66 rows, each specifying: cn8_code,
material_group, material_name, stage,
sovereignty_rationale, contamination_risk, and notes.

### 2.4 Trade flow scope

Flow: Imports only (Comext FLOW = 1).

Trade types: Both intra-EU and extra-EU trade are
included. The EU is not treated as a sovereign unit.
Intra-EU dependency counts as dependency. Austria can be
dependent on Germany; Germany can be dependent on China.
Alliance status does not nullify dependency.

Statistical procedure: Normal trade only
(Comext STAT_PROCEDURE = 1). Inward processing (code 2),
outward processing (code 3), and not-recorded (code 9)
are excluded. The rationale is that processing trade
represents temporary imports for transformation and
re-export, not structural dependency on the imported
material for domestic consumption or industrial use.

### 2.5 Indicator

All computations are based on import value in EUR
(Comext VALUE_EUR field). No quantity-based measures
(VALUE_NAC, QUANTITY_KG, QUANTITY_SUPPL_UNIT) are used.

### 2.6 Dependency perspective

The dependency perspective is importer-side throughout.
Country i is the importing country (reporter/declarant).
Countries j are the supplier countries (partners).


## 3. Data Sources

### 3.1 Primary source

One primary data source is used:

Source: Eurostat Comext Bulk Download Facility
Dataset: DS-045409 (EU trade since 1988 by HS2-4-6
  and CN8)
Granularity: CN8-level bilateral trade data
Bulk files consumed:
  full_v2_202252.7z (year 2022)
  full_v2_202352.7z (year 2023)
  full_v2_202452.7z (year 2024)
Access: https://ec.europa.eu/eurostat/api/dissemination/files/
Format: Comma-separated .dat files within .7z archives
  (Comext v2 format, 17 columns)
Authentication: None required
Download method: HTTP GET, no rate limits documented

No other data sources are used.
No third-party composite indices are used.
No qualitative inputs are used.

### 3.2 Data acquisition

DS-045409 is not available via the Eurostat SDMX 2.1
dissemination API, the JSON/CSV statistics API, or the
Easy Comext web application at the required granularity
and volume. The only viable programmatic access path is
the Comext Bulk Download Facility, which provides
pre-built annual files as .7z archives.

Each annual archive contains a single .dat file of
approximately 770 MB (decompressed), covering all
reporters, all partners, all CN8 product codes, and all
trade types for that year.

The extraction pipeline filters each decompressed file
to the 66 CN8 codes in the material universe, FLOW = 1,
STAT_PROCEDURE = 1, and EU-27 reporters, producing the
consolidated raw data file.

### 3.3 Raw data file (frozen)

Filename: eu_comext_critical_inputs_cn8_2022_2024.csv
Rows: 26,538
Columns: DECLARANT_ISO, PARTNER_ISO, PRODUCT_NC, FLOW,
  PERIOD, VALUE_IN_EUROS
Reporters: 27 (all EU-27 members)
Partners: 155 unique supplier countries
CN8 codes: 66 (complete material universe)
Years: 2022, 2023, 2024
Total value: EUR 62,122,749,221
Zero-value rows: 23
Negative values: 0
SHA-256: 93d0f128ca37c4e3173ffb54819f110745a04c9e
         18fcc91b81e313e108c9f8a4

### 3.4 Comext column mapping

The Comext v2 bulk format uses column names that differ
from ISI internal conventions. The following mappings are
applied during extraction:

  REPORTER       → DECLARANT_ISO
  PARTNER        → PARTNER_ISO
  VALUE_EUR      → VALUE_IN_EUROS
  PERIOD 202252  → 2022
  PERIOD 202352  → 2023
  PERIOD 202452  → 2024

Country code GR (Eurostat code for Greece) is remapped to
EL (ISI/Eurostat standard) during extraction.

### 3.5 Partner exclusions

Confidential and non-geographic partner codes with prefix
Q are excluded during extraction, with the exception of
QA (Qatar), which is a legitimate sovereign state using
the ISO 3166-1 alpha-2 code QA. The excluded codes are:
QP, QQ, QR, QS, QU, QV, QW, QX, QY, QZ.

EU aggregate partner codes (EU27_2020, EU28, EU27_2007,
EU25, EU15, EA19, EA20, EFTA) are excluded during
ingest validation.


## 4. Conceptual Framework

### 4.1 What the axis measures

Critical Inputs Dependency in ISI terms IS:

- Concentration of critical raw material imports by
  supplier country
- A structural position measurement
- Computed from observable bilateral trade flow data
- Decomposable into exactly two channels
- Deterministic and reproducible from public inputs

### 4.2 What the axis does not measure

Critical Inputs Dependency in ISI terms is NOT:

- Industrial processing capacity or refining capability
- Domestic mining or extraction output
- Strategic reserve or stockpile adequacy
- Recycling or circular economy contribution
- Substitution feasibility or material science potential
- ESG or environmental governance exposure
- Supply-chain governance or traceability
- Geopolitical alignment or alliance status
- A policy recommendation or regime judgment

### 4.3 Two-channel model

The axis decomposes import concentration into two
orthogonal perspectives:

Channel A measures aggregate supplier-country
concentration across all critical materials treated as a
single pool. It answers: how concentrated is this
country's total critical material import base across
supplier countries?

Channel B measures supplier-country concentration within
each of the five material groups, then aggregates across
groups using import-value weights. It answers: how
concentrated is this country's supplier base within each
strategic material domain?

Both channels use the Herfindahl-Hirschman Index (HHI)
as the concentration metric. The final axis score is the
arithmetic mean of the two channel scores.


## 5. Supplier Shares

For each importing country i and each supplier country j,
total import value is computed by summing across all CN8
codes in the material universe and across all years in
the data window (2022–2024).

Let V_{i,j} be the total import value (EUR) of all
critical materials shipped by supplier country j to
importing country i, summed across all CN8 codes and all
years in the reference window.

The supplier share of country j for importing country i
is:

  s_{i,j} = V_{i,j} / SUM_j V_{i,j}

Shares sum to 1.0 over all supplier countries j with
non-zero trade for a given importing country i.

Self-pairs (reporter = partner after code mapping) are
not explicitly excluded at the share computation stage.
Comext bilateral trade data may include re-imports
(country i importing from itself). These are retained as
recorded. Their empirical magnitude in the filtered
dataset is negligible.

EU aggregate partner codes are excluded during ingest
validation (Section 3.5).


## 6. Supplier Concentration (HHI)

Supplier concentration is measured using the Herfindahl-
Hirschman Index (HHI).

For a given set of supplier shares s_{i,j}, the HHI is:

  HHI_i = SUM_j ( s_{i,j} )^2

HHI_i is in [0, 1].

HHI_i approaches 0 when import value is uniformly spread
across many suppliers.

HHI_i = 1 when all import value originates from a single
supplier.

The HHI formulation is identical across all ISI axes.
No normalisation, rescaling, or threshold adjustment is
applied.

The HHI is computed on value shares (EUR), not on
physical quantity shares. This means that suppliers of
higher-value materials contribute more to concentration
than suppliers of lower-value materials of the same
physical volume.


## 7. Channel Definitions

### 7.1 Channel A — Supplier-Country Concentration

#### Definition

Channel A measures the concentration of critical material
imports into country i, broken down by supplier country,
aggregated across ALL CN8 codes in the material universe
and across ALL years in the data window.

It captures how much of country i's total critical
material import value originates from each foreign
supplier and how concentrated that supplier base is.

No material-group decomposition is applied. All 66 CN8
codes are treated as a single pool.

#### Mathematical formulation

Let V_{i,j}^{(A)} be the total import value (EUR) of all
critical materials shipped by supplier country j to
importing country i, summed across all CN8 codes and all
years in the data window (2022–2024).

Share of supplier country j:

  s_{i,j}^{(A)} = V_{i,j}^{(A)} / SUM_j V_{i,j}^{(A)}

Concentration (HHI):

  C_i^{(A)} = SUM_j ( s_{i,j}^{(A)} )^2

C_i^{(A)} is in [0, 1].

Volume for cross-channel weighting:

  W_i^{(A)} = SUM_j V_{i,j}^{(A)}

This is the total import value of all critical materials
received by country i from all supplier countries across
the data window.

#### Known limitations

1. No material-group weighting is applied. Materials with
   large import values dominate the aggregate HHI
   regardless of strategic significance. A country that
   imports large volumes of nickel from a single supplier
   and small volumes of gallium from many suppliers will
   have its aggregate score pulled toward the nickel
   concentration.

2. Import value (EUR) does not reflect physical quantity,
   unit price variation, or strategic criticality
   differentials between materials.

3. Re-exports and entrepot trade may distort bilateral
   attribution. A country that re-exports materials
   sourced from a third country may appear as the origin
   supplier.


### 7.2 Channel B — Material-Group Concentration

#### Definition

Channel B measures the concentration of critical material
imports into country i, broken down by supplier country
WITHIN each of the five material groups, then aggregated
across groups via import-value weighting.

It captures whether country i relies on the same supplier
across all material domains or has diversified supplier
bases per domain.

#### Material groups

Five groups are defined. Every CN8 code in the material
universe is assigned to exactly one group. The mapping is
defined in the audit file
(critical_materials_cn8_mapping_v01.csv).

1. rare_earths — Rare-earth ores, separated metals,
   compounds, and intermixtures/interalloys. 15 CN8
   codes covering bastnaesite, separated REE metals at
   various purities, scandium, and REE compounds.

2. battery_metals — Lithium ores and compounds, nickel
   ores/mattes/unwrought metal, cobalt ores/mattes/
   oxides, manganese ores and oxides, natural graphite.
   16 CN8 codes.

3. defense_industrial_metals — Tungsten ores/powders/
   unwrought metal/carbides/oxides, titanium ores and
   unwrought metal, molybdenum ores/powders/unwrought
   metal/oxides, niobium/tantalum/vanadium ores and
   metals, rhenium, hafnium, zirconium ores. 20 CN8
   codes.

4. semiconductor_inputs — High-purity and metallurgical-
   grade silicon, germanium metal and oxides, gallium,
   indium, tellurium, helium. 8 CN8 codes.

5. fertilizer_chokepoints — Phosphate rock (ground and
   unground), potassium chloride (all grades), potassium
   sulphate, crude natural potassium salts. 7 CN8 codes.

#### Mathematical formulation

For each importing country i and material group k:

Let V_{i,j}^{(B,k)} be the total import value (EUR) of
materials in group k shipped by supplier country j to
importing country i, summed across all CN8 codes in
group k and all years in the data window (2022–2024).

Share of supplier j in group k:

  s_{i,j}^{(B,k)} = V_{i,j}^{(B,k)} / SUM_j V_{i,j}^{(B,k)}

Group-level concentration (HHI):

  C_i^{(B,k)} = SUM_j ( s_{i,j}^{(B,k)} )^2

Group import-value volume:

  V_i^{(k)} = SUM_j V_{i,j}^{(B,k)}

Aggregate Channel B concentration (import-value-weighted
across groups):

  C_i^{(B)} = SUM_k [ C_i^{(B,k)} * V_i^{(k)} ]
              / SUM_k V_i^{(k)}

C_i^{(B)} is in [0, 1].

Groups with zero import value for a given importing
country are excluded from the weighted average. In the
frozen v0.1 dataset, all 27 EU reporters have non-zero
import value in all 5 material groups.

Volume for cross-channel weighting:

  W_i^{(B)} = SUM_k V_i^{(k)}

This equals total import value received by country i
(same as W_i^{(A)} by construction, since all CN8 codes
are assigned to exactly one group and all contribute to
both channels).

#### Known limitations

1. Group definitions are fixed at 5 groups. The number
   and composition of groups affect the Channel B score.
   Materials within the same group are treated as
   fungible for concentration purposes, which may not
   reflect physical or industrial reality.

2. Some CN8 codes bundle multiple materials into a single
   code. Notable examples:
   - 26159000 bundles niobium, tantalum, and vanadium
     ores into a single heading.
   - 28256000 bundles germanium oxides with zirconium
     dioxide.
   - 28499050 bundles carbides of aluminium, chromium,
     molybdenum, vanadium, tantalum, and titanium.
   - 81123100 includes hafnium waste and scrap alongside
     unwrought hafnium.
   These bundled codes cannot be disaggregated within the
   CN8 nomenclature. Contamination risk for each code is
   documented in the mapping audit file.

3. Import-value weighting means that groups with higher
   total EUR value dominate the Channel B aggregation.
   Groups with small trade volumes but high strategic
   significance (e.g., rare_earths at EUR 470M versus
   battery_metals at EUR 30.1B) contribute
   proportionally less to the final score.

4. Re-exports and entrepot trade may distort bilateral
   attribution within individual groups.


## 8. Critical Inputs Dependency Score (Axis Output)

### 8.1 Cross-channel aggregation formula

For each country i:

  M_i = ( C_i^{(A)} * W_i^{(A)} + C_i^{(B)} * W_i^{(B)} )
        / ( W_i^{(A)} + W_i^{(B)} )

Where:
- C_i^{(A)} is Channel A concentration (HHI)
- C_i^{(B)} is Channel B concentration (HHI)
- W_i^{(A)} is total import value of all critical
  materials for country i (aggregate basis)
- W_i^{(B)} is total import value of all critical
  materials for country i (group-weighted basis)

M_i is in [0, 1].

### 8.2 Equivalence to arithmetic mean

By construction, W_i^{(A)} = W_i^{(B)} for all importing
countries. Both channels account for the same total import
value, since every CN8 code contributes to both channels
and every bilateral trade row is counted once in each.

The cross-channel aggregation therefore reduces to:

  M_i = 0.5 * C_i^{(A)} + 0.5 * C_i^{(B)}

This equivalence is structural, not imposed. The volume-
weighted formula is retained for generality and
consistency with other ISI axes where channels may cover
non-identical row populations.

### 8.3 Edge cases

If W_i^{(A)} = 0 for a given country, Channel A does not
contribute. The score reduces to C_i^{(B)}.

If W_i^{(B)} = 0 for a given country, Channel B does not
contribute. The score reduces to C_i^{(A)}.

If both W_i^{(A)} = 0 and W_i^{(B)} = 0, the country is
omitted from the output with audit status
OMITTED_NO_DATA.

In the frozen v0.1 dataset, no EU-27 country has zero
total import value. All 27 reporters produce valid scores
in both channels.

### 8.4 Output properties

No normalisation is applied.
No rescaling is applied.
No thresholds are applied.
No policy adjustments are applied.
No ranking is imposed.

The output is a set of 27 scalar values, one per EU-27
member state, each in [0, 1].


## 9. Exclusions and Limitations

### 9.1 Substantive exclusions

The following are explicitly excluded from v0.1:

1. Domestic production and extraction. No proxy for
   domestic mining, refining, or processing capacity is
   applied. The axis measures import concentration only.

2. Strategic reserves and stockpiles. No publicly
   available bilateral reserve composition data exists
   at the required granularity for critical materials.

3. Recycling and secondary production. Circular economy
   contributions to material supply are not captured in
   bilateral trade data.

4. Quantity-based measurement. All concentrations are
   value-based (EUR). Physical tonnage, unit price
   variation, and volume-price divergences are not
   reflected.

5. Processed and finished products. The material
   universe is limited to ores, concentrates, refined
   metals, and chemical precursors. Downstream products
   (e.g., permanent magnets, battery cells, fertiliser
   blends) are excluded. Dependency embedded in finished
   goods is not captured.

6. Substitution and criticality weighting. No adjustment
   is made for the degree to which one material can
   substitute for another. All materials in the universe
   are treated as equally critical within their group.

7. Geopolitical risk adjustment. No adjustment is made
   for the political stability, alliance status, or
   reliability of supplier countries. Dependency on
   allies is treated identically to dependency on
   adversaries.

8. Countries outside EU-27. Not scored in v0.1. They may
   appear as supplier countries but are not included in
   the output.

### 9.2 Structural limitations

The following structural properties of the data and
methodology may affect interpretation. They are not
errors; they are documented boundary conditions.

1. Re-export and entrepot masking. Bilateral trade
   records reflect the shipping country (country of
   consignment), not the country of origin. No origin-
   adjusted trade data is available at CN8 level.
   Countries that serve as entrepot traders — notably
   the Netherlands (NL), Belgium (BE), and Luxembourg
   (LU) — may appear as suppliers when they are
   intermediaries re-exporting materials originally
   sourced from third countries. This inflates the
   apparent intra-EU share of supply and may understate
   true extra-EU dependency for countries that source
   through these hubs. In the v0.1 dataset, 13 of 27
   reporters source more than 50% of their critical
   material imports from EU partner countries by value.
   For AT, this figure is 90.7%. A significant fraction
   of this intra-EU flow is likely re-exported material.

2. Small-economy amplification. Countries with minimal
   total import volumes (e.g., CY at EUR 12.9M, MT at
   EUR 3.6M, LU at EUR 9.1M) produce mechanically high
   HHI values because their import base consists of few
   bilateral trade flows. A single large shipment from
   one supplier can dominate the entire import profile.
   These scores are arithmetically correct but are not
   comparable in strategic significance to high HHI
   values produced by large economies with substantial
   trade volumes. No volume normaliser is applied in
   v0.1.

3. Confidential trade suppression. Eurostat suppresses
   trade values for certain bilateral flows to protect
   commercial confidentiality. Confidential partner
   codes (Q-prefix except QA) are excluded during
   extraction. Trade flows suppressed at the value level
   (reported as zero, colon, or "c") are treated as
   zero. This may cause underestimation of trade with
   certain partners, particularly for materials with
   few traders and high commercial sensitivity.

4. CN8 scope captures upstream materials only. The 66
   CN8 codes cover ores, concentrates, refined metals,
   and chemical precursors. They do not capture midstream
   processing (e.g., Chinese dominance in REE separation
   and refining, Indonesian nickel smelting) or
   downstream manufactured products (e.g., NdFeB magnets,
   battery cathode materials). A country may appear to
   have low import concentration for rare earths at the
   ore/compound level while being highly dependent on a
   single supplier for processed REE products that fall
   outside the CN8 scope. In the v0.1 dataset, China
   appears as a top-5% supplier for only 2 of 27
   reporters (SE at 8.3%, PL at 6.3%), which understates
   China's actual role in the global critical materials
   supply chain. This is a known scope limitation, not a
   data error.

5. STAT_PROCEDURE = 1 exclusion. Only "normal" trade
   (statistical procedure code 1) is included. Inward
   processing (code 2) and outward processing (code 3)
   are excluded. This removes trade flows where materials
   are imported temporarily for transformation and re-
   export. The rationale is that processing trade does
   not represent structural dependency on the imported
   material for domestic consumption. However, some
   inward processing trade may represent genuine
   industrial dependency (e.g., a refiner that imports
   ore under inward processing relief but sells the
   refined product domestically). The magnitude of this
   exclusion is not quantified in v0.1.


## 10. Reproducibility

All inputs are publicly retrievable from the Eurostat
Comext Bulk Download Facility.

All formulas are explicitly stated in this document.
No hidden parameters, thresholds, or judgment calls
are applied.

The CN8-to-material-group mapping is defined in a
separate, versioned audit file
(critical_materials_cn8_mapping_v01.csv) containing
66 rows. Each row specifies: cn8_code, material_group,
material_name, stage, sovereignty_rationale,
contamination_risk, and notes.

The extraction pipeline is defined in:
  scripts/extract_critical_inputs_comext.py

The ingest validation gate is defined in:
  scripts/ingest_critical_inputs_comext_manual.py

All intermediate outputs (flat bilateral import values,
supplier shares, group-level concentrations, channel-
level concentrations, volumes) are preserved as CSV files
in the data pipeline.

Country code mappings (Eurostat conventions, including
the GR to EL remapping and Q-prefix partner exclusions)
are explicitly defined in the extraction script.

The raw data file is checksummed (SHA-256) and archived
in the project data directory.

To reproduce the v0.1 results from scratch:

1. Download three annual Comext v2 bulk files from the
   Eurostat Bulk Download Facility:
   full_v2_202252.7z, full_v2_202352.7z,
   full_v2_202452.7z

2. Run the extraction script to decompress, filter, and
   consolidate the raw data.

3. Run the ingest validation gate to confirm data
   integrity.

4. Compute Channel A (aggregate supplier HHI), Channel B
   (material-group-weighted supplier HHI), and the cross-
   channel arithmetic mean.

No external API credentials, proprietary datasets, or
manual adjustments are required at any step.


## 11. Versioning

This specification is version 0.1.

The version identifier "v0.1" appears in all script
docstrings, output filenames, mapping files, and
methodology documents associated with this axis.

Version 0.1 is the first scored release of the Critical
Inputs / Raw Materials Dependency Axis. It establishes
the baseline material universe, channel structure, and
concentration metric. Subsequent versions may expand the
geographic scope, extend the temporal window, refine
material group composition, or introduce additional
channels. Any such modification requires a new version
number and a new freeze declaration.


## 12. Freeze Declaration

The following components of ISI Axis 5 (Critical Inputs /
Raw Materials Dependency) are frozen as of 2026-02-08 at
version 0.1:

- Geographic scope: EU-27 (27 countries scored)
- Reference window: 2022–2024
- Data source: Eurostat Comext Bulk Download Facility,
  DS-045409, CN8 level
- Material universe: 66 CN8 codes in 5 groups
- Mapping file: critical_materials_cn8_mapping_v01.csv
- Raw data file: eu_comext_critical_inputs_cn8_2022_2024.csv
  (26,538 rows, SHA-256 93d0f128...)
- Channel A: Aggregate supplier-country HHI
- Channel B: Material-group-weighted supplier-country HHI
- Cross-channel aggregation: 0.5 * A + 0.5 * B
- Concentration metric: HHI, unnormalised, unrescaled
- Score range: [0, 1]
- Scored countries: 27/27 (no omissions)
- Extraction script: extract_critical_inputs_comext.py
- Ingest gate script: ingest_critical_inputs_comext_manual.py

No modifications to any of the above components are
permitted without incrementing the version number.

This document is the authoritative methodological
reference for all Axis 5 computations, outputs, and
audits at version 0.1.


End of document.
