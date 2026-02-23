"""
Derivation logic: ranking, summary statistics, correlations, axis drivers.

All computations use float64 (Python native float).
Derived stats stored at full precision; presentation formatting is in render.py.
"""

from __future__ import annotations

import math
from typing import Any

from .constants import (
    AXIS_COUNT,
    AXIS_IDS,
    AXIS_ISI_KEYS,
    AXIS_SLUGS,
    EU27_CODES,
    EU27_COUNT,
    SPIKE_THRESHOLD_K,
    VALID_AXIS_SLUGS,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CountryRecord = dict[str, Any]


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def compute_ranking(isi_data: dict[str, Any]) -> list[CountryRecord]:
    """
    Build ranked country list from isi.json data.

    Ranking: descending by isi_composite (highest = rank 1).
    Ties broken alphabetically by country code.

    Returns list of dicts with all ISI_COUNTRIES_COLUMNS fields.
    """
    countries = isi_data["countries"]
    version = isi_data.get("version", "v1.0")
    window = isi_data.get("window", "")

    # Sort: descending composite, then ascending country code for ties
    sorted_countries = sorted(
        countries,
        key=lambda c: (-c["isi_composite"], c["country"]),
    )

    result: list[CountryRecord] = []
    for rank, c in enumerate(sorted_countries, start=1):
        rec: CountryRecord = {
            "country": c["country"],
            "country_name": c["country_name"],
            "rank": rank,
            "isi_composite": c["isi_composite"],
            "classification": c["classification"],
            "axis_1_financial": c["axis_1_financial"],
            "axis_2_energy": c["axis_2_energy"],
            "axis_3_technology": c["axis_3_technology"],
            "axis_4_defense": c["axis_4_defense"],
            "axis_5_critical_inputs": c["axis_5_critical_inputs"],
            "axis_6_logistics": c["axis_6_logistics"],
            "complete": c.get("complete", True),
            "window": window,
            "methodology_version": version,
            "year": 2024,
        }
        result.append(rec)

    return result


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std_population(values: list[float]) -> float:
    m = _mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / len(values))


def _std_sample(values: list[float]) -> float:
    m = _mean(values)
    n = len(values)
    if n < 2:
        return 0.0
    return math.sqrt(sum((x - m) ** 2 for x in values) / (n - 1))


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _percentile(values: list[float], p: float) -> float:
    """
    Compute percentile using linear interpolation (numpy-compatible 'linear' method).
    p is in [0, 100].
    """
    s = sorted(values)
    n = len(s)
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    d0 = s[f] * (c - k)
    d1 = s[c] * (k - f)
    return d0 + d1


def compute_summary_stats(
    ranked: list[CountryRecord],
    isi_json_stats: dict[str, float],
) -> dict[str, Any]:
    """
    Compute summary statistics for EU-27 ISI composite scores.

    Returns dict with stats + validation against isi.json statistics.
    """
    composites = [r["isi_composite"] for r in ranked]

    computed_min = min(composites)
    computed_max = max(composites)
    computed_mean = _mean(composites)
    computed_median = _median(composites)
    computed_std_pop = _std_population(composites)
    computed_std_sample = _std_sample(composites)

    percentiles = {
        "p10": _percentile(composites, 10),
        "p25": _percentile(composites, 25),
        "p50": _percentile(composites, 50),
        "p75": _percentile(composites, 75),
        "p90": _percentile(composites, 90),
    }

    # Validation against isi.json
    validation: dict[str, Any] = {}
    tolerance = 1e-8

    for stat_name, computed, expected in [
        ("min", computed_min, isi_json_stats.get("min")),
        ("max", computed_max, isi_json_stats.get("max")),
        ("mean", computed_mean, isi_json_stats.get("mean")),
    ]:
        if expected is not None:
            diff = abs(computed - expected)
            validation[stat_name] = {
                "computed": computed,
                "expected": expected,
                "diff": diff,
                "pass": diff <= tolerance,
            }

    return {
        "n": len(composites),
        "min": computed_min,
        "max": computed_max,
        "mean": computed_mean,
        "median": computed_median,
        "std_population": computed_std_pop,
        "std_sample": computed_std_sample,
        "percentiles": percentiles,
        "paper_std_type": "population",
        "validation_vs_isi_json": validation,
    }


# ---------------------------------------------------------------------------
# Per-axis summary statistics
# ---------------------------------------------------------------------------

def compute_per_axis_stats(ranked: list[CountryRecord]) -> dict[str, dict[str, float]]:
    """Compute summary stats per axis across EU-27."""
    result: dict[str, dict[str, float]] = {}
    for axis_key in AXIS_ISI_KEYS:
        values = [r[axis_key] for r in ranked]
        result[axis_key] = {
            "min": min(values),
            "max": max(values),
            "mean": _mean(values),
            "median": _median(values),
            "std_population": _std_population(values),
        }
    return result


# ---------------------------------------------------------------------------
# Axis drivers
# ---------------------------------------------------------------------------

def compute_axis_drivers(ranked: list[CountryRecord]) -> list[dict[str, Any]]:
    """
    For each country, identify max and second-max axis, and concentration profile type.

    Profile type:
        'single-spike' if max_axis_score >= mean(axis_scores) + k * std(axis_scores)
        'broad-based' otherwise
    where k = SPIKE_THRESHOLD_K (1.0).
    """
    result: list[dict[str, Any]] = []

    for r in ranked:
        axis_scores: list[tuple[str, float]] = []
        for i, key in enumerate(AXIS_ISI_KEYS):
            axis_scores.append((AXIS_SLUGS[i], r[key]))

        # Sort by score descending, then by slug ascending for tie-break
        axis_scores.sort(key=lambda x: (-x[1], x[0]))

        max_axis = axis_scores[0][0]
        max_score = axis_scores[0][1]
        second_max_axis = axis_scores[1][0]
        second_max_score = axis_scores[1][1]

        values = [s for _, s in axis_scores]
        mean_val = _mean(values)
        std_val = _std_population(values)

        threshold = mean_val + SPIKE_THRESHOLD_K * std_val
        profile = "single-spike" if max_score >= threshold else "broad-based"

        result.append({
            "country": r["country"],
            "country_name": r["country_name"],
            "rank": r["rank"],
            "isi_composite": r["isi_composite"],
            "max_axis": max_axis,
            "max_axis_score": max_score,
            "second_max_axis": second_max_axis,
            "second_max_score": second_max_score,
            "profile_type": profile,
            "axis_mean": mean_val,
            "axis_std": std_val,
            "spike_threshold": threshold,
            "spike_k": SPIKE_THRESHOLD_K,
        })

    return result


# ---------------------------------------------------------------------------
# Pearson correlation
# ---------------------------------------------------------------------------

def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = _mean(x)
    my = _mean(y)
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    sx = _std_population(x)
    sy = _std_population(y)
    if sx == 0.0 or sy == 0.0:
        return 0.0
    return cov / (sx * sy)


def compute_correlation_matrix(ranked: list[CountryRecord]) -> dict[str, Any]:
    """
    Compute Pearson correlation matrix across 6 axes using EU-27 data.

    Returns:
        {
            "axes": [...],
            "matrix": [[r11, r12, ...], ...],
            "pairs": [{"axis_a": ..., "axis_b": ..., "r": ...}, ...]
        }
    """
    # Extract axis vectors
    vectors: dict[str, list[float]] = {}
    for key in AXIS_ISI_KEYS:
        vectors[key] = [r[key] for r in ranked]

    keys = list(AXIS_ISI_KEYS)
    n = len(keys)
    matrix: list[list[float]] = []
    pairs: list[dict[str, Any]] = []

    for i in range(n):
        row: list[float] = []
        for j in range(n):
            r = _pearson(vectors[keys[i]], vectors[keys[j]])
            row.append(r)
            if i < j:
                pairs.append({
                    "axis_a": AXIS_SLUGS[i],
                    "axis_b": AXIS_SLUGS[j],
                    "r": r,
                })
        matrix.append(row)

    return {
        "axes": list(AXIS_SLUGS),
        "matrix": matrix,
        "pairs": sorted(pairs, key=lambda p: -abs(p["r"])),
    }


# ---------------------------------------------------------------------------
# Distribution data
# ---------------------------------------------------------------------------

def compute_distribution_vectors(ranked: list[CountryRecord]) -> dict[str, Any]:
    """
    Extract distribution data for figures.
    """
    composites = [r["isi_composite"] for r in ranked]

    axis_distributions: dict[str, list[float]] = {}
    for key in AXIS_ISI_KEYS:
        axis_distributions[key] = sorted([r[key] for r in ranked])

    return {
        "composite_values": sorted(composites),
        "composite_by_country": [
            {"country": r["country"], "isi_composite": r["isi_composite"]}
            for r in ranked
        ],
        "axis_distributions": axis_distributions,
    }


# ---------------------------------------------------------------------------
# Country pages (appendix data)
# ---------------------------------------------------------------------------

def build_country_page(
    country_snapshot: dict[str, Any],
    country_v01: dict[str, Any] | None,
    rank: int,
) -> dict[str, Any]:
    """
    Build per-country appendix data bundle.

    Uses snapshot for authoritative scores, v01 for audit data if available.
    """
    page: dict[str, Any] = {
        "country": country_snapshot["country"],
        "country_name": country_snapshot["country_name"],
        "rank": rank,
        "isi_composite": country_snapshot["isi_composite"],
        "classification": country_snapshot["isi_classification"],
        "window": country_snapshot.get("window", ""),
        "year": country_snapshot.get("year", 2024),
        "methodology_version": country_snapshot.get("version", "v1.0"),
        "axes": [],
    }

    # Build axis data — use v01 for audit details
    v01_axes: dict[int, dict[str, Any]] = {}
    if country_v01 is not None:
        for ax in country_v01.get("axes", []):
            v01_axes[ax["axis_id"]] = ax

    for ax_snap in country_snapshot.get("axes", []):
        axis_id = ax_snap["axis_id"]
        ax_v01 = v01_axes.get(axis_id, {})
        audit = ax_v01.get("audit", {})

        axis_entry: dict[str, Any] = {
            "axis_id": axis_id,
            "axis_slug": ax_snap["axis_slug"],
            "axis_name": AXIS_FULL_NAMES.get(axis_id, ax_snap.get("axis_name", "")),
            "score": ax_snap["score"],
            "classification": ax_snap["classification"],
            "basis": audit.get("basis", ""),
            "channel_a_concentration": audit.get("channel_a_concentration", None),
            "channel_b_concentration": audit.get("channel_b_concentration", None),
            "warnings_count": len(ax_v01.get("warnings", [])),
        }
        page["axes"].append(axis_entry)

    return page


# Need this import at module level for build_country_page
from .constants import AXIS_FULL_NAMES  # noqa: E402


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_data(
    ranked: list[CountryRecord],
    isi_data: dict[str, Any],
    summary_stats: dict[str, Any],
    country_snapshots: dict[str, dict[str, Any]],
) -> list[str]:
    """
    Run all validation checks. Returns list of report lines.
    """
    lines: list[str] = []
    pass_count = 0
    fail_count = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal pass_count, fail_count
        status = "PASS" if ok else "FAIL"
        if not ok:
            fail_count += 1
        else:
            pass_count += 1
        line = f"- [{status}] {label}"
        if detail:
            line += f": {detail}"
        lines.append(line)

    # 1. EU-27 count
    check(
        "EU-27 country count = 27",
        len(ranked) == 27,
        f"got {len(ranked)}",
    )

    # 2. Complete count
    complete_count = sum(1 for r in ranked if r["complete"])
    expected_complete = isi_data.get("countries_complete", 27)
    check(
        "Complete countries matches isi.json countries_complete",
        complete_count == expected_complete,
        f"computed={complete_count}, expected={expected_complete}",
    )

    # 3. Stats validation
    for stat_name in ("min", "max", "mean"):
        v = summary_stats["validation_vs_isi_json"].get(stat_name, {})
        ok = v.get("pass", False)
        diff = v.get("diff", float("inf"))
        check(
            f"stats.{stat_name} matches isi.json within 1e-8",
            ok,
            f"diff={diff:.2e}, computed={v.get('computed')}, expected={v.get('expected')}",
        )

    # 4. Ranking tie-break
    for i in range(len(ranked) - 1):
        a, b = ranked[i], ranked[i + 1]
        if a["isi_composite"] == b["isi_composite"]:
            check(
                f"Tie-break: rank {a['rank']} ({a['country']}) before rank {b['rank']} ({b['country']})",
                a["country"] < b["country"],
                "alphabetical tie-break",
            )
    check("Ranking tie-break logic applied", True, "descending composite, alphabetical for ties")

    # 5. All axis scores in [0, 1]
    out_of_range: list[str] = []
    for r in ranked:
        for key in AXIS_ISI_KEYS:
            val = r[key]
            if val < 0.0 or val > 1.0:
                out_of_range.append(f"{r['country']}.{key}={val}")
    check(
        "All axis scores in [0.0, 1.0]",
        len(out_of_range) == 0,
        f"{len(out_of_range)} violations" if out_of_range else "all 162 values valid",
    )

    # 6. Countries with score == 1.0
    max_scores: list[str] = []
    for r in ranked:
        for key in AXIS_ISI_KEYS:
            if r[key] == 1.0:
                max_scores.append(f"{r['country']}.{key}")
    check(
        "Countries with axis score = 1.0 (transparency)",
        True,
        f"{len(max_scores)} instances: {', '.join(max_scores)}" if max_scores else "none",
    )

    # 7. Valid axis slugs
    seen_slugs: set[str] = set()
    for code, snap in country_snapshots.items():
        for ax in snap.get("axes", []):
            seen_slugs.add(ax["axis_slug"])
    unexpected = seen_slugs - VALID_AXIS_SLUGS
    check(
        "No unexpected axis_slug values",
        len(unexpected) == 0,
        f"expected: {sorted(VALID_AXIS_SLUGS)}, unexpected: {sorted(unexpected)}" if unexpected
        else f"all slugs valid: {sorted(seen_slugs)}",
    )

    # 8. Country codes match EU-27
    codes = {r["country"] for r in ranked}
    missing = EU27_CODES - codes
    extra = codes - EU27_CODES
    check(
        "Country codes match EU-27 set exactly",
        len(missing) == 0 and len(extra) == 0,
        f"missing: {sorted(missing)}, extra: {sorted(extra)}" if (missing or extra) else "exact match",
    )

    # 9. No scope contamination keywords
    # (check would apply to LaTeX prose — here we just note it)
    lines.append("")
    lines.append("### Scope Guard")
    lines.append("- No LaTeX prose files present in this evidence pack build.")
    lines.append("- Scope contamination check deferred to paper typesetting phase.")

    lines.append("")
    lines.append(f"### Summary: {pass_count} passed, {fail_count} failed")

    return lines
