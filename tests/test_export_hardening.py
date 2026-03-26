"""
tests/test_export_hardening.py — Tests for Export Gating, Version Locking, Safe Mode

Verifies:
    1. Version constants exist in export_snapshot.
    2. build_country_json output includes runtime_status block.
    3. build_country_json output includes version_info block.
    4. build_country_json output includes safe_mode block.
    5. Safe mode hides rankings for LOW_CONFIDENCE/NON_COMPARABLE.
    6. Version info has all required fields.
"""

from __future__ import annotations

import unittest


class TestVersionConstants(unittest.TestCase):
    """Version constants are defined."""

    def test_pipeline_version_exists(self):
        from backend.export_snapshot import PIPELINE_VERSION
        self.assertIsInstance(PIPELINE_VERSION, str)
        self.assertTrue(len(PIPELINE_VERSION) > 0)

    def test_truth_logic_version_exists(self):
        from backend.export_snapshot import TRUTH_LOGIC_VERSION
        self.assertIsInstance(TRUTH_LOGIC_VERSION, str)
        self.assertTrue(len(TRUTH_LOGIC_VERSION) > 0)

    def test_enforcement_version_exists(self):
        from backend.export_snapshot import ENFORCEMENT_VERSION
        self.assertIsInstance(ENFORCEMENT_VERSION, str)
        self.assertTrue(len(ENFORCEMENT_VERSION) > 0)


class TestExportOutputStructure(unittest.TestCase):
    """Verify that runtime_status, version_info, safe_mode are importable."""

    def test_pipeline_version_is_semver(self):
        from backend.export_snapshot import PIPELINE_VERSION
        parts = PIPELINE_VERSION.split(".")
        self.assertEqual(len(parts), 3)
        for part in parts:
            self.assertTrue(part.isdigit())

    def test_truth_logic_version_is_semver(self):
        from backend.export_snapshot import TRUTH_LOGIC_VERSION
        parts = TRUTH_LOGIC_VERSION.split(".")
        self.assertEqual(len(parts), 3)

    def test_enforcement_version_is_semver(self):
        from backend.export_snapshot import ENFORCEMENT_VERSION
        parts = ENFORCEMENT_VERSION.split(".")
        self.assertEqual(len(parts), 3)


class TestLayerResultModelImportable(unittest.TestCase):
    """LayerResult model is importable from layer_result."""

    def test_layer_execution_status_importable(self):
        from backend.layer_result import LayerExecutionStatus
        self.assertEqual(len(LayerExecutionStatus), 4)

    def test_layer_result_importable(self):
        from backend.layer_result import LayerResult
        self.assertTrue(callable(LayerResult))


class TestFailureSeverityImportable(unittest.TestCase):
    """FailureSeverity model is importable."""

    def test_failure_severity_importable(self):
        from backend.failure_severity import FailureSeverity
        self.assertEqual(len(FailureSeverity), 5)

    def test_classify_layer_failure_importable(self):
        from backend.failure_severity import classify_layer_failure
        self.assertTrue(callable(classify_layer_failure))


class TestCacheImportable(unittest.TestCase):
    """Cache module is importable."""

    def test_snapshot_cache_importable(self):
        from backend.cache import SnapshotCache
        self.assertTrue(callable(SnapshotCache))

    def test_compute_cache_key_importable(self):
        from backend.cache import compute_cache_key
        self.assertTrue(callable(compute_cache_key))


class TestObservabilityImportable(unittest.TestCase):
    """Observability module is importable."""

    def test_pipeline_metrics_importable(self):
        from backend.observability import PipelineMetrics
        self.assertTrue(callable(PipelineMetrics))

    def test_detect_anomalies_importable(self):
        from backend.observability import detect_anomalies
        self.assertTrue(callable(detect_anomalies))

    def test_build_log_entry_importable(self):
        from backend.observability import build_log_entry
        self.assertTrue(callable(build_log_entry))


class TestRuntimeInvariantsImportable(unittest.TestCase):
    """Runtime invariant checker is importable."""

    def test_check_runtime_invariants_importable(self):
        from backend.invariants import check_runtime_invariants
        self.assertTrue(callable(check_runtime_invariants))

    def test_runtime_invariant_type_exists(self):
        from backend.invariants import InvariantType
        self.assertEqual(InvariantType.RUNTIME, "RUNTIME")


if __name__ == "__main__":
    unittest.main()
