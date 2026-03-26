"""
tests/test_runtime_invariants.py — Tests for Runtime Invariants

Verifies:
    1. INV-RUNTIME-001: No silent failures.
    2. INV-RUNTIME-002: Degraded must propagate.
    3. INV-VERSION-001: Versions must be present.
    4. INV-EXPORT-002: Runtime status must be included.
    5. Invariant registry includes all 4 new entries.
    6. RUNTIME invariant type exists.
"""

from __future__ import annotations

import unittest

from backend.invariants import (
    InvariantType,
    InvariantSeverity,
    INVARIANT_REGISTRY,
    VALID_INVARIANT_TYPES,
    check_runtime_invariants,
)


class TestRuntimeInvariantType(unittest.TestCase):
    """RUNTIME invariant type exists."""

    def test_runtime_type_exists(self):
        self.assertEqual(InvariantType.RUNTIME, "RUNTIME")

    def test_runtime_in_valid_types(self):
        self.assertIn(InvariantType.RUNTIME, VALID_INVARIANT_TYPES)


class TestRuntimeInvariantRegistryEntries(unittest.TestCase):
    """Registry has all 4 runtime invariants."""

    def test_four_runtime_invariants_in_registry(self):
        runtime_invariants = [
            inv for inv in INVARIANT_REGISTRY
            if inv["type"] == InvariantType.RUNTIME
        ]
        self.assertEqual(len(runtime_invariants), 4)

    def test_expected_ids_present(self):
        expected_ids = {
            "INV-RUNTIME-001",
            "INV-RUNTIME-002",
            "INV-VERSION-001",
            "INV-EXPORT-002",
        }
        runtime_ids = {
            inv["invariant_id"] for inv in INVARIANT_REGISTRY
            if inv["type"] == InvariantType.RUNTIME
        }
        self.assertEqual(runtime_ids, expected_ids)

    def test_all_have_required_fields(self):
        runtime_invariants = [
            inv for inv in INVARIANT_REGISTRY
            if inv["type"] == InvariantType.RUNTIME
        ]
        for inv in runtime_invariants:
            self.assertIn("invariant_id", inv)
            self.assertIn("type", inv)
            self.assertIn("name", inv)
            self.assertIn("description", inv)


class TestINVRuntime001(unittest.TestCase):
    """INV-RUNTIME-001: No silent failures."""

    def test_no_violation_when_degraded_tracked(self):
        country_json = {
            "falsification": {"error": "assessment failed"},
            "runtime_status": {
                "pipeline_status": "DEGRADED",
                "degraded_layers": ["falsification"],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_001 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-001"]
        self.assertEqual(len(runtime_001), 0)

    def test_violation_when_error_not_tracked(self):
        country_json = {
            "falsification": {"error": "assessment failed"},
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_001 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-001"]
        self.assertEqual(len(runtime_001), 1)
        self.assertEqual(runtime_001[0]["severity"], InvariantSeverity.ERROR)

    def test_tracked_in_failed_also_ok(self):
        country_json = {
            "falsification": {"error": "total failure"},
            "runtime_status": {
                "pipeline_status": "FAILED",
                "degraded_layers": [],
                "failed_layers": ["falsification"],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_001 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-001"]
        self.assertEqual(len(runtime_001), 0)


class TestINVRuntime002(unittest.TestCase):
    """INV-RUNTIME-002: Degraded must propagate."""

    def test_no_violation_when_status_matches(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "DEGRADED",
                "degraded_layers": ["falsification"],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_002 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-002"]
        self.assertEqual(len(runtime_002), 0)

    def test_violation_when_degraded_but_healthy(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": ["falsification"],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_002 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-002"]
        self.assertEqual(len(runtime_002), 1)
        self.assertEqual(runtime_002[0]["severity"], InvariantSeverity.CRITICAL)

    def test_violation_when_failed_but_not_failed_status(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "DEGRADED",
                "degraded_layers": [],
                "failed_layers": ["governance"],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_002 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-002"]
        self.assertEqual(len(runtime_002), 1)


class TestINVVersion001(unittest.TestCase):
    """INV-VERSION-001: Versions must be present."""

    def test_no_violation_when_all_versions_present(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        version_001 = [v for v in violations if v["invariant_id"] == "INV-VERSION-001"]
        self.assertEqual(len(version_001), 0)

    def test_violation_when_version_info_missing(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        version_001 = [v for v in violations if v["invariant_id"] == "INV-VERSION-001"]
        self.assertEqual(len(version_001), 1)
        self.assertEqual(version_001[0]["severity"], InvariantSeverity.CRITICAL)

    def test_violation_when_version_field_missing(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                # Missing pipeline_version, truth_logic_version, enforcement_version
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        version_001 = [v for v in violations if v["invariant_id"] == "INV-VERSION-001"]
        self.assertEqual(len(version_001), 1)
        self.assertEqual(version_001[0]["severity"], InvariantSeverity.ERROR)


class TestINVExport002(unittest.TestCase):
    """INV-EXPORT-002: Runtime status must be included."""

    def test_no_violation_when_runtime_status_present(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        export_002 = [v for v in violations if v["invariant_id"] == "INV-EXPORT-002"]
        self.assertEqual(len(export_002), 0)

    def test_violation_when_runtime_status_missing(self):
        country_json = {
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        export_002 = [v for v in violations if v["invariant_id"] == "INV-EXPORT-002"]
        self.assertEqual(len(export_002), 1)
        self.assertEqual(export_002[0]["severity"], InvariantSeverity.CRITICAL)

    def test_violation_when_required_fields_missing(self):
        country_json = {
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                # Missing degraded_layers and failed_layers
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        export_002 = [v for v in violations if v["invariant_id"] == "INV-EXPORT-002"]
        self.assertEqual(len(export_002), 1)
        self.assertEqual(export_002[0]["severity"], InvariantSeverity.ERROR)


class TestRuntimeInvariantsNoCountryJson(unittest.TestCase):
    """check_runtime_invariants with no country_json."""

    def test_no_violations_when_none(self):
        violations = check_runtime_invariants("DE")
        self.assertEqual(len(violations), 0)

    def test_no_violations_when_explicit_none(self):
        violations = check_runtime_invariants("DE", country_json=None)
        self.assertEqual(len(violations), 0)


class TestRuntimeInvariantsMultipleErrors(unittest.TestCase):
    """Multiple silent failures detected."""

    def test_multiple_silent_failures(self):
        country_json = {
            "falsification": {"error": "failed1"},
            "decision_usability": {"error": "failed2"},
            "external_validation": {"error": "failed3"},
            "runtime_status": {
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
            "version_info": {
                "methodology_version": "v0.1",
                "pipeline_version": "2.0.0",
                "truth_logic_version": "1.0.0",
                "enforcement_version": "1.0.0",
            },
        }
        violations = check_runtime_invariants("DE", country_json=country_json)
        runtime_001 = [v for v in violations if v["invariant_id"] == "INV-RUNTIME-001"]
        # One per silent failure
        self.assertEqual(len(runtime_001), 3)


if __name__ == "__main__":
    unittest.main()
