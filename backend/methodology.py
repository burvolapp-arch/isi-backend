"""
backend.methodology — Single source of truth for ISI methodology parameters.

THIS IS THE ONLY PLACE where classification thresholds, composite formulas,
and methodology parameters exist. Both the exporter and the scenario engine
MUST import from this module. No hardcoded thresholds elsewhere.

Resolves D-6 (dual-source-of-truth for thresholds) permanently.

Design contract:
    - classify() is the ONLY classification function in the codebase.
    - compute_composite() is the ONLY composite computation function.
    - get_methodology() loads frozen, versioned methodology definitions.
    - get_latest_methodology_version() / get_latest_year() resolve "latest".
    - No implicit state. No mutability. No runtime modification of registry.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from backend.constants import ROUND_PRECISION

# ---------------------------------------------------------------------------
# Registry path — relative to this module
# ---------------------------------------------------------------------------

REGISTRY_PATH: Path = Path(__file__).resolve().parent / "snapshots" / "registry.json"

# ---------------------------------------------------------------------------
# Registry cache — loaded once, never mutated
# ---------------------------------------------------------------------------

_registry_cache: dict[str, Any] | None = None
_latest_version_cache: str | None = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_methodology_entry(version: str, entry: dict) -> None:
    """Validate a single methodology entry from the registry.

    Raises ValueError on any structural or logical error.
    """
    required_keys = {
        "methodology_version", "label", "frozen_at", "latest_year",
        "years_available", "aggregation_rule", "aggregation_formula",
        "axis_count", "axis_slugs", "axis_weights",
        "classification_thresholds", "default_classification",
        "score_range", "round_precision",
    }
    missing = required_keys - set(entry.keys())
    if missing:
        raise ValueError(
            f"Methodology '{version}': missing required keys: {sorted(missing)}"
        )

    # axis_count matches axis_slugs
    if entry["axis_count"] != len(entry["axis_slugs"]):
        raise ValueError(
            f"Methodology '{version}': axis_count ({entry['axis_count']}) "
            f"!= len(axis_slugs) ({len(entry['axis_slugs'])})"
        )

    # axis_weights covers all axes
    if set(entry["axis_weights"].keys()) != set(entry["axis_slugs"]):
        raise ValueError(
            f"Methodology '{version}': axis_weights keys do not match axis_slugs"
        )

    # Thresholds are in descending order
    thresholds = [t[0] for t in entry["classification_thresholds"]]
    if thresholds != sorted(thresholds, reverse=True):
        raise ValueError(
            f"Methodology '{version}': classification_thresholds not in descending order"
        )

    # Each threshold entry is [float, str]
    for item in entry["classification_thresholds"]:
        if not (isinstance(item, list) and len(item) == 2):
            raise ValueError(
                f"Methodology '{version}': invalid threshold entry: {item}"
            )

    # score_range
    if entry["score_range"] != [0.0, 1.0]:
        raise ValueError(
            f"Methodology '{version}': unexpected score_range: {entry['score_range']}"
        )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _load_registry() -> dict[str, Any]:
    """Load and validate the methodology registry. Cached after first call.

    Returns dict mapping methodology_version -> entry, plus
    "__latest__" -> version string and "__latest_year__" -> int.
    """
    global _registry_cache, _latest_version_cache

    if _registry_cache is not None:
        return _registry_cache

    if not REGISTRY_PATH.is_file():
        raise FileNotFoundError(
            f"Methodology registry not found: {REGISTRY_PATH}. "
            f"This file is required for all ISI operations."
        )

    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        raw = json.load(fh)

    if "schema_version" not in raw:
        raise ValueError("Registry missing 'schema_version'")

    if "latest" not in raw:
        raise ValueError("Registry missing 'latest' pointer")

    if "methodologies" not in raw or not raw["methodologies"]:
        raise ValueError("Registry missing or empty 'methodologies' array")

    registry: dict[str, Any] = {}
    seen_versions: set[str] = set()

    for entry in raw["methodologies"]:
        version = entry.get("methodology_version")
        if not version:
            raise ValueError("Methodology entry missing 'methodology_version'")

        if version in seen_versions:
            raise ValueError(f"Duplicate methodology version: '{version}'")
        seen_versions.add(version)

        _validate_methodology_entry(version, entry)
        registry[version] = entry

    # Validate latest pointer
    latest = raw["latest"]
    if latest not in registry:
        raise ValueError(
            f"Registry 'latest' points to '{latest}' which is not in the registry."
        )

    registry["__latest__"] = latest
    registry["__latest_year__"] = registry[latest]["latest_year"]

    _registry_cache = registry
    _latest_version_cache = latest
    return registry


def reload_registry() -> None:
    """Force reload of the registry. Used in testing only."""
    global _registry_cache, _latest_version_cache
    _registry_cache = None
    _latest_version_cache = None
    _load_registry()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_methodology(version: str) -> dict[str, Any]:
    """Get a specific methodology version.

    Raises KeyError if version is not found.
    """
    reg = _load_registry()
    if version not in reg or version.startswith("__"):
        raise KeyError(f"Unknown methodology version: '{version}'")
    return reg[version]


def get_latest_methodology_version() -> str:
    """Get the version string of the latest methodology."""
    reg = _load_registry()
    return reg["__latest__"]


def get_latest_year() -> int:
    """Get the latest year from the registry."""
    reg = _load_registry()
    return reg["__latest_year__"]


def get_years_available(methodology_version: str | None = None) -> list[int]:
    """Get available years for a methodology version.

    Defaults to latest methodology if version is None.
    """
    if methodology_version is None:
        methodology_version = get_latest_methodology_version()
    m = get_methodology(methodology_version)
    return sorted(m["years_available"])


# ---------------------------------------------------------------------------
# Classification — THE ONLY classify() in the codebase
# ---------------------------------------------------------------------------

def classify(score: float, methodology_version: str | None = None) -> str:
    """Classify a score using thresholds from the specified methodology.

    THIS IS THE ONLY CLASSIFICATION FUNCTION. Both the exporter and the
    scenario engine MUST call this. No hardcoded thresholds elsewhere.

    Args:
        score: A rounded float in [0.0, 1.0].
        methodology_version: Registry version to use. Defaults to latest.

    Returns:
        Classification label string.
    """
    if methodology_version is None:
        methodology_version = get_latest_methodology_version()
    m = get_methodology(methodology_version)
    for threshold, label in m["classification_thresholds"]:
        if score >= threshold:
            return label
    return m["default_classification"]


# ---------------------------------------------------------------------------
# Composite computation — THE ONLY compute_composite() in the codebase
# ---------------------------------------------------------------------------

def compute_composite(
    axis_scores: dict[str, float],
    methodology_version: str | None = None,
) -> float:
    """Compute composite using the methodology's aggregation rule.

    THIS IS THE ONLY COMPOSITE FUNCTION. Both the exporter and the
    scenario engine MUST call this. No hardcoded formula elsewhere.

    Args:
        axis_scores: Dict mapping ISI axis keys to rounded scores.
                     Example: {"axis_1_financial": 0.15, ...}
        methodology_version: Registry version to use. Defaults to latest.

    Returns:
        Composite score (NOT rounded — caller must round via ROUND_PRECISION).
    """
    if methodology_version is None:
        methodology_version = get_latest_methodology_version()
    m = get_methodology(methodology_version)
    rule = m["aggregation_rule"]

    if rule == "unweighted_arithmetic_mean":
        if not axis_scores:
            raise ValueError("axis_scores is empty")
        return sum(axis_scores.values()) / len(axis_scores)
    elif rule == "weighted_arithmetic_mean":
        weights = m["axis_weights"]
        # Map ISI keys to slugs for weight lookup
        total_weight = 0.0
        weighted_sum = 0.0
        for key, score in axis_scores.items():
            # Extract slug from key (e.g., "axis_1_financial" → "financial")
            parts = key.split("_", 2)
            slug = parts[2] if len(parts) > 2 else key
            w = weights.get(slug, 1.0)
            weighted_sum += score * w
            total_weight += w
        if total_weight == 0.0:
            raise ValueError("Total weight is zero")
        return weighted_sum / total_weight
    else:
        raise ValueError(f"Unknown aggregation rule: '{rule}'")


# ---------------------------------------------------------------------------
# Convenience: classification thresholds for backward compatibility
# ---------------------------------------------------------------------------

def get_classification_thresholds(
    methodology_version: str | None = None,
) -> list[tuple[float, str]]:
    """Get classification thresholds as list of (threshold, label) tuples.

    Useful for tests that need to inspect the threshold values.
    """
    if methodology_version is None:
        methodology_version = get_latest_methodology_version()
    m = get_methodology(methodology_version)
    return [(t[0], t[1]) for t in m["classification_thresholds"]]


def get_default_classification(
    methodology_version: str | None = None,
) -> str:
    """Get the default classification label (below all thresholds)."""
    if methodology_version is None:
        methodology_version = get_latest_methodology_version()
    m = get_methodology(methodology_version)
    return m["default_classification"]
