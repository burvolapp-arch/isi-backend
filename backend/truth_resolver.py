"""
backend.truth_resolver — Single Authoritative Truth Resolution Layer

SECTION 3 of Final Closure Pass: Truth Resolution.

Problem addressed:
    Multiple layers compute governance tier, ranking eligibility,
    usability class, and comparability — but they can DISAGREE.
    Without a single resolution point, the system outputs conflicting
    signals. A country can be simultaneously "ranking eligible" by
    governance and "excluded" by construct enforcement.

Solution:
    The truth resolver takes all layer outputs and the enforcement
    matrix result, and produces a SINGLE set of authoritative final
    values. These are the ONLY values that may appear in export.

Design contract:
    - Every exported field has ONE authoritative source.
    - Conflicts between layers are resolved by priority order.
    - Resolution decisions are logged and auditable.
    - The truth_status field indicates overall coherence:
        VALID:    No conflicts — all layers agree.
        DEGRADED: Conflicts resolved by priority — output is usable
                  but some layers disagree.
        INVALID:  Irreconcilable conflicts — export should include
                  explicit warnings.
    - NEVER export without running truth resolution.

Priority order (from highest authority to lowest):
    1. Enforcement matrix (binding consequences)
    2. Reality conflicts (empirical contradictions)
    3. Construct enforcement (structural validity)
    4. Failure visibility (trust assessment)
    5. External validation (benchmark alignment)
    6. Governance assessment (tier determination)
    7. Decision usability (downstream classification)
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# TRUTH STATUS
# ═══════════════════════════════════════════════════════════════════════════

class TruthStatus:
    """Classification of truth resolution outcome."""
    VALID = "VALID"         # All layers agree — no conflicts
    DEGRADED = "DEGRADED"   # Conflicts resolved by priority
    INVALID = "INVALID"     # Irreconcilable contradictions


VALID_TRUTH_STATUSES = frozenset({
    TruthStatus.VALID,
    TruthStatus.DEGRADED,
    TruthStatus.INVALID,
})

# Governance tier ordering (index = severity, higher = worse)
TIER_ORDER = {
    "FULLY_COMPARABLE": 0,
    "PARTIALLY_COMPARABLE": 1,
    "LOW_CONFIDENCE": 2,
    "NON_COMPARABLE": 3,
}

TIER_FROM_ORDER = {v: k for k, v in TIER_ORDER.items()}


def _worst_tier(*tiers: str) -> str:
    """Return the worst (most restrictive) tier from given tiers."""
    worst_idx = max(TIER_ORDER.get(t, 3) for t in tiers)
    return TIER_FROM_ORDER.get(worst_idx, "NON_COMPARABLE")


# ═══════════════════════════════════════════════════════════════════════════
# TRUTH RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def resolve_truth(
    state: dict[str, Any],
    enforcement_result: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the single authoritative truth from all layer outputs.

    This function takes the complete computed state and the enforcement
    matrix result, and produces the final, authoritative values for
    every user-facing field.

    Args:
        state: Complete pipeline state dict.
        enforcement_result: Output of apply_enforcement().

    Returns:
        Truth resolution dict with:
        - final_governance_tier: authoritative tier
        - final_ranking_eligible: authoritative ranking flag
        - final_cross_country_comparable: authoritative comparability
        - final_composite_suppressed: whether composite must be None
        - final_decision_usability: authoritative usability class
        - truth_status: VALID / DEGRADED / INVALID
        - conflicts: list of detected conflicts
        - resolutions: list of resolution decisions
    """
    conflicts: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []

    # ── Start from enforcement result (highest authority) ──
    final_tier = enforcement_result["enforced_governance_tier"]
    final_ranking = enforcement_result["enforced_ranking_eligible"]
    final_comparable = enforcement_result["enforced_cross_country_comparable"]
    final_composite_suppressed = enforcement_result["enforced_composite_suppressed"]
    final_usability = enforcement_result.get("enforced_usability_class")

    # ── Extract layer opinions ──
    governance = state.get("governance", {})
    gov_tier = governance.get("governance_tier", "NON_COMPARABLE")
    gov_ranking = governance.get("ranking_eligible", False)
    gov_comparable = governance.get("cross_country_comparable", False)

    du = state.get("decision_usability", {})
    du_class = du.get("decision_usability_class") if du else None

    ce = state.get("construct_enforcement", {})
    ce_producible = ce.get("composite_producible", True) if ce else True

    ev = state.get("external_validation", {})
    ev_alignment = ev.get("overall_alignment") if ev else None

    fv = state.get("failure_visibility", {})
    fv_trust = fv.get("trust_level") if fv else None

    rc = state.get("reality_conflicts", {})
    rc_critical = rc.get("has_critical", False) if rc else False
    rc_n_critical = rc.get("n_critical", 0) if rc else 0

    inv = state.get("invariant_assessment", {})
    inv_critical = inv.get("has_critical", False) if inv else False

    # ── Detect and resolve conflicts ──

    # Conflict 1: Governance tier vs enforcement tier
    if gov_tier != final_tier:
        conflicts.append({
            "conflict_id": "TRUTH-C001",
            "field": "governance_tier",
            "governance_says": gov_tier,
            "enforcement_says": final_tier,
            "description": (
                f"Governance assessed tier as {gov_tier} but enforcement "
                f"overrode to {final_tier}."
            ),
        })
        resolutions.append({
            "field": "governance_tier",
            "resolved_to": final_tier,
            "authority": "enforcement_matrix",
            "reason": "Enforcement matrix has highest authority.",
        })

    # Conflict 2: Governance ranking vs enforcement ranking
    if gov_ranking != final_ranking:
        conflicts.append({
            "conflict_id": "TRUTH-C002",
            "field": "ranking_eligible",
            "governance_says": gov_ranking,
            "enforcement_says": final_ranking,
            "description": (
                f"Governance says ranking_eligible={gov_ranking} but "
                f"enforcement overrode to {final_ranking}."
            ),
        })
        resolutions.append({
            "field": "ranking_eligible",
            "resolved_to": final_ranking,
            "authority": "enforcement_matrix",
            "reason": (
                "Enforcement detected conditions requiring "
                "ranking exclusion."
            ),
        })

    # Conflict 3: Construct producible vs composite suppressed
    if not ce_producible and not final_composite_suppressed:
        # This shouldn't happen if enforcement is correct, but catch it
        final_composite_suppressed = True
        conflicts.append({
            "conflict_id": "TRUTH-C003",
            "field": "composite_suppressed",
            "construct_enforcement_says": "not producible",
            "enforcement_says": "not suppressed",
            "description": (
                "Construct enforcement says composite is not producible "
                "but enforcement did not suppress it. Truth resolver "
                "forces suppression."
            ),
        })
        resolutions.append({
            "field": "composite_suppressed",
            "resolved_to": True,
            "authority": "truth_resolver",
            "reason": "Construct invalidity always suppresses composite.",
        })

    # Conflict 4: Usability class vs trust level
    if fv_trust == "DO_NOT_USE" and final_usability not in (
        "INVALID_FOR_COMPARISON", None
    ):
        old_usability = final_usability
        final_usability = "INVALID_FOR_COMPARISON"
        conflicts.append({
            "conflict_id": "TRUTH-C004",
            "field": "decision_usability_class",
            "failure_visibility_says": "DO_NOT_USE",
            "current_usability": old_usability,
            "description": (
                f"Failure visibility says DO_NOT_USE but usability was "
                f"{old_usability}. Truth resolver forces INVALID_FOR_COMPARISON."
            ),
        })
        resolutions.append({
            "field": "decision_usability_class",
            "resolved_to": "INVALID_FOR_COMPARISON",
            "authority": "failure_visibility",
            "reason": "DO_NOT_USE trust level overrides all usability.",
        })

    # Conflict 5: Ranking eligible but alignment DIVERGENT
    if final_ranking and ev_alignment == "DIVERGENT":
        final_ranking = False
        conflicts.append({
            "conflict_id": "TRUTH-C005",
            "field": "ranking_eligible",
            "external_validation_says": "DIVERGENT",
            "current_ranking": True,
            "description": (
                "External validation is DIVERGENT but ranking was "
                "still True. Truth resolver forces exclusion."
            ),
        })
        resolutions.append({
            "field": "ranking_eligible",
            "resolved_to": False,
            "authority": "external_validation",
            "reason": "DIVERGENT alignment incompatible with ranking.",
        })

    # Conflict 6: Reality conflicts CRITICAL but ranking not excluded
    if rc_critical and final_ranking:
        final_ranking = False
        conflicts.append({
            "conflict_id": "TRUTH-C006",
            "field": "ranking_eligible",
            "reality_conflicts_says": f"{rc_n_critical} CRITICAL",
            "current_ranking": True,
            "description": (
                f"Reality conflicts has {rc_n_critical} CRITICAL entries "
                f"but ranking was still True. Truth resolver forces exclusion."
            ),
        })
        resolutions.append({
            "field": "ranking_eligible",
            "resolved_to": False,
            "authority": "reality_conflicts",
            "reason": "CRITICAL reality conflicts exclude from ranking.",
        })

    # Conflict 7: Invariant CRITICAL but usability not downgraded
    if inv_critical and final_usability in (
        "TRUSTED_COMPARABLE", "COMPARABLE_WITH_CAVEATS"
    ):
        old_usability = final_usability
        final_usability = "REQUIRES_CONTEXT"
        conflicts.append({
            "conflict_id": "TRUTH-C007",
            "field": "decision_usability_class",
            "invariant_assessment_says": "has_critical=True",
            "current_usability": old_usability,
            "description": (
                f"Invariant assessment has CRITICAL violations but "
                f"usability was {old_usability}. Truth resolver "
                f"forces REQUIRES_CONTEXT."
            ),
        })
        resolutions.append({
            "field": "decision_usability_class",
            "resolved_to": "REQUIRES_CONTEXT",
            "authority": "invariant_assessment",
            "reason": "CRITICAL invariant violations require usability downgrade.",
        })

    # ── Determine truth status ──
    if enforcement_result.get("export_blocked", False):
        truth_status = TruthStatus.INVALID
    elif not conflicts:
        truth_status = TruthStatus.VALID
    else:
        truth_status = TruthStatus.DEGRADED

    # If usability wasn't set by any layer, use the original
    if final_usability is None:
        final_usability = du_class

    # ── Consistency assertions ──
    # NON_COMPARABLE → nothing comparative
    if final_tier == "NON_COMPARABLE":
        final_ranking = False
        final_comparable = False
        final_composite_suppressed = True

    # LOW_CONFIDENCE → no ranking
    if final_tier == "LOW_CONFIDENCE":
        final_ranking = False

    return {
        "final_governance_tier": final_tier,
        "final_ranking_eligible": final_ranking,
        "final_cross_country_comparable": final_comparable,
        "final_composite_suppressed": final_composite_suppressed,
        "final_decision_usability": final_usability,
        "truth_status": truth_status,
        "n_conflicts": len(conflicts),
        "n_resolutions": len(resolutions),
        "conflicts": conflicts,
        "resolutions": resolutions,
        "export_blocked": enforcement_result.get("export_blocked", False),
        "block_reasons": enforcement_result.get("block_reasons", []),
        "enforcement_actions": enforcement_result.get("actions", []),
        "honesty_note": (
            f"Truth resolver processed {len(conflicts)} conflicts with "
            f"{len(resolutions)} resolutions. "
            f"truth_status={truth_status}. "
            f"This is the SINGLE authoritative source for all user-facing fields. "
            f"No other layer's output should be used for governance tier, "
            f"ranking eligibility, or usability classification."
        ),
    }
