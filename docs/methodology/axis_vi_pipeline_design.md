# Axis 6 — Logistics / Freight Dependency: Pipeline Design

**Version:** 0.1  
**Date:** 2025-02-09  
**Status:** DESIGN ONLY — no code  
**Constraint:** This document specifies the pipeline architecture and
processing logic. Implementation is deferred to the coding phase.


## 1. Pipeline Overview

The Axis 6 pipeline consists of 5 scripts executed sequentially.
Each script reads from disk and writes to disk. No script holds
state in memory across pipeline stages.

```
Script 1: ingest_logistics_freight.py
    ↓ (raw CSV per mode)
Script 2: validate_logistics_freight.py
    ↓ (validated CSV + audit log)
Script 3: compute_channel_a_mode_concentration.py
    ↓ (Channel A scores CSV)
Script 4: compute_channel_b_partner_concentration.py
    ↓ (Channel B scores CSV)
Script 5: aggregate_logistics_freight_axis.py
    ↓ (Final Axis 6 scores CSV + audit file)
```


## 2. Script 1 — Ingest

### 2.1 Purpose

Retrieve bilateral freight data from Eurostat JSON API for
all required datasets and persist as flat CSV files, one per
mode.

### 2.2 Inputs

None (fetches from Eurostat API).

### 2.3 Outputs

| Output File | Contents |
|------------|----------|
| `raw_road_loaded_{year}.csv` | Road freight loaded goods by unloading country |
| `raw_road_unloaded_{year}.csv` | Road freight unloaded goods by loading country |
| `raw_rail_{year}.csv` | Rail freight by unloading country |
| `raw_maritime_{iso2}_{year}.csv` (×22) | Maritime freight by partner MCA per country |
| `raw_modal_split_{year}.csv` | Modal split percentages |
| `ingest_manifest.json` | Metadata: timestamps, HTTP status codes, record counts |

### 2.4 Processing Logic

```
FOR dataset IN [road_go_ia_lgtt, road_go_ia_ugtt,
                rail_go_intgong, tran_hv_frmod]:
    url = API_BASE + dataset + query_params(year, EU-27 geo)
    response = HTTP_GET(url)
    ASSERT response.status == 200
    PARSE JSON response → tabular rows
    FILTER: geo IN EU-27, unit = THS_T (or PC for modal split)
    WRITE CSV

FOR iso2 IN [be, bg, cy, de, dk, ee, el, es, fi, fr,
             hr, ie, it, lt, lv, mt, nl, pl, pt, ro,
             se, si]:
    url = API_BASE + "mar_go_am_" + iso2 + query_params(year)
    response = HTTP_GET(url)
    ASSERT response.status == 200
    PARSE JSON response → tabular rows
    FILTER: unit = THS_T, cargo = TOTAL, natvessr = TOTAL
    WRITE CSV

LOG all HTTP responses, record counts, any failures
```

### 2.5 Error handling

- HTTP 404 or 500: Log error, mark dataset as FAILED in manifest.
  Pipeline halts — no partial processing.
- Empty response: Log warning, proceed if structurally expected
  (e.g., MT road = empty).
- Rate limiting: Implement 1-second delay between API calls.

### 2.6 Design rationale

Raw data is persisted to disk before any transformation. This
enables re-running downstream scripts without re-fetching from
API. The ingest manifest provides a complete audit trail of
data provenance.


## 3. Script 2 — Validate (Ingest Gate)

### 3.1 Purpose

Validate all raw CSV files for structural integrity, enforce
EU-27 scope, and produce an audit log documenting data
completeness per country per mode.

### 3.2 Inputs

All `raw_*.csv` files from Script 1.

### 3.3 Outputs

| Output File | Contents |
|------------|----------|
| `validated_road_{year}.csv` | Road freight, validated and harmonised |
| `validated_rail_{year}.csv` | Rail freight, validated and harmonised |
| `validated_maritime_{year}.csv` | Maritime freight, all 22 countries combined, MCA aggregated to country |
| `validated_modal_split_{year}.csv` | Modal split, validated |
| `validation_audit.csv` | Per-country, per-mode audit: row count, total tonnage, partner count, pass/fail |

### 3.4 Processing Logic

```
FOR each raw CSV:
    LOAD data
    
    # Structural checks
    ASSERT required columns present
    ASSERT no duplicate (reporter, partner, mode) rows
    ASSERT all tonnage values >= 0
    ASSERT no null reporter or partner codes
    
    # Scope enforcement
    FILTER reporters to EU-27 only
    EXCLUDE EU aggregate partner codes (EU27_2020, etc.)
    
    # Maritime MCA-to-country aggregation
    IF maritime:
        LOAD MCA-to-country mapping
        MAP par_mar → ISO country code
        SUM tonnage across MCAs belonging to same country
        WRITE as country-level bilateral rows
    
    # Road direction harmonisation
    IF road:
        MERGE loaded (lgtt) and unloaded (ugtt) tables
        SUM bilateral tonnage (reporter → partner) from both directions
        DEDUPLICATE: each (reporter, partner) pair appears once
    
    WRITE validated CSV
    
    # Audit
    FOR each EU-27 country:
        COUNT rows, SUM tonnage, COUNT unique partners
        IF country expected to have data for this mode:
            IF row_count == 0: FAIL
            ELSE: PASS
        ELSE:
            EXPECTED_ABSENT (e.g., MT road, CY rail)
    
    WRITE validation_audit.csv
```

### 3.5 Validation gates (hard stops)

| Check | Condition | Action if Failed |
|-------|-----------|-----------------|
| EU-27 completeness | All expected reporters present per mode | HALT |
| Non-negative tonnage | All values >= 0 | HALT |
| Column structure | Required columns present | HALT |
| Zero-row countries | Expected countries have > 0 rows | HALT |
| Duplicate rows | No (reporter, partner) duplicates after merge | HALT |

### 3.6 Design rationale

The validation gate is a hard stop. If any structural check
fails, the pipeline halts and no scores are computed. This
prevents silent data corruption from propagating into
concentration calculations.

Maritime MCA-to-country aggregation is performed here rather
than in the scoring scripts to ensure a single, consistent
country-level representation is used throughout.


## 4. Script 3 — Channel A: Mode Concentration

### 4.1 Purpose

Compute per-country mode concentration (HHI) across transport
modes.

### 4.2 Inputs

| Input File | Used For |
|-----------|----------|
| `validated_road_{year}.csv` | Road tonnage per country (sum across partners) |
| `validated_rail_{year}.csv` | Rail tonnage per country (sum across partners) |
| `validated_maritime_{year}.csv` | Maritime tonnage per country (sum across partners) |
| `validated_modal_split_{year}.csv` | IWW percentage shares (where available) |

### 4.3 Outputs

| Output File | Contents |
|------------|----------|
| `channel_a_mode_shares_{year}.csv` | Per-country mode shares: country, mode, tonnage, share |
| `channel_a_scores_{year}.csv` | Per-country Channel A HHI: country, HHI, total_tonnage, mode_count |

### 4.4 Processing Logic

```
FOR each EU-27 country i:
    
    # Determine mode tonnages
    T_road = SUM of validated road tonnage for country i
    T_rail = SUM of validated rail tonnage for country i
    T_maritime = SUM of validated maritime tonnage for country i
    
    # IWW from modal split (if available)
    IF country i has IWW share in modal_split:
        # tran_hv_frmod gives percentage shares of inland freight
        # Inland freight = road + rail + IWW
        # IWW_pct = tran_hv_frmod IWW percentage
        # T_inland = T_road + T_rail + T_iww
        # T_iww = IWW_pct / (ROAD_pct + RAIL_pct) * (T_road + T_rail)
        # (deriving IWW absolute tonnage from bilateral road+rail
        #  totals and percentage shares)
        T_iww = derive_iww_tonnage(T_road, T_rail, IWW_pct, ROAD_pct, RAIL_pct)
    ELSE:
        T_iww = 0
    
    # Active modes and total
    modes = {m : T_m for m in [road, rail, maritime, iww] if T_m > 0}
    T_total = SUM(modes.values())
    
    IF T_total == 0:
        MARK country i as OMITTED_NO_DATA
        CONTINUE
    
    # Mode shares
    FOR each mode m in modes:
        s_m = T_m / T_total
    
    # HHI
    C_A = SUM(s_m^2 for m in modes)
    
    # Store
    W_A = T_total  # volume for cross-channel weighting
    
    WRITE (country, C_A, W_A, mode_count, modes_list)

WRITE channel_a_mode_shares CSV
WRITE channel_a_scores CSV
```

### 4.5 IWW derivation note

IWW absolute tonnage is not directly available from bilateral
data (no bilateral IWW dataset exists). It is derived from
`tran_hv_frmod` percentage shares combined with bilateral
road + rail totals. This introduces a methodological coupling:
IWW tonnage depends on the accuracy of both the modal split
percentages and the bilateral road/rail totals.

If the modal split percentages and bilateral totals are
inconsistent (e.g., due to different survey methodologies),
the derived IWW tonnage may be inaccurate. The pipeline
documents this derivation and flags countries where the
derivation produces implausible values.

### 4.6 Design rationale

Channel A computation is isolated in its own script to enable
independent validation. The mode shares CSV provides full
transparency into the inputs to the HHI calculation.


## 5. Script 4 — Channel B: Partner Concentration per Mode

### 5.1 Purpose

Compute per-country, per-mode partner concentration (HHI),
then aggregate across modes using freight-volume weights.

### 5.2 Inputs

| Input File | Used For |
|-----------|----------|
| `validated_road_{year}.csv` | Bilateral road freight by partner |
| `validated_rail_{year}.csv` | Bilateral rail freight by partner |
| `validated_maritime_{year}.csv` | Bilateral maritime freight by partner (country-level) |

### 5.3 Outputs

| Output File | Contents |
|------------|----------|
| `channel_b_partner_shares_{year}.csv` | Per-country, per-mode, per-partner: shares |
| `channel_b_mode_hhi_{year}.csv` | Per-country, per-mode HHI: country, mode, HHI, volume, partner_count |
| `channel_b_scores_{year}.csv` | Per-country Channel B aggregate: country, HHI_weighted, total_bilateral_tonnage |

### 5.4 Processing Logic

```
FOR each EU-27 country i:
    
    FOR each mode m IN [road, rail, maritime]:
        
        IF country i has no data for mode m:
            SKIP (e.g., MT road, CY rail, landlocked maritime)
        
        # Get bilateral flows
        flows = {partner_j : tonnage for all partners of country i in mode m}
        V_mode = SUM(flows.values())
        
        IF V_mode == 0:
            SKIP mode
        
        # Partner shares
        FOR each partner j:
            s_j = flows[j] / V_mode
        
        # Per-mode HHI
        C_B_m = SUM(s_j^2 for j in flows)
        
        STORE (country, mode, C_B_m, V_mode, partner_count)
    
    # Aggregate across modes (volume-weighted)
    modes_with_data = modes where C_B_m was computed
    
    IF no modes_with_data:
        MARK country i as OMITTED_NO_BILATERAL_DATA
        CONTINUE
    
    C_B = SUM(C_B_m * V_mode for m in modes_with_data) /
          SUM(V_mode for m in modes_with_data)
    
    W_B = SUM(V_mode for m in modes_with_data)
    
    WRITE (country, C_B, W_B)

WRITE channel_b_partner_shares CSV
WRITE channel_b_mode_hhi CSV
WRITE channel_b_scores CSV
```

### 5.5 Partner exclusions

- EU aggregate partner codes are excluded (handled in Script 2).
- Self-pairs (reporter = partner) are retained as recorded.
  If a country reports freight to/from itself in international
  tables, these rows are kept. Their magnitude is expected to
  be negligible.
- "TOTAL" or "WORLD" aggregate partner codes are excluded.
  Only individual country/MCA codes are used.

### 5.6 Design rationale

Per-mode HHI values are preserved as intermediate output
(`channel_b_mode_hhi`) to enable independent analysis of
partner concentration by mode. This is critical for hostile
validation: reviewers can inspect whether maritime partner
concentration dominates the weighted average for coastal
countries.


## 6. Script 5 — Cross-Channel Aggregation

### 6.1 Purpose

Combine Channel A and Channel B scores into the final Axis 6
score per country.

### 6.2 Inputs

| Input File | Used For |
|-----------|----------|
| `channel_a_scores_{year}.csv` | C_A and W_A per country |
| `channel_b_scores_{year}.csv` | C_B and W_B per country |

### 6.3 Outputs

| Output File | Contents |
|------------|----------|
| `axis_6_scores_v01_{year}.csv` | Final scores: country, axis_score, C_A, C_B, W_A, W_B, mode_count |
| `axis_6_scope_audit_v01_{year}.csv` | Per-country audit: inclusion/exclusion status, reason, available modes |

### 6.4 Processing Logic

```
LOAD channel_a_scores → dict {country: (C_A, W_A)}
LOAD channel_b_scores → dict {country: (C_B, W_B)}

FOR each EU-27 country i:
    
    IF i not in channel_a AND i not in channel_b:
        STATUS = OMITTED_NO_DATA
        CONTINUE
    
    IF i not in channel_a:
        L_i = C_B_i  # Channel A missing → score = Channel B
        STATUS = SCORED_CHANNEL_B_ONLY
        CONTINUE
    
    IF i not in channel_b:
        L_i = C_A_i  # Channel B missing → score = Channel A
        STATUS = SCORED_CHANNEL_A_ONLY
        CONTINUE
    
    # Normal case: both channels available
    L_i = (C_A_i * W_A_i + C_B_i * W_B_i) / (W_A_i + W_B_i)
    STATUS = SCORED_BOTH_CHANNELS
    
    WRITE (country, L_i, C_A_i, C_B_i, W_A_i, W_B_i, status)

# Scope audit
FOR each EU-27 country:
    WRITE (country, status, available_modes, C_A, C_B, L_i)

FOR each non-EU-27 country appearing in any dataset:
    WRITE (country, EXCLUDED_NOT_EU27)

ASSERT 27 countries scored (SCORED_BOTH_CHANNELS or
       SCORED_CHANNEL_*_ONLY)
ASSERT 0 countries OMITTED_NO_DATA
ASSERT all scores in [0, 1]

WRITE axis_6_scores CSV
WRITE axis_6_scope_audit CSV
```

### 6.5 Output validation

The final script performs these assertions before writing
output:

| Assertion | Expected |
|-----------|----------|
| Total scored countries | 27 |
| All scores in [0, 1] | True |
| No NaN or null scores | True |
| No duplicate countries | True |
| C_A, C_B individually in [0, 1] | True |
| W_A, W_B > 0 for scored countries | True |

### 6.6 Design rationale

The aggregation script is deliberately minimal. It reads two
CSV files and produces the final output. All complexity is
upstream. This ensures the aggregation logic is trivially
auditable.


## 7. File Naming Conventions

All output files follow the pattern:

```
{stage}_{descriptor}_v01_{year}.csv
```

Where:
- `{stage}` identifies the pipeline stage (raw, validated,
  channel_a, channel_b, axis_6)
- `{descriptor}` identifies the content
- `v01` is the methodology version
- `{year}` is the reference year

The methodology version is embedded in filenames to prevent
confusion across methodology iterations.


## 8. Pipeline Execution Order

```
Step 1: python ingest_logistics_freight.py --year 2023
Step 2: python validate_logistics_freight.py --year 2023
Step 3: python compute_channel_a_mode_concentration.py --year 2023
Step 4: python compute_channel_b_partner_concentration.py --year 2023
Step 5: python aggregate_logistics_freight_axis.py --year 2023
```

Each script accepts a `--year` argument. Each script checks
for the existence of its input files and halts with an explicit
error if any are missing.

No script imports from or depends on another script at the
module level. All inter-script communication is via CSV files
on disk.


## 9. Data Directory Structure

```
data/
  axis_6/
    raw/
      raw_road_loaded_2023.csv
      raw_road_unloaded_2023.csv
      raw_rail_2023.csv
      raw_maritime_be_2023.csv
      raw_maritime_bg_2023.csv
      ... (22 maritime files)
      raw_modal_split_2023.csv
      ingest_manifest.json
    validated/
      validated_road_2023.csv
      validated_rail_2023.csv
      validated_maritime_2023.csv
      validated_modal_split_2023.csv
      validation_audit.csv
    scores/
      channel_a_mode_shares_2023.csv
      channel_a_scores_2023.csv
      channel_b_partner_shares_2023.csv
      channel_b_mode_hhi_2023.csv
      channel_b_scores_2023.csv
      axis_6_scores_v01_2023.csv
      axis_6_scope_audit_v01_2023.csv
    reference/
      mca_to_country_mapping.csv
```


End of pipeline design.
