"""
backend.provenance — Full Provenance Trace System

SYSTEM 2: Every exported value must be traceable to its source data,
transformation chain, rules applied, thresholds used, and adjustments.

Design contract:
    - Provenance is ATTACHED at export time, not computed retroactively.
    - Provenance traces are deterministic — same inputs, same trace.
    - Machine-readable, auditor-parseable, reconstructable.
    - No exported value without provenance → export blocked.
    - Provenance does NOT modify scores — it annotates them.

Provenance record structure:
    {
        "source_data": {file, axis, year, data_window},
        "transformation_chain": [step, step, ...],
        "rules_applied": [rule_id, ...],
        "thresholds_used": [threshold_id, ...],
        "adjustments": [adjustment, ...],
    }

Honesty note:
    Provenance traces WHERE a number came from, not WHETHER it is correct.
    A perfectly traced value can still be substantively wrong if the source
    data or methodology has flaws.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# TRANSFORMATION STEP TYPES
# ═══════════════════════════════════════════════════════════════════════════

class TransformationType:
    """Canonical labels for transformation steps in the pipeline."""
    RAW_INGEST = "RAW_INGEST"
    SCORE_NORMALIZATION = "SCORE_NORMALIZATION"
    SEVERITY_ASSESSMENT = "SEVERITY_ASSESSMENT"
    GOVERNANCE_ASSESSMENT = "GOVERNANCE_ASSESSMENT"
    CONFIDENCE_PENALTY = "CONFIDENCE_PENALTY"
    PRODUCER_INVERSION = "PRODUCER_INVERSION"
    FALSIFICATION_CHECK = "FALSIFICATION_CHECK"
    ELIGIBILITY_CLASSIFICATION = "ELIGIBILITY_CLASSIFICATION"
    USABILITY_CLASSIFICATION = "USABILITY_CLASSIFICATION"
    COMPOSITE_COMPUTATION = "COMPOSITE_COMPUTATION"
    INVARIANT_CHECK = "INVARIANT_CHECK"
    EXPORT_MATERIALIZATION = "EXPORT_MATERIALIZATION"


VALID_TRANSFORMATION_TYPES = frozenset({
    TransformationType.RAW_INGEST,
    TransformationType.SCORE_NORMALIZATION,
    TransformationType.SEVERITY_ASSESSMENT,
    TransformationType.GOVERNANCE_ASSESSMENT,
    TransformationType.CONFIDENCE_PENALTY,
    TransformationType.PRODUCER_INVERSION,
    TransformationType.FALSIFICATION_CHECK,
    TransformationType.ELIGIBILITY_CLASSIFICATION,
    TransformationType.USABILITY_CLASSIFICATION,
    TransformationType.COMPOSITE_COMPUTATION,
    TransformationType.INVARIANT_CHECK,
    TransformationType.EXPORT_MATERIALIZATION,
})


# ═══════════════════════════════════════════════════════════════════════════
# PROVENANCE RECORD CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════

def _step(
    step_type: str,
    module: str,
    function: str,
    detail: str | None = None,
) -> dict[str, Any]:
    """Create a single transformation step record."""
    record: dict[str, Any] = {
        "step": step_type,
        "module": module,
        "function": function,
    }
    if detail is not None:
        record["detail"] = detail
    return record


def build_axis_provenance(
    country: str,
    axis_id: int,
    score: float | None,
    year: int,
    data_window: str,
    methodology_version: str,
    severity_result: dict[str, Any] | None = None,
    governance_axis_confidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build provenance trace for a single axis score.

    Args:
        country: ISO-2 code.
        axis_id: 1-6.
        score: The axis score (or None if missing).
        year: Reference year.
        data_window: Data window string.
        methodology_version: e.g. "ISI-M-2025-001".
        severity_result: Severity analysis for this axis (if available).
        governance_axis_confidence: Governance axis confidence detail.

    Returns:
        Provenance record for this axis score.
    """
    source = {
        "file_pattern": f"axis_{axis_id}_scores_{year}.csv",
        "country": country,
        "axis_id": axis_id,
        "year": year,
        "data_window": data_window,
    }

    chain: list[dict[str, Any]] = []

    # Step 1: Raw ingest
    chain.append(_step(
        TransformationType.RAW_INGEST,
        "backend.export_snapshot",
        "load_axis_scores",
        f"axis_{axis_id} for {country}, year={year}",
    ))

    # Step 2: Score normalization (methodology-specific)
    chain.append(_step(
        TransformationType.SCORE_NORMALIZATION,
        "backend.methodology",
        "classify",
        f"methodology={methodology_version}, axis_{axis_id}",
    ))

    rules: list[str] = []
    thresholds: list[str] = []
    adjustments: list[dict[str, Any]] = []

    # Step 3: Severity assessment (if data available)
    if severity_result is not None:
        chain.append(_step(
            TransformationType.SEVERITY_ASSESSMENT,
            "backend.severity",
            "compute_axis_severity",
            f"axis_{axis_id}, degradation_groups applied",
        ))
        flags = severity_result.get("flags", [])
        for f in flags:
            if isinstance(f, str):
                rules.append(f"SEVERITY_FLAG:{f}")
            elif isinstance(f, dict):
                rules.append(f"SEVERITY_FLAG:{f.get('flag', 'UNKNOWN')}")

    # Step 4: Governance axis confidence (if data available)
    if governance_axis_confidence is not None:
        chain.append(_step(
            TransformationType.GOVERNANCE_ASSESSMENT,
            "backend.governance",
            "assess_axis_confidence",
            f"axis_{axis_id}, baseline → penalties → final",
        ))
        penalties = governance_axis_confidence.get("penalties_applied", [])
        for p in penalties:
            flag = p.get("flag", "UNKNOWN")
            amount = p.get("penalty_amount", 0)
            chain.append(_step(
                TransformationType.CONFIDENCE_PENALTY,
                "backend.governance",
                "assess_axis_confidence",
                f"penalty: {flag} (-{amount})",
            ))
            rules.append(f"GOV_PENALTY:{flag}")
            thresholds.append(f"CONFIDENCE_PENALTIES:{flag}")
            adjustments.append({
                "type": "confidence_penalty",
                "flag": flag,
                "amount": -amount,
                "rule_id": f"GOV_PENALTY_{flag}",
            })
        is_inverted = governance_axis_confidence.get("is_producer_inverted", False)
        if is_inverted:
            chain.append(_step(
                TransformationType.PRODUCER_INVERSION,
                "backend.governance",
                "assess_axis_confidence",
                f"axis_{axis_id} is producer-inverted for {country}",
            ))
            rules.append("PRODUCER_INVERSION_REGISTRY")

    return {
        "country": country,
        "axis_id": axis_id,
        "score": score,
        "source_data": source,
        "transformation_chain": chain,
        "rules_applied": rules,
        "thresholds_used": thresholds,
        "adjustments": adjustments,
        "is_complete": score is not None,
    }


def build_composite_provenance(
    country: str,
    composite_score: float | None,
    axis_scores: dict[int, float | None],
    methodology_version: str,
    year: int,
    data_window: str,
    governance_result: dict[str, Any] | None = None,
    severity_result: dict[str, Any] | None = None,
    falsification_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build provenance trace for the ISI composite score.

    Args:
        country: ISO-2 code.
        composite_score: The computed composite (or None).
        axis_scores: {axis_id: score_or_None}.
        methodology_version: e.g. "ISI-M-2025-001".
        year: Reference year.
        data_window: Data window string.
        governance_result: From assess_country_governance().
        severity_result: From compute_country_severity().
        falsification_result: From assess_country_falsification().

    Returns:
        Provenance record for the composite score.
    """
    contributing_axes = {k: v for k, v in axis_scores.items() if v is not None}

    source = {
        "derived_from": "axis_scores",
        "n_contributing_axes": len(contributing_axes),
        "contributing_axes": sorted(contributing_axes.keys()),
        "methodology_version": methodology_version,
        "year": year,
        "data_window": data_window,
    }

    chain: list[dict[str, Any]] = []
    rules: list[str] = []
    thresholds: list[str] = []
    adjustments: list[dict[str, Any]] = []

    # Step 1: Axis aggregation
    chain.append(_step(
        TransformationType.COMPOSITE_COMPUTATION,
        "backend.methodology",
        "compute_composite",
        f"aggregation over {len(contributing_axes)} axes, "
        f"methodology={methodology_version}",
    ))
    thresholds.append("methodology.aggregation_method")

    # Step 2: Governance assessment
    if governance_result:
        tier = governance_result.get("governance_tier", "UNKNOWN")
        chain.append(_step(
            TransformationType.GOVERNANCE_ASSESSMENT,
            "backend.governance",
            "assess_country_governance",
            f"tier={tier}",
        ))
        rules.append(f"GOVERNANCE_TIER:{tier}")
        thresholds.append("MIN_AXES_FOR_COMPOSITE")
        thresholds.append("MIN_AXES_FOR_RANKING")
        thresholds.append("MIN_MEAN_CONFIDENCE_FOR_RANKING")

    # Step 3: Severity assessment
    if severity_result:
        chain.append(_step(
            TransformationType.SEVERITY_ASSESSMENT,
            "backend.severity",
            "compute_country_severity",
            "country-level severity analysis",
        ))
        comp_tier = severity_result.get("comparability_tier")
        if comp_tier:
            rules.append(f"COMPARABILITY_TIER:{comp_tier}")

    # Step 4: Falsification check
    if falsification_result:
        status = falsification_result.get("falsification_flag", "NOT_ASSESSED")
        chain.append(_step(
            TransformationType.FALSIFICATION_CHECK,
            "backend.falsification",
            "assess_country_falsification",
            f"status={status}",
        ))
        rules.append(f"FALSIFICATION:{status}")
        checks = falsification_result.get("checks", [])
        for check in checks:
            check_id = check.get("check_id", "UNKNOWN")
            rules.append(f"FALSIFICATION_CHECK:{check_id}")

    return {
        "country": country,
        "composite_score": composite_score,
        "source_data": source,
        "transformation_chain": chain,
        "rules_applied": rules,
        "thresholds_used": thresholds,
        "adjustments": adjustments,
        "is_complete": composite_score is not None,
    }


def build_governance_provenance(
    country: str,
    governance_result: dict[str, Any],
) -> dict[str, Any]:
    """Build provenance trace for governance tier determination.

    Traces which of the 14 governance rules applied to produce
    the final governance tier.
    """
    tier = governance_result.get("governance_tier", "UNKNOWN")
    interpretation = governance_result.get("governance_interpretation", "")

    chain: list[dict[str, Any]] = [
        _step(
            TransformationType.GOVERNANCE_ASSESSMENT,
            "backend.governance",
            "_determine_governance_tier",
            f"14-rule cascade, first-match → {tier}",
        ),
    ]

    rules: list[str] = [
        f"GOVERNANCE_TIER_RESULT:{tier}",
    ]
    thresholds: list[str] = [
        "AXIS_CONFIDENCE_BASELINES",
        "CONFIDENCE_PENALTIES",
        "CONFIDENCE_THRESHOLDS",
        "MIN_AXES_FOR_COMPOSITE",
        "MIN_AXES_FOR_RANKING",
        "MIN_MEAN_CONFIDENCE_FOR_RANKING",
        "MAX_LOW_CONFIDENCE_AXES_FOR_RANKING",
        "MAX_INVERTED_AXES_FOR_COMPARABLE",
    ]

    # Track structural limitations
    limitations = governance_result.get("structural_limitations", [])
    for lim in limitations:
        rules.append(f"STRUCTURAL_LIMITATION:{lim}")

    return {
        "country": country,
        "governance_tier": tier,
        "source_data": {
            "n_axes_with_data": governance_result.get("n_axes_with_data", 0),
            "mean_axis_confidence": governance_result.get("mean_axis_confidence", 0),
            "n_producer_inverted_axes": governance_result.get("n_producer_inverted_axes", 0),
        },
        "transformation_chain": chain,
        "rules_applied": rules,
        "thresholds_used": thresholds,
        "adjustments": [],
        "interpretation": interpretation,
    }


def build_usability_provenance(
    country: str,
    usability_class: str,
    governance_result: dict[str, Any] | None = None,
    falsification_result: dict[str, Any] | None = None,
    invariant_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build provenance for DecisionUsabilityClass determination."""
    chain: list[dict[str, Any]] = []
    rules: list[str] = [f"USABILITY_CLASS:{usability_class}"]
    thresholds: list[str] = []

    chain.append(_step(
        TransformationType.USABILITY_CLASSIFICATION,
        "backend.eligibility",
        "classify_decision_usability",
        f"result={usability_class}",
    ))

    if governance_result:
        tier = governance_result.get("governance_tier", "UNKNOWN")
        rules.append(f"GOVERNANCE_INPUT:{tier}")

    if falsification_result:
        flag = falsification_result.get("falsification_flag", "NOT_ASSESSED")
        rules.append(f"FALSIFICATION_INPUT:{flag}")

    if invariant_result:
        n_critical = invariant_result.get("n_critical", 0)
        if n_critical > 0:
            chain.append(_step(
                TransformationType.INVARIANT_CHECK,
                "backend.invariants",
                "should_downgrade_usability",
                f"{n_critical} critical violations → downgrade",
            ))
            rules.append(f"INVARIANT_DOWNGRADE:n_critical={n_critical}")

    return {
        "country": country,
        "usability_class": usability_class,
        "source_data": {
            "governance_tier": governance_result.get("governance_tier") if governance_result else None,
            "falsification_flag": falsification_result.get("falsification_flag") if falsification_result else None,
            "n_invariant_critical": invariant_result.get("n_critical", 0) if invariant_result else 0,
        },
        "transformation_chain": chain,
        "rules_applied": rules,
        "thresholds_used": thresholds,
        "adjustments": [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# FULL COUNTRY PROVENANCE BUNDLE
# ═══════════════════════════════════════════════════════════════════════════

def build_country_provenance(
    country: str,
    axis_scores: dict[int, float | None],
    composite_score: float | None,
    methodology_version: str,
    year: int,
    data_window: str,
    governance_result: dict[str, Any] | None = None,
    severity_result: dict[str, Any] | None = None,
    falsification_result: dict[str, Any] | None = None,
    invariant_result: dict[str, Any] | None = None,
    usability_class: str | None = None,
    axis_governance_details: list[dict[str, Any]] | None = None,
    axis_severity_details: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build complete provenance bundle for a country.

    This is the top-level provenance function that composes axis-level,
    composite-level, governance-level, and usability-level traces.

    Returns:
        {
            "country": str,
            "provenance_version": "1.0",
            "axes": {axis_id: axis_provenance},
            "composite": composite_provenance,
            "governance": governance_provenance,
            "usability": usability_provenance,
            "completeness": {n_axes_traced, n_complete, is_fully_traced},
        }
    """
    axis_provenances: dict[int, dict[str, Any]] = {}
    for ax_id in range(1, 7):
        score = axis_scores.get(ax_id)
        ax_sev = (axis_severity_details or {}).get(ax_id)
        ax_gov = None
        if axis_governance_details:
            for ag in axis_governance_details:
                if ag.get("axis_id") == ax_id:
                    ax_gov = ag
                    break

        axis_provenances[ax_id] = build_axis_provenance(
            country=country,
            axis_id=ax_id,
            score=score,
            year=year,
            data_window=data_window,
            methodology_version=methodology_version,
            severity_result=ax_sev,
            governance_axis_confidence=ax_gov,
        )

    composite_prov = build_composite_provenance(
        country=country,
        composite_score=composite_score,
        axis_scores=axis_scores,
        methodology_version=methodology_version,
        year=year,
        data_window=data_window,
        governance_result=governance_result,
        severity_result=severity_result,
        falsification_result=falsification_result,
    )

    governance_prov = (
        build_governance_provenance(country, governance_result)
        if governance_result else None
    )

    usability_prov = (
        build_usability_provenance(
            country, usability_class or "UNKNOWN",
            governance_result, falsification_result, invariant_result,
        )
        if usability_class else None
    )

    n_complete = sum(
        1 for p in axis_provenances.values() if p["is_complete"]
    )

    return {
        "country": country,
        "provenance_version": "1.0",
        "axes": axis_provenances,
        "composite": composite_prov,
        "governance": governance_prov,
        "usability": usability_prov,
        "completeness": {
            "n_axes_traced": 6,
            "n_complete": n_complete,
            "is_fully_traced": True,
        },
        "honesty_note": (
            "Provenance traces WHERE a number came from, not WHETHER "
            "it is correct. A perfectly traced value can still be wrong "
            "if the source data or methodology has flaws."
        ),
    }


def validate_provenance(
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Validate that a provenance record is structurally complete.

    Returns:
        {
            "is_valid": bool,
            "missing_fields": [str],
            "n_axes_traced": int,
            "n_complete_axes": int,
            "has_composite": bool,
            "has_governance": bool,
            "has_usability": bool,
        }
    """
    missing: list[str] = []

    if "country" not in provenance:
        missing.append("country")
    if "provenance_version" not in provenance:
        missing.append("provenance_version")
    if "axes" not in provenance:
        missing.append("axes")
    if "composite" not in provenance:
        missing.append("composite")

    axes = provenance.get("axes", {})
    n_traced = len(axes)
    n_complete = sum(1 for a in axes.values() if a.get("is_complete"))

    # Check each axis provenance has required fields
    for ax_id, ax_prov in axes.items():
        for field in ("source_data", "transformation_chain"):
            if field not in ax_prov:
                missing.append(f"axes.{ax_id}.{field}")

    has_composite = provenance.get("composite") is not None
    has_governance = provenance.get("governance") is not None
    has_usability = provenance.get("usability") is not None

    return {
        "is_valid": len(missing) == 0,
        "missing_fields": missing,
        "n_axes_traced": n_traced,
        "n_complete_axes": n_complete,
        "has_composite": has_composite,
        "has_governance": has_governance,
        "has_usability": has_usability,
    }
