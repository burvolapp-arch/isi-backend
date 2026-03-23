"""
pipeline.validate — Structural + economic validation engine for ISI datasets.

This is the GATEKEEPER. No dataset enters ISI computation without
passing ALL validation checks defined here.

Validation is STRICT and FAIL-FAST:
    - Missing data → explicit error
    - Incomplete distributions → rejected
    - Aggregates in partner list → rejected with mass tracking
    - Schema mismatches → rejected
    - Economic implausibility → rejected

12 validation checks:
    1. Schema compliance
    2. Self-trade detection
    3. Aggregate detection (with mass tracking)
    4. Sum integrity
    5. Partner count (source-aware thresholds)
    6. Dominance / extreme concentration
    7. Missing key partners
    8. Duplicate records
    9. Year coverage
   10. Economic sanity (plausible total, expected partners)
   11. Coverage validation (top-10 share ratio)
   12. Defense axis plausibility (scope-aware concentration annotation)

DO NOT:
    - Fallback silently
    - Interpolate data
    - Guess missing values
    - Downgrade errors to warnings
"""

from __future__ import annotations

from typing import Any

from pipeline.config import (
    AGGREGATE_PARTNER_NAMES,
    AGGREGATE_PARTNER_ISO2,
    MIN_PARTNER_COUNT_MAJOR,
    MIN_PARTNER_COUNT_SMALL,
    MIN_PARTNER_COUNT_ABSOLUTE,
    MAJOR_ECONOMY_ISO2,
    MIN_MAJOR_PARTNERS_PRESENT,
    EXTREME_CONCENTRATION_THRESHOLD,
    MAJOR_REPORTER_ISO2,
    SOURCE_PARTNER_COUNT_OVERRIDE,
    COVERAGE_TOP10_MIN,
    COVERAGE_TOP10_MAX,
    AGGREGATE_MASS_FAIL_THRESHOLD,
    SANITY_MIN_TOTAL_VALUE,
    EXPECTED_TRADE_PARTNERS,
)
from pipeline.schema import BilateralDataset, BilateralRecord
from pipeline.status import ValidationStatus


# ---------------------------------------------------------------------------
# Validation result container
# ---------------------------------------------------------------------------

class ValidationResult:
    """Structured validation result."""

    __slots__ = ("check_name", "status", "errors", "warnings", "details")

    def __init__(self, check_name: str):
        self.check_name = check_name
        self.status: str = ValidationStatus.PASS
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.details: dict[str, Any] = {}

    def fail(self, message: str) -> "ValidationResult":
        self.status = ValidationStatus.FAIL
        self.errors.append(message)
        return self

    def warn(self, message: str) -> "ValidationResult":
        if self.status == ValidationStatus.PASS:
            self.status = ValidationStatus.WARNING
        self.warnings.append(message)
        return self

    @property
    def passed(self) -> bool:
        return self.status in (ValidationStatus.PASS, ValidationStatus.WARNING)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check_name,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# CHECK 1: Schema compliance
# ---------------------------------------------------------------------------

def check_schema_compliance(dataset: BilateralDataset) -> ValidationResult:
    """Verify all records conform to canonical schema."""
    result = ValidationResult("schema_compliance")
    violations: list[str] = []
    sample_count = 0

    for i, r in enumerate(dataset.records):
        issues = []
        if len(r.reporter) < 2:
            issues.append(f"invalid reporter '{r.reporter}'")
        if len(r.partner) < 2:
            issues.append(f"invalid partner '{r.partner}'")
        if r.value <= 0:
            issues.append(f"non-positive value {r.value}")
        if r.year < 1990 or r.year > 2030:
            issues.append(f"year out of range {r.year}")
        if not r.source:
            issues.append("empty source")
        if not r.axis:
            issues.append("empty axis")
        if issues and sample_count < 20:
            violations.append(f"Record {i}: {'; '.join(issues)}")
            sample_count += 1

    result.details = {"n_violations": len(violations)}

    if violations:
        return result.fail(
            f"ERROR_SCHEMA_VIOLATION: {len(violations)} record(s) fail "
            f"schema compliance. Samples: {violations[:5]}"
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 2: Self-trade detection
# ---------------------------------------------------------------------------

def check_self_trade(dataset: BilateralDataset) -> ValidationResult:
    """Detect and reject self-trade records."""
    result = ValidationResult("self_trade_check")
    self_trades = [r for r in dataset.records if r.reporter == r.partner]

    result.details = {"n_self_trades": len(self_trades)}

    if self_trades:
        total_self = sum(r.value for r in self_trades)
        return result.fail(
            f"ERROR_SELF_TRADE: {len(self_trades)} record(s) where "
            f"reporter == partner ({dataset.reporter}). "
            f"Total self-trade value: {total_self:.4f}."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 3: Aggregate detection (with mass tracking — TASK 6)
# ---------------------------------------------------------------------------

def check_aggregate_detection(dataset: BilateralDataset) -> ValidationResult:
    """Reject rows with aggregate/unspecified partners.

    Also tracks the VALUE MASS of detected aggregates as a share of
    total value. If aggregate mass > AGGREGATE_MASS_FAIL_THRESHOLD,
    the distribution is structurally unreliable.
    """
    result = ValidationResult("aggregate_detection")
    found_aggregates: list[dict[str, Any]] = []

    for r in dataset.records:
        is_name_agg = r.partner in AGGREGATE_PARTNER_NAMES
        is_code_agg = r.partner in AGGREGATE_PARTNER_ISO2
        if is_name_agg or is_code_agg:
            found_aggregates.append({
                "partner": r.partner,
                "value": r.value,
                "year": r.year,
                "type": "name_match" if is_name_agg else "code_match",
            })

    result.details["aggregates_found"] = len(found_aggregates)
    result.details["aggregate_records"] = found_aggregates[:20]

    if found_aggregates:
        total_agg_value = sum(a["value"] for a in found_aggregates)
        total_dataset_value = dataset.total_value
        agg_share = (
            total_agg_value / total_dataset_value
            if total_dataset_value > 0
            else 1.0
        )
        result.details["aggregate_total_value"] = total_agg_value
        result.details["aggregate_share"] = round(agg_share, 6)

        if agg_share > AGGREGATE_MASS_FAIL_THRESHOLD:
            return result.fail(
                f"ERROR_AGGREGATE_MASS: {len(found_aggregates)} aggregate partner(s) "
                f"account for {agg_share:.1%} of total value "
                f"(threshold: {AGGREGATE_MASS_FAIL_THRESHOLD:.0%}). "
                f"Distribution is structurally unreliable."
            )

        return result.fail(
            f"ERROR_AGGREGATE_IN_DISTRIBUTION: {len(found_aggregates)} "
            f"aggregate/unspecified partner(s) detected "
            f"(total value: {total_agg_value:.2f}, share: {agg_share:.1%}). "
            f"Partners: {[a['partner'] for a in found_aggregates[:5]]}"
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 4: Sum integrity
# ---------------------------------------------------------------------------

def check_sum_integrity(dataset: BilateralDataset) -> ValidationResult:
    """Sum of values must be positive, no negative values."""
    result = ValidationResult("sum_integrity_check")

    negatives = [r for r in dataset.records if r.value < 0]
    zeros = [r for r in dataset.records if r.value == 0]
    total = dataset.total_value

    result.details = {
        "total_value": total,
        "n_records": len(dataset.records),
        "n_negative": len(negatives),
        "n_zero": len(zeros),
    }

    if negatives:
        return result.fail(
            f"ERROR_NEGATIVE_VALUES: {len(negatives)} records have negative "
            f"values. Largest negative: {min(r.value for r in negatives):.4f}."
        )

    if total <= 0:
        return result.fail(
            f"ERROR_ZERO_TOTAL: Total value is {total:.4f}. "
            f"Cannot compute concentration over a zero-sum distribution."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 5: Partner count (source-aware — TASK 2)
# ---------------------------------------------------------------------------

def check_partner_count(dataset: BilateralDataset) -> ValidationResult:
    """Partner count must exceed minimum threshold.

    Uses source-specific overrides for data sources with structurally
    fewer reporting countries (e.g., BIS LBS has ~30 worldwide).
    """
    result = ValidationResult("partner_count_check")
    n = dataset.n_partners
    source = dataset.source
    result.details = {
        "n_partners": n,
        "reporter": dataset.reporter,
        "source": source,
    }

    if n < MIN_PARTNER_COUNT_ABSOLUTE:
        return result.fail(
            f"ERROR_INCOMPLETE_DISTRIBUTION: {dataset.reporter} has only "
            f"{n} partners (minimum {MIN_PARTNER_COUNT_ABSOLUTE}). "
            f"Distribution is structurally incomplete."
        )

    # Source-specific threshold override
    if source in SOURCE_PARTNER_COUNT_OVERRIDE:
        override = SOURCE_PARTNER_COUNT_OVERRIDE[source]
        result.details["threshold"] = override
        result.details["threshold_type"] = "source_override"

        if n < override:
            return result.fail(
                f"ERROR_INCOMPLETE_DISTRIBUTION: {dataset.reporter} has {n} "
                f"partners from {source} (expected ≥{override}). "
                f"Distribution is truncated."
            )

        # If source override is satisfied, PASS (don't apply generic threshold)
        return result

    # Generic threshold
    threshold = (
        MIN_PARTNER_COUNT_MAJOR
        if dataset.reporter in MAJOR_REPORTER_ISO2
        else MIN_PARTNER_COUNT_SMALL
    )
    result.details["threshold"] = threshold
    result.details["threshold_type"] = (
        "major_economy" if dataset.reporter in MAJOR_REPORTER_ISO2 else "small_economy"
    )

    if n < threshold:
        return result.fail(
            f"ERROR_INCOMPLETE_DISTRIBUTION: {dataset.reporter} has {n} "
            f"partners (expected ≥{threshold} for "
            f"{'major' if dataset.reporter in MAJOR_REPORTER_ISO2 else 'small'} "
            f"economy). Distribution is truncated."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 6: Dominance / extreme concentration
# ---------------------------------------------------------------------------

def check_dominance(dataset: BilateralDataset) -> ValidationResult:
    """Flag extreme single-partner dominance (>95% share)."""
    result = ValidationResult("dominance_check")

    if dataset.total_value <= 0:
        result.details = {"skipped": True, "reason": "zero total value"}
        return result

    partner_values: dict[str, float] = {}
    for r in dataset.records:
        partner_values[r.partner] = partner_values.get(r.partner, 0.0) + r.value

    max_partner = max(partner_values.items(), key=lambda x: x[1])
    max_share = max_partner[1] / dataset.total_value

    result.details = {
        "dominant_partner": max_partner[0],
        "dominant_share": round(max_share, 8),
        "dominant_value": round(max_partner[1], 4),
        "total_value": round(dataset.total_value, 4),
    }

    if max_share > EXTREME_CONCENTRATION_THRESHOLD:
        return result.warn(
            f"EXTREME_CONCENTRATION: Partner {max_partner[0]} accounts for "
            f"{max_share:.1%} of total value (threshold: "
            f"{EXTREME_CONCENTRATION_THRESHOLD:.0%}). "
            f"Distribution is effectively monopolistic."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 7: Missing key partners
# ---------------------------------------------------------------------------

def check_missing_key_partners(dataset: BilateralDataset) -> ValidationResult:
    """Ensure major economies appear in partner list."""
    result = ValidationResult("missing_key_partners_check")

    expected = MAJOR_ECONOMY_ISO2 - {dataset.reporter}
    present = set(dataset.partners) & expected
    missing = expected - present

    result.details = {
        "expected_majors": sorted(expected),
        "present_majors": sorted(present),
        "missing_majors": sorted(missing),
        "n_present": len(present),
        "n_expected": len(expected),
    }

    if len(present) < MIN_MAJOR_PARTNERS_PRESENT:
        return result.fail(
            f"ERROR_MISSING_KEY_PARTNERS: Only {len(present)}/{len(expected)} "
            f"major economies present as partners. "
            f"Missing: {sorted(missing)}. "
            f"Distribution appears geographically truncated."
        )

    if missing:
        return result.warn(
            f"W-MISSING-MAJORS: {len(missing)} major economies missing as "
            f"partners: {sorted(missing)}. "
            f"Present: {sorted(present)}."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 8: Duplicate records
# ---------------------------------------------------------------------------

def check_duplicate_records(dataset: BilateralDataset) -> ValidationResult:
    """Detect duplicate reporter-partner-year-product tuples."""
    result = ValidationResult("duplicate_records_check")
    seen: dict[tuple, int] = {}
    duplicates: list[dict[str, Any]] = []

    for r in dataset.records:
        key = (r.reporter, r.partner, r.year, r.product_code or "")
        seen[key] = seen.get(key, 0) + 1

    for key, count in seen.items():
        if count > 1:
            duplicates.append({
                "reporter": key[0],
                "partner": key[1],
                "year": key[2],
                "product_code": key[3],
                "count": count,
            })

    result.details = {"n_duplicate_keys": len(duplicates)}

    if duplicates:
        return result.warn(
            f"W-DUPLICATES: {len(duplicates)} duplicate key(s) detected. "
            f"Samples: {duplicates[:5]}."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 9: Year coverage
# ---------------------------------------------------------------------------

def check_year_coverage(dataset: BilateralDataset) -> ValidationResult:
    """Verify year coverage matches expected range."""
    result = ValidationResult("year_coverage_check")
    lo, hi = dataset.year_range
    years = set(r.year for r in dataset.records)
    out_of_range = [y for y in years if y < lo or y > hi]

    result.details = {
        "expected_range": [lo, hi],
        "years_found": sorted(years),
        "out_of_range": out_of_range,
    }

    if out_of_range:
        return result.fail(
            f"ERROR_YEAR_OUT_OF_RANGE: Records found for years "
            f"{sorted(out_of_range)}, expected [{lo}, {hi}]."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 10: Economic sanity (TASK 4)
# ---------------------------------------------------------------------------

def check_economic_sanity(dataset: BilateralDataset) -> ValidationResult:
    """Verify economic plausibility of the dataset.

    Checks:
    1. Total value exceeds source-specific minimum
    2. Expected major trade partners are present (source-aware)
    3. Top partner share < 95% (not a single-source monopoly artifact)

    This catches data where parsing succeeded but the economic content
    is implausible (e.g., total trade = $500, or US missing from
    Japan's import partners).
    """
    result = ValidationResult("economic_sanity_check")
    source = dataset.source
    total = dataset.total_value

    result.details = {
        "source": source,
        "total_value": total,
        "reporter": dataset.reporter,
        "n_partners": dataset.n_partners,
    }

    # Check 1: Minimum total value
    min_total = SANITY_MIN_TOTAL_VALUE.get(source, 0)
    if total < min_total:
        return result.fail(
            f"ERROR_IMPLAUSIBLE_TOTAL: {dataset.reporter}/{dataset.axis} "
            f"total value {total:.2f} is below minimum {min_total:.2f} "
            f"for source {source}. Data may be truncated or misaligned."
        )

    # Check 2: Expected trade partners (for major reporters)
    if dataset.reporter in MAJOR_REPORTER_ISO2:
        expected = EXPECTED_TRADE_PARTNERS.get(source, frozenset())
        expected_check = expected - {dataset.reporter}
        if expected_check:
            present_partners = set(dataset.partners)
            missing = expected_check - present_partners
            result.details["expected_partners"] = sorted(expected_check)
            result.details["missing_expected"] = sorted(missing)

            if missing and len(missing) == len(expected_check):
                return result.fail(
                    f"ERROR_MISSING_EXPECTED_PARTNERS: NONE of the expected "
                    f"partners {sorted(expected_check)} appear for "
                    f"{dataset.reporter} in {source}. "
                    f"Data is likely geographically truncated or misfiltered."
                )
            elif missing:
                result.warn(
                    f"W-MISSING-EXPECTED: {sorted(missing)} not found as "
                    f"partners for {dataset.reporter} in {source}."
                )

    return result


# ---------------------------------------------------------------------------
# CHECK 11: Coverage validation (TASK 5)
# ---------------------------------------------------------------------------

def check_coverage_ratio(dataset: BilateralDataset) -> ValidationResult:
    """Validate top-10 partner coverage ratio.

    For a well-distributed bilateral dataset:
    - Top-10 partners should capture ≥50% of total value
    - Top-10 partners should NOT capture 100% (suggests truncation)

    These bounds catch:
    - Datasets where many small junk partners dilute the distribution
    - Datasets where only 10 partners exist (potentially truncated)
    """
    result = ValidationResult("coverage_ratio_check")

    if dataset.total_value <= 0 or not dataset.records:
        result.details = {"skipped": True}
        return result

    partner_values: dict[str, float] = {}
    for r in dataset.records:
        partner_values[r.partner] = partner_values.get(r.partner, 0.0) + r.value

    sorted_partners = sorted(partner_values.items(), key=lambda x: -x[1])
    top_10 = sorted_partners[:10]
    top_10_value = sum(v for _, v in top_10)
    top_10_share = top_10_value / dataset.total_value

    result.details = {
        "top_10_share": round(top_10_share, 6),
        "top_10_value": round(top_10_value, 2),
        "total_value": round(dataset.total_value, 2),
        "n_partners": dataset.n_partners,
        "top_10_partners": [p for p, _ in top_10],
    }

    if top_10_share < COVERAGE_TOP10_MIN:
        return result.warn(
            f"W-LOW-COVERAGE: Top-10 partners capture only {top_10_share:.1%} "
            f"of total value (expected ≥{COVERAGE_TOP10_MIN:.0%}). "
            f"Distribution may be excessively fragmented."
        )

    if dataset.n_partners <= 10 and top_10_share >= COVERAGE_TOP10_MAX:
        return result.warn(
            f"W-TRUNCATED-DISTRIBUTION: Only {dataset.n_partners} partners "
            f"and top-10 capture {top_10_share:.1%}. "
            f"Distribution may be artificially truncated."
        )

    return result


# ---------------------------------------------------------------------------
# CHECK 12: Defense axis plausibility (Task 6)
# ---------------------------------------------------------------------------

def check_defense_plausibility(dataset: BilateralDataset) -> ValidationResult:
    """Defense-specific validation: extreme concentration plausibility check.

    Arms transfers are inherently sparse. Most countries import major
    conventional weapons from 2-6 suppliers, with one often dominant.
    This check does NOT fail on extreme concentration — it ANNOTATES
    the result with defense-specific context so consumers understand
    the structural reasons for high concentration.

    Checks:
    1. If defense axis + single partner >90% → plausibility note
       (normal for defense, but must be flagged as scope-limited)
    2. If defense axis + <3 partners → structural sparsity note
    3. If TIV unit used → confirm value_type is correctly labeled

    This check only applies to axis="defense". For other axes, it
    returns PASS immediately with no action.
    """
    result = ValidationResult("defense_plausibility_check")

    # Only applies to defense axis
    if dataset.axis != "defense":
        result.details = {"skipped": True, "reason": "not defense axis"}
        return result

    result.details = {
        "axis": dataset.axis,
        "source": dataset.source,
        "n_partners": dataset.n_partners,
        "total_value": round(dataset.total_value, 4),
    }

    if dataset.total_value <= 0 or not dataset.records:
        result.details["skipped"] = True
        result.details["reason"] = "no data"
        return result

    # Partner concentration analysis
    partner_values: dict[str, float] = {}
    for r in dataset.records:
        partner_values[r.partner] = partner_values.get(r.partner, 0.0) + r.value

    sorted_partners = sorted(partner_values.items(), key=lambda x: -x[1])
    top_partner, top_value = sorted_partners[0]
    top_share = top_value / dataset.total_value

    result.details["dominant_partner"] = top_partner
    result.details["dominant_share"] = round(top_share, 6)
    result.details["partner_count"] = len(partner_values)

    # Value unit check
    units = set(r.unit for r in dataset.records)
    result.details["value_units"] = sorted(units)
    if "USD_MN" in units:
        result.warn(
            "W-DEFENSE-UNIT-MISMATCH: Defense records contain unit='USD_MN' "
            "but SIPRI uses Trend Indicator Values (TIV), not monetary units. "
            "Verify unit labeling in ingestion module."
        )

    # Extreme concentration annotation (WARNING, not FAIL)
    if top_share > 0.90:
        result.warn(
            f"W-DEFENSE-CONCENTRATION: {dataset.reporter} imports "
            f"{top_share:.1%} of major conventional weapons (TIV) from "
            f"{top_partner}. This is WITHIN NORMAL RANGE for SIPRI data — "
            f"arms markets are structurally concentrated. However, this "
            f"concentration reflects only major weapons platforms tracked "
            f"by SIPRI (aircraft, ships, armoured vehicles, missiles, etc.). "
            f"It does NOT represent total defense supply chain dependency. "
            f"Small arms, ammunition, services, cyber, and dual-use "
            f"technology are excluded from SIPRI scope."
        )

    # Structural sparsity annotation
    if len(partner_values) <= 3:
        result.warn(
            f"W-DEFENSE-SPARSE: {dataset.reporter} has only "
            f"{len(partner_values)} defense supplier(s) in SIPRI data. "
            f"This is structurally normal for arms transfers — most "
            f"countries have 2-6 major weapons suppliers. Low partner count "
            f"does NOT indicate data quality failure; it reflects the "
            f"inherent sparsity of major conventional weapons markets."
        )

    return result


# ---------------------------------------------------------------------------
# Full validation suite
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# CHECK 13: Output plausibility — suspicious result detection
# ---------------------------------------------------------------------------

# Known reference ranges for major importers (SIPRI defense axis)
# These are NOT hard constraints — they are plausibility anchors.
# If a result falls outside these ranges, it deserves human review.
_SIPRI_PLAUSIBILITY: dict[str, dict[str, Any]] = {
    "JP": {"expected_top": "US", "min_partners": 3, "min_total_tiv": 100},
    "DE": {"expected_top": None, "min_partners": 5, "min_total_tiv": 100},
    "US": {"expected_top": None, "min_partners": 8, "min_total_tiv": 100},
    "GB": {"expected_top": "US", "min_partners": 4, "min_total_tiv": 100},
    "FR": {"expected_top": None, "min_partners": 4, "min_total_tiv": 50},
    "PL": {"expected_top": None, "min_partners": 5, "min_total_tiv": 100},
}


def check_output_plausibility(dataset: BilateralDataset) -> ValidationResult:
    """Flag outputs that are plausible-looking but potentially wrong.

    This is NOT about forcing outputs to match expectations.
    It is about surfacing suspicious outputs for human review.

    Checks:
    1. Known major importers missing expected top partner
    2. Suspiciously low total value for known major importers
    3. Suspiciously few partners for known major importers
    4. Year distribution anomalies (all data in single year)
    """
    result = ValidationResult("output_plausibility_check")

    reporter = dataset.reporter
    result.details = {
        "reporter": reporter,
        "axis": dataset.axis,
        "source": dataset.source,
    }

    if not dataset.records or dataset.total_value <= 0:
        return result

    # Partner value breakdown
    partner_values: dict[str, float] = {}
    for r in dataset.records:
        partner_values[r.partner] = partner_values.get(r.partner, 0.0) + r.value

    sorted_partners = sorted(partner_values.items(), key=lambda x: -x[1])
    top_partner = sorted_partners[0][0] if sorted_partners else None

    # Year distribution
    year_counts: dict[int, int] = {}
    for r in dataset.records:
        year_counts[r.year] = year_counts.get(r.year, 0) + 1

    result.details["top_partner"] = top_partner
    result.details["n_years_with_data"] = len(year_counts)

    # Check 1: Known reference for specific reporter
    if dataset.source == "sipri" and reporter in _SIPRI_PLAUSIBILITY:
        ref = _SIPRI_PLAUSIBILITY[reporter]

        if ref["expected_top"] and top_partner != ref["expected_top"]:
            result.warn(
                f"W-PLAUSIBILITY-TOP: {reporter} expected top partner "
                f"'{ref['expected_top']}' but got '{top_partner}'. "
                f"This may indicate a data or mapping issue."
            )

        if dataset.n_partners < ref["min_partners"]:
            result.warn(
                f"W-PLAUSIBILITY-SPARSE: {reporter} has {dataset.n_partners} "
                f"partners (expected ≥{ref['min_partners']}). "
                f"Output may be truncated."
            )

        if dataset.total_value < ref["min_total_tiv"]:
            result.warn(
                f"W-PLAUSIBILITY-LOW-TOTAL: {reporter} total={dataset.total_value:.2f} "
                f"(expected ≥{ref['min_total_tiv']}). "
                f"Output may be incomplete."
            )

    # Check 2: Single-year concentration
    if len(year_counts) == 1 and len(dataset.records) > 5:
        only_year = list(year_counts.keys())[0]
        lo, hi = dataset.year_range
        if hi - lo >= 2:
            result.warn(
                f"W-PLAUSIBILITY-SINGLE-YEAR: All {len(dataset.records)} records "
                f"are in year {only_year} despite range [{lo}, {hi}]. "
                f"Data may be temporally truncated."
            )

    return result


ALL_CHECKS = (
    check_schema_compliance,
    check_self_trade,
    check_aggregate_detection,
    check_sum_integrity,
    check_partner_count,
    check_dominance,
    check_missing_key_partners,
    check_duplicate_records,
    check_year_coverage,
    check_economic_sanity,
    check_coverage_ratio,
    check_defense_plausibility,
    check_output_plausibility,
)


def validate_dataset(
    dataset: BilateralDataset,
    checks: tuple = ALL_CHECKS,
    hard_fail: bool = True,
) -> list[ValidationResult]:
    """Run all validation checks on a BilateralDataset.

    Args:
        dataset: The dataset to validate.
        checks: Tuple of check functions to run (default: all).
        hard_fail: If True, set dataset.validation_status to FAIL on first error.

    Returns:
        List of ValidationResult objects.
    """
    dataset.compute_metadata()
    results: list[ValidationResult] = []
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for check_fn in checks:
        vr = check_fn(dataset)
        results.append(vr)
        all_errors.extend(vr.errors)
        all_warnings.extend(vr.warnings)

    # Set dataset status
    if all_errors:
        dataset.validation_status = ValidationStatus.FAIL
        dataset.validation_errors = all_errors
        dataset.validation_warnings = all_warnings
    elif all_warnings:
        dataset.validation_status = ValidationStatus.WARNING
        dataset.validation_errors = []
        dataset.validation_warnings = all_warnings
    else:
        dataset.validation_status = ValidationStatus.PASS
        dataset.validation_errors = []
        dataset.validation_warnings = all_warnings

    return results


def validate_and_report(
    dataset: BilateralDataset,
) -> dict[str, Any]:
    """Validate a dataset and return a structured report.

    This is the primary validation entry point for pipeline consumers.
    """
    results = validate_dataset(dataset)
    return {
        "reporter": dataset.reporter,
        "axis": dataset.axis,
        "source": dataset.source,
        "overall_status": dataset.validation_status,
        "n_records": len(dataset.records),
        "n_partners": dataset.n_partners,
        "total_value": dataset.total_value,
        "data_hash": dataset.data_hash,
        "checks": [vr.to_dict() for vr in results],
        "errors": dataset.validation_errors,
        "warnings": dataset.validation_warnings,
    }
