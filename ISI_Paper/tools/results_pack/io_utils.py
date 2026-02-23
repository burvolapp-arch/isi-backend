"""
IO utilities: loading snapshot artifacts, SHA-256 hashing, writing outputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    """Load a JSON file. Raises FileNotFoundError with clear message."""
    if not path.is_file():
        raise FileNotFoundError(f"Required input not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any, *, indent: int = 2) -> None:
    """Write JSON with stable formatting. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=indent, ensure_ascii=False, sort_keys=False)
    # Ensure trailing newline
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def write_csv(path: Path, columns: tuple[str, ...] | list[str], rows: list[dict[str, Any]]) -> None:
    """Write CSV with explicit column ordering. Creates parent dirs."""
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_text(path: Path, content: str) -> None:
    """Write text file. Creates parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def collect_input_hashes(snapshot_dir: Path, registry_path: Path) -> dict[str, str]:
    """
    Compute SHA-256 for all input artifacts.
    Returns {relative_path: sha256_hex}.
    """
    result: dict[str, str] = {}

    # Registry
    result[str(registry_path)] = sha256_file(registry_path)

    # isi.json
    isi_path = snapshot_dir / "isi.json"
    result[str(isi_path)] = sha256_file(isi_path)

    # Country files
    country_dir = snapshot_dir / "country"
    if country_dir.is_dir():
        for p in sorted(country_dir.glob("*.json")):
            result[str(p)] = sha256_file(p)

    # Axis files
    axis_dir = snapshot_dir / "axis"
    if axis_dir.is_dir():
        for p in sorted(axis_dir.glob("*.json")):
            result[str(p)] = sha256_file(p)

    # Integrity files
    for name in ("MANIFEST.json", "HASH_SUMMARY.json", "SIGNATURE.json"):
        p = snapshot_dir / name
        if p.is_file():
            result[str(p)] = sha256_file(p)

    return result


def collect_output_hashes(output_dir: Path) -> dict[str, str]:
    """
    Compute SHA-256 for all output files.
    Returns {relative_path_from_output_dir: sha256_hex}.
    """
    result: dict[str, str] = {}
    for p in sorted(output_dir.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(output_dir))
            result[rel] = sha256_file(p)
    return result
