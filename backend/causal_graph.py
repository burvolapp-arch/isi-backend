"""
backend.causal_graph — Decision-Path Dependency Graph

FINALE: Graph honesty pass.

Problem addressed:
    Dominant constraint extraction scores reasons by severity and
    breadth but has no structural knowledge of which upstream
    modules contribute to a given final outcome. A severe constraint
    outside the decision path should not be dominant.

Solution:
    A static, versioned, deterministic DAG that models the
    decision-path dependency flow from upstream modules to final
    decision variables (arbiter outcomes). The graph is declared
    in code, not inferred dynamically.

Design contract:
    - The graph is STATIC — edges are declared, not learned.
    - The graph is used for VALIDATION and EXPLANATION, not for
      overriding the arbiter.
    - A constraint cannot be dominant if it does not lie on a valid
      decision path to the final outcome node.
    - The graph is minimal — only nodes that affect final decisions.

Honesty note:
    "This is a decision-path dependency graph, not a causal graph
    in the interventionist or counterfactual sense. It models which
    arbiter input sections can structurally affect which outcomes.
    It does NOT model counterfactual interventions, confounders,
    or probabilistic causation. Where this graph supports an
    explanation, the explanation is 'decision-path-associated' —
    not 'causally determined'."
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH VERSION
# ═══════════════════════════════════════════════════════════════════════════

GRAPH_VERSION = "decision-path-v1"

# Honest type label — this is NOT a causal graph in the interventionist
# sense. It is a decision-path dependency graph.
GRAPH_TYPE = "decision_path_dependency"

# For backward compatibility
CAUSAL_GRAPH_VERSION = GRAPH_VERSION


# ═══════════════════════════════════════════════════════════════════════════
# NODE DEFINITIONS (typed)
# ═══════════════════════════════════════════════════════════════════════════
# Nodes are either MODULE nodes (upstream computation) or OUTCOME nodes
# (final decision variables the arbiter controls).
# Node types are explicit — no implicit or inferred nodes exist.

class NodeType:
    MODULE = "MODULE"     # An upstream computation module
    OUTCOME = "OUTCOME"   # A final decision variable

# Module nodes — these are the 10 arbiter input sections
MODULE_NODES: tuple[str, ...] = (
    "runtime_status",
    "truth_resolution",
    "override_pressure",
    "authority_precedence",
    "governance",
    "failure_visibility",
    "invariant_report",
    "reality_conflicts",
    "scope",
    "publishability",
)

# Outcome nodes — the 5 claim categories + 2 meta-outcomes
OUTCOME_NODES: tuple[str, ...] = (
    "ranking",
    "comparison",
    "policy_claim",
    "composite",
    "country_ordering",
    "publication",
    "final_status",   # The overall arbiter status
)

ALL_NODES: frozenset[str] = frozenset(MODULE_NODES) | frozenset(OUTCOME_NODES)


# ═══════════════════════════════════════════════════════════════════════════
# EDGE DEFINITIONS — MODULE → OUTCOME decision-path links
# ═══════════════════════════════════════════════════════════════════════════
# Each edge means: "when this module produces a binding constraint,
# it structurally affects these outcome nodes."
#
# These are derived directly from the 10 arbiter sections in
# epistemic_arbiter.py::adjudicate(). When a section forbids claims
# or changes status, it structurally reaches those outcomes.
#
# NOTE: These are decision-path dependencies, not causal edges in
# the interventionist sense. They model code structure, not
# counterfactual causation.

CAUSAL_EDGES: dict[str, frozenset[str]] = {
    # Section 1: runtime FAILED → all claims forbidden + status
    "runtime_status": frozenset({
        "ranking", "comparison", "policy_claim",
        "composite", "country_ordering", "final_status",
    }),

    # Section 2: truth BLOCKED → all 5 claims + status
    "truth_resolution": frozenset({
        "ranking", "comparison", "policy_claim",
        "composite", "country_ordering", "final_status",
    }),

    # Section 3: override pressure → ranking, comparison + status
    "override_pressure": frozenset({
        "ranking", "comparison", "final_status",
    }),

    # Section 4: authority precedence → status only (RESTRICTED/FLAGGED)
    "authority_precedence": frozenset({
        "final_status",
    }),

    # Section 5: governance → ranking, comparison, country_ordering + status
    "governance": frozenset({
        "ranking", "comparison", "country_ordering", "final_status",
    }),

    # Section 6: failure visibility → status only (SUPPRESSED/FLAGGED)
    "failure_visibility": frozenset({
        "final_status",
    }),

    # Section 7: invariant report → ranking, comparison, policy_claim + status
    "invariant_report": frozenset({
        "ranking", "comparison", "policy_claim", "final_status",
    }),

    # Section 8: reality conflicts → status only (SUPPRESSED/FLAGGED)
    "reality_conflicts": frozenset({
        "final_status",
    }),

    # Section 9: scope → status (BLOCKED/RESTRICTED)
    "scope": frozenset({
        "final_status",
    }),

    # Section 10: publishability → publication + status
    "publishability": frozenset({
        "publication", "final_status",
    }),
}


# ═══════════════════════════════════════════════════════════════════════════
# DECISION-PATH QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def reaches_outcome(source: str, outcome: str) -> bool:
    """Check if a module source has a decision-path edge to an outcome.

    Args:
        source: Module node name (e.g. "governance").
        outcome: Outcome node name (e.g. "ranking").

    Returns:
        True if the source has a declared edge to the outcome.
    """
    edges = CAUSAL_EDGES.get(source, frozenset())
    return outcome in edges


def get_reachable_outcomes(source: str) -> frozenset[str]:
    """Get all outcome nodes reachable from a module source.

    Args:
        source: Module node name.

    Returns:
        Set of outcome node names this source can structurally affect.
    """
    return CAUSAL_EDGES.get(source, frozenset())


def get_causal_sources(outcome: str) -> list[str]:
    """Get all module sources with a decision-path edge to an outcome.

    Args:
        outcome: Outcome node name.

    Returns:
        List of module source names with an edge to this outcome.
    """
    return [
        source for source, outcomes in CAUSAL_EDGES.items()
        if outcome in outcomes
    ]


def trace_causal_path(
    reasons: list[dict[str, str]],
    final_status: str,
    forbidden_claims: list[str],
) -> list[dict[str, Any]]:
    """Trace decision-path associations from arbiter reasons to outcomes.

    For each reason, identifies which outcome nodes it structurally
    reaches via declared edges. This is decision-path association,
    not causal inference.

    Args:
        reasons: Arbiter reasoning list (each has source, decision, detail).
        final_status: The final arbiter status.
        forbidden_claims: Claims the arbiter has forbidden.

    Returns:
        List of path entries, one per reason.
    """
    # The relevant outcomes are: final_status + each forbidden claim
    relevant_outcomes = {"final_status"} | set(forbidden_claims)

    path: list[dict[str, Any]] = []
    for reason in reasons:
        source = reason.get("source", "")
        reachable = get_reachable_outcomes(source)
        causally_relevant = reachable & relevant_outcomes

        path.append({
            "source": source,
            "decision": reason.get("decision", "VALID"),
            "reachable_outcomes": sorted(reachable),
            "causally_relevant_outcomes": sorted(causally_relevant),
            "is_on_causal_path": len(causally_relevant) > 0,
        })

    return path


def validate_dominant_on_causal_path(
    dominant_source: str | None,
    final_status: str,
    forbidden_claims: list[str],
) -> dict[str, Any]:
    """Validate that the dominant constraint lies on a decision path.

    The DECISION_PATH_CONSISTENCY invariant: a constraint cannot be
    dominant if it does not lie on a valid path to the final outcome.
    This is structural consistency, not causal inference.

    Args:
        dominant_source: Source of the dominant constraint.
        final_status: The final arbiter status.
        forbidden_claims: Claims the arbiter has forbidden.

    Returns:
        Validation result with pass/fail.
    """
    if dominant_source is None:
        # No dominant constraint = no violation possible
        return {
            "passed": True,
            "dominant_source": None,
            "reason": "No dominant constraint to validate.",
        }

    # The dominant constraint must reach at least one relevant outcome
    relevant_outcomes = {"final_status"} | set(forbidden_claims)
    reachable = get_reachable_outcomes(dominant_source)
    causally_relevant = reachable & relevant_outcomes

    passed = len(causally_relevant) > 0

    return {
        "passed": passed,
        "dominant_source": dominant_source,
        "reachable_outcomes": sorted(reachable),
        "relevant_outcomes": sorted(relevant_outcomes),
        "causally_relevant_outcomes": sorted(causally_relevant),
        "explanation_type": (
            "decision_path_associated" if passed
            else "no_structural_path"
        ),
        "reason": (
            f"Dominant source '{dominant_source}' reaches "
            f"{sorted(causally_relevant)} — on decision path."
            if passed else
            f"Dominant source '{dominant_source}' reaches "
            f"{sorted(reachable)} but none are relevant to "
            f"final outcomes {sorted(relevant_outcomes)}. "
            f"DECISION_PATH_CONSISTENCY VIOLATION."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# STRUCTURAL VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def check_acyclicity() -> dict[str, Any]:
    """Verify the decision-path graph is a DAG (acyclic).

    Since this graph is bipartite (MODULE → OUTCOME, no OUTCOME → MODULE
    edges), acyclicity is guaranteed by construction. This function
    makes that guarantee explicit and mechanically verifiable.

    Returns:
        Acyclicity report with is_acyclic and reason.
    """
    # The graph is bipartite: MODULE_NODES → OUTCOME_NODES.
    # No edge goes from OUTCOME back to MODULE.
    # Therefore, no cycle is possible.
    module_set = frozenset(MODULE_NODES)
    outcome_set = frozenset(OUTCOME_NODES)

    # Verify no edge source is an outcome node
    for source in CAUSAL_EDGES:
        if source in outcome_set:
            return {
                "is_acyclic": False,
                "reason": (
                    f"Edge source '{source}' is an OUTCOME node — "
                    f"violates bipartite structure."
                ),
            }

    # Verify no edge target is a module node
    for source, targets in CAUSAL_EDGES.items():
        for target in targets:
            if target in module_set:
                return {
                    "is_acyclic": False,
                    "reason": (
                        f"Edge {source} → {target}: target is a MODULE "
                        f"node — violates bipartite structure."
                    ),
                }

    return {
        "is_acyclic": True,
        "reason": (
            "Graph is bipartite (MODULE → OUTCOME). "
            "No back-edges possible. Acyclicity guaranteed."
        ),
    }


def check_coverage() -> dict[str, Any]:
    """Verify graph coverage: every outcome is reachable from at
    least one module, and every module has at least one edge.

    Returns:
        Coverage report with passed and uncovered nodes.
    """
    uncovered_outcomes: list[str] = []
    for outcome in OUTCOME_NODES:
        sources = get_causal_sources(outcome)
        if not sources:
            uncovered_outcomes.append(outcome)

    edgeless_modules: list[str] = []
    for module in MODULE_NODES:
        if module not in CAUSAL_EDGES or len(CAUSAL_EDGES[module]) == 0:
            edgeless_modules.append(module)

    passed = len(uncovered_outcomes) == 0 and len(edgeless_modules) == 0

    return {
        "passed": passed,
        "uncovered_outcomes": uncovered_outcomes,
        "edgeless_modules": edgeless_modules,
        "reason": (
            "Full coverage: every outcome is reachable, every module has edges."
            if passed else
            f"Uncovered outcomes: {uncovered_outcomes}. "
            f"Edgeless modules: {edgeless_modules}."
        ),
    }


def get_graph_summary() -> dict[str, Any]:
    """Return a summary of the decision-path graph for export/audit."""
    acyclicity = check_acyclicity()
    return {
        "version": GRAPH_VERSION,
        "graph_type": GRAPH_TYPE,
        "is_acyclic": acyclicity["is_acyclic"],
        "n_module_nodes": len(MODULE_NODES),
        "n_outcome_nodes": len(OUTCOME_NODES),
        "n_edges": sum(len(e) for e in CAUSAL_EDGES.values()),
        "module_nodes": list(MODULE_NODES),
        "outcome_nodes": list(OUTCOME_NODES),
        "edges": {
            source: sorted(outcomes)
            for source, outcomes in CAUSAL_EDGES.items()
        },
        "honesty_note": (
            "This is a decision-path dependency graph. "
            "Edges represent structural code paths, not causal "
            "relationships in the interventionist sense."
        ),
    }
