#!/usr/bin/env python3
"""Tests for backend.scope — Scope abstraction module.

Validates all scope definitions, mappings, and public API functions
introduced for ISI v1.1 global expansion.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.scope import (
    EU27_CODES,
    PHASE1_EXPANSION_CODES,
    SCOPE_REGISTRY,
    EXPANSION_COUNTRY_NAMES,
    BIS_TO_CANONICAL_EXPANSION,
    CPIS_TO_CANONICAL_EXPANSION,
    CPIS_NON_PARTICIPANTS,
    SIPRI_TO_CANONICAL_EXPANSION,
    PRODUCER_INVERSION_FLAGS,
    get_scope,
    get_scope_sorted,
    get_country_name,
    validate_scope_coverage,
    validate_scope_minimum,
    is_producer_inverted,
    scope_id_for_methodology,
)


# ── EU-27 Codes ─────────────────────────────────────────────

class TestEU27Codes:
    def test_count(self):
        assert len(EU27_CODES) == 27

    def test_is_frozenset(self):
        assert isinstance(EU27_CODES, frozenset)

    def test_greece_is_el_in_backend(self):
        """Backend v01 still uses Eurostat's EL for Greece.
        The pipeline uses ISO-standard GR (see pipeline.config.EU27_ISO2).
        Backend migration to GR will happen in v02."""
        assert "EL" in EU27_CODES
        assert "GR" not in EU27_CODES

    def test_all_two_char(self):
        for code in EU27_CODES:
            assert len(code) == 2
            assert code.isalpha()
            assert code.isupper()

    def test_no_expansion_overlap(self):
        assert EU27_CODES & PHASE1_EXPANSION_CODES == frozenset()


# ── Phase 1 Expansion Codes ─────────────────────────────────

class TestPhase1Codes:
    def test_count(self):
        assert len(PHASE1_EXPANSION_CODES) == 7

    def test_is_frozenset(self):
        assert isinstance(PHASE1_EXPANSION_CODES, frozenset)

    def test_expected_countries(self):
        expected = {"AU", "CN", "GB", "JP", "KR", "NO", "US"}
        assert PHASE1_EXPANSION_CODES == expected

    def test_no_russia(self):
        assert "RU" not in PHASE1_EXPANSION_CODES

    def test_all_two_char(self):
        for code in PHASE1_EXPANSION_CODES:
            assert len(code) == 2


# ── Scope Registry ──────────────────────────────────────────

class TestScopeRegistry:
    def test_three_scopes(self):
        assert len(SCOPE_REGISTRY) == 3

    def test_eu27_scope(self):
        assert SCOPE_REGISTRY["EU-27"] == EU27_CODES

    def test_phase1_scope(self):
        assert SCOPE_REGISTRY["PHASE1-7"] == PHASE1_EXPANSION_CODES

    def test_global_scope(self):
        global_scope = SCOPE_REGISTRY["GLOBAL-34"]
        assert global_scope == EU27_CODES | PHASE1_EXPANSION_CODES
        assert len(global_scope) == 34

    def test_all_frozensets(self):
        for scope in SCOPE_REGISTRY.values():
            assert isinstance(scope, frozenset)


# ── Country Names ────────────────────────────────────────────

class TestCountryNames:
    def test_all_expansion_countries_named(self):
        for code in PHASE1_EXPANSION_CODES:
            assert code in EXPANSION_COUNTRY_NAMES

    def test_known_names(self):
        assert EXPANSION_COUNTRY_NAMES["US"] == "United States"
        assert EXPANSION_COUNTRY_NAMES["GB"] == "United Kingdom"
        assert EXPANSION_COUNTRY_NAMES["CN"] == "China"
        assert EXPANSION_COUNTRY_NAMES["JP"] == "Japan"
        assert EXPANSION_COUNTRY_NAMES["KR"] == "South Korea"
        assert EXPANSION_COUNTRY_NAMES["AU"] == "Australia"
        assert EXPANSION_COUNTRY_NAMES["NO"] == "Norway"


# ── BIS Mapping ──────────────────────────────────────────────

class TestBISMapping:
    def test_all_expansion_countries(self):
        mapped = set(BIS_TO_CANONICAL_EXPANSION.values())
        assert mapped == set(PHASE1_EXPANSION_CODES)

    def test_identity_mapping(self):
        # BIS uses standard ISO-2 for expansion countries
        for k, v in BIS_TO_CANONICAL_EXPANSION.items():
            assert k == v


# ── CPIS Mapping ─────────────────────────────────────────────

class TestCPISMapping:
    def test_all_expansion_countries(self):
        mapped = set(CPIS_TO_CANONICAL_EXPANSION.values())
        assert mapped == set(PHASE1_EXPANSION_CODES)

    def test_iso3_to_iso2(self):
        assert CPIS_TO_CANONICAL_EXPANSION["AUS"] == "AU"
        assert CPIS_TO_CANONICAL_EXPANSION["GBR"] == "GB"
        assert CPIS_TO_CANONICAL_EXPANSION["USA"] == "US"
        assert CPIS_TO_CANONICAL_EXPANSION["CHN"] == "CN"
        assert CPIS_TO_CANONICAL_EXPANSION["JPN"] == "JP"
        assert CPIS_TO_CANONICAL_EXPANSION["KOR"] == "KR"
        assert CPIS_TO_CANONICAL_EXPANSION["NOR"] == "NO"

    def test_all_keys_iso3(self):
        for key in CPIS_TO_CANONICAL_EXPANSION:
            assert len(key) == 3

    def test_cn_non_participant(self):
        assert "CN" in CPIS_NON_PARTICIPANTS


# ── SIPRI Mapping ────────────────────────────────────────────

class TestSIPRIMapping:
    def test_all_expansion_countries_reachable(self):
        mapped = set(SIPRI_TO_CANONICAL_EXPANSION.values())
        assert set(PHASE1_EXPANSION_CODES).issubset(mapped)

    def test_korea_variants(self):
        assert SIPRI_TO_CANONICAL_EXPANSION["South Korea"] == "KR"
        assert SIPRI_TO_CANONICAL_EXPANSION["Korea South"] == "KR"
        assert SIPRI_TO_CANONICAL_EXPANSION["Republic of Korea"] == "KR"


# ── Producer Inversion ───────────────────────────────────────

class TestProducerInversion:
    def test_axes_covered(self):
        assert 2 in PRODUCER_INVERSION_FLAGS
        assert 4 in PRODUCER_INVERSION_FLAGS
        assert 5 in PRODUCER_INVERSION_FLAGS

    def test_no_axis_1(self):
        assert 1 not in PRODUCER_INVERSION_FLAGS

    def test_us_defense(self):
        assert is_producer_inverted("US", 4)

    def test_cn_critical(self):
        assert is_producer_inverted("CN", 5)

    def test_de_defense_false(self):
        # DE is in v1.0 defense producers but we test expansion scope
        assert is_producer_inverted("DE", 4)

    def test_jp_defense_false(self):
        assert not is_producer_inverted("JP", 4)

    def test_no_energy(self):
        assert is_producer_inverted("NO", 2)

    def test_au_energy(self):
        assert is_producer_inverted("AU", 2)


# ── Public API ───────────────────────────────────────────────

class TestGetScope:
    def test_eu27(self):
        scope = get_scope("EU-27")
        assert len(scope) == 27

    def test_phase1(self):
        scope = get_scope("PHASE1-7")
        assert len(scope) == 7

    def test_global(self):
        scope = get_scope("GLOBAL-34")
        assert len(scope) == 34

    def test_unknown_raises(self):
        with pytest.raises(KeyError):
            get_scope("NONEXISTENT")


class TestGetScopeSorted:
    def test_sorted(self):
        result = get_scope_sorted("PHASE1-7")
        assert result == sorted(result)
        assert len(result) == 7

    def test_is_list(self):
        result = get_scope_sorted("EU-27")
        assert isinstance(result, list)


class TestGetCountryName:
    def test_expansion(self):
        assert get_country_name("US") == "United States"

    def test_expansion_all(self):
        for code in PHASE1_EXPANSION_CODES:
            name = get_country_name(code)
            assert isinstance(name, str)
            assert len(name) > 1


class TestValidateScopeCoverage:
    def test_exact_match(self):
        validate_scope_coverage(PHASE1_EXPANSION_CODES, "PHASE1-7", "test")

    def test_missing_raises(self):
        incomplete = PHASE1_EXPANSION_CODES - {"US"}
        with pytest.raises(ValueError, match="Missing"):
            validate_scope_coverage(incomplete, "PHASE1-7", "test")

    def test_extra_raises(self):
        extra = PHASE1_EXPANSION_CODES | {"RU"}
        with pytest.raises(ValueError, match="Unexpected"):
            validate_scope_coverage(extra, "PHASE1-7", "test")


class TestValidateScopeMinimum:
    def test_subset(self):
        subset = {"US", "GB", "JP"}
        missing = validate_scope_minimum(subset, "PHASE1-7", "test")
        assert "AU" in missing
        assert "US" not in missing

    def test_outside_scope_raises(self):
        with pytest.raises(ValueError, match="Scope violation"):
            validate_scope_minimum({"US", "RU"}, "PHASE1-7", "test")


class TestScopeIdForMethodology:
    def test_v10(self):
        assert scope_id_for_methodology("v1.0") == "EU-27"

    def test_v11(self):
        assert scope_id_for_methodology("v1.1") == "PHASE1-7"

    def test_unknown(self):
        with pytest.raises(KeyError):
            scope_id_for_methodology("v2.0")
