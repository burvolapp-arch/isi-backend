"""
backend.complexity_budget — Complexity Budget Engine

SECTION 13 of Ultimate Pass: Complexity Self-Regulation.

Problem addressed:
    The system can grow unboundedly complex. Each pass adds modules,
    layers, checks, and invariants. Without a complexity budget,
    the system becomes unmaintainable, untestable, and opaque.

Solution:
    The complexity budget engine tracks the system's structural
    complexity and raises alarms when budgets are exceeded:
    - Module count budget
    - Layer count budget
    - Invariant count budget
    - Line count budget per module
    - Cyclomatic depth budget

Design contract:
    - Complexity budgets are explicit, measurable, and enforced.
    - Exceeding a budget does not break the system but produces
      a WARNING that must be documented.
    - The budget is reviewed at each pass.
    - New modules must justify their complexity contribution.

Honesty note:
    A system that is too complex to audit is too complex to trust.
    The complexity budget is the system's self-awareness mechanism —
    it tells maintainers when the system is becoming dangerously
    intricate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# COMPLEXITY BUDGETS — hard limits
# ═══════════════════════════════════════════════════════════════════════════

# Module budget: max number of .py files in backend/
MAX_BACKEND_MODULES: int = 60

# Test budget: max number of test files
MAX_TEST_FILES: int = 60

# Invariant budget: max number of registered invariants
MAX_INVARIANTS: int = 60

# Line budget per module: max lines in any single .py file
MAX_LINES_PER_MODULE: int = 3000

# Total line budget: max total lines across all backend modules
MAX_TOTAL_LINES: int = 40_000

# Layer budget: max layers in the pipeline
MAX_PIPELINE_LAYERS: int = 20

# Enforcement rule budget
MAX_ENFORCEMENT_RULES: int = 20

# ── Endgame Pass v2: Additional complexity budgets ──

# Dependency depth: max import chain depth
MAX_DEPENDENCY_DEPTH: int = 8

# Reasoning chain: max steps in any single decision chain
MAX_REASONING_CHAIN_LENGTH: int = 15

# Authority conflict layers: max number of authority resolution layers
MAX_AUTHORITY_CONFLICT_LAYERS: int = 5


class BudgetStatus:
    """Status of a complexity budget."""
    WITHIN = "WITHIN"       # Under budget
    WARNING = "WARNING"     # Over 80% of budget
    EXCEEDED = "EXCEEDED"   # Over budget


VALID_BUDGET_STATUSES = frozenset({
    BudgetStatus.WITHIN,
    BudgetStatus.WARNING,
    BudgetStatus.EXCEEDED,
})


def _check_budget(
    name: str,
    current: int,
    budget: int,
    warning_pct: float = 0.80,
) -> dict[str, Any]:
    """Check a single budget item."""
    pct = current / budget if budget > 0 else 1.0

    if current > budget:
        status = BudgetStatus.EXCEEDED
    elif pct >= warning_pct:
        status = BudgetStatus.WARNING
    else:
        status = BudgetStatus.WITHIN

    return {
        "name": name,
        "current": current,
        "budget": budget,
        "utilization_pct": round(pct * 100, 1),
        "status": status,
        "remaining": max(0, budget - current),
    }


def audit_complexity(
    backend_dir: Path | None = None,
    tests_dir: Path | None = None,
    n_invariants: int = 0,
    n_pipeline_layers: int = 0,
    n_enforcement_rules: int = 0,
    n_dependency_depth: int = 0,
    n_reasoning_chain_length: int = 0,
    n_authority_conflict_layers: int = 0,
) -> dict[str, Any]:
    """Audit the system's structural complexity against budgets.

    Args:
        backend_dir: Path to backend/ directory.
        tests_dir: Path to tests/ directory.
        n_invariants: Number of registered invariants.
        n_pipeline_layers: Number of pipeline layers.
        n_enforcement_rules: Number of enforcement rules.
        n_dependency_depth: Maximum import chain depth.
        n_reasoning_chain_length: Maximum reasoning chain length.
        n_authority_conflict_layers: Number of authority conflict resolution layers.

    Returns:
        Complexity audit with per-budget status and overall assessment.
    """
    budgets: list[dict[str, Any]] = []
    exceeded: list[str] = []
    warnings: list[str] = []

    # ── Module count ──
    n_modules = 0
    max_module_lines = 0
    total_lines = 0
    largest_module = ""

    if backend_dir is not None and backend_dir.is_dir():
        for py_file in backend_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            n_modules += 1
            lines = py_file.read_text(encoding="utf-8").count("\n") + 1
            total_lines += lines
            if lines > max_module_lines:
                max_module_lines = lines
                largest_module = py_file.name

    module_budget = _check_budget("backend_modules", n_modules, MAX_BACKEND_MODULES)
    budgets.append(module_budget)
    if module_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(f"Backend modules: {n_modules}/{MAX_BACKEND_MODULES}")
    elif module_budget["status"] == BudgetStatus.WARNING:
        warnings.append(f"Backend modules: {n_modules}/{MAX_BACKEND_MODULES} (≥80%)")

    # ── Test file count ──
    n_tests = 0
    if tests_dir is not None and tests_dir.is_dir():
        for py_file in tests_dir.glob("test_*.py"):
            n_tests += 1

    test_budget = _check_budget("test_files", n_tests, MAX_TEST_FILES)
    budgets.append(test_budget)
    if test_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(f"Test files: {n_tests}/{MAX_TEST_FILES}")
    elif test_budget["status"] == BudgetStatus.WARNING:
        warnings.append(f"Test files: {n_tests}/{MAX_TEST_FILES} (≥80%)")

    # ── Invariant count ──
    inv_budget = _check_budget("invariants", n_invariants, MAX_INVARIANTS)
    budgets.append(inv_budget)
    if inv_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(f"Invariants: {n_invariants}/{MAX_INVARIANTS}")
    elif inv_budget["status"] == BudgetStatus.WARNING:
        warnings.append(f"Invariants: {n_invariants}/{MAX_INVARIANTS} (≥80%)")

    # ── Lines per module ──
    lines_budget = _check_budget(
        "max_lines_per_module", max_module_lines, MAX_LINES_PER_MODULE,
    )
    budgets.append(lines_budget)
    if lines_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(
            f"Module {largest_module}: {max_module_lines}/{MAX_LINES_PER_MODULE} lines"
        )
    elif lines_budget["status"] == BudgetStatus.WARNING:
        warnings.append(
            f"Module {largest_module}: {max_module_lines}/{MAX_LINES_PER_MODULE} lines (≥80%)"
        )

    # ── Total lines ──
    total_budget = _check_budget("total_lines", total_lines, MAX_TOTAL_LINES)
    budgets.append(total_budget)
    if total_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(f"Total lines: {total_lines}/{MAX_TOTAL_LINES}")
    elif total_budget["status"] == BudgetStatus.WARNING:
        warnings.append(f"Total lines: {total_lines}/{MAX_TOTAL_LINES} (≥80%)")

    # ── Pipeline layers ──
    layer_budget = _check_budget(
        "pipeline_layers", n_pipeline_layers, MAX_PIPELINE_LAYERS,
    )
    budgets.append(layer_budget)
    if layer_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(f"Pipeline layers: {n_pipeline_layers}/{MAX_PIPELINE_LAYERS}")

    # ── Enforcement rules ──
    enf_budget = _check_budget(
        "enforcement_rules", n_enforcement_rules, MAX_ENFORCEMENT_RULES,
    )
    budgets.append(enf_budget)
    if enf_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(
            f"Enforcement rules: {n_enforcement_rules}/{MAX_ENFORCEMENT_RULES}"
        )

    # ── Dependency depth ──
    dep_budget = _check_budget(
        "dependency_depth", n_dependency_depth, MAX_DEPENDENCY_DEPTH,
    )
    budgets.append(dep_budget)
    if dep_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(
            f"Dependency depth: {n_dependency_depth}/{MAX_DEPENDENCY_DEPTH}"
        )
    elif dep_budget["status"] == BudgetStatus.WARNING:
        warnings.append(
            f"Dependency depth: {n_dependency_depth}/{MAX_DEPENDENCY_DEPTH} (≥80%)"
        )

    # ── Reasoning chain length ──
    chain_budget = _check_budget(
        "reasoning_chain_length", n_reasoning_chain_length,
        MAX_REASONING_CHAIN_LENGTH,
    )
    budgets.append(chain_budget)
    if chain_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(
            f"Reasoning chain: {n_reasoning_chain_length}/{MAX_REASONING_CHAIN_LENGTH}"
        )
    elif chain_budget["status"] == BudgetStatus.WARNING:
        warnings.append(
            f"Reasoning chain: {n_reasoning_chain_length}/{MAX_REASONING_CHAIN_LENGTH} (≥80%)"
        )

    # ── Authority conflict layers ──
    auth_budget = _check_budget(
        "authority_conflict_layers", n_authority_conflict_layers,
        MAX_AUTHORITY_CONFLICT_LAYERS,
    )
    budgets.append(auth_budget)
    if auth_budget["status"] == BudgetStatus.EXCEEDED:
        exceeded.append(
            f"Authority conflict layers: {n_authority_conflict_layers}/{MAX_AUTHORITY_CONFLICT_LAYERS}"
        )
    elif auth_budget["status"] == BudgetStatus.WARNING:
        warnings.append(
            f"Authority conflict layers: {n_authority_conflict_layers}/{MAX_AUTHORITY_CONFLICT_LAYERS} (≥80%)"
        )

    # ── Overall status ──
    if exceeded:
        overall = BudgetStatus.EXCEEDED
    elif warnings:
        overall = BudgetStatus.WARNING
    else:
        overall = BudgetStatus.WITHIN

    return {
        "overall_status": overall,
        "budgets": budgets,
        "n_budgets_checked": len(budgets),
        "n_exceeded": len(exceeded),
        "n_warnings": len(warnings),
        "exceeded": exceeded,
        "warnings": warnings,
        "summary": {
            "n_backend_modules": n_modules,
            "n_test_files": n_tests,
            "n_invariants": n_invariants,
            "n_pipeline_layers": n_pipeline_layers,
            "n_enforcement_rules": n_enforcement_rules,
            "n_dependency_depth": n_dependency_depth,
            "n_reasoning_chain_length": n_reasoning_chain_length,
            "n_authority_conflict_layers": n_authority_conflict_layers,
            "max_module_lines": max_module_lines,
            "largest_module": largest_module,
            "total_lines": total_lines,
        },
        "honesty_note": (
            f"Complexity audit: {overall}. "
            f"{len(budgets)} budgets checked, {len(exceeded)} exceeded, "
            f"{len(warnings)} at warning level. "
            f"{'System is within all complexity budgets.' if overall == BudgetStatus.WITHIN else ''}"
            f"{'System is approaching complexity limits.' if overall == BudgetStatus.WARNING else ''}"
            f"{'ALERT: System has exceeded complexity budgets. Review and refactor.' if overall == BudgetStatus.EXCEEDED else ''}"
        ),
    }
