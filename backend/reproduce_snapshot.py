"""
backend.reproduce_snapshot — Reproducibility verification for ISI snapshots.

Re-exports a snapshot into a temporary directory and compares:
    - HASH_SUMMARY.json (snapshot hash + country hashes)
    - MANIFEST.json (file hashes)
    - All JSON file bytes (byte-for-byte)

If re-export produces identical artifacts, the snapshot is reproducible.
If any difference is detected, the tool exits with a non-zero code.

Usage:
    python -m backend.reproduce_snapshot --methodology v1.0 --year 2024
    python -m backend.reproduce_snapshot --methodology v1.0 --year 2024 --json

Exit codes:
    0: Reproducible — re-export matches committed snapshot.
    1: Not reproducible — differences detected.
    2: Error — re-export failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


def sha256_file(filepath: Path) -> str:
    """SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as fh:
        while chunk := fh.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compare_snapshots(
    committed_dir: Path,
    reproduced_dir: Path,
) -> dict:
    """Compare a committed snapshot against a freshly reproduced one.

    Returns:
        Dict with:
            reproducible (bool): True if all checks pass.
            differences (list[str]): List of difference descriptions.
    """
    differences: list[str] = []

    # Files to skip in comparison (timestamps differ)
    timestamp_fields = {"computed_at", "generated_at"}

    # 1. Compare HASH_SUMMARY.json — snapshot hash and country hashes
    for name in ("HASH_SUMMARY.json",):
        committed = committed_dir / name
        reproduced = reproduced_dir / name

        if not committed.is_file():
            differences.append(f"Committed {name} missing")
            continue
        if not reproduced.is_file():
            differences.append(f"Reproduced {name} missing")
            continue

        with open(committed, encoding="utf-8") as fh:
            c_data = json.load(fh)
        with open(reproduced, encoding="utf-8") as fh:
            r_data = json.load(fh)

        # Compare stable fields (skip timestamps)
        for key in ("snapshot_hash", "country_hashes", "methodology_version", "year", "round_precision"):
            if c_data.get(key) != r_data.get(key):
                differences.append(f"{name}: field '{key}' differs")

    # 2. Compare MANIFEST.json — file hashes
    for name in ("MANIFEST.json",):
        committed = committed_dir / name
        reproduced = reproduced_dir / name

        if not committed.is_file() or not reproduced.is_file():
            differences.append(f"{name} missing from one side")
            continue

        with open(committed, encoding="utf-8") as fh:
            c_manifest = json.load(fh)
        with open(reproduced, encoding="utf-8") as fh:
            r_manifest = json.load(fh)

        c_files = {e["path"]: e["sha256"] for e in c_manifest.get("files", [])}
        r_files = {e["path"]: e["sha256"] for e in r_manifest.get("files", [])}

        for path, c_hash in c_files.items():
            if path not in r_files:
                differences.append(f"MANIFEST: {path} missing from reproduced")
            elif c_hash != r_files[path]:
                differences.append(f"MANIFEST: {path} hash differs")

        for path in r_files:
            if path not in c_files:
                differences.append(f"MANIFEST: {path} unexpected in reproduced")

    # 3. Byte-level comparison of data files (excluding meta files)
    meta_files = {"HASH_SUMMARY.json", "MANIFEST.json", "SIGNATURE.json"}
    committed_files = set()
    for p in committed_dir.rglob("*.json"):
        rel = p.relative_to(committed_dir).as_posix()
        if rel not in meta_files:
            committed_files.add(rel)

    reproduced_files = set()
    for p in reproduced_dir.rglob("*.json"):
        rel = p.relative_to(reproduced_dir).as_posix()
        if rel not in meta_files:
            reproduced_files.add(rel)

    for rel in sorted(committed_files | reproduced_files):
        c_path = committed_dir / rel
        r_path = reproduced_dir / rel

        if not c_path.is_file():
            differences.append(f"Byte check: {rel} missing from committed")
            continue
        if not r_path.is_file():
            differences.append(f"Byte check: {rel} missing from reproduced")
            continue

        if sha256_file(c_path) != sha256_file(r_path):
            differences.append(f"Byte check: {rel} bytes differ")

    return {
        "reproducible": len(differences) == 0,
        "differences": differences,
    }


def reproduce_and_compare(
    methodology: str,
    year: int,
    committed_root: Path | None = None,
) -> dict:
    """Re-export a snapshot and compare against the committed version.

    Args:
        methodology: Methodology version (e.g., "v1.0").
        year: Snapshot year (e.g., 2024).
        committed_root: Override snapshot root (default: backend/snapshots).

    Returns:
        Dict with: reproducible (bool), differences (list[str]).
    """
    from backend.export_snapshot import SNAPSHOTS_ROOT, materialize_snapshot

    if committed_root is None:
        committed_root = SNAPSHOTS_ROOT

    committed_dir = committed_root / methodology / str(year)
    if not committed_dir.is_dir():
        return {
            "reproducible": False,
            "differences": [f"Committed snapshot not found: {methodology}/{year}"],
        }

    with tempfile.TemporaryDirectory(prefix="isi_repro_") as tmp:
        tmp_path = Path(tmp)

        # Temporarily override SNAPSHOTS_ROOT for re-export
        import backend.export_snapshot as _exp

        original_root = _exp.SNAPSHOTS_ROOT
        _exp.SNAPSHOTS_ROOT = tmp_path

        try:
            _exp.materialize_snapshot(
                year=year,
                methodology_version=methodology,
                force=True,
                no_sign=True,  # Don't sign reproduced snapshot — compare data only
            )
        except SystemExit:
            return {
                "reproducible": False,
                "differences": ["Re-export failed (SystemExit)"],
            }
        except Exception as exc:
            return {
                "reproducible": False,
                "differences": [f"Re-export failed: {type(exc).__name__}: {exc}"],
            }
        finally:
            _exp.SNAPSHOTS_ROOT = original_root

        reproduced_dir = tmp_path / methodology / str(year)
        if not reproduced_dir.is_dir():
            return {
                "reproducible": False,
                "differences": ["Re-export did not produce expected directory"],
            }

        return compare_snapshots(committed_dir, reproduced_dir)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="reproduce_snapshot",
        description="Verify ISI snapshot reproducibility by re-exporting and comparing.",
    )
    parser.add_argument("--methodology", required=True, help="Methodology version (e.g., v1.0)")
    parser.add_argument("--year", type=int, required=True, help="Snapshot year (e.g., 2024)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON report")

    args = parser.parse_args(argv)

    result = reproduce_and_compare(args.methodology, args.year)

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        status = "REPRODUCIBLE" if result["reproducible"] else "NOT REPRODUCIBLE"
        print(f"Snapshot: {args.methodology}/{args.year}")
        print(f"Status:   {status}")
        if result["differences"]:
            print(f"\nDifferences ({len(result['differences'])}):")
            for d in result["differences"]:
                print(f"  • {d}")

    return 0 if result["reproducible"] else 1


if __name__ == "__main__":
    sys.exit(main())
