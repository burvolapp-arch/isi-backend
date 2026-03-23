# ISI Theoretical Readiness & Country Eligibility

> **Epistemic status**: THEORETICAL — derived from internal rules, data
> architecture profile, and governance thresholds. NOT externally validated.
>
> **Last updated**: Audit-grade hardening pass (Tasks 1.1–1.10).

---

## 1. What This Module Does

`backend/eligibility.py` answers **four distinct questions** per country:

| # | Question | Meaning | Requires |
|---|----------|---------|----------|
| 1 | **Can compile?** | Pipeline can ingest data and produce axis scores | Source coverage ≥ 4 axes |
| 2 | **Can rate?** | Governance model produces a defensible tier | Compile + governance tier ≠ NON_COMPARABLE |
| 3 | **Can rank?** | Country can appear in ordinal rankings | Rate + ranking_eligible + ≥5 axes + confidence ≥ threshold |
| 4 | **Can compare?** | Cross-country pairwise comparison is defensible | Rank + cross_country_comparable + ≤ max inversions |

**These are NOT the same question.** Conflating "computable" with "defensibly
rankable" is a methodological error the ISI system explicitly refuses to make.

## 2. Eligibility Classes

```
COMPARABLE_WITHIN_MODEL   → Can compare cross-country
    ↑
RANKABLE_WITHIN_MODEL     → Can appear in ordinal rankings
    ↑
RATEABLE_WITHIN_MODEL     → Can receive a governance-backed tier
    ↑
COMPILE_READY             → Pipeline can produce scores
    ↑
COMPUTABLE_BUT_NOT_DEFENSIBLE → Scores exist, governance refuses ranking
    ↑
NOT_READY                 → Pipeline cannot produce scores
```

**"WITHIN_MODEL" suffix**: These classifications reflect the system's
internal rules, not external validation. See §6 below.

## 3. Axis-by-Country Readiness Levels

Each country × axis pair is assessed independently. Readiness levels
are **ordered from best to worst**:

| Level | Meaning | Example |
|-------|---------|---------|
| `SOURCE_CONFIDENT` | Primary source exists with good coverage and no structural distortions | IT axis 2 (energy via Comtrade) |
| `SOURCE_USABLE` | Source exists but with known limitations (single channel, granularity loss, TIV lumpiness) | JP axis 3 (tech — HS6 only, no CN8) |
| `PROXY_USED` | A proxy source stands in for the primary — measures a related but different construct | — |
| `CONSTRUCT_SUBSTITUTION` | Measurement construct is fundamentally different from what the axis label claims | JP axis 6 (trade value proxy for logistics) |
| `NOT_AVAILABLE` | No source covers this country + axis | RU axis 1 (not in BIS/CPIS) |

These levels are defined in `ReadinessLevel` and enforced by
`_assess_axis_readiness()` with explicit `rule_id` provenance
(pattern: `ELIG-RDN-{axis}-{issue}`).

### Per-Axis Source Profile (`AXIS_SOURCE_PROFILE`)

Every axis has a profile that states:
- **primary_sources**: What data sources feed this axis
- **construct**: What the axis actually computes
- **what_it_measures**: Plain-text scope of measurement
- **what_it_does_NOT_measure**: Explicit exclusions (audit-grade)
- **rule_id**: Provenance (`ELIG-SRC-001` through `ELIG-SRC-006`)

| Axis | Source | Construct Summary | EU vs Non-EU Difference |
|------|--------|-------------------|------------------------|
| 1 — Financial | BIS LBS + IMF CPIS | Cross-border banking + portfolio concentration | CN: CPIS absent → single-channel degradation |
| 2 — Energy | UN Comtrade | Energy commodity import concentration (HS 27xx) | None — same source, same granularity |
| 3 — Technology | UN Comtrade | Semiconductor goods import concentration (HS 8541/8542) | **EU: CN8 subcategories (SOURCE_CONFIDENT)**; **Non-EU: HS6 only (SOURCE_USABLE)** |
| 4 — Defense | SIPRI TIV | Major conventional weapons transfer concentration | None — but TIV is inherently lumpy (always SOURCE_USABLE) |
| 5 — Critical Inputs | UN Comtrade | Critical raw material import concentration (rare earths, lithium, etc.) | None — same source, same granularity |
| 6 — Logistics | Eurostat (EU) / Comtrade proxy (non-EU) | EU: physical logistics flows. **Non-EU: CONSTRUCT SUBSTITUTION** — trade value proxy, NOT logistics | **CRITICAL difference** — see §4 |

**Axes 2, 3, and 5 all use Comtrade but have DIFFERENT constructs.**
They differ in HS code scope, granularity, and what they claim to measure.
Collapsing them as "same as energy" is a methodological error.

## 4. Construct Substitution — The Logistics Problem

> The old `LOGISTICS_GAP` category has been renamed to
> `CONSTRUCT_SUBSTITUTION` because it is NOT a "gap" that can be
> filled — it is the use of a fundamentally different measurement
> construct.

**For EU-27 countries:**
Axis 6 uses Eurostat bilateral modal freight data — port throughput,
rail freight tonnage, air cargo by partner. This measures actual
logistics infrastructure dependency. Readiness: `SOURCE_CONFIDENT`.

**For non-EU countries (US, JP, AU, BR, IN, etc.):**
No bilateral logistics source exists. The system uses Comtrade bilateral
**trade value** as a proxy. This is the **same underlying data** as
axes 2, 3, and 5. The axis label says "logistics" but the measurement
is "goods trade." Port throughput, freight tonnage, and modal shares
are what the concept requires; trade value is what is available.

This distinction is surfaced in:
- `classify_country()` → `logistics_construct_substitution: True/False`
- `build_eligibility_explanation()` → per-axis `construct_substitution` flag
- `AXIS_SOURCE_PROFILE[6]["eu_vs_non_eu_warning"]`

**Why this matters:** A reviewer who sees "logistics axis score = 0.73"
for Japan must understand that this number reflects bilateral trade value
concentration, NOT logistics capacity concentration. The two are related
but not equivalent.

## 5. Weakness Categories

Every blocker is categorized:

| Type | Description |
|------|-------------|
| `DATA_AVAILABILITY` | Source not available for this country |
| `STRUCTURAL_METHODOLOGY` | Construct inapplicable (e.g., producer inversion) |
| `PRODUCER_INVERSION` | Major exporter — import concentration is misleading |
| `CONSTRUCT_SUBSTITUTION` | Proxy uses a fundamentally different measurement construct |
| `CONFIDENCE_DEGRADATION` | Low axis confidence degrades composite |
| `COMPARABILITY_FAILURE` | Governance rules reject cross-country comparison |
| `THRESHOLD_FRAGILITY` | Classification sensitive to small threshold changes |
| `SANCTIONS_DISTORTION` | Post-2022 data structurally unreliable |

## 6. Theoretical vs. Empirical — The Central Distinction

> **"Theoretical readiness" does NOT mean "empirically validated."**

| Claim the system MAKES | Claim the system does NOT make |
|------------------------|-------------------------------|
| "Our rules would permit a rating for country X" | "The rating for X is correct" |
| "X meets the threshold for ranking eligibility" | "The ranking of X is meaningful" |
| "X and Y are in the same governance tier" | "X and Y are comparable in reality" |
| "This classification is stable under perturbation" | "This classification is externally validated" |

All thresholds governing eligibility are **HEURISTIC** or
**STRUCTURAL_NORMATIVE** (see `backend/calibration.py`). None have been
calibrated against external quality benchmarks.

## 7. Rule Provenance

Every classification, blocker, and readiness assessment carries an
explicit `rule_id` for audit traceability:

| Pattern | Scope | Examples |
|---------|-------|---------|
| `ELIG-SRC-NNN` | Per-axis source profile | `ELIG-SRC-001` (financial), `ELIG-SRC-006` (logistics) |
| `ELIG-RDN-{ax}-{type}` | Per-axis readiness issue | `ELIG-RDN-3-HS6`, `ELIG-RDN-6-CONSTSUB`, `ELIG-RDN-4-LUMP` |
| `ELIG-Q{n}-NNN` | Eligibility question blocker | `ELIG-Q1-001` (insufficient axes), `ELIG-Q2-003` (sanctions) |
| `ELIG-Q{n}` | Question-level provenance | `ELIG-Q1` (can compile?), `ELIG-Q4` (can compare?) |

## 8. Data Architecture Profile

Static source coverage (not runtime file checks):

| Source Set | Countries | Used By |
|-----------|-----------|---------|
| `BIS_REPORTERS` | EU-27 + AU, GB, JP, KR, NO, US, ZA, CN (partial) | Axis 1 |
| `CPIS_PARTICIPANTS` | EU-27 + AU, BR, GB, IN, JP, KR, NO, SA, US, ZA | Axis 1 |
| `COMTRADE_REPORTERS` | EU-27 + AU, BR, CN, GB, IN, JP, KR, NO, SA, US, ZA, RU* | Axes 2, 3, 5 |
| `SIPRI_LIKELY_IMPORTERS` | EU-27 + AU, BR, CN, GB, IN, JP, KR, NO, SA, US, ZA, RU* | Axis 4 |
| `EUROSTAT_LOGISTICS_COUNTRIES` | EU-27 only | Axis 6 (genuine logistics) |

\* RU data exists but is sanctions-distorted post-2022.

**Note:** RU is NOT in `BIS_REPORTERS` or `CPIS_PARTICIPANTS` → axis 1
readiness = `NOT_AVAILABLE`.

## 9. Sensitivity Analysis

`run_eligibility_sensitivity()` perturbs key thresholds by ±N% and reports:

- **Stable countries**: Classification unchanged under perturbation
- **Fragile countries**: Classification flips under small threshold changes

Perturbed thresholds:
- Confidence baselines (±N%)
- MIN_MEAN_CONFIDENCE_FOR_RANKING (±N%)
- MAX_INVERTED_AXES_FOR_COMPARABLE (±1)
- MIN_AXES_FOR_RANKING (±1)

Fragile countries should be presented with explicit threshold-sensitivity
warnings. Their eligibility is a boundary artifact of heuristic choices.

## 10. Country-Specific Notes

### Russia (RU)
- **Eligibility**: `COMPUTABLE_BUT_NOT_DEFENSIBLE`
- Axes 2–6: data exists but sanctions-distorted (post-2022)
- Axis 1: `NOT_AVAILABLE` (not a BIS reporter or CPIS participant)
- **NEVER rateable** under current governance rules

### United States (US)
- **Eligibility**: `RATEABLE_WITHIN_MODEL` (not rankable/comparable)
- 3 producer inversions (energy, defense, critical inputs)
- Axis 6: `CONSTRUCT_SUBSTITUTION` (trade value proxy)
- Import concentration is structurally misleading for major exporters

### Japan / Australia / Brazil / etc. (non-EU Comtrade reporters)
- **Eligibility**: varies by inversion count
- Axis 3 (technology): `SOURCE_USABLE` — HS6 only, no CN8 granularity
- Axis 4 (defense): `SOURCE_USABLE` — TIV lumpiness (universal)
- Axis 6 (logistics): `CONSTRUCT_SUBSTITUTION` — trade value proxy

### Clean EU Countries (IT, ES, NL, PL, etc.)
- **Eligibility**: `COMPARABLE_WITHIN_MODEL` or `RANKABLE_WITHIN_MODEL`
- No structural inversions, all axes available
- Axis 3: `SOURCE_CONFIDENT` (CN8 from Eurostat)
- Axis 6: `SOURCE_CONFIDENT` (genuine Eurostat logistics)

### France / Germany (FR, DE)
- Defense axis inversion (major arms exporters)
- Single inversion does not block ranking but adds caveat
- Axis 4: `CONSTRUCT_SUBSTITUTION` (inversion overrides TIV lumpiness)

## 11. Export Propagation

- **`build_isi_json()`**: `governance_tier`, `ranking_eligible`,
  `cross_country_comparable` per country
- **`build_country_json()`**: full governance metadata
- **`gate_export()`**: suppresses ranking for NON_COMPARABLE countries
- **API `/isi`**: inherits per-country governance fields
- **API `/country/{code}`**: full governance detail

## 12. What This Module Does NOT Do

- Does NOT modify scores
- Does NOT claim empirical validation
- Does NOT override governance rules
- Does NOT predict real-world strategic vulnerability
- Does NOT substitute for external peer review

## 13. Files

| File | Role |
|------|------|
| `backend/eligibility.py` | Core eligibility model (1660 lines) |
| `tests/test_eligibility_hardening.py` | 104 tests covering eligibility + readiness registry |
| `backend/governance.py` | Governance tier rules (upstream) |
| `backend/calibration.py` | Calibration registry (upstream) |
| `backend/export_snapshot.py` | Export with governance propagation |
| `docs/THEORETICAL_READINESS.md` | This document |
