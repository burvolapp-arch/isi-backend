"""
backend.scenario — ISI Scenario Simulation Engine (v0.3)

Pure-computation module. Zero I/O. Zero global state. Zero randomness.
All functions are deterministic, bounded, and idempotent.

Given a country's baseline axis scores and a set of axis shifts,
computes the simulated axis scores, composite, rank, and classification.

The ISI composite is:
    ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6

Classification thresholds (frozen):
    >= 0.25  → highly_concentrated
    >= 0.15  → moderately_concentrated
    >= 0.10  → mildly_concentrated
    <  0.10  → unconcentrated

Request schema (v0.3):
    {
      "country_code": str,        # 2-letter uppercase ISO
      "axis_shifts": {             # 0–6 keys, all optional
          "<slug>": float          # each in [-0.20, +0.20]
      }
    }

    Accepted field aliases (frontend compat):
      country_code  OR  countryCode
      axis_shifts   OR  adjustments

Response contract (v0.3):
    {
      "simulated_composite": float,
      "simulated_rank": int,
      "simulated_classification": str,
      "axis_results": {
          "financial": float,
          "energy": float,
          "technology": float,
          "defense": float,
          "critical_inputs": float,
          "logistics": float
      },
      "request_id": str
    }
"""

from __future__ import annotations

import math
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants — frozen
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

# Valid classification labels (for output sanitization)
VALID_CLASSIFICATIONS: frozenset[str] = frozenset({
    "highly_concentrated",
    "moderately_concentrated",
    "mildly_concentrated",
    "unconcentrated",
})


# ---------------------------------------------------------------------------
# Pydantic request model — strict, schema-explicit validation
# ---------------------------------------------------------------------------

class ScenarioRequest(BaseModel):
    """Validated scenario simulation request.

    Accepts (with aliases for frontend compatibility):
      - country_code OR countryCode   → 2-letter uppercase ISO
      - axis_shifts  OR adjustments   → dict of axis_slug → float delta
      - empty axis_shifts {}          → treated as zero-delta (returns baseline)
      - extra fields are silently ignored (frontend may send metadata)

    Rejects (with structured 422):
      - missing country_code
      - country_code not exactly 2 uppercase alpha chars
      - unknown axis slugs in axis_shifts
      - shift values outside [-0.20, +0.20]
      - NaN / Inf / None / non-numeric shift values
      - string-typed shift values (no implicit coercion)
    """

    model_config = {"extra": "ignore", "populate_by_name": True}

    country_code: str = Field(
        ...,
        alias="countryCode",
        min_length=2,
        max_length=2,
        description="2-letter uppercase ISO country code (EU-27)",
    )
    axis_shifts: Dict[str, float] = Field(
        default_factory=dict,
        alias="adjustments",
        description="Per-axis shift deltas. Keys must be canonical axis slugs. Values in [-0.20, +0.20].",
    )

    @field_validator("country_code")
    @classmethod
    def _validate_country_code(cls, v: str) -> str:
        if v is None:
            raise ValueError("country_code must not be null.")
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError(f"Invalid country code: '{v}'. Must be exactly 2 uppercase ISO alpha characters.")
        return v

    @field_validator("axis_shifts")
    @classmethod
    def _validate_axis_shifts(cls, v: Dict[str, float]) -> Dict[str, float]:
        if v is None:
            return {}
        for slug, shift in v.items():
            if slug not in AXIS_SLUG_SET:
                raise ValueError(
                    f"Unknown axis slug: '{slug}'. "
                    f"Valid slugs: {sorted(AXIS_SLUG_SET)}"
                )
            if shift is None:
                raise ValueError(f"Shift for '{slug}' must not be null.")
            if not isinstance(shift, (int, float)):
                raise ValueError(
                    f"Shift for '{slug}' must be numeric float, got {type(shift).__name__}. "
                    f"No implicit coercion from string."
                )
            if math.isnan(shift) or math.isinf(shift):
                raise ValueError(
                    f"Shift for '{slug}' must be finite "
                    f"(got {'NaN' if math.isnan(shift) else 'Inf'})."
                )
            if shift < -MAX_ADJUSTMENT or shift > MAX_ADJUSTMENT:
                raise ValueError(
                    f"Shift for '{slug}' = {shift} is out of range "
                    f"[{-MAX_ADJUSTMENT}, +{MAX_ADJUSTMENT}]."
                )
        return v

    @model_validator(mode="after")
    def _post_coercion_check(self) -> ScenarioRequest:
        """Belt-and-suspenders: re-check after Pydantic coercion."""
        for slug, shift in self.axis_shifts.items():
            if math.isnan(shift) or math.isinf(shift):
                raise ValueError(f"Shift for '{slug}' is not finite after coercion.")
        return self


# ---------------------------------------------------------------------------
# Pure computation functions
# ---------------------------------------------------------------------------

def classify(composite: float) -> str:
    """Map a composite score to its classification string.

    Deterministic. Safe for any float in [0, 1].
    Always returns a member of VALID_CLASSIFICATIONS.
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
    """Compute rank (1 = highest dependency) among all countries.

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
    axis_shifts: dict[str, float],
    all_baselines: list[dict[str, Any]],
    request_id: str,
) -> dict[str, Any]:
    """Run a scenario simulation for one country.

    Args:
        country_code: ISO-2 country code (uppercase, validated).
        axis_shifts: {axis_slug: delta} — each in [-0.20, +0.20]. May be empty.
        all_baselines: The full countries array from isi.json.
        request_id: UUID from middleware (passed through to response).

    Returns:
        Deterministic response dict matching the v0.3 contract:
        {simulated_composite, simulated_rank, simulated_classification,
         axis_results, request_id}

    Raises:
        ValueError: If country_code not found in baselines.
        RuntimeError: If baseline data is corrupt or output sanitization fails.
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

    # --- Apply axis_shifts → simulated axes ---
    simulated_axes: dict[str, float] = {}
    for slug in AXIS_SLUGS:
        shift = axis_shifts.get(slug, 0.0)
        simulated_axes[slug] = clamp01(baseline_axes[slug] + shift)

    # --- Compute simulated composite ---
    simulated_composite = compute_composite(simulated_axes)
    simulated_rank = compute_rank(country_code, simulated_composite, all_baselines)
    simulated_classification = classify(simulated_composite)

    # --- Bound output sanitization ---
    for slug in AXIS_SLUGS:
        simulated_axes[slug] = clamp01(simulated_axes[slug])
    simulated_composite = clamp01(simulated_composite)
    simulated_rank = int(simulated_rank)

    if simulated_classification not in VALID_CLASSIFICATIONS:
        raise RuntimeError(
            f"Output sanitization failed: classification '{simulated_classification}' "
            f"is not in {sorted(VALID_CLASSIFICATIONS)}."
        )
    if math.isnan(simulated_composite) or math.isinf(simulated_composite):
        raise RuntimeError("Output sanitization failed: simulated_composite is NaN or Inf.")
    for slug, val in simulated_axes.items():
        if math.isnan(val) or math.isinf(val):
            raise RuntimeError(f"Output sanitization failed: axis '{slug}' is NaN or Inf.")

    # --- Deterministic response contract (v0.3) ---
    return {
        "simulated_composite": round(simulated_composite, 10),
        "simulated_rank": simulated_rank,
        "simulated_classification": simulated_classification,
        "axis_results": {
            slug: round(simulated_axes[slug], 10) for slug in AXIS_SLUGS
        },
        "request_id": request_id,
    }
