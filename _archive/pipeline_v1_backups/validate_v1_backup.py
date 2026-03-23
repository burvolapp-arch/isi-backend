"""
pipeline.validate — Structural validation engine for ISI datasets.

This is the GATEKEEPER. No dataset enters ISI computation without
passing ALL validation checks defined here.

Validation is STRICT and FAIL-FAST:
    - Missing data → explicit error
    - Incomplete distributions → rejected
    - Aggregates in partner list → rejected
    - Schema mismatches → rejected
    - Missing critical fields → rejected

DO NOT:
    - Fallback silently
    - Interpolate data
    - Guess missing values
    - Downgrade errors to warnings

Every validation function returns a structured result with:
    - status: PASS / FAIL / WARNING
    - errors: list of error messages (empty if PASS)
    - warnings: list of warning messages
    - details: supporting evidence for the decision
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
)
from pipeline.schema import BilateralDataset, BilateralRecord


# ---------------------------------------------------------------------------
# Validation result container
# ---------------------------------------------------------------------------

class ValidationResult:
    """Structured validation result."""

    __slots__ = ("check_name", "status", "errors", "warnings", "details")

    def __init__(self, check_name: str):
        self.check_name = check_name
        self.status: str = "PASS"
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.details: dict[str, Any] = {}

    def fail(self, message: str) -> "ValidationResult":
        self.status = "FAIL"
        self.errors.append(message)
        return self

    def warn(self, message: str) -> "ValidationResult":
        if self.status == "PASS":
            self.status = "WARNING"
        self.warnings.append(message)
        return self

    @property
    def passed(self) -> bool:
        return self.status in ("PASS", "WARNING")

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check_name,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Individual validation checks
# ---------------------------------------------------------------------------

def check_partner_count(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 1: Partner count must exceed minimum threshold.

    Major economies (G7 + large):  ≥ 20 partners
    Other economies:               ≥ 10 partners
    Absolute minimum:              ≥ 3 partners

    Rationale: Concentration indices (HHI) over fewer than 3 partners
    are meaningless. Even a "valid" HHI over 5 partners captures only
    the visible portion of the distribution.
    """
    result = ValidationResult("partner_count_check")
    n = dataset.n_partners
    result.details = {"n_partners": n, "reporter": dataset.reporter}

    if n < MIN_PARTNER_COUNT_ABSOLUTE:
        return result.fail(
            f"ERROR_INCOMPLETE_DISTRIBUTION: {dataset.reporter} has only "
            f"{n} partners (minimum {MIN_PARTNER_COUNT_ABSOLUTE}). "
            f"Distribution is structurally incomplete."
        )

    threshold = (
        MIN_PARTNER_COUNT_MAJOR
        if dataset.reporter in MAJOR_REPORTER_ISO2
        else MIN_PARTNER_COUNT_SMALL
    )
    result.details["threshold"] = threshold

    if n < threshold:
        return result.fail(
            f"ERROR_INCOMPLETE_DISTRIBUTION: {dataset.reporter} has {n} "
            f"partners (expected ≥{threshold} for "
            f"{'major' if dataset.reporter in MAJOR_REPORTER_ISO2 else 'small'} "
            f"economy). Distribution is truncated."
        )

    return result


def check_aggregate_detection(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 2: Reject rows with aggregate/unspecified partners.

    Aggregates like "World", "Other", "Not Specified" are NOT bilateral
    partners. Their presence means the distribution is not fully
    disaggregated and concentration measures would be biased.
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
    result.details["aggregate_records"] = found_aggregates[:20]  # cap detail

    if found_aggregates:
        total_agg_value = sum(a["value"] for a in found_aggregates)
        result.details["aggregate_total_value"] = total_agg_value
        return result.fail(
            f"ERROR_AGGREGATE_IN_DISTRIBUTION: {len(found_aggregates)} "
            f"aggregate/unspecified partner(s) detected "
            f"(total value: {total_agg_value:.2f}). "
            f"Partners: {[a['partner'] for a in found_aggregates[:5]]}"
        )

    return result


def check_sum_integrity(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 3: Sum of values must be positive, no negative values.

    A bilateral distribution with zero or negative total value is
    structurally invalid — it means no trade/investment was recorded.
    Individual negative values indicate data quality issues upstream.
    """
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
            f"values. Largest negative: {min(r.value for r in negatives):.4f}. "
            f"Raw bilateral data must be non-negative."
        )

    if total <= 0:
        return result.fail(
            f"ERROR_ZERO_TOTAL: Total value is {total:.4f}. "
            f"Cannot compute concentration over a zero-sum distribution."
        )

    return result


def check_dominance(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 4: Flag extreme single-partner dominance.

    If a single partner accounts for >95% of total value, the
    distribution is effectively a monopoly. This is flagged as
    EXTREME_CONCENTRATION — valid data, but requires interpretation.

    This is a WARNING, not an error: the data is structurally valid,
    but the resulting HHI will be near 1.0 by construction.
    """
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


def check_missing_key_partners(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 5: Ensure major economies appear in partner list.

    For a global bilateral distribution, the absence of US, CN, DE, etc.
    as trade partners suggests the data is geographically truncated.

    At least MIN_MAJOR_PARTNERS_PRESENT of MAJOR_ECONOMY_ISO2 must appear.
    The reporter itself is excluded from the check (a country doesn't
    trade with itself).
    """
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


def check_schema_compliance(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 6: Verify all records conform to canonical schema.

    Every record must have:
    - non-empty reporter (ISO-2)
    - non-empty partner (ISO-2)
    - value > 0
    - valid year
    - non-empty source
    - non-empty axis

    This is a structural integrity check, not a data quality check.
    """
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


def check_self_trade(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 7: Detect and reject self-trade records.

    A country trading with itself is an artifact of data preparation.
    These records inflate the distribution and distort HHI.
    """
    result = ValidationResult("self_trade_check")
    self_trades = [r for r in dataset.records if r.reporter == r.partner]

    result.details = {"n_self_trades": len(self_trades)}

    if self_trades:
        total_self = sum(r.value for r in self_trades)
        return result.fail(
            f"ERROR_SELF_TRADE: {len(self_trades)} record(s) where "
            f"reporter == partner ({dataset.reporter}). "
            f"Total self-trade value: {total_self:.4f}. "
            f"These must be removed before concentration computation."
        )

    return result


def check_duplicate_records(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 8: Detect duplicate reporter-partner-year-product tuples.

    Duplicates indicate upstream parsing issues. They must be resolved
    explicitly (aggregated or deduplicated) — never silently ignored.
    """
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
            f"Samples: {duplicates[:5]}. "
            f"These should be aggregated during staging."
        )

    return result


def check_year_coverage(dataset: BilateralDataset) -> ValidationResult:
    """CHECK 9: Verify year coverage matches expected range.

    All records should fall within the declared year range.
    Records outside the range indicate data misalignment.
    """
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
# Full validation suite
# ---------------------------------------------------------------------------

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
        dataset.validation_status = "FAIL"
        dataset.validation_errors = all_errors
        dataset.validation_warnings = all_warnings
    elif all_warnings:
        dataset.validation_status = "WARNING"
        dataset.validation_errors = []
        dataset.validation_warnings = all_warnings
    else:
        dataset.validation_status = "PASS"
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
