"""
backend.external_authority_registry — External Authority Registry

SECTION 2 of Ultimate Pass: External Authority Integration.

Problem addressed:
    The system references external data sources (BIS, IMF, IEA, etc.)
    but has no formal registry of their epistemic authority, coverage
    scope, or override permissions. Without this, the system cannot
    systematically determine when an external source should override
    an internal computation.

Solution:
    A formal registry of external authorities with:
    - AuthorityTier: classification of epistemic weight
    - Coverage scope: which ISI axes each authority is relevant to
    - Override permissions: what each authority can override
    - Conflict resolution rules: what happens when authorities disagree

Design contract:
    - Every external data source has an explicit authority entry.
    - Higher-tier authorities override lower-tier authorities.
    - No internal computation may override a Tier 1 authority.
    - Missing authority data is NEVER silently ignored.
    - Authority conflicts produce explicit conflict records.

Honesty note:
    External authority does not mean "always correct." It means
    "more defensible than internal computation." When BIS reports
    banking concentration that contradicts ISI's calculation, the
    BIS figure is epistemically superior because BIS has primary
    access to the underlying data.
"""

from __future__ import annotations

from typing import Any

from backend.epistemic_hierarchy import EpistemicLevel


# ═══════════════════════════════════════════════════════════════════════════
# AUTHORITY TIER — classification of external source authority
# ═══════════════════════════════════════════════════════════════════════════

class AuthorityTier:
    """Classification of external authority epistemic weight.

    Tier 1: Primary data custodian — has direct access to underlying
            data that ISI derives from. Override is mandatory.
    Tier 2: Authoritative secondary — recognized international body
            with strong empirical basis. Override is recommended.
    Tier 3: Supporting reference — useful for validation but not
            authoritative enough to override. Flag only.
    """
    TIER_1_PRIMARY = "TIER_1_PRIMARY"
    TIER_2_AUTHORITATIVE = "TIER_2_AUTHORITATIVE"
    TIER_3_SUPPORTING = "TIER_3_SUPPORTING"


VALID_AUTHORITY_TIERS = frozenset({
    AuthorityTier.TIER_1_PRIMARY,
    AuthorityTier.TIER_2_AUTHORITATIVE,
    AuthorityTier.TIER_3_SUPPORTING,
})

# Tier ordering — lower index = higher authority
AUTHORITY_TIER_ORDER: dict[str, int] = {
    AuthorityTier.TIER_1_PRIMARY: 0,
    AuthorityTier.TIER_2_AUTHORITATIVE: 1,
    AuthorityTier.TIER_3_SUPPORTING: 2,
}

AUTHORITY_TIER_DESCRIPTIONS: dict[str, str] = {
    AuthorityTier.TIER_1_PRIMARY: (
        "Primary data custodian with direct access to underlying data. "
        "Override of ISI computation is MANDATORY when conflict detected."
    ),
    AuthorityTier.TIER_2_AUTHORITATIVE: (
        "Authoritative secondary source from recognized international body. "
        "Override is RECOMMENDED when conflict detected."
    ),
    AuthorityTier.TIER_3_SUPPORTING: (
        "Supporting reference useful for validation. "
        "Not authoritative enough to override — FLAG only."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# OVERRIDE PERMISSION — what an authority can override
# ═══════════════════════════════════════════════════════════════════════════

class OverridePermission:
    """What an external authority is permitted to override."""
    RANKING = "RANKING"                     # Can override ranking eligibility
    COMPARABILITY = "COMPARABILITY"         # Can override comparability tier
    AXIS_SCORE = "AXIS_SCORE"               # Can override an axis score
    COMPOSITE = "COMPOSITE"                 # Can suppress composite
    GOVERNANCE_TIER = "GOVERNANCE_TIER"      # Can override governance tier
    USABILITY = "USABILITY"                 # Can override usability class
    CLASSIFICATION = "CLASSIFICATION"       # Can override classification label


VALID_OVERRIDE_PERMISSIONS = frozenset({
    OverridePermission.RANKING,
    OverridePermission.COMPARABILITY,
    OverridePermission.AXIS_SCORE,
    OverridePermission.COMPOSITE,
    OverridePermission.GOVERNANCE_TIER,
    OverridePermission.USABILITY,
    OverridePermission.CLASSIFICATION,
})


# ═══════════════════════════════════════════════════════════════════════════
# AUTHORITY REGISTRY — formal record of external authorities
# ═══════════════════════════════════════════════════════════════════════════

def _authority_entry(
    *,
    authority_id: str,
    name: str,
    organization: str,
    tier: str,
    relevant_axes: list[int],
    override_permissions: list[str],
    epistemic_level: str,
    data_description: str,
    coverage_scope: str,
    why_authoritative: str,
    conflict_resolution: str,
    url: str = "",
) -> dict[str, Any]:
    """Create a validated authority entry."""
    assert tier in VALID_AUTHORITY_TIERS, (
        f"Invalid tier '{tier}' for authority {authority_id}"
    )
    assert epistemic_level in {
        EpistemicLevel.EXTERNAL_AUTHORITY,
        EpistemicLevel.STRUCTURAL_BENCHMARK,
    }, f"Authority {authority_id} must be EXTERNAL_AUTHORITY or STRUCTURAL_BENCHMARK"
    for ax in relevant_axes:
        assert 1 <= ax <= 6, f"Invalid axis {ax} for authority {authority_id}"
    for perm in override_permissions:
        assert perm in VALID_OVERRIDE_PERMISSIONS, (
            f"Invalid permission '{perm}' for authority {authority_id}"
        )

    return {
        "authority_id": authority_id,
        "name": name,
        "organization": organization,
        "tier": tier,
        "relevant_axes": relevant_axes,
        "override_permissions": override_permissions,
        "epistemic_level": epistemic_level,
        "data_description": data_description,
        "coverage_scope": coverage_scope,
        "why_authoritative": why_authoritative,
        "conflict_resolution": conflict_resolution,
        "url": url,
    }


# ── Tier 1: Primary Data Custodians ──

AUTHORITY_BIS = _authority_entry(
    authority_id="AUTH_BIS",
    name="Bank for International Settlements",
    organization="BIS",
    tier=AuthorityTier.TIER_1_PRIMARY,
    relevant_axes=[1],
    override_permissions=[
        OverridePermission.AXIS_SCORE,
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "Consolidated and Locational Banking Statistics — primary source "
        "for cross-border banking claims used in ISI Axis 1 (Financial)."
    ),
    coverage_scope="Global banking claims by reporting country",
    why_authoritative=(
        "BIS is the PRIMARY data custodian for cross-border banking statistics. "
        "ISI Axis 1 is derived from BIS LBS data. When BIS reports differ "
        "from ISI calculations, BIS has epistemic priority because they have "
        "direct access to reporting-bank submissions."
    ),
    conflict_resolution=(
        "If BIS concentration figures contradict ISI Axis 1 calculations, "
        "the BIS figure overrides. ISI computation error is the more likely "
        "explanation than BIS reporting error."
    ),
    url="https://www.bis.org/statistics/bankstats.htm",
)

AUTHORITY_IEA = _authority_entry(
    authority_id="AUTH_IEA",
    name="International Energy Agency",
    organization="IEA",
    tier=AuthorityTier.TIER_1_PRIMARY,
    relevant_axes=[2],
    override_permissions=[
        OverridePermission.AXIS_SCORE,
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "World Energy Balances and Energy Security indicators — primary source "
        "for energy trade dependency used in ISI Axis 2 (Energy)."
    ),
    coverage_scope="Global energy production, trade, consumption",
    why_authoritative=(
        "IEA collects energy data directly from member states. ISI Axis 2 "
        "energy dependency calculations should be consistent with IEA "
        "energy trade balances. IEA has primary access to national "
        "energy reporting."
    ),
    conflict_resolution=(
        "If IEA energy dependency indicators contradict ISI Axis 2, "
        "the IEA figure has priority. National energy reporting to IEA "
        "is more authoritative than ISI's derived computation."
    ),
    url="https://www.iea.org/data-and-statistics",
)

AUTHORITY_EUROSTAT = _authority_entry(
    authority_id="AUTH_EUROSTAT",
    name="Eurostat",
    organization="European Commission",
    tier=AuthorityTier.TIER_1_PRIMARY,
    relevant_axes=[1, 2, 3, 4, 5, 6],
    override_permissions=[
        OverridePermission.AXIS_SCORE,
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
        OverridePermission.GOVERNANCE_TIER,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "EU trade statistics (COMEXT), energy statistics, financial "
        "accounts — primary source for intra-EU and extra-EU trade data "
        "used across all ISI axes."
    ),
    coverage_scope="EU-27 trade, energy, financial, logistics data",
    why_authoritative=(
        "Eurostat is the statistical office of the EU and the primary "
        "custodian of EU-27 trade data. ISI operates within the EU-27 "
        "scope. Eurostat data is the most authoritative source for any "
        "EU-specific trade flow used by ISI."
    ),
    conflict_resolution=(
        "Eurostat trade data overrides ISI calculations for any EU-27 "
        "trade flow. If Eurostat and ISI disagree on intra-EU trade "
        "concentration, Eurostat is definitionally correct."
    ),
    url="https://ec.europa.eu/eurostat",
)

# ── Tier 2: Authoritative Secondary Sources ──

AUTHORITY_IMF = _authority_entry(
    authority_id="AUTH_IMF",
    name="International Monetary Fund",
    organization="IMF",
    tier=AuthorityTier.TIER_2_AUTHORITATIVE,
    relevant_axes=[1],
    override_permissions=[
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "Direction of Trade Statistics (DOTS), Financial Soundness "
        "Indicators — secondary source for financial dependency assessment."
    ),
    coverage_scope="Global trade and financial indicators",
    why_authoritative=(
        "IMF DOTS provides bilateral trade data and financial stability "
        "assessments. While not the primary source for ISI Axis 1, IMF "
        "data provides authoritative secondary validation."
    ),
    conflict_resolution=(
        "IMF data flags but does not automatically override ISI. "
        "Persistent divergence between IMF and ISI triggers a "
        "comparability downgrade."
    ),
    url="https://data.imf.org/",
)

AUTHORITY_OECD = _authority_entry(
    authority_id="AUTH_OECD",
    name="Organisation for Economic Co-operation and Development",
    organization="OECD",
    tier=AuthorityTier.TIER_2_AUTHORITATIVE,
    relevant_axes=[1, 3, 5],
    override_permissions=[
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "Trade in Value Added (TiVA), STAN Industrial Analysis — "
        "secondary source for trade dependency and technology supply chains."
    ),
    coverage_scope="OECD member trade, technology, industrial data",
    why_authoritative=(
        "OECD TiVA provides value-added trade data that can validate "
        "ISI's gross-trade-based concentration measures. Divergence "
        "between OECD and ISI may indicate value-chain vs. gross-trade "
        "measurement differences."
    ),
    conflict_resolution=(
        "OECD data flags divergence but does not automatically override. "
        "Persistent divergence triggers comparability review."
    ),
    url="https://stats.oecd.org/",
)

AUTHORITY_SIPRI = _authority_entry(
    authority_id="AUTH_SIPRI",
    name="Stockholm International Peace Research Institute",
    organization="SIPRI",
    tier=AuthorityTier.TIER_2_AUTHORITATIVE,
    relevant_axes=[4],
    override_permissions=[
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
        OverridePermission.AXIS_SCORE,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "SIPRI Arms Transfers Database — primary reference for "
        "international arms trade flows used in ISI Axis 4 (Defense)."
    ),
    coverage_scope="Global arms transfers, military expenditure",
    why_authoritative=(
        "SIPRI is the recognized authority on international arms "
        "transfers. ISI Axis 4 measures defense supply concentration "
        "using trade data, but SIPRI has primary access to arms "
        "transfer records and expert assessment of military dependencies."
    ),
    conflict_resolution=(
        "SIPRI arms transfer data can override ISI Axis 4 if divergence "
        "indicates ISI is measuring commercial trade rather than actual "
        "defense supply dependency."
    ),
    url="https://www.sipri.org/databases/armstransfers",
)

AUTHORITY_USGS = _authority_entry(
    authority_id="AUTH_USGS",
    name="US Geological Survey",
    organization="USGS",
    tier=AuthorityTier.TIER_2_AUTHORITATIVE,
    relevant_axes=[5],
    override_permissions=[
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
        OverridePermission.AXIS_SCORE,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "Mineral Commodity Summaries — primary reference for critical "
        "mineral supply concentration used in ISI Axis 5 (Critical Inputs)."
    ),
    coverage_scope="Global mineral production, reserves, trade",
    why_authoritative=(
        "USGS is the recognized authority on global mineral production "
        "and supply concentration. ISI Axis 5 measures critical input "
        "dependency, and USGS data on production concentration is "
        "epistemically superior to ISI's trade-based inference."
    ),
    conflict_resolution=(
        "USGS mineral concentration data can override ISI Axis 5 "
        "if divergence indicates ISI's trade-based measure misses "
        "production-level concentration."
    ),
    url="https://www.usgs.gov/centers/national-minerals-information-center",
)

AUTHORITY_EU_CRM = _authority_entry(
    authority_id="AUTH_EU_CRM",
    name="EU Critical Raw Materials Act",
    organization="European Commission",
    tier=AuthorityTier.TIER_1_PRIMARY,
    relevant_axes=[5],
    override_permissions=[
        OverridePermission.AXIS_SCORE,
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
        OverridePermission.GOVERNANCE_TIER,
    ],
    epistemic_level=EpistemicLevel.STRUCTURAL_BENCHMARK,
    data_description=(
        "EU Critical Raw Materials list and supply risk assessments — "
        "structural benchmark for critical input dependency."
    ),
    coverage_scope="EU-27 critical raw material classifications",
    why_authoritative=(
        "The EU CRM Act is a structural benchmark — it defines WHICH "
        "materials are critical for EU strategic autonomy. ISI Axis 5 "
        "must be consistent with EU CRM classifications."
    ),
    conflict_resolution=(
        "EU CRM classifications are structural constraints. If ISI Axis 5 "
        "does not reflect materials classified as critical by the EU CRM Act, "
        "the ISI calculation is structurally incomplete."
    ),
    url="https://single-market-economy.ec.europa.eu/sectors/raw-materials/",
)

AUTHORITY_WORLD_BANK_LPI = _authority_entry(
    authority_id="AUTH_WB_LPI",
    name="World Bank Logistics Performance Index",
    organization="World Bank",
    tier=AuthorityTier.TIER_2_AUTHORITATIVE,
    relevant_axes=[6],
    override_permissions=[
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "Logistics Performance Index — secondary reference for "
        "logistics infrastructure and connectivity assessment."
    ),
    coverage_scope="Global logistics performance, 160+ countries",
    why_authoritative=(
        "World Bank LPI is the recognized benchmark for logistics "
        "performance. ISI Axis 6 measures logistics freight concentration, "
        "which is related but not identical. LPI provides structural "
        "validation of logistics dependency patterns."
    ),
    conflict_resolution=(
        "World Bank LPI flags divergence but does not automatically "
        "override. Persistent divergence triggers comparability review."
    ),
    url="https://lpi.worldbank.org/",
)

AUTHORITY_UNCTAD = _authority_entry(
    authority_id="AUTH_UNCTAD",
    name="UN Conference on Trade and Development",
    organization="UNCTAD",
    tier=AuthorityTier.TIER_2_AUTHORITATIVE,
    relevant_axes=[1, 2, 3, 5, 6],
    override_permissions=[
        OverridePermission.RANKING,
        OverridePermission.COMPARABILITY,
    ],
    epistemic_level=EpistemicLevel.EXTERNAL_AUTHORITY,
    data_description=(
        "UNCTAD trade statistics, commodity price indices, maritime "
        "transport statistics — secondary reference for trade dependency."
    ),
    coverage_scope="Global trade, investment, commodity data",
    why_authoritative=(
        "UNCTAD provides comprehensive global trade and commodity data. "
        "Useful as secondary validation for multiple ISI axes."
    ),
    conflict_resolution=(
        "UNCTAD data flags divergence but does not automatically override. "
        "Persistent divergence triggers comparability review."
    ),
    url="https://unctadstat.unctad.org/",
)


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRY — all authorities in a list
# ═══════════════════════════════════════════════════════════════════════════

EXTERNAL_AUTHORITY_REGISTRY: list[dict[str, Any]] = [
    AUTHORITY_BIS,
    AUTHORITY_IEA,
    AUTHORITY_EUROSTAT,
    AUTHORITY_IMF,
    AUTHORITY_OECD,
    AUTHORITY_SIPRI,
    AUTHORITY_USGS,
    AUTHORITY_EU_CRM,
    AUTHORITY_WORLD_BANK_LPI,
    AUTHORITY_UNCTAD,
]


def get_authority_by_id(authority_id: str) -> dict[str, Any] | None:
    """Look up an authority by ID."""
    for auth in EXTERNAL_AUTHORITY_REGISTRY:
        if auth["authority_id"] == authority_id:
            return auth
    return None


def get_authorities_for_axis(axis_id: int) -> list[dict[str, Any]]:
    """Get all authorities relevant to a specific ISI axis."""
    return [
        auth for auth in EXTERNAL_AUTHORITY_REGISTRY
        if axis_id in auth["relevant_axes"]
    ]


def get_tier_1_authorities() -> list[dict[str, Any]]:
    """Get all Tier 1 (primary data custodian) authorities."""
    return [
        auth for auth in EXTERNAL_AUTHORITY_REGISTRY
        if auth["tier"] == AuthorityTier.TIER_1_PRIMARY
    ]


def get_authorities_with_permission(
    permission: str,
) -> list[dict[str, Any]]:
    """Get all authorities that have a specific override permission."""
    return [
        auth for auth in EXTERNAL_AUTHORITY_REGISTRY
        if permission in auth["override_permissions"]
    ]


def authority_outranks(
    authority_a: dict[str, Any],
    authority_b: dict[str, Any],
) -> bool:
    """True if authority_a has strictly higher tier than authority_b."""
    tier_a = AUTHORITY_TIER_ORDER.get(authority_a["tier"], 999)
    tier_b = AUTHORITY_TIER_ORDER.get(authority_b["tier"], 999)
    return tier_a < tier_b


def get_registry_summary() -> dict[str, Any]:
    """Return a summary of the authority registry for export/docs."""
    tier_counts: dict[str, int] = {}
    for auth in EXTERNAL_AUTHORITY_REGISTRY:
        tier = auth["tier"]
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    return {
        "n_authorities": len(EXTERNAL_AUTHORITY_REGISTRY),
        "tier_counts": tier_counts,
        "tier_descriptions": dict(AUTHORITY_TIER_DESCRIPTIONS),
        "authorities": [
            {
                "authority_id": auth["authority_id"],
                "name": auth["name"],
                "organization": auth["organization"],
                "tier": auth["tier"],
                "relevant_axes": auth["relevant_axes"],
                "n_override_permissions": len(auth["override_permissions"]),
            }
            for auth in EXTERNAL_AUTHORITY_REGISTRY
        ],
    }
