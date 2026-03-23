"""
backend.falsification — External Contradiction Testing Framework

LAYER 2: Compares ISI outputs against external benchmark datasets to
identify where the system contradicts observable reality.

This module implements:
1. Benchmark dataset definitions with expected ISI-vs-external relationships
2. Per-country divergence scoring (synthetic, from structural analysis)
3. Falsification flags: CONSISTENT / TENSION / CONTRADICTION
4. Integration hooks for governance and export layers

Design contract:
    - EXTERNAL benchmarks define what the world looks like independently of ISI
    - ISI outputs are compared to those benchmarks
    - Contradictions are surfaced, not hidden
    - Until real external data is integrated, benchmarks use structural
      predictions (e.g., "a major energy exporter should show low
      import concentration on Axis 2")

HONESTY NOTE: This module currently performs STRUCTURAL falsification
(checking ISI logic against known country characteristics) rather than
EMPIRICAL falsification (comparing ISI scores against external datasets).
Structural falsification is necessary but not sufficient. Integration
of real external data (IEA, EU CRM, SIPRI MILEX) is the next step.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# FALSIFICATION FLAGS
# ═══════════════════════════════════════════════════════════════════════════

class FalsificationFlag:
    """Per-country falsification assessment result."""
    CONSISTENT = "CONSISTENT"
    TENSION = "TENSION"
    CONTRADICTION = "CONTRADICTION"
    NOT_ASSESSED = "NOT_ASSESSED"


VALID_FLAGS = frozenset({
    FalsificationFlag.CONSISTENT,
    FalsificationFlag.TENSION,
    FalsificationFlag.CONTRADICTION,
    FalsificationFlag.NOT_ASSESSED,
})


# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARK DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════
# Each benchmark defines an external data source or structural prediction
# that ISI outputs should be consistent with.

BENCHMARK_REGISTRY: list[dict[str, Any]] = [
    {
        "benchmark_id": "STRUCTURAL_PRODUCER_INVERSION",
        "name": "Producer Inversion Structural Consistency",
        "description": (
            "Major commodity exporters should show either: "
            "(a) low import concentration (HHI) on their export axis, OR "
            "(b) be flagged as PRODUCER_INVERSION in the governance model. "
            "If a known major exporter shows high import concentration "
            "WITHOUT a producer-inversion flag, the system has a blind spot."
        ),
        "relevant_axes": [2, 4, 5],
        "comparison_type": "STRUCTURAL_CONSISTENCY",
        "data_source": "SIPRI/IEA/USGS known exporter lists (coded)",
        "status": "INTEGRATED_STRUCTURAL",
    },
    {
        "benchmark_id": "STRUCTURAL_SANCTIONS_EFFECT",
        "name": "Sanctions Effect Structural Consistency",
        "description": (
            "Countries under active sanctions (2022+) should show "
            "governance tiers of NON_COMPARABLE or LOW_CONFIDENCE. "
            "If a sanctioned country reaches PARTIALLY_COMPARABLE or "
            "above, the sanctions model is too weak."
        ),
        "relevant_axes": [1, 2, 3, 4, 5, 6],
        "comparison_type": "STRUCTURAL_CONSISTENCY",
        "data_source": "EU/US sanctions lists (coded)",
        "status": "INTEGRATED_STRUCTURAL",
    },
    {
        "benchmark_id": "STRUCTURAL_EU_DATA_ADVANTAGE",
        "name": "EU-27 Data Architecture Advantage",
        "description": (
            "EU-27 members should generally achieve higher governance "
            "tiers than non-EU reference countries (due to Eurostat, "
            "CN8, intra-EU bilateral data). If non-EU countries "
            "systematically outperform EU members, the governance "
            "model is not reflecting data architecture reality."
        ),
        "relevant_axes": [1, 2, 3, 5, 6],
        "comparison_type": "RANK_ORDERING",
        "data_source": "Data architecture analysis",
        "status": "INTEGRATED_STRUCTURAL",
    },
    {
        "benchmark_id": "EXTERNAL_IEA_ENERGY",
        "name": "IEA Energy Security Indicators",
        "description": (
            "IEA energy import dependency metrics should correlate "
            "with ISI Axis 2 (energy) for OECD countries. "
            "Expected: Spearman rho > 0.5 for non-producer countries."
        ),
        "relevant_axes": [2],
        "comparison_type": "RANK_CORRELATION",
        "data_source": "IEA World Energy Outlook / Energy Security DB",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Access IEA bilateral energy import data",
            "Compute HHI-equivalent from IEA data",
            "Compute rank correlation with ISI Axis 2 for overlapping countries",
        ],
    },
    {
        "benchmark_id": "EXTERNAL_EU_CRM",
        "name": "EU Critical Raw Materials Supply Study",
        "description": (
            "EU CRM supply concentration data should correlate with "
            "ISI Axis 5 (critical inputs) for EU-27 countries. "
            "Expected: Spearman rho > 0.4."
        ),
        "relevant_axes": [5],
        "comparison_type": "RANK_CORRELATION",
        "data_source": "EU CRM Act supply studies",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Download EU CRM bilateral supply data",
            "Map EU CRM country codes to ISI ISO-2",
            "Compute HHI-equivalent from CRM data",
            "Compute rank correlation with ISI Axis 5",
        ],
    },
    {
        "benchmark_id": "EXTERNAL_SIPRI_MILEX",
        "name": "SIPRI Military Expenditure Cross-Check",
        "description": (
            "Countries with high military expenditure but low Axis 4 "
            "(defense) HHI should be flagged as potential producer "
            "inversions. If ISI fails to flag them, the producer "
            "inversion registry is incomplete."
        ),
        "relevant_axes": [4],
        "comparison_type": "STRUCTURAL_CONSISTENCY",
        "data_source": "SIPRI Military Expenditure Database",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Download SIPRI MILEX data",
            "Identify high-MILEX + low-Axis4-HHI countries",
            "Compare against PRODUCER_INVERSION_REGISTRY",
        ],
    },
    {
        "benchmark_id": "EXTERNAL_BIS_CBS",
        "name": "BIS Consolidated Banking Statistics",
        "description": (
            "BIS CBS (ultimate risk basis) should correlate with ISI "
            "Axis 1 (financial, BIS LBS + CPIS). Divergence suggests "
            "locational vs ultimate risk measurement matters."
        ),
        "relevant_axes": [1],
        "comparison_type": "RANK_CORRELATION",
        "data_source": "BIS Consolidated Banking Statistics",
        "status": "NOT_INTEGRATED",
        "integration_requirements": [
            "Access BIS CBS data",
            "Compute bilateral exposure HHI from CBS",
            "Compare with ISI Axis 1 for BIS-reporting countries",
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# KNOWN COUNTRY STRUCTURAL FACTS
# ═══════════════════════════════════════════════════════════════════════════
# These are externally verifiable facts about countries that ISI outputs
# must be consistent with. They serve as structural falsification inputs.

STRUCTURAL_FACTS: dict[str, dict[str, Any]] = {
    "US": {
        "known_exporter_axes": [2, 4, 5],
        "sanctions_active": False,
        "cpis_participant": False,  # Partial — US reports to CPIS but not as fully as EU
        "bis_reporter": True,
        "expected_min_governance": "NON_COMPARABLE",
        "reason": "3 producer-inverted axes → structural disqualification",
    },
    "RU": {
        "known_exporter_axes": [2, 4, 5],
        "sanctions_active": True,
        "cpis_participant": False,
        "bis_reporter": False,
        "expected_min_governance": "NON_COMPARABLE",
        "reason": "Sanctions + 3 inversions → double structural disqualification",
    },
    "CN": {
        "known_exporter_axes": [4, 5],
        "sanctions_active": False,
        "cpis_participant": False,
        "bis_reporter": False,
        "expected_min_governance": "LOW_CONFIDENCE",
        "reason": "2 inversions + CPIS absence → LOW_CONFIDENCE minimum",
    },
    "NO": {
        "known_exporter_axes": [2],
        "sanctions_active": False,
        "cpis_participant": True,
        "bis_reporter": True,
        "expected_min_governance": "PARTIALLY_COMPARABLE",
        "reason": "1 inversion (energy) → PARTIALLY at worst",
    },
    "AU": {
        "known_exporter_axes": [2, 5],
        "sanctions_active": False,
        "cpis_participant": True,
        "bis_reporter": True,
        "expected_min_governance": "LOW_CONFIDENCE",
        "reason": "2 inversions → LOW_CONFIDENCE",
    },
    "FR": {
        "known_exporter_axes": [4],
        "sanctions_active": False,
        "cpis_participant": True,
        "bis_reporter": True,
        "expected_min_governance": "PARTIALLY_COMPARABLE",
        "reason": "1 inversion (defense) → PARTIALLY at worst",
    },
    "DE": {
        "known_exporter_axes": [4],
        "sanctions_active": False,
        "cpis_participant": True,
        "bis_reporter": True,
        "expected_min_governance": "PARTIALLY_COMPARABLE",
        "reason": "1 inversion (defense) → PARTIALLY at worst",
    },
    "SA": {
        "known_exporter_axes": [2],
        "sanctions_active": False,
        "cpis_participant": True,
        "bis_reporter": False,
        "expected_min_governance": "PARTIALLY_COMPARABLE",
        "reason": "1 inversion (energy) + non-BIS → PARTIALLY",
    },
}

# Governance tier ordering for comparison
_TIER_ORDER = {
    "FULLY_COMPARABLE": 4,
    "PARTIALLY_COMPARABLE": 3,
    "LOW_CONFIDENCE": 2,
    "NON_COMPARABLE": 1,
}


# ═══════════════════════════════════════════════════════════════════════════
# FALSIFICATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════

def assess_country_falsification(
    country: str,
    governance_result: dict[str, Any],
) -> dict[str, Any]:
    """Assess whether ISI outputs for a country contradict known external facts.

    Args:
        country: ISO-2 country code.
        governance_result: Output of assess_country_governance() for this country.

    Returns:
        Falsification assessment with overall flag, per-benchmark results,
        and divergence details.
    """
    checks: list[dict[str, Any]] = []
    overall_flag = FalsificationFlag.NOT_ASSESSED

    actual_tier = governance_result.get("governance_tier", "UNKNOWN")
    actual_tier_rank = _TIER_ORDER.get(actual_tier, 0)

    # ── CHECK 1: Producer Inversion Structural Consistency ──
    facts = STRUCTURAL_FACTS.get(country)
    if facts:
        expected_governance = facts["expected_min_governance"]
        expected_rank = _TIER_ORDER.get(expected_governance, 0)

        # Country should be AT OR BELOW the expected governance tier
        # (i.e., actual_tier_rank <= expected_rank is allowed,
        #  actual_tier_rank > expected_rank means system is too generous)
        if actual_tier_rank > expected_rank:
            check_flag = FalsificationFlag.CONTRADICTION
            detail = (
                f"ISI assigns {actual_tier} but structural analysis expects "
                f"{expected_governance} or worse. Reason: {facts['reason']}. "
                f"The governance model is too generous for {country}."
            )
        elif actual_tier_rank == expected_rank:
            check_flag = FalsificationFlag.CONSISTENT
            detail = (
                f"ISI assigns {actual_tier}, consistent with structural "
                f"expectation ({expected_governance}). {facts['reason']}"
            )
        else:
            # Actual is stricter than expected — tension (conservative)
            check_flag = FalsificationFlag.TENSION
            detail = (
                f"ISI assigns {actual_tier}, stricter than structural "
                f"expectation ({expected_governance}). {facts['reason']}. "
                f"System may be overly conservative for {country}."
            )

        checks.append({
            "benchmark_id": "STRUCTURAL_PRODUCER_INVERSION",
            "flag": check_flag,
            "detail": detail,
            "expected_governance": expected_governance,
            "actual_governance": actual_tier,
        })

        # ── CHECK 2: Sanctions consistency ──
        if facts.get("sanctions_active"):
            if actual_tier_rank >= _TIER_ORDER["PARTIALLY_COMPARABLE"]:
                checks.append({
                    "benchmark_id": "STRUCTURAL_SANCTIONS_EFFECT",
                    "flag": FalsificationFlag.CONTRADICTION,
                    "detail": (
                        f"Sanctioned country {country} reached "
                        f"{actual_tier} — sanctions model too weak."
                    ),
                })
            else:
                checks.append({
                    "benchmark_id": "STRUCTURAL_SANCTIONS_EFFECT",
                    "flag": FalsificationFlag.CONSISTENT,
                    "detail": (
                        f"Sanctioned country {country} correctly "
                        f"classified as {actual_tier}."
                    ),
                })

        # ── CHECK 3: Producer inversion registry completeness ──
        from backend.governance import PRODUCER_INVERSION_REGISTRY
        registered_inversions = PRODUCER_INVERSION_REGISTRY.get(country, {})
        registered_axes = set(registered_inversions.get("inverted_axes", []))
        known_axes = set(facts.get("known_exporter_axes", []))

        missing_inversions = known_axes - registered_axes
        if missing_inversions:
            checks.append({
                "benchmark_id": "STRUCTURAL_PRODUCER_INVERSION",
                "flag": FalsificationFlag.CONTRADICTION,
                "detail": (
                    f"Country {country} is a known exporter on axes "
                    f"{sorted(missing_inversions)} but these are NOT in "
                    f"PRODUCER_INVERSION_REGISTRY. Registry is incomplete."
                ),
                "missing_axes": sorted(missing_inversions),
            })
        elif known_axes:
            extra_inversions = registered_axes - known_axes
            if extra_inversions:
                checks.append({
                    "benchmark_id": "STRUCTURAL_PRODUCER_INVERSION",
                    "flag": FalsificationFlag.TENSION,
                    "detail": (
                        f"PRODUCER_INVERSION_REGISTRY flags {country} on "
                        f"axes {sorted(extra_inversions)} beyond known "
                        f"exporter profile. Possible over-flagging."
                    ),
                })

    # ── CHECK 4: EU-27 Data Architecture Advantage ──
    # (Applied only for EU-27 countries)
    from backend.constants import EU27_CODES
    if country in EU27_CODES:
        # EU-27 countries with clean profiles should reach PARTIALLY or above
        n_inverted = governance_result.get("n_producer_inverted_axes", 0)
        if n_inverted == 0 and actual_tier_rank < _TIER_ORDER["PARTIALLY_COMPARABLE"]:
            checks.append({
                "benchmark_id": "STRUCTURAL_EU_DATA_ADVANTAGE",
                "flag": FalsificationFlag.TENSION,
                "detail": (
                    f"EU-27 country {country} with zero inversions "
                    f"is classified as {actual_tier}. EU data architecture "
                    f"should support at least PARTIALLY_COMPARABLE."
                ),
            })
        elif n_inverted == 0:
            checks.append({
                "benchmark_id": "STRUCTURAL_EU_DATA_ADVANTAGE",
                "flag": FalsificationFlag.CONSISTENT,
                "detail": (
                    f"EU-27 country {country} at {actual_tier}, "
                    f"consistent with EU data architecture advantage."
                ),
            })

    # ── Determine overall flag ──
    if not checks:
        overall_flag = FalsificationFlag.NOT_ASSESSED
    elif any(c["flag"] == FalsificationFlag.CONTRADICTION for c in checks):
        overall_flag = FalsificationFlag.CONTRADICTION
    elif any(c["flag"] == FalsificationFlag.TENSION for c in checks):
        overall_flag = FalsificationFlag.TENSION
    else:
        overall_flag = FalsificationFlag.CONSISTENT

    return {
        "country": country,
        "overall_flag": overall_flag,
        "n_checks": len(checks),
        "n_contradictions": sum(1 for c in checks if c["flag"] == FalsificationFlag.CONTRADICTION),
        "n_tensions": sum(1 for c in checks if c["flag"] == FalsificationFlag.TENSION),
        "checks": checks,
        "external_data_status": _benchmark_integration_summary(),
        "honesty_note": (
            "This falsification assessment is currently STRUCTURAL "
            "(based on known country characteristics) not EMPIRICAL "
            "(based on external dataset comparison). Structural "
            "falsification catches gross inconsistencies but cannot "
            "validate score accuracy."
        ),
    }


def assess_all_countries_falsification(
    governance_results: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Run falsification assessment for all countries with governance results.

    Args:
        governance_results: {country: governance_assessment} dict.

    Returns:
        {country: falsification_result} dict.
    """
    results = {}
    for country, gov in governance_results.items():
        results[country] = assess_country_falsification(country, gov)
    return results


def get_falsification_summary(
    falsification_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Summarize falsification results across all assessed countries."""
    n_total = len(falsification_results)
    n_consistent = sum(
        1 for r in falsification_results.values()
        if r["overall_flag"] == FalsificationFlag.CONSISTENT
    )
    n_tension = sum(
        1 for r in falsification_results.values()
        if r["overall_flag"] == FalsificationFlag.TENSION
    )
    n_contradiction = sum(
        1 for r in falsification_results.values()
        if r["overall_flag"] == FalsificationFlag.CONTRADICTION
    )
    n_not_assessed = sum(
        1 for r in falsification_results.values()
        if r["overall_flag"] == FalsificationFlag.NOT_ASSESSED
    )

    contradicted = sorted(
        c for c, r in falsification_results.items()
        if r["overall_flag"] == FalsificationFlag.CONTRADICTION
    )
    tensioned = sorted(
        c for c, r in falsification_results.items()
        if r["overall_flag"] == FalsificationFlag.TENSION
    )

    return {
        "total_assessed": n_total,
        "consistent": n_consistent,
        "tension": n_tension,
        "contradiction": n_contradiction,
        "not_assessed": n_not_assessed,
        "contradicted_countries": contradicted,
        "tensioned_countries": tensioned,
        "external_benchmarks_integrated": _count_integrated_benchmarks(),
        "external_benchmarks_pending": _count_pending_benchmarks(),
        "interpretation": (
            f"Of {n_total} countries assessed, {n_consistent} are "
            f"structurally consistent with known external facts, "
            f"{n_tension} show tension (conservative or borderline), "
            f"and {n_contradiction} show contradictions. "
            f"{_count_pending_benchmarks()} external empirical "
            f"benchmarks remain unintegrated."
        ),
        "honesty_note": (
            "Structural falsification catches logical inconsistencies "
            "but CANNOT validate score accuracy. Zero contradictions "
            "does NOT mean the scores are correct — it means they are "
            "internally consistent with known country characteristics. "
            "Empirical validation requires external benchmark integration."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARK MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def get_benchmark_registry() -> list[dict[str, Any]]:
    """Return the complete benchmark registry."""
    return list(BENCHMARK_REGISTRY)


def _benchmark_integration_summary() -> dict[str, int]:
    """Count benchmarks by integration status."""
    summary: dict[str, int] = {}
    for b in BENCHMARK_REGISTRY:
        status = b["status"]
        summary[status] = summary.get(status, 0) + 1
    return summary


def _count_integrated_benchmarks() -> int:
    """Count benchmarks that are integrated (structural or empirical)."""
    return sum(
        1 for b in BENCHMARK_REGISTRY
        if b["status"].startswith("INTEGRATED")
    )


def _count_pending_benchmarks() -> int:
    """Count benchmarks not yet integrated."""
    return sum(
        1 for b in BENCHMARK_REGISTRY
        if b["status"] == "NOT_INTEGRATED"
    )
