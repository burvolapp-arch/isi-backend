"""
backend.scope — Configurable country scope for ISI computation.

This module replaces all hardcoded EU-27 references in global-capable
pipeline paths. v1.0 EU-27 logic remains untouched in its frozen scripts.

Design contract:
    - get_scope() returns the canonical scope for a methodology version.
    - SCOPE_REGISTRY is the single source of truth for scope definitions.
    - All scope sets are frozensets of ISO-2 country codes.
    - No scope may be modified after module load.
    - validate_scope() hard-fails on any scope violation.

Constraint spec reference: Section 6.1 (Scope Abstraction).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Scope definitions — frozen, deterministic, no runtime mutation
# ---------------------------------------------------------------------------

EU27_CODES: frozenset[str] = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

PHASE1_EXPANSION_CODES: frozenset[str] = frozenset([
    "AU", "CN", "GB", "JP", "KR", "NO", "US",
])

# ---------------------------------------------------------------------------
# Country names — expansion countries only (EU-27 names in constants.py)
# ---------------------------------------------------------------------------

EXPANSION_COUNTRY_NAMES: dict[str, str] = {
    "AU": "Australia",
    "CN": "China",
    "GB": "United Kingdom",
    "JP": "Japan",
    "KR": "South Korea",
    "NO": "Norway",
    "US": "United States",
}

# ---------------------------------------------------------------------------
# Scope registry — maps scope identifier to country code set
# ---------------------------------------------------------------------------

SCOPE_REGISTRY: dict[str, frozenset[str]] = {
    "EU-27": EU27_CODES,
    "PHASE1-7": PHASE1_EXPANSION_CODES,
    "GLOBAL-34": EU27_CODES | PHASE1_EXPANSION_CODES,
}

# ---------------------------------------------------------------------------
# BIS country code mapping — expansion countries
#
# BIS uses standard ISO-2 for all expansion countries.
# No GR/EL-style conflicts exist in the expansion set.
# ---------------------------------------------------------------------------

BIS_TO_CANONICAL_EXPANSION: dict[str, str] = {
    "AU": "AU",
    "CN": "CN",
    "GB": "GB",
    "JP": "JP",
    "KR": "KR",
    "NO": "NO",
    "US": "US",
}

# ---------------------------------------------------------------------------
# CPIS (ISO-3) mapping — expansion countries
# ---------------------------------------------------------------------------

CPIS_TO_CANONICAL_EXPANSION: dict[str, str] = {
    "AUS": "AU",
    "CHN": "CN",
    "GBR": "GB",
    "JPN": "JP",
    "KOR": "KR",
    "NOR": "NO",
    "USA": "US",
}

# CPIS non-participants (constraint spec LIM-005)
CPIS_NON_PARTICIPANTS: frozenset[str] = frozenset(["CN"])

# ---------------------------------------------------------------------------
# SIPRI recipient mapping — expansion countries
#
# Extends SIPRI_TO_EUROSTAT from parse_defense_sipri_raw.py.
# Supplier map already contains all 7 countries.
# ---------------------------------------------------------------------------

SIPRI_TO_CANONICAL_EXPANSION: dict[str, str] = {
    "Australia": "AU",
    "China": "CN",
    "United Kingdom": "GB",
    "Japan": "JP",
    "South Korea": "KR",
    "Korea South": "KR",
    "Republic of Korea": "KR",
    "Norway": "NO",
    "United States": "US",
}

# ---------------------------------------------------------------------------
# Top-5 global exporters by axis (for DEGRADED/W-PRODUCER-INVERSION flagging)
#
# Source: latest available rankings (SIPRI, IEA, USGS, UN Comtrade).
# Used ONLY for axis validity labeling, never for score modification.
# ---------------------------------------------------------------------------

PRODUCER_INVERSION_FLAGS: dict[int, frozenset[str]] = {
    # Axis 2 — Energy: top exporters
    2: frozenset(["US", "RU", "SA", "AU", "NO"]),
    # Axis 4 — Defence: top arms exporters
    4: frozenset(["US", "RU", "FR", "CN", "DE"]),
    # Axis 5 — Critical Inputs: top mineral/material exporters
    5: frozenset(["CN", "AU", "ZA", "BR", "RU"]),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_scope(scope_id: str) -> frozenset[str]:
    """Return the frozen country code set for a scope identifier.

    Raises KeyError if scope_id is not registered.
    """
    if scope_id not in SCOPE_REGISTRY:
        raise KeyError(
            f"Unknown scope '{scope_id}'. "
            f"Registered scopes: {sorted(SCOPE_REGISTRY.keys())}"
        )
    return SCOPE_REGISTRY[scope_id]


def get_scope_sorted(scope_id: str) -> list[str]:
    """Return alphabetically sorted country list for a scope."""
    return sorted(get_scope(scope_id))


def get_country_name(code: str) -> str:
    """Return country name for any ISI country code.

    Checks expansion names first, then falls back to EU-27 names
    from backend.constants.
    """
    if code in EXPANSION_COUNTRY_NAMES:
        return EXPANSION_COUNTRY_NAMES[code]
    # Defer import to avoid circular dependency
    from backend.constants import COUNTRY_NAMES
    return COUNTRY_NAMES.get(code, code)


def validate_scope_coverage(
    countries: set[str] | frozenset[str],
    scope_id: str,
    context: str,
) -> None:
    """Validate that a set of countries matches expected scope exactly.

    Hard-fails (raises ValueError) on mismatch.

    Args:
        countries: Actual country codes found in data.
        scope_id: Expected scope identifier.
        context: Human-readable context for error messages.
    """
    expected = get_scope(scope_id)
    missing = expected - countries
    extra = countries - expected
    if missing or extra:
        parts = [f"Scope validation failed for '{context}' (scope={scope_id})."]
        if missing:
            parts.append(f"Missing: {sorted(missing)}")
        if extra:
            parts.append(f"Unexpected: {sorted(extra)}")
        raise ValueError(" ".join(parts))


def validate_scope_minimum(
    countries: set[str] | frozenset[str],
    scope_id: str,
    context: str,
) -> set[str]:
    """Validate that countries are a subset of expected scope.

    Returns the set of missing countries (may be empty).
    Raises ValueError if any country is NOT in the scope.

    Used for axes where not all countries may have data,
    but no country outside scope should appear.
    """
    expected = get_scope(scope_id)
    extra = countries - expected
    if extra:
        raise ValueError(
            f"Scope violation in '{context}' (scope={scope_id}): "
            f"unexpected countries {sorted(extra)}"
        )
    return expected - countries


def is_producer_inverted(country: str, axis_num: int) -> bool:
    """Check if a country is a known major exporter on a given axis.

    Returns True if the country should receive W-PRODUCER-INVERSION warning.
    This does NOT modify scores — it only flags for validity labeling.
    """
    return country in PRODUCER_INVERSION_FLAGS.get(axis_num, frozenset())


def scope_id_for_methodology(methodology_version: str) -> str:
    """Map methodology version to scope identifier.

    v1.0 → EU-27
    v1.1 → PHASE1-7
    """
    mapping = {
        "v1.0": "EU-27",
        "v1.1": "PHASE1-7",
    }
    if methodology_version not in mapping:
        raise KeyError(
            f"No scope defined for methodology '{methodology_version}'. "
            f"Known: {sorted(mapping.keys())}"
        )
    return mapping[methodology_version]
