"""
Constants for the ISI Results Evidence Pack generator.

All axis ordering, column names, and formatting rules are defined here.
No magic strings elsewhere.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Axis ordering — canonical, matches backend/constants.py
# ---------------------------------------------------------------------------

AXIS_COUNT: int = 6

AXIS_IDS: tuple[int, ...] = (1, 2, 3, 4, 5, 6)

AXIS_SLUGS: tuple[str, ...] = (
    "financial",
    "energy",
    "technology",
    "defense",
    "critical_inputs",
    "logistics",
)

AXIS_ISI_KEYS: tuple[str, ...] = (
    "axis_1_financial",
    "axis_2_energy",
    "axis_3_technology",
    "axis_4_defense",
    "axis_5_critical_inputs",
    "axis_6_logistics",
)

AXIS_SHORT_LABELS: dict[int, str] = {
    1: "A1 Fin.",
    2: "A2 Energy",
    3: "A3 Tech.",
    4: "A4 Def.",
    5: "A5 Crit.Inp.",
    6: "A6 Logist.",
}

AXIS_FULL_NAMES: dict[int, str] = {
    1: "Financial Sovereignty",
    2: "Energy Dependency",
    3: "Technology / Semiconductor Dependency",
    4: "Defense Industrial Dependency",
    5: "Critical Inputs / Raw Materials Dependency",
    6: "Logistics / Freight Dependency",
}

# ---------------------------------------------------------------------------
# EU-27 — canonical set
# ---------------------------------------------------------------------------

EU27_CODES: frozenset[str] = frozenset([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

EU27_COUNT: int = 27

# ---------------------------------------------------------------------------
# CSV column ordering — isi_countries.csv
# ---------------------------------------------------------------------------

ISI_COUNTRIES_COLUMNS: tuple[str, ...] = (
    "country",
    "country_name",
    "rank",
    "isi_composite",
    "classification",
    "axis_1_financial",
    "axis_2_energy",
    "axis_3_technology",
    "axis_4_defense",
    "axis_5_critical_inputs",
    "axis_6_logistics",
    "complete",
    "window",
    "methodology_version",
    "year",
)

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

SCORE_DECIMALS_PAPER: int = 4
"""Scores/deltas in paper tables: 4 decimal places."""

PERCENTAGE_DECIMALS_PAPER: int = 1
"""Percentages in paper tables: 1 decimal place."""

FULL_PRECISION_DECIMALS: int = 8
"""Full precision for machine-readable exports (matches backend ROUND_PRECISION)."""

# ---------------------------------------------------------------------------
# Axis driver detection
# ---------------------------------------------------------------------------

SPIKE_THRESHOLD_K: float = 1.0
"""
A country's concentration profile is 'single-spike' if:
    max_axis_score >= mean(axis_scores) + k * std(axis_scores)
where k = SPIKE_THRESHOLD_K.
Otherwise 'broad-based'.
"""

# ---------------------------------------------------------------------------
# Methodology — fixed for this pack
# ---------------------------------------------------------------------------

METHODOLOGY_VERSION: str = "v1.0"
YEAR: int = 2024

# ---------------------------------------------------------------------------
# Valid axis slugs — hard guard against scope drift
# ---------------------------------------------------------------------------

VALID_AXIS_SLUGS: frozenset[str] = frozenset(AXIS_SLUGS)
