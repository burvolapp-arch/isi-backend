"""
backend.publishability — Publishability Assessment Engine

SECTION 10 of Ultimate Pass: Publishability Determination.

Problem addressed:
    "Technically computable" ≠ "defensibly publishable." The system
    can compute a ranking for every country, but some rankings are
    not defensible under peer review, policy scrutiny, or adversarial
    analysis.

Solution:
    The publishability engine evaluates whether a country's output
    is fit for publication, considering:
    - Governance tier and truth resolution
    - Data completeness and quality
    - External authority alignment
    - Override and conflict history
    - Scope restrictions

Design contract:
    - PUBLISHABLE: output can appear in public-facing reports.
    - PUBLISHABLE_WITH_CAVEATS: output can appear with mandatory context.
    - NOT_PUBLISHABLE: output must not appear in public reports.
    - Every non-publishable determination includes an explanation.
    - The system NEVER publishes without running publishability check.

Honesty note:
    This is the system's final gate before output. If a country's
    data fails publishability, it means the system is honest enough
    to say "I cannot defensibly make this claim in public."
"""

from __future__ import annotations

from typing import Any

from backend.epistemic_fault_isolation import (
    EpistemicFaultScope,
    compute_scoped_publishability,
)


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHABILITY STATUS
# ═══════════════════════════════════════════════════════════════════════════

class PublishabilityStatus:
    """Classification of publishability."""
    PUBLISHABLE = "PUBLISHABLE"
    PUBLISHABLE_WITH_CAVEATS = "PUBLISHABLE_WITH_CAVEATS"
    RESTRICTED = "RESTRICTED"
    NOT_PUBLISHABLE = "NOT_PUBLISHABLE"


VALID_PUBLISHABILITY_STATUSES = frozenset({
    PublishabilityStatus.PUBLISHABLE,
    PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
    PublishabilityStatus.RESTRICTED,
    PublishabilityStatus.NOT_PUBLISHABLE,
})


# ═══════════════════════════════════════════════════════════════════════════
# PUBLISHABILITY ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def assess_publishability(
    country: str,
    truth_result: dict[str, Any] | None = None,
    scope_result: dict[str, Any] | None = None,
    override_summary: dict[str, Any] | None = None,
    authority_conflicts: dict[str, Any] | None = None,
    data_completeness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess whether a country's output is fit for publication.

    Args:
        country: ISO-2 country code.
        truth_result: Output of resolve_truth().
        scope_result: Output of determine_permitted_scope().
        override_summary: Output of compute_override_summary().
        authority_conflicts: Output of detect_authority_conflicts().
        data_completeness: {axes_available, axes_required, ...}

    Returns:
        Publishability assessment with status, reasons, and caveats.
    """
    status = PublishabilityStatus.PUBLISHABLE
    reasons: list[dict[str, str]] = []
    caveats: list[str] = []
    blockers: list[str] = []

    # ── Check 1: Truth resolution ──
    if truth_result is not None:
        truth_status = truth_result.get("truth_status", "VALID")
        export_blocked = truth_result.get("export_blocked", False)
        final_tier = truth_result.get("final_governance_tier", "FULLY_COMPARABLE")

        if export_blocked:
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append("Export blocked by truth resolver.")
            reasons.append({
                "check": "export_blocked",
                "result": "BLOCKED",
                "detail": "Truth resolver has blocked export.",
            })

        if truth_status == "INVALID":
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append("Truth status is INVALID — irreconcilable contradictions.")
            reasons.append({
                "check": "truth_invalid",
                "result": "BLOCKED",
                "detail": "Truth resolution found irreconcilable contradictions.",
            })

        if truth_status == "DEGRADED" and status == PublishabilityStatus.PUBLISHABLE:
            status = PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
            caveats.append(
                f"Truth resolution detected {truth_result.get('n_conflicts', 0)} "
                f"conflicts resolved by priority."
            )
            reasons.append({
                "check": "truth_degraded",
                "result": "CAVEATS",
                "detail": "Truth resolution has conflicts resolved by priority.",
            })

        if final_tier == "NON_COMPARABLE":
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append("Governance tier is NON_COMPARABLE.")
            reasons.append({
                "check": "tier_non_comparable",
                "result": "BLOCKED",
                "detail": "NON_COMPARABLE tier prevents publication.",
            })

        if final_tier == "LOW_CONFIDENCE" and status == PublishabilityStatus.PUBLISHABLE:
            status = PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
            caveats.append(
                "Governance tier is LOW_CONFIDENCE — output requires "
                "extensive context."
            )
            reasons.append({
                "check": "tier_low_confidence",
                "result": "CAVEATS",
                "detail": "LOW_CONFIDENCE tier requires caveats.",
            })

    # ── Check 2: Scope restrictions ──
    if scope_result is not None:
        scope_level = scope_result.get("scope_level", "FULL")

        if scope_level in ("BLOCKED", "SUPPRESSED"):
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append(f"Scope level is {scope_level}.")
            reasons.append({
                "check": "scope_blocked",
                "result": "BLOCKED",
                "detail": f"Scope level {scope_level} prevents publication.",
            })

        if scope_level in ("RESTRICTED", "CONTEXT_ONLY") and status == PublishabilityStatus.PUBLISHABLE:
            status = PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
            caveats.append(f"Scope level is {scope_level} — restricted output.")
            reasons.append({
                "check": "scope_restricted",
                "result": "CAVEATS",
                "detail": f"Scope level {scope_level} requires caveats.",
            })

    # ── Check 3: Override summary ──
    if override_summary is not None:
        if override_summary.get("has_blocking", False):
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append("Epistemic override has blocking conflict.")
            reasons.append({
                "check": "override_blocking",
                "result": "BLOCKED",
                "detail": "Epistemic override detected blocking conflict.",
            })

        n_accepted = override_summary.get("n_accepted", 0)
        if n_accepted > 0 and status == PublishabilityStatus.PUBLISHABLE:
            status = PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
            caveats.append(
                f"{n_accepted} external authority override(s) applied."
            )
            reasons.append({
                "check": "override_accepted",
                "result": "CAVEATS",
                "detail": f"{n_accepted} override(s) accepted.",
            })

    # ── Check 4: Authority conflicts ──
    if authority_conflicts is not None:
        if authority_conflicts.get("has_critical", False):
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append("Critical authority conflicts detected.")
            reasons.append({
                "check": "authority_critical",
                "result": "BLOCKED",
                "detail": "Critical authority conflicts prevent publication.",
            })

        n_conflicts = authority_conflicts.get("n_conflicts", 0)
        if n_conflicts > 0 and status == PublishabilityStatus.PUBLISHABLE:
            status = PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
            caveats.append(f"{n_conflicts} authority conflict(s) detected.")
            reasons.append({
                "check": "authority_conflicts",
                "result": "CAVEATS",
                "detail": f"{n_conflicts} authority conflict(s) require caveats.",
            })

        # ── Check 4b: Residual authority conflicts → RESTRICTED ──
        if authority_conflicts.get("has_residual_conflict", False):
            residual_severity = authority_conflicts.get(
                "residual_conflict_severity", "WARNING",
            )
            if (
                residual_severity in ("ERROR", "CRITICAL")
                and status in (
                    PublishabilityStatus.PUBLISHABLE,
                    PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
                )
            ):
                status = PublishabilityStatus.RESTRICTED
                caveats.append(
                    f"Residual authority conflict (severity: {residual_severity}). "
                    f"Output restricted — claim cannot be trivially extracted "
                    f"as stronger than evidence supports."
                )
                reasons.append({
                    "check": "residual_conflict_restriction",
                    "result": "RESTRICTED",
                    "detail": (
                        f"Residual conflict severity {residual_severity} "
                        f"triggers RESTRICTED status."
                    ),
                })

    # ── Check 5: Data completeness ──
    if data_completeness is not None:
        axes_available = data_completeness.get("axes_available", 6)
        axes_required = data_completeness.get("axes_required", 6)

        if axes_available == 0:
            status = PublishabilityStatus.NOT_PUBLISHABLE
            blockers.append("No axis data available.")
            reasons.append({
                "check": "no_data",
                "result": "BLOCKED",
                "detail": "No axis data available for publication.",
            })

        if 0 < axes_available < axes_required and status == PublishabilityStatus.PUBLISHABLE:
            status = PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
            caveats.append(
                f"Only {axes_available}/{axes_required} axes available."
            )
            reasons.append({
                "check": "incomplete_data",
                "result": "CAVEATS",
                "detail": f"Incomplete data: {axes_available}/{axes_required} axes.",
            })

    return {
        "country": country,
        "publishability_status": status,
        "is_publishable": status != PublishabilityStatus.NOT_PUBLISHABLE,
        "requires_caveats": status == PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        "reasons": reasons,
        "caveats": caveats,
        "blockers": blockers,
        "n_reasons": len(reasons),
        "n_caveats": len(caveats),
        "n_blockers": len(blockers),
        "honesty_note": (
            f"Publishability assessment for {country}: {status}. "
            f"{len(reasons)} checks performed, {len(blockers)} blockers, "
            f"{len(caveats)} caveats. "
            f"{'Output is fit for publication.' if status == PublishabilityStatus.PUBLISHABLE else ''}"
            f"{'Output requires mandatory caveats.' if status == PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS else ''}"
            f"{'Output is NOT fit for publication.' if status == PublishabilityStatus.NOT_PUBLISHABLE else ''}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# SCOPED PUBLISHABILITY ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def assess_scoped_publishability(
    country: str,
    fault_scope: EpistemicFaultScope | None = None,
    truth_result: dict[str, Any] | None = None,
    scope_result: dict[str, Any] | None = None,
    override_summary: dict[str, Any] | None = None,
    authority_conflicts: dict[str, Any] | None = None,
    data_completeness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess publishability with fault-scope awareness.

    This is the fault-isolation-aware wrapper around assess_publishability.
    Instead of a single global publishability status, it produces:
    - A global baseline (from assess_publishability)
    - Per-output publishability (from fault scope)
    - Independent axis publishability (axis failure does NOT suppress unrelated outputs)

    Rule: "Axis failure must not suppress unrelated outputs."

    Args:
        country: ISO-2 country code.
        fault_scope: Computed epistemic fault scope (or None for legacy mode).
        truth_result: Output of resolve_truth().
        scope_result: Output of determine_permitted_scope().
        override_summary: Output of compute_override_summary().
        authority_conflicts: Output of detect_authority_conflicts().
        data_completeness: {axes_available, axes_required, ...}

    Returns:
        Scoped publishability assessment with per-output status.
    """
    # ── Step 1: Compute baseline publishability ──
    baseline = assess_publishability(
        country=country,
        truth_result=truth_result,
        scope_result=scope_result,
        override_summary=override_summary,
        authority_conflicts=authority_conflicts,
        data_completeness=data_completeness,
    )

    # ── Step 2: If no fault scope, return baseline (legacy mode) ──
    if fault_scope is None:
        baseline["scoped"] = False
        baseline["per_output_publishability"] = {}
        return baseline

    # ── Step 3: Compute per-output publishability ──
    base_status = baseline["publishability_status"]
    per_output = compute_scoped_publishability(
        fault_scope=fault_scope,
        base_publishability=base_status,
    )

    # ── Step 4: Determine effective status ──
    # The scoped status is the MOST RESTRICTIVE per-output status
    # that applies to global outputs (ranking, composite, policy).
    # But per-axis outputs get INDEPENDENT assessment.
    global_output_statuses = []
    for key, val in per_output.items():
        if key.startswith("publishability_") and not key.startswith("publishability_axis_"):
            if key not in ("publishability_fault_scope_level",):
                global_output_statuses.append(val)

    # Effective global: most restrictive among global outputs
    status_order = {
        PublishabilityStatus.NOT_PUBLISHABLE: 0,
        PublishabilityStatus.RESTRICTED: 1,
        PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS: 2,
        PublishabilityStatus.PUBLISHABLE: 3,
    }

    effective_status = base_status
    for s in global_output_statuses:
        if status_order.get(s, 3) < status_order.get(effective_status, 3):
            effective_status = s

    # ── Step 5: Count independently publishable outputs ──
    n_publishable = sum(
        1 for key, val in per_output.items()
        if key.startswith("publishability_") and val == PublishabilityStatus.PUBLISHABLE
    )
    n_caveats = sum(
        1 for key, val in per_output.items()
        if key.startswith("publishability_") and val == PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS
    )
    n_blocked = sum(
        1 for key, val in per_output.items()
        if key.startswith("publishability_") and val == PublishabilityStatus.NOT_PUBLISHABLE
    )

    return {
        "country": country,
        "scoped": True,
        "publishability_status": effective_status,
        "is_publishable": effective_status != PublishabilityStatus.NOT_PUBLISHABLE,
        "requires_caveats": effective_status == PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        "baseline_status": base_status,
        "per_output_publishability": per_output,
        "n_outputs_publishable": n_publishable,
        "n_outputs_caveats": n_caveats,
        "n_outputs_blocked": n_blocked,
        "fault_scope_level": fault_scope.containment_level,
        "n_affected_axes": len(fault_scope.affected_axes),
        "affected_axes": sorted(fault_scope.affected_axes),
        "reasons": baseline["reasons"],
        "caveats": baseline["caveats"],
        "blockers": baseline["blockers"],
        "honesty_note": (
            f"Scoped publishability for {country}: baseline={base_status}, "
            f"effective={effective_status}. "
            f"Fault scope: {fault_scope.containment_level}, "
            f"{len(fault_scope.affected_axes)} axes affected. "
            f"Per-output: {n_publishable} publishable, "
            f"{n_caveats} with caveats, {n_blocked} blocked. "
            f"Unaffected outputs retain baseline publishability — "
            f"axis failures do NOT suppress unrelated outputs."
        ),
    }
