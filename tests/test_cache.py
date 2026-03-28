"""
tests/test_cache.py — Tests for SnapshotCache and Cache Key Generation

Verifies:
    1. Cache keys are deterministic.
    2. Cache stores and retrieves correctly.
    3. TTL expiry works.
    4. LRU eviction works.
    5. Invalidation works (single, all, prefix).
    6. Stats tracking is correct.
"""

from __future__ import annotations

import time
import unittest

from backend.cache import (
    compute_cache_key,
    compute_layer_cache_key,
    SnapshotCache,
)


class TestCacheKeyGeneration(unittest.TestCase):
    """Cache key determinism tests."""

    def test_same_inputs_same_key(self):
        k1 = compute_cache_key("DE", "v0.1", {"axes": {1: 0.5}})
        k2 = compute_cache_key("DE", "v0.1", {"axes": {1: 0.5}})
        self.assertEqual(k1, k2)

    def test_different_country_different_key(self):
        k1 = compute_cache_key("DE", "v0.1", {"axes": {1: 0.5}})
        k2 = compute_cache_key("FR", "v0.1", {"axes": {1: 0.5}})
        self.assertNotEqual(k1, k2)

    def test_different_version_different_key(self):
        k1 = compute_cache_key("DE", "v0.1", {"axes": {1: 0.5}})
        k2 = compute_cache_key("DE", "v0.2", {"axes": {1: 0.5}})
        self.assertNotEqual(k1, k2)

    def test_different_inputs_different_key(self):
        k1 = compute_cache_key("DE", "v0.1", {"axes": {1: 0.5}})
        k2 = compute_cache_key("DE", "v0.1", {"axes": {1: 0.6}})
        self.assertNotEqual(k1, k2)

    def test_key_is_hex_string(self):
        k = compute_cache_key("DE", "v0.1", {})
        self.assertEqual(len(k), 64)  # SHA-256 hex
        self.assertTrue(all(c in "0123456789abcdef" for c in k))

    def test_layer_cache_key_deterministic(self):
        k1 = compute_layer_cache_key("DE", "severity", "1.0.0", {"axes": {}})
        k2 = compute_layer_cache_key("DE", "severity", "1.0.0", {"axes": {}})
        self.assertEqual(k1, k2)

    def test_layer_cache_key_different_layer(self):
        k1 = compute_layer_cache_key("DE", "severity", "1.0.0", {})
        k2 = compute_layer_cache_key("DE", "governance", "1.0.0", {})
        self.assertNotEqual(k1, k2)


class TestSnapshotCacheBasics(unittest.TestCase):
    """Basic cache operations."""

    def test_put_and_get(self):
        cache = SnapshotCache()
        cache.put("key1", {"country": "DE", "score": 0.5})
        result = cache.get("key1")
        self.assertIsNotNone(result)
        self.assertEqual(result["country"], "DE")

    def test_miss_returns_none(self):
        cache = SnapshotCache()
        result = cache.get("nonexistent")
        self.assertIsNone(result)

    def test_size_tracks_entries(self):
        cache = SnapshotCache()
        self.assertEqual(cache.size, 0)
        cache.put("k1", {"a": 1})
        self.assertEqual(cache.size, 1)
        cache.put("k2", {"b": 2})
        self.assertEqual(cache.size, 2)

    def test_overwrite_same_key(self):
        cache = SnapshotCache()
        cache.put("k1", {"version": 1})
        cache.put("k1", {"version": 2})
        self.assertEqual(cache.size, 1)
        self.assertEqual(cache.get("k1")["version"], 2)


class TestSnapshotCacheTTL(unittest.TestCase):
    """TTL expiry tests."""

    def test_expired_entry_returns_none(self):
        cache = SnapshotCache(ttl_seconds=0.05)
        cache.put("k1", {"x": 1})
        time.sleep(0.1)
        result = cache.get("k1")
        self.assertIsNone(result)

    def test_valid_entry_returns_data(self):
        cache = SnapshotCache(ttl_seconds=10.0)
        cache.put("k1", {"x": 1})
        result = cache.get("k1")
        self.assertIsNotNone(result)

    def test_invalid_ttl_raises(self):
        with self.assertRaises(ValueError):
            SnapshotCache(ttl_seconds=0)

    def test_invalid_max_entries_raises(self):
        with self.assertRaises(ValueError):
            SnapshotCache(max_entries=0)


class TestSnapshotCacheLRU(unittest.TestCase):
    """LRU eviction tests."""

    def test_evicts_oldest_at_capacity(self):
        cache = SnapshotCache(max_entries=2)
        cache.put("k1", {"a": 1})
        cache.put("k2", {"b": 2})
        cache.put("k3", {"c": 3})  # Should evict k1
        self.assertIsNone(cache.get("k1"))
        self.assertIsNotNone(cache.get("k2"))
        self.assertIsNotNone(cache.get("k3"))

    def test_access_refreshes_lru(self):
        cache = SnapshotCache(max_entries=2)
        cache.put("k1", {"a": 1})
        cache.put("k2", {"b": 2})
        cache.get("k1")  # Refresh k1
        cache.put("k3", {"c": 3})  # Should evict k2 (oldest access)
        self.assertIsNotNone(cache.get("k1"))
        self.assertIsNone(cache.get("k2"))


class TestSnapshotCacheInvalidation(unittest.TestCase):
    """Cache invalidation tests."""

    def test_invalidate_single(self):
        cache = SnapshotCache()
        cache.put("k1", {"a": 1})
        removed = cache.invalidate("k1")
        self.assertTrue(removed)
        self.assertIsNone(cache.get("k1"))

    def test_invalidate_nonexistent(self):
        cache = SnapshotCache()
        removed = cache.invalidate("nonexistent")
        self.assertFalse(removed)

    def test_invalidate_all(self):
        cache = SnapshotCache()
        cache.put("k1", {"a": 1})
        cache.put("k2", {"b": 2})
        count = cache.invalidate_all()
        self.assertEqual(count, 2)
        self.assertEqual(cache.size, 0)

    def test_invalidate_by_prefix(self):
        cache = SnapshotCache()
        cache.put("de_v1", {"a": 1})
        cache.put("de_v2", {"a": 2})
        cache.put("fr_v1", {"b": 1})
        count = cache.invalidate_by_prefix("de_")
        self.assertEqual(count, 2)
        self.assertEqual(cache.size, 1)
        self.assertIsNotNone(cache.get("fr_v1"))


class TestSnapshotCacheStats(unittest.TestCase):
    """Cache statistics tests."""

    def test_initial_stats(self):
        cache = SnapshotCache()
        stats = cache.stats
        self.assertEqual(stats["size"], 0)
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)
        self.assertEqual(stats["hit_rate"], 0.0)

    def test_hit_miss_tracking(self):
        cache = SnapshotCache()
        cache.put("k1", {"a": 1})
        cache.get("k1")  # Hit
        cache.get("k2")  # Miss
        stats = cache.stats
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertAlmostEqual(stats["hit_rate"], 0.5)

    def test_metadata_stored(self):
        cache = SnapshotCache()
        cache.put("k1", {"a": 1}, metadata={"version": "v0.1"})
        # Metadata is internal — the get returns only data
        result = cache.get("k1")
        self.assertEqual(result["a"], 1)


if __name__ == "__main__":
    unittest.main()
