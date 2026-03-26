"""
backend.enforcement_matrix — Enforcement Matrix: Flags Must Have Consequences

SECTION 2 of Final Closure Pass: Enforcement Hardening.

Problem addressed:
    The system detects many problems: construct invalidity, alignment
    divergence, reality conflicts, visibility CRITICAL, and invariant
    violations. But detection without consequence is DECORATIVE.
    Flags that don't change output are lies of omission.

Solution:
    The enforcement matrix takes the full computed state (all layer
    outputs) and applies binding rules. Each rule maps a CONDITION to
    an ACTION — downgrade, suppress, exclude, or block.

Design contract:
    - Every rule has a unique ID, a condition, and a binding action.
    - No flag is advisory-only. If the system detects a problem,
      the matrix ENFORCES a consequence.
    - Enforcement actions are logged with rule tracing.
    - The matrix output feeds into the truth resolver.
    - Missing input layers → export BLOCKED (not ignored).

Priority order (highest to lowest):
    1. Export blocking (missing layers, structural impossibility)
    2. NON_COMPARABLE enforcement (override everything comparative)
    3. Construct invalidity (suppress composite)
    4. Reality conflicts CRITICAL (force ranking_eligible=False)
    5. Failure visibility CRITICAL/DO_NOT_USE (force usability downgrade)
    6. Alignment sensitivity UNSTABLE (downgrade usability)
    7. Producer inversion (force LOW_CONFIDENCE minimum)
    8. External validation DIVERGENT (flag + downgrade alignment)
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# ENFORCEMENT RULE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

ENFORCEMENT_RULES: list[dict[str, str]] = [
    {
        "rule_id": "ENF-001",
        "name": "Missing Layer Blocks Export",
        "description": (
            "If any required pipeline layer produced no output "
            "or errored, export is blocked entirely."
        ),
    },
    {
        "rule_id": "ENF-002",
        "name": "Construct Invalid Suppresses Composite",
        "description": (
            "If construct_enforcement shows composite_producible=False, "
            "composite MUST be set to None and ranking excluded."
        ),
    },
    {
        "rule_id": "ENF-003",
        "name": "Alignment DIVERGENT Downgrades",
        "description": (
            "If external_validation overall_alignment is DIVERGENT, "
            "ranking_eligible is forced to False and propagated."
        ),
    },
    {
        "rule_id": "ENF-004",
        "name": "Failure Visibility CRITICAL Forces Usability Downgrade",
        "description": (
            "If failure_visibility trust_level is DO_NOT_USE, "
            "decision usability is forced to INVALID_FOR_COMPARISON."
        ),
    },
    {
        "rule_id": "ENF-005",
        "name": "Reality Conflict CRITICAL Forces Ranking Exclusion",
        "description": (
            "If reality_conflicts has_critical=True, "
            "ranking_eligible is forced to False."
        ),
    },
    {
        "rule_id": "ENF-006",
        "name": "Producer Inversion Threshold Forces LOW_CONFIDENCE",
        "description": (
            "If n_producer_inverted_axes >= 2, governance tier MUST be "
            "at least LOW_CONFIDENCE (never better)."
        ),
    },
    {
        "rule_id": "ENF-007",
        "name": "Alignment Unstable Downgrades Usability",
        "description": (
            "If alignment_sensitivity stability_class is ALIGNMENT_UNSTABLE, "
            "decision usability cannot be TRUSTED_COMPARABLE."
        ),
    },
    {
        "rule_id": "ENF-008",
        "name": "Invariant CRITICAL Forces Review",
        "description": (
            "If invariant_assessment has_critical=True, "
            "decision usability is downgraded."
        ),
    },
]

# Tier ordering from best to worst
TIER_ORDER = {
    "FULLY_COMPARABLE": 0,
    "PARTIALLY_COMPARABLE": 1,
    "LOW_CONFIDENCE": 2,
    "NON_COMPARABLE": 3,
}


def _tier_worse_or_equal(tier_a: str, tier_b: str) -> bool:
    """True if tier_a is worse than or equal to tier_b."""
    return TIER_ORDER.get(tier_a, 3) >= TIER_ORDER.get(tier_b, 3)


def _worst_tier(tier_a: str, tier_b: str) -> str:
    """Return the worse of two tiers."""
    if TIER_ORDER.get(tier_a, 3) >= TIER_ORDER.get(tier_b, 3):
        return tier_a
    return tier_b


# ═══════════════════════════════════════════════════════════════════════════
# CORE ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════

class EnforcementError(Exception):
    """Raised when enforcement detects a blocking condition."""
    pass


def apply_enforcement(state: dict[str, Any]) -> dict[str, Any]:
    """Apply the enforcement matrix to computed pipeline state.

    Reads all layer outputs from state and produces a set of binding
    enforcement actions. These MODIFY the effective governance, usability,
    and ranking eligibility.

    Args:
        state: Full pipeline output dict containing governance,
               construct_enforcement, external_validation, etc.

    Returns:
        Enforcement result dict with:
        - actions: list of applied enforcement actions
        - enforced_governance_tier: possibly downgraded tier
        - enforced_ranking_eligible: possibly forced False
        - enforced_composite_suppressed: True if composite must be None
        - enforced_usability_class: possibly downgraded usability
        - export_blocked: True if export must be prevented
        - block_reasons: list of reasons for blocking
    """
    actions: list[dict[str, Any]] = []
    block_reasons: list[str] = []
    export_blocked = False

    # Extract current state
    governance = state.get("governance") or {}
    current_tier = governance.get("governance_tier", "NON_COMPARABLE")
    current_ranking = governance.get("ranking_eligible", False)
    current_comparable = governance.get("cross_country_comparable", False)
    current_composite_defensible = governance.get("composite_defensible", False)

    # Track enforced values (start from current)
    enforced_tier = current_tier
    enforced_ranking = current_ranking
    enforced_comparable = current_comparable
    enforced_composite_suppressed = False
    enforced_usability_class = None

    # Extract decision_usability
    du = state.get("decision_usability", {})
    if du:
        enforced_usability_class = du.get("decision_usability_class")

    # ── ENF-001: Missing Layer Blocks Export ──
    required_layers = [
        "governance", "decision_usability", "construct_enforcement",
        "external_validation", "failure_visibility", "reality_conflicts",
        "invariant_assessment",
    ]
    missing_layers = []
    for layer_key in required_layers:
        layer_data = state.get(layer_key)
        if layer_data is None:
            missing_layers.append(layer_key)
        elif isinstance(layer_data, dict) and layer_data.get("error"):
            missing_layers.append(f"{layer_key} (errored)")

    if missing_layers:
        export_blocked = True
        block_reasons.append(
            f"Missing or errored layers: {', '.join(missing_layers)}"
        )
        actions.append({
            "rule_id": "ENF-001",
            "action": "BLOCK_EXPORT",
            "reason": f"Missing layers: {', '.join(missing_layers)}",
            "severity": "CRITICAL",
        })

    # ── ENF-002: Construct Invalid Suppresses Composite ──
    ce = state.get("construct_enforcement", {})
    if ce and not ce.get("composite_producible", True):
        enforced_composite_suppressed = True
        enforced_ranking = False
        actions.append({
            "rule_id": "ENF-002",
            "action": "SUPPRESS_COMPOSITE",
            "reason": (
                f"Construct enforcement: composite not producible. "
                f"{ce.get('n_valid', 0)} valid axes, "
                f"{ce.get('n_invalid', 0)} invalid."
            ),
            "severity": "CRITICAL",
        })

    # ── ENF-003: Alignment DIVERGENT ──
    ev = state.get("external_validation", {})
    overall_alignment = ev.get("overall_alignment") if ev else None
    if overall_alignment == "DIVERGENT":
        enforced_ranking = False
        actions.append({
            "rule_id": "ENF-003",
            "action": "EXCLUDE_FROM_RANKING",
            "reason": (
                "External validation overall alignment is DIVERGENT. "
                "Ranking exclusion enforced."
            ),
            "severity": "ERROR",
        })

    # ── ENF-004: Failure Visibility CRITICAL ──
    fv = state.get("failure_visibility", {})
    trust_level = fv.get("trust_level") if fv else None
    if trust_level == "DO_NOT_USE":
        enforced_usability_class = "INVALID_FOR_COMPARISON"
        enforced_ranking = False
        actions.append({
            "rule_id": "ENF-004",
            "action": "DOWNGRADE_USABILITY",
            "reason": (
                "Failure visibility trust_level is DO_NOT_USE. "
                "Usability forced to INVALID_FOR_COMPARISON."
            ),
            "severity": "CRITICAL",
        })

    # ── ENF-005: Reality Conflict CRITICAL ──
    rc = state.get("reality_conflicts", {})
    if rc and rc.get("has_critical", False):
        enforced_ranking = False
        actions.append({
            "rule_id": "ENF-005",
            "action": "EXCLUDE_FROM_RANKING",
            "reason": (
                f"Reality conflicts: {rc.get('n_critical', 0)} CRITICAL "
                f"conflicts detected. Ranking exclusion enforced."
            ),
            "severity": "CRITICAL",
        })

    # ── ENF-006: Producer Inversion Threshold ──
    n_inverted = governance.get("n_producer_inverted_axes", 0)
    if n_inverted >= 2:
        enforced_tier = _worst_tier(enforced_tier, "LOW_CONFIDENCE")
        enforced_comparable = False
        actions.append({
            "rule_id": "ENF-006",
            "action": "ENFORCE_TIER_FLOOR",
            "reason": (
                f"{n_inverted} producer-inverted axes. "
                f"Tier floor enforced to LOW_CONFIDENCE."
            ),
            "severity": "WARNING",
        })

    # ── ENF-007: Alignment Unstable ──
    sens = state.get("alignment_sensitivity", {})
    stability_class = sens.get("stability_class") if sens else None
    if stability_class == "ALIGNMENT_UNSTABLE":
        if enforced_usability_class == "TRUSTED_COMPARABLE":
            enforced_usability_class = "COMPARABLE_WITH_CAVEATS"
        actions.append({
            "rule_id": "ENF-007",
            "action": "DOWNGRADE_USABILITY",
            "reason": (
                "Alignment sensitivity shows ALIGNMENT_UNSTABLE. "
                "Cannot maintain TRUSTED_COMPARABLE."
            ),
            "severity": "WARNING",
        })

    # ── ENF-008: Invariant CRITICAL ──
    inv = state.get("invariant_assessment", {})
    if inv and inv.get("has_critical", False):
        if enforced_usability_class in ("TRUSTED_COMPARABLE", "COMPARABLE_WITH_CAVEATS"):
            enforced_usability_class = "REQUIRES_CONTEXT"
        enforced_ranking = False
        actions.append({
            "rule_id": "ENF-008",
            "action": "DOWNGRADE_USABILITY",
            "reason": (
                f"Invariant assessment: {inv.get('n_critical', 0)} CRITICAL "
                f"violations. Usability downgraded, ranking excluded."
            ),
            "severity": "CRITICAL",
        })

    # If tier is NON_COMPARABLE, force all comparative flags off
    if enforced_tier == "NON_COMPARABLE":
        enforced_ranking = False
        enforced_comparable = False
        enforced_composite_suppressed = True

    # If tier is LOW_CONFIDENCE, force ranking off
    if enforced_tier == "LOW_CONFIDENCE":
        enforced_ranking = False

    return {
        "actions": actions,
        "n_actions": len(actions),
        "export_blocked": export_blocked,
        "block_reasons": block_reasons,
        "enforced_governance_tier": enforced_tier,
        "enforced_ranking_eligible": enforced_ranking,
        "enforced_cross_country_comparable": enforced_comparable,
        "enforced_composite_suppressed": enforced_composite_suppressed,
        "enforced_usability_class": enforced_usability_class,
        "original_governance_tier": current_tier,
        "original_ranking_eligible": current_ranking,
        "tier_changed": enforced_tier != current_tier,
        "ranking_changed": enforced_ranking != current_ranking,
        "honesty_note": (
            f"Enforcement matrix applied {len(actions)} actions. "
            f"{'EXPORT BLOCKED: ' + '; '.join(block_reasons) if export_blocked else 'Export permitted.'} "
            f"Every flag has a consequence — no decorative detection."
        ),
    }


def get_enforcement_rules() -> list[dict[str, str]]:
    """Return the full enforcement rule registry."""
    return list(ENFORCEMENT_RULES)
