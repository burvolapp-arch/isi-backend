# Axis 6 — Logistics / Freight Dependency: Hostile Validation Plan

**Version:** 0.1  
**Date:** 2025-02-09  
**Purpose:** Systematic adversarial validation to identify weaknesses,
edge cases, and potential failure modes in the Axis 6 methodology
before scores are frozen.


## 1. Validation Philosophy

Every ISI axis must survive hostile review before freeze. This document
defines the specific tests, edge cases, and adversarial challenges that
Axis 6 scores must withstand. Each test is designed to break the
methodology or reveal hidden assumptions.

A test PASSES if the score is arithmetically correct, methodologically
defensible, and the behavior is documented. A test FAILS if the score
is wrong, unexplained, or reveals an undocumented assumption.


## 2. Structural Edge Cases

### 2.1 Single-Mode Countries

**Test:** Malta (MT) — maritime only.
**Expected:** Channel A HHI = 1.0 (only one mode). Channel B HHI =
maritime partner concentration only.
**Challenge:** Is L_MT = 1.0 correct? MT has no choice — it's an island.
The score reflects geography, not policy failure.
**Validation:** Confirm C_A = 1.0. Confirm cross-channel aggregation
handles single-mode correctly. Document that MT's score reflects
structural geography.

**Test:** Cyprus (CY) — road + maritime only (no rail).
**Expected:** Channel A HHI ≥ 0.50 (minimum for 2 modes). Channel B
covers road + maritime partner concentration.
**Challenge:** If maritime dominates (likely for an island), C_A → 1.0.
Is this a valid signal or an artifact?
**Validation:** Verify mode shares. If maritime = 95%, C_A ≈ 0.90.
Document as valid structural dependency.

### 2.2 Landlocked Countries

**Test:** AT, CZ, HU, LU, SK — road + rail only (no maritime).
**Expected:** Channel A HHI ≥ 0.50 (minimum for 2 modes). Channel B
covers road + rail partner concentration.
**Challenge:** Landlocked countries have a structural floor on Channel A
(HHI ≥ 0.50) while coastal countries with 3+ modes can achieve
HHI ≈ 0.33. Is this systematic bias?
**Validation:** Compare mean scores of landlocked vs coastal groups.
If landlocked are systematically higher, document as structural
geography effect, not methodology error. Verify no landlocked country
has maritime data (would indicate mapping error).

### 2.3 IWW Asymmetry

**Test:** Netherlands (NL), Germany (DE), Belgium (BE) — countries
with significant inland waterway freight.
**Expected:** IWW tonnage included in Channel A (mode shares) but
excluded from Channel B (no bilateral data).
**Challenge:** W_A ≠ W_B for these countries because IWW adds tonnage
to Channel A but not Channel B. Does this distort the cross-channel
aggregation?
**Validation:** Compute W_A − W_B for all countries. If the difference
is large for NL/DE/BE, assess whether it materially changes the final
score compared to a hypothetical W_A = W_B scenario. Document the
magnitude of distortion.


## 3. Small-Economy Amplification

### 3.1 Mechanical HHI Inflation

**Test:** LU (Luxembourg) — small landlocked economy.
**Expected:** Few bilateral freight partners in road and rail. HHI
mechanically high due to small partner count.
**Challenge:** If LU has 5 road freight partners with DE at 60%, FR at
20%, BE at 15%, and 2 others at 5%, the road HHI ≈ 0.43. But if LU
has only 3 rail partners with DE at 80%, the rail HHI ≈ 0.66. Is
LU genuinely dependent, or is this a small-N artifact?
**Validation:** For each country, report partner count alongside HHI.
Flag countries with < 10 bilateral partners per mode. Verify HHI is
arithmetically correct for small partner sets.

### 3.2 Single-Shipment Dominance

**Test:** For the smallest economies (MT, CY, LU), check whether a
single bilateral flow represents > 50% of total mode tonnage.
**Expected:** Likely yes, especially for maritime MT.
**Challenge:** A single large shipment in the reference year could
dominate the score. No temporal smoothing is applied.
**Validation:** Identify the largest single bilateral flow as a
percentage of total mode tonnage for each country. If > 50%, flag
and document. This is a known limitation, not an error.


## 4. Entrepôt and Hub Effects

### 4.1 Netherlands as Freight Hub

**Test:** For countries that trade heavily via NL (e.g., DE, BE, LU),
check whether NL appears as a dominant bilateral partner.
**Expected:** NL likely appears as top partner for road and maritime
freight for multiple EU countries due to Rotterdam's role as Europe's
largest port.
**Challenge:** This inflates NL's share of bilateral freight and masks
the true origin of goods. Countries sourcing through Rotterdam appear
NL-dependent when they are actually diversified in terms of true
origin.
**Validation:** Report NL's partner share for all EU-27 countries
across all modes. If NL appears as top partner for > 10 countries
in maritime, flag as entrepôt effect. Document but do not adjust.

### 4.2 Belgium as Freight Hub

**Test:** Same as 4.1 but for BE (Antwerp).
**Validation:** Same protocol. Report BE partner shares for all
countries and modes.

### 4.3 Germany as Road/Rail Hub

**Test:** For landlocked central European countries (AT, CZ, HU, SK),
check whether DE dominates road and rail partner shares.
**Expected:** DE is the largest economy adjacent to all four. High DE
share is structurally expected.
**Validation:** Report DE's road and rail partner share for AT, CZ,
HU, SK. If DE > 40% for multiple countries, document as geographic
adjacency effect.


## 5. Mode Dominance Artifacts

### 5.1 Road-Dominated Economies

**Test:** For continental economies (PL, CZ, HU, SK, RO, BG), check
whether road freight represents > 80% of total tonnage.
**Expected:** Likely. Road is the dominant freight mode for most
continental EU economies.
**Challenge:** If road = 85%, Channel A HHI ≈ 0.74 regardless of
diversification within road partners. A country with 50 well-
diversified road partners could still have high Channel A.
**Validation:** For countries with road > 80%, compute Channel A with
and without road dominance to quantify the effect. Document that
Channel A captures mode concentration, not partner diversification —
that's Channel B's job.

### 5.2 Maritime-Dominated Economies

**Test:** Island and peripheral coastal states (MT, CY, IE, EL, HR).
**Expected:** Maritime likely > 60% for these countries.
**Challenge:** Channel A will be high. Channel B will be dominated by
maritime partner concentration (volume-weighted). Do both channels
effectively measure the same thing for maritime-dominated countries?
**Validation:** For countries with maritime > 60%, compare Channel B
maritime HHI vs Channel B aggregate HHI. If they're nearly identical,
document that Channel B reduces to maritime partner concentration for
these countries.


## 6. Data Quality Stress Tests

### 6.1 Maritime Asymmetry Consistency

**Test:** For each pair of EU countries with maritime trade, compare
reporter A's declaration of exports to B vs reporter B's declaration
of imports from A.
**Expected:** Systematic asymmetry (documented: DE→FR = 2,343 kt vs
FR←DE = 1,554 kt).
**Challenge:** If asymmetry exceeds 2:1 for many pairs, the choice of
reporter vs mirror data materially affects scores.
**Validation:** Compute asymmetry ratio for all EU-EU maritime pairs.
Report pairs where ratio > 2.0. Verify that using reporter-only data
(as specified) produces stable, defensible scores.

### 6.2 Year-over-Year Volatility

**Test:** Compute Axis 6 scores for two consecutive years (e.g., 2022
and 2023). Compare.
**Expected:** Structural freight patterns are relatively stable year-
to-year for large economies. Small economies may show more volatility.
**Challenge:** If DE's score changes by > 20% between years, the
single-year snapshot is unstable.
**Validation:** Compute |L_i(2023) − L_i(2022)| / L_i(2022) for all
countries. Flag any country with > 15% change. If > 5 countries
exceed this threshold, consider recommending multi-year averaging
in v0.2.

### 6.3 Missing Data Robustness

**Test:** Artificially drop one country's maritime data (e.g., remove
mar_go_am_it). Does IT still get scored? What happens to its Channel B?
**Expected:** IT loses maritime partner HHI. Channel B reduces to
road + rail partner HHI. Final score changes.
**Challenge:** Quantify sensitivity to missing a single mode's data.
**Validation:** For 3 large economies (DE, FR, IT), compute score
with and without each mode's bilateral data. Report score change.
If removing one mode changes the score by > 0.10, flag as high
sensitivity to data availability.


## 7. Cross-Axis Consistency Checks

### 7.1 Axis 6 vs Axis 5 Correlation

**Test:** Compare Axis 6 scores (freight concentration) with Axis 5
scores (critical materials import concentration).
**Expected:** Some positive correlation (countries with concentrated
trade tend to have concentrated freight), but not high correlation
(different dimensions being measured).
**Challenge:** If correlation > 0.80, the axes may be measuring the
same underlying construct (small economy = concentrated everything).
**Validation:** Compute Pearson and Spearman correlation between
Axis 5 and Axis 6 scores. If Spearman ρ > 0.80, investigate whether
both axes are proxies for country size.

### 7.2 Axis 6 vs Axis 3 Correlation

**Test:** Compare Axis 6 (freight concentration) with Axis 3 (energy
import concentration).
**Expected:** Low-to-moderate correlation. Energy and freight measure
different structural dependencies.
**Validation:** Same as 7.1. Flag if Spearman ρ > 0.70.


## 8. Formula Integrity Checks

### 8.1 HHI Bounds

**Test:** Verify C_A ∈ [0, 1] and C_B ∈ [0, 1] for all 27 countries.
**Expected:** All values in range.
**Validation:** Assert min ≥ 0 and max ≤ 1. Any violation indicates
a computation error.

### 8.2 Share Summation

**Test:** Verify SUM(s_m) = 1.0 for each country's mode shares
(Channel A) and SUM(s_j) = 1.0 for each country-mode's partner
shares (Channel B).
**Expected:** Exact or within floating-point tolerance (|1.0 − sum| <
1e-10).
**Validation:** Assert for all share vectors.

### 8.3 Weight Positivity

**Test:** Verify W_A > 0 and W_B > 0 for all scored countries.
**Expected:** All positive (no EU-27 country has zero freight).
**Validation:** Assert. Any zero-weight country should be flagged
OMITTED_NO_DATA.

### 8.4 Cross-Channel Aggregation Consistency

**Test:** For countries where W_A = W_B (no IWW), verify that
L_i = 0.5 * C_A + 0.5 * C_B exactly.
**Expected:** Exact equality (structural, not numerical).
**Validation:** Compute both formulas and assert |L_i − 0.5*(C_A + C_B)|
< 1e-12 for countries without IWW.


## 9. Adversarial Interpretation Challenges

### 9.1 "The Netherlands scores low — but it's a chokepoint for others"

**Anticipated attack:** NL has diverse modal split and diverse partners
→ low Axis 6 score. But NL is itself a chokepoint for DE, BE, LU.
The axis scores NL's OWN dependency, not NL's role as a dependency
for others.
**Defense:** Axis 6 measures structural dependency FROM the scored
country's perspective, not systemic importance TO other countries.
NL's low score correctly reflects its own diversified freight base.
Its role as a hub affecting others is a systemic risk question not
addressed by per-country concentration.

### 9.2 "Island states score high — that's just geography, not policy"

**Anticipated attack:** MT, CY inevitably score high on mode
concentration because they're islands. This is geographic determinism,
not a meaningful dependency signal.
**Defense:** Acknowledged in methodology Section 8.2, point 3. Island
states ARE structurally dependent on maritime freight. This is a real
vulnerability (a naval blockade would isolate them). The score correctly
captures this geographic reality. The limitation is that no policy
could change it. This is documented, not hidden.

### 9.3 "Tonnage ignores value — a tonne of coal ≠ a tonne of semiconductors"

**Anticipated attack:** Channel B treats all bilateral freight equally
per tonne. A country with concentrated high-value freight partnerships
may be more strategically exposed than a country with concentrated
bulk commodity freight.
**Defense:** Acknowledged in methodology Section 8.1, point 6. Value-
weighted freight concentration would require linking freight data to
trade value data (different Eurostat datasets with different partner
dimensions). This integration is deferred to v0.2. The tonnage-based
approach measures physical movement dependency, not economic dependency.

### 9.4 "The entrepôt effect makes all scores meaningless"

**Anticipated attack:** If NL and BE appear as top partners for
multiple countries due to port hub effects, the bilateral HHI
measures dependence on logistics hubs, not on true origin countries.
**Defense:** Partially valid. Entrepôt effects inflate apparent
dependence on NL/BE. However: (a) dependence on a single logistics
hub IS a genuine vulnerability (port strikes, congestion, sanctions
affecting the hub affect the dependent country); (b) no origin-
adjusted bilateral freight data exists in any public source; (c)
the effect is documented, quantified (Test 4.1/4.2), and explicitly
stated as a limitation.


## 10. Validation Execution Protocol

### 10.1 Mandatory tests (must PASS before freeze)

All tests in Sections 2, 3, 6.1, 8 are mandatory.
Any failure halts the freeze process.

### 10.2 Informational tests (document results, no halt)

Tests in Sections 4, 5, 6.2, 6.3, 7 are informational.
Results are documented in the validation report but do not
prevent freeze. Unexpected results trigger investigation
and documentation, not automatic methodology changes.

### 10.3 Adversarial tests (prepare written defense)

Section 9 challenges require written defense in the
validation report. Each defense must reference specific
methodology sections where the limitation is documented.

### 10.4 Validation report

The validation execution produces:

| Output | Contents |
|--------|----------|
| `axis_6_validation_report_v01.md` | Full results of all tests |
| `axis_6_edge_case_scores.csv` | Scores for all edge-case countries with annotations |
| `axis_6_sensitivity_analysis.csv` | Score changes under data removal scenarios |
| `axis_6_cross_axis_correlations.csv` | Pairwise correlations with Axes 3 and 5 |


## 11. Pass/Fail Criteria for Freeze

The following conditions must ALL be met for v0.1 freeze:

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | All 27 EU countries scored | 27/27 |
| 2 | All scores in [0, 1] | 100% |
| 3 | All share vectors sum to 1.0 (±1e-10) | 100% |
| 4 | No NaN, null, or infinite values | 0 violations |
| 5 | Single-mode countries handled correctly | MT, CY confirmed |
| 6 | Landlocked countries have no maritime data | AT, CZ, HU, LU, SK confirmed |
| 7 | Maritime asymmetry documented | All EU-EU pairs checked |
| 8 | Entrepôt effect quantified | NL, BE hub shares reported |
| 9 | Small-economy amplification documented | LU, MT, CY flagged |
| 10 | All adversarial challenges have written defense | 4/4 |


End of hostile validation plan.
