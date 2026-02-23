# ISI Results Evidence Pack — Validation Report

**Generated:** 2026-02-22T12:44:14.442205+00:00
**Git commit:** `4b3ac68eb2e004eae4affa24d04218834e2bd1b8`
**Methodology:** v1.0
**Year:** 2024
**Scope:** EU-27

---

## Validation Checks

- [PASS] EU-27 country count = 27: got 27
- [PASS] Complete countries matches isi.json countries_complete: computed=27, expected=27
- [PASS] stats.min matches isi.json within 1e-8: diff=0.00e+00, computed=0.23567126, expected=0.23567126
- [PASS] stats.max matches isi.json within 1e-8: diff=0.00e+00, computed=0.51748148, expected=0.51748148
- [PASS] stats.mean matches isi.json within 1e-8: diff=1.11e-09, computed=0.34439144111111114, expected=0.34439144
- [PASS] Ranking tie-break logic applied: descending composite, alphabetical for ties
- [PASS] All axis scores in [0.0, 1.0]: all 162 values valid
- [PASS] Countries with axis score = 1.0 (transparency): 2 instances: MT.axis_4_defense, MT.axis_6_logistics
- [PASS] No unexpected axis_slug values: all slugs valid: ['critical_inputs', 'defense', 'energy', 'financial', 'logistics', 'technology']
- [PASS] Country codes match EU-27 set exactly: exact match

### Scope Guard
- No LaTeX prose files present in this evidence pack build.
- Scope contamination check deferred to paper typesetting phase.

### Summary: 10 passed, 0 failed

---

## Input Artifacts

Total input files hashed: 38

- `backend/snapshots/registry.json`: `43fb9e02fa98c3bd...`
- `backend/snapshots/v1.0/2024/HASH_SUMMARY.json`: `56d40d0cf8689254...`
- `backend/snapshots/v1.0/2024/MANIFEST.json`: `578f6d3e15b04371...`
- `backend/snapshots/v1.0/2024/SIGNATURE.json`: `7839c66b74923b32...`
- `backend/snapshots/v1.0/2024/axis/1.json`: `0e41bc7ad78f18ea...`
- `backend/snapshots/v1.0/2024/axis/2.json`: `d25ea7304f6c8b53...`
- `backend/snapshots/v1.0/2024/axis/3.json`: `3fe5a15a62666fa5...`
- `backend/snapshots/v1.0/2024/axis/4.json`: `fada3aab1841fc74...`
- `backend/snapshots/v1.0/2024/axis/5.json`: `924196956d0e9b8f...`
- `backend/snapshots/v1.0/2024/axis/6.json`: `024cb036a1de9c25...`
- `backend/snapshots/v1.0/2024/country/AT.json`: `ee24fcd83dc25168...`
- `backend/snapshots/v1.0/2024/country/BE.json`: `0841ee109aa191c1...`
- `backend/snapshots/v1.0/2024/country/BG.json`: `8304621dea921d86...`
- `backend/snapshots/v1.0/2024/country/CY.json`: `3b2b477fbfba7117...`
- `backend/snapshots/v1.0/2024/country/CZ.json`: `043813742d292a91...`
- `backend/snapshots/v1.0/2024/country/DE.json`: `2444ff8ce5b6bda7...`
- `backend/snapshots/v1.0/2024/country/DK.json`: `bf572c782ff5ea1f...`
- `backend/snapshots/v1.0/2024/country/EE.json`: `b4a6e13f0d978bd2...`
- `backend/snapshots/v1.0/2024/country/EL.json`: `0223949a2cccda43...`
- `backend/snapshots/v1.0/2024/country/ES.json`: `7e588e9648003000...`
- `backend/snapshots/v1.0/2024/country/FI.json`: `573a2fa4c8fe2fd2...`
- `backend/snapshots/v1.0/2024/country/FR.json`: `1c5f09c5381329e9...`
- `backend/snapshots/v1.0/2024/country/HR.json`: `d7ad0e1e4d30b7e0...`
- `backend/snapshots/v1.0/2024/country/HU.json`: `93d7d9755afe289e...`
- `backend/snapshots/v1.0/2024/country/IE.json`: `21e4d1569ddf0819...`
- `backend/snapshots/v1.0/2024/country/IT.json`: `71ff2b84c32dff20...`
- `backend/snapshots/v1.0/2024/country/LT.json`: `3f12bd7ecccc90cb...`
- `backend/snapshots/v1.0/2024/country/LU.json`: `507015a412c2dd20...`
- `backend/snapshots/v1.0/2024/country/LV.json`: `8d697bc6297aa12d...`
- `backend/snapshots/v1.0/2024/country/MT.json`: `87ab2bd679d06a76...`
- `backend/snapshots/v1.0/2024/country/NL.json`: `b3d10711aa385713...`
- `backend/snapshots/v1.0/2024/country/PL.json`: `b6adaeffcd8120ad...`
- `backend/snapshots/v1.0/2024/country/PT.json`: `cbd0c5f1a2af57b4...`
- `backend/snapshots/v1.0/2024/country/RO.json`: `ed1c5d04ddf00395...`
- `backend/snapshots/v1.0/2024/country/SE.json`: `3b1332673500fb6d...`
- `backend/snapshots/v1.0/2024/country/SI.json`: `b9cd85f0bed297fb...`
- `backend/snapshots/v1.0/2024/country/SK.json`: `0d53cd4adc9be424...`
- `backend/snapshots/v1.0/2024/isi.json`: `2e7b0b41708518d7...`

---

## Countries with Axis Score = 1.0

- **MT** (Malta): `axis_4_defense` = 1.0
- **MT** (Malta): `axis_6_logistics` = 1.0

---

## Concentration Profile Summary

- Single-spike countries: 27
- Broad-based countries: 0
- Spike detection threshold: k = 1.0

---

## Strongest Cross-Axis Correlations

- critical_inputs × logistics: r = 0.5485
- energy × technology: r = 0.5299
- energy × critical_inputs: r = 0.3720
- defense × logistics: r = 0.2862
- technology × defense: r = -0.2218

---

*End of validation report.*
