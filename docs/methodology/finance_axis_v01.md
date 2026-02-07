# Financial Dependency Axis — ISI v0.1

Version: 0.1
Status: FROZEN
Date: 2026-02-07
Axis: Financial Dependency
Project: Panargus / International Sovereignty Index (ISI)


## 1. Title and Version Block

Axis name: Financial Dependency
Version: 0.1
Reference year: 2024
Geographic scope: EU-27
Channels: 2 (A: Cross-Border Banking, B: Portfolio Debt Securities)
Concentration metric: Herfindahl-Hirschman Index (HHI)
Aggregation method: Volume-weighted average across channels
Score range: [0, 1]


## 2. Purpose of the Financial Dependency Axis

The Financial Dependency Axis measures the degree to which
a country's external financial liabilities are concentrated
among a small number of foreign counterparty countries.

It quantifies structural exposure to potential denial,
withdrawal, or disruption of external financial access
by dominant counterparties.

It produces a single scalar score per country per year.

Higher values indicate greater counterparty concentration
(more dependency). Lower values indicate greater
diversification (more autonomy).


## 3. Conceptual Definition

Financial Dependency in ISI terms IS:
- Concentration of external financial liabilities by
  counterparty country
- A structural position measurement
- Computed from observable bilateral stock data
- Decomposable into exactly two channels

Financial Dependency in ISI terms is NOT:
- Financial development or sophistication
- Credit risk or probability of default
- Financial openness or capital account liberalization
- Fiscal health (debt-to-GDP, deficit ratios)
- Financial market performance or volatility
- Sanctions exposure or political risk
- A policy recommendation or regime judgment


## 4. Geographic and Temporal Scope

Countries: EU-27 member states as of 2024.

The 27 Eurostat geo codes are:
AT, BE, BG, CY, CZ, DE, DK, EE, EL, ES, FI, FR, HR, HU,
IE, IT, LT, LU, LV, MT, NL, PL, PT, RO, SE, SI, SK.

Reference year: 2024.

For BIS data: Q4 2024 positions (end-of-year stock).
For IMF CPIS data: End-2024 positions.

Countries outside the EU-27 (including the United States,
China, and Russia) are excluded from v0.1 Financial axis
output. They may appear as counterparty countries in the
bilateral breakdowns but are not scored.


## 5. Data Sources

Two primary data sources are used:

Source 1: Bank for International Settlements (BIS)
- Dataset: Locational Banking Statistics (LBS)
- Table: A6 — by counterparty country
- Series: Cross-border claims, all instruments, all
  currencies, all sectors, immediate counterparty basis
- Unit: USD millions
- Access: https://www.bis.org/statistics/bankstats.htm
- Bulk dataset code: LBS_D_PUB

Source 2: International Monetary Fund (IMF)
- Dataset: Coordinated Portfolio Investment Survey (CPIS)
- Table: Inward portfolio investment by source economy
- Component: Debt securities only (equity excluded)
- Basis: Residence-based
- Unit: USD millions
- Access: https://data.imf.org/CPIS

No other data sources are used.
No third-party composite indices are used.
No qualitative inputs are used.

IMF CPIS bilateral data is ingested from a manually downloaded
raw file due to the absence of a publicly accessible,
unauthenticated API. This design choice preserves
methodological transparency and reproducibility without
reliance on credentials.


## 6. Channel A — Cross-Border Banking Dependency

### Definition

Channel A measures the concentration of inward cross-border
bank claims on country i, broken down by creditor country.

It captures how much country i owes to each foreign banking
system and how concentrated that exposure is.

The dependency perspective is debtor-side: country i is the
borrower; counterparty countries j are the creditors.

### Mathematical Formulation

Let V_{i,j}^(A) be the outstanding stock of cross-border
claims held by banks located in country j on all sectors
in country i (USD millions, immediate counterparty basis).

Share of creditor country j:

  s_{i,j}^(A) = V_{i,j}^(A) / SUM_j V_{i,j}^(A)

Concentration (HHI):

  C_i^(A) = SUM_j ( s_{i,j}^(A) )^2

C_i^(A) is in [0, 1].
C_i^(A) = 0 when exposure is uniformly spread across
infinitely many creditors.
C_i^(A) = 1 when all exposure is to a single creditor.

Volume for cross-channel weighting:

  W_i^(A) = SUM_j V_{i,j}^(A)

This is the total inward cross-border bank claims on
country i from all reporting creditor countries.

### Data Source and Coverage

Dataset: BIS LBS Table A6.
Reporting: Approximately 48 jurisdictions report as
creditor banking systems, including 16-18 EU member states.

All 27 EU member states appear as counterparty (debtor)
countries. Concentration CAN be computed for all EU-27.

The bilateral breakdown is limited to BIS-reporting
creditor countries. Non-reporting creditor countries do
not appear in the data.

### Known Limitations

1. Creditor coverage gap: Non-BIS-reporting countries are
   absent as creditors. SUM_j V_{i,j}^(A) understates total
   inward claims by the share attributable to non-reporting
   creditors. This may bias concentration upward (fewer
   identified creditors appear more concentrated).

2. The magnitude of under-coverage varies by country.
   Countries whose creditors are predominantly BIS-reporting
   jurisdictions (e.g., Western European countries) will
   have near-complete coverage. Countries borrowing from
   non-reporting jurisdictions will have larger gaps.

3. Coverage limitations are documented per country in a
   separate audit file. No imputation or correction is
   applied. The audit file reports: (a) total reported
   claims on country i, (b) number of reporting creditor
   countries with non-zero claims.


## 7. Channel B — Portfolio Debt Securities Dependency

### Definition

Channel B measures the concentration of foreign holdings
of portfolio debt securities issued by residents of
country i, broken down by holder country.

It captures how much of country i's outstanding debt paper
is held by investors in each foreign country and how
concentrated that exposure is.

Only debt securities are included. Equity securities are
excluded.

### Mathematical Formulation

Let V_{i,j}^(B) be the outstanding stock of portfolio debt
securities issued by residents of country i and held by
residents of country j (USD millions, residence basis).

Share of holder country j:

  s_{i,j}^(B) = V_{i,j}^(B) / SUM_j V_{i,j}^(B)

Concentration (HHI):

  C_i^(B) = SUM_j ( s_{i,j}^(B) )^2

C_i^(B) is in [0, 1].

Volume for cross-channel weighting:

  W_i^(B) = SUM_j V_{i,j}^(B)

This is the total portfolio debt securities issued by
country i and held by all reporting foreign countries.

### Data Source and Coverage

Dataset: IMF Coordinated Portfolio Investment Survey (CPIS).
Component: Inward, debt securities only.
Reporting: Approximately 80+ jurisdictions participate.
Most EU-27 members are covered as destination countries.

### Known Limitations

1. Participation is voluntary. Some significant holder
   countries (notably China) do not participate or report
   with significant confidential suppression.

2. CPIS covers portfolio debt securities only. It excludes:
   bank loans (captured separately in Channel A), official
   bilateral lending, trade credit, FDI-related intercompany
   lending, and privately placed debt.

3. Partial double-count with Channel A: Debt securities held
   by foreign banks appear in both BIS LBS (as part of bank
   claims, all instruments) and CPIS (as portfolio holdings,
   if the holding bank's country reports to CPIS). This
   overlap is accepted and documented. It is not corrected
   in v0.1.

4. CPIS may contain a residual or "not allocated" category
   when total identified holdings fall short of total
   outstanding debt. This residual is not attributable to
   any counterparty country and is excluded from the share
   calculation. Shares sum to 1.0 over identified holders
   only. This may bias concentration upward to the extent
   that unidentified holders are diversified.

5. Coverage limitations are documented per country in a
   separate audit file. No imputation or correction is
   applied. The audit file reports: (a) total identified
   holdings, (b) number of reporting holder countries with
   non-zero positions.


## 8. Cross-Channel Aggregation

### Exact Formula

For each country i:

  F_i = ( C_i^(A) * W_i^(A) + C_i^(B) * W_i^(B) )
        / ( W_i^(A) + W_i^(B) )

Where:
- C_i^(A) is Channel A concentration (HHI)
- C_i^(B) is Channel B concentration (HHI)
- W_i^(A) is total inward cross-border bank claims on
  country i (USD millions)
- W_i^(B) is total inward portfolio debt securities
  holdings in country i (USD millions)

F_i is in [0, 1].

### Weighting Logic

Aggregation is volume-weighted. The channel with the larger
absolute exposure volume contributes proportionally more to
the final score.

Both W_i^(A) and W_i^(B) are denominated in USD millions.
Volume weighting is dimensionally consistent without unit
conversion.

If W_i^(A) = 0 for a given country, Channel A does not
contribute. The score reduces to C_i^(B).

If W_i^(B) = 0 for a given country, Channel B does not
contribute. The score reduces to C_i^(A).

If both W_i^(A) = 0 and W_i^(B) = 0, the country is
omitted from the output.

No equal weighting is applied.
No normalization is applied.
No rescaling is applied.


## 9. Exclusions and Deferred Components

The following are explicitly excluded from v0.1:

1. Channel C — Reserve currency and payment system
   dependency. Deferred because IMF COFER individual
   country reserve composition is confidential and not
   publicly available. No proxy is applied.

2. Official bilateral lending exposure. Not captured by
   either BIS LBS or IMF CPIS.

3. FDI-related intercompany lending. Not isolable from
   available data sources.

4. Trade credit. No bilateral public source exists.

5. Derivative exposures. BIS reports some aggregate
   derivative statistics but not bilateral counterparty-
   level positions at country level.

6. Non-reporting counterparty gap correction. Coverage
   gaps in BIS and CPIS are documented per country but
   not corrected or imputed.

7. CPIS residual/unallocated holdings correction. Excluded
   from share calculation. Documented but not corrected.

8. Countries outside EU-27. The United States, China, and
   Russia are not scored in v0.1 Financial axis. They may
   appear as counterparty countries but are not included
   in the output.

9. Overlap correction between Channel A and Channel B.
   The partial double-count of debt securities held by
   foreign banks is documented but not corrected.


## 10. Reproducibility and Versioning Notes

All inputs are publicly retrievable from BIS and IMF.

All formulas are explicitly stated in this document.
No hidden parameters, thresholds, or judgment calls
are applied.

All intermediate outputs (shares, concentrations, volumes)
are preserved as CSV files in the data pipeline.

All coverage gaps and known biases are documented in
per-country audit files accompanying each computation step.

This specification is version 0.1. It is frozen as of
2026-02-07. Any modification requires a new version number.

The version identifier "v0.1" appears in all script
docstrings, output filenames, and methodology documents
associated with this axis.
