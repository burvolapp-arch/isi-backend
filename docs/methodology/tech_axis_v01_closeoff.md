# ISI Axis 4 — Technology / Semiconductor Dependency

## Formal Close-Off Note — v0.1

**Date:** 2026-02-07
**Axis:** 4 — Technology / Semiconductor Dependency
**Index:** International Sovereignty Index (ISI)
**Status:** FROZEN

---

## 1. Acknowledgements

Methodology v0.1 for Axis 4 (Technology / Semiconductor Dependency) is the authoritative specification. It was written, reviewed, and validated prior to this close-off.

Implementation is complete. The full pipeline comprises five scripts executed in strict sequence:

1. `scripts/ingest_tech_comext_manual.py`
2. `scripts/parse_tech_comext_raw.py`
3. `scripts/compute_tech_channel_a.py`
4. `scripts/compute_tech_channel_b.py`
5. `scripts/aggregate_tech_cross_channel.py`

The pipeline has been executed end-to-end. All 27 EU member states are scored. All internal consistency checks pass.

Hostile validation has been performed and is documented in `docs/audit/tech_axis_v01_hostile_validation.md`. The validation covered solar PV contamination resolution, outlier analysis, category volume distributions, supplier concentration patterns, and defensive guard integrity.

---

## 2. Final Locked Parameters

| Parameter | Value |
|---|---|
| **Scope** | EU-27 |
| **Reference window** | 2022–2024 (aggregated to a single 2024-labelled score) |
| **Data source** | Eurostat Comext, dataset ds-045409, CN8-level, bilateral partner data |
| **Product scope** | HS 8541 (CN8 subcodes: 85411000, 85412100, 85412900, 85413000, 85416000, 85419000) and HS 8542 (HS4 aggregate) |
| **Structural exclusion** | CN 854140xx (solar photovoltaic cells) — absent from data; defensive parser guard enforces fatal abort if encountered |
| **Channel A** | Aggregate supplier country concentration via Herfindahl-Hirschman Index (HHI) across all product codes |
| **Channel B** | Category-weighted supplier concentration; HHI computed per category, then volume-weighted across three categories: `legacy_discrete`, `legacy_components`, `integrated_circuits` |
| **Aggregation** | Volume-weighted average of Channel A and Channel B concentrations |
| **Category mapping** | Persisted at `docs/audit/tech_cn8_category_mapping_v01.csv`; validated against hardcoded map at runtime |
| **Country code convention** | Eurostat GR mapped to EL for Greece |
| **Exclusions** | EU27_2020 aggregate reporter; self-pairs; zero/missing values; non-import flows |

---

## 3. Changes Since Initial Design

The following changes were made between initial design and final frozen implementation:

- **HS4 → CN8 migration.** The raw data source was changed from HS4-level (product codes `8541`, `8542`) to CN8-level (six 8-digit subcodes under HS 8541, plus HS4 aggregate `8542`). This was required to enable surgical exclusion of solar PV contamination.

- **Solar PV contamination eliminated structurally.** The CN8-level Eurostat download does not contain CN 854140xx (photovoltaic cells) or CN 854150xx (optoelectronic devices). The ~EUR 185B in solar PV and LED trade that silently inflated HS4-level HS 8541 values is no longer present. A defensive guard in both the ingest gate and the parser enforces a fatal abort if 854140xx appears in future data.

- **Category mapping refined.** The original two categories (`legacy`, `advanced`) were replaced with three explicit categories (`legacy_discrete`, `legacy_components`, `integrated_circuits`), each backed by a deterministic CN8 → category lookup table. The mapping is persisted as a machine-readable artifact and cross-validated at runtime.

No formulas were changed. No weights were changed. No conceptual changes were made.

---

## 4. What Was Not Changed

- **Mathematical structure.** HHI computation, share derivation, volume weighting, and cross-channel aggregation are identical to the initial design specification.

- **Channel logic.** Channel A computes aggregate supplier concentration. Channel B computes category-weighted supplier concentration. The cross-channel formula $T_i = (C_i^A \cdot W_i^A + C_i^B \cdot W_i^B) / (W_i^A + W_i^B)$ is unchanged.

- **Interpretation of the score.** A higher score indicates greater supplier concentration (higher dependency). The score is bounded to [0, 1].

- **Reference window.** 2022–2024, aggregated.

- **Country scope.** EU-27.

---

## 5. Final Outcome

Axis 4 passes validation with warnings. All warnings are non-fatal and documented:

| Warning | Severity | Status |
|---|---|---|
| W-1: Solar PV contamination | HIGH | **RESOLVED** |
| W-2: Re-export blindness | MEDIUM | Documented; inherent to bilateral trade data |
| W-3: Trade ≠ sovereignty | LOW | Documented; interpretive caveat |
| W-4: HS 8542 at HS4 aggregate | LOW | Documented; Eurostat data limitation |
| W-5: Intra-EU trade included | LOW | Documented; by design |
| W-6: Three-year aggregation window | LOW | Documented; period-average caveat |

27/27 EU member states scored. Both channels active for all 27. All internal bounds checks pass.

Final scores delivered in `data/processed/tech/tech_dependency_2024_eu27.csv`.
Full audit trail in `data/processed/tech/tech_dependency_2024_eu27_audit.csv`.

---

## 6. Freeze Declaration

Axis 4 (Technology / Semiconductor Dependency) v0.1 is formally frozen. No further methodological or data changes are permitted without a new version number.
