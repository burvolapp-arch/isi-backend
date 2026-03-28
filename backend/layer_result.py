"""
backend.layer_result — Layer Execution Result Model

Defines the explicit, frozen result type for every layer execution
in the ISI pipeline. Every layer MUST return a LayerResult — no raw
dicts, no silent None returns, no swallowed exceptions.

Design contract:
    - LayerExecutionStatus is exhaustive — SUCCESS/DEGRADED/FAILED/SKIPPED.
    - LayerResult is frozen — once created, immutable.
    - Every result carries timing, warnings, errors.
    - DEGRADED means partial data produced (layer caught its own error).
    - FAILED means no usable data — pipeline must track this.
    - SKIPPED means the layer was short-circuited due to upstream critical failure.

Honesty note:
    This model forces every layer to declare its own health.
    A layer that returns SUCCESS with empty data is a lie detector target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# EXECUTION STATUS
# ═══════════════════════════════════════════════════════════════════════════

class LayerExecutionStatus(Enum):
    """Exhaustive execution status for a pipeline layer.

    SUCCESS  — Layer ran to completion, produced all declared outputs.
    DEGRADED — Layer ran but produced partial/fallback data.
    FAILED   — Layer threw or produced no usable data.
    SKIPPED  — Layer was not executed (upstream critical failure).
    """
    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


VALID_EXECUTION_STATUSES = frozenset({
    LayerExecutionStatus.SUCCESS,
    LayerExecutionStatus.DEGRADED,
    LayerExecutionStatus.FAILED,
    LayerExecutionStatus.SKIPPED,
})


# ═══════════════════════════════════════════════════════════════════════════
# LAYER RESULT — frozen, immutable
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LayerResult:
    """Frozen result of a single pipeline layer execution.

    Attributes:
        layer_name: Name of the layer that produced this result.
        status: Execution status (SUCCESS/DEGRADED/FAILED/SKIPPED).
        data: Dict of produced key→value pairs (empty on FAILED/SKIPPED).
        warnings: List of warning messages from execution.
        errors: List of error messages from execution.
        timing_ms: Wall-clock execution time in milliseconds.
        version: Version tag for the layer's logic (for reproducibility).
    """
    layer_name: str
    status: LayerExecutionStatus
    data: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    timing_ms: float = 0.0
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        """Validate invariants on construction."""
        if not isinstance(self.status, LayerExecutionStatus):
            raise TypeError(
                f"LayerResult.status must be LayerExecutionStatus, "
                f"got {type(self.status).__name__}"
            )
        if not isinstance(self.layer_name, str) or not self.layer_name:
            raise ValueError("LayerResult.layer_name must be a non-empty string")
        if not isinstance(self.data, dict):
            raise TypeError(
                f"LayerResult.data must be a dict, got {type(self.data).__name__}"
            )
        if not isinstance(self.warnings, tuple):
            raise TypeError(
                f"LayerResult.warnings must be a tuple, "
                f"got {type(self.warnings).__name__}"
            )
        if not isinstance(self.errors, tuple):
            raise TypeError(
                f"LayerResult.errors must be a tuple, "
                f"got {type(self.errors).__name__}"
            )
        if self.timing_ms < 0:
            raise ValueError(
                f"LayerResult.timing_ms must be >= 0, got {self.timing_ms}"
            )
        # Structural integrity: FAILED/SKIPPED should have empty data
        if self.status in (LayerExecutionStatus.FAILED, LayerExecutionStatus.SKIPPED):
            if self.data:
                raise ValueError(
                    f"LayerResult with status {self.status.value} must have "
                    f"empty data, but got keys: {sorted(self.data.keys())}"
                )
        # SUCCESS must have no errors
        if self.status == LayerExecutionStatus.SUCCESS and self.errors:
            raise ValueError(
                "LayerResult with status SUCCESS must have no errors"
            )

    @property
    def is_usable(self) -> bool:
        """Whether this result produced usable data."""
        return self.status in (
            LayerExecutionStatus.SUCCESS,
            LayerExecutionStatus.DEGRADED,
        )

    @property
    def is_healthy(self) -> bool:
        """Whether this result is fully healthy (no warnings or errors)."""
        return (
            self.status == LayerExecutionStatus.SUCCESS
            and not self.warnings
            and not self.errors
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for export/logging."""
        return {
            "layer_name": self.layer_name,
            "status": self.status.value,
            "data_keys": sorted(self.data.keys()),
            "n_warnings": len(self.warnings),
            "n_errors": len(self.errors),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "timing_ms": self.timing_ms,
            "version": self.version,
            "is_usable": self.is_usable,
            "is_healthy": self.is_healthy,
        }
