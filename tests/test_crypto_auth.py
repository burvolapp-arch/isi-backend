"""
tests.test_crypto_auth — Cryptographic authenticity, immutability, reproducibility, adversarial tests.

Phase 1: Ed25519 signature verification
Phase 2: Immutable runtime contract
Phase 3: Reproducible build guarantee
Phase 4: Adversarial hardening (float safety, Unicode, timing, path length)
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import math
import os
import shutil
import stat
import time
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.hardening import (
    MAX_PATH_COMPONENT_LENGTH,
    is_safe_float,
    normalize_text,
    timing_safe_compare,
    validate_json_floats,
    validate_path_length,
)
from backend.immutability import (
    check_directory_not_writable,
    check_snapshot_immutability,
)
from backend.signing import (
    SIGNATURE_ALGORITHM,
    SIGNATURE_FILENAME,
    generate_keypair,
    load_private_key,
    load_public_keys,
    sign_snapshot_hash,
    verify_signature,
)
from backend.snapshot_cache import SnapshotCache, _artifact_to_path
from backend.snapshot_integrity import (
    EXIT_OK,
    EXIT_SIGNATURE_INVALID,
    expected_files,
    validate_snapshot,
)
from backend.snapshot_resolver import SNAPSHOTS_ROOT, resolve_snapshot

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = SNAPSHOTS_ROOT / "v1.0" / "2024"


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    from backend.isi_api_v01 import app

    return TestClient(app)


@pytest.fixture(scope="module")
def snapshot_hash() -> str:
    """The committed snapshot hash."""
    with open(SNAPSHOT_DIR / "HASH_SUMMARY.json", encoding="utf-8") as fh:
        return json.load(fh)["snapshot_hash"]


@pytest.fixture()
def tmp_snapshot(tmp_path: Path) -> Path:
    """Copy the real snapshot for mutation testing. Makes all files writable."""
    target = tmp_path / "v1.0" / "2024"
    shutil.copytree(SNAPSHOT_DIR, target)
    for p in target.rglob("*"):
        p.chmod(p.stat().st_mode | stat.S_IWUSR)
    for p in [target, target / "country", target / "axis"]:
        if p.exists():
            p.chmod(p.stat().st_mode | stat.S_IWUSR)
    return target


@pytest.fixture()
def test_keypair() -> tuple[str, str]:
    """Generate a fresh keypair for testing. Returns (seed_b64, pub_b64)."""
    seed, pub = generate_keypair()
    return base64.b64encode(seed).decode(), base64.b64encode(pub).decode()


# ===========================================================================
# Phase 1 — Ed25519 Signature Verification
# ===========================================================================


class TestSigningInfra:
    """Core Ed25519 signing infrastructure tests."""

    def test_generate_keypair_sizes(self):
        """Keypair generation produces 32-byte seed and 32-byte public key."""
        seed, pub = generate_keypair()
        assert len(seed) == 32
        assert len(pub) == 32

    def test_deterministic_signature(self, snapshot_hash: str):
        """Ed25519 signatures are deterministic — same key + hash → same signature."""
        seed, _ = generate_keypair()
        key = load_private_key(base64.b64encode(seed).decode())

        sig1 = sign_snapshot_hash(snapshot_hash, key, "v1")
        sig2 = sign_snapshot_hash(snapshot_hash, key, "v1")
        assert sig1["signature"] == sig2["signature"]

    def test_sign_and_verify_roundtrip(self, tmp_snapshot: Path, snapshot_hash: str):
        """Sign a snapshot, write SIGNATURE.json, verify succeeds."""
        # Sign with the project key (known to match public_keys.json)
        env_key = os.environ.get("ISI_SIGNING_PRIVATE_KEY", "aBwm7fjm4kqwDYOo4XeGidw+e2KL6DiH77RlWaIuqYg=")
        key = load_private_key(env_key)
        sig_data = sign_snapshot_hash(snapshot_hash, key, "v1")

        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        content = json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        sig_path.write_text(content, encoding="utf-8")

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is True
        assert result["error"] is None
        assert result["public_key_id"] == "v1"

    def test_committed_snapshot_signature_valid(self):
        """The committed v1.0/2024 snapshot has a valid signature."""
        result = verify_signature(SNAPSHOT_DIR)
        assert result["valid"] is True, f"Signature invalid: {result['error']}"

    def test_wrong_key_fails(self, tmp_snapshot: Path, snapshot_hash: str):
        """Signature from a different key is rejected."""
        # Generate a different keypair
        seed, _ = generate_keypair()
        wrong_key = load_private_key(base64.b64encode(seed).decode())
        sig_data = sign_snapshot_hash(snapshot_hash, wrong_key, "v1")

        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        content = json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        sig_path.write_text(content, encoding="utf-8")

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "verification failed" in result["error"].lower()

    def test_modified_hash_after_signing_fails(self, tmp_snapshot: Path, snapshot_hash: str):
        """Modifying HASH_SUMMARY after signing invalidates the signature."""
        env_key = os.environ.get("ISI_SIGNING_PRIVATE_KEY", "aBwm7fjm4kqwDYOo4XeGidw+e2KL6DiH77RlWaIuqYg=")
        key = load_private_key(env_key)
        sig_data = sign_snapshot_hash(snapshot_hash, key, "v1")

        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        content = json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        sig_path.write_text(content, encoding="utf-8")

        # Tamper: modify snapshot_hash in HASH_SUMMARY.json
        hs_path = tmp_snapshot / "HASH_SUMMARY.json"
        with open(hs_path, encoding="utf-8") as fh:
            hs = json.load(fh)
        hs["snapshot_hash"] = "a" * 64  # Different hash
        hs_path.write_text(
            json.dumps(hs, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "does not match" in result["error"]

    def test_missing_signature_fails(self, tmp_snapshot: Path):
        """Missing SIGNATURE.json is detected."""
        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        if sig_path.exists():
            sig_path.unlink()

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_corrupted_signature_base64_fails(self, tmp_snapshot: Path, snapshot_hash: str):
        """Corrupted base64 in signature field is rejected."""
        sig_data = {
            "algorithm": "ed25519",
            "public_key_id": "v1",
            "signature": "not-valid-base64!!!",
            "signed_hash": snapshot_hash,
        }
        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        sig_path.write_text(
            json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False

    def test_unknown_key_id_fails(self, tmp_snapshot: Path, snapshot_hash: str):
        """Signature referencing an unknown key ID is rejected."""
        env_key = os.environ.get("ISI_SIGNING_PRIVATE_KEY", "aBwm7fjm4kqwDYOo4XeGidw+e2KL6DiH77RlWaIuqYg=")
        key = load_private_key(env_key)
        sig_data = sign_snapshot_hash(snapshot_hash, key, "v999")  # Unknown key ID

        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        sig_path.write_text(
            json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "Unknown public_key_id" in result["error"]

    def test_bad_algorithm_fails(self, tmp_snapshot: Path, snapshot_hash: str):
        """Signature with unsupported algorithm is rejected."""
        sig_data = {
            "algorithm": "rsa-4096",
            "public_key_id": "v1",
            "signature": base64.b64encode(b"\x00" * 64).decode(),
            "signed_hash": snapshot_hash,
        }
        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        sig_path.write_text(
            json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "Unsupported algorithm" in result["error"]

    def test_invalid_private_key_seed(self):
        """Invalid seed length raises ValueError."""
        with pytest.raises(ValueError, match="32 bytes"):
            load_private_key(base64.b64encode(b"\x00" * 16).decode())

    def test_invalid_base64_key(self):
        """Non-base64 private key raises ValueError."""
        with pytest.raises(ValueError, match="not valid base64"):
            load_private_key("not-valid-base64!!!")

    def test_sign_invalid_hash_length(self):
        """Signing with non-64-char hash raises ValueError."""
        seed, _ = generate_keypair()
        key = load_private_key(base64.b64encode(seed).decode())
        with pytest.raises(ValueError, match="64 hex characters"):
            sign_snapshot_hash("abc", key, "v1")

    def test_public_keys_loaded(self):
        """Public key registry loads successfully with at least one key."""
        keys = load_public_keys()
        assert len(keys) >= 1
        assert "v1" in keys


class TestSignatureInIntegrity:
    """Signature verification integrated into snapshot_integrity validation."""

    def test_integrity_includes_signature_check(self):
        """validate_snapshot includes signature_verification check."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        check_names = [c["check"] for c in report.checks]
        assert "signature_verification" in check_names

    def test_integrity_passes_with_valid_signature(self):
        """Full validation passes when signature is valid."""
        report = validate_snapshot(SNAPSHOT_DIR, "v1.0", 2024)
        assert report.valid
        assert report.exit_code == EXIT_OK

    def test_integrity_fails_with_missing_signature(self, tmp_snapshot: Path):
        """Validation fails when SIGNATURE.json is missing.

        NOTE: directory_structure fires first (EXIT_MISSING_FILES = 1) since
        SIGNATURE.json is in expected_files(). The signature_verification
        check also reports the failure independently.
        """
        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        if sig_path.exists():
            sig_path.unlink()

        report = validate_snapshot(tmp_snapshot, "v1.0", 2024)
        assert not report.valid
        # directory_structure detects the missing file first → exit code 1
        # signature_verification also fails independently
        sig_check = [c for c in report.checks if c["check"] == "signature_verification"]
        assert len(sig_check) == 1
        assert sig_check[0]["passed"] is False
        assert "not found" in sig_check[0]["detail"]

    def test_expected_files_includes_signature(self):
        """expected_files() includes SIGNATURE.json."""
        files = expected_files()
        assert "SIGNATURE.json" in files


class TestSignatureSchemaContract:
    """SIGNATURE.json schema tests."""

    def test_signature_file_exists(self):
        """SIGNATURE.json exists in committed snapshot."""
        assert (SNAPSHOT_DIR / SIGNATURE_FILENAME).is_file()

    def test_signature_file_schema(self):
        """SIGNATURE.json has all required fields."""
        with open(SNAPSHOT_DIR / SIGNATURE_FILENAME, encoding="utf-8") as fh:
            sig = json.load(fh)

        assert sig["algorithm"] == "ed25519"
        assert isinstance(sig["public_key_id"], str)
        assert isinstance(sig["signature"], str)
        assert isinstance(sig["signed_hash"], str)
        assert len(sig["signed_hash"]) == 64

    def test_signature_file_canonical_json(self):
        """SIGNATURE.json is in canonical JSON format."""
        with open(SNAPSHOT_DIR / SIGNATURE_FILENAME, encoding="utf-8") as fh:
            raw = fh.read()
        data = json.loads(raw)
        canonical = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        assert raw == canonical


# ===========================================================================
# Phase 2 — Immutable Runtime Contract
# ===========================================================================


class TestImmutability:
    """Snapshot immutability verification tests."""

    def test_committed_snapshot_immutable(self):
        """Committed v1.0/2024 snapshot has no writable files."""
        result = check_snapshot_immutability(SNAPSHOT_DIR)
        assert result["immutable"], f"Violations: {result['violations']}"

    def test_writable_file_detected(self, tmp_snapshot: Path):
        """Writable file is detected as an immutability violation."""
        # tmp_snapshot files are already writable from fixture
        result = check_snapshot_immutability(tmp_snapshot)
        assert not result["immutable"]
        assert len(result["violations"]) > 0

    def test_readonly_snapshot_passes(self, tmp_snapshot: Path):
        """Snapshot passes after making all files read-only."""
        # Make everything read-only
        for p in tmp_snapshot.rglob("*"):
            if p.is_file():
                p.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        for p in [tmp_snapshot] + list(tmp_snapshot.rglob("*")):
            if p.is_dir():
                p.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        result = check_snapshot_immutability(tmp_snapshot)
        assert result["immutable"]

    def test_nonexistent_directory(self, tmp_path: Path):
        """Non-existent directory returns immutable=False."""
        result = check_snapshot_immutability(tmp_path / "nonexistent")
        assert not result["immutable"]

    def test_check_directory_not_writable(self, tmp_path: Path):
        """Read-only directory detected by os.access check."""
        read_only = tmp_path / "readonly"
        read_only.mkdir()
        read_only.chmod(stat.S_IRUSR | stat.S_IXUSR)

        assert check_directory_not_writable(read_only) is True

        # Restore for cleanup
        read_only.chmod(stat.S_IRWXU)

    def test_writable_directory_detected(self, tmp_path: Path):
        """Writable directory returns False from check_directory_not_writable."""
        writable = tmp_path / "writable"
        writable.mkdir()
        writable.chmod(stat.S_IRWXU)

        assert check_directory_not_writable(writable) is False


class TestDockerfile:
    """Dockerfile hardening contract tests (static analysis)."""

    def test_dockerfile_exists(self):
        """Dockerfile exists at project root."""
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        assert dockerfile.is_file()

    def test_dockerfile_non_root_user(self):
        """Dockerfile switches to non-root user before CMD."""
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "USER isi" in content

    def test_dockerfile_chmod_snapshots(self):
        """Dockerfile sets read-only permissions on snapshots."""
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "chmod 0444" in content
        assert "chmod 0555" in content

    def test_dockerfile_python_311(self):
        """Dockerfile pins Python 3.11."""
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "python:3.11-slim" in content

    def test_dockerfile_no_cache(self):
        """Dockerfile uses --no-cache-dir for pip install."""
        dockerfile = Path(__file__).resolve().parent.parent / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        assert "--no-cache-dir" in content


# ===========================================================================
# Phase 3 — Reproducible Build
# ===========================================================================


class TestReproducibility:
    """Snapshot reproducibility guarantee."""

    def test_snapshot_hash_deterministic(self):
        """Snapshot hash is deterministic — recomputing from data yields same hash."""
        from backend.hashing import compute_country_hash, compute_snapshot_hash

        with open(SNAPSHOT_DIR / "HASH_SUMMARY.json", encoding="utf-8") as fh:
            hs = json.load(fh)

        committed_hash = hs["snapshot_hash"]
        committed_country_hashes = hs["country_hashes"]

        # Recompute snapshot hash from country hashes
        recomputed = compute_snapshot_hash(committed_country_hashes)
        assert recomputed == committed_hash

    def test_canonical_json_format(self):
        """All snapshot JSON files are in canonical sorted-key format."""
        failures = []
        for f in sorted(SNAPSHOT_DIR.rglob("*.json")):
            with open(f, encoding="utf-8") as fh:
                raw = fh.read()
            data = json.loads(raw)
            canonical = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            if raw != canonical:
                failures.append(f.relative_to(SNAPSHOT_DIR).as_posix())

        assert failures == [], f"Non-canonical files: {failures}"

    def test_manifest_hashes_match(self):
        """MANIFEST SHA-256 hashes match actual file bytes."""
        with open(SNAPSHOT_DIR / "MANIFEST.json", encoding="utf-8") as fh:
            manifest = json.load(fh)

        for entry in manifest["files"]:
            filepath = SNAPSHOT_DIR / entry["path"]
            actual = hashlib.sha256(filepath.read_bytes()).hexdigest()
            assert actual == entry["sha256"], f"Hash mismatch: {entry['path']}"


# ===========================================================================
# Phase 4 — Adversarial Hardening
# ===========================================================================


class TestFloatSafety:
    """JSON float edge case detection."""

    def test_nan_detected(self):
        assert not is_safe_float(float("nan"))

    def test_inf_detected(self):
        assert not is_safe_float(float("inf"))

    def test_neg_inf_detected(self):
        assert not is_safe_float(float("-inf"))

    def test_neg_zero_detected(self):
        assert not is_safe_float(-0.0)

    def test_positive_zero_safe(self):
        assert is_safe_float(0.0)

    def test_normal_float_safe(self):
        assert is_safe_float(0.5)
        assert is_safe_float(1.0)
        assert is_safe_float(0.12345678)

    def test_validate_json_floats_clean(self):
        """Clean JSON structure has no violations."""
        data = {"score": 0.5, "items": [0.1, 0.2], "nested": {"x": 1.0}}
        assert validate_json_floats(data) == []

    def test_validate_json_floats_nan(self):
        """NaN in nested structure is detected."""
        data = {"nested": {"bad": float("nan")}}
        violations = validate_json_floats(data)
        assert len(violations) == 1
        assert "nan" in violations[0].lower()

    def test_validate_json_floats_neg_zero(self):
        """Negative zero in list is detected."""
        data = {"values": [-0.0, 1.0]}
        violations = validate_json_floats(data)
        assert len(violations) == 1

    def test_snapshot_data_no_hazardous_floats(self):
        """Committed snapshot data contains no hazardous float values."""
        for f in sorted(SNAPSHOT_DIR.rglob("*.json")):
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            violations = validate_json_floats(data)
            assert violations == [], f"{f.name}: {violations}"


class TestUnicodeNormalization:
    """Unicode normalization for deterministic comparison."""

    def test_nfc_normalize_combining_characters(self):
        """Combining character sequences normalize to precomposed form."""
        # e + combining acute = é (precomposed)
        decomposed = "e\u0301"  # NFD
        precomposed = "\u00e9"  # NFC
        assert normalize_text(decomposed) == precomposed

    def test_already_nfc_unchanged(self):
        """NFC-normal text is unchanged."""
        text = "hello world"
        assert normalize_text(text) == text

    def test_methodology_version_nfc_safe(self):
        """Methodology version strings contain only ASCII — NFC is a no-op."""
        version = "v1.0"
        assert normalize_text(version) == version

    def test_country_codes_ascii_only(self):
        """All EU27 country codes are pure ASCII."""
        from backend.constants import EU27_SORTED

        for code in EU27_SORTED:
            assert code.isascii()
            assert normalize_text(code) == code


class TestTimingSafety:
    """Timing-safe comparison tests."""

    def test_equal_strings_match(self):
        assert timing_safe_compare("abc", "abc") is True

    def test_different_strings_no_match(self):
        assert timing_safe_compare("abc", "def") is False

    def test_empty_strings_match(self):
        assert timing_safe_compare("", "") is True

    def test_length_mismatch(self):
        assert timing_safe_compare("short", "longer_string") is False

    def test_hash_comparison(self):
        """SHA-256 hex digests compared timing-safely."""
        h1 = hashlib.sha256(b"test").hexdigest()
        h2 = hashlib.sha256(b"test").hexdigest()
        h3 = hashlib.sha256(b"other").hexdigest()
        assert timing_safe_compare(h1, h2) is True
        assert timing_safe_compare(h1, h3) is False


class TestPathLengthValidation:
    """Overlong path component detection."""

    def test_normal_length_valid(self):
        assert validate_path_length("v1.0") is True
        assert validate_path_length("SE") is True
        assert validate_path_length("isi.json") is True

    def test_max_length_valid(self):
        assert validate_path_length("a" * MAX_PATH_COMPONENT_LENGTH) is True

    def test_overlong_rejected(self):
        assert validate_path_length("a" * (MAX_PATH_COMPONENT_LENGTH + 1)) is False

    def test_empty_rejected(self):
        assert validate_path_length("") is False

    def test_artifact_key_length_cap(self):
        """Cache rejects artifact keys longer than 64 characters."""
        cache = SnapshotCache(max_snapshots=1)
        long_key = "country:" + "A" * 60  # > 64 total
        with pytest.raises(ValueError, match="too long"):
            cache.get_artifact("v1.0", 2024, long_key, SNAPSHOT_DIR)


class TestArtifactKeySignature:
    """Artifact key 'signature' maps to SIGNATURE.json."""

    def test_signature_artifact_resolves(self):
        """'signature' artifact key resolves to SIGNATURE.json."""
        path = _artifact_to_path(SNAPSHOT_DIR, "signature")
        assert path.name == "SIGNATURE.json"

    def test_signature_artifact_loadable(self):
        """Cache can load SIGNATURE.json via 'signature' artifact key."""
        cache = SnapshotCache(max_snapshots=1)
        data = cache.get_artifact("v1.0", 2024, "signature", SNAPSHOT_DIR)
        assert data["algorithm"] == "ed25519"


class TestAdversarialInputs:
    """Adversarial input tests combining multiple attack vectors."""

    @pytest.mark.parametrize("bad_hash", [
        "",          # empty
        "xyz",       # non-hex
        "a" * 63,    # too short
        "a" * 65,    # too long
        "G" * 64,    # invalid hex chars
    ])
    def test_sign_rejects_bad_hash(self, bad_hash: str):
        """sign_snapshot_hash rejects malformed hash strings."""
        seed, _ = generate_keypair()
        key = load_private_key(base64.b64encode(seed).decode())
        with pytest.raises(ValueError):
            sign_snapshot_hash(bad_hash, key, "v1")

    def test_signature_json_missing_field(self, tmp_snapshot: Path, snapshot_hash: str):
        """SIGNATURE.json with missing field is rejected."""
        sig_data = {
            "algorithm": "ed25519",
            "public_key_id": "v1",
            # "signature" intentionally missing
            "signed_hash": snapshot_hash,
        }
        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        sig_path.write_text(
            json.dumps(sig_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "missing field" in result["error"]

    def test_signature_json_malformed(self, tmp_snapshot: Path):
        """Malformed SIGNATURE.json (invalid JSON) is rejected."""
        sig_path = tmp_snapshot / SIGNATURE_FILENAME
        sig_path.write_text("{not valid json", encoding="utf-8")

        result = verify_signature(tmp_snapshot)
        assert result["valid"] is False
        assert "unreadable" in result["error"]

    def test_exporter_rejects_negative_zero(self):
        """Exporter normalizes -0.0 to 0.0."""
        from backend.export_snapshot import parse_float

        result = parse_float("-0.0", "test")
        assert result == 0.0
        assert math.copysign(1.0, result) > 0  # Positive zero

    def test_all_snapshot_files_have_trailing_newline(self):
        """All snapshot JSON files end with exactly one newline."""
        for f in sorted(SNAPSHOT_DIR.rglob("*.json")):
            raw = f.read_bytes()
            assert raw.endswith(b"\n"), f"{f.name} missing trailing newline"
            assert not raw.endswith(b"\n\n"), f"{f.name} has double trailing newline"

    def test_no_bom_in_snapshot_files(self):
        """No snapshot JSON file starts with a BOM."""
        bom = b"\xef\xbb\xbf"
        for f in sorted(SNAPSHOT_DIR.rglob("*.json")):
            raw = f.read_bytes()
            assert not raw.startswith(bom), f"{f.name} has UTF-8 BOM"
