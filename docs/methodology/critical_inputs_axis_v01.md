# International Sovereignty Index (ISI)

# Critical Inputs / Raw Materials Dependency Axis — Methodology v0.1 (EU-27, 2024)

Version: 0.1
Status: FROZEN
Date: 2026-02-07
Axis: Critical Inputs / Raw Materials Dependency
Project: Panargus / International Sovereignty Index (ISI)


## 1. Purpose

The Critical Inputs / Raw Materials Dependency Axis measures
the degree to which a country's imports of critical raw
materials are concentrated among a small number of foreign
supplier countries.

It quantifies structural exposure to potential denial,
disruption, or coercive leverage by dominant suppliers of
materials essential to industrial, defense, energy, and
agricultural systems.

It produces a single scalar score per country per year.

Higher values indicate greater supplier concentration
(more dependency). Lower values indicate greater
diversification (more autonomy).


## 2. Scope

### 2.1 Geographic scope

Countries: EU-27 member states as of 2024.

The 27 Eurostat geo codes are:
AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU,
IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK.

Reference year: 2024.

Data window: 2022–2024. Import values across all three
years are aggregated to produce a single 2024-labelled
score per country.

Countries outside the EU-27 are excluded from v0.1
Critical Inputs axis output. They may appear as supplier
countries in the bilateral breakdowns but are not scored.


## 3. Data Sources

### 3.1 Primary source

One primary data source is used:

Source: Eurostat Comext
- Dataset: ds-045409 (EU trade since 1988 by HS2-4-6
  and CN8)
- Granularity: CN8-level (Combined Nomenclature,
  8-digit product codes)
- Flow: Imports only (flow code 1)
- Indicator: VALUE_IN_EUROS
- Format: Bilateral partner CSV, manual download
- Access: https://ec.europa.eu/eurostat/comext/

No other data sources are used.
No third-party composite indices are used.
No qualitative inputs are used.
No quantity-based measures are used. All computations
are based on import value in EUR.


## 4. Conceptual Framework

Critical Inputs Dependency in ISI terms IS:
- Concentration of critical raw material imports by
  supplier country
- A structural position measurement
- Computed from observable bilateral trade flow data
- Decomposable into exactly two channels

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

The material universe consists of 66 unique CN8 codes
organised into 5 material groups:

1. rare_earths
2. battery_metals
3. defense_industrial_metals
4. semiconductor_inputs
5. fertilizer_chokepoints

The complete CN8-to-material-group mapping is defined
in a separate audit file (critical_materials_cn8_mapping_v01.csv).
Each CN8 code is assigned to exactly one material group.
No CN8 code appears in more than one group.

The material universe covers ores, concentrates, refined
metals, and chemical precursors. Finished products,
manufactured goods, and downstream articles are excluded.

Intra-EU dependency counts as dependency. The EU is not
treated as a sovereign unit. Austria can be dependent on
Germany; Germany can be dependent on China. Alliance
status does not nullify dependency.


## 5. Supplier Shares

For each importing country i and each supplier country j,
total import value is computed by summing across all CN8
codes in the material universe and across all years in
the data window (2022–2024).

Let V_{i,j} be the total import value (EUR) of all
critical materials shipped by supplier country j to
importing country i.

The supplier share of country j for importing country i
is:

  s_{i,j} = V_{i,j} / SUM_j V_{i,j}

Shares sum to 1.0 over all supplier countries j with
non-zero trade for a given importing country i.

Self-pairs (reporter = partner after code mapping) are
excluded. The EU-27 aggregate partner code (EU27_2020)
is excluded.

Country code mapping: Eurostat geo code GR is mapped to
EL (Greece). All supplier and reporter country codes
follow Eurostat conventions.


## 6. Supplier Concentration

Supplier concentration is measured using the Herfindahl-
Hirschman Index (HHI).

For a given set of supplier shares s_{i,j}, the HHI is:

  HHI_i = SUM_j ( s_{i,j} )^2

HHI_i is in [0, 1].

HHI_i = 0 when import value is uniformly spread across
infinitely many suppliers.

HHI_i = 1 when all import value originates from a single
supplier.

The HHI formulation is identical across all ISI axes.
No normalisation, rescaling, or threshold adjustment is
applied.


## 7. Channel Definitions

### 7.1 Channel A — Aggregate Supplier Concentration

#### Definition

Channel A measures the concentration of critical material
imports into country i, broken down by supplier country,
aggregated across ALL CN8 codes in the material universe
and across ALL years in the data window.

It captures how much of country i's total critical
material import value originates from each foreign
supplier and how concentrated that supplier base is.

The dependency perspective is importer-side: country i is
the buyer; countries j are the suppliers.

No material-group decomposition is applied. All 66 CN8
codes are treated as a single pool.

#### Mathematical Formulation

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

#### Data Source and Coverage

Dataset: Eurostat Comext ds-045409, CN8 level.
All 27 EU member states may appear as importing countries.
Supplier countries include all Eurostat-reported partner
origins.

#### Known Limitations

1. No material-group weighting is applied. Materials with
   large import values dominate the aggregate HHI
   regardless of strategic significance. A country that
   imports large volumes of graphite from a single
   supplier and small volumes of gallium from many
   suppliers will have its aggregate score pulled toward
   the graphite concentration.

2. Import value (EUR) does not reflect physical quantity,
   unit price variation, or strategic criticality
   differentials between materials.

3. Re-exports and entrepôt trade may distort bilateral
   attribution. A country that re-exports materials
   sourced from a third country may appear as the origin.


### 7.2 Channel B — Material-Group Concentration

#### Definition

Channel B measures the concentration of critical material
imports into country i, broken down by supplier country
WITHIN each of the five material groups, then aggregated
across groups via import-value weighting.

It captures whether country i relies on the same supplier
across all material domains or has diversified supplier
bases per domain.

#### Material Groups

Five groups are defined. Every CN8 code in the material
universe is assigned to exactly one group. The mapping is
defined in the audit file
(critical_materials_cn8_mapping_v01.csv).

1. rare_earths — Rare-earth ores, separated metals,
   compounds, and intermixtures/interalloys.

2. battery_metals — Lithium ores and compounds, nickel
   ores/mattes/unwrought metal, cobalt ores/mattes/
   oxides, manganese ores and oxides, natural graphite.

3. defense_industrial_metals — Tungsten ores/powders/
   unwrought metal/carbides/oxides, titanium ores and
   unwrought metal, molybdenum ores/powders/unwrought
   metal/oxides, niobium/tantalum/vanadium ores and
   metals, rhenium, hafnium, zirconium ores.

4. semiconductor_inputs — High-purity and metallurgical
   silicon, germanium metal and oxides, gallium, indium,
   tellurium, helium.

5. fertilizer_chokepoints — Phosphate rock (ground and
   unground), potassium chloride (all grades), potassium
   sulphate, crude natural potassium salts.

#### Mathematical Formulation

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
country are excluded from the weighted average.

Volume for cross-channel weighting:

  W_i^{(B)} = SUM_k V_i^{(k)}

This equals total import value received by country i
(same as W_i^{(A)} by construction, since all CN8 codes
are assigned to exactly one group and all contribute to
both channels).

#### Data Source and Coverage

Same as Channel A: Eurostat Comext ds-045409, CN8 level.

#### Known Limitations

1. Group definitions are fixed at 5 groups. The number
   and composition of groups affect the Channel B score.
   Materials within the same group are treated as
   substitutable for concentration purposes, which may
   not reflect physical reality.

2. Some CN8 codes bundle multiple materials into a single
   code (e.g., 26159000 bundles niobium, tantalum, and
   vanadium ores; 28256000 bundles germanium oxides and
   zirconium dioxide). These bundled codes cannot be
   disaggregated further within the CN8 nomenclature.
   Contamination risk for each code is documented in the
   mapping audit file.

3. Import-value weighting means that groups with higher
   total EUR value dominate the Channel B aggregation.
   Groups with small trade volumes but high strategic
   significance (e.g., semiconductor_inputs) contribute
   proportionally less to the final score.

4. Re-exports and entrepôt trade may distort bilateral
   attribution within individual groups.


## 8. Critical Inputs Dependency Score (Axis Output)

### Exact Formula

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

### Weighting Logic

Aggregation is volume-weighted. The channel with the
larger absolute import value contributes proportionally
more to the final score.

By construction, W_i^{(A)} = W_i^{(B)} for all importing
countries (both channels account for the same total
import value, since every CN8 code contributes to both
channels). The cross-channel aggregation therefore
reduces to a simple arithmetic average:

  M_i = ( C_i^{(A)} + C_i^{(B)} ) / 2

This equivalence holds because every bilateral trade row
contributes to both channels. No import value is excluded
from either channel. The volume-weighted formula is
retained for generality and consistency with other axes.

If W_i^{(A)} = 0 for a given country, Channel A does not
contribute. The score reduces to C_i^{(B)}.

If W_i^{(B)} = 0 for a given country, Channel B does not
contribute. The score reduces to C_i^{(A)}.

If both W_i^{(A)} = 0 and W_i^{(B)} = 0, the country is
omitted from the output with audit status OMITTED_NO_DATA.

No equal weighting is imposed externally.
No normalisation is applied.
No rescaling is applied.

### Scope Enforcement

After aggregation, the output is filtered to EU-27
member states only. Countries outside EU-27 are excluded.
A scope audit file records the inclusion/exclusion
status of every country present in the unfiltered output.


## 9. Exclusions and Limitations

The following are explicitly excluded from v0.1:

1. Domestic production and extraction. No proxy for
   domestic mining, refining, or processing capacity is
   applied. The axis measures import concentration only.

2. Strategic reserves and stockpiles. No publicly
   available bilateral reserve composition data exists
   at the required granularity for critical materials.
   No proxy is applied.

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

6. Re-export correction. Bilateral trade records reflect
   shipping country, not country of origin. No origin-
   adjusted trade data is available at CN8 level. This
   may cause countries that serve as entrepôt traders
   (e.g., the Netherlands, Belgium) to appear as
   suppliers when they are intermediaries.

7. Substitution and criticality weighting. No adjustment
   is made for the degree to which one material can
   substitute for another. All materials in the universe
   are treated as equally critical within their group.

8. Geopolitical risk adjustment. No adjustment is made
   for the political stability, alliance status, or
   reliability of supplier countries. Dependency on
   allies is treated identically to dependency on
   adversaries.

9. Countries outside EU-27. Not scored in v0.1 Critical
   Inputs axis. They may appear as supplier countries
   but are not included in the output.


## 10. Reproducibility

All inputs are publicly retrievable from Eurostat Comext.

All formulas are explicitly stated in this document.
No hidden parameters, thresholds, or judgment calls
are applied.

The CN8-to-material-group mapping is defined in a
separate, versioned audit file
(critical_materials_cn8_mapping_v01.csv) containing
66 rows. Each row specifies: cn8_code, material_group,
material_name, stage, sovereignty_rationale,
contamination_risk, and notes.

All intermediate outputs (flat bilateral import values,
supplier shares, group-level concentrations, channel-level
concentrations, volumes) are preserved as CSV files in
the data pipeline.

Coverage gaps and omitted countries are documented in
per-country audit files accompanying each computation
step.

Country code mappings (Eurostat conventions, including
GR → EL) are explicitly defined in the parser.


## 11. Versioning

This specification is version 0.1. It is frozen as of
2026-02-07. Any modification requires a new version
number.

The version identifier "v0.1" appears in all script
docstrings, output filenames, and methodology documents
associated with this axis.
