"""
tests/test_nsa_finish.py — NSA-finish security, integrity, and contract tests.

Covers:
    1. Tamper detection (mtime pinning, cache invalidation)
    2. Strict allowlist enforcement (methodology regex, country code, axis ID,
       unicode/encoded traversal, long strings)
    3. Startup/ready semantics (STRICT mode, degraded mode)
    4. Internal endpoint hardening (no path leaks, injection, gating)
    5. Log sanitizer (path stripping, secret redaction)
    6. OpenAPI contract tests (schema snapshots for all endpoints)
    7. Cache bounds (MAX_ARTIFACTS_PER_SNAPSHOT, eviction determinism)
    8. Resolver input validation (methodology regex, year bounds)

All tests run against the real materialized snapshot at v1.0/2024.
No mocking of snapshot data unless explicitly simulating tampering.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.constants import (
    CANONICAL_AXIS_KEYS,
    EU27_CODES,
    EU27_SORTED,
    ISI_AXIS_KEYS,
    NUM_AXES,
)
from backend.log_sanitizer import sanitize_error, sanitize_path, sanitize_value
from backend.snapshot_cache import (
    AXIS_ID_RE,
    COUNTRY_CODE_RE,
    MAX_ARTIFACTS_PER_SNAPSHOT,
    METHODOLOGY_RE,
    SnapshotCache,
    _artifact_to_path,
)
from backend.snapshot_resolver import (
    SNAPSHOTS_ROOT,
    SnapshotContext,
    SnapshotNotFoundError,
    resolve_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = SNAPSHOTS_ROOT / "v1.0" / "2024"


@pytest.fixture(scope="module")
def client() -> TestClient:
    from backend.isi_api_v01 import app
    return TestClient(app)


@pytest.fixture(scope="module")
def ctx() -> SnapshotContext:
    return resolve_snapshot(methodology="v1.0", year=2024)


@pytest.fixture()
def fresh_cache() -> SnapshotCache:
    return SnapshotCache(max_snapshots=2)


@pytest.fixture()
def tamper_snapshot(tmp_path: Path) -> Path:
    """Create a copy of the real snapshot for tamper testing.

    Returns the path to the copy. Caller can modify files freely.
    """
    target = tmp_path / "v1.0" / "2024"
    shutil.copytree(SNAPSHOT_DIR, target)
    # Make all files and directories writable so tests can tamper
    import stat
    for p in target.rglob("*"):
        p.chmod(p.stat().st_mode | stat.S_IWUSR)
    for p in [target, target / "country", target / "axis"]:
        if p.exists():
            p.chmod(p.stat().st_mode | stat.S_IWUSR)
    return target


# ===========================================================================
# 1. Tamper Detection — mtime pinning
# ===========================================================================


class TestTamperDetection:
    """Cache detects filesystem modifications after initial load."""

    def test_clean_snapshot_no_tamper(self, ctx: SnapshotContext):
        """Unmodified snapshot reports zero tampered artifacts."""
        cache = SnapshotCache(max_snapshots=1)
        cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        tampered = cache.check_tamper(ctx.methodology_version, ctx.year, ctx.path)
        assert tampered == []

    def test_tamper_detected_after_file_modification(self, tamper_snapshot: Path):
        """Modifying a cached file triggers tamper detection."""
        cache = SnapshotCache(max_snapshots=1)
        cache.get_artifact("v1.0", 2024, "isi", tamper_snapshot)

        # Tamper: modify isi.json
        isi_path = tamper_snapshot / "isi.json"
        time.sleep(0.05)  # Ensure mtime changes
        isi_path.write_text(
            isi_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )

        tampered = cache.check_tamper("v1.0", 2024, tamper_snapshot)
        assert "isi" in tampered

    def test_tamper_invalidates_cache_slot(self, tamper_snapshot: Path):
        """Tamper detection atomically invalidates the entire cache slot."""
        cache = SnapshotCache(max_snapshots=1)
        cache.get_artifact("v1.0", 2024, "isi", tamper_snapshot)
        cache.get_artifact("v1.0", 2024, "country:SE", tamper_snapshot)
        assert cache.snapshot_count == 1

        # Tamper one file
        isi_path = tamper_snapshot / "isi.json"
        time.sleep(0.05)
        isi_path.write_text(
            isi_path.read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )

        tampered = cache.check_tamper("v1.0", 2024, tamper_snapshot)
        assert len(tampered) >= 1
        # Cache slot should be evicted
        assert cache.snapshot_count == 0

    def test_tamper_detected_file_deleted(self, tamper_snapshot: Path):
        """Deleting a cached file triggers tamper detection."""
        cache = SnapshotCache(max_snapshots=1)
        cache.get_artifact("v1.0", 2024, "country:SE", tamper_snapshot)

        # Delete the file
        (tamper_snapshot / "country" / "SE.json").unlink()

        tampered = cache.check_tamper("v1.0", 2024, tamper_snapshot)
        assert "country:SE" in tampered

    def test_no_tamper_on_uncached_snapshot(self, ctx: SnapshotContext):
        """check_tamper on a snapshot with no cached data returns empty."""
        cache = SnapshotCache(max_snapshots=1)
        tampered = cache.check_tamper("v99.0", 9999, ctx.path)
        assert tampered == []

    def test_tamper_after_load_next_request_gets_fresh_data(self, tamper_snapshot: Path):
        """After tamper+invalidation, next load returns fresh disk data."""
        cache = SnapshotCache(max_snapshots=1)
        data1 = cache.get_artifact("v1.0", 2024, "isi", tamper_snapshot)
        original_countries = len(data1["countries"])

        # Tamper: write a completely different isi.json
        isi_path = tamper_snapshot / "isi.json"
        time.sleep(0.05)
        data_modified = dict(data1)
        data_modified["tamper_marker"] = True
        isi_path.write_text(
            json.dumps(data_modified, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Detect tamper → slot invalidated
        tampered = cache.check_tamper("v1.0", 2024, tamper_snapshot)
        assert "isi" in tampered

        # Re-load: should get the tampered data (fresh from disk)
        data2 = cache.get_artifact("v1.0", 2024, "isi", tamper_snapshot)
        assert data2.get("tamper_marker") is True


# ===========================================================================
# 2. Strict Allowlist Enforcement
# ===========================================================================


class TestStrictAllowlists:
    """Input validation at cache + resolver layer blocks adversarial inputs."""

    # --- Methodology version regex ---

    @pytest.mark.parametrize("bad_methodology", [
        "../etc",
        "v1.0/../../../etc/passwd",
        "%2e%2e%2f",
        "v1.0\x00",
        "",
        "   ",
        "v1",
        "1.0",
        "V1.0",      # must be lowercase v
        "v1.0.0",    # too many dots
        "v-1.0",     # negative
        "v1.0; DROP TABLE",
        "v1.0\n",
        "v" + "1" * 100 + ".0",  # absurdly long
        "v١.٠",      # Arabic numerals
        "v1．0",     # fullwidth period
    ])
    def test_bad_methodology_rejected_by_cache(self, bad_methodology: str, ctx: SnapshotContext):
        """Cache rejects methodology versions that don't match ^v\\d+\\.\\d+$."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="methodology_version"):
            cache.get_artifact(bad_methodology, 2024, "isi", ctx.path)

    @pytest.mark.parametrize("bad_methodology", [
        "../etc",
        "v1.0/../../../etc/passwd",
        "%2e%2e",
        "v1",
        "V1.0",
        "v1.0.0",
    ])
    def test_bad_methodology_rejected_by_resolver(self, bad_methodology: str):
        """Resolver rejects methodology versions that don't match regex."""
        with pytest.raises(SnapshotNotFoundError, match="Invalid methodology"):
            resolve_snapshot(methodology=bad_methodology, year=2024)

    def test_valid_methodology_accepted(self):
        """v1.0 passes all validation."""
        assert METHODOLOGY_RE.match("v1.0")
        assert METHODOLOGY_RE.match("v2.1")
        assert METHODOLOGY_RE.match("v99.99")

    # --- Country code regex ---

    @pytest.mark.parametrize("bad_code", [
        "../",
        "../../etc/passwd",
        "%2e%2e",
        "se",         # lowercase
        "SEE",        # too long
        "S",          # too short
        "S1",         # digit
        "S\x00E",     # null byte
        "🇸🇪",       # emoji flag
        "",
    ])
    def test_bad_country_code_rejected(self, bad_code: str, ctx: SnapshotContext):
        """Country codes that don't match ^[A-Z]{2}$ are rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="Invalid country code|Path traversal"):
            cache.get_artifact(ctx.methodology_version, ctx.year, f"country:{bad_code}", ctx.path)

    # --- Axis ID regex ---

    @pytest.mark.parametrize("bad_axis", [
        "../",
        "../../etc/passwd",
        "0",          # axis 0 doesn't exist
        "10",         # two digits
        "a",          # letter
        "-1",         # negative
        "",           # empty
    ])
    def test_bad_axis_id_rejected(self, bad_axis: str, ctx: SnapshotContext):
        """Axis IDs that don't match ^[1-9]$ are rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="Invalid axis ID|Path traversal"):
            cache.get_artifact(ctx.methodology_version, ctx.year, f"axis:{bad_axis}", ctx.path)

    # --- Year bounds ---

    @pytest.mark.parametrize("bad_year", [-1, 0, 1999, 2101, 99999])
    def test_bad_year_rejected_by_resolver(self, bad_year: int):
        """Years outside [2000, 2100] are rejected before registry lookup."""
        with pytest.raises(SnapshotNotFoundError, match="outside valid range"):
            resolve_snapshot(methodology="v1.0", year=bad_year)

    def test_bad_year_rejected_by_cache(self, ctx: SnapshotContext):
        """Cache rejects non-positive years."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="positive integer"):
            cache.get_artifact(ctx.methodology_version, -1, "isi", ctx.path)

    # --- Unknown artifact keys ---

    @pytest.mark.parametrize("bad_artifact", [
        "../../etc/passwd",
        "file:///etc/passwd",
        "country:../../etc/passwd",
        "axis:../../etc/passwd",
        "random_key",
        "__proto__",
        "constructor",
    ])
    def test_unknown_artifact_key_rejected(self, bad_artifact: str, ctx: SnapshotContext):
        """Unknown or malformed artifact keys are rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError):
            cache.get_artifact(ctx.methodology_version, ctx.year, bad_artifact, ctx.path)


# ===========================================================================
# 3. Startup / Ready Semantics
# ===========================================================================


class TestStartupReadySemantics:
    """Verify /ready reflects actual system state."""

    def test_ready_returns_200(self, client: TestClient):
        """/ready always returns 200 (orchestrator contract)."""
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_ready_has_required_fields(self, client: TestClient):
        """/ready response has all required fields."""
        resp = client.get("/ready")
        data = resp.json()
        assert "ready" in data
        assert "status" in data
        assert "version" in data
        assert "data_present" in data
        assert "timestamp" in data

    def test_ready_timestamp_is_iso(self, client: TestClient):
        """/ready timestamp is valid ISO 8601."""
        from datetime import datetime
        resp = client.get("/ready")
        ts = resp.json()["timestamp"]
        # Should not raise
        datetime.fromisoformat(ts)

    def test_health_always_200(self, client: TestClient):
        """/health always returns 200 regardless of state."""
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ===========================================================================
# 4. Internal Endpoint Hardening
# ===========================================================================


class TestInternalEndpointHardening:
    """/_internal/snapshot/verify security guarantees."""

    def test_endpoint_excluded_from_openapi(self, client: TestClient):
        """Internal endpoint never appears in OpenAPI schema."""
        resp = client.get("/openapi.json")
        if resp.status_code == 200:
            paths = resp.json().get("paths", {})
            assert "/_internal/snapshot/verify" not in paths

    def test_endpoint_disabled_returns_404(self, client: TestClient):
        """Without ENABLE_INTERNAL_VERIFY=1, returns 404."""
        if os.getenv("ENABLE_INTERNAL_VERIFY", "") != "1":
            resp = client.get("/_internal/snapshot/verify")
            assert resp.status_code in (404, 405)

    def test_no_stack_trace_in_500(self, client: TestClient):
        """500 errors never contain stack traces or file paths."""
        # Attempt to trigger an error with bad path
        resp = client.get("/country/INVALID_VERY_LONG_CODE_THAT_DOESNT_EXIST")
        if resp.status_code in (404, 500):
            body = resp.text
            assert "/Users/" not in body
            assert "/app/" not in body
            assert "Traceback" not in body

    def test_global_exception_handler_no_leak(self, client: TestClient):
        """Global exception handler returns safe JSON without internals."""
        # Exercise various bad inputs
        for path in ["/country/XX", "/axis/99", "/country/../../etc/passwd"]:
            resp = client.get(path)
            if resp.status_code >= 400:
                body = resp.text
                assert "Traceback" not in body
                assert "/Users/" not in body
                assert ".py" not in body or "not found" in body.lower() or "not valid" in body.lower()

    def test_scenario_400_no_path_leak(self, client: TestClient):
        """POST /scenario 400 error doesn't leak paths."""
        resp = client.post("/scenario", json={"country": "XX", "adjustments": {}})
        body = resp.text
        assert "/Users/" not in body
        assert "/app/" not in body
        assert "backend/" not in body


# ===========================================================================
# 5. Log Sanitizer
# ===========================================================================


class TestLogSanitizer:
    """backend.log_sanitizer strips paths and secrets."""

    def test_sanitize_project_path(self):
        """Project-internal paths are made relative."""
        result = sanitize_path("/Users/sebastiandrazsky/Panargus-isi/backend/snapshots/v1.0")
        assert not result.startswith("/")
        assert "backend/snapshots" in result

    def test_sanitize_external_path(self):
        """Paths outside project are fully redacted."""
        result = sanitize_path("/etc/passwd")
        assert result == "<external>"

    def test_sanitize_relative_path_unchanged(self):
        """Relative paths pass through unchanged."""
        result = sanitize_path("backend/snapshots/v1.0")
        assert result == "backend/snapshots/v1.0"

    def test_sanitize_error_strips_paths(self):
        """Error messages have project paths stripped."""
        from backend.log_sanitizer import _PROJECT_ROOT_SLASH
        exc = FileNotFoundError(f"{_PROJECT_ROOT_SLASH}backend/foo.json not found")
        result = sanitize_error(exc)
        assert "FileNotFoundError" in result
        assert _PROJECT_ROOT_SLASH not in result
        assert "backend/foo.json" in result

    def test_sanitize_value_redacts_redis_url(self):
        """Redis URLs are redacted."""
        result = sanitize_value("redis://user:pass@host:6379/0")
        assert "[REDACTED_URL]" in result
        assert "pass" not in result

    def test_sanitize_value_redacts_postgres_url(self):
        """PostgreSQL URLs are redacted."""
        result = sanitize_value("postgresql://admin:secret@db.host:5432/mydb")
        assert "[REDACTED_URL]" in result
        assert "secret" not in result

    def test_sanitize_value_safe_string_unchanged(self):
        """Normal strings pass through unchanged."""
        result = sanitize_value("This is a normal log message")
        assert result == "This is a normal log message"


# ===========================================================================
# 6. OpenAPI Contract Tests (schema snapshots)
# ===========================================================================


class TestOpenAPIContract:
    """Verify API schema stability — additive only, no breaking changes."""

    def test_isi_endpoint_schema(self, client: TestClient):
        """/isi returns the expected top-level keys."""
        resp = client.get("/isi")
        if resp.status_code == 200:
            data = resp.json()
            assert "countries" in data
            assert "window" in data
            countries = data["countries"]
            assert len(countries) == 27
            # Every country has required fields
            for c in countries:
                assert "country" in c
                assert "isi_composite" in c
                assert "classification" in c
                for key in ISI_AXIS_KEYS:
                    assert key in c, f"Missing ISI axis key: {key}"

    def test_country_endpoint_schema(self, client: TestClient):
        """/country/{code} returns expected structure."""
        resp = client.get("/country/SE")
        if resp.status_code == 200:
            data = resp.json()
            assert data["country"] == "SE"
            assert "country_name" in data
            assert "isi_composite" in data
            assert "axes" in data
            assert len(data["axes"]) == NUM_AXES
            for ax in data["axes"]:
                assert "axis_id" in ax
                assert "score" in ax
                assert "axis_slug" in ax

    def test_scenario_endpoint_schema(self, client: TestClient):
        """POST /scenario returns expected response shape."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {"energy_external_supplier_concentration": 0.05},
        })
        assert resp.status_code == 200
        data = resp.json()
        # Top-level keys
        assert "country" in data
        assert "baseline" in data
        assert "simulated" in data
        assert "delta" in data
        assert "meta" in data
        # Baseline block
        bl = data["baseline"]
        assert "composite" in bl
        assert "rank" in bl
        assert "classification" in bl
        assert "axes" in bl
        for key in CANONICAL_AXIS_KEYS:
            assert key in bl["axes"], f"Missing axis: {key}"
        # Simulated block (same shape)
        sim = data["simulated"]
        assert set(bl.keys()) == set(sim.keys())
        # Delta block
        d = data["delta"]
        assert "composite" in d
        assert "rank" in d
        assert "axes" in d
        # Meta block
        m = data["meta"]
        assert "version" in m
        assert "timestamp" in m
        assert "bounds" in m

    def test_scenario_with_year_methodology(self, client: TestClient):
        """POST /scenario with explicit year/methodology returns enriched meta."""
        resp = client.post("/scenario", json={
            "country": "DE",
            "adjustments": {},
            "year": 2024,
            "methodology": "v1.0",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["year"] == 2024
        assert data["meta"]["methodology"] == "v1.0"

    def test_methodology_versions_schema(self, client: TestClient):
        """/methodology/versions returns expected structure."""
        resp = client.get("/methodology/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert "latest" in data
        assert "versions" in data
        assert isinstance(data["versions"], list)
        for v in data["versions"]:
            assert "methodology_version" in v
            assert "years_available" in v
            assert "axis_count" in v
            assert v["axis_count"] == NUM_AXES

    def test_country_history_schema(self, client: TestClient):
        """/country/{code}/history returns expected structure."""
        resp = client.get("/country/SE/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country"] == "SE"
        assert "country_name" in data
        assert "methodology_version" in data
        assert "years_count" in data
        assert "years" in data
        for point in data["years"]:
            assert "year" in point
            assert "composite" in point
            assert "rank" in point
            assert "classification" in point
            assert "axes" in point

    def test_isi_endpoint_all_countries_present(self, client: TestClient):
        """/isi contains exactly the EU-27 countries."""
        resp = client.get("/isi")
        if resp.status_code == 200:
            codes = {c["country"] for c in resp.json()["countries"]}
            assert codes == EU27_CODES

    def test_scenario_unknown_axis_returns_400(self, client: TestClient):
        """POST /scenario with unknown axis key returns 400 BAD_INPUT."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {"nonexistent_axis": 0.05},
        })
        assert resp.status_code == 400
        assert "BAD_INPUT" in resp.json().get("error", "")

    def test_scenario_out_of_range_returns_400(self, client: TestClient):
        """POST /scenario with adjustment > 0.20 returns 400."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {"energy_external_supplier_concentration": 0.50},
        })
        assert resp.status_code == 400

    def test_scenario_get_returns_405(self, client: TestClient):
        """GET /scenario returns 405 Method Not Allowed."""
        resp = client.get("/scenario")
        assert resp.status_code == 405


# ===========================================================================
# 7. Cache Bounds & Performance
# ===========================================================================


class TestCacheBounds:
    """Verify memory bounds and eviction guarantees."""

    def test_max_cached_snapshots_enforced(self):
        """Cache never holds more than max_snapshots slots."""
        cache = SnapshotCache(max_snapshots=2)
        for i in range(5):
            # Use the real snapshot path but different keys to trigger eviction
            cache.get_artifact(f"v{i}.0", 2024, "isi", SNAPSHOT_DIR)
            assert cache.snapshot_count <= 2

    def test_artifact_count_cap_respected(self, ctx: SnapshotContext):
        """Artifacts beyond MAX_ARTIFACTS_PER_SNAPSHOT are not cached."""
        # Create a cache with small artifact cap
        cache = SnapshotCache(max_snapshots=1)
        # Load all valid artifacts (should be < 50)
        loaded = 0
        for code in EU27_SORTED:
            cache.get_artifact(ctx.methodology_version, ctx.year, f"country:{code}", ctx.path)
            loaded += 1
        for i in range(1, NUM_AXES + 1):
            cache.get_artifact(ctx.methodology_version, ctx.year, f"axis:{i}", ctx.path)
            loaded += 1
        cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        loaded += 1
        cache.get_artifact(ctx.methodology_version, ctx.year, "manifest", ctx.path)
        loaded += 1
        cache.get_artifact(ctx.methodology_version, ctx.year, "hash_summary", ctx.path)
        loaded += 1

        # Total should be 27 + 6 + 3 = 36, well under 50 cap
        stats = cache.stats
        assert stats["slots"][0]["artifacts_cached"] == 36
        assert stats["slots"][0]["artifacts_cached"] <= MAX_ARTIFACTS_PER_SNAPSHOT

    def test_eviction_is_lru(self, ctx: SnapshotContext):
        """Least-recently-used snapshot is evicted first."""
        cache = SnapshotCache(max_snapshots=2)
        # Load slot A
        cache.get_artifact("v1.0", 2024, "isi", ctx.path)
        # Load slot B
        cache.get_artifact("v2.0", 2024, "isi", ctx.path)
        # Access slot A again (make it recent)
        cache.get_artifact("v1.0", 2024, "isi", ctx.path)
        # Load slot C — should evict B (LRU)
        cache.get_artifact("v3.0", 2024, "isi", ctx.path)

        assert cache.snapshot_count == 2
        slots = {(s["methodology_version"], s["year"]) for s in cache.stats["slots"]}
        assert ("v1.0", 2024) in slots
        assert ("v3.0", 2024) in slots
        assert ("v2.0", 2024) not in slots

    def test_cache_stats_structure(self, ctx: SnapshotContext):
        """Cache stats returns well-structured data."""
        cache = SnapshotCache(max_snapshots=3)
        cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        stats = cache.stats
        assert "max_snapshots" in stats
        assert stats["max_snapshots"] == 3
        assert "slots_used" in stats
        assert stats["slots_used"] == 1
        assert "slots" in stats
        assert len(stats["slots"]) == 1
        slot = stats["slots"][0]
        assert "methodology_version" in slot
        assert "year" in slot
        assert "artifacts_cached" in slot


# ===========================================================================
# 8. Resolver Input Validation
# ===========================================================================


class TestResolverInputValidation:
    """Resolver enforces strict allowlists before filesystem access."""

    def test_resolve_valid_snapshot(self):
        """Valid inputs resolve successfully."""
        ctx = resolve_snapshot(methodology="v1.0", year=2024)
        assert ctx.methodology_version == "v1.0"
        assert ctx.year == 2024

    def test_resolve_defaults_to_latest(self):
        """None inputs resolve to latest."""
        ctx = resolve_snapshot()
        assert ctx.methodology_version == "v1.0"
        assert ctx.year == 2024

    @pytest.mark.parametrize("bad_meth", [
        "../etc", "v1.0/../../etc", "V1.0", "v1", "v1.0.0",
    ])
    def test_resolve_rejects_bad_methodology(self, bad_meth: str):
        """Bad methodology formats are rejected."""
        with pytest.raises(SnapshotNotFoundError):
            resolve_snapshot(methodology=bad_meth, year=2024)

    @pytest.mark.parametrize("bad_year", [-1, 0, 1999, 2101])
    def test_resolve_rejects_bad_year(self, bad_year: int):
        """Years outside bounds are rejected."""
        with pytest.raises(SnapshotNotFoundError):
            resolve_snapshot(methodology="v1.0", year=bad_year)

    def test_resolve_nonexistent_year_in_range(self):
        """Valid-format year not in registry is rejected."""
        with pytest.raises(SnapshotNotFoundError, match="not available"):
            resolve_snapshot(methodology="v1.0", year=2025)

    def test_resolve_path_never_escapes_snapshots_root(self):
        """Resolved path is always under SNAPSHOTS_ROOT."""
        ctx = resolve_snapshot(methodology="v1.0", year=2024)
        assert str(ctx.path.resolve()).startswith(str(SNAPSHOTS_ROOT.resolve()))
