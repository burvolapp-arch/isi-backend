"""
tests/test_observability.py — Tests for Pipeline Observability

Verifies:
    1. PipelineMetrics records executions correctly.
    2. Anomaly detection works for various patterns.
    3. Structured log entries have correct shape.
    4. Execution summary is correct.
    5. Metrics reset works.
"""

from __future__ import annotations

import unittest

from backend.observability import (
    PipelineMetrics,
    detect_anomalies,
    build_log_entry,
    build_execution_summary,
    SLOW_LAYER_THRESHOLD_MS,
    SLOW_PIPELINE_THRESHOLD_MS,
)


def _make_pipeline_state(
    status="HEALTHY",
    total_ms=100.0,
    results=None,
    degraded=None,
    failed=None,
    skipped=None,
    worst_severity="INFO",
):
    """Helper to build a mock pipeline state dict."""
    return {
        "_pipeline_status": status,
        "_pipeline_total_ms": total_ms,
        "_pipeline_results": results or [],
        "_pipeline_degraded_layers": degraded or [],
        "_pipeline_failed_layers": failed or [],
        "_pipeline_skipped_layers": skipped or [],
        "_pipeline_worst_severity": worst_severity,
    }


class TestPipelineMetricsRecording(unittest.TestCase):
    """PipelineMetrics recording tests."""

    def test_initial_state(self):
        metrics = PipelineMetrics()
        summary = metrics.summary
        self.assertEqual(summary["total_executions"], 0)
        self.assertEqual(summary["avg_total_ms"], 0.0)

    def test_record_single_execution(self):
        metrics = PipelineMetrics()
        state = _make_pipeline_state(
            results=[
                {"layer_name": "a", "status": "SUCCESS", "timing_ms": 10.0,
                 "n_warnings": 0, "n_errors": 0},
            ],
        )
        result = metrics.record_execution(state)
        self.assertEqual(result["execution_number"], 1)
        self.assertEqual(result["pipeline_status"], "HEALTHY")

    def test_record_multiple_executions(self):
        metrics = PipelineMetrics()
        for _ in range(5):
            state = _make_pipeline_state(
                total_ms=50.0,
                results=[
                    {"layer_name": "a", "status": "SUCCESS", "timing_ms": 50.0,
                     "n_warnings": 0, "n_errors": 0},
                ],
            )
            metrics.record_execution(state)
        summary = metrics.summary
        self.assertEqual(summary["total_executions"], 5)
        self.assertAlmostEqual(summary["avg_total_ms"], 50.0)

    def test_layer_success_rate(self):
        metrics = PipelineMetrics()
        # 2 successes
        for _ in range(2):
            state = _make_pipeline_state(
                results=[
                    {"layer_name": "a", "status": "SUCCESS", "timing_ms": 10.0,
                     "n_warnings": 0, "n_errors": 0},
                ],
            )
            metrics.record_execution(state)
        # 1 degraded
        state = _make_pipeline_state(
            status="DEGRADED",
            degraded=["a"],
            results=[
                {"layer_name": "a", "status": "DEGRADED", "timing_ms": 10.0,
                 "n_warnings": 1, "n_errors": 0},
            ],
        )
        metrics.record_execution(state)
        summary = metrics.summary
        self.assertAlmostEqual(
            summary["layer_summaries"]["a"]["success_rate"],
            2 / 3,
        )

    def test_reset_clears_everything(self):
        metrics = PipelineMetrics()
        state = _make_pipeline_state(
            results=[
                {"layer_name": "a", "status": "SUCCESS", "timing_ms": 10.0,
                 "n_warnings": 0, "n_errors": 0},
            ],
        )
        metrics.record_execution(state)
        metrics.reset()
        summary = metrics.summary
        self.assertEqual(summary["total_executions"], 0)
        self.assertEqual(summary["layer_summaries"], {})


class TestAnomalyDetection(unittest.TestCase):
    """Anomaly detection tests."""

    def test_no_anomalies_for_healthy_pipeline(self):
        state = _make_pipeline_state(
            results=[
                {"layer_name": "a", "status": "SUCCESS", "timing_ms": 10.0},
            ],
        )
        anomalies = detect_anomalies(state)
        self.assertEqual(len(anomalies), 0)

    def test_excessive_degradation_anomaly(self):
        state = _make_pipeline_state(
            status="DEGRADED",
            degraded=["a", "b", "c"],
            results=[
                {"layer_name": "a", "status": "DEGRADED", "timing_ms": 10.0},
                {"layer_name": "b", "status": "DEGRADED", "timing_ms": 10.0},
                {"layer_name": "c", "status": "DEGRADED", "timing_ms": 10.0},
            ],
        )
        anomalies = detect_anomalies(state)
        anomaly_ids = [a["anomaly_id"] for a in anomalies]
        self.assertIn("ANOMALY-001", anomaly_ids)

    def test_slow_layer_anomaly(self):
        state = _make_pipeline_state(
            results=[
                {"layer_name": "a", "status": "SUCCESS",
                 "timing_ms": SLOW_LAYER_THRESHOLD_MS + 1000},
            ],
        )
        anomalies = detect_anomalies(state)
        anomaly_ids = [a["anomaly_id"] for a in anomalies]
        self.assertIn("ANOMALY-002", anomaly_ids)

    def test_slow_pipeline_anomaly(self):
        state = _make_pipeline_state(
            total_ms=SLOW_PIPELINE_THRESHOLD_MS + 1000,
            results=[],
        )
        anomalies = detect_anomalies(state)
        anomaly_ids = [a["anomaly_id"] for a in anomalies]
        self.assertIn("ANOMALY-003", anomaly_ids)

    def test_layer_failure_anomaly(self):
        state = _make_pipeline_state(
            status="FAILED",
            failed=["governance"],
            skipped=["decision_usability"],
            results=[
                {"layer_name": "governance", "status": "FAILED", "timing_ms": 5.0},
                {"layer_name": "decision_usability", "status": "SKIPPED", "timing_ms": 0.0},
            ],
        )
        anomalies = detect_anomalies(state)
        anomaly_ids = [a["anomaly_id"] for a in anomalies]
        self.assertIn("ANOMALY-004", anomaly_ids)

    def test_total_degradation_anomaly(self):
        state = _make_pipeline_state(
            status="DEGRADED",
            degraded=["a", "b"],
            results=[
                {"layer_name": "a", "status": "DEGRADED", "timing_ms": 10.0},
                {"layer_name": "b", "status": "DEGRADED", "timing_ms": 10.0},
            ],
        )
        anomalies = detect_anomalies(state)
        anomaly_ids = [a["anomaly_id"] for a in anomalies]
        self.assertIn("ANOMALY-005", anomaly_ids)


class TestStructuredLogEntries(unittest.TestCase):
    """Structured log entry tests."""

    def test_log_entry_shape(self):
        entry = build_log_entry(
            country="DE",
            layer_name="severity",
            status="SUCCESS",
            severity="INFO",
            message="Layer completed",
        )
        self.assertEqual(entry["country"], "DE")
        self.assertEqual(entry["layer"], "severity")
        self.assertEqual(entry["status"], "SUCCESS")
        self.assertEqual(entry["severity"], "INFO")
        self.assertEqual(entry["message"], "Layer completed")
        self.assertIn("timestamp_mono", entry)

    def test_log_entry_with_extra(self):
        entry = build_log_entry(
            country="FR",
            layer_name="governance",
            status="DEGRADED",
            severity="WARNING",
            message="Fallback used",
            extra={"fallback_reason": "missing data"},
        )
        self.assertIn("extra", entry)
        self.assertEqual(entry["extra"]["fallback_reason"], "missing data")


class TestExecutionSummary(unittest.TestCase):
    """Execution summary tests."""

    def test_healthy_summary(self):
        state = _make_pipeline_state(
            total_ms=150.5,
            results=[
                {"layer_name": "a", "status": "SUCCESS", "timing_ms": 50.0},
                {"layer_name": "b", "status": "SUCCESS", "timing_ms": 100.5},
            ],
        )
        summary = build_execution_summary(state, "DE")
        self.assertEqual(summary["country"], "DE")
        self.assertEqual(summary["pipeline_status"], "HEALTHY")
        self.assertEqual(summary["n_layers_total"], 2)
        self.assertEqual(summary["n_success"], 2)
        self.assertEqual(summary["n_degraded"], 0)
        self.assertEqual(summary["n_failed"], 0)
        self.assertAlmostEqual(summary["total_ms"], 150.5)

    def test_degraded_summary(self):
        state = _make_pipeline_state(
            status="DEGRADED",
            degraded=["b"],
            total_ms=200.0,
            results=[
                {"layer_name": "a", "status": "SUCCESS", "timing_ms": 50.0},
                {"layer_name": "b", "status": "DEGRADED", "timing_ms": 150.0},
            ],
        )
        summary = build_execution_summary(state, "FR")
        self.assertEqual(summary["pipeline_status"], "DEGRADED")
        self.assertEqual(summary["n_success"], 1)
        self.assertEqual(summary["n_degraded"], 1)
        self.assertEqual(summary["degraded_layers"], ["b"])


class TestRecentAnomalies(unittest.TestCase):
    """Recent anomalies capping."""

    def test_recent_anomalies_capped_at_100(self):
        metrics = PipelineMetrics()
        # Force anomalies by creating many degraded pipelines
        for i in range(50):
            state = _make_pipeline_state(
                status="FAILED",
                failed=[f"layer_{i}"],
                skipped=[f"dep_{i}"],
                results=[
                    {"layer_name": f"layer_{i}", "status": "FAILED", "timing_ms": 1.0},
                    {"layer_name": f"dep_{i}", "status": "SKIPPED", "timing_ms": 0.0},
                ],
            )
            metrics.record_execution(state)
        # Should have at most 100 recent anomalies
        recent = metrics.recent_anomalies
        self.assertLessEqual(len(recent), 100)


if __name__ == "__main__":
    unittest.main()
