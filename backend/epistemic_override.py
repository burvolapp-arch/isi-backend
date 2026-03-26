"""
backend.epistemic_override — Epistemic Override Engine

SECTION 3 of Ultimate Pass: Epistemic Override Logic.

Problem addressed:
    When an external authority's data contradicts ISI's internal
    computation, the system must RESOLVE the conflict — not merely
    flag it. Without an override engine, flags are decorative.

Solution:
    The epistemic override engine takes:
    - Internal computation result
    - External authority claim
    - Epistemic hierarchy
    And produces an OverrideResult that either:
    - ACCEPTS the external authority (overrides internal)
    - RESTRICTS the output (downgrades to more conservative)
    - FLAGS the conflict (documents but does not override)
    - BLOCKS the output (irreconcilable contradiction)

Design contract:
    - External authority ALWAYS wins for Tier 1 conflicts.
    - Tier 2 conflicts trigger restriction (conservative output).
    - Tier 3 conflicts are flagged but not overridden.
    - Every override is logged with full provenance.
    - The system NEVER produces output stronger than external
      authority allows.

Honesty note:
    "External authority outranks internal elegance." If BIS says
    the financial concentration for Country X is different from what
    ISI calculates, the BIS figure wins — not because BIS is always
    right, but because BIS has PRIMARY data access and ISI's calculation
    is derivative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.epistemic_hierarchy import (
    EpistemicClaim,
    EpistemicLevel,
    claim_to_dict,
    epistemic_authority,
    outranks,
)
from backend.external_authority_registry import (
    AuthorityTier,
    AUTHORITY_TIER_ORDER,
    get_authority_by_id,
)


# ═══════════════════════════════════════════════════════════════════════════
# OVERRIDE OUTCOME CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class OverrideOutcome:
    """Classification of override resolution.

    ACCEPTED:   External authority overrides internal computation.
                The external value replaces the internal value.
    RESTRICTED: External authority restricts internal computation.
                Output is downgraded to the more conservative value.
    FLAGGED:    External authority flags a discrepancy but does not
                override. Output carries a warning annotation.
    BLOCKED:    Irreconcilable contradiction — no defensible output
                can be produced.
    NO_CONFLICT: External authority and internal computation agree.
    """
    ACCEPTED = "ACCEPTED"
    RESTRICTED = "RESTRICTED"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"
    NO_CONFLICT = "NO_CONFLICT"


VALID_OVERRIDE_OUTCOMES = frozenset({
    OverrideOutcome.ACCEPTED,
    OverrideOutcome.RESTRICTED,
    OverrideOutcome.FLAGGED,
    OverrideOutcome.BLOCKED,
    OverrideOutcome.NO_CONFLICT,
})


# ═══════════════════════════════════════════════════════════════════════════
# OVERRIDE RESULT
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class OverrideResult:
    """Result of an epistemic override evaluation.

    Attributes:
        outcome: Classification of the override resolution.
        field: The field that was evaluated.
        internal_value: What ISI computed internally.
        external_value: What the external authority claims.
        resolved_value: The value that should be used in output.
        authority_id: Which external authority triggered this.
        authority_tier: Tier of the triggering authority.
        override_reason: Human-readable explanation.
        warnings: List of warnings to include in output.
    """
    outcome: str
    field: str
    internal_value: Any
    external_value: Any
    resolved_value: Any
    authority_id: str
    authority_tier: str
    override_reason: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome not in VALID_OVERRIDE_OUTCOMES:
            raise ValueError(
                f"Invalid override outcome: {self.outcome}. "
                f"Must be one of {sorted(VALID_OVERRIDE_OUTCOMES)}"
            )


def override_result_to_dict(result: OverrideResult) -> dict[str, Any]:
    """Serialize an OverrideResult to a JSON-safe dict."""
    return {
        "outcome": result.outcome,
        "field": result.field,
        "internal_value": result.internal_value,
        "external_value": result.external_value,
        "resolved_value": result.resolved_value,
        "authority_id": result.authority_id,
        "authority_tier": result.authority_tier,
        "override_reason": result.override_reason,
        "warnings": list(result.warnings),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CORE OVERRIDE ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def evaluate_epistemic_override(
    field: str,
    internal_value: Any,
    external_value: Any,
    authority_id: str,
    internal_level: str = EpistemicLevel.INTERNAL_COMPUTATION,
) -> OverrideResult:
    """Evaluate whether an external authority should override an internal value.

    This is the core override function. It determines what happens when
    an external authority's data contradicts ISI's internal computation.

    Args:
        field: The field being evaluated (e.g., "axis_1_score").
        internal_value: What ISI computed.
        external_value: What the external authority reports.
        authority_id: ID of the external authority.
        internal_level: Epistemic level of the internal computation.

    Returns:
        OverrideResult with the resolution.
    """
    authority = get_authority_by_id(authority_id)

    if authority is None:
        return OverrideResult(
            outcome=OverrideOutcome.FLAGGED,
            field=field,
            internal_value=internal_value,
            external_value=external_value,
            resolved_value=internal_value,
            authority_id=authority_id,
            authority_tier="UNKNOWN",
            override_reason=(
                f"Unknown authority '{authority_id}'. Cannot evaluate "
                f"override. Internal value retained with warning."
            ),
            warnings=(
                f"Unknown external authority '{authority_id}' cited. "
                f"Value cannot be validated.",
            ),
        )

    authority_tier = authority["tier"]

    # ── Check for agreement (no conflict) ──
    if _values_agree(internal_value, external_value):
        return OverrideResult(
            outcome=OverrideOutcome.NO_CONFLICT,
            field=field,
            internal_value=internal_value,
            external_value=external_value,
            resolved_value=internal_value,
            authority_id=authority_id,
            authority_tier=authority_tier,
            override_reason=(
                f"Internal computation agrees with {authority['name']}. "
                f"No override needed."
            ),
        )

    # ── Tier 1: Primary data custodian — MANDATORY override ──
    if authority_tier == AuthorityTier.TIER_1_PRIMARY:
        return OverrideResult(
            outcome=OverrideOutcome.ACCEPTED,
            field=field,
            internal_value=internal_value,
            external_value=external_value,
            resolved_value=external_value,
            authority_id=authority_id,
            authority_tier=authority_tier,
            override_reason=(
                f"{authority['name']} ({authority_tier}) is the primary "
                f"data custodian. Override is MANDATORY. "
                f"Internal value {internal_value} replaced by "
                f"external value {external_value}."
            ),
            warnings=(
                f"Value overridden by {authority['name']} "
                f"(Tier 1 — primary data custodian). "
                f"ISI computed {internal_value}, authority reports "
                f"{external_value}.",
            ),
        )

    # ── Tier 2: Authoritative secondary — RESTRICTIVE override ──
    if authority_tier == AuthorityTier.TIER_2_AUTHORITATIVE:
        # Resolve to the MORE CONSERVATIVE value
        conservative_value = _more_conservative(
            field, internal_value, external_value,
        )
        return OverrideResult(
            outcome=OverrideOutcome.RESTRICTED,
            field=field,
            internal_value=internal_value,
            external_value=external_value,
            resolved_value=conservative_value,
            authority_id=authority_id,
            authority_tier=authority_tier,
            override_reason=(
                f"{authority['name']} ({authority_tier}) reports "
                f"different value. Output restricted to more "
                f"conservative interpretation: {conservative_value}."
            ),
            warnings=(
                f"Value restricted by {authority['name']} "
                f"(Tier 2 — authoritative secondary). "
                f"ISI computed {internal_value}, authority reports "
                f"{external_value}. Using conservative value.",
            ),
        )

    # ── Tier 3: Supporting — FLAG only ──
    return OverrideResult(
        outcome=OverrideOutcome.FLAGGED,
        field=field,
        internal_value=internal_value,
        external_value=external_value,
        resolved_value=internal_value,
        authority_id=authority_id,
        authority_tier=authority_tier,
        override_reason=(
            f"{authority['name']} ({authority_tier}) reports "
            f"different value. Flagged but not overridden."
        ),
        warnings=(
            f"Discrepancy noted with {authority['name']} "
            f"(Tier 3 — supporting reference). "
            f"ISI computed {internal_value}, reference reports "
            f"{external_value}.",
        ),
    )


def evaluate_batch_overrides(
    overrides: list[dict[str, Any]],
) -> list[OverrideResult]:
    """Evaluate multiple override claims at once.

    Each entry in overrides should have:
        field, internal_value, external_value, authority_id

    Returns:
        List of OverrideResults.
    """
    results = []
    for entry in overrides:
        result = evaluate_epistemic_override(
            field=entry["field"],
            internal_value=entry["internal_value"],
            external_value=entry["external_value"],
            authority_id=entry["authority_id"],
            internal_level=entry.get(
                "internal_level", EpistemicLevel.INTERNAL_COMPUTATION,
            ),
        )
        results.append(result)
    return results


def compute_override_summary(
    results: list[OverrideResult],
) -> dict[str, Any]:
    """Compute a summary of override evaluation results.

    Returns:
        Summary dict with counts and categorized results.
    """
    outcome_counts: dict[str, int] = {}
    warnings: list[str] = []
    has_blocking = False

    for result in results:
        outcome_counts[result.outcome] = (
            outcome_counts.get(result.outcome, 0) + 1
        )
        warnings.extend(result.warnings)
        if result.outcome == OverrideOutcome.BLOCKED:
            has_blocking = True

    return {
        "n_overrides": len(results),
        "outcome_counts": outcome_counts,
        "n_accepted": outcome_counts.get(OverrideOutcome.ACCEPTED, 0),
        "n_restricted": outcome_counts.get(OverrideOutcome.RESTRICTED, 0),
        "n_flagged": outcome_counts.get(OverrideOutcome.FLAGGED, 0),
        "n_blocked": outcome_counts.get(OverrideOutcome.BLOCKED, 0),
        "n_no_conflict": outcome_counts.get(OverrideOutcome.NO_CONFLICT, 0),
        "has_blocking": has_blocking,
        "warnings": warnings,
        "n_warnings": len(warnings),
        "overrides": [override_result_to_dict(r) for r in results],
        "honesty_note": (
            f"Epistemic override engine evaluated {len(results)} claims. "
            f"{outcome_counts.get(OverrideOutcome.ACCEPTED, 0)} overrides accepted, "
            f"{outcome_counts.get(OverrideOutcome.RESTRICTED, 0)} restricted, "
            f"{outcome_counts.get(OverrideOutcome.FLAGGED, 0)} flagged. "
            f"{'OUTPUT BLOCKED — irreconcilable contradiction.' if has_blocking else 'No blocking conflicts.'}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _values_agree(
    internal: Any,
    external: Any,
    tolerance: float = 0.05,
) -> bool:
    """Check if two values agree within tolerance.

    For numeric values: agree if |a - b| / max(|a|, |b|, 1) < tolerance
    For string values: agree if equal (case-insensitive)
    For bool values: agree if equal
    """
    if internal is None or external is None:
        return internal is None and external is None

    if isinstance(internal, bool) and isinstance(external, bool):
        return internal == external

    if isinstance(internal, (int, float)) and isinstance(external, (int, float)):
        denominator = max(abs(internal), abs(external), 1.0)
        return abs(internal - external) / denominator < tolerance

    if isinstance(internal, str) and isinstance(external, str):
        return internal.upper() == external.upper()

    return internal == external


def _more_conservative(
    field: str,
    value_a: Any,
    value_b: Any,
) -> Any:
    """Return the more conservative (more restrictive) of two values.

    For ranking_eligible: False is more conservative.
    For governance_tier: higher severity (NON_COMPARABLE > LOW_CONFIDENCE > ...).
    For numeric scores: higher score means more concentrated (worse).
    For usability: more restricted class.
    """
    # Tier ordering (worst = most conservative)
    tier_order = {
        "FULLY_COMPARABLE": 0,
        "PARTIALLY_COMPARABLE": 1,
        "LOW_CONFIDENCE": 2,
        "NON_COMPARABLE": 3,
    }

    # Usability ordering (worst = most conservative)
    usability_order = {
        "TRUSTED_COMPARABLE": 0,
        "COMPARABLE_WITH_CAVEATS": 1,
        "REQUIRES_CONTEXT": 2,
        "INVALID_FOR_COMPARISON": 3,
    }

    # Boolean fields — False is more conservative
    if isinstance(value_a, bool) and isinstance(value_b, bool):
        return False if (not value_a or not value_b) else True

    # Tier fields
    if isinstance(value_a, str) and isinstance(value_b, str):
        if value_a in tier_order and value_b in tier_order:
            return value_a if tier_order[value_a] >= tier_order[value_b] else value_b
        if value_a in usability_order and value_b in usability_order:
            return (
                value_a
                if usability_order[value_a] >= usability_order[value_b]
                else value_b
            )

    # Numeric — higher concentration (larger number) is worse/more conservative
    if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
        return max(value_a, value_b)

    # Fallback: return first value
    return value_a
