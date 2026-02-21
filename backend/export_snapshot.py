#!/usr/bin/env python3
"""
export_snapshot.py — ISI Snapshot Materializer (v2)

Parameterized exporter that reads year-specific CSVs, computes per-country
hashes, and writes an atomic, immutable snapshot to:

    backend/snapshots/{methodology}/{year}/

This replaces the monolithic export_isi_backend_v01.py for snapshot production.
The old exporter remains functional for backward-compatible backend/v01/ output.

Usage:
    python -m backend.export_snapshot --year 2024 --methodology v1.0
    python -m backend.export_snapshot --year 2024 --methodology v1.0 --force

Protocol:
    1. Write to .tmp_{methodology}_{year}_{uuid}/
    2. Verify all hashes.
    3. Write HASH_SUMMARY.json (last file).
    4. Atomic os.rename() to final directory.
    5. Set files read-only (chmod 0o444).

Hard constraints:
    - All floats rounded via ROUND_PRECISION.
    - All JSON written with sort_keys=True.
    - All sorting includes deterministic tie-breaker.
    - If snapshot directory already exists → abort (freeze policy).
    - If any hash mismatch → abort.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import stat
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.constants import (
    COUNTRY_NAMES,
    EU27_CODES,
    EU27_SORTED,
    ISI_AXIS_KEYS,
    NUM_AXES,
    ROUND_PRECISION,
)
from backend.hashing import (
    canonical_float,
    compute_country_hash,
    compute_snapshot_hash,
)
from backend.methodology import classify, compute_composite, get_methodology

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "processed"
SNAPSHOTS_ROOT = PROJECT_ROOT / "backend" / "snapshots"

# ---------------------------------------------------------------------------
# Axis registry — maps axis number to CSV metadata
#
# For v2 snapshots, we only need the final score CSV per axis.
# The full AXIS_REGISTRY with channel/audit detail remains in the
# legacy exporter for backend/v01/ backward compatibility.
# ---------------------------------------------------------------------------

AXIS_SCORE_FILES: dict[int, dict[str, str]] = {
    1: {
        "slug": "financial",
        "data_dir": "finance",
        "final_file": "finance_dependency_{year}_eu27.csv",
        "score_column": "finance_dependency",
        "country_key": "geo",
    },
    2: {
        "slug": "energy",
        "data_dir": "energy",
        "final_file": "energy_dependency_{year}_eu27.csv",
        "score_column": "energy_dependency",
        "country_key": "geo",
    },
    3: {
        "slug": "technology",
        "data_dir": "tech",
        "final_file": "tech_dependency_{year}_eu27.csv",
        "score_column": "tech_dependency",
        "country_key": "geo",
    },
    4: {
        "slug": "defense",
        "data_dir": "defense",
        "final_file": "defense_dependency_{year}_eu27.csv",
        "score_column": "defense_dependency",
        "country_key": "geo",
    },
    5: {
        "slug": "critical_inputs",
        "data_dir": "critical_inputs",
        "final_file": "critical_inputs_dependency_{year}_eu27.csv",
        "score_column": "critical_inputs_dependency",
        "country_key": "geo",
    },
    6: {
        "slug": "logistics",
        "data_dir": "logistics",
        "final_file": "logistics_freight_axis_score.csv",
        "score_column": "axis6_logistics_score",
        "country_key": "reporter",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fatal(msg: str) -> None:
    """Print error and exit."""
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(filepath: Path) -> list[dict[str, str]]:
    """Read a CSV file. Returns list of dicts. Hard-fails if file missing."""
    if not filepath.is_file():
        fatal(f"File not found: {filepath}")
    with open(filepath, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_float(val: str, context: str) -> float:
    """Parse a string to float. Hard-fail on bad values."""
    try:
        f = float(val)
    except (ValueError, TypeError):
        fatal(f"Non-numeric value '{val}' in {context}")
    if math.isnan(f) or math.isinf(f):
        fatal(f"NaN/Inf value in {context}")
    return f


def write_canonical_json(filepath: Path, data: object) -> None:
    """Write JSON in canonical form: sort_keys=True, UTF-8, trailing newline.

    This is NOT atomic by itself — the atomic protocol wraps this
    via the temp-dir → rename dance in materialize_snapshot().
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    content += "\n"
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(content)


def sha256_file(filepath: Path) -> str:
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
# Data loading
# ---------------------------------------------------------------------------

def load_axis_scores(axis_num: int, year: int) -> dict[str, float]:
    """Load final scores for one axis from CSV.

    Returns {country_code: rounded_score}.
    """
    spec = AXIS_SCORE_FILES[axis_num]
    filename = spec["final_file"].format(year=year)
    filepath = DATA_ROOT / spec["data_dir"] / filename
    rows = read_csv(filepath)

    if not rows:
        fatal(f"Axis {axis_num}: zero rows in {filepath}")

    score_col = spec["score_column"]
    country_col = spec["country_key"]
    eu27_set = EU27_CODES
    scores: dict[str, float] = {}

    for row in rows:
        geo = row.get(country_col, "").strip()
        if geo not in eu27_set:
            continue
        raw = row.get(score_col, "").strip()
        s = parse_float(raw, f"axis {axis_num}, country {geo}")
        if s < 0.0 or s > 1.0:
            fatal(f"Axis {axis_num}: score {s} out of [0,1] for {geo}")
        if geo in scores:
            fatal(f"Axis {axis_num}: duplicate country {geo}")
        scores[geo] = round(s, ROUND_PRECISION)

    missing = eu27_set - set(scores.keys())
    if missing:
        fatal(f"Axis {axis_num}: missing EU-27 countries: {sorted(missing)}")

    return scores


# ---------------------------------------------------------------------------
# Snapshot building
# ---------------------------------------------------------------------------

def build_isi_json(
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
) -> dict:
    """Build isi.json: composite scores for all 27 countries.

    Response shape matches existing backend/v01/isi.json exactly.
    """
    rows = []
    for country in EU27_SORTED:
        axis_scores_isi: dict[str, float] = {}
        complete = True
        for axis_num in range(1, NUM_AXES + 1):
            s = all_scores.get(axis_num, {}).get(country)
            if s is not None:
                key = ISI_AXIS_KEYS[axis_num - 1]
                axis_scores_isi[key] = s
            else:
                complete = False

        if complete and len(axis_scores_isi) == NUM_AXES:
            raw_composite = compute_composite(axis_scores_isi, methodology_version)
            composite = round(raw_composite, ROUND_PRECISION)
        else:
            composite = None

        row = {
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
        }
        for axis_num in range(1, NUM_AXES + 1):
            key = ISI_AXIS_KEYS[axis_num - 1]
            row[key] = axis_scores_isi.get(key)
        row["isi_composite"] = composite
        row["classification"] = classify(composite, methodology_version) if composite is not None else None
        row["complete"] = complete
        rows.append(row)

    # Sort: descending by composite, tie-break alphabetical by country (D-2 fix)
    rows.sort(key=lambda x: (-(x["isi_composite"] if x["isi_composite"] is not None else -1.0), x["country"]))

    vals = [r["isi_composite"] for r in rows if r["isi_composite"] is not None]

    return {
        "version": methodology_version,
        "window": data_window,
        "aggregation_rule": "unweighted_arithmetic_mean",
        "formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
        "countries_complete": len(vals),
        "countries_total": len(EU27_SORTED),
        "statistics": {
            "min": round(min(vals), ROUND_PRECISION) if vals else None,
            "max": round(max(vals), ROUND_PRECISION) if vals else None,
            "mean": round(sum(vals) / len(vals), ROUND_PRECISION) if vals else None,
        },
        "countries": rows,
    }


def build_country_json(
    country: str,
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
) -> dict:
    """Build per-country detail JSON.

    Simplified shape for v2 snapshots (no channel/audit detail —
    that lives in the full country files produced by the legacy exporter).
    """
    name = COUNTRY_NAMES.get(country, country)
    axes_detail = []
    score_sum = 0.0
    axes_with_data = 0

    for axis_num in range(1, NUM_AXES + 1):
        slug = AXIS_SCORE_FILES[axis_num]["slug"]
        score = all_scores.get(axis_num, {}).get(country)

        axis_entry: dict[str, Any] = {
            "axis_id": axis_num,
            "axis_slug": slug,
        }

        if score is not None:
            axis_entry["score"] = score
            axis_entry["classification"] = classify(score, methodology_version)
            score_sum += score
            axes_with_data += 1
        else:
            axis_entry["score"] = None
            axis_entry["classification"] = None

        axes_detail.append(axis_entry)

    if axes_with_data == NUM_AXES:
        raw_composite = score_sum / NUM_AXES
        composite = round(raw_composite, ROUND_PRECISION)
    else:
        composite = None

    return {
        "country": country,
        "country_name": name,
        "version": methodology_version,
        "year": year,
        "window": data_window,
        "isi_composite": composite,
        "isi_classification": classify(composite, methodology_version) if composite is not None else None,
        "axes_available": axes_with_data,
        "axes_required": NUM_AXES,
        "axes": axes_detail,
    }


def build_axis_json(
    axis_num: int,
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
) -> dict:
    """Build per-axis detail JSON across all countries."""
    slug = AXIS_SCORE_FILES[axis_num]["slug"]
    scores = all_scores.get(axis_num, {})

    countries = []
    for country in EU27_SORTED:
        score = scores.get(country)
        entry: dict[str, Any] = {
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
        }
        if score is not None:
            entry["score"] = score
            entry["classification"] = classify(score, methodology_version)
        else:
            entry["score"] = None
            entry["classification"] = None
        countries.append(entry)

    # Sort by score descending, tie-break alphabetical by country (D-2 fix)
    countries.sort(key=lambda x: (-(x["score"] if x["score"] is not None else -1.0), x["country"]))

    vals = [c["score"] for c in countries if c["score"] is not None]

    return {
        "axis_id": axis_num,
        "axis_slug": slug,
        "version": methodology_version,
        "year": year,
        "countries_scored": len(vals),
        "statistics": {
            "min": round(min(vals), ROUND_PRECISION) if vals else None,
            "max": round(max(vals), ROUND_PRECISION) if vals else None,
            "mean": round(sum(vals) / len(vals), ROUND_PRECISION) if vals else None,
        },
        "countries": countries,
    }


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

def compute_all_hashes(
    all_scores: dict[int, dict[str, float]],
    methodology_version: str,
    year: int,
    data_window: str,
    methodology_params: dict,
) -> tuple[dict[str, str], str]:
    """Compute per-country and snapshot-level hashes.

    Returns (country_hashes, snapshot_hash).
    """
    country_hashes: dict[str, str] = {}

    for country in EU27_SORTED:
        # Build axis_scores dict keyed by slug
        axis_scores_by_slug: dict[str, float] = {}
        for axis_num in range(1, NUM_AXES + 1):
            slug = AXIS_SCORE_FILES[axis_num]["slug"]
            score = all_scores.get(axis_num, {}).get(country)
            if score is not None:
                axis_scores_by_slug[slug] = score

        if len(axis_scores_by_slug) != NUM_AXES:
            fatal(f"Country {country}: incomplete axis scores ({len(axis_scores_by_slug)}/{NUM_AXES})")

        # Compute composite (already rounded in all_scores)
        isi_axes = {}
        for axis_num in range(1, NUM_AXES + 1):
            key = ISI_AXIS_KEYS[axis_num - 1]
            isi_axes[key] = all_scores[axis_num][country]

        raw_composite = compute_composite(isi_axes, methodology_version)
        composite = round(raw_composite, ROUND_PRECISION)

        h = compute_country_hash(
            country_code=country,
            year=year,
            methodology_version=methodology_version,
            axis_scores=axis_scores_by_slug,
            composite=composite,
            data_window=data_window,
            methodology_params=methodology_params,
        )
        country_hashes[country] = h

    snapshot_hash = compute_snapshot_hash(country_hashes)
    return country_hashes, snapshot_hash


# ---------------------------------------------------------------------------
# MANIFEST generation
# ---------------------------------------------------------------------------

def generate_manifest(snapshot_dir: Path) -> dict:
    """Generate MANIFEST.json for a snapshot directory.

    Computes SHA-256 for every JSON file in the snapshot (excluding MANIFEST.json
    and HASH_SUMMARY.json themselves).
    """
    files = []
    for filepath in sorted(snapshot_dir.rglob("*.json")):
        rel = filepath.relative_to(snapshot_dir)
        if rel.name in ("MANIFEST.json", "HASH_SUMMARY.json"):
            continue
        files.append({
            "path": str(rel),
            "sha256": sha256_file(filepath),
            "size_bytes": filepath.stat().st_size,
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "generator": "export_snapshot.py",
        "file_count": len(files),
        "files": files,
    }


# ---------------------------------------------------------------------------
# Filesystem protection
# ---------------------------------------------------------------------------

def make_readonly(directory: Path) -> None:
    """Remove write permissions from all files in a snapshot directory."""
    for f in directory.rglob("*"):
        if f.is_file():
            f.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444
    directory.chmod(
        stat.S_IRUSR | stat.S_IXUSR |
        stat.S_IRGRP | stat.S_IXGRP |
        stat.S_IROTH | stat.S_IXOTH
    )  # 0o555
    # Make subdirectories traversable
    for d in directory.rglob("*"):
        if d.is_dir():
            d.chmod(
                stat.S_IRUSR | stat.S_IXUSR |
                stat.S_IRGRP | stat.S_IXGRP |
                stat.S_IROTH | stat.S_IXOTH
            )  # 0o555


def cleanup_partial_snapshots() -> int:
    """Remove any temp directories from failed materializations."""
    removed = 0
    if not SNAPSHOTS_ROOT.is_dir():
        return removed
    for d in SNAPSHOTS_ROOT.iterdir():
        if d.is_dir() and d.name.startswith(".tmp_"):
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Main materialization
# ---------------------------------------------------------------------------

def materialize_snapshot(
    year: int,
    methodology_version: str,
    *,
    force: bool = False,
) -> Path:
    """Materialize a complete snapshot atomically.

    1. Load methodology from registry.
    2. Load all axis scores from CSVs.
    3. Compute hashes.
    4. Write to temp directory.
    5. Verify.
    6. Atomic rename to final location.
    7. Set read-only.

    Returns the final snapshot directory path.
    """
    # ── LOAD METHODOLOGY ──
    methodology = get_methodology(methodology_version)
    data_window = f"2022\u20132024"  # TODO: derive from methodology/year when multi-year data exists

    print(f"Materializing snapshot: {methodology_version}/{year}")
    print(f"  Methodology: {methodology['label']}")
    print(f"  Data window: {data_window}")
    print()

    # ── FREEZE ENFORCEMENT ──
    final_dir = SNAPSHOTS_ROOT / methodology_version / str(year)
    if final_dir.exists() and not force:
        fatal(
            f"FREEZE VIOLATION: Snapshot {methodology_version}/{year} already exists at {final_dir}. "
            f"Historical snapshots are immutable. "
            f"To publish revised data, register a new methodology version. "
            f"Use --force to override (development only)."
        )

    if final_dir.exists() and force:
        print(f"  WARNING: --force specified. Removing existing snapshot at {final_dir}")
        # Need to make writable first if read-only
        for f in final_dir.rglob("*"):
            if f.is_file():
                f.chmod(stat.S_IWUSR | stat.S_IRUSR)
        for d in [final_dir] + list(final_dir.rglob("*")):
            if d.is_dir():
                d.chmod(stat.S_IRWXU)
        shutil.rmtree(final_dir)
        print()

    # ── LOAD AXIS SCORES ──
    print("Phase 1: Loading axis scores...")
    all_scores: dict[int, dict[str, float]] = {}
    for axis_num in range(1, NUM_AXES + 1):
        scores = load_axis_scores(axis_num, year)
        all_scores[axis_num] = scores
        slug = AXIS_SCORE_FILES[axis_num]["slug"]
        print(f"  Axis {axis_num} ({slug}): {len(scores)} countries")
    print()

    # ── COMPUTE HASHES ──
    print("Phase 2: Computing hashes...")
    country_hashes, snapshot_hash = compute_all_hashes(
        all_scores, methodology_version, year, data_window, methodology,
    )
    print(f"  Snapshot hash: {snapshot_hash[:16]}...")
    print()

    # ── TEMP DIRECTORY ──
    temp_name = f".tmp_{methodology_version}_{year}_{uuid.uuid4().hex[:8]}"
    temp_dir = SNAPSHOTS_ROOT / temp_name
    temp_dir.mkdir(parents=True, exist_ok=False)

    try:
        # ── WRITE SNAPSHOT FILES ──
        print("Phase 3: Writing snapshot files...")

        # isi.json
        isi_data = build_isi_json(all_scores, methodology_version, year, data_window)
        write_canonical_json(temp_dir / "isi.json", isi_data)
        print(f"  isi.json ({isi_data['countries_complete']} countries)")

        # country/{CODE}.json
        for country in EU27_SORTED:
            detail = build_country_json(country, all_scores, methodology_version, year, data_window)
            write_canonical_json(temp_dir / "country" / f"{country}.json", detail)
        print(f"  country/*.json ({len(EU27_SORTED)} files)")

        # axis/{n}.json
        for axis_num in range(1, NUM_AXES + 1):
            detail = build_axis_json(axis_num, all_scores, methodology_version, year, data_window)
            write_canonical_json(temp_dir / "axis" / f"{axis_num}.json", detail)
        print(f"  axis/*.json ({NUM_AXES} files)")

        # MANIFEST.json (hashes of data files only)
        manifest = generate_manifest(temp_dir)
        write_canonical_json(temp_dir / "MANIFEST.json", manifest)
        print(f"  MANIFEST.json ({manifest['file_count']} files tracked)")

        # HASH_SUMMARY.json (computation hashes — LAST file written)
        hash_summary = {
            "schema_version": 1,
            "year": year,
            "methodology_version": methodology_version,
            "snapshot_hash": snapshot_hash,
            "computed_at": datetime.now(UTC).isoformat(),
            "computed_by": f"export_snapshot.py",
            "round_precision": ROUND_PRECISION,
            "country_hashes": country_hashes,
        }
        write_canonical_json(temp_dir / "HASH_SUMMARY.json", hash_summary)
        print(f"  HASH_SUMMARY.json (snapshot_hash={snapshot_hash[:16]}...)")
        print()

        # ── VERIFY COMPLETENESS ──
        print("Phase 4: Verifying...")
        expected_files = 1 + len(EU27_SORTED) + NUM_AXES + 1 + 1  # isi + countries + axes + manifest + hash_summary
        actual_files = len(list(temp_dir.rglob("*.json")))
        if actual_files != expected_files:
            fatal(f"Expected {expected_files} files, found {actual_files}")
        print(f"  File count: {actual_files}/{expected_files} ✓")

        # Verify MANIFEST hashes match actual files
        for entry in manifest["files"]:
            filepath = temp_dir / entry["path"]
            actual_hash = sha256_file(filepath)
            if actual_hash != entry["sha256"]:
                fatal(f"MANIFEST hash mismatch: {entry['path']}")
        print(f"  MANIFEST verification: {manifest['file_count']} files ✓")

        # Verify snapshot hash is reproducible
        country_hashes_2, snapshot_hash_2 = compute_all_hashes(
            all_scores, methodology_version, year, data_window, methodology,
        )
        if snapshot_hash_2 != snapshot_hash:
            fatal("Snapshot hash is NOT reproducible — determinism violation")
        print(f"  Hash reproducibility: ✓")
        print()

        # ── ATOMIC PROMOTION ──
        print("Phase 5: Promoting snapshot...")

        # Ensure parent directory exists
        final_dir.parent.mkdir(parents=True, exist_ok=True)

        os.rename(temp_dir, final_dir)
        print(f"  Renamed {temp_dir.name} → {final_dir}")

        # ── MAKE READ-ONLY ──
        make_readonly(final_dir)
        print(f"  Permissions set to read-only")

    except Exception:
        # Clean up temp directory on ANY failure
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    # ── SUMMARY ──
    print()
    print("═" * 60)
    print(f"  SNAPSHOT MATERIALIZED: {methodology_version}/{year}")
    print(f"  Location:      {final_dir}")
    print(f"  Files:         {actual_files}")
    print(f"  Snapshot hash: {snapshot_hash}")
    print("═" * 60)

    return final_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="ISI Snapshot Materializer — produces immutable snapshot directories.",
    )
    parser.add_argument("--year", type=int, required=True, help="Reference year (e.g., 2024)")
    parser.add_argument("--methodology", type=str, required=True, help="Methodology version (e.g., v1.0)")
    parser.add_argument("--force", action="store_true", help="Override freeze protection (development only)")
    parser.add_argument("--cleanup", action="store_true", help="Clean up partial snapshots before materializing")

    args = parser.parse_args()

    if args.cleanup:
        removed = cleanup_partial_snapshots()
        if removed:
            print(f"Cleaned up {removed} partial snapshot(s)")
        else:
            print("No partial snapshots found")
        print()

    materialize_snapshot(
        year=args.year,
        methodology_version=args.methodology,
        force=args.force,
    )


if __name__ == "__main__":
    main()
