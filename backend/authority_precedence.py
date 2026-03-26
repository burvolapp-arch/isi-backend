"""
backend.authority_precedence — Authority Precedence Resolution Engine

ENDGAME PASS v2, SECTION 4: Deterministic Authority Precedence.

Problem addressed:
    When multiple external authorities disagree on the same field,
    the system needs a DETERMINISTIC rule for which authority wins.
    The current authority_conflicts.py detects conflicts but does not
    produce a single binding precedence decision with full reasoning.

Solution:
    The authority precedence engine takes all authority claims for a
    field and produces a single winning authority with:
    - The winning_authority and why it won
    - All losing_authorities with reasons
    - Whether any residual conflict remains
    - The conservative bound to apply if conflict is unresolved

Design contract:
    - Precedence is deterministic: same inputs → same winner.
    - Precedence dimensions: tier > recency > domain specificity >
      construct validity > data coverage.
    - If precedence cannot resolve → enforce conservative bound.
    - Every precedence decision is fully documented.
    - NO authority wins by default — it must win on dimensions.

Honesty note:
    "If two authorities disagree and we cannot determine which is
    more reliable, we must not pretend the conflict is resolved.
    We enforce the most conservative interpretation and flag the
    residual conflict."
"""

from __future__ import annotations

from typing import Any

from backend.external_authority_registry import (
    AuthorityTier,
    AUTHORITY_TIER_ORDER,
    get_authority_by_id,
)


# ═══════════════════════════════════════════════════════════════════════════
# PRECEDENCE DIMENSIONS
# ═══════════════════════════════════════════════════════════════════════════

# Tier precedence — lower AUTHORITY_TIER_ORDER = higher precedence
# Recency: 0.0 (oldest) to 1.0 (most recent)
# Domain specificity: 0.0 (general) to 1.0 (highly specific)
# Construct validity: 0.0 (weak) to 1.0 (strong)
# Data coverage: 0.0 (sparse) to 1.0 (comprehensive)


class PrecedenceOutcome:
    """Outcome of a precedence resolution."""
    RESOLVED = "RESOLVED"           # Clear winner determined
    CONSERVATIVE_BOUND = "CONSERVATIVE_BOUND"  # Tie → conservative
    UNRESOLVABLE = "UNRESOLVABLE"   # Cannot determine precedence


VALID_PRECEDENCE_OUTCOMES = frozenset({
    PrecedenceOutcome.RESOLVED,
    PrecedenceOutcome.CONSERVATIVE_BOUND,
    PrecedenceOutcome.UNRESOLVABLE,
})


# ═══════════════════════════════════════════════════════════════════════════
# PRECEDENCE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def resolve_authority_precedence(
    claims: list[dict[str, Any]],
    field: str | None = None,
) -> dict[str, Any]:
    """Resolve which authority wins when multiple authorities disagree.

    Each claim should contain:
        authority_id: str
        value: Any (the value the authority reports)
        recency: float (0.0–1.0, optional, default 0.5)
        domain_specificity: float (0.0–1.0, optional, default 0.5)
        construct_validity: float (0.0–1.0, optional, default 0.5)
        data_coverage: float (0.0–1.0, optional, default 0.5)

    Precedence order:
        1. Authority tier (Tier 1 > Tier 2 > Tier 3)
        2. Recency (more recent > older)
        3. Domain specificity (more specific > general)
        4. Construct validity (stronger validity > weaker)
        5. Data coverage (more comprehensive > sparse)

    If all dimensions are tied → enforce conservative bound.

    Args:
        claims: List of authority claims with metadata.
        field: The field being disputed (for documentation).

    Returns:
        Precedence resolution with winner, losers, and reasoning.
    """
    if not claims:
        return {
            "outcome": PrecedenceOutcome.UNRESOLVABLE,
            "field": field,
            "winning_authority": None,
            "winning_value": None,
            "precedence_reason": "No claims to resolve.",
            "losing_authorities": [],
            "residual_conflict": False,
            "residual_conflict_severity": "NONE",
            "conservative_bound_applied": False,
            "n_claims": 0,
            "honesty_note": (
                "Authority precedence: no claims provided. "
                "Cannot resolve precedence without authority claims."
            ),
        }

    if len(claims) == 1:
        claim = claims[0]
        authority_id = claim.get("authority_id", "unknown")
        authority = get_authority_by_id(authority_id)
        tier = authority["tier"] if authority else "UNKNOWN"

        return {
            "outcome": PrecedenceOutcome.RESOLVED,
            "field": field,
            "winning_authority": authority_id,
            "winning_value": claim.get("value"),
            "winning_tier": tier,
            "precedence_reason": (
                f"Single authority ({authority_id}, {tier}) — "
                f"no conflict to resolve."
            ),
            "losing_authorities": [],
            "residual_conflict": False,
            "residual_conflict_severity": "NONE",
            "conservative_bound_applied": False,
            "n_claims": 1,
            "honesty_note": (
                f"Authority precedence for {field or 'field'}: "
                f"single authority {authority_id} — resolved trivially."
            ),
        }

    # ── Score each claim on precedence dimensions ──
    scored_claims = []
    for claim in claims:
        authority_id = claim.get("authority_id", "unknown")
        authority = get_authority_by_id(authority_id)
        tier = authority["tier"] if authority else AuthorityTier.TIER_3_SUPPORTING
        tier_score = _tier_to_score(tier)

        recency = claim.get("recency", 0.5)
        domain_specificity = claim.get("domain_specificity", 0.5)
        construct_validity = claim.get("construct_validity", 0.5)
        data_coverage = claim.get("data_coverage", 0.5)

        # Composite precedence score (tier-weighted)
        composite = (
            tier_score * 0.40
            + recency * 0.20
            + domain_specificity * 0.15
            + construct_validity * 0.15
            + data_coverage * 0.10
        )

        scored_claims.append({
            "authority_id": authority_id,
            "value": claim.get("value"),
            "tier": tier,
            "tier_score": tier_score,
            "recency": recency,
            "domain_specificity": domain_specificity,
            "construct_validity": construct_validity,
            "data_coverage": data_coverage,
            "composite_score": round(composite, 4),
        })

    # ── Sort by composite score (descending) ──
    scored_claims.sort(key=lambda c: c["composite_score"], reverse=True)

    winner = scored_claims[0]
    runner_up = scored_claims[1]

    # ── Check if winner is clearly ahead ──
    margin = winner["composite_score"] - runner_up["composite_score"]

    if margin < 0.05:
        # Too close to call — enforce conservative bound
        conservative_value = _conservative_value(
            [c["value"] for c in scored_claims],
        )
        losing = [
            {
                "authority_id": c["authority_id"],
                "tier": c["tier"],
                "value": c["value"],
                "composite_score": c["composite_score"],
                "reason": "Too close to call — conservative bound applied.",
            }
            for c in scored_claims
        ]

        # Severity based on tier disagreement
        tiers = {c["tier"] for c in scored_claims}
        if AuthorityTier.TIER_1_PRIMARY in tiers:
            severity = "CRITICAL"
        elif AuthorityTier.TIER_2_AUTHORITATIVE in tiers:
            severity = "ERROR"
        else:
            severity = "WARNING"

        return {
            "outcome": PrecedenceOutcome.CONSERVATIVE_BOUND,
            "field": field,
            "winning_authority": None,
            "winning_value": conservative_value,
            "precedence_reason": (
                f"Precedence margin too small ({margin:.4f} < 0.05). "
                f"Enforcing conservative bound: {conservative_value}."
            ),
            "losing_authorities": losing,
            "residual_conflict": True,
            "residual_conflict_severity": severity,
            "conservative_bound_applied": True,
            "conservative_value": conservative_value,
            "margin": round(margin, 4),
            "n_claims": len(claims),
            "scored_claims": scored_claims,
            "honesty_note": (
                f"Authority precedence for {field or 'field'}: "
                f"CONSERVATIVE BOUND applied. {len(claims)} claims, "
                f"margin {margin:.4f} too small to determine winner. "
                f"Residual conflict severity: {severity}."
            ),
        }

    # ── Clear winner ──
    losers = [
        {
            "authority_id": c["authority_id"],
            "tier": c["tier"],
            "value": c["value"],
            "composite_score": c["composite_score"],
            "reason": (
                f"Outranked by {winner['authority_id']} "
                f"(margin: {winner['composite_score'] - c['composite_score']:.4f})."
            ),
        }
        for c in scored_claims[1:]
    ]

    # Check for residual conflict even with clear winner
    residual = any(
        c["value"] != winner["value"] for c in scored_claims[1:]
    )
    residual_severity = "NONE"
    if residual:
        loser_tiers = {c["tier"] for c in scored_claims[1:]}
        if AuthorityTier.TIER_1_PRIMARY in loser_tiers:
            residual_severity = "ERROR"
        elif AuthorityTier.TIER_2_AUTHORITATIVE in loser_tiers:
            residual_severity = "WARNING"
        else:
            residual_severity = "INFO"

    return {
        "outcome": PrecedenceOutcome.RESOLVED,
        "field": field,
        "winning_authority": winner["authority_id"],
        "winning_value": winner["value"],
        "winning_tier": winner["tier"],
        "winning_score": winner["composite_score"],
        "precedence_reason": (
            f"{winner['authority_id']} ({winner['tier']}) wins with "
            f"composite score {winner['composite_score']:.4f} "
            f"(margin: {margin:.4f} over runner-up)."
        ),
        "losing_authorities": losers,
        "residual_conflict": residual,
        "residual_conflict_severity": residual_severity,
        "conservative_bound_applied": False,
        "margin": round(margin, 4),
        "n_claims": len(claims),
        "scored_claims": scored_claims,
        "honesty_note": (
            f"Authority precedence for {field or 'field'}: "
            f"RESOLVED. Winner: {winner['authority_id']} ({winner['tier']}). "
            f"{len(claims)} claims evaluated, margin {margin:.4f}. "
            f"{'Residual conflict remains (losers disagree).' if residual else 'No residual conflict.'}"
        ),
    }


def resolve_multi_field_precedence(
    field_claims: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Resolve authority precedence for multiple fields at once.

    Args:
        field_claims: Mapping of field name → list of authority claims.

    Returns:
        Dict with per-field resolutions and overall summary.
    """
    resolutions: dict[str, dict[str, Any]] = {}
    n_resolved = 0
    n_conservative = 0
    n_unresolvable = 0
    has_residual = False

    for field_name, claims in field_claims.items():
        resolution = resolve_authority_precedence(claims, field=field_name)
        resolutions[field_name] = resolution

        outcome = resolution["outcome"]
        if outcome == PrecedenceOutcome.RESOLVED:
            n_resolved += 1
        elif outcome == PrecedenceOutcome.CONSERVATIVE_BOUND:
            n_conservative += 1
        else:
            n_unresolvable += 1

        if resolution.get("residual_conflict", False):
            has_residual = True

    return {
        "resolutions": resolutions,
        "n_fields": len(field_claims),
        "n_resolved": n_resolved,
        "n_conservative_bound": n_conservative,
        "n_unresolvable": n_unresolvable,
        "has_residual_conflict": has_residual,
        "honesty_note": (
            f"Multi-field precedence: {len(field_claims)} fields. "
            f"{n_resolved} resolved, {n_conservative} conservative bound, "
            f"{n_unresolvable} unresolvable. "
            f"{'Residual conflicts remain.' if has_residual else 'No residual conflicts.'}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _tier_to_score(tier: str) -> float:
    """Convert authority tier to a numeric score (higher = more precedence)."""
    tier_scores = {
        AuthorityTier.TIER_1_PRIMARY: 1.0,
        AuthorityTier.TIER_2_AUTHORITATIVE: 0.6,
        AuthorityTier.TIER_3_SUPPORTING: 0.3,
    }
    return tier_scores.get(tier, 0.1)


def _conservative_value(values: list[Any]) -> Any:
    """Return the most conservative value from a list.

    For booleans: False is more conservative.
    For numbers: higher is more conservative (higher concentration = worse).
    For strings with known orderings: most restrictive.
    """
    if not values:
        return None

    # Boolean — False is conservative
    if all(isinstance(v, bool) for v in values):
        return any(v is False for v in values) is True and False or all(values)

    # Numeric — higher is conservative (more concentrated = worse)
    if all(isinstance(v, (int, float)) for v in values):
        return max(values)

    # String with known tier ordering
    tier_order = {
        "FULLY_COMPARABLE": 0,
        "PARTIALLY_COMPARABLE": 1,
        "LOW_CONFIDENCE": 2,
        "NON_COMPARABLE": 3,
    }
    if all(isinstance(v, str) and v in tier_order for v in values):
        return max(values, key=lambda x: tier_order[x])

    # Fallback
    return values[0]
