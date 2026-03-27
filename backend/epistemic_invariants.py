"""
backend.epistemic_invariants — Epistemic Monotonicity Invariants

ENDGAME PASS v2, SECTION 1: Epistemic Monotonicity Guarantees.

Problem addressed:
    Downstream layers can produce outputs that are epistemically
    stronger, cleaner, or more usable than their weakest upstream
    constraint actually allows. This class of error is eliminated
    by monotonicity invariants that verify: NO layer may inflate
    confidence, resurrect rankings, clean caveats, or upgrade
    publishability beyond what its inputs justify.

Solution:
    10 invariants (EMI-001 through EMI-010) that together guarantee
    epistemic monotonicity across the full pipeline. Each invariant
    is a pure function that takes a before-state and after-state and
    returns PASS or VIOLATION. Violations are HARD ERRORS — the
    system must not proceed.

Design contract:
    - All checks are pure functions — no side effects.
    - Violation = HARD ERROR (not a warning).
    - Each invariant has a unique ID (EMI-xxx).
    - Violations produce structured records identical to invariants.py format.
    - The system must run ALL 10 checks after every pipeline step.

Honesty note:
    "If a competent external reviewer can extract a stronger claim
    from your output than your system is justified in making, your
    system has failed." These invariants enforce that principle.
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# EMI INVARIANT DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

EMI_INVARIANTS: list[dict[str, str]] = [
    {
        "invariant_id": "EMI-001",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Confidence Monotonicity",
        "description": (
            "No downstream layer may produce a confidence value higher "
            "than the minimum confidence established by upstream layers. "
            "If upstream says confidence ≤ 0.6, downstream MUST NOT "
            "output confidence > 0.6."
        ),
    },
    {
        "invariant_id": "EMI-002",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Publishability Monotonicity",
        "description": (
            "No downstream layer may upgrade publishability status. "
            "NOT_PUBLISHABLE → PUBLISHABLE_WITH_CAVEATS is forbidden. "
            "Publishability can only degrade or remain unchanged."
        ),
    },
    {
        "invariant_id": "EMI-003",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Ranking Visibility Monotonicity",
        "description": (
            "If ranking_eligible was set to False by any upstream layer, "
            "no downstream layer may set it back to True. Rankings "
            "cannot be resurrected once killed."
        ),
    },
    {
        "invariant_id": "EMI-004",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Comparability Monotonicity",
        "description": (
            "If cross-country comparability was disabled upstream, "
            "no downstream layer may re-enable it. Comparability "
            "can only be restricted."
        ),
    },
    {
        "invariant_id": "EMI-005",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "API Monotonicity",
        "description": (
            "API outputs must not be epistemically stronger than the "
            "internal system state. The API is a lossy projection — "
            "it may omit detail but must not add strength."
        ),
    },
    {
        "invariant_id": "EMI-006",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Caveat Non-Substitutability",
        "description": (
            "Required caveats established upstream must not be removed, "
            "replaced with weaker caveats, or hidden by downstream "
            "formatting. Caveats are monotonically accumulated."
        ),
    },
    {
        "invariant_id": "EMI-007",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Missing Authority Non-Upgrading",
        "description": (
            "If a required authority source is missing, no downstream "
            "layer may treat the result as if the authority were present. "
            "Missing authority = epistemic ceiling cannot be raised."
        ),
    },
    {
        "invariant_id": "EMI-008",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Contradiction Non-Upgrading",
        "description": (
            "If contradictions were detected upstream, no downstream "
            "layer may produce output that implies the contradictions "
            "are resolved unless they were explicitly resolved with "
            "documented authority and reasoning."
        ),
    },
    {
        "invariant_id": "EMI-009",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Replay Determinism",
        "description": (
            "Audit replay of the same input must produce identical "
            "epistemic state. If replaying from the same input gives "
            "different confidence, rankings, or publishability, the "
            "system is non-deterministic and untrustworthy."
        ),
    },
    {
        "invariant_id": "EMI-010",
        "type": "EPISTEMIC_MONOTONICITY",
        "name": "Diff Epistemic Sensitivity",
        "description": (
            "Snapshot diffs must detect and report ALL epistemic state "
            "changes. If confidence dropped, rankings changed, or "
            "publishability degraded between versions, the diff MUST "
            "surface this — silent epistemic changes are violations."
        ),
    },
    {
        "invariant_id": "ARB-001",
        "type": "ARBITER_DOMINANCE",
        "name": "No Output Without Arbiter",
        "description": (
            "No output row may exist without an arbiter verdict. "
            "The ranking list (isi.json) must include arbiter_status "
            "for every country row. If arbiter_status is None, the "
            "output was produced without arbiter enforcement."
        ),
    },
    {
        "invariant_id": "ARB-002",
        "type": "ARBITER_DOMINANCE",
        "name": "No Ranking When Arbiter Forbids",
        "description": (
            "If the arbiter's forbidden_claims include 'ranking', "
            "no output may claim ranking_eligible=True. The ranking "
            "list is not exempt from arbiter authority."
        ),
    },
    {
        "invariant_id": "ARB-003",
        "type": "ARBITER_DOMINANCE",
        "name": "Arbiter Terminality",
        "description": (
            "No output field may be epistemically stronger than the "
            "arbiter's verdict allows. The arbiter is the terminal "
            "constraint — all downstream values must be ≤ arbiter bounds."
        ),
    },
]


# Publishability ordering — lower index = more permissive
_PUBLISHABILITY_ORDER: dict[str, int] = {
    "PUBLISHABLE": 0,
    "PUBLISHABLE_WITH_CAVEATS": 1,
    "RESTRICTED": 2,
    "NOT_PUBLISHABLE": 3,
}


# ═══════════════════════════════════════════════════════════════════════════
# INVARIANT VIOLATION CONSTRUCTOR
# ═══════════════════════════════════════════════════════════════════════════

def _emi_violation(
    invariant_id: str,
    description: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Construct a canonical EMI violation record."""
    return {
        "invariant_id": invariant_id,
        "type": "EPISTEMIC_MONOTONICITY",
        "severity": "CRITICAL",
        "description": description,
        "evidence": evidence,
    }


# ═══════════════════════════════════════════════════════════════════════════
# INDIVIDUAL INVARIANT CHECKS
# ═══════════════════════════════════════════════════════════════════════════

def _check_emi_001(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-001: Confidence Monotonicity."""
    conf_before = state_before.get("confidence", 1.0)
    conf_after = state_after.get("confidence", 1.0)

    if conf_after > conf_before:
        return _emi_violation(
            "EMI-001",
            (
                f"Confidence inflated from {conf_before} to {conf_after}. "
                f"Downstream layer produced higher confidence than upstream ceiling."
            ),
            {
                "confidence_before": conf_before,
                "confidence_after": conf_after,
                "inflation": round(conf_after - conf_before, 6),
            },
        )
    return None


def _check_emi_002(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-002: Publishability Monotonicity."""
    pub_before = state_before.get("publishability_status", "PUBLISHABLE")
    pub_after = state_after.get("publishability_status", "PUBLISHABLE")

    idx_before = _PUBLISHABILITY_ORDER.get(pub_before, 0)
    idx_after = _PUBLISHABILITY_ORDER.get(pub_after, 0)

    if idx_after < idx_before:
        return _emi_violation(
            "EMI-002",
            (
                f"Publishability upgraded from {pub_before} to {pub_after}. "
                f"Downstream layer made output MORE publishable than upstream allowed."
            ),
            {
                "publishability_before": pub_before,
                "publishability_after": pub_after,
            },
        )
    return None


def _check_emi_003(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-003: Ranking Visibility Monotonicity."""
    rank_before = state_before.get("ranking_eligible", True)
    rank_after = state_after.get("ranking_eligible", True)

    if not rank_before and rank_after:
        return _emi_violation(
            "EMI-003",
            (
                "Ranking was disabled upstream (ranking_eligible=False) but "
                "re-enabled downstream (ranking_eligible=True). "
                "Rankings cannot be resurrected once killed."
            ),
            {
                "ranking_eligible_before": rank_before,
                "ranking_eligible_after": rank_after,
            },
        )
    return None


def _check_emi_004(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-004: Comparability Monotonicity."""
    comp_before = state_before.get("cross_country_comparable", True)
    comp_after = state_after.get("cross_country_comparable", True)

    if not comp_before and comp_after:
        return _emi_violation(
            "EMI-004",
            (
                "Comparability was disabled upstream "
                "(cross_country_comparable=False) but re-enabled downstream. "
                "Comparability cannot be restored once revoked."
            ),
            {
                "cross_country_comparable_before": comp_before,
                "cross_country_comparable_after": comp_after,
            },
        )
    return None


def _check_emi_005(
    internal_state: dict[str, Any],
    api_output: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-005: API Monotonicity.

    API output must not be epistemically stronger than internal state.
    """
    violations: list[str] = []

    # Confidence
    int_conf = internal_state.get("confidence", 1.0)
    api_conf = api_output.get("confidence", int_conf)
    if api_conf > int_conf:
        violations.append(
            f"API confidence {api_conf} > internal {int_conf}."
        )

    # Ranking
    int_rank = internal_state.get("ranking_eligible", True)
    api_rank = api_output.get("ranking_eligible", int_rank)
    if not int_rank and api_rank:
        violations.append(
            "API shows ranking_eligible=True but internal is False."
        )

    # Comparability
    int_comp = internal_state.get("cross_country_comparable", True)
    api_comp = api_output.get("cross_country_comparable", int_comp)
    if not int_comp and api_comp:
        violations.append(
            "API shows cross_country_comparable=True but internal is False."
        )

    if violations:
        return _emi_violation(
            "EMI-005",
            (
                "API output is epistemically stronger than internal state. "
                f"Violations: {'; '.join(violations)}"
            ),
            {
                "violations": violations,
                "n_violations": len(violations),
            },
        )
    return None


def _check_emi_006(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-006: Caveat Non-Substitutability.

    Required caveats may only accumulate, never be removed.
    """
    caveats_before = set(state_before.get("required_caveats", []))
    caveats_after = set(state_after.get("required_caveats", []))

    dropped = caveats_before - caveats_after
    if dropped:
        return _emi_violation(
            "EMI-006",
            (
                f"Required caveats were dropped downstream: {sorted(dropped)}. "
                f"Caveats are monotonically accumulated — removal is forbidden."
            ),
            {
                "caveats_before": sorted(caveats_before),
                "caveats_after": sorted(caveats_after),
                "dropped": sorted(dropped),
            },
        )
    return None


def _check_emi_007(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-007: Missing Authority Non-Upgrading.

    If required authorities are missing, downstream cannot claim
    authority-gated privileges.
    """
    missing_authorities = state_before.get("missing_authorities", [])
    if not missing_authorities:
        return None

    # With missing authorities, confidence should not increase
    conf_before = state_before.get("confidence", 1.0)
    conf_after = state_after.get("confidence", conf_before)

    if conf_after > conf_before:
        return _emi_violation(
            "EMI-007",
            (
                f"Missing authorities {missing_authorities} but downstream "
                f"increased confidence from {conf_before} to {conf_after}. "
                f"Missing authority means epistemic ceiling cannot rise."
            ),
            {
                "missing_authorities": missing_authorities,
                "confidence_before": conf_before,
                "confidence_after": conf_after,
            },
        )
    return None


def _check_emi_008(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-008: Contradiction Non-Upgrading.

    Contradictions upstream prevent upgrading downstream unless
    explicitly resolved with documentation.
    """
    contradictions = state_before.get("contradictions", [])
    if not contradictions:
        return None

    resolutions = state_after.get("contradiction_resolutions", [])
    n_resolved = len(resolutions)
    n_contradictions = len(contradictions)

    # Check if downstream claims "clean" state without resolving all contradictions
    truth_status_after = state_after.get("truth_status", "VALID")
    if truth_status_after == "VALID" and n_resolved < n_contradictions:
        return _emi_violation(
            "EMI-008",
            (
                f"{n_contradictions} contradiction(s) upstream but only "
                f"{n_resolved} resolved. Downstream claims VALID truth status "
                f"without resolving all contradictions."
            ),
            {
                "n_contradictions": n_contradictions,
                "n_resolved": n_resolved,
                "unresolved": n_contradictions - n_resolved,
            },
        )
    return None


def _check_emi_009(
    replay_a: dict[str, Any],
    replay_b: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-009: Replay Determinism.

    Same input must produce identical epistemic state.
    """
    keys_to_compare = [
        "confidence", "ranking_eligible", "cross_country_comparable",
        "publishability_status", "truth_status",
    ]

    differences: list[dict[str, Any]] = []
    for key in keys_to_compare:
        val_a = replay_a.get(key)
        val_b = replay_b.get(key)
        if val_a != val_b:
            differences.append({
                "key": key,
                "replay_a": val_a,
                "replay_b": val_b,
            })

    if differences:
        return _emi_violation(
            "EMI-009",
            (
                f"Replay produced different epistemic state on "
                f"{len(differences)} dimension(s). System is non-deterministic."
            ),
            {
                "differences": differences,
                "n_differences": len(differences),
            },
        )
    return None


def _check_emi_010(
    old_state: dict[str, Any],
    new_state: dict[str, Any],
    diff_report: dict[str, Any],
) -> dict[str, Any] | None:
    """EMI-010: Diff Epistemic Sensitivity.

    Snapshot diffs must detect ALL epistemic state changes.
    """
    epistemic_keys = [
        "confidence", "ranking_eligible", "cross_country_comparable",
        "publishability_status", "truth_status",
    ]

    actual_changes: list[str] = []
    for key in epistemic_keys:
        if old_state.get(key) != new_state.get(key):
            actual_changes.append(key)

    if not actual_changes:
        return None

    # Check if diff_report captured all changes
    reported_changes = set(diff_report.get("epistemic_changes_detected", []))
    missed = set(actual_changes) - reported_changes

    if missed:
        return _emi_violation(
            "EMI-010",
            (
                f"Diff missed epistemic changes: {sorted(missed)}. "
                f"Detected: {sorted(reported_changes)}. "
                f"Silent epistemic changes are violations."
            ),
            {
                "actual_changes": sorted(actual_changes),
                "reported_changes": sorted(reported_changes),
                "missed": sorted(missed),
            },
        )
    return None


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def check_epistemic_monotonicity(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any]:
    """Check all applicable epistemic monotonicity invariants.

    Runs EMI-001 through EMI-008 (the state-transition invariants).
    EMI-005 (API), EMI-009 (replay), and EMI-010 (diff) require
    specialized inputs and must be called separately.

    Args:
        state_before: Epistemic state BEFORE the layer.
        state_after: Epistemic state AFTER the layer.

    Returns:
        Result dict with violations and pass/fail status.
    """
    checks = [
        _check_emi_001,
        _check_emi_002,
        _check_emi_003,
        _check_emi_004,
        _check_emi_006,
        _check_emi_007,
        _check_emi_008,
    ]

    violations: list[dict[str, Any]] = []
    for check_fn in checks:
        result = check_fn(state_before, state_after)
        if result is not None:
            violations.append(result)

    passed = len(violations) == 0

    return {
        "passed": passed,
        "n_checks": len(checks),
        "n_violations": len(violations),
        "violations": violations,
        "invariant_ids_checked": [
            "EMI-001", "EMI-002", "EMI-003", "EMI-004",
            "EMI-006", "EMI-007", "EMI-008",
        ],
        "honesty_note": (
            f"Epistemic monotonicity check: {'PASSED' if passed else 'FAILED'}. "
            f"{len(checks)} invariants checked, {len(violations)} violation(s). "
            f"{'All downstream states respect upstream ceilings.' if passed else 'HARD ERROR — downstream state exceeds upstream bounds.'}"
        ),
    }


def check_api_monotonicity(
    internal_state: dict[str, Any],
    api_output: dict[str, Any],
) -> dict[str, Any]:
    """Check EMI-005: API output must not exceed internal state.

    Args:
        internal_state: Full internal epistemic state.
        api_output: The output being sent via API.

    Returns:
        Result dict with pass/fail and any violations.
    """
    result = _check_emi_005(internal_state, api_output)
    violations = [result] if result else []
    passed = len(violations) == 0

    return {
        "passed": passed,
        "n_violations": len(violations),
        "violations": violations,
        "invariant_ids_checked": ["EMI-005"],
        "honesty_note": (
            f"API monotonicity check: {'PASSED' if passed else 'FAILED'}. "
            f"{'API output respects internal epistemic state.' if passed else 'HARD ERROR — API output is epistemically stronger than internal state.'}"
        ),
    }


def check_replay_determinism(
    replay_a: dict[str, Any],
    replay_b: dict[str, Any],
) -> dict[str, Any]:
    """Check EMI-009: Replay determinism.

    Args:
        replay_a: First replay of the same input.
        replay_b: Second replay of the same input.

    Returns:
        Result dict with pass/fail and any differences.
    """
    result = _check_emi_009(replay_a, replay_b)
    violations = [result] if result else []
    passed = len(violations) == 0

    return {
        "passed": passed,
        "n_violations": len(violations),
        "violations": violations,
        "invariant_ids_checked": ["EMI-009"],
        "honesty_note": (
            f"Replay determinism check: {'PASSED' if passed else 'FAILED'}. "
            f"{'Replay is deterministic.' if passed else 'HARD ERROR — replay produced different epistemic state.'}"
        ),
    }


def check_diff_sensitivity(
    old_state: dict[str, Any],
    new_state: dict[str, Any],
    diff_report: dict[str, Any],
) -> dict[str, Any]:
    """Check EMI-010: Diff epistemic sensitivity.

    Args:
        old_state: Epistemic state from old version.
        new_state: Epistemic state from new version.
        diff_report: The diff report to validate.

    Returns:
        Result dict with pass/fail and any missed changes.
    """
    result = _check_emi_010(old_state, new_state, diff_report)
    violations = [result] if result else []
    passed = len(violations) == 0

    return {
        "passed": passed,
        "n_violations": len(violations),
        "violations": violations,
        "invariant_ids_checked": ["EMI-010"],
        "honesty_note": (
            f"Diff sensitivity check: {'PASSED' if passed else 'FAILED'}. "
            f"{'Diff captures all epistemic changes.' if passed else 'HARD ERROR — diff missed epistemic state changes.'}"
        ),
    }


def check_arbiter_dominance(
    isi_rows: list[dict[str, Any]],
    country_verdicts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check ARB-001 through ARB-003: arbiter dominance invariants.

    Verifies that:
    - ARB-001: Every ISI row has an arbiter_status (not None).
    - ARB-002: No row has ranking_eligible=True when arbiter forbids ranking.
    - ARB-003: No row is epistemically stronger than arbiter allows.

    Args:
        isi_rows: The countries[] array from isi.json.
        country_verdicts: {country: arbiter_verdict} from country JSONs.
            If None, only ARB-001 (presence check) is enforced.

    Returns:
        Violation report with pass/fail.
    """
    violations: list[dict[str, Any]] = []
    ids_checked = ["ARB-001", "ARB-002", "ARB-003"]

    verdicts = country_verdicts or {}

    for row in isi_rows:
        country = row.get("country", "UNKNOWN")

        # ARB-001: arbiter_status must be present and non-None
        arbiter_status = row.get("arbiter_status")
        if arbiter_status is None:
            violations.append(_emi_violation(
                "ARB-001",
                f"ISI row for {country} has no arbiter_status. "
                f"Output produced without arbiter enforcement.",
                {"country": country, "arbiter_status": arbiter_status},
            ))

        # ARB-002 & ARB-003 require country verdicts
        verdict = verdicts.get(country)
        if verdict is not None:
            forbidden = set(verdict.get("final_forbidden_claims", []))

            # ARB-002: ranking_eligible vs arbiter forbidden
            if row.get("ranking_eligible", False) and "ranking" in forbidden:
                violations.append(_emi_violation(
                    "ARB-002",
                    f"ISI row for {country} has ranking_eligible=True but "
                    f"arbiter forbids 'ranking'.",
                    {
                        "country": country,
                        "ranking_eligible": True,
                        "arbiter_forbidden": sorted(forbidden),
                    },
                ))

            # ARB-003: comparability vs arbiter forbidden
            if (
                row.get("cross_country_comparable", False)
                and ("comparison" in forbidden or "country_ordering" in forbidden)
            ):
                violations.append(_emi_violation(
                    "ARB-003",
                    f"ISI row for {country} claims cross_country_comparable=True but "
                    f"arbiter forbids comparison/ordering.",
                    {
                        "country": country,
                        "cross_country_comparable": True,
                        "arbiter_forbidden": sorted(forbidden),
                    },
                ))

    return {
        "passed": len(violations) == 0,
        "n_checks": len(ids_checked),
        "n_violations": len(violations),
        "violations": violations,
        "invariant_ids_checked": ids_checked,
    }


def check_pre_arbiter_disclosure(
    country_verdicts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Check ARB-004: pre-arbiter narrowing disclosure invariant.

    Verifies that TRANSFORM modules which narrowed the epistemic
    possibility space before the arbiter have their narrowing
    explicitly disclosed in the arbiter verdict. A verdict with
    non-trivial upstream narrowing but an empty pre_arbiter_narrowing
    list indicates hidden authority leakage.

    Detection logic:
        For each verdict, check whether the arbiter's own reasoning
        references sources that correspond to TRANSFORM narrowing
        (governance tier != FULLY_COMPARABLE, trust != full, critical
        reality conflicts) — if such constraints bind the verdict
        but pre_arbiter_narrowing is absent or empty, that's a
        violation.

    Args:
        country_verdicts: {country: arbiter_verdict} from country JSONs.

    Returns:
        Violation report with pass/fail.
    """
    violations: list[dict[str, Any]] = []
    ids_checked = ["ARB-004"]

    # Sources whose binding presence implies pre-arbiter narrowing occurred
    narrowing_indicators = {
        "governance", "failure_visibility", "reality_conflicts",
    }

    for country, verdict in country_verdicts.items():
        narrowing = verdict.get("pre_arbiter_narrowing", [])
        binding = set(verdict.get("binding_constraints", []))
        reasons = verdict.get("arbiter_reasoning", [])

        # Check: did any narrowing-indicator source produce a
        # SUPPRESSED or BLOCKED reason?
        has_hard_narrowing = False
        narrowing_sources: list[str] = []
        for reason in reasons:
            source = reason.get("source", "")
            decision = reason.get("decision", "VALID")
            if source in narrowing_indicators and decision in (
                "SUPPRESSED", "BLOCKED",
            ):
                has_hard_narrowing = True
                narrowing_sources.append(source)

        if has_hard_narrowing and not narrowing:
            violations.append(_emi_violation(
                "ARB-004",
                f"Arbiter verdict for {country} has hard narrowing from "
                f"{narrowing_sources} but pre_arbiter_narrowing is empty. "
                f"Hidden authority leakage: TRANSFORM modules narrowed "
                f"the epistemic input space without disclosure.",
                {
                    "country": country,
                    "narrowing_sources": narrowing_sources,
                    "binding_constraints": sorted(binding),
                    "pre_arbiter_narrowing": narrowing,
                },
            ))

    return {
        "passed": len(violations) == 0,
        "n_checks": len(ids_checked),
        "n_violations": len(violations),
        "violations": violations,
        "invariant_ids_checked": ids_checked,
    }


def enforce_epistemic_monotonicity(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
) -> dict[str, Any]:
    """Enforce epistemic monotonicity — clamp state_after to respect state_before.

    Unlike check_epistemic_monotonicity (which detects violations),
    this function CORRECTS violations by clamping downstream values
    to upstream ceilings. It returns the corrected state plus a
    record of any corrections applied.

    Args:
        state_before: Upstream epistemic state (ceiling).
        state_after: Downstream epistemic state (to be clamped).

    Returns:
        Dict with corrected_state, corrections applied, and report.
    """
    corrected = dict(state_after)
    corrections: list[dict[str, Any]] = []

    # Confidence: clamp to upstream ceiling
    conf_before = state_before.get("confidence", 1.0)
    conf_after = state_after.get("confidence", 1.0)
    if conf_after > conf_before:
        corrected["confidence"] = conf_before
        corrections.append({
            "field": "confidence",
            "original": conf_after,
            "corrected": conf_before,
            "reason": "Clamped to upstream confidence ceiling.",
        })

    # Publishability: clamp to upstream ceiling
    pub_before = state_before.get("publishability_status", "PUBLISHABLE")
    pub_after = state_after.get("publishability_status", "PUBLISHABLE")
    idx_before = _PUBLISHABILITY_ORDER.get(pub_before, 0)
    idx_after = _PUBLISHABILITY_ORDER.get(pub_after, 0)
    if idx_after < idx_before:
        corrected["publishability_status"] = pub_before
        corrections.append({
            "field": "publishability_status",
            "original": pub_after,
            "corrected": pub_before,
            "reason": "Clamped to upstream publishability ceiling.",
        })

    # Boolean fields: cannot re-enable if disabled upstream
    bool_fields = [
        "ranking_eligible",
        "cross_country_comparable",
    ]
    for field in bool_fields:
        val_before = state_before.get(field, True)
        val_after = state_after.get(field, True)
        if not val_before and val_after:
            corrected[field] = False
            corrections.append({
                "field": field,
                "original": val_after,
                "corrected": False,
                "reason": f"{field} disabled upstream — cannot re-enable.",
            })

    # Caveats: accumulate, never remove
    caveats_before = set(state_before.get("required_caveats", []))
    caveats_after = set(state_after.get("required_caveats", []))
    if not caveats_before.issubset(caveats_after):
        merged = sorted(caveats_before | caveats_after)
        corrected["required_caveats"] = merged
        corrections.append({
            "field": "required_caveats",
            "original": sorted(caveats_after),
            "corrected": merged,
            "reason": "Restored dropped upstream caveats.",
        })

    return {
        "corrected_state": corrected,
        "n_corrections": len(corrections),
        "corrections": corrections,
        "was_modified": len(corrections) > 0,
        "honesty_note": (
            f"Epistemic monotonicity enforcement: {len(corrections)} correction(s) applied. "
            f"{'State was already monotonic.' if not corrections else 'State was clamped to respect upstream ceilings.'}"
        ),
    }


def build_epistemic_invariant_report(
    monotonicity_result: dict[str, Any] | None = None,
    api_result: dict[str, Any] | None = None,
    replay_result: dict[str, Any] | None = None,
    diff_result: dict[str, Any] | None = None,
    arbiter_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a consolidated report of all EMI invariant checks.

    Args:
        monotonicity_result: Output of check_epistemic_monotonicity().
        api_result: Output of check_api_monotonicity().
        replay_result: Output of check_replay_determinism().
        diff_result: Output of check_diff_sensitivity().
        arbiter_result: Output of check_arbiter_dominance().

    Returns:
        Consolidated report with overall pass/fail.
    """
    all_violations: list[dict[str, Any]] = []
    all_ids_checked: list[str] = []
    n_checks = 0

    components = [
        ("monotonicity", monotonicity_result),
        ("api", api_result),
        ("replay", replay_result),
        ("diff", diff_result),
        ("arbiter", arbiter_result),
    ]

    for name, result in components:
        if result is not None:
            all_violations.extend(result.get("violations", []))
            all_ids_checked.extend(result.get("invariant_ids_checked", []))
            n_checks += result.get("n_checks", len(result.get("invariant_ids_checked", [])))

    passed = len(all_violations) == 0

    return {
        "passed": passed,
        "n_invariants_checked": n_checks,
        "n_violations": len(all_violations),
        "violations": all_violations,
        "invariant_ids_checked": all_ids_checked,
        "violation_ids": [v["invariant_id"] for v in all_violations],
        "honesty_note": (
            f"Epistemic invariant report: {'ALL PASSED' if passed else 'VIOLATIONS DETECTED'}. "
            f"{n_checks} invariants checked, {len(all_violations)} violation(s). "
            f"{'System maintains epistemic monotonicity.' if passed else 'HARD ERROR — system violates epistemic monotonicity.'}"
        ),
    }
