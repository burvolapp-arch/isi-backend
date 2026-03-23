# ISI Correctness Guarantees

**Version:** Post-hardening pass (Session: correctness-hardening-v1)
**Test count:** 1030 (922 pre-existing + 108 new correctness tests)
**Python:** 3.14.0

---

## What is proven

### 1. End-to-end reproducibility
- SIPRI ingestion is **fully deterministic**: same raw input → same output hash, every time.
- Verified across 3 consecutive runs for JP, and single runs for DE, FR, US, GB, SE, PL, IT.
- Reference hashes are frozen in `tests/test_correctness_hardening.py`.
- `pipeline/rebuild.py` provides programmatic deterministic rebuild with hash verification.

### 2. Source-of-truth enforcement
- No ingestion module reads from `STAGING_DIR` or `VALIDATED_DIR`.
- Data flows in one direction: `data/raw/` → `data/staging/` → `data/validated/`.
- Verified by AST scan of all `pipeline/ingest/` modules.

### 3. Archive containment
- `_archive/__init__.py` raises `ImportError` on any import attempt.
- `_archive/scripts_global_v11/global_v11/__init__.py` deleted (was making archive importable).
- No live code in `backend/` or `pipeline/` imports from `_archive/`.
- Verified by file scan test in `TestArchiveContainment`.

### 4. Dead code removal
- AST-based analysis of all `backend/` and `pipeline/` files identified genuinely dead imports.
- Removed: `SEVERITY_WEIGHTS`, `compute_axis_severity_breakdown` (axis_result.py); `re`, `classify`, `SnapshotContext`, `list_available_snapshots`, `sanitize_path`, `VALID_CANONICAL_KEYS` (isi_api_v01.py); `ROUND_PRECISION`, `math` (methodology.py).
- Each removal verified against re-export patterns before deletion.

### 5. Ingestion stress testing
- 16 adversarial input scenarios tested: missing columns, truncated preamble, empty file, bad encoding, zero/negative TIV, question marks, whitespace, duplicates, wrong delimiter, non-state entities, self-trade in raw data, out-of-range years, mixed valid/invalid rows.
- All produce either correct fallback behavior or explicit error — no silent corruption.

### 6. SIPRI transformation correctness
- 11 tests verify: year range filtering, self-trade removal, non-state entity dropping, TIV positivity, aggregation by partner-year, delivery year parsing, dedup handling, reporter-partner role correctness, multi-year value distribution, partial year flagging, importer/exporter semantics.

### 7. Validation framework (13 checks)
- 9 original checks + 3 added in pipeline v1.1 + CHECK 13 (output plausibility).
- CHECK 13 verifies: minimum total value thresholds per source, extreme partner concentration, self-as-dominant-partner contamination, year distribution skew.
- All checks return structured `ValidationResult` objects with status, errors, warnings, details.

### 8. Data contract enforcement
- `BilateralRecord.__post_init__` validates: reporter (2-char uppercase), partner (2-char uppercase), value (non-negative float), year (1900–2100), source (non-empty), axis (non-empty).
- 8 contract enforcement tests verify rejection of each violation type.

### 9. Output truthfulness
- `AxisResult.to_dict()` **always** includes: `data_quality_flags`, `degradation_severity`, `data_severity`, `axis_constraints`.
- `CompositeResult.to_dict()` **always** includes: `interpretation_flags`, `interpretation_summary`, `strict_comparability_tier`, `exclude_from_rankings`, `severity_analysis`, `stability_analysis`.
- TIER_4 nullification invariant: `composite_adjusted = NULL`, `exclude_from_rankings = TRUE`. Non-negotiable. Enforced by `enforce_output_integrity()`.
- API endpoint `/country/{code}/axes` now carries `data_quality_flags` and `degradation_severity` per axis (previously stripped).
- API endpoint `/isi` carries `_truthfulness_caveat` noting that per-country comparability tiers are not yet embedded in the ranked list.

### 10. Self-falsification
- 8 adversarial scenarios test: corrupted headers, column shifts, inconsistent country casing, stale manifests, processed→ingestion feedback loops, empty value columns, all-zero TIV, extreme single-partner concentration.

---

## What is NOT proven

### 1. Full-pipeline end-to-end correctness
- The 6-axis composite computation path is tested structurally but not against ground-truth composite scores from an independent reference implementation.
- `export_snapshot.py` materializes JSON without passing through the severity model — the ranked list in `isi.json` does not carry per-country comparability tiers.

### 2. Non-SIPRI ingestion modules
- Only the SIPRI (defense axis) ingestion path has been stress-tested with real data. Other axes (financial, energy, technology, critical_inputs, logistics) have structural tests but no real-data correctness proofs.

### 3. Temporal stability
- Determinism is proven for the current raw data snapshot. If SIPRI updates their CSV format, encoding, or column layout, ingestion may break. The stress tests cover many format variations but cannot cover all future changes.

### 4. Cross-country comparability
- The severity model assigns comparability tiers, but the actual comparability of scores across countries with different data quality profiles is a methodological claim, not a proven invariant.

### 5. Scenario simulation fidelity
- `POST /scenario` applies linear adjustments to baseline scores. Whether these adjustments produce meaningful policy-relevant outputs is a domain question, not a code correctness question.

---

## Invariants enforced by tests

| Invariant | Test class | Count |
|-----------|-----------|-------|
| Deterministic rebuild | `TestEndToEndReproducibility` | 5 |
| SIPRI transformation | `TestSIPRITransformationCorrectness` | 11 |
| Ingestion stress | `TestIngestionStressTests` | 16 |
| Archive containment | `TestArchiveContainment` | 4 |
| Data contract | `TestDataContractEnforcement` | 8 |
| Plausibility | `TestPlausibilityChecks` | 9 |
| Self-falsification | `TestSelfFalsification` | 8 |
| Source-of-truth | `TestSourceOfTruth` | 3 |
| Entrypoint | `TestEntrypoint` | 2 |
| Validation checks | `TestValidationCorrectness` | 9 |
| Rebuild module | `TestRebuildModule` | 3 |
| Reference data | `TestReferenceDataStability` | 23 |
| Output truthfulness | `TestOutputTruthfulness` | 7 |

---

## How to verify

```bash
# Full test suite
cd /path/to/Panargus-isi
.venv/bin/python -m pytest tests/ --tb=short -q

# Correctness hardening tests only
.venv/bin/python -m pytest tests/test_correctness_hardening.py -v

# Single-country deterministic rebuild
.venv/bin/python -c "from pipeline.rebuild import rebuild_sipri; ds, h = rebuild_sipri('JP'); print(h)"
```
