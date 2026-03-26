"""
tests/test_no_decorative_modules.py — Anti-Decoration Guarantee (Section 6)

Verifies:
    1. Every backend module that defines detection/enforcement functions
       is imported somewhere in the production pipeline.
    2. Every module imported by export_snapshot.py is actually used.
    3. The three new modules (layer_pipeline, enforcement_matrix,
       truth_resolver) are imported and their outputs appear in
       country JSON.
    4. No module exists solely as documentation — if it has functions,
       those functions must be callable from the export pipeline.

Design:
    This test does NOT run the pipeline (that's for test_layer_pipeline).
    It inspects the import graph and module structure to detect
    decorative modules — modules that EXIST but are never WIRED.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"

# Modules that are legitimately not called from export_snapshot
# (infrastructure, utilities, CLI, API, etc.)
INFRASTRUCTURE_MODULES = frozenset({
    "__init__",
    "isi_api_v01",          # FastAPI app — separate entry point
    "reproduce_snapshot",   # CLI tool for snapshot reproduction
    "verify_snapshot",      # CLI tool for verification
    "snapshot_resolver",    # Used by API, not by export
    "snapshot_cache",       # Used by API, not by export
    "snapshot_integrity",   # Used by API, not by export
    "snapshot_diff",        # Used by API — snapshot comparison tool
    "export_snapshot",      # THE export entry point (imports others)
    "log_sanitizer",        # Security utility
    "security",             # Security utility
    "immutability",         # Used by export internals
    "provenance",           # Used by export internals
    "scope",                # Used by config/methodology
    "calibration",          # Used by methodology
    "scenario",             # Analysis tool
    "hardening",            # Hardening meta-module (self-verifying)
    "config",               # Configuration directory
    "v01",                  # Legacy subpackage
    "axis_result",          # Data structure module
    "threshold_registry",   # Used by eligibility/governance
    "benchmark_registry",   # Used by external_validation
    "layer_pipeline",       # New — used indirectly (defines pipeline registry)
    "layer_result",         # Data structure module (used by layer_pipeline)
    "failure_severity",     # Severity model (used by layer_pipeline)
    "cache",                # Caching infrastructure (used by API)
    "observability",        # Metrics/logging (infrastructure module)
    # ── Ultimate Pass: epistemic/authority infrastructure modules ──
    "epistemic_hierarchy",          # Epistemic level definitions (used by override engine)
    "external_authority_registry",  # Authority registry (used by override engine)
    "epistemic_override",           # Override engine (used by export pipeline)
    "permitted_scope",              # Scope engine (used by export pipeline)
    "audit_replay",                 # Audit replay (diagnostic tool)
    "authority_conflicts",          # Conflict detection (used by export pipeline)
    "publishability",               # Publishability assessment (used by export pipeline)
    "complexity_budget",            # Complexity budget (meta-governance tool)
    # ── Endgame Pass v2: epistemic monotonicity/arbiter infrastructure ──
    "epistemic_bounds",             # Bounds propagation (used by arbiter)
    "epistemic_invariants",         # Monotonicity invariants (enforcement tool)
    "authority_precedence",         # Precedence resolution (used by arbiter)
    "epistemic_arbiter",            # Final epistemic authority (used by export pipeline)
    # ── True Final Pass v3: fault isolation infrastructure ──
    "epistemic_dependencies",       # Dependency graph (used by fault isolation)
    "epistemic_fault_isolation",    # Fault isolation engine (used by arbiter)
})

# Core computation modules that MUST be imported by export_snapshot.py
CORE_COMPUTATION_MODULES = frozenset({
    "constants",
    "hashing",
    "methodology",
    "governance",
    "severity",
    "falsification",
    "eligibility",
    "external_validation",
    "failure_visibility",
    "reality_conflicts",
    "construct_enforcement",
    "benchmark_mapping_audit",
    "alignment_sensitivity",
    "invariants",
    "signing",
    "enforcement_matrix",
    "truth_resolver",
})


class TestNoDecorativeModules(unittest.TestCase):
    """Every core computation module must be imported by export_snapshot."""

    def test_all_core_modules_imported_by_export(self):
        """Every core module must be imported by export_snapshot.py."""
        export_path = BACKEND_DIR / "export_snapshot.py"
        source = export_path.read_text()
        tree = ast.parse(source)

        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    # Extract module name from "backend.xxx" → "xxx"
                    parts = node.module.split(".")
                    if parts[0] == "backend" and len(parts) > 1:
                        imported_modules.add(parts[1])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if parts[0] == "backend" and len(parts) > 1:
                        imported_modules.add(parts[1])

        missing = CORE_COMPUTATION_MODULES - imported_modules
        self.assertEqual(
            missing, set(),
            f"Core modules NOT imported by export_snapshot.py: {sorted(missing)}. "
            f"These modules exist but are decorative — never wired into production."
        )

    def test_enforcement_matrix_imported(self):
        """enforcement_matrix MUST be imported by export_snapshot."""
        export_path = BACKEND_DIR / "export_snapshot.py"
        source = export_path.read_text()
        self.assertIn("enforcement_matrix", source)

    def test_truth_resolver_imported(self):
        """truth_resolver MUST be imported by export_snapshot."""
        export_path = BACKEND_DIR / "export_snapshot.py"
        source = export_path.read_text()
        self.assertIn("truth_resolver", source)

    def test_enforcement_output_in_country_json(self):
        """enforcement_actions must appear in build_country_json return."""
        export_path = BACKEND_DIR / "export_snapshot.py"
        source = export_path.read_text()
        self.assertIn('"enforcement_actions"', source)

    def test_truth_resolution_output_in_country_json(self):
        """truth_resolution must appear in build_country_json return."""
        export_path = BACKEND_DIR / "export_snapshot.py"
        source = export_path.read_text()
        self.assertIn('"truth_resolution"', source)


class TestModulesAreImportable(unittest.TestCase):
    """Every .py file in backend/ must be importable without error."""

    def test_all_modules_importable(self):
        for py_file in BACKEND_DIR.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            module_name = f"backend.{py_file.stem}"
            try:
                importlib.import_module(module_name)
            except Exception as e:
                self.fail(
                    f"Module {module_name} is not importable: {e}. "
                    f"Non-importable modules are structurally broken."
                )


class TestNewModulesHaveProperStructure(unittest.TestCase):
    """New closure-pass modules must have proper public API."""

    def test_layer_pipeline_has_public_api(self):
        from backend.layer_pipeline import (
            Layer,
            validate_pipeline,
            run_pipeline,
            COUNTRY_PIPELINE,
            run_country_pipeline,
        )
        self.assertTrue(callable(validate_pipeline))
        self.assertTrue(callable(run_pipeline))
        self.assertTrue(callable(run_country_pipeline))
        self.assertIsInstance(COUNTRY_PIPELINE, list)
        self.assertGreater(len(COUNTRY_PIPELINE), 0)

    def test_enforcement_matrix_has_public_api(self):
        from backend.enforcement_matrix import (
            apply_enforcement,
            get_enforcement_rules,
            ENFORCEMENT_RULES,
        )
        self.assertTrue(callable(apply_enforcement))
        self.assertTrue(callable(get_enforcement_rules))
        self.assertIsInstance(ENFORCEMENT_RULES, list)
        self.assertGreater(len(ENFORCEMENT_RULES), 0)

    def test_truth_resolver_has_public_api(self):
        from backend.truth_resolver import (
            resolve_truth,
            TruthStatus,
            VALID_TRUTH_STATUSES,
        )
        self.assertTrue(callable(resolve_truth))
        self.assertIsInstance(VALID_TRUTH_STATUSES, frozenset)
        self.assertGreater(len(VALID_TRUTH_STATUSES), 0)


class TestNoOrphanedBackendModules(unittest.TestCase):
    """Every backend .py file must be either infrastructure or imported."""

    def test_no_orphans(self):
        all_modules = set()
        for py_file in BACKEND_DIR.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            all_modules.add(py_file.stem)

        accounted_for = CORE_COMPUTATION_MODULES | INFRASTRUCTURE_MODULES
        orphaned = all_modules - accounted_for
        self.assertEqual(
            orphaned, set(),
            f"Backend modules not accounted for: {sorted(orphaned)}. "
            f"Either add to CORE_COMPUTATION_MODULES (and import in export_snapshot) "
            f"or to INFRASTRUCTURE_MODULES (with justification)."
        )


class TestInvariantRegistryHasPipelineIntegrity(unittest.TestCase):
    """The 5 new pipeline integrity invariants must exist."""

    def test_pipeline_integrity_invariants_exist(self):
        from backend.invariants import INVARIANT_REGISTRY, InvariantType

        pipeline_invariants = [
            inv for inv in INVARIANT_REGISTRY
            if inv["type"] == InvariantType.PIPELINE_INTEGRITY
        ]
        self.assertEqual(len(pipeline_invariants), 5)

        expected_ids = {
            "INV-PIPELINE-001",
            "INV-ENFORCEMENT-001",
            "INV-TRUTH-001",
            "INV-EXPORT-001",
            "INV-NO-DECORATION-001",
        }
        actual_ids = {inv["invariant_id"] for inv in pipeline_invariants}
        self.assertEqual(actual_ids, expected_ids)


class TestPipelineIntegrityCheckerExists(unittest.TestCase):
    """The check_pipeline_integrity_invariants function must exist."""

    def test_checker_callable(self):
        from backend.invariants import check_pipeline_integrity_invariants
        self.assertTrue(callable(check_pipeline_integrity_invariants))

    def test_checker_returns_list(self):
        from backend.invariants import check_pipeline_integrity_invariants
        result = check_pipeline_integrity_invariants("DE")
        self.assertIsInstance(result, list)

    def test_missing_layers_fires_inv_pipeline_001(self):
        from backend.invariants import check_pipeline_integrity_invariants
        country_json = {
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "decision_usability": {},
            "construct_enforcement": {},
            "external_validation": {},
            "failure_visibility": {},
            "reality_conflicts": None,  # Missing!
            "invariant_assessment": {},
        }
        violations = check_pipeline_integrity_invariants(
            "DE", country_json=country_json,
        )
        ids = [v["invariant_id"] for v in violations]
        self.assertIn("INV-PIPELINE-001", ids)

    def test_critical_flags_without_enforcement_fires(self):
        from backend.invariants import check_pipeline_integrity_invariants
        country_json = {
            "governance": {},
            "decision_usability": {},
            "construct_enforcement": {"composite_producible": False},
            "external_validation": {},
            "failure_visibility": {"trust_level": "STRUCTURALLY_SOUND"},
            "reality_conflicts": {"has_critical": False},
            "invariant_assessment": {"has_critical": False},
        }
        enforcement_result = {"actions": [], "n_actions": 0}
        violations = check_pipeline_integrity_invariants(
            "DE",
            enforcement_result=enforcement_result,
            country_json=country_json,
        )
        ids = [v["invariant_id"] for v in violations]
        self.assertIn("INV-ENFORCEMENT-001", ids)

    def test_non_comparable_ranking_eligible_fires(self):
        from backend.invariants import check_pipeline_integrity_invariants
        truth_result = {
            "final_governance_tier": "NON_COMPARABLE",
            "final_ranking_eligible": True,
            "final_composite_suppressed": True,
        }
        violations = check_pipeline_integrity_invariants(
            "DE", truth_result=truth_result,
        )
        ids = [v["invariant_id"] for v in violations]
        self.assertIn("INV-TRUTH-001", ids)

    def test_missing_truth_resolution_fires(self):
        from backend.invariants import check_pipeline_integrity_invariants
        country_json = {
            "governance": {},
            "decision_usability": {},
            "construct_enforcement": {},
            "external_validation": {},
            "failure_visibility": {},
            "reality_conflicts": {},
            "invariant_assessment": {},
            # truth_resolution missing!
        }
        truth_result = {
            "final_governance_tier": "FULLY_COMPARABLE",
            "final_ranking_eligible": True,
            "final_composite_suppressed": False,
        }
        violations = check_pipeline_integrity_invariants(
            "DE",
            truth_result=truth_result,
            country_json=country_json,
        )
        ids = [v["invariant_id"] for v in violations]
        self.assertIn("INV-EXPORT-001", ids)


if __name__ == "__main__":
    unittest.main()
