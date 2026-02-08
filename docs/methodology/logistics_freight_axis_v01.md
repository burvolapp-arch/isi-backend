# ISI Axis 6 — Logistics / Freight Dependency
# Methodology Specification v0.1

**Version:** 0.1  
**Status:** DRAFT  
**Date:** 2025-02-09  
**Axis:** 6 — Logistics / Freight Dependency  
**Project:** Panargus ISI (Integrated Strategic Index)


## 1. Purpose

This document defines the methodology for ISI Axis 6:
Logistics / Freight Dependency, version 0.1.

The axis measures a country's structural dependence on
(a) a limited number of transport modes for international
freight movement, and (b) a limited number of bilateral
freight partners within each transport mode.

The axis produces a single scalar score per country,
valued in [0, 1]. Higher values indicate greater
structural concentration — and therefore greater
vulnerability to disruption, denial, or coercive
leverage in the physical movement of goods.

The score is computed deterministically from publicly
available Eurostat transport statistics using the
Herfindahl-Hirschman Index (HHI) as the sole
concentration metric. No normalization, rescaling,
thresholds, or policy adjustments are applied.

The axis decomposes into exactly two channels:

- Channel A: Transport Mode Concentration
- Channel B: Partner Concentration per Mode

The two channel scores are combined via a volume-weighted
cross-channel aggregation formula to produce the final
axis score.


## 2. Conceptual Definition

### 2.1 What the axis measures

Logistics / Freight Dependency in ISI terms IS:

- Concentration of international freight across transport
  modes (road, rail, maritime)
- Concentration of bilateral freight partners within each
  transport mode
- A structural position measurement
- Computed from observable bilateral freight flow data
  reported by Eurostat in thousand tonnes (THS_T)
- Decomposable into exactly two channels
- Deterministic and reproducible from public inputs
- Inclusive of intra-EU freight flows (dependency on EU
  partners is treated identically to dependency on non-EU
  partners)

### 2.2 What the axis does NOT measure

Logistics / Freight Dependency in ISI terms is NOT:

- Physical route or corridor concentration. No public
  Eurostat dataset reveals which physical routes (e.g.,
  Suez Canal, Bosporus Strait, Brenner Pass) goods
  traverse. The data provides origin-destination pairs
  by mode, not routing paths. This was verified through
  25+ direct API probes during feasibility assessment.

- Transit country or intermediary country dependence. No
  public Eurostat dataset reveals which countries goods
  transit through en route from origin to destination.
  Road data reports where goods are loaded and unloaded,
  not the transit path. KILLED during feasibility.

- Infrastructure chokepoint vulnerability. No data on
  specific bridges, tunnels, ports-of-transit, canal
  passages, or strait transits is available in any
  Eurostat freight table.

- Multimodal supply chain routing. If Chinese goods
  arrive by sea at Rotterdam and then move by rail to
  Germany, this appears as NL→DE by rail (if reported),
  not as a single China→DE supply chain.

- Logistics performance or efficiency. No LPI (Logistics
  Performance Index), dwell time, customs clearance, or
  handling quality measures are included.

- Infrastructure quality or capacity. No road quality
  ratings, port depth, rail gauge, or capacity
  utilization metrics are included.

- Supply chain governance, trade facilitation, or
  regulatory alignment.

- A policy recommendation or regime judgment. The axis
  measures structural concentration, not whether that
  concentration is "good" or "bad."


## 3. Scope

### 3.1 Geographic scope

EU-27 member states. The following 27 countries are
scored:

AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES,
FI, FR, HR, HU, IE, IT, LT, LU, LV, MT,
NL, PL, PT, RO, SE, SI, SK

Countries outside EU-27 may appear as partner countries
in bilateral freight flows but are not included in the
output.

### 3.2 Temporal scope

Reference year: most recent year with complete coverage
across all three transport modes (road, rail, maritime).
Based on feasibility probing, datasets provide coverage
through 2023-2024. The specific reference year is
determined during data extraction and documented in the
pipeline output.

Multi-year averaging: NOT applied in v0.1. The score
is computed from a single reference year to avoid
temporal smoothing that could mask recent structural
shifts.

### 3.3 Mode scope

Three transport modes are included:

1. **Road** — International road freight, measured in
   thousand tonnes (THS_T)
2. **Rail** — International rail freight, measured in
   thousand tonnes (THS_T)
3. **Maritime** — Maritime freight, measured in thousand
   tonnes (THS_T)

Three transport modes are EXCLUDED:

1. **Air** — No bilateral partner dimension exists in any
   public Eurostat air freight dataset. Verified via
   direct probe of `avia_gooc`. EXCLUDED.
2. **Inland Waterway (IWW)** — No bilateral partner
   dimension exists in public Eurostat IWW freight
   dataset `iww_go_atygo`. EXCLUDED from bilateral
   analysis. IWW volumes ARE included in Channel A mode
   shares via `tran_hv_frmod` where reported.
3. **Pipeline** — No publicly available bilateral data.
   Pipeline freight is covered separately under ISI
   Axis 3 (Energy). EXCLUDED.

### 3.4 Coverage gaps by mode

The following coverage gaps are structurally inherent
and do not represent data errors:

| Country | Road | Rail | Maritime | Reason |
|---------|------|------|----------|--------|
| MT | ❌ | ❌ | ✅ | Island state; no road/rail freight |
| CY | ✅ | ❌ | ✅ | Island state; no rail connections |
| AT | ✅ | ✅ | ❌ | Landlocked |
| CZ | ✅ | ✅ | ❌ | Landlocked |
| HU | ✅ | ✅ | ❌ | Landlocked |
| LU | ✅ | ✅ | ❌ | Landlocked |
| SK | ✅ | ✅ | ❌ | Landlocked |

All remaining 20 EU-27 members have data for all three
modes.

### 3.5 Freight flow direction

Both inward (import/unloading) and outward (export/
loading) freight flows are used. The specific treatment
depends on the dataset:

- Road: `road_go_ia_lgtt` provides loaded goods by
  country of unloading (outward from reporter);
  `road_go_ia_ugtt` provides unloaded goods by country
  of loading (inward to reporter). Both directions are
  combined.
- Rail: `rail_go_intgong` provides goods from reporting
  country to unloading country (outward). The
  corresponding inward table is used symmetrically.
- Maritime: `mar_go_am_{iso2}` provides both inward and
  outward flows via the `direct` dimension.

### 3.6 Indicator

All concentrations are computed on freight tonnage
(thousand tonnes, THS_T). No price, value, or monetary
unit is used. This axis measures physical freight
dependency, not trade value dependency.

### 3.7 Dependency perspective

Intra-EU freight flows are treated as dependency.
Dependency on France (an EU ally) is measured identically
to dependency on a non-EU country. This is consistent
with the ISI framework applied across all axes: the index
measures structural concentration, not geopolitical
alignment.


## 4. Data Sources

### 4.1 Primary datasets

Four Eurostat datasets are used. All are publicly
available via the Eurostat JSON/SDMX API. No
authentication is required.

**Dataset 1: road_go_ia_lgtt**
Title: International road freight — loaded goods by
  country of unloading
API: https://ec.europa.eu/eurostat/api/dissemination/
  statistics/1.0/data/road_go_ia_lgtt
Dimensions: freq, tra_type, c_unload, nst07, unit,
  geo, time
Partner dimension: c_unload (76 countries)
Unit: THS_T (thousand tonnes)
EU-27 coverage: 26/27 (MT missing)
Time range: 2008–2024
Role: Channel B — road partner concentration (outward)

**Dataset 2: road_go_ia_ugtt**
Title: International road freight — unloaded goods by
  country of loading
API: https://ec.europa.eu/eurostat/api/dissemination/
  statistics/1.0/data/road_go_ia_ugtt
Dimensions: freq, tra_type, c_load, nst07, unit,
  geo, time
Partner dimension: c_load
Unit: THS_T (thousand tonnes)
EU-27 coverage: 26/27 (MT missing)
Time range: 2008–2024
Role: Channel B — road partner concentration (inward)

**Dataset 3: rail_go_intgong**
Title: International rail goods transport — from
  reporting country to country of unloading
API: https://ec.europa.eu/eurostat/api/dissemination/
  statistics/1.0/data/rail_go_intgong
Dimensions: freq, unit, c_unload, geo, time
Partner dimension: c_unload (78 countries)
Unit: THS_T (thousand tonnes)
EU-27 coverage: 25/27 (CY, MT missing)
Time range: 2003–2024
Role: Channel B — rail partner concentration

**Dataset 4: mar_go_am_{iso2}**
Title: Maritime goods transport — main ports, by partner
  Maritime Coastal Area (per-country tables)
API: https://ec.europa.eu/eurostat/api/dissemination/
  statistics/1.0/data/mar_go_am_{iso2}
  (where {iso2} is the 2-letter country code in
  lowercase, e.g., mar_go_am_de, mar_go_am_fr)
Dimensions: freq, direct, cargo, natvessr, unit,
  par_mar, rep_mar, time
Partner dimension: par_mar (249 Maritime Coastal Areas)
Unit: THS_T (thousand tonnes)
EU-27 coverage: 22/27 (5 landlocked excluded: AT, CZ,
  HU, LU, SK — structurally correct)
Time range: 1997–2024
Role: Channel B — maritime partner concentration
Note: Data is split across 22 per-country tables. Each
  must be retrieved separately.

### 4.2 Supplementary dataset

**Dataset 5: tran_hv_frmod**
Title: Modal split of inland freight transport
API: https://ec.europa.eu/eurostat/api/dissemination/
  statistics/1.0/data/tran_hv_frmod
Dimensions: freq, unit, tra_mode, geo, time
Modes: ROAD, RAIL, IWW
Unit: PC (percentage)
EU-27 coverage: 27/27 (all countries)
Time range: varies
Role: Channel A — mode concentration input. Provides
  modal share of inland freight (road, rail, IWW) as
  percentages. Maritime share is derived separately
  from bilateral maritime datasets (total tonnage).

### 4.3 No other data sources

No third-party datasets are used.
No composite indices are used.
No qualitative inputs are used.
No survey data is used.


## 5. Channel A — Transport Mode Concentration

### 5.1 Definition

Channel A measures how concentrated a country's
international freight is across transport modes. A
country that depends overwhelmingly on a single transport
mode for moving goods is structurally more vulnerable to
disruption of that mode than a country with balanced
multimodal freight.

Channel A answers: how dependent is country i on a
single transport mode for its international freight?

### 5.2 Mode set

For each country i, the set of active modes M_i is
determined by data availability:

- Countries with all three modes: M_i = {road, rail,
  maritime} (20 countries)
- Landlocked countries: M_i = {road, rail}
  (AT, CZ, HU, LU, SK)
- CY: M_i = {road, maritime} (no rail connections)
- MT: M_i = {maritime} (no road data, no rail)

IWW (inland waterway) is included in mode shares where
reported via `tran_hv_frmod`. When IWW data is available
for a country, M_i is expanded to include IWW.

### 5.3 Mathematical formulation

For each country i, let T_i^{m} be the total
international freight tonnage (THS_T) moved by mode m.

Mode share:

  s_i^{m} = T_i^{m} / SUM_m T_i^{m}

where the sum is over all active modes m ∈ M_i.

Shares sum to 1.0 across all active modes.

Mode concentration (HHI):

  C_i^{(A)} = SUM_m ( s_i^{m} )^2

C_i^{(A)} is in [0, 1].

C_i^{(A)} approaches 0 when freight is uniformly spread
across many modes. In practice, with at most 4 modes,
the minimum HHI for a country with n equally-used modes
is 1/n (i.e., 0.25 for 4 modes, 0.33 for 3 modes, 0.50
for 2 modes).

C_i^{(A)} = 1 when all freight moves on a single mode.

### 5.4 Mode tonnage derivation

Mode tonnage T_i^{m} is derived as follows:

- Road: Sum of bilateral tonnage from `road_go_ia_lgtt`
  and `road_go_ia_ugtt` for country i across all
  partners, aggregated to total road freight. Cross-
  validated against `tran_hv_frmod` percentage shares.

- Rail: Sum of bilateral tonnage from `rail_go_intgong`
  for country i across all partners. Cross-validated
  against `tran_hv_frmod` percentage shares.

- Maritime: Sum of bilateral tonnage from
  `mar_go_am_{iso2}` for country i across all partner
  MCAs.

- IWW: Derived from `tran_hv_frmod` percentage shares
  and total inland freight volume. No bilateral partner
  data exists for IWW.

### 5.5 Volume for cross-channel weighting

  W_i^{(A)} = SUM_m T_i^{m}

This is the total international freight tonnage moved by
country i across all active modes.

### 5.6 Known limitations

1. The number of active modes varies by country (2 to 4).
   Countries with fewer available modes mechanically have
   higher minimum HHI. Malta with only maritime freight
   has C_i^{(A)} = 1.0 by construction, not by strategic
   choice. This is arithmetically correct — Malta IS
   100% dependent on maritime freight — but the score
   is structurally constrained.

2. IWW is included in mode shares where data is available
   via `tran_hv_frmod`, but IWW has no bilateral partner
   dimension. IWW contributes to Channel A (mode
   concentration) but NOT to Channel B (partner
   concentration). This creates asymmetry: a country
   with large IWW shares has more modes in Channel A
   but the same modes in Channel B.

3. Air freight is excluded entirely. For most EU-27
   countries, air freight represents a small fraction of
   total freight tonnage. However, for high-value,
   low-weight goods (e.g., pharmaceuticals, electronics),
   air freight may be strategically significant despite
   low tonnage share. This limitation is inherent to
   tonnage-based measurement.

4. Mode shares are computed on tonnage, not on value.
   Road freight of bulk commodities counts equally per
   tonne with rail freight of manufactured goods. No
   value weighting is applied.


## 6. Channel B — Partner Concentration per Mode

### 6.1 Definition

Channel B measures, for each transport mode separately,
how concentrated a country's bilateral freight is across
partner countries. It then aggregates across modes using
freight tonnage as weights.

Channel B answers: for each transport mode, how dependent
is country i on a small number of bilateral freight
partners?

### 6.2 Mathematical formulation

For each country i and each mode m with bilateral data:

Let V_{i,j}^{m} be the bilateral freight tonnage (THS_T)
between country i and partner country j via mode m.

Share of partner j for mode m:

  s_{i,j}^{m} = V_{i,j}^{m} / SUM_j V_{i,j}^{m}

Shares sum to 1.0 over all partner countries with
non-zero bilateral freight for country i in mode m.

Partner concentration for mode m (HHI):

  C_i^{(B,m)} = SUM_j ( s_{i,j}^{m} )^2

C_i^{(B,m)} is in [0, 1].

Mode freight volume:

  V_i^{m} = SUM_j V_{i,j}^{m}

Aggregate Channel B concentration (freight-volume-
weighted across modes):

  C_i^{(B)} = SUM_m [ C_i^{(B,m)} * V_i^{m} ]
              / SUM_m V_i^{m}

where the sum is over all modes m with bilateral partner
data for country i. This means m ∈ {road, rail,
maritime}, subject to the coverage constraints in
Section 3.4.

C_i^{(B)} is in [0, 1].

### 6.3 Modes with bilateral partner data

Only the following modes have bilateral partner
dimensions and are included in Channel B:

- Road (via `road_go_ia_lgtt` / `road_go_ia_ugtt`)
- Rail (via `rail_go_intgong`)
- Maritime (via `mar_go_am_{iso2}`)

IWW and air do NOT have bilateral partner dimensions
and are EXCLUDED from Channel B.

### 6.4 Maritime partner dimension: MCA codes

The maritime dataset `mar_go_am_{iso2}` uses Maritime
Coastal Area (MCA) codes in the `par_mar` dimension,
not ISO country codes. MCAs are sub-national coastal
regions defined by Eurostat. Multiple MCAs may belong
to the same country.

For Channel B computation, MCA-level bilateral data
is aggregated to the country level before computing
partner shares. This ensures consistency with road
and rail data, which use country-level partner
dimensions.

The MCA-to-country mapping is documented in the
pipeline's reference mapping file.

### 6.5 Volume for cross-channel weighting

  W_i^{(B)} = SUM_m V_i^{m}

This is the total bilateral freight tonnage for country i
across all modes with bilateral data (road + rail +
maritime, subject to coverage).

Note: W_i^{(B)} may differ from W_i^{(A)} because
Channel A may include IWW tonnage (from `tran_hv_frmod`)
while Channel B excludes IWW (no bilateral data). This
asymmetry is structural and documented.

### 6.6 Known limitations

1. Maritime data is split across 22 per-country tables
   (`mar_go_am_{iso2}`). Each table must be retrieved
   separately. Tables may have slightly different time
   coverage or dimension values.

2. Maritime bilateral data exhibits systematic asymmetry
   between reporter and partner declarations. For
   example, DE reports 2,343 kt to FR via maritime,
   while FR reports only 1,554 kt from DE. Standard
   practice: each country's own reporter data is used
   for that country's freight profile. No reconciliation
   or averaging is applied.

3. MCA-level data introduces granularity that must be
   aggregated to the country level. Some MCAs may
   correspond to overseas territories or non-sovereign
   entities, requiring careful mapping.

4. Road data combines both directions (loaded and
   unloaded). Double-counting is prevented by using
   each country's reporter declarations only, not
   summing reporter and mirror data.

5. Partner concentration is computed on tonnage, not
   value. A country that receives bulk coal by rail from
   one partner and precision instruments by road from
   another treats both equally per tonne.

6. Entrepôt and re-export effects: the Netherlands,
   Belgium, and Germany serve as major freight hubs.
   Goods transiting through Rotterdam or Antwerp may
   appear as originating from NL or BE, inflating
   apparent bilateral concentration on these partners
   and masking the true origin. No origin-adjustment
   is applied.


## 7. Cross-Channel Aggregation

### 7.1 Aggregation formula

For each country i:

  L_i = ( C_i^{(A)} * W_i^{(A)} + C_i^{(B)} * W_i^{(B)} )
        / ( W_i^{(A)} + W_i^{(B)} )

Where:
- C_i^{(A)} is Channel A concentration (mode HHI)
- C_i^{(B)} is Channel B concentration (partner HHI,
  volume-weighted across modes)
- W_i^{(A)} is total freight tonnage across all active
  modes (including IWW where available)
- W_i^{(B)} is total bilateral freight tonnage across
  modes with partner data (road + rail + maritime)
- L_i is the final Axis 6 score for country i

L_i is in [0, 1].

### 7.2 Weight asymmetry

Unlike ISI Axis 5 (Critical Inputs), where W^{(A)} =
W^{(B)} by construction, Axis 6 may have W_i^{(A)} ≠
W_i^{(B)} because:

- Channel A includes IWW tonnage (from `tran_hv_frmod`)
  when available
- Channel B excludes IWW (no bilateral partner data)

The volume-weighted formula is therefore NOT equivalent
to a simple arithmetic mean. The channel with larger
total tonnage contributes proportionally more. In
practice, IWW represents a small share of total freight
for most countries, so the deviation from 0.5/0.5 is
typically modest.

### 7.3 Edge cases

If W_i^{(A)} = 0 for a given country, Channel A does
not contribute. The score reduces to C_i^{(B)}.

If W_i^{(B)} = 0 for a given country, Channel B does
not contribute. The score reduces to C_i^{(A)}.

If both W_i^{(A)} = 0 and W_i^{(B)} = 0, the country
is omitted from the output with audit status
OMITTED_NO_DATA.

In practice, no EU-27 country is expected to have zero
total freight tonnage. All 27 countries should produce
valid scores.

### 7.4 Output properties

No normalisation is applied.
No rescaling is applied.
No thresholds are applied.
No policy adjustments are applied.
No ranking is imposed.

The output is a set of 27 scalar values, one per EU-27
member state, each in [0, 1].


## 8. Exclusions and Limitations

### 8.1 Substantive exclusions

The following are explicitly excluded from v0.1:

1. Route and corridor concentration. No public Eurostat
   dataset provides information on which physical routes,
   corridors, or chokepoints (e.g., Suez Canal, Bosporus
   Strait, Brenner Pass, Strait of Malacca) goods
   traverse. This was the original Channel A concept; it
   was KILLED during feasibility assessment after 25+
   API probes confirmed no such data exists.

2. Transit country or intermediary country concentration.
   No public Eurostat dataset reveals which countries
   goods transit through en route between origin and
   destination. This was the original Channel B concept;
   it was KILLED during feasibility assessment.

3. Air freight bilateral flows. No bilateral partner
   dimension exists in `avia_gooc` or any other public
   Eurostat air freight dataset. Air freight is entirely
   excluded.

4. Inland waterway bilateral flows. No bilateral partner
   dimension exists in `iww_go_atygo`. IWW is included
   in Channel A mode shares but excluded from Channel B
   partner concentration.

5. Pipeline freight. Not publicly available at bilateral
   granularity. Energy pipeline dependency is covered
   under ISI Axis 3.

6. Freight value. All concentrations are tonnage-based.
   No monetary value data is used. High-value, low-
   weight goods (e.g., pharmaceuticals, electronics)
   contribute less to concentration than their economic
   significance would warrant.

7. Logistics performance indices. No LPI, dwell time,
   customs efficiency, or handling quality metrics are
   incorporated.

8. Infrastructure quality or capacity. No port depth,
   rail gauge, road condition, or capacity utilization
   data is used.

9. Countries outside EU-27. Not scored in v0.1. They
   appear only as partner countries.

### 8.2 Structural limitations

The following structural properties of the data and
methodology may affect interpretation:

1. Entrepôt and hub masking. The Netherlands, Belgium,
   and Germany serve as major European freight hubs.
   Goods transiting through Rotterdam, Antwerp, or
   Hamburg may appear as originating from NL, BE, or DE
   in bilateral freight data, inflating apparent partner
   concentration on these countries and masking the true
   origin. This applies to all three modes but is
   particularly significant for maritime freight. No
   origin-adjustment is applied in v0.1.

2. Small-economy amplification. Countries with minimal
   total freight volumes (e.g., CY, MT, LU) produce
   mechanically high HHI values because their freight
   base consists of few bilateral flows. A single large
   shipment from one partner can dominate the entire
   mode profile. These scores are arithmetically correct
   but are not comparable in strategic significance to
   high HHI values from large economies. No volume
   normaliser is applied in v0.1.

3. Structural mode constraints. Island states (CY, MT)
   are inherently dependent on maritime freight.
   Landlocked states (AT, CZ, HU, LU, SK) have zero
   maritime freight by geography. These constraints
   produce deterministic HHI patterns that reflect
   geography, not policy failure.

4. Maritime data asymmetry. Reporter and partner
   declarations differ systematically. DE reports 2,343
   kt to FR; FR reports 1,554 kt from DE. Each
   country's own reporter data is used. No
   reconciliation is applied.

5. Mode count inequality. Countries have between 1 and 4
   active modes. The minimum possible HHI for Channel A
   is 1/|M_i|, which varies from 0.25 (4 modes) to 1.0
   (1 mode). This structural floor is not adjusted.

6. IWW asymmetry between channels. IWW contributes to
   Channel A (mode shares) but not to Channel B (no
   bilateral data). Countries with significant IWW
   freight (e.g., NL, DE, BE) have a broader mode base
   in Channel A than in Channel B, creating structural
   asymmetry between the two channels.

7. Temporal snapshot. v0.1 uses a single reference year.
   Freight patterns may exhibit significant year-to-year
   variation due to seasonal effects, strikes, pandemic
   disruption, or infrastructure closures. No temporal
   smoothing is applied.


## 9. Reproducibility

All inputs are publicly retrievable from Eurostat via
the JSON statistics API:

  https://ec.europa.eu/eurostat/api/dissemination/
  statistics/1.0/data/{dataset_code}

All formulas are explicitly stated in this document.
No hidden parameters, thresholds, or judgment calls
are applied.

All intermediate outputs (bilateral freight tonnages,
mode shares, per-mode partner shares, per-mode partner
HHI values, Channel A score, Channel B score, final
score) are preserved as CSV files in the data pipeline.

The MCA-to-country mapping for maritime data is
documented in a separate versioned reference file.

The scope enforcement step produces an audit file
documenting every country's inclusion or exclusion
status, available modes, and data completeness.

To reproduce the v0.1 results from scratch:

1. Retrieve bilateral road freight data from
   `road_go_ia_lgtt` and `road_go_ia_ugtt`, filtering
   to EU-27 reporters and the reference year.

2. Retrieve bilateral rail freight data from
   `rail_go_intgong`, filtering to EU-27 reporters and
   the reference year.

3. Retrieve bilateral maritime freight data from 22
   per-country tables `mar_go_am_{iso2}`, one per
   maritime EU-27 country.

4. Retrieve modal split data from `tran_hv_frmod` for
   all EU-27 countries.

5. Compute Channel A: mode shares and mode HHI per
   country.

6. Compute Channel B: per-mode partner shares, per-mode
   partner HHI, volume-weighted aggregate partner HHI
   per country.

7. Compute cross-channel aggregation: volume-weighted
   combination of Channel A and Channel B scores.

No external API credentials, proprietary datasets, or
manual adjustments are required at any step.


## 10. Versioning

This specification is version 0.1.

The version identifier "v0.1" appears in all script
docstrings, output filenames, and methodology documents
associated with this axis.

Version 0.1 is the first scored release of the Logistics
/ Freight Dependency Axis. It establishes the baseline
mode set, channel structure, and concentration metric.
Subsequent versions may:

- Incorporate air freight bilateral data if Eurostat
  publishes partner-level tables
- Add IWW bilateral data if partner dimensions become
  available
- Extend to multi-year temporal windows
- Introduce commodity-weighted mode concentration
- Separate maritime data into container, bulk, and
  tanker segments where data permits

Any such modification requires a new version number.


## 11. Relationship to Other ISI Axes

Axis 6 is designed to be orthogonal to other ISI axes:

- Axis 3 (Energy): Measures energy import concentration
  by supplier country. Axis 6 measures freight mode and
  partner concentration. Energy pipeline dependency is
  in Axis 3, not Axis 6.

- Axis 5 (Critical Inputs): Measures critical raw
  material import concentration by supplier country
  (EUR value-based). Axis 6 measures freight
  concentration by transport mode and bilateral partner
  (tonnage-based). The two axes may correlate for
  countries with concentrated trade profiles, but they
  measure different structural dimensions: Axis 5
  measures WHAT is imported and from WHOM, while Axis 6
  measures HOW goods are physically moved and with WHICH
  bilateral freight partners.

- Axis 1 (Defense), Axis 2 (Tech), Axis 4 (Finance):
  No direct overlap.


End of methodology specification.
