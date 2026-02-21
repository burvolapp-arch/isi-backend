"""
tests/test_serving_layer.py — Tests for the time-aware serving layer.

Covers:
    - Snapshot resolver (Phase A)
    - Snapshot cache (Phase B)
    - GET /methodology/versions (Phase C)
    - GET /country/{code}/history (Phase C)
    - POST /scenario with year/methodology (Phase D)
    - Backward compatibility of all existing endpoints

Runs against real materialized snapshots in backend/snapshots/v1.0/2024/.
No mocking of snapshot data — tests validate real end-to-end behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.constants import (
    CANONICAL_AXIS_KEYS,
    EU27_CODES,
    EU27_SORTED,
    ISI_AXIS_KEYS,
    NUM_AXES,
    ROUND_PRECISION,
)
from backend.methodology import (
    classify,
    get_latest_methodology_version,
    get_latest_year,
    get_years_available,
)
from backend.snapshot_cache import SnapshotCache
from backend.snapshot_resolver import (
    SnapshotContext,
    SnapshotNotFoundError,
    list_available_snapshots,
    resolve_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SNAPSHOTS_ROOT = Path(__file__).resolve().parent.parent / "backend" / "snapshots"
V01_ROOT = Path(__file__).resolve().parent.parent / "backend" / "v01"


@pytest.fixture(scope="module")
def client() -> TestClient:
    """FastAPI test client. Module-scoped for performance."""
    from backend.isi_api_v01 import app
    return TestClient(app)


@pytest.fixture()
def fresh_cache() -> SnapshotCache:
    """A fresh cache instance for isolated tests."""
    return SnapshotCache(max_snapshots=2)


# ===========================================================================
# Phase A — Snapshot Resolver
# ===========================================================================


class TestSnapshotResolver:
    """Snapshot resolution and validation."""

    def test_resolve_latest(self):
        """resolve_snapshot() with no args resolves to latest."""
        ctx = resolve_snapshot()
        assert isinstance(ctx, SnapshotContext)
        assert ctx.methodology_version == "v1.0"
        assert ctx.year == 2024
        assert ctx.path.is_dir()
        assert (ctx.path / "isi.json").is_file()
        assert ctx.snapshot_hash  # Non-empty
        assert ctx.data_window  # Non-empty

    def test_resolve_explicit_year(self):
        """resolve_snapshot(year=2024) resolves correctly."""
        ctx = resolve_snapshot(methodology="v1.0", year=2024)
        assert ctx.methodology_version == "v1.0"
        assert ctx.year == 2024
        assert ctx.path.is_dir()

    def test_resolve_invalid_year_raises(self):
        """resolve_snapshot(year=9999) raises SnapshotNotFoundError."""
        with pytest.raises(SnapshotNotFoundError) as exc_info:
            resolve_snapshot(methodology="v1.0", year=9999)
        assert "9999" in str(exc_info.value)
        assert exc_info.value.year == 9999

    def test_resolve_invalid_methodology_raises(self):
        """resolve_snapshot(methodology='v99.0') raises KeyError."""
        with pytest.raises(KeyError):
            resolve_snapshot(methodology="v99.0")

    def test_snapshot_context_is_frozen(self):
        """SnapshotContext fields cannot be mutated."""
        ctx = resolve_snapshot()
        with pytest.raises(AttributeError):
            ctx.year = 2025  # type: ignore[misc]

    def test_list_available_snapshots(self):
        """list_available_snapshots returns at least the v1.0/2024 snapshot."""
        snapshots = list_available_snapshots()
        assert len(snapshots) >= 1
        found = any(
            s["methodology_version"] == "v1.0" and s["year"] == 2024
            for s in snapshots
        )
        assert found, f"v1.0/2024 not found in {snapshots}"

    def test_resolve_none_methodology_defaults_to_latest(self):
        """methodology=None → latest from registry."""
        ctx = resolve_snapshot(methodology=None, year=2024)
        assert ctx.methodology_version == get_latest_methodology_version()

    def test_resolve_none_year_defaults_to_latest(self):
        """year=None → latest year from registry."""
        ctx = resolve_snapshot(methodology="v1.0", year=None)
        assert ctx.year == get_latest_year()


# ===========================================================================
# Phase B — Snapshot Cache
# ===========================================================================


class TestSnapshotCache:
    """Thread-safe, bounded, LRU snapshot cache."""

    def test_load_isi_artifact(self, fresh_cache: SnapshotCache):
        """Cache loads isi.json correctly."""
        ctx = resolve_snapshot()
        data = fresh_cache.get_artifact(
            methodology_version=ctx.methodology_version,
            year=ctx.year,
            artifact="isi",
            snapshot_dir=ctx.path,
        )
        assert data is not None
        assert "countries" in data
        assert len(data["countries"]) == 27

    def test_load_country_artifact(self, fresh_cache: SnapshotCache):
        """Cache loads country/SE.json correctly."""
        ctx = resolve_snapshot()
        data = fresh_cache.get_artifact(
            methodology_version=ctx.methodology_version,
            year=ctx.year,
            artifact="country:SE",
            snapshot_dir=ctx.path,
        )
        assert data is not None
        assert data["country"] == "SE"
        assert data["country_name"] == "Sweden"

    def test_load_axis_artifact(self, fresh_cache: SnapshotCache):
        """Cache loads axis/1.json correctly."""
        ctx = resolve_snapshot()
        data = fresh_cache.get_artifact(
            methodology_version=ctx.methodology_version,
            year=ctx.year,
            artifact="axis:1",
            snapshot_dir=ctx.path,
        )
        assert data is not None
        assert data["axis_id"] == 1

    def test_cache_returns_same_object_on_second_call(self, fresh_cache: SnapshotCache):
        """Second call returns the same cached object (identity check)."""
        ctx = resolve_snapshot()
        data1 = fresh_cache.get_artifact(
            ctx.methodology_version, ctx.year, "isi", ctx.path,
        )
        data2 = fresh_cache.get_artifact(
            ctx.methodology_version, ctx.year, "isi", ctx.path,
        )
        assert data1 is data2  # Same object in memory

    def test_cache_bounded(self):
        """Cache evicts oldest slot when max_snapshots exceeded."""
        cache = SnapshotCache(max_snapshots=1)
        ctx = resolve_snapshot()

        # Load first artifact
        cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        assert cache.snapshot_count == 1

        # Simulate a different snapshot key (same path, different key)
        cache.get_artifact("v0.0-test", 2020, "isi", ctx.path)
        assert cache.snapshot_count == 1  # Evicted the first

    def test_invalidate_specific_slot(self, fresh_cache: SnapshotCache):
        """invalidate() removes a specific snapshot slot."""
        ctx = resolve_snapshot()
        fresh_cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        assert fresh_cache.snapshot_count == 1
        count = fresh_cache.invalidate(ctx.methodology_version, ctx.year)
        assert count == 1
        assert fresh_cache.snapshot_count == 0

    def test_invalidate_all(self, fresh_cache: SnapshotCache):
        """invalidate() with no args clears entire cache."""
        ctx = resolve_snapshot()
        fresh_cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        fresh_cache.invalidate()
        assert fresh_cache.snapshot_count == 0

    def test_cache_stats(self, fresh_cache: SnapshotCache):
        """stats property returns structured diagnostics."""
        ctx = resolve_snapshot()
        fresh_cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        fresh_cache.get_artifact(ctx.methodology_version, ctx.year, "country:SE", ctx.path)
        stats = fresh_cache.stats
        assert stats["max_snapshots"] == 2
        assert stats["slots_used"] == 1
        assert stats["slots"][0]["artifacts_cached"] == 2

    def test_missing_artifact_returns_none(self, fresh_cache: SnapshotCache):
        """Requesting a non-existent country file returns None."""
        ctx = resolve_snapshot()
        data = fresh_cache.get_artifact(
            ctx.methodology_version, ctx.year, "country:ZZ", ctx.path,
        )
        assert data is None

    def test_unknown_artifact_key_raises(self, fresh_cache: SnapshotCache):
        """Unrecognised artifact key raises ValueError."""
        ctx = resolve_snapshot()
        with pytest.raises(ValueError, match="Unknown artifact key"):
            fresh_cache.get_artifact(
                ctx.methodology_version, ctx.year, "garbage", ctx.path,
            )


# ===========================================================================
# Phase C — Time-Series Endpoints
# ===========================================================================


class TestMethodologyVersions:
    """GET /methodology/versions"""

    def test_returns_200(self, client: TestClient):
        resp = client.get("/methodology/versions")
        assert resp.status_code == 200

    def test_response_structure(self, client: TestClient):
        resp = client.get("/methodology/versions")
        data = resp.json()
        assert "latest" in data
        assert "latest_year" in data
        assert "versions" in data
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) >= 1

    def test_latest_points_to_v1_0(self, client: TestClient):
        resp = client.get("/methodology/versions")
        data = resp.json()
        assert data["latest"] == "v1.0"
        assert data["latest_year"] == 2024

    def test_version_entry_structure(self, client: TestClient):
        resp = client.get("/methodology/versions")
        entry = resp.json()["versions"][0]
        assert "methodology_version" in entry
        assert "label" in entry
        assert "frozen_at" in entry
        assert "years_available" in entry
        assert "latest_year" in entry
        assert "aggregation_rule" in entry
        assert "axis_count" in entry
        assert entry["axis_count"] == NUM_AXES

    def test_years_available_sorted_ascending(self, client: TestClient):
        resp = client.get("/methodology/versions")
        for entry in resp.json()["versions"]:
            years = entry["years_available"]
            assert years == sorted(years)


class TestCountryHistory:
    """GET /country/{code}/history"""

    def test_returns_200_for_valid_country(self, client: TestClient):
        resp = client.get("/country/SE/history")
        assert resp.status_code == 200

    def test_response_structure(self, client: TestClient):
        resp = client.get("/country/SE/history")
        data = resp.json()
        assert data["country"] == "SE"
        assert data["country_name"] == "Sweden"
        assert data["methodology_version"] == "v1.0"
        assert "years_count" in data
        assert "years" in data
        assert isinstance(data["years"], list)
        assert data["years_count"] >= 1

    def test_year_entry_structure(self, client: TestClient):
        resp = client.get("/country/SE/history")
        entry = resp.json()["years"][0]
        required_keys = {
            "year", "composite", "rank", "classification",
            "axes", "data_window", "delta_vs_previous",
            "classification_change",
        }
        assert required_keys <= set(entry.keys())

    def test_axes_contain_all_six(self, client: TestClient):
        resp = client.get("/country/SE/history")
        entry = resp.json()["years"][0]
        axes = entry["axes"]
        for key in ISI_AXIS_KEYS:
            assert key in axes, f"Missing axis key: {key}"

    def test_years_sorted_ascending(self, client: TestClient):
        resp = client.get("/country/SE/history")
        years = [e["year"] for e in resp.json()["years"]]
        assert years == sorted(years)

    def test_first_year_has_no_delta(self, client: TestClient):
        """First year in history has delta_vs_previous = None."""
        resp = client.get("/country/SE/history")
        first = resp.json()["years"][0]
        assert first["delta_vs_previous"] is None

    def test_first_year_has_no_classification_change(self, client: TestClient):
        """First year has classification_change = None."""
        resp = client.get("/country/SE/history")
        first = resp.json()["years"][0]
        assert first["classification_change"] is None

    def test_invalid_country_returns_404(self, client: TestClient):
        resp = client.get("/country/ZZ/history")
        assert resp.status_code == 404

    def test_invalid_methodology_returns_404(self, client: TestClient):
        resp = client.get("/country/SE/history?methodology=v99.0")
        assert resp.status_code == 404

    def test_methodology_filter(self, client: TestClient):
        """Explicit methodology parameter works."""
        resp = client.get("/country/SE/history?methodology=v1.0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["methodology_version"] == "v1.0"

    def test_year_range_filter(self, client: TestClient):
        """from_year and to_year filters work."""
        resp = client.get("/country/SE/history?from_year=2024&to_year=2024")
        assert resp.status_code == 200
        years = [e["year"] for e in resp.json()["years"]]
        assert all(2024 <= y <= 2024 for y in years)

    def test_all_eu27_countries_have_history(self, client: TestClient):
        """Every EU-27 country returns valid history."""
        for code in EU27_SORTED:
            resp = client.get(f"/country/{code}/history")
            assert resp.status_code == 200, f"Failed for {code}: {resp.status_code}"
            data = resp.json()
            assert data["country"] == code
            assert len(data["years"]) >= 1

    def test_composite_matches_snapshot(self, client: TestClient):
        """History composite matches the materialized snapshot's isi.json."""
        ctx = resolve_snapshot()
        with open(ctx.path / "isi.json") as f:
            isi_data = json.load(f)
        snapshot_composites = {
            c["country"]: c["isi_composite"] for c in isi_data["countries"]
        }

        resp = client.get("/country/SE/history")
        history_entry = resp.json()["years"][0]
        assert history_entry["composite"] == snapshot_composites["SE"]

    def test_rank_is_positive_integer(self, client: TestClient):
        resp = client.get("/country/MT/history")
        for entry in resp.json()["years"]:
            assert isinstance(entry["rank"], int)
            assert entry["rank"] >= 1
            assert entry["rank"] <= 27


# ===========================================================================
# Phase D — Scenario Year Awareness
# ===========================================================================


class TestScenarioYearAwareness:
    """POST /scenario with optional year/methodology."""

    def test_default_scenario_unchanged(self, client: TestClient):
        """POST /scenario without year/methodology behaves exactly as before."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["country"] == "SE"
        assert "baseline" in data
        assert "simulated" in data
        assert "delta" in data
        assert "meta" in data
        # No year/methodology in meta when not explicitly requested
        assert "year" not in data["meta"]
        assert "methodology" not in data["meta"]

    def test_scenario_with_explicit_year(self, client: TestClient):
        """POST /scenario with year=2024 loads from snapshot."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
            "year": 2024,
            "methodology": "v1.0",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["country"] == "SE"
        assert data["meta"]["year"] == 2024
        assert data["meta"]["methodology"] == "v1.0"

    def test_scenario_year_baseline_matches_snapshot(self, client: TestClient):
        """Scenario baseline from year=2024 matches snapshot composite."""
        ctx = resolve_snapshot(methodology="v1.0", year=2024)
        with open(ctx.path / "isi.json") as f:
            isi_data = json.load(f)
        snapshot_se = next(c for c in isi_data["countries"] if c["country"] == "SE")

        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
            "year": 2024,
            "methodology": "v1.0",
        })
        data = resp.json()
        assert data["baseline"]["composite"] == snapshot_se["isi_composite"]

    def test_scenario_invalid_year_returns_404(self, client: TestClient):
        """POST /scenario with year=9999 returns 404."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
            "year": 9999,
            "methodology": "v1.0",
        })
        assert resp.status_code == 404
        assert resp.json()["error"] == "SNAPSHOT_NOT_FOUND"

    def test_scenario_invalid_methodology_returns_error(self, client: TestClient):
        """POST /scenario with methodology=v99.0 returns error."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
            "methodology": "v99.0",
        })
        # Should be either 404 or 500 (KeyError from methodology lookup)
        assert resp.status_code in (404, 500)

    def test_scenario_monotonicity_preserved_with_year(self, client: TestClient):
        """Positive adjustment → composite increases (monotonicity invariant)."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {
                "energy_external_supplier_concentration": 0.10,
            },
            "year": 2024,
            "methodology": "v1.0",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["simulated"]["composite"] >= data["baseline"]["composite"]

    def test_scenario_with_year_only(self, client: TestClient):
        """POST /scenario with year but no methodology defaults methodology to latest."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
            "year": 2024,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["year"] == 2024

    def test_scenario_rank_within_year_distribution(self, client: TestClient):
        """Rank is computed within that year's distribution (1-27)."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {},
            "year": 2024,
            "methodology": "v1.0",
        })
        data = resp.json()
        assert 1 <= data["baseline"]["rank"] <= 27
        assert 1 <= data["simulated"]["rank"] <= 27


# ===========================================================================
# Backward Compatibility — Existing Endpoints
# ===========================================================================


class TestBackwardCompatibility:
    """Verify ALL existing endpoints continue to work exactly as before."""

    def test_get_isi(self, client: TestClient):
        resp = client.get("/isi")
        assert resp.status_code == 200
        data = resp.json()
        assert "countries" in data
        assert len(data["countries"]) == 27

    def test_get_country_se(self, client: TestClient):
        resp = client.get("/country/SE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["country"] == "SE"

    def test_get_countries(self, client: TestClient):
        resp = client.get("/countries")
        assert resp.status_code == 200

    def test_get_axes(self, client: TestClient):
        resp = client.get("/axes")
        assert resp.status_code == 200

    def test_get_axis_1(self, client: TestClient):
        resp = client.get("/axis/1")
        assert resp.status_code == 200

    def test_get_country_axes(self, client: TestClient):
        resp = client.get("/country/SE/axes")
        assert resp.status_code == 200

    def test_get_country_axis_1(self, client: TestClient):
        resp = client.get("/country/SE/axis/1")
        assert resp.status_code == 200

    def test_post_scenario_default(self, client: TestClient):
        """Default scenario (no year/methodology) unchanged."""
        resp = client.post("/scenario", json={
            "country": "SE",
            "adjustments": {
                "energy_external_supplier_concentration": -0.10,
            },
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["country"] == "SE"
        assert "baseline" in data
        assert "simulated" in data
        assert "delta" in data
        # Verify structure matches exactly
        for block_name in ("baseline", "simulated"):
            block = data[block_name]
            assert "composite" in block
            assert "rank" in block
            assert "classification" in block
            assert "axes" in block

    def test_health(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ready(self, client: TestClient):
        resp = client.get("/ready")
        assert resp.status_code == 200

    def test_root(self, client: TestClient):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_scenario_get_returns_405(self, client: TestClient):
        resp = client.get("/scenario")
        assert resp.status_code == 405

    def test_scenario_schema(self, client: TestClient):
        resp = client.get("/scenario/schema")
        assert resp.status_code == 200
        data = resp.json()
        assert "axis_keys" in data
        assert "bounds" in data
