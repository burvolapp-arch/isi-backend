"""
backend.failure_visibility — Failure Visibility Engine (Anti-Bullshit Layer)

SECTION 6 of Final Hardening Pass.

Problem addressed:
    The system is internally rigorous but could still be misinterpreted
    as "fully valid" by consumers who don't read governance fields.
    Every limitation, construct flag, alignment issue, and invariant
    violation MUST be surfaced in a way that cannot be ignored.

This module produces:
    - validity_warnings[]  — issues that limit how output should be used
    - construct_flags[]    — construct substitution and validity issues
    - alignment_flags[]    — external alignment issues
    - invariant_violations[] — internal consistency violations

Each entry includes:
    - severity (WARNING, ERROR, CRITICAL)
    - rule_id
    - explanation

Design contract:
    - No consumer can import ISI output without seeing limitations.
    - Warnings are ATTACHED to the data, not in a separate file.
    - Severity classification is machine-readable.
    - The system self-degrades rather than silently passing weak data.

Honesty note:
    This module exists because even rigorous systems can be misused.
    A policy-maker who only reads the composite score and ignores
    governance tiers, construct warnings, and alignment flags would
    reach dangerously wrong conclusions. This module makes that
    impossible by embedding warnings INTO the output.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# FLAG SEVERITY
# ═══════════════════════════════════════════════════════════════════════════

class FlagSeverity:
    """Severity levels for visibility flags."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


VALID_FLAG_SEVERITIES = frozenset({
    FlagSeverity.INFO,
    FlagSeverity.WARNING,
    FlagSeverity.ERROR,
    FlagSeverity.CRITICAL,
})


# ═══════════════════════════════════════════════════════════════════════════
# FLAG CONSTRUCTORS
# ═══════════════════════════════════════════════════════════════════════════

def _flag(
    severity: str,
    rule_id: str,
    category: str,
    explanation: str,
    **extra: Any,
) -> dict[str, Any]:
    """Construct a canonical visibility flag."""
    entry: dict[str, Any] = {
        "severity": severity,
        "rule_id": rule_id,
        "category": category,
        "explanation": explanation,
    }
    entry.update(extra)
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# VALIDITY WARNINGS — GENERAL USAGE LIMITATIONS
# ═══════════════════════════════════════════════════════════════════════════

def collect_validity_warnings(
    country: str,
    governance_result: dict[str, Any] | None = None,
    decision_usability: dict[str, Any] | None = None,
    construct_enforcement: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect validity warnings for a country's output.

    These are conditions that limit how ISI output should be used.
    """
    warnings: list[dict[str, Any]] = []

    # Governance-based warnings
    if governance_result:
        tier = governance_result.get("governance_tier", "UNKNOWN")
        if tier == "NON_COMPARABLE":
            warnings.append(_flag(
                severity=FlagSeverity.CRITICAL,
                rule_id="VW-001",
                category="validity",
                explanation=(
                    f"Country {country} is NON_COMPARABLE. "
                    f"ISI output should NOT be used for any comparative purpose."
                ),
                governance_tier=tier,
            ))
        elif tier == "LOW_CONFIDENCE":
            warnings.append(_flag(
                severity=FlagSeverity.ERROR,
                rule_id="VW-002",
                category="validity",
                explanation=(
                    f"Country {country} is LOW_CONFIDENCE. "
                    f"ISI output provides directional insight only."
                ),
                governance_tier=tier,
            ))
        elif tier == "PARTIALLY_COMPARABLE":
            warnings.append(_flag(
                severity=FlagSeverity.WARNING,
                rule_id="VW-003",
                category="validity",
                explanation=(
                    f"Country {country} is PARTIALLY_COMPARABLE. "
                    f"Cross-country comparison requires documented caveats."
                ),
                governance_tier=tier,
            ))

        # Producer inversions
        n_inverted = governance_result.get("n_producer_inverted_axes", 0)
        if n_inverted >= 2:
            warnings.append(_flag(
                severity=FlagSeverity.ERROR,
                rule_id="VW-004",
                category="validity",
                explanation=(
                    f"Country {country} has {n_inverted} producer-inverted "
                    f"axes. Import concentration metric is inverted for "
                    f"these axes."
                ),
                n_inverted_axes=n_inverted,
            ))
        elif n_inverted == 1:
            warnings.append(_flag(
                severity=FlagSeverity.WARNING,
                rule_id="VW-004",
                category="validity",
                explanation=(
                    f"Country {country} has 1 producer-inverted axis."
                ),
                n_inverted_axes=n_inverted,
            ))

    # Decision usability warnings
    if decision_usability:
        usab_class = decision_usability.get("decision_usability_class")
        if usab_class == "INVALID_FOR_COMPARISON":
            warnings.append(_flag(
                severity=FlagSeverity.CRITICAL,
                rule_id="VW-005",
                category="validity",
                explanation=(
                    f"Country {country} classified as INVALID_FOR_COMPARISON. "
                    f"DO NOT use for any policy decision."
                ),
                usability_class=usab_class,
            ))
        elif usab_class == "STRUCTURALLY_LIMITED":
            warnings.append(_flag(
                severity=FlagSeverity.ERROR,
                rule_id="VW-006",
                category="validity",
                explanation=(
                    f"Country {country} is STRUCTURALLY_LIMITED. "
                    f"Directional insight only — not suitable for ranking."
                ),
                usability_class=usab_class,
            ))

    # Construct enforcement warnings
    if construct_enforcement:
        n_invalid = construct_enforcement.get("n_invalid", 0)
        n_degraded = construct_enforcement.get("n_degraded", 0)
        if n_invalid > 0:
            warnings.append(_flag(
                severity=FlagSeverity.ERROR,
                rule_id="VW-007",
                category="validity",
                explanation=(
                    f"Country {country} has {n_invalid} axis(es) with "
                    f"INVALID construct validity. These axes are excluded "
                    f"from composite."
                ),
                n_invalid_axes=n_invalid,
            ))
        if n_degraded > 0:
            warnings.append(_flag(
                severity=FlagSeverity.WARNING,
                rule_id="VW-008",
                category="validity",
                explanation=(
                    f"Country {country} has {n_degraded} axis(es) with "
                    f"DEGRADED construct validity. Composite weight is capped."
                ),
                n_degraded_axes=n_degraded,
            ))

    return warnings


# ═══════════════════════════════════════════════════════════════════════════
# CONSTRUCT FLAGS — MEASUREMENT VALIDITY ISSUES
# ═══════════════════════════════════════════════════════════════════════════

def collect_construct_flags(
    country: str,
    readiness_matrix: list[dict[str, Any]] | None = None,
    construct_enforcement: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect construct validity flags for a country.

    These flag axes where the measurement does not match the axis label.
    """
    flags: list[dict[str, Any]] = []

    if readiness_matrix:
        for rm in readiness_matrix:
            axis_id = rm.get("axis_id")
            if rm.get("construct_substitution"):
                flags.append(_flag(
                    severity=FlagSeverity.WARNING,
                    rule_id="CF-001",
                    category="construct",
                    explanation=(
                        f"Axis {axis_id} uses CONSTRUCT SUBSTITUTION for "
                        f"{country}. Measurement does not capture what "
                        f"the axis label claims."
                    ),
                    axis_id=axis_id,
                    readiness_level=rm.get("readiness_level"),
                ))
            if rm.get("proxy_used"):
                flags.append(_flag(
                    severity=FlagSeverity.INFO,
                    rule_id="CF-002",
                    category="construct",
                    explanation=(
                        f"Axis {axis_id} uses PROXY data for {country}. "
                        f"Proxy measures a related but different construct."
                    ),
                    axis_id=axis_id,
                ))

    if construct_enforcement:
        for ax_result in construct_enforcement.get("per_axis", []):
            cv_class = ax_result.get("construct_validity_class")
            if cv_class == "CONSTRUCT_INVALID":
                flags.append(_flag(
                    severity=FlagSeverity.CRITICAL,
                    rule_id="CF-003",
                    category="construct",
                    explanation=(
                        f"Axis {ax_result['axis_id']} has INVALID construct "
                        f"validity — excluded from composite. "
                        f"Rules: {', '.join(ax_result.get('applied_rules', []))}."
                    ),
                    axis_id=ax_result["axis_id"],
                    applied_rules=ax_result.get("applied_rules", []),
                ))

    return flags


# ═══════════════════════════════════════════════════════════════════════════
# ALIGNMENT FLAGS — EXTERNAL VALIDATION ISSUES
# ═══════════════════════════════════════════════════════════════════════════

def collect_alignment_flags(
    country: str,
    external_validation: dict[str, Any] | None = None,
    sensitivity_result: dict[str, Any] | None = None,
    mapping_audit_results: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect alignment flags for a country.

    These flag issues with external benchmark alignment.
    """
    flags: list[dict[str, Any]] = []

    if external_validation:
        overall = external_validation.get("overall_alignment", "NO_DATA")

        if overall == "DIVERGENT":
            flags.append(_flag(
                severity=FlagSeverity.ERROR,
                rule_id="AF-001",
                category="alignment",
                explanation=(
                    f"Country {country} DIVERGES from external benchmarks "
                    f"on majority of compared axes. ISI output may not "
                    f"reflect external reality."
                ),
                overall_alignment=overall,
            ))
        elif overall == "NO_DATA":
            flags.append(_flag(
                severity=FlagSeverity.WARNING,
                rule_id="AF-002",
                category="alignment",
                explanation=(
                    f"Country {country} has NO external benchmark data. "
                    f"ISI output is internally consistent but NOT "
                    f"empirically validated."
                ),
            ))
        elif overall == "WEAKLY_ALIGNED":
            flags.append(_flag(
                severity=FlagSeverity.INFO,
                rule_id="AF-003",
                category="alignment",
                explanation=(
                    f"Country {country} shows MIXED alignment with "
                    f"external benchmarks."
                ),
            ))

        # Per-axis divergence flags
        for aa in external_validation.get("per_axis_summary", []):
            if aa.get("alignment_status") == "NO_EXTERNAL_DATA":
                flags.append(_flag(
                    severity=FlagSeverity.INFO,
                    rule_id="AF-004",
                    category="alignment",
                    explanation=(
                        f"Axis {aa['axis_id']}: no external benchmark data "
                        f"available for comparison."
                    ),
                    axis_id=aa["axis_id"],
                ))

    # Sensitivity flags
    if sensitivity_result:
        stability = sensitivity_result.get("stability_class")
        if stability == "ALIGNMENT_UNSTABLE":
            flags.append(_flag(
                severity=FlagSeverity.ERROR,
                rule_id="AF-005",
                category="alignment",
                explanation=(
                    f"Country {country} alignment is UNSTABLE — "
                    f"changes under minimal perturbation. "
                    f"Empirical grounding claim is NOT supported."
                ),
                stability_class=stability,
            ))
        elif stability == "ALIGNMENT_SENSITIVE":
            flags.append(_flag(
                severity=FlagSeverity.WARNING,
                rule_id="AF-006",
                category="alignment",
                explanation=(
                    f"Country {country} alignment is SENSITIVE — "
                    f"changes under some perturbations."
                ),
                stability_class=stability,
            ))

    # Mapping audit flags
    if mapping_audit_results:
        for bm_id, audit in mapping_audit_results.items():
            validity = audit.get("mapping_validity")
            if validity == "INVALID_MAPPING":
                flags.append(_flag(
                    severity=FlagSeverity.CRITICAL,
                    rule_id="AF-007",
                    category="alignment",
                    explanation=(
                        f"Benchmark {bm_id} has INVALID mapping. "
                        f"Alignment results for this benchmark are "
                        f"structurally meaningless."
                    ),
                    benchmark_id=bm_id,
                    mapping_validity=validity,
                ))
            elif validity == "WEAK_MAPPING":
                flags.append(_flag(
                    severity=FlagSeverity.INFO,
                    rule_id="AF-008",
                    category="alignment",
                    explanation=(
                        f"Benchmark {bm_id} has WEAK mapping. "
                        f"Alignment should be interpreted with caveats."
                    ),
                    benchmark_id=bm_id,
                    mapping_validity=validity,
                ))

    return flags


# ═══════════════════════════════════════════════════════════════════════════
# INVARIANT VIOLATION FLAGS
# ═══════════════════════════════════════════════════════════════════════════

def collect_invariant_flags(
    invariant_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Convert invariant violations to visibility flags.

    Translates internal invariant violation records into the unified
    flag format.
    """
    flags: list[dict[str, Any]] = []

    if invariant_result is None:
        return flags

    for violation in invariant_result.get("violations", []):
        severity_map = {
            "WARNING": FlagSeverity.WARNING,
            "ERROR": FlagSeverity.ERROR,
            "CRITICAL": FlagSeverity.CRITICAL,
        }
        sev = severity_map.get(
            violation.get("severity", "WARNING"),
            FlagSeverity.WARNING,
        )

        flags.append(_flag(
            severity=sev,
            rule_id=violation.get("invariant_id", "UNKNOWN"),
            category="invariant",
            explanation=violation.get("description", "Invariant violation"),
            invariant_type=violation.get("type"),
            affected_country=violation.get("affected_country"),
            evidence=violation.get("evidence"),
        ))

    return flags


# ═══════════════════════════════════════════════════════════════════════════
# UNIFIED VISIBILITY BLOCK
# ═══════════════════════════════════════════════════════════════════════════

def build_visibility_block(
    country: str,
    governance_result: dict[str, Any] | None = None,
    decision_usability: dict[str, Any] | None = None,
    construct_enforcement: dict[str, Any] | None = None,
    readiness_matrix: list[dict[str, Any]] | None = None,
    external_validation: dict[str, Any] | None = None,
    sensitivity_result: dict[str, Any] | None = None,
    mapping_audit_results: dict[str, dict[str, Any]] | None = None,
    invariant_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the unified failure visibility block for export.

    This is the anti-bullshit layer — it aggregates ALL flags,
    warnings, and issues into a single machine-readable block
    that MUST be attached to every country output.

    Returns:
        Visibility block with all flag categories and severity summary.
    """
    validity_warnings = collect_validity_warnings(
        country, governance_result, decision_usability, construct_enforcement,
    )
    construct_flags = collect_construct_flags(
        country, readiness_matrix, construct_enforcement,
    )
    alignment_flags = collect_alignment_flags(
        country, external_validation, sensitivity_result, mapping_audit_results,
    )
    invariant_violations = collect_invariant_flags(invariant_result)

    all_flags = validity_warnings + construct_flags + alignment_flags + invariant_violations

    # Severity summary
    n_critical = sum(1 for f in all_flags if f["severity"] == FlagSeverity.CRITICAL)
    n_error = sum(1 for f in all_flags if f["severity"] == FlagSeverity.ERROR)
    n_warning = sum(1 for f in all_flags if f["severity"] == FlagSeverity.WARNING)
    n_info = sum(1 for f in all_flags if f["severity"] == FlagSeverity.INFO)

    # Overall trust level
    if n_critical > 0:
        trust_level = "DO_NOT_USE"
        trust_explanation = (
            f"CRITICAL issues detected ({n_critical}). "
            f"ISI output for {country} should NOT be used for any purpose."
        )
    elif n_error > 0:
        trust_level = "USE_WITH_EXTREME_CAUTION"
        trust_explanation = (
            f"Significant issues detected ({n_error} errors). "
            f"ISI output for {country} provides directional insight only."
        )
    elif n_warning > 0:
        trust_level = "USE_WITH_DOCUMENTED_CAVEATS"
        trust_explanation = (
            f"Warnings detected ({n_warning}). "
            f"ISI output for {country} is usable with documented limitations."
        )
    else:
        trust_level = "STRUCTURALLY_SOUND"
        trust_explanation = (
            f"No significant issues detected for {country}. "
            f"Standard methodological caveats apply."
        )

    return {
        "country": country,
        "trust_level": trust_level,
        "trust_explanation": trust_explanation,
        "severity_summary": {
            "n_critical": n_critical,
            "n_error": n_error,
            "n_warning": n_warning,
            "n_info": n_info,
            "total_flags": len(all_flags),
        },
        "validity_warnings": validity_warnings,
        "construct_flags": construct_flags,
        "alignment_flags": alignment_flags,
        "invariant_violations": invariant_violations,
        "honesty_note": (
            "This block contains ALL known limitations, issues, and "
            "warnings for this country's ISI output. Consumers MUST "
            "check trust_level before using the output. Ignoring "
            "CRITICAL or ERROR flags constitutes methodological "
            "malpractice."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# DECISION USABILITY HARDENING (SECTION 5)
# ═══════════════════════════════════════════════════════════════════════════

def should_downgrade_usability(
    visibility_block: dict[str, Any],
    current_usability_class: str,
) -> dict[str, Any]:
    """Determine if visibility flags require usability downgrade.

    SECTION 5: Strict enforcement of hard constraints.

    IF:
    - empirical_alignment == CONTRADICTED
    - OR construct_validity == INVALID (any axis)
    - OR invariants CRITICAL violated

    THEN:
    → DecisionUsability = INVALID_FOR_COMPARISON

    Args:
        visibility_block: Output of build_visibility_block().
        current_usability_class: Current DecisionUsabilityClass.

    Returns:
        Downgrade decision with new class and justification.
    """
    reasons: list[str] = []
    downgrade_to = current_usability_class

    n_critical = visibility_block["severity_summary"]["n_critical"]
    n_error = visibility_block["severity_summary"]["n_error"]

    # Check for CRITICAL construct flags → INVALID
    critical_construct = [
        f for f in visibility_block["construct_flags"]
        if f["severity"] == FlagSeverity.CRITICAL
    ]
    if critical_construct:
        downgrade_to = "INVALID_FOR_COMPARISON"
        reasons.append(
            f"{len(critical_construct)} CRITICAL construct validity issue(s)"
        )

    # Check for CRITICAL invariant violations → INVALID
    critical_invariants = [
        f for f in visibility_block["invariant_violations"]
        if f["severity"] == FlagSeverity.CRITICAL
    ]
    if critical_invariants:
        downgrade_to = "INVALID_FOR_COMPARISON"
        reasons.append(
            f"{len(critical_invariants)} CRITICAL invariant violation(s)"
        )

    # Check for alignment DIVERGENCE → at minimum STRUCTURALLY_LIMITED
    divergent_flags = [
        f for f in visibility_block["alignment_flags"]
        if f.get("rule_id") == "AF-001"  # Overall divergence
    ]
    if divergent_flags and downgrade_to not in ("INVALID_FOR_COMPARISON",):
        if downgrade_to in ("TRUSTED_COMPARABLE", "CONDITIONALLY_USABLE"):
            downgrade_to = "STRUCTURALLY_LIMITED"
            reasons.append("Alignment DIVERGENT from external benchmarks")

    # Check alignment UNSTABLE → downgrade
    unstable_flags = [
        f for f in visibility_block["alignment_flags"]
        if f.get("rule_id") == "AF-005"
    ]
    if unstable_flags and downgrade_to not in ("INVALID_FOR_COMPARISON", "STRUCTURALLY_LIMITED"):
        downgrade_to = "STRUCTURALLY_LIMITED"
        reasons.append("Alignment UNSTABLE under perturbation")

    downgraded = downgrade_to != current_usability_class

    return {
        "downgraded": downgraded,
        "original_class": current_usability_class,
        "final_class": downgrade_to,
        "reasons": reasons,
        "n_critical_flags": n_critical,
        "n_error_flags": n_error,
        "justification": (
            f"Usability downgraded from {current_usability_class} to "
            f"{downgrade_to}: {'; '.join(reasons)}"
            if downgraded
            else f"No downgrade required. Current class: {current_usability_class}."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# RANKING EXCLUSION
# ═══════════════════════════════════════════════════════════════════════════

def should_exclude_from_ranking(
    visibility_block: dict[str, Any],
) -> dict[str, Any]:
    """Determine if a country should be excluded from rankings.

    Countries with INVALID usability MUST NOT appear in rankings.
    This is the final enforcement gate.
    """
    trust = visibility_block.get("trust_level", "UNKNOWN")
    n_critical = visibility_block["severity_summary"]["n_critical"]

    exclude = trust == "DO_NOT_USE" or n_critical > 0

    return {
        "exclude_from_ranking": exclude,
        "trust_level": trust,
        "n_critical_flags": n_critical,
        "reason": (
            f"EXCLUDED: trust_level={trust}, {n_critical} critical flags."
            if exclude
            else f"INCLUDED: trust_level={trust}."
        ),
    }
