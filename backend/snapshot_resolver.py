"""
backend.snapshot_resolver — Snapshot resolution and validation.

Resolves (methodology, year) pairs to concrete snapshot directories.
Validates existence and structural completeness. Provides the canonical
entry point for all snapshot data access.

Design contract:
    - resolve_snapshot() is the ONLY function that maps
      (methodology, year) → filesystem path.
    - No fallback behavior. No silent coercion.
    - Missing snapshots produce structured errors, not None.
    - SnapshotContext is an immutable value object.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from backend.methodology import (
    get_latest_methodology_version,
    get_latest_year,
    get_years_available,
)

logger = logging.getLogger("isi.resolver")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SNAPSHOTS_ROOT: Path = Path(__file__).resolve().parent / "snapshots"

# ---------------------------------------------------------------------------
# Strict validation — opt-in via environment variable
# ---------------------------------------------------------------------------

STRICT_VALIDATION: bool = os.getenv("SNAPSHOT_STRICT_VALIDATION", "").strip() == "1"
"""When enabled, resolve_snapshot() runs full integrity validation
via snapshot_integrity.validate_snapshot() before returning a context.
If validation fails, SnapshotNotFoundError is raised and the snapshot
is never served. Off by default — enable for staging/audit environments."""

# Cache of already-validated snapshot directories (strict mode only).
# Once a snapshot passes validation, it is not re-validated until restart.
_validated_snapshots: set[tuple[str, int]] = set()

# ---------------------------------------------------------------------------
# SnapshotContext — immutable value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SnapshotContext:
    """Fully resolved, validated snapshot reference.

    All fields are guaranteed non-None. The path is guaranteed
    to exist and contain isi.json at construction time.
    """

    methodology_version: str
    year: int
    path: Path
    data_window: str
    snapshot_hash: str


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SnapshotNotFoundError(Exception):
    """Raised when a requested snapshot does not exist on disk."""

    def __init__(self, methodology_version: str, year: int, detail: str) -> None:
        self.methodology_version = methodology_version
        self.year = year
        self.detail = detail
        super().__init__(detail)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_snapshot(
    methodology: str | None = None,
    year: int | None = None,
) -> SnapshotContext:
    """Resolve a (methodology, year) pair to a validated SnapshotContext.

    Args:
        methodology: Methodology version string (e.g. "v1.0").
                     None → latest from registry.
        year: Reference year (e.g. 2024).
              None → latest year for the resolved methodology.

    Returns:
        SnapshotContext with validated path and metadata.

    Raises:
        SnapshotNotFoundError: if the snapshot directory does not exist
            or is structurally incomplete.
        KeyError: if the methodology version is not in the registry.
    """
    # Resolve defaults from registry
    if methodology is None:
        methodology = get_latest_methodology_version()

    if year is None:
        year = get_latest_year()

    # Validate year is in registry's available years
    available = get_years_available(methodology)
    if year not in available:
        raise SnapshotNotFoundError(
            methodology_version=methodology,
            year=year,
            detail=(
                f"Year {year} is not available for methodology '{methodology}'. "
                f"Available years: {available}"
            ),
        )

    # Resolve filesystem path
    snapshot_dir = SNAPSHOTS_ROOT / methodology / str(year)

    if not snapshot_dir.is_dir():
        raise SnapshotNotFoundError(
            methodology_version=methodology,
            year=year,
            detail=(
                f"Snapshot directory not found: {methodology}/{year}. "
                f"Run export_snapshot.py to materialize."
            ),
        )

    # Validate structural completeness: isi.json must exist
    isi_path = snapshot_dir / "isi.json"
    if not isi_path.is_file():
        raise SnapshotNotFoundError(
            methodology_version=methodology,
            year=year,
            detail=(
                f"Snapshot {methodology}/{year} is structurally incomplete: "
                f"isi.json not found."
            ),
        )

    # Load metadata from HASH_SUMMARY.json
    hash_summary_path = snapshot_dir / "HASH_SUMMARY.json"
    snapshot_hash = ""
    if hash_summary_path.is_file():
        with open(hash_summary_path, encoding="utf-8") as fh:
            hs = json.load(fh)
            snapshot_hash = hs.get("snapshot_hash", "")

    # Load data_window from isi.json (cached — first access only)
    with open(isi_path, encoding="utf-8") as fh:
        isi_meta = json.load(fh)
    data_window = isi_meta.get("window", "")

    # Strict validation gate — runs full integrity check when enabled.
    # Cached per (methodology, year) so subsequent calls are free.
    if STRICT_VALIDATION:
        _strict_validate(snapshot_dir, methodology, year)

    return SnapshotContext(
        methodology_version=methodology,
        year=year,
        path=snapshot_dir,
        data_window=data_window,
        snapshot_hash=snapshot_hash,
    )


def _strict_validate(
    snapshot_dir: Path,
    methodology: str,
    year: int,
) -> None:
    """Run full integrity validation in strict mode.

    Called only when SNAPSHOT_STRICT_VALIDATION=1.
    Results are cached per (methodology, year) to avoid repeated I/O.
    """
    key = (methodology, year)
    if key in _validated_snapshots:
        return

    # Lazy import to avoid circular dependency at module load time
    from backend.snapshot_integrity import validate_snapshot

    report = validate_snapshot(snapshot_dir, methodology, year)
    if report.valid:
        _validated_snapshots.add(key)
        logger.info(
            "Strict validation passed: %s/%s (%d checks)",
            methodology, year, len(report.checks),
        )
    else:
        raise SnapshotNotFoundError(
            methodology_version=methodology,
            year=year,
            detail=(
                f"Strict validation failed for {methodology}/{year}: "
                f"{report.errors}"
            ),
        )


def list_available_snapshots() -> list[dict]:
    """List all materialized snapshots on disk.

    Returns list of {methodology_version, year, path} dicts,
    sorted by (methodology_version, year) ascending.
    Only includes snapshots that have isi.json present.
    """
    results: list[dict] = []

    if not SNAPSHOTS_ROOT.is_dir():
        return results

    for methodology_dir in sorted(SNAPSHOTS_ROOT.iterdir()):
        if not methodology_dir.is_dir():
            continue
        # Skip internal files (registry.json, etc.)
        methodology_version = methodology_dir.name
        if methodology_version.startswith(".") or methodology_version.startswith("_"):
            continue

        for year_dir in sorted(methodology_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            try:
                year_val = int(year_dir.name)
            except ValueError:
                continue

            if (year_dir / "isi.json").is_file():
                results.append({
                    "methodology_version": methodology_version,
                    "year": year_val,
                    "path": str(year_dir),
                })

    return results
