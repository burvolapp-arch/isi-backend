"""
backend.epistemic_bounds — Epistemic Bounds Propagation Engine

ENDGAME PASS v2, SECTION 2: Epistemic Bound Propagation.

Problem addressed:
    Every upstream constraint imposes a ceiling on what downstream
    layers can claim. If confidence is capped at 0.6 because of
    data quality, NO downstream layer should produce output that
    implies confidence > 0.6 — not in scores, rankings, comparisons,
    or publishability.

Solution:
    EpistemicBounds is a frozen dataclass that captures the epistemic
    ceiling imposed by upstream layers. Bounds can only TIGHTEN — never
    loosen — as they propagate downstream. The merge rule is: take
    the MORE RESTRICTIVE of any two bounds on every dimension.

Design contract:
    - Bounds are immutable (frozen dataclass).
    - merge_bounds() always returns bounds ≤ both inputs on every dimension.
    - No layer may call expand — only tighten or pass through.
    - Every function that produces output should accept and respect bounds.

Honesty note:
    If upstream says "confidence ≤ 0.6", then downstream output that
    implies confidence 0.8 is epistemically dishonest — even if the
    downstream computation is technically correct. Bounds enforce
    epistemic humility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# EPISTEMIC BOUNDS — immutable ceiling on downstream claims
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EpistemicBounds:
    """Immutable epistemic ceiling.

    Every field represents the MAXIMUM that downstream layers are
    permitted to claim. Bounds only tighten — never expand.
    """
    max_confidence: float = 1.0
    max_publishability: str = "PUBLISHABLE"
    can_rank: bool = True
    can_compare: bool = True
    can_publish_policy_claim: bool = True
    can_publish_composite: bool = True
    can_publish_country_ordering: bool = True
    required_warnings: tuple[str, ...] = ()
    binding_constraints: tuple[str, ...] = ()


# Publishability ordering — lower index = more permissive
_PUBLISHABILITY_ORDER: dict[str, int] = {
    "PUBLISHABLE": 0,
    "PUBLISHABLE_WITH_CAVEATS": 1,
    "RESTRICTED": 2,
    "NOT_PUBLISHABLE": 3,
}

# Reverse lookup
_PUBLISHABILITY_BY_INDEX: dict[int, str] = {
    v: k for k, v in _PUBLISHABILITY_ORDER.items()
}


def _more_restrictive_publishability(a: str, b: str) -> str:
    """Return the more restrictive publishability status."""
    idx_a = _PUBLISHABILITY_ORDER.get(a, 3)
    idx_b = _PUBLISHABILITY_ORDER.get(b, 3)
    return _PUBLISHABILITY_BY_INDEX.get(max(idx_a, idx_b), "NOT_PUBLISHABLE")


# ═══════════════════════════════════════════════════════════════════════════
# BOUNDS OPERATIONS — merge (tighten), never expand
# ═══════════════════════════════════════════════════════════════════════════

def merge_bounds(a: EpistemicBounds, b: EpistemicBounds) -> EpistemicBounds:
    """Merge two bounds, taking the MORE RESTRICTIVE on every dimension.

    This is the fundamental operation of bounds propagation. The result
    is always ≤ both inputs on every dimension.

    Args:
        a: First bounds.
        b: Second bounds.

    Returns:
        Merged bounds — the tightest constraint from either input.
    """
    merged_warnings = tuple(sorted(set(a.required_warnings) | set(b.required_warnings)))
    merged_constraints = tuple(sorted(set(a.binding_constraints) | set(b.binding_constraints)))

    return EpistemicBounds(
        max_confidence=min(a.max_confidence, b.max_confidence),
        max_publishability=_more_restrictive_publishability(
            a.max_publishability, b.max_publishability,
        ),
        can_rank=a.can_rank and b.can_rank,
        can_compare=a.can_compare and b.can_compare,
        can_publish_policy_claim=(
            a.can_publish_policy_claim and b.can_publish_policy_claim
        ),
        can_publish_composite=(
            a.can_publish_composite and b.can_publish_composite
        ),
        can_publish_country_ordering=(
            a.can_publish_country_ordering and b.can_publish_country_ordering
        ),
        required_warnings=merged_warnings,
        binding_constraints=merged_constraints,
    )


def tighten_bounds(
    base: EpistemicBounds,
    *,
    max_confidence: float | None = None,
    max_publishability: str | None = None,
    can_rank: bool | None = None,
    can_compare: bool | None = None,
    can_publish_policy_claim: bool | None = None,
    can_publish_composite: bool | None = None,
    can_publish_country_ordering: bool | None = None,
    add_warnings: tuple[str, ...] = (),
    add_constraints: tuple[str, ...] = (),
) -> EpistemicBounds:
    """Tighten specific dimensions of existing bounds.

    Each provided value is merged with the existing value using the
    MORE RESTRICTIVE rule. Unprovided dimensions are unchanged.

    Args:
        base: Starting bounds.
        max_confidence: If provided, new confidence ceiling (min with existing).
        max_publishability: If provided, more restrictive publishability.
        can_rank: If False, disables ranking.
        can_compare: If False, disables comparison.
        can_publish_policy_claim: If False, disables policy claims.
        can_publish_composite: If False, disables composite publication.
        can_publish_country_ordering: If False, disables country ordering.
        add_warnings: Additional required warnings.
        add_constraints: Additional binding constraints.

    Returns:
        Tightened bounds — never looser than base.
    """
    new_confidence = base.max_confidence
    if max_confidence is not None:
        new_confidence = min(base.max_confidence, max_confidence)

    new_publishability = base.max_publishability
    if max_publishability is not None:
        new_publishability = _more_restrictive_publishability(
            base.max_publishability, max_publishability,
        )

    new_rank = base.can_rank
    if can_rank is not None:
        new_rank = base.can_rank and can_rank

    new_compare = base.can_compare
    if can_compare is not None:
        new_compare = base.can_compare and can_compare

    new_policy = base.can_publish_policy_claim
    if can_publish_policy_claim is not None:
        new_policy = base.can_publish_policy_claim and can_publish_policy_claim

    new_composite = base.can_publish_composite
    if can_publish_composite is not None:
        new_composite = base.can_publish_composite and can_publish_composite

    new_ordering = base.can_publish_country_ordering
    if can_publish_country_ordering is not None:
        new_ordering = base.can_publish_country_ordering and can_publish_country_ordering

    merged_warnings = tuple(sorted(
        set(base.required_warnings) | set(add_warnings),
    ))
    merged_constraints = tuple(sorted(
        set(base.binding_constraints) | set(add_constraints),
    ))

    return EpistemicBounds(
        max_confidence=new_confidence,
        max_publishability=new_publishability,
        can_rank=new_rank,
        can_compare=new_compare,
        can_publish_policy_claim=new_policy,
        can_publish_composite=new_composite,
        can_publish_country_ordering=new_ordering,
        required_warnings=merged_warnings,
        binding_constraints=merged_constraints,
    )


def bounds_are_tighter_or_equal(
    child: EpistemicBounds,
    parent: EpistemicBounds,
) -> bool:
    """Check that child bounds are ≤ parent bounds on every dimension.

    Returns True if the child respects the parent's ceiling on ALL
    dimensions. This is the monotonicity check.
    """
    if child.max_confidence > parent.max_confidence:
        return False

    child_pub_idx = _PUBLISHABILITY_ORDER.get(child.max_publishability, 3)
    parent_pub_idx = _PUBLISHABILITY_ORDER.get(parent.max_publishability, 3)
    if child_pub_idx < parent_pub_idx:
        return False

    # Boolean dimensions: child True when parent False = expansion
    if child.can_rank and not parent.can_rank:
        return False
    if child.can_compare and not parent.can_compare:
        return False
    if child.can_publish_policy_claim and not parent.can_publish_policy_claim:
        return False
    if child.can_publish_composite and not parent.can_publish_composite:
        return False
    if child.can_publish_country_ordering and not parent.can_publish_country_ordering:
        return False

    # Warnings: child must include ALL parent warnings
    if not set(parent.required_warnings).issubset(set(child.required_warnings)):
        return False

    return True


def detect_bounds_violations(
    child: EpistemicBounds,
    parent: EpistemicBounds,
) -> list[dict[str, Any]]:
    """Detect specific dimensions where child expands beyond parent.

    Returns a list of violation records, one per violated dimension.
    Empty list = child respects parent bounds.
    """
    violations: list[dict[str, Any]] = []

    if child.max_confidence > parent.max_confidence:
        violations.append({
            "dimension": "max_confidence",
            "parent_value": parent.max_confidence,
            "child_value": child.max_confidence,
            "violation": "Confidence expanded beyond upstream ceiling.",
        })

    child_pub_idx = _PUBLISHABILITY_ORDER.get(child.max_publishability, 3)
    parent_pub_idx = _PUBLISHABILITY_ORDER.get(parent.max_publishability, 3)
    if child_pub_idx < parent_pub_idx:
        violations.append({
            "dimension": "max_publishability",
            "parent_value": parent.max_publishability,
            "child_value": child.max_publishability,
            "violation": "Publishability expanded beyond upstream ceiling.",
        })

    bool_dims = [
        ("can_rank", child.can_rank, parent.can_rank),
        ("can_compare", child.can_compare, parent.can_compare),
        ("can_publish_policy_claim", child.can_publish_policy_claim, parent.can_publish_policy_claim),
        ("can_publish_composite", child.can_publish_composite, parent.can_publish_composite),
        ("can_publish_country_ordering", child.can_publish_country_ordering, parent.can_publish_country_ordering),
    ]

    for dim_name, child_val, parent_val in bool_dims:
        if child_val and not parent_val:
            violations.append({
                "dimension": dim_name,
                "parent_value": parent_val,
                "child_value": child_val,
                "violation": f"{dim_name} enabled by child but disabled by parent.",
            })

    missing_warnings = set(parent.required_warnings) - set(child.required_warnings)
    if missing_warnings:
        violations.append({
            "dimension": "required_warnings",
            "parent_value": list(parent.required_warnings),
            "child_value": list(child.required_warnings),
            "violation": f"Child dropped required warnings: {sorted(missing_warnings)}",
        })

    return violations


def bounds_from_truth_result(
    truth_result: dict[str, Any],
) -> EpistemicBounds:
    """Derive epistemic bounds from a truth resolution result.

    Maps truth resolver outputs to the bounds they imply.
    """
    truth_status = truth_result.get("truth_status", "VALID")
    final_tier = truth_result.get("final_governance_tier", "FULLY_COMPARABLE")
    ranking_eligible = truth_result.get("final_ranking_eligible", True)
    comparable = truth_result.get("final_cross_country_comparable", True)
    export_blocked = truth_result.get("export_blocked", False)

    warnings: list[str] = []
    constraints: list[str] = []

    if export_blocked:
        return EpistemicBounds(
            max_confidence=0.0,
            max_publishability="NOT_PUBLISHABLE",
            can_rank=False,
            can_compare=False,
            can_publish_policy_claim=False,
            can_publish_composite=False,
            can_publish_country_ordering=False,
            required_warnings=("Export blocked by truth resolver.",),
            binding_constraints=("truth_export_blocked",),
        )

    if truth_status == "INVALID":
        return EpistemicBounds(
            max_confidence=0.0,
            max_publishability="NOT_PUBLISHABLE",
            can_rank=False,
            can_compare=False,
            can_publish_policy_claim=False,
            can_publish_composite=False,
            can_publish_country_ordering=False,
            required_warnings=("Truth status INVALID — irreconcilable contradictions.",),
            binding_constraints=("truth_invalid",),
        )

    max_conf = 1.0
    max_pub = "PUBLISHABLE"

    if truth_status == "DEGRADED":
        max_conf = min(max_conf, 0.7)
        max_pub = "PUBLISHABLE_WITH_CAVEATS"
        n_conflicts = truth_result.get("n_conflicts", 0)
        warnings.append(
            f"Truth resolution degraded with {n_conflicts} conflict(s)."
        )
        constraints.append("truth_degraded")

    if final_tier == "NON_COMPARABLE":
        max_conf = min(max_conf, 0.3)
        max_pub = "NOT_PUBLISHABLE"
        constraints.append("tier_non_comparable")
    elif final_tier == "LOW_CONFIDENCE":
        max_conf = min(max_conf, 0.5)
        max_pub = _more_restrictive_publishability(
            max_pub, "PUBLISHABLE_WITH_CAVEATS",
        )
        warnings.append("Governance tier is LOW_CONFIDENCE.")
        constraints.append("tier_low_confidence")

    return EpistemicBounds(
        max_confidence=max_conf,
        max_publishability=max_pub,
        can_rank=ranking_eligible,
        can_compare=comparable,
        can_publish_policy_claim=truth_status == "VALID",
        can_publish_composite=truth_result.get("final_composite_suppressed", False) is False,
        can_publish_country_ordering=ranking_eligible and comparable,
        required_warnings=tuple(warnings),
        binding_constraints=tuple(constraints),
    )


def bounds_from_scope_result(
    scope_result: dict[str, Any],
) -> EpistemicBounds:
    """Derive epistemic bounds from a scope determination result."""
    scope_level = scope_result.get("scope_level", "FULL")
    permissions = scope_result.get("permissions", {})

    scope_pub_map = {
        "FULL": "PUBLISHABLE",
        "RESTRICTED": "PUBLISHABLE_WITH_CAVEATS",
        "CONTEXT_ONLY": "RESTRICTED",
        "SUPPRESSED": "NOT_PUBLISHABLE",
        "BLOCKED": "NOT_PUBLISHABLE",
    }

    scope_conf_map = {
        "FULL": 1.0,
        "RESTRICTED": 0.7,
        "CONTEXT_ONLY": 0.4,
        "SUPPRESSED": 0.0,
        "BLOCKED": 0.0,
    }

    warnings: list[str] = []
    constraints: list[str] = []

    if scope_level not in ("FULL",):
        warnings.append(f"Scope level is {scope_level}.")
        constraints.append(f"scope_{scope_level.lower()}")

    return EpistemicBounds(
        max_confidence=scope_conf_map.get(scope_level, 0.0),
        max_publishability=scope_pub_map.get(scope_level, "NOT_PUBLISHABLE"),
        can_rank=permissions.get("ranking_permitted", scope_level in ("FULL", "RESTRICTED")),
        can_compare=permissions.get("comparison_permitted", scope_level in ("FULL", "RESTRICTED")),
        can_publish_policy_claim=permissions.get(
            "policy_claims_permitted", scope_level == "FULL",
        ),
        can_publish_composite=permissions.get(
            "composite_permitted", scope_level in ("FULL", "RESTRICTED"),
        ),
        can_publish_country_ordering=permissions.get(
            "ordering_permitted", scope_level == "FULL",
        ),
        required_warnings=tuple(warnings),
        binding_constraints=tuple(constraints),
    )


def bounds_to_dict(bounds: EpistemicBounds) -> dict[str, Any]:
    """Serialize EpistemicBounds to a dictionary."""
    return {
        "max_confidence": bounds.max_confidence,
        "max_publishability": bounds.max_publishability,
        "can_rank": bounds.can_rank,
        "can_compare": bounds.can_compare,
        "can_publish_policy_claim": bounds.can_publish_policy_claim,
        "can_publish_composite": bounds.can_publish_composite,
        "can_publish_country_ordering": bounds.can_publish_country_ordering,
        "required_warnings": list(bounds.required_warnings),
        "binding_constraints": list(bounds.binding_constraints),
    }
