"""
backend.epistemic_dependencies — Output Dependency Graph

TRUE FINAL PASS v3, SECTION 7: Explicit Dependency Graph.

Problem addressed:
    When a failure occurs in one axis, the system must know WHICH
    outputs actually depend on that axis. Without an explicit
    dependency graph, the system either:
    (a) conservatively kills all outputs (overcollapse), or
    (b) lets invalid outputs through (undercollapse).

Solution:
    An explicit, auditable mapping from each output type to the
    axes it requires. All propagation decisions must consult this
    graph. No propagation is allowed without explicit dependency.

Design contract:
    - Every output type has a declared dependency set.
    - No axis failure propagates unless a dependency chain exists.
    - Composite depends on ALL axes by default.
    - Ranking depends on composite.
    - Per-axis insights depend only on their own axis.
    - The dependency graph is static and deterministic.

Honesty note:
    "If we suppress an output because Axis 3 failed but the output
    has no dependency on Axis 3, we have committed an epistemic
    error — we punished a valid signal for an unrelated failure."
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# OUTPUT TYPES
# ═══════════════════════════════════════════════════════════════════════════

class OutputType:
    """Types of outward-facing outputs the system can produce."""
    RANKING = "ranking"
    COMPOSITE = "composite"
    AXIS_INSIGHT = "axis_insight"
    POLICY_CLAIM = "policy_claim"
    COMPARISON = "comparison"
    COUNTRY_ORDERING = "country_ordering"
    AXIS_SCORE = "axis_score"


VALID_OUTPUT_TYPES = frozenset({
    OutputType.RANKING,
    OutputType.COMPOSITE,
    OutputType.AXIS_INSIGHT,
    OutputType.POLICY_CLAIM,
    OutputType.COMPARISON,
    OutputType.COUNTRY_ORDERING,
    OutputType.AXIS_SCORE,
})


# ═══════════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH — output → required axes
# ═══════════════════════════════════════════════════════════════════════════

# Which axes each output type depends on.
# An output is ONLY affected by failures in its declared dependencies.
OUTPUT_DEPENDENCIES: dict[str, frozenset[int]] = {
    # Ranking requires the composite, which requires all axes
    OutputType.RANKING: frozenset({1, 2, 3, 4, 5, 6}),

    # Composite score requires all 6 axes
    OutputType.COMPOSITE: frozenset({1, 2, 3, 4, 5, 6}),

    # Per-axis insight depends ONLY on its own axis
    OutputType.AXIS_INSIGHT: frozenset(),  # resolved per-axis at query time

    # Policy claims require composite + governance (all axes)
    OutputType.POLICY_CLAIM: frozenset({1, 2, 3, 4, 5, 6}),

    # Comparison requires composite (all axes)
    OutputType.COMPARISON: frozenset({1, 2, 3, 4, 5, 6}),

    # Country ordering requires ranking (all axes)
    OutputType.COUNTRY_ORDERING: frozenset({1, 2, 3, 4, 5, 6}),

    # Individual axis score — depends only on that axis
    OutputType.AXIS_SCORE: frozenset(),  # resolved per-axis at query time
}


def get_axis_insight_dependencies(axis_id: int) -> frozenset[int]:
    """Get dependencies for a specific axis insight.

    Axis insights depend ONLY on their own axis.
    This is the core of fault isolation: axis 3 failing
    cannot affect axis 1 insight.

    Args:
        axis_id: The axis (1–6).

    Returns:
        Frozenset containing only the specified axis.
    """
    if not 1 <= axis_id <= 6:
        raise ValueError(f"Invalid axis_id: {axis_id}. Must be 1–6.")
    return frozenset({axis_id})


def get_output_dependencies(
    output_type: str,
    axis_id: int | None = None,
) -> frozenset[int]:
    """Get the axis dependencies for a given output type.

    Args:
        output_type: One of VALID_OUTPUT_TYPES.
        axis_id: Required for AXIS_INSIGHT and AXIS_SCORE (specifies which axis).

    Returns:
        Set of axis IDs (1–6) that this output depends on.

    Raises:
        ValueError: If output_type is invalid or axis_id missing when required.
    """
    if output_type not in VALID_OUTPUT_TYPES:
        raise ValueError(f"Unknown output type: {output_type}")

    if output_type in (OutputType.AXIS_INSIGHT, OutputType.AXIS_SCORE):
        if axis_id is None:
            raise ValueError(
                f"{output_type} requires axis_id to determine dependencies."
            )
        return get_axis_insight_dependencies(axis_id)

    return OUTPUT_DEPENDENCIES[output_type]


def is_output_affected(
    output_type: str,
    failed_axes: set[int],
    axis_id: int | None = None,
) -> bool:
    """Check whether a specific output is affected by axis failures.

    This is the fundamental isolation check. An output is affected
    ONLY IF at least one of its dependencies has failed.

    Args:
        output_type: The output type to check.
        failed_axes: Set of axis IDs that have failed.
        axis_id: Required for per-axis outputs.

    Returns:
        True if the output is affected by the failures.
    """
    deps = get_output_dependencies(output_type, axis_id=axis_id)
    return bool(deps & failed_axes)


def compute_affected_outputs(
    failed_axes: set[int],
) -> dict[str, Any]:
    """Compute which outputs are affected by a set of axis failures.

    Uses the explicit dependency graph to determine exactly which
    outputs must be degraded and which survive.

    Args:
        failed_axes: Set of axis IDs that have failed.

    Returns:
        Mapping of each output type to its affected status.
    """
    if not failed_axes:
        return {
            "affected_outputs": [],
            "unaffected_outputs": sorted(VALID_OUTPUT_TYPES),
            "n_affected": 0,
            "n_unaffected": len(VALID_OUTPUT_TYPES),
            "failed_axes": sorted(failed_axes),
            "per_axis_insights": {
                ax: {"affected": False} for ax in range(1, 7)
            },
            "honesty_note": "No axis failures — all outputs valid.",
        }

    affected: list[str] = []
    unaffected: list[str] = []

    # Check global outputs (non-per-axis)
    for otype in sorted(VALID_OUTPUT_TYPES):
        if otype in (OutputType.AXIS_INSIGHT, OutputType.AXIS_SCORE):
            continue  # handled per-axis below
        if is_output_affected(otype, failed_axes):
            affected.append(otype)
        else:
            unaffected.append(otype)

    # Check per-axis outputs
    per_axis: dict[int, dict[str, Any]] = {}
    for ax in range(1, 7):
        ax_affected = ax in failed_axes
        per_axis[ax] = {
            "affected": ax_affected,
            "insight_valid": not ax_affected,
            "score_valid": not ax_affected,
        }
        if ax_affected:
            affected.append(f"axis_insight_{ax}")
            affected.append(f"axis_score_{ax}")
        else:
            unaffected.append(f"axis_insight_{ax}")
            unaffected.append(f"axis_score_{ax}")

    return {
        "affected_outputs": sorted(set(affected)),
        "unaffected_outputs": sorted(set(unaffected)),
        "n_affected": len(affected),
        "n_unaffected": len(unaffected),
        "failed_axes": sorted(failed_axes),
        "per_axis_insights": per_axis,
        "honesty_note": (
            f"Fault isolation: {len(failed_axes)} axis failure(s) "
            f"(axes {sorted(failed_axes)}). "
            f"{len(affected)} output(s) affected, "
            f"{len(unaffected)} output(s) survive. "
            f"Unaffected outputs remain valid and publishable."
        ),
    }


def get_composite_weight_threshold() -> float:
    """Return the weight threshold for composite suppression.

    If the combined weight of failed axes exceeds this threshold,
    the composite should be SUPPRESSED (not just degraded).
    Below this threshold, the composite should be DEGRADED with
    caveats noting which axes are missing.

    Returns:
        Weight threshold (fraction of total weight).
    """
    return 0.50  # Suppress composite if >50% of weight is invalid


def should_suppress_composite(
    failed_axes: set[int],
    axis_weights: dict[int, float] | None = None,
) -> dict[str, Any]:
    """Determine whether composite should be suppressed or degraded.

    FI-004: Suppress composite only if weight threshold exceeded
    or critical axis invalid. Otherwise degrade, do not remove.

    Args:
        failed_axes: Set of failed axis IDs.
        axis_weights: Optional weight per axis (default: equal weights).

    Returns:
        Decision with suppress/degrade and reasoning.
    """
    if not failed_axes:
        return {
            "action": "VALID",
            "suppress": False,
            "degrade": False,
            "failed_weight": 0.0,
            "threshold": get_composite_weight_threshold(),
            "reasoning": "No axis failures — composite valid.",
        }

    if axis_weights is None:
        # Default equal weights
        axis_weights = {ax: 1.0 / 6 for ax in range(1, 7)}

    total_weight = sum(axis_weights.values())
    failed_weight = sum(
        axis_weights.get(ax, 0.0) for ax in failed_axes
    )

    if total_weight == 0:
        frac = 1.0
    else:
        frac = failed_weight / total_weight

    threshold = get_composite_weight_threshold()

    if frac > threshold:
        return {
            "action": "SUPPRESS",
            "suppress": True,
            "degrade": False,
            "failed_weight": round(frac, 4),
            "threshold": threshold,
            "failed_axes": sorted(failed_axes),
            "reasoning": (
                f"Failed axis weight {frac:.2%} exceeds threshold "
                f"{threshold:.0%}. Composite suppressed."
            ),
        }
    else:
        return {
            "action": "DEGRADE",
            "suppress": False,
            "degrade": True,
            "failed_weight": round(frac, 4),
            "threshold": threshold,
            "failed_axes": sorted(failed_axes),
            "reasoning": (
                f"Failed axis weight {frac:.2%} below threshold "
                f"{threshold:.0%}. Composite degraded with caveats, "
                f"not suppressed. Axes {sorted(failed_axes)} excluded."
            ),
        }
