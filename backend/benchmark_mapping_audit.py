"""
backend.benchmark_mapping_audit — Benchmark Mapping Validity Assessment

SECTION 2 of Final Hardening Pass.

Problem addressed:
    Benchmark alignment exists, but the mapping between ISI variables and
    external variables is not formally justified. Without mapping audit,
    "alignment" could be meaningless — comparing apples to oranges and
    calling it validation.

For EACH benchmark, this module documents:
    - ISI variable definition (what ISI actually measures)
    - External variable definition (what the benchmark measures)
    - Transformation applied (normalization, aggregation)
    - Unit/scale differences
    - Time alignment (lags, reference periods)
    - Aggregation differences (bilateral vs aggregate, HHI vs raw)
    - Known distortions (offshore centers, transit countries, etc.)
    - Expected failure modes (where the mapping breaks)

Design contract:
    - Every benchmark has a FORMAL mapping validation status.
    - VALID: mapping is methodologically defensible.
    - WEAK_MAPPING: mapping exists but has known structural issues.
    - INVALID_MAPPING: mapping is structurally unsound — comparison
      is misleading. Alignment results MUST be downgraded.
    - Mapping audit results are integrated into external_validation.py
      and invariants.py.

Honesty note:
    A high Spearman correlation between ISI and an external benchmark
    means NOTHING if the mapping between variables is invalid.
    This module prevents the system from claiming "alignment" when
    the comparison itself is structurally unsound.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# MAPPING VALIDITY CLASSES
# ═══════════════════════════════════════════════════════════════════════════

class MappingValidityClass:
    """Classification of benchmark-to-ISI mapping quality.

    VALID_MAPPING:    Constructs overlap substantively. Transformation
                      is documented and methodologically defensible.
                      Alignment results can be interpreted at face value.

    WEAK_MAPPING:     Constructs partially overlap but with known
                      structural differences. Alignment results should
                      be interpreted with documented caveats.

    INVALID_MAPPING:  Constructs differ fundamentally. Any alignment
                      metric would be misleading. Alignment results
                      MUST be downgraded to STRUCTURALLY_INCOMPARABLE.
    """
    VALID_MAPPING = "VALID_MAPPING"
    WEAK_MAPPING = "WEAK_MAPPING"
    INVALID_MAPPING = "INVALID_MAPPING"


VALID_MAPPING_CLASSES = frozenset({
    MappingValidityClass.VALID_MAPPING,
    MappingValidityClass.WEAK_MAPPING,
    MappingValidityClass.INVALID_MAPPING,
})


# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARK MAPPING AUDIT REGISTRY
# ═══════════════════════════════════════════════════════════════════════════
# Each entry documents the FULL mapping between an ISI axis variable
# and an external benchmark variable.

BENCHMARK_MAPPING_AUDIT: dict[str, dict[str, Any]] = {

    # ── Axis 1: Financial — BIS CBS ──
    "EXT_BIS_CBS": {
        "benchmark_id": "EXT_BIS_CBS",
        "isi_variable": {
            "name": "Financial import concentration (Axis 1)",
            "definition": (
                "HHI of bilateral banking claims from BIS LBS (locational "
                "basis) combined with IMF CPIS portfolio investment positions. "
                "Measures how concentrated a country's financial exposure is "
                "across counterparty countries."
            ),
            "unit": "HHI index [0, 1] normalized",
            "aggregation": "Bilateral → HHI per reporting country",
            "source": "BIS LBS + IMF CPIS",
        },
        "external_variable": {
            "name": "BIS Consolidated Banking Statistics (Ultimate Risk)",
            "definition": (
                "Bilateral banking claims reallocated to ultimate risk basis. "
                "Unlike LBS (locational), CBS attributes claims to the country "
                "where the actual credit risk resides."
            ),
            "unit": "USD millions, bilateral",
            "aggregation": "Bilateral claims by reporting country",
            "source": "BIS CBS",
        },
        "transformation": {
            "isi_to_comparable": (
                "ISI Axis 1 is HHI-normalized. CBS data must be converted "
                "to HHI-equivalent concentration measure, then normalized "
                "to [0,1] for rank comparison."
            ),
            "normalization": "Min-max within EU27 for both series",
        },
        "unit_scale_differences": (
            "ISI: dimensionless HHI ratio [0,1]. "
            "CBS: USD millions, must be converted to HHI."
        ),
        "time_alignment": {
            "isi_reference": "Annual (latest available year)",
            "external_reference": "Quarterly (Q4 or annual aggregate)",
            "lag": "0-1 quarter typical",
            "known_issues": (
                "LBS and CBS reporting cycles differ. Some countries "
                "report CBS with 6+ month lag."
            ),
        },
        "aggregation_differences": (
            "LBS: locational basis (where claim is booked). "
            "CBS: ultimate risk basis (where risk resides). "
            "For countries with offshore financial centers (IE, LU, NL), "
            "this creates substantial divergence."
        ),
        "known_distortions": [
            "Offshore financial centers (IE, LU, NL, CY) inflate LBS relative to CBS",
            "CBS does not include portfolio investment (CPIS component of ISI Axis 1)",
            "Small reporting countries may have confidential entries in CBS",
        ],
        "expected_failure_modes": [
            "IE/LU/NL will show large LBS-CBS divergence (expected, not error)",
            "Countries not in BIS reporting set will have NO_DATA",
            "CPIS component has no CBS equivalent — partial mapping only",
        ],
        "mapping_validity": MappingValidityClass.WEAK_MAPPING,
        "mapping_justification": (
            "WEAK: LBS and CBS share underlying data but differ on allocation "
            "basis. Portfolio investment (CPIS) has no CBS equivalent. "
            "Rank correlation is meaningful but level comparison is not."
        ),
    },

    # ── Axis 2: Energy — IEA ──
    "EXT_IEA_ENERGY": {
        "benchmark_id": "EXT_IEA_ENERGY",
        "isi_variable": {
            "name": "Energy import concentration (Axis 2)",
            "definition": (
                "HHI of bilateral energy-related trade flows from Comtrade. "
                "HS codes for energy products (oil, gas, coal, nuclear fuel). "
                "Measures how concentrated energy imports are by partner country."
            ),
            "unit": "HHI index [0, 1] normalized",
            "aggregation": "Bilateral trade → HHI per importing country",
            "source": "UN Comtrade",
        },
        "external_variable": {
            "name": "IEA Energy Security Indicators",
            "definition": (
                "IEA energy import dependency metrics: net import ratios, "
                "supplier diversification, energy mix diversity. "
                "Composite indicator of energy security."
            ),
            "unit": "Composite index (various)",
            "aggregation": "National-level aggregate indicators",
            "source": "IEA World Energy Outlook / Energy Security",
        },
        "transformation": {
            "isi_to_comparable": (
                "ISI uses TRADE-based concentration (who supplies energy imports). "
                "IEA uses PHYSICAL energy flow data including domestic production. "
                "Transformation: normalize both to [0,1], compare ranks."
            ),
            "normalization": "Min-max within EU27 for both series",
        },
        "unit_scale_differences": (
            "ISI: trade-value HHI (USD-weighted). "
            "IEA: physical energy units (toe, TWh). "
            "A country importing expensive LNG vs cheap pipeline gas "
            "looks different in value vs physical terms."
        ),
        "time_alignment": {
            "isi_reference": "Annual (Comtrade reporting year)",
            "external_reference": "Annual (IEA reporting year, ~1 year lag)",
            "lag": "~1 year",
            "known_issues": (
                "IEA data lags Comtrade by approximately 1 year. "
                "Energy market shocks create temporal misalignment."
            ),
        },
        "aggregation_differences": (
            "ISI: BILATERAL trade (from whom). "
            "IEA: NATIONAL aggregate (total import dependency, not by partner). "
            "ISI measures PARTNER concentration. IEA measures TOTAL dependency."
        ),
        "known_distortions": [
            "Transit countries (NL, BE) show high trade-based imports but low IEA dependency",
            "Countries with domestic production (NL gas, PL coal) diverge on dependency measures",
            "LNG vs pipeline gas creates value-physical divergence",
        ],
        "expected_failure_modes": [
            "Transit hub countries will diverge (expected, not error)",
            "Domestic producers will show low IEA but high ISI if they still import",
            "Energy mix differences make aggregate comparison noisy",
        ],
        "mapping_validity": MappingValidityClass.WEAK_MAPPING,
        "mapping_justification": (
            "WEAK: ISI measures PARTNER concentration (who supplies). "
            "IEA measures TOTAL dependency (how much is imported). "
            "Related but different constructs. Rank correlation is "
            "meaningful as a broad directional check. Level comparison "
            "is invalid."
        ),
    },

    # ── Axis 2: Energy — Comtrade cross-validation ──
    "EXT_COMTRADE_XVAL": {
        "benchmark_id": "EXT_COMTRADE_XVAL",
        "isi_variable": {
            "name": "Energy import concentration (Axis 2)",
            "definition": "HHI of bilateral energy trade from Comtrade.",
            "unit": "HHI index [0, 1]",
            "aggregation": "Bilateral → HHI",
            "source": "UN Comtrade (mirror check)",
        },
        "external_variable": {
            "name": "Comtrade Mirror Statistics (reporter vs partner reported)",
            "definition": (
                "Cross-validation of reported imports against partner-reported "
                "exports. Tests whether bilateral flows are consistently "
                "reported from both sides."
            ),
            "unit": "USD thousands, bilateral",
            "aggregation": "Bilateral trade flows",
            "source": "UN Comtrade (partner-reported mirror)",
        },
        "transformation": {
            "isi_to_comparable": (
                "Compare reporter-reported import HHI with partner-reported "
                "export HHI. Both use same HS codes and country universe."
            ),
            "normalization": "Same methodology applied to both sides",
        },
        "unit_scale_differences": "None — same source, same units.",
        "time_alignment": {
            "isi_reference": "Annual",
            "external_reference": "Annual (same year)",
            "lag": "None (same data vintage)",
            "known_issues": (
                "Some countries report with delay. Mirror data may be "
                "from a different vintage."
            ),
        },
        "aggregation_differences": (
            "Minimal — same bilateral structure. Differences arise from "
            "CIF vs FOB valuation (imports CIF, exports FOB) and "
            "reporting coverage differences."
        ),
        "known_distortions": [
            "CIF/FOB gap (imports include transport costs, exports do not)",
            "Confidential trade flows are suppressed differently by reporters",
            "Re-exports create mirror asymmetries (NL, BE, DE hub effects)",
        ],
        "expected_failure_modes": [
            "Hub economies will show mirror asymmetries (expected)",
            "Confidential energy trade will cause systematic bias",
        ],
        "mapping_validity": MappingValidityClass.VALID_MAPPING,
        "mapping_justification": (
            "VALID: Same source, same methodology, same units. "
            "Mirror comparison is the gold standard for Comtrade "
            "data quality. CIF/FOB gap is systematic and well-understood."
        ),
    },

    # ── Axis 4: Defense — SIPRI MILEX ──
    "EXT_SIPRI_MILEX": {
        "benchmark_id": "EXT_SIPRI_MILEX",
        "isi_variable": {
            "name": "Defense import concentration (Axis 4)",
            "definition": (
                "HHI of bilateral arms transfer flows from SIPRI Arms "
                "Transfer Database. Trend Indicator Values (TIV), not "
                "actual prices."
            ),
            "unit": "HHI index [0, 1] based on TIV",
            "aggregation": "Bilateral TIV → HHI per importing country",
            "source": "SIPRI Arms Transfers Database",
        },
        "external_variable": {
            "name": "SIPRI Military Expenditure Database",
            "definition": (
                "Total national military expenditure. Includes personnel, "
                "operations, procurement, R&D. Broader than arms transfers."
            ),
            "unit": "USD millions (constant prices)",
            "aggregation": "National aggregate",
            "source": "SIPRI MILEX Database",
        },
        "transformation": {
            "isi_to_comparable": (
                "ISI uses ARMS TRANSFER concentration (from whom). "
                "MILEX is TOTAL spending (how much). Very different constructs. "
                "Structural consistency check: high MILEX + low ISI suggests "
                "domestic arms production (producer inversion)."
            ),
            "normalization": "Normalize MILEX to [0,1] within EU27, compare directionally",
        },
        "unit_scale_differences": (
            "ISI: TIV-based HHI (dimensionless). "
            "MILEX: USD millions. Completely different scales and units."
        ),
        "time_alignment": {
            "isi_reference": "Annual (SIPRI latest available, ~2 year lag for TIV)",
            "external_reference": "Annual (SIPRI latest available, ~1 year lag for MILEX)",
            "lag": "~1 year between MILEX and TIV reporting",
            "known_issues": "TIV covers multi-year delivery streams, not annual procurement.",
        },
        "aggregation_differences": (
            "ISI: BILATERAL arms transfers (from whom). "
            "MILEX: NATIONAL total spending (how much on military overall). "
            "A country can have high MILEX but low arms import concentration "
            "if it produces arms domestically."
        ),
        "known_distortions": [
            "Major arms producers (FR, DE, IT, SE) have high MILEX but low import concentration",
            "TIV is a volume indicator, not actual prices — value comparisons are invalid",
            "Multi-year deliveries span reporting periods, creating temporal noise",
        ],
        "expected_failure_modes": [
            "Arms-producing countries will show MILEX-ISI divergence (expected, confirms producer inversion)",
            "Small countries with one-off large orders will appear as outliers",
        ],
        "mapping_validity": MappingValidityClass.WEAK_MAPPING,
        "mapping_justification": (
            "WEAK: Structural consistency check (high MILEX + low ISI = producer), "
            "not rank correlation. The mapping is useful for CONFIRMING "
            "producer inversions but NOT for general alignment assessment."
        ),
    },

    # ── Axis 5: Critical Inputs — EU CRM ──
    "EXT_EU_CRM": {
        "benchmark_id": "EXT_EU_CRM",
        "isi_variable": {
            "name": "Critical inputs import concentration (Axis 5)",
            "definition": (
                "HHI of bilateral trade in critical raw materials "
                "(HS codes for rare earths, lithium, cobalt, etc.). "
                "Measures supply concentration by partner country."
            ),
            "unit": "HHI index [0, 1]",
            "aggregation": "Bilateral trade → HHI per importing country",
            "source": "UN Comtrade",
        },
        "external_variable": {
            "name": "EU Critical Raw Materials Assessment",
            "definition": (
                "EU supply risk assessment for critical raw materials. "
                "Considers supply concentration, substitutability, "
                "recycling rates, and governance of producing countries."
            ),
            "unit": "Supply risk index (composite)",
            "aggregation": "Material-level, aggregated to country level",
            "source": "European Commission (CRM Assessment)",
        },
        "transformation": {
            "isi_to_comparable": (
                "ISI: country-level import HHI across all CRM categories. "
                "EU CRM: material-level supply risk, must aggregate to "
                "country import exposure. Different aggregation unit."
            ),
            "normalization": "Both normalized to [0,1], compare ranks",
        },
        "unit_scale_differences": (
            "ISI: trade-value HHI across HS codes. "
            "EU CRM: multi-dimensional supply risk index including non-trade factors."
        ),
        "time_alignment": {
            "isi_reference": "Annual (Comtrade)",
            "external_reference": "Irregular (EU CRM assessments every ~3 years)",
            "lag": "1-3 years (CRM assessment cycle)",
            "known_issues": "EU CRM assessment is not annual — temporal alignment is poor.",
        },
        "aggregation_differences": (
            "ISI: PARTNER concentration (from whom). "
            "EU CRM: MATERIAL supply risk (which materials are risky). "
            "A country importing CRM from a single supplier (high ISI) may "
            "import non-critical materials (low EU CRM risk)."
        ),
        "known_distortions": [
            "EU CRM covers a fixed list of materials; ISI HS codes may not perfectly match",
            "Recycling and substitution reduce EU CRM risk but not ISI import concentration",
            "Country-level CRM exposure requires complex aggregation from material-level data",
        ],
        "expected_failure_modes": [
            "Countries with high recycling rates will diverge (ISI still shows import dependency)",
            "Material-country aggregation mismatch will add noise",
        ],
        "mapping_validity": MappingValidityClass.WEAK_MAPPING,
        "mapping_justification": (
            "WEAK: ISI measures PARTNER concentration for CRM imports. "
            "EU CRM measures MATERIAL supply risk. Different aggregation "
            "unit (country-partner vs material). Rank correlation tests "
            "broad directional agreement only."
        ),
    },

    # ── Axis 6: Logistics — UNCTAD LSCI ──
    "EXT_UNCTAD_LSCI": {
        "benchmark_id": "EXT_UNCTAD_LSCI",
        "isi_variable": {
            "name": "Logistics concentration (Axis 6)",
            "definition": (
                "For EU countries: Eurostat bilateral logistics data "
                "(freight throughput, modal shares). "
                "For non-EU: Comtrade bilateral trade as PROXY for logistics."
            ),
            "unit": "HHI-like index [0, 1] normalized",
            "aggregation": "Bilateral → concentration per country",
            "source": "Eurostat (EU) / Comtrade proxy (non-EU)",
        },
        "external_variable": {
            "name": "UNCTAD Liner Shipping Connectivity Index",
            "definition": (
                "Measures a country's integration into global liner "
                "shipping networks. Based on ship deployments, services, "
                "and capacity. Higher = more connected."
            ),
            "unit": "Index (dimensionless, max ~200)",
            "aggregation": "National aggregate",
            "source": "UNCTAD",
        },
        "transformation": {
            "isi_to_comparable": (
                "ISI: logistics CONCENTRATION (how dependent on few partners). "
                "LSCI: shipping CONNECTIVITY (how well connected). "
                "Inverse relationship expected: high connectivity → low concentration "
                "(more options). Rank correlation should be NEGATIVE."
            ),
            "normalization": "Both normalized to [0,1] within EU27, expect negative correlation",
        },
        "unit_scale_differences": (
            "ISI: bilateral concentration HHI [0,1]. "
            "LSCI: connectivity index [0, ~200]. Different scales and direction."
        ),
        "time_alignment": {
            "isi_reference": "Annual",
            "external_reference": "Quarterly (UNCTAD), annualized",
            "lag": "Minimal (<1 quarter)",
            "known_issues": "LSCI covers maritime only; ISI includes all transport modes.",
        },
        "aggregation_differences": (
            "ISI: BILATERAL logistics concentration. "
            "LSCI: NATIONAL aggregate connectivity. Different dimensions. "
            "A country can be well-connected (high LSCI) but concentrated "
            "on few logistics partners (high ISI)."
        ),
        "known_distortions": [
            "LSCI covers maritime only — landlocked countries have low LSCI by definition",
            "Comtrade proxy for non-EU countries measures trade, not logistics",
            "Hub ports (NL, BE, DE) inflate LSCI relative to actual logistics dependency",
        ],
        "expected_failure_modes": [
            "Landlocked countries (AT, CZ, SK, HU, LU) will show structural divergence",
            "Non-EU countries using Comtrade proxy will diverge from LSCI (construct substitution)",
        ],
        "mapping_validity": MappingValidityClass.WEAK_MAPPING,
        "mapping_justification": (
            "WEAK: ISI measures logistics CONCENTRATION (dependency). "
            "LSCI measures shipping CONNECTIVITY (opportunity). "
            "Expected inverse relationship but different constructs. "
            "Landlocked EU members will fail the mapping structurally."
        ),
    },

    # ── Axis 6: Logistics — World Bank LPI ──
    "EXT_WB_LPI": {
        "benchmark_id": "EXT_WB_LPI",
        "isi_variable": {
            "name": "Logistics concentration (Axis 6)",
            "definition": "Same as LSCI entry above.",
            "unit": "HHI-like index [0, 1]",
            "aggregation": "Bilateral → concentration per country",
            "source": "Eurostat (EU) / Comtrade proxy (non-EU)",
        },
        "external_variable": {
            "name": "World Bank Logistics Performance Index",
            "definition": (
                "Composite of customs efficiency, infrastructure quality, "
                "logistics competence, tracking ability, timeliness, and "
                "international shipment ease. Survey-based."
            ),
            "unit": "Index [1, 5]",
            "aggregation": "National aggregate (survey-based)",
            "source": "World Bank LPI (biennial)",
        },
        "transformation": {
            "isi_to_comparable": (
                "ISI: logistics CONCENTRATION (import dependency). "
                "LPI: logistics PERFORMANCE (how good is logistics infrastructure). "
                "Expected inverse: good performance → lower concentration "
                "(more options). Rank correlation should be NEGATIVE."
            ),
            "normalization": "Both normalized to [0,1], expect negative correlation",
        },
        "unit_scale_differences": (
            "ISI: bilateral concentration [0,1]. LPI: survey-based [1,5]."
        ),
        "time_alignment": {
            "isi_reference": "Annual",
            "external_reference": "Biennial (every 2 years)",
            "lag": "0-2 years (biennial cycle)",
            "known_issues": "LPI is biennial — temporal alignment is coarse.",
        },
        "aggregation_differences": (
            "ISI: BILATERAL concentration. LPI: NATIONAL performance (survey). "
            "A country can have excellent logistics (high LPI) but still "
            "be dependent on few logistics partners (high ISI)."
        ),
        "known_distortions": [
            "LPI is survey-based — subjective assessments may lag reality",
            "LPI covers all logistics, ISI covers international trade logistics only",
            "Hub economies score high on LPI but may show concentration in ISI",
        ],
        "expected_failure_modes": [
            "Biennial gap causes temporal mismatch",
            "Hub economies diverge on concentration vs performance",
        ],
        "mapping_validity": MappingValidityClass.WEAK_MAPPING,
        "mapping_justification": (
            "WEAK: ISI measures logistics DEPENDENCY (concentration). "
            "LPI measures logistics CAPABILITY (performance). "
            "Different constructs but expected inverse relationship. "
            "Biennial timing makes precise alignment impossible."
        ),
    },

    # ── Axis 6: Logistics — Eurostat Transport ──
    "EXT_EUROSTAT_TRANSPORT": {
        "benchmark_id": "EXT_EUROSTAT_TRANSPORT",
        "isi_variable": {
            "name": "Logistics concentration (Axis 6)",
            "definition": "Eurostat bilateral logistics data for EU members.",
            "unit": "Composite logistics concentration [0, 1]",
            "aggregation": "Bilateral freight flows → concentration",
            "source": "Eurostat",
        },
        "external_variable": {
            "name": "Eurostat Transport Statistics (Goods Transport)",
            "definition": (
                "Eurostat modal transport volumes: road, rail, maritime, "
                "inland waterway freight volumes by partner country."
            ),
            "unit": "Thousand tonnes, tonne-km",
            "aggregation": "Bilateral by mode and partner",
            "source": "Eurostat Transport Statistics",
        },
        "transformation": {
            "isi_to_comparable": (
                "Same source (Eurostat), similar methodology. "
                "ISI aggregates across modes to compute concentration. "
                "Validation: compare ISI logistics score against modal "
                "breakdowns to check consistency."
            ),
            "normalization": "Same normalization methodology",
        },
        "unit_scale_differences": "Minimal — same source family.",
        "time_alignment": {
            "isi_reference": "Annual",
            "external_reference": "Annual (same Eurostat vintage)",
            "lag": "None",
            "known_issues": "EU-only coverage; non-EU countries not available.",
        },
        "aggregation_differences": (
            "ISI: composite across modes. Eurostat: per-mode separate. "
            "Aggregation methodology may differ."
        ),
        "known_distortions": [
            "Road transport dominance may obscure maritime concentration",
            "Transit country effects (NL, BE) inflate volumes",
        ],
        "expected_failure_modes": [
            "Non-EU countries: NO_DATA (EU-only source)",
            "Aggregation methodology differences for modal weighting",
        ],
        "mapping_validity": MappingValidityClass.VALID_MAPPING,
        "mapping_justification": (
            "VALID: Same source (Eurostat), same bilateral structure, "
            "compatible units. Modal aggregation may differ but "
            "structural consistency check is methodologically sound."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def validate_benchmark_mapping(benchmark_id: str) -> dict[str, Any]:
    """Validate the mapping quality for a specific benchmark.

    Args:
        benchmark_id: The benchmark ID to validate.

    Returns:
        Mapping validity assessment with class, justification, and issues.
    """
    audit = BENCHMARK_MAPPING_AUDIT.get(benchmark_id)
    if audit is None:
        return {
            "benchmark_id": benchmark_id,
            "mapping_validity": MappingValidityClass.INVALID_MAPPING,
            "mapping_audited": False,
            "justification": (
                f"No mapping audit entry for benchmark '{benchmark_id}'. "
                f"Alignment results for unaudited benchmarks MUST be "
                f"treated as structurally incomparable."
            ),
            "known_distortions": [],
            "expected_failure_modes": [],
        }

    return {
        "benchmark_id": benchmark_id,
        "mapping_validity": audit["mapping_validity"],
        "mapping_audited": True,
        "justification": audit["mapping_justification"],
        "isi_variable": audit["isi_variable"]["name"],
        "external_variable": audit["external_variable"]["name"],
        "unit_scale_differences": audit["unit_scale_differences"],
        "time_alignment": audit["time_alignment"],
        "aggregation_differences": audit["aggregation_differences"],
        "known_distortions": audit["known_distortions"],
        "expected_failure_modes": audit["expected_failure_modes"],
    }


def validate_all_mappings() -> dict[str, Any]:
    """Validate all benchmark mappings and produce a summary.

    Returns:
        Summary of mapping validity across all benchmarks.
    """
    results: dict[str, dict[str, Any]] = {}
    for benchmark_id in BENCHMARK_MAPPING_AUDIT:
        results[benchmark_id] = validate_benchmark_mapping(benchmark_id)

    n_valid = sum(
        1 for r in results.values()
        if r["mapping_validity"] == MappingValidityClass.VALID_MAPPING
    )
    n_weak = sum(
        1 for r in results.values()
        if r["mapping_validity"] == MappingValidityClass.WEAK_MAPPING
    )
    n_invalid = sum(
        1 for r in results.values()
        if r["mapping_validity"] == MappingValidityClass.INVALID_MAPPING
    )

    return {
        "total_audited": len(results),
        "n_valid": n_valid,
        "n_weak": n_weak,
        "n_invalid": n_invalid,
        "per_benchmark": results,
        "honesty_note": (
            f"Of {len(results)} audited benchmark mappings, "
            f"{n_valid} are VALID, {n_weak} are WEAK, "
            f"{n_invalid} are INVALID. "
            f"WEAK mappings produce alignment results that should be "
            f"interpreted with documented caveats. "
            f"INVALID mappings should produce STRUCTURALLY_INCOMPARABLE "
            f"alignment class, regardless of metric value."
        ),
    }


def should_downgrade_alignment(
    benchmark_id: str,
    raw_alignment_class: str,
) -> dict[str, Any]:
    """Determine if alignment class should be downgraded due to mapping issues.

    Args:
        benchmark_id: The benchmark being compared.
        raw_alignment_class: The alignment class from metric computation
            (before mapping audit adjustment).

    Returns:
        Adjusted alignment assessment.
    """
    mapping = validate_benchmark_mapping(benchmark_id)
    validity = mapping["mapping_validity"]

    if validity == MappingValidityClass.VALID_MAPPING:
        return {
            "adjusted_alignment_class": raw_alignment_class,
            "downgraded": False,
            "mapping_validity": validity,
            "adjustment_reason": None,
        }

    if validity == MappingValidityClass.INVALID_MAPPING:
        return {
            "adjusted_alignment_class": "STRUCTURALLY_INCOMPARABLE",
            "downgraded": True,
            "mapping_validity": validity,
            "adjustment_reason": (
                f"Mapping for {benchmark_id} is INVALID. "
                f"Alignment metric is meaningless regardless of value. "
                f"Raw class was '{raw_alignment_class}' but forced to "
                f"STRUCTURALLY_INCOMPARABLE."
            ),
        }

    # WEAK_MAPPING: downgrade STRONGLY_ALIGNED → WEAKLY_ALIGNED
    if validity == MappingValidityClass.WEAK_MAPPING:
        if raw_alignment_class == "STRONGLY_ALIGNED":
            return {
                "adjusted_alignment_class": "WEAKLY_ALIGNED",
                "downgraded": True,
                "mapping_validity": validity,
                "adjustment_reason": (
                    f"Mapping for {benchmark_id} is WEAK. "
                    f"STRONGLY_ALIGNED downgraded to WEAKLY_ALIGNED "
                    f"because mapping limitations prevent strong claims."
                ),
            }
        return {
            "adjusted_alignment_class": raw_alignment_class,
            "downgraded": False,
            "mapping_validity": validity,
            "adjustment_reason": (
                f"Mapping for {benchmark_id} is WEAK. "
                f"Alignment class '{raw_alignment_class}' not further "
                f"downgraded but should be interpreted with caveats."
            ),
        }

    # Fallback
    return {
        "adjusted_alignment_class": raw_alignment_class,
        "downgraded": False,
        "mapping_validity": "UNKNOWN",
        "adjustment_reason": None,
    }


def get_mapping_audit_registry() -> dict[str, dict[str, Any]]:
    """Return the full mapping audit registry."""
    return dict(BENCHMARK_MAPPING_AUDIT)


def get_mapping_audit(benchmark_id: str) -> dict[str, Any] | None:
    """Return the mapping audit entry for a specific benchmark."""
    return BENCHMARK_MAPPING_AUDIT.get(benchmark_id)
