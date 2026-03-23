"""
ISI Global Data Ingestion Pipeline (v1.1)

Production-grade, deterministic, auditable data infrastructure
for the International Sovereignty Index.

Architecture layers:
    RAW       → /data/raw/{source}/{country}/{year}.{ext}   (immutable)
    STAGING   → /data/staging/{axis}/{country}.csv           (parsed)
    VALIDATED → /data/validated/{axis}/{country}.csv          (clean)
    METADATA  → /data/meta/{axis}/{country}.json             (audit)

Status semantics (canonical, no alternatives):
    PASS                     — data complete and validated
    WARNING                  — data usable with minor issues
    STRUCTURAL_LIMITATION    — source genuinely does not cover this reporter
    IMPLEMENTATION_LIMITATION — data exists but not yet ingested by pipeline
    FAILED                   — attempted and invalid

Design contract:
    - No data loss: full partner distributions, no top-N truncation
    - No silent failure: missing data triggers explicit errors
    - Reproducibility: raw data stored unchanged, all transforms logged
    - Schema consistency: all axes output the SAME canonical structure
    - Separation of concerns: ingestion STRICTLY separate from computation
    - Single pipeline: EU-27 is a subset of global, not a separate flow

No dataset can enter ISI computation unless:
    → it is structurally complete
    → validated
    → fully auditable
"""

__version__ = "1.1.1"
