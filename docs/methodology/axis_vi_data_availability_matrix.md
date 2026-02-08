# Axis 6 — Logistics / Freight Dependency: Data Availability Matrix

**Version:** 0.1  
**Date:** 2025-02-09  
**Status:** VERIFIED (all entries backed by direct Eurostat API probes)


## 1. Datasets WITH Bilateral Partner Dimension (Used in Pipeline)

| # | Dataset Code | Full Title | Partner Dimension | Partner Count | Unit | EU-27 Reporter Coverage | Missing Countries | Time Range | API Endpoint | Role |
|---|-------------|-----------|-------------------|---------------|------|------------------------|-------------------|------------|-------------|------|
| 1 | `road_go_ia_lgtt` | International road freight — loaded goods by country of unloading | `c_unload` | 76 countries | THS_T | 26/27 | MT | 2008–2024 | `.../data/road_go_ia_lgtt` | Ch.B — road partner conc. (outward) |
| 2 | `road_go_ia_ugtt` | International road freight — unloaded goods by country of loading | `c_load` | ~76 countries | THS_T | 26/27 | MT | 2008–2024 | `.../data/road_go_ia_ugtt` | Ch.B — road partner conc. (inward) |
| 3 | `rail_go_intgong` | International rail goods — from reporting to unloading country | `c_unload` | 78 countries | THS_T, MIO_TKM | 25/27 | CY, MT | 2003–2024 | `.../data/rail_go_intgong` | Ch.B — rail partner conc. |
| 4 | `mar_go_am_{iso2}` (×22 tables) | Maritime goods — main ports by partner MCA | `par_mar` | 249 MCAs | THS_T | 22/27 | AT, CZ, HU, LU, SK (landlocked) | 1997–2024 | `.../data/mar_go_am_{iso2}` | Ch.B — maritime partner conc. |
| 5 | `tran_hv_frmod` | Modal split of inland freight transport | N/A (modes: ROAD, RAIL, IWW) | N/A | PC (%) | 27/27 | None | varies | `.../data/tran_hv_frmod` | Ch.A — mode shares |

API base: `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/`


## 2. Verified Bilateral Data Points

These specific values were retrieved during feasibility probing to confirm
data availability and quality:

| Probe | Dataset | Reporter | Partner | Year | Value | Unit |
|-------|---------|----------|---------|------|-------|------|
| Road DE→FR | `road_go_ia_lgtt` | DE | FR | 2023 | confirmed present | THS_T |
| Rail DE→FR | `rail_go_intgong` | DE | FR | 2023 | 1,165 | THS_T |
| Rail DE→FR | `rail_go_intgong` | DE | FR | 2023 | 546 | MIO_TKM |
| Maritime DE→FR | `mar_go_am_de` | DE | FR | 2023 | 2,343 | THS_T |
| Maritime FR←DE | `mar_go_am_fr` | FR | DE | 2023 | 1,554 | THS_T |

The maritime asymmetry (DE reports 2,343 kt vs FR reports 1,554 kt) is
documented and expected. Each country's own reporter data is authoritative.


## 3. Datasets WITHOUT Bilateral Partner Dimension (Excluded from Pipeline)

| Dataset Code | Full Title | Dimensions Present | Why Excluded |
|-------------|-----------|-------------------|--------------|
| `mar_go_aa` | Maritime goods all ports — annual | freq, direct, unit, rep_mar, time | Total tonnage per port/MCA; no partner |
| `mar_mg_aa_cwh` | Maritime goods — country-level gross weight | freq, unit, rep_mar, time | Aggregate tonnage only |
| `road_go_ta_tott` | Total road freight | freq, tra_type, tra_oper, unit, geo, time | National aggregate; no partner |
| `road_go_ta_tg` | Road freight by goods type | freq, tra_type, nst07, unit, geo, time | No partner dimension |
| `rail_go_grpgood` | Rail goods by group of goods | freq, unit, nst07, geo, time | Domestic aggregate; no partner |
| `iww_go_atygo` | Inland waterway goods by type of goods | freq, tra_cov, nst07, typpack, unit, geo, time | Has national/international split but NO bilateral partner country |
| `avia_gooc` | Air freight by country | freq, unit, tra_meas, schedule, tra_cov, geo, time | Has intra/extra-EU split but NO bilateral partner country |


## 4. Failed / Non-Existent Table Probes

These table codes were probed during feasibility assessment and confirmed
to not exist in the Eurostat API:

| Attempted Table Code | HTTP Response | Notes |
|---------------------|---------------|-------|
| `mar_go_am` | 404 | No unified maritime bilateral table |
| `mar_go_am_eu` | 404 | |
| `mar_go_am_cwh` | 404 | |
| `mar_go_am_cw` | 404 | |
| `mar_go_am_det` | 404 | |
| `mar_go_am_deta` | 404 | |
| `mar_go_am_detbc` | 404 | |
| `mar_go_am_csm` | 404 | |
| `mar_go_am_esms` | 404 | |
| `mar_go_am_custom` | 404 | |
| `mar_go_aa_dcmh` | 404 | |
| `road_go_na_rl3g` | 400 | Dimension error |


## 5. EU-27 Coverage Matrix by Mode

✅ = bilateral data available, ❌ = no data (structurally correct), ⚠️ = missing (unexpected)

| Country | Road (`road_go_ia_lgtt/ugtt`) | Rail (`rail_go_intgong`) | Maritime (`mar_go_am_{iso2}`) | Modal Split (`tran_hv_frmod`) | Active Modes for Ch.B |
|---------|-----|------|----------|-------------|----------------------|
| AT | ✅ | ✅ | ❌ landlocked | ✅ | road, rail |
| BE | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| BG | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| CY | ✅ | ❌ no rail | ✅ | ✅ | road, maritime |
| CZ | ✅ | ✅ | ❌ landlocked | ✅ | road, rail |
| DE | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| DK | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| EE | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| EL | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| ES | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| FI | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| FR | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| HR | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| HU | ✅ | ✅ | ❌ landlocked | ✅ | road, rail |
| IE | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| IT | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| LT | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| LU | ✅ | ✅ | ❌ landlocked | ✅ | road, rail |
| LV | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| MT | ❌ island | ❌ no rail | ✅ | ✅ | maritime |
| NL | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| PL | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| PT | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| RO | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| SE | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| SI | ✅ | ✅ | ✅ | ✅ | road, rail, maritime |
| SK | ✅ | ✅ | ❌ landlocked | ✅ | road, rail |

**Summary:**
- Road: 26/27 (MT missing — structurally irrelevant)
- Rail: 25/27 (CY, MT missing — no rail connections)
- Maritime: 22/27 (AT, CZ, HU, LU, SK — landlocked)
- Modal split: 27/27 (complete)
- All 27 countries can be scored


## 6. Dimension Detail per Dataset

### 6.1 road_go_ia_lgtt

| Dimension | Values | Notes |
|-----------|--------|-------|
| `freq` | A (annual) | |
| `tra_type` | TOTAL, NST_INT, ... | Filter: use TOTAL or sum across types |
| `c_unload` | 76 country codes | Partner country where goods unloaded |
| `nst07` | TOTAL + commodity groups | Filter: use TOTAL |
| `unit` | THS_T | Thousand tonnes |
| `geo` | EU-27 reporters + others | Filter: EU-27 only |
| `time` | 2008–2024 | |

### 6.2 rail_go_intgong

| Dimension | Values | Notes |
|-----------|--------|-------|
| `freq` | A (annual) | |
| `unit` | THS_T, MIO_TKM | Use THS_T for consistency |
| `c_unload` | 78 country codes | Partner unloading country |
| `geo` | EU-27 reporters + others | Filter: EU-27 only |
| `time` | 2003–2024 | |

### 6.3 mar_go_am_{iso2}

| Dimension | Values | Notes |
|-----------|--------|-------|
| `freq` | A (annual) | |
| `direct` | INWARD, OUTWARD, TOTAL | Direction of freight |
| `cargo` | TOTAL + cargo types | Filter: use TOTAL |
| `natvessr` | TOTAL + vessel nationalities | Filter: use TOTAL |
| `unit` | THS_T | Thousand tonnes |
| `par_mar` | 249 Maritime Coastal Areas | Partner MCA; aggregate to country |
| `rep_mar` | Reporter's own MCAs | Can aggregate or use TOTAL |
| `time` | 1997–2024 | |

### 6.4 tran_hv_frmod

| Dimension | Values | Notes |
|-----------|--------|-------|
| `freq` | A (annual) | |
| `unit` | PC (percentage) | Modal share as percentage |
| `tra_mode` | ROAD, RAIL, IWW | Three inland modes |
| `geo` | All EU-27 | |
| `time` | varies | |


## 7. Data Quality Notes

1. **All claims in this matrix are empirically verified** through direct
   HTTP GET requests to the Eurostat JSON statistics API during the
   feasibility assessment phase.

2. **No dataset was assumed to exist without verification.** 12 table
   codes were probed and confirmed non-existent (Section 4).

3. **Maritime data requires 22 separate API calls** (one per maritime
   EU-27 country). There is no single unified maritime bilateral table.

4. **Maritime partner dimension uses MCA codes**, not ISO country codes.
   Country-level aggregation is required in the pipeline.

5. **Unit consistency**: Road and maritime use THS_T natively. Rail
   offers both THS_T and MIO_TKM; THS_T is selected for cross-mode
   consistency. Modal split (`tran_hv_frmod`) uses percentages.

6. **No authentication or API keys** are required for any dataset.


End of data availability matrix.
