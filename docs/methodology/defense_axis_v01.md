# Defense / Military Dependency Axis — ISI v0.1

Version: 0.1
Status: FROZEN
Date: 2026-02-07
Axis: Defense / Military Dependency
Project: Panargus / International Sovereignty Index (ISI)


## 1. Title and Version Block

Axis name: Defense / Military Dependency
Version: 0.1
Reference year: 2024 (delivery window: 2019–2024)
Geographic scope: EU-27
Channels: 2 (A: Supplier Country Concentration, B: Capability-Block Concentration)
Concentration metric: Herfindahl-Hirschman Index (HHI)
Aggregation method: Volume-weighted average across channels
Score range: [0, 1]


## 2. Purpose of the Defense / Military Dependency Axis

The Defense / Military Dependency Axis measures the degree
to which a country's major conventional arms imports are
concentrated among a small number of foreign supplier
countries and across a narrow set of military capability
domains.

It quantifies structural exposure to potential denial,
disruption, or coercive leverage by dominant arms suppliers.

It produces a single scalar score per country per year.

Higher values indicate greater supplier concentration
(more dependency). Lower values indicate greater
diversification (more autonomy).


## 3. Conceptual Definition

Defense Dependency in ISI terms IS:
- Concentration of major conventional arms imports by
  supplier country and by capability domain
- A structural position measurement
- Computed from observable bilateral arms transfer data
- Decomposable into exactly two channels

Defense Dependency in ISI terms is NOT:
- Military capability or force readiness
- Defense spending adequacy (% GDP)
- NATO membership or alliance commitment
- Domestic defense industrial capacity
- Arms export performance
- Ammunition or consumables supply chain resilience
- Licensed domestic production dependency
- Maintenance, repair, and overhaul (MRO) dependency
- A policy recommendation or regime judgment


## 4. Geographic and Temporal Scope

Countries: EU-27 member states as of 2024.

The 27 Eurostat geo codes are:
AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU,
IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK.

Reference year: 2024.

Delivery window: 2019–2024. SIPRI Trade Register deals
are included if any delivery year falls within this
six-year window. Total delivered TIV is distributed
evenly across delivery years within the window.

Countries outside the EU-27 are excluded from v0.1
Defense axis output. They may appear as supplier countries
in the bilateral breakdowns but are not scored.

Special case: Slovakia (SK) is omitted from the scored
output due to zero SIPRI-recorded major arms deliveries
in the 2019–2024 window. SK appears in the audit file
with status OMITTED_NO_DATA.


## 5. Data Sources

One primary data source is used:

Source: Stockholm International Peace Research Institute (SIPRI)
- Dataset: Arms Transfers Database — Trade Register
- Export format: CSV (manual download)
- Filter: Deliveries to EU-27 recipients, 2019–2024
- File: sipri_trade_register_2019_2024.csv
- Encoding: Latin-1
- Structure: 11 metadata lines before header row (line 12)
- Columns (16): Recipient, Supplier, Year of order,
  [empty], Number ordered, [empty], Weapon designation,
  Weapon description, Number delivered, [empty],
  Year(s) of delivery, status, Comments, SIPRI TIV per
  unit, SIPRI TIV for total order, SIPRI TIV of delivered
  weapons
- Metric: SIPRI Trend-Indicator Value (TIV), a volume-
  based measure of major conventional arms transfers
- Access: https://www.sipri.org/databases/armstransfers

No other data sources are used.
No third-party composite indices are used.
No qualitative inputs are used.

SIPRI Trade Register data is ingested from a manually
downloaded CSV file. This design choice preserves
methodological transparency and reproducibility without
reliance on API credentials.


## 6. Channel A — Supplier Country Concentration

### Definition

Channel A measures the concentration of inward major arms
transfers to country i, broken down by supplier country,
aggregated across all capability blocks and all years in
the delivery window.

It captures how much of country i's total received TIV
originates from each foreign supplier and how concentrated
that supplier base is.

The dependency perspective is importer-side: country i is
the recipient; countries j are the suppliers.

### Mathematical Formulation

Let V_{i,j}^{(A)} be the total TIV of major arms
delivered by supplier country j to recipient country i,
summed across all capability blocks and all years in the
delivery window (2019–2024).

Share of supplier country j:

  s_{i,j}^{(A)} = V_{i,j}^{(A)} / SUM_j V_{i,j}^{(A)}

Concentration (HHI):

  C_i^{(A)} = SUM_j ( s_{i,j}^{(A)} )^2

C_i^{(A)} is in [0, 1].
C_i^{(A)} = 0 when TIV is uniformly spread across
infinitely many suppliers.
C_i^{(A)} = 1 when all TIV originates from a single
supplier.

Volume for cross-channel weighting:

  W_i^{(A)} = SUM_j V_{i,j}^{(A)}

This is the total TIV received by country i from all
supplier countries across the delivery window.

### Data Source and Coverage

Dataset: SIPRI Trade Register (2019–2024 deliveries).
SIPRI country names are mapped to Eurostat geo codes.
Supplier names are mapped to ISO-2 codes.

Special mappings applied:
- "Turkiye" → TR (SIPRI 2024 spelling)
- "unknown supplier(s)" → XX (SIPRI convention)
- "Czech Republic" → CZ (historical name)
- "Greece" → EL (Eurostat convention)

Self-pairs (recipient = supplier after code mapping) are
excluded. Recipients outside EU-27 are excluded.

### Known Limitations

1. SIPRI TIV is a volume indicator, not a financial value.
   It measures the military capability transferred, not
   the contract price. Concentration in TIV terms may
   differ from concentration in monetary terms.

2. SIPRI covers major conventional weapons systems only.
   Small arms, ammunition, maintenance, sustainment, and
   licensed domestic production are excluded from scope.
   This introduces a major-system bias: countries whose
   import portfolios are dominated by small arms or
   sustainment contracts will appear to have lower import
   volumes than their actual procurement dependency
   warrants.

3. The six-year delivery window (2019–2024) smooths
   annual volatility but may include deliveries under
   contracts signed decades earlier. No contract-vintage
   adjustment is applied.

4. TIV is distributed evenly across delivery years. If
   a deal delivers 10 units over 2020–2024, each year
   receives 2 units × TIV per unit. The actual delivery
   schedule within the window is not known.


## 7. Channel B — Capability-Block Concentration

### Definition

Channel B measures the concentration of inward major arms
transfers to country i, broken down by supplier country
WITHIN each of six capability blocks, then aggregated
across blocks via TIV weighting.

It captures whether country i relies on the same supplier
across all military capability domains or has diversified
supplier bases per domain.

### Capability Blocks

Six blocks are defined. Every weapon description in the
SIPRI Trade Register is classified into exactly one block
using ordered regex rules. First match wins.

Block evaluation order and classification criteria:

1. air_missile_defense — SAM systems, MANPADS, SPAAG,
   anti-aircraft, CIWS, SHORADS, Patriot, S-300, S-400,
   NASAMS, IRIS-T SLM, Gepard, surface-to-air systems.
   Evaluated first to capture SAM/air defense items before
   the general missile block.

2. air_power — Fixed-wing aircraft, helicopters, FGA,
   fighters, trainers, transport aircraft, tanker aircraft,
   AEW/AWACS, maritime patrol aircraft, UAV/UCAV/drones,
   aircraft engines (turbofan, turboprop, turboshaft).

3. land_combat — Tanks, IFV, APC, armoured vehicles,
   howitzers, mortars, artillery, self-propelled guns,
   multiple rocket launchers, armoured vehicle engines
   and turrets.

4. naval_combat — Frigates, corvettes, submarines,
   destroyers, aircraft carriers, fast attack craft (FAC),
   OPV, patrol boats, patrol ships, patrol vessels,
   minehunters, MCM vessels, landing ships, landing craft,
   support ships, transport ships, ship engines, naval
   guns, torpedoes, sonar, ASW weapons.

5. strike_missile — Air-to-surface missiles, surface-to-
   surface missiles, guided rockets, guided shells,
   loitering munitions, ASM, SSM, ARM, ALCM, SLCM,
   anti-ship missiles, anti-tank guided missiles, guided
   bombs, cruise missiles, ballistic missiles, BVRAAM,
   SRAAM, stand-off weapons, rocket launchers (excluding
   multiple rocket launchers, which are classified as
   land_combat).

6. isr_support — Radar, sensors, electro-optical systems,
   SIGINT/ELINT, surveillance, reconnaissance, satellites,
   fire control systems, and all items not matched by
   blocks 1–5 (catch-all fallback).

Block classification is deterministic and logged. Every
unique weapon description is recorded with its assigned
block and the specific regex sub-pattern that matched, in
a capability block mapping audit file.

### Mathematical Formulation

For each recipient country i and capability block k:

Let V_{i,j}^{(B,k)} be the total TIV delivered by supplier
country j to recipient country i in block k, summed across
all years in the delivery window.

Share of supplier j in block k:

  s_{i,j}^{(B,k)} = V_{i,j}^{(B,k)} / SUM_j V_{i,j}^{(B,k)}

Block-level concentration (HHI):

  C_i^{(B,k)} = SUM_j ( s_{i,j}^{(B,k)} )^2

Block TIV volume:

  V_i^{(k)} = SUM_j V_{i,j}^{(B,k)}

Aggregate Channel B concentration (TIV-weighted across
blocks):

  C_i^{(B)} = SUM_k [ C_i^{(B,k)} * V_i^{(k)} ]
              / SUM_k V_i^{(k)}

C_i^{(B)} is in [0, 1].

Blocks with zero TIV for a given recipient are excluded
from the weighted average.

Volume for cross-channel weighting:

  W_i^{(B)} = SUM_k V_i^{(k)}

This equals total TIV received by country i (same as
W_i^{(A)} by construction, since all TIV is assigned to
exactly one block).

### Data Source and Coverage

Same as Channel A: SIPRI Trade Register (2019–2024).

### Known Limitations

1. Regex-based classification is imperfect. Weapon
   descriptions in the SIPRI Trade Register are free-text
   and may contain ambiguous terminology. The ordered-
   rule approach (first match wins) resolves ambiguity
   deterministically but may misclassify edge cases.

2. Block definitions reflect major system categories.
   Cyber, space (beyond satellites), and emerging domains
   are not represented as separate blocks.

3. The isr_support block acts as a catch-all. Items that
   do not match any specific block pattern are assigned
   to isr_support. This may inflate the isr_support
   block's TIV relative to its true scope.


## 8. Cross-Channel Aggregation

### Exact Formula

For each country i:

  D_i = ( C_i^{(A)} * W_i^{(A)} + C_i^{(B)} * W_i^{(B)} )
        / ( W_i^{(A)} + W_i^{(B)} )

Where:
- C_i^{(A)} is Channel A concentration (HHI)
- C_i^{(B)} is Channel B concentration (HHI)
- W_i^{(A)} is total TIV received by country i
  (aggregate supplier concentration basis)
- W_i^{(B)} is total TIV received by country i
  (capability-block concentration basis)

D_i is in [0, 1].

### Weighting Logic

Aggregation is volume-weighted. The channel with the larger
absolute TIV volume contributes proportionally more to
the final score.

By construction, W_i^{(A)} = W_i^{(B)} for all recipients
(both channels account for the same total TIV). The
cross-channel aggregation therefore reduces to a simple
arithmetic average:

  D_i = ( C_i^{(A)} + C_i^{(B)} ) / 2

This equivalence holds because every flat row contributes
to both channels. No TIV is excluded from either channel.
The volume-weighted formula is retained in the code for
generality and consistency with other axes.

If W_i^{(A)} = 0 for a given country, Channel A does not
contribute. The score reduces to C_i^{(B)}.

If W_i^{(B)} = 0 for a given country, Channel B does not
contribute. The score reduces to C_i^{(A)}.

If both W_i^{(A)} = 0 and W_i^{(B)} = 0, the country is
omitted from the output with audit status OMITTED_NO_DATA.

No equal weighting is imposed externally.
No normalization is applied.
No rescaling is applied.


## 9. Exclusions and Deferred Components

The following are explicitly excluded from v0.1:

1. Ammunition and consumables. Not covered by SIPRI Trade
   Register, which tracks major conventional weapons
   systems only.

2. Small arms and light weapons. Excluded from SIPRI
   Trade Register scope.

3. Maintenance, repair, and overhaul (MRO) contracts.
   Not captured in SIPRI transfer data.

4. Licensed domestic production. SIPRI records some
   licensed production but the Trade Register primarily
   tracks physical transfers. Licensed production is
   not isolated or separately scored.

5. NATO guarantees and alliance effects. No adjustment
   is made for alliance membership, nuclear umbrella
   coverage, or collective defense commitments. The axis
   measures observed transfer concentration only.

6. Domestic defense industrial base. No proxy for
   self-sufficiency or domestic production capacity is
   applied.

7. Contract financial values. SIPRI TIV is a capability
   transfer indicator, not a monetary measure. No
   financial data is used.

8. Cyber, space, and emerging technology domains. Not
   represented as separate capability blocks. Satellite-
   related items are captured under isr_support.

9. Countries outside EU-27. Not scored in v0.1 Defense
   axis. They may appear as supplier countries but are
   not included in the output.

10. Slovakia (SK). Omitted due to zero SIPRI-recorded
    deliveries in the 2019–2024 window. Documented in
    audit file with status OMITTED_NO_DATA.


## 10. Reproducibility and Versioning Notes

All inputs are retrievable from the SIPRI Arms Transfers
Database (Trade Register export). The raw CSV is archived
in the project data directory.

All formulas are explicitly stated in this document.
No hidden parameters, thresholds, or judgment calls
are applied.

All intermediate outputs (flat bilateral TIV, shares,
concentrations, volumes, block-level breakdowns) are
preserved as CSV files in the data pipeline.

All capability block classifications are logged in a
per-description audit file
(defense_capability_block_mapping_v01.csv) recording the
assigned block and the specific regex pattern that matched.

A parser waterfall audit file
(defense_parser_waterfall_2024.csv) records row counts at
each processing stage.

Coverage gaps and omitted countries are documented in
per-country audit files accompanying each computation step.

SIPRI country name mappings (SIPRI name → Eurostat/ISO-2
code) are explicitly defined in the parser source code.

This specification is version 0.1. It is frozen as of
2026-02-07. Any modification requires a new version number.

The version identifier "v0.1" appears in all script
docstrings, output filenames, and methodology documents
associated with this axis.
