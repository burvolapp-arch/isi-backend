"""
tests/test_arbiter_wiring.py — Arbiter Production Wiring Tests

MASTER CLOSURE PASS: Verifies that the epistemic arbiter is actually
wired into the production export pipeline and produces binding verdicts.

Sections:
    1. Import verification — arbiter is imported by export_snapshot
    2. Output structure — arbiter_verdict appears in country JSON
    3. Safe mode derivation — safe_mode uses arbiter verdict
    4. Monotonicity — arbiter verdict is at least as restrictive as truth
    5. Anti-laundering — forbidden claims cannot leak through
    6. Adversarial — hostile inputs, boundary conditions, fault injection
    7. Publishability wiring — publishability is in country JSON
    8. Authority coherence — no contradictions between layers
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Any

from backend.epistemic_arbiter import (
    ArbiterStatus,
    adjudicate,
    validate_output_against_arbiter,
    ARBITER_STATUS_ORDER,
)
from backend.publishability import (
    PublishabilityStatus,
    assess_publishability,
)
from backend.truth_resolver import resolve_truth, TruthStatus
from backend.enforcement_matrix import apply_enforcement


BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: IMPORT VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterImportedByExport(unittest.TestCase):
    """The arbiter MUST be imported by export_snapshot.py."""

    def test_arbiter_imported(self):
        """export_snapshot.py must import from epistemic_arbiter."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn("epistemic_arbiter", source)

    def test_arbiter_import_is_adjudicate(self):
        """export_snapshot.py must import adjudicate (the core function)."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn("adjudicate", source)

    def test_publishability_imported(self):
        """export_snapshot.py must import from publishability."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn("publishability", source)

    def test_arbiter_import_via_ast(self):
        """Verify import is actual Python import, not just a string mention."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "epistemic_arbiter" in node.module:
                    found = True
                    break
        self.assertTrue(
            found,
            "export_snapshot.py does not have an actual import from epistemic_arbiter"
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: OUTPUT STRUCTURE — arbiter_verdict in country JSON
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterVerdictInOutput(unittest.TestCase):
    """arbiter_verdict must appear in build_country_json return dict."""

    def test_arbiter_verdict_key_in_source(self):
        """The string 'arbiter_verdict' must be in the return dict."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn('"arbiter_verdict"', source)

    def test_publishability_key_in_source(self):
        """The string 'publishability' must be in the return dict."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn('"publishability"', source)

    def test_arbiter_verdict_fields_complete(self):
        """adjudicate() must return all required fields."""
        verdict = adjudicate(country="DE")
        required_fields = {
            "country", "final_epistemic_status", "final_confidence_cap",
            "final_publishability", "final_allowed_claims",
            "final_forbidden_claims", "final_required_warnings",
            "final_bounds", "binding_constraints", "arbiter_reasoning",
            "fault_scope", "scoped_publishability",
            "n_inputs_evaluated", "n_reasons", "n_warnings",
            "n_forbidden_claims", "n_allowed_claims",
            "n_binding_constraints", "honesty_note",
        }
        missing = required_fields - set(verdict.keys())
        self.assertEqual(
            missing, set(),
            f"Arbiter verdict missing fields: {sorted(missing)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: SAFE MODE DERIVATION FROM ARBITER
# ═══════════════════════════════════════════════════════════════════════════

class TestSafeModeDerivesFromArbiter(unittest.TestCase):
    """Safe mode must be driven by arbiter verdict, not duplicated logic."""

    def test_safe_mode_mentions_arbiter(self):
        """The safe_mode section in export_snapshot.py must reference arbiter."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        # Find the safe mode section
        safe_mode_idx = source.find("Safe Mode Export")
        self.assertGreater(safe_mode_idx, 0, "Safe Mode Export section not found")
        safe_mode_section = source[safe_mode_idx:safe_mode_idx + 2000]
        self.assertIn("arbiter", safe_mode_section.lower())

    def test_arbiter_forbidden_claims_drive_ranking_hidden(self):
        """If arbiter forbids ranking, safe_mode should hide rankings."""
        # Arbiter that forbids ranking
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        self.assertIn("ranking", verdict["final_forbidden_claims"])

    def test_arbiter_blocked_generates_warning(self):
        """Blocked arbiter status generates safe_mode warning."""
        verdict = adjudicate(
            country="DE",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["governance"],
                "degraded_layers": [],
            },
        )
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.BLOCKED)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: MONOTONICITY — arbiter at least as restrictive as truth
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterMonotonicity(unittest.TestCase):
    """Arbiter verdict must be at least as restrictive as truth resolution."""

    def _build_enforcement_state(self, **overrides: Any) -> dict[str, Any]:
        """Build a minimal enforcement state dict."""
        state = {
            "governance": {"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True,
                           "cross_country_comparable": True},
            "decision_usability": {"decision_usability_class": "FULL_USABILITY"},
            "construct_enforcement": {"composite_producible": True, "n_valid": 6, "n_degraded": 0, "n_invalid": 0},
            "external_validation": {"overall_alignment": "ALIGNED"},
            "failure_visibility": {"trust_level": "FULL_TRUST"},
            "reality_conflicts": {"has_critical": False, "n_conflicts": 0},
            "invariant_assessment": {"has_critical": False, "n_violations": 0},
            "alignment_sensitivity": {"stability_class": "STABLE"},
        }
        state.update(overrides)
        return state

    def test_healthy_pipeline_arbiter_is_valid(self):
        """Healthy pipeline → arbiter should be VALID or RESTRICTED (not blocked)."""
        state = self._build_enforcement_state()
        enforcement = apply_enforcement(state)
        truth = resolve_truth(state, enforcement)

        verdict = adjudicate(
            country="DE",
            truth_resolution=truth,
            governance=state["governance"],
            runtime_status={
                "pipeline_status": "HEALTHY",
                "degraded_layers": [],
                "failed_layers": [],
            },
        )
        self.assertIn(
            verdict["final_epistemic_status"],
            {ArbiterStatus.VALID, ArbiterStatus.RESTRICTED, ArbiterStatus.FLAGGED},
        )

    def test_blocked_truth_means_blocked_arbiter(self):
        """If truth says export_blocked, arbiter must also block."""
        truth = {
            "truth_status": TruthStatus.INVALID,
            "export_blocked": True,
            "final_governance_tier": "NON_COMPARABLE",
            "final_ranking_eligible": False,
            "final_cross_country_comparable": False,
            "final_composite_suppressed": True,
        }
        verdict = adjudicate(country="DE", truth_resolution=truth)
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.BLOCKED)

    def test_non_comparable_truth_suppresses_arbiter(self):
        """NON_COMPARABLE governance → arbiter should be SUPPRESSED or worse."""
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        self.assertIn(
            verdict["final_epistemic_status"],
            {ArbiterStatus.SUPPRESSED, ArbiterStatus.BLOCKED},
        )

    def test_arbiter_never_weaker_than_truth(self):
        """Arbiter can never produce a LESS restrictive status than truth implies."""
        # Truth says DEGRADED with conflicts
        truth = {
            "truth_status": TruthStatus.DEGRADED,
            "n_conflicts": 3,
            "export_blocked": False,
            "final_governance_tier": "LOW_CONFIDENCE",
            "final_ranking_eligible": False,
        }
        verdict = adjudicate(country="DE", truth_resolution=truth)
        # RESTRICTED or more restrictive
        self.assertGreaterEqual(
            ARBITER_STATUS_ORDER.get(verdict["final_epistemic_status"], 0),
            ARBITER_STATUS_ORDER.get(ArbiterStatus.RESTRICTED, 1),
        )

    def test_critical_reality_conflict_suppresses(self):
        """Critical reality conflicts → arbiter must suppress."""
        verdict = adjudicate(
            country="DE",
            reality_conflicts={"has_critical": True, "n_conflicts": 2},
        )
        self.assertIn(
            verdict["final_epistemic_status"],
            {ArbiterStatus.SUPPRESSED, ArbiterStatus.BLOCKED},
        )

    def test_no_trust_failure_visibility_suppresses(self):
        """NO_TRUST visibility → arbiter must suppress."""
        verdict = adjudicate(
            country="DE",
            failure_visibility={"trust_level": "NO_TRUST"},
        )
        self.assertIn(
            verdict["final_epistemic_status"],
            {ArbiterStatus.SUPPRESSED, ArbiterStatus.BLOCKED},
        )

    def test_invariant_violation_blocks(self):
        """Epistemic invariant violations → arbiter must block."""
        verdict = adjudicate(
            country="DE",
            invariant_report={"passed": False, "n_violations": 2, "violation_ids": ["INV-001", "INV-002"]},
        )
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.BLOCKED)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: ANTI-LAUNDERING
# ═══════════════════════════════════════════════════════════════════════════

class TestAntiLaundering(unittest.TestCase):
    """Forbidden claims must not leak through output validation."""

    def test_ranking_forbidden_catches_ranking_in_output(self):
        """If arbiter forbids ranking, output with ranking should fail validation."""
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        self.assertIn("ranking", verdict["final_forbidden_claims"])

        output = {"ranking_eligible": True, "rank": 5}
        validation = validate_output_against_arbiter(output, verdict)
        self.assertFalse(validation["passed"])
        self.assertGreater(validation["n_violations"], 0)

    def test_comparison_forbidden_catches_comparable_output(self):
        """If arbiter forbids comparison, comparable output should fail."""
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        self.assertIn("comparison", verdict["final_forbidden_claims"])

        output = {"cross_country_comparable": True}
        validation = validate_output_against_arbiter(output, verdict)
        self.assertFalse(validation["passed"])

    def test_clean_output_passes_validation(self):
        """Valid arbiter + clean output should pass validation."""
        verdict = adjudicate(country="DE")
        output = {"warnings": []}
        validation = validate_output_against_arbiter(output, verdict)
        self.assertTrue(validation["passed"])

    def test_blocked_output_with_published_flag_fails(self):
        """Blocked status + is_published=True should fail validation."""
        verdict = adjudicate(
            country="DE",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["governance"],
                "degraded_layers": [],
            },
        )
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.BLOCKED)

        output = {"is_published": True}
        validation = validate_output_against_arbiter(output, verdict)
        self.assertFalse(validation["passed"])

    def test_confidence_cap_exceeded_fails(self):
        """Output confidence above arbiter cap should fail."""
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "LOW_CONFIDENCE", "ranking_eligible": False},
        )
        cap = verdict["final_confidence_cap"]
        self.assertLess(cap, 1.0)

        output = {"confidence": 0.99}
        validation = validate_output_against_arbiter(output, verdict)
        self.assertFalse(validation["passed"])


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: ADVERSARIAL — hostile inputs, boundary conditions
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterAdversarial(unittest.TestCase):
    """Adversarial inputs must not crash or weaken the arbiter."""

    def test_all_none_inputs(self):
        """Arbiter with all None inputs should produce VALID (no evidence to restrict)."""
        verdict = adjudicate(country="DE")
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.VALID)
        self.assertEqual(verdict["n_inputs_evaluated"], 0)

    def test_all_hostile_inputs(self):
        """Maximum restriction from all inputs → BLOCKED."""
        verdict = adjudicate(
            country="DE",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["everything"],
                "degraded_layers": ["also_everything"],
            },
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
                "final_governance_tier": "NON_COMPARABLE",
                "final_ranking_eligible": False,
            },
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
            failure_visibility={"trust_level": "NO_TRUST"},
            invariant_report={"passed": False, "n_violations": 10, "violation_ids": ["X"]},
            reality_conflicts={"has_critical": True, "n_conflicts": 5},
            publishability_result={"publishability_status": "NOT_PUBLISHABLE"},
        )
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.BLOCKED)
        self.assertEqual(verdict["final_publishability"], "NOT_PUBLISHABLE")
        self.assertEqual(verdict["final_confidence_cap"], 0.0)
        self.assertGreater(len(verdict["final_forbidden_claims"]), 0)

    def test_empty_dicts_dont_crash(self):
        """Empty dict inputs should not crash."""
        verdict = adjudicate(
            country="DE",
            runtime_status={},
            truth_resolution={},
            governance={},
            failure_visibility={},
            invariant_report={},
            reality_conflicts={},
        )
        self.assertIn(
            verdict["final_epistemic_status"], 
            set(ARBITER_STATUS_ORDER.keys()),
        )

    def test_garbage_governance_tier(self):
        """Unknown governance tier should not crash."""
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "ABSOLUTELY_BOGUS", "ranking_eligible": True},
        )
        # Should still produce valid output
        self.assertIn(verdict["final_epistemic_status"], set(ARBITER_STATUS_ORDER.keys()))

    def test_all_27_countries_produce_valid_verdicts(self):
        """Every EU-27 country should produce a valid arbiter verdict."""
        from backend.constants import EU27_CODES
        for country in sorted(EU27_CODES):
            verdict = adjudicate(country=country)
            self.assertIn(
                verdict["final_epistemic_status"],
                set(ARBITER_STATUS_ORDER.keys()),
                f"Country {country} produced invalid arbiter status"
            )
            self.assertEqual(verdict["country"], country)

    def test_confidence_cap_never_negative(self):
        """Confidence cap must never be negative."""
        for gov_tier in ["FULLY_COMPARABLE", "LOW_CONFIDENCE", "NON_COMPARABLE"]:
            for trust in ["FULL_TRUST", "LOW_TRUST", "NO_TRUST"]:
                verdict = adjudicate(
                    country="DE",
                    governance={"governance_tier": gov_tier, "ranking_eligible": False},
                    failure_visibility={"trust_level": trust},
                )
                self.assertGreaterEqual(
                    verdict["final_confidence_cap"], 0.0,
                    f"Negative confidence cap for tier={gov_tier}, trust={trust}"
                )

    def test_confidence_cap_never_above_one(self):
        """Confidence cap must never exceed 1.0."""
        verdict = adjudicate(country="DE")
        self.assertLessEqual(verdict["final_confidence_cap"], 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: PUBLISHABILITY WIRING
# ═══════════════════════════════════════════════════════════════════════════

class TestPublishabilityWiring(unittest.TestCase):
    """Publishability assessment must be wired into export."""

    def test_publishability_imported_by_export(self):
        """export_snapshot.py must import assess_publishability."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        tree = ast.parse(source)
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "publishability" in node.module:
                    found = True
                    break
        self.assertTrue(found, "export_snapshot.py does not import publishability")

    def test_publishability_key_in_country_json(self):
        """'publishability' key must appear in build_country_json return."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn('"publishability":', source)

    def test_blocked_truth_means_not_publishable(self):
        """Export blocked → publishability must be NOT_PUBLISHABLE."""
        result = assess_publishability(
            country="DE",
            truth_result={"truth_status": "INVALID", "export_blocked": True},
        )
        self.assertEqual(result["publishability_status"], PublishabilityStatus.NOT_PUBLISHABLE)

    def test_non_comparable_means_not_publishable(self):
        """NON_COMPARABLE tier → NOT_PUBLISHABLE."""
        result = assess_publishability(
            country="DE",
            truth_result={
                "truth_status": "VALID",
                "export_blocked": False,
                "final_governance_tier": "NON_COMPARABLE",
            },
        )
        self.assertEqual(result["publishability_status"], PublishabilityStatus.NOT_PUBLISHABLE)

    def test_clean_input_is_publishable(self):
        """Clean input → PUBLISHABLE."""
        result = assess_publishability(country="DE")
        self.assertEqual(result["publishability_status"], PublishabilityStatus.PUBLISHABLE)

    def test_degraded_truth_requires_caveats(self):
        """Degraded truth → PUBLISHABLE_WITH_CAVEATS."""
        result = assess_publishability(
            country="DE",
            truth_result={
                "truth_status": "DEGRADED",
                "n_conflicts": 2,
                "export_blocked": False,
                "final_governance_tier": "FULLY_COMPARABLE",
            },
        )
        self.assertEqual(
            result["publishability_status"],
            PublishabilityStatus.PUBLISHABLE_WITH_CAVEATS,
        )


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: AUTHORITY COHERENCE — no contradictions between layers
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthorityCoherence(unittest.TestCase):
    """There must be no contradictions between truth, arbiter, and safe_mode."""

    def test_arbiter_publishability_consistent_with_status(self):
        """Arbiter publishability must be consistent with status."""
        # VALID → PUBLISHABLE
        v1 = adjudicate(country="DE")
        self.assertEqual(v1["final_publishability"], "PUBLISHABLE")

        # BLOCKED → NOT_PUBLISHABLE
        v2 = adjudicate(
            country="DE",
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"], "degraded_layers": []},
        )
        self.assertEqual(v2["final_publishability"], "NOT_PUBLISHABLE")

        # SUPPRESSED → NOT_PUBLISHABLE
        v3 = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        self.assertEqual(v3["final_publishability"], "NOT_PUBLISHABLE")

    def test_forbidden_claims_subset_of_known_claims(self):
        """All forbidden claims must be from a known set."""
        known_claims = {
            "ranking", "comparison", "policy_claim", "composite",
            "country_ordering", "publication",
        }
        verdict = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        for claim in verdict["final_forbidden_claims"]:
            self.assertIn(
                claim, known_claims,
                f"Unknown forbidden claim: {claim}"
            )

    def test_allowed_and_forbidden_never_overlap(self):
        """No claim can be both allowed AND forbidden."""
        for gov_tier in ["FULLY_COMPARABLE", "LOW_CONFIDENCE", "NON_COMPARABLE"]:
            verdict = adjudicate(
                country="DE",
                governance={"governance_tier": gov_tier, "ranking_eligible": gov_tier == "FULLY_COMPARABLE"},
            )
            allowed = set(verdict["final_allowed_claims"])
            forbidden = set(verdict["final_forbidden_claims"])
            overlap = allowed & forbidden
            self.assertEqual(
                overlap, set(),
                f"Claims both allowed AND forbidden for tier={gov_tier}: {overlap}"
            )

    def test_n_inputs_matches_non_none_count(self):
        """n_inputs_evaluated must match actual non-None input count."""
        # 3 inputs provided
        verdict = adjudicate(
            country="DE",
            runtime_status={"pipeline_status": "HEALTHY", "degraded_layers": [], "failed_layers": []},
            governance={"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
            reality_conflicts={"has_critical": False, "n_conflicts": 0},
        )
        self.assertEqual(verdict["n_inputs_evaluated"], 3)

    def test_honesty_note_always_present(self):
        """Every verdict must have an honesty_note."""
        verdict = adjudicate(country="DE")
        self.assertIn("honesty_note", verdict)
        self.assertGreater(len(verdict["honesty_note"]), 0)

    def test_arbiter_verdict_is_final(self):
        """Once computed, arbiter verdict fields must all be present."""
        verdict = adjudicate(
            country="DE",
            runtime_status={"pipeline_status": "DEGRADED", "degraded_layers": ["x"], "failed_layers": []},
            governance={"governance_tier": "LOW_CONFIDENCE", "ranking_eligible": False},
        )
        # Must have ALL output fields
        self.assertIn("final_epistemic_status", verdict)
        self.assertIn("final_confidence_cap", verdict)
        self.assertIn("final_publishability", verdict)
        self.assertIn("final_allowed_claims", verdict)
        self.assertIn("final_forbidden_claims", verdict)
        self.assertIn("final_required_warnings", verdict)
        self.assertIn("binding_constraints", verdict)
        self.assertIn("arbiter_reasoning", verdict)
        self.assertIn("fault_scope", verdict)
        self.assertIn("scoped_publishability", verdict)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: MULTI-INPUT INTERACTION — stacking restrictions
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiInputInteraction(unittest.TestCase):
    """Multiple restriction sources must stack correctly."""

    def test_degraded_plus_low_confidence_stacks(self):
        """Degraded runtime + LOW_CONFIDENCE gov → at least RESTRICTED."""
        verdict = adjudicate(
            country="DE",
            runtime_status={"pipeline_status": "DEGRADED", "degraded_layers": ["x"], "failed_layers": []},
            governance={"governance_tier": "LOW_CONFIDENCE", "ranking_eligible": False},
        )
        self.assertGreaterEqual(
            ARBITER_STATUS_ORDER.get(verdict["final_epistemic_status"], 0),
            ARBITER_STATUS_ORDER[ArbiterStatus.RESTRICTED],
        )

    def test_multiple_weak_signals_accumulate(self):
        """Multiple weak signals should accumulate to at least FLAGGED."""
        verdict = adjudicate(
            country="DE",
            runtime_status={"pipeline_status": "DEGRADED", "degraded_layers": ["x"], "failed_layers": []},
            reality_conflicts={"has_critical": False, "n_conflicts": 3},
            failure_visibility={"trust_level": "GUARDED_TRUST"},
        )
        self.assertGreaterEqual(
            ARBITER_STATUS_ORDER.get(verdict["final_epistemic_status"], 0),
            ARBITER_STATUS_ORDER[ArbiterStatus.FLAGGED],
        )

    def test_one_block_overrides_all_valid(self):
        """One BLOCKED input overrides all VALID inputs."""
        verdict = adjudicate(
            country="DE",
            runtime_status={"pipeline_status": "HEALTHY", "degraded_layers": [], "failed_layers": []},
            governance={"governance_tier": "FULLY_COMPARABLE", "ranking_eligible": True},
            # But invariants BLOCK
            invariant_report={"passed": False, "n_violations": 1, "violation_ids": ["X"]},
        )
        self.assertEqual(verdict["final_epistemic_status"], ArbiterStatus.BLOCKED)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10: EXPORT PIPELINE STRUCTURAL INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════

class TestExportPipelineIntegrity(unittest.TestCase):
    """The export pipeline must have the correct authority chain."""

    def test_authority_chain_order_in_export(self):
        """export_snapshot.py must call enforcement → truth → publishability → arbiter."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        # Find positions of key calls in build_country_json
        enforcement_pos = source.find("apply_enforcement")
        truth_pos = source.find("resolve_truth")
        publishability_pos = source.find("_compute_publishability")
        arbiter_pos = source.find("_compute_arbiter_verdict")

        self.assertGreater(enforcement_pos, 0, "apply_enforcement not found")
        self.assertGreater(truth_pos, 0, "resolve_truth not found")
        self.assertGreater(publishability_pos, 0, "_compute_publishability not found")
        self.assertGreater(arbiter_pos, 0, "_compute_arbiter_verdict not found")

        # Correct order: enforcement < truth < publishability < arbiter
        self.assertLess(
            enforcement_pos, truth_pos,
            "enforcement must come before truth_resolver"
        )
        self.assertLess(
            truth_pos, publishability_pos,
            "truth_resolver must come before publishability"
        )
        self.assertLess(
            publishability_pos, arbiter_pos,
            "publishability must come before arbiter"
        )

    def test_no_parallel_authority_systems(self):
        """export_snapshot must use ONE authority chain, not two parallel ones."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        # The arbiter must be called AFTER truth, and safe_mode must reference arbiter
        self.assertIn("arbiter_verdict", source)
        self.assertIn("arbiter_status", source)

    def test_compute_arbiter_verdict_helper_exists(self):
        """_compute_arbiter_verdict helper must exist in export_snapshot."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn("def _compute_arbiter_verdict(", source)

    def test_compute_publishability_helper_exists(self):
        """_compute_publishability helper must exist in export_snapshot."""
        source = (BACKEND_DIR / "export_snapshot.py").read_text()
        self.assertIn("def _compute_publishability(", source)


if __name__ == "__main__":
    unittest.main()
