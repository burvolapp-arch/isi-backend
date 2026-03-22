# ISI — True Limitations

**Version**: Post–real-data integration hardening pass
**Date**: 2026-03
**Purpose**: Honest, complete enumeration of what ISI cannot do.
No marketing language. No hedging. No aspirational claims.

---

## 1. What ISI Measures

ISI is a **bilateral import concentration index**. For each country, it computes
HHI-based concentration scores across 6 axes (financial, energy, technology,
defense, critical inputs, logistics) and averages them into a composite.

**That is all it does.**

---

## 2. What ISI Does NOT Measure

| Claim ISI does NOT support | Why |
|---------------------------|-----|
| "Country X is strategically vulnerable" | Concentration is one dimension of vulnerability. Stockpiles, substitution capacity, alliances, and domestic production are not captured. |
| "Country X is more dependent than Country Y" | The composite mixes TIV (defense), USD (trade), and positions (financial). These are incommensurable units. |
| "Defense dependency is Z%" | SIPRI covers only major conventional weapons. Small arms, ammunition, services, cyber, and MRO are excluded. The defense score measures a partial slice. |
| "Country X should diversify" | ISI measures concentration, not whether concentration is harmful. Concentrated imports from a trusted ally may be optimal. |
| "ISI predicts supply chain disruption" | ISI is backward-looking (realized trade/deliveries), not predictive. |
| "Country X ranks #N in dependency" | Cross-country ranking is valid only within the same comparability tier. TIER_3 and TIER_4 countries MUST NOT be ranked alongside TIER_1 countries. |

---

## 3. Defense Axis — Specific Limitations

### 3.1 SIPRI Scope Is Partial
SIPRI Arms Transfers Database covers **major conventional weapons only**:
aircraft, armoured vehicles, artillery, air defence systems, anti-submarine
warfare weapons, engines, missiles, naval weapons, satellites, sensors/EW, ships.

**Excluded**: Small arms and light weapons (SALW), ammunition, dual-use
technology, military services/training, cyber capabilities, maintenance/repair,
black/grey market transfers.

For most countries, the excluded categories represent a **significant share**
of actual defense procurement spending. The defense axis measures platform-level
dependency, not total military supply chain exposure.

### 3.2 TIV Is Not Money
SIPRI's Trend Indicator Value (TIV) is an index based on production cost of a
core set of weapons. It measures military **capability transferred**, not
financial cost.

- A $100M TIV delivery does NOT mean $100M was paid.
- TIV values across different weapon types are not directly comparable
  in financial terms.
- TIV cannot be compared to USD trade values on other ISI axes.

Every defense output carries `value_type=TIV_MN` and an explicit
`interpretation_note` warning against cross-axis comparison.

### 3.3 Procurement Is Lumpy
Arms procurement cycles are 5-20 years. A single fighter jet order worth
thousands of TIV units can dominate a 6-year delivery window. This means:

- Year-to-year defense scores are **highly volatile**
- A country's defense concentration can swing 30+ percentage points
  based on delivery timing, not policy change
- The 6-year window (2020-2025) smooths some lumpiness but cannot
  eliminate it for small importers

### 3.4 High Concentration Is Normal
Most countries import major weapons from 2-6 suppliers. Japan's ~95% US
share is normal within SIPRI scope — it reflects genuine supplier
concentration in the major weapons market, not a data quality issue.

The `check_defense_plausibility()` validation annotates (does not fail)
extreme concentration with SIPRI-specific context.

---

## 4. Cross-Axis Comparability

### 4.1 Incommensurable Value Types
| Axis | Value Type | Unit |
|------|-----------|------|
| Financial | Positions | USD millions (stock) |
| Energy | Trade flow | USD millions (annual) |
| Technology | Trade flow | USD millions (annual) |
| Defense | Capability transfer | TIV millions (rolling) |
| Critical Inputs | Trade flow | USD millions (annual) |
| Logistics | Physical flow | Mixed (tonnes, TEU, modal shares) |

The ISI composite averages HHI scores derived from these different
value types. While HHI normalizes to [0,1], the underlying distributions
have different statistical properties, coverage, and temporal semantics.

### 4.2 Different Temporal Windows
- Financial: point-in-time positions (quarterly/annual snapshot)
- Trade axes: annual calendar-year flows
- Defense: 6-year rolling delivery window
- Logistics: annual statistics

A composite that mixes these temporal scales is meaningful as a summary
but should not be over-interpreted for temporal trends.

### 4.3 Different Confidence Baselines
| Axis | Confidence Baseline | Reason |
|------|-------------------|--------|
| Energy | 0.80 | Good UN Comtrade coverage, standardized HS codes |
| Technology | 0.80 | Good coverage, narrow HS scope (8541/8542) |
| Financial | 0.75 | BIS (~30 reporters) + CPIS (~80 participants) |
| Critical Inputs | 0.75 | Good coverage but diverse HS scope |
| Logistics | 0.60 | Partial coverage, EU-centric data |
| Defense | 0.55 | Partial scope (major weapons only), lumpy data, TIV not monetary |

---

## 5. Data Source Coverage Gaps

| Source | Coverage Gap | Implication |
|--------|-------------|-------------|
| BIS LBS | ~30 reporting countries | Non-reporting countries invisible as partners |
| IMF CPIS | ~80 participants | Missing for most non-OECD countries |
| UN Comtrade | Mirror trade data | Reporting delays, classification inconsistencies |
| SIPRI | Major conventional weapons only | See Section 3 above |
| Eurostat | EU-27 only | Non-EU logistics axis → STRUCTURAL_LIMITATION |
| OECD Logistics | Limited country coverage | Many countries lack bilateral freight data |

---

## 6. Non-State Entity Policy

All non-sovereign entities are dropped from ISI computation:
- **Multinational organizations** (NATO, AU, UN): arms transfers TO
  NATO as an organization are invisible in any member state's score.
- **Armed non-state actors** (Hezbollah, Houthis, RSF): excluded entirely.
- **Unknown entities**: unresolvable SIPRI entries dropped.

This is a **policy choice**. ISI measures sovereign-to-sovereign bilateral
concentration. Arms flows involving non-state actors are a real phenomenon
that ISI does not capture.

---

## 7. Composite Methodology Boundaries

| Design Choice | Implication |
|--------------|-------------|
| Unweighted mean of 6 axes | No axis weighting by economic significance |
| 4-axis minimum for composite | Hard cutoff, not gradual degradation |
| HHI-based concentration | Sensitive to partner count; small N → high HHI |
| No supply chain depth | Only first-tier bilateral imports captured |
| Backward-looking | No predictive capability |

---

## 8. What Would Make ISI Better (Not Implemented)

These are genuine limitations that could be addressed with additional
data or methodology, but are NOT implemented in the current version:

1. **Weighted composite** — axis weights reflecting economic significance
2. **Supply chain mapping** — upstream dependencies beyond first-tier imports
3. **Substitution capacity** — domestic production and stockpile data
4. **Political risk overlay** — ally vs. rival distinction
5. **Small arms/ammunition data** — complementary defense data sources
6. **Services trade** — IT, consulting, and other knowledge-economy dependencies
7. **Time series analysis** — trend detection with structural break identification

None of these are promised. They are listed for intellectual honesty
about the gap between what ISI measures and what users might want it
to measure.
