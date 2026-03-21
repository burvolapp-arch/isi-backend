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
        """Canonical JSON-serializable representation."""
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
        }


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
        """Canonical JSON-serializable representation."""
        return {
            "country": self.country,
            "country_name": self.country_name,
            "isi_composite": self.isi_composite,
            "classification": self.classification,
            "axes_included": self.axes_included,
            "axes_excluded": [dict(e) for e in self.axes_excluded],
            "confidence": self.confidence,
            "scope": self.scope,
            "methodology_version": self.methodology_version,
            "warnings": list(self.warnings),
            "axes": [ar.to_dict() for ar in self.axis_results],
        }


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
            if ar.validity == "DEGRADED":
                n_degraded += 1

        # Collect warnings
        all_warnings.extend(ar.warnings)

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

        # Confidence: constraint spec Section 9.3
        if n_degraded == 0 and n_computable == 6:
            confidence = "FULL"
        elif n_degraded > 2 or n_computable == 4:
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
