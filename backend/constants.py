"""
backend.constants — Single source of truth for ISI global constants.

Every module that needs these values MUST import from here.
No hardcoded duplicates anywhere in the codebase.

Design lifetime: 20 years. Do not add transient configuration here.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Precision
# ---------------------------------------------------------------------------

ROUND_PRECISION: int = 8
"""All axis scores, composite scores, statistics, shares, and any
floating-point value that enters storage, classification, sorting,
or hashing MUST be rounded to exactly ROUND_PRECISION decimal places
BEFORE any downstream use.

Rounding rule: Python's round() (banker's rounding / round-half-to-even).
Rounding happens ONCE at the earliest point where the value is finalized.
No double-rounding. Values are rounded BEFORE classification, BEFORE
sorting, BEFORE hashing, BEFORE JSON serialization.
"""

# ---------------------------------------------------------------------------
# Structural constants
# ---------------------------------------------------------------------------

NUM_AXES: int = 6
"""Number of ISI axes. Changing this requires a new methodology version."""

MAX_ADJUSTMENT: float = 0.20
"""Scenario simulation adjustment bound: [-MAX_ADJUSTMENT, +MAX_ADJUSTMENT]."""

SCENARIO_VERSION: str = "scenario-v1"
"""Wire-format version tag for scenario responses."""

# ---------------------------------------------------------------------------
# EU-27 country codes — frozen set, canonical order
# ---------------------------------------------------------------------------

EU27_CODES: frozenset[str] = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

EU27_SORTED: list[str] = sorted(EU27_CODES)
"""EU-27 codes in deterministic alphabetical order."""

# ---------------------------------------------------------------------------
# Axis key mappings — canonical ↔ isi.json internal keys
# ---------------------------------------------------------------------------

CANONICAL_AXIS_KEYS: tuple[str, ...] = (
    "financial_external_supplier_concentration",
    "energy_external_supplier_concentration",
    "technology_semiconductor_external_supplier_concentration",
    "defense_external_supplier_concentration",
    "critical_inputs_raw_materials_external_supplier_concentration",
    "logistics_freight_external_supplier_concentration",
)
"""Long-form snake_case axis keys — the wire format for scenario requests."""

VALID_CANONICAL_KEYS: frozenset[str] = frozenset(CANONICAL_AXIS_KEYS)

CANONICAL_TO_ISI_KEY: dict[str, str] = {
    "financial_external_supplier_concentration": "axis_1_financial",
    "energy_external_supplier_concentration": "axis_2_energy",
    "technology_semiconductor_external_supplier_concentration": "axis_3_technology",
    "defense_external_supplier_concentration": "axis_4_defense",
    "critical_inputs_raw_materials_external_supplier_concentration": "axis_5_critical_inputs",
    "logistics_freight_external_supplier_concentration": "axis_6_logistics",
}

ISI_AXIS_KEYS: tuple[str, ...] = (
    "axis_1_financial",
    "axis_2_energy",
    "axis_3_technology",
    "axis_4_defense",
    "axis_5_critical_inputs",
    "axis_6_logistics",
)
"""The 6 isi.json keys, in canonical order."""

ISI_KEY_TO_CANONICAL: dict[str, str] = {v: k for k, v in CANONICAL_TO_ISI_KEY.items()}

# ---------------------------------------------------------------------------
# Country names — static, avoids external dependency
# ---------------------------------------------------------------------------

COUNTRY_NAMES: dict[str, str] = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DK": "Denmark", "EE": "Estonia", "EL": "Greece",
    "ES": "Spain", "FI": "Finland", "FR": "France",
    "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
    "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania",
    "SE": "Sweden", "SI": "Slovenia", "SK": "Slovakia",
}
