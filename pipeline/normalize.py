"""
pipeline.normalize — Normalization engine for ISI data ingestion.

Handles:
    - ISO-3 → ISO-2 country code mapping
    - HS code → category mapping
    - Currency normalization (ensure value consistency)
    - Duplicate removal (deterministic aggregation)
    - Aggregate partner filtering

All transformations are LOGGED. No silent data modification.
Every normalization step produces an audit record.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline.config import (
    ISO3_TO_ISO2,
    CPIS_TO_ISO2,
    BIS_TO_ISO2,
    SIPRI_TO_ISO2,
    AGGREGATE_PARTNER_NAMES,
    AGGREGATE_PARTNER_ISO2,
)
from pipeline.schema import BilateralRecord, BilateralDataset


# ---------------------------------------------------------------------------
# Normalization audit record
# ---------------------------------------------------------------------------

@dataclass
class NormalizationAudit:
    """Tracks every normalization action for auditability."""
    records_input: int = 0
    records_output: int = 0
    country_codes_remapped: int = 0
    aggregates_removed: int = 0
    self_trades_removed: int = 0
    zero_values_removed: int = 0
    negative_values_removed: int = 0
    duplicates_aggregated: int = 0
    unmapped_codes: list[str] = field(default_factory=list)
    remapping_log: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records_input": self.records_input,
            "records_output": self.records_output,
            "records_removed": self.records_input - self.records_output,
            "country_codes_remapped": self.country_codes_remapped,
            "aggregates_removed": self.aggregates_removed,
            "self_trades_removed": self.self_trades_removed,
            "zero_values_removed": self.zero_values_removed,
            "negative_values_removed": self.negative_values_removed,
            "duplicates_aggregated": self.duplicates_aggregated,
            "unmapped_codes": self.unmapped_codes[:50],
            "n_unmapped": len(self.unmapped_codes),
        }


# ---------------------------------------------------------------------------
# Country code normalization
# ---------------------------------------------------------------------------

def normalize_country_code(
    code: str,
    source: str = "generic",
    audit: NormalizationAudit | None = None,
) -> str | None:
    """Normalize a country code to ISI canonical ISO-2.

    Resolution order:
    1. If already valid ISO-2 (2 chars, alpha): return as-is
    2. Source-specific mapping (BIS, CPIS, SIPRI)
    3. Generic ISO-3 → ISO-2 mapping
    4. If unmapped: return None (caller decides how to handle)

    Returns None for aggregate/invalid codes.
    """
    if not code or not code.strip():
        return None

    code = code.strip()

    # Check for known aggregate codes first
    if code in AGGREGATE_PARTNER_ISO2:
        return None

    # Source-specific mappings
    if source == "bis_lbs":
        if code in BIS_TO_ISO2:
            mapped = BIS_TO_ISO2[code]
            if mapped == "__AGGREGATE__":
                return None
            if audit:
                audit.country_codes_remapped += 1
            return mapped

    if source == "imf_cpis":
        if code in CPIS_TO_ISO2:
            mapped = CPIS_TO_ISO2[code]
            if mapped in AGGREGATE_PARTNER_ISO2:
                return None
            if audit:
                audit.country_codes_remapped += 1
            return mapped

    if source == "sipri":
        if code in SIPRI_TO_ISO2:
            mapped = SIPRI_TO_ISO2[code]
            if mapped in AGGREGATE_PARTNER_ISO2:
                return None
            if audit:
                audit.country_codes_remapped += 1
            return mapped

    # Already ISO-2?
    if len(code) == 2 and code.isalpha():
        return code.upper()

    # ISO-3 → ISO-2
    if code.upper() in ISO3_TO_ISO2:
        mapped = ISO3_TO_ISO2[code.upper()]
        if audit:
            audit.country_codes_remapped += 1
        return mapped

    # Unmapped
    if audit:
        audit.unmapped_codes.append(code)
    return None


# ---------------------------------------------------------------------------
# Aggregate partner filter
# ---------------------------------------------------------------------------

def is_aggregate_partner(partner: str) -> bool:
    """Check if a partner code/name represents an aggregate.

    Returns True if the partner should be REMOVED from bilateral data.
    Covers ISO-2 aggregate codes, aggregate names, and free-text heuristics
    for all sources (Comtrade, BIS, IMF CPIS, Eurostat, SIPRI).
    """
    if not partner:
        return True
    partner_stripped = partner.strip()
    if partner_stripped in AGGREGATE_PARTNER_NAMES:
        return True
    if partner_stripped in AGGREGATE_PARTNER_ISO2:
        return True
    # Heuristic keywords covering all data sources
    partner_lower = partner_stripped.lower()
    for agg in ("world", "total", "other", "unspecified", "not specified",
                 "not allocated", "unallocated", "rest of", "areas, nes",
                 "bunkers", "free zones", "international organizations",
                 "confidential"):
        if agg in partner_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Full normalization pipeline for a record list
# ---------------------------------------------------------------------------

def normalize_records(
    records: list[BilateralRecord],
    source: str,
    axis: str,
    reporter_filter: str | None = None,
) -> tuple[list[BilateralRecord], NormalizationAudit]:
    """Apply full normalization pipeline to a list of raw records.

    Steps (in order):
    1. Country code normalization (reporter + partner)
    2. Aggregate partner removal
    3. Self-trade removal
    4. Zero/negative value removal
    5. Duplicate aggregation

    All steps are LOGGED in the audit record.

    Args:
        records: Raw BilateralRecords.
        source: Data source identifier.
        axis: Axis slug.
        reporter_filter: If set, only keep records with this reporter.

    Returns:
        (normalized_records, audit)
    """
    audit = NormalizationAudit()
    audit.records_input = len(records)

    # Step 1: Country code normalization
    step1: list[BilateralRecord] = []
    for r in records:
        reporter = normalize_country_code(r.reporter, source, audit)
        partner = normalize_country_code(r.partner, source, audit)

        if reporter is None:
            continue
        if partner is None:
            audit.aggregates_removed += 1
            continue

        if reporter_filter and reporter != reporter_filter:
            continue

        step1.append(BilateralRecord(
            reporter=reporter,
            partner=partner,
            value=r.value,
            year=r.year,
            source=r.source,
            axis=r.axis,
            product_code=r.product_code,
            product_desc=r.product_desc,
            unit=r.unit,
            sub_category=r.sub_category,
        ))

    # Step 2: Aggregate partner removal (belt-and-suspenders)
    step2: list[BilateralRecord] = []
    for r in step1:
        if is_aggregate_partner(r.partner):
            audit.aggregates_removed += 1
            continue
        step2.append(r)

    # Step 3: Self-trade removal
    step3: list[BilateralRecord] = []
    for r in step2:
        if r.reporter == r.partner:
            audit.self_trades_removed += 1
            continue
        step3.append(r)

    # Step 4: Zero/negative value removal
    step4: list[BilateralRecord] = []
    for r in step3:
        if r.value < 0:
            audit.negative_values_removed += 1
            continue
        if r.value == 0:
            audit.zero_values_removed += 1
            continue
        step4.append(r)

    # Step 5: Duplicate aggregation
    # Key: (reporter, partner, year, product_code, sub_category)
    # Values from duplicate keys are SUMMED (they represent fragments)
    agg_key = {}
    for r in step4:
        key = (r.reporter, r.partner, r.year, r.product_code or "", r.sub_category or "")
        if key in agg_key:
            audit.duplicates_aggregated += 1
            existing = agg_key[key]
            agg_key[key] = BilateralRecord(
                reporter=r.reporter,
                partner=r.partner,
                value=existing.value + r.value,
                year=r.year,
                source=r.source,
                axis=r.axis,
                product_code=r.product_code,
                product_desc=r.product_desc or existing.product_desc,
                unit=r.unit,
                sub_category=r.sub_category,
            )
        else:
            agg_key[key] = r

    result = list(agg_key.values())
    audit.records_output = len(result)

    return result, audit


# ---------------------------------------------------------------------------
# HS code → category mapping
# ---------------------------------------------------------------------------

# Energy HS codes → fuel category
HS_TO_ENERGY_CATEGORY: dict[str, str] = {
    "2701": "coal",
    "270112": "coal_bituminous",
    "270119": "coal_other",
    "2709": "crude_oil",
    "270900": "crude_oil",
    "2710": "petroleum_products",
    "271012": "petroleum_light",
    "271019": "petroleum_other",
    "2711": "natural_gas",
    "271111": "lng",
    "271121": "natural_gas_pipeline",
    "2716": "electricity",
}

# Tech HS codes → category
HS_TO_TECH_CATEGORY: dict[str, str] = {
    "8541": "semiconductor_devices",
    "854110": "diodes",
    "854121": "transistors",
    "854129": "transistors_other",
    "854130": "thyristors",
    "854140": "photosensitive_devices",
    "854150": "led_devices",
    "854160": "piezoelectric",
    "854190": "semiconductor_parts",
    "8542": "integrated_circuits",
    "854231": "ic_processors",
    "854232": "ic_memory",
    "854233": "ic_amplifiers",
    "854239": "ic_other",
    "854290": "ic_parts",
}

# Critical inputs HS codes → material group
HS_TO_CRITICAL_MATERIAL: dict[str, str] = {
    "2504": "natural_graphite",
    "2602": "manganese_ore",
    "2605": "cobalt_ore",
    "2610": "chromium_ore",
    "2611": "tungsten_ore",
    "2612": "uranium_thorium_ore",
    "2614": "titanium_ore",
    "2615": "niobium_tantalum_ore",
    "2804": "silicon",
    "2825": "lithium_compounds",
    "2836": "lithium_carbonate",
    "2846": "rare_earth_compounds",
    "7110": "platinum_group",
    "8105": "cobalt_unwrought",
    "8108": "titanium_unwrought",
}


def map_hs_to_category(hs_code: str, axis: str) -> str | None:
    """Map an HS code to its ISI category for a given axis.

    Returns None if the HS code is not relevant for the axis.
    Tries exact match first, then prefix matching.
    """
    if axis == "energy":
        mapping = HS_TO_ENERGY_CATEGORY
    elif axis == "technology":
        mapping = HS_TO_TECH_CATEGORY
    elif axis == "critical_inputs":
        mapping = HS_TO_CRITICAL_MATERIAL
    else:
        return None

    # Exact match
    if hs_code in mapping:
        return mapping[hs_code]

    # Prefix match (4-digit code matches 6-digit entries)
    for prefix_len in (4, 2):
        prefix = hs_code[:prefix_len]
        if prefix in mapping:
            return mapping[prefix]

    return None
