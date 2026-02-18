"""
backend.scenario — ISI Scenario Simulation Engine (v0.4)

Pure-computation module. Zero I/O. Zero global state. Zero randomness.
All functions are deterministic, bounded, and idempotent.

Given a country's baseline axis scores and a set of adjustments,
computes the simulated axis scores, composite, rank, and classification.

The ISI composite is:
    ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6

Classification thresholds (frozen):
    >= 0.25  → highly_concentrated
    >= 0.15  → moderately_concentrated
    >= 0.10  → mildly_concentrated
    <  0.10  → unconcentrated

Request schema (v0.4):
    {
      "country_code": str,        # 2-letter uppercase ISO (EU-27)
      "adjustments": {             # 0–6 keys, missing → 0.0, out-of-range → clamped
          "<canonical_axis_key>": float
      },
      "meta": {                    # optional, ignored by compute
          "preset": str | null,
          "client_version": str | null,
          "timestamp": str | null
      }
    }

    Canonical axis keys:
      financial_external_supplier_concentration
      energy_external_supplier_concentration
      technology_semiconductor_external_supplier_concentration
      defense_external_supplier_concentration
      critical_inputs_raw_materials_external_supplier_concentration
      logistics_freight_external_supplier_concentration

Response contract (v0.4):
    {
      "baseline_composite": float,
      "simulated_composite": float,
      "baseline_rank": int,
      "simulated_rank": int,
      "baseline_classification": str,
      "simulated_classification": str,
      "axis_results": {
          "<canonical_axis_key>": {
              "baseline": float,
              "simulated": float,
              "delta": float
          }
      }
    }

    No extra nesting. No renaming. No optional nulls. Always deterministic.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants — frozen
# ---------------------------------------------------------------------------

NUM_AXES = 6

# Canonical axis keys — the long-form names the frontend sends.
CANONICAL_AXIS_KEYS: tuple[str, ...] = (
    "financial_external_supplier_concentration",
    "energy_external_supplier_concentration",
    "technology_semiconductor_external_supplier_concentration",
    "defense_external_supplier_concentration",
    "critical_inputs_raw_materials_external_supplier_concentration",
    "logistics_freight_external_supplier_concentration",
)

CANONICAL_AXIS_KEY_SET: frozenset[str] = frozenset(CANONICAL_AXIS_KEYS)

# Maps canonical axis key → key in isi.json countries[] objects
CANONICAL_TO_ISI_KEY: dict[str, str] = {
    "financial_external_supplier_concentration": "axis_1_financial",
    "energy_external_supplier_concentration": "axis_2_energy",
    "technology_semiconductor_external_supplier_concentration": "axis_3_technology",
    "defense_external_supplier_concentration": "axis_4_defense",
    "critical_inputs_raw_materials_external_supplier_concentration": "axis_5_critical_inputs",
    "logistics_freight_external_supplier_concentration": "axis_6_logistics",
}

# Also accept short slug names from older frontends → map to canonical
SHORT_SLUG_TO_CANONICAL: dict[str, str] = {
    "financial": "financial_external_supplier_concentration",
    "energy": "energy_external_supplier_concentration",
    "technology": "technology_semiconductor_external_supplier_concentration",
    "defense": "defense_external_supplier_concentration",
    "critical_inputs": "critical_inputs_raw_materials_external_supplier_concentration",
    "logistics": "logistics_freight_external_supplier_concentration",
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

# Legacy exports for backwards compat in tests
AXIS_SLUGS = CANONICAL_AXIS_KEYS


# ---------------------------------------------------------------------------
# Pydantic request model — tolerant, never-400 validation
# ---------------------------------------------------------------------------

class ScenarioMeta(BaseModel):
    """Optional metadata from the frontend. Ignored by compute."""
    preset: Optional[str] = None
    client_version: Optional[str] = None
    timestamp: Optional[str] = None


class ScenarioRequest(BaseModel):
    """Tolerant scenario simulation request.

    Design principle: NEVER return 400 for structural reasons.
    - Missing adjustments keys → filled with 0.0
    - Out-of-range values → clamped to [-0.20, +0.20]
    - Unknown keys → silently ignored
    - Extra top-level fields → silently ignored
    - Short slugs (financial, energy, ...) → auto-mapped to canonical keys
    - NaN/Inf values → replaced with 0.0
    - meta field → optional, passed through

    Only reject:
    - Missing country_code entirely (422 — malformed JSON)
    """

    model_config = {"extra": "ignore", "populate_by_name": True}

    country_code: str = Field(
        ...,
        alias="countryCode",
        description="2-letter uppercase ISO country code (EU-27)",
    )
    adjustments: Dict[str, float] = Field(
        default_factory=dict,
        alias="axis_shifts",
        description="Per-axis adjustment deltas. Keys are canonical axis keys. Values clamped to [-0.20, +0.20].",
    )
    meta: Optional[ScenarioMeta] = None

    @field_validator("country_code")
    @classmethod
    def _normalize_country_code(cls, v: str) -> str:
        if v is None:
            raise ValueError("country_code must not be null.")
        v = str(v).strip().upper()
        if len(v) < 2:
            raise ValueError(f"country_code too short: '{v}'.")
        # Take first 2 alpha chars, be tolerant
        v = v[:2]
        if not v.isalpha():
            raise ValueError(f"country_code must be alphabetic: '{v}'.")
        return v

    @model_validator(mode="after")
    def _normalize_adjustments(self) -> ScenarioRequest:
        """Tolerant normalization:
        - Map short slugs → canonical keys
        - Ignore unknown keys
        - Clamp values to [-0.20, +0.20]
        - Replace NaN/Inf with 0.0
        - Fill missing canonical keys with 0.0
        """
        raw = self.adjustments or {}
        normalized: Dict[str, float] = {}

        for key, val in raw.items():
            # Map short slug to canonical if needed
            canonical = SHORT_SLUG_TO_CANONICAL.get(key, key)

            # Skip unknown keys silently
            if canonical not in CANONICAL_AXIS_KEY_SET:
                continue

            # Coerce to float safely
            try:
                fval = float(val)
            except (TypeError, ValueError):
                fval = 0.0

            # Replace NaN/Inf with 0.0
            if math.isnan(fval) or math.isinf(fval):
                fval = 0.0

            # Clamp to [-MAX_ADJUSTMENT, +MAX_ADJUSTMENT]
            fval = max(-MAX_ADJUSTMENT, min(MAX_ADJUSTMENT, fval))

            normalized[canonical] = fval

        # Fill missing canonical keys with 0.0
        for key in CANONICAL_AXIS_KEYS:
            if key not in normalized:
                normalized[key] = 0.0

        self.adjustments = normalized
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
    total = sum(axis_scores[key] for key in CANONICAL_AXIS_KEYS)
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


def compute_baseline_rank(
    country_code: str,
    all_baselines: list[dict[str, Any]],
) -> int:
    """Compute baseline rank for a country from isi.json data."""
    composites: list[tuple[float, str]] = []
    for entry in all_baselines:
        composites.append((entry["isi_composite"], entry["country"]))

    composites.sort(key=lambda x: (-x[0], x[1]))

    for i, (_, code) in enumerate(composites, 1):
        if code == country_code:
            return i

    return len(all_baselines)


def simulate(
    country_code: str,
    adjustments: dict[str, float],
    all_baselines: list[dict[str, Any]],
    request_id: str,
) -> dict[str, Any]:
    """Run a scenario simulation for one country.

    Args:
        country_code: ISO-2 country code (uppercase, validated).
        adjustments: {canonical_axis_key: delta} — all 6 keys present, clamped.
        all_baselines: The full countries array from isi.json.
        request_id: UUID from middleware (passed through for tracing).

    Returns:
        Deterministic response dict matching the v0.4 contract:
        {baseline_composite, simulated_composite, baseline_rank, simulated_rank,
         baseline_classification, simulated_classification,
         axis_results: {key: {baseline, simulated, delta}}}

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
    for canonical_key in CANONICAL_AXIS_KEYS:
        isi_key = CANONICAL_TO_ISI_KEY[canonical_key]
        raw = baseline_entry.get(isi_key)
        if raw is None or not isinstance(raw, (int, float)):
            raise RuntimeError(
                f"Baseline data corrupt: missing or non-numeric '{isi_key}' for {country_code}."
            )
        baseline_axes[canonical_key] = clamp01(float(raw))

    # --- Compute baseline composite and rank ---
    baseline_composite = compute_composite(baseline_axes)
    baseline_rank = compute_baseline_rank(country_code, all_baselines)
    baseline_classification = classify(baseline_composite)

    # --- Apply adjustments → simulated axes ---
    simulated_axes: dict[str, float] = {}
    for canonical_key in CANONICAL_AXIS_KEYS:
        delta = adjustments.get(canonical_key, 0.0)
        simulated_axes[canonical_key] = clamp01(baseline_axes[canonical_key] + delta)

    # --- Compute simulated composite ---
    simulated_composite = compute_composite(simulated_axes)
    simulated_rank = compute_rank(country_code, simulated_composite, all_baselines)
    simulated_classification = classify(simulated_composite)

    # --- Output sanitization ---
    baseline_composite = clamp01(baseline_composite)
    simulated_composite = clamp01(simulated_composite)
    baseline_rank = int(baseline_rank)
    simulated_rank = int(simulated_rank)

    for label, comp in [("baseline", baseline_composite), ("simulated", simulated_composite)]:
        if math.isnan(comp) or math.isinf(comp):
            raise RuntimeError(f"Output sanitization failed: {label}_composite is NaN or Inf.")

    for cls_label, cls_val in [
        ("baseline", baseline_classification),
        ("simulated", simulated_classification),
    ]:
        if cls_val not in VALID_CLASSIFICATIONS:
            raise RuntimeError(
                f"Output sanitization failed: {cls_label}_classification '{cls_val}' "
                f"is not in {sorted(VALID_CLASSIFICATIONS)}."
            )

    for canonical_key in CANONICAL_AXIS_KEYS:
        for label, axes_dict in [("baseline", baseline_axes), ("simulated", simulated_axes)]:
            val = axes_dict[canonical_key]
            if math.isnan(val) or math.isinf(val):
                raise RuntimeError(
                    f"Output sanitization failed: {label} axis '{canonical_key}' is NaN or Inf."
                )

    # --- Build axis_results with baseline/simulated/delta per axis ---
    axis_results: dict[str, dict[str, float]] = {}
    for canonical_key in CANONICAL_AXIS_KEYS:
        b = round(baseline_axes[canonical_key], 10)
        s = round(simulated_axes[canonical_key], 10)
        d = round(s - b, 10)
        axis_results[canonical_key] = {
            "baseline": b,
            "simulated": s,
            "delta": d,
        }

    # --- Deterministic response contract (v0.4) ---
    return {
        "baseline_composite": round(baseline_composite, 10),
        "simulated_composite": round(simulated_composite, 10),
        "baseline_rank": baseline_rank,
        "simulated_rank": simulated_rank,
        "baseline_classification": baseline_classification,
        "simulated_classification": simulated_classification,
        "axis_results": axis_results,
    }
