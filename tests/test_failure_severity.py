"""
tests/test_failure_severity.py — Tests for FailureSeverity Model

Verifies:
    1. FailureSeverity enum has exactly 5 values.
    2. Severity ordering is correct.
    3. worst_severity() returns the most severe.
    4. severity_at_least() compares correctly.
    5. classify_layer_failure() classifies correctly.
    6. Serialization works.
"""

from __future__ import annotations

import unittest

from backend.failure_severity import (
    FailureSeverity,
    VALID_FAILURE_SEVERITIES,
    SEVERITY_ORDER,
    CONSEQUENTIAL_SEVERITIES,
    EXPORT_BLOCKING_SEVERITIES,
    worst_severity,
    severity_at_least,
    classify_layer_failure,
    severity_to_dict,
)


class TestFailureSeverityEnum(unittest.TestCase):
    """FailureSeverity enum tests."""

    def test_has_five_values(self):
        self.assertEqual(len(FailureSeverity), 5)

    def test_all_values_in_valid_set(self):
        for sev in FailureSeverity:
            self.assertIn(sev, VALID_FAILURE_SEVERITIES)

    def test_info_value(self):
        self.assertEqual(FailureSeverity.INFO.value, "INFO")

    def test_warning_value(self):
        self.assertEqual(FailureSeverity.WARNING.value, "WARNING")

    def test_error_value(self):
        self.assertEqual(FailureSeverity.ERROR.value, "ERROR")

    def test_critical_value(self):
        self.assertEqual(FailureSeverity.CRITICAL.value, "CRITICAL")

    def test_invalidating_value(self):
        self.assertEqual(FailureSeverity.INVALIDATING.value, "INVALIDATING")


class TestSeverityOrdering(unittest.TestCase):
    """Severity ordering tests."""

    def test_info_is_lowest(self):
        self.assertEqual(SEVERITY_ORDER[FailureSeverity.INFO], 0)

    def test_invalidating_is_highest(self):
        self.assertEqual(SEVERITY_ORDER[FailureSeverity.INVALIDATING], 4)

    def test_ordering_monotonic(self):
        expected = [
            FailureSeverity.INFO,
            FailureSeverity.WARNING,
            FailureSeverity.ERROR,
            FailureSeverity.CRITICAL,
            FailureSeverity.INVALIDATING,
        ]
        for i in range(len(expected) - 1):
            self.assertLess(
                SEVERITY_ORDER[expected[i]],
                SEVERITY_ORDER[expected[i + 1]],
            )

    def test_consequential_severities(self):
        self.assertIn(FailureSeverity.CRITICAL, CONSEQUENTIAL_SEVERITIES)
        self.assertIn(FailureSeverity.INVALIDATING, CONSEQUENTIAL_SEVERITIES)
        self.assertNotIn(FailureSeverity.INFO, CONSEQUENTIAL_SEVERITIES)
        self.assertNotIn(FailureSeverity.WARNING, CONSEQUENTIAL_SEVERITIES)
        self.assertNotIn(FailureSeverity.ERROR, CONSEQUENTIAL_SEVERITIES)

    def test_export_blocking_severities(self):
        self.assertIn(FailureSeverity.INVALIDATING, EXPORT_BLOCKING_SEVERITIES)
        self.assertNotIn(FailureSeverity.CRITICAL, EXPORT_BLOCKING_SEVERITIES)


class TestWorstSeverity(unittest.TestCase):
    """worst_severity() tests."""

    def test_single_value(self):
        self.assertEqual(worst_severity(FailureSeverity.INFO), FailureSeverity.INFO)

    def test_two_values(self):
        self.assertEqual(
            worst_severity(FailureSeverity.INFO, FailureSeverity.ERROR),
            FailureSeverity.ERROR,
        )

    def test_all_values(self):
        self.assertEqual(
            worst_severity(
                FailureSeverity.INFO,
                FailureSeverity.WARNING,
                FailureSeverity.ERROR,
                FailureSeverity.CRITICAL,
                FailureSeverity.INVALIDATING,
            ),
            FailureSeverity.INVALIDATING,
        )

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            worst_severity()

    def test_duplicate_values(self):
        self.assertEqual(
            worst_severity(FailureSeverity.WARNING, FailureSeverity.WARNING),
            FailureSeverity.WARNING,
        )


class TestSeverityAtLeast(unittest.TestCase):
    """severity_at_least() tests."""

    def test_equal_is_true(self):
        self.assertTrue(
            severity_at_least(FailureSeverity.ERROR, FailureSeverity.ERROR)
        )

    def test_higher_is_true(self):
        self.assertTrue(
            severity_at_least(FailureSeverity.CRITICAL, FailureSeverity.ERROR)
        )

    def test_lower_is_false(self):
        self.assertFalse(
            severity_at_least(FailureSeverity.INFO, FailureSeverity.WARNING)
        )

    def test_info_at_least_info(self):
        self.assertTrue(
            severity_at_least(FailureSeverity.INFO, FailureSeverity.INFO)
        )


class TestClassifyLayerFailure(unittest.TestCase):
    """classify_layer_failure() tests."""

    def test_critical_layer_always_critical(self):
        for layer in ("severity", "governance", "invariants"):
            result = classify_layer_failure(layer, error=ValueError("x"))
            self.assertEqual(result, FailureSeverity.CRITICAL)

    def test_non_critical_error_no_fallback(self):
        result = classify_layer_failure(
            "falsification", error=ValueError("x"), has_fallback_data=False,
        )
        self.assertEqual(result, FailureSeverity.ERROR)

    def test_non_critical_error_with_fallback(self):
        result = classify_layer_failure(
            "falsification", error=ValueError("x"), has_fallback_data=True,
        )
        self.assertEqual(result, FailureSeverity.WARNING)

    def test_no_error_is_info(self):
        result = classify_layer_failure("falsification")
        self.assertEqual(result, FailureSeverity.INFO)


class TestSeverityToDict(unittest.TestCase):
    """severity_to_dict() tests."""

    def test_info_dict(self):
        d = severity_to_dict(FailureSeverity.INFO)
        self.assertEqual(d["level"], "INFO")
        self.assertEqual(d["ordinal"], 0)
        self.assertFalse(d["is_consequential"])
        self.assertFalse(d["blocks_export"])

    def test_critical_dict(self):
        d = severity_to_dict(FailureSeverity.CRITICAL)
        self.assertEqual(d["level"], "CRITICAL")
        self.assertTrue(d["is_consequential"])
        self.assertFalse(d["blocks_export"])

    def test_invalidating_dict(self):
        d = severity_to_dict(FailureSeverity.INVALIDATING)
        self.assertEqual(d["level"], "INVALIDATING")
        self.assertTrue(d["is_consequential"])
        self.assertTrue(d["blocks_export"])


if __name__ == "__main__":
    unittest.main()
