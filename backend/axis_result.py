"""
backend.axis_result — Structured axis and composite result types for ISI.

This module defines the canonical output schema for axis-level and
composite-level ISI results, as specified in the constraint specification
(Sections 9.1, 9.2, 9.3).

Every axis computation in the v1.1+ pipeline MUST produce an AxisResult.
Every composite computation MUST produce a CompositeResult.

Validation is strict and fail-fast. Malformed results raise ValueError
immediately — no silent degradation.

Design contract:
    - AxisResult and CompositeResult are immutable after creation.
    - validate_axis_result() and validate_composite_result() are the ONLY
      validation functions for these types.
    - to_dict() produces JSON-serializable output in canonical form.
    - No optional fields silently omitted — all fields present, null if absent.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from backend.constants import ROUND_PRECISION
from backend.severity import (
    compute_axis_severity,
    compute_axis_data_severity,
    compute_axis_severity_breakdown,
    compute_country_severity,
    assign_comparability_tier,
    compute_adjusted_composite,
    compute_stability_analysis,
    build_interpretation,
    classify_structural_class,
    SEVERITY_WEIGHTS,
)

# ---------------------------------------------------------------------------
# Enums (string-based for JSON compatibility)
# ---------------------------------------------------------------------------

# Basis: how the axis score was computed
VALID_BASIS = frozenset({"BOTH", "A_ONLY", "B_ONLY", "INVALID"})

# Validity: structural quality of the axis result
VALID_VALIDITY = frozenset({"VALID", "A_ONLY", "DEGRADED", "INVALID"})

# Confidence: composite-level quality assessment
VALID_CONFIDENCE = frozenset({"FULL", "REDUCED", "LOW_CONFIDENCE"})

# Warning codes (non-exhaustive — new codes may be added)
KNOWN_WARNING_CODES = frozenset({
    "W-PRODUCER-INVERSION",
    "W-HS6-GRANULARITY",
    "W-TEMPORAL-MIX",
    "W-SANCTIONS-DISTORTION",
    "F-CPIS-ABSENT",
    "D-5",  # zero bilateral suppliers (defense)
})

# Axis slugs
AXIS_SLUGS = (
    "financial",
    "energy",
    "technology",
    "defense",
    "critical_inputs",
    "logistics",
)

AXIS_ID_TO_SLUG: dict[int, str] = {
    1: "financial",
    2: "energy",
    3: "technology",
    4: "defense",
    5: "critical_inputs",
    6: "logistics",
}


# ---------------------------------------------------------------------------
# AxisResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AxisResult:
    """Structured result for a single axis computation for a single country.

    All fields correspond to constraint specification Section 9.1.
    """
    country: str
    axis_id: int
    axis_slug: str
    score: float | None
    basis: str
    validity: str
    coverage: float | None  # [0.0, 1.0] or None if full coverage
    source: str
    warnings: tuple[str, ...]  # immutable sequence
    channel_a_concentration: float | None
    channel_b_concentration: float | None

    def to_dict(self) -> dict[str, Any]:
        """Canonical JSON-serializable representation.

        Includes `data_quality_flags` — a machine-readable list of every
        structural weakness in this result. Consumers MUST NOT ignore this
        field. If it is non-empty, the score is NOT directly comparable
        to scores produced under different conditions.

        Includes `degradation_severity` — a float quantifying the total
        severity of all data quality issues on this axis. 0.0 = clean.
        Higher values indicate greater interpretive compromise.
        """
        flags = _build_quality_flags(self)
        severity = compute_axis_severity(flags)
        data_severity = compute_axis_data_severity(flags)
        return {
            "country": self.country,
            "axis_id": self.axis_id,
            "axis_slug": self.axis_slug,
            "score": self.score,
            "basis": self.basis,
            "validity": self.validity,
            "coverage": self.coverage,
            "source": self.source,
            "warnings": list(self.warnings),
            "channel_a_concentration": self.channel_a_concentration,
            "channel_b_concentration": self.channel_b_concentration,
            "data_quality_flags": flags,
            "degradation_severity": severity,
            "data_severity": data_severity,
        }


def _build_quality_flags(r: "AxisResult") -> list[str]:
    """Derive machine-readable data quality flags from an AxisResult.

    These flags make every structural weakness explicit in the serialized
    output. A consumer receiving a non-empty list MUST treat the score
    as non-comparable to unflagged scores without adjustment.

    Flags are deterministic: same AxisResult → same flags.
    """
    flags: list[str] = []

    if r.validity == "INVALID":
        flags.append("INVALID_AXIS")
        return flags  # No further flags meaningful

    # --- Channel degradation ---
    if r.basis == "A_ONLY":
        flags.append("SINGLE_CHANNEL_A")
    elif r.basis == "B_ONLY":
        flags.append("SINGLE_CHANNEL_B")

    # --- Granularity warnings ---
    if any("W-HS6-GRANULARITY" in w for w in r.warnings):
        flags.append("REDUCED_PRODUCT_GRANULARITY")

    # --- Producer inversion ---
    if any("W-PRODUCER-INVERSION" in w for w in r.warnings):
        flags.append("PRODUCER_INVERSION")

    # --- Sanctions distortion ---
    if any("W-SANCTIONS-DISTORTION" in w for w in r.warnings):
        flags.append("SANCTIONS_DISTORTION")

    # --- CPIS absence ---
    if any("F-CPIS-ABSENT" in w for w in r.warnings):
        flags.append("CPIS_NON_PARTICIPANT")

    # --- Zero-supplier structural zero (defense) ---
    if any("D-5" in w for w in r.warnings):
        flags.append("ZERO_BILATERAL_SUPPLIERS")

    # --- Temporal mismatch ---
    if any("W-TEMPORAL-MIX" in w for w in r.warnings):
        flags.append("TEMPORAL_MISMATCH")

    return flags


def validate_axis_result(r: AxisResult) -> None:
    """Validate an AxisResult. Raises ValueError on any violation.

    Checks:
    - basis and validity are valid enum values
    - score is in [0.0, 1.0] if not None
    - channel concentrations are in [0.0, 1.0] if not None
    - INVALID basis implies score is None
    - axis_id in [1, 6]
    - axis_slug matches axis_id
    - coverage in [0.0, 1.0] if not None
    - no NaN or Inf in any numeric field
    """
    if r.basis not in VALID_BASIS:
        raise ValueError(
            f"AxisResult({r.country}, axis {r.axis_id}): "
            f"invalid basis '{r.basis}'. Must be one of {sorted(VALID_BASIS)}"
        )

    if r.validity not in VALID_VALIDITY:
        raise ValueError(
            f"AxisResult({r.country}, axis {r.axis_id}): "
            f"invalid validity '{r.validity}'. Must be one of {sorted(VALID_VALIDITY)}"
        )

    if r.axis_id not in AXIS_ID_TO_SLUG:
        raise ValueError(
            f"AxisResult({r.country}): axis_id {r.axis_id} not in [1..6]"
        )

    if r.axis_slug != AXIS_ID_TO_SLUG[r.axis_id]:
        raise ValueError(
            f"AxisResult({r.country}, axis {r.axis_id}): "
            f"slug mismatch '{r.axis_slug}' != expected '{AXIS_ID_TO_SLUG[r.axis_id]}'"
        )

    # INVALID basis → score must be None
    if r.basis == "INVALID" and r.score is not None:
        raise ValueError(
            f"AxisResult({r.country}, axis {r.axis_id}): "
            f"basis=INVALID but score is not None ({r.score})"
        )

    # INVALID validity → score must be None
    if r.validity == "INVALID" and r.score is not None:
        raise ValueError(
            f"AxisResult({r.country}, axis {r.axis_id}): "
            f"validity=INVALID but score is not None ({r.score})"
        )

    # Non-INVALID → score must be present
    if r.basis != "INVALID" and r.validity != "INVALID" and r.score is None:
        raise ValueError(
            f"AxisResult({r.country}, axis {r.axis_id}): "
            f"basis={r.basis}, validity={r.validity} but score is None"
        )

    # Numeric field validation
    for name, val in [
        ("score", r.score),
        ("channel_a_concentration", r.channel_a_concentration),
        ("channel_b_concentration", r.channel_b_concentration),
        ("coverage", r.coverage),
    ]:
        if val is None:
            continue
        if math.isnan(val) or math.isinf(val):
            raise ValueError(
                f"AxisResult({r.country}, axis {r.axis_id}): "
                f"{name} is NaN or Inf ({val})"
            )
        if val < 0.0 or val > 1.0 + 1e-9:
            raise ValueError(
                f"AxisResult({r.country}, axis {r.axis_id}): "
                f"{name} out of [0.0, 1.0]: {val}"
            )


def make_invalid_axis(
    country: str,
    axis_id: int,
    source: str,
    warnings: tuple[str, ...] = (),
) -> AxisResult:
    """Create an INVALID AxisResult for a country/axis pair.

    Used when an axis cannot be computed (no data, coverage < 50%, etc.).
    """
    return AxisResult(
        country=country,
        axis_id=axis_id,
        axis_slug=AXIS_ID_TO_SLUG[axis_id],
        score=None,
        basis="INVALID",
        validity="INVALID",
        coverage=None,
        source=source,
        warnings=warnings,
        channel_a_concentration=None,
        channel_b_concentration=None,
    )


# ---------------------------------------------------------------------------
# CompositeResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompositeResult:
    """Structured result for a country's ISI composite score.

    All fields correspond to constraint specification Section 9.2.
    """
    country: str
    country_name: str
    isi_composite: float | None
    classification: str | None
    axes_included: int
    axes_excluded: tuple[dict[str, Any], ...]  # ({axis_id, reason}, ...)
    confidence: str
    scope: str
    methodology_version: str
    warnings: tuple[str, ...]
    axis_results: tuple[AxisResult, ...]  # all 6 axis results

    def to_dict(self) -> dict[str, Any]:
        """Canonical JSON-serializable representation.

        Includes:
        - `comparability_tier` (legacy) and `structural_degradation_profile`
        - `composite_raw` — current unweighted arithmetic mean
        - `composite_adjusted` — degradation-aware weighted composite
        - `severity_analysis` — per-axis and total severity metrics
        - `strict_comparability_tier` — TIER_1/2/3/4 from severity model
        - `stability_analysis` — leave-one-out sensitivity metrics
        - `interpretation_flags` / `interpretation_summary` — mandatory
          human-readable interpretation with explicit warning language

        No composite output can appear "clean" when the underlying
        axis data quality is asymmetric or degraded.
        """
        # Legacy comparability (kept for backward compatibility)
        legacy_tier, profile = _compute_comparability(
            self.axis_results, self.axes_included
        )

        # Per-axis severity + country severity
        axis_dicts = [ar.to_dict() for ar in self.axis_results]
        axis_severities: list[tuple[int, str, float]] = []
        included_axis_scores: list[tuple[float, float]] = []
        included_axes_for_stability: list[tuple[int, str, float]] = []

        for ad in axis_dicts:
            if ad["validity"] != "INVALID":
                sev = ad["degradation_severity"]
                axis_severities.append((ad["axis_id"], ad["axis_slug"], sev))
                if ad["score"] is not None:
                    # Use data_severity (not total severity) for aggregation
                    # weights. Structural severity affects comparability
                    # assessment but NOT the quality weight function.
                    data_sev = ad["data_severity"]
                    included_axis_scores.append((ad["score"], data_sev))
                    included_axes_for_stability.append(
                        (ad["axis_id"], ad["axis_slug"], ad["score"])
                    )

        country_sev = compute_country_severity(axis_severities)
        total_severity = country_sev["total_severity"]

        # Strict comparability tier (severity-driven)
        strict_tier = assign_comparability_tier(total_severity)

        # Degradation-adjusted composite (only if raw composite is eligible)
        if self.isi_composite is not None:
            composite_adjusted = compute_adjusted_composite(included_axis_scores)
        else:
            composite_adjusted = None

        # Stability analysis (leave-one-out)
        stability = compute_stability_analysis(included_axes_for_stability)

        # Interpretation engine
        interpretation = build_interpretation(
            total_severity=total_severity,
            comparability_tier=strict_tier,
            n_degraded_axes=country_sev["n_degraded_axes"],
            n_included_axes=self.axes_included,
            confidence=self.confidence,
            warnings=list(self.warnings),
        )

        # Structural class (IMPORTER / BALANCED / PRODUCER)
        structural_class_info = classify_structural_class(
            self.country, axis_dicts,
        )

        return {
            "country": self.country,
            "country_name": self.country_name,
            "isi_composite": self.isi_composite,
            "composite_raw": self.isi_composite,
            "composite_adjusted": composite_adjusted,
            "classification": self.classification,
            "axes_included": self.axes_included,
            "axes_excluded": [dict(e) for e in self.axes_excluded],
            "confidence": self.confidence,
            "comparability_tier": legacy_tier,
            "strict_comparability_tier": strict_tier,
            "severity_analysis": country_sev,
            "structural_degradation_profile": profile,
            "structural_class": structural_class_info,
            "stability_analysis": stability,
            "interpretation_flags": interpretation["interpretation_flags"],
            "interpretation_summary": interpretation["interpretation_summary"],
            "scope": self.scope,
            "methodology_version": self.methodology_version,
            "warnings": list(self.warnings),
            "axes": axis_dicts,
        }


def _compute_comparability(
    axis_results: tuple["AxisResult", ...],
    axes_included: int,
) -> tuple[str, dict[str, Any]]:
    """Derive comparability tier and degradation profile from axis results.

    Tiers:
        FULL_COMPARABILITY  — 6 axes, all VALID, all BOTH basis, no granularity warnings
        HIGH_COMPARABILITY  — 5-6 axes, mostly VALID, minor degradation
        LIMITED_COMPARABILITY — 4+ axes but significant degradation (A_ONLY, mixed sources)
        NOT_COMPARABLE      — fewer than 4 axes or severe structural issues

    The profile dict gives machine-readable counts of each degradation type.
    """
    n_valid_both = 0
    n_a_only = 0
    n_b_only = 0
    n_degraded = 0
    n_invalid = 0
    n_producer_inversion = 0
    n_reduced_granularity = 0
    n_zero_suppliers = 0
    unique_sources: set[str] = set()

    for ar in axis_results:
        if ar.validity == "INVALID":
            n_invalid += 1
            continue
        if ar.validity == "VALID" and ar.basis == "BOTH":
            n_valid_both += 1
        if ar.basis == "A_ONLY":
            n_a_only += 1
        elif ar.basis == "B_ONLY":
            n_b_only += 1
        if ar.validity == "DEGRADED":
            n_degraded += 1
        if any("W-PRODUCER-INVERSION" in w for w in ar.warnings):
            n_producer_inversion += 1
        if any("W-HS6-GRANULARITY" in w for w in ar.warnings):
            n_reduced_granularity += 1
        if any("D-5" in w for w in ar.warnings):
            n_zero_suppliers += 1
        if ar.source:
            unique_sources.add(ar.source)

    profile: dict[str, Any] = {
        "axes_valid_both": n_valid_both,
        "axes_a_only": n_a_only,
        "axes_b_only": n_b_only,
        "axes_degraded": n_degraded,
        "axes_invalid": n_invalid,
        "axes_producer_inverted": n_producer_inversion,
        "axes_reduced_granularity": n_reduced_granularity,
        "axes_zero_bilateral_suppliers": n_zero_suppliers,
        "unique_source_count": len(unique_sources),
        "source_heterogeneous": len(unique_sources) > 1,
    }

    # Determine tier
    if axes_included < 4:
        tier = "NOT_COMPARABLE"
    elif (
        n_valid_both == 6
        and n_a_only == 0
        and n_degraded == 0
        and n_reduced_granularity == 0
    ):
        tier = "FULL_COMPARABILITY"
    elif (
        axes_included >= 5
        and n_a_only <= 1
        and n_degraded == 0
    ):
        tier = "HIGH_COMPARABILITY"
    else:
        tier = "LIMITED_COMPARABILITY"

    return tier, profile


def validate_composite_result(r: CompositeResult) -> None:
    """Validate a CompositeResult. Raises ValueError on any violation."""
    if r.confidence not in VALID_CONFIDENCE:
        raise ValueError(
            f"CompositeResult({r.country}): "
            f"invalid confidence '{r.confidence}'. "
            f"Must be one of {sorted(VALID_CONFIDENCE)}"
        )

    if r.isi_composite is not None:
        if math.isnan(r.isi_composite) or math.isinf(r.isi_composite):
            raise ValueError(
                f"CompositeResult({r.country}): composite is NaN/Inf"
            )
        if r.isi_composite < 0.0 or r.isi_composite > 1.0 + 1e-9:
            raise ValueError(
                f"CompositeResult({r.country}): composite out of [0,1]: "
                f"{r.isi_composite}"
            )

    # axes_included + len(axes_excluded) must equal total axis count
    total = r.axes_included + len(r.axes_excluded)
    if total != 6:
        raise ValueError(
            f"CompositeResult({r.country}): "
            f"axes_included ({r.axes_included}) + axes_excluded "
            f"({len(r.axes_excluded)}) != 6"
        )

    # If composite is None, axes_included must be < 4
    # (or there's an internal logic error)
    if r.isi_composite is None and r.axes_included >= 4:
        raise ValueError(
            f"CompositeResult({r.country}): composite is None but "
            f"axes_included={r.axes_included} >= 4"
        )

    # Validate all axis results
    for ar in r.axis_results:
        validate_axis_result(ar)

    # --- Phase 8: Validation hardening for new mandatory fields ---
    d = r.to_dict()

    # severity_analysis must be present and non-empty
    if "severity_analysis" not in d:
        raise ValueError(
            f"CompositeResult({r.country}): missing severity_analysis"
        )
    sev = d["severity_analysis"]
    if "total_severity" not in sev:
        raise ValueError(
            f"CompositeResult({r.country}): severity_analysis missing total_severity"
        )

    # strict_comparability_tier must be present
    if "strict_comparability_tier" not in d:
        raise ValueError(
            f"CompositeResult({r.country}): missing strict_comparability_tier"
        )

    # composite_adjusted must be present (may be None for ineligible)
    if "composite_adjusted" not in d:
        raise ValueError(
            f"CompositeResult({r.country}): missing composite_adjusted"
        )

    # stability_analysis must be present
    if "stability_analysis" not in d:
        raise ValueError(
            f"CompositeResult({r.country}): missing stability_analysis"
        )

    # interpretation_flags and interpretation_summary must be present
    if "interpretation_flags" not in d:
        raise ValueError(
            f"CompositeResult({r.country}): missing interpretation_flags"
        )
    if "interpretation_summary" not in d:
        raise ValueError(
            f"CompositeResult({r.country}): missing interpretation_summary"
        )

    # Severity must be consistent with flags:
    # If any axis has data_quality_flags but severity is missing, fail.
    for ad in d.get("axes", []):
        if ad.get("data_quality_flags") and "degradation_severity" not in ad:
            raise ValueError(
                f"CompositeResult({r.country}): axis {ad.get('axis_id')} "
                f"has data_quality_flags but missing degradation_severity"
            )


# ---------------------------------------------------------------------------
# Composite computation (v1.1 path)
# ---------------------------------------------------------------------------

def compute_composite_v11(
    axis_results: list[AxisResult],
    country: str,
    country_name: str,
    scope_id: str,
    methodology_version: str,
) -> CompositeResult:
    """Compute ISI composite for v1.1 methodology.

    Implements constraint specification Sections 5.3, 5.4, 8.3, 9.2, 9.3.

    Rules:
    - INVALID axes are excluded from composite.
    - VALID, A_ONLY, DEGRADED axes are included.
    - Composite = arithmetic mean of included axis scores.
    - If < 4 computable axes → composite is None.
    - Confidence assigned per Section 9.3.
    """
    from backend.methodology import classify

    if len(axis_results) != 6:
        raise ValueError(
            f"compute_composite_v11({country}): expected 6 axis results, "
            f"got {len(axis_results)}"
        )

    included: list[AxisResult] = []
    excluded: list[dict[str, Any]] = []
    all_warnings: list[str] = []
    n_degraded = 0
    n_a_only = 0
    included_sources: set[str] = set()

    for ar in axis_results:
        validate_axis_result(ar)

        if ar.validity == "INVALID":
            excluded.append({
                "axis_id": ar.axis_id,
                "axis_slug": ar.axis_slug,
                "reason": "INVALID — " + (ar.warnings[0] if ar.warnings else "no data"),
            })
        else:
            included.append(ar)
            included_sources.add(ar.source)
            if ar.validity == "DEGRADED":
                n_degraded += 1
            if ar.basis in ("A_ONLY", "B_ONLY"):
                n_a_only += 1

        # Collect warnings
        all_warnings.extend(ar.warnings)

    # Source heterogeneity: if included axes use >2 distinct data sources,
    # the composite mixes incompatible provenance → flag it.
    if len(included_sources) > 2:
        all_warnings.append(
            f"W-SOURCE-HETEROGENEITY: composite merges {len(included_sources)} "
            f"distinct data sources — cross-country comparability is limited"
        )

    # Channel degradation: if >50% of included axes are single-channel,
    # the composite structurally lacks the dual-channel robustness.
    if included and n_a_only > len(included) / 2:
        all_warnings.append(
            f"W-CHANNEL-DEGRADATION: {n_a_only}/{len(included)} included axes "
            f"are single-channel — composite reliability is reduced"
        )

    n_computable = len(included)

    # Composite eligibility: constraint spec Section 5.3
    if n_computable < 4:
        composite = None
        classification = None
        confidence = "LOW_CONFIDENCE"
    else:
        scores = [ar.score for ar in included]
        assert all(s is not None for s in scores)
        raw = sum(scores) / len(scores)  # type: ignore[arg-type]
        composite = round(raw, ROUND_PRECISION)
        classification = classify(composite, methodology_version)

        # Confidence: constraint spec Section 9.3 (hardened)
        # FULL requires: all 6 axes computable, none DEGRADED, none single-channel
        # A_ONLY axes are structurally incomplete — they MUST reduce confidence.
        n_structurally_weak = n_degraded + n_a_only
        if n_structurally_weak == 0 and n_computable == 6:
            confidence = "FULL"
        elif n_structurally_weak > 2 or n_computable == 4:
            confidence = "LOW_CONFIDENCE"
        else:
            confidence = "REDUCED"

    result = CompositeResult(
        country=country,
        country_name=country_name,
        isi_composite=composite,
        classification=classification,
        axes_included=n_computable,
        axes_excluded=tuple(excluded),
        confidence=confidence,
        scope=scope_id,
        methodology_version=methodology_version,
        warnings=tuple(sorted(set(all_warnings))),
        axis_results=tuple(axis_results),
    )

    validate_composite_result(result)
    return result
