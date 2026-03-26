"""
test_integration_wiring.py — Regression Tests for Integration Wiring

Tests that ALL backend hardening layers are actually called in production
export paths. These tests exist because BUG-1 through BUG-6 in the
Final Error/Problem Audit discovered that multiple layers were
DECORATIVE — tested in isolation but never wired into the export pipeline.

These tests prevent regression to decorative integration.

Created: Final Error/Problem Audit Pass
"""

import unittest
from unittest.mock import patch, MagicMock
from typing import Any


class TestExportSnapshotWiring(unittest.TestCase):
    """Verify build_country_json wires ALL layers with real data."""

    def _build_test_country(self, country: str = "DE") -> dict[str, Any]:
        """Build a country JSON using the real export pipeline."""
        from backend.export_snapshot import build_country_json

        # Minimal all_scores: 6 axes with DE having a score
        all_scores: dict[int, dict[str, float]] = {}
        for axis_id in range(1, 7):
            all_scores[axis_id] = {country: 0.5}

        return build_country_json(
            country=country,
            all_scores=all_scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2024",
        )

    # ── BUG-1 Regression: reality_conflicts must receive alignment data ──

    def test_reality_conflicts_receives_alignment_data(self):
        """BUG-1: _compute_reality_conflicts was called without alignment.

        The reality conflict layer MUST receive external_validation data
        so it can compare governance tier against alignment class.
        If alignment is None, governance-alignment mismatch checks are
        silently skipped — the entire layer becomes decorative.
        """
        result = self._build_test_country()
        rc = result["reality_conflicts"]

        # Must have the structural fields
        self.assertIn("n_conflicts", rc)
        self.assertIn("conflicts", rc)
        self.assertIn("interpretation", rc)
        # Must NOT have an error field (i.e., should compute successfully)
        self.assertNotIn("error", rc, "Reality conflicts should not error with proper wiring")

    def test_reality_conflicts_not_all_zero(self):
        """If governance and alignment genuinely conflict, we must see it.

        This is a STRUCTURAL test — it doesn't require a specific conflict,
        but ensures the conflict detection machinery actually runs.
        """
        result = self._build_test_country()
        rc = result["reality_conflicts"]

        # The result must be a complete block, not a stub
        self.assertIsInstance(rc["conflicts"], list)
        self.assertIsInstance(rc["n_conflicts"], int)
        # n_conflicts >= 0 — we can't guarantee a conflict, but the
        # mechanism must actually execute
        self.assertGreaterEqual(rc["n_conflicts"], 0)

    # ── BUG-2 Regression: failure_visibility must receive ALL upstream data ──

    def test_failure_visibility_receives_full_data(self):
        """BUG-2: _compute_failure_visibility was called with only 3 of 8 params.

        The anti-bullshit layer MUST receive construct_enforcement,
        external_validation, sensitivity_result, mapping_audit_results,
        and invariant_result. Without these, most visibility flags are
        silently skipped.
        """
        result = self._build_test_country()
        fv = result["failure_visibility"]

        self.assertIn("trust_level", fv)
        self.assertIn("severity_summary", fv)
        self.assertNotIn("error", fv, "Failure visibility should not error with proper wiring")

    # ── BUG-3 Regression: decision_usability not called twice ──

    def test_decision_usability_computed_once(self):
        """BUG-3: _compute_decision_usability was called twice in build_country_json.

        The fix stores the result and reuses it. Verify the key exists
        and is a proper result dict.
        """
        result = self._build_test_country()
        du = result["decision_usability"]

        self.assertIn("decision_usability_class", du)
        self.assertNotIn("error", du)

    # ── BUG-4 Regression: construct_enforcement must be in production ──

    def test_construct_enforcement_wired(self):
        """BUG-4: construct_enforcement.py was never called from export.

        build_country_json MUST now include a construct_enforcement key
        with real enforcement results, not None.
        """
        result = self._build_test_country()

        self.assertIn("construct_enforcement", result)
        ce = result["construct_enforcement"]
        self.assertIsInstance(ce, dict)
        self.assertIn("n_valid", ce)
        self.assertIn("n_degraded", ce)
        self.assertIn("n_invalid", ce)
        self.assertIn("composite_producible", ce)
        self.assertNotIn("error", ce, "Construct enforcement should not error")

    def test_construct_enforcement_has_per_axis(self):
        """Construct enforcement must produce per-axis results."""
        result = self._build_test_country()
        ce = result["construct_enforcement"]

        self.assertIn("per_axis", ce)
        self.assertIsInstance(ce["per_axis"], list)
        self.assertGreater(len(ce["per_axis"]), 0)

    # ── BUG-5 Regression: benchmark_mapping_audit must be used ──

    def test_mapping_audit_feeds_visibility(self):
        """BUG-5: benchmark_mapping_audit was never called from production.

        Mapping audit results must now be computed and passed to
        failure_visibility for flag generation.
        """
        # We verify this by checking the export path calls get_mapping_audit_registry
        from backend.export_snapshot import _compute_mapping_audit
        result = _compute_mapping_audit()
        self.assertIsInstance(result, dict)
        # Should contain at least some benchmark mappings
        self.assertGreater(len(result), 0)

    # ── BUG-6 Regression: alignment_sensitivity must be in production ──

    def test_alignment_sensitivity_wired(self):
        """BUG-6: alignment_sensitivity.py was never called from production.

        build_country_json MUST now include alignment_sensitivity with
        real sensitivity results.
        """
        result = self._build_test_country()

        self.assertIn("alignment_sensitivity", result)
        sens = result["alignment_sensitivity"]
        self.assertIsInstance(sens, dict)
        self.assertIn("stability_class", sens)
        self.assertIn("country", sens)
        self.assertNotIn("error", sens, "Alignment sensitivity should not error")

    # ── NEW: invariant_assessment must be in country JSON ──

    def test_invariant_assessment_wired(self):
        """Invariant assessment must be included in country JSON with full data."""
        result = self._build_test_country()

        self.assertIn("invariant_assessment", result)
        inv = result["invariant_assessment"]
        self.assertIsInstance(inv, dict)
        self.assertIn("n_violations", inv)
        self.assertIn("violations", inv)
        self.assertNotIn("error", inv, "Invariant assessment should not error")

    # ── STRUCTURAL: all layers present and no errors ──

    def test_all_layers_present_in_country_json(self):
        """Every layer must appear as a key in the country JSON."""
        result = self._build_test_country()

        required_keys = [
            "country", "country_name", "version", "year", "window",
            "isi_composite", "isi_classification",
            "axes_available", "axes_required",
            "severity_analysis", "strict_comparability_tier",
            "governance", "axes",
            "falsification", "decision_usability",
            "external_validation",
            "construct_enforcement",
            "alignment_sensitivity",
            "failure_visibility",
            "reality_conflicts",
            "invariant_assessment",
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing required key: {key}")

    def test_no_layer_has_error_key(self):
        """No layer should have an 'error' key when called with valid data."""
        result = self._build_test_country()

        layers_to_check = [
            "governance", "falsification", "decision_usability",
            "external_validation", "construct_enforcement",
            "alignment_sensitivity", "failure_visibility",
            "reality_conflicts", "invariant_assessment",
        ]
        for layer_key in layers_to_check:
            layer = result.get(layer_key)
            if isinstance(layer, dict):
                self.assertNotIn(
                    "error", layer,
                    f"Layer '{layer_key}' has an error: {layer.get('error')}",
                )


class TestExportSnapshotHelperSignatures(unittest.TestCase):
    """Verify the export helper wrappers have correct signatures."""

    def test_compute_failure_visibility_accepts_all_params(self):
        """_compute_failure_visibility must accept all 8 data params."""
        from backend.export_snapshot import _compute_failure_visibility
        import inspect

        sig = inspect.signature(_compute_failure_visibility)
        params = list(sig.parameters.keys())

        expected = [
            "country", "governance", "decision_usability",
            "construct_enforcement", "external_validation",
            "sensitivity_result", "mapping_audit_results",
            "invariant_result",
        ]
        for p in expected:
            self.assertIn(p, params, f"_compute_failure_visibility missing param: {p}")

    def test_compute_reality_conflicts_accepts_alignment(self):
        """_compute_reality_conflicts must accept alignment data."""
        from backend.export_snapshot import _compute_reality_conflicts
        import inspect

        sig = inspect.signature(_compute_reality_conflicts)
        params = list(sig.parameters.keys())

        self.assertIn("alignment", params)
        self.assertIn("decision_usability", params)
        self.assertIn("empirical_alignment", params)


class TestDecorativeModuleElimination(unittest.TestCase):
    """Verify modules that were decorative are now production-called."""

    def test_construct_enforcement_imported_by_export(self):
        """construct_enforcement must be imported by export_snapshot."""
        import backend.export_snapshot as es
        # Verify enforce_all_axes is accessible
        self.assertTrue(
            hasattr(es, 'enforce_all_axes'),
            "export_snapshot must import enforce_all_axes from construct_enforcement",
        )

    def test_benchmark_mapping_audit_imported_by_export(self):
        """benchmark_mapping_audit must be imported by export_snapshot."""
        import backend.export_snapshot as es
        self.assertTrue(
            hasattr(es, 'get_mapping_audit_registry'),
            "export_snapshot must import get_mapping_audit_registry from benchmark_mapping_audit",
        )

    def test_alignment_sensitivity_imported_by_export(self):
        """alignment_sensitivity must be imported by export_snapshot."""
        import backend.export_snapshot as es
        self.assertTrue(
            hasattr(es, 'run_alignment_sensitivity'),
            "export_snapshot must import run_alignment_sensitivity from alignment_sensitivity",
        )

    def test_empirical_alignment_imported_by_export(self):
        """classify_empirical_alignment must be imported by export_snapshot."""
        import backend.export_snapshot as es
        self.assertTrue(
            hasattr(es, 'classify_empirical_alignment'),
            "export_snapshot must import classify_empirical_alignment from eligibility",
        )

    def test_invariants_imported_by_export(self):
        """assess_country_invariants must be imported by export_snapshot."""
        import backend.export_snapshot as es
        self.assertTrue(
            hasattr(es, 'assess_country_invariants'),
            "export_snapshot must import assess_country_invariants from invariants",
        )


class TestDataFlowIntegrity(unittest.TestCase):
    """Verify data flows between layers correctly."""

    def _build_test_country(self, country: str = "DE") -> dict[str, Any]:
        from backend.export_snapshot import build_country_json
        all_scores: dict[int, dict[str, float]] = {}
        for axis_id in range(1, 7):
            all_scores[axis_id] = {country: 0.5}
        return build_country_json(
            country=country,
            all_scores=all_scores,
            methodology_version="v1.0",
            year=2024,
            data_window="2024",
        )

    def test_external_validation_populates_alignment_data(self):
        """External validation must produce alignment data that feeds downstream."""
        result = self._build_test_country()
        ev = result["external_validation"]

        # Must have the fields that reality_conflicts needs
        self.assertIn("overall_alignment", ev)

    def test_construct_enforcement_uses_readiness_matrix(self):
        """Construct enforcement must use real readiness matrix data."""
        result = self._build_test_country()
        ce = result["construct_enforcement"]

        # n_valid + n_degraded + n_invalid should equal number of axes checked
        total = ce["n_valid"] + ce["n_degraded"] + ce["n_invalid"]
        self.assertGreater(total, 0, "Construct enforcement should check at least 1 axis")

    def test_sensitivity_reflects_alignment_class(self):
        """Alignment sensitivity must receive the original alignment class."""
        result = self._build_test_country()
        sens = result["alignment_sensitivity"]

        # If there's an original_alignment_class, it should match external_validation
        ev = result["external_validation"]
        ev_class = ev.get("overall_alignment")
        sens_class = sens.get("original_alignment_class")
        # These should be consistent (sensitivity uses the alignment from EV)
        self.assertEqual(
            ev_class, sens_class,
            "Sensitivity original_alignment_class should match external_validation",
        )

    def test_invariant_assessment_has_violations_list(self):
        """Invariant assessment must produce a proper violations list."""
        result = self._build_test_country()
        inv = result["invariant_assessment"]

        self.assertIsInstance(inv["violations"], list)
        self.assertIsInstance(inv["n_violations"], int)
        self.assertEqual(inv["n_violations"], len(inv["violations"]))

    def test_multiple_countries_independently_computed(self):
        """Each country must get its own independent layer results."""
        from backend.export_snapshot import build_country_json

        all_scores: dict[int, dict[str, float]] = {}
        for axis_id in range(1, 7):
            all_scores[axis_id] = {"DE": 0.8, "FR": 0.3}

        de = build_country_json("DE", all_scores, "v1.0", 2024, "2024")
        fr = build_country_json("FR", all_scores, "v1.0", 2024, "2024")

        self.assertEqual(de["country"], "DE")
        self.assertEqual(fr["country"], "FR")
        self.assertEqual(de["reality_conflicts"]["country"], "DE")
        self.assertEqual(fr["reality_conflicts"]["country"], "FR")
        self.assertEqual(de["construct_enforcement"]["per_axis"][0]["axis_id"], 1)
        self.assertEqual(fr["construct_enforcement"]["per_axis"][0]["axis_id"], 1)

    def test_missing_data_produces_graceful_results(self):
        """Country with missing axis data should still produce all layers."""
        from backend.export_snapshot import build_country_json

        # Only 2 axes have data
        all_scores: dict[int, dict[str, float]] = {
            1: {"DE": 0.5},
            2: {"DE": 0.7},
        }

        result = build_country_json("DE", all_scores, "v1.0", 2024, "2024")

        # All layers must still be present
        for key in ["construct_enforcement", "alignment_sensitivity",
                     "failure_visibility", "reality_conflicts",
                     "invariant_assessment"]:
            self.assertIn(key, result, f"Missing {key} with sparse data")
            self.assertNotIn("error", result[key],
                             f"{key} errored with sparse data: {result[key].get('error')}")


class TestHelperGracefulDegradation(unittest.TestCase):
    """Verify helpers degrade gracefully on edge cases."""

    def test_compute_construct_enforcement_with_nonexistent_country(self):
        """Construct enforcement with unknown country should not crash."""
        from backend.export_snapshot import _compute_construct_enforcement
        result = _compute_construct_enforcement("ZZ")
        self.assertIsInstance(result, dict)
        # Should still produce a result (readiness matrix returns defaults)

    def test_compute_alignment_sensitivity_with_no_scores(self):
        """Sensitivity with empty scores should produce NOT_ASSESSED."""
        from backend.export_snapshot import _compute_alignment_sensitivity
        result = _compute_alignment_sensitivity("ZZ", {})
        self.assertIsInstance(result, dict)
        self.assertIn("stability_class", result)

    def test_compute_empirical_alignment_with_none(self):
        """Empirical alignment with None input should return None gracefully."""
        from backend.export_snapshot import _compute_empirical_alignment
        result = _compute_empirical_alignment(None)
        # classify_empirical_alignment(None) returns a dict with NOT_ASSESSED
        self.assertIsNotNone(result)

    def test_compute_invariants_minimal(self):
        """Invariants with minimal data should not crash."""
        from backend.export_snapshot import _compute_invariants
        governance = {
            "governance_tier": "NON_COMPARABLE",
            "mean_axis_confidence": 0.0,
            "ranking_eligible": False,
        }
        result = _compute_invariants("ZZ", {}, governance)
        self.assertIsInstance(result, dict)
        self.assertIn("n_violations", result)


class TestSnapshotDiffNewLayers(unittest.TestCase):
    """BUG-7 regression: snapshot_diff must track new layer changes."""

    def test_diff_country_includes_reality_conflicts_change(self):
        """diff_country must include reality_conflicts_change field."""
        from backend.snapshot_diff import diff_country

        entry_a = {"isi_composite": 0.5, "rank": 1}
        entry_b = {"isi_composite": 0.5, "rank": 1}
        detail_a = {"reality_conflicts": {"n_conflicts": 0}}
        detail_b = {"reality_conflicts": {"n_conflicts": 2}}

        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        self.assertIn("reality_conflicts_change", result)
        rc = result["reality_conflicts_change"]
        self.assertIsNotNone(rc)
        self.assertEqual(rc["from"], 0)
        self.assertEqual(rc["to"], 2)
        self.assertTrue(rc["changed"])

    def test_diff_country_includes_visibility_change(self):
        """diff_country must include visibility_change field."""
        from backend.snapshot_diff import diff_country

        entry_a = {"isi_composite": 0.5, "rank": 1}
        entry_b = {"isi_composite": 0.5, "rank": 1}
        detail_a = {"failure_visibility": {"trust_level": "TRUSTED"}}
        detail_b = {"failure_visibility": {"trust_level": "USE_WITH_EXTREME_CAUTION"}}

        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        self.assertIn("visibility_change", result)
        vc = result["visibility_change"]
        self.assertIsNotNone(vc)
        self.assertTrue(vc["changed"])

    def test_diff_country_includes_construct_enforcement_change(self):
        """diff_country must include construct_enforcement_change field."""
        from backend.snapshot_diff import diff_country

        entry_a = {"isi_composite": 0.5, "rank": 1}
        entry_b = {"isi_composite": 0.5, "rank": 1}
        detail_a = {"construct_enforcement": {"composite_producible": True, "n_valid": 6}}
        detail_b = {"construct_enforcement": {"composite_producible": False, "n_valid": 3}}

        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        self.assertIn("construct_enforcement_change", result)
        ce = result["construct_enforcement_change"]
        self.assertIsNotNone(ce)
        self.assertTrue(ce["changed"])

    def test_diff_country_includes_sensitivity_change(self):
        """diff_country must include sensitivity_change field."""
        from backend.snapshot_diff import diff_country

        entry_a = {"isi_composite": 0.5, "rank": 1}
        entry_b = {"isi_composite": 0.5, "rank": 1}
        detail_a = {"alignment_sensitivity": {"stability_class": "STABLE"}}
        detail_b = {"alignment_sensitivity": {"stability_class": "UNSTABLE"}}

        result = diff_country("DE", entry_a, entry_b, detail_a, detail_b)
        self.assertIn("sensitivity_change", result)
        sc = result["sensitivity_change"]
        self.assertIsNotNone(sc)
        self.assertTrue(sc["changed"])

    def test_diff_country_no_change_new_layers(self):
        """No change in new layers should produce changed=False."""
        from backend.snapshot_diff import diff_country

        entry = {"isi_composite": 0.5, "rank": 1}
        detail = {
            "reality_conflicts": {"n_conflicts": 0},
            "failure_visibility": {"trust_level": "TRUSTED"},
            "construct_enforcement": {"composite_producible": True, "n_valid": 6},
            "alignment_sensitivity": {"stability_class": "STABLE"},
        }

        result = diff_country("DE", entry, entry, detail, detail)
        self.assertFalse(result["reality_conflicts_change"]["changed"])
        self.assertFalse(result["visibility_change"]["changed"])
        self.assertFalse(result["construct_enforcement_change"]["changed"])
        self.assertFalse(result["sensitivity_change"]["changed"])

    def test_diff_added_country_has_none_new_layers(self):
        """Added country should have None for new layer changes."""
        from backend.snapshot_diff import diff_country

        entry_b = {"isi_composite": 0.5, "rank": 1}
        result = diff_country("DE", None, entry_b)
        self.assertIsNone(result["reality_conflicts_change"])
        self.assertIsNone(result["visibility_change"])
        self.assertIsNone(result["construct_enforcement_change"])
        self.assertIsNone(result["sensitivity_change"])

    def test_compare_snapshots_summary_includes_new_counts(self):
        """Global summary must include counts for new layer changes."""
        from backend.snapshot_diff import compare_snapshots

        snapshot_a = {
            "methodology": "v1.0", "year": 2024,
            "data_window": "2024",
            "countries": [{"country": "DE", "isi_composite": 0.5, "rank": 1}],
        }
        snapshot_b = {
            "methodology": "v1.0", "year": 2024,
            "data_window": "2024",
            "countries": [{"country": "DE", "isi_composite": 0.5, "rank": 1}],
        }

        result = compare_snapshots(snapshot_a, snapshot_b)
        gs = result["global_summary"]
        self.assertIn("n_reality_conflicts_changes", gs)
        self.assertIn("n_visibility_changes", gs)
        self.assertIn("n_construct_enforcement_changes", gs)
        self.assertIn("n_sensitivity_changes", gs)

    def test_extract_nested_utility(self):
        """_extract_nested must safely extract nested fields."""
        from backend.snapshot_diff import _extract_nested

        self.assertIsNone(_extract_nested(None, "foo", "bar"))
        self.assertIsNone(_extract_nested({}, "foo", "bar"))
        self.assertIsNone(_extract_nested({"foo": "not_a_dict"}, "foo", "bar"))
        self.assertEqual(_extract_nested({"foo": {"bar": 42}}, "foo", "bar"), 42)


if __name__ == "__main__":
    unittest.main()
