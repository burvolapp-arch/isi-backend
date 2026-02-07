# Energy Dependency Axis — ISI v0.1

Version: 0.1
Status: FROZEN
Date: 2026-02-07
Axis: Energy Dependency
Project: Panargus / International Sovereignty Index (ISI)


## 1. Title and Version Block

Axis name: Energy Dependency
Version: 0.1
Reference year: 2024
Geographic scope: EU-27
Fuels: 3 (Natural gas, Crude oil & petroleum products, Solid fossil fuels)
Concentration metric: Herfindahl-Hirschman Index (HHI)
Aggregation method: Volume-weighted average across fuels
Score range: [0, 1]


## 2. Purpose of the Energy Dependency Axis

The Energy Dependency Axis measures the degree to which
a country's fossil fuel imports are concentrated among
a small number of foreign supplier countries.

It quantifies structural exposure to potential denial,
disruption, or coercive leverage by dominant energy
suppliers.

It produces a single scalar score per country per year.

Higher values indicate greater supplier concentration
(more dependency). Lower values indicate greater
diversification (more autonomy).


## 3. Conceptual Definition

Energy Dependency in ISI terms IS:
- Concentration of fossil fuel imports by supplier country
- A structural position measurement
- Computed from observable bilateral trade flow data
- Decomposable by fuel type (natural gas, crude oil &
  petroleum products, solid fossil fuels)

Energy Dependency in ISI terms is NOT:
- Energy intensity or efficiency
- Renewable energy penetration or energy mix composition
- Strategic reserve adequacy
- Energy price exposure or volatility
- Pipeline vs LNG infrastructure differentiation
- Contract duration or lock-in
- Electricity import dependency
- A policy recommendation or regime judgment


## 4. Geographic and Temporal Scope

Countries: EU-27 member states as of 2024.

The 27 Eurostat geo codes are:
AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU,
IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK.

Reference year: 2024.

For Eurostat data: Annual import volumes for 2024.

Countries outside the EU-27 are excluded from v0.1 Energy
axis output. They may appear as partner (supplier) countries
in the bilateral breakdowns but are not scored.


## 5. Data Sources

One primary data source is used:

Source: Eurostat — Energy Statistics
- Datasets:
  - nrg_ti_gas — Imports of natural gas by partner country
  - nrg_ti_oil — Imports of oil and petroleum products by
    partner country
  - nrg_ti_sff — Imports of solid fossil fuels by partner
    country
- Access method: SDMX 2.1 REST API (JSON format)
- Base URL: https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data
- SDMX key: A.... (annual frequency, all dimensions
  wildcarded)
- Query parameters: startPeriod=2024, endPeriod=2024
- Unit: As reported per dataset (terajoules, thousand
  tonnes, or other Eurostat standard units)

No other data sources are used.
No third-party composite indices are used.
No qualitative inputs are used.


## 6. Channel A — Natural Gas Import Concentration

### Definition

Channel A measures the concentration of natural gas
imports into country i, broken down by supplier country.

It captures how much of country i's gas imports originate
from each foreign supplier and how concentrated that
supplier base is.

The dependency perspective is importer-side: country i is
the buyer; partner countries j are the suppliers.

### Mathematical Formulation

For each country i and each product-unit combination p
within the nrg_ti_gas dataset:

Let V_{i,j}^{p} be the import volume of product p from
partner country j into country i.

Share of supplier country j for product p:

  s_{i,j}^{p} = V_{i,j}^{p} / SUM_j V_{i,j}^{p}

Concentration for product p (HHI):

  C_i^{p} = SUM_j ( s_{i,j}^{p} )^2

C_i^{p} is in [0, 1].

Fuel-level concentration is computed as the volume-weighted
average across all product-unit combinations within the
gas dataset:

  C_i^{gas} = SUM_p [ C_i^{p} * W_i^{p} ] / SUM_p W_i^{p}

Where W_i^{p} = SUM_j V_{i,j}^{p} is the total import
volume of product p for country i.

### Data Source and Coverage

Dataset: Eurostat nrg_ti_gas.
All 27 EU member states may appear as importing countries.
Partner countries include all Eurostat-reported supplier
origins.

### Known Limitations

1. Pipeline gas and LNG are not separated. The dataset
   reports total gas imports by partner country without
   distinguishing delivery mode.

2. No contract duration or long-term supply agreement
   information is captured. Spot vs contract volumes
   are not differentiated.

3. Re-exports and transit flows may distort bilateral
   attribution. A country that re-exports gas from a
   third country may appear as an origin.


## 7. Channel B — Oil and Petroleum Products Import Concentration

### Definition

Channel B measures the concentration of crude oil and
petroleum product imports into country i, broken down
by supplier country.

It captures how much of country i's oil-related imports
originate from each foreign supplier and how concentrated
that supplier base is.

### Mathematical Formulation

The formulation is identical to Channel A, applied to the
nrg_ti_oil dataset.

Let V_{i,j}^{p} be the import volume of product p from
partner country j into country i.

Share of supplier country j for product p:

  s_{i,j}^{p} = V_{i,j}^{p} / SUM_j V_{i,j}^{p}

Concentration for product p (HHI):

  C_i^{p} = SUM_j ( s_{i,j}^{p} )^2

Fuel-level concentration:

  C_i^{oil} = SUM_p [ C_i^{p} * W_i^{p} ] / SUM_p W_i^{p}

### Data Source and Coverage

Dataset: Eurostat nrg_ti_oil.
Coverage is analogous to Channel A.

### Known Limitations

1. Crude oil and refined petroleum products are grouped
   within a single dataset. Different product-unit
   combinations within nrg_ti_oil are aggregated via
   volume weighting, but crude and refined streams are
   not separated at the channel level.

2. No price effects are captured. Volume-based
   concentration does not account for price differentials
   between suppliers.

3. Re-exports and transit flows may distort bilateral
   attribution.


## 7b. Supplementary Fuel — Solid Fossil Fuels

### Definition

Solid fossil fuel import concentration is computed
identically to Channels A and B, using the nrg_ti_sff
dataset.

  C_i^{sff} = SUM_p [ C_i^{p} * W_i^{p} ] / SUM_p W_i^{p}

This fuel participates in the cross-fuel aggregation
alongside gas and oil. It is not designated as a
separate named channel but follows the identical
methodology.

### Data Source and Coverage

Dataset: Eurostat nrg_ti_sff.
Coverage is analogous to Channels A and B.

### Known Limitations

1. Solid fossil fuels include hard coal, brown coal,
   coke, and other solid fuels as reported by Eurostat.
   Sub-fuel disaggregation is handled at the product-
   unit level via volume weighting.

2. No price or quality differentiation is captured.


## 8. Cross-Fuel Aggregation

### Exact Formula

For each country i:

  E_i = SUM_f [ C_i^{f} * W_i^{f} ] / SUM_f W_i^{f}

Where:
- f ∈ {gas, oil, solid_fossil}
- C_i^{f} is the fuel-level concentration (HHI) for
  fuel f
- W_i^{f} is the total import volume for fuel f

E_i is in [0, 1].

### Weighting Logic

Aggregation is volume-weighted across fuels. The fuel
with the larger absolute import volume contributes
proportionally more to the final score.

If W_i^{f} = 0 for a given fuel, that fuel does not
contribute. The score reduces to the weighted average
of the remaining fuels.

If all W_i^{f} = 0 for a given country, the country
is excluded from the output.

No equal weighting is applied.
No normalization is applied.
No rescaling is applied.

### Scope Enforcement

After aggregation, the output is filtered to EU-27
member states only. Countries outside EU-27 are excluded.
A scope audit file records the inclusion/exclusion
status of every country present in the unfiltered output.


## 9. Exclusions and Deferred Components

The following are explicitly excluded from v0.1:

1. Electricity imports. No bilateral electricity trade
   data is included. Deferred due to methodological
   complexity (interconnected grids, intra-day flows,
   and re-dispatch effects).

2. Pipeline vs LNG separation. The nrg_ti_gas dataset
   does not distinguish delivery mode. No proxy is
   applied.

3. Strategic petroleum and gas reserves. No publicly
   available bilateral reserve composition data exists
   at the required granularity. No proxy is applied.

4. Contract duration and long-term supply agreements.
   Not captured in Eurostat trade flow data.

5. Price effects. All concentrations are volume-based.
   Price differentials between suppliers are not
   reflected.

6. Nuclear fuel imports. Not included in the three
   Eurostat datasets used (nrg_ti_gas, nrg_ti_oil,
   nrg_ti_sff).

7. Renewable energy import dependencies. Not applicable
   to the fossil fuel scope of v0.1.

8. Countries outside EU-27. Not scored in v0.1 Energy
   axis. They may appear as partner countries but are
   not included in the output.


## 10. Reproducibility and Versioning Notes

All inputs are publicly retrievable from Eurostat via
the SDMX 2.1 REST API.

All formulas are explicitly stated in this document.
No hidden parameters, thresholds, or judgment calls
are applied.

All intermediate outputs (flat import data, shares,
concentrations, fuel-level concentrations) are preserved
as CSV files in the data pipeline.

The scope enforcement step produces an audit file
documenting every country's inclusion or exclusion status.

This specification is version 0.1. It is frozen as of
2026-02-07. Any modification requires a new version number.

The version identifier "v0.1" appears in all script
docstrings, output filenames, and methodology documents
associated with this axis.
