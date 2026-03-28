"""
backend.cache — Per-Layer Caching and Compute Isolation

Provides deterministic, hash-keyed caching for pipeline layer outputs.
The API serves cached snapshots — it NEVER recomputes synchronously.

Design contract:
    - Cache key = (country, version, inputs_hash) — deterministic.
    - Cache is invalidated on version change or input change.
    - Cached results include timing and metadata.
    - Cache misses return None — they never trigger recomputation.
    - Thread-safe via simple dict (CPython GIL is sufficient here).

Honesty note:
    Caching does NOT improve correctness — it only improves performance.
    A correct but slow system is preferable to a fast but stale one.
    Cache invalidation is the ONLY structural risk.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# CACHE KEY GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def _canonical_json(obj: Any) -> str:
    """Serialize object to canonical JSON for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_cache_key(
    country: str,
    version: str,
    inputs: dict[str, Any],
) -> str:
    """Compute a deterministic cache key.

    Args:
        country: ISO-2 code.
        version: Methodology version string.
        inputs: Dict of input data that affects the computation.

    Returns:
        SHA-256 hex digest of the canonical (country, version, inputs).
    """
    payload = _canonical_json({
        "country": country,
        "version": version,
        "inputs": inputs,
    })
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_layer_cache_key(
    country: str,
    layer_name: str,
    version: str,
    input_keys: dict[str, Any],
) -> str:
    """Compute a deterministic cache key for a single layer.

    Args:
        country: ISO-2 code.
        layer_name: Name of the pipeline layer.
        version: Version string for the layer logic.
        input_keys: Dict of input values the layer consumes.

    Returns:
        SHA-256 hex digest.
    """
    payload = _canonical_json({
        "country": country,
        "layer": layer_name,
        "version": version,
        "inputs": input_keys,
    })
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# SNAPSHOT RESULT CACHE
# ═══════════════════════════════════════════════════════════════════════════

class SnapshotCache:
    """In-memory cache for computed country snapshots.

    Thread-safe under CPython GIL. Supports TTL-based expiry
    and version-aware invalidation.
    """

    def __init__(self, ttl_seconds: float = 3600.0, max_entries: int = 1000):
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour).
            max_entries: Maximum number of cached entries.
        """
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        if max_entries <= 0:
            raise ValueError(f"max_entries must be > 0, got {max_entries}")

        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, dict[str, Any]] = {}
        self._access_order: list[str] = []  # LRU tracking
        self._hits = 0
        self._misses = 0

    def get(self, cache_key: str) -> dict[str, Any] | None:
        """Retrieve a cached snapshot.

        Returns None on miss or expired entry. Never triggers recomputation.

        Args:
            cache_key: The cache key (from compute_cache_key).

        Returns:
            Cached snapshot dict, or None.
        """
        entry = self._store.get(cache_key)
        if entry is None:
            self._misses += 1
            return None

        # Check TTL
        if time.monotonic() - entry["_cached_at_mono"] > self._ttl:
            del self._store[cache_key]
            if cache_key in self._access_order:
                self._access_order.remove(cache_key)
            self._misses += 1
            return None

        self._hits += 1
        # Update access order
        if cache_key in self._access_order:
            self._access_order.remove(cache_key)
        self._access_order.append(cache_key)
        return entry["data"]

    def put(
        self,
        cache_key: str,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a computed snapshot in the cache.

        Args:
            cache_key: The cache key.
            data: The snapshot data to cache.
            metadata: Optional metadata (version, timing, etc.).
        """
        # Evict if at capacity (LRU)
        while len(self._store) >= self._max_entries and self._access_order:
            oldest_key = self._access_order.pop(0)
            self._store.pop(oldest_key, None)

        self._store[cache_key] = {
            "data": data,
            "metadata": metadata or {},
            "_cached_at_mono": time.monotonic(),
        }
        if cache_key in self._access_order:
            self._access_order.remove(cache_key)
        self._access_order.append(cache_key)

    def invalidate(self, cache_key: str) -> bool:
        """Remove a specific entry from the cache.

        Args:
            cache_key: The cache key to invalidate.

        Returns:
            True if the entry existed and was removed.
        """
        if cache_key in self._store:
            del self._store[cache_key]
            if cache_key in self._access_order:
                self._access_order.remove(cache_key)
            return True
        return False

    def invalidate_all(self) -> int:
        """Clear the entire cache.

        Returns:
            Number of entries that were cleared.
        """
        count = len(self._store)
        self._store.clear()
        self._access_order.clear()
        return count

    def invalidate_by_prefix(self, prefix: str) -> int:
        """Invalidate all entries whose keys start with a prefix.

        Args:
            prefix: Key prefix to match.

        Returns:
            Number of entries invalidated.
        """
        to_remove = [k for k in self._store if k.startswith(prefix)]
        for k in to_remove:
            del self._store[k]
            if k in self._access_order:
                self._access_order.remove(k)
        return len(to_remove)

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._store)

    @property
    def stats(self) -> dict[str, Any]:
        """Cache performance statistics."""
        total = self._hits + self._misses
        return {
            "size": self.size,
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "total_requests": total,
            "hit_rate": self._hits / total if total > 0 else 0.0,
        }
