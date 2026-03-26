"""
backend.permitted_scope — Permitted Output Scope Engine

SECTION 4 of Ultimate Pass: Output Scope Enforcement.

Problem addressed:
    The system can produce outputs that are STRONGER than the data
    supports. A country with LOW_CONFIDENCE governance tier should
    not have a clean ranking position. A composite score computed
    from 4/6 axes should not be treated identically to one from 6/6.

Solution:
    The permitted scope engine determines what the system is ALLOWED
    to output for a given country, based on:
    - Governance tier
    - Truth resolution result
    - Override results
    - Data completeness
    - External authority constraints

Design contract:
    - The system NEVER outputs more than the scope permits.
    - Scope restrictions STACK (most restrictive wins).
    - Every scope limitation is documented in output.
    - If all scope checks pass, the system is permitted to output
      the full range. Otherwise, specific outputs are suppressed.
    - Rankings are the FIRST thing suppressed.
    - Clean scores are the SECOND thing suppressed.
    - Classifications are the LAST thing suppressed.

Honesty note:
    Permitted scope is the system's self-censorship mechanism. If
    the system cannot defensibly produce a ranking, it MUST NOT
    produce a ranking — even if the score is technically computable.
    "Technically computable" ≠ "defensibly publishable."
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# SCOPE LEVELS — what the system is permitted to output
# ═══════════════════════════════════════════════════════════════════════════

class ScopeLevel:
    """Classification of permitted output scope.

    FULL:       All outputs permitted — score, rank, classification,
                comparison, composite.
    RESTRICTED: Scores and classification permitted, ranking suppressed.
    CONTEXT_ONLY: Scores available but MUST carry mandatory caveats.
                  No ranking, no clean comparison.
    SUPPRESSED: Only metadata and limitations available. No scores,
                no ranking, no classification.
    BLOCKED:    Nothing can be output. Export must fail for this country.
    """
    FULL = "FULL"
    RESTRICTED = "RESTRICTED"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    SUPPRESSED = "SUPPRESSED"
    BLOCKED = "BLOCKED"


VALID_SCOPE_LEVELS = frozenset({
    ScopeLevel.FULL,
    ScopeLevel.RESTRICTED,
    ScopeLevel.CONTEXT_ONLY,
    ScopeLevel.SUPPRESSED,
    ScopeLevel.BLOCKED,
})

# Scope ordering — higher index = more restrictive
SCOPE_ORDER: dict[str, int] = {
    ScopeLevel.FULL: 0,
    ScopeLevel.RESTRICTED: 1,
    ScopeLevel.CONTEXT_ONLY: 2,
    ScopeLevel.SUPPRESSED: 3,
    ScopeLevel.BLOCKED: 4,
}


def _most_restrictive_scope(*scopes: str) -> str:
    """Return the most restrictive scope from given scopes."""
    worst_idx = max(SCOPE_ORDER.get(s, 4) for s in scopes)
    for level, idx in SCOPE_ORDER.items():
        if idx == worst_idx:
            return level
    return ScopeLevel.BLOCKED


# ═══════════════════════════════════════════════════════════════════════════
# SCOPE PERMISSIONS — what is allowed at each level
# ═══════════════════════════════════════════════════════════════════════════

SCOPE_PERMISSIONS: dict[str, dict[str, bool]] = {
    ScopeLevel.FULL: {
        "ranking_permitted": True,
        "comparison_permitted": True,
        "composite_permitted": True,
        "score_permitted": True,
        "classification_permitted": True,
        "caveats_required": False,
    },
    ScopeLevel.RESTRICTED: {
        "ranking_permitted": False,
        "comparison_permitted": False,
        "composite_permitted": True,
        "score_permitted": True,
        "classification_permitted": True,
        "caveats_required": True,
    },
    ScopeLevel.CONTEXT_ONLY: {
        "ranking_permitted": False,
        "comparison_permitted": False,
        "composite_permitted": False,
        "score_permitted": True,
        "classification_permitted": True,
        "caveats_required": True,
    },
    ScopeLevel.SUPPRESSED: {
        "ranking_permitted": False,
        "comparison_permitted": False,
        "composite_permitted": False,
        "score_permitted": False,
        "classification_permitted": False,
        "caveats_required": True,
    },
    ScopeLevel.BLOCKED: {
        "ranking_permitted": False,
        "comparison_permitted": False,
        "composite_permitted": False,
        "score_permitted": False,
        "classification_permitted": False,
        "caveats_required": True,
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# SCOPE DETERMINATION
# ═══════════════════════════════════════════════════════════════════════════

def determine_permitted_scope(
    truth_result: dict[str, Any] | None = None,
    override_summary: dict[str, Any] | None = None,
    data_completeness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Determine the permitted output scope for a country.

    This function evaluates all available information and produces
    the maximum scope of output that the system is defensibly
    permitted to produce.

    Args:
        truth_result: Output of resolve_truth() for this country.
        override_summary: Output of compute_override_summary() if any.
        data_completeness: {axes_available, axes_required, ...}

    Returns:
        Scope determination with level, permissions, and reasons.
    """
    scope_reasons: list[dict[str, Any]] = []
    current_scope = ScopeLevel.FULL

    # ── Check 1: Truth resolution status ──
    if truth_result is not None:
        truth_status = truth_result.get("truth_status", "VALID")
        export_blocked = truth_result.get("export_blocked", False)
        final_tier = truth_result.get("final_governance_tier", "FULLY_COMPARABLE")
        final_ranking = truth_result.get("final_ranking_eligible", True)
        final_composite_suppressed = truth_result.get(
            "final_composite_suppressed", False,
        )

        if export_blocked:
            current_scope = _most_restrictive_scope(current_scope, ScopeLevel.BLOCKED)
            scope_reasons.append({
                "check": "truth_export_blocked",
                "scope_applied": ScopeLevel.BLOCKED,
                "reason": (
                    "Truth resolver has blocked export. "
                    f"Block reasons: {truth_result.get('block_reasons', [])}"
                ),
            })

        if truth_status == "INVALID":
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.SUPPRESSED,
            )
            scope_reasons.append({
                "check": "truth_status_invalid",
                "scope_applied": ScopeLevel.SUPPRESSED,
                "reason": "Truth status is INVALID — irreconcilable contradictions.",
            })

        if final_tier == "NON_COMPARABLE":
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.SUPPRESSED,
            )
            scope_reasons.append({
                "check": "tier_non_comparable",
                "scope_applied": ScopeLevel.SUPPRESSED,
                "reason": "Governance tier is NON_COMPARABLE — no comparative output.",
            })

        if final_tier == "LOW_CONFIDENCE":
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.CONTEXT_ONLY,
            )
            scope_reasons.append({
                "check": "tier_low_confidence",
                "scope_applied": ScopeLevel.CONTEXT_ONLY,
                "reason": (
                    "Governance tier is LOW_CONFIDENCE — "
                    "scores available with mandatory caveats only."
                ),
            })

        if not final_ranking:
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.RESTRICTED,
            )
            scope_reasons.append({
                "check": "ranking_not_eligible",
                "scope_applied": ScopeLevel.RESTRICTED,
                "reason": "Country is not ranking-eligible.",
            })

        if final_composite_suppressed:
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.CONTEXT_ONLY,
            )
            scope_reasons.append({
                "check": "composite_suppressed",
                "scope_applied": ScopeLevel.CONTEXT_ONLY,
                "reason": "Composite score is suppressed — context-only output.",
            })

    # ── Check 2: Override results ──
    if override_summary is not None:
        if override_summary.get("has_blocking", False):
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.BLOCKED,
            )
            scope_reasons.append({
                "check": "override_blocking",
                "scope_applied": ScopeLevel.BLOCKED,
                "reason": "Epistemic override engine detected blocking conflict.",
            })

        n_accepted = override_summary.get("n_accepted", 0)
        n_restricted = override_summary.get("n_restricted", 0)
        if n_accepted > 0 or n_restricted > 0:
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.RESTRICTED,
            )
            scope_reasons.append({
                "check": "override_restrictions",
                "scope_applied": ScopeLevel.RESTRICTED,
                "reason": (
                    f"External authority overrides applied: "
                    f"{n_accepted} accepted, {n_restricted} restricted."
                ),
            })

    # ── Check 3: Data completeness ──
    if data_completeness is not None:
        axes_available = data_completeness.get("axes_available", 6)
        axes_required = data_completeness.get("axes_required", 6)

        if axes_available < axes_required:
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.CONTEXT_ONLY,
            )
            scope_reasons.append({
                "check": "incomplete_data",
                "scope_applied": ScopeLevel.CONTEXT_ONLY,
                "reason": (
                    f"Only {axes_available}/{axes_required} axes available. "
                    f"Incomplete data restricts scope."
                ),
            })

        if axes_available == 0:
            current_scope = _most_restrictive_scope(
                current_scope, ScopeLevel.SUPPRESSED,
            )
            scope_reasons.append({
                "check": "no_data",
                "scope_applied": ScopeLevel.SUPPRESSED,
                "reason": "No axis data available. All output suppressed.",
            })

    # ── Build permissions from scope level ──
    permissions = dict(SCOPE_PERMISSIONS.get(current_scope, SCOPE_PERMISSIONS[ScopeLevel.BLOCKED]))

    return {
        "scope_level": current_scope,
        "permissions": permissions,
        "scope_reasons": scope_reasons,
        "n_reasons": len(scope_reasons),
        "honesty_note": (
            f"Permitted scope is {current_scope}. "
            f"{len(scope_reasons)} restriction(s) applied. "
            f"The system will not produce output beyond this scope."
        ),
    }


def enforce_scope(
    output: dict[str, Any],
    scope_result: dict[str, Any],
) -> dict[str, Any]:
    """Apply scope restrictions to a country output dict.

    This function modifies the output to comply with the determined
    scope. Fields that are not permitted are set to None with
    an explanation.

    Args:
        output: The country JSON output dict.
        scope_result: Output of determine_permitted_scope().

    Returns:
        Modified output dict with scope enforcement applied.
    """
    permissions = scope_result.get("permissions", {})
    scope_level = scope_result.get("scope_level", ScopeLevel.BLOCKED)
    enforced = dict(output)

    scope_warnings: list[str] = []

    if not permissions.get("ranking_permitted", False):
        if enforced.get("ranking_position") is not None:
            enforced["ranking_position"] = None
            scope_warnings.append(
                "Ranking position suppressed: not permitted at scope "
                f"level {scope_level}."
            )

    if not permissions.get("composite_permitted", False):
        if enforced.get("isi_composite") is not None:
            scope_warnings.append(
                "Composite score suppressed: not permitted at scope "
                f"level {scope_level}."
            )
            enforced["isi_composite"] = None
            enforced["isi_classification"] = None

    if not permissions.get("score_permitted", False):
        for ax in enforced.get("axes", []):
            if isinstance(ax, dict) and ax.get("score") is not None:
                ax["score"] = None
                ax["classification"] = None
        scope_warnings.append(
            "Individual axis scores suppressed: not permitted at scope "
            f"level {scope_level}."
        )

    # Attach scope enforcement metadata
    enforced["permitted_scope"] = {
        "scope_level": scope_level,
        "permissions": permissions,
        "scope_warnings": scope_warnings,
        "n_scope_warnings": len(scope_warnings),
        "scope_reasons": scope_result.get("scope_reasons", []),
    }

    return enforced
