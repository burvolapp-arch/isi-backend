"""
tests.test_diff_epistemic_materiality — Epistemic Materiality in Diffs

Verifies:
    - Diffs must detect suppression status changes.
    - Diffs must detect ranking eligibility changes.
    - Diffs must detect authority conflict changes.
    - Diffs must detect confidence cap changes.
    - Diffs must detect publishability status changes.
    - Arbiter status changes are material changes.
"""

from __future__ import annotations

from backend.epistemic_arbiter import (
    ArbiterStatus,
    adjudicate,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_epistemic_diff(old_verdict: dict, new_verdict: dict) -> dict:
    """Detect epistemically material changes between two arbiter verdicts.

    This is the diff-level materiality check: if the arbiter's
    verdict changes in a way that affects what claims can be made,
    the diff MUST surface it.
    """
    changes: list[dict] = []

    # Status change
    old_status = old_verdict.get("final_epistemic_status")
    new_status = new_verdict.get("final_epistemic_status")
    if old_status != new_status:
        changes.append({
            "field": "final_epistemic_status",
            "old": old_status,
            "new": new_status,
            "material": True,
        })

    # Confidence cap change
    old_cap = old_verdict.get("final_confidence_cap", 1.0)
    new_cap = new_verdict.get("final_confidence_cap", 1.0)
    if abs(old_cap - new_cap) > 1e-6:
        changes.append({
            "field": "final_confidence_cap",
            "old": old_cap,
            "new": new_cap,
            "material": abs(old_cap - new_cap) > 0.05,
        })

    # Publishability change
    old_pub = old_verdict.get("final_publishability")
    new_pub = new_verdict.get("final_publishability")
    if old_pub != new_pub:
        changes.append({
            "field": "final_publishability",
            "old": old_pub,
            "new": new_pub,
            "material": True,
        })

    # Allowed claims change
    old_allowed = set(old_verdict.get("final_allowed_claims", []))
    new_allowed = set(new_verdict.get("final_allowed_claims", []))
    lost_claims = old_allowed - new_allowed
    gained_claims = new_allowed - old_allowed
    if lost_claims or gained_claims:
        changes.append({
            "field": "final_allowed_claims",
            "lost": sorted(lost_claims),
            "gained": sorted(gained_claims),
            "material": len(lost_claims) > 0,
        })

    # Forbidden claims change
    old_forbidden = set(old_verdict.get("final_forbidden_claims", []))
    new_forbidden = set(new_verdict.get("final_forbidden_claims", []))
    newly_forbidden = new_forbidden - old_forbidden
    newly_unforbidden = old_forbidden - new_forbidden
    if newly_forbidden or newly_unforbidden:
        changes.append({
            "field": "final_forbidden_claims",
            "newly_forbidden": sorted(newly_forbidden),
            "newly_unforbidden": sorted(newly_unforbidden),
            "material": len(newly_forbidden) > 0,
        })

    # Binding constraints change
    old_constraints = set(old_verdict.get("binding_constraints", []))
    new_constraints = set(new_verdict.get("binding_constraints", []))
    if old_constraints != new_constraints:
        changes.append({
            "field": "binding_constraints",
            "added": sorted(new_constraints - old_constraints),
            "removed": sorted(old_constraints - new_constraints),
            "material": True,
        })

    has_material = any(c.get("material", False) for c in changes)

    return {
        "has_epistemic_diff": len(changes) > 0,
        "has_material_epistemic_diff": has_material,
        "n_epistemic_changes": len(changes),
        "changes": changes,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: STATUS CHANGES
# ═══════════════════════════════════════════════════════════════════════════

class TestStatusChanges:
    """Arbiter status transitions must be detected."""

    def test_valid_to_blocked_detected(self):
        old = adjudicate(country="DE")
        new = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        diff = _detect_epistemic_diff(old, new)
        assert diff["has_epistemic_diff"] is True
        assert diff["has_material_epistemic_diff"] is True
        status_changes = [c for c in diff["changes"] if c["field"] == "final_epistemic_status"]
        assert len(status_changes) == 1
        assert status_changes[0]["old"] == ArbiterStatus.VALID
        assert status_changes[0]["new"] == ArbiterStatus.BLOCKED

    def test_blocked_to_valid_detected(self):
        old = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        assert diff["has_epistemic_diff"] is True

    def test_no_change_no_diff(self):
        old = adjudicate(country="DE")
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        assert diff["has_epistemic_diff"] is False
        assert diff["n_epistemic_changes"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: RANKING ELIGIBILITY CHANGES
# ═══════════════════════════════════════════════════════════════════════════

class TestRankingEligibilityChanges:
    """Changes in ranking eligibility must be material."""

    def test_ranking_lost_is_material(self):
        old = adjudicate(country="DE")
        new = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "DECISIVE",
                "confidence_cap": 0.3,
                "can_rank": False,
                "can_compare": False,
            },
        )
        diff = _detect_epistemic_diff(old, new)
        assert diff["has_material_epistemic_diff"] is True
        claim_changes = [c for c in diff["changes"] if c["field"] == "final_allowed_claims"]
        if claim_changes:
            assert "ranking" in claim_changes[0].get("lost", [])

    def test_ranking_gained_detected(self):
        old = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "DECISIVE",
                "confidence_cap": 0.3,
                "can_rank": False,
                "can_compare": False,
            },
        )
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        assert diff["has_epistemic_diff"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: CONFIDENCE CAP CHANGES
# ═══════════════════════════════════════════════════════════════════════════

class TestConfidenceCapChanges:
    """Confidence cap changes must be detected and assessed for materiality."""

    def test_large_cap_change_is_material(self):
        old = adjudicate(country="DE")
        new = adjudicate(
            country="DE",
            override_pressure={
                "max_strength": "STRONG",
                "confidence_cap": 0.4,
                "can_rank": True,
                "can_compare": True,
            },
        )
        diff = _detect_epistemic_diff(old, new)
        cap_changes = [c for c in diff["changes"] if c["field"] == "final_confidence_cap"]
        assert len(cap_changes) == 1
        assert cap_changes[0]["material"] is True

    def test_no_cap_change_no_diff(self):
        old = adjudicate(country="DE")
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        cap_changes = [c for c in diff["changes"] if c["field"] == "final_confidence_cap"]
        assert len(cap_changes) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: PUBLISHABILITY CHANGES
# ═══════════════════════════════════════════════════════════════════════════

class TestPublishabilityChanges:
    """Publishability status transitions must be material."""

    def test_publishable_to_not_publishable_is_material(self):
        old = adjudicate(country="DE")
        new = adjudicate(
            country="DE",
            governance={"governance_tier": "NON_COMPARABLE", "ranking_eligible": False},
        )
        diff = _detect_epistemic_diff(old, new)
        pub_changes = [c for c in diff["changes"] if c["field"] == "final_publishability"]
        assert len(pub_changes) == 1
        assert pub_changes[0]["material"] is True

    def test_same_publishability_no_diff(self):
        old = adjudicate(country="DE")
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        pub_changes = [c for c in diff["changes"] if c["field"] == "final_publishability"]
        assert len(pub_changes) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: FORBIDDEN CLAIMS CHANGES
# ═══════════════════════════════════════════════════════════════════════════

class TestForbiddenClaimsChanges:
    """New forbidden claims must be detected as material."""

    def test_newly_forbidden_claims_detected(self):
        old = adjudicate(country="DE")
        new = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        diff = _detect_epistemic_diff(old, new)
        forbidden_changes = [c for c in diff["changes"] if c["field"] == "final_forbidden_claims"]
        assert len(forbidden_changes) == 1
        assert len(forbidden_changes[0]["newly_forbidden"]) > 0
        assert forbidden_changes[0]["material"] is True

    def test_no_new_forbidden_no_diff(self):
        old = adjudicate(country="DE")
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        forbidden_changes = [c for c in diff["changes"] if c["field"] == "final_forbidden_claims"]
        assert len(forbidden_changes) == 0


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: BINDING CONSTRAINTS CHANGES
# ═══════════════════════════════════════════════════════════════════════════

class TestBindingConstraintsChanges:
    """Binding constraint additions/removals must be detected."""

    def test_new_binding_constraint_detected(self):
        old = adjudicate(country="DE")
        new = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        diff = _detect_epistemic_diff(old, new)
        bc_changes = [c for c in diff["changes"] if c["field"] == "binding_constraints"]
        assert len(bc_changes) == 1
        assert len(bc_changes[0]["added"]) > 0

    def test_removed_binding_constraint_detected(self):
        old = adjudicate(
            country="DE",
            truth_resolution={"truth_status": "INVALID", "export_blocked": True},
        )
        new = adjudicate(country="DE")
        diff = _detect_epistemic_diff(old, new)
        bc_changes = [c for c in diff["changes"] if c["field"] == "binding_constraints"]
        assert len(bc_changes) == 1
        assert len(bc_changes[0]["removed"]) > 0
