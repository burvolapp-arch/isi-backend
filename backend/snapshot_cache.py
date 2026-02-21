"""
backend.snapshot_cache — Thread-safe, bounded, keyed snapshot cache.

Replaces the flat ``_cache: dict[str, Any]`` in isi_api_v01.py with a
structured cache keyed by ``(methodology_version, year, artifact)``.

Design contract:
    - All snapshot data is loaded from disk exactly once per key.
    - Cache is bounded by MAX_CACHED_SNAPSHOTS (default 3) at the
      snapshot level (methodology, year). Individual artifacts within
      a cached snapshot do not count separately toward the bound.
    - LRU eviction: least-recently-used snapshot is evicted when
      a new snapshot exceeds the bound.
    - Thread-safe via threading.Lock.
    - No mutation of cached data. Read-only after load.
    - Backward-compatible: existing endpoints can use get_artifact()
      with the latest snapshot transparently.

Cache key design:
    Level 1: (methodology_version, year)  → SnapshotSlot
    Level 2: artifact string              → parsed JSON data

    Artifact naming convention:
        "isi"           → isi.json
        "country:SE"    → country/SE.json
        "axis:1"        → axis/1.json
        "hash_summary"  → HASH_SUMMARY.json
        "manifest"      → MANIFEST.json
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

logger = logging.getLogger("isi.cache")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_CACHED_SNAPSHOTS: int = int(os.getenv("MAX_CACHED_SNAPSHOTS", "3"))
"""Maximum number of (methodology, year) snapshot slots held in memory.
Controlled by MAX_CACHED_SNAPSHOTS env var. Default: 3."""

MAX_ARTIFACTS_PER_SNAPSHOT: int = 50
"""Hard cap on artifacts per snapshot slot. 36 expected (isi + manifest +
hash_summary + 6 axes + 27 countries) — 50 gives safe headroom.
Prevents unbounded memory growth from malformed artifact keys."""

# Strict allowlist regex for methodology version strings.
# Only vN.M format accepted — no traversal, no unicode, no spaces.
# Uses [0-9] (not \d which matches Unicode digits) with {1,10} length cap.
METHODOLOGY_RE: re.Pattern[str] = re.compile(r"^v[0-9]{1,10}\.[0-9]{1,10}\Z")
"""Methodology version must match ``^v[0-9]{1,10}\\.[0-9]{1,10}\\Z`` exactly."""

# Country code allowlist regex (strict ISO 3166-1 alpha-2 uppercase)
COUNTRY_CODE_RE: re.Pattern[str] = re.compile(r"^[A-Z]{2}$")

# Axis ID allowlist regex (single digit 1-9)
AXIS_ID_RE: re.Pattern[str] = re.compile(r"^[1-9]$")


# ---------------------------------------------------------------------------
# Artifact path resolution
# ---------------------------------------------------------------------------

def _artifact_to_path(snapshot_dir: Path, artifact: str) -> Path:
    """Map an artifact key to its filesystem path within a snapshot directory.

    Artifact keys:
        "isi"           → isi.json
        "country:{CODE}" → country/{CODE}.json
        "axis:{N}"      → axis/{N}.json
        "hash_summary"  → HASH_SUMMARY.json
        "manifest"      → MANIFEST.json
        "signature"     → SIGNATURE.json

    Raises ValueError for unrecognised artifact keys.
    Raises ValueError if resolved path escapes the snapshot directory
    (path traversal guard).
    """
    # Reject overlong artifact keys (max 64 chars)
    if len(artifact) > 64:
        raise ValueError(f"Artifact key too long: {len(artifact)} chars (max 64)")

    if artifact == "isi":
        resolved = snapshot_dir / "isi.json"
    elif artifact == "hash_summary":
        resolved = snapshot_dir / "HASH_SUMMARY.json"
    elif artifact == "manifest":
        resolved = snapshot_dir / "MANIFEST.json"
    elif artifact == "signature":
        resolved = snapshot_dir / "SIGNATURE.json"
    elif artifact.startswith("country:"):
        code = artifact[8:]  # len("country:") == 8
        if not COUNTRY_CODE_RE.match(code):
            raise ValueError(
                f"Invalid country code in artifact key: '{code}'. "
                f"Must be exactly 2 uppercase ASCII letters."
            )
        resolved = snapshot_dir / "country" / f"{code}.json"
    elif artifact.startswith("axis:"):
        axis_id = artifact[5:]  # len("axis:") == 5
        if not AXIS_ID_RE.match(axis_id):
            raise ValueError(
                f"Invalid axis ID in artifact key: '{axis_id}'. "
                f"Must be a single digit 1-9."
            )
        resolved = snapshot_dir / "axis" / f"{axis_id}.json"
    else:
        raise ValueError(f"Unknown artifact key: '{artifact}'")

    # Path traversal guard: resolved path must stay within snapshot_dir.
    try:
        resolved.resolve().relative_to(snapshot_dir.resolve())
    except ValueError:
        raise ValueError(
            f"Path traversal detected: artifact '{artifact}' resolves to "
            f"{resolved.resolve()}, which is outside {snapshot_dir.resolve()}."
        )

    return resolved


# ---------------------------------------------------------------------------
# SnapshotCache
# ---------------------------------------------------------------------------

class SnapshotCache:
    """Thread-safe, bounded, LRU cache for snapshot artifacts.

    Usage::

        cache = SnapshotCache()

        # Load an artifact from a resolved snapshot path
        data = cache.get_artifact(
            methodology_version="v1.0",
            year=2024,
            artifact="isi",
            snapshot_dir=Path("backend/snapshots/v1.0/2024"),
        )

        # data is the parsed JSON, cached for subsequent calls
    """

    def __init__(self, max_snapshots: int | None = None) -> None:
        self._max: int = max_snapshots if max_snapshots is not None else MAX_CACHED_SNAPSHOTS
        self._lock: threading.Lock = threading.Lock()
        # OrderedDict keyed by (methodology_version, year)
        # Values are dicts mapping artifact → parsed JSON
        self._slots: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()
        # Pinned mtimes for tamper detection — {slot_key: {artifact: mtime}}
        self._mtimes: dict[tuple[str, int], dict[str, float]] = {}

    def get_artifact(
        self,
        methodology_version: str,
        year: int,
        artifact: str,
        snapshot_dir: Path,
    ) -> Any:
        """Get a cached artifact, loading from disk if necessary.

        Args:
            methodology_version: e.g. "v1.0"
            year: e.g. 2024
            artifact: e.g. "isi", "country:SE", "axis:1"
            snapshot_dir: Filesystem path to the snapshot directory.

        Returns:
            Parsed JSON data (dict or list). None if file does not exist.

        Thread-safety:
            Lock is held only during dict operations, not during disk I/O.
            This means two threads may both attempt to load the same file
            concurrently. The last writer wins, but since snapshot data is
            immutable and deterministic, both will produce identical results.

        Defensive checks:
            - methodology_version and year must be non-empty / positive.
            - Artifact path must stay within snapshot_dir (no traversal).
            - Eviction is atomic at snapshot-level (entire slot removed).
        """
        # --- Defensive assertions ---
        if not methodology_version or not isinstance(methodology_version, str):
            raise ValueError(
                f"methodology_version must be a non-empty string, "
                f"got {methodology_version!r}"
            )
        if not METHODOLOGY_RE.match(methodology_version):
            raise ValueError(
                f"methodology_version must match {METHODOLOGY_RE.pattern!r}, "
                f"got {methodology_version!r}"
            )
        if not isinstance(year, int) or year <= 0:
            raise ValueError(f"year must be a positive integer, got {year!r}")

        slot_key = (methodology_version, year)

        with self._lock:
            if slot_key in self._slots:
                self._slots.move_to_end(slot_key)
                slot = self._slots[slot_key]
                if artifact in slot:
                    return slot[artifact]
            else:
                slot = None

        # Load from disk (outside lock)
        # _artifact_to_path includes path traversal guard + allowlist checks
        filepath = _artifact_to_path(snapshot_dir, artifact)

        # Mtime pinning — record file mtime on first load, detect changes
        file_mtime = filepath.stat().st_mtime if filepath.is_file() else None
        data = self._load_json(filepath)

        with self._lock:
            if slot_key not in self._slots:
                # New snapshot slot — atomic eviction of entire oldest slot
                while len(self._slots) >= self._max:
                    evicted_key, evicted_slot = self._slots.popitem(last=False)
                    artifact_count = len(evicted_slot)
                    evicted_slot.clear()  # Explicit clear — no partial retention
                    logger.info(
                        "Cache eviction: %s/%s (%d artifacts, max_snapshots=%d)",
                        evicted_key[0], evicted_key[1], artifact_count, self._max,
                    )
                self._slots[slot_key] = {}
                self._mtimes[slot_key] = {}

            # Artifact count cap — refuse to cache beyond MAX_ARTIFACTS_PER_SNAPSHOT
            if len(self._slots[slot_key]) >= MAX_ARTIFACTS_PER_SNAPSHOT:
                logger.warning(
                    "Artifact count cap reached for %s/%s (%d). "
                    "Artifact '%s' served but not cached.",
                    methodology_version, year,
                    MAX_ARTIFACTS_PER_SNAPSHOT, artifact,
                )
                return data

            self._slots.move_to_end(slot_key)
            self._slots[slot_key][artifact] = data

            # Pin mtime for tamper detection
            if slot_key not in self._mtimes:
                self._mtimes[slot_key] = {}
            if file_mtime is not None:
                self._mtimes[slot_key][artifact] = file_mtime

        return data

    def check_tamper(
        self,
        methodology_version: str,
        year: int,
        snapshot_dir: Path,
    ) -> list[str]:
        """Check cached artifacts for filesystem tampering.

        Compares pinned mtimes with current filesystem mtimes.
        Returns list of tampered artifact names (empty = clean).

        If tampering is detected, the entire snapshot slot is
        atomically invalidated from cache.
        """
        slot_key = (methodology_version, year)
        tampered: list[str] = []

        with self._lock:
            pinned = self._mtimes.get(slot_key, {})
            if not pinned:
                return tampered
            # Copy to iterate outside lock
            pinned_copy = dict(pinned)

        for artifact, original_mtime in pinned_copy.items():
            try:
                filepath = _artifact_to_path(snapshot_dir, artifact)
                if not filepath.is_file():
                    tampered.append(artifact)
                    continue
                current_mtime = filepath.stat().st_mtime
                if current_mtime != original_mtime:
                    tampered.append(artifact)
            except (ValueError, OSError):
                tampered.append(artifact)

        if tampered:
            # Atomic invalidation — drop entire slot
            with self._lock:
                self._slots.pop(slot_key, None)
                self._mtimes.pop(slot_key, None)
            logger.warning(
                "Tamper detected in %s/%s — %d artifacts modified. "
                "Cache slot invalidated.",
                methodology_version, year, len(tampered),
            )

        return tampered

    def invalidate(
        self,
        methodology_version: str | None = None,
        year: int | None = None,
    ) -> int:
        """Invalidate cached data.

        Args:
            methodology_version: If provided with year, invalidate that
                specific snapshot slot. If both None, invalidate all.
            year: See above.

        Returns:
            Number of slots invalidated.
        """
        with self._lock:
            if methodology_version is not None and year is not None:
                key = (methodology_version, year)
                if key in self._slots:
                    del self._slots[key]
                    self._mtimes.pop(key, None)
                    return 1
                return 0
            else:
                count = len(self._slots)
                self._slots.clear()
                self._mtimes.clear()
                return count

    @property
    def snapshot_count(self) -> int:
        """Number of snapshot slots currently cached."""
        with self._lock:
            return len(self._slots)

    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics for diagnostics."""
        with self._lock:
            slots_info = []
            for (mv, yr), artifacts in self._slots.items():
                slots_info.append({
                    "methodology_version": mv,
                    "year": yr,
                    "artifacts_cached": len(artifacts),
                })
            return {
                "max_snapshots": self._max,
                "slots_used": len(self._slots),
                "slots": slots_info,
            }

    @staticmethod
    def _load_json(filepath: Path) -> Any:
        """Load and parse a JSON file. Returns None if file does not exist."""
        if not filepath.is_file():
            return None
        with open(filepath, encoding="utf-8") as fh:
            return json.load(fh)
