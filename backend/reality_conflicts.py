"""
backend.reality_conflicts — Reality Conflict Detection Engine

SECTION 3 of Institutionalization Pass.

Problem addressed:
    If governance says 'FULLY_COMPARABLE' but external alignment says
    'DIVERGENT' — that is a REALITY CONFLICT. Not a soft flag. Not a
    log entry. A STRUCTURAL entry in the country output.

    The system can be internally consistent (all invariants pass) while
    being externally wrong (reality contradicts the classification).
    This module detects those contradictions and produces hard,
    machine-readable conflict records.

Conflict types:
    GOVERNANCE_ALIGNMENT_MISMATCH:
        Governance says high trust but alignment says divergent
        (or vice versa — governance says non-comparable but alignment
        is strongly confirmed).

    CONFIDENCE_ALIGNMENT_MISMATCH:
        High mean axis confidence but external alignment diverges.

    USABILITY_ALIGNMENT_MISMATCH:
        Decision usability says TRUSTED_COMPARABLE but empirical
        alignment says EMPIRICALLY_CONTRADICTED.

    RANKING_ELIGIBILITY_DIVERGENCE:
        Country is ranking-eligible but externally divergent.

Each conflict includes:
    - conflict_id: unique identifier
    - conflict_type: classification
    - severity: WARNING / ERROR / CRITICAL
    - internal_state: what ISI says
    - external_state: what reality says
    - resolution_guidance: what a consumer should do

Design contract:
    - Reality conflicts are STRUCTURAL entries in country JSON.
    - They are NOT suppressible by configuration.
    - They are produced deterministically from governance + alignment data.
    - An empty reality_conflicts list is a POSITIVE signal — it means
      internal state and external evidence are consistent.

Honesty note:
    A conflict does NOT necessarily mean ISI is wrong. It means
    ISI's internal classification is INCONSISTENT with external
    evidence. Both explanations are reported:
    (1) ISI may have a measurement problem.
    (2) External benchmarks may measure a different construct.
    The consumer must decide which interpretation applies.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT SEVERITY
# ═══════════════════════════════════════════════════════════════════════════

class ConflictSeverity:
    """Severity levels for reality conflicts."""
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


VALID_CONFLICT_SEVERITIES = frozenset({
    ConflictSeverity.WARNING,
    ConflictSeverity.ERROR,
    ConflictSeverity.CRITICAL,
})


# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT TYPE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class ConflictType:
    """Classification of reality conflict types."""
    GOVERNANCE_ALIGNMENT_MISMATCH = "GOVERNANCE_ALIGNMENT_MISMATCH"
    CONFIDENCE_ALIGNMENT_MISMATCH = "CONFIDENCE_ALIGNMENT_MISMATCH"
    USABILITY_ALIGNMENT_MISMATCH = "USABILITY_ALIGNMENT_MISMATCH"
    RANKING_ELIGIBILITY_DIVERGENCE = "RANKING_ELIGIBILITY_DIVERGENCE"


VALID_CONFLICT_TYPES = frozenset({
    ConflictType.GOVERNANCE_ALIGNMENT_MISMATCH,
    ConflictType.CONFIDENCE_ALIGNMENT_MISMATCH,
    ConflictType.USABILITY_ALIGNMENT_MISMATCH,
    ConflictType.RANKING_ELIGIBILITY_DIVERGENCE,
})


# ═══════════════════════════════════════════════════════════════════════════
# GOVERNANCE TIER TRUST ORDERING
# ═══════════════════════════════════════════════════════════════════════════

# Maps governance tiers to a trust level for comparison logic.
# Higher number = more trust.
_GOVERNANCE_TRUST_ORDER = {
    "FULLY_COMPARABLE": 4,
    "PARTIALLY_COMPARABLE": 3,
    "LOW_CONFIDENCE": 2,
    "NON_COMPARABLE": 1,
}

# Alignment classes mapped to trust-like ordering.
_ALIGNMENT_TRUST_ORDER = {
    "STRONGLY_ALIGNED": 4,
    "WEAKLY_ALIGNED": 3,
    "DIVERGENT": 1,
    "NO_DATA": 0,
    "STRUCTURALLY_INCOMPARABLE": 0,
}

# Threshold: if governance trust and alignment trust differ by more than
# this, it's a conflict.
_MISMATCH_THRESHOLD = 2


# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT CONSTRUCTOR
# ═══════════════════════════════════════════════════════════════════════════

def _conflict(
    conflict_id: str,
    conflict_type: str,
    severity: str,
    internal_state: dict[str, Any],
    external_state: dict[str, Any],
    explanation: str,
    resolution_guidance: str,
) -> dict[str, Any]:
    """Construct a canonical reality conflict record."""
    return {
        "conflict_id": conflict_id,
        "conflict_type": conflict_type,
        "severity": severity,
        "internal_state": internal_state,
        "external_state": external_state,
        "explanation": explanation,
        "resolution_guidance": resolution_guidance,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CORE DETECTION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def detect_governance_alignment_mismatch(
    country: str,
    governance_tier: str,
    overall_alignment: str,
    n_axes_compared: int,
) -> list[dict[str, Any]]:
    """Detect when governance tier contradicts external alignment.

    CRITICAL: FULLY_COMPARABLE + DIVERGENT
    ERROR:    PARTIALLY_COMPARABLE + DIVERGENT
    WARNING:  NON_COMPARABLE + STRONGLY_ALIGNED (inverse conflict)

    Args:
        country: ISO-2 code.
        governance_tier: From governance result.
        overall_alignment: From alignment result.
        n_axes_compared: Number of axes with alignment data.

    Returns:
        List of conflict records.
    """
    conflicts: list[dict[str, Any]] = []

    if n_axes_compared == 0:
        # No alignment data → no conflict detectable
        return conflicts

    gov_trust = _GOVERNANCE_TRUST_ORDER.get(governance_tier, 0)
    align_trust = _ALIGNMENT_TRUST_ORDER.get(overall_alignment, 0)

    # Case 1: High governance trust + low alignment = system claims
    # trustworthiness that reality contradicts
    if governance_tier == "FULLY_COMPARABLE" and overall_alignment == "DIVERGENT":
        conflicts.append(_conflict(
            conflict_id=f"RC-GAM-CRIT-{country}",
            conflict_type=ConflictType.GOVERNANCE_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.CRITICAL,
            internal_state={
                "governance_tier": governance_tier,
                "trust_level": gov_trust,
            },
            external_state={
                "overall_alignment": overall_alignment,
                "trust_level": align_trust,
                "n_axes_compared": n_axes_compared,
            },
            explanation=(
                f"Country {country} is classified as FULLY_COMPARABLE "
                f"(highest governance tier) but external benchmarks show "
                f"DIVERGENT alignment on {n_axes_compared} compared axes. "
                f"Internal consistency does not match external reality."
            ),
            resolution_guidance=(
                "INVESTIGATE: Either (1) ISI has a measurement problem on "
                "this country, (2) external benchmarks measure a different "
                "construct, or (3) the governance tier determination is too "
                "permissive. Do NOT use this country's ISI output for policy "
                "decisions without resolving this conflict."
            ),
        ))
    elif governance_tier == "PARTIALLY_COMPARABLE" and overall_alignment == "DIVERGENT":
        conflicts.append(_conflict(
            conflict_id=f"RC-GAM-ERR-{country}",
            conflict_type=ConflictType.GOVERNANCE_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.ERROR,
            internal_state={
                "governance_tier": governance_tier,
                "trust_level": gov_trust,
            },
            external_state={
                "overall_alignment": overall_alignment,
                "trust_level": align_trust,
                "n_axes_compared": n_axes_compared,
            },
            explanation=(
                f"Country {country} is PARTIALLY_COMPARABLE but external "
                f"benchmarks show DIVERGENT alignment. The partial-trust "
                f"classification is inconsistent with observed divergence."
            ),
            resolution_guidance=(
                "REVIEW: This country may need governance tier downgrade. "
                "Check whether divergence stems from construct differences "
                "or actual ISI measurement issues."
            ),
        ))

    # Case 2: Low governance trust + high alignment = system is
    # undervaluing a country that reality supports
    if governance_tier == "NON_COMPARABLE" and overall_alignment == "STRONGLY_ALIGNED":
        conflicts.append(_conflict(
            conflict_id=f"RC-GAM-WARN-{country}",
            conflict_type=ConflictType.GOVERNANCE_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.WARNING,
            internal_state={
                "governance_tier": governance_tier,
                "trust_level": gov_trust,
            },
            external_state={
                "overall_alignment": overall_alignment,
                "trust_level": align_trust,
                "n_axes_compared": n_axes_compared,
            },
            explanation=(
                f"Country {country} is NON_COMPARABLE but external "
                f"benchmarks show STRONG alignment. The governance "
                f"tier may be overly conservative — ISI output appears "
                f"to track reality despite structural limitations."
            ),
            resolution_guidance=(
                "REVIEW: Governance tier constraints (data quality, "
                "axis coverage) may be too strict for this country. "
                "Consider whether partial output is more useful than "
                "exclusion."
            ),
        ))

    return conflicts


def detect_confidence_alignment_mismatch(
    country: str,
    mean_axis_confidence: float,
    overall_alignment: str,
    n_axes_compared: int,
) -> list[dict[str, Any]]:
    """Detect when high internal confidence contradicts external alignment.

    A country with mean_axis_confidence >= 0.7 showing DIVERGENT
    alignment means the system is confident in outputs that
    external evidence contradicts.

    Args:
        country: ISO-2 code.
        mean_axis_confidence: From governance result.
        overall_alignment: From alignment result.
        n_axes_compared: Number of compared axes.

    Returns:
        List of conflict records.
    """
    conflicts: list[dict[str, Any]] = []

    if n_axes_compared == 0:
        return conflicts

    # High confidence + divergent alignment → ERROR
    if mean_axis_confidence >= 0.7 and overall_alignment == "DIVERGENT":
        conflicts.append(_conflict(
            conflict_id=f"RC-CAM-ERR-{country}",
            conflict_type=ConflictType.CONFIDENCE_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.ERROR,
            internal_state={
                "mean_axis_confidence": mean_axis_confidence,
            },
            external_state={
                "overall_alignment": overall_alignment,
                "n_axes_compared": n_axes_compared,
            },
            explanation=(
                f"Country {country} has high mean axis confidence "
                f"({mean_axis_confidence:.2f}) but external benchmarks "
                f"show DIVERGENT alignment. The system is confident "
                f"in outputs that reality contradicts."
            ),
            resolution_guidance=(
                "INVESTIGATE: Confidence is data-quality-based, alignment "
                "is empirical. High confidence + divergence means data "
                "quality is fine but the measured construct may not match "
                "external expectations. Check axis-level divergence."
            ),
        ))

    # Very low confidence + strong alignment → WARNING (unusual but worth noting)
    if mean_axis_confidence < 0.3 and overall_alignment == "STRONGLY_ALIGNED":
        conflicts.append(_conflict(
            conflict_id=f"RC-CAM-WARN-{country}",
            conflict_type=ConflictType.CONFIDENCE_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.WARNING,
            internal_state={
                "mean_axis_confidence": mean_axis_confidence,
            },
            external_state={
                "overall_alignment": overall_alignment,
                "n_axes_compared": n_axes_compared,
            },
            explanation=(
                f"Country {country} has low confidence "
                f"({mean_axis_confidence:.2f}) but strong external "
                f"alignment. The ISI output aligns with reality "
                f"despite internal data quality concerns."
            ),
            resolution_guidance=(
                "NOTE: Low confidence may be overly conservative. "
                "If external alignment is strong, consider whether "
                "data quality flags are too strict."
            ),
        ))

    return conflicts


def detect_usability_alignment_mismatch(
    country: str,
    decision_usability_class: str | None,
    empirical_alignment_class: str | None,
) -> list[dict[str, Any]]:
    """Detect when decision usability contradicts empirical alignment.

    TRUSTED_COMPARABLE + EMPIRICALLY_CONTRADICTED is a critical conflict.
    INVALID_FOR_COMPARISON + EMPIRICALLY_GROUNDED is a warning.

    Args:
        country: ISO-2 code.
        decision_usability_class: From classify_decision_usability().
        empirical_alignment_class: From classify_empirical_alignment().

    Returns:
        List of conflict records.
    """
    conflicts: list[dict[str, Any]] = []

    if decision_usability_class is None or empirical_alignment_class is None:
        return conflicts

    # Highest trust + contradicted by reality → CRITICAL
    if (decision_usability_class == "TRUSTED_COMPARABLE"
            and empirical_alignment_class == "EMPIRICALLY_CONTRADICTED"):
        conflicts.append(_conflict(
            conflict_id=f"RC-UAM-CRIT-{country}",
            conflict_type=ConflictType.USABILITY_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.CRITICAL,
            internal_state={
                "decision_usability_class": decision_usability_class,
            },
            external_state={
                "empirical_alignment_class": empirical_alignment_class,
            },
            explanation=(
                f"Country {country} is classified as TRUSTED_COMPARABLE "
                f"(highest decision usability) but empirically "
                f"CONTRADICTED. The system is signaling maximum trust "
                f"in output that external data contradicts."
            ),
            resolution_guidance=(
                "CRITICAL: This is the most severe reality conflict. "
                "The country's output MUST NOT be treated as trusted "
                "until the empirical contradiction is resolved."
            ),
        ))

    # High usability + weak alignment → ERROR
    if (decision_usability_class == "TRUSTED_COMPARABLE"
            and empirical_alignment_class == "EMPIRICALLY_WEAK"):
        conflicts.append(_conflict(
            conflict_id=f"RC-UAM-ERR-{country}",
            conflict_type=ConflictType.USABILITY_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.ERROR,
            internal_state={
                "decision_usability_class": decision_usability_class,
            },
            external_state={
                "empirical_alignment_class": empirical_alignment_class,
            },
            explanation=(
                f"Country {country} is TRUSTED_COMPARABLE but empirical "
                f"alignment is WEAK. Trust classification lacks empirical "
                f"support."
            ),
            resolution_guidance=(
                "REVIEW: TRUSTED_COMPARABLE requires empirical grounding. "
                "Without strong alignment, the trust classification may "
                "be structurally valid but empirically unsupported."
            ),
        ))

    # Inverse: Low usability but strong empirical grounding → WARNING
    if (decision_usability_class == "INVALID_FOR_COMPARISON"
            and empirical_alignment_class == "EMPIRICALLY_GROUNDED"):
        conflicts.append(_conflict(
            conflict_id=f"RC-UAM-WARN-{country}",
            conflict_type=ConflictType.USABILITY_ALIGNMENT_MISMATCH,
            severity=ConflictSeverity.WARNING,
            internal_state={
                "decision_usability_class": decision_usability_class,
            },
            external_state={
                "empirical_alignment_class": empirical_alignment_class,
            },
            explanation=(
                f"Country {country} is INVALID_FOR_COMPARISON but "
                f"empirically GROUNDED. Structural issues prevent "
                f"comparison, but where data exists it aligns with "
                f"reality."
            ),
            resolution_guidance=(
                "NOTE: The structural invalidity ruling may be too "
                "conservative. Consider whether partial directional "
                "insight is safe to extract."
            ),
        ))

    return conflicts


def detect_ranking_eligibility_divergence(
    country: str,
    ranking_eligible: bool,
    overall_alignment: str,
    n_axes_compared: int,
) -> list[dict[str, Any]]:
    """Detect when a ranking-eligible country has divergent alignment.

    If a country is eligible for ranking but external benchmarks
    show divergence, the ranking is structurally valid but
    empirically questionable.

    Args:
        country: ISO-2 code.
        ranking_eligible: From governance result.
        overall_alignment: From alignment result.
        n_axes_compared: Number of compared axes.

    Returns:
        List of conflict records.
    """
    conflicts: list[dict[str, Any]] = []

    if n_axes_compared == 0:
        return conflicts

    if ranking_eligible and overall_alignment == "DIVERGENT":
        conflicts.append(_conflict(
            conflict_id=f"RC-RED-ERR-{country}",
            conflict_type=ConflictType.RANKING_ELIGIBILITY_DIVERGENCE,
            severity=ConflictSeverity.ERROR,
            internal_state={
                "ranking_eligible": ranking_eligible,
            },
            external_state={
                "overall_alignment": overall_alignment,
                "n_axes_compared": n_axes_compared,
            },
            explanation=(
                f"Country {country} is ranking-eligible but external "
                f"benchmarks show DIVERGENT alignment on {n_axes_compared} "
                f"axes. The ranking position is structurally defensible "
                f"but empirically questionable."
            ),
            resolution_guidance=(
                "FLAG: Include an explicit caveat on this country's "
                "ranking position. The rank may be structurally correct "
                "but the underlying scores diverge from external "
                "reference points."
            ),
        ))

    return conflicts


# ═══════════════════════════════════════════════════════════════════════════
# MAIN DETECTION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def detect_reality_conflicts(
    country: str,
    governance_result: dict[str, Any],
    alignment_result: dict[str, Any] | None = None,
    decision_usability: dict[str, Any] | None = None,
    empirical_alignment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all reality conflict checks for a country.

    This is the main entry point. It compares ISI's internal
    classification state against external alignment evidence
    and produces a structured conflict block for the country JSON.

    Args:
        country: ISO-2 code.
        governance_result: From assess_country_governance().
        alignment_result: From assess_country_alignment().
            None if no external validation was performed.
        decision_usability: From classify_decision_usability().
            None if not computed.
        empirical_alignment: From classify_empirical_alignment().
            None if not computed.

    Returns:
        Reality conflict block for inclusion in country JSON.
    """
    all_conflicts: list[dict[str, Any]] = []

    governance_tier = governance_result.get("governance_tier", "NON_COMPARABLE")
    mean_confidence = governance_result.get("mean_axis_confidence", 0.0)
    ranking_eligible = governance_result.get("ranking_eligible", False)

    # Extract alignment data
    if alignment_result is not None:
        overall_alignment = alignment_result.get("overall_alignment", "NO_DATA")
        n_axes_compared = alignment_result.get("n_axes_compared", 0)
    else:
        overall_alignment = "NO_DATA"
        n_axes_compared = 0

    # 1. Governance vs Alignment
    all_conflicts.extend(detect_governance_alignment_mismatch(
        country, governance_tier, overall_alignment, n_axes_compared,
    ))

    # 2. Confidence vs Alignment
    all_conflicts.extend(detect_confidence_alignment_mismatch(
        country, mean_confidence, overall_alignment, n_axes_compared,
    ))

    # 3. Usability vs Empirical Alignment
    du_class = None
    if decision_usability is not None:
        du_class = decision_usability.get("decision_usability_class")

    ea_class = None
    if empirical_alignment is not None:
        ea_class = empirical_alignment.get("empirical_class")

    all_conflicts.extend(detect_usability_alignment_mismatch(
        country, du_class, ea_class,
    ))

    # 4. Ranking Eligibility vs Divergence
    all_conflicts.extend(detect_ranking_eligibility_divergence(
        country, ranking_eligible, overall_alignment, n_axes_compared,
    ))

    # Severity summary
    n_warning = sum(
        1 for c in all_conflicts if c["severity"] == ConflictSeverity.WARNING
    )
    n_error = sum(
        1 for c in all_conflicts if c["severity"] == ConflictSeverity.ERROR
    )
    n_critical = sum(
        1 for c in all_conflicts if c["severity"] == ConflictSeverity.CRITICAL
    )

    return {
        "country": country,
        "n_conflicts": len(all_conflicts),
        "n_warnings": n_warning,
        "n_errors": n_error,
        "n_critical": n_critical,
        "has_critical": n_critical > 0,
        "conflicts": all_conflicts,
        "interpretation": _build_interpretation(
            country, len(all_conflicts), n_critical, n_error, n_warning,
        ),
        "honesty_note": (
            "Reality conflicts detect INCONSISTENCY between ISI's "
            "internal classification and external evidence. A conflict "
            "does NOT automatically mean ISI is wrong — it means the "
            "internal state and external evidence disagree. Both "
            "explanations (ISI error vs construct difference) are valid "
            "and must be investigated."
        ),
    }


def _build_interpretation(
    country: str,
    n_total: int,
    n_critical: int,
    n_error: int,
    n_warning: int,
) -> str:
    """Build human-readable interpretation of reality conflicts."""
    if n_total == 0:
        return (
            f"Country {country}: No reality conflicts detected. "
            f"Internal classification is consistent with external "
            f"evidence (or no external evidence is available)."
        )
    if n_critical > 0:
        return (
            f"Country {country}: {n_total} reality conflict(s) "
            f"detected including {n_critical} CRITICAL. ISI's internal "
            f"classification CONTRADICTS external evidence. "
            f"Output MUST NOT be used without resolving conflicts."
        )
    if n_error > 0:
        return (
            f"Country {country}: {n_total} reality conflict(s) "
            f"detected including {n_error} ERROR. Internal state is "
            f"inconsistent with external evidence. Review required."
        )
    return (
        f"Country {country}: {n_total} reality conflict(s) detected "
        f"({n_warning} warnings). Minor inconsistencies between "
        f"internal classification and external evidence."
    )
