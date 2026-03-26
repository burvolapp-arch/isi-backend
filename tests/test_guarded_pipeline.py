"""
tests/test_guarded_pipeline.py — Tests for Guarded Pipeline Executor

Verifies:
    1. Pipeline tracks timing per layer.
    2. Pipeline records degraded/failed/skipped layers.
    3. Pipeline status reflects layer health.
    4. Critical layer failure short-circuits remaining layers.
    5. Pipeline runtime metadata is correct.
    6. Non-critical PipelineError still raises.
"""

from __future__ import annotations

import unittest

from backend.layer_pipeline import (
    Layer,
    PipelineError,
    run_pipeline,
)


class TestPipelineRuntimeMetadata(unittest.TestCase):
    """Pipeline produces runtime metadata."""

    def test_healthy_pipeline_has_status(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_status"], "HEALTHY")

    def test_healthy_pipeline_has_timing(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
        ]
        result = run_pipeline(layers, {})
        self.assertGreaterEqual(result["_pipeline_total_ms"], 0.0)

    def test_healthy_pipeline_no_degraded_or_failed(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_degraded_layers"], [])
        self.assertEqual(result["_pipeline_failed_layers"], [])
        self.assertEqual(result["_pipeline_skipped_layers"], [])

    def test_pipeline_results_list(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {"y": 2}, requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        result = run_pipeline(layers, {})
        results = result["_pipeline_results"]
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["layer_name"], "a")
        self.assertEqual(results[0]["status"], "SUCCESS")
        self.assertIn("timing_ms", results[0])

    def test_pipeline_worst_severity_info_when_healthy(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_worst_severity"], "INFO")


class TestDegradedLayerDetection(unittest.TestCase):
    """Pipeline detects degraded layers (layers with error fields in output)."""

    def test_layer_with_error_field_is_degraded(self):
        def degraded_compute(state, ctx):
            return {"result": {"error": "Something went wrong", "fallback": True}}

        layers = [
            Layer(name="a", compute=degraded_compute, produces=frozenset({"result"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_status"], "DEGRADED")
        self.assertIn("a", result["_pipeline_degraded_layers"])

    def test_degraded_result_has_warnings(self):
        def degraded_compute(state, ctx):
            return {"result": {"error": "fallback data", "value": 0}}

        layers = [
            Layer(name="a", compute=degraded_compute, produces=frozenset({"result"})),
        ]
        result = run_pipeline(layers, {})
        results = result["_pipeline_results"]
        self.assertEqual(results[0]["status"], "DEGRADED")
        self.assertGreater(results[0]["n_warnings"], 0)

    def test_mixed_healthy_and_degraded(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {"y": {"error": "oops"}},
                  requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_status"], "DEGRADED")
        self.assertNotIn("a", result["_pipeline_degraded_layers"])
        self.assertIn("b", result["_pipeline_degraded_layers"])


class TestCriticalLayerFailure(unittest.TestCase):
    """Critical layer failures short-circuit remaining layers."""

    def test_critical_layer_failure_skips_dependents(self):
        """When 'severity' (critical) fails, downstream layers are skipped."""
        def failing_severity(state, ctx):
            raise ValueError("data corruption")

        def governance_compute(state, ctx):
            return {"governance": {}}

        layers = [
            Layer(name="severity", compute=failing_severity,
                  produces=frozenset({"severity_analysis", "strict_comparability_tier"})),
            Layer(name="governance", compute=governance_compute,
                  requires=frozenset({"severity"}),
                  produces=frozenset({"governance"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_status"], "FAILED")
        self.assertIn("severity", result["_pipeline_failed_layers"])
        self.assertIn("governance", result["_pipeline_skipped_layers"])

    def test_critical_failure_records_error(self):
        def failing_governance(state, ctx):
            raise RuntimeError("database down")

        layers = [
            Layer(name="governance", compute=failing_governance,
                  produces=frozenset({"governance"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_status"], "FAILED")
        results = result["_pipeline_results"]
        self.assertEqual(results[0]["status"], "FAILED")
        self.assertGreater(results[0]["n_errors"], 0)

    def test_non_critical_failure_still_raises(self):
        """Non-critical layers that fail without fallback still raise PipelineError."""
        def failing_non_critical(state, ctx):
            raise ValueError("oops")

        layers = [
            Layer(name="external_validation", compute=failing_non_critical,
                  produces=frozenset({"external_validation"})),
        ]
        with self.assertRaises(PipelineError):
            run_pipeline(layers, {})


class TestPipelineTimingTracking(unittest.TestCase):
    """Pipeline tracks per-layer timing."""

    def test_timing_is_non_negative(self):
        import time

        def slow_compute(state, ctx):
            time.sleep(0.01)
            return {"x": 1}

        layers = [
            Layer(name="a", compute=slow_compute, produces=frozenset({"x"})),
        ]
        result = run_pipeline(layers, {})
        results = result["_pipeline_results"]
        self.assertGreater(results[0]["timing_ms"], 0.0)

    def test_total_timing_tracks(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {"y": 2}, requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        result = run_pipeline(layers, {})
        self.assertGreaterEqual(result["_pipeline_total_ms"], 0.0)


class TestEmptyPipelineRuntime(unittest.TestCase):
    """Empty pipeline still produces runtime metadata."""

    def test_empty_pipeline_healthy(self):
        result = run_pipeline([], {})
        self.assertEqual(result["_pipeline_status"], "HEALTHY")
        self.assertEqual(result["_pipeline_degraded_layers"], [])
        self.assertEqual(result["_pipeline_failed_layers"], [])
        self.assertEqual(result["_pipeline_results"], [])
        self.assertEqual(result["_pipeline_worst_severity"], "INFO")


if __name__ == "__main__":
    unittest.main()
