"""
backend.invariants — Structural Invariants Engine

SYSTEM 1: Detects when the system produces internally inconsistent outputs,
even when all computations are technically correct.

Three classes of invariants:
    1. CROSS_AXIS — logical contradictions across axes
    2. GOVERNANCE — governance output consistency
    3. TEMPORAL — cross-version snapshot consistency

Each violation produces a structured record with:
    invariant_id, type, severity, description, affected_country, evidence

Design contract:
    - Invariant checks are PURE FUNCTIONS — no side effects.
    - All checks are deterministic and auditable.
    - CRITICAL violations automatically downgrade DecisionUsabilityClass.
    - Invariant results are attached to country JSON and ISI export.
    - This module does NOT modify scores.

Honesty note:
    Invariants verify INTERNAL CONSISTENCY, not external validity.
    A system can be perfectly internally consistent and still wrong.
    Invariants catch structural anomalies — they do not validate truth.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# INVARIANT TYPES AND SEVERITY
# ═══════════════════════════════════════════════════════════════════════════

class InvariantType:
    """Classification of invariant checks."""
    CROSS_AXIS = "CROSS_AXIS"
    GOVERNANCE = "GOVERNANCE"
    TEMPORAL = "TEMPORAL"
    EXTERNAL_VALIDITY = "EXTERNAL_VALIDITY"
    CONSTRUCT_ENFORCEMENT = "CONSTRUCT_ENFORCEMENT"
    FAILURE_VISIBILITY = "FAILURE_VISIBILITY"
    AUTHORITY_CONSISTENCY = "AUTHORITY_CONSISTENCY"
    REALITY_CONFLICT = "REALITY_CONFLICT"
    PIPELINE_INTEGRITY = "PIPELINE_INTEGRITY"
    RUNTIME = "RUNTIME"
    EPISTEMIC_MONOTONICITY = "EPISTEMIC_MONOTONICITY"


VALID_INVARIANT_TYPES = frozenset({
    InvariantType.CROSS_AXIS,
    InvariantType.GOVERNANCE,
    InvariantType.TEMPORAL,
    InvariantType.EXTERNAL_VALIDITY,
    InvariantType.CONSTRUCT_ENFORCEMENT,
    InvariantType.FAILURE_VISIBILITY,
    InvariantType.AUTHORITY_CONSISTENCY,
    InvariantType.REALITY_CONFLICT,
    InvariantType.PIPELINE_INTEGRITY,
    InvariantType.RUNTIME,
    InvariantType.EPISTEMIC_MONOTONICITY,
})


class InvariantSeverity:
    """Severity of an invariant violation."""
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


VALID_SEVERITIES = frozenset({
    InvariantSeverity.WARNING,
    InvariantSeverity.ERROR,
    InvariantSeverity.CRITICAL,
})


# ═══════════════════════════════════════════════════════════════════════════
# INVARIANT REGISTRY — every invariant has a unique ID and rule
# ═══════════════════════════════════════════════════════════════════════════

INVARIANT_REGISTRY: list[dict[str, str]] = [
    # ── Cross-Axis Invariants ──
    {
        "invariant_id": "CA-001",
        "type": InvariantType.CROSS_AXIS,
        "name": "Logistics Divergence from Goods-Based Axes",
        "description": (
            "If logistics concentration (Axis 6) increases while ALL "
            "goods-based axes (2, 3, 5) decrease, the pattern is suspicious — "
            "logistics should co-move with trade flows."
        ),
    },
    {
        "invariant_id": "CA-002",
        "type": InvariantType.CROSS_AXIS,
        "name": "Producer Country High-Import Anomaly",
        "description": (
            "A country with registered producer inversions should NOT show "
            "high import concentration (score > 0.6) on inverted axes."
        ),
    },
    {
        "invariant_id": "CA-003",
        "type": InvariantType.CROSS_AXIS,
        "name": "Low Axis Majority with High Composite",
        "description": (
            "If 4+ out of 6 axes have scores < 0.15, the composite should "
            "not exceed 0.25. A high composite with mostly low axes signals "
            "that one axis is dominating the unweighted mean."
        ),
    },
    {
        "invariant_id": "CA-004",
        "type": InvariantType.CROSS_AXIS,
        "name": "Uniform Score Anomaly",
        "description": (
            "If all 6 axis scores are within 0.02 of each other, this "
            "is structurally improbable — different data sources measuring "
            "different constructs should not produce identical values."
        ),
    },
    # ── Governance Consistency Invariants ──
    {
        "invariant_id": "GOV-001",
        "type": InvariantType.GOVERNANCE,
        "name": "Ranking Eligible but Wrong Tier",
        "description": (
            "ranking_eligible=True is only valid for FULLY_COMPARABLE "
            "or PARTIALLY_COMPARABLE tiers."
        ),
    },
    {
        "invariant_id": "GOV-002",
        "type": InvariantType.GOVERNANCE,
        "name": "Cross-Comparable with Excessive Inversions",
        "description": (
            "cross_country_comparable=True should not be possible "
            "with n_producer_inverted_axes > MAX_INVERTED threshold."
        ),
    },
    {
        "invariant_id": "GOV-003",
        "type": InvariantType.GOVERNANCE,
        "name": "LOW_CONFIDENCE but Ranked",
        "description": (
            "A country at LOW_CONFIDENCE or NON_COMPARABLE must not "
            "have ranking_eligible=True."
        ),
    },
    {
        "invariant_id": "GOV-004",
        "type": InvariantType.GOVERNANCE,
        "name": "Composite Defensible but Non-Comparable",
        "description": (
            "composite_defensible=True should not coexist with "
            "governance_tier=NON_COMPARABLE."
        ),
    },
    {
        "invariant_id": "GOV-005",
        "type": InvariantType.GOVERNANCE,
        "name": "Confidence–Tier Mismatch",
        "description": (
            "Mean axis confidence below MIN_MEAN_CONFIDENCE_FOR_RANKING "
            "but governance tier is FULLY_COMPARABLE."
        ),
    },
    {
        "invariant_id": "GOV-006",
        "type": InvariantType.GOVERNANCE,
        "name": "Sanctions Flag but High Tier",
        "description": (
            "A country with SANCTIONS_DISTORTION flag on any axis "
            "must not be FULLY_COMPARABLE or PARTIALLY_COMPARABLE."
        ),
    },
    # ── Temporal / Snapshot Invariants ──
    {
        "invariant_id": "TEMP-001",
        "type": InvariantType.TEMPORAL,
        "name": "Large Rank Shift without Input Change",
        "description": (
            "Rank change > 5 positions between versions without any "
            "axis score changing by > 0.05."
        ),
    },
    {
        "invariant_id": "TEMP-002",
        "type": InvariantType.TEMPORAL,
        "name": "Composite Change without Axis Change",
        "description": (
            "Composite changed by > 0.02 but no individual axis "
            "changed by > 0.01."
        ),
    },
    {
        "invariant_id": "TEMP-003",
        "type": InvariantType.TEMPORAL,
        "name": "Governance Tier Change without Structural Cause",
        "description": (
            "Governance tier changed between versions without an "
            "axis confidence change, inversion change, or severity change."
        ),
    },
    # ── External Validity Invariants ──
    {
        "invariant_id": "EXT-001",
        "type": InvariantType.EXTERNAL_VALIDITY,
        "name": "Benchmark Divergence with High Confidence",
        "description": (
            "If ISI assigns HIGH confidence to an axis but external "
            "benchmarks show DIVERGENT alignment on that axis, the "
            "confidence assessment may be internally valid but "
            "empirically unsupported."
        ),
    },
    {
        "invariant_id": "EXT-002",
        "type": InvariantType.EXTERNAL_VALIDITY,
        "name": "Trusted-Comparable without Empirical Grounding",
        "description": (
            "A country classified as TRUSTED_COMPARABLE (highest "
            "decision usability) but with no external benchmark "
            "comparisons has a structurally sound but empirically "
            "unverified classification."
        ),
    },
    {
        "invariant_id": "EXT-003",
        "type": InvariantType.EXTERNAL_VALIDITY,
        "name": "Producer Inversion Unconfirmed by External Data",
        "description": (
            "A country is in PRODUCER_INVERSION_REGISTRY but no "
            "external benchmark (e.g., SIPRI MILEX) confirms the "
            "inversion. The registry entry may be outdated."
        ),
    },
    {
        "invariant_id": "EXT-004",
        "type": InvariantType.EXTERNAL_VALIDITY,
        "name": "Majority Axes Divergent from Benchmarks",
        "description": (
            "If a country shows DIVERGENT alignment on more than "
            "half of compared axes, the overall ISI output for "
            "that country is empirically suspect."
        ),
    },
    # ── Construct Enforcement Invariants (Final Hardening) ──
    {
        "invariant_id": "CE-INV-001",
        "type": InvariantType.CONSTRUCT_ENFORCEMENT,
        "name": "No Invalid Construct in Composite",
        "description": (
            "If any axis has CONSTRUCT_INVALID validity, it MUST NOT "
            "contribute to the composite score. If it does, the "
            "composite is structurally unsound."
        ),
    },
    {
        "invariant_id": "CE-INV-002",
        "type": InvariantType.CONSTRUCT_ENFORCEMENT,
        "name": "Logistics Proxy Requires Alignment",
        "description": (
            "If Axis 6 (logistics) uses a proxy construct, it MUST "
            "show at least WEAKLY_ALIGNED external alignment to be "
            "considered CONSTRUCT_VALID. Without alignment evidence, "
            "the proxy is unvalidated."
        ),
    },
    {
        "invariant_id": "CE-INV-003",
        "type": InvariantType.CONSTRUCT_ENFORCEMENT,
        "name": "No Alignment with Invalid Mapping",
        "description": (
            "If a benchmark has INVALID_MAPPING, alignment results "
            "for that benchmark MUST be STRUCTURALLY_INCOMPARABLE. "
            "Claiming alignment with an invalid mapping is "
            "structurally meaningless."
        ),
    },
    {
        "invariant_id": "CE-INV-004",
        "type": InvariantType.CONSTRUCT_ENFORCEMENT,
        "name": "Alignment Must Be Stable for High Trust",
        "description": (
            "If alignment is classified as ALIGNMENT_UNSTABLE by "
            "sensitivity testing, the country MUST NOT have "
            "decision usability of TRUSTED_COMPARABLE."
        ),
    },
    # ── Failure Visibility Invariants (Institutionalization Pass) ──
    {
        "invariant_id": "FV-001",
        "type": InvariantType.FAILURE_VISIBILITY,
        "name": "Visibility Block Required for Export",
        "description": (
            "Every exported country JSON MUST include a failure "
            "visibility block. Export without embedded limitations "
            "is a methodological violation."
        ),
    },
    {
        "invariant_id": "FV-002",
        "type": InvariantType.FAILURE_VISIBILITY,
        "name": "Trust Level Consistent with Usability",
        "description": (
            "visibility trust_level MUST be consistent with "
            "decision_usability_class. DO_NOT_USE → INVALID_FOR_COMPARISON."
        ),
    },
    # ── Authority Consistency Invariants (Institutionalization Pass) ──
    {
        "invariant_id": "AUTH-001",
        "type": InvariantType.AUTHORITY_CONSISTENCY,
        "name": "Structural Benchmark Contradiction",
        "description": (
            "If a STRUCTURAL-authority benchmark CONTRADICTS a "
            "HIGH_CONFIDENCE benchmark on the same axis, the system "
            "MUST flag the conflict and downgrade alignment confidence."
        ),
    },
    {
        "invariant_id": "AUTH-002",
        "type": InvariantType.AUTHORITY_CONSISTENCY,
        "name": "Weighted Score Must Reflect Hierarchy",
        "description": (
            "weighted_alignment_score MUST weight STRUCTURAL benchmarks "
            "at 1.0, HIGH_CONFIDENCE at 0.7, SUPPORTING at 0.4. "
            "Any deviation is a hierarchy violation."
        ),
    },
    # ── Reality Conflict Invariants (Institutionalization Pass) ──
    {
        "invariant_id": "RC-001",
        "type": InvariantType.REALITY_CONFLICT,
        "name": "Governance-Alignment Reality Conflict",
        "description": (
            "If governance tier is FULLY_COMPARABLE or PARTIALLY_COMPARABLE "
            "but external alignment is DIVERGENT, the country output MUST "
            "contain a reality_conflict entry. Not a flag, not a log — a "
            "STRUCTURAL entry."
        ),
    },
    {
        "invariant_id": "RC-002",
        "type": InvariantType.REALITY_CONFLICT,
        "name": "Ranking-Eligible with Divergent Alignment",
        "description": (
            "If a country is ranking_eligible=True but external alignment "
            "is DIVERGENT, the reality_conflicts block MUST contain a "
            "RANKING_ELIGIBILITY_DIVERGENCE entry."
        ),
    },
    {
        "invariant_id": "RC-003",
        "type": InvariantType.REALITY_CONFLICT,
        "name": "Usability-Alignment Contradiction",
        "description": (
            "If decision usability is TRUSTED_COMPARABLE but empirical "
            "alignment is EMPIRICALLY_CONTRADICTED, this MUST be flagged "
            "as a CRITICAL reality conflict."
        ),
    },
    # ── Pipeline Integrity Invariants (Final Closure Pass) ──
    {
        "invariant_id": "INV-PIPELINE-001",
        "type": InvariantType.PIPELINE_INTEGRITY,
        "name": "No Missing Layer Outputs",
        "description": (
            "Every required pipeline layer must produce output. "
            "Missing layer outputs indicate structural pipeline failure."
        ),
    },
    {
        "invariant_id": "INV-ENFORCEMENT-001",
        "type": InvariantType.PIPELINE_INTEGRITY,
        "name": "CRITICAL Flags Must Have Consequences",
        "description": (
            "If any layer produces a CRITICAL flag (has_critical, "
            "trust_level=DO_NOT_USE, composite_producible=False), "
            "the enforcement matrix MUST have produced corresponding "
            "actions. A CRITICAL flag without enforcement is decorative."
        ),
    },
    {
        "invariant_id": "INV-TRUTH-001",
        "type": InvariantType.PIPELINE_INTEGRITY,
        "name": "No Conflicting Final States",
        "description": (
            "The truth resolver's final values must be internally "
            "consistent: NON_COMPARABLE cannot be ranking_eligible, "
            "LOW_CONFIDENCE cannot be ranking_eligible, and "
            "composite_suppressed must agree with tier."
        ),
    },
    {
        "invariant_id": "INV-EXPORT-001",
        "type": InvariantType.PIPELINE_INTEGRITY,
        "name": "Export Must Reflect Truth Resolver",
        "description": (
            "If truth_resolution is present in the export, its "
            "final_governance_tier, final_ranking_eligible, and "
            "final_composite_suppressed must match the effective "
            "values in the country JSON."
        ),
    },
    {
        "invariant_id": "INV-NO-DECORATION-001",
        "type": InvariantType.PIPELINE_INTEGRITY,
        "name": "No Unused Modules",
        "description": (
            "Every backend module that defines detection or "
            "enforcement functions must be imported and executed "
            "in the production pipeline. A module that exists "
            "but is never called is decorative."
        ),
    },
    # ── Runtime Invariants (Production Hardening Pass) ──
    {
        "invariant_id": "INV-RUNTIME-001",
        "type": InvariantType.RUNTIME,
        "name": "No Silent Failures",
        "description": (
            "Every layer failure must be explicitly recorded in "
            "the pipeline runtime status. A layer that fails but "
            "is not listed in degraded_layers or failed_layers "
            "is a silent failure."
        ),
    },
    {
        "invariant_id": "INV-RUNTIME-002",
        "type": InvariantType.RUNTIME,
        "name": "Degraded Must Propagate",
        "description": (
            "If any layer is degraded, the pipeline_status MUST "
            "be DEGRADED or FAILED. A HEALTHY pipeline with "
            "degraded layers is a lie."
        ),
    },
    {
        "invariant_id": "INV-VERSION-001",
        "type": InvariantType.RUNTIME,
        "name": "Versions Must Be Present",
        "description": (
            "Every export must contain version_info with "
            "methodology_version, pipeline_version, "
            "truth_logic_version, and enforcement_version. "
            "Missing versions make reproducibility impossible."
        ),
    },
    {
        "invariant_id": "INV-EXPORT-002",
        "type": InvariantType.RUNTIME,
        "name": "Runtime Status Must Be Included",
        "description": (
            "Every export must contain a runtime_status block "
            "with pipeline_status, degraded_layers, and "
            "failed_layers. An export without runtime status "
            "is structurally incomplete."
        ),
    },
    # ── Endgame Pass v2: Epistemic Monotonicity Invariants ──
    {
        "invariant_id": "EMI-001",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Confidence Monotonicity",
        "description": (
            "No downstream layer may produce a confidence value higher "
            "than the minimum confidence established by upstream layers."
        ),
    },
    {
        "invariant_id": "EMI-002",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Publishability Monotonicity",
        "description": (
            "No downstream layer may upgrade publishability status. "
            "Publishability can only degrade or remain unchanged."
        ),
    },
    {
        "invariant_id": "EMI-003",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Ranking Visibility Monotonicity",
        "description": (
            "If ranking_eligible was set to False by any upstream layer, "
            "no downstream layer may set it back to True."
        ),
    },
    {
        "invariant_id": "EMI-004",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Comparability Monotonicity",
        "description": (
            "If cross-country comparability was disabled upstream, "
            "no downstream layer may re-enable it."
        ),
    },
    {
        "invariant_id": "EMI-005",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "API Monotonicity",
        "description": (
            "API outputs must not be epistemically stronger than the "
            "internal system state."
        ),
    },
    {
        "invariant_id": "EMI-006",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Caveat Non-Substitutability",
        "description": (
            "Required caveats established upstream must not be removed, "
            "replaced with weaker caveats, or hidden by downstream formatting."
        ),
    },
    {
        "invariant_id": "EMI-007",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Missing Authority Non-Upgrading",
        "description": (
            "If a required authority source is missing, no downstream "
            "layer may treat the result as if the authority were present."
        ),
    },
    {
        "invariant_id": "EMI-008",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Contradiction Non-Upgrading",
        "description": (
            "If contradictions were detected upstream, no downstream "
            "layer may produce output implying they are resolved "
            "without documented authority and reasoning."
        ),
    },
    {
        "invariant_id": "EMI-009",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Replay Determinism",
        "description": (
            "Audit replay of the same input must produce identical "
            "epistemic state."
        ),
    },
    {
        "invariant_id": "EMI-010",
        "type": InvariantType.EPISTEMIC_MONOTONICITY,
        "name": "Diff Epistemic Sensitivity",
        "description": (
            "Snapshot diffs must detect and report ALL epistemic state "
            "changes between versions."
        ),
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# VIOLATION CONSTRUCTOR
# ═══════════════════════════════════════════════════════════════════════════

def _violation(
    invariant_id: str,
    inv_type: str,
    severity: str,
    description: str,
    country: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Construct a canonical invariant violation record."""
    return {
        "invariant_id": invariant_id,
        "type": inv_type,
        "severity": severity,
        "description": description,
        "affected_country": country,
        "evidence": evidence,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-AXIS INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_cross_axis_invariants(
    country: str,
    axis_scores: dict[int, float | None],
    governance_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check cross-axis structural invariants for a single country.

    Args:
        country: ISO-2 code.
        axis_scores: {axis_id: score} for axes 1-6. None if missing.
        governance_result: governance dict from assess_country_governance().

    Returns:
        List of violation dicts (empty if no violations).
    """
    violations: list[dict[str, Any]] = []
    present = {k: v for k, v in axis_scores.items() if v is not None}

    if len(present) < 3:
        return violations  # Not enough data for cross-axis checks

    # ── CA-001: Logistics divergence from goods-based axes ──
    logistics = axis_scores.get(6)
    goods_axes = [axis_scores.get(a) for a in (2, 3, 5)]
    goods_valid = [s for s in goods_axes if s is not None]
    if logistics is not None and len(goods_valid) >= 2:
        goods_mean = sum(goods_valid) / len(goods_valid)
        # If logistics is > 2x goods mean and goods mean is very low
        if goods_mean < 0.10 and logistics > 0.30:
            violations.append(_violation(
                invariant_id="CA-001",
                inv_type=InvariantType.CROSS_AXIS,
                severity=InvariantSeverity.WARNING,
                description=(
                    f"Logistics axis ({logistics:.4f}) is significantly higher "
                    f"than goods-based axes mean ({goods_mean:.4f}). "
                    f"Logistics should co-move with trade flows."
                ),
                country=country,
                evidence={
                    "logistics_score": logistics,
                    "goods_mean": round(goods_mean, 8),
                    "goods_scores": {a: axis_scores.get(a) for a in (2, 3, 5)},
                },
            ))

    # ── CA-002: Producer country high-import anomaly ──
    if governance_result:
        inverted_axes = governance_result.get("producer_inverted_axes", [])
        for ax_id in inverted_axes:
            score = axis_scores.get(ax_id)
            if score is not None and score > 0.60:
                violations.append(_violation(
                    invariant_id="CA-002",
                    inv_type=InvariantType.CROSS_AXIS,
                    severity=InvariantSeverity.ERROR,
                    description=(
                        f"Producer-inverted axis {ax_id} has high import "
                        f"concentration ({score:.4f} > 0.60). A major exporter "
                        f"should not show high import dependency."
                    ),
                    country=country,
                    evidence={
                        "axis_id": ax_id,
                        "score": score,
                        "threshold": 0.60,
                        "inverted_axes": inverted_axes,
                    },
                ))

    # ── CA-003: Low axis majority with high composite ──
    all_scores = [v for v in present.values()]
    if len(all_scores) >= 4:
        n_low = sum(1 for s in all_scores if s < 0.15)
        composite = sum(all_scores) / len(all_scores)
        if n_low >= 4 and composite > 0.25:
            violations.append(_violation(
                invariant_id="CA-003",
                inv_type=InvariantType.CROSS_AXIS,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"{n_low} axes have scores < 0.15 but composite is "
                    f"{composite:.4f} > 0.25. One axis may be dominating "
                    f"the unweighted mean."
                ),
                country=country,
                evidence={
                    "n_low_axes": n_low,
                    "composite": round(composite, 8),
                    "scores": dict(present),
                },
            ))

    # ── CA-004: Uniform score anomaly ──
    if len(all_scores) == 6:
        score_range = max(all_scores) - min(all_scores)
        if score_range < 0.02:
            violations.append(_violation(
                invariant_id="CA-004",
                inv_type=InvariantType.CROSS_AXIS,
                severity=InvariantSeverity.WARNING,
                description=(
                    f"All 6 axis scores are within {score_range:.4f} of each "
                    f"other. Structurally improbable for independent data sources."
                ),
                country=country,
                evidence={
                    "score_range": round(score_range, 8),
                    "min_score": min(all_scores),
                    "max_score": max(all_scores),
                    "scores": dict(present),
                },
            ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# GOVERNANCE CONSISTENCY INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_governance_invariants(
    country: str,
    governance_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check that governance outputs are internally consistent.

    Args:
        country: ISO-2 code.
        governance_result: from assess_country_governance().

    Returns:
        List of violation dicts (empty if consistent).
    """
    violations: list[dict[str, Any]] = []

    tier = governance_result.get("governance_tier", "UNKNOWN")
    ranking_eligible = governance_result.get("ranking_eligible", False)
    comparable = governance_result.get("cross_country_comparable", False)
    composite_defensible = governance_result.get("composite_defensible", False)
    n_inverted = governance_result.get("n_producer_inverted_axes", 0)
    mean_conf = governance_result.get("mean_axis_confidence", 0)

    # Import thresholds
    from backend.governance import (
        MAX_INVERTED_AXES_FOR_COMPARABLE,
        MIN_MEAN_CONFIDENCE_FOR_RANKING,
    )

    # ── GOV-001: ranking_eligible only for FULLY or PARTIALLY ──
    if ranking_eligible and tier not in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE"):
        violations.append(_violation(
            invariant_id="GOV-001",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"ranking_eligible=True but tier={tier}. "
                f"Only FULLY or PARTIALLY_COMPARABLE may be ranking-eligible."
            ),
            country=country,
            evidence={
                "ranking_eligible": ranking_eligible,
                "governance_tier": tier,
            },
        ))

    # ── GOV-002: cross_country_comparable with excessive inversions ──
    if comparable and n_inverted > MAX_INVERTED_AXES_FOR_COMPARABLE:
        violations.append(_violation(
            invariant_id="GOV-002",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"cross_country_comparable=True but {n_inverted} inverted "
                f"axes exceed threshold ({MAX_INVERTED_AXES_FOR_COMPARABLE})."
            ),
            country=country,
            evidence={
                "cross_country_comparable": comparable,
                "n_inverted": n_inverted,
                "max_threshold": MAX_INVERTED_AXES_FOR_COMPARABLE,
            },
        ))

    # ── GOV-003: LOW_CONFIDENCE or NON_COMPARABLE must not be ranking-eligible ──
    if ranking_eligible and tier in ("LOW_CONFIDENCE", "NON_COMPARABLE"):
        violations.append(_violation(
            invariant_id="GOV-003",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"ranking_eligible=True but tier={tier}. "
                f"LOW_CONFIDENCE and NON_COMPARABLE are never ranking-eligible."
            ),
            country=country,
            evidence={
                "ranking_eligible": ranking_eligible,
                "governance_tier": tier,
            },
        ))

    # ── GOV-004: composite_defensible + NON_COMPARABLE ──
    if composite_defensible and tier == "NON_COMPARABLE":
        violations.append(_violation(
            invariant_id="GOV-004",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"composite_defensible=True but tier=NON_COMPARABLE. "
                f"A non-comparable country cannot have a defensible composite."
            ),
            country=country,
            evidence={
                "composite_defensible": composite_defensible,
                "governance_tier": tier,
            },
        ))

    # ── GOV-005: confidence–tier mismatch ──
    if (tier == "FULLY_COMPARABLE"
            and mean_conf < MIN_MEAN_CONFIDENCE_FOR_RANKING):
        violations.append(_violation(
            invariant_id="GOV-005",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.ERROR,
            description=(
                f"FULLY_COMPARABLE but mean confidence {mean_conf:.4f} is "
                f"below MIN_MEAN_CONFIDENCE_FOR_RANKING "
                f"({MIN_MEAN_CONFIDENCE_FOR_RANKING})."
            ),
            country=country,
            evidence={
                "governance_tier": tier,
                "mean_confidence": mean_conf,
                "threshold": MIN_MEAN_CONFIDENCE_FOR_RANKING,
            },
        ))

    # ── GOV-006: sanctions flag but high tier ──
    axis_confs = governance_result.get("axis_confidences", [])
    has_sanctions = False
    for ac in axis_confs:
        for p in ac.get("penalties_applied", []):
            if p.get("flag") == "SANCTIONS_DISTORTION":
                has_sanctions = True
                break
    if has_sanctions and tier in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE"):
        violations.append(_violation(
            invariant_id="GOV-006",
            inv_type=InvariantType.GOVERNANCE,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"SANCTIONS_DISTORTION penalty applied but tier={tier}. "
                f"Sanctioned countries must be LOW_CONFIDENCE or NON_COMPARABLE."
            ),
            country=country,
            evidence={
                "governance_tier": tier,
                "sanctions_flag_present": True,
            },
        ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# TEMPORAL / SNAPSHOT INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def check_temporal_invariants(
    country: str,
    snapshot_a: dict[str, Any],
    snapshot_b: dict[str, Any],
) -> list[dict[str, Any]]:
    """Check temporal consistency between two country snapshots.

    Args:
        country: ISO-2 code.
        snapshot_a: Earlier country detail dict (from build_country_json).
        snapshot_b: Later country detail dict (from build_country_json).

    Returns:
        List of violation dicts (empty if temporally consistent).
    """
    violations: list[dict[str, Any]] = []

    composite_a = snapshot_a.get("isi_composite")
    composite_b = snapshot_b.get("isi_composite")
    rank_a = snapshot_a.get("rank")
    rank_b = snapshot_b.get("rank")

    # Extract axis scores
    axes_a: dict[int, float | None] = {}
    axes_b: dict[int, float | None] = {}
    for ax in snapshot_a.get("axes", []):
        axes_a[ax["axis_id"]] = ax.get("score")
    for ax in snapshot_b.get("axes", []):
        axes_b[ax["axis_id"]] = ax.get("score")

    # Extract governance
    gov_a = snapshot_a.get("governance", {})
    gov_b = snapshot_b.get("governance", {})
    tier_a = gov_a.get("governance_tier", "UNKNOWN")
    tier_b = gov_b.get("governance_tier", "UNKNOWN")

    # Compute max axis delta
    max_axis_delta = 0.0
    axis_deltas: dict[int, float] = {}
    for ax_id in range(1, 7):
        sa = axes_a.get(ax_id)
        sb = axes_b.get(ax_id)
        if sa is not None and sb is not None:
            delta = abs(sb - sa)
            axis_deltas[ax_id] = round(delta, 8)
            if delta > max_axis_delta:
                max_axis_delta = delta

    # ── TEMP-001: Large rank shift without input change ──
    if rank_a is not None and rank_b is not None:
        rank_shift = abs(rank_b - rank_a)
        if rank_shift > 5 and max_axis_delta < 0.05:
            violations.append(_violation(
                invariant_id="TEMP-001",
                inv_type=InvariantType.TEMPORAL,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"Rank shifted by {rank_shift} positions but max axis "
                    f"delta is only {max_axis_delta:.4f} (< 0.05)."
                ),
                country=country,
                evidence={
                    "rank_a": rank_a,
                    "rank_b": rank_b,
                    "rank_shift": rank_shift,
                    "max_axis_delta": max_axis_delta,
                    "axis_deltas": axis_deltas,
                },
            ))

    # ── TEMP-002: Composite change without axis change ──
    if composite_a is not None and composite_b is not None:
        composite_delta = abs(composite_b - composite_a)
        if composite_delta > 0.02 and max_axis_delta < 0.01:
            violations.append(_violation(
                invariant_id="TEMP-002",
                inv_type=InvariantType.TEMPORAL,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Composite changed by {composite_delta:.4f} but no axis "
                    f"changed by more than {max_axis_delta:.4f}. "
                    f"Composite should be derived from axes."
                ),
                country=country,
                evidence={
                    "composite_a": composite_a,
                    "composite_b": composite_b,
                    "composite_delta": round(composite_delta, 8),
                    "max_axis_delta": max_axis_delta,
                    "axis_deltas": axis_deltas,
                },
            ))

    # ── TEMP-003: Governance tier change without structural cause ──
    if tier_a != tier_b and tier_a != "UNKNOWN" and tier_b != "UNKNOWN":
        n_inv_a = gov_a.get("n_producer_inverted_axes", 0)
        n_inv_b = gov_b.get("n_producer_inverted_axes", 0)
        conf_a = gov_a.get("mean_axis_confidence", 0)
        conf_b = gov_b.get("mean_axis_confidence", 0)
        conf_delta = abs(conf_b - conf_a)

        # A tier change without inversion change or confidence change
        if n_inv_a == n_inv_b and conf_delta < 0.05 and max_axis_delta < 0.05:
            violations.append(_violation(
                invariant_id="TEMP-003",
                inv_type=InvariantType.TEMPORAL,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"Governance tier changed from {tier_a} to {tier_b} "
                    f"without structural cause (no inversion change, "
                    f"confidence delta {conf_delta:.4f} < 0.05, "
                    f"max axis delta {max_axis_delta:.4f} < 0.05)."
                ),
                country=country,
                evidence={
                    "tier_a": tier_a,
                    "tier_b": tier_b,
                    "n_inverted_a": n_inv_a,
                    "n_inverted_b": n_inv_b,
                    "confidence_delta": round(conf_delta, 8),
                    "max_axis_delta": max_axis_delta,
                },
            ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# UNIFIED INVARIANT ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def check_external_validity_invariants(
    country: str,
    governance_result: dict[str, Any],
    alignment_result: dict[str, Any] | None = None,
    decision_usability_class: str | None = None,
) -> list[dict[str, Any]]:
    """Check external validity invariants for a single country.

    These invariants detect when internal classifications are
    empirically unsupported by external benchmarks.

    Args:
        country: ISO-2 code.
        governance_result: from assess_country_governance().
        alignment_result: from assess_country_alignment() (optional).
        decision_usability_class: from classify_decision_usability() (optional).

    Returns:
        List of violation dicts (empty if no violations).
    """
    violations: list[dict[str, Any]] = []

    if alignment_result is None:
        # No external data available — cannot check external validity
        return violations

    overall_alignment = alignment_result.get("overall_alignment", "NO_DATA")
    n_compared = alignment_result.get("n_axes_compared", 0)
    n_divergent = alignment_result.get("n_axes_divergent", 0)
    n_aligned = alignment_result.get("n_axes_aligned", 0)

    # ── EXT-001: Benchmark divergence with HIGH confidence ──
    axis_alignments = alignment_result.get("axis_alignments", [])
    axis_confs = governance_result.get("axis_confidences", [])
    conf_by_axis: dict[int, str] = {
        ac.get("axis_id", 0): ac.get("confidence_level", "UNKNOWN")
        for ac in axis_confs
    }
    for aa in axis_alignments:
        axis_id = aa.get("axis_id", 0)
        axis_conf = conf_by_axis.get(axis_id, "UNKNOWN")
        for br in aa.get("benchmark_results", []):
            if (br.get("alignment_class") == "DIVERGENT"
                    and axis_conf == "HIGH"):
                violations.append(_violation(
                    invariant_id="EXT-001",
                    inv_type=InvariantType.EXTERNAL_VALIDITY,
                    severity=InvariantSeverity.WARNING,
                    description=(
                        f"Axis {axis_id} has HIGH confidence but "
                        f"DIVERGENT alignment with benchmark "
                        f"{br.get('benchmark_id', 'UNKNOWN')}. "
                        f"Internal confidence is empirically unsupported."
                    ),
                    country=country,
                    evidence={
                        "axis_id": axis_id,
                        "confidence_level": axis_conf,
                        "alignment_class": "DIVERGENT",
                        "benchmark_id": br.get("benchmark_id"),
                        "metric_value": br.get("metric_value"),
                    },
                ))

    # ── EXT-002: Trusted-Comparable without empirical grounding ──
    if (decision_usability_class == "TRUSTED_COMPARABLE"
            and n_compared == 0):
        violations.append(_violation(
            invariant_id="EXT-002",
            inv_type=InvariantType.EXTERNAL_VALIDITY,
            severity=InvariantSeverity.WARNING,
            description=(
                f"Country {country} is TRUSTED_COMPARABLE but has "
                f"zero external benchmark comparisons. Classification "
                f"is structurally sound but empirically unverified."
            ),
            country=country,
            evidence={
                "decision_usability_class": decision_usability_class,
                "n_benchmarks_compared": n_compared,
            },
        ))

    # ── EXT-003: Producer inversion unconfirmed ──
    from backend.governance import PRODUCER_INVERSION_REGISTRY
    producer_info = PRODUCER_INVERSION_REGISTRY.get(country)
    if producer_info and n_compared > 0:
        # Check if any structural consistency benchmark confirmed the inversion
        inversion_confirmed = False
        for aa in axis_alignments:
            for br in aa.get("benchmark_results", []):
                if br.get("comparison_type") == "STRUCTURAL_CONSISTENCY":
                    if br.get("alignment_class") not in ("NO_DATA", "STRUCTURALLY_INCOMPARABLE"):
                        inversion_confirmed = True
                        break
        if not inversion_confirmed:
            violations.append(_violation(
                invariant_id="EXT-003",
                inv_type=InvariantType.EXTERNAL_VALIDITY,
                severity=InvariantSeverity.WARNING,
                description=(
                    f"Country {country} is in PRODUCER_INVERSION_REGISTRY "
                    f"but no external benchmark confirms the inversion. "
                    f"Registry entry may be outdated."
                ),
                country=country,
                evidence={
                    "inverted_axes": producer_info.get("inverted_axes", []),
                    "n_benchmarks_compared": n_compared,
                },
            ))

    # ── EXT-004: Majority axes divergent ──
    if n_compared >= 2 and n_divergent > n_compared / 2:
        violations.append(_violation(
            invariant_id="EXT-004",
            inv_type=InvariantType.EXTERNAL_VALIDITY,
            severity=InvariantSeverity.ERROR,
            description=(
                f"Country {country} shows DIVERGENT alignment on "
                f"{n_divergent}/{n_compared} compared axes. "
                f"ISI output is empirically suspect."
            ),
            country=country,
            evidence={
                "n_compared": n_compared,
                "n_divergent": n_divergent,
                "n_aligned": n_aligned,
                "overall_alignment": overall_alignment,
            },
        ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# CONSTRUCT ENFORCEMENT INVARIANT CHECKS (FINAL HARDENING)
# ═══════════════════════════════════════════════════════════════════════════

def check_construct_enforcement_invariants(
    country: str,
    construct_enforcement: dict[str, Any] | None = None,
    mapping_audit_results: dict[str, dict[str, Any]] | None = None,
    sensitivity_result: dict[str, Any] | None = None,
    decision_usability_class: str | None = None,
    alignment_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check construct enforcement invariants (Final Hardening Pass).

    These invariants enforce consequences for:
    - Invalid constructs contributing to composites
    - Proxy axes without alignment evidence
    - Alignment claims with invalid mappings
    - Unstable alignment with high trust classification

    Args:
        country: ISO-2 code.
        construct_enforcement: Result from enforce_all_axes().
        mapping_audit_results: {benchmark_id: audit_result} from benchmark_mapping_audit.
        sensitivity_result: Result from run_alignment_sensitivity().
        decision_usability_class: Current DecisionUsabilityClass.
        alignment_result: from assess_country_alignment().

    Returns:
        List of violation dicts.
    """
    violations: list[dict[str, Any]] = []

    # ── CE-INV-001: No invalid construct in composite ──
    if construct_enforcement:
        composite_blocked = construct_enforcement.get("composite_blocked", False)
        n_invalid = construct_enforcement.get("n_invalid", 0)
        if n_invalid > 0 and not composite_blocked:
            # Invalid axes exist but composite is NOT blocked —
            # check if any invalid axis still contributes
            for ax_result in construct_enforcement.get("per_axis", []):
                if (ax_result.get("construct_validity_class") == "CONSTRUCT_INVALID"
                        and ax_result.get("weight_factor", 0) > 0):
                    violations.append(_violation(
                        invariant_id="CE-INV-001",
                        inv_type=InvariantType.CONSTRUCT_ENFORCEMENT,
                        severity=InvariantSeverity.CRITICAL,
                        description=(
                            f"Axis {ax_result['axis_id']} has CONSTRUCT_INVALID "
                            f"validity but weight_factor={ax_result['weight_factor']} > 0. "
                            f"Invalid constructs MUST have zero weight."
                        ),
                        country=country,
                        evidence={
                            "axis_id": ax_result["axis_id"],
                            "construct_validity_class": ax_result["construct_validity_class"],
                            "weight_factor": ax_result["weight_factor"],
                        },
                    ))

    # ── CE-INV-002: Logistics proxy requires alignment ──
    if construct_enforcement:
        for ax_result in construct_enforcement.get("per_axis", []):
            if (ax_result.get("axis_id") == 6
                    and ax_result.get("is_proxy", False)
                    and ax_result.get("construct_validity_class") == "CONSTRUCT_VALID"):
                # Proxy on Axis 6 marked valid — check if alignment supports this
                has_alignment_evidence = False
                if alignment_result:
                    for aa in alignment_result.get("axis_alignments", []):
                        if aa.get("axis_id") == 6:
                            for br in aa.get("benchmark_results", []):
                                if br.get("alignment_class") in (
                                    "STRONGLY_ALIGNED", "WEAKLY_ALIGNED",
                                ):
                                    has_alignment_evidence = True
                                    break
                if not has_alignment_evidence:
                    violations.append(_violation(
                        invariant_id="CE-INV-002",
                        inv_type=InvariantType.CONSTRUCT_ENFORCEMENT,
                        severity=InvariantSeverity.WARNING,
                        description=(
                            f"Axis 6 uses proxy for {country} but is marked "
                            f"CONSTRUCT_VALID without external alignment evidence. "
                            f"Proxy validation requires alignment data."
                        ),
                        country=country,
                        evidence={
                            "axis_id": 6,
                            "is_proxy": True,
                            "construct_validity_class": ax_result["construct_validity_class"],
                            "has_alignment_evidence": False,
                        },
                    ))

    # ── CE-INV-003: No alignment with invalid mapping ──
    if mapping_audit_results and alignment_result:
        for aa in alignment_result.get("axis_alignments", []):
            for br in aa.get("benchmark_results", []):
                bm_id = br.get("benchmark_id")
                audit = (mapping_audit_results or {}).get(bm_id)
                if (audit
                        and audit.get("mapping_validity") == "INVALID_MAPPING"
                        and br.get("alignment_class") not in (
                            "NO_DATA", "STRUCTURALLY_INCOMPARABLE",
                        )):
                    violations.append(_violation(
                        invariant_id="CE-INV-003",
                        inv_type=InvariantType.CONSTRUCT_ENFORCEMENT,
                        severity=InvariantSeverity.ERROR,
                        description=(
                            f"Benchmark {bm_id} has INVALID_MAPPING but "
                            f"alignment_class={br['alignment_class']}. "
                            f"Should be STRUCTURALLY_INCOMPARABLE."
                        ),
                        country=country,
                        evidence={
                            "benchmark_id": bm_id,
                            "mapping_validity": "INVALID_MAPPING",
                            "alignment_class": br["alignment_class"],
                            "axis_id": aa.get("axis_id"),
                        },
                    ))

    # ── CE-INV-004: Alignment must be stable for high trust ──
    if sensitivity_result and decision_usability_class:
        stability = sensitivity_result.get("stability_class")
        if (stability == "ALIGNMENT_UNSTABLE"
                and decision_usability_class == "TRUSTED_COMPARABLE"):
            violations.append(_violation(
                invariant_id="CE-INV-004",
                inv_type=InvariantType.CONSTRUCT_ENFORCEMENT,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Country {country} has ALIGNMENT_UNSTABLE but is "
                    f"classified as TRUSTED_COMPARABLE. Unstable alignment "
                    f"is incompatible with highest trust level."
                ),
                country=country,
                evidence={
                    "stability_class": stability,
                    "decision_usability_class": decision_usability_class,
                },
            ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# FAILURE VISIBILITY INVARIANT CHECKS (INSTITUTIONALIZATION PASS)
# ═══════════════════════════════════════════════════════════════════════════

def check_failure_visibility_invariants(
    country: str,
    visibility_block: dict[str, Any] | None = None,
    decision_usability_class: str | None = None,
) -> list[dict[str, Any]]:
    """Check failure visibility invariants.

    These invariants ensure that every exported country output
    includes embedded limitation data that cannot be ignored.

    Args:
        country: ISO-2 code.
        visibility_block: Output of build_visibility_block() (optional).
        decision_usability_class: Current DecisionUsabilityClass (optional).

    Returns:
        List of violation dicts.
    """
    violations: list[dict[str, Any]] = []

    # ── FV-001: Visibility block must be present ──
    if visibility_block is None:
        violations.append(_violation(
            invariant_id="FV-001",
            inv_type=InvariantType.FAILURE_VISIBILITY,
            severity=InvariantSeverity.CRITICAL,
            description=(
                f"Country {country} has no failure visibility block. "
                f"Export without embedded limitations is a "
                f"methodological violation."
            ),
            country=country,
            evidence={
                "visibility_block_present": False,
            },
        ))
        return violations  # Can't check FV-002 without a block

    # ── FV-002: Trust level consistent with usability ──
    trust_level = visibility_block.get("trust_level", "UNKNOWN")
    if (trust_level == "DO_NOT_USE"
            and decision_usability_class is not None
            and decision_usability_class != "INVALID_FOR_COMPARISON"):
        violations.append(_violation(
            invariant_id="FV-002",
            inv_type=InvariantType.FAILURE_VISIBILITY,
            severity=InvariantSeverity.ERROR,
            description=(
                f"Country {country} has trust_level=DO_NOT_USE but "
                f"decision_usability_class={decision_usability_class}. "
                f"Should be INVALID_FOR_COMPARISON."
            ),
            country=country,
            evidence={
                "trust_level": trust_level,
                "decision_usability_class": decision_usability_class,
            },
        ))

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# AUTHORITY CONSISTENCY INVARIANT CHECKS (INSTITUTIONALIZATION PASS)
# ═══════════════════════════════════════════════════════════════════════════

def check_authority_consistency_invariants(
    country: str,
    alignment_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check benchmark authority consistency invariants.

    These invariants enforce the benchmark authority hierarchy:
    STRUCTURAL > HIGH_CONFIDENCE > SUPPORTING.

    Args:
        country: ISO-2 code.
        alignment_result: from assess_country_alignment() (optional).

    Returns:
        List of violation dicts.
    """
    violations: list[dict[str, Any]] = []

    if alignment_result is None:
        return violations

    # ── AUTH-001: Structural benchmark contradiction ──
    authority_conflicts = alignment_result.get("authority_conflicts", [])
    for conflict in authority_conflicts:
        if conflict.get("severity") == "CRITICAL":
            violations.append(_violation(
                invariant_id="AUTH-001",
                inv_type=InvariantType.AUTHORITY_CONSISTENCY,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"STRUCTURAL benchmark contradicts HIGH_CONFIDENCE "
                    f"benchmark on axis {conflict.get('axis_id', '?')}: "
                    f"{conflict.get('description', 'unknown conflict')}."
                ),
                country=country,
                evidence=conflict,
            ))

    # ── AUTH-002: Weighted score must reflect hierarchy ──
    weighted = alignment_result.get("weighted_alignment_score", {})
    composition = weighted.get("weight_composition", {}) if isinstance(weighted, dict) else {}
    if composition:
        structural_w = composition.get("STRUCTURAL", 0)
        high_conf_w = composition.get("HIGH_CONFIDENCE", 0)
        supporting_w = composition.get("SUPPORTING", 0)
        # If any weight is present, verify it matches the expected values
        if (structural_w > 0 and abs(structural_w - 1.0) > 0.01):
            violations.append(_violation(
                invariant_id="AUTH-002",
                inv_type=InvariantType.AUTHORITY_CONSISTENCY,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"STRUCTURAL weight is {structural_w}, expected 1.0. "
                    f"Authority hierarchy is violated."
                ),
                country=country,
                evidence={
                    "expected_structural": 1.0,
                    "actual_structural": structural_w,
                    "weight_composition": composition,
                },
            ))
        if (high_conf_w > 0 and abs(high_conf_w - 0.7) > 0.01):
            violations.append(_violation(
                invariant_id="AUTH-002",
                inv_type=InvariantType.AUTHORITY_CONSISTENCY,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"HIGH_CONFIDENCE weight is {high_conf_w}, expected 0.7. "
                    f"Authority hierarchy is violated."
                ),
                country=country,
                evidence={
                    "expected_high_confidence": 0.7,
                    "actual_high_confidence": high_conf_w,
                    "weight_composition": composition,
                },
            ))
        if (supporting_w > 0 and abs(supporting_w - 0.4) > 0.01):
            violations.append(_violation(
                invariant_id="AUTH-002",
                inv_type=InvariantType.AUTHORITY_CONSISTENCY,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"SUPPORTING weight is {supporting_w}, expected 0.4. "
                    f"Authority hierarchy is violated."
                ),
                country=country,
                evidence={
                    "expected_supporting": 0.4,
                    "actual_supporting": supporting_w,
                    "weight_composition": composition,
                },
            ))

    return violations


def check_reality_conflict_invariants(
    country: str,
    governance_result: dict[str, Any],
    alignment_result: dict[str, Any] | None = None,
    decision_usability_class: str | None = None,
    reality_conflicts_block: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check reality conflict invariants.

    These invariants enforce that when ISI's internal classification
    contradicts external evidence, the contradiction is STRUCTURALLY
    surfaced in the country output — not silently swallowed.

    Args:
        country: ISO-2 code.
        governance_result: from assess_country_governance().
        alignment_result: from assess_country_alignment() (optional).
        decision_usability_class: from classify_decision_usability() (optional).
        reality_conflicts_block: from detect_reality_conflicts() (optional).

    Returns:
        List of violation dicts.
    """
    violations: list[dict[str, Any]] = []

    if alignment_result is None:
        return violations

    governance_tier = governance_result.get("governance_tier", "NON_COMPARABLE")
    overall_alignment = alignment_result.get("overall_alignment", "NO_DATA")
    n_axes_compared = alignment_result.get("n_axes_compared", 0)
    ranking_eligible = governance_result.get("ranking_eligible", False)

    # ── RC-001: Governance-alignment reality conflict ──
    # If governance is high trust and alignment is divergent,
    # the reality_conflicts block MUST contain the conflict
    high_trust = governance_tier in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE")
    if (high_trust and overall_alignment == "DIVERGENT" and n_axes_compared > 0):
        # Check that reality_conflicts_block actually captured this
        if reality_conflicts_block is None:
            violations.append(_violation(
                invariant_id="RC-001",
                inv_type=InvariantType.REALITY_CONFLICT,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Governance tier is {governance_tier} but alignment "
                    f"is DIVERGENT — no reality_conflicts block was "
                    f"computed. This contradiction MUST be surfaced."
                ),
                country=country,
                evidence={
                    "governance_tier": governance_tier,
                    "overall_alignment": overall_alignment,
                    "n_axes_compared": n_axes_compared,
                    "reality_conflicts_block": None,
                },
            ))
        else:
            # Block exists — verify it contains the conflict
            conflicts = reality_conflicts_block.get("conflicts", [])
            has_gam = any(
                c.get("conflict_type") == "GOVERNANCE_ALIGNMENT_MISMATCH"
                for c in conflicts
            )
            if not has_gam:
                violations.append(_violation(
                    invariant_id="RC-001",
                    inv_type=InvariantType.REALITY_CONFLICT,
                    severity=InvariantSeverity.ERROR,
                    description=(
                        f"Governance is {governance_tier}, alignment is "
                        f"DIVERGENT, but reality_conflicts block does not "
                        f"contain GOVERNANCE_ALIGNMENT_MISMATCH entry."
                    ),
                    country=country,
                    evidence={
                        "governance_tier": governance_tier,
                        "overall_alignment": overall_alignment,
                        "conflict_types_found": [
                            c.get("conflict_type") for c in conflicts
                        ],
                    },
                ))

    # ── RC-002: Ranking-eligible with divergent alignment ──
    if (ranking_eligible and overall_alignment == "DIVERGENT"
            and n_axes_compared > 0):
        if reality_conflicts_block is not None:
            conflicts = reality_conflicts_block.get("conflicts", [])
            has_red = any(
                c.get("conflict_type") == "RANKING_ELIGIBILITY_DIVERGENCE"
                for c in conflicts
            )
            if not has_red:
                violations.append(_violation(
                    invariant_id="RC-002",
                    inv_type=InvariantType.REALITY_CONFLICT,
                    severity=InvariantSeverity.ERROR,
                    description=(
                        f"Country is ranking_eligible=True but alignment "
                        f"is DIVERGENT. reality_conflicts block must "
                        f"contain RANKING_ELIGIBILITY_DIVERGENCE entry."
                    ),
                    country=country,
                    evidence={
                        "ranking_eligible": ranking_eligible,
                        "overall_alignment": overall_alignment,
                    },
                ))
        elif reality_conflicts_block is None:
            violations.append(_violation(
                invariant_id="RC-002",
                inv_type=InvariantType.REALITY_CONFLICT,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"Country is ranking_eligible=True but alignment "
                    f"is DIVERGENT — no reality_conflicts block exists."
                ),
                country=country,
                evidence={
                    "ranking_eligible": ranking_eligible,
                    "overall_alignment": overall_alignment,
                    "reality_conflicts_block": None,
                },
            ))

    # ── RC-003: Usability-alignment contradiction ──
    if (decision_usability_class == "TRUSTED_COMPARABLE"
            and n_axes_compared > 0):
        n_divergent = alignment_result.get("n_axes_divergent", 0)
        # If majority divergent, this is a TRUSTED + CONTRADICTED situation
        if n_divergent > n_axes_compared / 2:
            if reality_conflicts_block is None:
                violations.append(_violation(
                    invariant_id="RC-003",
                    inv_type=InvariantType.REALITY_CONFLICT,
                    severity=InvariantSeverity.CRITICAL,
                    description=(
                        f"Decision usability is TRUSTED_COMPARABLE but "
                        f"majority of axes are DIVERGENT ({n_divergent}/"
                        f"{n_axes_compared}). This CRITICAL contradiction "
                        f"has no reality_conflicts block."
                    ),
                    country=country,
                    evidence={
                        "decision_usability_class": decision_usability_class,
                        "n_axes_divergent": n_divergent,
                        "n_axes_compared": n_axes_compared,
                    },
                ))

    return violations


def check_pipeline_integrity_invariants(
    country: str,
    enforcement_result: dict[str, Any] | None = None,
    truth_result: dict[str, Any] | None = None,
    country_json: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check pipeline integrity invariants (Final Closure Pass).

    These verify that the pipeline, enforcement matrix, and truth resolver
    are structurally sound — no decorative flags, no conflicting states.

    Args:
        country: ISO-2 code.
        enforcement_result: Output of apply_enforcement().
        truth_result: Output of resolve_truth().
        country_json: Full country JSON (for export consistency check).

    Returns:
        List of violation dicts (empty if no violations).
    """
    violations: list[dict[str, Any]] = []

    # ── INV-PIPELINE-001: No missing layer outputs ──
    if country_json is not None:
        required_keys = [
            "governance", "decision_usability", "construct_enforcement",
            "external_validation", "failure_visibility", "reality_conflicts",
            "invariant_assessment",
        ]
        missing = [k for k in required_keys if country_json.get(k) is None]
        if missing:
            violations.append(_violation(
                invariant_id="INV-PIPELINE-001",
                inv_type=InvariantType.PIPELINE_INTEGRITY,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Missing layer outputs in country JSON: {', '.join(missing)}. "
                    f"Pipeline did not produce all required layers."
                ),
                country=country,
                evidence={"missing_layers": missing},
            ))

    # ── INV-ENFORCEMENT-001: CRITICAL flags must have consequences ──
    if enforcement_result is not None and country_json is not None:
        critical_flags_found = []

        # Check reality_conflicts
        rc = country_json.get("reality_conflicts", {})
        if rc and rc.get("has_critical"):
            critical_flags_found.append("reality_conflicts.has_critical")

        # Check failure_visibility
        fv = country_json.get("failure_visibility", {})
        if fv and fv.get("trust_level") == "DO_NOT_USE":
            critical_flags_found.append("failure_visibility.DO_NOT_USE")

        # Check construct_enforcement
        ce = country_json.get("construct_enforcement", {})
        if ce and not ce.get("composite_producible", True):
            critical_flags_found.append("construct_enforcement.not_producible")

        # Check invariant_assessment
        inv = country_json.get("invariant_assessment", {})
        if inv and inv.get("has_critical"):
            critical_flags_found.append("invariant_assessment.has_critical")

        if critical_flags_found:
            enf_actions = enforcement_result.get("actions", [])
            if not enf_actions:
                violations.append(_violation(
                    invariant_id="INV-ENFORCEMENT-001",
                    inv_type=InvariantType.PIPELINE_INTEGRITY,
                    severity=InvariantSeverity.CRITICAL,
                    description=(
                        f"CRITICAL flags detected ({', '.join(critical_flags_found)}) "
                        f"but enforcement matrix produced 0 actions. "
                        f"Flags without consequences are decorative."
                    ),
                    country=country,
                    evidence={
                        "critical_flags": critical_flags_found,
                        "n_enforcement_actions": 0,
                    },
                ))

    # ── INV-TRUTH-001: No conflicting final states ──
    if truth_result is not None:
        final_tier = truth_result.get("final_governance_tier")
        final_ranking = truth_result.get("final_ranking_eligible")
        final_suppressed = truth_result.get("final_composite_suppressed")

        if final_tier == "NON_COMPARABLE" and final_ranking:
            violations.append(_violation(
                invariant_id="INV-TRUTH-001",
                inv_type=InvariantType.PIPELINE_INTEGRITY,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    "Truth resolver final state conflict: "
                    "governance_tier=NON_COMPARABLE but "
                    "ranking_eligible=True."
                ),
                country=country,
                evidence={
                    "final_governance_tier": final_tier,
                    "final_ranking_eligible": final_ranking,
                },
            ))

        if final_tier == "LOW_CONFIDENCE" and final_ranking:
            violations.append(_violation(
                invariant_id="INV-TRUTH-001",
                inv_type=InvariantType.PIPELINE_INTEGRITY,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    "Truth resolver final state conflict: "
                    "governance_tier=LOW_CONFIDENCE but "
                    "ranking_eligible=True."
                ),
                country=country,
                evidence={
                    "final_governance_tier": final_tier,
                    "final_ranking_eligible": final_ranking,
                },
            ))

        if final_tier == "NON_COMPARABLE" and not final_suppressed:
            violations.append(_violation(
                invariant_id="INV-TRUTH-001",
                inv_type=InvariantType.PIPELINE_INTEGRITY,
                severity=InvariantSeverity.ERROR,
                description=(
                    "Truth resolver final state conflict: "
                    "governance_tier=NON_COMPARABLE but "
                    "composite is not suppressed."
                ),
                country=country,
                evidence={
                    "final_governance_tier": final_tier,
                    "final_composite_suppressed": final_suppressed,
                },
            ))

    # ── INV-EXPORT-001: Export must reflect truth resolver ──
    if truth_result is not None and country_json is not None:
        tr = country_json.get("truth_resolution")
        if tr is None:
            violations.append(_violation(
                invariant_id="INV-EXPORT-001",
                inv_type=InvariantType.PIPELINE_INTEGRITY,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    "truth_resolution block missing from country JSON. "
                    "Export does not include truth resolver output."
                ),
                country=country,
                evidence={},
            ))
        else:
            # Check composite suppression consistency
            if tr.get("final_composite_suppressed") and country_json.get("isi_composite") is not None:
                violations.append(_violation(
                    invariant_id="INV-EXPORT-001",
                    inv_type=InvariantType.PIPELINE_INTEGRITY,
                    severity=InvariantSeverity.CRITICAL,
                    description=(
                        "Truth resolver says composite suppressed but "
                        "isi_composite is not None in export."
                    ),
                    country=country,
                    evidence={
                        "final_composite_suppressed": True,
                        "isi_composite": country_json.get("isi_composite"),
                    },
                ))

    return violations


def check_runtime_invariants(
    country: str,
    country_json: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Check runtime invariants (Production Hardening Pass).

    These verify that runtime metadata (pipeline status, versions,
    runtime_status) is structurally present and consistent.

    Args:
        country: ISO-2 code.
        country_json: Full country JSON (for export consistency check).

    Returns:
        List of violation dicts (empty if no violations).
    """
    violations: list[dict[str, Any]] = []

    if country_json is None:
        return violations

    # ── INV-RUNTIME-001: No silent failures ──
    runtime_status = country_json.get("runtime_status")
    if runtime_status is not None:
        degraded = runtime_status.get("degraded_layers", [])
        failed = runtime_status.get("failed_layers", [])

        # Check that layers with error fields are listed as degraded
        for layer_key in [
            "falsification", "decision_usability", "external_validation",
            "construct_enforcement", "alignment_sensitivity",
            "failure_visibility", "reality_conflicts", "invariant_assessment",
        ]:
            block = country_json.get(layer_key)
            if isinstance(block, dict) and block.get("error"):
                if layer_key not in degraded and layer_key not in failed:
                    violations.append(_violation(
                        invariant_id="INV-RUNTIME-001",
                        inv_type=InvariantType.RUNTIME,
                        severity=InvariantSeverity.ERROR,
                        description=(
                            f"Layer '{layer_key}' has an error field but is not "
                            f"listed in runtime_status.degraded_layers or "
                            f"failed_layers. This is a silent failure."
                        ),
                        country=country,
                        evidence={
                            "layer": layer_key,
                            "error": block.get("error"),
                            "degraded_layers": degraded,
                            "failed_layers": failed,
                        },
                    ))

    # ── INV-RUNTIME-002: Degraded must propagate ──
    if runtime_status is not None:
        pipeline_status = runtime_status.get("pipeline_status")
        degraded = runtime_status.get("degraded_layers", [])
        failed = runtime_status.get("failed_layers", [])

        if degraded and pipeline_status == "HEALTHY":
            violations.append(_violation(
                invariant_id="INV-RUNTIME-002",
                inv_type=InvariantType.RUNTIME,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Pipeline status is HEALTHY but {len(degraded)} layers "
                    f"are degraded: {', '.join(degraded)}. "
                    f"A HEALTHY pipeline cannot have degraded layers."
                ),
                country=country,
                evidence={
                    "pipeline_status": pipeline_status,
                    "degraded_layers": degraded,
                },
            ))

        if failed and pipeline_status != "FAILED":
            violations.append(_violation(
                invariant_id="INV-RUNTIME-002",
                inv_type=InvariantType.RUNTIME,
                severity=InvariantSeverity.CRITICAL,
                description=(
                    f"Pipeline has {len(failed)} failed layers but "
                    f"status is '{pipeline_status}' instead of 'FAILED'."
                ),
                country=country,
                evidence={
                    "pipeline_status": pipeline_status,
                    "failed_layers": failed,
                },
            ))

    # ── INV-VERSION-001: Versions must be present ──
    version_info = country_json.get("version_info")
    if version_info is None:
        violations.append(_violation(
            invariant_id="INV-VERSION-001",
            inv_type=InvariantType.RUNTIME,
            severity=InvariantSeverity.CRITICAL,
            description=(
                "version_info block missing from country JSON. "
                "Without version tracking, reproducibility is impossible."
            ),
            country=country,
            evidence={},
        ))
    else:
        required_versions = [
            "methodology_version", "pipeline_version",
            "truth_logic_version", "enforcement_version",
        ]
        missing = [v for v in required_versions if not version_info.get(v)]
        if missing:
            violations.append(_violation(
                invariant_id="INV-VERSION-001",
                inv_type=InvariantType.RUNTIME,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"version_info missing required fields: "
                    f"{', '.join(missing)}."
                ),
                country=country,
                evidence={"missing_versions": missing},
            ))

    # ── INV-EXPORT-002: Runtime status must be included ──
    if runtime_status is None:
        violations.append(_violation(
            invariant_id="INV-EXPORT-002",
            inv_type=InvariantType.RUNTIME,
            severity=InvariantSeverity.CRITICAL,
            description=(
                "runtime_status block missing from country JSON. "
                "An export without runtime status is structurally incomplete."
            ),
            country=country,
            evidence={},
        ))
    else:
        required_fields = ["pipeline_status", "degraded_layers", "failed_layers"]
        missing = [f for f in required_fields if f not in runtime_status]
        if missing:
            violations.append(_violation(
                invariant_id="INV-EXPORT-002",
                inv_type=InvariantType.RUNTIME,
                severity=InvariantSeverity.ERROR,
                description=(
                    f"runtime_status missing required fields: "
                    f"{', '.join(missing)}."
                ),
                country=country,
                evidence={"missing_fields": missing},
            ))

    return violations


def assess_country_invariants(
    country: str,
    axis_scores: dict[int, float | None],
    governance_result: dict[str, Any],
    previous_snapshot: dict[str, Any] | None = None,
    current_snapshot: dict[str, Any] | None = None,
    alignment_result: dict[str, Any] | None = None,
    decision_usability_class: str | None = None,
    construct_enforcement: dict[str, Any] | None = None,
    mapping_audit_results: dict[str, dict[str, Any]] | None = None,
    sensitivity_result: dict[str, Any] | None = None,
    visibility_block: dict[str, Any] | None = None,
    reality_conflicts_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all invariant checks for a single country.

    Args:
        country: ISO-2 code.
        axis_scores: {axis_id: score_or_None} for axes 1-6.
        governance_result: from assess_country_governance().
        previous_snapshot: Earlier country JSON (for temporal checks).
        current_snapshot: Current country JSON (for temporal checks).
        alignment_result: from assess_country_alignment() (for external validity).
        decision_usability_class: from classify_decision_usability() (for external validity).
        construct_enforcement: from enforce_all_axes() (for construct enforcement).
        mapping_audit_results: {benchmark_id: audit_result} (for construct enforcement).
        sensitivity_result: from run_alignment_sensitivity() (for construct enforcement).
        visibility_block: from build_visibility_block() (for failure visibility).
        reality_conflicts_block: from detect_reality_conflicts() (for reality conflict checks).

    Returns:
        Invariant assessment with violations, counts, and severity summary.
    """
    all_violations: list[dict[str, Any]] = []

    # Cross-axis checks
    all_violations.extend(
        check_cross_axis_invariants(country, axis_scores, governance_result)
    )

    # Governance consistency checks
    all_violations.extend(
        check_governance_invariants(country, governance_result)
    )

    # Temporal checks (only if both snapshots provided)
    if previous_snapshot is not None and current_snapshot is not None:
        all_violations.extend(
            check_temporal_invariants(country, previous_snapshot, current_snapshot)
        )

    # External validity checks (only if alignment data provided)
    if alignment_result is not None:
        all_violations.extend(
            check_external_validity_invariants(
                country, governance_result, alignment_result,
                decision_usability_class,
            )
        )

    # Construct enforcement checks (Final Hardening Pass)
    if (construct_enforcement is not None
            or mapping_audit_results is not None
            or sensitivity_result is not None):
        all_violations.extend(
            check_construct_enforcement_invariants(
                country,
                construct_enforcement=construct_enforcement,
                mapping_audit_results=mapping_audit_results,
                sensitivity_result=sensitivity_result,
                decision_usability_class=decision_usability_class,
                alignment_result=alignment_result,
            )
        )

    # Failure visibility checks (Institutionalization Pass)
    # Only check if visibility_block was explicitly provided
    # (None means the caller didn't compute it — backward compatible)
    if visibility_block is not None:
        all_violations.extend(
            check_failure_visibility_invariants(
                country,
                visibility_block=visibility_block,
                decision_usability_class=decision_usability_class,
            )
        )

    # Authority consistency checks (Institutionalization Pass)
    if alignment_result is not None:
        all_violations.extend(
            check_authority_consistency_invariants(
                country,
                alignment_result=alignment_result,
            )
        )

    # Reality conflict checks (Institutionalization Pass)
    # Only check if alignment data is available
    if alignment_result is not None:
        all_violations.extend(
            check_reality_conflict_invariants(
                country,
                governance_result=governance_result,
                alignment_result=alignment_result,
                decision_usability_class=decision_usability_class,
                reality_conflicts_block=reality_conflicts_block,
            )
        )

    # Severity counts
    n_warning = sum(1 for v in all_violations if v["severity"] == InvariantSeverity.WARNING)
    n_error = sum(1 for v in all_violations if v["severity"] == InvariantSeverity.ERROR)
    n_critical = sum(1 for v in all_violations if v["severity"] == InvariantSeverity.CRITICAL)

    return {
        "country": country,
        "n_violations": len(all_violations),
        "n_warnings": n_warning,
        "n_errors": n_error,
        "n_critical": n_critical,
        "has_critical": n_critical > 0,
        "violations": all_violations,
        "honesty_note": (
            "Invariant checks verify INTERNAL CONSISTENCY only. "
            "Zero violations does NOT mean the outputs are correct — "
            "it means they are structurally coherent."
        ),
    }


def assess_all_invariants(
    all_scores: dict[int, dict[str, float]],
    governance_results: dict[str, dict[str, Any]],
    previous_snapshots: dict[str, dict[str, Any]] | None = None,
    current_snapshots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run invariant checks for all countries.

    Args:
        all_scores: {axis_id: {country: score}}.
        governance_results: {country: governance_dict}.
        previous_snapshots: {country: earlier_country_json} (optional).
        current_snapshots: {country: current_country_json} (optional).

    Returns:
        {country: invariant_assessment}.
    """
    results: dict[str, dict[str, Any]] = {}
    for country, gov in governance_results.items():
        axis_scores: dict[int, float | None] = {}
        for ax_id in range(1, 7):
            axis_scores[ax_id] = all_scores.get(ax_id, {}).get(country)

        prev = (previous_snapshots or {}).get(country)
        curr = (current_snapshots or {}).get(country)

        results[country] = assess_country_invariants(
            country, axis_scores, gov, prev, curr,
        )
    return results


def get_invariant_summary(
    invariant_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate invariant results across all countries."""
    total_countries = len(invariant_results)
    total_violations = sum(r["n_violations"] for r in invariant_results.values())
    total_critical = sum(r["n_critical"] for r in invariant_results.values())
    total_errors = sum(r["n_errors"] for r in invariant_results.values())
    total_warnings = sum(r["n_warnings"] for r in invariant_results.values())

    countries_with_violations = sorted(
        c for c, r in invariant_results.items() if r["n_violations"] > 0
    )
    countries_with_critical = sorted(
        c for c, r in invariant_results.items() if r["n_critical"] > 0
    )

    return {
        "total_countries_assessed": total_countries,
        "total_violations": total_violations,
        "total_critical": total_critical,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "countries_with_violations": countries_with_violations,
        "countries_with_critical": countries_with_critical,
        "system_consistent": total_critical == 0,
        "interpretation": (
            f"Of {total_countries} countries, {len(countries_with_violations)} "
            f"have invariant violations. {total_critical} critical, "
            f"{total_errors} errors, {total_warnings} warnings."
        ),
        "honesty_note": (
            "Invariant checks verify internal consistency only. "
            "system_consistent=True means no structural contradictions, "
            "NOT that the outputs are empirically correct."
        ),
    }


def get_invariant_registry() -> list[dict[str, str]]:
    """Return the full invariant registry."""
    return list(INVARIANT_REGISTRY)


def should_downgrade_usability(
    invariant_result: dict[str, Any],
) -> bool:
    """Determine if invariant violations require usability downgrade.

    CRITICAL invariant violations MUST downgrade DecisionUsabilityClass.
    """
    return invariant_result.get("has_critical", False)
