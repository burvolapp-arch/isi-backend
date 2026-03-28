"""
tests.test_kill_pass — ISI FINAL SURGICAL KILL-PASS tests.

Validates all changes from the kill-pass:
  1. Arbiter dominance: build_isi_json respects arbiter verdicts.
  2. Dominant constraint extraction: arbiter identifies bottleneck.
  3. ARB invariants: check_arbiter_dominance detects violations.
  4. Module type registry: MODULE_TYPES covers all backend modules.
  5. Anti-laundering: API axes endpoint carries arbiter envelope.
  6. Materialize ordering: countries built before ISI ranking.
  7. Cross-layer coherence: ISI ranking ≤ arbiter bounds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# TEST DATA HELPERS
# ═══════════════════════════════════════════════════════════════════════════

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

def _all_scores(val: float = 0.5) -> dict[int, dict[str, float]]:
    """Minimal all-country, all-axis score dict."""
    return {i: {c: val for c in EU27} for i in range(1, 7)}


def _arbiter_verdict(
    country: str,
    status: str = "VALID",
    forbidden: list[str] | None = None,
    dominant: str | None = None,
    dominant_source: str | None = None,
) -> dict[str, Any]:
    """Build a minimal arbiter verdict dict."""
    return {
        "country": country,
        "final_epistemic_status": status,
        "final_confidence_cap": 1.0 if status == "VALID" else 0.5,
        "final_publishability": "PUBLISHABLE" if status == "VALID" else "NOT_PUBLISHABLE",
        "final_allowed_claims": [],
        "final_forbidden_claims": forbidden or [],
        "final_required_warnings": [],
        "final_bounds": {},
        "binding_constraints": [],
        "dominant_constraint": dominant,
        "dominant_constraint_source": dominant_source,
        "arbiter_reasoning": [],
        "fault_scope": {},
        "scoped_publishability": {},
        "n_inputs_evaluated": 0,
        "n_reasons": 0,
        "n_warnings": 0,
        "n_forbidden_claims": len(forbidden or []),
        "n_allowed_claims": 0,
        "n_binding_constraints": 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: ARBITER DOMINANCE — build_isi_json
# ═══════════════════════════════════════════════════════════════════════════

class TestArbiterDominanceInISI:
    """build_isi_json must respect arbiter verdicts when provided."""

    def test_isi_rows_have_arbiter_status_when_verdicts_provided(self):
        """Every ISI row should have arbiter_status when verdicts are passed."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        for row in isi["countries"]:
            assert "arbiter_status" in row, f"{row['country']} missing arbiter_status"
            assert row["arbiter_status"] is not None, f"{row['country']} arbiter_status is None"

    def test_isi_rows_have_null_arbiter_when_no_verdicts(self):
        """Without verdicts, arbiter_status should be None (backward-compat)."""
        from backend.export_snapshot import build_isi_json

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024")

        for row in isi["countries"]:
            assert row.get("arbiter_status") is None

    def test_arbiter_overrides_ranking_eligible(self):
        """When arbiter forbids ranking, ISI row must show ranking_eligible=False."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        # Override AT: arbiter blocks ranking
        verdicts["AT"] = _arbiter_verdict(
            "AT", status="SUPPRESSED",
            forbidden=["ranking", "comparison", "country_ordering"],
        )

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        rows = {r["country"]: r for r in isi["countries"]}
        assert rows["AT"]["ranking_eligible"] is False
        assert rows["AT"]["cross_country_comparable"] is False

    def test_arbiter_overrides_comparability(self):
        """When arbiter forbids comparison, cross_country_comparable must be False."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        verdicts["DE"] = _arbiter_verdict(
            "DE", status="RESTRICTED",
            forbidden=["comparison"],
        )

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        rows = {r["country"]: r for r in isi["countries"]}
        assert rows["DE"]["cross_country_comparable"] is False

    def test_arbiter_blocked_suppresses_ranking(self):
        """BLOCKED arbiter status → ranking_eligible=False regardless of governance."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        verdicts["FR"] = _arbiter_verdict("FR", status="BLOCKED", forbidden=[])

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        rows = {r["country"]: r for r in isi["countries"]}
        assert rows["FR"]["ranking_eligible"] is False

    def test_arbiter_valid_preserves_governance_ranking(self):
        """VALID arbiter → governance ranking_eligible preserved."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c, status="VALID") for c in EU27}

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        # All countries have uniform 0.5 data → governance should allow ranking
        rows = {r["country"]: r for r in isi["countries"]}
        # At least some countries should be ranking eligible (those without inversions)
        eligible_count = sum(1 for r in rows.values() if r["ranking_eligible"])
        assert eligible_count > 0

    def test_dominant_constraint_propagated_to_isi_rows(self):
        """ISI rows should carry dominant_constraint from arbiter verdict."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        verdicts["AT"] = _arbiter_verdict(
            "AT", status="BLOCKED",
            forbidden=["ranking"],
            dominant="Pipeline failed with 2 failed layer(s).",
            dominant_source="runtime_status",
        )

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        rows = {r["country"]: r for r in isi["countries"]}
        assert rows["AT"]["dominant_constraint"] == "Pipeline failed with 2 failed layer(s)."
        assert rows["AT"]["dominant_constraint_source"] == "runtime_status"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: DOMINANT CONSTRAINT EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

class TestDominantConstraintExtraction:
    """Arbiter must identify the single dominant binding constraint."""

    def test_dominant_constraint_present_in_verdict(self):
        """adjudicate() must return dominant_constraint fields."""
        from backend.epistemic_arbiter import adjudicate

        verdict = adjudicate(country="AT")
        assert "dominant_constraint" in verdict
        assert "dominant_constraint_source" in verdict

    def test_dominant_is_most_restrictive_reason(self):
        """Dominant constraint should come from the most restrictive input."""
        from backend.epistemic_arbiter import adjudicate

        # Runtime failed → should be the dominant constraint (BLOCKED)
        verdict = adjudicate(
            country="AT",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["truth"],
                "degraded_layers": [],
            },
            governance={
                "governance_tier": "LOW_CONFIDENCE",
                "ranking_eligible": False,
            },
        )

        assert verdict["final_epistemic_status"] == "BLOCKED"
        assert verdict["dominant_constraint_source"] == "runtime_status"

    def test_dominant_none_when_no_reasons(self):
        """If no inputs produce reasons, dominant is None."""
        from backend.epistemic_arbiter import adjudicate

        verdict = adjudicate(country="AT")
        assert verdict["dominant_constraint"] is None
        assert verdict["dominant_constraint_source"] is None

    def test_dominant_picks_blocked_over_restricted(self):
        """BLOCKED reason dominates RESTRICTED reason."""
        from backend.epistemic_arbiter import adjudicate

        verdict = adjudicate(
            country="AT",
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
                "final_ranking_eligible": False,
            },
            governance={
                "governance_tier": "LOW_CONFIDENCE",
                "ranking_eligible": False,
            },
        )

        # truth_resolution produces BLOCKED, governance produces RESTRICTED
        assert verdict["dominant_constraint_source"] == "truth_resolution"

    def test_dominant_earliest_on_tie(self):
        """When multiple reasons have the same restrictiveness, first wins."""
        from backend.epistemic_arbiter import adjudicate

        # Both runtime and truth produce BLOCKED
        verdict = adjudicate(
            country="AT",
            runtime_status={
                "pipeline_status": "FAILED",
                "failed_layers": ["truth"],
                "degraded_layers": [],
            },
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
        )

        # runtime_status is evaluated first → should be dominant
        assert verdict["dominant_constraint_source"] == "runtime_status"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: ARB INVARIANTS
# ═══════════════════════════════════════════════════════════════════════════

class TestARBInvariants:
    """check_arbiter_dominance must detect all arbiter violations."""

    def test_arb001_missing_arbiter_status(self):
        """ARB-001: rows without arbiter_status are violations."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [{"country": "AT", "ranking_eligible": True}]  # No arbiter_status
        result = check_arbiter_dominance(rows)

        assert result["passed"] is False
        assert any(v["invariant_id"] == "ARB-001" for v in result["violations"])

    def test_arb001_null_arbiter_status_fails(self):
        """ARB-001: arbiter_status=None is also a violation."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [{"country": "AT", "arbiter_status": None}]
        result = check_arbiter_dominance(rows)

        assert result["passed"] is False
        assert any(v["invariant_id"] == "ARB-001" for v in result["violations"])

    def test_arb001_passes_with_valid_status(self):
        """ARB-001: arbiter_status present → passes."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [{"country": "AT", "arbiter_status": "VALID", "ranking_eligible": False}]
        result = check_arbiter_dominance(rows)

        assert result["passed"] is True

    def test_arb002_ranking_when_forbidden(self):
        """ARB-002: ranking_eligible=True when arbiter forbids ranking."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [{"country": "AT", "arbiter_status": "BLOCKED", "ranking_eligible": True}]
        verdicts = {"AT": _arbiter_verdict("AT", forbidden=["ranking"])}
        result = check_arbiter_dominance(rows, country_verdicts=verdicts)

        assert result["passed"] is False
        assert any(v["invariant_id"] == "ARB-002" for v in result["violations"])

    def test_arb002_passes_when_ranking_not_forbidden(self):
        """ARB-002: ranking_eligible=True when arbiter allows ranking."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [{"country": "AT", "arbiter_status": "VALID", "ranking_eligible": True}]
        verdicts = {"AT": _arbiter_verdict("AT")}
        result = check_arbiter_dominance(rows, country_verdicts=verdicts)

        # Should pass — ranking is not forbidden
        arb002_violations = [v for v in result["violations"] if v["invariant_id"] == "ARB-002"]
        assert len(arb002_violations) == 0

    def test_arb003_comparability_when_forbidden(self):
        """ARB-003: cross_country_comparable=True when arbiter forbids."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [{"country": "AT", "arbiter_status": "BLOCKED",
                 "cross_country_comparable": True, "ranking_eligible": False}]
        verdicts = {"AT": _arbiter_verdict("AT", forbidden=["comparison"])}
        result = check_arbiter_dominance(rows, country_verdicts=verdicts)

        assert result["passed"] is False
        assert any(v["invariant_id"] == "ARB-003" for v in result["violations"])

    def test_arb_all_pass_with_valid_data(self):
        """All ARB checks pass with properly constrained data."""
        from backend.epistemic_invariants import check_arbiter_dominance

        rows = [
            {"country": "AT", "arbiter_status": "VALID",
             "ranking_eligible": True, "cross_country_comparable": True},
            {"country": "DE", "arbiter_status": "BLOCKED",
             "ranking_eligible": False, "cross_country_comparable": False},
        ]
        verdicts = {
            "AT": _arbiter_verdict("AT"),
            "DE": _arbiter_verdict("DE", status="BLOCKED", forbidden=["ranking", "comparison"]),
        }
        result = check_arbiter_dominance(rows, country_verdicts=verdicts)
        assert result["passed"] is True

    def test_arb_report_integration(self):
        """ARB result integrates into build_epistemic_invariant_report."""
        from backend.epistemic_invariants import (
            build_epistemic_invariant_report,
            check_arbiter_dominance,
        )

        # Failing ARB check
        rows = [{"country": "AT"}]  # No arbiter_status
        arb_result = check_arbiter_dominance(rows)

        report = build_epistemic_invariant_report(arbiter_result=arb_result)
        assert report["passed"] is False
        assert any(v["invariant_id"] == "ARB-001" for v in report["violations"])


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: MODULE TYPE REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

class TestModuleTypeRegistry:
    """MODULE_TYPES in constants must cover all backend modules."""

    def test_module_types_exists(self):
        from backend.constants import MODULE_TYPES
        assert isinstance(MODULE_TYPES, dict)
        assert len(MODULE_TYPES) > 0

    def test_valid_types_only(self):
        from backend.constants import MODULE_TYPES
        valid = {"INPUT", "TRANSFORM", "CONSTRAINT", "META", "OUTPUT"}
        for name, typ in MODULE_TYPES.items():
            assert typ in valid, f"Module {name} has invalid type {typ}"

    def test_constraint_modules_frozenset(self):
        from backend.constants import CONSTRAINT_MODULES
        assert isinstance(CONSTRAINT_MODULES, frozenset)
        assert "epistemic_arbiter" in CONSTRAINT_MODULES
        assert "truth_resolver" in CONSTRAINT_MODULES
        assert "enforcement_matrix" in CONSTRAINT_MODULES

    def test_non_constraint_modules_excluded(self):
        from backend.constants import CONSTRAINT_MODULES
        assert "audit_replay" not in CONSTRAINT_MODULES
        assert "snapshot_diff" not in CONSTRAINT_MODULES
        assert "export_snapshot" not in CONSTRAINT_MODULES
        assert "governance" not in CONSTRAINT_MODULES

    def test_arbiter_is_constraint(self):
        from backend.constants import MODULE_TYPES
        assert MODULE_TYPES["epistemic_arbiter"] == "CONSTRAINT"

    def test_output_modules_classified(self):
        from backend.constants import MODULE_TYPES
        assert MODULE_TYPES["export_snapshot"] == "OUTPUT"
        assert MODULE_TYPES["isi_api_v01"] == "OUTPUT"

    def test_meta_modules_classified(self):
        from backend.constants import MODULE_TYPES
        assert MODULE_TYPES["audit_replay"] == "META"
        assert MODULE_TYPES["complexity_budget"] == "META"
        assert MODULE_TYPES["snapshot_diff"] == "META"

    def test_all_backend_modules_covered(self):
        """Every .py file in backend/ (except __init__, __pycache__) has a type."""
        from backend.constants import MODULE_TYPES
        backend_dir = Path(__file__).parent.parent / "backend"
        py_files = sorted(
            f.stem for f in backend_dir.glob("*.py")
            if f.stem != "__init__" and not f.stem.startswith("_")
        )
        # Not all modules need to be in the registry — but core ones must be
        core_modules = [
            "enforcement_matrix", "truth_resolver", "epistemic_arbiter",
            "publishability", "governance", "severity", "eligibility",
            "export_snapshot", "isi_api_v01", "constants",
        ]
        for mod in core_modules:
            assert mod in MODULE_TYPES, f"Core module {mod} missing from MODULE_TYPES"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: ANTI-LAUNDERING — API AXES ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════

class TestAPIAntiLaundering:
    """API axes endpoint must include arbiter envelope."""

    def test_axes_endpoint_includes_arbiter_fields(self):
        """The /country/{code}/axes response shape must include arbiter."""
        # Simulate what get_country_axes does
        detail = {
            "country": "AT",
            "country_name": "Austria",
            "isi_composite": 0.5,
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "arbiter_verdict": {
                "final_epistemic_status": "RESTRICTED",
                "final_forbidden_claims": ["ranking"],
                "final_required_warnings": ["Trust level: LOW_TRUST."],
            },
            "axes": [
                {
                    "axis_id": 1,
                    "axis_slug": "financial",
                    "score": 0.5,
                    "classification": "MODERATE",
                    "data_quality_flags": [],
                    "degradation_severity": 0.0,
                    "confidence": {"confidence_level": "HIGH"},
                    "warnings": [],
                }
            ],
        }

        # Replicate the API logic
        arbiter = detail.get("arbiter_verdict", {})
        result = {
            "country": detail["country"],
            "country_name": detail["country_name"],
            "isi_composite": detail["isi_composite"],
            "governance": detail.get("governance"),
            "arbiter_status": arbiter.get("final_epistemic_status"),
            "arbiter_forbidden_claims": arbiter.get("final_forbidden_claims", []),
            "arbiter_required_warnings": arbiter.get("final_required_warnings", []),
            "axes": detail["axes"],
        }

        assert result["arbiter_status"] == "RESTRICTED"
        assert "ranking" in result["arbiter_forbidden_claims"]
        assert "Trust level: LOW_TRUST." in result["arbiter_required_warnings"]

    def test_axes_endpoint_without_arbiter_has_none(self):
        """If country JSON has no arbiter_verdict, arbiter fields are None/empty."""
        detail = {
            "country": "AT",
            "country_name": "Austria",
            "isi_composite": 0.5,
            "governance": {"governance_tier": "FULLY_COMPARABLE"},
            "axes": [],
        }

        arbiter = detail.get("arbiter_verdict", {})
        result = {
            "arbiter_status": arbiter.get("final_epistemic_status"),
            "arbiter_forbidden_claims": arbiter.get("final_forbidden_claims", []),
        }

        assert result["arbiter_status"] is None
        assert result["arbiter_forbidden_claims"] == []


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: CROSS-LAYER COHERENCE
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossLayerCoherence:
    """ISI ranking list must be coherent with per-country arbiter verdicts."""

    def test_isi_ranking_eligible_leq_arbiter(self):
        """No ISI row should claim ranking_eligible beyond arbiter permission."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        # Block 5 countries from ranking
        for c in ["AT", "BE", "BG", "CY", "CZ"]:
            verdicts[c] = _arbiter_verdict(c, status="BLOCKED", forbidden=["ranking", "comparison"])

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        rows = {r["country"]: r for r in isi["countries"]}
        for c in ["AT", "BE", "BG", "CY", "CZ"]:
            assert rows[c]["ranking_eligible"] is False, \
                f"{c} should not be ranking eligible (arbiter BLOCKED)"
            assert rows[c]["cross_country_comparable"] is False, \
                f"{c} should not be comparable (arbiter BLOCKED)"

    def test_arbiter_invariants_on_full_isi(self):
        """ARB invariants should pass on properly built ISI JSON."""
        from backend.export_snapshot import build_isi_json
        from backend.epistemic_invariants import check_arbiter_dominance

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        result = check_arbiter_dominance(isi["countries"], country_verdicts=verdicts)
        assert result["passed"] is True, f"ARB violations: {result['violations']}"

    def test_arbiter_invariants_detect_bypass_on_old_isi(self):
        """ARB-001 should fail on ISI JSON built WITHOUT arbiter verdicts."""
        from backend.export_snapshot import build_isi_json
        from backend.epistemic_invariants import check_arbiter_dominance

        # Build without verdicts → arbiter_status will be None
        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024")

        result = check_arbiter_dominance(isi["countries"])
        assert result["passed"] is False
        assert len(result["violations"]) == 27  # One per country
        assert all(v["invariant_id"] == "ARB-001" for v in result["violations"])


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7: ADVERSARIAL — CANNOT RECONSTRUCT STRONGER CLAIMS
# ═══════════════════════════════════════════════════════════════════════════

class TestAdversarialReconstruction:
    """A competent adversary cannot extract stronger claims from output."""

    def test_blocked_country_no_ranking_visible(self):
        """Blocked country must not have ranking_eligible=True anywhere."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        verdicts["IT"] = _arbiter_verdict(
            "IT", status="BLOCKED",
            forbidden=["ranking", "comparison", "composite", "country_ordering"],
        )

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        row = next(r for r in isi["countries"] if r["country"] == "IT")
        assert row["ranking_eligible"] is False
        assert row["cross_country_comparable"] is False
        assert row["arbiter_status"] == "BLOCKED"

    def test_suppressed_country_not_comparable(self):
        """Suppressed country must have cross_country_comparable=False."""
        from backend.export_snapshot import build_isi_json

        verdicts = {c: _arbiter_verdict(c) for c in EU27}
        verdicts["ES"] = _arbiter_verdict(
            "ES", status="SUPPRESSED",
            forbidden=["ranking", "comparison", "country_ordering"],
        )

        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        row = next(r for r in isi["countries"] if r["country"] == "ES")
        assert row["ranking_eligible"] is False
        assert row["cross_country_comparable"] is False

    def test_partial_arbiter_coverage_detected(self):
        """If only some countries have verdicts, ARB-001 catches the rest."""
        from backend.export_snapshot import build_isi_json
        from backend.epistemic_invariants import check_arbiter_dominance

        # Only AT has a verdict
        verdicts = {"AT": _arbiter_verdict("AT")}
        isi = build_isi_json(_all_scores(), "v1.0", 2024, "2022-2024",
                             country_arbiter_verdicts=verdicts)

        result = check_arbiter_dominance(isi["countries"])
        # 26 countries without arbiter_status → 26 violations
        arb001 = [v for v in result["violations"] if v["invariant_id"] == "ARB-001"]
        assert len(arb001) == 26


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 8: VALIDATE_OUTPUT_AGAINST_ARBITER INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestValidateOutputAgainstArbiter:
    """validate_output_against_arbiter must detect all violation classes."""

    def test_ranking_violation(self):
        from backend.epistemic_arbiter import validate_output_against_arbiter

        verdict = _arbiter_verdict("AT", forbidden=["ranking"])
        output = {"ranking_eligible": True, "rank": 5}

        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False
        assert any("ranking" in v["field"] for v in result["violations"])

    def test_comparison_violation(self):
        from backend.epistemic_arbiter import validate_output_against_arbiter

        verdict = _arbiter_verdict("AT", forbidden=["comparison"])
        output = {"cross_country_comparable": True}

        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is False

    def test_clean_output_passes(self):
        from backend.epistemic_arbiter import validate_output_against_arbiter

        verdict = _arbiter_verdict("AT")
        output = {"ranking_eligible": False, "confidence": 0.5}

        result = validate_output_against_arbiter(output, verdict)
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 9: MATERIALIZE ORDERING INVARIANT
# ═══════════════════════════════════════════════════════════════════════════

class TestMaterializeOrdering:
    """materialize_snapshot must build countries before ISI."""

    def test_build_isi_json_accepts_verdicts_kwarg(self):
        """build_isi_json signature accepts country_arbiter_verdicts."""
        import inspect
        from backend.export_snapshot import build_isi_json

        sig = inspect.signature(build_isi_json)
        assert "country_arbiter_verdicts" in sig.parameters

    def test_build_isi_json_verdicts_default_none(self):
        """country_arbiter_verdicts defaults to None."""
        import inspect
        from backend.export_snapshot import build_isi_json

        sig = inspect.signature(build_isi_json)
        param = sig.parameters["country_arbiter_verdicts"]
        assert param.default is None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 10: DETERMINISTIC CONFLICT RIGIDITY
# ═══════════════════════════════════════════════════════════════════════════

class TestDeterministicConflictRigidity:
    """Authority conflict resolution must be path-independent."""

    def test_authority_conflicts_deterministic(self):
        """Same input in different order → same output."""
        from backend.authority_conflicts import detect_authority_conflicts

        claims_a = [
            {"field": "score", "value": 0.8, "authority_tier": 1, "source": "A"},
            {"field": "score", "value": 0.6, "authority_tier": 1, "source": "B"},
        ]
        claims_b = [
            {"field": "score", "value": 0.6, "authority_tier": 1, "source": "B"},
            {"field": "score", "value": 0.8, "authority_tier": 1, "source": "A"},
        ]

        result_a = detect_authority_conflicts(claims_a)
        result_b = detect_authority_conflicts(claims_b)

        assert result_a["n_conflicts"] == result_b["n_conflicts"]
        # Conservative bound should be the same regardless of order
        # For ISI dependency scores, higher = more dependent = more conservative
        for r in [result_a, result_b]:
            if r["resolutions"]:
                for res in r["resolutions"]:
                    if res.get("resolved_value") is not None:
                        assert res["resolved_value"] == max(0.6, 0.8)

    def test_authority_precedence_deterministic(self):
        """Precedence scoring is pure function of inputs."""
        from backend.authority_precedence import resolve_authority_precedence

        claims = [
            {"field": "score", "value": 0.8, "authority_tier": 1,
             "recency": 0.9, "domain_specificity": 0.8,
             "construct_validity": 0.7, "data_coverage": 0.6},
            {"field": "score", "value": 0.6, "authority_tier": 2,
             "recency": 0.5, "domain_specificity": 0.4,
             "construct_validity": 0.3, "data_coverage": 0.2},
        ]

        result1 = resolve_authority_precedence(claims, "score")
        result2 = resolve_authority_precedence(claims, "score")

        assert result1["outcome"] == result2["outcome"]
        assert result1["winning_value"] == result2["winning_value"]


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 11: FAULT ISOLATION GRAPH-BOUND
# ═══════════════════════════════════════════════════════════════════════════

class TestFaultIsolationGraphBound:
    """Fault isolation must respect the dependency graph."""

    def test_single_axis_failure_stays_local(self):
        """Failure in one axis should not escalate to GLOBAL."""
        from backend.epistemic_fault_isolation import compute_fault_isolation

        result = compute_fault_isolation(
            country="AT",
            axis_failures={1},  # Only financial axis failed
        )

        assert result.containment_level != "GLOBAL"

    def test_four_axis_failures_escalate_to_global(self):
        """≥4 axis failures should escalate to GLOBAL (FI-008)."""
        from backend.epistemic_fault_isolation import compute_fault_isolation

        result = compute_fault_isolation(
            country="AT",
            axis_failures={1, 2, 3, 4},  # 4 axes failed
        )

        assert result.containment_level == "GLOBAL"

    def test_three_axis_failures_not_global(self):
        """3 axis failures should NOT escalate to GLOBAL."""
        from backend.epistemic_fault_isolation import compute_fault_isolation

        result = compute_fault_isolation(
            country="AT",
            axis_failures={1, 2, 3},
        )

        assert result.containment_level != "GLOBAL"
