"""
backend.epistemic_fault_isolation — Epistemic Fault Isolation Engine

TRUE FINAL PASS v3, SECTION 1: Fault Isolation Core.

Problem addressed:
    The system is globally conservative instead of locally conservative.
    A single axis failure, authority conflict, or runtime degradation
    causes ALL outputs to degrade — even outputs with no dependency
    on the failed component.

Solution:
    The fault isolation engine computes the MINIMAL SCOPE of each
    failure, using the explicit dependency graph. Failures are
    contained to their affected outputs. Valid signals survive
    unrelated failures.

Design contract:
    - Every fault has an explicit scope (axes, countries, outputs).
    - Scope is always MINIMAL — never broader than justified.
    - Escalation to GLOBAL requires explicit proof of overlap.
    - The arbiter uses fault scope to make scoped decisions.
    - All scoping decisions are serialized and auditable.

Rules implemented:
    FI-001  Minimal Scope Principle
    FI-002  Axis Independence
    FI-003  Output-Specific Degradation
    FI-004  Weighted Composite Containment
    FI-005  Authority Locality
    FI-006  Invariant Containment
    FI-007  Runtime Containment
    FI-008  Containment Escalation Rule

Honesty note:
    "A system that suppresses valid outputs because of unrelated
    failures is not conservative — it is wasteful. True conservatism
    means being maximally strict WHERE needed and maximally informative
    WHERE safe."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.epistemic_dependencies import (
    OutputType,
    VALID_OUTPUT_TYPES,
    compute_affected_outputs,
    is_output_affected,
    should_suppress_composite,
)


# ═══════════════════════════════════════════════════════════════════════════
# CONTAINMENT LEVELS
# ═══════════════════════════════════════════════════════════════════════════

class ContainmentLevel:
    """How broadly a fault must be contained."""
    LOCAL = "LOCAL"         # Single axis or output
    REGIONAL = "REGIONAL"   # Multiple axes but not system-wide
    GLOBAL = "GLOBAL"       # System-wide impact


VALID_CONTAINMENT_LEVELS = frozenset({
    ContainmentLevel.LOCAL,
    ContainmentLevel.REGIONAL,
    ContainmentLevel.GLOBAL,
})

# Containment ordering — higher = broader
_CONTAINMENT_ORDER: dict[str, int] = {
    ContainmentLevel.LOCAL: 0,
    ContainmentLevel.REGIONAL: 1,
    ContainmentLevel.GLOBAL: 2,
}


def _broader_containment(a: str, b: str) -> str:
    """Return the broader of two containment levels."""
    if _CONTAINMENT_ORDER.get(a, 0) >= _CONTAINMENT_ORDER.get(b, 0):
        return a
    return b


# ═══════════════════════════════════════════════════════════════════════════
# FAULT SCOPE — the core isolation dataclass
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EpistemicFaultScope:
    """Describes the exact scope of a fault or set of faults.

    This is the output of the fault isolation engine. The arbiter
    uses it to make scoped decisions instead of global ones.
    """
    affected_axes: frozenset[int]
    affected_countries: frozenset[str]
    affected_outputs: frozenset[str]
    unaffected_outputs: frozenset[str]
    containment_level: str
    propagation_allowed: bool
    composite_action: str  # "VALID", "DEGRADE", "SUPPRESS"
    reasoning: tuple[str, ...]


def fault_scope_to_dict(scope: EpistemicFaultScope) -> dict[str, Any]:
    """Serialize an EpistemicFaultScope to a dictionary."""
    return {
        "affected_axes": sorted(scope.affected_axes),
        "affected_countries": sorted(scope.affected_countries),
        "affected_outputs": sorted(scope.affected_outputs),
        "unaffected_outputs": sorted(scope.unaffected_outputs),
        "containment_level": scope.containment_level,
        "propagation_allowed": scope.propagation_allowed,
        "composite_action": scope.composite_action,
        "reasoning": list(scope.reasoning),
    }


# ═══════════════════════════════════════════════════════════════════════════
# FAULT ISOLATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def compute_fault_isolation(
    *,
    country: str = "",
    invariant_violations: list[dict[str, Any]] | None = None,
    authority_conflicts: dict[str, Any] | None = None,
    runtime_failures: dict[str, Any] | None = None,
    epistemic_bounds: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    axis_failures: set[int] | None = None,
    axis_weights: dict[int, float] | None = None,
) -> EpistemicFaultScope:
    """Compute the minimal fault scope from all failure inputs.

    This is the core function of the fault isolation engine.
    It determines EXACTLY which outputs are affected by the
    current set of failures, and which outputs survive.

    Args:
        country: ISO-2 country code.
        invariant_violations: List of invariant violation records.
        authority_conflicts: Authority conflict detection result.
        runtime_failures: Runtime failure/degradation info.
        epistemic_bounds: Current epistemic bounds dict.
        governance: Governance assessment result.
        axis_failures: Explicitly failed axes (direct input).
        axis_weights: Optional per-axis weights for composite threshold.

    Returns:
        EpistemicFaultScope describing the minimal containment.
    """
    failed_axes: set[int] = set(axis_failures or set())
    affected_outputs: set[str] = set()
    containment = ContainmentLevel.LOCAL
    reasons: list[str] = []
    propagation_allowed = False

    # ── FI-006: Invariant Containment ──
    if invariant_violations:
        inv_axes, inv_outputs, inv_global = _isolate_invariant_faults(
            invariant_violations,
        )
        failed_axes |= inv_axes
        affected_outputs |= inv_outputs
        if inv_global:
            containment = _broader_containment(containment, ContainmentLevel.GLOBAL)
            propagation_allowed = True
            reasons.append(
                f"System-wide invariant violated — global containment required."
            )
        elif inv_axes:
            containment = _broader_containment(
                containment,
                ContainmentLevel.REGIONAL if len(inv_axes) > 1 else ContainmentLevel.LOCAL,
            )
            reasons.append(
                f"Invariant violations scoped to axes {sorted(inv_axes)}."
            )

    # ── FI-005: Authority Locality ──
    if authority_conflicts is not None:
        auth_axes = _isolate_authority_faults(authority_conflicts)
        if auth_axes:
            failed_axes |= auth_axes
            containment = _broader_containment(
                containment,
                ContainmentLevel.REGIONAL if len(auth_axes) > 1 else ContainmentLevel.LOCAL,
            )
            reasons.append(
                f"Authority conflicts scoped to axes {sorted(auth_axes)}."
            )

    # ── FI-007: Runtime Containment ──
    if runtime_failures is not None:
        rt_axes, rt_global = _isolate_runtime_faults(runtime_failures)
        if rt_global:
            failed_axes |= rt_axes
            containment = _broader_containment(containment, ContainmentLevel.GLOBAL)
            propagation_allowed = True
            reasons.append(
                "Runtime failure affects entire pipeline — global containment."
            )
        elif rt_axes:
            failed_axes |= rt_axes
            containment = _broader_containment(
                containment,
                ContainmentLevel.REGIONAL if len(rt_axes) > 1 else ContainmentLevel.LOCAL,
            )
            reasons.append(
                f"Runtime failures scoped to axes {sorted(rt_axes)}."
            )

    # ── FI-002: Axis Independence — governance failures ──
    if governance is not None:
        gov_tier = governance.get("governance_tier", "FULLY_COMPARABLE")
        if gov_tier == "NON_COMPARABLE":
            # Governance failure affects ranking/comparison/ordering globally
            containment = _broader_containment(containment, ContainmentLevel.GLOBAL)
            propagation_allowed = True
            affected_outputs |= {
                OutputType.RANKING,
                OutputType.COMPARISON,
                OutputType.COUNTRY_ORDERING,
            }
            reasons.append(
                "NON_COMPARABLE governance — ranking/comparison/ordering suppressed globally."
            )

    # ── FI-003: Output-Specific Degradation ──
    # Use dependency graph to determine which outputs are actually affected
    dep_result = compute_affected_outputs(failed_axes)
    graph_affected = set(dep_result["affected_outputs"])
    affected_outputs |= graph_affected

    # Unaffected outputs are those NOT in the affected set
    all_output_types = set(VALID_OUTPUT_TYPES)
    # Add per-axis types
    for ax in range(1, 7):
        all_output_types.add(f"axis_insight_{ax}")
        all_output_types.add(f"axis_score_{ax}")
    unaffected_outputs = all_output_types - affected_outputs

    # ── FI-004: Weighted Composite Containment ──
    composite_decision = should_suppress_composite(
        failed_axes, axis_weights=axis_weights,
    )
    composite_action = composite_decision["action"]

    if composite_action == "DEGRADE":
        # Composite survives but with caveats — do NOT add to affected_outputs
        # unless it was already affected by other means
        if OutputType.COMPOSITE not in affected_outputs:
            # Composite degraded but not suppressed — it's still partially valid
            pass
        reasons.append(
            f"Composite DEGRADED (not suppressed): failed weight "
            f"{composite_decision['failed_weight']:.2%} < "
            f"{composite_decision['threshold']:.0%} threshold."
        )
    elif composite_action == "SUPPRESS":
        affected_outputs.add(OutputType.COMPOSITE)
        reasons.append(
            f"Composite SUPPRESSED: failed weight "
            f"{composite_decision['failed_weight']:.2%} > "
            f"{composite_decision['threshold']:.0%} threshold."
        )

    # ── FI-008: Containment Escalation Rule ──
    if not propagation_allowed and len(failed_axes) >= 4:
        # Multiple independent scopes overlap → global
        containment = ContainmentLevel.GLOBAL
        propagation_allowed = True
        reasons.append(
            f"Escalation: {len(failed_axes)} failed axes → GLOBAL containment."
        )

    # Handle no-failure case
    if not failed_axes and not affected_outputs and containment == ContainmentLevel.LOCAL:
        composite_action = "VALID"
        reasons.append("No faults detected — all outputs valid.")

    return EpistemicFaultScope(
        affected_axes=frozenset(failed_axes),
        affected_countries=frozenset({country} if country else set()),
        affected_outputs=frozenset(affected_outputs),
        unaffected_outputs=frozenset(unaffected_outputs),
        containment_level=containment,
        propagation_allowed=propagation_allowed,
        composite_action=composite_action,
        reasoning=tuple(reasons),
    )


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL FAULT ISOLATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _isolate_invariant_faults(
    violations: list[dict[str, Any]],
) -> tuple[set[int], set[str], bool]:
    """Extract fault scope from invariant violations.

    FI-006: All invariant violations must specify scope and affected outputs.
    No blanket invalidation.

    Returns:
        (affected_axes, affected_outputs, is_global)
    """
    axes: set[int] = set()
    outputs: set[str] = set()
    is_global = False

    for v in violations:
        # Check for axis scope
        v_axes = v.get("affected_axes", [])
        if isinstance(v_axes, (list, set, frozenset)):
            axes.update(v_axes)

        # Check for output scope
        v_outputs = v.get("affected_outputs", [])
        if isinstance(v_outputs, (list, set, frozenset)):
            outputs.update(v_outputs)

        # System-wide invariants escalate to GLOBAL
        inv_type = v.get("invariant_type", "")
        severity = v.get("severity", "WARNING")
        if inv_type in ("PIPELINE_INTEGRITY", "RUNTIME") and severity == "CRITICAL":
            is_global = True

    return axes, outputs, is_global


def _isolate_authority_faults(
    authority_conflicts: dict[str, Any],
) -> set[int]:
    """Extract affected axes from authority conflicts.

    FI-005: Authority conflicts apply only within domain.
    No global escalation without proof.

    Returns:
        Set of affected axis IDs.
    """
    affected_axes: set[int] = set()

    conflicts = authority_conflicts.get("conflicts", [])
    for conflict in conflicts:
        axis = conflict.get("axis_id")
        if isinstance(axis, int) and 1 <= axis <= 6:
            affected_axes.add(axis)

        # Also check relevant_axes from authority metadata
        axes = conflict.get("relevant_axes", [])
        if isinstance(axes, (list, set)):
            for a in axes:
                if isinstance(a, int) and 1 <= a <= 6:
                    affected_axes.add(a)

    return affected_axes


def _isolate_runtime_faults(
    runtime_failures: dict[str, Any],
) -> tuple[set[int], bool]:
    """Extract fault scope from runtime failures.

    FI-007: Runtime degradation affects only dependent outputs.
    Full pipeline failure → GLOBAL.

    Returns:
        (affected_axes, is_global)
    """
    pipeline_status = runtime_failures.get("pipeline_status", "HEALTHY")

    if pipeline_status == "FAILED":
        return set(range(1, 7)), True

    affected_axes: set[int] = set()
    failed_layers = runtime_failures.get("failed_layers", [])
    degraded_layers = runtime_failures.get("degraded_layers", [])

    for layer in failed_layers + degraded_layers:
        if isinstance(layer, dict):
            layer_axes = layer.get("affected_axes", [])
            if isinstance(layer_axes, (list, set)):
                for a in layer_axes:
                    if isinstance(a, int) and 1 <= a <= 6:
                        affected_axes.add(a)
        elif isinstance(layer, str):
            # Layer name — can't determine axes, conservative
            pass

    return affected_axes, False


# ═══════════════════════════════════════════════════════════════════════════
# SCOPED PUBLISHABILITY
# ═══════════════════════════════════════════════════════════════════════════

def compute_scoped_publishability(
    fault_scope: EpistemicFaultScope,
    base_publishability: str = "PUBLISHABLE",
) -> dict[str, Any]:
    """Compute per-output publishability respecting fault scope.

    Instead of a single global publishability, this produces
    independent publishability for each output type.

    Args:
        fault_scope: The computed fault scope.
        base_publishability: The baseline publishability status.

    Returns:
        Per-output publishability assessments.
    """
    result: dict[str, Any] = {}

    # Global outputs
    for otype in sorted(VALID_OUTPUT_TYPES):
        if otype in (OutputType.AXIS_INSIGHT, OutputType.AXIS_SCORE):
            continue

        if otype in fault_scope.affected_outputs:
            if fault_scope.containment_level == ContainmentLevel.GLOBAL:
                result[f"publishability_{otype}"] = "NOT_PUBLISHABLE"
            else:
                result[f"publishability_{otype}"] = "PUBLISHABLE_WITH_CAVEATS"
        else:
            result[f"publishability_{otype}"] = base_publishability

    # Per-axis publishability
    for ax in range(1, 7):
        insight_key = f"axis_insight_{ax}"
        score_key = f"axis_score_{ax}"

        if insight_key in fault_scope.affected_outputs or ax in fault_scope.affected_axes:
            result[f"publishability_axis_{ax}"] = "PUBLISHABLE_WITH_CAVEATS"
        else:
            result[f"publishability_axis_{ax}"] = base_publishability

    # Composite special handling
    if fault_scope.composite_action == "SUPPRESS":
        result[f"publishability_{OutputType.COMPOSITE}"] = "NOT_PUBLISHABLE"
    elif fault_scope.composite_action == "DEGRADE":
        result[f"publishability_{OutputType.COMPOSITE}"] = "PUBLISHABLE_WITH_CAVEATS"

    result["fault_scope_level"] = fault_scope.containment_level
    result["n_affected_outputs"] = len(fault_scope.affected_outputs)
    result["n_unaffected_outputs"] = len(fault_scope.unaffected_outputs)

    result["honesty_note"] = (
        f"Scoped publishability: {len(fault_scope.affected_outputs)} output(s) "
        f"affected, {len(fault_scope.unaffected_outputs)} output(s) unaffected. "
        f"Containment level: {fault_scope.containment_level}. "
        f"Composite: {fault_scope.composite_action}. "
        f"Unaffected outputs retain their baseline publishability."
    )

    return result
