"""
pipeline.config — Central configuration for the ISI ingestion pipeline.

Every path, threshold, country mapping, and structural constant
lives HERE. No magic numbers anywhere else in the pipeline.

Design lifetime: 20 years. Extend via REGISTRY dicts, never delete.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Project root — resolved ONCE
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
DATA_ROOT: Path = PROJECT_ROOT / "data"

# ---------------------------------------------------------------------------
# Layer paths — the four canonical pipeline layers
# ---------------------------------------------------------------------------

RAW_DIR: Path = DATA_ROOT / "raw"
STAGING_DIR: Path = DATA_ROOT / "staging"
VALIDATED_DIR: Path = DATA_ROOT / "validated"
META_DIR: Path = DATA_ROOT / "meta"
AUDIT_DIR: Path = DATA_ROOT / "audit" / "pipeline"

# ---------------------------------------------------------------------------
# Source identifiers — one per upstream dataset
# ---------------------------------------------------------------------------

SOURCES = (
    "imf_cpis",
    "bis_lbs",
    "un_comtrade",
    "eurostat_comext",
    "eurostat_nrg",
    "sipri",
    "oecd_logistics",
    "national_stats",
)

# ---------------------------------------------------------------------------
# Axis registry — maps axis_id to slug and data sources
# ---------------------------------------------------------------------------

AXIS_REGISTRY: dict[int, dict[str, Any]] = {
    1: {
        "slug": "financial",
        "sources": ["imf_cpis", "bis_lbs"],
        "description": "Financial external supplier concentration",
        "channel_a": "bis_lbs",
        "channel_b": "imf_cpis",
        # ── Interpretability metadata (Task 1 + Task 4) ──────────────
        "value_type": "USD_MN",
        "value_label": "USD millions (nominal)",
        "scope": "Cross-border banking claims (BIS LBS) + portfolio investment positions (IMF CPIS)",
        "exclusions": [
            "FDI stocks and flows",
            "Domestic financial exposures",
            "Derivatives and off-balance-sheet instruments",
            "Non-reporting BIS countries (approx. 150 jurisdictions)",
        ],
        "interpretation_note": (
            "Measures concentration of cross-border financial claims and portfolio "
            "investment among reporting counterparties. Does NOT capture full "
            "financial dependency — FDI, domestic banking, and derivatives are excluded. "
            "BIS LBS coverage is limited to ~30 reporting countries; CPIS to ~80 participants."
        ),
        "confidence_baseline": 0.75,
        "window_type": "snapshot",
        "window_semantics": "Point-in-time positions (BIS quarterly, CPIS annual)",
        "temporal_sensitivity": "low",
    },
    2: {
        "slug": "energy",
        "sources": ["un_comtrade", "eurostat_nrg"],
        "description": "Energy external supplier concentration",
        "channel_a": "un_comtrade",  # fuel imports by partner
        "channel_b": "un_comtrade",  # fuel-category mix
        "value_type": "USD_MN",
        "value_label": "USD millions (nominal trade value)",
        "scope": "Bilateral imports of HS 2701/2709/2710/2711/2716 (coal, crude oil, petroleum products, natural gas/LNG, electricity)",
        "exclusions": [
            "Uranium and nuclear fuel (HS 2612 — under critical_inputs)",
            "Renewable energy equipment imports",
            "Long-term supply contract terms (only realized trade captured)",
            "Energy transit / re-export flows",
        ],
        "interpretation_note": (
            "Measures concentration of energy commodity imports by trade value. "
            "Trade value may not reflect volume dependency (price volatility distorts). "
            "Does NOT capture long-term contract lock-in, strategic reserves, "
            "or domestic production capacity."
        ),
        "confidence_baseline": 0.80,
        "window_type": "annual_flow",
        "window_semantics": "Calendar year trade flows (UN Comtrade mirror)",
        "temporal_sensitivity": "moderate",
    },
    3: {
        "slug": "technology",
        "sources": ["un_comtrade", "eurostat_comext"],
        "description": "Technology semiconductor external supplier concentration",
        "channel_a": "un_comtrade",  # semiconductor imports
        "channel_b": "un_comtrade",  # product-category mix
        "value_type": "USD_MN",
        "value_label": "USD millions (nominal trade value)",
        "scope": "Bilateral imports of HS 8541 (semiconductor devices) and HS 8542 (electronic integrated circuits)",
        "exclusions": [
            "Semiconductor manufacturing equipment (HS 8486)",
            "Design IP and licensing (services trade, not goods)",
            "Fabless design dependency (captured as goods from fabrication country)",
            "Embedded semiconductors in finished products",
        ],
        "interpretation_note": (
            "Measures concentration of semiconductor goods imports. Country of "
            "export may differ from country of design or IP ownership "
            "(e.g., TSMC chips exported from Taiwan, designed in US). "
            "Does NOT capture the full semiconductor supply chain dependency."
        ),
        "confidence_baseline": 0.80,
        "window_type": "annual_flow",
        "window_semantics": "Calendar year trade flows (UN Comtrade / Eurostat CN8)",
        "temporal_sensitivity": "moderate",
    },
    4: {
        "slug": "defense",
        "sources": ["sipri"],
        "description": "Defense external supplier concentration",
        "channel_a": "sipri",
        "channel_b": "sipri",  # capability-block structure
        "value_type": "TIV_MN",
        "value_label": "SIPRI Trend Indicator Value (TIV) millions",
        "scope": (
            "Major conventional weapons transfers as tracked by SIPRI Arms "
            "Transfers Database. Covers: aircraft, armoured vehicles, artillery, "
            "air defence systems, anti-submarine warfare weapons, engines, "
            "missiles, naval weapons, satellites, sensors/EW, ships, other."
        ),
        "exclusions": [
            "Small arms and light weapons (SALW)",
            "Ammunition and ordnance",
            "Dual-use technology transfers",
            "Military services, training, and advisory contracts",
            "Cyber and electronic warfare capabilities",
            "Licensed production (partially captured via 'Local production' flag)",
            "Black/grey market transfers",
            "Maintenance, repair, and overhaul (MRO) contracts",
        ],
        "interpretation_note": (
            "CRITICAL: TIV is NOT a monetary value. It is an index measuring "
            "the military capability transferred, based on production cost of "
            "a core set of weapons. TIV cannot be compared to USD trade values "
            "on other axes. A country with high defense TIV concentration and "
            "low trade-value concentration on other axes is NOT necessarily "
            "more dependent on defense than on trade — the units are incommensurable. "
            "SIPRI covers only MAJOR conventional weapons; small arms, ammunition, "
            "cyber, and services are excluded. Defense dependency as measured here "
            "is a PARTIAL view of military supply chain exposure."
        ),
        "confidence_baseline": 0.55,
        "window_type": "rolling_delivery_window",
        "window_semantics": (
            "6-year delivery window (2020-2025). Arms procurement is inherently lumpy: "
            "a single multi-billion fighter jet order delivered in one year can dominate "
            "the window. Year-to-year volatility is expected and does NOT indicate "
            "changing dependency — it reflects delivery schedules. The 6-year window "
            "smooths some lumpiness but cannot eliminate it for small importers."
        ),
        "temporal_sensitivity": "high",
    },
    5: {
        "slug": "critical_inputs",
        "sources": ["un_comtrade", "eurostat_comext"],
        "description": "Critical inputs raw materials external supplier concentration",
        "channel_a": "un_comtrade",
        "channel_b": "un_comtrade",  # material-group mix
        "value_type": "USD_MN",
        "value_label": "USD millions (nominal trade value)",
        "scope": "Bilateral imports of critical raw materials: rare earths (HS 2612/2846), lithium (2825/2836), cobalt (2605/8105), manganese (2602), titanium (2614/8108), chromium (2610), tungsten (2611), platinum (7110), graphite (2504), niobium (2615), silicon (2804)",
        "exclusions": [
            "Processed/refined critical materials beyond HS scope",
            "Recycled/secondary materials",
            "Stockpile releases (domestic, not trade)",
            "Long-term offtake agreements (only realized trade captured)",
        ],
        "interpretation_note": (
            "Measures concentration of critical raw material imports by trade value. "
            "Trade value may underrepresent volume dependency for low-unit-value "
            "high-volume materials. Does NOT capture recycling, stockpiles, "
            "or substitution capacity."
        ),
        "confidence_baseline": 0.75,
        "window_type": "annual_flow",
        "window_semantics": "Calendar year trade flows (UN Comtrade / Eurostat CN8)",
        "temporal_sensitivity": "moderate",
    },
    6: {
        "slug": "logistics",
        "sources": ["oecd_logistics", "national_stats", "eurostat_comext"],
        "description": "Logistics freight external supplier concentration",
        "channel_a": "national_stats",  # mode-share structure
        "channel_b": "national_stats",  # bilateral maritime/rail
        "value_type": "MIXED",
        "value_label": "Mixed units (tonnes, TEU, modal shares — source-dependent)",
        "scope": "Freight logistics infrastructure dependency: maritime container flows, rail freight, air cargo by partner country of origin/transit",
        "exclusions": [
            "Pipeline transport (captured partially via energy axis)",
            "Digital/data logistics",
            "Warehousing and inland distribution",
            "Insurance and financial logistics services",
        ],
        "interpretation_note": (
            "Measures concentration of physical logistics flows. Data availability "
            "varies significantly across countries and modes. Maritime data is "
            "most complete; rail and air cargo coverage is partial. "
            "Interpretation requires awareness of each country's modal mix."
        ),
        "confidence_baseline": 0.60,
        "window_type": "annual_flow",
        "window_semantics": "Annual logistics statistics (OECD/national sources)",
        "temporal_sensitivity": "low",
    },
}

AXIS_SLUGS: dict[int, str] = {k: v["slug"] for k, v in AXIS_REGISTRY.items()}

# ---------------------------------------------------------------------------
# ISO country code mappings — comprehensive, auditable
# ---------------------------------------------------------------------------

# ISO-3 alpha → ISO-2 alpha (complete for all ISI-relevant countries)
ISO3_TO_ISO2: dict[str, str] = {
    # EU-27
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "CYP": "CY", "CZE": "CZ",
    "DEU": "DE", "DNK": "DK", "EST": "EE", "GRC": "GR", "ESP": "ES",
    "FIN": "FI", "FRA": "FR", "HRV": "HR", "HUN": "HU", "IRL": "IE",
    "ITA": "IT", "LTU": "LT", "LUX": "LU", "LVA": "LV", "MLT": "MT",
    "NLD": "NL", "POL": "PL", "PRT": "PT", "ROU": "RO", "SWE": "SE",
    "SVN": "SI", "SVK": "SK",
    # Phase 1 expansion
    "AUS": "AU", "CHN": "CN", "GBR": "GB", "JPN": "JP",
    "KOR": "KR", "NOR": "NO", "USA": "US",
    # Major trade partners (appear as partners in bilateral data)
    "TWN": "TW", "SGP": "SG", "MYS": "MY", "THA": "TH", "VNM": "VN",
    "IDN": "ID", "PHL": "PH", "IND": "IN", "BRA": "BR", "MEX": "MX",
    "CAN": "CA", "CHE": "CH", "ISR": "IL", "SAU": "SA", "ARE": "AE",
    "ZAF": "ZA", "RUS": "RU", "TUR": "TR", "NZL": "NZ", "ARG": "AR",
    "CHL": "CL", "COL": "CO", "PER": "PE", "NGA": "NG", "EGY": "EG",
    "PAK": "PK", "BGD": "BD", "UKR": "UA", "KAZ": "KZ", "QAT": "QA",
    "KWT": "KW", "OMN": "OM", "BHR": "BH", "IRQ": "IQ", "IRN": "IR",
    "LBY": "LY", "AGO": "AO", "COD": "CD", "MMR": "MM", "LKA": "LK",
    "PNG": "PG", "BOL": "BO", "PRY": "PY", "URY": "UY", "CRI": "CR",
    "PAN": "PA", "DOM": "DO", "GTM": "GT", "HND": "HN", "SLV": "SV",
    "JAM": "JM", "TTO": "TT", "GHA": "GH", "SEN": "SN", "TZA": "TZ",
    "KEN": "KE", "ETH": "ET", "MOZ": "MZ", "ZMB": "ZM", "ZWE": "ZW",
    "NAM": "NA", "BWA": "BW", "MUS": "MU", "JOR": "JO", "LBN": "LB",
    "GEO": "GE", "ARM": "AM", "AZE": "AZ", "UZB": "UZ", "TKM": "TM",
    "MNG": "MN", "BRN": "BN", "KHM": "KH", "LAO": "LA",
}

ISO2_TO_ISO3: dict[str, str] = {v: k for k, v in ISO3_TO_ISO2.items()}

# IMF CPIS uses its own country code system (ISO-3 based with variations)
CPIS_TO_ISO2: dict[str, str] = {
    **ISO3_TO_ISO2,
    # Overrides for CPIS-specific codes
    "EA": "EA",   # Euro area aggregate (filtered as aggregate)
}

# BIS uses ISO-2 but with some non-standard codes
BIS_TO_ISO2: dict[str, str] = {
    "5J": "__AGGREGATE__",  # All reporting countries
    "5A": "__AGGREGATE__",  # BIS-reporting countries
    "1C": "__AGGREGATE__",  # Advanced economies
    "4T": "__AGGREGATE__",  # OPEC
    "4Z": "__AGGREGATE__",  # Other
    "1R": "__AGGREGATE__",  # All countries
}

# SIPRI country name → ISO-2 (comprehensive)
# Audited against data/raw/sipri/trade-register.csv (5532 rows, 69 suppliers, 172 recipients)
SIPRI_TO_ISO2: dict[str, str] = {
    "Afghanistan": "AF", "Albania": "AL", "Algeria": "DZ",
    "Angola": "AO", "Antigua and Barbuda": "AG", "Argentina": "AR", "Armenia": "AM",
    "Australia": "AU", "Austria": "AT", "Azerbaijan": "AZ",
    "Bahrain": "BH", "Bangladesh": "BD", "Belarus": "BY",
    "Belgium": "BE", "Belize": "BZ", "Benin": "BJ",
    "Bhutan": "BT", "Bolivia": "BO", "Bosnia-Herzegovina": "BA",
    "Botswana": "BW", "Brazil": "BR", "Brunei": "BN",
    "Bulgaria": "BG", "Burkina Faso": "BF", "Cambodia": "KH",
    "Cameroon": "CM", "Canada": "CA",
    "Central African Republic": "CF", "Chad": "TD",
    "Chile": "CL", "China": "CN", "Colombia": "CO",
    "Comoros": "KM", "Congo": "CG", "Congo, Republic": "CG",
    "Costa Rica": "CR", "Cote d'Ivoire": "CI",
    "Croatia": "HR", "Cuba": "CU", "Cyprus": "CY",
    "Czechia": "CZ", "Czech Republic": "CZ",
    "DR Congo": "CD",
    "Denmark": "DK", "Djibouti": "DJ", "Dominican Republic": "DO",
    "Ecuador": "EC", "Egypt": "EG", "El Salvador": "SV",
    "Equatorial Guinea": "GQ",
    "Estonia": "EE", "Ethiopia": "ET", "Fiji": "FJ", "Finland": "FI",
    "France": "FR", "Gabon": "GA", "Gambia": "GM", "Georgia": "GE",
    "Germany": "DE", "Ghana": "GH", "Greece": "GR",
    "Guatemala": "GT", "Guinea": "GN", "Guyana": "GY",
    "Haiti": "HT", "Honduras": "HN", "Hungary": "HU",
    "India": "IN", "Indonesia": "ID", "Iran": "IR",
    "Iraq": "IQ", "Ireland": "IE", "Israel": "IL",
    "Italy": "IT", "Jamaica": "JM", "Japan": "JP",
    "Jordan": "JO", "Kazakhstan": "KZ", "Kenya": "KE",
    "Korea, South": "KR", "Korea South": "KR",
    "Kosovo": "XK",
    "South Korea": "KR", "Republic of Korea": "KR",
    "Kuwait": "KW", "Kyrgyzstan": "KG",
    "Laos": "LA", "Latvia": "LV", "Lebanon": "LB",
    "Liberia": "LR", "Libya": "LY", "Lithuania": "LT", "Luxembourg": "LU",
    "Madagascar": "MG", "Malawi": "MW", "Malaysia": "MY",
    "Maldives": "MV", "Mali": "ML", "Malta": "MT", "Mauritania": "MR",
    "Mauritius": "MU", "Mexico": "MX", "Moldova": "MD",
    "Mongolia": "MN", "Montenegro": "ME", "Morocco": "MA",
    "Mozambique": "MZ", "Myanmar": "MM", "Namibia": "NA",
    "Nepal": "NP", "Netherlands": "NL", "New Zealand": "NZ",
    "Nicaragua": "NI", "Niger": "NE", "Nigeria": "NG",
    "North Korea": "KP", "North Macedonia": "MK", "Norway": "NO",
    "Oman": "OM", "Pakistan": "PK", "Palestine": "PS", "Panama": "PA",
    "Papua New Guinea": "PG", "Paraguay": "PY", "Peru": "PE",
    "Philippines": "PH", "Poland": "PL", "Portugal": "PT",
    "Qatar": "QA", "Romania": "RO", "Russia": "RU",
    "Rwanda": "RW", "Saudi Arabia": "SA", "Senegal": "SN",
    "Serbia": "RS", "Seychelles": "SC", "Singapore": "SG", "Slovakia": "SK",
    "Slovenia": "SI", "Solomon Islands": "SB",
    "Somalia": "SO", "South Africa": "ZA", "South Sudan": "SS", "Spain": "ES",
    "Sri Lanka": "LK", "Sudan": "SD", "Suriname": "SR", "Sweden": "SE",
    "Switzerland": "CH", "Syria": "SY", "eSwatini": "SZ",
    "Taiwan": "TW", "Tajikistan": "TJ", "Tanzania": "TZ",
    "Thailand": "TH", "Togo": "TG",
    "Tonga": "TO", "Trinidad and Tobago": "TT",
    "Tunisia": "TN", "Turkey": "TR", "Turkiye": "TR", "Turkmenistan": "TM",
    "Uganda": "UG", "Ukraine": "UA",
    "UAE": "AE", "United Arab Emirates": "AE", "United Kingdom": "GB",
    "United States": "US", "Uruguay": "UY",
    "Uzbekistan": "UZ", "Vanuatu": "VU",
    "Venezuela": "VE", "Viet Nam": "VN", "Vietnam": "VN",
    "Yemen": "YE", "Zambia": "ZM", "Zimbabwe": "ZW",
    # Non-state / aggregate entities — classified by type for audit transparency.
    # MULTINATIONAL: intergovernmental organizations with recognized legal status.
    #   These are dropped because they lack a single ISO-2 sovereign code,
    #   but they represent legitimate state-backed procurement, not illicit flows.
    # NONSTATE: armed non-state actors, sub-national factions, rebel groups.
    #   These are dropped because they are not sovereign entities and their
    #   procurement patterns do not represent national-level dependency.
    # UNKNOWN: unidentified or unresolvable entities in SIPRI data.
    #
    # All three categories are dropped from ISI computation and tracked
    # separately in ingestion statistics for full audit transparency.
    "Unknown recipient(s)": "__UNKNOWN__",
    "unknown recipient(s)": "__UNKNOWN__",
    "unknown supplier(s)": "__UNKNOWN__",
    "African Union**": "__MULTINATIONAL__",
    "NATO**": "__MULTINATIONAL__",
    "United Nations**": "__MULTINATIONAL__",
    "Hezbollah (Lebanon)*": "__NONSTATE__",
    "House of Representatives (Libya)*": "__NONSTATE__",
    "Houthi rebels (Yemen)*": "__NONSTATE__",
    "RSF (Sudan)*": "__NONSTATE__",
}

# Comtrade numeric → ISO-2 (most common; rest resolved via ISO3)
COMTRADE_NUM_TO_ISO2: dict[int, str] = {
    # UN Comtrade M49 numeric codes → ISO-2
    # Note: Comtrade uses 842 (not 840) for USA in practice
    4: "AF",   8: "AL",  12: "DZ",  20: "AD",  24: "AO",
    28: "AG",  31: "AZ",  32: "AR",  36: "AU",  40: "AT",
    44: "BS",  48: "BH",  50: "BD",  51: "AM",  52: "BB",
    56: "BE",  60: "BM",  64: "BT",  68: "BO",  70: "BA",
    72: "BW",  76: "BR",  84: "BZ",  90: "SB",  96: "BN",
    100: "BG", 104: "MM", 108: "BI", 112: "BY", 116: "KH",
    120: "CM", 124: "CA", 132: "CV", 136: "KY", 140: "CF",
    144: "LK", 148: "TD", 152: "CL", 156: "CN", 158: "TW",
    170: "CO", 174: "KM", 178: "CG", 180: "CD", 188: "CR",
    191: "HR", 192: "CU", 196: "CY", 203: "CZ", 204: "BJ",
    208: "DK", 212: "DM", 214: "DO", 218: "EC", 222: "SV",
    226: "GQ", 231: "ET", 232: "ER", 233: "EE", 242: "FJ",
    246: "FI", 251: "FR", 262: "DJ", 266: "GA", 268: "GE",
    270: "GM", 275: "PS", 276: "DE", 288: "GH", 296: "KI",
    300: "GR", 308: "GD", 320: "GT", 324: "GN", 328: "GY",
    332: "HT", 340: "HN", 344: "HK", 348: "HU", 352: "IS",
    356: "IN", 360: "ID", 364: "IR", 368: "IQ", 372: "IE",
    376: "IL", 380: "IT", 384: "CI", 388: "JM", 392: "JP",
    398: "KZ", 400: "JO", 404: "KE", 408: "KP", 410: "KR",
    414: "KW", 417: "KG", 418: "LA", 422: "LB", 426: "LS",
    428: "LV", 430: "LR", 434: "LY", 438: "LI", 440: "LT",
    442: "LU", 446: "MO", 450: "MG", 454: "MW", 458: "MY",
    462: "MV", 466: "ML", 470: "MT", 478: "MR", 480: "MU",
    484: "MX", 496: "MN", 498: "MD", 499: "ME", 504: "MA",
    508: "MZ", 512: "OM", 516: "NA", 524: "NP", 528: "NL",
    531: "CW", 533: "AW", 540: "NC", 548: "VU", 554: "NZ",
    558: "NI", 562: "NE", 566: "NG", 578: "NO", 579: "NO",
    583: "FM", 584: "MH", 585: "PW", 586: "PK", 591: "PA",
    598: "PG", 600: "PY", 604: "PE", 608: "PH", 616: "PL",
    620: "PT", 624: "GW", 626: "TL", 634: "QA", 642: "RO",
    643: "RU", 646: "RW", 659: "KN", 662: "LC", 670: "VC",
    682: "SA", 686: "SN", 688: "RS", 690: "SC", 694: "SL",
    699: "IN", 702: "SG", 703: "SK", 704: "VN", 705: "SI",
    706: "SO", 710: "ZA", 716: "ZW", 724: "ES", 728: "SS",
    736: "SD", 740: "SR", 748: "SZ", 752: "SE", 756: "CH",
    757: "CH", 760: "SY", 762: "TJ", 764: "TH", 768: "TG",
    776: "TO", 780: "TT", 784: "AE", 788: "TN", 792: "TR",
    795: "TM", 798: "TV", 800: "UG", 804: "UA", 807: "MK",
    818: "EG", 826: "GB", 834: "TZ", 840: "US", 842: "US",
    854: "BF", 858: "UY", 860: "UZ", 862: "VE", 876: "WF",
    882: "WS", 887: "YE", 894: "ZM",
    # Aggregates / special (map to None via AGGREGATE logic)
    # 0: "World", 490: "Other Asia nes", 899: "Other nes"
}

# Map known aggregate numeric codes
COMTRADE_AGGREGATE_CODES: frozenset[int] = frozenset({
    0, 97, 290, 490, 492, 527, 568, 577, 636, 637,
    838, 839, 879, 896, 897, 898, 899,
})

# ---------------------------------------------------------------------------
# Aggregate / reject patterns — partners to ALWAYS reject
# ---------------------------------------------------------------------------

AGGREGATE_PARTNER_NAMES: frozenset[str] = frozenset({
    "World", "WORLD", "world",
    "Other", "OTHER", "other",
    "Not Specified", "NOT_SPECIFIED", "not specified",
    "Not specified", "Not allocated",
    "Unspecified", "UNSPECIFIED", "unspecified",
    "Other Asia, nes", "Other Asia nes",
    "Areas, nes", "Areas nes",
    "Bunkers", "bunkers",
    "Free Zones", "Free zones",
    "Special Categories",
    "Neutral Zone", "Neutral zone",
    "Total", "TOTAL", "total",
    "Rest of world", "Rest of World",
    "European Union", "EU", "Euro area",
})

AGGREGATE_PARTNER_ISO2: frozenset[str] = frozenset({
    "XX", "XZ", "WL", "W0", "W1", "W2",
    "__AGGREGATE__", "__UNKNOWN__", "__NONSTATE__", "__MULTINATIONAL__",
})

# ---------------------------------------------------------------------------
# Validation thresholds
# ---------------------------------------------------------------------------

# Minimum number of bilateral partners for a valid distribution
MIN_PARTNER_COUNT_MAJOR: int = 20     # for G7 + large economies
MIN_PARTNER_COUNT_SMALL: int = 10     # for small open economies
MIN_PARTNER_COUNT_ABSOLUTE: int = 3   # below this → always reject

# Source-specific overrides: some sources have structurally fewer reporters
# BIS LBS only has ~30 reporting countries worldwide
SOURCE_PARTNER_COUNT_OVERRIDE: dict[str, int] = {
    "bis_lbs": 15,    # BIS LBS: ~30 reporting countries, 20+ expected for majors
    "sipri": 3,       # SIPRI: arms transfers are sparse by nature
}

# Major economies that MUST appear as partners (sanity check)
MAJOR_ECONOMY_ISO2: frozenset[str] = frozenset({
    "US", "CN", "DE", "JP", "GB", "FR", "IN",
})

# Sum integrity
MIN_TOTAL_VALUE: float = 0.0          # must be > 0

# Extreme concentration flag
EXTREME_CONCENTRATION_THRESHOLD: float = 0.95  # single partner > 95%

# Missing key partner flag (how many of MAJOR_ECONOMY_ISO2 must appear)
MIN_MAJOR_PARTNERS_PRESENT: int = 3

# Economic sanity thresholds
# Top-10 coverage: share of total captured by top 10 partners
COVERAGE_TOP10_MIN: float = 0.50      # top-10 must capture ≥50%
COVERAGE_TOP10_MAX: float = 0.9999    # top-10 < 100% (at least 1 "other")

# Aggregate mass threshold: if removed aggregates > this share → FAIL
AGGREGATE_MASS_FAIL_THRESHOLD: float = 0.50  # >50% removed → suspicious

# Economic sanity: minimum plausible total values by source (USD)
SANITY_MIN_TOTAL_VALUE: dict[str, float] = {
    "un_comtrade": 1_000_000,       # $1M minimum trade for any axis
    "bis_lbs": 1_000,               # $1B (values in millions) minimum
    "imf_cpis": 1_000,              # $1B (values in millions) minimum
    "sipri": 0.1,                   # 0.1 TIV million (very small OK)
    "eurostat_logistics": 1.0,      # 1 thousand tonnes minimum
}

# Countries that SHOULD appear as partners for economic plausibility
# (source-aware — e.g., US/CN must appear in trade data for major economies)
EXPECTED_TRADE_PARTNERS: dict[str, frozenset[str]] = {
    "un_comtrade": frozenset({"US", "CN", "DE"}),
    "bis_lbs": frozenset({"US", "GB", "FR"}),
    "imf_cpis": frozenset({"US"}),
}

# EU-27 ISO-2 codes — used to determine Eurostat coverage
# Note: Greece uses ISO-standard "GR" here, not Eurostat's "EL".
EU27_ISO2: frozenset[str] = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "GR", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
})

# Eurostat uses non-standard codes for some countries.
# This mapping normalizes Eurostat codes → ISO-3166-1 alpha-2.
EUROSTAT_TO_ISO2: dict[str, str] = {
    "EL": "GR",  # Greece — Eurostat convention → ISO standard
    "UK": "GB",  # United Kingdom — Eurostat convention → ISO standard
}

# HS code definitions per axis
ENERGY_HS_CODES: frozenset[str] = frozenset({
    "2701",   # coal
    "2709",   # crude oil
    "2710",   # petroleum products
    "2711",   # natural gas / LNG
    "2716",   # electricity
})

TECH_HS_CODES: frozenset[str] = frozenset({
    "8541",   # semiconductor devices
    "8542",   # electronic integrated circuits
})

CRITICAL_INPUTS_HS_CODES: frozenset[str] = frozenset({
    # Rare earths
    "2612",   # thorium/uranium ores
    "2846",   # rare-earth compounds
    # Lithium
    "2825",   # lithium oxide/hydroxide
    "2836",   # lithium carbonate
    # Cobalt
    "2605",   # cobalt ores
    "8105",   # cobalt unwrought
    # Manganese
    "2602",   # manganese ores
    # Titanium
    "2614",   # titanium ores
    "8108",   # titanium unwrought
    # Chromium
    "2610",   # chromium ores
    # Tungsten
    "2611",   # tungsten ores
    # Platinum group
    "7110",   # platinum
    # Natural graphite
    "2504",   # natural graphite
    # Niobium
    "2615",   # niobium/tantalum ores
    # Silicon
    "2804",   # silicon
})

# ---------------------------------------------------------------------------
# Year defaults
# ---------------------------------------------------------------------------

DEFAULT_YEAR_RANGE: tuple[int, int] = (2022, 2024)
CPIS_YEAR: int = 2024
BIS_QUARTER: str = "2024-Q4"
SIPRI_YEAR_RANGE: tuple[int, int] = (2020, 2025)

# ---------------------------------------------------------------------------
# Scope imports (reuse from backend)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(PROJECT_ROOT))

from backend.scope import (  # noqa: E402
    EU27_CODES,
    PHASE1_EXPANSION_CODES,
    SCOPE_REGISTRY,
)

ALL_ISI_COUNTRIES: frozenset[str] = EU27_CODES | PHASE1_EXPANSION_CODES

# Countries considered "major" for partner-count validation
MAJOR_REPORTER_ISO2: frozenset[str] = frozenset({
    "US", "CN", "JP", "DE", "GB", "FR", "IN", "KR", "AU", "IT",
    "NL", "ES", "SE", "NO", "BE", "PL",
})
