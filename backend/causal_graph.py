"""
backend.causal_graph — Deterministic Causal Decision Graph

EXTENSION PASS B: Formal Causal Graph (Controlled).

Problem addressed:
    Dominant constraint extraction is heuristic — it scores reasons
    by severity, breadth, and path bonus. But it has no structural
    knowledge of WHICH upstream modules causally contribute to a
    given final outcome. A severe constraint that lies outside the
    actual causal path should not be dominant.

Solution:
    A static, versioned, deterministic DAG that models the causal
    dependency flow from upstream modules to final decision variables
    (arbiter outcomes). The graph is declared in code, not inferred
    dynamically.

Design contract:
    - The graph is STATIC — edges are declared, not learned.
    - The graph is used for VALIDATION and EXPLANATION, not for
      overriding the arbiter.
    - A constraint cannot be dominant if it does not lie on a valid
      causal path to the final outcome node.
    - The graph is minimal — only nodes that affect final decisions.

Honesty note:
    "A causal graph makes structural claims about decision flow.
    If the declared graph does not match the actual code paths,
    the graph is lying. Keep it synchronized with reality."
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# GRAPH VERSION
# ═══════════════════════════════════════════════════════════════════════════

CAUSAL_GRAPH_VERSION = "causal-v1"


# ═══════════════════════════════════════════════════════════════════════════
# NODE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════
# Nodes are either MODULE nodes (upstream computation) or OUTCOME nodes
# (final decision variables the arbiter controls).

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
# EDGE DEFINITIONS — MODULE → OUTCOME causal links
# ═══════════════════════════════════════════════════════════════════════════
# Each edge means: "when this module produces a binding constraint,
# it causally affects these outcome nodes."
#
# These are derived directly from the 10 arbiter sections in
# epistemic_arbiter.py::adjudicate(). When a section forbids claims
# or changes status, it causally reaches those outcomes.

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
# CAUSAL PATH QUERIES
# ═══════════════════════════════════════════════════════════════════════════

def reaches_outcome(source: str, outcome: str) -> bool:
    """Check if a module source has a causal path to an outcome node.

    Args:
        source: Module node name (e.g. "governance").
        outcome: Outcome node name (e.g. "ranking").

    Returns:
        True if the source has a declared causal edge to the outcome.
    """
    edges = CAUSAL_EDGES.get(source, frozenset())
    return outcome in edges


def get_reachable_outcomes(source: str) -> frozenset[str]:
    """Get all outcome nodes reachable from a module source.

    Args:
        source: Module node name.

    Returns:
        Set of outcome node names this source can causally affect.
    """
    return CAUSAL_EDGES.get(source, frozenset())


def get_causal_sources(outcome: str) -> list[str]:
    """Get all module sources that can causally affect an outcome.

    Args:
        outcome: Outcome node name.

    Returns:
        List of module source names with a causal edge to this outcome.
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
    """Trace the causal path from arbiter reasons to final outcomes.

    For each reason, identifies which outcome nodes it causally reaches.
    This is used for audit/explanation augmentation.

    Args:
        reasons: Arbiter reasoning list (each has source, decision, detail).
        final_status: The final arbiter status.
        forbidden_claims: Claims the arbiter has forbidden.

    Returns:
        List of causal path entries, one per reason.
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
    """Validate that the dominant constraint lies on a causal path.

    The CAUSAL_CONSISTENCY invariant: a constraint cannot be dominant
    if it does not lie on a valid path to the final outcome.

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
        "reason": (
            f"Dominant source '{dominant_source}' reaches "
            f"{sorted(causally_relevant)} — on causal path."
            if passed else
            f"Dominant source '{dominant_source}' reaches "
            f"{sorted(reachable)} but none are relevant to "
            f"final outcomes {sorted(relevant_outcomes)}. "
            f"CAUSAL_CONSISTENCY VIOLATION."
        ),
    }


def get_graph_summary() -> dict[str, Any]:
    """Return a summary of the causal graph for export/audit."""
    return {
        "version": CAUSAL_GRAPH_VERSION,
        "n_module_nodes": len(MODULE_NODES),
        "n_outcome_nodes": len(OUTCOME_NODES),
        "n_edges": sum(len(e) for e in CAUSAL_EDGES.values()),
        "module_nodes": list(MODULE_NODES),
        "outcome_nodes": list(OUTCOME_NODES),
        "edges": {
            source: sorted(outcomes)
            for source, outcomes in CAUSAL_EDGES.items()
        },
    }
