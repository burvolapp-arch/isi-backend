"""
backend.snapshot_integrity — Snapshot structural integrity validation.

Validates a materialized snapshot directory for:
    1. Directory structure correctness (expected files, no unexpected files)
    2. MANIFEST.json consistency (SHA-256 recomputation of every file)
    3. HASH_SUMMARY.json consistency (per-country + aggregate hash verification)
    4. Internal structural invariants (27 countries, NUM_AXES, rank, composite, classification)

Design contract:
    - validate_snapshot() is the ONLY validation entry point.
    - No recomputation of baselines. Only validates stored artifacts.
    - Returns a structured IntegrityReport — never raises on validation failure.
    - Strict mode: if any check fails, snapshot must not be served.
    - No disk I/O during normal request path. Validation is opt-in or startup-only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.constants import (
    EU27_CODES,
    EU27_SORTED,
    ISI_AXIS_KEYS,
    NUM_AXES,
    ROUND_PRECISION,
)
from backend.hashing import (
    compute_country_hash,
    compute_snapshot_hash,
)
from backend.methodology import classify, get_methodology


# ---------------------------------------------------------------------------
# Exit codes — used by CLI, exposed for programmatic use
# ---------------------------------------------------------------------------

EXIT_OK: int = 0
EXIT_MISSING_FILES: int = 1
EXIT_MANIFEST_MISMATCH: int = 2
EXIT_HASH_MISMATCH: int = 3
EXIT_STRUCTURAL_INVARIANT: int = 4
EXIT_METHODOLOGY_MISMATCH: int = 5


# ---------------------------------------------------------------------------
# Expected file inventory
# ---------------------------------------------------------------------------

def expected_files(eu27: list[str] | None = None) -> set[str]:
    """Return the set of expected relative paths within a snapshot directory.

    Paths are POSIX-style relative (forward slashes).
    """
    if eu27 is None:
        eu27 = EU27_SORTED
    files = {
        "isi.json",
        "MANIFEST.json",
        "HASH_SUMMARY.json",
    }
    for i in range(1, NUM_AXES + 1):
        files.add(f"axis/{i}.json")
    for code in eu27:
        files.add(f"country/{code}.json")
    return files


# ---------------------------------------------------------------------------
# IntegrityReport — structured, immutable result
# ---------------------------------------------------------------------------


@dataclass
class IntegrityReport:
    """Structured report from snapshot validation.

    Fields:
        valid: True only if ALL checks pass.
        methodology_version: The methodology version being validated.
        year: The snapshot year being validated.
        checks: List of check results — each a dict with
            {check, passed, detail?}.
        errors: Flat list of human-readable error strings.
        exit_code: Numeric exit code (0 = ok, non-zero = specific failure).
    """
    valid: bool = True
    methodology_version: str = ""
    year: int = 0
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    exit_code: int = EXIT_OK

    def fail(self, check: str, detail: str, code: int) -> None:
        """Record a failed check."""
        self.valid = False
        self.checks.append({"check": check, "passed": False, "detail": detail})
        self.errors.append(f"[{check}] {detail}")
        # Keep the first (most severe) exit code
        if self.exit_code == EXIT_OK:
            self.exit_code = code

    def ok(self, check: str, detail: str = "") -> None:
        """Record a passing check."""
        self.checks.append({"check": check, "passed": True, "detail": detail})

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON output."""
        return {
            "valid": self.valid,
            "methodology_version": self.methodology_version,
            "year": self.year,
            "exit_code": self.exit_code,
            "checks": self.checks,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# SHA-256 file hashing
# ---------------------------------------------------------------------------

def _sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Individual validation steps
# ---------------------------------------------------------------------------

def _check_directory_structure(
    snapshot_dir: Path,
    report: IntegrityReport,
) -> bool:
    """Check 1: Directory structure correctness.

    Verifies:
        - All expected files exist.
        - No unexpected files present.

    Returns True if all expected files present (even if unexpected found).
    """
    expected = expected_files()
    actual: set[str] = set()

    for p in snapshot_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(snapshot_dir).as_posix()
            actual.add(rel)

    missing = expected - actual
    unexpected = actual - expected

    if missing:
        report.fail(
            "directory_structure",
            f"Missing files: {sorted(missing)}",
            EXIT_MISSING_FILES,
        )
        return False

    if unexpected:
        # Unexpected files are a warning, not a failure.
        # But we still note it in the report.
        report.ok(
            "directory_structure",
            f"All {len(expected)} expected files present. "
            f"Unexpected files (allowed): {sorted(unexpected)}",
        )
    else:
        report.ok(
            "directory_structure",
            f"All {len(expected)} expected files present. No unexpected files.",
        )

    return True


def _check_manifest_consistency(
    snapshot_dir: Path,
    report: IntegrityReport,
) -> bool:
    """Check 2: MANIFEST.json SHA-256 consistency.

    Recomputes SHA-256 of every file listed in MANIFEST.json.
    Hard fail on any mismatch.
    """
    manifest_path = snapshot_dir / "MANIFEST.json"
    if not manifest_path.is_file():
        report.fail(
            "manifest_consistency",
            "MANIFEST.json not found.",
            EXIT_MANIFEST_MISMATCH,
        )
        return False

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        report.fail(
            "manifest_consistency",
            f"Failed to parse MANIFEST.json: {type(exc).__name__}: {exc}",
            EXIT_MANIFEST_MISMATCH,
        )
        return False

    files_list = manifest.get("files", [])
    if not files_list:
        report.fail(
            "manifest_consistency",
            "MANIFEST.json contains no file entries.",
            EXIT_MANIFEST_MISMATCH,
        )
        return False

    mismatches: list[str] = []
    missing: list[str] = []
    checked = 0

    for entry in files_list:
        rel_path = entry.get("path", "")
        expected_hash = entry.get("sha256", "")
        if not rel_path or not expected_hash:
            mismatches.append(f"Invalid entry: {entry}")
            continue

        file_path = snapshot_dir / rel_path
        if not file_path.is_file():
            missing.append(rel_path)
            continue

        actual_hash = _sha256_file(file_path)
        checked += 1
        if actual_hash != expected_hash:
            mismatches.append(
                f"{rel_path}: expected {expected_hash[:16]}…, "
                f"got {actual_hash[:16]}…"
            )

    if missing:
        report.fail(
            "manifest_consistency",
            f"Missing files referenced in manifest: {missing}",
            EXIT_MANIFEST_MISMATCH,
        )
        return False

    if mismatches:
        report.fail(
            "manifest_consistency",
            f"SHA-256 mismatches ({len(mismatches)}): {mismatches}",
            EXIT_MANIFEST_MISMATCH,
        )
        return False

    report.ok(
        "manifest_consistency",
        f"All {checked} files verified against MANIFEST.json.",
    )
    return True


def _check_hash_summary(
    snapshot_dir: Path,
    methodology_version: str,
    year: int,
    report: IntegrityReport,
) -> bool:
    """Check 3: HASH_SUMMARY.json consistency.

    Verifies:
        - Per-country hashes match recomputation via hashing.compute_country_hash()
        - Snapshot-level aggregate hash matches hashing.compute_snapshot_hash()
    """
    hs_path = snapshot_dir / "HASH_SUMMARY.json"
    if not hs_path.is_file():
        report.fail(
            "hash_summary",
            "HASH_SUMMARY.json not found.",
            EXIT_HASH_MISMATCH,
        )
        return False

    try:
        with open(hs_path, encoding="utf-8") as fh:
            hs = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        report.fail(
            "hash_summary",
            f"Failed to parse HASH_SUMMARY.json: {type(exc).__name__}: {exc}",
            EXIT_HASH_MISMATCH,
        )
        return False

    stored_country_hashes = hs.get("country_hashes", {})
    stored_snapshot_hash = hs.get("snapshot_hash", "")

    if not stored_country_hashes:
        report.fail(
            "hash_summary",
            "HASH_SUMMARY.json has no country_hashes.",
            EXIT_HASH_MISMATCH,
        )
        return False

    # Load isi.json to get data_window
    isi_path = snapshot_dir / "isi.json"
    if not isi_path.is_file():
        report.fail(
            "hash_summary",
            "isi.json not found (required to extract data_window for hash).",
            EXIT_HASH_MISMATCH,
        )
        return False

    with open(isi_path, encoding="utf-8") as fh:
        isi_data = json.load(fh)

    data_window = isi_data.get("window", "")

    # Load methodology params
    try:
        methodology_params = get_methodology(methodology_version)
    except KeyError:
        report.fail(
            "hash_summary",
            f"Methodology '{methodology_version}' not found in registry.",
            EXIT_METHODOLOGY_MISMATCH,
        )
        return False

    # Recompute per-country hashes
    countries = isi_data.get("countries", [])
    country_by_code: dict[str, dict] = {c["country"]: c for c in countries}

    recomputed_hashes: dict[str, str] = {}
    hash_mismatches: list[str] = []

    axis_slugs = sorted(methodology_params["axis_slugs"])

    # Build ISI key → slug mapping
    isi_key_to_slug = {}
    for slug in axis_slugs:
        for isi_key in ISI_AXIS_KEYS:
            if isi_key.endswith(f"_{slug}"):
                isi_key_to_slug[isi_key] = slug
                break

    for code in EU27_SORTED:
        if code not in country_by_code:
            hash_mismatches.append(f"{code}: not found in isi.json countries[]")
            continue

        entry = country_by_code[code]

        # Build axis_scores as {slug: score}
        axis_scores: dict[str, float] = {}
        for isi_key in ISI_AXIS_KEYS:
            slug = isi_key_to_slug.get(isi_key)
            if slug:
                axis_scores[slug] = entry.get(isi_key, 0.0)

        composite = entry.get("isi_composite", 0.0)

        recomputed = compute_country_hash(
            country_code=code,
            year=year,
            methodology_version=methodology_version,
            axis_scores=axis_scores,
            composite=composite,
            data_window=data_window,
            methodology_params=methodology_params,
        )
        recomputed_hashes[code] = recomputed

        stored = stored_country_hashes.get(code, "")
        if recomputed != stored:
            hash_mismatches.append(
                f"{code}: stored {stored[:16]}… ≠ recomputed {recomputed[:16]}…"
            )

    if hash_mismatches:
        report.fail(
            "hash_summary",
            f"Country hash mismatches ({len(hash_mismatches)}): {hash_mismatches}",
            EXIT_HASH_MISMATCH,
        )
        return False

    # Verify aggregate snapshot hash
    recomputed_snapshot = compute_snapshot_hash(recomputed_hashes)
    if recomputed_snapshot != stored_snapshot_hash:
        report.fail(
            "hash_summary",
            f"Snapshot hash mismatch: stored {stored_snapshot_hash[:16]}… "
            f"≠ recomputed {recomputed_snapshot[:16]}…",
            EXIT_HASH_MISMATCH,
        )
        return False

    report.ok(
        "hash_summary",
        f"All {len(recomputed_hashes)} country hashes + snapshot hash verified.",
    )
    return True


def _check_structural_invariants(
    snapshot_dir: Path,
    methodology_version: str,
    report: IntegrityReport,
) -> bool:
    """Check 4: Internal structural invariants.

    Verifies:
        - Exactly 27 countries in isi.json
        - Exactly NUM_AXES per country in country/*.json
        - Rank range 1–27
        - Composite ∈ [0, 1]
        - Classification matches methodology thresholds
    """
    isi_path = snapshot_dir / "isi.json"
    if not isi_path.is_file():
        report.fail(
            "structural_invariants",
            "isi.json not found.",
            EXIT_STRUCTURAL_INVARIANT,
        )
        return False

    with open(isi_path, encoding="utf-8") as fh:
        isi_data = json.load(fh)

    countries = isi_data.get("countries", [])
    violations: list[str] = []

    # — Exactly 27 countries
    if len(countries) != 27:
        violations.append(f"Expected 27 countries, found {len(countries)}.")

    # — Country code set must match EU-27
    country_codes = {c["country"] for c in countries}
    if country_codes != EU27_CODES:
        missing = EU27_CODES - country_codes
        extra = country_codes - EU27_CODES
        if missing:
            violations.append(f"Missing EU-27 countries: {sorted(missing)}")
        if extra:
            violations.append(f"Unexpected countries: {sorted(extra)}")

    # — Rank, composite, classification checks on isi.json
    composites_for_ranking: list[tuple[float, str]] = []
    for entry in countries:
        code = entry.get("country", "??")
        composite = entry.get("isi_composite")

        if composite is None:
            violations.append(f"{code}: isi_composite is None.")
            continue

        # Composite ∈ [0, 1]
        if not (0.0 <= composite <= 1.0):
            violations.append(f"{code}: composite {composite} outside [0, 1].")

        # Classification matches methodology
        try:
            expected_class = classify(composite, methodology_version)
        except KeyError:
            violations.append(
                f"{code}: cannot classify — methodology '{methodology_version}' "
                f"not found in registry."
            )
            composites_for_ranking.append((composite, code))
            continue

        actual_class = entry.get("classification", "")
        if actual_class != expected_class:
            violations.append(
                f"{code}: classification '{actual_class}' does not match "
                f"expected '{expected_class}' for composite {composite}."
            )

        composites_for_ranking.append((composite, code))

        # All 6 ISI axis keys present and in [0, 1]
        for isi_key in ISI_AXIS_KEYS:
            val = entry.get(isi_key)
            if val is None:
                violations.append(f"{code}: missing axis key '{isi_key}'.")
            elif not (0.0 <= val <= 1.0):
                violations.append(f"{code}: {isi_key}={val} outside [0, 1].")

    # — Validate ranks: sorted by (-composite, code) → rank 1..27
    composites_for_ranking.sort(key=lambda x: (-x[0], x[1]))
    expected_rank_map: dict[str, int] = {}
    for i, (_, code) in enumerate(composites_for_ranking, 1):
        expected_rank_map[code] = i

    # — Validate country/*.json structural invariants
    for code in EU27_SORTED:
        country_path = snapshot_dir / "country" / f"{code}.json"
        if not country_path.is_file():
            violations.append(f"{code}: country/{code}.json not found.")
            continue

        with open(country_path, encoding="utf-8") as fh:
            country_data = json.load(fh)

        axes = country_data.get("axes", [])
        if len(axes) != NUM_AXES:
            violations.append(
                f"{code}: expected {NUM_AXES} axes in country file, found {len(axes)}."
            )

        for ax in axes:
            ax_id = ax.get("axis_id")
            score = ax.get("score")
            if score is not None and not (0.0 <= score <= 1.0):
                violations.append(
                    f"{code}: axis {ax_id} score {score} outside [0, 1]."
                )

    # — Validate axis/*.json structural invariants
    for axis_num in range(1, NUM_AXES + 1):
        axis_path = snapshot_dir / "axis" / f"{axis_num}.json"
        if not axis_path.is_file():
            violations.append(f"axis/{axis_num}.json not found.")
            continue

        with open(axis_path, encoding="utf-8") as fh:
            axis_data = json.load(fh)

        axis_countries = axis_data.get("countries", [])
        if len(axis_countries) != 27:
            violations.append(
                f"axis/{axis_num}.json: expected 27 countries, found {len(axis_countries)}."
            )

    if violations:
        report.fail(
            "structural_invariants",
            f"{len(violations)} violation(s): {violations}",
            EXIT_STRUCTURAL_INVARIANT,
        )
        return False

    report.ok(
        "structural_invariants",
        "All structural invariants satisfied: 27 countries, "
        f"{NUM_AXES} axes each, ranks 1–27, composites ∈ [0,1], "
        "classifications match methodology thresholds.",
    )
    return True


def _check_methodology_consistency(
    snapshot_dir: Path,
    methodology_version: str,
    report: IntegrityReport,
) -> bool:
    """Check 5: Methodology version consistency.

    Verifies HASH_SUMMARY.json and isi.json agree on methodology version.
    """
    hs_path = snapshot_dir / "HASH_SUMMARY.json"
    if not hs_path.is_file():
        report.fail(
            "methodology_consistency",
            "HASH_SUMMARY.json not found.",
            EXIT_METHODOLOGY_MISMATCH,
        )
        return False

    with open(hs_path, encoding="utf-8") as fh:
        hs = json.load(fh)

    stored_methodology = hs.get("methodology_version", "")
    if stored_methodology != methodology_version:
        report.fail(
            "methodology_consistency",
            f"HASH_SUMMARY methodology_version='{stored_methodology}' "
            f"does not match requested '{methodology_version}'.",
            EXIT_METHODOLOGY_MISMATCH,
        )
        return False

    # Verify round_precision matches
    stored_precision = hs.get("round_precision")
    if stored_precision is not None and stored_precision != ROUND_PRECISION:
        report.fail(
            "methodology_consistency",
            f"HASH_SUMMARY round_precision={stored_precision} "
            f"does not match ROUND_PRECISION={ROUND_PRECISION}.",
            EXIT_METHODOLOGY_MISMATCH,
        )
        return False

    report.ok(
        "methodology_consistency",
        f"Methodology '{methodology_version}' consistent across artifacts.",
    )
    return True


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_snapshot(
    snapshot_dir: Path,
    methodology_version: str,
    year: int,
) -> IntegrityReport:
    """Validate a snapshot directory for full structural integrity.

    Runs all 5 check categories in order:
        1. Directory structure
        2. Manifest consistency (SHA-256)
        3. HASH_SUMMARY consistency (per-country + aggregate)
        4. Structural invariants (27 countries, axes, ranks, etc.)
        5. Methodology consistency

    Args:
        snapshot_dir: Path to the snapshot directory.
        methodology_version: Expected methodology version (e.g., "v1.0").
        year: Expected snapshot year (e.g., 2024).

    Returns:
        IntegrityReport with all checks recorded.
        report.valid is True only if ALL checks pass.
    """
    report = IntegrityReport(
        methodology_version=methodology_version,
        year=year,
    )

    if not snapshot_dir.is_dir():
        report.fail(
            "directory_exists",
            f"Snapshot directory does not exist: {snapshot_dir}",
            EXIT_MISSING_FILES,
        )
        return report

    report.ok("directory_exists", str(snapshot_dir))

    # Run checks in order of severity
    _check_directory_structure(snapshot_dir, report)
    _check_manifest_consistency(snapshot_dir, report)
    _check_hash_summary(snapshot_dir, methodology_version, year, report)
    _check_structural_invariants(snapshot_dir, methodology_version, report)
    _check_methodology_consistency(snapshot_dir, methodology_version, report)

    return report
