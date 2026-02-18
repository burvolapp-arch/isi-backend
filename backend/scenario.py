"""
backend.scenario — ISI Scenario Simulation Engine (v0.5)

Thin, data-driven transformation layer on top of baseline ISI data.
Zero I/O. Zero global state. Zero randomness. Zero duplicate registries.

Design principle:
    The canonical axis keys for the request payload are the long-form
    snake_case names. The mapping to isi.json internal keys is defined
    once here. The computation model, classification, and composite
    formula are identical to the baseline endpoints.

Scenario computation model:
    For each axis:
        simulated_value = clamp(baseline_value * (1 + adjustment), 0.0, 1.0)

    Composite:
        simulated_composite = mean(simulated_axes)

    This is a multiplicative shift model, not additive.
    adjustment = +0.10 means "10% increase from baseline".
    adjustment = -0.10 means "10% decrease from baseline".
    adjustment range: [-0.20, +0.20]

Input contract:
    {
        "country": "SE",
        "adjustments": {
            "financial_external_supplier_concentration": 0.0,
            "energy_external_supplier_concentration": 0.0,
            "technology_semiconductor_external_supplier_concentration": 0.0,
            "defense_external_supplier_concentration": 0.0,
            "critical_inputs_raw_materials_external_supplier_concentration": 0.0,
            "logistics_freight_external_supplier_concentration": 0.0
        }
    }

    - country: 2-letter ISO, uppercased, must exist in baseline dataset
    - adjustments: keyed by canonical long-form axis key
    - unknown keys → 400 with explicit reason
    - values clamped to [-0.20, +0.20]
    - missing axes → adjustment = 0.0 (identity)

Output contract:
    {
        "country": "SE",
        "baseline_composite": float,
        "simulated_composite": float,
        "baseline_rank": int,
        "simulated_rank": int,
        "baseline_classification": str,
        "simulated_classification": str,
        "axis_results": {
            canonical_key: {
                "baseline": float,
                "simulated": float,
                "delta": float
            }
        }
    }
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_AXES = 6
MAX_ADJUSTMENT = 0.20

# Classification thresholds — IDENTICAL to baseline endpoint logic
_CLASSIFICATION_THRESHOLDS: list[tuple[float, str]] = [
    (0.25, "highly_concentrated"),
    (0.15, "moderately_concentrated"),
    (0.10, "mildly_concentrated"),
]
_CLASSIFICATION_DEFAULT = "unconcentrated"

# Canonical long-form axis keys — these are the keys the frontend sends.
CANONICAL_AXIS_KEYS: tuple[str, ...] = (
    "financial_external_supplier_concentration",
    "energy_external_supplier_concentration",
    "technology_semiconductor_external_supplier_concentration",
    "defense_external_supplier_concentration",
    "critical_inputs_raw_materials_external_supplier_concentration",
    "logistics_freight_external_supplier_concentration",
)

# Set of valid canonical keys (for input validation)
VALID_CANONICAL_KEYS: frozenset[str] = frozenset(CANONICAL_AXIS_KEYS)

# Canonical key → isi.json internal key
CANONICAL_TO_ISI_KEY: dict[str, str] = {
    "financial_external_supplier_concentration": "axis_1_financial",
    "energy_external_supplier_concentration": "axis_2_energy",
    "technology_semiconductor_external_supplier_concentration": "axis_3_technology",
    "defense_external_supplier_concentration": "axis_4_defense",
    "critical_inputs_raw_materials_external_supplier_concentration": "axis_5_critical_inputs",
    "logistics_freight_external_supplier_concentration": "axis_6_logistics",
}

# The 6 isi.json keys, in canonical order
ISI_AXIS_KEYS: tuple[str, ...] = (
    "axis_1_financial",
    "axis_2_energy",
    "axis_3_technology",
    "axis_4_defense",
    "axis_5_critical_inputs",
    "axis_6_logistics",
)

# Reverse: isi.json key → canonical key
ISI_KEY_TO_CANONICAL: dict[str, str] = {v: k for k, v in CANONICAL_TO_ISI_KEY.items()}


# ---------------------------------------------------------------------------
# Pure computation — same functions used by baseline endpoints
# ---------------------------------------------------------------------------

def classify(composite: float) -> str:
    """Classify a composite score. Same logic as baseline."""
    for threshold, label in _CLASSIFICATION_THRESHOLDS:
        if composite >= threshold:
            return label
    return _CLASSIFICATION_DEFAULT


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]. NaN/Inf → lo."""
    if math.isnan(value) or math.isinf(value):
        return lo
    return max(lo, min(hi, value))


def compute_composite(axis_values: dict[str, float]) -> float:
    """ISI composite = unweighted arithmetic mean of 6 axis scores.

    Same formula as baseline: ISI_i = (A1 + A2 + A3 + A4 + A5 + A6) / 6
    """
    total = sum(axis_values[k] for k in ISI_AXIS_KEYS)
    return clamp(total / NUM_AXES, 0.0, 1.0)


def compute_rank(
    country_code: str,
    simulated_composite: float,
    all_baselines: list[dict[str, Any]],
) -> int:
    """Rank among all countries (1 = highest dependency).

    Inserts simulated composite for target country into the sorted
    baseline composites. Ties broken by country code alphabetically.
    """
    composites: list[tuple[float, str]] = []
    for entry in all_baselines:
        code = entry["country"]
        if code == country_code:
            composites.append((simulated_composite, code))
        else:
            composites.append((entry["isi_composite"], code))

    composites.sort(key=lambda x: (-x[0], x[1]))

    for i, (_, code) in enumerate(composites, 1):
        if code == country_code:
            return i

    return len(all_baselines)


# ---------------------------------------------------------------------------
# Main simulation function
# ---------------------------------------------------------------------------

def simulate(
    country_code: str,
    adjustments: dict[str, float],
    all_baselines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run a scenario simulation for one country.

    Args:
        country_code: Uppercase 2-letter ISO code.
        adjustments: {canonical_key: float} — adjustment factors in [-0.20, +0.20].
                     Missing axes default to 0.0.
                     Computation: simulated = clamp(baseline * (1 + adj), 0, 1)
        all_baselines: The countries[] array from isi.json.

    Returns:
        Full response dict matching the output contract.

    Raises:
        ValueError: country_code not found in baseline data.
        RuntimeError: baseline data is corrupt.
    """
    # Find baseline entry
    baseline_entry: dict[str, Any] | None = None
    for entry in all_baselines:
        if entry["country"] == country_code:
            baseline_entry = entry
            break

    if baseline_entry is None:
        raise ValueError(f"Country '{country_code}' not found in ISI baseline data.")

    # Extract baseline axes and compute simulated axes
    baseline_axes: dict[str, float] = {}
    simulated_axes: dict[str, float] = {}
    axis_results: dict[str, dict[str, float]] = {}

    for canonical_key in CANONICAL_AXIS_KEYS:
        isi_key = CANONICAL_TO_ISI_KEY[canonical_key]

        raw = baseline_entry.get(isi_key)
        if raw is None or not isinstance(raw, (int, float)):
            raise RuntimeError(
                f"Baseline data corrupt: missing or non-numeric '{isi_key}' for {country_code}."
            )

        baseline_val = clamp(float(raw), 0.0, 1.0)
        adj = adjustments.get(canonical_key, 0.0)
        simulated_val = clamp(baseline_val * (1.0 + adj), 0.0, 1.0)

        baseline_axes[isi_key] = baseline_val
        simulated_axes[isi_key] = simulated_val

        axis_results[canonical_key] = {
            "baseline": round(baseline_val, 10),
            "simulated": round(simulated_val, 10),
            "delta": round(simulated_val - baseline_val, 10),
        }

    # Compute composites
    baseline_composite = compute_composite(baseline_axes)
    simulated_composite = compute_composite(simulated_axes)

    # Compute ranks
    baseline_rank = compute_rank(country_code, baseline_composite, all_baselines)
    simulated_rank = compute_rank(country_code, simulated_composite, all_baselines)

    # Classify
    baseline_classification = classify(baseline_composite)
    simulated_classification = classify(simulated_composite)

    return {
        "country": country_code,
        "baseline_composite": round(baseline_composite, 10),
        "simulated_composite": round(simulated_composite, 10),
        "baseline_rank": baseline_rank,
        "simulated_rank": simulated_rank,
        "baseline_classification": baseline_classification,
        "simulated_classification": simulated_classification,
        "axis_results": axis_results,
    }
