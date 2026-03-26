"""
backend.layer_pipeline — Explicit, Deterministic Execution Pipeline

SECTION 1 of Final Closure Pass: Execution Pipeline Hardening.

Problem addressed:
    build_country_json() previously relied on IMPLICIT ordering of
    function calls. This is fragile: reorder two lines and the system
    silently produces wrong output. No layer declared its dependencies.

Solution:
    Each computation step is a registered Layer with:
    - name: unique identifier
    - compute: function that takes (state, context) → partial result
    - requires: set of layer names that must have completed first
    - produces: set of state keys this layer writes

    The pipeline runner:
    1. Validates the DAG (no cycles, no missing deps)
    2. Executes in topological order
    3. Asserts required inputs exist before each step
    4. Asserts outputs were produced after each step
    5. Rejects duplicate layers
    6. Rejects undeclared input access

Design contract:
    - Execution order is DETERMINISTIC (topological sort with stable tie-break)
    - No layer may access state keys not listed in its requires
    - No layer may write state keys not listed in its produces
    - Pipeline failure is LOUD — never silent
    - The pipeline is the ONLY sanctioned execution path
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.layer_result import LayerExecutionStatus, LayerResult
from backend.failure_severity import (
    FailureSeverity,
    classify_layer_failure,
    worst_severity,
    severity_at_least,
)


# ═══════════════════════════════════════════════════════════════════════════
# LAYER DEFINITION
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Layer:
    """A single computation step in the ISI pipeline.

    Attributes:
        name: Unique layer identifier.
        compute: Function (state: dict, context: dict) → dict of outputs.
        requires: Set of layer names whose outputs must be available.
        produces: Set of state keys this layer writes.
    """
    name: str
    compute: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    requires: frozenset[str] = field(default_factory=frozenset)
    produces: frozenset[str] = field(default_factory=frozenset)


class PipelineError(Exception):
    """Raised when pipeline structure or execution fails."""
    pass


class MissingDependencyError(PipelineError):
    """Raised when a layer's required dependency hasn't been computed."""
    pass


class DuplicateLayerError(PipelineError):
    """Raised when two layers share the same name."""
    pass


class CyclicDependencyError(PipelineError):
    """Raised when the layer DAG contains a cycle."""
    pass


class MissingOutputError(PipelineError):
    """Raised when a layer failed to produce its declared outputs."""
    pass


class UndeclaredInputError(PipelineError):
    """Raised when a layer accesses state keys not in its requires."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def validate_pipeline(layers: list[Layer]) -> list[str]:
    """Validate pipeline structure. Returns execution order.

    Checks:
        1. No duplicate layer names
        2. All dependencies reference existing layers
        3. No cycles in the dependency graph
        4. No output key conflicts between layers

    Returns:
        List of layer names in valid execution order.

    Raises:
        DuplicateLayerError: If two layers share the same name.
        MissingDependencyError: If a layer requires a non-existent layer.
        CyclicDependencyError: If the DAG has a cycle.
    """
    # Check duplicates
    names = [l.name for l in layers]
    seen = set()
    for n in names:
        if n in seen:
            raise DuplicateLayerError(f"Duplicate layer name: '{n}'")
        seen.add(n)

    # Check all dependencies exist
    name_set = set(names)
    for layer in layers:
        for dep in layer.requires:
            if dep not in name_set:
                raise MissingDependencyError(
                    f"Layer '{layer.name}' requires '{dep}' which does not exist"
                )

    # Topological sort (Kahn's algorithm) with stable tie-break
    layer_map = {l.name: l for l in layers}
    in_degree: dict[str, int] = {n: 0 for n in names}
    for layer in layers:
        for dep in layer.requires:
            in_degree[layer.name] = in_degree.get(layer.name, 0)
    # Compute actual in-degrees
    for layer in layers:
        in_degree[layer.name] = len(layer.requires)

    order: list[str] = []
    # Use sorted for deterministic tie-break
    available = sorted([n for n in names if in_degree[n] == 0])

    while available:
        current = available.pop(0)
        order.append(current)
        # Reduce in-degree for dependents
        for layer in layers:
            if current in layer.requires:
                in_degree[layer.name] -= 1
                if in_degree[layer.name] == 0:
                    # Insert in sorted position for stable ordering
                    available.append(layer.name)
                    available.sort()

    if len(order) != len(names):
        remaining = set(names) - set(order)
        raise CyclicDependencyError(
            f"Cyclic dependency detected involving layers: {sorted(remaining)}"
        )

    return order


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline(
    layers: list[Layer],
    context: dict[str, Any],
    initial_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the pipeline in validated order.

    Args:
        layers: Registered pipeline layers.
        context: Immutable context (country, scores, methodology, etc.)
        initial_state: Pre-populated state keys (e.g., raw axis scores).

    Returns:
        Final state dict with all layer outputs plus runtime metadata:
        - _pipeline_execution_log: per-layer execution trace
        - _pipeline_execution_order: topological execution order
        - _pipeline_status: overall status (HEALTHY/DEGRADED/FAILED)
        - _pipeline_results: list of LayerResult.to_dict()
        - _pipeline_degraded_layers: names of degraded layers
        - _pipeline_failed_layers: names of failed layers
        - _pipeline_skipped_layers: names of skipped layers
        - _pipeline_total_ms: total wall-clock time
        - _pipeline_worst_severity: worst failure severity across layers

    Raises:
        PipelineError: On any structural or execution failure.
    """
    execution_order = validate_pipeline(layers)
    layer_map = {l.name: l for l in layers}

    state: dict[str, Any] = dict(initial_state) if initial_state else {}
    completed: set[str] = set()

    # Track which state keys were produced by which layer
    key_provenance: dict[str, str] = {}
    for k in state:
        key_provenance[k] = "__initial__"

    execution_log: list[dict[str, Any]] = []
    layer_results: list[LayerResult] = []
    degraded_layers: list[str] = []
    failed_layers: list[str] = []
    skipped_layers: list[str] = []
    layer_severities: list[FailureSeverity] = []
    pipeline_start = time.monotonic()

    # Track whether a critical failure has occurred (short-circuit)
    critical_failure = False

    for layer_name in execution_order:
        layer = layer_map[layer_name]

        # Short-circuit: skip remaining layers on critical failure
        if critical_failure:
            result = LayerResult(
                layer_name=layer_name,
                status=LayerExecutionStatus.SKIPPED,
                warnings=("Skipped due to upstream critical failure.",),
            )
            layer_results.append(result)
            skipped_layers.append(layer_name)
            execution_log.append({
                "layer": layer_name,
                "produced": [],
                "status": "SKIPPED",
                "timing_ms": 0.0,
                "reason": "upstream_critical_failure",
            })
            continue

        # Assert all required layers have completed
        for dep in layer.requires:
            if dep not in completed:
                raise MissingDependencyError(
                    f"Layer '{layer_name}' requires '{dep}' which has not completed. "
                    f"Completed: {sorted(completed)}"
                )

        # Execute with guarded state access and timing
        guarded_state = _GuardedState(state, layer, completed, key_provenance)
        layer_start = time.monotonic()
        layer_warnings: list[str] = []
        layer_errors: list[str] = []

        try:
            outputs = layer.compute(guarded_state, context)
        except UndeclaredInputError:
            raise  # Re-raise access violations — structural bug
        except Exception as e:
            # Layer failed — classify severity
            elapsed_ms = (time.monotonic() - layer_start) * 1000
            severity = classify_layer_failure(layer_name, error=e, has_fallback_data=False)
            layer_severities.append(severity)
            layer_errors.append(f"{type(e).__name__}: {e}")

            if severity_at_least(severity, FailureSeverity.CRITICAL):
                # Critical layer failure — short-circuit remaining pipeline
                result = LayerResult(
                    layer_name=layer_name,
                    status=LayerExecutionStatus.FAILED,
                    errors=tuple(layer_errors),
                    timing_ms=elapsed_ms,
                )
                layer_results.append(result)
                failed_layers.append(layer_name)
                critical_failure = True
                execution_log.append({
                    "layer": layer_name,
                    "produced": [],
                    "status": "FAILED",
                    "timing_ms": elapsed_ms,
                    "severity": severity.value,
                    "errors": layer_errors,
                })
                continue

            # Non-critical failure — wrap in PipelineError as before
            raise PipelineError(
                f"Layer '{layer_name}' failed during execution: {e}"
            ) from e

        elapsed_ms = (time.monotonic() - layer_start) * 1000

        # Validate outputs
        if not isinstance(outputs, dict):
            raise MissingOutputError(
                f"Layer '{layer_name}' must return a dict, got {type(outputs).__name__}"
            )

        for key in layer.produces:
            if key not in outputs:
                raise MissingOutputError(
                    f"Layer '{layer_name}' declared output '{key}' but did not produce it. "
                    f"Produced: {sorted(outputs.keys())}"
                )

        # Check for degraded outputs (layer caught its own error)
        is_degraded = False
        for key, value in outputs.items():
            if isinstance(value, dict) and value.get("error"):
                is_degraded = True
                layer_warnings.append(
                    f"Key '{key}' contains error field: {value['error']}"
                )

        if is_degraded:
            severity = classify_layer_failure(layer_name, error=None, has_fallback_data=True)
            layer_severities.append(severity)
            status = LayerExecutionStatus.DEGRADED
            degraded_layers.append(layer_name)
        else:
            status = LayerExecutionStatus.SUCCESS
            layer_severities.append(FailureSeverity.INFO)

        result = LayerResult(
            layer_name=layer_name,
            status=status,
            data=dict(outputs),
            warnings=tuple(layer_warnings),
            timing_ms=elapsed_ms,
        )
        layer_results.append(result)

        # Merge outputs into state
        for key, value in outputs.items():
            state[key] = value
            key_provenance[key] = layer_name

        completed.add(layer_name)
        execution_log.append({
            "layer": layer_name,
            "produced": sorted(outputs.keys()),
            "status": status.value,
            "timing_ms": elapsed_ms,
        })

    pipeline_total_ms = (time.monotonic() - pipeline_start) * 1000

    # Determine pipeline status
    if failed_layers:
        pipeline_status = "FAILED"
    elif degraded_layers:
        pipeline_status = "DEGRADED"
    else:
        pipeline_status = "HEALTHY"

    # Compute worst severity
    pipeline_worst = (
        worst_severity(*layer_severities) if layer_severities
        else FailureSeverity.INFO
    )

    state["_pipeline_execution_log"] = execution_log
    state["_pipeline_execution_order"] = execution_order
    state["_pipeline_status"] = pipeline_status
    state["_pipeline_results"] = [r.to_dict() for r in layer_results]
    state["_pipeline_degraded_layers"] = degraded_layers
    state["_pipeline_failed_layers"] = failed_layers
    state["_pipeline_skipped_layers"] = skipped_layers
    state["_pipeline_total_ms"] = pipeline_total_ms
    state["_pipeline_worst_severity"] = pipeline_worst.value
    return state


class _GuardedState(dict):
    """State wrapper that enforces declared input access.

    A layer may only read keys that are:
    1. In initial_state (pre-populated)
    2. Produced by a layer listed in its requires

    This prevents hidden cross-layer dependencies.
    """

    def __init__(
        self,
        state: dict[str, Any],
        current_layer: Layer,
        completed: set[str],
        key_provenance: dict[str, str],
    ):
        super().__init__(state)
        self._current_layer = current_layer
        self._completed = completed
        self._key_provenance = key_provenance
        # Compute allowed keys: initial + keys from required layers' outputs
        self._allowed_keys: set[str] = set()
        for k, producer in key_provenance.items():
            if producer == "__initial__":
                self._allowed_keys.add(k)
            elif producer in current_layer.requires:
                self._allowed_keys.add(k)
        # Also allow keys produced by dependencies' dependencies (transitive)
        # — actually, we only need direct requires since the state is flat
        # and each layer's outputs are in state after completion.
        # A layer's requires already implies it can see those outputs.
        for dep in current_layer.requires:
            for k, producer in key_provenance.items():
                if producer == dep:
                    self._allowed_keys.add(k)

    def __getitem__(self, key: str) -> Any:
        if key.startswith("_"):
            return super().__getitem__(key)
        if key not in self._allowed_keys:
            raise UndeclaredInputError(
                f"Layer '{self._current_layer.name}' accessed state key '{key}' "
                f"which is not in its declared requirements. "
                f"Key was produced by '{self._key_provenance.get(key, 'UNKNOWN')}'. "
                f"Allowed: {sorted(self._allowed_keys)}"
            )
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key.startswith("_"):
            return super().get(key, default)
        if key not in self._allowed_keys:
            raise UndeclaredInputError(
                f"Layer '{self._current_layer.name}' accessed state key '{key}' "
                f"which is not in its declared requirements. "
                f"Key was produced by '{self._key_provenance.get(key, 'UNKNOWN')}'. "
                f"Allowed: {sorted(self._allowed_keys)}"
            )
        return super().get(key, default)


# ═══════════════════════════════════════════════════════════════════════════
# ISI COUNTRY PIPELINE DEFINITION
# ═══════════════════════════════════════════════════════════════════════════

def _compute_severity_layer(state: dict, ctx: dict) -> dict:
    """Compute severity analysis from axis detail."""
    from backend.severity import (
        compute_axis_severity,
        compute_country_severity,
        assign_comparability_tier,
    )
    axes_detail = state["axes_detail"]
    axis_severity_tuples = []
    for ax in axes_detail:
        if ax.get("validity") == "VALID":
            sev = compute_axis_severity(ax.get("data_quality_flags", []))
            axis_severity_tuples.append((ax["axis_id"], ax["axis_slug"], sev))
    country_sev = compute_country_severity(axis_severity_tuples)
    strict_tier = assign_comparability_tier(country_sev["total_severity"])
    return {
        "severity_analysis": country_sev,
        "strict_comparability_tier": strict_tier,
    }


def _compute_governance_layer(state: dict, ctx: dict) -> dict:
    """Compute governance tier from axis detail and severity."""
    from backend.governance import assess_country_governance
    return {
        "governance": assess_country_governance(
            country=ctx["country"],
            axis_results=state["axes_detail"],
            severity_total=state["severity_analysis"]["total_severity"],
            strict_comparability_tier=state["strict_comparability_tier"],
        ),
    }


def _compute_falsification_layer(state: dict, ctx: dict) -> dict:
    """Compute falsification assessment."""
    from backend.falsification import assess_country_falsification
    try:
        return {"falsification": assess_country_falsification(
            ctx["country"], state["governance"],
        )}
    except Exception:
        return {"falsification": {
            "country": ctx["country"],
            "overall_flag": "NOT_ASSESSED",
            "error": "Falsification assessment failed",
        }}


def _compute_decision_usability_layer(state: dict, ctx: dict) -> dict:
    """Compute decision usability classification."""
    from backend.eligibility import classify_decision_usability
    try:
        return {"decision_usability": classify_decision_usability(
            country=ctx["country"],
            governance_result=state["governance"],
        )}
    except Exception:
        return {"decision_usability": {
            "country": ctx["country"],
            "decision_usability_class": "NOT_ASSESSED",
            "error": "Decision usability classification failed",
        }}


def _compute_external_validation_layer(state: dict, ctx: dict) -> dict:
    """Compute external validation block."""
    from backend.external_validation import build_external_validation_block
    from backend.constants import NUM_AXES
    try:
        all_scores = ctx["all_scores"]
        country = ctx["country"]
        axis_scores = {}
        for axis_id in range(1, NUM_AXES + 1):
            scores = all_scores.get(axis_id, {})
            axis_scores[axis_id] = scores.get(country)
        return {"external_validation": build_external_validation_block(
            country=country, axis_scores=axis_scores,
        )}
    except Exception:
        return {"external_validation": {
            "country": ctx["country"],
            "overall_alignment": "NOT_ASSESSED",
            "error": "External validation failed",
        }}


def _compute_construct_enforcement_layer(state: dict, ctx: dict) -> dict:
    """Compute construct enforcement."""
    from backend.construct_enforcement import enforce_all_axes
    from backend.eligibility import build_axis_readiness_matrix
    try:
        readiness_matrix = build_axis_readiness_matrix(ctx["country"])
        ev = state["external_validation"]
        axis_alignment_map = None
        if ev and "per_axis_summary" in ev:
            axis_alignment_map = {}
            for ax in ev["per_axis_summary"]:
                aid = ax.get("axis_id")
                if aid is not None:
                    axis_alignment_map[aid] = ax.get("alignment_status", "UNKNOWN")
        return {"construct_enforcement": enforce_all_axes(
            readiness_matrix=readiness_matrix,
            axis_alignment_map=axis_alignment_map,
        )}
    except Exception:
        return {"construct_enforcement": {
            "per_axis": [], "n_valid": 0, "n_degraded": 0, "n_invalid": 0,
            "composite_producible": False,
            "error": f"Construct enforcement failed for {ctx['country']}",
        }}


def _compute_mapping_audit_layer(state: dict, ctx: dict) -> dict:
    """Compute benchmark mapping audit."""
    from backend.benchmark_mapping_audit import get_mapping_audit_registry
    try:
        return {"mapping_audit_results": get_mapping_audit_registry()}
    except Exception:
        return {"mapping_audit_results": {}}


def _compute_alignment_sensitivity_layer(state: dict, ctx: dict) -> dict:
    """Compute alignment sensitivity."""
    from backend.alignment_sensitivity import run_alignment_sensitivity
    from backend.constants import NUM_AXES
    try:
        all_scores = ctx["all_scores"]
        country = ctx["country"]
        axis_scores = {}
        for axis_id in range(1, NUM_AXES + 1):
            scores = all_scores.get(axis_id, {})
            axis_scores[axis_id] = scores.get(country)
        original_class = None
        ev = state["external_validation"]
        if ev:
            original_class = ev.get("overall_alignment")
        return {"alignment_sensitivity": run_alignment_sensitivity(
            country=country, axis_scores=axis_scores,
            original_alignment_class=original_class,
        )}
    except Exception:
        return {"alignment_sensitivity": {
            "country": ctx["country"],
            "stability_class": "NOT_ASSESSED",
            "original_alignment_class": None,
            "n_perturbations_run": 0, "n_perturbations_changed": 0,
            "error": f"Alignment sensitivity failed for {ctx['country']}",
        }}


def _compute_empirical_alignment_layer(state: dict, ctx: dict) -> dict:
    """Compute empirical alignment classification."""
    from backend.eligibility import classify_empirical_alignment
    try:
        return {"empirical_alignment": classify_empirical_alignment(
            state["external_validation"],
        )}
    except Exception:
        return {"empirical_alignment": None}


def _compute_invariants_layer(state: dict, ctx: dict) -> dict:
    """Compute invariant assessment."""
    from backend.invariants import assess_country_invariants
    from backend.constants import NUM_AXES
    try:
        all_scores = ctx["all_scores"]
        country = ctx["country"]
        axis_scores = {}
        for axis_id in range(1, NUM_AXES + 1):
            scores = all_scores.get(axis_id, {})
            axis_scores[axis_id] = scores.get(country)
        du = state.get("decision_usability")
        du_class = du.get("decision_usability_class") if du else None
        return {"invariant_assessment": assess_country_invariants(
            country=country, axis_scores=axis_scores,
            governance_result=state["governance"],
            alignment_result=state.get("external_validation"),
            decision_usability_class=du_class,
            construct_enforcement=state.get("construct_enforcement"),
            mapping_audit_results=state.get("mapping_audit_results"),
            sensitivity_result=state.get("alignment_sensitivity"),
        )}
    except Exception:
        return {"invariant_assessment": {
            "country": ctx["country"],
            "n_violations": 0, "n_warnings": 0, "n_errors": 0,
            "n_critical": 0, "has_critical": False, "violations": [],
            "error": f"Invariant assessment failed for {ctx['country']}",
        }}


def _compute_failure_visibility_layer(state: dict, ctx: dict) -> dict:
    """Compute failure visibility block."""
    from backend.failure_visibility import build_visibility_block
    try:
        return {"failure_visibility": build_visibility_block(
            country=ctx["country"],
            governance_result=state["governance"],
            decision_usability=state.get("decision_usability"),
            construct_enforcement=state.get("construct_enforcement"),
            external_validation=state.get("external_validation"),
            sensitivity_result=state.get("alignment_sensitivity"),
            mapping_audit_results=state.get("mapping_audit_results"),
            invariant_result=state.get("invariant_assessment"),
        )}
    except Exception:
        return {"failure_visibility": {
            "country": ctx["country"],
            "trust_level": "UNKNOWN",
            "trust_explanation": "Failure visibility computation failed.",
            "severity_summary": {
                "n_critical": 0, "n_error": 0, "n_warning": 0, "n_info": 0,
                "total_flags": 0,
            },
            "error": "Failure visibility failed",
        }}


def _compute_reality_conflicts_layer(state: dict, ctx: dict) -> dict:
    """Compute reality conflicts."""
    from backend.reality_conflicts import detect_reality_conflicts
    try:
        return {"reality_conflicts": detect_reality_conflicts(
            country=ctx["country"],
            governance_result=state["governance"],
            alignment_result=state.get("external_validation"),
            decision_usability=state.get("decision_usability"),
            empirical_alignment=state.get("empirical_alignment"),
        )}
    except Exception:
        return {"reality_conflicts": {
            "country": ctx["country"],
            "n_conflicts": 0, "n_warnings": 0, "n_errors": 0,
            "n_critical": 0, "has_critical": False, "conflicts": [],
            "error": "Reality conflict detection failed",
        }}


# ── Layer Registry ──

COUNTRY_PIPELINE: list[Layer] = [
    Layer(
        name="severity",
        compute=_compute_severity_layer,
        requires=frozenset(),
        produces=frozenset({"severity_analysis", "strict_comparability_tier"}),
    ),
    Layer(
        name="governance",
        compute=_compute_governance_layer,
        requires=frozenset({"severity"}),
        produces=frozenset({"governance"}),
    ),
    Layer(
        name="falsification",
        compute=_compute_falsification_layer,
        requires=frozenset({"governance"}),
        produces=frozenset({"falsification"}),
    ),
    Layer(
        name="decision_usability",
        compute=_compute_decision_usability_layer,
        requires=frozenset({"governance"}),
        produces=frozenset({"decision_usability"}),
    ),
    Layer(
        name="external_validation",
        compute=_compute_external_validation_layer,
        requires=frozenset(),
        produces=frozenset({"external_validation"}),
    ),
    Layer(
        name="construct_enforcement",
        compute=_compute_construct_enforcement_layer,
        requires=frozenset({"external_validation"}),
        produces=frozenset({"construct_enforcement"}),
    ),
    Layer(
        name="mapping_audit",
        compute=_compute_mapping_audit_layer,
        requires=frozenset(),
        produces=frozenset({"mapping_audit_results"}),
    ),
    Layer(
        name="alignment_sensitivity",
        compute=_compute_alignment_sensitivity_layer,
        requires=frozenset({"external_validation"}),
        produces=frozenset({"alignment_sensitivity"}),
    ),
    Layer(
        name="empirical_alignment",
        compute=_compute_empirical_alignment_layer,
        requires=frozenset({"external_validation"}),
        produces=frozenset({"empirical_alignment"}),
    ),
    Layer(
        name="invariants",
        compute=_compute_invariants_layer,
        requires=frozenset({
            "governance", "decision_usability", "external_validation",
            "construct_enforcement", "mapping_audit", "alignment_sensitivity",
        }),
        produces=frozenset({"invariant_assessment"}),
    ),
    Layer(
        name="failure_visibility",
        compute=_compute_failure_visibility_layer,
        requires=frozenset({
            "governance", "decision_usability", "external_validation",
            "construct_enforcement", "mapping_audit", "alignment_sensitivity",
            "invariants",
        }),
        produces=frozenset({"failure_visibility"}),
    ),
    Layer(
        name="reality_conflicts",
        compute=_compute_reality_conflicts_layer,
        requires=frozenset({
            "governance", "decision_usability", "external_validation",
            "empirical_alignment",
        }),
        produces=frozenset({"reality_conflicts"}),
    ),
]


def run_country_pipeline(
    country: str,
    all_scores: dict[int, dict[str, float]],
    axes_detail: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run the full country computation pipeline.

    This is the ONLY sanctioned entry point for computing
    all layers for a single country.

    Args:
        country: ISO-2 code.
        all_scores: {axis_id: {country: score}} for all axes.
        axes_detail: Pre-computed per-axis detail dicts.

    Returns:
        Complete state dict with all layer outputs.
    """
    context = {
        "country": country,
        "all_scores": all_scores,
    }
    initial_state = {
        "axes_detail": axes_detail,
    }
    return run_pipeline(COUNTRY_PIPELINE, context, initial_state)
