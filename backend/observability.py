"""
backend.observability — Pipeline Observability and Structured Metrics

Provides per-layer metrics, execution time tracking, anomaly pattern
detection, and structured logging for the ISI pipeline.

Design contract:
    - Every pipeline execution is observable.
    - Metrics are structured (not free-text log lines).
    - Anomaly patterns are detected deterministically.
    - Observer is side-effect free — it reads pipeline results, never modifies.
    - All output is serializable to JSON.

Honesty note:
    Observability helps detect WHEN things go wrong. It does not
    prevent errors or guarantee correctness. A perfectly observable
    system can still produce wrong results.
"""

from __future__ import annotations

import time
from typing import Any

from backend.layer_result import LayerExecutionStatus
from backend.failure_severity import (
    FailureSeverity,
    SEVERITY_ORDER,
)


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE METRICS COLLECTOR
# ═══════════════════════════════════════════════════════════════════════════

class PipelineMetrics:
    """Collects and aggregates metrics across pipeline executions.

    Thread-safe under CPython GIL (single-writer pattern).
    """

    def __init__(self) -> None:
        self._executions: int = 0
        self._layer_counts: dict[str, dict[str, int]] = {}
        # layer_name → {SUCCESS: n, DEGRADED: n, FAILED: n, SKIPPED: n}
        self._layer_timing_sums: dict[str, float] = {}
        self._layer_timing_counts: dict[str, int] = {}
        self._total_time_sum: float = 0.0
        self._anomalies: list[dict[str, Any]] = []
        self._severity_counts: dict[str, int] = {
            s.value: 0 for s in FailureSeverity
        }

    def record_execution(self, pipeline_state: dict[str, Any]) -> dict[str, Any]:
        """Record metrics from a completed pipeline execution.

        Args:
            pipeline_state: The state dict returned by run_pipeline(),
                containing _pipeline_results, _pipeline_status, etc.

        Returns:
            Metrics summary for this execution.
        """
        self._executions += 1

        results = pipeline_state.get("_pipeline_results", [])
        total_ms = pipeline_state.get("_pipeline_total_ms", 0.0)
        self._total_time_sum += total_ms

        execution_metrics: dict[str, Any] = {
            "execution_number": self._executions,
            "pipeline_status": pipeline_state.get("_pipeline_status", "UNKNOWN"),
            "total_ms": total_ms,
            "n_layers": len(results),
            "layer_metrics": [],
        }

        for result in results:
            layer_name = result["layer_name"]
            status = result["status"]
            timing = result.get("timing_ms", 0.0)

            # Initialize layer counters if needed
            if layer_name not in self._layer_counts:
                self._layer_counts[layer_name] = {
                    s.value: 0 for s in LayerExecutionStatus
                }
                self._layer_timing_sums[layer_name] = 0.0
                self._layer_timing_counts[layer_name] = 0

            # Update counts
            if status in self._layer_counts[layer_name]:
                self._layer_counts[layer_name][status] += 1
            self._layer_timing_sums[layer_name] += timing
            self._layer_timing_counts[layer_name] += 1

            execution_metrics["layer_metrics"].append({
                "layer_name": layer_name,
                "status": status,
                "timing_ms": timing,
                "n_warnings": result.get("n_warnings", 0),
                "n_errors": result.get("n_errors", 0),
            })

        # Record worst severity
        worst = pipeline_state.get("_pipeline_worst_severity", "INFO")
        if worst in self._severity_counts:
            self._severity_counts[worst] += 1

        # Detect anomalies
        anomalies = detect_anomalies(pipeline_state)
        if anomalies:
            self._anomalies.extend(anomalies)
            execution_metrics["anomalies"] = anomalies

        return execution_metrics

    @property
    def summary(self) -> dict[str, Any]:
        """Aggregate metrics summary across all executions."""
        layer_summaries: dict[str, dict[str, Any]] = {}
        for layer_name, counts in self._layer_counts.items():
            total = self._layer_timing_counts.get(layer_name, 0)
            avg_ms = (
                self._layer_timing_sums[layer_name] / total
                if total > 0 else 0.0
            )
            layer_summaries[layer_name] = {
                "status_counts": dict(counts),
                "avg_timing_ms": avg_ms,
                "total_executions": total,
                "success_rate": (
                    counts.get("SUCCESS", 0) / total if total > 0 else 0.0
                ),
            }

        return {
            "total_executions": self._executions,
            "avg_total_ms": (
                self._total_time_sum / self._executions
                if self._executions > 0 else 0.0
            ),
            "severity_counts": dict(self._severity_counts),
            "n_anomalies": len(self._anomalies),
            "layer_summaries": layer_summaries,
        }

    @property
    def recent_anomalies(self) -> list[dict[str, Any]]:
        """Return the last 100 anomalies."""
        return self._anomalies[-100:]

    def reset(self) -> None:
        """Reset all metrics."""
        self._executions = 0
        self._layer_counts.clear()
        self._layer_timing_sums.clear()
        self._layer_timing_counts.clear()
        self._total_time_sum = 0.0
        self._anomalies.clear()
        self._severity_counts = {s.value: 0 for s in FailureSeverity}


# ═══════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION
# ═══════════════════════════════════════════════════════════════════════════

# Threshold for what constitutes a "slow" layer (ms)
SLOW_LAYER_THRESHOLD_MS = 5000.0

# Threshold for total pipeline being too slow
SLOW_PIPELINE_THRESHOLD_MS = 30000.0


def detect_anomalies(pipeline_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect anomaly patterns in a pipeline execution.

    Anomalies are structural patterns that are not errors per se but
    indicate something unusual that should be investigated.

    Args:
        pipeline_state: The state dict from run_pipeline().

    Returns:
        List of anomaly dicts.
    """
    anomalies: list[dict[str, Any]] = []
    results = pipeline_state.get("_pipeline_results", [])
    total_ms = pipeline_state.get("_pipeline_total_ms", 0.0)
    degraded = pipeline_state.get("_pipeline_degraded_layers", [])
    failed = pipeline_state.get("_pipeline_failed_layers", [])
    skipped = pipeline_state.get("_pipeline_skipped_layers", [])

    # Anomaly 1: Too many degraded layers
    if len(degraded) >= 3:
        anomalies.append({
            "anomaly_id": "ANOMALY-001",
            "pattern": "EXCESSIVE_DEGRADATION",
            "description": (
                f"{len(degraded)} layers degraded: {', '.join(degraded)}. "
                f"This suggests systemic data quality issues."
            ),
            "severity": "WARNING",
            "evidence": {"degraded_layers": degraded},
        })

    # Anomaly 2: Slow layer
    for result in results:
        timing = result.get("timing_ms", 0.0)
        if timing > SLOW_LAYER_THRESHOLD_MS:
            anomalies.append({
                "anomaly_id": "ANOMALY-002",
                "pattern": "SLOW_LAYER",
                "description": (
                    f"Layer '{result['layer_name']}' took {timing:.1f}ms "
                    f"(threshold: {SLOW_LAYER_THRESHOLD_MS}ms)."
                ),
                "severity": "INFO",
                "evidence": {
                    "layer_name": result["layer_name"],
                    "timing_ms": timing,
                    "threshold_ms": SLOW_LAYER_THRESHOLD_MS,
                },
            })

    # Anomaly 3: Slow pipeline total
    if total_ms > SLOW_PIPELINE_THRESHOLD_MS:
        anomalies.append({
            "anomaly_id": "ANOMALY-003",
            "pattern": "SLOW_PIPELINE",
            "description": (
                f"Total pipeline execution took {total_ms:.1f}ms "
                f"(threshold: {SLOW_PIPELINE_THRESHOLD_MS}ms)."
            ),
            "severity": "WARNING",
            "evidence": {
                "total_ms": total_ms,
                "threshold_ms": SLOW_PIPELINE_THRESHOLD_MS,
            },
        })

    # Anomaly 4: Failed layers exist
    if failed:
        anomalies.append({
            "anomaly_id": "ANOMALY-004",
            "pattern": "LAYER_FAILURES",
            "description": (
                f"{len(failed)} layers failed: {', '.join(failed)}. "
                f"{len(skipped)} layers skipped as consequence."
            ),
            "severity": "ERROR",
            "evidence": {
                "failed_layers": failed,
                "skipped_layers": skipped,
            },
        })

    # Anomaly 5: All layers degraded (unlikely in practice)
    n_total = len(results)
    if n_total > 0 and len(degraded) == n_total:
        anomalies.append({
            "anomaly_id": "ANOMALY-005",
            "pattern": "TOTAL_DEGRADATION",
            "description": (
                "Every single layer is degraded. "
                "This is structurally suspicious."
            ),
            "severity": "CRITICAL",
            "evidence": {"n_layers": n_total, "all_degraded": True},
        })

    return anomalies


# ═══════════════════════════════════════════════════════════════════════════
# STRUCTURED LOG ENTRIES
# ═══════════════════════════════════════════════════════════════════════════

def build_log_entry(
    country: str,
    layer_name: str,
    status: str,
    severity: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a structured log entry.

    Args:
        country: ISO-2 code.
        layer_name: Pipeline layer name.
        status: Execution status.
        severity: Log severity.
        message: Human-readable message.
        extra: Additional context.

    Returns:
        Structured log dict.
    """
    entry: dict[str, Any] = {
        "timestamp_mono": time.monotonic(),
        "country": country,
        "layer": layer_name,
        "status": status,
        "severity": severity,
        "message": message,
    }
    if extra:
        entry["extra"] = extra
    return entry


def build_execution_summary(
    pipeline_state: dict[str, Any],
    country: str,
) -> dict[str, Any]:
    """Build a human-readable execution summary.

    Args:
        pipeline_state: State dict from run_pipeline().
        country: ISO-2 code for context.

    Returns:
        Summary dict suitable for logging or API response.
    """
    results = pipeline_state.get("_pipeline_results", [])
    status = pipeline_state.get("_pipeline_status", "UNKNOWN")
    total_ms = pipeline_state.get("_pipeline_total_ms", 0.0)
    degraded = pipeline_state.get("_pipeline_degraded_layers", [])
    failed = pipeline_state.get("_pipeline_failed_layers", [])
    skipped = pipeline_state.get("_pipeline_skipped_layers", [])

    n_success = sum(
        1 for r in results if r.get("status") == "SUCCESS"
    )

    return {
        "country": country,
        "pipeline_status": status,
        "total_ms": round(total_ms, 2),
        "n_layers_total": len(results),
        "n_success": n_success,
        "n_degraded": len(degraded),
        "n_failed": len(failed),
        "n_skipped": len(skipped),
        "degraded_layers": degraded,
        "failed_layers": failed,
        "skipped_layers": skipped,
        "worst_severity": pipeline_state.get("_pipeline_worst_severity", "INFO"),
    }
