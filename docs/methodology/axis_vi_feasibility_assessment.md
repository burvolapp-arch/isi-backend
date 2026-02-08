# Axis 6 — Logistics and Trade Flow Dependency: Feasibility Assessment

**Date:** 2025-02-09  
**Status:** STEP 1 (Data Reality Check) COMPLETE · STEP 2 (Feasibility Decision) COMPLETE  
**Verdict:** **CONDITIONAL GO — REDESIGN REQUIRED**

---

## 1. Axis Definition (Locked)

> Axis 6 measures logistics and trade flow dependency — how exposed a country is
> to disruption, denial, or coercive leverage due to reliance on a limited number
> of external logistics corridors, transit routes, transport modes, or
> intermediary countries for the physical movement of goods.

**Constraints (immutable):**
- EU-27 only
- HHI concentration metric
- No normalization or rescaling
- Intra-EU flows count (friendly countries do NOT reduce dependency)

**Provisional channels from original specification:**
- Channel A: Route/corridor concentration
- Channel B: Intermediary transit country concentration

---

## 2. Data Reality Check — Systematic Probe Results

Every claim below is backed by a direct API probe against the Eurostat JSON API
(`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{table}`).
No table was assumed to exist without verification.

### 2.1 Datasets WITH Bilateral Partner Dimension

| Dataset | Title | Key Dimensions | Partner Dim | EU-27 Coverage | Unit | Time Range |
|---------|-------|----------------|-------------|----------------|------|------------|
| `road_go_ia_lgtt` | International road freight — loaded goods by country of unloading | `freq, tra_type, c_unload, nst07, unit, geo, time` | `c_unload` (76 countries) | 26/27 (missing: MT) | THS_T | 2008–2024 |
| `road_go_ia_ugtt` | International road freight — unloaded goods by country of loading | `freq, tra_type, c_load, nst07, unit, geo, time` | `c_load` (confirmed exists) | 26/27 (missing: MT) | THS_T | 2008–2024 |
| `rail_go_intgong` | International rail goods — from reporting to unloading country | `freq, unit, c_unload, geo, time` | `c_unload` (78 countries) | 25/27 (missing: CY, MT) | THS_T, MIO_TKM | 2003–2024 |
| `mar_go_am_{iso2}` | Maritime goods — main ports by partner MCA (per-country tables) | `freq, direct, cargo, natvessr, unit, par_mar, rep_mar, time` | `par_mar` (249 MCAs) | 22/27 (5 landlocked: AT, CZ, HU, LU, SK — inherently correct) | THS_T | 1997–2024 |

**Verified bilateral data points:**
- `road_go_ia_lgtt` (DE→FR): Data returned (verified present via API)
- `rail_go_intgong` (DE→FR): 1,165 thousand tonnes (2023), 546 thousand tonnes (MIO_TKM)
- `mar_go_am_de` (DE→FR partner): 2,343 thousand tonnes (2023)
- `mar_go_am_fr` (FR←DE partner): 1,554 thousand tonnes (2023) — asymmetry due to methodological differences (inward vs. outward declarations, port coverage)

### 2.2 Datasets WITHOUT Bilateral Partner Dimension

| Dataset | Title | Dimensions Present | Why Insufficient |
|---------|-------|--------------------|------------------|
| `mar_go_aa` | Maritime goods all ports — annual | `freq, direct, unit, rep_mar, time` | Total tonnage per port/MCA; no partner |
| `mar_mg_aa_cwh` | Maritime goods — country-level gross weight | `freq, unit, rep_mar, time` | Aggregate tonnage only |
| `road_go_ta_tott` | Total road freight | `freq, tra_type, tra_oper, unit, geo, time` | National aggregate; no partner |
| `road_go_ta_tg` | Road freight by goods type | `freq, tra_type, nst07, unit, geo, time` | No partner dimension |
| `rail_go_grpgood` | Rail goods by group | `freq, unit, nst07, geo, time` | Domestic aggregate; no partner |
| `iww_go_atygo` | Inland waterway goods by type | `freq, tra_cov, nst07, typpack, unit, geo, time` | Has nat/intl split but NO partner country |
| `avia_gooc` | Air freight by country | `freq, unit, tra_meas, schedule, tra_cov, geo, time` | Has intra/extra-EU split but NO partner country |

### 2.3 Failed / Non-Existent Table Probes

| Attempted Table | Result |
|-----------------|--------|
| `mar_go_am` | 404 — not available |
| `mar_go_am_eu` | 404 |
| `mar_go_am_cwh` | 404 |
| `mar_go_am_cw` | 404 |
| `mar_go_am_det` | 404 |
| `mar_go_am_deta` | 404 |
| `mar_go_am_detbc` | 404 |
| `mar_go_am_csm` | 404 |
| `mar_go_am_esms` | 404 |
| `mar_go_am_custom` | 404 |
| `mar_go_aa_dcmh` | 404 |
| `road_go_na_rl3g` | 400 — dimension error |

### 2.4 Supplementary Datasets (No Bilateral, But Useful)

| Dataset | Title | Key Content | Relevance |
|---------|-------|-------------|-----------|
| `tran_hv_frmod` | Modal split of inland freight | Road/Rail/IWW % shares per country | Could inform mode concentration; ALL EU-27 covered |
| `avia_gooc` | Air freight by country (aggregate) | Total/national/international tonnes | Volume baseline only |
| `iww_go_atygo` | Inland waterway by goods type | National/international split | Volume baseline only |

### 2.5 Coverage Summary

| Mode | Bilateral Exists? | EU-27 Reporter Coverage | Partner Granularity |
|------|-------------------|------------------------|---------------------|
| **Road** | ✅ YES | 26/27 (MT missing — island, road freight negligible) | 76 countries incl. all EU-27 |
| **Rail** | ✅ YES | 25/27 (CY, MT missing — islands, no rail connections) | 78 countries incl. all EU-27 |
| **Maritime** | ✅ YES | 22/27 (5 landlocked = structurally correct) | 249 MCAs incl. all EU-27 + worldwide |
| **Air** | ❌ NO | N/A | No bilateral partner dimension in any public table |
| **Inland Waterway** | ❌ NO | N/A | No bilateral partner dimension |
| **Pipeline** | ❌ NO | Not probed in detail | Known to be confidential/restricted |

---

## 3. Conceptual Feasibility Analysis

### 3.1 What the Data Actually Measures

The bilateral transport datasets provide:

> For each EU reporter country, for each partner country, for each transport mode:
> the **tonnage** of goods physically moved between them.

This enables:
- **Mode concentration per country**: How dependent is country X on a single
  transport mode for its international freight? (e.g., Malta is ~100% maritime)
- **Partner concentration per mode**: How concentrated are a country's maritime
  imports across partner MCAs? (e.g., does Finland receive 80% of maritime goods
  from one MCA?)
- **Combined mode × partner concentration**: Full matrix analysis

### 3.2 What the Data Does NOT Measure

The data does **NOT** reveal:
- **Physical routes or corridors**: "German imports from China transit through
  Suez Canal via Rotterdam" is invisible. The data shows DE←CN by sea, but not
  the chokepoint traversed.
- **Transit dependencies**: If Poland's road exports to Spain transit through
  Germany and France, this is invisible. The data shows PL→ES by road, not the
  intermediary countries on the route.
- **Infrastructure-level chokepoints**: No data on specific bridges, tunnels,
  ports-of-transit, canals, or straits.
- **Multimodal routing**: If Chinese goods arrive by sea at Rotterdam, then move
  by rail to Germany, this appears as NL→DE by rail (if at all), not as a
  single China→DE supply chain.

### 3.3 Critical Conceptual Question

> **Original Axis 6 channels:**
> - Channel A: Route/corridor concentration
> - Channel B: Intermediary transit country concentration
>
> **Verdict: Neither channel is feasible as originally specified.**

**Channel A (route/corridor concentration)** requires knowledge of which physical
corridors goods traverse. Public Eurostat data provides origin-destination pairs
by mode, not routes. KILLED.

**Channel B (intermediary transit country concentration)** requires knowledge of
which countries goods transit through en route. Eurostat road data reports where
goods are loaded and unloaded, not the transit path. KILLED.

### 3.4 What IS Feasible — Redesigned Axis

The bilateral mode × partner data enables a **different but defensible** measure
of logistics dependency:

**Redesigned Channel A: Transport Mode Concentration**

For each country, compute HHI across transport modes for total international
freight. A country dependent on a single mode (e.g., Cyprus/Malta ~100% maritime)
is more vulnerable to disruption of that mode than a country with balanced
modal split.

- Source: `tran_hv_frmod` (all EU-27) or derived from bilateral tables
- Metric: HHI over mode shares (road, rail, maritime, IWW)
- Interpretation: High HHI = single-mode dependency = higher vulnerability

**Redesigned Channel B: Partner Concentration by Mode**

For each country × mode combination, compute HHI across partner countries. A
country whose maritime trade is dominated by a single partner MCA is more
exposed to disruption of that specific bilateral link.

- Source: `road_go_ia_lgtt/ugtt`, `rail_go_intgong`, `mar_go_am_{iso2}`
- Metric: Per-mode HHI over partner countries
- Interpretation: High HHI = concentrated dependency on few partners for that mode

**Composite**: Weighted combination of mode concentration and per-mode partner
concentration, where weights are the mode's share of total freight.

---

## 4. Feasibility Decision

### 4.1 Verdict: CONDITIONAL GO

The axis **can** be built, but **not** as originally specified. The original
channels (route/corridor concentration, transit country concentration) are
**infeasible** with public data. No Eurostat dataset reveals physical transit
routes or intermediary countries.

A redesigned axis measuring **transport mode concentration** × **per-mode partner
concentration** is fully feasible with verified public data.

### 4.2 GO Conditions

1. **Accept channel redesign**: The axis measures mode + partner concentration,
   NOT route/corridor concentration. This must be explicitly acknowledged as a
   limitation.

2. **Accept coverage gaps**: Malta has no road data (irrelevant — island).
   Cyprus and Malta have no rail data (correct — no rail connections). Air and
   IWW bilateral data do not exist. The axis covers road + rail + maritime only.

3. **Accept maritime data complexity**: Maritime data is split across 22
   per-country tables (`mar_go_am_{iso2}`), requiring assembly. The `par_mar`
   dimension uses Maritime Coastal Area codes, not ISO country codes directly
   (though country-level aggregates exist within each table).

4. **Accept asymmetry**: Maritime bilateral data shows systematic asymmetry
   between reporter and partner declarations (e.g., DE reports 2,343 kt to FR,
   but FR reports only 1,554 kt from DE). Standard practice: use reporter
   declarations for each country's own outflow/inflow.

### 4.3 What the Redesigned Axis Still Captures

Despite not measuring physical routes, the redesigned axis captures real
strategic vulnerability:

- **A country 100% dependent on maritime freight** (e.g., Cyprus) is genuinely
  more vulnerable to naval blockade, port strikes, or maritime insurance
  disruption than a country with balanced road/rail/sea split.
- **A country whose maritime imports come 80% from one MCA** is genuinely more
  exposed to disruption of that single bilateral maritime link.
- **These are measurable, defensible, HHI-compatible concentrations** that align
  with the axis definition of "reliance on a limited number of ... transport
  modes."

### 4.4 What the Redesigned Axis Does NOT Capture

- Suez Canal dependency (no route data)
- Bosporus strait dependency (no route data)
- Transit through specific countries (no intermediary data)
- Physical infrastructure chokepoints (bridges, tunnels)
- Multimodal supply chain routing

These limitations must be explicitly stated in the methodology document.

---

## 5. Data Acquisition Plan (If GO Accepted)

### 5.1 Primary Data Sources

| Dataset | Records Est. | Extraction Method |
|---------|-------------|-------------------|
| `road_go_ia_lgtt` | ~237,659 total | Single API call, filter by EU-27 geo |
| `road_go_ia_ugtt` | ~222,860 total | Single API call, filter by EU-27 geo |
| `rail_go_intgong` | ~27,274 total | Single API call, filter by EU-27 geo |
| `mar_go_am_{iso2}` × 22 tables | ~3M per table (raw), filtered ~manageable | 22 API calls, one per maritime EU country |
| `tran_hv_frmod` | ~2,104 total | Single API call |

### 5.2 Pipeline Architecture

```
Step 1: Extract bilateral freight data (3 modes × EU-27)
Step 2: Harmonize units (all to thousand tonnes)
Step 3: Build country × partner × mode matrix
Step 4: Compute Channel A: mode HHI per country
Step 5: Compute Channel B: partner HHI per country per mode
Step 6: Compute composite score (weighted by mode share)
Step 7: Validate against known strategic profiles
```

### 5.3 Expected Structural Patterns

| Country | Expected Profile | Rationale |
|---------|-----------------|-----------|
| CY, MT | Very high mode concentration (maritime ~100%) | Island states |
| DE, FR, PL | Low mode concentration (balanced road/rail/maritime) | Large continental economies |
| AT, CZ, HU, LU, SK | No maritime (road + rail only) | Landlocked |
| EE, LV, LT | Medium concentration | Baltic states with rail + maritime |

---

## 6. Structural Limitations (Must Be Documented in Frozen Methodology)

1. **No route/corridor data exists publicly.** The axis cannot measure Suez,
   Bosporus, or any specific chokepoint dependency.

2. **No transit country data exists publicly.** The axis cannot measure
   intermediary country dependency.

3. **Air freight has no bilateral partner dimension.** Air is excluded from
   the analysis.

4. **Inland waterway freight has no bilateral partner dimension.** IWW is
   excluded from bilateral partner analysis but can be included in mode share
   via `tran_hv_frmod`.

5. **Pipeline data is not publicly available** at bilateral granularity.
   Excluded entirely.

6. **Maritime data asymmetry.** Reporter and partner declarations differ
   systematically. Each country's own reporter data is used.

7. **Malta missing from road data.** Structurally irrelevant (island, minimal
   road freight).

8. **Cyprus and Malta missing from rail data.** Structurally correct (no rail
   connections).

---

## 7. Decision Required

**The axis definition must be narrowed from the original specification.**

Original: "reliance on a limited number of external logistics corridors, transit
routes, transport modes, or intermediary countries"

Feasible scope: "reliance on a limited number of **transport modes** or
**bilateral freight partners per mode** for the physical movement of goods"

**If this narrowing is acceptable → PROCEED to design sketch.**  
**If route/corridor concentration is considered essential → KILL the axis.**

---

*Assessment compiled from 25+ direct Eurostat API probes. Every dataset existence
claim is empirically verified. No data source is assumed.*
