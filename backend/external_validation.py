"""
backend.external_validation — External Validation Engine

Alignment engine that compares ISI outputs against external benchmarks.
This is the system that answers: "Does this align with reality?"

Core functions:
    compare_to_benchmark() — compare ISI axis to one external benchmark
    assess_country_alignment() — full alignment profile for a country
    assess_construct_validity() — whether ISI axes measure what they claim

Design contract:
    - NEVER fake alignment. Missing data → NO_DATA, not silent skip.
    - NEVER assume correlation means correctness.
    - HANDLE structural incomparability explicitly.
    - FLAG divergence as potentially meaningful, not automatically wrong.
    - NO silent fallbacks.

Honesty note:
    External validation tests CONSTRUCT OVERLAP between ISI and external
    datasets. Alignment confirms that ISI captures part of reality.
    Divergence may mean ISI is wrong, OR that the external dataset measures
    something genuinely different. Both interpretations are reported.
"""

from __future__ import annotations

from typing import Any

from backend.benchmark_registry import (
    AlignmentClass,
    BenchmarkAuthority,
    AUTHORITY_WEIGHTS,
    ComparisonType,
    IntegrationStatus,
    EXTERNAL_BENCHMARK_REGISTRY,
    get_benchmark_by_id,
    get_benchmarks_for_axis,
)


# ═══════════════════════════════════════════════════════════════════════════
# EMPIRICAL ALIGNMENT ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def compare_to_benchmark(
    benchmark_id: str,
    isi_values: dict[str, float] | None,
    external_values: dict[str, float] | None,
) -> dict[str, Any]:
    """Compare ISI axis values to an external benchmark dataset.

    This is the core alignment function. It computes alignment
    metrics between ISI axis scores and external benchmark values
    for overlapping countries.

    Args:
        benchmark_id: ID of the benchmark to compare against.
        isi_values: {country_code: isi_score} for the relevant ISI axis.
            None if ISI data is unavailable.
        external_values: {country_code: external_value} from the benchmark.
            None if external data is unavailable.

    Returns:
        Alignment assessment with classification, metrics, and interpretation.
    """
    benchmark = get_benchmark_by_id(benchmark_id)
    if benchmark is None:
        return {
            "benchmark_id": benchmark_id,
            "alignment_class": AlignmentClass.NO_DATA,
            "error": f"Unknown benchmark_id: {benchmark_id}",
        }

    # ── Handle missing data explicitly ──
    if isi_values is None or external_values is None:
        return _no_data_result(
            benchmark_id=benchmark_id,
            benchmark_name=benchmark["name"],
            reason=(
                "ISI data not provided"
                if isi_values is None
                else "External benchmark data not provided"
            ),
        )

    if len(isi_values) == 0 or len(external_values) == 0:
        return _no_data_result(
            benchmark_id=benchmark_id,
            benchmark_name=benchmark["name"],
            reason="Empty dataset provided",
        )

    # ── Find overlapping countries ──
    overlap_countries = sorted(
        set(isi_values.keys()) & set(external_values.keys())
    )

    if len(overlap_countries) < 5:
        return {
            "benchmark_id": benchmark_id,
            "benchmark_name": benchmark["name"],
            "alignment_class": AlignmentClass.STRUCTURALLY_INCOMPARABLE,
            "reason": (
                f"Only {len(overlap_countries)} overlapping countries "
                f"(minimum 5 required for meaningful comparison)"
            ),
            "overlap_countries": overlap_countries,
            "n_isi_countries": len(isi_values),
            "n_external_countries": len(external_values),
        }

    # ── Compute alignment metrics based on comparison type ──
    comparison_type = benchmark["comparison_type"]

    if comparison_type == ComparisonType.RANK_CORRELATION:
        result = _compute_rank_correlation(
            isi_values, external_values, overlap_countries
        )
    elif comparison_type == ComparisonType.STRUCTURAL_CONSISTENCY:
        result = _compute_structural_consistency(
            isi_values, external_values, overlap_countries
        )
    elif comparison_type == ComparisonType.DIRECTIONAL_AGREEMENT:
        result = _compute_directional_agreement(
            isi_values, external_values, overlap_countries
        )
    elif comparison_type == ComparisonType.LEVEL_COMPARISON:
        result = _compute_level_comparison(
            isi_values, external_values, overlap_countries
        )
    else:
        result = {
            "metric": None,
            "metric_name": "UNKNOWN",
            "detail": f"Unsupported comparison type: {comparison_type}",
        }

    # ── Classify alignment ──
    thresholds = benchmark["alignment_thresholds"]
    alignment_class = _classify_alignment(
        metric_value=result.get("metric"),
        strong_min=thresholds["strong_alignment_min"],
        weak_min=thresholds["weak_alignment_min"],
        comparison_type=comparison_type,
    )

    return {
        "benchmark_id": benchmark_id,
        "benchmark_name": benchmark["name"],
        "comparison_type": comparison_type,
        "alignment_class": alignment_class,
        "n_overlap_countries": len(overlap_countries),
        "overlap_countries": overlap_countries,
        "metric_name": result.get("metric_name", ""),
        "metric_value": result.get("metric"),
        "strong_alignment_threshold": thresholds["strong_alignment_min"],
        "weak_alignment_threshold": thresholds["weak_alignment_min"],
        "detail": result.get("detail", ""),
        "per_country_detail": result.get("per_country_detail", []),
        "construct_overlap_note": benchmark["construct_overlap_with_isi"],
        "construct_divergence_note": benchmark["construct_divergence_from_isi"],
        "divergence_interpretation": benchmark["divergence_interpretation"],
        "honesty_note": (
            f"Alignment class '{alignment_class}' reflects construct "
            f"overlap between ISI and {benchmark['name']}. "
            f"{'STRONG alignment confirms ISI captures a dimension measured by the benchmark.' if alignment_class == AlignmentClass.STRONGLY_ALIGNED else ''}"
            f"{'WEAK alignment suggests partial construct overlap.' if alignment_class == AlignmentClass.WEAKLY_ALIGNED else ''}"
            f"{'DIVERGENT result may indicate ISI error OR genuine construct difference. Both possibilities are real.' if alignment_class == AlignmentClass.DIVERGENT else ''}"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# COUNTRY-LEVEL ALIGNMENT ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def assess_country_alignment(
    country: str,
    axis_scores: dict[int, float | None],
    external_data: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Assess how well a country's ISI output aligns with external benchmarks.

    Args:
        country: ISO-2 country code.
        axis_scores: {axis_id: score_or_None} for axes 1-6.
        external_data: {benchmark_id: {country: value}} for available benchmarks.
            None if no external data is available.

    Returns:
        Country alignment profile with per-axis and overall assessment.
    """
    axis_alignments: list[dict[str, Any]] = []
    overall_flags: list[str] = []

    for axis_id in range(1, 7):
        score = axis_scores.get(axis_id)
        benchmarks = get_benchmarks_for_axis(axis_id)

        axis_result: dict[str, Any] = {
            "axis_id": axis_id,
            "isi_score": score,
            "benchmarks_available": len(benchmarks),
            "benchmark_results": [],
        }

        if score is None:
            axis_result["alignment_status"] = "ISI_SCORE_MISSING"
            axis_alignments.append(axis_result)
            continue

        has_any_comparison = False

        for benchmark in benchmarks:
            bid = benchmark["benchmark_id"]

            # Check if external data is available for this benchmark
            if external_data is None or bid not in external_data:
                # Benchmark defined but no data loaded
                if benchmark["status"] == IntegrationStatus.INTEGRATED:
                    axis_result["benchmark_results"].append({
                        "benchmark_id": bid,
                        "alignment_class": AlignmentClass.NO_DATA,
                        "reason": "Benchmark integrated but data not provided",
                    })
                else:
                    axis_result["benchmark_results"].append({
                        "benchmark_id": bid,
                        "alignment_class": AlignmentClass.NO_DATA,
                        "reason": f"Benchmark status: {benchmark['status']}",
                    })
                continue

            # We have external data — run comparison
            ext_vals = external_data[bid]
            if country not in ext_vals:
                axis_result["benchmark_results"].append({
                    "benchmark_id": bid,
                    "alignment_class": AlignmentClass.NO_DATA,
                    "reason": f"Country {country} not in benchmark dataset",
                })
                continue

            has_any_comparison = True

            # For country-level, we still run the full comparison
            # but focus on this country's position
            isi_axis_values = {
                c: s for c, s in _collect_all_isi_scores_for_axis(
                    axis_id, axis_scores, country
                ).items()
                if s is not None
            }

            comparison = compare_to_benchmark(
                benchmark_id=bid,
                isi_values=isi_axis_values if isi_axis_values else {country: score},
                external_values=ext_vals,
            )

            axis_result["benchmark_results"].append(comparison)

            # Track alignment flags for overall assessment
            ac = comparison.get("alignment_class", AlignmentClass.NO_DATA)
            if ac == AlignmentClass.DIVERGENT:
                overall_flags.append(f"DIVERGENT_AXIS_{axis_id}_{bid}")
            elif ac == AlignmentClass.STRONGLY_ALIGNED:
                overall_flags.append(f"ALIGNED_AXIS_{axis_id}_{bid}")

        if not has_any_comparison:
            axis_result["alignment_status"] = "NO_EXTERNAL_DATA"
        else:
            axis_result["alignment_status"] = "COMPARED"

        axis_alignments.append(axis_result)

    # ── Overall alignment classification ──
    n_divergent = sum(1 for f in overall_flags if f.startswith("DIVERGENT"))
    n_aligned = sum(1 for f in overall_flags if f.startswith("ALIGNED"))
    n_compared = n_divergent + n_aligned

    # ── Weighted alignment score using benchmark authority ──
    weighted_alignment_score, authority_conflicts, alignment_confidence = (
        _compute_weighted_alignment(axis_alignments)
    )

    if n_compared == 0:
        overall_alignment = AlignmentClass.NO_DATA
        overall_interpretation = (
            f"No external benchmark data available for {country}. "
            f"Cannot assess alignment with external reality."
        )
    elif n_divergent > n_aligned:
        overall_alignment = AlignmentClass.DIVERGENT
        overall_interpretation = (
            f"Country {country} shows more divergent than aligned "
            f"benchmark comparisons ({n_divergent}/{n_compared}). "
            f"This may indicate ISI measurement issues OR genuine "
            f"construct differences."
        )
    elif n_aligned > 0 and n_divergent == 0:
        overall_alignment = AlignmentClass.STRONGLY_ALIGNED
        overall_interpretation = (
            f"Country {country} shows consistent alignment across "
            f"all compared benchmarks ({n_aligned}/{n_compared}). "
            f"ISI outputs are empirically grounded."
        )
    else:
        overall_alignment = AlignmentClass.WEAKLY_ALIGNED
        overall_interpretation = (
            f"Country {country} shows mixed alignment: {n_aligned} "
            f"aligned, {n_divergent} divergent out of {n_compared} "
            f"comparisons."
        )

    return {
        "country": country,
        "overall_alignment": overall_alignment,
        "n_axes_compared": n_compared,
        "n_axes_aligned": n_aligned,
        "n_axes_divergent": n_divergent,
        "weighted_alignment_score": weighted_alignment_score,
        "authority_conflicts": authority_conflicts,
        "alignment_confidence": alignment_confidence,
        "axis_alignments": axis_alignments,
        "overall_interpretation": overall_interpretation,
        "honesty_note": (
            "External alignment checks test CONSTRUCT OVERLAP, not "
            "'correctness.' Strong alignment confirms ISI captures "
            "aspects of external reality. Divergence may be ISI error "
            "or genuine construct difference. This assessment is "
            "descriptive, not evaluative."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CONSTRUCT VALIDITY ASSESSMENT
# ═══════════════════════════════════════════════════════════════════════════

def assess_construct_validity(
    all_scores: dict[int, dict[str, float]],
    external_data: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Assess construct validity of each ISI axis against external benchmarks.

    Construct validity = does this axis measure what it claims to measure?

    Args:
        all_scores: {axis_id: {country: score}}.
        external_data: {benchmark_id: {country: value}}.

    Returns:
        Per-axis construct validity assessment.
    """
    axis_validity: dict[int, dict[str, Any]] = {}

    for axis_id in range(1, 7):
        isi_scores = all_scores.get(axis_id, {})
        benchmarks = get_benchmarks_for_axis(axis_id)

        results: list[dict[str, Any]] = []

        for benchmark in benchmarks:
            bid = benchmark["benchmark_id"]
            ext_vals = (external_data or {}).get(bid)

            comparison = compare_to_benchmark(
                benchmark_id=bid,
                isi_values=isi_scores if isi_scores else None,
                external_values=ext_vals,
            )
            results.append(comparison)

        # Aggregate validity assessment for this axis
        n_compared = sum(
            1 for r in results
            if r.get("alignment_class") not in (
                AlignmentClass.NO_DATA,
                AlignmentClass.STRUCTURALLY_INCOMPARABLE,
            )
        )
        n_aligned = sum(
            1 for r in results
            if r.get("alignment_class") in (
                AlignmentClass.STRONGLY_ALIGNED,
                AlignmentClass.WEAKLY_ALIGNED,
            )
        )
        n_divergent = sum(
            1 for r in results
            if r.get("alignment_class") == AlignmentClass.DIVERGENT
        )

        if n_compared == 0:
            validity_status = "NOT_ASSESSED"
            validity_note = (
                f"Axis {axis_id}: no external benchmarks compared. "
                f"Construct validity is UNKNOWN."
            )
        elif n_divergent > n_aligned:
            validity_status = "WEAK"
            validity_note = (
                f"Axis {axis_id}: more divergent than aligned benchmarks "
                f"({n_divergent} divergent, {n_aligned} aligned out of "
                f"{n_compared}). Construct validity is questionable."
            )
        elif n_aligned > 0 and n_divergent == 0:
            validity_status = "SUPPORTED"
            validity_note = (
                f"Axis {axis_id}: all compared benchmarks show alignment "
                f"({n_aligned}/{n_compared}). Construct validity is "
                f"empirically supported."
            )
        else:
            validity_status = "PARTIAL"
            validity_note = (
                f"Axis {axis_id}: mixed benchmark alignment ({n_aligned} "
                f"aligned, {n_divergent} divergent). Construct validity "
                f"is partially supported."
            )

        axis_validity[axis_id] = {
            "axis_id": axis_id,
            "n_benchmarks_defined": len(benchmarks),
            "n_benchmarks_compared": n_compared,
            "n_aligned": n_aligned,
            "n_divergent": n_divergent,
            "validity_status": validity_status,
            "validity_note": validity_note,
            "benchmark_results": results,
        }

    # Overall system validity
    all_statuses = [av["validity_status"] for av in axis_validity.values()]
    n_supported = all_statuses.count("SUPPORTED")
    n_partial = all_statuses.count("PARTIAL")
    n_weak = all_statuses.count("WEAK")
    n_not_assessed = all_statuses.count("NOT_ASSESSED")

    return {
        "per_axis_validity": axis_validity,
        "summary": {
            "n_axes_supported": n_supported,
            "n_axes_partial": n_partial,
            "n_axes_weak": n_weak,
            "n_axes_not_assessed": n_not_assessed,
        },
        "system_validity_status": (
            "EMPIRICALLY_GROUNDED" if n_supported >= 3
            else "PARTIALLY_GROUNDED" if n_supported + n_partial >= 3
            else "WEAKLY_GROUNDED" if n_supported + n_partial >= 1
            else "NOT_ASSESSED"
        ),
        "honesty_note": (
            f"Construct validity assessment: {n_supported} axes supported, "
            f"{n_partial} partial, {n_weak} weak, {n_not_assessed} not assessed. "
            f"'Supported' means external benchmarks align — it does NOT mean "
            f"the axis is 'correct.' It means ISI captures a dimension that "
            f"external data also reflects."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# EXTERNAL VALIDATION STATUS FOR EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def build_external_validation_block(
    country: str,
    axis_scores: dict[int, float | None],
    external_data: dict[str, dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Build the external_validation block for country JSON export.

    This is the function that integrates into build_country_json()
    in export_snapshot.py.

    Args:
        country: ISO-2 code.
        axis_scores: {axis_id: score_or_None}.
        external_data: {benchmark_id: {country: value}} if available.

    Returns:
        Structured block for inclusion in country JSON.
    """
    alignment = assess_country_alignment(
        country=country,
        axis_scores=axis_scores,
        external_data=external_data,
    )

    # Compute benchmark coverage status
    from backend.benchmark_registry import get_benchmark_coverage_summary
    coverage = get_benchmark_coverage_summary()

    return {
        "overall_alignment": alignment["overall_alignment"],
        "n_axes_compared": alignment["n_axes_compared"],
        "n_axes_aligned": alignment["n_axes_aligned"],
        "n_axes_divergent": alignment["n_axes_divergent"],
        "weighted_alignment_score": alignment.get("weighted_alignment_score"),
        "authority_conflicts": alignment.get("authority_conflicts", []),
        "alignment_confidence": alignment.get("alignment_confidence", 0.0),
        "interpretation": alignment["overall_interpretation"],
        "benchmark_coverage": {
            "total_benchmarks_defined": coverage["total_benchmarks"],
            "total_integrated": coverage["n_integrated"],
            "total_structurally_defined": coverage["n_structurally_defined"],
        },
        "per_axis_summary": [
            {
                "axis_id": aa["axis_id"],
                "isi_score": aa["isi_score"],
                "alignment_status": aa.get("alignment_status", "UNKNOWN"),
                "n_benchmarks_available": aa["benchmarks_available"],
            }
            for aa in alignment["axis_alignments"]
        ],
        "honesty_note": alignment["honesty_note"],
        "empirical_grounding_answer": _empirical_grounding_answer(alignment),
    }


def _empirical_grounding_answer(alignment: dict[str, Any]) -> str:
    """Generate the explicit YES/NO answer to 'Does this align with reality?'

    This is the critical deliverable from SECTION 1.
    """
    overall = alignment.get("overall_alignment", AlignmentClass.NO_DATA)
    n_compared = alignment.get("n_axes_compared", 0)

    if overall == AlignmentClass.NO_DATA or n_compared == 0:
        return (
            "CANNOT ANSWER — no external benchmark data available for "
            "comparison. ISI output is internally consistent but NOT "
            "empirically validated."
        )
    if overall == AlignmentClass.STRONGLY_ALIGNED:
        return (
            f"YES — ISI output aligns with external benchmarks across "
            f"{n_compared} compared axes. Empirical grounding is "
            f"confirmed for the compared dimensions."
        )
    if overall == AlignmentClass.WEAKLY_ALIGNED:
        return (
            f"PARTIALLY — ISI output shows mixed alignment with "
            f"external benchmarks ({n_compared} axes compared). "
            f"Some dimensions are empirically grounded, others diverge."
        )
    if overall == AlignmentClass.DIVERGENT:
        return (
            f"NO — ISI output diverges from external benchmarks on "
            f"the majority of compared axes ({n_compared} compared). "
            f"This may indicate measurement issues OR genuine "
            f"construct differences."
        )
    if overall == AlignmentClass.STRUCTURALLY_INCOMPARABLE:
        return (
            "CANNOT ANSWER — insufficient overlap between ISI country "
            "universe and external benchmark coverage for meaningful "
            "comparison."
        )
    return f"UNKNOWN — alignment class '{overall}' not handled."


def _compute_weighted_alignment(
    axis_alignments: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], float]:
    """Compute authority-weighted alignment score and detect cross-tier conflicts.

    Returns:
        (weighted_alignment_info, authority_conflicts, alignment_confidence)
        weighted_alignment_info: dict with weighted_score, n_benchmarks_scored, weight_composition
        authority_conflicts: list of cross-tier contradiction records
        alignment_confidence: 0.0-1.0 confidence in the alignment assessment
    """
    alignment_values = {
        AlignmentClass.STRONGLY_ALIGNED: 1.0,
        AlignmentClass.WEAKLY_ALIGNED: 0.5,
        AlignmentClass.DIVERGENT: 0.0,
        AlignmentClass.STRUCTURALLY_INCOMPARABLE: None,  # excluded
        AlignmentClass.NO_DATA: None,  # excluded
    }

    weighted_sum = 0.0
    total_weight = 0.0
    conflicts: list[dict[str, Any]] = []

    # Collect all benchmark results with their authority levels
    tier_results: dict[str, list[dict[str, Any]]] = {
        BenchmarkAuthority.STRUCTURAL: [],
        BenchmarkAuthority.HIGH_CONFIDENCE: [],
        BenchmarkAuthority.SUPPORTING: [],
    }

    for aa in axis_alignments:
        for br in aa.get("benchmark_results", []):
            ac = br.get("alignment_class", AlignmentClass.NO_DATA)
            val = alignment_values.get(ac)
            if val is None:
                continue  # skip NO_DATA and STRUCTURALLY_INCOMPARABLE

            # Look up authority level from registry
            benchmark = get_benchmark_by_id(br.get("benchmark_id", ""))
            if benchmark is None:
                authority = BenchmarkAuthority.SUPPORTING
            else:
                authority = benchmark.get(
                    "authority_level", BenchmarkAuthority.SUPPORTING
                )

            weight = AUTHORITY_WEIGHTS.get(authority, 0.4)
            weighted_sum += val * weight
            total_weight += weight

            tier_results[authority].append({
                "benchmark_id": br.get("benchmark_id"),
                "axis_id": aa.get("axis_id"),
                "alignment_class": ac,
                "alignment_value": val,
                "authority": authority,
            })

    # Compute weighted score
    weighted_score = (
        round(weighted_sum / total_weight, 6) if total_weight > 0 else None
    )

    # Detect cross-tier contradictions
    structural_classes = {
        r["alignment_class"] for r in tier_results[BenchmarkAuthority.STRUCTURAL]
    }
    high_conf_classes = {
        r["alignment_class"] for r in tier_results[BenchmarkAuthority.HIGH_CONFIDENCE]
    }
    supporting_classes = {
        r["alignment_class"] for r in tier_results[BenchmarkAuthority.SUPPORTING]
    }

    # STRUCTURAL vs HIGH_CONFIDENCE contradiction → CRITICAL
    if (structural_classes & {AlignmentClass.STRONGLY_ALIGNED}
            and high_conf_classes & {AlignmentClass.DIVERGENT}):
        conflicts.append({
            "severity": "CRITICAL",
            "type": "STRUCTURAL_VS_HIGH_CONFIDENCE",
            "explanation": (
                "STRUCTURAL benchmarks show STRONGLY_ALIGNED but "
                "HIGH_CONFIDENCE benchmarks show DIVERGENT. This is a "
                "fundamental contradiction requiring investigation."
            ),
            "structural_classes": sorted(structural_classes),
            "high_confidence_classes": sorted(high_conf_classes),
        })
    if (structural_classes & {AlignmentClass.DIVERGENT}
            and high_conf_classes & {AlignmentClass.STRONGLY_ALIGNED}):
        conflicts.append({
            "severity": "CRITICAL",
            "type": "STRUCTURAL_VS_HIGH_CONFIDENCE",
            "explanation": (
                "STRUCTURAL benchmarks show DIVERGENT but "
                "HIGH_CONFIDENCE benchmarks show STRONGLY_ALIGNED. "
                "Structural divergence is more concerning than "
                "high-confidence alignment."
            ),
            "structural_classes": sorted(structural_classes),
            "high_confidence_classes": sorted(high_conf_classes),
        })

    # HIGH_CONFIDENCE vs SUPPORTING contradiction → WARNING
    if (high_conf_classes & {AlignmentClass.STRONGLY_ALIGNED}
            and supporting_classes & {AlignmentClass.DIVERGENT}):
        conflicts.append({
            "severity": "WARNING",
            "type": "HIGH_CONFIDENCE_VS_SUPPORTING",
            "explanation": (
                "HIGH_CONFIDENCE benchmarks show STRONGLY_ALIGNED but "
                "SUPPORTING benchmarks show DIVERGENT. Supporting "
                "benchmarks measure different constructs — divergence "
                "may be expected."
            ),
            "high_confidence_classes": sorted(high_conf_classes),
            "supporting_classes": sorted(supporting_classes),
        })
    if (high_conf_classes & {AlignmentClass.DIVERGENT}
            and supporting_classes & {AlignmentClass.STRONGLY_ALIGNED}):
        conflicts.append({
            "severity": "WARNING",
            "type": "HIGH_CONFIDENCE_VS_SUPPORTING",
            "explanation": (
                "HIGH_CONFIDENCE benchmarks show DIVERGENT but "
                "SUPPORTING benchmarks show STRONGLY_ALIGNED. "
                "High-confidence divergence is more concerning."
            ),
            "high_confidence_classes": sorted(high_conf_classes),
            "supporting_classes": sorted(supporting_classes),
        })

    # Alignment confidence: higher when more high-authority benchmarks compared
    n_structural = len(tier_results[BenchmarkAuthority.STRUCTURAL])
    n_high = len(tier_results[BenchmarkAuthority.HIGH_CONFIDENCE])
    n_supporting = len(tier_results[BenchmarkAuthority.SUPPORTING])
    n_total = n_structural + n_high + n_supporting

    if n_total == 0:
        alignment_confidence = 0.0
    else:
        # Weighted count: structural counts most
        conf_score = (
            n_structural * 1.0 + n_high * 0.7 + n_supporting * 0.4
        ) / (n_total * 1.0)  # normalize
        alignment_confidence = round(min(1.0, conf_score), 4)

    weighted_info: dict[str, Any] = {
        "weighted_score": weighted_score,
        "n_benchmarks_scored": n_total,
        "weight_composition": {
            BenchmarkAuthority.STRUCTURAL: AUTHORITY_WEIGHTS[BenchmarkAuthority.STRUCTURAL],
            BenchmarkAuthority.HIGH_CONFIDENCE: AUTHORITY_WEIGHTS[BenchmarkAuthority.HIGH_CONFIDENCE],
            BenchmarkAuthority.SUPPORTING: AUTHORITY_WEIGHTS[BenchmarkAuthority.SUPPORTING],
        },
        "tier_counts": {
            "structural": n_structural,
            "high_confidence": n_high,
            "supporting": n_supporting,
        },
    }

    return weighted_info, conflicts, alignment_confidence


# ═══════════════════════════════════════════════════════════════════════
# METRIC COMPUTATION FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def _compute_rank_correlation(
    isi_values: dict[str, float],
    external_values: dict[str, float],
    overlap_countries: list[str],
) -> dict[str, Any]:
    """Compute Spearman rank correlation between ISI and external values."""
    # Extract paired values
    isi_list = [isi_values[c] for c in overlap_countries]
    ext_list = [external_values[c] for c in overlap_countries]

    n = len(overlap_countries)
    if n < 3:
        return {
            "metric": None,
            "metric_name": "spearman_rho",
            "detail": f"Insufficient overlap ({n} < 3) for rank correlation",
        }

    # Compute ranks (handling ties with average ranks)
    isi_ranks = _compute_ranks(isi_list)
    ext_ranks = _compute_ranks(ext_list)

    # Spearman rho = 1 - 6*sum(d^2) / (n*(n^2-1))
    d_squared_sum = sum(
        (isi_ranks[i] - ext_ranks[i]) ** 2 for i in range(n)
    )

    if n == 1:
        rho = 1.0  # Single pair, trivially correlated
    else:
        rho = 1.0 - (6.0 * d_squared_sum) / (n * (n * n - 1.0))

    # Cap at [-1, 1] for numerical safety
    rho = max(-1.0, min(1.0, rho))

    # Per-country detail: rank difference
    per_country = []
    for i, c in enumerate(overlap_countries):
        per_country.append({
            "country": c,
            "isi_value": round(isi_list[i], 8),
            "external_value": round(ext_list[i], 8),
            "isi_rank": isi_ranks[i],
            "external_rank": ext_ranks[i],
            "rank_difference": abs(isi_ranks[i] - ext_ranks[i]),
        })

    return {
        "metric": round(rho, 6),
        "metric_name": "spearman_rho",
        "n_countries": n,
        "detail": (
            f"Spearman rank correlation = {rho:.4f} across {n} countries. "
            f"{'Positive correlation suggests aligned constructs.' if rho > 0 else 'Negative correlation suggests inverse constructs.'}"
        ),
        "per_country_detail": per_country,
    }


def _compute_structural_consistency(
    isi_values: dict[str, float],
    external_values: dict[str, float],
    overlap_countries: list[str],
) -> dict[str, Any]:
    """Check structural consistency between ISI and external values.

    Used for SIPRI MILEX cross-check: high external value + low ISI
    should be flagged as producer inversion.
    """
    inconsistencies: list[dict[str, Any]] = []

    for c in overlap_countries:
        isi_v = isi_values[c]
        ext_v = external_values[c]

        # High external (e.g., MILEX > 0.5 normalized) + low ISI (< 0.2)
        # suggests producer inversion
        if ext_v > 0.5 and isi_v < 0.2:
            inconsistencies.append({
                "country": c,
                "isi_value": round(isi_v, 8),
                "external_value": round(ext_v, 8),
                "flag": "POTENTIAL_PRODUCER_INVERSION",
                "detail": (
                    f"High external value ({ext_v:.3f}) but low ISI "
                    f"({isi_v:.3f}) — potential unregistered producer inversion"
                ),
            })

    n_inconsistent = len(inconsistencies)
    n_total = len(overlap_countries)
    consistency_rate = 1.0 - (n_inconsistent / n_total) if n_total > 0 else 0.0

    return {
        "metric": round(consistency_rate, 6),
        "metric_name": "structural_consistency_rate",
        "n_countries": n_total,
        "n_inconsistencies": n_inconsistent,
        "detail": (
            f"Structural consistency: {n_total - n_inconsistent}/{n_total} "
            f"countries are consistent. {n_inconsistent} show potential "
            f"producer inversion signals."
        ),
        "per_country_detail": inconsistencies,
    }


def _compute_directional_agreement(
    isi_values: dict[str, float],
    external_values: dict[str, float],
    overlap_countries: list[str],
) -> dict[str, Any]:
    """Check directional agreement: do ISI and external values agree on
    which countries are high vs low?

    Splits countries into quartiles and checks agreement.
    """
    n = len(overlap_countries)
    if n < 4:
        return {
            "metric": None,
            "metric_name": "directional_agreement_rate",
            "detail": f"Insufficient overlap ({n} < 4) for quartile analysis",
        }

    # Sort by ISI value, split into top and bottom halves
    isi_sorted = sorted(overlap_countries, key=lambda c: isi_values[c], reverse=True)
    ext_sorted = sorted(overlap_countries, key=lambda c: external_values[c], reverse=True)

    half = n // 2
    isi_top = set(isi_sorted[:half])
    ext_top = set(ext_sorted[:half])

    agreement = len(isi_top & ext_top)
    agreement_rate = agreement / half if half > 0 else 0.0

    return {
        "metric": round(agreement_rate, 6),
        "metric_name": "directional_agreement_rate",
        "n_countries": n,
        "detail": (
            f"Top-half directional agreement: {agreement}/{half} countries "
            f"({agreement_rate:.1%}) are in the top half of both ISI and "
            f"external rankings."
        ),
        "per_country_detail": [
            {
                "country": c,
                "isi_value": round(isi_values[c], 8),
                "external_value": round(external_values[c], 8),
                "isi_top_half": c in isi_top,
                "ext_top_half": c in ext_top,
                "agrees": (c in isi_top) == (c in ext_top),
            }
            for c in overlap_countries
        ],
    }


def _compute_level_comparison(
    isi_values: dict[str, float],
    external_values: dict[str, float],
    overlap_countries: list[str],
) -> dict[str, Any]:
    """Compare absolute levels between ISI and external values.

    Requires that both are on comparable scales (0-1).
    """
    diffs = []
    for c in overlap_countries:
        diff = abs(isi_values[c] - external_values[c])
        diffs.append(diff)

    mean_diff = sum(diffs) / len(diffs) if diffs else 0.0
    max_diff = max(diffs) if diffs else 0.0

    # Metric: 1 - mean absolute difference (higher = better alignment)
    metric = 1.0 - mean_diff

    return {
        "metric": round(metric, 6),
        "metric_name": "level_agreement",
        "n_countries": len(overlap_countries),
        "mean_absolute_difference": round(mean_diff, 6),
        "max_absolute_difference": round(max_diff, 6),
        "detail": (
            f"Level comparison: mean absolute difference = {mean_diff:.4f}, "
            f"max = {max_diff:.4f}. Level agreement = {metric:.4f}."
        ),
        "per_country_detail": [
            {
                "country": c,
                "isi_value": round(isi_values[c], 8),
                "external_value": round(external_values[c], 8),
                "absolute_difference": round(abs(isi_values[c] - external_values[c]), 8),
            }
            for c in overlap_countries
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _compute_ranks(values: list[float]) -> list[float]:
    """Compute ranks with average rank for ties."""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * n

    i = 0
    while i < n:
        # Find group of tied values
        j = i
        while j < n and indexed[j][1] == indexed[i][1]:
            j += 1
        # Average rank for this group
        avg_rank = sum(range(i + 1, j + 1)) / (j - i)
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j

    return ranks


def _classify_alignment(
    metric_value: float | None,
    strong_min: float,
    weak_min: float,
    comparison_type: str,
) -> str:
    """Classify alignment based on metric value and thresholds."""
    if metric_value is None:
        return AlignmentClass.NO_DATA

    # For structural consistency, metric is consistency rate
    # For rank correlation, use absolute value (direction is handled separately)
    if comparison_type == ComparisonType.RANK_CORRELATION:
        # Use absolute value — negative correlation is still alignment
        # (some benchmarks have inverse relationship)
        effective_metric = abs(metric_value)
    else:
        effective_metric = metric_value

    if effective_metric >= strong_min:
        return AlignmentClass.STRONGLY_ALIGNED
    if effective_metric >= weak_min:
        return AlignmentClass.WEAKLY_ALIGNED
    return AlignmentClass.DIVERGENT


def _no_data_result(
    benchmark_id: str,
    benchmark_name: str,
    reason: str,
) -> dict[str, Any]:
    """Construct a NO_DATA result."""
    return {
        "benchmark_id": benchmark_id,
        "benchmark_name": benchmark_name,
        "alignment_class": AlignmentClass.NO_DATA,
        "reason": reason,
        "honesty_note": (
            "No alignment assessment possible due to missing data. "
            "This is reported explicitly — NOT silently omitted."
        ),
    }


def _collect_all_isi_scores_for_axis(
    axis_id: int,
    axis_scores: dict[int, float | None],
    country: str,
) -> dict[str, float | None]:
    """Collect ISI scores for an axis across known countries.

    In the country-level assessment, we only have the scores for
    the specific country being assessed. For a proper rank
    correlation, we would need all countries' scores. Since we
    may only have single-country context, return what we have.
    """
    score = axis_scores.get(axis_id)
    if score is not None:
        return {country: score}
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION STATUS FOR API
# ═══════════════════════════════════════════════════════════════════════════

def get_external_validation_status() -> dict[str, Any]:
    """Return the current status of external validation integration.

    This provides a truthful answer to 'Is ISI externally validated?'
    """
    from backend.benchmark_registry import get_benchmark_coverage_summary

    coverage = get_benchmark_coverage_summary()
    n_integrated = coverage["n_integrated"]
    n_total = coverage["total_benchmarks"]

    if n_integrated == 0:
        status = "NOT_EXTERNALLY_VALIDATED"
        answer = (
            "NO — ISI is internally consistent but has ZERO integrated "
            "external benchmarks. External validation infrastructure "
            f"exists ({n_total} benchmarks defined) but no actual data "
            f"comparison has been performed."
        )
    elif n_integrated < 3:
        status = "MINIMALLY_VALIDATED"
        answer = (
            f"PARTIALLY — {n_integrated}/{n_total} benchmarks are "
            f"integrated with actual data. External validation is "
            f"preliminary."
        )
    elif n_integrated < n_total // 2:
        status = "PARTIALLY_VALIDATED"
        answer = (
            f"PARTIALLY — {n_integrated}/{n_total} benchmarks integrated. "
            f"External validation covers some axes but not all."
        )
    else:
        status = "SUBSTANTIALLY_VALIDATED"
        answer = (
            f"YES — {n_integrated}/{n_total} benchmarks integrated. "
            f"External validation covers the majority of ISI axes."
        )

    return {
        "validation_status": status,
        "does_this_align_with_reality": answer,
        "benchmark_coverage": coverage,
        "honesty_note": (
            "External validation tests construct overlap, not "
            "'correctness.' Even with full benchmark integration, "
            "ISI remains a model-based estimate with documented "
            "uncertainty."
        ),
    }
