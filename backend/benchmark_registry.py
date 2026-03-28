"""
backend.benchmark_registry — External Benchmark Definitions

Formal registry of external datasets against which ISI outputs can be
validated. Each benchmark specifies:
    - What it measures (construct)
    - Which ISI axes it maps to
    - What comparison is meaningful (rank correlation, structural check, etc.)
    - Expected alignment range if construct is genuinely the same
    - What divergence MEANS (construct difference vs measurement error)

Design contract:
    - Every benchmark has an explicit CONSTRUCT description.
    - No benchmark is assumed to measure exactly the same thing as ISI.
    - Alignment expectations include BOTH direction and magnitude bounds.
    - STRUCTURAL_INCOMPARABILITY is a first-class outcome, not a fallback.
    - Missing data produces NO_DATA, never silent omission.

Honesty note:
    External benchmarks validate CONSTRUCT OVERLAP, not "correctness."
    ISI measures bilateral import concentration (HHI). External datasets
    measure related but different things (energy security, supply risk,
    financial exposure). Alignment confirms that ISI captures PART of what
    the external dataset measures. Divergence may mean ISI is wrong, OR
    that the constructs genuinely differ.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# ALIGNMENT CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class AlignmentClass:
    """Classification of ISI-benchmark alignment.

    NOT a quality judgment — alignment depends on construct overlap.
    """
    STRONGLY_ALIGNED = "STRONGLY_ALIGNED"
    WEAKLY_ALIGNED = "WEAKLY_ALIGNED"
    DIVERGENT = "DIVERGENT"
    STRUCTURALLY_INCOMPARABLE = "STRUCTURALLY_INCOMPARABLE"
    NO_DATA = "NO_DATA"


VALID_ALIGNMENT_CLASSES = frozenset({
    AlignmentClass.STRONGLY_ALIGNED,
    AlignmentClass.WEAKLY_ALIGNED,
    AlignmentClass.DIVERGENT,
    AlignmentClass.STRUCTURALLY_INCOMPARABLE,
    AlignmentClass.NO_DATA,
})


class ComparisonType:
    """Type of comparison between ISI and external benchmark."""
    RANK_CORRELATION = "RANK_CORRELATION"
    STRUCTURAL_CONSISTENCY = "STRUCTURAL_CONSISTENCY"
    DIRECTIONAL_AGREEMENT = "DIRECTIONAL_AGREEMENT"
    LEVEL_COMPARISON = "LEVEL_COMPARISON"


VALID_COMPARISON_TYPES = frozenset({
    ComparisonType.RANK_CORRELATION,
    ComparisonType.STRUCTURAL_CONSISTENCY,
    ComparisonType.DIRECTIONAL_AGREEMENT,
    ComparisonType.LEVEL_COMPARISON,
})


class IntegrationStatus:
    """Status of benchmark data integration."""
    INTEGRATED = "INTEGRATED"
    STRUCTURALLY_DEFINED = "STRUCTURALLY_DEFINED"
    NOT_INTEGRATED = "NOT_INTEGRATED"


VALID_INTEGRATION_STATUSES = frozenset({
    IntegrationStatus.INTEGRATED,
    IntegrationStatus.STRUCTURALLY_DEFINED,
    IntegrationStatus.NOT_INTEGRATED,
})


class BenchmarkAuthority:
    """Authority hierarchy for benchmarks.

    Not all benchmarks are equal. Some are close to ground truth
    (structural constraints), some are high-confidence empirical
    measures, and some are supporting/directional only.

    This hierarchy determines:
    - How much weight a benchmark gets in alignment scoring
    - What happens when benchmarks at different tiers contradict
    """
    STRUCTURAL = "STRUCTURAL"           # Hard constraints, closest to ground truth
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"  # Strong empirical measures
    SUPPORTING = "SUPPORTING"           # Directional, partial overlap


VALID_AUTHORITY_LEVELS = frozenset({
    BenchmarkAuthority.STRUCTURAL,
    BenchmarkAuthority.HIGH_CONFIDENCE,
    BenchmarkAuthority.SUPPORTING,
})

# Weight each authority tier contributes to weighted alignment score
AUTHORITY_WEIGHTS: dict[str, float] = {
    BenchmarkAuthority.STRUCTURAL: 1.0,
    BenchmarkAuthority.HIGH_CONFIDENCE: 0.7,
    BenchmarkAuthority.SUPPORTING: 0.4,
}


# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARK DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

def _benchmark_entry(
    *,
    benchmark_id: str,
    name: str,
    relevant_axes: list[int],
    comparison_type: str,
    status: str,
    construct_description: str,
    construct_overlap_with_isi: str,
    construct_divergence_from_isi: str,
    data_source: str,
    geographic_coverage: str,
    alignment_thresholds: dict[str, float],
    divergence_interpretation: str,
    integration_requirements: list[str],
    authority_level: str = BenchmarkAuthority.SUPPORTING,
    authority_justification: str = "",
) -> dict[str, Any]:
    """Create a validated benchmark entry."""
    assert comparison_type in VALID_COMPARISON_TYPES, (
        f"Invalid comparison_type '{comparison_type}' for {benchmark_id}"
    )
    assert status in VALID_INTEGRATION_STATUSES, (
        f"Invalid status '{status}' for {benchmark_id}"
    )
    assert authority_level in VALID_AUTHORITY_LEVELS, (
        f"Invalid authority_level '{authority_level}' for {benchmark_id}"
    )
    assert len(relevant_axes) > 0, (
        f"Benchmark {benchmark_id} must map to at least one ISI axis"
    )
    for ax in relevant_axes:
        assert 1 <= ax <= 6, f"Invalid axis {ax} for {benchmark_id}"
    # Alignment thresholds must include strong and weak bounds
    assert "strong_alignment_min" in alignment_thresholds, (
        f"Missing strong_alignment_min for {benchmark_id}"
    )
    assert "weak_alignment_min" in alignment_thresholds, (
        f"Missing weak_alignment_min for {benchmark_id}"
    )
    return {
        "benchmark_id": benchmark_id,
        "name": name,
        "relevant_axes": relevant_axes,
        "comparison_type": comparison_type,
        "status": status,
        "construct_description": construct_description,
        "construct_overlap_with_isi": construct_overlap_with_isi,
        "construct_divergence_from_isi": construct_divergence_from_isi,
        "data_source": data_source,
        "geographic_coverage": geographic_coverage,
        "alignment_thresholds": alignment_thresholds,
        "divergence_interpretation": divergence_interpretation,
        "integration_requirements": integration_requirements,
        "authority_level": authority_level,
        "authority_justification": authority_justification,
    }


# ── Axis 1: Financial ──

BENCHMARK_BIS_CBS = _benchmark_entry(
    benchmark_id="EXT_BIS_CBS",
    name="BIS Consolidated Banking Statistics (Ultimate Risk)",
    relevant_axes=[1],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "Bilateral banking claims on an ultimate risk basis. Unlike "
        "BIS LBS (locational, used by ISI), CBS allocates claims to "
        "the country of ultimate risk, not the booking location."
    ),
    construct_overlap_with_isi=(
        "Both measure cross-border banking concentration. CBS and LBS "
        "share the same underlying data for many reporting countries."
    ),
    construct_divergence_from_isi=(
        "CBS ultimate risk allocation differs from LBS locational basis. "
        "For countries with major offshore financial centers (IE, LU, NL), "
        "CBS vs LBS can diverge substantially. CBS also lacks the CPIS "
        "portfolio dimension that ISI Axis 1 includes."
    ),
    data_source="BIS Consolidated Banking Statistics",
    geographic_coverage="~30 BIS reporting countries as creditors",
    alignment_thresholds={
        "strong_alignment_min": 0.70,
        "weak_alignment_min": 0.40,
    },
    divergence_interpretation=(
        "Divergence between LBS-based ISI Axis 1 and CBS-based measure "
        "indicates that locational vs ultimate risk allocation matters "
        "for the country. This is a CONSTRUCT DIFFERENCE, not an error "
        "in either measure."
    ),
    integration_requirements=[
        "Access BIS CBS data (bilateral, ultimate risk basis)",
        "Compute HHI-equivalent from CBS bilateral claims",
        "Align country universe with ISI (ISO-2 codes)",
        "Compute Spearman rank correlation with ISI Axis 1",
    ],
    authority_level=BenchmarkAuthority.STRUCTURAL,
    authority_justification=(
        "BIS CBS uses the same underlying bilateral banking data as ISI "
        "Axis 1 (BIS LBS). Divergence signals locational vs ultimate risk "
        "allocation difference — a hard structural constraint."
    ),
)


# ── Axis 2: Energy ──

BENCHMARK_IEA_ENERGY = _benchmark_entry(
    benchmark_id="EXT_IEA_ENERGY",
    name="IEA Energy Security Indicators",
    relevant_axes=[2],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "IEA energy import dependency metrics including net import "
        "ratios, supplier diversification, and energy mix data "
        "covering oil, gas, coal, and electricity."
    ),
    construct_overlap_with_isi=(
        "Both measure energy import concentration. IEA covers the same "
        "HS commodity space (fossil fuels). For OECD countries, coverage "
        "overlaps substantially with Comtrade-based ISI Axis 2."
    ),
    construct_divergence_from_isi=(
        "IEA includes pipeline gas (often not in bilateral Comtrade for "
        "transit countries), nuclear fuel, and energy mix weighting. "
        "ISI uses pure trade-value HHI; IEA uses volume-weighted metrics. "
        "IEA also includes domestic production (relevant for energy "
        "independence but not for import concentration)."
    ),
    data_source="IEA Energy Security Indicators / World Energy Balances",
    geographic_coverage="OECD members + selected non-OECD",
    alignment_thresholds={
        "strong_alignment_min": 0.65,
        "weak_alignment_min": 0.35,
    },
    divergence_interpretation=(
        "Divergence most likely for energy transit countries (NL, BE) "
        "where re-exports inflate Comtrade bilateral flows, and for "
        "pipeline-dependent countries where bilateral gas flows are "
        "underreported in Comtrade."
    ),
    integration_requirements=[
        "Access IEA energy security indicators",
        "Extract bilateral energy import concentration data",
        "Map IEA country codes to ISI ISO-2",
        "Compute rank correlation with ISI Axis 2",
    ],
    authority_level=BenchmarkAuthority.HIGH_CONFIDENCE,
    authority_justification=(
        "IEA covers the same commodity space (fossil fuels) with "
        "authoritative source data. Pipeline gas coverage is the "
        "main difference — prevents STRUCTURAL classification."
    ),
)

BENCHMARK_EUROSTAT_ENERGY = _benchmark_entry(
    benchmark_id="EXT_EUROSTAT_ENERGY",
    name="Eurostat Energy Import Dependency",
    relevant_axes=[2],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "Eurostat energy import dependency rate: (imports - exports) / "
        "(gross available energy). Published annually for all EU-27."
    ),
    construct_overlap_with_isi=(
        "Measures the same underlying phenomenon (energy import reliance) "
        "for the same country set (EU-27). Coverage is nearly perfect."
    ),
    construct_divergence_from_isi=(
        "Eurostat uses a LEVEL metric (import dependency rate, 0-100%), "
        "while ISI uses CONCENTRATION (HHI of bilateral suppliers). "
        "A country can have high import dependency but low concentration "
        "(many diverse suppliers). These are RELATED but DISTINCT constructs."
    ),
    data_source="Eurostat (nrg_ind_id)",
    geographic_coverage="EU-27 (complete)",
    alignment_thresholds={
        "strong_alignment_min": 0.50,
        "weak_alignment_min": 0.25,
    },
    divergence_interpretation=(
        "Divergence is EXPECTED because dependency and concentration are "
        "different constructs. A country like DE may have high dependency "
        "but moderate concentration (many suppliers). Low alignment does "
        "NOT invalidate ISI — it confirms the construct measures something "
        "different from simple dependency."
    ),
    integration_requirements=[
        "Download Eurostat nrg_ind_id dataset",
        "Extract energy import dependency rate per EU-27 country",
        "Compute Spearman rank correlation with ISI Axis 2",
    ],
    authority_level=BenchmarkAuthority.SUPPORTING,
    authority_justification=(
        "Eurostat measures DEPENDENCY (level), not CONCENTRATION (HHI). "
        "Different construct — useful for directional validation only."
    ),
)


# ── Axis 3: Technology ──

BENCHMARK_WITS_TECH = _benchmark_entry(
    benchmark_id="EXT_WITS_TECH",
    name="World Bank WITS Technology Trade Concentration",
    relevant_axes=[3],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "World Bank WITS (World Integrated Trade Solution) provides "
        "bilateral semiconductor and electronics trade data from the "
        "same Comtrade source but with World Bank processing and "
        "mirror-trade adjustments."
    ),
    construct_overlap_with_isi=(
        "Same underlying data source (UN Comtrade) and same HS codes "
        "(8541, 8542). WITS processing may differ in gap-filling "
        "and mirror-trade reconciliation."
    ),
    construct_divergence_from_isi=(
        "WITS applies its own cleaning and gap-filling procedures. "
        "Differences indicate sensitivity to data processing choices, "
        "not to the underlying bilateral structure."
    ),
    data_source="World Bank WITS",
    geographic_coverage="Global (~200 countries)",
    alignment_thresholds={
        "strong_alignment_min": 0.80,
        "weak_alignment_min": 0.55,
    },
    divergence_interpretation=(
        "Divergence from WITS on the same HS codes indicates that "
        "ISI's data processing choices matter. This is a DATA QUALITY "
        "signal, not a construct difference."
    ),
    integration_requirements=[
        "Download WITS bilateral trade data for HS 8541/8542",
        "Compute HHI-equivalent from WITS data",
        "Compare with ISI Axis 3 for overlapping countries",
    ],
    authority_level=BenchmarkAuthority.STRUCTURAL,
    authority_justification=(
        "Same underlying data source (UN Comtrade), same HS codes. "
        "Divergence indicates data processing sensitivity — a hard "
        "data quality signal."
    ),
)


# ── Axis 4: Defense ──

BENCHMARK_SIPRI_MILEX = _benchmark_entry(
    benchmark_id="EXT_SIPRI_MILEX",
    name="SIPRI Military Expenditure Cross-Check",
    relevant_axes=[4],
    comparison_type=ComparisonType.STRUCTURAL_CONSISTENCY,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "SIPRI Military Expenditure Database. Countries with high MILEX "
        "relative to GDP are likely domestic arms producers. If they "
        "also show LOW import concentration on Axis 4, this is a "
        "producer inversion signal."
    ),
    construct_overlap_with_isi=(
        "SIPRI TIV (used by ISI Axis 4) measures arms TRANSFERS. "
        "SIPRI MILEX measures arms EXPENDITURE. High MILEX + low "
        "import TIV concentration = domestic production."
    ),
    construct_divergence_from_isi=(
        "MILEX includes personnel costs, maintenance, R&D — not just "
        "imports. A country can have high MILEX but low arms imports "
        "because it produces domestically. This divergence is "
        "EXPECTED and signals producer inversion."
    ),
    data_source="SIPRI Military Expenditure Database",
    geographic_coverage="~170 countries",
    alignment_thresholds={
        "strong_alignment_min": 0.0,  # Structural check, not correlation
        "weak_alignment_min": 0.0,
    },
    divergence_interpretation=(
        "High MILEX + low ISI Axis 4 = domestic arms production. "
        "These countries MUST be in PRODUCER_INVERSION_REGISTRY. "
        "If they are not, the registry is incomplete."
    ),
    integration_requirements=[
        "Download SIPRI MILEX data",
        "Compute MILEX/GDP ratio per country",
        "Identify countries with MILEX/GDP > 3% and ISI Axis 4 < 0.2",
        "Cross-check against PRODUCER_INVERSION_REGISTRY",
    ],
    authority_level=BenchmarkAuthority.STRUCTURAL,
    authority_justification=(
        "SIPRI MILEX provides a hard structural constraint: high "
        "military expenditure + low import concentration = domestic "
        "production. This directly validates producer inversion."
    ),
)

BENCHMARK_SIPRI_TIV_COMPARE = _benchmark_entry(
    benchmark_id="EXT_SIPRI_TIV_COMPARE",
    name="SIPRI TIV Cross-Validation (Alternate Window)",
    relevant_axes=[4],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "SIPRI TIV data for a different time window (e.g., 5-year vs "
        "ISI's reference window). Tests temporal stability of defense "
        "import concentration rankings."
    ),
    construct_overlap_with_isi=(
        "Same source (SIPRI TIV), same construct (arms import concentration). "
        "Only the time window differs."
    ),
    construct_divergence_from_isi=(
        "Arms deliveries are lumpy — large orders arrive in specific "
        "years. Different windows can produce very different HHI values "
        "for the same country. Low cross-window correlation indicates "
        "the defense axis is TEMPORALLY UNSTABLE."
    ),
    data_source="SIPRI Arms Transfers Database",
    geographic_coverage="All countries with major arms imports",
    alignment_thresholds={
        "strong_alignment_min": 0.60,
        "weak_alignment_min": 0.30,
    },
    divergence_interpretation=(
        "Low temporal correlation confirms that SIPRI TIV-based "
        "defense rankings are sensitive to delivery timing. This "
        "supports the low baseline confidence (0.55) for Axis 4."
    ),
    integration_requirements=[
        "Download SIPRI TIV for alternate time window",
        "Compute bilateral import HHI per country",
        "Compute Spearman rank correlation with ISI Axis 4",
    ],
    authority_level=BenchmarkAuthority.HIGH_CONFIDENCE,
    authority_justification=(
        "Same source (SIPRI TIV), same construct. Tests temporal "
        "stability — high confidence because construct identity is "
        "guaranteed."
    ),
)


# ── Axis 5: Critical Inputs ──

BENCHMARK_EU_CRM = _benchmark_entry(
    benchmark_id="EXT_EU_CRM",
    name="EU Critical Raw Materials Supply Studies",
    relevant_axes=[5],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "EU CRM Act supply concentration data — measures supply risk "
        "for critical raw materials by computing HHI of global supply "
        "sources for each CRM commodity."
    ),
    construct_overlap_with_isi=(
        "Both measure concentration of critical material supply. "
        "EU CRM uses supply-side HHI; ISI uses import-side HHI from "
        "Comtrade bilateral trade."
    ),
    construct_divergence_from_isi=(
        "EU CRM measures SUPPLY RISK (who produces the material globally), "
        "while ISI measures IMPORT CONCENTRATION (who each country buys from). "
        "These converge for countries that import from the global supply "
        "mix but diverge for countries with bilateral supply agreements "
        "or domestic extraction."
    ),
    data_source="European Commission CRM Act supply studies",
    geographic_coverage="EU-27 (primary), global supply chain",
    alignment_thresholds={
        "strong_alignment_min": 0.55,
        "weak_alignment_min": 0.30,
    },
    divergence_interpretation=(
        "Divergence indicates that a country's bilateral import mix "
        "differs from the global supply structure. This is a REAL "
        "difference in what is being measured — supply risk vs import "
        "concentration."
    ),
    integration_requirements=[
        "Download EU CRM bilateral supply data",
        "Map EU CRM country codes to ISI ISO-2",
        "Compute HHI-equivalent from CRM supply data",
        "Compute Spearman rank correlation with ISI Axis 5",
    ],
    authority_level=BenchmarkAuthority.HIGH_CONFIDENCE,
    authority_justification=(
        "EU CRM uses HHI-equivalent for critical materials — same "
        "concentration methodology. Supply-side vs import-side is a "
        "known construct difference, not a reliability issue."
    ),
)

BENCHMARK_USGS_MINERALS = _benchmark_entry(
    benchmark_id="EXT_USGS_MINERALS",
    name="USGS Mineral Commodity Summaries",
    relevant_axes=[5],
    comparison_type=ComparisonType.DIRECTIONAL_AGREEMENT,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "USGS annual mineral commodity summaries. Includes global "
        "production shares, import sources, and net import reliance "
        "for ~90 mineral commodities."
    ),
    construct_overlap_with_isi=(
        "USGS import sources for critical minerals overlap with "
        "ISI Axis 5 bilateral imports. Both identify major supplier "
        "countries for mineral commodities."
    ),
    construct_divergence_from_isi=(
        "USGS is US-centric (import reliance for the US), while ISI "
        "is per-country. USGS covers a broader commodity basket "
        "including rare earths and strategic minerals not necessarily "
        "in ISI's HS code scope."
    ),
    data_source="USGS Mineral Commodity Summaries",
    geographic_coverage="US-centric, global production data",
    alignment_thresholds={
        "strong_alignment_min": 0.50,
        "weak_alignment_min": 0.25,
    },
    divergence_interpretation=(
        "Divergence expected because USGS covers different commodity "
        "scope and is US-specific. Useful for directional validation "
        "only."
    ),
    integration_requirements=[
        "Download USGS mineral commodity summaries",
        "Extract import source data for ISI-relevant commodities",
        "Map to ISI country universe",
        "Compare directional agreement with ISI Axis 5",
    ],
    authority_level=BenchmarkAuthority.SUPPORTING,
    authority_justification=(
        "USGS is US-centric with different commodity scope. "
        "Useful for directional validation only."
    ),
)


# ── Axis 6: Logistics ──

BENCHMARK_UNCTAD_LSCI = _benchmark_entry(
    benchmark_id="EXT_UNCTAD_LSCI",
    name="UNCTAD Liner Shipping Connectivity Index",
    relevant_axes=[6],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "UNCTAD LSCI measures a country's connectivity to global "
        "liner shipping networks. Components: number of ships, "
        "container-carrying capacity, maximum vessel size, number "
        "of services, and number of companies."
    ),
    construct_overlap_with_isi=(
        "Both relate to maritime logistics infrastructure. UNCTAD "
        "LSCI captures connectivity; ISI Axis 6 captures bilateral "
        "freight concentration."
    ),
    construct_divergence_from_isi=(
        "LSCI measures CONNECTIVITY (how well-connected), while ISI "
        "measures CONCENTRATION (how dependent on few routes/partners). "
        "A country can be highly connected but still concentrated if "
        "most freight goes through one port. These are INVERSE-RELATED "
        "constructs: high connectivity often means low concentration."
    ),
    data_source="UNCTAD Liner Shipping Connectivity Index",
    geographic_coverage="~160 countries",
    alignment_thresholds={
        "strong_alignment_min": 0.45,
        "weak_alignment_min": 0.20,
    },
    divergence_interpretation=(
        "Expect NEGATIVE correlation (high LSCI = low ISI Axis 6). "
        "Alignment thresholds apply to absolute correlation. If "
        "no relationship exists, ISI Axis 6 is not measuring the "
        "same dimension of logistics."
    ),
    integration_requirements=[
        "Download UNCTAD LSCI annual data",
        "Map UNCTAD country codes to ISI ISO-2",
        "Compute Spearman rank correlation with ISI Axis 6",
        "Note: expect NEGATIVE correlation",
    ],
    authority_level=BenchmarkAuthority.HIGH_CONFIDENCE,
    authority_justification=(
        "UNCTAD LSCI is the authoritative measure of maritime "
        "connectivity. Inverse relationship with ISI Axis 6 is "
        "expected and informative."
    ),
)

BENCHMARK_LPI = _benchmark_entry(
    benchmark_id="EXT_WORLD_BANK_LPI",
    name="World Bank Logistics Performance Index",
    relevant_axes=[6],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.STRUCTURALLY_DEFINED,
    construct_description=(
        "World Bank LPI is a survey-based logistics performance "
        "indicator covering customs efficiency, infrastructure quality, "
        "international shipment ease, logistics competence, "
        "tracking capability, and timeliness."
    ),
    construct_overlap_with_isi=(
        "Both relate to logistics infrastructure quality. LPI reflects "
        "perceived logistics performance; ISI Axis 6 reflects bilateral "
        "freight concentration."
    ),
    construct_divergence_from_isi=(
        "LPI is PERCEPTION-based (survey of logistics professionals). "
        "ISI is DATA-based (bilateral freight volumes). LPI measures "
        "QUALITY; ISI measures CONCENTRATION. A country can have "
        "excellent logistics (high LPI) but concentrated freight "
        "routes (high ISI Axis 6)."
    ),
    data_source="World Bank Logistics Performance Index",
    geographic_coverage="~160 countries (survey-based, biennial)",
    alignment_thresholds={
        "strong_alignment_min": 0.40,
        "weak_alignment_min": 0.15,
    },
    divergence_interpretation=(
        "Low alignment is EXPECTED because quality and concentration "
        "are different constructs. LPI is useful for directional "
        "validation only."
    ),
    integration_requirements=[
        "Download World Bank LPI data",
        "Map to ISI country universe",
        "Compute Spearman rank correlation with ISI Axis 6",
    ],
    authority_level=BenchmarkAuthority.SUPPORTING,
    authority_justification=(
        "LPI is survey/perception-based, not data-based. Different "
        "construct (quality vs concentration). Directional only."
    ),
)


# ── Cross-Axis ──

BENCHMARK_EIU_SUPPLY_CHAIN = _benchmark_entry(
    benchmark_id="EXT_EIU_SUPPLY_CHAIN",
    name="Economist Intelligence Unit Supply Chain Risk Index",
    relevant_axes=[1, 2, 3, 4, 5, 6],
    comparison_type=ComparisonType.RANK_CORRELATION,
    status=IntegrationStatus.NOT_INTEGRATED,
    construct_description=(
        "EIU proprietary supply chain risk index covering economic, "
        "political, and logistical risk factors across multiple "
        "dimensions."
    ),
    construct_overlap_with_isi=(
        "Both aim to measure supply-chain vulnerability. EIU is a "
        "composite risk measure; ISI is a bilateral concentration "
        "measure. Correlation would validate that concentration "
        "captures an aspect of supply chain risk."
    ),
    construct_divergence_from_isi=(
        "EIU includes political risk, regulatory environment, and "
        "infrastructure quality — dimensions ISI does not attempt to "
        "measure. Divergence is expected and does not invalidate either."
    ),
    data_source="Economist Intelligence Unit (proprietary)",
    geographic_coverage="~130 countries",
    alignment_thresholds={
        "strong_alignment_min": 0.50,
        "weak_alignment_min": 0.25,
    },
    divergence_interpretation=(
        "Low alignment confirms ISI measures a different (narrower) "
        "construct than comprehensive supply chain risk. High alignment "
        "would suggest concentration is a strong predictor of overall "
        "supply chain risk."
    ),
    integration_requirements=[
        "Obtain EIU data license",
        "Extract per-country risk scores",
        "Map to ISI country universe",
        "Compute composite and per-axis rank correlations",
    ],
    authority_level=BenchmarkAuthority.SUPPORTING,
    authority_justification=(
        "Proprietary composite index with broader scope. Different "
        "construct (risk vs concentration). Directional comparison only."
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARK REGISTRY — Complete list
# ═══════════════════════════════════════════════════════════════════════════

EXTERNAL_BENCHMARK_REGISTRY: list[dict[str, Any]] = [
    # Axis 1: Financial
    BENCHMARK_BIS_CBS,
    # Axis 2: Energy
    BENCHMARK_IEA_ENERGY,
    BENCHMARK_EUROSTAT_ENERGY,
    # Axis 3: Technology
    BENCHMARK_WITS_TECH,
    # Axis 4: Defense
    BENCHMARK_SIPRI_MILEX,
    BENCHMARK_SIPRI_TIV_COMPARE,
    # Axis 5: Critical Inputs
    BENCHMARK_EU_CRM,
    BENCHMARK_USGS_MINERALS,
    # Axis 6: Logistics
    BENCHMARK_UNCTAD_LSCI,
    BENCHMARK_LPI,
    # Cross-Axis
    BENCHMARK_EIU_SUPPLY_CHAIN,
]

# Index by ID for fast lookup
_BENCHMARK_BY_ID: dict[str, dict[str, Any]] = {
    b["benchmark_id"]: b for b in EXTERNAL_BENCHMARK_REGISTRY
}

# Index by axis
_BENCHMARKS_BY_AXIS: dict[int, list[dict[str, Any]]] = {}
for _b in EXTERNAL_BENCHMARK_REGISTRY:
    for _ax in _b["relevant_axes"]:
        _BENCHMARKS_BY_AXIS.setdefault(_ax, []).append(_b)


# ═══════════════════════════════════════════════════════════════════════════
# QUERY API
# ═══════════════════════════════════════════════════════════════════════════

def get_benchmark_registry() -> list[dict[str, Any]]:
    """Return the complete external benchmark registry."""
    return list(EXTERNAL_BENCHMARK_REGISTRY)


def get_benchmark_by_id(benchmark_id: str) -> dict[str, Any] | None:
    """Look up a benchmark by its ID. Returns None if not found."""
    return _BENCHMARK_BY_ID.get(benchmark_id)


def get_benchmarks_for_axis(axis_id: int) -> list[dict[str, Any]]:
    """Return all benchmarks relevant to a given ISI axis."""
    return list(_BENCHMARKS_BY_AXIS.get(axis_id, []))


def get_benchmarks_by_status(status: str) -> list[dict[str, Any]]:
    """Filter benchmarks by integration status."""
    return [b for b in EXTERNAL_BENCHMARK_REGISTRY if b["status"] == status]


def get_benchmark_coverage_summary() -> dict[str, Any]:
    """Return a summary of benchmark coverage per axis."""
    coverage: dict[int, dict[str, Any]] = {}
    for ax in range(1, 7):
        benchmarks = _BENCHMARKS_BY_AXIS.get(ax, [])
        coverage[ax] = {
            "n_benchmarks": len(benchmarks),
            "benchmark_ids": [b["benchmark_id"] for b in benchmarks],
            "n_integrated": sum(
                1 for b in benchmarks
                if b["status"] == IntegrationStatus.INTEGRATED
            ),
            "n_structurally_defined": sum(
                1 for b in benchmarks
                if b["status"] == IntegrationStatus.STRUCTURALLY_DEFINED
            ),
            "n_not_integrated": sum(
                1 for b in benchmarks
                if b["status"] == IntegrationStatus.NOT_INTEGRATED
            ),
        }

    total = len(EXTERNAL_BENCHMARK_REGISTRY)
    n_integrated = sum(
        1 for b in EXTERNAL_BENCHMARK_REGISTRY
        if b["status"] == IntegrationStatus.INTEGRATED
    )
    n_defined = sum(
        1 for b in EXTERNAL_BENCHMARK_REGISTRY
        if b["status"] == IntegrationStatus.STRUCTURALLY_DEFINED
    )

    return {
        "total_benchmarks": total,
        "n_integrated": n_integrated,
        "n_structurally_defined": n_defined,
        "n_not_integrated": total - n_integrated - n_defined,
        "per_axis_coverage": coverage,
        "axes_with_benchmarks": sorted(
            ax for ax in range(1, 7) if _BENCHMARKS_BY_AXIS.get(ax)
        ),
        "axes_without_benchmarks": sorted(
            ax for ax in range(1, 7) if not _BENCHMARKS_BY_AXIS.get(ax)
        ),
        "honesty_note": (
            f"Of {total} defined benchmarks, {n_integrated} are integrated "
            f"with actual data, {n_defined} are structurally defined "
            f"(comparison framework exists but data not loaded), and "
            f"{total - n_integrated - n_defined} are not yet integrated. "
            f"Benchmark alignment validates CONSTRUCT OVERLAP, not "
            f"'correctness.' Low alignment may indicate genuine construct "
            f"differences, not ISI errors."
        ),
    }


def validate_benchmark_registry() -> list[str]:
    """Run self-validation on the benchmark registry.

    Returns a list of issues (empty if clean).
    """
    issues: list[str] = []
    seen_ids: set[str] = set()

    for b in EXTERNAL_BENCHMARK_REGISTRY:
        # Check for duplicate IDs
        if b["benchmark_id"] in seen_ids:
            issues.append(f"Duplicate benchmark_id: {b['benchmark_id']}")
        seen_ids.add(b["benchmark_id"])

        # Check alignment thresholds are valid
        thresholds = b.get("alignment_thresholds", {})
        strong = thresholds.get("strong_alignment_min", 0)
        weak = thresholds.get("weak_alignment_min", 0)
        if strong < weak:
            issues.append(
                f"{b['benchmark_id']}: strong_alignment_min ({strong}) "
                f"< weak_alignment_min ({weak})"
            )

        # Check all axes are 1-6
        for ax in b.get("relevant_axes", []):
            if ax < 1 or ax > 6:
                issues.append(f"{b['benchmark_id']}: invalid axis {ax}")

    # Check axis coverage — all axes should have at least one benchmark
    for ax in range(1, 7):
        if ax not in _BENCHMARKS_BY_AXIS or len(_BENCHMARKS_BY_AXIS[ax]) == 0:
            issues.append(f"Axis {ax} has no benchmarks defined")

    return issues
