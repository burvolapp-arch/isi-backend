#!/usr/bin/env python3
"""
generate_manifest.py — Generate MANIFEST.json for backend/v01 artifacts.

Computes SHA-256 hashes for all JSON files in backend/v01/ and writes
a MANIFEST.json file that the API uses for data integrity verification
at startup.

Usage:
    python scripts/generate_manifest.py

No external dependencies — uses only Python stdlib.

Task: ISI-MANIFEST
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_V01 = PROJECT_ROOT / "backend" / "v01"


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


def main() -> None:
    if not BACKEND_V01.is_dir():
        print(
            f"FATAL: backend/v01 directory not found: {BACKEND_V01}\n"
            f"Run export_isi_backend_v01.py first to materialize JSON artifacts.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Collect all JSON files recursively, sorted for determinism
    json_files = sorted(BACKEND_V01.rglob("*.json"))

    # Exclude MANIFEST.json itself
    json_files = [f for f in json_files if f.name != "MANIFEST.json"]

    if not json_files:
        print("FATAL: No JSON files found in backend/v01/.", file=sys.stderr)
        sys.exit(1)

    print(f"Generating MANIFEST.json for {len(json_files)} files...")
    print()

    files_list = []
    for filepath in json_files:
        rel_path = filepath.relative_to(BACKEND_V01).as_posix()
        digest = sha256_file(filepath)
        size_bytes = filepath.stat().st_size
        files_list.append({
            "path": rel_path,
            "sha256": digest,
            "size_bytes": size_bytes,
        })
        print(f"  {rel_path}: {digest[:16]}... ({size_bytes:,} bytes)")

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "scripts/generate_manifest.py",
        "backend_version": "v0.1",
        "file_count": len(files_list),
        "files": files_list,
    }

    manifest_path = BACKEND_V01 / "MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    print()
    print(f"Wrote: {manifest_path}")
    print(f"Files: {len(files_list)}")
    print(f"Timestamp: {manifest['generated_at']}")
    print()
    print("Done. Commit MANIFEST.json alongside the data artifacts.")


if __name__ == "__main__":
    main()
