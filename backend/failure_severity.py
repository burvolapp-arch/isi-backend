"""
backend.failure_severity — Failure Severity Classification Model

Defines the canonical severity levels for failures across the ISI pipeline.
These feed into enforcement, truth resolution, export gating, and observability.

Severity Hierarchy (lowest → highest):
    INFO       — Informational, no action required.
    WARNING    — Potential issue, logged but no enforcement.
    ERROR      — Confirmed issue, triggers enforcement action.
    CRITICAL   — Structural failure, may block export.
    INVALIDATING — Fatal, export MUST be blocked.

Design contract:
    - Severity is ordinal — higher severity always takes precedence.
    - Every pipeline event must be classifiable by this enum.
    - CRITICAL and INVALIDATING must always produce consequences.

Honesty note:
    This model does NOT determine truth — it classifies the
    consequences of detected problems. A WARNING that should
    be CRITICAL is a design error, not a runtime error.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# FAILURE SEVERITY ENUM
# ═══════════════════════════════════════════════════════════════════════════

class FailureSeverity(Enum):
    """Canonical severity levels for pipeline failures.

    Ordinal: INFO < WARNING < ERROR < CRITICAL < INVALIDATING.
    """
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    INVALIDATING = "INVALIDATING"


VALID_FAILURE_SEVERITIES = frozenset({
    FailureSeverity.INFO,
    FailureSeverity.WARNING,
    FailureSeverity.ERROR,
    FailureSeverity.CRITICAL,
    FailureSeverity.INVALIDATING,
})

# Ordinal mapping for comparison
SEVERITY_ORDER: dict[FailureSeverity, int] = {
    FailureSeverity.INFO: 0,
    FailureSeverity.WARNING: 1,
    FailureSeverity.ERROR: 2,
    FailureSeverity.CRITICAL: 3,
    FailureSeverity.INVALIDATING: 4,
}

# Severities that MUST produce enforcement consequences
CONSEQUENTIAL_SEVERITIES = frozenset({
    FailureSeverity.CRITICAL,
    FailureSeverity.INVALIDATING,
})

# Severities that block export
EXPORT_BLOCKING_SEVERITIES = frozenset({
    FailureSeverity.INVALIDATING,
})


def worst_severity(*severities: FailureSeverity) -> FailureSeverity:
    """Return the worst (highest) severity from a collection.

    Args:
        *severities: One or more FailureSeverity values.

    Returns:
        The most severe value.

    Raises:
        ValueError: If no severities provided.
    """
    if not severities:
        raise ValueError("worst_severity requires at least one severity")
    return max(severities, key=lambda s: SEVERITY_ORDER[s])


def severity_at_least(
    severity: FailureSeverity,
    threshold: FailureSeverity,
) -> bool:
    """Check if severity meets or exceeds a threshold.

    Args:
        severity: The severity to check.
        threshold: The minimum severity level.

    Returns:
        True if severity >= threshold.
    """
    return SEVERITY_ORDER[severity] >= SEVERITY_ORDER[threshold]


def classify_layer_failure(
    layer_name: str,
    error: Exception | None = None,
    has_fallback_data: bool = False,
) -> FailureSeverity:
    """Classify the severity of a layer failure.

    Args:
        layer_name: Name of the failed layer.
        error: The exception that caused the failure (if any).
        has_fallback_data: Whether the layer produced fallback data.

    Returns:
        Appropriate FailureSeverity for the failure.
    """
    # Critical layers — failure is always CRITICAL
    critical_layers = frozenset({
        "severity", "governance", "invariants",
    })

    if layer_name in critical_layers:
        return FailureSeverity.CRITICAL

    if error is not None and not has_fallback_data:
        return FailureSeverity.ERROR

    if error is not None and has_fallback_data:
        return FailureSeverity.WARNING

    return FailureSeverity.INFO


def severity_to_dict(severity: FailureSeverity) -> dict[str, Any]:
    """Serialize severity for export."""
    return {
        "level": severity.value,
        "ordinal": SEVERITY_ORDER[severity],
        "is_consequential": severity in CONSEQUENTIAL_SEVERITIES,
        "blocks_export": severity in EXPORT_BLOCKING_SEVERITIES,
    }
