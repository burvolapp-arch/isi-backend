"""
backend.authority_conflicts — Authority Conflict Resolution Engine

SECTION 8 of Ultimate Pass: Authority Conflict Handling.

Problem addressed:
    Multiple external authorities may cover the same ISI axis. When
    they disagree (e.g., BIS vs IMF on financial concentration),
    the system must resolve the conflict explicitly — not silently
    pick one.

Solution:
    The authority conflicts engine:
    1. Detects when multiple authorities disagree about the same field.
    2. Resolves conflicts using authority tier hierarchy.
    3. Documents every conflict and its resolution.
    4. Produces warnings when authorities at the same tier disagree.

Design contract:
    - Higher-tier authority always wins in cross-tier conflicts.
    - Same-tier conflicts produce explicit warnings and use the
      MORE CONSERVATIVE value.
    - Every conflict is logged with full provenance.
    - Unresolvable conflicts (same tier, same authority type)
      trigger output restriction.

Honesty note:
    Authority conflicts are NOT errors — they indicate genuine
    measurement divergence between recognized bodies. The system's
    job is to make the conflict VISIBLE and resolve conservatively.
"""

from __future__ import annotations

from typing import Any

from backend.external_authority_registry import (
    AUTHORITY_TIER_ORDER,
    AuthorityTier,
    get_authority_by_id,
)


# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT SEVERITY
# ═══════════════════════════════════════════════════════════════════════════

class ConflictSeverity:
    """Severity of an authority conflict."""
    INFO = "INFO"           # Minor disagreement, same direction
    WARNING = "WARNING"     # Significant disagreement
    ERROR = "ERROR"         # Major disagreement, may affect output
    CRITICAL = "CRITICAL"   # Irreconcilable, must restrict output


VALID_CONFLICT_SEVERITIES = frozenset({
    ConflictSeverity.INFO,
    ConflictSeverity.WARNING,
    ConflictSeverity.ERROR,
    ConflictSeverity.CRITICAL,
})


# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT DETECTION AND RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def detect_authority_conflicts(
    authority_claims: list[dict[str, Any]],
) -> dict[str, Any]:
    """Detect and resolve conflicts among authority claims.

    Takes a list of claims from different authorities about the same
    field(s), detects disagreements, and resolves them.

    Each claim should have:
        authority_id: str
        field: str
        value: Any

    Args:
        authority_claims: List of authority claim dicts.

    Returns:
        Conflict resolution result with detected conflicts,
        resolutions, and output restrictions.
    """
    if not authority_claims:
        return {
            "n_claims": 0,
            "n_conflicts": 0,
            "conflicts": [],
            "resolutions": [],
            "has_critical": False,
            "output_restricted": False,
            "warnings": [],
            "n_warnings": 0,
            "honesty_note": (
                "Authority conflict engine processed 0 claims, "
                "detected 0 conflicts. No critical conflicts."
            ),
        }

    # Group claims by field
    claims_by_field: dict[str, list[dict[str, Any]]] = {}
    for claim in authority_claims:
        field = claim.get("field", "unknown")
        if field not in claims_by_field:
            claims_by_field[field] = []
        claims_by_field[field].append(claim)

    conflicts: list[dict[str, Any]] = []
    resolutions: list[dict[str, Any]] = []
    warnings: list[str] = []
    has_critical = False
    output_restricted = False

    for field, field_claims in claims_by_field.items():
        if len(field_claims) < 2:
            continue

        # Compare all pairs
        for i in range(len(field_claims)):
            for j in range(i + 1, len(field_claims)):
                claim_a = field_claims[i]
                claim_b = field_claims[j]

                if _values_agree(claim_a.get("value"), claim_b.get("value")):
                    continue

                # Conflict detected
                auth_a = get_authority_by_id(claim_a.get("authority_id", ""))
                auth_b = get_authority_by_id(claim_b.get("authority_id", ""))

                tier_a = auth_a["tier"] if auth_a else "UNKNOWN"
                tier_b = auth_b["tier"] if auth_b else "UNKNOWN"
                name_a = auth_a["name"] if auth_a else claim_a.get("authority_id", "unknown")
                name_b = auth_b["name"] if auth_b else claim_b.get("authority_id", "unknown")

                severity = _assess_conflict_severity(
                    tier_a, tier_b,
                    claim_a.get("value"), claim_b.get("value"),
                )

                if severity == ConflictSeverity.CRITICAL:
                    has_critical = True
                    output_restricted = True

                conflict_record = {
                    "field": field,
                    "authority_a": name_a,
                    "authority_a_id": claim_a.get("authority_id"),
                    "authority_a_tier": tier_a,
                    "value_a": claim_a.get("value"),
                    "authority_b": name_b,
                    "authority_b_id": claim_b.get("authority_id"),
                    "authority_b_tier": tier_b,
                    "value_b": claim_b.get("value"),
                    "severity": severity,
                }
                conflicts.append(conflict_record)

                # Resolve
                resolution = _resolve_authority_conflict(
                    field, claim_a, claim_b, tier_a, tier_b, name_a, name_b,
                )
                resolutions.append(resolution)
                if resolution.get("warning"):
                    warnings.append(resolution["warning"])

    return {
        "n_claims": len(authority_claims),
        "n_conflicts": len(conflicts),
        "conflicts": conflicts,
        "resolutions": resolutions,
        "has_critical": has_critical,
        "output_restricted": output_restricted,
        "warnings": warnings,
        "n_warnings": len(warnings),
        "honesty_note": (
            f"Authority conflict engine processed {len(authority_claims)} claims, "
            f"detected {len(conflicts)} conflicts. "
            f"{'CRITICAL conflicts detected — output restricted.' if has_critical else 'No critical conflicts.'}"
        ),
    }


def _resolve_authority_conflict(
    field: str,
    claim_a: dict[str, Any],
    claim_b: dict[str, Any],
    tier_a: str,
    tier_b: str,
    name_a: str,
    name_b: str,
) -> dict[str, Any]:
    """Resolve a single authority conflict."""
    order_a = AUTHORITY_TIER_ORDER.get(tier_a, 999)
    order_b = AUTHORITY_TIER_ORDER.get(tier_b, 999)

    if order_a < order_b:
        # A has higher authority
        return {
            "field": field,
            "resolved_value": claim_a.get("value"),
            "resolved_by": name_a,
            "reason": (
                f"{name_a} ({tier_a}) outranks {name_b} ({tier_b}). "
                f"Higher-tier authority prevails."
            ),
            "warning": (
                f"Authority conflict on {field}: {name_a} ({tier_a}) says "
                f"{claim_a.get('value')}, {name_b} ({tier_b}) says "
                f"{claim_b.get('value')}. Resolved to {claim_a.get('value')}."
            ),
        }
    elif order_b < order_a:
        # B has higher authority
        return {
            "field": field,
            "resolved_value": claim_b.get("value"),
            "resolved_by": name_b,
            "reason": (
                f"{name_b} ({tier_b}) outranks {name_a} ({tier_a}). "
                f"Higher-tier authority prevails."
            ),
            "warning": (
                f"Authority conflict on {field}: {name_b} ({tier_b}) says "
                f"{claim_b.get('value')}, {name_a} ({tier_a}) says "
                f"{claim_a.get('value')}. Resolved to {claim_b.get('value')}."
            ),
        }
    else:
        # Same tier — use more conservative value
        conservative = _more_conservative(
            claim_a.get("value"), claim_b.get("value"),
        )
        return {
            "field": field,
            "resolved_value": conservative,
            "resolved_by": "conservative_resolution",
            "reason": (
                f"{name_a} and {name_b} are both {tier_a}. "
                f"Same-tier conflict resolved to more conservative value."
            ),
            "warning": (
                f"SAME-TIER authority conflict on {field}: {name_a} says "
                f"{claim_a.get('value')}, {name_b} says {claim_b.get('value')}. "
                f"Conservative value used: {conservative}."
            ),
        }


def _assess_conflict_severity(
    tier_a: str,
    tier_b: str,
    value_a: Any,
    value_b: Any,
) -> str:
    """Assess the severity of an authority conflict."""
    # Same Tier 1 authorities disagreeing is CRITICAL
    if tier_a == AuthorityTier.TIER_1_PRIMARY and tier_b == AuthorityTier.TIER_1_PRIMARY:
        return ConflictSeverity.CRITICAL

    # Cross-tier disagreements where lower-tier contradicts higher-tier
    order_a = AUTHORITY_TIER_ORDER.get(tier_a, 999)
    order_b = AUTHORITY_TIER_ORDER.get(tier_b, 999)
    if abs(order_a - order_b) >= 2:
        return ConflictSeverity.ERROR

    # Same tier 2 disagreements
    if tier_a == tier_b:
        return ConflictSeverity.WARNING

    # Default
    return ConflictSeverity.INFO


def _values_agree(
    value_a: Any,
    value_b: Any,
    tolerance: float = 0.05,
) -> bool:
    """Check if two values agree within tolerance."""
    if value_a is None or value_b is None:
        return value_a is None and value_b is None

    if isinstance(value_a, bool) and isinstance(value_b, bool):
        return value_a == value_b

    if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
        denominator = max(abs(value_a), abs(value_b), 1.0)
        return abs(value_a - value_b) / denominator < tolerance

    if isinstance(value_a, str) and isinstance(value_b, str):
        return value_a.upper() == value_b.upper()

    return value_a == value_b


def _more_conservative(value_a: Any, value_b: Any) -> Any:
    """Return the more conservative of two values."""
    if isinstance(value_a, bool) and isinstance(value_b, bool):
        return False if (not value_a or not value_b) else True

    if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
        return max(value_a, value_b)

    return value_a
