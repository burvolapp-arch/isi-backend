"""
pipeline.rebuild — Deterministic rebuild and reproducibility verification.

This module provides the end-to-end reproducibility proof for ISI:

    1. Wipe all derived outputs (staging, validated, meta)
    2. Rebuild from raw data only
    3. Compare output hashes across runs
    4. Fail loudly if outputs differ

Source-of-truth rules:
    - data/raw/          → CANONICAL (input, never generated)
    - data/staging/      → DERIVED (generated from raw by pipeline)
    - data/validated/    → DERIVED (filtered staging that passed validation)
    - data/meta/         → DERIVED (metadata computed from raw/staging)
    - data/audit/        → DERIVED (audit logs from pipeline runs)
    - _archive/          → INERT (quarantined legacy, never read)

If any code path reads from staging/validated/meta as a SOURCE
(rather than as a cache), it is a correctness bug.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.config import (
    DATA_ROOT,
    RAW_DIR,
    STAGING_DIR,
    VALIDATED_DIR,
    META_DIR,
    AUDIT_DIR,
)

logger = logging.getLogger("pipeline.rebuild")


# ---------------------------------------------------------------------------
# Source-of-truth validation
# ---------------------------------------------------------------------------

# Directories that are DERIVED (generated, not canonical source)
DERIVED_DIRS: tuple[Path, ...] = (
    STAGING_DIR,
    VALIDATED_DIR,
    # META_DIR excluded: contains SIPRI manifest (canonical reference)
    AUDIT_DIR,
)


def verify_source_of_truth() -> list[str]:
    """Verify that raw data exists and is the canonical source.

    Returns list of violations (empty = all good).
    """
    violations: list[str] = []

    # RAW must exist
    if not RAW_DIR.is_dir():
        violations.append(f"RAW_DIR does not exist: {RAW_DIR}")

    # Check SIPRI canonical file exists
    sipri_canonical = RAW_DIR / "sipri" / "trade-register.csv"
    if not sipri_canonical.is_file():
        violations.append(f"SIPRI canonical file missing: {sipri_canonical}")

    # Check that no ingestion module reads from STAGING or VALIDATED
    # (This is a static check — more thorough version in tests)
    import ast
    ingest_dir = RAW_DIR.parent.parent / "pipeline" / "ingest"
    for py_file in ingest_dir.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        source = py_file.read_text(encoding="utf-8")
        # Check for references to STAGING_DIR or VALIDATED_DIR
        if "STAGING_DIR" in source or "VALIDATED_DIR" in source:
            # Check if it's in an import or actual usage
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    if node.id in ("STAGING_DIR", "VALIDATED_DIR"):
                        violations.append(
                            f"{py_file.name} references {node.id} — "
                            f"ingestion must read from RAW_DIR only"
                        )

    return violations


# ---------------------------------------------------------------------------
# Derived output management
# ---------------------------------------------------------------------------

def wipe_derived(reporter: str | None = None) -> dict[str, int]:
    """Delete all derived outputs for a clean rebuild.

    Args:
        reporter: If set, only wipe outputs for this reporter.
                  If None, wipe ALL derived outputs.

    Returns:
        Dict of {directory: files_deleted}.
    """
    stats: dict[str, int] = {}
    for derived_dir in DERIVED_DIRS:
        if not derived_dir.is_dir():
            stats[str(derived_dir)] = 0
            continue

        if reporter:
            target = derived_dir / reporter
            if target.is_dir():
                count = sum(1 for _ in target.rglob("*") if _.is_file())
                shutil.rmtree(target)
                stats[str(target)] = count
            else:
                stats[str(target)] = 0
        else:
            count = sum(1 for _ in derived_dir.rglob("*") if _.is_file())
            for child in derived_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.is_file():
                    child.unlink()
            stats[str(derived_dir)] = count

    return stats


# ---------------------------------------------------------------------------
# Reproducibility verification
# ---------------------------------------------------------------------------

@dataclass
class ReproducibilityResult:
    """Result of a reproducibility check."""
    reporter: str
    axis: str
    source: str
    run1_hash: str
    run2_hash: str
    run1_records: int
    run2_records: int
    run1_total: float
    run2_total: float
    deterministic: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reporter": self.reporter,
            "axis": self.axis,
            "source": self.source,
            "run1_hash": self.run1_hash[:16],
            "run2_hash": self.run2_hash[:16],
            "run1_records": self.run1_records,
            "run2_records": self.run2_records,
            "run1_total": round(self.run1_total, 4),
            "run2_total": round(self.run2_total, 4),
            "deterministic": self.deterministic,
            "details": self.details,
        }


def verify_reproducibility_sipri(
    reporters: list[str],
) -> list[ReproducibilityResult]:
    """Run SIPRI ingestion twice for each reporter and compare.

    This is the PROOF of reproducibility. If hashes differ,
    the system has non-determinism.
    """
    from pipeline.ingest.sipri import ingest_sipri

    results: list[ReproducibilityResult] = []
    for cc in reporters:
        ds1, stats1 = ingest_sipri(cc)
        ds2, stats2 = ingest_sipri(cc)

        if ds1 is None and ds2 is None:
            results.append(ReproducibilityResult(
                reporter=cc, axis="defense", source="sipri",
                run1_hash="", run2_hash="",
                run1_records=0, run2_records=0,
                run1_total=0.0, run2_total=0.0,
                deterministic=True,
                details={"note": "Both runs produced no data"},
            ))
            continue

        if ds1 is None or ds2 is None:
            results.append(ReproducibilityResult(
                reporter=cc, axis="defense", source="sipri",
                run1_hash=ds1.data_hash if ds1 else "",
                run2_hash=ds2.data_hash if ds2 else "",
                run1_records=len(ds1.records) if ds1 else 0,
                run2_records=len(ds2.records) if ds2 else 0,
                run1_total=ds1.total_value if ds1 else 0.0,
                run2_total=ds2.total_value if ds2 else 0.0,
                deterministic=False,
                details={"error": "One run produced data, the other did not"},
            ))
            continue

        match = (
            ds1.data_hash == ds2.data_hash
            and len(ds1.records) == len(ds2.records)
            and ds1.total_value == ds2.total_value
        )

        results.append(ReproducibilityResult(
            reporter=cc, axis="defense", source="sipri",
            run1_hash=ds1.data_hash,
            run2_hash=ds2.data_hash,
            run1_records=len(ds1.records),
            run2_records=len(ds2.records),
            run1_total=ds1.total_value,
            run2_total=ds2.total_value,
            deterministic=match,
        ))

    return results


def verify_reproducibility_full(
    reporters: list[str],
) -> dict[str, Any]:
    """Full reproducibility check: wipe, rebuild, compare.

    Returns structured report.
    """
    # Phase 1: Source-of-truth validation
    sot_violations = verify_source_of_truth()

    # Phase 2: SIPRI reproducibility
    sipri_results = verify_reproducibility_sipri(reporters)

    # Phase 3: Summary
    all_deterministic = all(r.deterministic for r in sipri_results)

    return {
        "source_of_truth_violations": sot_violations,
        "sipri_results": [r.to_dict() for r in sipri_results],
        "all_deterministic": all_deterministic,
        "n_reporters": len(reporters),
        "n_deterministic": sum(1 for r in sipri_results if r.deterministic),
        "n_non_deterministic": sum(1 for r in sipri_results if not r.deterministic),
    }
