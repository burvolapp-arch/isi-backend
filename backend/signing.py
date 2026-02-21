"""
backend.signing — Ed25519 cryptographic signing and verification for ISI snapshots.

Signing model:
    - The signed payload is the SHA-256 snapshot hash from HASH_SUMMARY.json.
    - Ed25519 signs the raw hash bytes (32 bytes from hex decode).
    - SIGNATURE.json stores: algorithm, public_key_id, signature (base64), signed_hash.
    - Private key is loaded from ISI_SIGNING_PRIVATE_KEY env var (base64-encoded raw seed).
    - Public keys are stored in backend/config/public_keys.json, versioned.

Security properties:
    - Deterministic: Ed25519 signatures are deterministic (no nonce).
    - Compact: 64-byte signature, 32-byte public key.
    - Timing-safe: verification uses hmac.compare_digest for hash comparison.
    - No fallback: missing or invalid signature is a hard error in STRICT mode.

No custom crypto. Uses the ``cryptography`` library exclusively.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(__file__).resolve().parent / "config"
PUBLIC_KEYS_PATH = CONFIG_DIR / "public_keys.json"

# ---------------------------------------------------------------------------
# Signature file schema
# ---------------------------------------------------------------------------

SIGNATURE_FILENAME = "SIGNATURE.json"
SIGNATURE_ALGORITHM = "ed25519"

# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate a new Ed25519 keypair.

    Returns:
        (private_key_seed, public_key_bytes) — both raw 32-byte values.

    The private_key_seed should be base64-encoded and stored as
    ISI_SIGNING_PRIVATE_KEY environment variable.
    The public_key_bytes should be base64-encoded and added to
    backend/config/public_keys.json.
    """
    private_key = Ed25519PrivateKey.generate()
    seed = private_key.private_bytes(
        encoding=Encoding.Raw,
        format=PrivateFormat.Raw,
        encryption_algorithm=NoEncryption(),
    )
    pub = private_key.public_key().public_bytes(
        encoding=Encoding.Raw,
        format=PublicFormat.Raw,
    )
    return seed, pub


def load_private_key(env_value: str) -> Ed25519PrivateKey:
    """Load an Ed25519 private key from a base64-encoded seed.

    Args:
        env_value: Base64-encoded 32-byte seed (from ISI_SIGNING_PRIVATE_KEY).

    Returns:
        Ed25519PrivateKey object.

    Raises:
        ValueError: if the seed is not exactly 32 bytes after decoding.
    """
    try:
        seed = base64.b64decode(env_value, validate=True)
    except Exception as exc:
        raise ValueError(f"ISI_SIGNING_PRIVATE_KEY is not valid base64: {type(exc).__name__}") from exc

    if len(seed) != 32:
        raise ValueError(
            f"ISI_SIGNING_PRIVATE_KEY seed must be exactly 32 bytes, got {len(seed)}"
        )

    return Ed25519PrivateKey.from_private_bytes(seed)


def load_public_keys() -> dict[str, Ed25519PublicKey]:
    """Load all public keys from backend/config/public_keys.json.

    Returns:
        Dict mapping key_id (e.g. "v1") to Ed25519PublicKey objects.

    Raises:
        FileNotFoundError: if public_keys.json is missing.
        ValueError: if any key entry is malformed.
    """
    if not PUBLIC_KEYS_PATH.is_file():
        raise FileNotFoundError(
            f"Public key registry not found: {PUBLIC_KEYS_PATH}"
        )

    with open(PUBLIC_KEYS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)

    keys: dict[str, Ed25519PublicKey] = {}
    for entry in data.get("keys", []):
        key_id = entry.get("key_id")
        algorithm = entry.get("algorithm")
        pub_b64 = entry.get("public_key")

        if algorithm != SIGNATURE_ALGORITHM:
            raise ValueError(
                f"Unsupported algorithm '{algorithm}' for key '{key_id}'"
            )

        try:
            pub_bytes = base64.b64decode(pub_b64, validate=True)
        except Exception as exc:
            raise ValueError(
                f"Invalid base64 for key '{key_id}': {type(exc).__name__}"
            ) from exc

        if len(pub_bytes) != 32:
            raise ValueError(
                f"Public key '{key_id}' must be 32 bytes, got {len(pub_bytes)}"
            )

        keys[key_id] = Ed25519PublicKey.from_public_bytes(pub_bytes)

    if not keys:
        raise ValueError("No keys found in public_keys.json")

    return keys


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def sign_snapshot_hash(
    snapshot_hash: str,
    private_key: Ed25519PrivateKey,
    public_key_id: str = "v1",
) -> dict[str, str]:
    """Sign a snapshot hash and return a SIGNATURE.json-compatible dict.

    Args:
        snapshot_hash: The SHA-256 hex digest from HASH_SUMMARY.json.
        private_key: Ed25519 private key.
        public_key_id: Key version identifier (e.g., "v1").

    Returns:
        Dict with: algorithm, public_key_id, signature (base64), signed_hash.
    """
    # Validate hash format: must be exactly 64 hex characters
    if len(snapshot_hash) != 64:
        raise ValueError(f"snapshot_hash must be 64 hex characters, got {len(snapshot_hash)}")
    try:
        hash_bytes = bytes.fromhex(snapshot_hash)
    except ValueError as exc:
        raise ValueError(f"snapshot_hash is not valid hex: {exc}") from exc

    signature = private_key.sign(hash_bytes)

    return {
        "algorithm": SIGNATURE_ALGORITHM,
        "public_key_id": public_key_id,
        "signature": base64.b64encode(signature).decode("ascii"),
        "signed_hash": snapshot_hash,
    }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_signature(snapshot_dir: Path) -> dict[str, Any]:
    """Verify the Ed25519 signature of a snapshot.

    Checks:
        1. SIGNATURE.json exists and is well-formed.
        2. signed_hash matches the snapshot_hash in HASH_SUMMARY.json (timing-safe).
        3. The public key referenced by public_key_id is in the key registry.
        4. The Ed25519 signature is valid.

    Args:
        snapshot_dir: Path to the snapshot directory.

    Returns:
        Dict with:
            valid (bool): True if all checks pass.
            error (str | None): Description of failure, or None.
            public_key_id (str | None): Which key was used.
            signed_hash (str | None): The hash that was signed.
    """
    result: dict[str, Any] = {
        "valid": False,
        "error": None,
        "public_key_id": None,
        "signed_hash": None,
    }

    # 1. Load SIGNATURE.json
    sig_path = snapshot_dir / SIGNATURE_FILENAME
    if not sig_path.is_file():
        result["error"] = "SIGNATURE.json not found"
        return result

    try:
        with open(sig_path, encoding="utf-8") as fh:
            sig_data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        result["error"] = f"SIGNATURE.json unreadable: {type(exc).__name__}"
        return result

    # Validate schema
    for field in ("algorithm", "public_key_id", "signature", "signed_hash"):
        if field not in sig_data:
            result["error"] = f"SIGNATURE.json missing field: {field}"
            return result

    if sig_data["algorithm"] != SIGNATURE_ALGORITHM:
        result["error"] = f"Unsupported algorithm: {sig_data['algorithm']}"
        return result

    result["public_key_id"] = sig_data["public_key_id"]
    result["signed_hash"] = sig_data["signed_hash"]

    # 2. Load HASH_SUMMARY.json and compare hashes (timing-safe)
    hash_summary_path = snapshot_dir / "HASH_SUMMARY.json"
    if not hash_summary_path.is_file():
        result["error"] = "HASH_SUMMARY.json not found"
        return result

    try:
        with open(hash_summary_path, encoding="utf-8") as fh:
            hash_summary = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        result["error"] = f"HASH_SUMMARY.json unreadable: {type(exc).__name__}"
        return result

    stored_hash = hash_summary.get("snapshot_hash", "")
    signed_hash = sig_data["signed_hash"]

    # Timing-safe comparison — no early return on partial match
    if not hmac.compare_digest(stored_hash, signed_hash):
        result["error"] = (
            "signed_hash does not match HASH_SUMMARY.json snapshot_hash"
        )
        return result

    # 3. Load public key
    try:
        public_keys = load_public_keys()
    except (FileNotFoundError, ValueError) as exc:
        result["error"] = f"Public key registry error: {exc}"
        return result

    key_id = sig_data["public_key_id"]
    if key_id not in public_keys:
        result["error"] = f"Unknown public_key_id: {key_id}"
        return result

    public_key = public_keys[key_id]

    # 4. Verify Ed25519 signature
    try:
        sig_bytes = base64.b64decode(sig_data["signature"], validate=True)
    except Exception:
        result["error"] = "Invalid base64 in signature field"
        return result

    try:
        hash_bytes = bytes.fromhex(signed_hash)
    except ValueError:
        result["error"] = "signed_hash is not valid hex"
        return result

    try:
        public_key.verify(sig_bytes, hash_bytes)
    except Exception:
        result["error"] = "Ed25519 signature verification failed"
        return result

    result["valid"] = True
    return result
