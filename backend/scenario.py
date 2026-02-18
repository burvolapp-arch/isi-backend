"""
backend.scenario — ISI Scenario Simulation Engine (scenario-v1)

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

Input contract (Pydantic-validated at the API layer):
    {
        "country": "SE",
        "adjustments": {
            "energy_external_supplier_concentration": -0.15,
            "defense_external_supplier_concentration": 0.10
        }
    }

Output contract (ScenarioResponse — Pydantic-validated before return):
    {
        "country": "SE",
        "baseline": { "composite": float, "rank": int, "classification": str,
                       "axes": { canonical_key: float } },
        "simulated": { ... same shape ... },
        "delta":     { "composite": float, "rank": int,
                       "axes": { canonical_key: float } },
        "meta": { "version": "scenario-v1", "timestamp": ISO8601, "bounds": { "min": -0.2, "max": 0.2 } }
    }
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants — single source of truth
# ---------------------------------------------------------------------------

NUM_AXES = 6
MAX_ADJUSTMENT = 0.20
SCENARIO_VERSION = "scenario-v1"

# Classification thresholds — IDENTICAL to baseline endpoint logic
_CLASSIFICATION_THRESHOLDS: list[tuple[float, str]] = [
    (0.25, "highly_concentrated"),
    (0.15, "moderately_concentrated"),
    (0.10, "mildly_concentrated"),
]
_CLASSIFICATION_DEFAULT = "unconcentrated"
VALID_CLASSIFICATIONS: frozenset[str] = frozenset(
    [label for _, label in _CLASSIFICATION_THRESHOLDS] + [_CLASSIFICATION_DEFAULT]
)

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

# EU-27 country codes
EU27_CODES: frozenset[str] = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])


# ---------------------------------------------------------------------------
# Pydantic models — request
# ---------------------------------------------------------------------------

class ScenarioRequest(BaseModel):
    """Strict input model for POST /scenario.

    Validates country code and adjustment keys/values.
    Missing adjustments default to empty dict (= no changes).
    """

    country: str = Field(
        ...,
        min_length=2,
        max_length=2,
        description="2-letter ISO country code, uppercase, must be in EU-27",
    )
    adjustments: dict[str, float] = Field(
        default_factory=dict,
        description="Axis adjustments keyed by canonical axis key. "
                    "Values in [-0.20, +0.20]. Missing axes treated as 0.0.",
    )

    @field_validator("country")
    @classmethod
    def _validate_country(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError(f"'country' must be a 2-letter ISO code. Got: '{v}'.")
        if v not in EU27_CODES:
            raise ValueError(
                f"Country '{v}' is not in the EU-27 dataset. "
                f"Valid: {sorted(EU27_CODES)}"
            )
        return v

    @model_validator(mode="after")
    def _validate_adjustments(self) -> ScenarioRequest:
        cleaned: dict[str, float] = {}
        for key, val in self.adjustments.items():
            if key not in VALID_CANONICAL_KEYS:
                raise ValueError(
                    f"Unknown axis key: '{key}'. "
                    f"Valid keys: {sorted(VALID_CANONICAL_KEYS)}"
                )
            if math.isnan(val) or math.isinf(val):
                raise ValueError(
                    f"Adjustment for '{key}' must be a finite number. Got: {val!r}."
                )
            if not (-MAX_ADJUSTMENT <= val <= MAX_ADJUSTMENT):
                raise ValueError(
                    f"Adjustment for '{key}' must be in "
                    f"[{-MAX_ADJUSTMENT}, {MAX_ADJUSTMENT}]. Got: {val}."
                )
            cleaned[key] = val
        self.adjustments = cleaned
        return self


# ---------------------------------------------------------------------------
# Pydantic models — response
# ---------------------------------------------------------------------------

class AxisScores(BaseModel):
    """All 6 axis scores, always present, always finite floats in [0, 1]."""
    financial_external_supplier_concentration: float
    energy_external_supplier_concentration: float
    technology_semiconductor_external_supplier_concentration: float
    defense_external_supplier_concentration: float
    critical_inputs_raw_materials_external_supplier_concentration: float
    logistics_freight_external_supplier_concentration: float

    @model_validator(mode="after")
    def _no_nan_or_missing(self) -> AxisScores:
        for key in CANONICAL_AXIS_KEYS:
            v = getattr(self, key)
            if v is None or math.isnan(v) or math.isinf(v):
                raise ValueError(f"Axis '{key}' must be a finite float, got {v!r}")
        return self


class AxisDeltas(BaseModel):
    """Per-axis delta (simulated - baseline). Always all 6 keys."""
    financial_external_supplier_concentration: float
    energy_external_supplier_concentration: float
    technology_semiconductor_external_supplier_concentration: float
    defense_external_supplier_concentration: float
    critical_inputs_raw_materials_external_supplier_concentration: float
    logistics_freight_external_supplier_concentration: float


class BaselineBlock(BaseModel):
    composite: float = Field(..., ge=0.0, le=1.0)
    rank: int = Field(..., ge=1)
    classification: str
    axes: AxisScores


class SimulatedBlock(BaseModel):
    composite: float = Field(..., ge=0.0, le=1.0)
    rank: int = Field(..., ge=1)
    classification: str
    axes: AxisScores


class DeltaBlock(BaseModel):
    composite: float
    rank: int
    axes: AxisDeltas


class MetaBlock(BaseModel):
    version: str = SCENARIO_VERSION
    timestamp: str
    bounds: dict[str, float] = Field(
        default_factory=lambda: {"min": -MAX_ADJUSTMENT, "max": MAX_ADJUSTMENT}
    )


class ScenarioResponse(BaseModel):
    """Guaranteed response shape for POST /scenario.

    ABSOLUTE RULE: baseline.axes and simulated.axes MUST include
    ALL 6 keys always. Never omit. Never null. Never NaN.
    """
    country: str
    baseline: BaselineBlock
    simulated: SimulatedBlock
    delta: DeltaBlock
    meta: MetaBlock


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
) -> ScenarioResponse:
    """Run a scenario simulation for one country.

    Args:
        country_code: Uppercase 2-letter ISO code (already validated).
        adjustments: {canonical_key: float} — adjustment factors in [-0.20, +0.20].
                     Missing axes default to 0.0.
                     Computation: simulated = clamp(baseline * (1 + adj), 0, 1)
        all_baselines: The countries[] array from isi.json.

    Returns:
        ScenarioResponse — Pydantic-validated, guaranteed complete.

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
    baseline_isi_axes: dict[str, float] = {}
    simulated_isi_axes: dict[str, float] = {}
    baseline_canonical: dict[str, float] = {}
    simulated_canonical: dict[str, float] = {}
    delta_canonical: dict[str, float] = {}

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

        baseline_isi_axes[isi_key] = baseline_val
        simulated_isi_axes[isi_key] = simulated_val

        baseline_canonical[canonical_key] = round(baseline_val, 10)
        simulated_canonical[canonical_key] = round(simulated_val, 10)
        delta_canonical[canonical_key] = round(simulated_val - baseline_val, 10)

    # Compute composites
    baseline_composite = compute_composite(baseline_isi_axes)
    simulated_composite = compute_composite(simulated_isi_axes)

    # Compute ranks
    baseline_rank = compute_rank(country_code, baseline_composite, all_baselines)
    simulated_rank = compute_rank(country_code, simulated_composite, all_baselines)

    # Classify
    baseline_classification = classify(baseline_composite)
    simulated_classification = classify(simulated_composite)

    # Build and validate response through Pydantic
    return ScenarioResponse(
        country=country_code,
        baseline=BaselineBlock(
            composite=round(baseline_composite, 10),
            rank=baseline_rank,
            classification=baseline_classification,
            axes=AxisScores(**baseline_canonical),
        ),
        simulated=SimulatedBlock(
            composite=round(simulated_composite, 10),
            rank=simulated_rank,
            classification=simulated_classification,
            axes=AxisScores(**simulated_canonical),
        ),
        delta=DeltaBlock(
            composite=round(simulated_composite - baseline_composite, 10),
            rank=simulated_rank - baseline_rank,
            axes=AxisDeltas(**delta_canonical),
        ),
        meta=MetaBlock(
            timestamp=datetime.now(UTC).isoformat(),
        ),
    )
