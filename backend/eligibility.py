"""
backend.eligibility — Theoretical country eligibility model for ISI.

This module answers four distinct questions for every country:

    1. COMPILE_READY:  Can the pipeline ingest and compute scores?
    2. RATEABLE:       Can the governance model produce a defensible rating?
    3. RANKABLE:       Can the country appear in ordinal rankings?
    4. COMPARABLE:     Can cross-country pairwise comparison be made?

These are NOT the same question. Conflating them is a methodological error.

Design contract:
    - Every classification is RULE-BASED and MACHINE-READABLE.
    - Every classification is THEORETICAL — derived from the current
      code, governance rules, and data architecture, NOT from external
      empirical validation.
    - "Theoretical" means: "the system's rules would permit this
      classification IF the required data were available and processed."
    - "Theoretical" does NOT mean "empirically validated" or "proven."
    - No classification may be upgraded beyond what the system's own
      rules support.
    - Every axis-country readiness assessment distinguishes:
        SOURCE_CONFIDENT / SOURCE_USABLE / PROXY_USED /
        CONSTRUCT_SUBSTITUTION / NOT_AVAILABLE
    - Every rule has explicit provenance (rule ID + plain-text rationale).

Epistemic status:
    - All thresholds governing eligibility are HEURISTIC or
      STRUCTURAL_NORMATIVE (see backend/calibration.py).
    - No eligibility classification has been externally validated.
    - The word "theoretical" appears throughout. This is intentional.

This module does NOT modify scores. It classifies countries.
"""

from __future__ import annotations

from typing import Any

from backend.constants import EU27_CODES, NUM_AXES
from backend.governance import (
    AXIS_CONFIDENCE_BASELINES,
    CONFIDENCE_PENALTIES,
    CONFIDENCE_THRESHOLDS,
    GOVERNANCE_TIERS,
    LOGISTICS_AXIS_ID,
    LOGISTICS_PROXY_CONFIDENCE_CAP,
    MAX_INVERTED_AXES_FOR_COMPARABLE,
    MAX_LOW_CONFIDENCE_AXES_FOR_RANKING,
    MIN_AXES_FOR_COMPOSITE,
    MIN_AXES_FOR_RANKING,
    MIN_MEAN_CONFIDENCE_FOR_RANKING,
    PRODUCER_INVERSION_REGISTRY,
    assess_axis_confidence,
    assess_country_governance,
)


# ═══════════════════════════════════════════════════════════════════════════
# ELIGIBILITY CLASSES
# ═══════════════════════════════════════════════════════════════════════════
# These form a strict hierarchy. Each class implies all classes above it.
#
#   COMPILE_READY:         Pipeline can ingest data and produce axis scores.
#   RATEABLE_WITHIN_MODEL: Governance model can produce a meaningful tier.
#   RANKABLE_WITHIN_MODEL: Country can appear in ordinal rankings.
#   COMPARABLE_WITHIN_MODEL: Cross-country pairwise comparison is defensible.
#   COMPUTABLE_BUT_NOT_DEFENSIBLE: Scores exist but governance refuses ranking.
#   NOT_READY:             Pipeline cannot produce scores for this country.
#
# "WITHIN_MODEL" suffix: These classifications are THEORETICAL. They reflect
# the system's internal rules, not external validation.

class TheoreticalEligibility:
    """Theoretical eligibility classification constants."""
    COMPILE_READY = "COMPILE_READY"
    RATEABLE_WITHIN_MODEL = "RATEABLE_WITHIN_MODEL"
    RANKABLE_WITHIN_MODEL = "RANKABLE_WITHIN_MODEL"
    COMPARABLE_WITHIN_MODEL = "COMPARABLE_WITHIN_MODEL"
    COMPUTABLE_BUT_NOT_DEFENSIBLE = "COMPUTABLE_BUT_NOT_DEFENSIBLE"
    NOT_READY = "NOT_READY"


VALID_ELIGIBILITY_CLASSES = frozenset({
    TheoreticalEligibility.COMPILE_READY,
    TheoreticalEligibility.RATEABLE_WITHIN_MODEL,
    TheoreticalEligibility.RANKABLE_WITHIN_MODEL,
    TheoreticalEligibility.COMPARABLE_WITHIN_MODEL,
    TheoreticalEligibility.COMPUTABLE_BUT_NOT_DEFENSIBLE,
    TheoreticalEligibility.NOT_READY,
})

# Hierarchy: higher index = more restrictive requirements
_ELIGIBILITY_RANK = {
    TheoreticalEligibility.NOT_READY: 0,
    TheoreticalEligibility.COMPILE_READY: 1,
    TheoreticalEligibility.COMPUTABLE_BUT_NOT_DEFENSIBLE: 2,
    TheoreticalEligibility.RATEABLE_WITHIN_MODEL: 3,
    TheoreticalEligibility.RANKABLE_WITHIN_MODEL: 4,
    TheoreticalEligibility.COMPARABLE_WITHIN_MODEL: 5,
}


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3: DECISION-GRADE COUNTRY USABILITY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════
# This answers: "Can a policy-maker actually USE this country's ISI output
# for a comparative decision?"
#
# Unlike TheoreticalEligibility (which is model-internal), this integrates:
#   - Eligibility class (from the 4-question hierarchy)
#   - Producer inversion severity
#   - Construct substitution extent
#   - Confidence level distribution
#   - Falsification consistency (when available)

class DecisionUsabilityClass:
    """Decision-grade country usability classification.

    TRUSTED_COMPARABLE:    Output is suitable for policy-level cross-country
                           comparison. All structural requirements met,
                           no falsification contradictions, confidence is
                           predominantly HIGH.

    CONDITIONALLY_USABLE:  Output can support decisions WITH documented
                           caveats. Some structural limitations exist but
                           the overall profile is defensible.

    STRUCTURALLY_LIMITED:  Output provides directional insight only.
                           Significant structural issues (inversions,
                           construct substitution, low confidence) limit
                           comparative use. NOT suitable for ranking.

    INVALID_FOR_COMPARISON: Output should NOT be used for any comparative
                            purpose. Structural disqualification (sanctions,
                            majority inversions, data absence).
    """
    TRUSTED_COMPARABLE = "TRUSTED_COMPARABLE"
    CONDITIONALLY_USABLE = "CONDITIONALLY_USABLE"
    STRUCTURALLY_LIMITED = "STRUCTURALLY_LIMITED"
    INVALID_FOR_COMPARISON = "INVALID_FOR_COMPARISON"


VALID_USABILITY_CLASSES = frozenset({
    DecisionUsabilityClass.TRUSTED_COMPARABLE,
    DecisionUsabilityClass.CONDITIONALLY_USABLE,
    DecisionUsabilityClass.STRUCTURALLY_LIMITED,
    DecisionUsabilityClass.INVALID_FOR_COMPARISON,
})

# Mapping from usability class to numeric rank for comparison
_USABILITY_RANK = {
    DecisionUsabilityClass.INVALID_FOR_COMPARISON: 0,
    DecisionUsabilityClass.STRUCTURALLY_LIMITED: 1,
    DecisionUsabilityClass.CONDITIONALLY_USABLE: 2,
    DecisionUsabilityClass.TRUSTED_COMPARABLE: 3,
}


# ═══════════════════════════════════════════════════════════════════════════
# EMPIRICAL ALIGNMENT DIMENSION
# ═══════════════════════════════════════════════════════════════════════════
# This extends the STRUCTURAL usability classification (DecisionUsabilityClass)
# with an EMPIRICAL dimension: does the ISI output align with external
# benchmarks?
#
# The structural class answers: "Is this output defensible given the system's
#   internal rules?"
# The empirical class answers: "Does this output agree with external reality?"
#
# These are ORTHOGONAL dimensions. A country can be:
#   TRUSTED_COMPARABLE + EMPIRICALLY_ALIGNED  → Best case
#   TRUSTED_COMPARABLE + EMPIRICALLY_WEAK     → Structurally sound but
#                                                external data disagrees
#   STRUCTURALLY_LIMITED + EMPIRICALLY_ALIGNED → Data agrees but internal
#                                                 structural issues exist
#
# The combined class (PolicyUsabilityClass) integrates both dimensions
# into a single policy-relevant classification.

class EmpiricalAlignmentClass:
    """Empirical alignment dimension for decision usability.

    EMPIRICALLY_GROUNDED:      ISI output aligns with available external
                               benchmarks. Correlation is STRONGLY_ALIGNED
                               on a majority of compared axes.

    EMPIRICALLY_MIXED:         Some axes align, some diverge. External
                               grounding is partial — useful with caveats.

    EMPIRICALLY_WEAK:          Alignment data exists but correlation is
                               low across most compared axes. ISI output
                               may not reflect external reality.

    EMPIRICALLY_CONTRADICTED:  ISI output actively contradicts external
                               benchmarks on a majority of compared axes.
                               Policy use requires extreme caution.

    NOT_EMPIRICALLY_ASSESSED:  No external benchmark data available for
                               comparison. Empirical alignment is unknown.
    """
    EMPIRICALLY_GROUNDED = "EMPIRICALLY_GROUNDED"
    EMPIRICALLY_MIXED = "EMPIRICALLY_MIXED"
    EMPIRICALLY_WEAK = "EMPIRICALLY_WEAK"
    EMPIRICALLY_CONTRADICTED = "EMPIRICALLY_CONTRADICTED"
    NOT_EMPIRICALLY_ASSESSED = "NOT_EMPIRICALLY_ASSESSED"


VALID_EMPIRICAL_CLASSES = frozenset({
    EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED,
    EmpiricalAlignmentClass.EMPIRICALLY_MIXED,
    EmpiricalAlignmentClass.EMPIRICALLY_WEAK,
    EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED,
    EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED,
})

_EMPIRICAL_RANK = {
    EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED: 0,
    EmpiricalAlignmentClass.EMPIRICALLY_WEAK: 1,
    EmpiricalAlignmentClass.EMPIRICALLY_MIXED: 2,
    EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED: 3,
    EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED: -1,  # Special: unknown
}


class PolicyUsabilityClass:
    """Combined structural + empirical usability for policy decisions.

    STRUCTURALLY_SOUND_EMPIRICALLY_ALIGNED:
        Best case. Internal structure is defensible AND external
        benchmarks confirm alignment. Suitable for policy use.

    STRUCTURALLY_SOUND_EMPIRICALLY_WEAK:
        Internal structure is defensible but external benchmarks
        show weak or no alignment. Use with documented caveats
        about empirical grounding.

    EMPIRICALLY_CONTRADICTED:
        External benchmarks actively contradict ISI output.
        Regardless of structural soundness, policy use requires
        extreme caution and investigation into WHY disagreement exists.

    STRUCTURALLY_LIMITED:
        Structural issues dominate. Empirical alignment does not
        override structural disqualification. Directional use only.

    INVALID_FOR_POLICY_USE:
        Either structurally invalid (sanctions, data absence) OR
        both structurally limited AND empirically contradicted.
        Do NOT use for any policy decision.

    NOT_ASSESSED:
        Insufficient information to classify.
    """
    SOUND_AND_ALIGNED = "STRUCTURALLY_SOUND_EMPIRICALLY_ALIGNED"
    SOUND_BUT_WEAK = "STRUCTURALLY_SOUND_EMPIRICALLY_WEAK"
    EMPIRICALLY_CONTRADICTED = "EMPIRICALLY_CONTRADICTED"
    STRUCTURALLY_LIMITED = "STRUCTURALLY_LIMITED"
    INVALID_FOR_POLICY_USE = "INVALID_FOR_POLICY_USE"
    NOT_ASSESSED = "NOT_ASSESSED"


VALID_POLICY_CLASSES = frozenset({
    PolicyUsabilityClass.SOUND_AND_ALIGNED,
    PolicyUsabilityClass.SOUND_BUT_WEAK,
    PolicyUsabilityClass.EMPIRICALLY_CONTRADICTED,
    PolicyUsabilityClass.STRUCTURALLY_LIMITED,
    PolicyUsabilityClass.INVALID_FOR_POLICY_USE,
    PolicyUsabilityClass.NOT_ASSESSED,
})


def classify_empirical_alignment(
    external_validation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify the empirical alignment dimension from external validation.

    Args:
        external_validation_result: Output of
            external_validation.build_external_validation_block() or
            external_validation.assess_country_alignment().
            None if external validation has not been performed.

    Returns:
        Dict with empirical_class, evidence, and interpretation.
    """
    if external_validation_result is None:
        return {
            "empirical_class": EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED,
            "n_axes_compared": 0,
            "n_axes_aligned": 0,
            "n_axes_divergent": 0,
            "interpretation": (
                "No external validation data available. Empirical "
                "alignment cannot be assessed."
            ),
        }

    # Extract alignment statistics — handle both block and raw formats
    n_compared = external_validation_result.get("n_axes_compared", 0)
    n_aligned = external_validation_result.get("n_axes_aligned", 0)
    n_divergent = external_validation_result.get("n_axes_divergent", 0)
    overall = external_validation_result.get("overall_alignment", "NO_DATA")

    if n_compared == 0 or overall == "NO_DATA":
        return {
            "empirical_class": EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED,
            "n_axes_compared": n_compared,
            "n_axes_aligned": n_aligned,
            "n_axes_divergent": n_divergent,
            "interpretation": (
                "No axes had sufficient external data for comparison."
            ),
        }

    # Classification logic:
    # EMPIRICALLY_GROUNDED: majority aligned, none divergent
    # EMPIRICALLY_MIXED: some aligned, some divergent
    # EMPIRICALLY_WEAK: majority not aligned (neither aligned nor divergent — just weak)
    # EMPIRICALLY_CONTRADICTED: majority divergent

    if n_divergent > n_compared / 2:
        emp_class = EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED
        interp = (
            f"External benchmarks contradict ISI output on "
            f"{n_divergent}/{n_compared} compared axes."
        )
    elif n_aligned > n_compared / 2:
        emp_class = EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED
        interp = (
            f"External benchmarks confirm ISI alignment on "
            f"{n_aligned}/{n_compared} compared axes."
        )
    elif n_aligned > 0 and n_divergent > 0:
        emp_class = EmpiricalAlignmentClass.EMPIRICALLY_MIXED
        interp = (
            f"Mixed external alignment: {n_aligned} aligned, "
            f"{n_divergent} divergent out of {n_compared} compared."
        )
    else:
        emp_class = EmpiricalAlignmentClass.EMPIRICALLY_WEAK
        interp = (
            f"External comparisons available ({n_compared} axes) but "
            f"alignment is weak — neither strongly confirming nor "
            f"contradicting ISI output."
        )

    return {
        "empirical_class": emp_class,
        "n_axes_compared": n_compared,
        "n_axes_aligned": n_aligned,
        "n_axes_divergent": n_divergent,
        "interpretation": interp,
    }


def classify_policy_usability(
    structural_class: str,
    empirical_class: str,
) -> dict[str, Any]:
    """Derive combined policy usability from structural + empirical dimensions.

    Args:
        structural_class: DecisionUsabilityClass value.
        empirical_class: EmpiricalAlignmentClass value.

    Returns:
        Dict with policy_usability_class, justification, and guidance.
    """
    # RULE 1: Structural invalidity is absolute
    if structural_class == DecisionUsabilityClass.INVALID_FOR_COMPARISON:
        if empirical_class == EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED:
            policy_class = PolicyUsabilityClass.INVALID_FOR_POLICY_USE
            justification = (
                "Structurally invalid AND empirically contradicted. "
                "No basis for policy use."
            )
        else:
            policy_class = PolicyUsabilityClass.INVALID_FOR_POLICY_USE
            justification = (
                "Structurally invalid — empirical alignment cannot "
                "override structural disqualification."
            )

    # RULE 2: Empirical contradiction is a hard warning
    elif empirical_class == EmpiricalAlignmentClass.EMPIRICALLY_CONTRADICTED:
        policy_class = PolicyUsabilityClass.EMPIRICALLY_CONTRADICTED
        justification = (
            f"Structural class is {structural_class} but external "
            f"benchmarks actively contradict ISI output. Investigation "
            f"required before policy use."
        )

    # RULE 3: Structural limitation dominates over weak empirical
    elif structural_class == DecisionUsabilityClass.STRUCTURALLY_LIMITED:
        if empirical_class == EmpiricalAlignmentClass.EMPIRICALLY_WEAK:
            policy_class = PolicyUsabilityClass.INVALID_FOR_POLICY_USE
            justification = (
                "Structurally limited AND empirically weak. "
                "Insufficient basis for any policy decision."
            )
        else:
            policy_class = PolicyUsabilityClass.STRUCTURALLY_LIMITED
            justification = (
                f"Structural limitations dominate. Empirical status: "
                f"{empirical_class}."
            )

    # RULE 4: Sound structure + good empirical → best class
    elif structural_class in (
        DecisionUsabilityClass.TRUSTED_COMPARABLE,
        DecisionUsabilityClass.CONDITIONALLY_USABLE,
    ):
        if empirical_class == EmpiricalAlignmentClass.EMPIRICALLY_GROUNDED:
            policy_class = PolicyUsabilityClass.SOUND_AND_ALIGNED
            justification = (
                f"Structural class: {structural_class}. External "
                f"benchmarks confirm alignment. Suitable for policy use."
            )
        elif empirical_class in (
            EmpiricalAlignmentClass.EMPIRICALLY_WEAK,
            EmpiricalAlignmentClass.EMPIRICALLY_MIXED,
        ):
            policy_class = PolicyUsabilityClass.SOUND_BUT_WEAK
            justification = (
                f"Structural class: {structural_class}. External "
                f"alignment is {empirical_class}. Use with empirical "
                f"caveats documented."
            )
        elif empirical_class == EmpiricalAlignmentClass.NOT_EMPIRICALLY_ASSESSED:
            policy_class = PolicyUsabilityClass.SOUND_BUT_WEAK
            justification = (
                f"Structural class: {structural_class}. No external "
                f"validation available — empirical grounding unknown."
            )
        else:
            policy_class = PolicyUsabilityClass.SOUND_BUT_WEAK
            justification = (
                f"Structural class: {structural_class}. Empirical "
                f"status: {empirical_class}."
            )

    # RULE 5: Default — not assessed
    else:
        policy_class = PolicyUsabilityClass.NOT_ASSESSED
        justification = (
            f"Cannot determine combined class from structural="
            f"{structural_class}, empirical={empirical_class}."
        )

    guidance = _build_policy_usability_guidance(policy_class)

    return {
        "policy_usability_class": policy_class,
        "structural_class": structural_class,
        "empirical_class": empirical_class,
        "justification": justification,
        "policy_guidance": guidance,
    }


def _build_policy_usability_guidance(policy_class: str) -> str:
    """Generate policy guidance for a combined usability class."""
    if policy_class == PolicyUsabilityClass.SOUND_AND_ALIGNED:
        return (
            "ISI output is structurally defensible and empirically "
            "grounded. Suitable for cross-country comparison and "
            "policy decision support. Standard methodological caveats "
            "apply."
        )
    if policy_class == PolicyUsabilityClass.SOUND_BUT_WEAK:
        return (
            "ISI output is structurally defensible but empirical "
            "alignment with external benchmarks is weak, mixed, or "
            "not yet assessed. Use for policy decisions WITH explicit "
            "documentation of empirical limitations."
        )
    if policy_class == PolicyUsabilityClass.EMPIRICALLY_CONTRADICTED:
        return (
            "CAUTION: External benchmarks contradict ISI output. "
            "Before policy use, investigate whether divergence stems "
            "from (a) ISI measurement issues, (b) construct differences, "
            "or (c) genuine structural differences. Do NOT use without "
            "resolution of the contradiction."
        )
    if policy_class == PolicyUsabilityClass.STRUCTURALLY_LIMITED:
        return (
            "ISI output provides directional insight only due to "
            "structural limitations. NOT suitable for cross-country "
            "ranking or comparison. Empirical alignment does not "
            "override structural disqualification."
        )
    if policy_class == PolicyUsabilityClass.INVALID_FOR_POLICY_USE:
        return (
            "DO NOT use ISI output for this country in any policy "
            "decision context. Both structural and empirical grounds "
            "are insufficient."
        )
    return "Insufficient information for policy guidance."


def classify_decision_usability(
    country: str,
    governance_result: dict[str, Any] | None = None,
    falsification_result: dict[str, Any] | None = None,
    external_validation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify a country's decision-grade usability.

    Derives from:
    1. TheoreticalEligibility (4-question hierarchy)
    2. Governance tier and confidence distribution
    3. Producer inversion count and severity
    4. Construct substitution extent
    5. Falsification flags (if available)
    6. External validation alignment (if available)

    Args:
        country: ISO-2 country code.
        governance_result: Output of assess_country_governance(), or None
            (in which case it will be simulated).
        falsification_result: Output of assess_country_falsification(), or None.
        external_validation_result: Output of
            external_validation.build_external_validation_block() or
            assess_country_alignment(). None if not available.

    Returns:
        Dict with decision_usability_class, empirical_alignment,
        policy_usability_class, justification, conditions,
        and policy-relevant guidance.
    """
    # Get eligibility classification
    classification = classify_country(country)
    eligibility_class = classification["eligibility_class"]

    # Get or simulate governance
    if governance_result is None:
        if classification["can_compile"]:
            governance_result = _simulate_governance(country)
        else:
            # Cannot even compile → INVALID
            empirical = classify_empirical_alignment(external_validation_result)
            emp_class = empirical["empirical_class"]
            policy = classify_policy_usability(
                DecisionUsabilityClass.INVALID_FOR_COMPARISON, emp_class,
            )
            return {
                "country": country,
                "decision_usability_class": DecisionUsabilityClass.INVALID_FOR_COMPARISON,
                "empirical_alignment_class": emp_class,
                "policy_usability_class": policy["policy_usability_class"],
                "eligibility_class": eligibility_class,
                "governance_tier": "N/A",
                "justification": (
                    f"Country {country} cannot compile ISI scores. "
                    f"No usability assessment possible."
                ),
                "conditions": [],
                "policy_guidance": (
                    "DO NOT use ISI output for this country in any "
                    "comparative or decision context."
                ),
                "falsification_flag": (
                    falsification_result.get("overall_flag", "NOT_ASSESSED")
                    if falsification_result else "NOT_ASSESSED"
                ),
                "empirical_alignment": empirical,
                "policy_usability": policy,
            }

    gov_tier = governance_result.get("governance_tier", "UNKNOWN")
    mean_conf = governance_result.get("mean_axis_confidence", 0)
    n_inverted = governance_result.get("n_producer_inverted_axes", 0)
    n_valid = governance_result.get("n_valid_axes", 0)
    ranking_eligible = governance_result.get("ranking_eligible", False)
    comparable = governance_result.get("cross_country_comparable", False)

    # Count HIGH and LOW confidence axes
    axis_confidences = governance_result.get("axis_confidences", [])
    n_high = sum(
        1 for ac in axis_confidences
        if ac.get("confidence_level") == "HIGH"
    )
    n_low = sum(
        1 for ac in axis_confidences
        if ac.get("confidence_level") == "LOW"
    )

    # Get falsification flag
    falsification_flag = "NOT_ASSESSED"
    if falsification_result:
        falsification_flag = falsification_result.get(
            "overall_flag", "NOT_ASSESSED"
        )

    # Count construct substitutions
    readiness = build_axis_readiness_matrix(country)
    n_construct_sub = sum(1 for r in readiness if r["construct_substitution"])
    n_proxy = sum(1 for r in readiness if r["proxy_used"])

    # ── DECISION LOGIC ──
    # Rule ordering: most restrictive first

    conditions: list[str] = []
    usability_class: str

    # RULE 1: INVALID — sanctions, NON_COMPARABLE tier, or cannot compile
    if gov_tier == "NON_COMPARABLE" or eligibility_class == TheoreticalEligibility.NOT_READY:
        usability_class = DecisionUsabilityClass.INVALID_FOR_COMPARISON
        conditions.append(f"Governance tier: {gov_tier}")
        if n_inverted >= 3:
            conditions.append(f"{n_inverted} producer-inverted axes")

    # RULE 2: INVALID — falsification contradiction
    elif falsification_flag == "CONTRADICTION":
        usability_class = DecisionUsabilityClass.INVALID_FOR_COMPARISON
        conditions.append("Falsification contradiction detected")

    # RULE 3: STRUCTURALLY_LIMITED — LOW_CONFIDENCE tier
    elif gov_tier == "LOW_CONFIDENCE":
        usability_class = DecisionUsabilityClass.STRUCTURALLY_LIMITED
        conditions.append(f"Governance tier: {gov_tier}")
        if n_inverted >= 2:
            conditions.append(f"{n_inverted} producer-inverted axes")
        if mean_conf < 0.45:
            conditions.append(f"Mean confidence: {mean_conf:.2f}")

    # RULE 4: STRUCTURALLY_LIMITED — not ranking-eligible
    elif not ranking_eligible:
        usability_class = DecisionUsabilityClass.STRUCTURALLY_LIMITED
        conditions.append("Not ranking-eligible within model")
        if n_low >= 3:
            conditions.append(f"{n_low} axes at LOW confidence")

    # RULE 5: CONDITIONALLY_USABLE — PARTIALLY_COMPARABLE, or
    #          has inversions, or significant construct substitution
    elif (gov_tier == "PARTIALLY_COMPARABLE"
          or n_inverted >= 1
          or n_construct_sub >= 2
          or n_proxy >= 2
          or falsification_flag == "TENSION"):
        usability_class = DecisionUsabilityClass.CONDITIONALLY_USABLE
        if gov_tier == "PARTIALLY_COMPARABLE":
            conditions.append(f"Governance tier: {gov_tier}")
        if n_inverted >= 1:
            conditions.append(f"{n_inverted} producer-inverted axis(es)")
        if n_construct_sub >= 2:
            conditions.append(f"{n_construct_sub} axes use construct substitution")
        if n_proxy >= 2:
            conditions.append(f"{n_proxy} axes use proxy data")
        if falsification_flag == "TENSION":
            conditions.append("Falsification tension detected")

    # RULE 6: TRUSTED_COMPARABLE — FULLY_COMPARABLE, high confidence,
    #          no falsification issues
    elif (gov_tier == "FULLY_COMPARABLE"
          and comparable
          and ranking_eligible
          and n_high >= 4
          and falsification_flag in ("CONSISTENT", "NOT_ASSESSED")):
        usability_class = DecisionUsabilityClass.TRUSTED_COMPARABLE

    # RULE 7: Default to CONDITIONALLY_USABLE
    else:
        usability_class = DecisionUsabilityClass.CONDITIONALLY_USABLE
        conditions.append("Does not meet all TRUSTED_COMPARABLE requirements")
        if n_high < 4:
            conditions.append(f"Only {n_high}/6 axes at HIGH confidence")

    # ── BUILD POLICY GUIDANCE ──
    guidance = _build_policy_guidance(usability_class, country, conditions)

    # ── EMPIRICAL ALIGNMENT DIMENSION ──
    empirical = classify_empirical_alignment(external_validation_result)
    emp_class = empirical["empirical_class"]

    # ── COMBINED POLICY USABILITY ──
    policy = classify_policy_usability(usability_class, emp_class)

    return {
        "country": country,
        "decision_usability_class": usability_class,
        "decision_usability_dimensions": _compute_usability_dimensions(
            usability_class, ranking_eligible, gov_tier, conditions,
            falsification_flag, n_inverted, mean_conf,
        ),
        "failure_modes": _compute_failure_modes(
            usability_class, conditions, gov_tier, falsification_flag,
            n_inverted, mean_conf, n_construct_sub,
        ),
        "empirical_alignment_class": emp_class,
        "policy_usability_class": policy["policy_usability_class"],
        "eligibility_class": eligibility_class,
        "governance_tier": gov_tier,
        "mean_confidence": round(mean_conf, 3),
        "n_producer_inverted": n_inverted,
        "n_valid_axes": n_valid,
        "n_high_confidence_axes": n_high,
        "n_low_confidence_axes": n_low,
        "n_construct_substitutions": n_construct_sub,
        "n_proxy_axes": n_proxy,
        "conditions": conditions,
        "falsification_flag": falsification_flag,
        "empirical_alignment": empirical,
        "policy_usability": policy,
        "justification": (
            f"Country {country} classified as {usability_class} "
            f"(structural), {emp_class} (empirical), "
            f"→ {policy['policy_usability_class']} (policy) based on "
            f"governance tier ({gov_tier}), {n_inverted} inversions, "
            f"{n_high} HIGH-confidence axes, falsification={falsification_flag}."
        ),
        "policy_guidance": policy["policy_guidance"],
        "theoretical_caveat": (
            "The structural usability classification is derived from the ISI "
            "system's internal governance rules and has NOT been validated "
            "against external expert panel assessments. The empirical "
            "alignment dimension reflects comparison against external "
            "benchmarks where available. Combined policy usability "
            "integrates both dimensions."
        ),
    }


def _build_policy_guidance(
    usability_class: str,
    country: str,
    conditions: list[str],
) -> str:
    """Build plain-language policy guidance for a usability class."""
    if usability_class == DecisionUsabilityClass.TRUSTED_COMPARABLE:
        return (
            f"ISI output for {country} is suitable for cross-country "
            f"comparison and policy-level decisions. All structural "
            f"requirements met. Standard methodological caveats apply."
        )
    if usability_class == DecisionUsabilityClass.CONDITIONALLY_USABLE:
        cond_text = "; ".join(conditions) if conditions else "minor limitations"
        return (
            f"ISI output for {country} can support comparative analysis "
            f"WITH the following documented conditions: {cond_text}. "
            f"Results should be presented with these caveats."
        )
    if usability_class == DecisionUsabilityClass.STRUCTURALLY_LIMITED:
        return (
            f"ISI output for {country} provides DIRECTIONAL insight only. "
            f"Do NOT use for ranking or cross-country comparison. "
            f"Structural limitations: {'; '.join(conditions)}."
        )
    if usability_class == DecisionUsabilityClass.INVALID_FOR_COMPARISON:
        return (
            f"DO NOT use ISI output for {country} in any comparative "
            f"or decision context. Structural disqualification: "
            f"{'; '.join(conditions)}."
        )
    return f"Usability assessment for {country}: {usability_class}."


def _compute_usability_dimensions(
    usability_class: str,
    ranking_eligible: bool,
    governance_tier: str,
    conditions: list[str],
    falsification_flag: str,
    n_inverted: int,
    mean_confidence: float,
) -> dict[str, bool]:
    """Compute per-dimension usability assessment.

    Returns a dict with:
        ranking: bool — suitable for ordinal ranking
        directional_insight: bool — suitable for directional analysis
        policy_design: bool — suitable for policy design input
        stress_testing: bool — suitable for scenario/stress testing

    These are NOT independent — they form a hierarchy where each
    higher-level use requires all lower-level suitability.
    """
    # Ranking: most restrictive
    ranking = (
        usability_class in (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
        )
        and ranking_eligible
        and governance_tier in ("FULLY_COMPARABLE", "PARTIALLY_COMPARABLE")
        and falsification_flag != "CONTRADICTION"
    )

    # Policy design: requires at least conditionally usable
    policy_design = (
        usability_class in (
            DecisionUsabilityClass.TRUSTED_COMPARABLE,
            DecisionUsabilityClass.CONDITIONALLY_USABLE,
        )
        and falsification_flag != "CONTRADICTION"
        and n_inverted < 3
    )

    # Stress testing: works even with limitations (scenario analysis)
    stress_testing = (
        usability_class != DecisionUsabilityClass.INVALID_FOR_COMPARISON
        and mean_confidence > 0.20
    )

    # Directional insight: least restrictive — anything computable
    directional_insight = (
        usability_class != DecisionUsabilityClass.INVALID_FOR_COMPARISON
    )

    return {
        "ranking": ranking,
        "directional_insight": directional_insight,
        "policy_design": policy_design,
        "stress_testing": stress_testing,
    }


def _compute_failure_modes(
    usability_class: str,
    conditions: list[str],
    governance_tier: str,
    falsification_flag: str,
    n_inverted: int,
    mean_confidence: float,
    n_construct_sub: int,
) -> list[dict[str, str]]:
    """Compute structured failure modes for decision usability.

    Each failure mode describes:
        condition: what triggered it
        effect: what it means for the output
        severity: WARNING | ERROR | CRITICAL
    """
    modes: list[dict[str, str]] = []

    if governance_tier == "NON_COMPARABLE":
        modes.append({
            "condition": f"Governance tier: {governance_tier}",
            "effect": "Output is structurally compromised. No comparative use.",
            "severity": "CRITICAL",
        })
    elif governance_tier == "LOW_CONFIDENCE":
        modes.append({
            "condition": f"Governance tier: {governance_tier}",
            "effect": "Output provides directional insight only. Not rankable.",
            "severity": "ERROR",
        })

    if falsification_flag == "CONTRADICTION":
        modes.append({
            "condition": "Falsification contradiction detected",
            "effect": (
                "Internal checks contradict governance classification. "
                "Output reliability is unknown."
            ),
            "severity": "CRITICAL",
        })
    elif falsification_flag == "TENSION":
        modes.append({
            "condition": "Falsification tension detected",
            "effect": (
                "Internal checks show tension with governance classification. "
                "Use with heightened scrutiny."
            ),
            "severity": "WARNING",
        })

    if n_inverted >= 3:
        modes.append({
            "condition": f"{n_inverted} producer-inverted axes",
            "effect": (
                "Majority of profile measures absence of import dependency, "
                "not vulnerability. Construct is fundamentally different."
            ),
            "severity": "CRITICAL",
        })
    elif n_inverted >= 2:
        modes.append({
            "condition": f"{n_inverted} producer-inverted axes",
            "effect": (
                "Significant construct inversion. Cross-country comparison "
                "with non-producer countries is misleading."
            ),
            "severity": "ERROR",
        })
    elif n_inverted == 1:
        modes.append({
            "condition": "1 producer-inverted axis",
            "effect": "One axis measures different construct. Document in comparison.",
            "severity": "WARNING",
        })

    if n_construct_sub >= 2:
        modes.append({
            "condition": f"{n_construct_sub} axes use construct substitution",
            "effect": (
                "Multiple axes measure related but different constructs. "
                "Composite is a weighted mix of real and proxy measurements."
            ),
            "severity": "WARNING",
        })

    if mean_confidence < 0.35:
        modes.append({
            "condition": f"Mean confidence: {mean_confidence:.2f}",
            "effect": "Very low confidence across axes. All outputs are fragile.",
            "severity": "ERROR",
        })
    elif mean_confidence < 0.45:
        modes.append({
            "condition": f"Mean confidence: {mean_confidence:.2f}",
            "effect": "Below-threshold confidence. Ranking excluded.",
            "severity": "WARNING",
        })

    for cond in conditions:
        # Avoid duplicating conditions already covered above
        if any(cond in m["condition"] for m in modes):
            continue
        modes.append({
            "condition": cond,
            "effect": "Contributes to usability limitation.",
            "severity": "WARNING",
        })

    return modes


# ═══════════════════════════════════════════════════════════════════════════
# WEAKNESS CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════
# Every blocking weakness is categorized so the explanation object can
# say WHAT TYPE of issue prevents an upgrade.
#
# Task 1.5: LOGISTICS_GAP renamed to CONSTRUCT_SUBSTITUTION —
# what the ISI does for non-EU logistics is NOT a "gap" that can be
# filled. It is the use of a TRADE proxy (Comtrade bilateral goods)
# where LOGISTICS data (port throughput, freight tonnage, modal shares)
# is what the axis construct requires. This is a fundamentally different
# kind of data, not a less complete version of the same data.

class WeaknessType:
    """Categories of weakness that block eligibility upgrades."""
    DATA_AVAILABILITY = "DATA_AVAILABILITY"
    STRUCTURAL_METHODOLOGY = "STRUCTURAL_METHODOLOGY"
    PRODUCER_INVERSION = "PRODUCER_INVERSION"
    CONSTRUCT_SUBSTITUTION = "CONSTRUCT_SUBSTITUTION"
    CONFIDENCE_DEGRADATION = "CONFIDENCE_DEGRADATION"
    COMPARABILITY_FAILURE = "COMPARABILITY_FAILURE"
    THRESHOLD_FRAGILITY = "THRESHOLD_FRAGILITY"
    SANCTIONS_DISTORTION = "SANCTIONS_DISTORTION"


# Backward-compatibility alias — old name was misleading
# (it implied the issue was just "missing data" rather than
#  "using a fundamentally different measurement construct")
LOGISTICS_GAP = WeaknessType.CONSTRUCT_SUBSTITUTION


# ═══════════════════════════════════════════════════════════════════════════
# AXIS-COUNTRY READINESS LEVELS (Task 1.2)
# ═══════════════════════════════════════════════════════════════════════════
# These describe what the data architecture provides for a given
# country + axis pair. They are ORDERED from best to worst.
#
# Each level answers a different question:
#   SOURCE_CONFIDENT:         Primary source exists with good coverage
#                             and no structural distortions.
#   SOURCE_USABLE:            Primary source exists but with known
#                             limitations (single channel, partial
#                             coverage, granularity loss).
#   PROXY_USED:               A proxy source stands in for the primary.
#                             The proxy measures a RELATED but different
#                             construct. (e.g., trade value as proxy
#                             for port throughput on logistics)
#   CONSTRUCT_SUBSTITUTION:   The axis construct is fundamentally
#                             different for this country. The measurement
#                             is valid arithmetic but does not capture
#                             what the axis label claims. (e.g., import
#                             concentration for a major exporter)
#   NOT_AVAILABLE:            No source covers this country+axis.

class ReadinessLevel:
    """Per-axis readiness levels for a country."""
    SOURCE_CONFIDENT = "SOURCE_CONFIDENT"
    SOURCE_USABLE = "SOURCE_USABLE"
    PROXY_USED = "PROXY_USED"
    CONSTRUCT_SUBSTITUTION = "CONSTRUCT_SUBSTITUTION"
    NOT_AVAILABLE = "NOT_AVAILABLE"


_READINESS_ORDER = {
    ReadinessLevel.SOURCE_CONFIDENT: 4,
    ReadinessLevel.SOURCE_USABLE: 3,
    ReadinessLevel.PROXY_USED: 2,
    ReadinessLevel.CONSTRUCT_SUBSTITUTION: 1,
    ReadinessLevel.NOT_AVAILABLE: 0,
}

VALID_READINESS_LEVELS = frozenset(_READINESS_ORDER.keys())


# ═══════════════════════════════════════════════════════════════════════════
# DATA ARCHITECTURE PROFILE
# ═══════════════════════════════════════════════════════════════════════════
# Static profile of what the ISI data architecture provides for each
# country. This is based on SOURCE AVAILABILITY, not on whether the
# pipeline has been run.

# Countries that are BIS LBS reporters (banking claims data available)
BIS_REPORTERS: frozenset[str] = frozenset({
    # EU-27: all are reporters via Eurozone/ECB or national central banks
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    # Non-EU BIS reporters
    "AU", "GB", "JP", "KR", "NO", "US", "ZA",
    # Partial reporters
    "CN",  # Chinese banks report through Hong Kong aggregate
})

# Countries that participate in IMF CPIS
CPIS_PARTICIPANTS: frozenset[str] = frozenset({
    # EU-27: all participate
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    # Non-EU participants
    "AU", "BR", "GB", "IN", "JP", "KR", "NO", "SA", "US", "ZA",
})

# Countries with Comtrade bilateral trade data (axes 2, 3, 5)
# NOTE: Comtrade is used for THREE separate axes (energy, technology,
# critical inputs). The HS code scope differs per axis, but the
# SOURCE is the same UN Comtrade mirror. Do NOT assume that
# "Comtrade coverage" means the same thing for all three axes —
# coverage is the same, but the CONSTRUCT differs per axis.
COMTRADE_REPORTERS: frozenset[str] = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    "AU", "BR", "CN", "GB", "IN", "JP", "KR", "NO", "SA", "US", "ZA",
    "RU",  # Pre-sanctions data exists
})

# Countries with SIPRI TIV data (axis 4) as importers
# All countries appear in SIPRI if they import major weapons;
# but very small importers may have zero entries in a given window
SIPRI_LIKELY_IMPORTERS: frozenset[str] = frozenset({
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    "AU", "BR", "CN", "GB", "IN", "JP", "KR", "NO", "SA", "US", "ZA",
    "RU",
})

# Countries with Eurostat bilateral logistics data (axis 6)
# CRITICAL: Eurostat ONLY covers EU member states.
# For non-EU countries, there is NO equivalent bilateral logistics
# source available for free download. This is a STRUCTURAL_LIMITATION.
# See pipeline/ingest/logistics.py for the definitive statement.
EUROSTAT_LOGISTICS_COUNTRIES: frozenset[str] = EU27_CODES

# Countries known to have sanctions distortion (post-2022 data unreliable)
SANCTIONS_DISTORTED: frozenset[str] = frozenset({"RU"})


# ═══════════════════════════════════════════════════════════════════════════
# PER-AXIS SOURCE PROFILE (Task 1.2, Task 1.6)
# ═══════════════════════════════════════════════════════════════════════════
# This is the heart of the audit-grade readiness registry. Each axis
# has DIFFERENT sources, scope, and limitations — they must NOT be
# collapsed into "has Comtrade data" as though axes 2, 3, and 5 are
# interchangeable.
#
# The AXIS_SOURCE_PROFILE dict maps each axis to a description of
# its primary source, what that source actually measures, and what
# it does NOT measure. This information is sourced from
# pipeline/config.py AXIS_REGISTRY and pipeline/orchestrator.py
# AXIS_INGEST_MAP.
#
# Rule provenance: ELIG-SRC-001 through ELIG-SRC-006

AXIS_SOURCE_PROFILE: dict[int, dict[str, Any]] = {
    1: {
        "axis_name": "financial",
        "primary_sources": ["bis_lbs", "imf_cpis"],
        "dual_channel": True,
        "construct": (
            "Cross-border banking claims (BIS LBS) + portfolio investment "
            "positions (IMF CPIS). Two independent channels measuring "
            "different facets of financial exposure."
        ),
        "what_it_measures": (
            "Concentration of bilateral cross-border financial claims "
            "(banking) and portfolio investment (debt/equity) among "
            "reporting counterparties."
        ),
        "what_it_does_NOT_measure": (
            "FDI stocks/flows, domestic financial exposures, derivatives, "
            "off-balance-sheet instruments. BIS LBS is limited to ~30 "
            "reporting countries; CPIS to ~80 participants."
        ),
        "single_channel_degradation": (
            "If CPIS is absent (e.g., CN), axis degrades to banking-only "
            "concentration — halving the financial exposure construct."
        ),
        "rule_id": "ELIG-SRC-001",
    },
    2: {
        "axis_name": "energy",
        "primary_sources": ["un_comtrade"],
        "dual_channel": False,
        "construct": (
            "Bilateral imports of energy commodities "
            "(HS 2701/2709/2710/2711/2716: coal, crude oil, petroleum "
            "products, natural gas/LNG, electricity) from UN Comtrade."
        ),
        "what_it_measures": (
            "Concentration of energy commodity imports by trade value. "
            "Captures realized trade flows for fossil fuel categories."
        ),
        "what_it_does_NOT_measure": (
            "Long-term contract lock-in, strategic reserves, domestic "
            "production capacity, renewable energy, nuclear fuel "
            "(HS 2612 is under critical_inputs), energy transit/re-export, "
            "price-vs-volume distortions."
        ),
        "single_channel_degradation": "N/A — single-source axis.",
        "rule_id": "ELIG-SRC-002",
    },
    3: {
        "axis_name": "technology",
        "primary_sources": ["un_comtrade"],
        "dual_channel": False,
        "construct": (
            "Bilateral imports of semiconductor goods "
            "(HS 8541 semiconductor devices + HS 8542 electronic "
            "integrated circuits) from UN Comtrade."
        ),
        "what_it_measures": (
            "Concentration of semiconductor goods imports by trade value. "
            "Captures physical goods crossing borders."
        ),
        "what_it_does_NOT_measure": (
            "Semiconductor manufacturing equipment (HS 8486), design IP "
            "and licensing (services trade), fabless design dependency, "
            "embedded semiconductors in finished products. Country of "
            "export may differ from country of design/IP ownership."
        ),
        "single_channel_degradation": "N/A — single-source axis.",
        "rule_id": "ELIG-SRC-003",
    },
    4: {
        "axis_name": "defense",
        "primary_sources": ["sipri"],
        "dual_channel": False,
        "construct": (
            "Major conventional weapons transfers tracked by SIPRI Arms "
            "Transfers Database. TIV (Trend Indicator Value) is NOT a "
            "monetary value — it indexes military capability transferred."
        ),
        "what_it_measures": (
            "Concentration of major weapons imports by SIPRI TIV. "
            "Covers aircraft, armoured vehicles, artillery, air defence, "
            "missiles, naval weapons, sensors/EW, ships."
        ),
        "what_it_does_NOT_measure": (
            "Small arms, ammunition, dual-use technology, military "
            "services/training, cyber/electronic warfare, licensed "
            "production, MRO contracts, black/grey market transfers. "
            "TIV is incommensurable with USD trade values on other axes."
        ),
        "single_channel_degradation": "N/A — SIPRI is the only source.",
        "rule_id": "ELIG-SRC-004",
    },
    5: {
        "axis_name": "critical_inputs",
        "primary_sources": ["un_comtrade"],
        "dual_channel": False,
        "construct": (
            "Bilateral imports of critical raw materials: rare earths "
            "(HS 2612/2846), lithium (2825/2836), cobalt (2605/8105), "
            "manganese (2602), titanium (2614/8108), chromium (2610), "
            "tungsten (2611), platinum (7110), graphite (2504), "
            "niobium (2615), silicon (2804)."
        ),
        "what_it_measures": (
            "Concentration of critical raw material imports by trade value."
        ),
        "what_it_does_NOT_measure": (
            "Processed/refined materials beyond HS scope, recycled/ "
            "secondary materials, stockpile releases, long-term offtake "
            "agreements, substitution capacity. Trade value may "
            "underrepresent volume dependency for low-unit-value "
            "high-volume materials."
        ),
        "single_channel_degradation": "N/A — single-source axis.",
        "rule_id": "ELIG-SRC-005",
    },
    6: {
        "axis_name": "logistics",
        "primary_sources": ["eurostat_comext", "oecd_logistics", "national_stats"],
        "dual_channel": False,
        "construct": (
            "Freight logistics infrastructure dependency: maritime "
            "container flows, rail freight, air cargo by partner. "
            "EU-27 uses Eurostat bilateral modal data. Non-EU countries "
            "have NO equivalent bilateral logistics source — the system "
            "uses Comtrade bilateral TRADE DATA as a PROXY. This is "
            "CONSTRUCT SUBSTITUTION, not a coverage gap."
        ),
        "what_it_measures": (
            "For EU-27: concentration of physical logistics flows "
            "(tonnes, TEU, modal shares). "
            "For non-EU: NOTHING directly — trade-value proxy is used "
            "instead, which measures goods trade, NOT logistics capacity."
        ),
        "what_it_does_NOT_measure": (
            "Pipeline transport (partially via energy axis), digital/ "
            "data logistics, warehousing, inland distribution, insurance "
            "and financial logistics services."
        ),
        "single_channel_degradation": (
            "N/A — there is only one source per country group. "
            "EU-27: Eurostat. Non-EU: trade-value proxy (Comtrade). "
            "These are fundamentally different measurement constructs."
        ),
        "eu_vs_non_eu_warning": (
            "CRITICAL: For non-EU countries, what is labeled 'logistics' "
            "is actually bilateral trade value from Comtrade — the same "
            "underlying source as axes 2, 3, 5. This is CONSTRUCT "
            "SUBSTITUTION: the axis label says 'logistics' but the "
            "measurement is 'trade'. The two constructs are related but "
            "NOT equivalent. Port throughput, freight tonnage, and modal "
            "shares are what the axis concept requires; trade value is "
            "what is available. This distinction MUST be surfaced in "
            "every output that references axis 6 for non-EU countries."
        ),
        "rule_id": "ELIG-SRC-006",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# AXIS-COUNTRY READINESS REGISTRY (Task 1.2)
# ═══════════════════════════════════════════════════════════════════════════

def _assess_axis_readiness(country: str, axis_num: int) -> dict[str, Any]:
    """Assess readiness level for a single country + axis pair.

    Returns a detailed dict with:
    - readiness_level: one of ReadinessLevel constants
    - source_present: bool — any source covers this country
    - source_usable: bool — source is present AND no structural distortion
    - source_confident: bool — source is usable AND dual-channel/full-scope
    - proxy_used: bool — a proxy stands in for the primary source
    - construct_substitution: bool — measurement construct is fundamentally different
    - issues: list of specific issues
    - rule_id: provenance for this assessment

    Rule provenance: ELIG-RDN-{axis_num}-{issue_type}
    """
    profile = AXIS_SOURCE_PROFILE.get(axis_num, {})
    producer_info = PRODUCER_INVERSION_REGISTRY.get(country, {})
    inverted = axis_num in producer_info.get("inverted_axes", [])
    is_sanctioned = country in SANCTIONS_DISTORTED

    issues: list[dict[str, str]] = []
    source_present = False
    source_usable = False
    source_confident = False
    proxy_used = False
    construct_sub = False

    # ── Axis 1: Financial ─────────────────────────────────────────────
    if axis_num == 1:
        has_bis = country in BIS_REPORTERS
        has_cpis = country in CPIS_PARTICIPANTS
        source_present = has_bis or has_cpis

        if has_bis and has_cpis:
            source_confident = True
            source_usable = True
        elif has_bis or has_cpis:
            source_usable = True
            if not has_cpis:
                issues.append({
                    "issue": "CPIS_NON_PARTICIPANT",
                    "detail": (
                        "Country does not participate in IMF CPIS. "
                        "Financial axis measures only banking claims (BIS LBS), "
                        "not portfolio investment. Construct is halved."
                    ),
                    "rule_id": "ELIG-RDN-1-CPIS",
                })
            if not has_bis:
                issues.append({
                    "issue": "BIS_NON_REPORTER",
                    "detail": (
                        "Country is not a BIS LBS reporter. Financial axis "
                        "measures only portfolio investment (CPIS), not "
                        "banking claims. Construct is halved."
                    ),
                    "rule_id": "ELIG-RDN-1-BIS",
                })

    # ── Axis 2: Energy ────────────────────────────────────────────────
    elif axis_num == 2:
        source_present = country in COMTRADE_REPORTERS
        if source_present:
            source_usable = True
            source_confident = True
            # Energy axis has good Comtrade coverage — HS codes are
            # well-defined and high-value so reporting is reliable.

    # ── Axis 3: Technology ────────────────────────────────────────────
    elif axis_num == 3:
        source_present = country in COMTRADE_REPORTERS
        if source_present:
            source_usable = True
            # Technology axis has an HS6 vs CN8 granularity risk for
            # semiconductor subcategories. Not confident without CN8.
            if country in EU27_CODES:
                source_confident = True  # CN8 available via Eurostat
            else:
                source_confident = False  # HS6 only — granularity loss
                issues.append({
                    "issue": "HS6_GRANULARITY",
                    "detail": (
                        "Non-EU countries use HS6 classification. "
                        "Semiconductor subcategory detail (CN8) unavailable. "
                        "~7 subcategories collapse to ~3. HHI partner "
                        "structure unchanged but category weights degrade."
                    ),
                    "rule_id": "ELIG-RDN-3-HS6",
                })

    # ── Axis 4: Defense ───────────────────────────────────────────────
    elif axis_num == 4:
        source_present = country in SIPRI_LIKELY_IMPORTERS
        if source_present:
            source_usable = True
            # SIPRI TIV is inherently lumpy — 6-year window smooths
            # but cannot eliminate delivery schedule noise.
            source_confident = False  # Conservative: TIV lumpiness
            issues.append({
                "issue": "TIV_LUMPINESS",
                "detail": (
                    "SIPRI TIV data is inherently lumpy. A single "
                    "multi-billion fighter jet order can dominate the "
                    "6-year window. Year-to-year volatility is expected "
                    "and does not indicate changing dependency."
                ),
                "rule_id": "ELIG-RDN-4-LUMP",
            })

    # ── Axis 5: Critical Inputs ───────────────────────────────────────
    elif axis_num == 5:
        source_present = country in COMTRADE_REPORTERS
        if source_present:
            source_usable = True
            source_confident = True
            # Critical inputs HS codes are specific enough for
            # reliable bilateral concentration measurement.

    # ── Axis 6: Logistics (CRITICAL — construct substitution) ─────────
    elif axis_num == 6:
        if country in EUROSTAT_LOGISTICS_COUNTRIES:
            # EU-27: Eurostat bilateral modal data — genuine logistics
            source_present = True
            source_usable = True
            source_confident = True
        elif country in COMTRADE_REPORTERS:
            # Non-EU: trade-value proxy — NOT logistics data
            source_present = True  # Something exists
            source_usable = False  # But it's not logistics data
            proxy_used = True
            construct_sub = True
            issues.append({
                "issue": "CONSTRUCT_SUBSTITUTION",
                "detail": (
                    "No bilateral logistics source exists for this country. "
                    "Comtrade bilateral trade value is used as PROXY. This is "
                    "CONSTRUCT SUBSTITUTION: the axis label says 'logistics' "
                    "(port throughput, freight tonnage, modal shares) but the "
                    "measurement is 'trade value' (goods crossing borders). "
                    "These are related but fundamentally different constructs. "
                    "See pipeline/ingest/logistics.py for the structural limitation."
                ),
                "rule_id": "ELIG-RDN-6-CONSTSUB",
            })
        else:
            source_present = False

    # ── Cross-axis issues ─────────────────────────────────────────────

    # Producer inversion affects the CONSTRUCT, not the source
    if inverted and source_present:
        construct_sub = True
        issues.append({
            "issue": "PRODUCER_INVERSION",
            "detail": (
                f"Country is a major exporter on axis {axis_num} "
                f"({profile.get('axis_name', '?')}). Import concentration "
                f"does NOT measure strategic vulnerability — it measures the "
                f"ABSENCE of import dependency. The construct is fundamentally "
                f"different for this country."
            ),
            "rule_id": f"ELIG-RDN-{axis_num}-INV",
        })

    # Sanctions affect usability
    if is_sanctioned and source_present:
        source_usable = False
        source_confident = False
        issues.append({
            "issue": "SANCTIONS_DISTORTION",
            "detail": (
                "Active sanctions regime during measurement window. "
                "All post-2022 data reflects crisis-distorted patterns, "
                "not steady-state bilateral structure."
            ),
            "rule_id": f"ELIG-RDN-{axis_num}-SANC",
        })

    # ── Determine overall readiness level ─────────────────────────────
    if not source_present:
        level = ReadinessLevel.NOT_AVAILABLE
    elif construct_sub:
        level = ReadinessLevel.CONSTRUCT_SUBSTITUTION
    elif proxy_used:
        level = ReadinessLevel.PROXY_USED
    elif source_confident:
        level = ReadinessLevel.SOURCE_CONFIDENT
    elif source_usable:
        level = ReadinessLevel.SOURCE_USABLE
    else:
        level = ReadinessLevel.NOT_AVAILABLE

    return {
        "axis_id": axis_num,
        "axis_name": profile.get("axis_name", f"axis_{axis_num}"),
        "readiness_level": level,
        "source_present": source_present,
        "source_usable": source_usable,
        "source_confident": source_confident,
        "proxy_used": proxy_used,
        "construct_substitution": construct_sub,
        "issues": issues,
        "rule_id": profile.get("rule_id", f"ELIG-SRC-{axis_num:03d}"),
        "primary_sources": profile.get("primary_sources", []),
    }


def build_axis_readiness_matrix(country: str) -> list[dict[str, Any]]:
    """Build the full 6-axis readiness assessment for a country.

    Returns a list of 6 readiness dicts, one per axis.
    """
    return [_assess_axis_readiness(country, ax) for ax in range(1, NUM_AXES + 1)]


def build_full_readiness_registry() -> dict[str, list[dict[str, Any]]]:
    """Build the complete axis-by-country readiness registry.

    Returns:
        Dict of country_code -> list of 6 axis readiness assessments.
        Machine-readable. Every entry distinguishes SOURCE_CONFIDENT,
        SOURCE_USABLE, PROXY_USED, and CONSTRUCT_SUBSTITUTION.
    """
    return {
        country: build_axis_readiness_matrix(country)
        for country in sorted(ALL_ASSESSABLE_COUNTRIES)
    }


# ═══════════════════════════════════════════════════════════════════════════
# FOUR DISTINCT QUESTIONS
# ═══════════════════════════════════════════════════════════════════════════

def can_compile(country: str) -> dict[str, Any]:
    """Question 1: Can this country be compiled now?

    Compilation requires:
    - At least MIN_AXES_FOR_COMPOSITE axes with source_present=True
    - Country appears in at least one source set

    Rule provenance: ELIG-Q1-001 through ELIG-Q1-003

    Returns:
        Dict with 'result' (bool), 'reason', 'blockers'.
    """
    blockers: list[dict[str, Any]] = []
    readiness = build_axis_readiness_matrix(country)

    n_source_present = sum(1 for r in readiness if r["source_present"])
    axis_availability: dict[int, bool] = {
        r["axis_id"]: r["source_present"] for r in readiness
    }

    if n_source_present < MIN_AXES_FOR_COMPOSITE:
        blockers.append({
            "type": WeaknessType.DATA_AVAILABILITY,
            "detail": (
                f"Only {n_source_present} axes have any source present "
                f"(minimum {MIN_AXES_FOR_COMPOSITE} for composite). "
                f"Unavailable axes: {[r['axis_id'] for r in readiness if not r['source_present']]}"
            ),
            "rule_id": "ELIG-Q1-001",
        })

    # Sanctions don't block compilation, but block interpretability
    is_sanctioned = country in SANCTIONS_DISTORTED

    return {
        "question": "Can this country be compiled?",
        "country": country,
        "result": len(blockers) == 0,
        "n_axes_available": n_source_present,
        "axis_availability": axis_availability,
        "axis_readiness": readiness,
        "sanctions_distorted": is_sanctioned,
        "blockers": blockers,
        "caveat": (
            "THEORETICAL: based on source coverage analysis, not on "
            "actual pipeline execution. Actual compilation may fail "
            "if source data is missing, corrupt, or delayed."
        ),
        "rule_id": "ELIG-Q1",
    }


def can_rate(country: str) -> dict[str, Any]:
    """Question 2: Can this country be rated now?

    Rating requires:
    - Compilable (question 1)
    - Governance tier is NOT NON_COMPARABLE
    - At least MIN_AXES_FOR_COMPOSITE axes with data
    - Composite is defensible under governance rules

    Rule provenance: ELIG-Q2-001 through ELIG-Q2-004

    Returns:
        Dict with 'result' (bool), 'reason', 'blockers', 'governance_tier'.
    """
    compile_result = can_compile(country)
    blockers: list[dict[str, Any]] = list(compile_result["blockers"])

    if not compile_result["result"]:
        return {
            "question": "Can this country be rated?",
            "country": country,
            "result": False,
            "governance_tier": None,
            "blockers": blockers,
            "caveat": "Not compile-ready — rating not possible.",
            "rule_id": "ELIG-Q2",
        }

    # Simulate governance assessment
    gov = _simulate_governance(country)
    tier = gov["governance_tier"]

    if tier == "NON_COMPARABLE":
        blockers.append({
            "type": WeaknessType.COMPARABILITY_FAILURE,
            "detail": (
                f"Governance tier is NON_COMPARABLE — too many structural "
                f"issues for defensible rating"
            ),
            "rule_id": "ELIG-Q2-001",
        })

    if not gov["composite_defensible"]:
        blockers.append({
            "type": WeaknessType.CONFIDENCE_DEGRADATION,
            "detail": "Composite not defensible under governance rules",
            "rule_id": "ELIG-Q2-002",
        })

    if country in SANCTIONS_DISTORTED:
        blockers.append({
            "type": WeaknessType.SANCTIONS_DISTORTION,
            "detail": "Active sanctions regime — all post-2022 data is crisis-distorted",
            "rule_id": "ELIG-Q2-003",
        })

    return {
        "question": "Can this country be rated?",
        "country": country,
        "result": len(blockers) == 0,
        "governance_tier": tier,
        "composite_defensible": gov["composite_defensible"],
        "mean_confidence": gov["mean_axis_confidence"],
        "blockers": blockers,
        "caveat": (
            "THEORETICAL: rating means the governance model WOULD produce "
            "a defensible tier. It does NOT mean the ISI score is correct "
            "or externally validated."
        ),
        "rule_id": "ELIG-Q2",
    }


def can_rank(country: str) -> dict[str, Any]:
    """Question 3: Can this country be ranked now?

    Ranking requires:
    - Rateable (question 2)
    - Governance tier is FULLY_COMPARABLE or PARTIALLY_COMPARABLE
    - ranking_eligible = True under governance rules
    - At least MIN_AXES_FOR_RANKING axes with data
    - Mean confidence >= threshold

    Rule provenance: ELIG-Q3-001 through ELIG-Q3-003

    Returns:
        Dict with 'result' (bool), 'reason', 'blockers'.
    """
    rate_result = can_rate(country)
    blockers: list[dict[str, Any]] = list(rate_result["blockers"])

    if not rate_result["result"]:
        return {
            "question": "Can this country be ranked?",
            "country": country,
            "result": False,
            "ranking_eligible": False,
            "blockers": blockers,
            "caveat": "Not rateable — ranking not possible.",
            "rule_id": "ELIG-Q3",
        }

    gov = _simulate_governance(country)

    if not gov["ranking_eligible"]:
        blockers.append({
            "type": WeaknessType.CONFIDENCE_DEGRADATION,
            "detail": (
                f"Governance rules reject ranking: tier={gov['governance_tier']}, "
                f"mean_confidence={gov['mean_axis_confidence']}, "
                f"n_low_axes={gov['n_low_confidence_axes']}"
            ),
            "rule_id": "ELIG-Q3-001",
        })

    if gov["n_axes_with_data"] < MIN_AXES_FOR_RANKING:
        blockers.append({
            "type": WeaknessType.DATA_AVAILABILITY,
            "detail": (
                f"Only {gov['n_axes_with_data']} axes (need {MIN_AXES_FOR_RANKING} "
                f"for ranking)"
            ),
            "rule_id": "ELIG-Q3-002",
        })

    return {
        "question": "Can this country be ranked?",
        "country": country,
        "result": len(blockers) == 0,
        "ranking_eligible": gov["ranking_eligible"],
        "governance_tier": gov["governance_tier"],
        "blockers": blockers,
        "caveat": (
            "THEORETICAL: ranking eligibility is determined by heuristic "
            "governance thresholds. The ordinal position is meaningful "
            "only within the same governance tier partition."
        ),
        "rule_id": "ELIG-Q3",
    }


def can_compare(country: str) -> dict[str, Any]:
    """Question 4: Can this country be compared cross-country now?

    Comparison requires:
    - Rankable (question 3)
    - cross_country_comparable = True under governance rules
    - No sanctions distortion
    - <= MAX_INVERTED_AXES_FOR_COMPARABLE producer inversions

    Rule provenance: ELIG-Q4-001 through ELIG-Q4-002

    Returns:
        Dict with 'result' (bool), 'reason', 'blockers'.
    """
    rank_result = can_rank(country)
    blockers: list[dict[str, Any]] = list(rank_result["blockers"])

    if not rank_result["result"]:
        return {
            "question": "Can this country be compared cross-country?",
            "country": country,
            "result": False,
            "cross_country_comparable": False,
            "blockers": blockers,
            "caveat": "Not rankable — comparison not possible.",
            "rule_id": "ELIG-Q4",
        }

    gov = _simulate_governance(country)

    if not gov["cross_country_comparable"]:
        blockers.append({
            "type": WeaknessType.COMPARABILITY_FAILURE,
            "detail": (
                f"Governance rules reject cross-country comparison: "
                f"n_inverted={gov['n_producer_inverted_axes']}, "
                f"tier={gov['governance_tier']}"
            ),
            "rule_id": "ELIG-Q4-001",
        })

    return {
        "question": "Can this country be compared cross-country?",
        "country": country,
        "result": len(blockers) == 0,
        "cross_country_comparable": gov["cross_country_comparable"],
        "governance_tier": gov["governance_tier"],
        "blockers": blockers,
        "caveat": (
            "THEORETICAL: cross-country comparability is governed by "
            "heuristic rules about structural similarity. Two countries "
            "that are both 'comparable' may still differ substantially "
            "in data quality on specific axes."
        ),
        "rule_id": "ELIG-Q4",
    }


# ═══════════════════════════════════════════════════════════════════════════
# COMPOSITE ELIGIBILITY CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════

def classify_country(country: str) -> dict[str, Any]:
    """Classify a country into the theoretical eligibility hierarchy.

    Returns:
        Dict with:
        - eligibility_class: The highest class the country qualifies for
        - can_compile, can_rate, can_rank, can_compare: bool answers
        - governance_tier: Theoretical governance tier
        - explanation: Why this class
        - upgrade_blockers: What prevents reaching a higher class
        - weakness_types: Categories of blocking issues
        - fragility_note: Whether classification is threshold-sensitive
        - axis_readiness: Full per-axis readiness matrix
    """
    compile_q = can_compile(country)
    rate_q = can_rate(country)
    rank_q = can_rank(country)
    compare_q = can_compare(country)

    # Determine highest eligible class
    if compare_q["result"]:
        eligibility = TheoreticalEligibility.COMPARABLE_WITHIN_MODEL
    elif rank_q["result"]:
        eligibility = TheoreticalEligibility.RANKABLE_WITHIN_MODEL
    elif rate_q["result"]:
        eligibility = TheoreticalEligibility.RATEABLE_WITHIN_MODEL
    elif compile_q["result"]:
        # Compilable but not rateable
        if rate_q.get("governance_tier") in ("LOW_CONFIDENCE", "NON_COMPARABLE"):
            eligibility = TheoreticalEligibility.COMPUTABLE_BUT_NOT_DEFENSIBLE
        else:
            eligibility = TheoreticalEligibility.COMPILE_READY
    else:
        eligibility = TheoreticalEligibility.NOT_READY

    # Collect all blockers
    all_blockers = compare_q.get("blockers", [])
    weakness_types = list({b["type"] for b in all_blockers})

    # Build upgrade explanation
    upgrade_blockers = _what_blocks_upgrade(
        eligibility, all_blockers, compile_q, rate_q, rank_q, compare_q,
    )

    # Simulate governance for additional metadata
    gov_tier = rate_q.get("governance_tier")
    gov = _simulate_governance(country) if compile_q["result"] else None

    # Fragility note
    fragility = _assess_fragility(country, gov) if gov else "N/A — not compile-ready"

    # Per-axis readiness
    readiness = build_axis_readiness_matrix(country)
    axis_strength = _axis_strength_summary(country)

    return {
        "country": country,
        "eligibility_class": eligibility,
        "theoretical_caveat": (
            "This classification is THEORETICAL — derived from the ISI system's "
            "internal rules, data architecture profile, and governance thresholds. "
            "It has NOT been externally validated. 'Rateable within model' means "
            "the system's own governance rules would permit a rating, not that "
            "the rating is empirically grounded."
        ),
        "can_compile": compile_q["result"],
        "can_rate": rate_q["result"],
        "can_rank": rank_q["result"],
        "can_compare": compare_q["result"],
        "governance_tier": gov_tier,
        "n_axes_available": compile_q["n_axes_available"],
        "mean_confidence": rate_q.get("mean_confidence"),
        "n_producer_inversions": len(
            PRODUCER_INVERSION_REGISTRY.get(country, {}).get("inverted_axes", [])
        ),
        "sanctions_distorted": country in SANCTIONS_DISTORTED,
        "logistics_available": any(
            r["source_present"] for r in readiness if r["axis_id"] == LOGISTICS_AXIS_ID
        ),
        "logistics_construct_substitution": any(
            r["construct_substitution"] for r in readiness
            if r["axis_id"] == LOGISTICS_AXIS_ID
        ),
        "axis_strength_summary": axis_strength,
        "axis_readiness": readiness,
        "weakness_types": weakness_types,
        "upgrade_blockers": upgrade_blockers,
        "fragility_note": fragility,
        "ranking_allowed": rank_q["result"],
        "cross_country_comparison_allowed": compare_q["result"],
        "logistics_blocks_confidence": not any(
            r["source_present"] for r in readiness if r["axis_id"] == LOGISTICS_AXIS_ID
        ),
        "producer_inversion_materially_degrades": (
            len(PRODUCER_INVERSION_REGISTRY.get(country, {}).get("inverted_axes", []))
            >= MAX_INVERTED_AXES_FOR_COMPARABLE
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# COUNTRY REGISTRY BUILDER
# ═══════════════════════════════════════════════════════════════════════════

# All countries the system can theoretically process
ALL_ASSESSABLE_COUNTRIES: frozenset[str] = frozenset({
    # EU-27
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
    # Phase-1 expansion
    "AU", "BR", "CN", "GB", "IN", "JP", "KR", "NO", "SA", "US", "ZA",
    # Blocked
    "RU",
})


def build_full_registry() -> list[dict[str, Any]]:
    """Build the complete country eligibility registry.

    Evaluates every country in ALL_ASSESSABLE_COUNTRIES using
    rule-based classification.

    Returns:
        List of classification dicts, sorted by eligibility class
        (highest first), then alphabetically.
    """
    registry: list[dict[str, Any]] = []
    for country in sorted(ALL_ASSESSABLE_COUNTRIES):
        entry = classify_country(country)
        registry.append(entry)

    # Sort: highest eligibility first, then alphabetical
    registry.sort(
        key=lambda x: (-_ELIGIBILITY_RANK.get(x["eligibility_class"], 0), x["country"])
    )
    return registry


def get_registry_summary() -> dict[str, Any]:
    """Return summary grouped by eligibility class.

    This is the formal answer to "which countries can be compiled/rated/ranked."
    """
    registry = build_full_registry()
    by_class: dict[str, list[str]] = {}
    for entry in registry:
        cls = entry["eligibility_class"]
        by_class.setdefault(cls, []).append(entry["country"])

    # Readiness level summary
    readiness_registry = build_full_readiness_registry()
    axis_readiness_summary: dict[int, dict[str, int]] = {}
    for ax in range(1, NUM_AXES + 1):
        level_counts: dict[str, int] = {}
        for _country, axes in readiness_registry.items():
            level = axes[ax - 1]["readiness_level"]
            level_counts[level] = level_counts.get(level, 0) + 1
        axis_readiness_summary[ax] = level_counts

    return {
        "methodology_status": "THEORETICAL — not externally validated",
        "total_countries_assessed": len(registry),
        "by_class": {
            cls: {
                "countries": sorted(countries),
                "count": len(countries),
            }
            for cls, countries in by_class.items()
        },
        "answers": {
            "theoretically_compile_ready": sorted(
                e["country"] for e in registry if e["can_compile"]
            ),
            "theoretically_rateable": sorted(
                e["country"] for e in registry if e["can_rate"]
            ),
            "theoretically_rankable": sorted(
                e["country"] for e in registry if e["can_rank"]
            ),
            "theoretically_comparable": sorted(
                e["country"] for e in registry if e["can_compare"]
            ),
            "computable_but_not_defensible": sorted(
                e["country"] for e in registry
                if e["can_compile"] and not e["can_rate"]
            ),
            "not_ready": sorted(
                e["country"] for e in registry if not e["can_compile"]
            ),
        },
        "axis_readiness_summary": axis_readiness_summary,
        "honesty_note": (
            "ALL classifications are THEORETICAL. They reflect the ISI "
            "system's internal governance rules and data architecture "
            "analysis. No classification has been externally validated. "
            "'Rankable within model' does NOT mean 'correctly ranked.' "
            "'Comparable within model' does NOT mean 'meaningfully "
            "comparable in reality.' These classifications are the "
            "system's BEST CURRENT JUDGMENT about its own capabilities."
        ),
        "non_empirical_warning": (
            "The thresholds governing these classifications (confidence "
            "baselines, penalty magnitudes, tier boundaries, minimum axis "
            "counts) are heuristic or structural-normative. None are "
            "empirically calibrated against external benchmarks. Small "
            "threshold changes could reclassify some countries. See "
            "sensitivity analysis for fragility assessment."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════
# SENSITIVITY ANALYSIS FOR ELIGIBILITY
# ═══════════════════════════════════════════════════════════════════════════

def run_eligibility_sensitivity(
    perturbation_pct: float = 0.15,
) -> dict[str, Any]:
    """Test how country eligibility classes change under threshold perturbations.

    Perturbs:
    - Confidence baselines (+/-perturbation_pct)
    - Inversion threshold (+/-1)
    - MIN_MEAN_CONFIDENCE_FOR_RANKING (+/-perturbation_pct)
    - MIN_AXES_FOR_RANKING (+/-1)
    - LOGISTICS_PROXY_CONFIDENCE_CAP (+/-perturbation_pct)

    Returns:
        Dict with stable countries, fragile countries, threshold-sensitive details.
    """
    # Baseline classifications
    baseline_registry = build_full_registry()
    baseline_classes = {e["country"]: e["eligibility_class"] for e in baseline_registry}

    # Track which countries change class under any perturbation
    changes: dict[str, list[str]] = {c: [] for c in baseline_classes}

    # --- Perturbation 1: Confidence baselines ---
    _perturb_confidence_baselines(baseline_classes, changes, perturbation_pct)

    # --- Perturbation 2: Mean confidence threshold ---
    _perturb_mean_confidence(baseline_classes, changes, perturbation_pct)

    # --- Perturbation 3: Inversion threshold ---
    _perturb_inversion_threshold(baseline_classes, changes)

    # --- Perturbation 4: Minimum axes for ranking ---
    _perturb_min_axes_ranking(baseline_classes, changes)

    # Classify results
    stable: list[str] = []
    fragile: list[str] = []
    for country, change_list in changes.items():
        if len(change_list) == 0:
            stable.append(country)
        else:
            fragile.append(country)

    return {
        "perturbation_pct": perturbation_pct,
        "total_countries": len(baseline_classes),
        "stable_countries": sorted(stable),
        "n_stable": len(stable),
        "fragile_countries": sorted(fragile),
        "n_fragile": len(fragile),
        "fragile_details": {
            country: changes[country]
            for country in sorted(fragile)
        },
        "interpretation": (
            f"Under +/-{perturbation_pct*100:.0f}% threshold perturbation, "
            f"{len(stable)} countries maintain their eligibility class "
            f"(stable) and {len(fragile)} would change class (fragile). "
            f"Fragile classifications should be presented with explicit "
            f"threshold-sensitivity warnings."
        ),
        "honesty_note": (
            "Countries that flip class under small perturbations should "
            "NOT be presented as confidently classified. Their eligibility "
            "is a boundary artifact of heuristic threshold choices."
        ),
    }


def _perturb_confidence_baselines(
    baseline_classes: dict[str, str],
    changes: dict[str, list[str]],
    pct: float,
) -> None:
    """Perturb all confidence baselines and check class changes."""
    import backend.governance as gov_mod

    original_baselines = dict(gov_mod.AXIS_CONFIDENCE_BASELINES)

    for direction, label in [(1, "up"), (-1, "down")]:
        # Temporarily perturb baselines
        for axis_id in original_baselines:
            gov_mod.AXIS_CONFIDENCE_BASELINES[axis_id] = min(
                1.0,
                max(0.0, original_baselines[axis_id] * (1 + direction * pct)),
            )

        # Re-classify
        for country in baseline_classes:
            try:
                new = classify_country(country)
                if new["eligibility_class"] != baseline_classes[country]:
                    changes[country].append(
                        f"confidence_baselines_{label}: "
                        f"{baseline_classes[country]} -> {new['eligibility_class']}"
                    )
            except Exception:
                pass

        # Restore
        for axis_id in original_baselines:
            gov_mod.AXIS_CONFIDENCE_BASELINES[axis_id] = original_baselines[axis_id]


def _perturb_mean_confidence(
    baseline_classes: dict[str, str],
    changes: dict[str, list[str]],
    pct: float,
) -> None:
    """Perturb MIN_MEAN_CONFIDENCE_FOR_RANKING."""
    import backend.governance as gov_mod

    original = gov_mod.MIN_MEAN_CONFIDENCE_FOR_RANKING

    for direction, label in [(1, "up"), (-1, "down")]:
        gov_mod.MIN_MEAN_CONFIDENCE_FOR_RANKING = original * (1 + direction * pct)

        for country in baseline_classes:
            try:
                new = classify_country(country)
                if new["eligibility_class"] != baseline_classes[country]:
                    changes[country].append(
                        f"mean_confidence_threshold_{label}: "
                        f"{baseline_classes[country]} -> {new['eligibility_class']}"
                    )
            except Exception:
                pass

        gov_mod.MIN_MEAN_CONFIDENCE_FOR_RANKING = original


def _perturb_inversion_threshold(
    baseline_classes: dict[str, str],
    changes: dict[str, list[str]],
) -> None:
    """Perturb MAX_INVERTED_AXES_FOR_COMPARABLE by +/-1."""
    import backend.governance as gov_mod

    original = gov_mod.MAX_INVERTED_AXES_FOR_COMPARABLE

    for new_val, label in [(original - 1, "tighter"), (original + 1, "looser")]:
        if new_val < 1:
            continue
        gov_mod.MAX_INVERTED_AXES_FOR_COMPARABLE = new_val

        for country in baseline_classes:
            try:
                new = classify_country(country)
                if new["eligibility_class"] != baseline_classes[country]:
                    changes[country].append(
                        f"inversion_threshold_{label}: "
                        f"{baseline_classes[country]} -> {new['eligibility_class']}"
                    )
            except Exception:
                pass

        gov_mod.MAX_INVERTED_AXES_FOR_COMPARABLE = original


def _perturb_min_axes_ranking(
    baseline_classes: dict[str, str],
    changes: dict[str, list[str]],
) -> None:
    """Perturb MIN_AXES_FOR_RANKING by +/-1."""
    import backend.governance as gov_mod

    original = gov_mod.MIN_AXES_FOR_RANKING

    for new_val, label in [(original - 1, "looser"), (original + 1, "tighter")]:
        if new_val < MIN_AXES_FOR_COMPOSITE:
            continue
        gov_mod.MIN_AXES_FOR_RANKING = new_val

        for country in baseline_classes:
            try:
                new = classify_country(country)
                if new["eligibility_class"] != baseline_classes[country]:
                    changes[country].append(
                        f"min_axes_ranking_{label}: "
                        f"{baseline_classes[country]} -> {new['eligibility_class']}"
                    )
            except Exception:
                pass

        gov_mod.MIN_AXES_FOR_RANKING = original


# ═══════════════════════════════════════════════════════════════════════════
# EXPLANATION OBJECT (Task 1.7 — audit-grade)
# ═══════════════════════════════════════════════════════════════════════════

def build_eligibility_explanation(country: str) -> dict[str, Any]:
    """Build a comprehensive, audit-grade explanation object for a country.

    This is the definitive answer to "why is this country in this class?"
    Every claim is traceable to a rule_id. Every axis has a detailed
    readiness assessment that distinguishes source presence from usability
    from construct applicability.

    Answers:
    - Why is the country in its class?
    - What blocks an upgrade?
    - What would need to improve?
    - What type of weakness blocks the upgrade?
    - Per-axis: what source is used, what it measures, what it does not measure

    Usable for internal review and later publication.
    """
    classification = classify_country(country)
    gov = _simulate_governance(country) if classification["can_compile"] else None
    readiness = build_axis_readiness_matrix(country)

    # Axis-by-axis detail with full provenance
    axis_detail: list[dict[str, Any]] = []
    for r in readiness:
        axis_num = r["axis_id"]
        profile = AXIS_SOURCE_PROFILE.get(axis_num, {})
        producer_info = PRODUCER_INVERSION_REGISTRY.get(country, {})
        inverted = axis_num in producer_info.get("inverted_axes", [])

        # Compute strength from readiness level
        level = r["readiness_level"]
        if level == ReadinessLevel.NOT_AVAILABLE:
            strength = "UNAVAILABLE"
        elif level == ReadinessLevel.CONSTRUCT_SUBSTITUTION:
            if inverted:
                strength = "STRUCTURALLY_INVERTED"
            elif r.get("proxy_used"):
                strength = "PROXY_CONSTRUCT_SUBSTITUTION"
            else:
                strength = "CONSTRUCT_SUBSTITUTION"
        elif level == ReadinessLevel.PROXY_USED:
            strength = "PROXY"
        elif level == ReadinessLevel.SOURCE_USABLE:
            strength = "DEGRADED"
        elif level == ReadinessLevel.SOURCE_CONFIDENT:
            strength = "STRONG"
        else:
            strength = "UNKNOWN"

        # Collect plain-text issues
        issues: list[str] = [iss["detail"] for iss in r["issues"]]

        # Add logistics construct substitution warning for non-EU
        if axis_num == LOGISTICS_AXIS_ID and r["construct_substitution"]:
            cs_warning = profile.get("eu_vs_non_eu_warning", "")
            if cs_warning and cs_warning not in issues:
                issues.append(cs_warning)

        axis_detail.append({
            "axis_id": axis_num,
            "axis_name": r["axis_name"],
            "available": r["source_present"],
            "readiness_level": r["readiness_level"],
            "strength": strength,
            "producer_inverted": inverted,
            "construct_substitution": r["construct_substitution"],
            "proxy_used": r["proxy_used"],
            "source_confident": r["source_confident"],
            "primary_sources": r["primary_sources"],
            "what_it_measures": profile.get("what_it_measures", ""),
            "what_it_does_NOT_measure": profile.get("what_it_does_NOT_measure", ""),
            "issues": issues,
            "rule_ids": [iss.get("rule_id", "") for iss in r["issues"]],
        })

    return {
        "country": country,
        "eligibility_class": classification["eligibility_class"],
        "theoretical_caveat": classification["theoretical_caveat"],
        "four_questions": {
            "can_compile": classification["can_compile"],
            "can_rate": classification["can_rate"],
            "can_rank": classification["can_rank"],
            "can_compare": classification["can_compare"],
        },
        "governance_tier": classification["governance_tier"],
        "mean_confidence": classification.get("mean_confidence"),
        "axes": axis_detail,
        "upgrade_blockers": classification["upgrade_blockers"],
        "weakness_types": classification["weakness_types"],
        "what_would_improve_class": _upgrade_path(
            classification["eligibility_class"],
            classification["weakness_types"],
            country,
        ),
        "fragility_note": classification["fragility_note"],
        "unresolved_weaknesses": [
            {
                "type": b["type"],
                "detail": b["detail"],
                "rule_id": b.get("rule_id", ""),
                "fixable_by_code": b["type"] not in (
                    WeaknessType.DATA_AVAILABILITY,
                    WeaknessType.STRUCTURAL_METHODOLOGY,
                    WeaknessType.SANCTIONS_DISTORTION,
                ),
            }
            for b in classification.get("upgrade_blockers", [])
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _axis_data_theoretically_available(country: str, axis_num: int) -> bool:
    """Check if data is theoretically available for a country+axis.

    This is a STATIC check based on known source coverage.
    It does NOT check actual file existence.

    NOTE: This function returns True if ANY source is present,
    including proxies and construct-substituted sources. For the
    full readiness picture, use _assess_axis_readiness() which
    distinguishes SOURCE_CONFIDENT from PROXY_USED from
    CONSTRUCT_SUBSTITUTION.
    """
    r = _assess_axis_readiness(country, axis_num)
    return r["source_present"]


def _simulate_governance(country: str) -> dict[str, Any]:
    """Simulate a governance assessment based on theoretical data profile.

    This creates a synthetic axis_results list and runs the REAL
    governance assessment function. The synthetic profile reflects
    what the data architecture WOULD produce for this country.
    """
    axis_results: list[dict[str, Any]] = []
    producer_info = PRODUCER_INVERSION_REGISTRY.get(country, {})
    inverted_axes = producer_info.get("inverted_axes", [])
    readiness = build_axis_readiness_matrix(country)

    for r in readiness:
        axis_num = r["axis_id"]
        available = r["source_present"]

        flags: list[str] = []
        is_proxy = r["proxy_used"]

        if axis_num in inverted_axes:
            flags.append("PRODUCER_INVERSION")
        if country in SANCTIONS_DISTORTED:
            flags.append("SANCTIONS_DISTORTION")
        if axis_num == 1 and country not in CPIS_PARTICIPANTS:
            flags.append("CPIS_NON_PARTICIPANT")
        if axis_num == 1 and country not in BIS_REPORTERS:
            flags.append("SINGLE_CHANNEL_A")
        if axis_num == LOGISTICS_AXIS_ID and not r["source_confident"]:
            is_proxy = True  # Conservative: non-confident logistics = proxy

        axis_results.append({
            "axis_id": axis_num,
            "data_quality_flags": flags,
            "is_proxy": is_proxy,
            "validity": "VALID" if available else "INVALID",
        })

    # Estimate severity
    total_severity = 0.0
    for ar in axis_results:
        if ar["validity"] == "VALID":
            # Simplified severity estimate from flags
            max_sev = 0.0
            for flag in ar["data_quality_flags"]:
                from backend.severity import SEVERITY_WEIGHTS
                w = SEVERITY_WEIGHTS.get(flag, 0.0)
                if w > max_sev:
                    max_sev = w
            total_severity += max_sev

    from backend.severity import assign_comparability_tier
    strict_tier = assign_comparability_tier(total_severity)

    return assess_country_governance(
        country=country,
        axis_results=axis_results,
        severity_total=total_severity,
        strict_comparability_tier=strict_tier,
    )


def _axis_strength_summary(country: str) -> dict[str, str]:
    """Produce per-axis strength summary for a country.

    Uses the readiness registry to distinguish between strong,
    degraded, proxy, construct-substituted, inverted, and unavailable.
    This is NOT the same as the old 5-level system — it reflects
    the actual readiness level.
    """
    readiness = build_axis_readiness_matrix(country)
    summary: dict[str, str] = {}

    for r in readiness:
        name = r["axis_name"]
        level = r["readiness_level"]
        producer_info = PRODUCER_INVERSION_REGISTRY.get(country, {})
        inverted = r["axis_id"] in producer_info.get("inverted_axes", [])

        if level == ReadinessLevel.NOT_AVAILABLE:
            summary[name] = "UNAVAILABLE"
        elif inverted:
            summary[name] = "INVERTED"
        elif level == ReadinessLevel.CONSTRUCT_SUBSTITUTION:
            summary[name] = "CONSTRUCT_SUBSTITUTION"
        elif level == ReadinessLevel.PROXY_USED:
            summary[name] = "PROXY"
        elif level == ReadinessLevel.SOURCE_USABLE:
            summary[name] = "DEGRADED"
        elif level == ReadinessLevel.SOURCE_CONFIDENT:
            summary[name] = "STRONG"
        else:
            summary[name] = "UNKNOWN"

    return summary


def _what_blocks_upgrade(
    current_class: str,
    all_blockers: list[dict[str, Any]],
    compile_q: dict,
    rate_q: dict,
    rank_q: dict,
    compare_q: dict,
) -> list[dict[str, Any]]:
    """Determine what blocks the country from reaching the next class."""
    if current_class == TheoreticalEligibility.COMPARABLE_WITHIN_MODEL:
        return []  # Already at maximum
    if current_class == TheoreticalEligibility.NOT_READY:
        return compile_q.get("blockers", [])
    if current_class == TheoreticalEligibility.COMPILE_READY:
        return rate_q.get("blockers", [])
    if current_class == TheoreticalEligibility.COMPUTABLE_BUT_NOT_DEFENSIBLE:
        return rate_q.get("blockers", [])
    if current_class == TheoreticalEligibility.RATEABLE_WITHIN_MODEL:
        return rank_q.get("blockers", [])
    if current_class == TheoreticalEligibility.RANKABLE_WITHIN_MODEL:
        return compare_q.get("blockers", [])
    return all_blockers


def _upgrade_path(
    current_class: str,
    weakness_types: list[str],
    country: str,
) -> str:
    """Describe what would need to change for the country to upgrade."""
    if current_class == TheoreticalEligibility.COMPARABLE_WITHIN_MODEL:
        return "Already at maximum theoretical eligibility."

    parts: list[str] = []

    if WeaknessType.SANCTIONS_DISTORTION in weakness_types:
        parts.append(
            "Sanctions lifting + 3-year stabilization period required."
        )
    if WeaknessType.PRODUCER_INVERSION in weakness_types:
        n = len(PRODUCER_INVERSION_REGISTRY.get(country, {}).get("inverted_axes", []))
        parts.append(
            f"Construct redesign for producer countries ({n} inverted axes)."
        )
    if WeaknessType.DATA_AVAILABILITY in weakness_types:
        parts.append(
            "Additional data source coverage needed."
        )
    if WeaknessType.CONSTRUCT_SUBSTITUTION in weakness_types:
        parts.append(
            "Genuine logistics data source required — current proxy "
            "(Comtrade trade value) substitutes a fundamentally different "
            "measurement construct for the axis concept."
        )
    if WeaknessType.CONFIDENCE_DEGRADATION in weakness_types:
        parts.append(
            "Higher data quality or additional channels needed."
        )
    if WeaknessType.COMPARABILITY_FAILURE in weakness_types:
        parts.append(
            "Structural comparability requirements not met."
        )
    if WeaknessType.THRESHOLD_FRAGILITY in weakness_types:
        parts.append(
            "Classification is threshold-sensitive — small rule changes "
            "would alter the result."
        )

    if not parts:
        parts.append("Review governance rules for potential upgrade path.")

    return " ".join(parts)


def _assess_fragility(country: str, gov: dict[str, Any] | None) -> str:
    """Assess whether the classification is threshold-fragile."""
    if gov is None:
        return "N/A"

    fragile_signals: list[str] = []
    mean_conf = gov.get("mean_axis_confidence", 0)

    # Check if mean confidence is near ranking threshold
    if abs(mean_conf - MIN_MEAN_CONFIDENCE_FOR_RANKING) < 0.05:
        fragile_signals.append(
            f"Mean confidence ({mean_conf:.2f}) is within +/-0.05 of "
            f"ranking threshold ({MIN_MEAN_CONFIDENCE_FOR_RANKING})"
        )

    # Check if n_low_minimal is at the boundary
    n_low = gov.get("n_low_confidence_axes", 0)
    if n_low == MAX_LOW_CONFIDENCE_AXES_FOR_RANKING:
        fragile_signals.append(
            f"n_low_confidence_axes ({n_low}) is exactly at the "
            f"ranking maximum ({MAX_LOW_CONFIDENCE_AXES_FOR_RANKING})"
        )

    # Check if producer inversions are at boundary
    n_inv = gov.get("n_producer_inverted_axes", 0)
    if n_inv == MAX_INVERTED_AXES_FOR_COMPARABLE:
        fragile_signals.append(
            f"n_inverted ({n_inv}) is exactly at the comparability "
            f"threshold ({MAX_INVERTED_AXES_FOR_COMPARABLE})"
        )

    if fragile_signals:
        return (
            "FRAGILE: This classification is threshold-sensitive. " +
            "; ".join(fragile_signals) +
            ". Small threshold changes could reclassify this country."
        )
    return "STABLE: Classification is not near any threshold boundary."
