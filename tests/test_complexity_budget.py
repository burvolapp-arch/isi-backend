"""
tests/test_complexity_budget.py — Tests for Complexity Budget Engine (Section 13)
"""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.complexity_budget import (
    BudgetStatus,
    MAX_BACKEND_MODULES,
    MAX_ENFORCEMENT_RULES,
    MAX_INVARIANTS,
    MAX_LINES_PER_MODULE,
    MAX_PIPELINE_LAYERS,
    MAX_TEST_FILES,
    MAX_TOTAL_LINES,
    VALID_BUDGET_STATUSES,
    audit_complexity,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
TESTS_DIR = PROJECT_ROOT / "tests"


class TestBudgetStatus(unittest.TestCase):
    """Budget statuses must be formally defined."""

    def test_three_statuses(self):
        self.assertEqual(len(VALID_BUDGET_STATUSES), 3)

    def test_expected_statuses(self):
        expected = {"WITHIN", "WARNING", "EXCEEDED"}
        self.assertEqual(VALID_BUDGET_STATUSES, expected)


class TestBudgetLimits(unittest.TestCase):
    """Budget limits must be reasonable."""

    def test_module_budget_reasonable(self):
        self.assertGreaterEqual(MAX_BACKEND_MODULES, 40)
        self.assertLessEqual(MAX_BACKEND_MODULES, 100)

    def test_test_budget_reasonable(self):
        self.assertGreaterEqual(MAX_TEST_FILES, 40)
        self.assertLessEqual(MAX_TEST_FILES, 100)

    def test_invariant_budget_reasonable(self):
        self.assertGreaterEqual(MAX_INVARIANTS, 30)
        self.assertLessEqual(MAX_INVARIANTS, 100)

    def test_line_budget_per_module_reasonable(self):
        self.assertGreaterEqual(MAX_LINES_PER_MODULE, 1000)
        self.assertLessEqual(MAX_LINES_PER_MODULE, 5000)


class TestAuditComplexity(unittest.TestCase):
    """Complexity audit must check all budgets."""

    def test_audit_with_no_inputs(self):
        result = audit_complexity()
        self.assertIn("overall_status", result)
        self.assertIn("budgets", result)
        self.assertGreater(result["n_budgets_checked"], 0)

    def test_audit_with_real_dirs(self):
        """Audit against the actual project directories."""
        result = audit_complexity(
            backend_dir=BACKEND_DIR,
            tests_dir=TESTS_DIR,
            n_invariants=37,
            n_pipeline_layers=12,
            n_enforcement_rules=8,
        )
        self.assertIn(result["overall_status"], VALID_BUDGET_STATUSES)
        # Summary should reflect real counts
        summary = result["summary"]
        self.assertGreater(summary["n_backend_modules"], 30)
        self.assertGreater(summary["n_test_files"], 20)

    def test_exceeded_budget_detected(self):
        """Exceeding a budget should be flagged."""
        result = audit_complexity(
            n_invariants=MAX_INVARIANTS + 10,  # Over budget
        )
        self.assertGreater(result["n_exceeded"], 0)

    def test_within_budget_clean(self):
        """Under-budget should be clean."""
        result = audit_complexity(
            n_invariants=5,
            n_pipeline_layers=5,
            n_enforcement_rules=3,
        )
        # These specific budgets should be within
        for budget in result["budgets"]:
            if budget["name"] in ("invariants", "pipeline_layers", "enforcement_rules"):
                self.assertEqual(budget["status"], BudgetStatus.WITHIN)

    def test_warning_threshold(self):
        """80%+ utilization should trigger warning."""
        # 80% of MAX_INVARIANTS
        threshold = int(MAX_INVARIANTS * 0.81)
        result = audit_complexity(n_invariants=threshold)
        inv_budget = next(
            b for b in result["budgets"] if b["name"] == "invariants"
        )
        self.assertIn(inv_budget["status"], {BudgetStatus.WARNING, BudgetStatus.EXCEEDED})

    def test_result_has_honesty_note(self):
        result = audit_complexity()
        self.assertIn("honesty_note", result)

    def test_summary_has_all_counts(self):
        result = audit_complexity(
            backend_dir=BACKEND_DIR,
            tests_dir=TESTS_DIR,
        )
        summary = result["summary"]
        self.assertIn("n_backend_modules", summary)
        self.assertIn("n_test_files", summary)
        self.assertIn("total_lines", summary)
        self.assertIn("largest_module", summary)


class TestActualProjectComplexity(unittest.TestCase):
    """The actual project must be within complexity budgets."""

    def test_backend_modules_within_budget(self):
        n_modules = sum(
            1 for f in BACKEND_DIR.glob("*.py")
            if not f.name.startswith("_")
        )
        self.assertLessEqual(
            n_modules, MAX_BACKEND_MODULES,
            f"Backend has {n_modules} modules, budget is {MAX_BACKEND_MODULES}.",
        )

    def test_test_files_within_budget(self):
        n_tests = sum(1 for _ in TESTS_DIR.glob("test_*.py"))
        self.assertLessEqual(
            n_tests, MAX_TEST_FILES,
            f"Tests has {n_tests} files, budget is {MAX_TEST_FILES}.",
        )

    def test_no_module_exceeds_line_budget(self):
        for py_file in BACKEND_DIR.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            lines = py_file.read_text(encoding="utf-8").count("\n") + 1
            self.assertLessEqual(
                lines, MAX_LINES_PER_MODULE,
                f"{py_file.name} has {lines} lines, budget is {MAX_LINES_PER_MODULE}.",
            )


if __name__ == "__main__":
    unittest.main()
