"""
tests.test_complexity_budget_enforcement — Complexity Budget Enforcement

Verifies:
    - Dependency depth budget is enforced.
    - Reasoning chain length budget is enforced.
    - Authority conflict layer budget is enforced.
    - All three new budgets interact correctly with existing budgets.
    - Summary includes new metrics.
"""

from __future__ import annotations

from backend.complexity_budget import (
    BudgetStatus,
    MAX_DEPENDENCY_DEPTH,
    MAX_REASONING_CHAIN_LENGTH,
    MAX_AUTHORITY_CONFLICT_LAYERS,
    audit_complexity,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _find_budget(result: dict, name: str) -> dict | None:
    """Find a specific budget item by name."""
    for b in result["budgets"]:
        if b["name"] == name:
            return b
    return None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: DEPENDENCY DEPTH
# ═══════════════════════════════════════════════════════════════════════════

class TestDependencyDepthBudget:
    """Dependency depth must be budgeted."""

    def test_max_dependency_depth_is_8(self):
        assert MAX_DEPENDENCY_DEPTH == 8

    def test_depth_within_budget_passes(self):
        result = audit_complexity(n_dependency_depth=5)
        budget = _find_budget(result, "dependency_depth")
        assert budget is not None
        assert budget["status"] == BudgetStatus.WITHIN

    def test_depth_at_limit_passes(self):
        result = audit_complexity(n_dependency_depth=MAX_DEPENDENCY_DEPTH)
        budget = _find_budget(result, "dependency_depth")
        assert budget is not None
        assert budget["status"] != BudgetStatus.EXCEEDED

    def test_depth_exceeding_limit_fails(self):
        result = audit_complexity(n_dependency_depth=MAX_DEPENDENCY_DEPTH + 1)
        budget = _find_budget(result, "dependency_depth")
        assert budget is not None
        assert budget["status"] == BudgetStatus.EXCEEDED
        assert result["overall_status"] == BudgetStatus.EXCEEDED
        assert result["n_exceeded"] > 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: REASONING CHAIN LENGTH
# ═══════════════════════════════════════════════════════════════════════════

class TestReasoningChainLengthBudget:
    """Reasoning chain length must be budgeted."""

    def test_max_reasoning_chain_length_is_15(self):
        assert MAX_REASONING_CHAIN_LENGTH == 15

    def test_chain_within_budget_passes(self):
        result = audit_complexity(n_reasoning_chain_length=10)
        budget = _find_budget(result, "reasoning_chain_length")
        assert budget is not None
        assert budget["status"] == BudgetStatus.WITHIN

    def test_chain_at_limit_passes(self):
        result = audit_complexity(
            n_reasoning_chain_length=MAX_REASONING_CHAIN_LENGTH,
        )
        budget = _find_budget(result, "reasoning_chain_length")
        assert budget is not None
        assert budget["status"] != BudgetStatus.EXCEEDED

    def test_chain_exceeding_limit_fails(self):
        result = audit_complexity(
            n_reasoning_chain_length=MAX_REASONING_CHAIN_LENGTH + 1,
        )
        budget = _find_budget(result, "reasoning_chain_length")
        assert budget is not None
        assert budget["status"] == BudgetStatus.EXCEEDED
        assert result["overall_status"] == BudgetStatus.EXCEEDED


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: AUTHORITY CONFLICT LAYERS
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthorityConflictLayersBudget:
    """Authority conflict layer count must be budgeted."""

    def test_max_authority_conflict_layers_is_5(self):
        assert MAX_AUTHORITY_CONFLICT_LAYERS == 5

    def test_layers_within_budget_passes(self):
        result = audit_complexity(n_authority_conflict_layers=3)
        budget = _find_budget(result, "authority_conflict_layers")
        assert budget is not None
        assert budget["status"] == BudgetStatus.WITHIN

    def test_layers_at_limit_passes(self):
        result = audit_complexity(
            n_authority_conflict_layers=MAX_AUTHORITY_CONFLICT_LAYERS,
        )
        budget = _find_budget(result, "authority_conflict_layers")
        assert budget is not None
        assert budget["status"] != BudgetStatus.EXCEEDED

    def test_layers_exceeding_limit_fails(self):
        result = audit_complexity(
            n_authority_conflict_layers=MAX_AUTHORITY_CONFLICT_LAYERS + 1,
        )
        budget = _find_budget(result, "authority_conflict_layers")
        assert budget is not None
        assert budget["status"] == BudgetStatus.EXCEEDED
        assert result["overall_status"] == BudgetStatus.EXCEEDED


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: ALL THREE EXCEED SIMULTANEOUSLY
# ═══════════════════════════════════════════════════════════════════════════

class TestAllNewBudgetsExceed:
    """All three new budgets exceeded simultaneously."""

    def test_all_three_exceeded(self):
        result = audit_complexity(
            n_dependency_depth=MAX_DEPENDENCY_DEPTH + 5,
            n_reasoning_chain_length=MAX_REASONING_CHAIN_LENGTH + 5,
            n_authority_conflict_layers=MAX_AUTHORITY_CONFLICT_LAYERS + 5,
        )
        assert result["overall_status"] == BudgetStatus.EXCEEDED
        assert result["n_exceeded"] >= 3


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: SUMMARY INCLUDES NEW METRICS
# ═══════════════════════════════════════════════════════════════════════════

class TestSummaryNewMetrics:
    """Summary must include all new budget dimensions."""

    def test_summary_has_dependency_depth(self):
        result = audit_complexity(n_dependency_depth=3)
        summary = result["summary"]
        assert "n_dependency_depth" in summary
        assert summary["n_dependency_depth"] == 3

    def test_summary_has_reasoning_chain_length(self):
        result = audit_complexity(n_reasoning_chain_length=7)
        summary = result["summary"]
        assert "n_reasoning_chain_length" in summary
        assert summary["n_reasoning_chain_length"] == 7

    def test_summary_has_authority_conflict_layers(self):
        result = audit_complexity(n_authority_conflict_layers=2)
        summary = result["summary"]
        assert "n_authority_conflict_layers" in summary
        assert summary["n_authority_conflict_layers"] == 2

    def test_all_zero_still_in_summary(self):
        result = audit_complexity()
        summary = result["summary"]
        assert "n_dependency_depth" in summary
        assert "n_reasoning_chain_length" in summary
        assert "n_authority_conflict_layers" in summary


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: INTERACTION WITH EXISTING BUDGETS
# ═══════════════════════════════════════════════════════════════════════════

class TestInteractionWithExistingBudgets:
    """New budgets must work alongside existing budgets."""

    def test_existing_invariant_budget_still_works(self):
        from backend.complexity_budget import MAX_INVARIANTS
        result = audit_complexity(n_invariants=MAX_INVARIANTS + 1)
        assert result["overall_status"] == BudgetStatus.EXCEEDED

    def test_new_and_old_budgets_combined(self):
        from backend.complexity_budget import MAX_INVARIANTS
        result = audit_complexity(
            n_invariants=MAX_INVARIANTS + 1,
            n_dependency_depth=MAX_DEPENDENCY_DEPTH + 1,
        )
        assert result["overall_status"] == BudgetStatus.EXCEEDED
        assert result["n_exceeded"] >= 2

    def test_output_has_required_fields(self):
        result = audit_complexity()
        required = [
            "overall_status", "budgets", "n_budgets_checked",
            "n_exceeded", "n_warnings", "exceeded", "warnings",
            "summary", "honesty_note",
        ]
        for field in required:
            assert field in result, f"Missing field: {field}"

    def test_warning_threshold(self):
        """80% of budget should trigger WARNING."""
        # 80% of 8 = 6.4, so 7 should trigger warning
        result = audit_complexity(n_dependency_depth=7)
        budget = _find_budget(result, "dependency_depth")
        assert budget is not None
        assert budget["status"] == BudgetStatus.WARNING
