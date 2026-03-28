"""
backend.epistemic_arbiter — Final Epistemic Arbiter

ENDGAME PASS v2, SECTION 5: Single Final Epistemic Authority.

Problem addressed:
    Multiple subsystems produce epistemic state independently —
    truth resolution, override pressure, authority precedence,
    bounds propagation, governance, and scope. Without a single
    final arbiter, these can produce inconsistent outward-facing
    epistemic claims.

Solution:
    The epistemic arbiter is the SINGLE FINAL AUTHORITY over all
    outward-facing epistemic state. It takes ALL upstream results
    and produces a single, binding epistemic verdict that ALL
    exports, API endpoints, and diff reports must respect.

Design contract:
    - ALL exports + API must pass through the arbiter. NO EXCEPTIONS.
    - The arbiter takes the most conservative position across all inputs.
    - If ANY input says "blocked" → the arbiter blocks.
    - If ANY input says "restricted" → the arbiter restricts.
    - The arbiter's output is the ONLY source of truth for external claims.
    - Every arbiter decision includes full reasoning.

Honesty note:
    "The arbiter exists because subsystems can independently reach
    different conclusions. Without a single point of truth, the
    system's external claims become a function of which subsystem
    the consumer happens to query — that is epistemic fraud."
"""

from __future__ import annotations

from typing import Any

from backend.calibration_config import (
    DOMINANCE_FEATURES,
    get_active_calibration,
)
from backend.causal_graph import (
    trace_causal_path,
    validate_dominant_on_causal_path,
    get_reachable_outcomes,
)
from backend.epistemic_bounds import (
    EpistemicBounds,
    bounds_from_truth_result,
    bounds_from_scope_result,
    bounds_to_dict,
    merge_bounds,
    tighten_bounds,
)
from backend.epistemic_fault_isolation import (
    ContainmentLevel,
    EpistemicFaultScope,
    compute_fault_isolation,
    compute_scoped_publishability,
    fault_scope_to_dict,
)


# ═══════════════════════════════════════════════════════════════════════════
# ARBITER STATUS
# ═══════════════════════════════════════════════════════════════════════════

class ArbiterStatus:
    """Final epistemic status determined by the arbiter.

    VALID:      Output may be published without restriction.
    RESTRICTED: Output may be published with mandatory context.
    FLAGGED:    Output should carry warnings, limited usage.
    SUPPRESSED: Output may not be published but may be used internally.
    BLOCKED:    Output must not be used for any purpose.
    """
    VALID = "VALID"
    RESTRICTED = "RESTRICTED"
    FLAGGED = "FLAGGED"
    SUPPRESSED = "SUPPRESSED"
    BLOCKED = "BLOCKED"


VALID_ARBITER_STATUSES = frozenset({
    ArbiterStatus.VALID,
    ArbiterStatus.RESTRICTED,
    ArbiterStatus.FLAGGED,
    ArbiterStatus.SUPPRESSED,
    ArbiterStatus.BLOCKED,
})

# Status ordering — higher index = more restrictive
ARBITER_STATUS_ORDER: dict[str, int] = {
    ArbiterStatus.VALID: 0,
    ArbiterStatus.RESTRICTED: 1,
    ArbiterStatus.FLAGGED: 2,
    ArbiterStatus.SUPPRESSED: 3,
    ArbiterStatus.BLOCKED: 4,
}


def _more_restrictive_status(a: str, b: str) -> str:
    """Return the more restrictive of two arbiter statuses."""
    idx_a = ARBITER_STATUS_ORDER.get(a, 0)
    idx_b = ARBITER_STATUS_ORDER.get(b, 0)
    if idx_a >= idx_b:
        return a
    return b


# ═══════════════════════════════════════════════════════════════════════════
# ARBITER ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def adjudicate(
    *,
    country: str,
    runtime_status: dict[str, Any] | None = None,
    truth_resolution: dict[str, Any] | None = None,
    override_pressure: dict[str, Any] | None = None,
    authority_precedence: dict[str, Any] | None = None,
    epistemic_bounds: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    failure_visibility: dict[str, Any] | None = None,
    invariant_report: dict[str, Any] | None = None,
    reality_conflicts: dict[str, Any] | None = None,
    scope_result: dict[str, Any] | None = None,
    publishability_result: dict[str, Any] | None = None,
    axis_failures: set[int] | None = None,
    invariant_violations: list[dict[str, Any]] | None = None,
    authority_conflicts: dict[str, Any] | None = None,
    axis_weights: dict[int, float] | None = None,
    pre_arbiter_narrowing: list[dict[str, str]] | None = None,
    external_authority_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Produce the final epistemic verdict for a country.

    This is the SINGLE POINT OF TRUTH for all outward-facing claims.
    Every export, API endpoint, and diff report must use this output.

    Args:
        country: ISO-2 country code.
        runtime_status: Pipeline runtime status.
        truth_resolution: Output of resolve_truth().
        override_pressure: Override pressure dict (from compute_override_pressure).
        authority_precedence: Output of resolve_multi_field_precedence().
        epistemic_bounds: Serialized EpistemicBounds dict.
        governance: Governance assessment result.
        failure_visibility: Failure visibility result.
        invariant_report: Output of build_epistemic_invariant_report().
        reality_conflicts: Reality conflict detection result.
        scope_result: Output of determine_permitted_scope().
        publishability_result: Output of assess_publishability().
        pre_arbiter_narrowing: Narrowing disclosures from TRANSFORM modules
            that ran before the arbiter. Included in verdict for transparency.
        external_authority_signals: Structured signals from external
            authorities (BIS, IMF, etc.). These are INPUT SIGNALS —
            the arbiter weighs them but is never overridden by them.

    Returns:
        The final epistemic verdict with status, caps, and reasoning.
    """
    status = ArbiterStatus.VALID
    reasons: list[dict[str, str]] = []
    required_warnings: list[str] = []
    allowed_claims: list[str] = []
    forbidden_claims: list[str] = []
    binding_constraints: list[str] = []
    confidence_cap = 1.0

    # ── Start with full bounds, tighten from each input ──
    bounds = EpistemicBounds()

    # ── 1. Runtime Status ──
    if runtime_status is not None:
        pipeline_status = runtime_status.get("pipeline_status", "HEALTHY")
        n_failed = len(runtime_status.get("failed_layers", []))
        n_degraded = len(runtime_status.get("degraded_layers", []))

        if pipeline_status == "FAILED" or n_failed > 0:
            status = _more_restrictive_status(status, ArbiterStatus.BLOCKED)
            reasons.append({
                "source": "runtime_status",
                "decision": "BLOCKED",
                "detail": f"Pipeline failed with {n_failed} failed layer(s).",
            })
            binding_constraints.append("runtime_failed")
            bounds = tighten_bounds(
                bounds,
                max_confidence=0.0,
                max_publishability="NOT_PUBLISHABLE",
                can_rank=False,
                can_compare=False,
            )

        elif pipeline_status == "DEGRADED" or n_degraded > 0:
            status = _more_restrictive_status(status, ArbiterStatus.FLAGGED)
            confidence_cap = min(confidence_cap, 0.7)
            reasons.append({
                "source": "runtime_status",
                "decision": "FLAGGED",
                "detail": f"Pipeline degraded with {n_degraded} degraded layer(s).",
            })
            required_warnings.append(
                f"Pipeline degraded: {n_degraded} layer(s) in degraded state."
            )
            bounds = tighten_bounds(
                bounds,
                max_confidence=0.7,
                add_constraints=("runtime_degraded",),
            )

    # ── 2. Truth Resolution ──
    if truth_resolution is not None:
        truth_bounds = bounds_from_truth_result(truth_resolution)
        bounds = merge_bounds(bounds, truth_bounds)

        truth_status = truth_resolution.get("truth_status", "VALID")
        export_blocked = truth_resolution.get("export_blocked", False)

        if export_blocked or truth_status == "INVALID":
            status = _more_restrictive_status(status, ArbiterStatus.BLOCKED)
            reasons.append({
                "source": "truth_resolution",
                "decision": "BLOCKED",
                "detail": f"Truth status {truth_status}, export_blocked={export_blocked}.",
            })
            binding_constraints.append("truth_blocked")
            forbidden_claims.extend([
                "ranking", "comparison", "policy_claim",
                "composite", "country_ordering",
            ])

        elif truth_status == "DEGRADED":
            status = _more_restrictive_status(status, ArbiterStatus.RESTRICTED)
            n_conflicts = truth_resolution.get("n_conflicts", 0)
            reasons.append({
                "source": "truth_resolution",
                "decision": "RESTRICTED",
                "detail": f"Truth degraded with {n_conflicts} conflict(s).",
            })
            required_warnings.append(
                f"Truth resolution detected {n_conflicts} conflict(s)."
            )
            binding_constraints.append("truth_degraded")

    # ── 3. Override Pressure ──
    if override_pressure is not None:
        max_strength = override_pressure.get("max_strength", "NONE")
        pressure_cap = override_pressure.get("confidence_cap", 1.0)
        confidence_cap = min(confidence_cap, pressure_cap)

        if max_strength == "DECISIVE":
            status = _more_restrictive_status(status, ArbiterStatus.BLOCKED)
            reasons.append({
                "source": "override_pressure",
                "decision": "BLOCKED",
                "detail": "DECISIVE override pressure — irreconcilable.",
            })
            binding_constraints.append("override_decisive")
            forbidden_claims.extend(["ranking", "comparison"])

        elif max_strength == "STRONG":
            status = _more_restrictive_status(status, ArbiterStatus.RESTRICTED)
            reasons.append({
                "source": "override_pressure",
                "decision": "RESTRICTED",
                "detail": "STRONG override pressure — output restricted.",
            })
            binding_constraints.append("override_strong")

        elif max_strength in ("MODERATE", "WEAK"):
            if max_strength == "MODERATE":
                status = _more_restrictive_status(status, ArbiterStatus.FLAGGED)
            reasons.append({
                "source": "override_pressure",
                "decision": "FLAGGED" if max_strength == "MODERATE" else "VALID",
                "detail": f"{max_strength} override pressure.",
            })

        if not override_pressure.get("can_rank", True):
            bounds = tighten_bounds(bounds, can_rank=False)
            forbidden_claims.append("ranking")
        if not override_pressure.get("can_compare", True):
            bounds = tighten_bounds(bounds, can_compare=False)
            forbidden_claims.append("comparison")

        bounds = tighten_bounds(bounds, max_confidence=pressure_cap)

    # ── 4. Authority Precedence ──
    if authority_precedence is not None:
        if authority_precedence.get("has_residual_conflict", False):
            n_conservative = authority_precedence.get("n_conservative_bound", 0)
            if n_conservative > 0:
                status = _more_restrictive_status(status, ArbiterStatus.RESTRICTED)
                reasons.append({
                    "source": "authority_precedence",
                    "decision": "RESTRICTED",
                    "detail": (
                        f"{n_conservative} field(s) resolved by "
                        f"conservative bound (tie-breaking)."
                    ),
                })
                required_warnings.append(
                    f"Authority precedence tie on {n_conservative} field(s)."
                )
                binding_constraints.append("authority_conservative_bound")

        n_unresolvable = authority_precedence.get("n_unresolvable", 0)
        if n_unresolvable > 0:
            status = _more_restrictive_status(status, ArbiterStatus.FLAGGED)
            reasons.append({
                "source": "authority_precedence",
                "decision": "FLAGGED",
                "detail": f"{n_unresolvable} field(s) with unresolvable precedence.",
            })

    # ── 5. Governance ──
    if governance is not None:
        gov_tier = governance.get("governance_tier", "FULLY_COMPARABLE")
        ranking_eligible = governance.get("ranking_eligible", True)

        if gov_tier == "NON_COMPARABLE":
            status = _more_restrictive_status(status, ArbiterStatus.SUPPRESSED)
            reasons.append({
                "source": "governance",
                "decision": "SUPPRESSED",
                "detail": "Governance tier is NON_COMPARABLE.",
            })
            forbidden_claims.extend([
                "ranking", "comparison", "country_ordering",
            ])
            bounds = tighten_bounds(
                bounds,
                can_rank=False,
                can_compare=False,
                can_publish_country_ordering=False,
                max_confidence=0.3,
            )

        elif gov_tier == "LOW_CONFIDENCE":
            status = _more_restrictive_status(status, ArbiterStatus.RESTRICTED)
            reasons.append({
                "source": "governance",
                "decision": "RESTRICTED",
                "detail": "Governance tier is LOW_CONFIDENCE.",
            })
            required_warnings.append("Governance tier is LOW_CONFIDENCE.")
            bounds = tighten_bounds(
                bounds,
                max_confidence=0.5,
                add_warnings=("LOW_CONFIDENCE governance tier.",),
            )

        if not ranking_eligible:
            bounds = tighten_bounds(bounds, can_rank=False)
            if "ranking" not in forbidden_claims:
                forbidden_claims.append("ranking")

    # ── 6. Failure Visibility ──
    if failure_visibility is not None:
        trust_level = failure_visibility.get("trust_level", "FULL_TRUST")
        if trust_level == "NO_TRUST":
            status = _more_restrictive_status(status, ArbiterStatus.SUPPRESSED)
            reasons.append({
                "source": "failure_visibility",
                "decision": "SUPPRESSED",
                "detail": "Trust level is NO_TRUST.",
            })
            binding_constraints.append("no_trust")

        elif trust_level in ("LOW_TRUST", "GUARDED_TRUST"):
            status = _more_restrictive_status(status, ArbiterStatus.FLAGGED)
            reasons.append({
                "source": "failure_visibility",
                "decision": "FLAGGED",
                "detail": f"Trust level is {trust_level}.",
            })
            required_warnings.append(f"Trust level: {trust_level}.")

    # ── 7. Invariant Report ──
    if invariant_report is not None:
        if not invariant_report.get("passed", True):
            status = _more_restrictive_status(status, ArbiterStatus.BLOCKED)
            n_violations = invariant_report.get("n_violations", 0)
            violation_ids = invariant_report.get("violation_ids", [])
            reasons.append({
                "source": "invariant_report",
                "decision": "BLOCKED",
                "detail": (
                    f"Epistemic invariant violations: {n_violations}. "
                    f"IDs: {violation_ids}."
                ),
            })
            binding_constraints.append("invariant_violations")
            forbidden_claims.extend([
                "ranking", "comparison", "policy_claim",
            ])

    # ── 8. Reality Conflicts ──
    if reality_conflicts is not None:
        has_critical = reality_conflicts.get("has_critical", False)
        n_conflicts = reality_conflicts.get("n_conflicts", 0)

        if has_critical:
            status = _more_restrictive_status(status, ArbiterStatus.SUPPRESSED)
            reasons.append({
                "source": "reality_conflicts",
                "decision": "SUPPRESSED",
                "detail": f"Critical reality conflicts detected ({n_conflicts} total).",
            })
            binding_constraints.append("reality_critical")

        elif n_conflicts > 0:
            status = _more_restrictive_status(status, ArbiterStatus.FLAGGED)
            reasons.append({
                "source": "reality_conflicts",
                "decision": "FLAGGED",
                "detail": f"{n_conflicts} reality conflict(s) detected.",
            })
            required_warnings.append(
                f"{n_conflicts} reality conflict(s) detected."
            )

    # ── 9. Scope ──
    if scope_result is not None:
        scope_bounds = bounds_from_scope_result(scope_result)
        bounds = merge_bounds(bounds, scope_bounds)

        scope_level = scope_result.get("scope_level", "FULL")
        if scope_level in ("BLOCKED", "SUPPRESSED"):
            status = _more_restrictive_status(status, ArbiterStatus.BLOCKED)
            reasons.append({
                "source": "scope",
                "decision": "BLOCKED",
                "detail": f"Scope level is {scope_level}.",
            })
            binding_constraints.append(f"scope_{scope_level.lower()}")

        elif scope_level in ("RESTRICTED", "CONTEXT_ONLY"):
            status = _more_restrictive_status(status, ArbiterStatus.RESTRICTED)
            reasons.append({
                "source": "scope",
                "decision": "RESTRICTED",
                "detail": f"Scope level is {scope_level}.",
            })

    # ── 10. Publishability ──
    if publishability_result is not None:
        pub_status = publishability_result.get("publishability_status", "PUBLISHABLE")
        if pub_status == "NOT_PUBLISHABLE":
            status = _more_restrictive_status(status, ArbiterStatus.SUPPRESSED)
            reasons.append({
                "source": "publishability",
                "decision": "SUPPRESSED",
                "detail": "Publishability assessment: NOT_PUBLISHABLE.",
            })
            binding_constraints.append("not_publishable")
            forbidden_claims.append("publication")

        elif pub_status == "RESTRICTED":
            status = _more_restrictive_status(status, ArbiterStatus.RESTRICTED)
            reasons.append({
                "source": "publishability",
                "decision": "RESTRICTED",
                "detail": "Publishability assessment: RESTRICTED.",
            })

        elif pub_status == "PUBLISHABLE_WITH_CAVEATS":
            status = _more_restrictive_status(status, ArbiterStatus.FLAGGED)
            caveats = publishability_result.get("caveats", [])
            required_warnings.extend(caveats)

    # ── Apply final confidence cap from bounds ──
    confidence_cap = min(confidence_cap, bounds.max_confidence)

    # ── Determine allowed claims from bounds ──
    if bounds.can_rank and "ranking" not in forbidden_claims:
        allowed_claims.append("ranking")
    if bounds.can_compare and "comparison" not in forbidden_claims:
        allowed_claims.append("comparison")
    if bounds.can_publish_policy_claim and "policy_claim" not in forbidden_claims:
        allowed_claims.append("policy_claim")
    if bounds.can_publish_composite and "composite" not in forbidden_claims:
        allowed_claims.append("composite")
    if bounds.can_publish_country_ordering and "country_ordering" not in forbidden_claims:
        allowed_claims.append("country_ordering")

    # ── Deduplicate ──
    forbidden_claims = sorted(set(forbidden_claims))
    allowed_claims = sorted(set(allowed_claims))
    required_warnings = list(dict.fromkeys(required_warnings))
    binding_constraints = sorted(set(binding_constraints))

    # ── External Authority Signals ──
    # External authority signals are INPUT SIGNALS to the arbiter.
    # They influence the verdict but NEVER override it.
    # Signals are evaluated by CLAIM DOMAIN — a signal can only
    # constrain an outcome in its own domain. Cross-domain signals
    # are surfaced as typed conflicts, never silently applied.
    #
    # Claim domains map signal claim_type to arbiter outcome domains:
    CLAIM_DOMAINS: dict[str, frozenset[str]] = {
        "ranking": frozenset({"ranking"}),
        "comparison": frozenset({"comparison"}),
        "policy_claim": frozenset({"policy_claim"}),
        "composite": frozenset({"composite"}),
        "country_ordering": frozenset({"country_ordering"}),
        "publication": frozenset({"publication"}),
        "scope": frozenset({"final_status"}),
        "governance": frozenset({"ranking", "comparison", "country_ordering", "final_status"}),
        "trust": frozenset({"final_status"}),
        "data_quality": frozenset({"final_status", "ranking", "comparison"}),
        "temporal": frozenset({"final_status"}),
    }

    external_authority_report: list[dict[str, Any]] = []
    ext_signals = external_authority_signals or []
    for signal in ext_signals:
        signal_source = signal.get("source_id", "unknown")
        signal_claim = signal.get("claim_type", "unknown")
        signal_confidence = signal.get("confidence", 0.0)
        signal_decision = signal.get("decision", "VALID")
        signal_scope = signal.get("scope", "unknown")

        # Determine signal domain
        signal_domain = CLAIM_DOMAINS.get(signal_claim, frozenset())

        # If signal_claim is not a recognized domain, treat as
        # domain mismatch — surface conflict, do not accept
        domain_recognized = len(signal_domain) > 0

        # Check which internal reasons overlap with signal domain
        internal_conflict = False
        conflict_detail = ""
        conflict_type = "none"
        for reason in reasons:
            reason_source = reason.get("source", "")
            reason_decision = reason.get("decision", "VALID")
            # Match by scope or claim overlap
            if (
                reason_source in (signal_scope, signal_claim)
                and reason_decision != signal_decision
            ):
                internal_conflict = True
                conflict_detail = (
                    f"External {signal_source} says {signal_decision} "
                    f"but internal {reason_source} says {reason_decision}."
                )
                # Classify conflict type
                if not domain_recognized:
                    conflict_type = "domain_mismatch"
                elif signal_claim != signal_scope:
                    conflict_type = "cross_domain"
                else:
                    conflict_type = "same_domain"
                break

        # Decision logic: domain-typed, not scalar
        signal_status_level = ARBITER_STATUS_ORDER.get(signal_decision, 0)
        current_status_level = ARBITER_STATUS_ORDER.get(status, 0)

        accepted = False
        rejection_reason = ""

        if not domain_recognized:
            # Unrecognized domain — reject with typed conflict
            rejection_reason = (
                f"Rejected: signal claim_type '{signal_claim}' is not a "
                f"recognized claim domain. Domain mismatch — cannot "
                f"silently constrain."
            )
            if internal_conflict:
                required_warnings.append(
                    f"External authority domain mismatch: {conflict_detail}"
                )
        elif signal_status_level > current_status_level:
            # More restrictive AND in a recognized domain — accept
            # but ONLY affect the claim domains it covers
            status = _more_restrictive_status(status, signal_decision)
            reasons.append({
                "source": f"external_authority:{signal_source}",
                "decision": signal_decision,
                "detail": (
                    f"External authority {signal_source} reports "
                    f"{signal_decision} for domain '{signal_claim}' "
                    f"(confidence={signal_confidence:.2f}). "
                    f"Constrains: {sorted(signal_domain)}."
                ),
            })
            accepted = True
            # If signal domain includes specific claims, forbid them
            for domain_claim in signal_domain:
                if (
                    domain_claim != "final_status"
                    and domain_claim not in forbidden_claims
                    and signal_status_level >= 3  # SUPPRESSED or BLOCKED
                ):
                    forbidden_claims.append(domain_claim)
        else:
            # Less restrictive — reject
            rejection_reason = (
                f"Rejected: internal assessment is already "
                f"{status} (≥ {signal_decision})."
            )
            if internal_conflict:
                required_warnings.append(
                    f"External authority conflict ({conflict_type}): "
                    f"{conflict_detail}"
                )

        external_authority_report.append({
            "source_id": signal_source,
            "claim_type": signal_claim,
            "confidence": signal_confidence,
            "decision": signal_decision,
            "domain": sorted(signal_domain) if signal_domain else [],
            "domain_recognized": domain_recognized,
            "conflict_type": conflict_type,
            "accepted": accepted,
            "internal_conflict": internal_conflict,
            "conflict_detail": conflict_detail,
            "reason": (
                f"Accepted: more restrictive in domain '{signal_claim}'. "
                f"Constrains: {sorted(signal_domain)}."
                if accepted else rejection_reason
            ),
        })

    # Re-deduplicate after external authority processing
    forbidden_claims = sorted(set(forbidden_claims))

    # ── Dominant Constraint Extraction (weighted + decision-path) ──
    # Uses versioned weights from CalibrationConfig and validates
    # that the dominant constraint lies on a decision path to the
    # final outcome. Weights are heuristic defaults unless a fitted
    # artifact has been loaded.
    calibration = get_active_calibration()

    # Map source → number of forbidden claims that source directly adds.
    _SOURCE_CLAIMS_FORBIDDEN: dict[str, int] = {}
    for fc_source, fc_count in [
        ("runtime_status", 5),
        ("truth_resolution", 5),
        ("override_pressure", 2),
        ("governance", 3),
        ("invariant_report", 3),
        ("publishability", 1),
    ]:
        _SOURCE_CLAIMS_FORBIDDEN[fc_source] = fc_count

    _PRIMARY_PATH_SOURCES = {"truth_resolution", "governance", "runtime_status"}

    # Compute source recurrence (how many reasons each source has)
    source_recurrence: dict[str, int] = {}
    for reason in reasons:
        src = reason.get("source", "")
        source_recurrence[src] = source_recurrence.get(src, 0) + 1

    # Relevant outcomes for decision-path validation
    relevant_outcomes = {"final_status"} | set(forbidden_claims)

    def _dominance_score(reason: dict[str, str]) -> float:
        """Compute weighted dominance score for a reason."""
        src = reason.get("source", "")
        # Strip external_authority: prefix for decision-path lookup
        causal_src = src.split(":")[-1] if src.startswith("external_authority:") else src
        severity = ARBITER_STATUS_ORDER.get(
            reason.get("decision", "VALID"), 0
        )
        claims = _SOURCE_CLAIMS_FORBIDDEN.get(causal_src, 0)
        primary = 1.0 if causal_src in _PRIMARY_PATH_SOURCES else 0.0
        recurrence = float(source_recurrence.get(src, 1))

        return (
            calibration.weight("severity") * severity
            + calibration.weight("claims_forbidden") * claims
            + calibration.weight("primary_path") * primary
            + calibration.weight("recurrence") * recurrence
        )

    dominant_constraint: str | None = None
    dominant_constraint_source: str | None = None
    if reasons:
        # Score all reasons and filter by decision path
        scored: list[tuple[int, float, dict[str, str]]] = []
        for i, reason in enumerate(reasons):
            src = reason.get("source", "")
            causal_src = src.split(":")[-1] if src.startswith("external_authority:") else src
            reachable = get_reachable_outcomes(causal_src)
            on_path = len(reachable & relevant_outcomes) > 0

            score = _dominance_score(reason)
            # Reasons NOT on decision path get their score halved —
            # they can still be dominant if nothing else qualifies,
            # but path-connected reasons are strongly preferred.
            if not on_path:
                score *= 0.5
            scored.append((i, score, reason))

        # Pick the highest score; ties broken by earliest index
        best_idx, best_score, best_reason = scored[0]
        for idx, score, reason in scored[1:]:
            if score > best_score:
                best_idx, best_score, best_reason = idx, score, reason

        dominant_constraint = best_reason.get("detail", "unknown")
        dominant_constraint_source = best_reason.get("source", "unknown")

    # Decision-path trace for audit
    causal_path = trace_causal_path(reasons, status, forbidden_claims)
    causal_validation = validate_dominant_on_causal_path(
        dominant_constraint_source, status, forbidden_claims,
    )

    # ── Map arbiter status to publishability ──
    publishability_map = {
        ArbiterStatus.VALID: "PUBLISHABLE",
        ArbiterStatus.RESTRICTED: "PUBLISHABLE_WITH_CAVEATS",
        ArbiterStatus.FLAGGED: "PUBLISHABLE_WITH_CAVEATS",
        ArbiterStatus.SUPPRESSED: "NOT_PUBLISHABLE",
        ArbiterStatus.BLOCKED: "NOT_PUBLISHABLE",
    }
    final_publishability = publishability_map.get(status, "NOT_PUBLISHABLE")

    # ── Fault Isolation (v3) — compute scoped degradation ──
    fault_scope = compute_fault_isolation(
        country=country,
        invariant_violations=invariant_violations,
        authority_conflicts=authority_conflicts,
        runtime_failures=runtime_status,
        epistemic_bounds=epistemic_bounds,
        governance=governance,
        axis_failures=axis_failures,
        axis_weights=axis_weights,
    )

    # ── Apply fault-scope-aware rules ──
    # Only suppress globally if containment is GLOBAL
    scoped_pub = compute_scoped_publishability(
        fault_scope, base_publishability=final_publishability,
    )

    return {
        "country": country,
        "final_epistemic_status": status,
        "final_confidence_cap": round(confidence_cap, 4),
        "final_publishability": final_publishability,
        "final_allowed_claims": allowed_claims,
        "final_forbidden_claims": forbidden_claims,
        "final_required_warnings": required_warnings,
        "final_bounds": bounds_to_dict(bounds),
        "binding_constraints": binding_constraints,
        "dominant_constraint": dominant_constraint,
        "dominant_constraint_source": dominant_constraint_source,
        "pre_arbiter_narrowing": pre_arbiter_narrowing or [],
        "calibration_version": calibration.version,
        "calibration_weights": calibration.weights,
        "calibration_mode": calibration.mode,
        "calibration_artifact_present": calibration.is_fitted(),
        "calibration_honesty_note": (
            "Weights are fitted to labeled data."
            if calibration.is_fitted() else
            "Weights are heuristic defaults — not fitted to data."
        ),
        "causal_path": causal_path,
        "causal_validation": causal_validation,
        "decision_path_type": "decision_path_dependency",
        "decision_path_honesty_note": (
            "Decision-path associations are structural code paths, "
            "not causal relationships in the interventionist sense."
        ),
        "external_authority_report": external_authority_report,
        "arbiter_reasoning": reasons,
        "fault_scope": fault_scope_to_dict(fault_scope),
        "scoped_publishability": scoped_pub,
        "n_inputs_evaluated": sum(
            1 for x in [
                runtime_status, truth_resolution, override_pressure,
                authority_precedence, governance, failure_visibility,
                invariant_report, reality_conflicts, scope_result,
                publishability_result,
            ] if x is not None
        ),
        "n_external_signals": len(ext_signals),
        "n_external_accepted": sum(
            1 for r in external_authority_report if r.get("accepted")
        ),
        "n_external_conflicts": sum(
            1 for r in external_authority_report if r.get("internal_conflict")
        ),
        "n_reasons": len(reasons),
        "n_warnings": len(required_warnings),
        "n_forbidden_claims": len(forbidden_claims),
        "n_allowed_claims": len(allowed_claims),
        "n_binding_constraints": len(binding_constraints),
        "honesty_note": (
            f"Epistemic arbiter verdict for {country}: {status}. "
            f"Confidence capped at {confidence_cap:.2f}. "
            f"Publishability: {final_publishability}. "
            f"{len(allowed_claims)} claims allowed, "
            f"{len(forbidden_claims)} claims forbidden. "
            f"{len(reasons)} reasoning steps, "
            f"{len(binding_constraints)} binding constraints. "
            f"Weight mode: {calibration.mode}. "
            f"External signals: {len(ext_signals)} "
            f"({sum(1 for r in external_authority_report if r.get('accepted'))} accepted). "
            f"This is the sole terminal epistemic authority — all exports "
            f"and API endpoints must respect this verdict."
        ),
    }


def validate_output_against_arbiter(
    output: dict[str, Any],
    arbiter_verdict: dict[str, Any],
) -> dict[str, Any]:
    """Validate that an output respects the arbiter's verdict.

    This is the anti-laundering check. No output may present
    claims that the arbiter has forbidden.

    Args:
        output: The output to validate.
        arbiter_verdict: The arbiter's verdict for this country.

    Returns:
        Validation result with pass/fail and violations.
    """
    violations: list[dict[str, str]] = []
    forbidden = set(arbiter_verdict.get("final_forbidden_claims", []))
    final_status = arbiter_verdict.get("final_epistemic_status", ArbiterStatus.VALID)
    confidence_cap = arbiter_verdict.get("final_confidence_cap", 1.0)

    # Check confidence
    output_confidence = output.get("confidence")
    if output_confidence is not None and output_confidence > confidence_cap:
        violations.append({
            "field": "confidence",
            "violation": (
                f"Output confidence {output_confidence} exceeds "
                f"arbiter cap {confidence_cap}."
            ),
        })

    # Check forbidden claims
    if "ranking" in forbidden:
        if output.get("rank") is not None or output.get("ranking_eligible", False):
            violations.append({
                "field": "ranking",
                "violation": "Output contains ranking but arbiter forbids it.",
            })

    if "comparison" in forbidden:
        if output.get("cross_country_comparable", False):
            violations.append({
                "field": "comparison",
                "violation": "Output claims comparability but arbiter forbids it.",
            })

    if "composite" in forbidden:
        if output.get("composite_score") is not None:
            violations.append({
                "field": "composite",
                "violation": "Output contains composite score but arbiter forbids it.",
            })

    if "policy_claim" in forbidden:
        if output.get("policy_implications"):
            violations.append({
                "field": "policy_claim",
                "violation": "Output contains policy claims but arbiter forbids it.",
            })

    # Check required warnings are present
    required = arbiter_verdict.get("final_required_warnings", [])
    output_warnings = set(output.get("warnings", []))
    for warning in required:
        if warning not in output_warnings:
            violations.append({
                "field": "warnings",
                "violation": f"Required warning missing: {warning}",
            })

    # Blocked/suppressed should not be in output at all
    if final_status in (ArbiterStatus.BLOCKED, ArbiterStatus.SUPPRESSED):
        if output.get("is_published", False):
            violations.append({
                "field": "publication",
                "violation": (
                    f"Output is marked as published but arbiter "
                    f"status is {final_status}."
                ),
            })

    passed = len(violations) == 0

    return {
        "passed": passed,
        "n_violations": len(violations),
        "violations": violations,
        "arbiter_status": final_status,
        "honesty_note": (
            f"Output validation against arbiter: {'PASSED' if passed else 'FAILED'}. "
            f"{len(violations)} violation(s). "
            f"{'Output respects arbiter verdict.' if passed else 'ANTI-LAUNDERING VIOLATION — output exceeds arbiter permissions.'}"
        ),
    }
