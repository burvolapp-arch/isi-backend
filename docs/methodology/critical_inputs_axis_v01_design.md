# ISI Axis 5 — Critical Inputs / Raw Materials Dependency

## Methodology Design Memo

Status: DESIGN PHASE — NOT IMPLEMENTED
Date: 2026-02-07
Axis: Critical Inputs / Raw Materials Dependency (Axis 5)
Project: Panargus / International Sovereignty Index (ISI)

---

## 1. What Axis 5 Measures

Axis 5 measures the degree to which an EU-27 country's imports of
**critical raw materials** are concentrated among a small number of
foreign supplier countries — at both the aggregate level and the
level of individual material groups.

The sovereignty question it answers:

> If a dominant supplier of a critical material were to deny,
> restrict, or disrupt supply to country i, how structurally
> exposed is country i to that disruption?

This is a **structural position measurement**. It captures
concentration of supply, not stockpile adequacy, recycling
capacity, or substitutability. Those are distinct dimensions
of resilience that Axis 5 does not claim to measure.

The unit of analysis is a country (not the EU as a bloc).
A country that imports 100% of its lithium from a single
EU partner is dependent — the fact that the partner is
European does not eliminate the chokepoint.

---

## 2. What Axis 5 Does NOT Measure

Critical Inputs Dependency in ISI terms is **NOT**:

- **Domestic extraction or production capacity.** A country that
  mines its own cobalt has lower real vulnerability, but Axis 5
  measures only the import-side concentration. Domestic production
  would require a separate data source and a different channel
  design (out of scope for v0.1).

- **Processing-stage dependency.** China dominates mid-stream
  processing (refining, smelting) for many critical materials even
  when it is not the ore-stage origin. Trade data records the
  shipping country and the HS code of the traded product — it does
  not reveal whether the product was mined domestically by the
  shipper or imported as ore and refined. This is the same
  "re-export blindness" limitation present in Axes 1 and 4.

- **Stockpile or strategic reserve adequacy.** A country with a
  90-day lithium reserve is less immediately vulnerable than one
  with zero reserves, but reserve data is not bilateral trade data
  and cannot be captured by the HHI methodology.

- **Substitutability or demand-side elasticity.** Some materials
  have substitutes (e.g., cobalt can partially be replaced in
  battery cathodes); others do not (e.g., there is no substitute
  for gallium in certain semiconductor applications). Axis 5 does
  not model substitution — it treats each material group as an
  irreducible category.

- **Environmental or labor governance of supply chains.** Axis 5
  does not distinguish between "responsible" and "irresponsible"
  sourcing.

- **A policy recommendation or regime judgment.** Dependency on
  China is not treated differently from dependency on Canada. The
  score is origin-agnostic.

---

## 3. Where Dependency Arises

Dependency in critical raw materials can originate from several
structurally distinct mechanisms. The channel design must decide
which of these to capture.

### 3.1 Supplier country concentration (import-side)

The most direct analog to Axes 1, 3, and 4. For each country i,
measure how concentrated its imports of critical material group k
are across supplier countries j.

This is observable from bilateral trade data at the HS code level.
It is the strongest candidate for Channel A.

**Strengths:** Directly measurable. Consistent with ISI methodology.
Bilateral trade data exists (Eurostat Comext, UN Comtrade).

**Weaknesses:** Re-export blindness. A country importing "refined
cobalt" from Belgium may actually be importing Congolese cobalt
processed in Belgian refineries. The trade data sees Belgium as
the supplier. This is a known limitation accepted in Axes 1 and 4.

### 3.2 Material-group-weighted concentration

Analogous to Channel B in Axes 3 and 4. Not all critical materials
carry equal strategic weight. Rare earth elements used in defense
applications may warrant higher implicit weight than construction
aggregates. Volume-weighting by trade value provides one natural
weighting scheme (larger import bills → higher weight), but it
conflates price with strategic importance.

This is a strong candidate for Channel B — per-material-group HHI,
volume-weighted across groups.

**Strengths:** Captures the intuition that concentration in lithium
matters more than concentration in feldspar. Consistent with
Channel B patterns in other axes.

**Weaknesses:** Volume-weighting by EUR value biases toward
expensive materials. A small-volume but irreplaceable material
(gallium, germanium) may be underweighted relative to a large-volume
but substitutable material (copper). This is a design trade-off,
not a fatal flaw — the same issue exists in Axis 4 where ICs
dominate by value.

### 3.3 Processing-stage chokepoint concentration

This is the conceptually richest but most data-demanding channel.
Many critical materials have a supply chain with at least three
stages: (1) mining/extraction, (2) refining/processing, (3)
finished material/alloy. Concentration can differ dramatically
across stages. For example, the Democratic Republic of Congo
dominates cobalt mining, but China dominates cobalt refining.

Capturing this would require either:
- Trade data at multiple HS code levels (ores vs. refined products)
  for the same material group, which may be feasible
- Non-trade data (USGS, BGS, or OECD production statistics), which
  would introduce a methodological asymmetry with other axes

This is a candidate for Channel C or a v0.2 extension. It should
NOT be included in v0.1 unless the data is bilateral, country-level,
and available in bulk.

---

## 4. Candidate Channel Structures

### Option A: Two-channel (consistent with Axes 3 and 4)

| Channel | Definition |
|---|---|
| A | Aggregate supplier concentration: HHI across all critical materials combined |
| B | Material-group-weighted concentration: per-group HHI, volume-weighted |

**Pros:** Exact structural analog to Axes 3 and 4. Same formula,
same aggregation, same interpretation. Minimizes methodological
complexity. Data requirements are identical to Axis 4 (bilateral
trade data, one product-group mapping).

**Cons:** Does not capture processing-stage dynamics. Volume-weighting
may underweight strategically critical but low-value materials.

**Assessment:** Recommended for v0.1.

### Option B: Three-channel (adds ore vs. refined distinction)

| Channel | Definition |
|---|---|
| A | Aggregate supplier concentration across all HS codes |
| B | Material-group-weighted concentration |
| C | Processing-stage concentration: separate HHI for ore-stage and refined-stage HS codes within each material group |

**Pros:** Captures the most strategically relevant dimension — who
controls the refining bottleneck, not just who ships the final
product. Would be the most analytically powerful structure.

**Cons:** Requires mapping each material group to both ore-stage
and refined-stage HS codes. Some material groups may not have a
clean ore/refined split at the HS code level. Increases data
preparation complexity substantially. The bilateral trade data
may not reliably distinguish processing stages (e.g., "unwrought
cobalt" includes both matte from DRC and refined metal from Finland).

**Assessment:** Conceptually superior. Likely infeasible for v0.1
due to HS code mapping complexity. Strong candidate for v0.2.

### Option C: Single-channel (minimal viable)

| Channel | Definition |
|---|---|
| A | Aggregate supplier concentration across all critical materials combined |

**Pros:** Simplest possible structure. One HHI per country.

**Cons:** Loses all material-group resolution. A country that is
diversified in copper but completely dependent on one supplier for
rare earths would show a moderate aggregate score, masking the
critical vulnerability. This is the same problem that motivates
Channel B in Axes 3 and 4.

**Assessment:** Insufficient. The material-group dimension is too
important to collapse.

---

## 5. Biggest Conceptual Traps

### Trap 1: Product scope definition — what counts as "critical"?

This is the most dangerous design decision. The EU Critical Raw
Materials Act (CRMA, 2024) defines 34 critical raw materials and
17 strategic raw materials. But:

- The CRMA list is a political/regulatory artifact, not an
  analytical one. It changes over time.
- Not all CRMA-listed materials are equally relevant to
  sovereignty. Bauxite is critical for aluminum but abundantly
  available from many sources. Gallium is critical for
  semiconductors and overwhelmingly sourced from China.
- Using the full CRMA list risks including materials where no
  EU country has meaningful import concentration (diluting scores).
- Excluding materials risks omitting genuine vulnerabilities.

**Mitigation:** The product scope must be defined by an explicit,
versioned mapping table (analogous to Axis 4's CN8 → category
mapping). The mapping should be based on HS codes that correspond
to CRMA-listed materials, but the ISI is not bound by the CRMA
list. The mapping table is the authoritative scope definition,
not the CRMA regulation.

### Trap 2: HS code contamination (the solar PV problem again)

HS codes for raw materials are notoriously overloaded. For example:

- HS 2611 (tungsten ores) is clean — it maps to a single material.
- HS 2825 (hydrazine, hydroxylamine, and their inorganic salts)
  includes lithium hydroxide but also other compounds. Using the
  full 4-digit HS code would contaminate lithium scores with
  non-lithium trade.
- HS 8112 (beryllium, chromium, germanium, vanadium, gallium,
  hafnium, indium, niobium, rhenium, thallium, and articles
  thereof) bundles multiple critical materials into a single code.

This is the exact analog of the HS 8541 solar PV contamination
that required CN8-level correction in Axis 4.

**Mitigation:** CN8-level (or at minimum HS6-level) product codes
are mandatory. HS4-level aggregation is not acceptable for Axis 5.
Every material-group-to-HS-code mapping must be validated for
semantic purity before data ingestion.

### Trap 3: Volume vs. value weighting

Critical raw materials span orders of magnitude in unit value.
Rare earth elements trade at EUR hundreds per kilogram; iron ore
trades at EUR cents per kilogram. If Channel B is value-weighted,
high-value materials dominate. If volume-weighted (by mass or
quantity), bulk commodities dominate. Neither is objectively correct.

**Mitigation:** This is a design choice, not an error. The choice
must be stated explicitly and defended. Value-weighting is
consistent with Axes 1, 3, and 4. Mass-weighting would be a
methodological departure. The decision should be made during
data inspection, not during design.

### Trap 4: Country-of-origin vs. country-of-shipment

This is the re-export blindness problem, but it is more severe
for raw materials than for semiconductors or energy. Major
European commodity trading hubs (Netherlands, Belgium, Germany)
re-export significant volumes of materials they did not mine or
refine. A country importing "cobalt" from the Netherlands may
actually be importing Congolese cobalt transshipped via Rotterdam.

Unlike Axis 4, where re-export blindness is a MEDIUM-severity
warning, it is potentially HIGH severity for Axis 5 because the
entire value proposition of the axis — "who actually controls
your supply?" — is undermined if the data cannot distinguish
origin from transit.

**Mitigation:** This cannot be fully resolved with bilateral trade
data. It must be documented as a known limitation. If available,
Eurostat's supplementary "country of origin" statistics (as
opposed to "country of consignment") could be explored — but
this is a data investigation question, not a design question.

### Trap 5: Conflating materials and products

Critical raw materials exist at multiple stages: ore, concentrate,
oxide, metal, alloy, manufactured component. A country that imports
raw lithium ore and processes it domestically is in a different
sovereignty position from a country that imports lithium-ion battery
cells. Axis 5 must define a clear cut-off: does it measure
dependency on the raw material, the intermediate product, or the
finished good?

**Mitigation:** Axis 5 should measure dependency at the raw and
intermediate material stages only — not at the finished-product
level. Finished products (batteries, magnets, catalysts) are
downstream applications that belong to sector-specific axes (Axis 4
already covers semiconductor finished goods). The HS code mapping
must enforce this boundary.

---

## 6. Scope and Constraint Summary

| Parameter | Value |
|---|---|
| Scope | EU-27 |
| Unit of analysis | Individual countries |
| Score range | [0, 1] |
| Concentration metric | HHI |
| Intra-EU dependency | Counts as real dependency |
| Data format | Bulk/statistical CSV; no APIs preferred |
| Ideology | None — origin-agnostic |
| Domestic production | Not captured (import-side only) |
| Processing stage | Not captured in v0.1 (potential v0.2 Channel C) |
| Stockpiles/reserves | Not captured |
| Substitutability | Not captured |

---

## 7. GO / NO-GO Decision

### **GO.**

Axis 5 is conceptually viable. The core measurement — bilateral
import supplier concentration for critical raw materials, per
EU-27 country — is structurally identical to what has already been
validated in Axes 1, 3, and 4. The HHI methodology, channel
architecture, and aggregation formula all transfer directly.

The primary risks are:

1. **HS code contamination** — manageable with CN8-level codes
   and explicit mapping validation (proven approach from Axis 4).
2. **Re-export blindness** — inherent to bilateral trade data;
   documented as a known limitation in all prior axes.
3. **Product scope definition** — requires careful HS code mapping
   with hostile validation; not a conceptual barrier.

None of these risks are fatal. All have precedent mitigations
within the existing ISI framework.

---

## 8. Next Concrete Steps

1. **Define the material-group scope.** Produce a candidate list
   of critical raw material groups for v0.1, cross-referenced
   against the EU CRMA list but not bound by it. Each group must
   have a clear sovereignty rationale (not just "it's on the list").

2. **Identify candidate HS codes.** For each material group, map
   to CN8-level (or HS6 minimum) product codes in Eurostat Comext.
   Flag codes that bundle multiple materials (Trap 2). This is
   the highest-risk step.

3. **Verify data availability.** Download a sample Eurostat Comext
   extraction for the candidate HS codes. Confirm bilateral
   partner-level data exists, has adequate country coverage
   (27/27 EU reporters), and has plausible value/volume
   distributions. Identify missing data or anomalies.

4. **Select channel structure.** Based on data inspection, choose
   between Option A (two-channel) and Option B (three-channel).
   Option A is the default unless ore/refined HS code splits are
   confirmed to be clean.

5. **Produce the material-group → HS code → category mapping
   table** as a machine-readable artifact, analogous to Axis 4's
   `tech_cn8_category_mapping_v01.csv`. This is the authoritative
   scope definition for Axis 5.

6. **Write the formal v0.1 methodology document** before any
   implementation begins. Submit for hostile review.
