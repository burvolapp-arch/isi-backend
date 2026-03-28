"""
tests/test_layer_result_model.py — Tests for LayerResult and LayerExecutionStatus

Verifies:
    1. LayerExecutionStatus enum has exactly 4 values.
    2. LayerResult is frozen (immutable).
    3. LayerResult validates invariants on construction.
    4. FAILED/SKIPPED results must have empty data.
    5. SUCCESS results must have no errors.
    6. Serialization produces correct dict.
    7. is_usable and is_healthy properties work correctly.
"""

from __future__ import annotations

import unittest

from backend.layer_result import (
    LayerExecutionStatus,
    LayerResult,
    VALID_EXECUTION_STATUSES,
)


class TestLayerExecutionStatus(unittest.TestCase):
    """LayerExecutionStatus enum tests."""

    def test_has_four_values(self):
        self.assertEqual(len(LayerExecutionStatus), 4)

    def test_all_values_in_valid_set(self):
        for status in LayerExecutionStatus:
            self.assertIn(status, VALID_EXECUTION_STATUSES)

    def test_success_value(self):
        self.assertEqual(LayerExecutionStatus.SUCCESS.value, "SUCCESS")

    def test_degraded_value(self):
        self.assertEqual(LayerExecutionStatus.DEGRADED.value, "DEGRADED")

    def test_failed_value(self):
        self.assertEqual(LayerExecutionStatus.FAILED.value, "FAILED")

    def test_skipped_value(self):
        self.assertEqual(LayerExecutionStatus.SKIPPED.value, "SKIPPED")


class TestLayerResultConstruction(unittest.TestCase):
    """LayerResult construction and validation tests."""

    def test_basic_success_result(self):
        r = LayerResult(
            layer_name="severity",
            status=LayerExecutionStatus.SUCCESS,
            data={"severity_analysis": {}, "strict_comparability_tier": "FULLY_COMPARABLE"},
            timing_ms=12.5,
        )
        self.assertEqual(r.layer_name, "severity")
        self.assertEqual(r.status, LayerExecutionStatus.SUCCESS)
        self.assertEqual(len(r.data), 2)
        self.assertEqual(r.timing_ms, 12.5)

    def test_basic_degraded_result(self):
        r = LayerResult(
            layer_name="falsification",
            status=LayerExecutionStatus.DEGRADED,
            data={"falsification": {"error": "assessment failed"}},
            warnings=("Fallback data used.",),
            timing_ms=5.0,
        )
        self.assertEqual(r.status, LayerExecutionStatus.DEGRADED)
        self.assertEqual(len(r.warnings), 1)

    def test_basic_failed_result(self):
        r = LayerResult(
            layer_name="governance",
            status=LayerExecutionStatus.FAILED,
            errors=("ValueError: missing data",),
            timing_ms=1.0,
        )
        self.assertEqual(r.status, LayerExecutionStatus.FAILED)
        self.assertEqual(len(r.errors), 1)
        self.assertEqual(len(r.data), 0)

    def test_basic_skipped_result(self):
        r = LayerResult(
            layer_name="invariants",
            status=LayerExecutionStatus.SKIPPED,
            warnings=("Skipped due to upstream failure.",),
        )
        self.assertEqual(r.status, LayerExecutionStatus.SKIPPED)

    def test_frozen_immutable(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SUCCESS,
            data={"x": 1},
        )
        with self.assertRaises(AttributeError):
            r.layer_name = "modified"

    def test_invalid_status_type_raises(self):
        with self.assertRaises(TypeError):
            LayerResult(layer_name="test", status="SUCCESS", data={})

    def test_empty_layer_name_raises(self):
        with self.assertRaises(ValueError):
            LayerResult(layer_name="", status=LayerExecutionStatus.SUCCESS)

    def test_non_string_layer_name_raises(self):
        with self.assertRaises(ValueError):
            LayerResult(layer_name=None, status=LayerExecutionStatus.SUCCESS)

    def test_non_dict_data_raises(self):
        with self.assertRaises(TypeError):
            LayerResult(layer_name="test", status=LayerExecutionStatus.SUCCESS, data=[1, 2])

    def test_non_tuple_warnings_raises(self):
        with self.assertRaises(TypeError):
            LayerResult(
                layer_name="test",
                status=LayerExecutionStatus.SUCCESS,
                data={},
                warnings=["warning"],
            )

    def test_non_tuple_errors_raises(self):
        with self.assertRaises(TypeError):
            LayerResult(
                layer_name="test",
                status=LayerExecutionStatus.DEGRADED,
                data={},
                errors=["error"],
            )

    def test_negative_timing_raises(self):
        with self.assertRaises(ValueError):
            LayerResult(
                layer_name="test",
                status=LayerExecutionStatus.SUCCESS,
                data={},
                timing_ms=-1.0,
            )

    def test_failed_with_data_raises(self):
        with self.assertRaises(ValueError):
            LayerResult(
                layer_name="test",
                status=LayerExecutionStatus.FAILED,
                data={"x": 1},
                errors=("boom",),
            )

    def test_skipped_with_data_raises(self):
        with self.assertRaises(ValueError):
            LayerResult(
                layer_name="test",
                status=LayerExecutionStatus.SKIPPED,
                data={"x": 1},
            )

    def test_success_with_errors_raises(self):
        with self.assertRaises(ValueError):
            LayerResult(
                layer_name="test",
                status=LayerExecutionStatus.SUCCESS,
                data={},
                errors=("shouldn't have errors",),
            )


class TestLayerResultProperties(unittest.TestCase):
    """LayerResult property tests."""

    def test_success_is_usable(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SUCCESS,
            data={"x": 1},
        )
        self.assertTrue(r.is_usable)

    def test_degraded_is_usable(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.DEGRADED,
            data={"x": 1},
        )
        self.assertTrue(r.is_usable)

    def test_failed_not_usable(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.FAILED,
            errors=("boom",),
        )
        self.assertFalse(r.is_usable)

    def test_skipped_not_usable(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SKIPPED,
        )
        self.assertFalse(r.is_usable)

    def test_success_no_warnings_is_healthy(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SUCCESS,
            data={"x": 1},
        )
        self.assertTrue(r.is_healthy)

    def test_success_with_warnings_not_healthy(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SUCCESS,
            data={"x": 1},
            warnings=("something iffy",),
        )
        self.assertFalse(r.is_healthy)

    def test_degraded_not_healthy(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.DEGRADED,
            data={"x": 1},
        )
        self.assertFalse(r.is_healthy)


class TestLayerResultSerialization(unittest.TestCase):
    """LayerResult.to_dict() tests."""

    def test_to_dict_keys(self):
        r = LayerResult(
            layer_name="severity",
            status=LayerExecutionStatus.SUCCESS,
            data={"a": 1, "b": 2},
            timing_ms=10.0,
            version="1.0.0",
        )
        d = r.to_dict()
        self.assertEqual(d["layer_name"], "severity")
        self.assertEqual(d["status"], "SUCCESS")
        self.assertEqual(d["data_keys"], ["a", "b"])
        self.assertEqual(d["n_warnings"], 0)
        self.assertEqual(d["n_errors"], 0)
        self.assertEqual(d["timing_ms"], 10.0)
        self.assertEqual(d["version"], "1.0.0")
        self.assertTrue(d["is_usable"])
        self.assertTrue(d["is_healthy"])

    def test_to_dict_with_warnings(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.DEGRADED,
            data={"x": 1},
            warnings=("w1", "w2"),
        )
        d = r.to_dict()
        self.assertEqual(d["n_warnings"], 2)
        self.assertEqual(d["warnings"], ["w1", "w2"])
        self.assertTrue(d["is_usable"])
        self.assertFalse(d["is_healthy"])

    def test_to_dict_failed(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.FAILED,
            errors=("error1",),
            timing_ms=3.0,
        )
        d = r.to_dict()
        self.assertEqual(d["status"], "FAILED")
        self.assertEqual(d["data_keys"], [])
        self.assertEqual(d["n_errors"], 1)
        self.assertFalse(d["is_usable"])
        self.assertFalse(d["is_healthy"])


class TestLayerResultDefaultVersion(unittest.TestCase):
    """Version field defaults and custom values."""

    def test_default_version(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SUCCESS,
            data={"x": 1},
        )
        self.assertEqual(r.version, "1.0.0")

    def test_custom_version(self):
        r = LayerResult(
            layer_name="test",
            status=LayerExecutionStatus.SUCCESS,
            data={"x": 1},
            version="2.3.1",
        )
        self.assertEqual(r.version, "2.3.1")


if __name__ == "__main__":
    unittest.main()
