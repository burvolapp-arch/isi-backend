#!/usr/bin/env python3
"""
export_isi_backend_v01.py — ISI Backend Materializer

Reads ALL frozen axis CSV outputs and materializes a complete set
of structured JSON artifacts for the read-only ISI backend.

This script performs ZERO computation. It reads scores that were
already computed and validated by the upstream axis pipelines. It
reformats, attaches metadata, and writes JSON.

Every value in the output JSON is traceable to a specific CSV file
and row. The exporter hard-fails on any inconsistency.

Output directory: backend/v01/

Artifacts produced:
    backend/v01/meta.json                   — ISI version metadata
    backend/v01/axes.json                   — axis registry
    backend/v01/countries.json              — country list with all scores
    backend/v01/isi.json                    — composite ISI scores
    backend/v01/country/{code}.json         — per-country full detail
    backend/v01/axis/{axis_id}.json         — per-axis full detail

No pandas. Stdlib + json only.
"""

import csv
import json
import math
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

EU27_SET = frozenset(EU27)

VERSION = "v0.1"
WINDOW = "2022\u20132024"
NUM_AXES = 6

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data" / "processed"
OUTPUT_ROOT = PROJECT_ROOT / "backend" / "v01"

# Country names — static, avoids external dependency
COUNTRY_NAMES = {
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


# ---------------------------------------------------------------------------
# Axis registry — the canonical definition of what each axis IS
# ---------------------------------------------------------------------------

AXIS_REGISTRY = {
    1: {
        "id": 1,
        "slug": "financial",
        "name": "Financial Sovereignty",
        "description": "Concentration of inward banking claims and portfolio debt holdings across foreign creditor countries.",
        "unit": "USD millions",
        "country_key": "geo",
        "score_column": "finance_dependency",
        "data_dir": "finance",
        "final_file": "finance_dependency_2024_eu27.csv",
        "audit_file": "finance_dependency_2024_eu27_audit.csv",
        "channels": [
            {
                "id": "A",
                "name": "Banking Claims Concentration",
                "source": "BIS Locational Banking Statistics (LBS)",
                "concentration_file": "bis_lbs_inward_2024_concentration.csv",
                "shares_file": "bis_lbs_inward_2024_shares.csv",
                "volumes_file": "bis_lbs_inward_2024_volumes.csv",
                "country_key": "counterparty_country",
                "partner_key": "reporting_country",
            },
            {
                "id": "B",
                "name": "Portfolio Debt Concentration",
                "source": "IMF CPIS",
                "concentration_file": "cpis_debt_inward_2024_concentration.csv",
                "shares_file": "cpis_debt_inward_2024_shares.csv",
                "volumes_file": "cpis_debt_inward_2024_volumes.csv",
                "country_key": "reference_country",
                "partner_key": "counterparty_country",
            },
        ],
        "audit_columns": {
            "channel_a_concentration": "channel_a_concentration",
            "channel_a_volume": "channel_a_volume_usd_mn",
            "channel_b_concentration": "channel_b_concentration",
            "channel_b_volume": "channel_b_volume_usd_mn",
            "score": "finance_dependency",
            "basis": "source",
        },
        "warnings": [
            {
                "id": "L-1",
                "severity": "MEDIUM",
                "text": "BIS creditor coverage gap: non-BIS-reporting countries absent as creditors; concentration may be biased upward.",
            },
            {
                "id": "L-2",
                "severity": "MEDIUM",
                "text": "IMF CPIS participation is voluntary; China does not participate. Portfolio debt concentration may understate true exposure.",
            },
            {
                "id": "L-3",
                "severity": "LOW",
                "text": "Partial overlap between Channel A (bank claims) and Channel B (portfolio debt securities held by banks).",
            },
            {
                "id": "L-4",
                "severity": "LOW",
                "text": "Croatia (HR) absent from Channel B (IMF CPIS). Score reduces to Channel A only.",
            },
        ],
    },
    2: {
        "id": 2,
        "slug": "energy",
        "name": "Energy Dependency",
        "description": "Concentration of fossil fuel imports (gas, oil, solid fossil fuels) across supplier countries, volume-weighted across fuel types.",
        "unit": "varies by fuel (MIO_M3, THS_T)",
        "country_key": "geo",
        "score_column": "energy_dependency",
        "data_dir": "energy",
        "final_file": "energy_dependency_2024_eu27.csv",
        "audit_file": None,
        "channels": [
            {
                "id": "gas",
                "name": "Natural Gas Import Concentration",
                "source": "Eurostat nrg_ti_gas",
                "fuel_concentration_file": "nrg_ti_gas_2024_fuel_concentration.csv",
                "concentration_file": "nrg_ti_gas_2024_concentration.csv",
                "shares_file": "nrg_ti_gas_2024_shares.csv",
                "country_key": "geo",
                "partner_key": "partner",
            },
            {
                "id": "oil",
                "name": "Oil Import Concentration",
                "source": "Eurostat nrg_ti_oil",
                "fuel_concentration_file": "nrg_ti_oil_2024_fuel_concentration.csv",
                "concentration_file": "nrg_ti_oil_2024_concentration.csv",
                "shares_file": "nrg_ti_oil_2024_shares.csv",
                "country_key": "geo",
                "partner_key": "partner",
            },
            {
                "id": "solid_fossil",
                "name": "Solid Fossil Fuel Import Concentration",
                "source": "Eurostat nrg_ti_sff",
                "fuel_concentration_file": "nrg_ti_sff_2024_fuel_concentration.csv",
                "concentration_file": "nrg_ti_sff_2024_concentration.csv",
                "shares_file": "nrg_ti_sff_2024_shares.csv",
                "country_key": "geo",
                "partner_key": "partner",
            },
        ],
        "audit_columns": None,
        "warnings": [
            {
                "id": "L-1",
                "severity": "MEDIUM",
                "text": "Pipeline gas and LNG not separated. A country importing 50% pipeline gas from Russia and 50% LNG from multiple sources scores as if partially diversified.",
            },
            {
                "id": "L-2",
                "severity": "MEDIUM",
                "text": "Re-exports and transit flows may distort bilateral attribution across all fuel types.",
            },
            {
                "id": "L-3",
                "severity": "LOW",
                "text": "No price or contract-duration effects captured. Volume-based concentration only.",
            },
        ],
    },
    3: {
        "id": 3,
        "slug": "technology",
        "name": "Technology / Semiconductor Dependency",
        "description": "Concentration of semiconductor imports across supplier countries, with category-level decomposition.",
        "unit": "EUR",
        "country_key": "geo",
        "score_column": "tech_dependency",
        "data_dir": "tech",
        "final_file": "tech_dependency_2024_eu27.csv",
        "audit_file": "tech_dependency_2024_eu27_audit.csv",
        "channels": [
            {
                "id": "A",
                "name": "Aggregate Supplier Concentration",
                "source": "Eurostat Comext ds-045409",
                "concentration_file": "tech_channel_a_concentration.csv",
                "shares_file": "tech_channel_a_shares.csv",
                "volumes_file": "tech_channel_a_volumes.csv",
                "country_key": "reporter",
                "partner_key": "partner",
            },
            {
                "id": "B",
                "name": "Category-Weighted Supplier Concentration",
                "source": "Eurostat Comext ds-045409",
                "concentration_file": "tech_channel_b_concentration.csv",
                "shares_file": None,
                "volumes_file": "tech_channel_b_volumes.csv",
                "country_key": "reporter",
                "partner_key": None,
                "subcategory_concentration_file": "tech_channel_b_category_concentration.csv",
                "subcategory_shares_file": "tech_channel_b_category_shares.csv",
            },
        ],
        "audit_columns": {
            "channel_a_concentration": "channel_a_concentration",
            "channel_a_volume": "channel_a_volume",
            "channel_b_concentration": "channel_b_concentration",
            "channel_b_volume": "channel_b_volume",
            "score": "tech_dependency",
            "basis": "score_basis",
        },
        "warnings": [
            {
                "id": "W-2",
                "severity": "MEDIUM",
                "text": "Re-export blindness: bilateral trade records shipping country, not country of origin.",
            },
            {
                "id": "W-3",
                "severity": "LOW",
                "text": "Trade concentration does not capture domestic fabrication capacity.",
            },
            {
                "id": "W-4",
                "severity": "LOW",
                "text": "HS 8542 at HS4 aggregate: integrated circuits not decomposed into subcategories.",
            },
            {
                "id": "W-5",
                "severity": "LOW",
                "text": "Intra-EU trade included: EU partners appear as suppliers (by design).",
            },
            {
                "id": "W-6",
                "severity": "LOW",
                "text": "Three-year window (2022\u20132024) may include pandemic-era distortions.",
            },
        ],
    },
    4: {
        "id": 4,
        "slug": "defense",
        "name": "Defense Industrial Dependency",
        "description": "Concentration of major conventional arms imports across supplier countries and capability blocks.",
        "unit": "SIPRI TIV",
        "country_key": "geo",
        "score_column": "defense_dependency",
        "data_dir": "defense",
        "final_file": "defense_dependency_2024_eu27.csv",
        "audit_file": "defense_dependency_2024_eu27_audit.csv",
        "channels": [
            {
                "id": "A",
                "name": "Aggregate Supplier Concentration",
                "source": "SIPRI Arms Transfers Database",
                "concentration_file": "sipri_channel_a_concentration.csv",
                "shares_file": "sipri_channel_a_shares.csv",
                "volumes_file": "sipri_channel_a_volumes.csv",
                "country_key": "recipient_country",
                "partner_key": "supplier_country",
            },
            {
                "id": "B",
                "name": "Capability-Block Weighted Concentration",
                "source": "SIPRI Arms Transfers Database",
                "concentration_file": "sipri_channel_b_concentration.csv",
                "shares_file": None,
                "volumes_file": "sipri_channel_b_volumes.csv",
                "country_key": "recipient_country",
                "partner_key": None,
                "subcategory_concentration_file": "sipri_channel_b_block_concentration.csv",
                "subcategory_shares_file": "sipri_channel_b_block_shares.csv",
            },
        ],
        "audit_columns": {
            "channel_a_concentration": "channel_a_concentration",
            "channel_a_volume": "channel_a_volume",
            "channel_b_concentration": "channel_b_concentration",
            "channel_b_volume": "channel_b_volume",
            "score": "defense_dependency",
            "basis": "score_basis",
        },
        "warnings": [
            {
                "id": "L-1",
                "severity": "MEDIUM",
                "text": "SIPRI TIV is a volume indicator, not a financial value. Comparability across weapon types is approximate.",
            },
            {
                "id": "L-2",
                "severity": "MEDIUM",
                "text": "SIPRI covers major conventional weapons only. Small arms, ammunition, MRO, and sustainment contracts are excluded.",
            },
            {
                "id": "L-3",
                "severity": "LOW",
                "text": "Six-year delivery window (2019\u20132024) may include legacy contracts not reflecting current strategic posture.",
            },
            {
                "id": "L-4",
                "severity": "LOW",
                "text": "Regex-based weapon classification may cause edge-case misclassification across capability blocks.",
            },
        ],
    },
    5: {
        "id": 5,
        "slug": "critical_inputs",
        "name": "Critical Inputs / Raw Materials Dependency",
        "description": "Concentration of critical raw material imports across supplier countries, with material-group decomposition.",
        "unit": "EUR",
        "country_key": "geo",
        "score_column": "critical_inputs_dependency",
        "data_dir": "critical_inputs",
        "final_file": "critical_inputs_dependency_2024_eu27.csv",
        "audit_file": "critical_inputs_dependency_2024_eu27_audit.csv",
        "channels": [
            {
                "id": "A",
                "name": "Aggregate Supplier Concentration",
                "source": "Eurostat Comext ds-045409 (CN8)",
                "concentration_file": "critical_inputs_channel_a_concentration.csv",
                "shares_file": "critical_inputs_channel_a_shares.csv",
                "volumes_file": "critical_inputs_channel_a_volumes.csv",
                "country_key": "geo",
                "partner_key": "partner",
            },
            {
                "id": "B",
                "name": "Material-Group Weighted Supplier Concentration",
                "source": "Eurostat Comext ds-045409 (CN8)",
                "concentration_file": "critical_inputs_channel_b_concentration.csv",
                "shares_file": None,
                "volumes_file": "critical_inputs_channel_b_volumes.csv",
                "country_key": "geo",
                "partner_key": None,
                "subcategory_concentration_file": "critical_inputs_channel_b_group_concentration.csv",
                "subcategory_shares_file": "critical_inputs_channel_b_group_shares.csv",
            },
        ],
        "audit_columns": {
            "channel_a_concentration": "channel_a_concentration",
            "channel_a_volume": "channel_a_volume",
            "channel_b_concentration": "channel_b_concentration",
            "channel_b_volume": "channel_b_volume",
            "score": "critical_inputs_dependency",
            "basis": "score_basis",
        },
        "warnings": [
            {
                "id": "L-1",
                "severity": "HIGH",
                "text": "Re-export and entrepot masking: bilateral trade records shipping country, not origin. 13 of 27 reporters source >50% from EU partners.",
            },
            {
                "id": "L-2",
                "severity": "MEDIUM",
                "text": "Small-economy amplification: CY, MT, LU produce mechanically high HHI values due to low total import volumes.",
            },
            {
                "id": "L-3",
                "severity": "MEDIUM",
                "text": "CN8 scope covers upstream materials only. Midstream processing and downstream products excluded. China's role understated.",
            },
            {
                "id": "L-4",
                "severity": "LOW",
                "text": "Confidential trade suppression: Q-prefix partner codes excluded. May cause underestimation for some partners.",
            },
        ],
        "not_yet_materialized": True,
    },
    6: {
        "id": 6,
        "slug": "logistics",
        "name": "Logistics / Freight Dependency",
        "description": "Concentration of international freight across transport modes and bilateral freight partners per mode.",
        "unit": "THS_T (thousand tonnes)",
        "country_key": "reporter",
        "score_column": "axis6_logistics_score",
        "data_dir": "logistics",
        "final_file": "logistics_freight_axis_score.csv",
        "audit_file": "logistics_freight_axis_score.csv",
        "channels": [
            {
                "id": "A",
                "name": "Transport Mode Concentration",
                "source": "Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw",
                "concentration_file": "logistics_channel_a_mode_concentration.csv",
                "shares_file": None,
                "volumes_file": None,
                "country_key": "reporter",
                "partner_key": None,
            },
            {
                "id": "B",
                "name": "Partner Concentration per Transport Mode",
                "source": "Eurostat tran_hv_frmod / tran_r_frgo / mar_sg_am_cw",
                "concentration_file": "logistics_channel_b_concentration.csv",
                "shares_file": "logistics_channel_b_mode_shares.csv",
                "volumes_file": "logistics_channel_b_volumes.csv",
                "country_key": "reporter",
                "partner_key": "partner",
                "subcategory_concentration_file": "logistics_channel_b_mode_concentration.csv",
                "subcategory_shares_file": "logistics_channel_b_mode_shares.csv",
            },
        ],
        "audit_columns": {
            "channel_a_concentration": "channel_a_mode_hhi",
            "channel_a_volume": "weight_a_tonnes",
            "channel_b_concentration": "channel_b_partner_hhi",
            "channel_b_volume": "weight_b_tonnes",
            "score": "axis6_logistics_score",
            "basis": "aggregation_case",
        },
        "warnings": [
            {
                "id": "W-1",
                "severity": "HIGH",
                "text": "Entrepot/hub masking: NL and BE scores understate their systemic importance as continental freight hubs; countries trading through NL/BE have inflated partner concentration masking true origin.",
            },
            {
                "id": "W-2",
                "severity": "MEDIUM",
                "text": "Geographic determinism: MT (Channel A HHI = 1.0), CY, and landlocked countries have structurally constrained scores reflecting geography, not policy choices.",
            },
            {
                "id": "W-3",
                "severity": "MEDIUM",
                "text": "Maritime-energy overlap: maritime tonnage includes energy commodity transport, creating partial redundancy with Axis 3 (Energy).",
            },
            {
                "id": "W-4",
                "severity": "MEDIUM",
                "text": "Tonnage blindness: all freight is treated equally per tonne regardless of commodity type; strategic commodity differentiation is absent.",
            },
            {
                "id": "W-5",
                "severity": "LOW",
                "text": "No route/chokepoint data: the axis cannot detect Suez, Bosporus, or any physical corridor dependency.",
            },
        ],
        "not_yet_materialized": True,
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fatal(msg: str) -> None:
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def read_csv(filepath: Path) -> list[dict[str, str]]:
    """Read a CSV file. Returns list of dicts. Hard-fails if file missing."""
    if not filepath.is_file():
        fatal(f"File not found: {filepath}")
    with open(filepath, "r", newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def parse_float(val: str, context: str) -> float:
    """Parse a string to float. Hard-fail on bad values."""
    try:
        f = float(val)
    except (ValueError, TypeError):
        fatal(f"Non-numeric value '{val}' in {context}")
    if math.isnan(f) or math.isinf(f):
        fatal(f"NaN/Inf value in {context}")
    return f


def write_json(filepath: Path, data: object) -> None:
    """Write JSON with deterministic formatting."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")


def classify_score(score: float) -> str:
    """
    Generate a machine-readable concentration classification.
    Thresholds from standard HHI interpretation used across all audits.
    """
    if score >= 0.50:
        return "highly_concentrated"
    if score >= 0.25:
        return "moderately_concentrated"
    if score >= 0.15:
        return "mildly_concentrated"
    return "unconcentrated"


def driver_statement(axis_slug: str, score: float, country: str) -> str:
    """
    Generate a deterministic, factual driver statement.
    No opinion. No recommendation. Just what the number means.
    """
    level = classify_score(score)
    level_text = level.replace("_", " ")

    templates = {
        "financial": f"{country} scores {score:.4f} on financial sovereignty ({level_text}). This reflects the concentration of inward banking claims and portfolio debt holdings across foreign creditor countries.",
        "energy": f"{country} scores {score:.4f} on energy dependency ({level_text}). This reflects the concentration of fossil fuel imports (gas, oil, solid fossil fuels) across supplier countries.",
        "technology": f"{country} scores {score:.4f} on technology/semiconductor dependency ({level_text}). This reflects the concentration of semiconductor imports across supplier countries.",
        "defense": f"{country} scores {score:.4f} on defense industrial dependency ({level_text}). This reflects the concentration of major conventional arms imports across supplier countries.",
        "critical_inputs": f"{country} scores {score:.4f} on critical inputs dependency ({level_text}). This reflects the concentration of critical raw material imports across supplier countries.",
        "logistics": f"{country} scores {score:.4f} on logistics/freight dependency ({level_text}). This reflects the concentration of international freight across transport modes and bilateral partners.",
    }
    return templates[axis_slug]


# ---------------------------------------------------------------------------
# Load axis scores from actual CSV files on disk
# ---------------------------------------------------------------------------

def load_axis_scores(axis_num: int) -> dict[str, float]:
    """
    Load final scores for one axis. Returns {country_code: score}.
    Only loads axes whose data is materialized on disk.
    """
    reg = AXIS_REGISTRY[axis_num]

    if reg.get("not_yet_materialized"):
        return {}

    dirpath = DATA / reg["data_dir"]
    filepath = dirpath / reg["final_file"]
    rows = read_csv(filepath)

    if len(rows) == 0:
        fatal(f"Axis {axis_num}: zero rows in {filepath}")

    score_col = reg["score_column"]
    country_col = reg["country_key"]
    scores = {}

    for row in rows:
        geo = row.get(country_col, "").strip()
        if geo not in EU27_SET:
            continue
        raw = row.get(score_col, "").strip()
        s = parse_float(raw, f"axis {axis_num}, country {geo}")
        if s < 0.0 or s > 1.0:
            fatal(f"Axis {axis_num}: score {s} out of [0,1] for {geo}")
        if geo in scores:
            fatal(f"Axis {axis_num}: duplicate country {geo}")
        scores[geo] = s

    # Verify EU-27 coverage
    missing = EU27_SET - set(scores.keys())
    if missing:
        fatal(f"Axis {axis_num}: missing EU-27 countries: {sorted(missing)}")

    return scores


def load_audit_data(axis_num: int) -> dict[str, dict]:
    """Load per-country audit breakdown for axes that have audit files."""
    reg = AXIS_REGISTRY[axis_num]
    if reg.get("not_yet_materialized") or reg["audit_file"] is None:
        return {}

    filepath = DATA / reg["data_dir"] / reg["audit_file"]
    rows = read_csv(filepath)
    cols = reg["audit_columns"]
    country_col = reg["country_key"]
    result = {}

    for row in rows:
        geo = row.get(country_col, "").strip()
        if geo not in EU27_SET:
            continue

        entry = {}
        for key, col_name in cols.items():
            raw = row.get(col_name, "").strip()
            if key == "basis":
                entry[key] = raw
            else:
                entry[key] = parse_float(raw, f"axis {axis_num} audit, {geo}, {key}")

        result[geo] = entry

    return result


def load_channel_shares(axis_num: int, channel_idx: int) -> dict[str, list[dict]]:
    """
    Load bilateral partner shares for a channel.
    Returns {country: [{partner, share}, ...]} sorted by share descending.
    """
    reg = AXIS_REGISTRY[axis_num]
    if reg.get("not_yet_materialized"):
        return {}

    ch = reg["channels"][channel_idx]
    shares_file = ch.get("shares_file")
    if shares_file is None:
        return {}

    filepath = DATA / reg["data_dir"] / shares_file
    rows = read_csv(filepath)

    country_key = ch["country_key"]
    partner_key = ch["partner_key"]

    by_country: dict[str, list[dict]] = {}

    for row in rows:
        geo = row.get(country_key, "").strip()
        if geo not in EU27_SET:
            continue
        partner = row.get(partner_key, "").strip()
        share = parse_float(row.get("share", "0"), f"shares axis {axis_num}, {geo}")

        if share <= 0.0:
            continue

        if geo not in by_country:
            by_country[geo] = []
        by_country[geo].append({"partner": partner, "share": round(share, 8)})

    # Sort each country's partners by share descending
    for geo in by_country:
        by_country[geo].sort(key=lambda x: -x["share"])

    return by_country


def load_energy_fuel_concentrations() -> dict[str, dict[str, float]]:
    """
    Load per-fuel concentration for each EU-27 country.
    Returns {country: {gas: hhi, oil: hhi, solid_fossil: hhi}}.
    """
    result: dict[str, dict[str, float]] = {}

    fuel_files = {
        "gas": DATA / "energy" / "nrg_ti_gas_2024_fuel_concentration.csv",
        "oil": DATA / "energy" / "nrg_ti_oil_2024_fuel_concentration.csv",
        "solid_fossil": DATA / "energy" / "nrg_ti_sff_2024_fuel_concentration.csv",
    }

    for fuel_name, filepath in fuel_files.items():
        rows = read_csv(filepath)
        for row in rows:
            geo = row.get("geo", "").strip()
            if geo not in EU27_SET:
                continue
            conc = parse_float(row.get("concentration", "0"),
                               f"energy fuel {fuel_name}, {geo}")
            if geo not in result:
                result[geo] = {}
            result[geo][fuel_name] = round(conc, 8)

    return result


def load_subcategory_data(axis_num: int, channel_idx: int) -> dict[str, list[dict]]:
    """
    Load subcategory (capability block / HS category) breakdowns.
    Returns {country: [{category, concentration, volume}, ...]}.
    """
    reg = AXIS_REGISTRY[axis_num]
    if reg.get("not_yet_materialized"):
        return {}

    ch = reg["channels"][channel_idx]
    sub_file = ch.get("subcategory_concentration_file")
    if sub_file is None:
        return {}

    filepath = DATA / reg["data_dir"] / sub_file
    rows = read_csv(filepath)
    country_key = ch["country_key"]

    by_country: dict[str, list[dict]] = {}

    for row in rows:
        geo = row.get(country_key, "").strip()
        if geo not in EU27_SET:
            continue

        # Detect category column name
        cat_name = None
        for candidate in ("hs_category", "capability_block", "mode",
                          "material_group"):
            if candidate in row:
                cat_name = candidate
                break

        if cat_name is None:
            fatal(f"No subcategory column found in {filepath}")

        entry = {
            "category": row[cat_name],
            "concentration": parse_float(row.get("concentration", "0"),
                                         f"subcat axis {axis_num}, {geo}"),
        }

        # Volume column varies
        for vol_col in ("category_value", "block_tiv", "mode_tonnes",
                         "group_value"):
            if vol_col in row:
                entry["volume"] = parse_float(row[vol_col],
                                              f"subcat vol axis {axis_num}, {geo}")
                break

        if geo not in by_country:
            by_country[geo] = []
        by_country[geo].append(entry)

    return by_country


# ---------------------------------------------------------------------------
# Build JSON artifacts
# ---------------------------------------------------------------------------

def build_meta() -> dict:
    return {
        "project": "Panargus / International Sovereignty Index (ISI)",
        "version": VERSION,
        "reference_window": WINDOW,
        "scope": "EU-27",
        "num_axes": NUM_AXES,
        "num_countries": len(EU27),
        "aggregation_rule": "unweighted_arithmetic_mean",
        "aggregation_formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
        "score_range": [0.0, 1.0],
        "interpretation": "higher = more concentrated = more dependent",
        "generated_by": "export_isi_backend_v01.py",
    }


def build_axes_registry() -> list[dict]:
    axes = []
    for axis_num in sorted(AXIS_REGISTRY.keys()):
        reg = AXIS_REGISTRY[axis_num]
        axes.append({
            "id": reg["id"],
            "slug": reg["slug"],
            "name": reg["name"],
            "description": reg["description"],
            "unit": reg["unit"],
            "version": VERSION,
            "status": "FROZEN",
            "materialized": not reg.get("not_yet_materialized", False),
            "channels": [
                {"id": ch["id"], "name": ch["name"], "source": ch["source"]}
                for ch in reg["channels"]
            ],
            "warnings": reg["warnings"],
        })
    return axes


def build_country_detail(
    country: str,
    all_scores: dict[int, dict[str, float]],
    all_audits: dict[int, dict[str, dict]],
    all_shares: dict[int, dict[int, dict[str, list[dict]]]],
    energy_fuels: dict[str, dict[str, float]],
    all_subcats: dict[int, dict[int, dict[str, list[dict]]]],
) -> dict:
    """Build the complete detail object for one country."""

    name = COUNTRY_NAMES.get(country, country)

    axes_detail = []
    score_sum = 0.0
    axes_with_data = 0

    for axis_num in range(1, NUM_AXES + 1):
        reg = AXIS_REGISTRY[axis_num]
        slug = reg["slug"]

        scores = all_scores.get(axis_num, {})
        score = scores.get(country)

        axis_entry = {
            "axis_id": axis_num,
            "axis_slug": slug,
            "axis_name": reg["name"],
        }

        if score is not None:
            axis_entry["score"] = round(score, 8)
            axis_entry["classification"] = classify_score(score)
            axis_entry["driver_statement"] = driver_statement(slug, score, name)
            score_sum += score
            axes_with_data += 1
        else:
            axis_entry["score"] = None
            axis_entry["classification"] = None
            axis_entry["driver_statement"] = f"{name}: Axis {axis_num} ({reg['name']}) data not yet materialized on disk."

        # Audit breakdown
        audits = all_audits.get(axis_num, {})
        if country in audits:
            axis_entry["audit"] = audits[country]

        # Channel breakdowns
        channels = []
        for ch_idx, ch_def in enumerate(reg["channels"]):
            ch_entry = {
                "channel_id": ch_def["id"],
                "channel_name": ch_def["name"],
                "source": ch_def["source"],
            }

            # Top partners
            shares_data = all_shares.get(axis_num, {}).get(ch_idx, {})
            if country in shares_data:
                partners = shares_data[country]
                ch_entry["top_partners"] = partners[:10]
                ch_entry["total_partners"] = len(partners)

            # Subcategory breakdown
            subcat_data = all_subcats.get(axis_num, {}).get(ch_idx, {})
            if country in subcat_data:
                ch_entry["subcategories"] = subcat_data[country]

            channels.append(ch_entry)

        if channels:
            axis_entry["channels"] = channels

        # Energy-specific fuel breakdown
        if axis_num == 2 and country in energy_fuels:
            axis_entry["fuel_concentrations"] = energy_fuels[country]

        # Warnings
        axis_entry["warnings"] = reg["warnings"]

        axes_detail.append(axis_entry)

    # Composite
    if axes_with_data == NUM_AXES:
        composite = score_sum / NUM_AXES
    else:
        composite = None

    return {
        "country": country,
        "country_name": name,
        "version": VERSION,
        "window": WINDOW,
        "isi_composite": round(composite, 8) if composite is not None else None,
        "isi_classification": classify_score(composite) if composite is not None else None,
        "axes_available": axes_with_data,
        "axes_required": NUM_AXES,
        "axes": axes_detail,
    }


def build_axis_detail(
    axis_num: int,
    all_scores: dict[int, dict[str, float]],
    all_audits: dict[int, dict[str, dict]],
    all_shares: dict[int, dict[int, dict[str, list[dict]]]],
    energy_fuels: dict[str, dict[str, float]],
    all_subcats: dict[int, dict[int, dict[str, list[dict]]]],
) -> dict:
    """Build the complete detail object for one axis across all countries."""

    reg = AXIS_REGISTRY[axis_num]
    scores = all_scores.get(axis_num, {})

    countries = []
    for country in EU27:
        score = scores.get(country)
        entry = {
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
        }

        if score is not None:
            entry["score"] = round(score, 8)
            entry["classification"] = classify_score(score)
        else:
            entry["score"] = None
            entry["classification"] = None

        # Audit
        audits = all_audits.get(axis_num, {})
        if country in audits:
            entry["audit"] = audits[country]

        countries.append(entry)

    # Sort by score descending (most concentrated first), nulls last
    countries.sort(key=lambda x: -(x["score"] if x["score"] is not None else -1.0))

    vals = [c["score"] for c in countries if c["score"] is not None]

    return {
        "axis_id": axis_num,
        "axis_slug": reg["slug"],
        "axis_name": reg["name"],
        "description": reg["description"],
        "version": VERSION,
        "status": "FROZEN",
        "materialized": not reg.get("not_yet_materialized", False),
        "unit": reg["unit"],
        "countries_scored": len(vals),
        "statistics": {
            "min": round(min(vals), 8) if vals else None,
            "max": round(max(vals), 8) if vals else None,
            "mean": round(sum(vals) / len(vals), 8) if vals else None,
        },
        "channels": [
            {"id": ch["id"], "name": ch["name"], "source": ch["source"]}
            for ch in reg["channels"]
        ],
        "warnings": reg["warnings"],
        "countries": countries,
    }


def build_isi_composite(
    all_scores: dict[int, dict[str, float]],
) -> dict:
    """Build the ISI composite summary."""

    rows = []
    for country in EU27:
        axis_scores = {}
        complete = True
        for axis_num in range(1, NUM_AXES + 1):
            s = all_scores.get(axis_num, {}).get(country)
            if s is not None:
                axis_scores[axis_num] = round(s, 8)
            else:
                complete = False

        if complete and len(axis_scores) == NUM_AXES:
            composite = sum(axis_scores.values()) / NUM_AXES
        else:
            composite = None

        rows.append({
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
            "axis_1_financial": axis_scores.get(1),
            "axis_2_energy": axis_scores.get(2),
            "axis_3_technology": axis_scores.get(3),
            "axis_4_defense": axis_scores.get(4),
            "axis_5_critical_inputs": axis_scores.get(5),
            "axis_6_logistics": axis_scores.get(6),
            "isi_composite": round(composite, 8) if composite is not None else None,
            "classification": classify_score(composite) if composite is not None else None,
            "complete": complete,
        })

    # Sort by composite descending, nulls last
    rows.sort(key=lambda x: -(x["isi_composite"] if x["isi_composite"] is not None else -1.0))

    vals = [r["isi_composite"] for r in rows if r["isi_composite"] is not None]

    return {
        "version": VERSION,
        "window": WINDOW,
        "aggregation_rule": "unweighted_arithmetic_mean",
        "formula": "ISI_i = (A1_i + A2_i + A3_i + A4_i + A5_i + A6_i) / 6",
        "countries_complete": len(vals),
        "countries_total": len(EU27),
        "statistics": {
            "min": round(min(vals), 8) if vals else None,
            "max": round(max(vals), 8) if vals else None,
            "mean": round(sum(vals) / len(vals), 8) if vals else None,
        },
        "countries": rows,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("export_isi_backend_v01.py")
    print(f"Output: {OUTPUT_ROOT}")
    print()

    # -- Phase 1: Load all axis scores --
    print("Phase 1: Loading axis scores...")
    all_scores: dict[int, dict[str, float]] = {}
    for axis_num in range(1, NUM_AXES + 1):
        reg = AXIS_REGISTRY[axis_num]
        if reg.get("not_yet_materialized"):
            print(f"  Axis {axis_num} ({reg['slug']}): NOT YET MATERIALIZED — skipping data load")
            continue
        scores = load_axis_scores(axis_num)
        all_scores[axis_num] = scores
        print(f"  Axis {axis_num} ({reg['slug']}): {len(scores)} countries loaded")
    print()

    # -- Phase 2: Load audit data --
    print("Phase 2: Loading audit breakdowns...")
    all_audits: dict[int, dict[str, dict]] = {}
    for axis_num in range(1, NUM_AXES + 1):
        audits = load_audit_data(axis_num)
        if audits:
            all_audits[axis_num] = audits
            print(f"  Axis {axis_num}: {len(audits)} audit rows loaded")
        else:
            print(f"  Axis {axis_num}: no audit data")
    print()

    # -- Phase 3: Load channel shares (top partners) --
    print("Phase 3: Loading channel partner shares...")
    all_shares: dict[int, dict[int, dict[str, list[dict]]]] = {}
    for axis_num in range(1, NUM_AXES + 1):
        reg = AXIS_REGISTRY[axis_num]
        if reg.get("not_yet_materialized"):
            continue
        all_shares[axis_num] = {}
        for ch_idx, ch_def in enumerate(reg["channels"]):
            shares = load_channel_shares(axis_num, ch_idx)
            if shares:
                all_shares[axis_num][ch_idx] = shares
                sample_count = len(next(iter(shares.values())))
                print(f"  Axis {axis_num} Channel {ch_def['id']}: {len(shares)} countries, ~{sample_count} partners each")
    print()

    # -- Phase 4: Load energy fuel concentrations --
    print("Phase 4: Loading energy fuel concentrations...")
    energy_fuels = load_energy_fuel_concentrations()
    print(f"  {len(energy_fuels)} countries with fuel breakdowns")
    print()

    # -- Phase 5: Load subcategory data --
    print("Phase 5: Loading subcategory breakdowns...")
    all_subcats: dict[int, dict[int, dict[str, list[dict]]]] = {}
    for axis_num in range(1, NUM_AXES + 1):
        reg = AXIS_REGISTRY[axis_num]
        if reg.get("not_yet_materialized"):
            continue
        all_subcats[axis_num] = {}
        for ch_idx, ch_def in enumerate(reg["channels"]):
            subcats = load_subcategory_data(axis_num, ch_idx)
            if subcats:
                all_subcats[axis_num][ch_idx] = subcats
                print(f"  Axis {axis_num} Channel {ch_def['id']}: {len(subcats)} countries with subcategory data")
    print()

    # -- Phase 6: Materialize JSON --
    print("Phase 6: Writing JSON artifacts...")

    # meta.json
    write_json(OUTPUT_ROOT / "meta.json", build_meta())
    print("  meta.json")

    # axes.json
    write_json(OUTPUT_ROOT / "axes.json", build_axes_registry())
    print("  axes.json")

    # isi.json
    isi_data = build_isi_composite(all_scores)
    write_json(OUTPUT_ROOT / "isi.json", isi_data)
    print(f"  isi.json ({isi_data['countries_complete']} complete)")

    # countries.json — summary list
    countries_summary = []
    for country in EU27:
        entry = {
            "country": country,
            "country_name": COUNTRY_NAMES.get(country, country),
        }
        for axis_num in range(1, NUM_AXES + 1):
            slug = AXIS_REGISTRY[axis_num]["slug"]
            s = all_scores.get(axis_num, {}).get(country)
            entry[f"axis_{axis_num}_{slug}"] = round(s, 8) if s is not None else None

        axis_vals = [v for k, v in entry.items()
                     if k.startswith("axis_") and v is not None]
        if len(axis_vals) == NUM_AXES:
            entry["isi_composite"] = round(sum(axis_vals) / NUM_AXES, 8)
        else:
            entry["isi_composite"] = None

        countries_summary.append(entry)

    write_json(OUTPUT_ROOT / "countries.json", countries_summary)
    print(f"  countries.json ({len(countries_summary)} countries)")

    # Per-country detail files
    country_dir = OUTPUT_ROOT / "country"
    for country in EU27:
        detail = build_country_detail(
            country, all_scores, all_audits, all_shares,
            energy_fuels, all_subcats,
        )
        write_json(country_dir / f"{country}.json", detail)
    print(f"  country/*.json ({len(EU27)} files)")

    # Per-axis detail files
    axis_dir = OUTPUT_ROOT / "axis"
    for axis_num in range(1, NUM_AXES + 1):
        detail = build_axis_detail(
            axis_num, all_scores, all_audits, all_shares,
            energy_fuels, all_subcats,
        )
        write_json(axis_dir / f"{axis_num}.json", detail)
    print(f"  axis/*.json ({NUM_AXES} files)")

    # -- Summary --
    print()
    total_files = 1 + 1 + 1 + 1 + len(EU27) + NUM_AXES
    print(f"Total artifacts: {total_files} JSON files")
    print(f"Axes materialized: {len(all_scores)}/{NUM_AXES}")
    print(f"Axes pending: {NUM_AXES - len(all_scores)}")
    print()

    if isi_data["countries_complete"] == len(EU27):
        print("EXPORT PASS \u2014 ALL 27 COUNTRIES COMPLETE")
    else:
        print(f"EXPORT PARTIAL \u2014 {isi_data['countries_complete']}/{len(EU27)} countries complete")
        print("Axes 5 and 6 not yet materialized to disk.")

    print()


if __name__ == "__main__":
    main()
