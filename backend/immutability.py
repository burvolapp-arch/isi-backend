"""
backend.immutability — Runtime immutability verification for ISI snapshots.

Enforces that snapshot directories are read-only at runtime.
In STRICT mode, the application refuses to start if any snapshot
file has write permissions or the snapshot directory is writable.

Design contract:
    - check_snapshot_immutability() scans all files in a snapshot directory.
    - Returns structured result: {immutable: bool, violations: list[str]}.
    - No writes. No modifications. Read-only inspection.
    - Called at startup in STRICT mode.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path


def check_snapshot_immutability(snapshot_dir: Path) -> dict:
    """Verify that a snapshot directory and all its files are read-only.

    Checks:
        - No file has user/group/other write permission.
        - Directories have no user write permission (traversable only).

    Args:
        snapshot_dir: Path to the snapshot directory (e.g., backend/snapshots/v1.0/2024).

    Returns:
        Dict with:
            immutable (bool): True if no violations found.
            violations (list[str]): List of violation descriptions.
    """
    violations: list[str] = []

    if not snapshot_dir.is_dir():
        return {"immutable": False, "violations": [f"Directory not found: {snapshot_dir.name}"]}

    # Check files
    for p in snapshot_dir.rglob("*"):
        if p.is_file():
            mode = p.stat().st_mode
            if mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
                rel = p.relative_to(snapshot_dir).as_posix()
                violations.append(f"File writable: {rel} (mode={oct(mode)})")

    # Check directories
    for p in [snapshot_dir] + list(snapshot_dir.rglob("*")):
        if p.is_dir():
            mode = p.stat().st_mode
            if mode & stat.S_IWUSR:
                rel = p.relative_to(snapshot_dir).as_posix() if p != snapshot_dir else "."
                violations.append(f"Directory writable: {rel} (mode={oct(mode)})")

    return {
        "immutable": len(violations) == 0,
        "violations": violations,
    }


def check_directory_not_writable(path: Path) -> bool:
    """Check whether a directory is NOT writable by the current process.

    Uses os.access() which checks the effective user's permissions,
    accounting for filesystem mounts (e.g., read-only mounts in containers).

    Returns:
        True if the directory is NOT writable (desired state).
        False if the directory IS writable (violation).
    """
    if not path.is_dir():
        return True  # Non-existent directories are trivially non-writable
    return not os.access(path, os.W_OK)
