"""
tests.test_extension_pass — ISI EXTENSION PASS tests.

Validates all three extensions:
  Extension A: Calibration — weights applied, fallback works, lock enforced.
  Extension B: Causal graph — dominant on path, invalid rejected.
  Extension C: External authority — influences but does not override.
  Integration: arbiter remains single terminal authority.
"""

from __future__ import annotations

from typing import Any

import pytest

from backend.calibration_config import (
    CalibrationConfig,
    DEFAULT_CALIBRATION,
    DOMINANCE_FEATURES,
    HEURISTIC_WEIGHTS,
    HEURISTIC_VERSION,
    get_active_calibration,
    load_calibration,
    reset_to_heuristic,
)
from backend.causal_graph import (
    CAUSAL_EDGES,
    CAUSAL_GRAPH_VERSION,
    MODULE_NODES,
    OUTCOME_NODES,
    get_causal_sources,
    get_graph_summary,
    get_reachable_outcomes,
    reaches_outcome,
    trace_causal_path,
    validate_dominant_on_causal_path,
)
from backend.epistemic_arbiter import adjudicate as arbiter_adjudicate
from backend.epistemic_invariants import (
    check_calibration_lock,
    check_causal_consistency,
    check_no_external_override,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _verdict(
    country: str = "DE",
    *,
    runtime_status: dict[str, Any] | None = None,
    truth_resolution: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    failure_visibility: dict[str, Any] | None = None,
    invariant_report: dict[str, Any] | None = None,
    reality_conflicts: dict[str, Any] | None = None,
    publishability_result: dict[str, Any] | None = None,
    pre_arbiter_narrowing: list[dict[str, str]] | None = None,
    external_authority_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Helper to call arbiter_adjudicate with minimal boilerplate."""
    return arbiter_adjudicate(
        country=country,
        runtime_status=runtime_status,
        truth_resolution=truth_resolution,
        governance=governance,
        failure_visibility=failure_visibility,
        invariant_report=invariant_report,
        reality_conflicts=reality_conflicts,
        publishability_result=publishability_result,
        pre_arbiter_narrowing=pre_arbiter_narrowing,
        external_authority_signals=external_authority_signals,
    )


@pytest.fixture(autouse=True)
def _reset_calibration():
    """Ensure calibration is reset to heuristic defaults after each test."""
    yield
    reset_to_heuristic()


# ═══════════════════════════════════════════════════════════════════════════
# EXTENSION A: EMPIRICAL CALIBRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestCalibrationConfig:
    """CalibrationConfig data artifact."""

    def test_default_calibration_is_heuristic(self):
        config = get_active_calibration()
        assert config.version == HEURISTIC_VERSION
        assert config.weights == HEURISTIC_WEIGHTS

    def test_config_immutable_weights(self):
        config = get_active_calibration()
        w = config.weights
        w["severity"] = 999.0  # mutate the returned copy
        assert config.weights["severity"] == 3.0  # original unchanged

    def test_config_requires_all_features(self):
        with pytest.raises(ValueError, match="Missing"):
            CalibrationConfig(
                version="bad-v1",
                weights={"severity": 1.0},  # missing other features
            )

    def test_config_rejects_extra_features(self):
        weights = dict(HEURISTIC_WEIGHTS)
        weights["bogus"] = 1.0
        with pytest.raises(ValueError, match="Extra"):
            CalibrationConfig(version="bad-v2", weights=weights)

    def test_config_rejects_negative_weights(self):
        weights = dict(HEURISTIC_WEIGHTS)
        weights["severity"] = -1.0
        with pytest.raises(ValueError, match="non-negative"):
            CalibrationConfig(version="bad-v3", weights=weights)

    def test_load_custom_calibration(self):
        custom = CalibrationConfig(
            version="calibrated-v1",
            weights={
                "severity": 4.0,
                "claims_forbidden": 1.5,
                "primary_path": 2.0,
                "recurrence": 0.5,
            },
            method="logistic_regression",
            dataset="test_dataset_2026",
        )
        load_calibration(custom)
        assert get_active_calibration().version == "calibrated-v1"

    def test_reset_to_heuristic(self):
        custom = CalibrationConfig(
            version="calibrated-v1",
            weights={"severity": 4.0, "claims_forbidden": 1.5,
                     "primary_path": 2.0, "recurrence": 0.5},
        )
        load_calibration(custom)
        reset_to_heuristic()
        assert get_active_calibration().version == HEURISTIC_VERSION

    def test_config_to_dict(self):
        d = DEFAULT_CALIBRATION.to_dict()
        assert "version" in d
        assert "weights" in d
        assert "features" in d
        assert set(d["features"]) == set(DOMINANCE_FEATURES)


class TestCalibrationInArbiter:
    """Calibration weights used in arbiter scoring."""

    def test_verdict_exposes_calibration_version(self):
        v = _verdict()
        assert v["calibration_version"] == HEURISTIC_VERSION

    def test_verdict_exposes_calibration_weights(self):
        v = _verdict()
        assert v["calibration_weights"] == HEURISTIC_WEIGHTS

    def test_custom_calibration_changes_verdict_version(self):
        custom = CalibrationConfig(
            version="custom-v1",
            weights={"severity": 4.0, "claims_forbidden": 1.5,
                     "primary_path": 2.0, "recurrence": 0.5},
        )
        load_calibration(custom)
        v = _verdict(governance={"governance_tier": "NON_COMPARABLE"})
        assert v["calibration_version"] == "custom-v1"

    def test_recurrence_feature_affects_scoring(self):
        """With high recurrence weight, a source appearing in multiple
        reasons should become dominant even if less severe."""
        custom = CalibrationConfig(
            version="recurrence-test",
            weights={"severity": 1.0, "claims_forbidden": 0.0,
                     "primary_path": 0.0, "recurrence": 10.0},
        )
        load_calibration(custom)
        # Truth degraded + truth blocked = 2 reasons from truth_resolution
        # vs governance SUPPRESSED = 1 reason
        # recurrence(truth)=2 * 10 = 20, recurrence(governance)=1 * 10 = 10
        v = _verdict(
            truth_resolution={
                "truth_status": "INVALID",
                "export_blocked": True,
            },
            governance={"governance_tier": "NON_COMPARABLE"},
        )
        assert v["dominant_constraint_source"] == "truth_resolution"

    def test_heuristic_fallback_when_no_calibration(self):
        """Default heuristic weights produce same results as before."""
        reset_to_heuristic()
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
        )
        assert v["dominant_constraint_source"] == "runtime_status"
        assert v["calibration_version"] == HEURISTIC_VERSION


class TestCalibrationLockInvariant:
    """ARB-005: Calibration lock — runtime weights match config."""

    def test_matching_calibration_passes(self):
        v = _verdict()
        result = check_calibration_lock({"DE": v})
        assert result["passed"] is True

    def test_tampered_version_fails(self):
        v = _verdict()
        v["calibration_version"] = "tampered-v999"
        result = check_calibration_lock({"DE": v})
        assert result["passed"] is False
        assert result["violations"][0]["invariant_id"] == "ARB-005"

    def test_tampered_weights_fail(self):
        v = _verdict()
        v["calibration_weights"]["severity"] = 999.0
        result = check_calibration_lock({"DE": v})
        assert result["passed"] is False


# ═══════════════════════════════════════════════════════════════════════════
# EXTENSION B: FORMAL CAUSAL GRAPH
# ═══════════════════════════════════════════════════════════════════════════

class TestCausalGraph:
    """Static causal graph structure."""

    def test_all_module_nodes_have_edges(self):
        for node in MODULE_NODES:
            assert node in CAUSAL_EDGES, f"Module {node} has no causal edges"

    def test_all_edges_point_to_valid_outcomes(self):
        valid = frozenset(OUTCOME_NODES)
        for source, outcomes in CAUSAL_EDGES.items():
            for outcome in outcomes:
                assert outcome in valid, (
                    f"Edge {source} → {outcome} points to invalid outcome"
                )

    def test_every_module_reaches_final_status(self):
        """Every module can affect the final status."""
        for node in MODULE_NODES:
            assert reaches_outcome(node, "final_status"), (
                f"Module {node} does not reach final_status"
            )

    def test_runtime_reaches_all_claims(self):
        outcomes = get_reachable_outcomes("runtime_status")
        assert "ranking" in outcomes
        assert "comparison" in outcomes
        assert "final_status" in outcomes

    def test_failure_visibility_only_reaches_status(self):
        outcomes = get_reachable_outcomes("failure_visibility")
        assert outcomes == frozenset({"final_status"})

    def test_get_causal_sources(self):
        sources = get_causal_sources("ranking")
        assert "runtime_status" in sources
        assert "truth_resolution" in sources
        assert "governance" in sources
        assert "failure_visibility" not in sources

    def test_graph_summary(self):
        s = get_graph_summary()
        assert s["version"] == CAUSAL_GRAPH_VERSION
        assert s["n_module_nodes"] == len(MODULE_NODES)
        assert s["n_outcome_nodes"] == len(OUTCOME_NODES)


class TestCausalPathValidation:
    """Dominant constraint must lie on causal path."""

    def test_dominant_on_path_passes(self):
        result = validate_dominant_on_causal_path(
            "runtime_status", "BLOCKED", ["ranking", "comparison"],
        )
        assert result["passed"] is True

    def test_no_dominant_passes(self):
        result = validate_dominant_on_causal_path(None, "VALID", [])
        assert result["passed"] is True

    def test_trace_causal_path_marks_relevant(self):
        reasons = [
            {"source": "runtime_status", "decision": "BLOCKED",
             "detail": "pipeline failed"},
            {"source": "failure_visibility", "decision": "FLAGGED",
             "detail": "low trust"},
        ]
        # With forbidden_claims=["ranking"], relevant outcomes are
        # {"final_status", "ranking"}. runtime_status reaches both.
        # failure_visibility reaches final_status, so it IS on causal path.
        path = trace_causal_path(reasons, "BLOCKED", ["ranking"])
        assert path[0]["is_on_causal_path"] is True   # runtime reaches ranking + final_status
        assert path[1]["is_on_causal_path"] is True   # FV reaches final_status

        # But FV does NOT reach "ranking" specifically:
        assert "ranking" in path[0]["causally_relevant_outcomes"]
        assert "ranking" not in path[1]["causally_relevant_outcomes"]

    def test_causal_path_in_verdict(self):
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
        )
        assert "causal_path" in v
        assert "causal_validation" in v
        assert v["causal_validation"]["passed"] is True

    def test_causal_filtering_prefers_path_connected(self):
        """Between two SUPPRESSED reasons, one on causal path (governance)
        and one off path (failure_visibility), the on-path one should
        be dominant."""
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
            failure_visibility={"trust_level": "NO_TRUST"},
        )
        # Governance reaches ranking/comparison/country_ordering — on path.
        # Failure visibility only reaches final_status — still on path
        # but with fewer reachable outcomes.
        # Governance: severity=3, claims=3, primary=1 → on path, full score
        # FV: severity=3, claims=0, primary=0 → on path, lower score
        assert v["dominant_constraint_source"] == "governance"


class TestCausalConsistencyInvariant:
    """ARB-006: Causal consistency."""

    def test_valid_dominant_passes(self):
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
        )
        result = check_causal_consistency({"DE": v})
        assert result["passed"] is True

    def test_no_dominant_passes(self):
        v = _verdict()
        result = check_causal_consistency({"DE": v})
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# EXTENSION C: EXTERNAL AUTHORITY
# ═══════════════════════════════════════════════════════════════════════════

class TestExternalAuthoritySignals:
    """External authority signals as arbiter inputs."""

    def test_no_signals_clean_verdict(self):
        v = _verdict()
        assert v["external_authority_report"] == []
        assert v["n_external_signals"] == 0

    def test_more_restrictive_signal_accepted(self):
        """BLOCKED external signal on a VALID country → accepted."""
        signals = [{
            "source_id": "BIS",
            "claim_type": "banking_concentration",
            "confidence": 0.95,
            "decision": "BLOCKED",
            "scope": "governance",
        }]
        v = _verdict(external_authority_signals=signals)
        assert v["n_external_accepted"] == 1
        assert v["final_epistemic_status"] == "BLOCKED"
        # Must show up in reasoning
        ext_reasons = [r for r in v["arbiter_reasoning"]
                       if r["source"].startswith("external_authority:")]
        assert len(ext_reasons) == 1

    def test_less_restrictive_signal_rejected(self):
        """VALID external signal on a BLOCKED country → rejected."""
        signals = [{
            "source_id": "IMF",
            "claim_type": "fiscal_assessment",
            "confidence": 0.8,
            "decision": "VALID",
            "scope": "governance",
        }]
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
            external_authority_signals=signals,
        )
        assert v["n_external_accepted"] == 0
        assert v["final_epistemic_status"] == "BLOCKED"

    def test_conflicting_signal_surfaced_as_warning(self):
        """External signal contradicting internal → conflict surfaced."""
        signals = [{
            "source_id": "OECD",
            "claim_type": "governance_assessment",
            "confidence": 0.9,
            "decision": "VALID",
            "scope": "governance",
        }]
        v = _verdict(
            governance={"governance_tier": "NON_COMPARABLE"},
            external_authority_signals=signals,
        )
        # Internal governance says SUPPRESSED, external says VALID.
        # External is less restrictive → rejected.
        # But internal conflict should be surfaced as warning.
        assert v["n_external_conflicts"] >= 1

    def test_external_report_in_verdict(self):
        signals = [{
            "source_id": "Eurostat",
            "claim_type": "data_quality",
            "confidence": 0.85,
            "decision": "FLAGGED",
            "scope": "truth_resolution",
        }]
        v = _verdict(external_authority_signals=signals)
        report = v["external_authority_report"]
        assert len(report) == 1
        assert report[0]["source_id"] == "Eurostat"
        assert "accepted" in report[0]
        assert "reason" in report[0]

    def test_external_cannot_bypass_arbiter(self):
        """Even with VALID external signals, arbiter's BLOCKED stays BLOCKED."""
        signals = [{
            "source_id": "BIS",
            "claim_type": "override_attempt",
            "confidence": 1.0,
            "decision": "VALID",
            "scope": "runtime_status",
        }]
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
            external_authority_signals=signals,
        )
        assert v["final_epistemic_status"] == "BLOCKED"


class TestNoExternalOverrideInvariant:
    """ARB-007: No external override."""

    def test_no_external_signals_passes(self):
        v = _verdict()
        result = check_no_external_override({"DE": v})
        assert result["passed"] is True

    def test_accepted_no_conflict_passes(self):
        signals = [{
            "source_id": "BIS",
            "claim_type": "banking",
            "confidence": 0.95,
            "decision": "BLOCKED",
            "scope": "governance",
        }]
        v = _verdict(external_authority_signals=signals)
        result = check_no_external_override({"DE": v})
        assert result["passed"] is True


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """All three extensions integrated without breaking single authority."""

    def test_all_three_in_one_verdict(self):
        """Calibration + causal + external in a single verdict."""
        signals = [{
            "source_id": "IMF",
            "claim_type": "fiscal",
            "confidence": 0.9,
            "decision": "FLAGGED",
            "scope": "governance",
        }]
        v = _verdict(
            governance={"governance_tier": "LOW_CONFIDENCE"},
            external_authority_signals=signals,
        )
        # Calibration
        assert "calibration_version" in v
        assert "calibration_weights" in v
        # Causal
        assert "causal_path" in v
        assert "causal_validation" in v
        # External
        assert "external_authority_report" in v
        assert v["n_external_signals"] == 1
        # Arbiter still terminal
        assert v["final_epistemic_status"] in (
            "VALID", "RESTRICTED", "FLAGGED", "SUPPRESSED", "BLOCKED"
        )

    def test_arbiter_remains_terminal(self):
        """No new bypass paths — arbiter status is still the only truth."""
        v = _verdict(
            runtime_status={"pipeline_status": "FAILED", "failed_layers": ["x"]},
            external_authority_signals=[{
                "source_id": "BIS",
                "claim_type": "override",
                "confidence": 1.0,
                "decision": "VALID",
                "scope": "runtime_status",
            }],
        )
        # External VALID cannot override internal BLOCKED
        assert v["final_epistemic_status"] == "BLOCKED"

    def test_all_invariants_pass_on_clean_verdict(self):
        v = _verdict()
        verdicts = {"DE": v}
        assert check_calibration_lock(verdicts)["passed"] is True
        assert check_causal_consistency(verdicts)["passed"] is True
        assert check_no_external_override(verdicts)["passed"] is True

    def test_honesty_note_includes_calibration_and_external(self):
        v = _verdict()
        note = v["honesty_note"]
        assert "Calibration:" in note
        assert "External signals:" in note
