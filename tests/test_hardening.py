"""
tests/test_hardening.py — Hardening & Institutional Integrity Tests

Covers:
    Phase 1: Snapshot structural integrity validation
    Phase 2: Verification CLI
    Phase 3: Cache hardening (path traversal, atomic eviction, concurrency)
    Phase 4: Determinism enforcement (JSON serialization, scenario determinism)
    Phase 5: Scenario engine formal invariants (identity, monotonicity,
             boundedness, ranking stability — all countries, randomized vectors)
    Phase 6: Internal verification endpoint

All tests run against the real materialized snapshot at v1.0/2024.
No mocking of snapshot data.
"""

from __future__ import annotations

import json
import os
import random
import threading
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
    ROUND_PRECISION,
)
from backend.methodology import classify, get_methodology
from backend.scenario import simulate
from backend.snapshot_cache import SnapshotCache, _artifact_to_path
from backend.snapshot_integrity import (
    EXIT_HASH_MISMATCH,
    EXIT_MANIFEST_MISMATCH,
    EXIT_METHODOLOGY_MISMATCH,
    EXIT_MISSING_FILES,
    EXIT_OK,
    EXIT_STRUCTURAL_INVARIANT,
    IntegrityReport,
    expected_files,
    validate_snapshot,
)
from backend.snapshot_resolver import (
    SNAPSHOTS_ROOT,
    SnapshotContext,
    SnapshotNotFoundError,
    resolve_snapshot,
)
from backend.verify_snapshot import main as cli_main

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


@pytest.fixture(scope="module")
def all_baselines(ctx: SnapshotContext) -> list[dict]:
    """Load the countries[] array from the snapshot's isi.json."""
    cache = SnapshotCache(max_snapshots=1)
    isi = cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
    return isi["countries"]


@pytest.fixture()
def fresh_cache() -> SnapshotCache:
    return SnapshotCache(max_snapshots=2)


# ===========================================================================
# Phase 1 — Snapshot Structural Integrity Validation
# ===========================================================================


class TestSnapshotIntegrity:
    """Full integrity validation of v1.0/2024 snapshot."""

    def test_validate_real_snapshot_passes(self):
        """Real snapshot passes all 5 check categories."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        assert report.valid, f"Validation failed: {report.errors}"
        assert report.exit_code == EXIT_OK

    def test_report_has_six_checks(self):
        """Report contains exactly 6 checks (directory_exists + 5 categories)."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        assert len(report.checks) == 6

    def test_all_checks_pass(self):
        """Every individual check is marked passed."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        for check in report.checks:
            assert check["passed"], f"Check '{check['check']}' failed: {check.get('detail')}"

    def test_no_errors_in_valid_report(self):
        """Valid report has empty errors list."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        assert report.errors == []

    def test_expected_files_count(self):
        """Expected file set has exactly 36 entries."""
        files = expected_files()
        # 1 isi.json + 1 MANIFEST.json + 1 HASH_SUMMARY.json
        # + 6 axis/*.json + 27 country/*.json = 36
        assert len(files) == 36

    def test_missing_directory_fails(self, tmp_path: Path):
        """Non-existent directory fails with EXIT_MISSING_FILES."""
        report = validate_snapshot(tmp_path / "nonexistent", "v1.0", 2024)
        assert not report.valid
        assert report.exit_code == EXIT_MISSING_FILES

    def test_empty_directory_fails(self, tmp_path: Path):
        """Empty directory fails with EXIT_MISSING_FILES."""
        empty = tmp_path / "empty"
        empty.mkdir()
        report = validate_snapshot(empty, "v1.0", 2024)
        assert not report.valid
        assert report.exit_code == EXIT_MISSING_FILES

    def test_report_to_dict_is_json_serializable(self):
        """IntegrityReport.to_dict() produces valid JSON."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        d = report.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)
        assert isinstance(serialized, str)
        roundtripped = json.loads(serialized)
        assert roundtripped["valid"] is True

    def test_wrong_methodology_fails(self):
        """Validating with wrong methodology version fails at some check."""
        report = validate_snapshot(SNAPSHOT_DIR, "v99.0", 2024)
        assert not report.valid
        # Should fail at hash_summary (methodology not in registry) or methodology_consistency
        assert report.exit_code in (
            EXIT_HASH_MISMATCH, EXIT_METHODOLOGY_MISMATCH, EXIT_STRUCTURAL_INVARIANT,
        )


# ===========================================================================
# Phase 2 — Verification CLI
# ===========================================================================


class TestVerificationCLI:
    """CLI exit codes and output modes."""

    def test_valid_snapshot_exit_0(self):
        """CLI returns exit code 0 for valid snapshot."""
        code = cli_main(["--methodology", "v1.0", "--year", "2024", "--quiet"])
        assert code == 0

    def test_invalid_year_exit_nonzero(self):
        """CLI returns non-zero for non-existent year."""
        code = cli_main(["--methodology", "v1.0", "--year", "9999", "--quiet"])
        assert code != 0

    def test_json_output_is_valid_json(self, capsys: pytest.CaptureFixture[str]):
        """CLI --json produces valid JSON output."""
        cli_main(["--methodology", "v1.0", "--year", "2024", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["valid"] is True
        assert data["exit_code"] == 0

    def test_json_output_has_checks(self, capsys: pytest.CaptureFixture[str]):
        """CLI --json output includes checks array."""
        cli_main(["--methodology", "v1.0", "--year", "2024", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "checks" in data
        assert len(data["checks"]) >= 5

    def test_human_output_contains_checkmarks(self, capsys: pytest.CaptureFixture[str]):
        """Default output contains ✓ markers."""
        cli_main(["--methodology", "v1.0", "--year", "2024"])
        output = capsys.readouterr().out
        assert "✓" in output
        assert "VALID" in output


# ===========================================================================
# Phase 3 — Cache Hardening
# ===========================================================================


class TestCacheHardening:
    """Path traversal guards, atomic eviction, concurrency."""

    def test_path_traversal_blocked(self, ctx: SnapshotContext):
        """Artifact key with path traversal is rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="Unknown artifact key"):
            cache.get_artifact(
                ctx.methodology_version, ctx.year,
                "../../../etc/passwd", ctx.path,
            )

    def test_country_code_traversal_blocked(self, ctx: SnapshotContext):
        """Country artifact with path traversal in code is caught."""
        cache = SnapshotCache(max_snapshots=1)
        # country:../../etc/passwd → should resolve outside snapshot_dir
        with pytest.raises(ValueError, match="Path traversal detected"):
            cache.get_artifact(
                ctx.methodology_version, ctx.year,
                "country:../../etc/passwd", ctx.path,
            )

    def test_axis_traversal_blocked(self, ctx: SnapshotContext):
        """Axis artifact with path traversal is caught."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="Path traversal detected"):
            cache.get_artifact(
                ctx.methodology_version, ctx.year,
                "axis:../../etc/passwd", ctx.path,
            )

    def test_empty_methodology_rejected(self, ctx: SnapshotContext):
        """Empty methodology_version is rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="non-empty string"):
            cache.get_artifact("", ctx.year, "isi", ctx.path)

    def test_negative_year_rejected(self, ctx: SnapshotContext):
        """Negative year is rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="positive integer"):
            cache.get_artifact(ctx.methodology_version, -1, "isi", ctx.path)

    def test_zero_year_rejected(self, ctx: SnapshotContext):
        """Year=0 is rejected."""
        cache = SnapshotCache(max_snapshots=1)
        with pytest.raises(ValueError, match="positive integer"):
            cache.get_artifact(ctx.methodology_version, 0, "isi", ctx.path)

    def test_atomic_eviction_no_partial_retention(self, ctx: SnapshotContext):
        """When a slot is evicted, all its artifacts are removed."""
        cache = SnapshotCache(max_snapshots=1)
        # Load multiple artifacts into one slot
        cache.get_artifact(ctx.methodology_version, ctx.year, "isi", ctx.path)
        cache.get_artifact(ctx.methodology_version, ctx.year, "country:SE", ctx.path)
        assert cache.snapshot_count == 1
        stats_before = cache.stats
        assert stats_before["slots"][0]["artifacts_cached"] == 2

        # Force eviction by loading a different snapshot key
        cache.get_artifact("v0.0-test", 2020, "isi", ctx.path)
        assert cache.snapshot_count == 1
        # The old slot should be completely gone, not partially retained
        stats_after = cache.stats
        assert stats_after["slots"][0]["methodology_version"] == "v0.0-test"
        assert stats_after["slots"][0]["year"] == 2020

    def test_concurrent_access_safe(self, ctx: SnapshotContext):
        """Multiple threads can access the cache without corruption."""
        cache = SnapshotCache(max_snapshots=3)
        errors: list[str] = []

        def worker(artifact: str) -> None:
            try:
                data = cache.get_artifact(
                    ctx.methodology_version, ctx.year, artifact, ctx.path,
                )
                if data is None and artifact in ("isi", "country:SE", "axis:1"):
                    errors.append(f"{artifact} returned None unexpectedly")
            except Exception as exc:
                errors.append(f"{artifact}: {exc}")

        threads = []
        artifacts = ["isi", "country:SE", "country:DE", "axis:1", "axis:2", "axis:3"]
        for _ in range(3):  # 3 rounds
            for art in artifacts:
                t = threading.Thread(target=worker, args=(art,))
                threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Concurrency errors: {errors}"
        assert cache.snapshot_count == 1

    def test_rapid_cross_year_access(self, ctx: SnapshotContext):
        """Rapid switching between snapshot keys maintains cache coherence."""
        cache = SnapshotCache(max_snapshots=2)
        for i in range(20):
            # Alternate between two "virtual" snapshot keys
            if i % 2 == 0:
                data = cache.get_artifact(
                    ctx.methodology_version, ctx.year, "isi", ctx.path,
                )
            else:
                data = cache.get_artifact(
                    "v0.0-alt", 2020, "isi", ctx.path,
                )
            assert data is not None
        assert cache.snapshot_count == 2

    def test_forced_eviction_under_pressure(self, ctx: SnapshotContext):
        """Cache with max_snapshots=1 handles rapid eviction gracefully."""
        cache = SnapshotCache(max_snapshots=1)
        for i in range(10):
            data = cache.get_artifact(f"v{i}.0", 2020 + i, "isi", ctx.path)
            assert data is not None
            assert cache.snapshot_count == 1

    def test_artifact_path_stays_within_snapshot_dir(self, ctx: SnapshotContext):
        """All valid artifact keys resolve within the snapshot directory."""
        artifacts = ["isi", "hash_summary", "manifest"]
        for code in EU27_SORTED:
            artifacts.append(f"country:{code}")
        for i in range(1, NUM_AXES + 1):
            artifacts.append(f"axis:{i}")

        for art in artifacts:
            resolved = _artifact_to_path(ctx.path, art)
            assert str(resolved.resolve()).startswith(str(ctx.path.resolve())), \
                f"Artifact '{art}' resolves outside snapshot dir: {resolved}"


# ===========================================================================
# Phase 4 — Determinism Enforcement
# ===========================================================================


class TestDeterminismEnforcement:
    """Verify JSON serialization and computation are deterministic."""

    def test_two_snapshot_loads_produce_identical_json(self, ctx: SnapshotContext):
        """Loading the same snapshot twice produces byte-identical JSON."""
        cache1 = SnapshotCache(max_snapshots=1)
        cache2 = SnapshotCache(max_snapshots=1)

        data1 = cache1.get_artifact(
            ctx.methodology_version, ctx.year, "isi", ctx.path,
        )
        data2 = cache2.get_artifact(
            ctx.methodology_version, ctx.year, "isi", ctx.path,
        )

        json1 = json.dumps(data1, sort_keys=True, ensure_ascii=False)
        json2 = json.dumps(data2, sort_keys=True, ensure_ascii=False)
        assert json1 == json2

    def test_country_json_deterministic(self, ctx: SnapshotContext):
        """Country JSON files produce identical dumps across two loads."""
        for code in ["SE", "DE", "MT", "CY", "FR"]:
            cache1 = SnapshotCache(max_snapshots=1)
            cache2 = SnapshotCache(max_snapshots=1)

            d1 = cache1.get_artifact(
                ctx.methodology_version, ctx.year, f"country:{code}", ctx.path,
            )
            d2 = cache2.get_artifact(
                ctx.methodology_version, ctx.year, f"country:{code}", ctx.path,
            )
            s1 = json.dumps(d1, sort_keys=True, ensure_ascii=False)
            s2 = json.dumps(d2, sort_keys=True, ensure_ascii=False)
            assert s1 == s2, f"Nondeterminism detected for country:{code}"

    def test_scenario_response_deterministic(self, client: TestClient):
        """Identical scenario inputs produce identical outputs (excluding timestamp)."""
        payload = {
            "country": "SE",
            "adjustments": {"energy_external_supplier_concentration": -0.10},
            "year": 2024,
            "methodology": "v1.0",
        }

        resp1 = client.post("/scenario", json=payload)
        resp2 = client.post("/scenario", json=payload)

        d1 = resp1.json()
        d2 = resp2.json()

        # Remove timestamps (expected to differ)
        d1["meta"].pop("timestamp", None)
        d2["meta"].pop("timestamp", None)

        assert d1 == d2, "Nondeterministic scenario response detected"

    def test_scenario_default_path_deterministic(self, client: TestClient):
        """Default scenario path (no year/methodology) is also deterministic."""
        payload = {
            "country": "DE",
            "adjustments": {"defense_external_supplier_concentration": 0.05},
        }

        resp1 = client.post("/scenario", json=payload)
        resp2 = client.post("/scenario", json=payload)

        d1 = resp1.json()
        d2 = resp2.json()
        d1["meta"].pop("timestamp", None)
        d2["meta"].pop("timestamp", None)

        assert d1 == d2

    def test_canonical_json_sort_keys(self, ctx: SnapshotContext):
        """isi.json keys are in sorted order (canonical JSON)."""
        with open(ctx.path / "isi.json", encoding="utf-8") as fh:
            raw = fh.read()
        data = json.loads(raw)
        re_serialized = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        assert raw == re_serialized, "isi.json is not in canonical sorted-key format"

    def test_hash_summary_canonical(self, ctx: SnapshotContext):
        """HASH_SUMMARY.json is in canonical sorted-key format."""
        with open(ctx.path / "HASH_SUMMARY.json", encoding="utf-8") as fh:
            raw = fh.read()
        data = json.loads(raw)
        re_serialized = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        assert raw == re_serialized

    def test_all_country_files_canonical(self, ctx: SnapshotContext):
        """All country/*.json files are in canonical sorted-key format."""
        for code in EU27_SORTED:
            path = ctx.path / "country" / f"{code}.json"
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
            data = json.loads(raw)
            re_serialized = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            assert raw == re_serialized, f"country/{code}.json not canonical"


# ===========================================================================
# Phase 5 — Scenario Engine Formal Invariants
# ===========================================================================


class TestScenarioFormalInvariants:
    """Hard mathematical invariants for the scenario engine.

    All tests run via simulate() directly — no HTTP layer, no rate limits.
    Covers all EU-27 countries and randomized adjustment vectors.
    """

    # ----- Invariant 1: Identity -----

    def test_identity_zero_adjustments_all_countries(self, all_baselines: list[dict]):
        """Zero adjustments → simulated == baseline for all EU-27."""
        for code in EU27_SORTED:
            result = simulate(code, {}, all_baselines)
            assert result.baseline.composite == result.simulated.composite, \
                f"{code}: identity invariant violated (composite)"
            assert result.baseline.rank == result.simulated.rank, \
                f"{code}: identity invariant violated (rank)"
            assert result.baseline.classification == result.simulated.classification, \
                f"{code}: identity invariant violated (classification)"

            for axis_key in CANONICAL_AXIS_KEYS:
                b = getattr(result.baseline.axes, axis_key)
                s = getattr(result.simulated.axes, axis_key)
                assert b == s, f"{code}: identity violated on axis {axis_key}"

    def test_identity_explicit_zero_adjustments(self, all_baselines: list[dict]):
        """Explicitly setting all adjustments to 0.0 → simulated == baseline."""
        adjustments = {key: 0.0 for key in CANONICAL_AXIS_KEYS}
        for code in ["SE", "DE", "MT", "CY", "FR"]:
            result = simulate(code, adjustments, all_baselines)
            assert result.baseline.composite == result.simulated.composite, \
                f"{code}: identity invariant violated with explicit zeros"

    # ----- Invariant 2: Monotonicity -----

    def test_monotonicity_positive_adjustment_all_countries(self, all_baselines: list[dict]):
        """Positive adjustment on one axis → composite must not decrease."""
        for code in EU27_SORTED:
            result = simulate(
                code,
                {"energy_external_supplier_concentration": 0.10},
                all_baselines,
            )
            assert result.simulated.composite >= result.baseline.composite, \
                f"{code}: monotonicity violated (positive adjustment)"

    def test_monotonicity_negative_adjustment_all_countries(self, all_baselines: list[dict]):
        """Negative adjustment on one axis → composite must not increase."""
        for code in EU27_SORTED:
            result = simulate(
                code,
                {"defense_external_supplier_concentration": -0.10},
                all_baselines,
            )
            assert result.simulated.composite <= result.baseline.composite, \
                f"{code}: monotonicity violated (negative adjustment)"

    def test_monotonicity_all_axes_positive(self, all_baselines: list[dict]):
        """All axes +0.10 → composite strictly increases (unless already at ceiling)."""
        adjustments = {key: 0.10 for key in CANONICAL_AXIS_KEYS}
        for code in ["SE", "DE", "FR", "PL", "IT"]:
            result = simulate(code, adjustments, all_baselines)
            if result.baseline.composite < 1.0:
                assert result.simulated.composite > result.baseline.composite, \
                    f"{code}: expected strict increase"

    # ----- Invariant 3: Boundedness -----

    def test_boundedness_all_axes_all_countries(self, all_baselines: list[dict]):
        """All simulated axis values ∈ [0, 1] for all countries."""
        for code in EU27_SORTED:
            result = simulate(
                code,
                {"energy_external_supplier_concentration": 0.20},
                all_baselines,
            )
            for axis_key in CANONICAL_AXIS_KEYS:
                val = getattr(result.simulated.axes, axis_key)
                assert 0.0 <= val <= 1.0, \
                    f"{code}: axis {axis_key} = {val} out of bounds"

    def test_boundedness_extreme_negative(self, all_baselines: list[dict]):
        """Maximum negative adjustment still produces axes ∈ [0, 1]."""
        adjustments = {key: -0.20 for key in CANONICAL_AXIS_KEYS}
        for code in EU27_SORTED:
            result = simulate(code, adjustments, all_baselines)
            for axis_key in CANONICAL_AXIS_KEYS:
                val = getattr(result.simulated.axes, axis_key)
                assert 0.0 <= val <= 1.0, \
                    f"{code}: axis {axis_key} = {val} out of bounds (extreme neg)"

    def test_boundedness_extreme_positive(self, all_baselines: list[dict]):
        """Maximum positive adjustment still produces axes ∈ [0, 1]."""
        adjustments = {key: 0.20 for key in CANONICAL_AXIS_KEYS}
        for code in EU27_SORTED:
            result = simulate(code, adjustments, all_baselines)
            for axis_key in CANONICAL_AXIS_KEYS:
                val = getattr(result.simulated.axes, axis_key)
                assert 0.0 <= val <= 1.0, \
                    f"{code}: axis {axis_key} = {val} out of bounds (extreme pos)"
            assert 0.0 <= result.simulated.composite <= 1.0

    def test_boundedness_composite_always_in_range(self, all_baselines: list[dict]):
        """Composite is always in [0, 1] regardless of adjustments."""
        random.seed(42)  # Deterministic randomization
        for code in ["SE", "DE", "MT", "CY", "FR", "IT", "PL", "AT", "BG"]:
            for _ in range(5):
                adjustments = {
                    key: random.uniform(-0.20, 0.20)
                    for key in random.sample(list(CANONICAL_AXIS_KEYS), k=random.randint(1, 6))
                }
                result = simulate(code, adjustments, all_baselines)
                assert 0.0 <= result.simulated.composite <= 1.0, \
                    f"{code}: composite {result.simulated.composite} out of [0,1]"

    # ----- Invariant 4: Ranking stability -----

    def test_ranking_stability_zero_adjustment(self, all_baselines: list[dict]):
        """Zero adjustments → rank unchanged for all countries."""
        for code in EU27_SORTED:
            result = simulate(code, {}, all_baselines)
            assert result.baseline.rank == result.simulated.rank, \
                f"{code}: rank changed with zero adjustments"
            assert result.delta.rank == 0, \
                f"{code}: delta rank != 0 with zero adjustments"

    def test_rank_always_in_1_to_27(self, all_baselines: list[dict]):
        """Simulated rank is always in [1, 27]."""
        random.seed(123)
        for code in EU27_SORTED:
            adjustments = {
                key: random.uniform(-0.20, 0.20)
                for key in random.sample(list(CANONICAL_AXIS_KEYS), k=random.randint(0, 6))
            }
            result = simulate(code, adjustments, all_baselines)
            assert 1 <= result.simulated.rank <= 27, \
                f"{code}: simulated rank {result.simulated.rank} out of [1, 27]"
            assert 1 <= result.baseline.rank <= 27

    # ----- Cross-cutting: Randomized invariant vectors -----

    def test_randomized_invariants_50_vectors(self, all_baselines: list[dict]):
        """50 random adjustment vectors across random countries.

        All must satisfy: boundedness, and rank range.
        """
        random.seed(999)
        countries = list(EU27_SORTED)
        m = get_methodology("v1.0")
        valid_labels = {t[1] for t in m["classification_thresholds"]}
        valid_labels.add(m["default_classification"])

        for _ in range(50):
            code = random.choice(countries)
            num_axes = random.randint(0, 6)
            axes_to_adjust = random.sample(list(CANONICAL_AXIS_KEYS), k=num_axes)
            adjustments = {key: random.uniform(-0.20, 0.20) for key in axes_to_adjust}

            result = simulate(code, adjustments, all_baselines)

            # Boundedness
            for axis_key in CANONICAL_AXIS_KEYS:
                v = getattr(result.simulated.axes, axis_key)
                assert 0.0 <= v <= 1.0, f"{code}: axis {axis_key} = {v}"

            assert 0.0 <= result.simulated.composite <= 1.0
            assert 1 <= result.simulated.rank <= 27

            # Classification is a valid label
            assert result.simulated.classification in valid_labels


# ===========================================================================
# Phase 6 — Internal Verification Endpoint
# ===========================================================================


class TestInternalVerifyEndpoint:
    """GET /_internal/snapshot/verify (requires ENABLE_INTERNAL_VERIFY=1)."""

    def test_endpoint_disabled_by_default(self, client: TestClient):
        """Without ENABLE_INTERNAL_VERIFY=1, endpoint returns 404."""
        # The endpoint is only registered when the flag is set.
        # When flag is not set at import time, this should 404.
        if os.getenv("ENABLE_INTERNAL_VERIFY", "") != "1":
            resp = client.get("/_internal/snapshot/verify?methodology=v1.0&year=2024")
            assert resp.status_code in (404, 405)

    def test_endpoint_not_in_openapi_schema(self, client: TestClient):
        """Internal endpoint is excluded from OpenAPI schema."""
        resp = client.get("/openapi.json")
        if resp.status_code == 200:
            schema = resp.json()
            paths = schema.get("paths", {})
            assert "/_internal/snapshot/verify" not in paths


# ===========================================================================
# Cross-Phase: Strict Validation Integration
# ===========================================================================


class TestStrictValidationIntegration:
    """Verify strict validation mode wiring in resolver."""

    def test_strict_mode_env_var_exists(self):
        """SNAPSHOT_STRICT_VALIDATION env var is wired into resolver."""
        from backend.snapshot_resolver import STRICT_VALIDATION
        # Just verify the attribute exists and is a bool
        assert isinstance(STRICT_VALIDATION, bool)

    def test_validated_snapshots_cache_exists(self):
        """_validated_snapshots set exists in resolver module."""
        from backend.snapshot_resolver import _validated_snapshots
        assert isinstance(_validated_snapshots, set)

    def test_resolve_still_works_without_strict_mode(self):
        """resolve_snapshot works normally without strict mode."""
        # This confirms strict mode is opt-in and default path is unchanged
        ctx = resolve_snapshot(methodology="v1.0", year=2024)
        assert ctx.methodology_version == "v1.0"
        assert ctx.year == 2024
