"""
backend.scenario — ISI Scenario Simulation Engine

Pure-computation module. Zero I/O. Zero global state.
All functions are deterministic and bounded.

Given a country's baseline axis scores and a set of adjustments,
computes the simulated axis scores, composite, rank, classification,
and deltas from baseline.

The ISI composite is:
    ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6

Classification thresholds (frozen v0.1):
    >= 0.25  → highly_concentrated
    >= 0.15  → moderately_concentrated
    >= 0.10  → mildly_concentrated
    <  0.10  → unconcentrated
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants — frozen v0.1
# ---------------------------------------------------------------------------

NUM_AXES = 6

# Canonical axis slugs in axis-ID order (1–6)
AXIS_SLUGS: tuple[str, ...] = (
    "financial",
    "energy",
    "technology",
    "defense",
    "critical_inputs",
    "logistics",
)

AXIS_SLUG_SET: frozenset[str] = frozenset(AXIS_SLUGS)

# Maps axis slug → key in isi.json countries[] objects
AXIS_SLUG_TO_ISI_KEY: dict[str, str] = {
    "financial": "axis_1_financial",
    "energy": "axis_2_energy",
    "technology": "axis_3_technology",
    "defense": "axis_4_defense",
    "critical_inputs": "axis_5_critical_inputs",
    "logistics": "axis_6_logistics",
}

# Maximum allowed adjustment magnitude per axis
MAX_ADJUSTMENT = 0.20

# Classification thresholds (descending)
_CLASSIFICATION_THRESHOLDS: list[tuple[float, str]] = [
    (0.25, "highly_concentrated"),
    (0.15, "moderately_concentrated"),
    (0.10, "mildly_concentrated"),
]
_CLASSIFICATION_DEFAULT = "unconcentrated"


# ---------------------------------------------------------------------------
# Pydantic request model — strict validation
# ---------------------------------------------------------------------------

class ScenarioRequest(BaseModel):
    """Validated scenario simulation request.

    Rejects:
      - unknown fields
      - unknown axis slugs
      - adjustments outside [-0.20, +0.20]
      - NaN, Inf, non-numeric values
    """

    model_config = {"extra": "forbid"}

    country_code: str
    adjustments: dict[str, float]

    @field_validator("country_code")
    @classmethod
    def _validate_country_code(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError(f"Invalid country code: '{v}'. Must be 2-letter ISO alpha.")
        return v

    @field_validator("adjustments")
    @classmethod
    def _validate_adjustments(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("adjustments must contain at least one axis slug.")
        for slug, adj in v.items():
            if slug not in AXIS_SLUG_SET:
                raise ValueError(
                    f"Unknown axis slug: '{slug}'. "
                    f"Valid slugs: {sorted(AXIS_SLUG_SET)}"
                )
            if not isinstance(adj, (int, float)):
                raise ValueError(f"Adjustment for '{slug}' must be numeric, got {type(adj).__name__}.")
            if math.isnan(adj) or math.isinf(adj):
                raise ValueError(f"Adjustment for '{slug}' must be finite (got {'NaN' if math.isnan(adj) else 'Inf'}).")
            if adj < -MAX_ADJUSTMENT or adj > MAX_ADJUSTMENT:
                raise ValueError(
                    f"Adjustment for '{slug}' = {adj} is out of range "
                    f"[{-MAX_ADJUSTMENT}, +{MAX_ADJUSTMENT}]."
                )
        return v

    @model_validator(mode="after")
    def _no_nan_in_adjustments(self) -> ScenarioRequest:
        """Double-check after coercion."""
        for slug, adj in self.adjustments.items():
            if math.isnan(adj) or math.isinf(adj):
                raise ValueError(f"Adjustment for '{slug}' is not finite after coercion.")
        return self


# ---------------------------------------------------------------------------
# Pure computation functions
# ---------------------------------------------------------------------------

def classify(composite: float) -> str:
    """Map a composite score to its classification string.

    Deterministic. Safe for any float in [0, 1].
    """
    for threshold, label in _CLASSIFICATION_THRESHOLDS:
        if composite >= threshold:
            return label
    return _CLASSIFICATION_DEFAULT


def clamp01(value: float) -> float:
    """Clamp a value to [0.0, 1.0]. Handles NaN/Inf safely."""
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return max(0.0, min(1.0, value))


def compute_composite(axis_scores: dict[str, float]) -> float:
    """Compute ISI composite as unweighted arithmetic mean of 6 axes.

    All inputs must already be clamped to [0, 1].
    Result is clamped to [0, 1].
    """
    total = sum(axis_scores[slug] for slug in AXIS_SLUGS)
    return clamp01(total / NUM_AXES)


def compute_rank(
    country_code: str,
    simulated_composite: float,
    all_baselines: list[dict[str, Any]],
) -> int:
    """Compute rank (1 = highest dependency) among all 27 countries.

    Replaces the target country's baseline composite with the simulated value,
    then sorts descending. Ties are broken by country code (alphabetical).
    Returns rank in [1, len(all_baselines)].
    """
    composites: list[tuple[float, str]] = []
    for entry in all_baselines:
        code = entry["country"]
        if code == country_code:
            composites.append((simulated_composite, code))
        else:
            composites.append((entry["isi_composite"], code))

    # Sort: descending by composite, then ascending by code for tie-breaking
    composites.sort(key=lambda x: (-x[0], x[1]))

    for i, (_, code) in enumerate(composites, 1):
        if code == country_code:
            return i

    # Should never happen if country_code is in all_baselines
    return len(all_baselines)


def simulate(
    country_code: str,
    adjustments: dict[str, float],
    all_baselines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a scenario simulation for one country.

    Args:
        country_code: ISO-2 country code (uppercase, validated).
        adjustments: {axis_slug: delta} — each in [-0.20, +0.20].
        all_baselines: The full countries array from isi.json.

    Returns:
        Structured result dict with baseline, simulated, delta sections.

    Raises:
        ValueError: If country_code not found in baselines.
        RuntimeError: If any numerical invariant is violated.
    """
    # --- Find baseline for the target country ---
    baseline_entry: dict[str, Any] | None = None
    for entry in all_baselines:
        if entry["country"] == country_code:
            baseline_entry = entry
            break

    if baseline_entry is None:
        raise ValueError(f"Country '{country_code}' not found in ISI baseline data.")

    # --- Extract baseline axis scores ---
    baseline_axes: dict[str, float] = {}
    for slug in AXIS_SLUGS:
        key = AXIS_SLUG_TO_ISI_KEY[slug]
        raw = baseline_entry.get(key)
        if raw is None or not isinstance(raw, (int, float)):
            raise RuntimeError(f"Baseline data corrupt: missing or non-numeric '{key}' for {country_code}.")
        baseline_axes[slug] = clamp01(float(raw))

    baseline_composite = clamp01(float(baseline_entry.get("isi_composite", 0.0)))

    # --- Compute baseline rank ---
    baseline_rank = compute_rank(country_code, baseline_composite, all_baselines)
    baseline_classification = classify(baseline_composite)

    # --- Apply adjustments → simulated axes ---
    simulated_axes: dict[str, float] = {}
    axis_deltas: dict[str, float] = {}
    for slug in AXIS_SLUGS:
        adj = adjustments.get(slug, 0.0)
        simulated_axes[slug] = clamp01(baseline_axes[slug] + adj)
        axis_deltas[slug] = round(simulated_axes[slug] - baseline_axes[slug], 10)

    # --- Compute simulated composite ---
    simulated_composite = compute_composite(simulated_axes)
    simulated_rank = compute_rank(country_code, simulated_composite, all_baselines)
    simulated_classification = classify(simulated_composite)

    # --- Final invariant checks ---
    assert 0.0 <= simulated_composite <= 1.0, f"Composite {simulated_composite} out of [0,1]"
    assert 1 <= simulated_rank <= len(all_baselines), f"Rank {simulated_rank} out of range"
    for slug, score in simulated_axes.items():
        assert 0.0 <= score <= 1.0, f"Axis {slug} = {score} out of [0,1]"

    # --- Build response ---
    return {
        "ok": True,
        "baseline": {
            "country": country_code,
            "country_name": baseline_entry.get("country_name", country_code),
            "axis_scores": {slug: round(baseline_axes[slug], 10) for slug in AXIS_SLUGS},
            "composite": round(baseline_composite, 10),
            "rank": baseline_rank,
            "classification": baseline_classification,
        },
        "simulated": {
            "axis_scores": {slug: round(simulated_axes[slug], 10) for slug in AXIS_SLUGS},
            "composite": round(simulated_composite, 10),
            "rank": simulated_rank,
            "classification": simulated_classification,
        },
        "delta": {
            "composite": round(simulated_composite - baseline_composite, 10),
            "rank_change": simulated_rank - baseline_rank,
            "axis_deltas": {slug: round(axis_deltas[slug], 10) for slug in AXIS_SLUGS},
        },
    }
