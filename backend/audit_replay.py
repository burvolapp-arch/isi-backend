"""
backend.audit_replay — Audit Replay Engine

SECTION 7 of Ultimate Pass: Full Decision Tracing.

Problem addressed:
    When a user or reviewer asks "WHY does Country X get this ranking?"
    the system must be able to replay the complete decision chain —
    from raw data through every layer, enforcement rule, truth
    resolution, override, and scope determination.

Solution:
    The audit replay engine constructs a full audit trail for any
    country, showing every decision point, its inputs, and its
    output. This is the system's "show your work" mechanism.

Design contract:
    - Every decision in the pipeline is traceable.
    - Audit replay is deterministic — same input = same audit.
    - The audit trail includes epistemic provenance for every value.
    - Missing audit data produces an explicit "UNAUDITABLE" status.
    - Audit replay does NOT re-compute — it reads from materialized state.

Honesty note:
    If the audit trail is incomplete, the system admits it. An
    "UNAUDITABLE" decision is worse than a wrong one — at least a
    wrong decision can be corrected.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT STATUS
# ═══════════════════════════════════════════════════════════════════════════

class AuditStatus:
    """Classification of audit trail completeness."""
    COMPLETE = "COMPLETE"       # Full chain auditable
    PARTIAL = "PARTIAL"         # Some decisions missing context
    UNAUDITABLE = "UNAUDITABLE" # Critical decisions not traceable


VALID_AUDIT_STATUSES = frozenset({
    AuditStatus.COMPLETE,
    AuditStatus.PARTIAL,
    AuditStatus.UNAUDITABLE,
})


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT REPLAY
# ═══════════════════════════════════════════════════════════════════════════

def replay_country_audit(
    country: str,
    country_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a full audit trail for one country.

    This reads from the materialized country JSON (not recomputed)
    and constructs a traceable decision chain.

    Args:
        country: ISO-2 country code.
        country_json: The full materialized country JSON.

    Returns:
        Audit trail with decision chain, status, and gaps.
    """
    if country_json is None:
        return {
            "country": country,
            "audit_status": AuditStatus.UNAUDITABLE,
            "reason": "No materialized country JSON available.",
            "decision_chain": [],
            "gaps": ["country_json_missing"],
            "n_decision_steps": 0,
            "n_gaps": 1,
            "honesty_note": (
                f"Audit replay for {country}: 0 decision steps traced, "
                f"1 gaps detected. Audit status: {AuditStatus.UNAUDITABLE}. "
                f"UNAUDITABLE — critical decisions not traceable."
            ),
        }

    decision_chain: list[dict[str, Any]] = []
    gaps: list[str] = []

    # ── Step 1: Governance Assessment ──
    governance = country_json.get("governance")
    if governance:
        decision_chain.append({
            "step": 1,
            "layer": "governance",
            "decision": "governance_tier_assignment",
            "input_summary": {
                "severity_total": governance.get("total_severity"),
                "n_producer_inverted": governance.get("n_producer_inverted_axes", 0),
            },
            "output": {
                "governance_tier": governance.get("governance_tier"),
                "ranking_eligible": governance.get("ranking_eligible"),
                "cross_country_comparable": governance.get("cross_country_comparable"),
            },
        })
    else:
        gaps.append("governance_missing")

    # ── Step 2: Decision Usability ──
    du = country_json.get("decision_usability")
    if du:
        decision_chain.append({
            "step": 2,
            "layer": "decision_usability",
            "decision": "usability_classification",
            "output": {
                "decision_usability_class": du.get("decision_usability_class"),
            },
        })
    else:
        gaps.append("decision_usability_missing")

    # ── Step 3: External Validation ──
    ev = country_json.get("external_validation")
    if ev:
        decision_chain.append({
            "step": 3,
            "layer": "external_validation",
            "decision": "alignment_assessment",
            "output": {
                "overall_alignment": ev.get("overall_alignment"),
                "n_benchmarks_assessed": ev.get("n_benchmarks_assessed", 0),
            },
        })
    else:
        gaps.append("external_validation_missing")

    # ── Step 4: Construct Enforcement ──
    ce = country_json.get("construct_enforcement")
    if ce:
        decision_chain.append({
            "step": 4,
            "layer": "construct_enforcement",
            "decision": "composite_producibility",
            "output": {
                "composite_producible": ce.get("composite_producible"),
                "n_valid": ce.get("n_valid"),
                "n_invalid": ce.get("n_invalid"),
            },
        })
    else:
        gaps.append("construct_enforcement_missing")

    # ── Step 5: Failure Visibility ──
    fv = country_json.get("failure_visibility")
    if fv:
        decision_chain.append({
            "step": 5,
            "layer": "failure_visibility",
            "decision": "trust_level_assessment",
            "output": {
                "trust_level": fv.get("trust_level"),
            },
        })
    else:
        gaps.append("failure_visibility_missing")

    # ── Step 6: Reality Conflicts ──
    rc = country_json.get("reality_conflicts")
    if rc:
        decision_chain.append({
            "step": 6,
            "layer": "reality_conflicts",
            "decision": "conflict_detection",
            "output": {
                "n_conflicts": rc.get("n_conflicts", 0),
                "has_critical": rc.get("has_critical", False),
            },
        })
    else:
        gaps.append("reality_conflicts_missing")

    # ── Step 7: Enforcement Matrix ──
    enforcement = country_json.get("enforcement_actions")
    if enforcement:
        decision_chain.append({
            "step": 7,
            "layer": "enforcement_matrix",
            "decision": "enforcement_application",
            "output": {
                "n_actions": enforcement.get("n_actions", 0),
                "export_blocked": enforcement.get("export_blocked", False),
                "enforced_tier": enforcement.get("enforced_governance_tier"),
                "enforced_ranking": enforcement.get("enforced_ranking_eligible"),
            },
        })
    else:
        gaps.append("enforcement_actions_missing")

    # ── Step 8: Truth Resolution ──
    truth = country_json.get("truth_resolution")
    if truth:
        decision_chain.append({
            "step": 8,
            "layer": "truth_resolver",
            "decision": "authoritative_resolution",
            "output": {
                "truth_status": truth.get("truth_status"),
                "final_tier": truth.get("final_governance_tier"),
                "final_ranking": truth.get("final_ranking_eligible"),
                "n_conflicts": truth.get("n_conflicts", 0),
                "n_resolutions": truth.get("n_resolutions", 0),
            },
        })
    else:
        gaps.append("truth_resolution_missing")

    # ── Step 9: Permitted Scope ──
    scope = country_json.get("permitted_scope")
    if scope:
        decision_chain.append({
            "step": 9,
            "layer": "permitted_scope",
            "decision": "output_scope_determination",
            "output": {
                "scope_level": scope.get("scope_level"),
                "ranking_permitted": scope.get("permissions", {}).get("ranking_permitted"),
                "n_scope_reasons": scope.get("n_scope_warnings", 0),
            },
        })
    else:
        gaps.append("permitted_scope_missing")

    # ── Determine audit status ──
    critical_layers = {
        "governance_missing",
        "enforcement_actions_missing",
        "truth_resolution_missing",
    }
    if critical_layers & set(gaps):
        audit_status = AuditStatus.UNAUDITABLE
    elif gaps:
        audit_status = AuditStatus.PARTIAL
    else:
        audit_status = AuditStatus.COMPLETE

    return {
        "country": country,
        "audit_status": audit_status,
        "n_decision_steps": len(decision_chain),
        "n_gaps": len(gaps),
        "gaps": gaps,
        "decision_chain": decision_chain,
        "honesty_note": (
            f"Audit replay for {country}: {len(decision_chain)} decision steps "
            f"traced, {len(gaps)} gaps detected. "
            f"Audit status: {audit_status}. "
            f"{'COMPLETE — all decisions traceable.' if audit_status == AuditStatus.COMPLETE else ''}"
            f"{'PARTIAL — some decisions missing context.' if audit_status == AuditStatus.PARTIAL else ''}"
            f"{'UNAUDITABLE — critical decisions not traceable.' if audit_status == AuditStatus.UNAUDITABLE else ''}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# COUNTERFACTUAL REPLAY
# ═══════════════════════════════════════════════════════════════════════════

def build_counterfactual_replay(
    country: str,
    country_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a counterfactual replay for a country.

    This answers: "What is the MINIMUM change needed to enable
    ranking, comparison, higher confidence, or policy claims?"

    For each currently-blocked capability, the replay identifies
    the binding constraint and the minimal change that would remove it.

    Args:
        country: ISO-2 country code.
        country_json: The full materialized country JSON.

    Returns:
        Counterfactual analysis with binding constraints and
        minimal changes needed for each capability.
    """
    if country_json is None:
        return {
            "country": country,
            "counterfactual_status": "UNANALYZABLE",
            "reason": "No materialized country JSON available.",
            "binding_constraints": [],
            "counterfactuals": [],
            "n_counterfactuals": 0,
            "honesty_note": (
                f"Counterfactual replay for {country}: "
                f"UNANALYZABLE — no data available."
            ),
        }

    binding_constraints: list[dict[str, Any]] = []
    counterfactuals: list[dict[str, Any]] = []

    # ── Analyze ranking eligibility ──
    governance = country_json.get("governance", {})
    ranking_eligible = governance.get("ranking_eligible", True)
    gov_tier = governance.get("governance_tier", "FULLY_COMPARABLE")

    if not ranking_eligible:
        constraint = {
            "capability": "ranking",
            "blocked_by": "governance",
            "current_value": ranking_eligible,
            "blocking_reason": f"Governance tier {gov_tier} prevents ranking.",
        }
        binding_constraints.append(constraint)

        # What would need to change?
        if gov_tier == "NON_COMPARABLE":
            counterfactuals.append({
                "capability": "ranking",
                "minimal_change": (
                    "Reduce governance severity or resolve producer "
                    "inversions to move tier from NON_COMPARABLE to at "
                    "least PARTIALLY_COMPARABLE."
                ),
                "difficulty": "HIGH",
                "requires": ["governance_tier_upgrade"],
            })
        elif gov_tier == "LOW_CONFIDENCE":
            counterfactuals.append({
                "capability": "ranking",
                "minimal_change": (
                    "Improve axis confidence scores to move tier from "
                    "LOW_CONFIDENCE to PARTIALLY_COMPARABLE."
                ),
                "difficulty": "MODERATE",
                "requires": ["confidence_improvement"],
            })

    # ── Analyze comparability ──
    truth = country_json.get("truth_resolution", {})
    comparable = truth.get("final_cross_country_comparable", True)

    if not comparable:
        constraint = {
            "capability": "comparison",
            "blocked_by": "truth_resolution",
            "current_value": comparable,
            "blocking_reason": "Truth resolution disabled cross-country comparison.",
        }
        binding_constraints.append(constraint)

        n_conflicts = truth.get("n_conflicts", 0)
        counterfactuals.append({
            "capability": "comparison",
            "minimal_change": (
                f"Resolve {n_conflicts} truth conflict(s) that prevent "
                f"cross-country comparison."
            ),
            "difficulty": "HIGH" if n_conflicts > 2 else "MODERATE",
            "requires": ["conflict_resolution"],
        })

    # ── Analyze confidence ──
    confidence = country_json.get("confidence", 1.0)
    if isinstance(confidence, (int, float)) and confidence < 0.5:
        constraint = {
            "capability": "high_confidence",
            "blocked_by": "data_quality",
            "current_value": confidence,
            "blocking_reason": f"Confidence {confidence} below 0.5 threshold.",
        }
        binding_constraints.append(constraint)

        counterfactuals.append({
            "capability": "high_confidence",
            "minimal_change": (
                f"Improve data quality to raise confidence from "
                f"{confidence} to at least 0.5."
            ),
            "difficulty": "MODERATE",
            "requires": ["data_quality_improvement"],
        })

    # ── Analyze publishability ──
    pub = country_json.get("publishability", {})
    pub_status = pub.get("publishability_status", "PUBLISHABLE")
    if pub_status in ("NOT_PUBLISHABLE", "RESTRICTED"):
        blockers = pub.get("blockers", [])
        constraint = {
            "capability": "publication",
            "blocked_by": "publishability",
            "current_value": pub_status,
            "blocking_reason": f"Publishability: {pub_status}. Blockers: {blockers}",
        }
        binding_constraints.append(constraint)

        counterfactuals.append({
            "capability": "publication",
            "minimal_change": (
                f"Address {len(blockers)} blocker(s): {blockers}. "
                f"Each blocker must be individually resolved."
            ),
            "difficulty": "HIGH",
            "requires": ["blocker_resolution"],
        })

    # ── Analyze policy claims ──
    truth_status = truth.get("truth_status", "VALID")
    if truth_status != "VALID":
        constraint = {
            "capability": "policy_claim",
            "blocked_by": "truth_status",
            "current_value": truth_status,
            "blocking_reason": (
                f"Truth status {truth_status} prevents policy claims. "
                f"Only VALID truth status permits policy claims."
            ),
        }
        binding_constraints.append(constraint)

        counterfactuals.append({
            "capability": "policy_claim",
            "minimal_change": (
                f"Resolve all truth conflicts to achieve VALID truth status "
                f"(currently {truth_status})."
            ),
            "difficulty": "HIGH",
            "requires": ["truth_status_upgrade"],
        })

    return {
        "country": country,
        "counterfactual_status": "COMPLETE",
        "n_binding_constraints": len(binding_constraints),
        "n_counterfactuals": len(counterfactuals),
        "binding_constraints": binding_constraints,
        "counterfactuals": counterfactuals,
        "currently_blocked_capabilities": [
            c["capability"] for c in binding_constraints
        ],
        "honesty_note": (
            f"Counterfactual replay for {country}: {len(binding_constraints)} "
            f"binding constraint(s), {len(counterfactuals)} counterfactual(s). "
            f"Blocked capabilities: "
            f"{[c['capability'] for c in binding_constraints] or 'none'}. "
            f"This analysis shows the MINIMUM changes needed to enable "
            f"each blocked capability."
        ),
    }
