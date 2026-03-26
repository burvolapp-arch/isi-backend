"""
tests/test_layer_pipeline.py — Tests for the Layer Pipeline (Section 1)

Verifies:
    1. Pipeline validation catches cycles, duplicates, missing deps
    2. Pipeline execution respects dependency order
    3. GuardedState prevents undeclared access
    4. Layers must produce declared outputs
    5. Pipeline produces deterministic execution order
    6. COUNTRY_PIPELINE is structurally valid
"""

from __future__ import annotations

import unittest

from backend.layer_pipeline import (
    Layer,
    CyclicDependencyError,
    DuplicateLayerError,
    MissingDependencyError,
    MissingOutputError,
    PipelineError,
    UndeclaredInputError,
    validate_pipeline,
    run_pipeline,
    COUNTRY_PIPELINE,
    run_country_pipeline,
)


class TestPipelineValidation(unittest.TestCase):
    """Pipeline DAG validation tests."""

    def test_empty_pipeline_valid(self):
        order = validate_pipeline([])
        self.assertEqual(order, [])

    def test_single_layer_valid(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {}, produces=frozenset({"x"})),
        ]
        order = validate_pipeline(layers)
        self.assertEqual(order, ["a"])

    def test_linear_chain(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {}, requires=frozenset({"a"}), produces=frozenset({"y"})),
            Layer(name="c", compute=lambda s, c: {}, requires=frozenset({"b"}), produces=frozenset({"z"})),
        ]
        order = validate_pipeline(layers)
        self.assertEqual(order, ["a", "b", "c"])

    def test_diamond_dependency(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {}, requires=frozenset({"a"}), produces=frozenset({"y"})),
            Layer(name="c", compute=lambda s, c: {}, requires=frozenset({"a"}), produces=frozenset({"z"})),
            Layer(name="d", compute=lambda s, c: {}, requires=frozenset({"b", "c"}), produces=frozenset({"w"})),
        ]
        order = validate_pipeline(layers)
        # d must come after b and c, b and c after a
        self.assertEqual(order[0], "a")
        self.assertEqual(order[-1], "d")
        self.assertIn("b", order[1:3])
        self.assertIn("c", order[1:3])

    def test_duplicate_name_raises(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {}, produces=frozenset({"x"})),
            Layer(name="a", compute=lambda s, c: {}, produces=frozenset({"y"})),
        ]
        with self.assertRaises(DuplicateLayerError):
            validate_pipeline(layers)

    def test_missing_dependency_raises(self):
        layers = [
            Layer(name="b", compute=lambda s, c: {}, requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        with self.assertRaises(MissingDependencyError):
            validate_pipeline(layers)

    def test_cyclic_dependency_raises(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {}, requires=frozenset({"b"}), produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {}, requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        with self.assertRaises(CyclicDependencyError):
            validate_pipeline(layers)

    def test_three_node_cycle_raises(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {}, requires=frozenset({"c"}), produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {}, requires=frozenset({"a"}), produces=frozenset({"y"})),
            Layer(name="c", compute=lambda s, c: {}, requires=frozenset({"b"}), produces=frozenset({"z"})),
        ]
        with self.assertRaises(CyclicDependencyError):
            validate_pipeline(layers)

    def test_deterministic_tie_break(self):
        """Independent layers should be ordered alphabetically."""
        layers = [
            Layer(name="z", compute=lambda s, c: {}, produces=frozenset({"out_z"})),
            Layer(name="a", compute=lambda s, c: {}, produces=frozenset({"out_a"})),
            Layer(name="m", compute=lambda s, c: {}, produces=frozenset({"out_m"})),
        ]
        order = validate_pipeline(layers)
        self.assertEqual(order, ["a", "m", "z"])


class TestPipelineExecution(unittest.TestCase):
    """Pipeline execution tests."""

    def test_simple_pipeline_execution(self):
        def compute_a(state, ctx):
            return {"result_a": ctx["value"] + 1}

        def compute_b(state, ctx):
            return {"result_b": state["result_a"] * 2}

        layers = [
            Layer(name="a", compute=compute_a, produces=frozenset({"result_a"})),
            Layer(name="b", compute=compute_b, requires=frozenset({"a"}), produces=frozenset({"result_b"})),
        ]
        result = run_pipeline(layers, {"value": 10})
        self.assertEqual(result["result_a"], 11)
        self.assertEqual(result["result_b"], 22)

    def test_initial_state_available(self):
        def compute_a(state, ctx):
            return {"output": state["seed"] + 1}

        layers = [
            Layer(name="a", compute=compute_a, produces=frozenset({"output"})),
        ]
        result = run_pipeline(layers, {}, {"seed": 100})
        self.assertEqual(result["output"], 101)

    def test_missing_output_raises(self):
        def bad_compute(state, ctx):
            return {"wrong_key": 42}

        layers = [
            Layer(name="a", compute=bad_compute, produces=frozenset({"expected_key"})),
        ]
        with self.assertRaises(MissingOutputError):
            run_pipeline(layers, {})

    def test_non_dict_output_raises(self):
        def bad_compute(state, ctx):
            return 42  # Not a dict

        layers = [
            Layer(name="a", compute=bad_compute, produces=frozenset({"x"})),
        ]
        with self.assertRaises(MissingOutputError):
            run_pipeline(layers, {})

    def test_compute_exception_raises_pipeline_error(self):
        def exploding_compute(state, ctx):
            raise ValueError("boom")

        layers = [
            Layer(name="a", compute=exploding_compute, produces=frozenset({"x"})),
        ]
        with self.assertRaises(PipelineError) as cm:
            run_pipeline(layers, {})
        self.assertIn("boom", str(cm.exception))

    def test_execution_log_recorded(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {"y": 2}, requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        result = run_pipeline(layers, {})
        log = result["_pipeline_execution_log"]
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["layer"], "a")
        self.assertEqual(log[1]["layer"], "b")
        self.assertEqual(log[0]["status"], "SUCCESS")
        self.assertEqual(log[1]["status"], "SUCCESS")

    def test_execution_order_recorded(self):
        layers = [
            Layer(name="a", compute=lambda s, c: {"x": 1}, produces=frozenset({"x"})),
            Layer(name="b", compute=lambda s, c: {"y": 2}, requires=frozenset({"a"}), produces=frozenset({"y"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["_pipeline_execution_order"], ["a", "b"])


class TestGuardedState(unittest.TestCase):
    """Test that GuardedState prevents undeclared access."""

    def test_undeclared_access_raises(self):
        """Layer accessing key from non-required layer raises."""
        def compute_a(state, ctx):
            return {"secret": 42}

        def compute_b(state, ctx):
            # b does NOT require a, but tries to read a's output
            return {"result": state["secret"]}

        layers = [
            Layer(name="a", compute=compute_a, produces=frozenset({"secret"})),
            Layer(name="b", compute=compute_b, produces=frozenset({"result"})),
        ]
        with self.assertRaises(UndeclaredInputError):
            run_pipeline(layers, {})

    def test_declared_access_succeeds(self):
        """Layer accessing key from required layer works."""
        def compute_a(state, ctx):
            return {"secret": 42}

        def compute_b(state, ctx):
            return {"result": state["secret"]}

        layers = [
            Layer(name="a", compute=compute_a, produces=frozenset({"secret"})),
            Layer(name="b", compute=compute_b, requires=frozenset({"a"}), produces=frozenset({"result"})),
        ]
        result = run_pipeline(layers, {})
        self.assertEqual(result["result"], 42)

    def test_initial_state_always_accessible(self):
        """Initial state keys are accessible by all layers."""
        def compute_a(state, ctx):
            return {"result": state["seed"]}

        layers = [
            Layer(name="a", compute=compute_a, produces=frozenset({"result"})),
        ]
        result = run_pipeline(layers, {}, {"seed": 99})
        self.assertEqual(result["result"], 99)

    def test_get_method_guarded(self):
        """state.get() is also guarded."""
        def compute_a(state, ctx):
            return {"secret": 42}

        def compute_b(state, ctx):
            return {"result": state.get("secret", 0)}

        layers = [
            Layer(name="a", compute=compute_a, produces=frozenset({"secret"})),
            Layer(name="b", compute=compute_b, produces=frozenset({"result"})),
        ]
        with self.assertRaises(UndeclaredInputError):
            run_pipeline(layers, {})


class TestCountryPipeline(unittest.TestCase):
    """Test the ISI country pipeline definition."""

    def test_country_pipeline_is_valid(self):
        """COUNTRY_PIPELINE must pass validation."""
        order = validate_pipeline(COUNTRY_PIPELINE)
        self.assertIsInstance(order, list)
        self.assertEqual(len(order), len(COUNTRY_PIPELINE))

    def test_country_pipeline_no_duplicate_names(self):
        names = [l.name for l in COUNTRY_PIPELINE]
        self.assertEqual(len(names), len(set(names)))

    def test_country_pipeline_all_layers_have_produces(self):
        for layer in COUNTRY_PIPELINE:
            self.assertTrue(
                len(layer.produces) > 0,
                f"Layer '{layer.name}' has no declared outputs",
            )

    def test_country_pipeline_has_required_layers(self):
        names = {l.name for l in COUNTRY_PIPELINE}
        required = {
            "severity", "governance", "falsification",
            "decision_usability", "external_validation",
            "construct_enforcement", "mapping_audit",
            "alignment_sensitivity", "empirical_alignment",
            "invariants", "failure_visibility", "reality_conflicts",
        }
        self.assertEqual(names, required)

    def test_country_pipeline_severity_before_governance(self):
        order = validate_pipeline(COUNTRY_PIPELINE)
        self.assertLess(order.index("severity"), order.index("governance"))

    def test_country_pipeline_governance_before_decision_usability(self):
        order = validate_pipeline(COUNTRY_PIPELINE)
        self.assertLess(order.index("governance"), order.index("decision_usability"))

    def test_country_pipeline_external_validation_before_construct(self):
        order = validate_pipeline(COUNTRY_PIPELINE)
        self.assertLess(order.index("external_validation"), order.index("construct_enforcement"))

    def test_country_pipeline_invariants_after_upstream(self):
        order = validate_pipeline(COUNTRY_PIPELINE)
        inv_idx = order.index("invariants")
        for dep in ["governance", "decision_usability", "external_validation",
                     "construct_enforcement", "mapping_audit", "alignment_sensitivity"]:
            self.assertLess(
                order.index(dep), inv_idx,
                f"invariants should come after {dep}",
            )

    def test_country_pipeline_visibility_after_invariants(self):
        order = validate_pipeline(COUNTRY_PIPELINE)
        self.assertLess(order.index("invariants"), order.index("failure_visibility"))

    def test_pipeline_order_is_deterministic(self):
        """Running validation 100 times produces same order."""
        reference = validate_pipeline(COUNTRY_PIPELINE)
        for _ in range(100):
            order = validate_pipeline(COUNTRY_PIPELINE)
            self.assertEqual(order, reference)


class TestPipelineOrderInvariance(unittest.TestCase):
    """Verify that reordering layers doesn't change execution order."""

    def test_reversed_registration_same_execution(self):
        """Even if layers are registered in reverse, execution order is the same."""
        reference = validate_pipeline(COUNTRY_PIPELINE)
        reversed_layers = list(reversed(COUNTRY_PIPELINE))
        reversed_order = validate_pipeline(reversed_layers)
        self.assertEqual(reference, reversed_order)

    def test_shuffled_registration_same_execution(self):
        """Even if layers are shuffled, execution order is the same."""
        import random
        reference = validate_pipeline(COUNTRY_PIPELINE)
        shuffled = list(COUNTRY_PIPELINE)
        rng = random.Random(42)
        for _ in range(10):
            rng.shuffle(shuffled)
            order = validate_pipeline(shuffled)
            self.assertEqual(reference, order)


if __name__ == "__main__":
    unittest.main()
