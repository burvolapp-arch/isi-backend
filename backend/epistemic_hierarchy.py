"""
backend.epistemic_hierarchy — Epistemic Hierarchy Model

SECTION 1 of Ultimate Pass: Epistemic Override Layer.

Problem addressed:
    The ISI system produces values from multiple sources — internal
    computation, structural benchmarks, external authority data, and
    derived inferences. Without an explicit epistemic hierarchy, the
    system cannot determine WHICH source should prevail when they disagree.

Solution:
    A formal epistemic hierarchy that ranks every claim by its source.
    External authority outranks internal elegance. Structural constraints
    outrank statistical computation. Measurement always yields to
    calibration from authoritative bodies.

Design contract:
    - Every value in the system has an epistemic level.
    - Higher-level claims override lower-level claims.
    - The hierarchy is fixed — no runtime reconfiguration.
    - Claims must carry their epistemic provenance.
    - NEVER allow a derived inference to override an external authority.

Priority order (from HIGHEST to LOWEST epistemic authority):
    1. EXTERNAL_AUTHORITY — data from recognized international bodies
       (BIS, IMF, IEA, Eurostat, OECD, SIPRI, USGS, EU CRM)
    2. STRUCTURAL_BENCHMARK — hard structural constraints that cannot
       be overridden by data (e.g., EU membership, geographic facts)
    3. INTERNAL_GOVERNANCE — ISI's own governance assessment (tiers,
       eligibility, comparability) based on data quality evaluation
    4. INTERNAL_COMPUTATION — ISI's computed values (axis scores,
       composite, HHI concentrations)
    5. DERIVED_INFERENCE — anything inferred from computed values
       (rankings, classifications, scenario simulations)

Honesty note:
    This hierarchy enforces epistemic humility. ISI's own computations
    are at level 4 — they can be overridden by governance (level 3),
    structural constraints (level 2), and external authority (level 1).
    No internal computation may contradict external authority without
    explicit conflict documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# EPISTEMIC LEVEL — ordered from HIGHEST to LOWEST authority
# ═══════════════════════════════════════════════════════════════════════════

class EpistemicLevel:
    """Classification of epistemic authority.

    Ordered from HIGHEST authority (index 0) to LOWEST (index 4).
    Higher authority ALWAYS overrides lower authority in conflicts.
    """
    EXTERNAL_AUTHORITY = "EXTERNAL_AUTHORITY"
    STRUCTURAL_BENCHMARK = "STRUCTURAL_BENCHMARK"
    INTERNAL_GOVERNANCE = "INTERNAL_GOVERNANCE"
    INTERNAL_COMPUTATION = "INTERNAL_COMPUTATION"
    DERIVED_INFERENCE = "DERIVED_INFERENCE"


# Authority ordering — lower index = higher authority
EPISTEMIC_ORDER: dict[str, int] = {
    EpistemicLevel.EXTERNAL_AUTHORITY: 0,
    EpistemicLevel.STRUCTURAL_BENCHMARK: 1,
    EpistemicLevel.INTERNAL_GOVERNANCE: 2,
    EpistemicLevel.INTERNAL_COMPUTATION: 3,
    EpistemicLevel.DERIVED_INFERENCE: 4,
}

VALID_EPISTEMIC_LEVELS = frozenset(EPISTEMIC_ORDER.keys())

# Human-readable descriptions
EPISTEMIC_DESCRIPTIONS: dict[str, str] = {
    EpistemicLevel.EXTERNAL_AUTHORITY: (
        "Data from recognized international bodies (BIS, IMF, IEA, "
        "Eurostat, OECD, SIPRI, USGS, EU CRM). Highest epistemic "
        "authority. Internal computation must defer."
    ),
    EpistemicLevel.STRUCTURAL_BENCHMARK: (
        "Hard structural constraints (EU membership, geographic facts, "
        "commodity classifications). Cannot be overridden by data."
    ),
    EpistemicLevel.INTERNAL_GOVERNANCE: (
        "ISI's data quality assessment: governance tiers, eligibility, "
        "comparability. Based on internal evaluation of data integrity."
    ),
    EpistemicLevel.INTERNAL_COMPUTATION: (
        "ISI's computed values: axis scores, composite indices, HHI "
        "concentrations. These are the system's analytical outputs."
    ),
    EpistemicLevel.DERIVED_INFERENCE: (
        "Anything inferred from computed values: rankings, "
        "classifications, scenario simulations, trend extrapolations. "
        "Lowest epistemic authority."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# EPISTEMIC CLAIM — carries provenance metadata
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EpistemicClaim:
    """A single claim with epistemic provenance.

    Every value in the system should be traceable to an EpistemicClaim
    that records WHO says it, at WHAT level, and with WHAT confidence.

    Attributes:
        field: The field this claim is about (e.g., "governance_tier").
        value: The claimed value.
        level: The epistemic level of the source.
        source: Human-readable source identifier.
        source_id: Machine-readable source identifier.
        confidence: Source confidence (0.0 to 1.0). None if not applicable.
        justification: Why this claim is at this level.
    """
    field: str
    value: Any
    level: str
    source: str
    source_id: str
    confidence: float | None = None
    justification: str = ""

    def __post_init__(self) -> None:
        if self.level not in VALID_EPISTEMIC_LEVELS:
            raise ValueError(
                f"Invalid epistemic level: {self.level}. "
                f"Must be one of {sorted(VALID_EPISTEMIC_LEVELS)}"
            )
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Confidence must be between 0.0 and 1.0, got {self.confidence}"
            )


def epistemic_authority(level: str) -> int:
    """Return the authority rank of an epistemic level.

    Lower number = higher authority.
    Returns 999 for unknown levels (lowest possible authority).
    """
    return EPISTEMIC_ORDER.get(level, 999)


def outranks(level_a: str, level_b: str) -> bool:
    """True if level_a has strictly higher epistemic authority than level_b.

    Higher authority = lower index in EPISTEMIC_ORDER.
    """
    return epistemic_authority(level_a) < epistemic_authority(level_b)


def resolve_conflict(
    claim_a: EpistemicClaim,
    claim_b: EpistemicClaim,
) -> tuple[EpistemicClaim, EpistemicClaim, str]:
    """Resolve a conflict between two claims by epistemic authority.

    The claim with higher epistemic authority wins.
    If both are at the same level, the more conservative claim wins
    (the one that restricts more).

    Returns:
        (winner, loser, resolution_reason)
    """
    auth_a = epistemic_authority(claim_a.level)
    auth_b = epistemic_authority(claim_b.level)

    if auth_a < auth_b:
        return (
            claim_a,
            claim_b,
            f"Claim from {claim_a.source} ({claim_a.level}) outranks "
            f"claim from {claim_b.source} ({claim_b.level}). "
            f"Higher epistemic authority prevails.",
        )
    elif auth_b < auth_a:
        return (
            claim_b,
            claim_a,
            f"Claim from {claim_b.source} ({claim_b.level}) outranks "
            f"claim from {claim_a.source} ({claim_a.level}). "
            f"Higher epistemic authority prevails.",
        )
    else:
        # Same level — more conservative (more restrictive) wins
        # Convention: alphabetically later values are more restrictive
        # This is a heuristic; real resolution depends on domain semantics
        return (
            claim_a,
            claim_b,
            f"Both claims at same level ({claim_a.level}). "
            f"Claim from {claim_a.source} retained (first-registered). "
            f"Same-level conflicts should be resolved by domain logic.",
        )


def build_claim(
    field: str,
    value: Any,
    level: str,
    source: str,
    source_id: str = "",
    confidence: float | None = None,
    justification: str = "",
) -> EpistemicClaim:
    """Factory function for creating epistemic claims.

    Convenience wrapper that validates level and confidence.
    """
    return EpistemicClaim(
        field=field,
        value=value,
        level=level,
        source=source,
        source_id=source_id or source.lower().replace(" ", "_"),
        confidence=confidence,
        justification=justification,
    )


def claim_to_dict(claim: EpistemicClaim) -> dict[str, Any]:
    """Serialize an epistemic claim to a JSON-safe dict."""
    return {
        "field": claim.field,
        "value": claim.value,
        "level": claim.level,
        "source": claim.source,
        "source_id": claim.source_id,
        "confidence": claim.confidence,
        "justification": claim.justification,
        "authority_rank": epistemic_authority(claim.level),
    }


def get_hierarchy() -> list[dict[str, Any]]:
    """Return the full epistemic hierarchy for documentation/export."""
    return [
        {
            "level": level,
            "authority_rank": rank,
            "description": EPISTEMIC_DESCRIPTIONS.get(level, ""),
        }
        for level, rank in sorted(EPISTEMIC_ORDER.items(), key=lambda x: x[1])
    ]
