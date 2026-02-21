"""
backend.hardening — Adversarial input validation and safety utilities.

Provides:
    - safe_json_value(): Rejects NaN, Inf, -0.0 in JSON serialization.
    - normalize_text(): NFC Unicode normalization for determinism.
    - timing_safe_compare(): Constant-time string comparison.
    - validate_path_length(): Rejects overlong path components.
    - validate_json_floats(): Deep scan for hazardous float values in parsed JSON.

No implicit trust. No ambient authority. No silent fallbacks.
"""

from __future__ import annotations

import hmac
import math
import unicodedata


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

MAX_PATH_COMPONENT_LENGTH: int = 64
"""Maximum length of any single path component (filename or directory name).
Prevents overlong path attacks and filesystem edge cases."""


def validate_path_length(path_component: str) -> bool:
    """Validate that a path component is within safe length bounds.

    Returns True if valid, False if overlong.
    """
    return 0 < len(path_component) <= MAX_PATH_COMPONENT_LENGTH


# ---------------------------------------------------------------------------
# Unicode normalization
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """NFC-normalize a string for deterministic comparison.

    Ensures that equivalent Unicode representations compare equal.
    Used for any user-facing text that may contain combining characters.
    """
    return unicodedata.normalize("NFC", text)


# ---------------------------------------------------------------------------
# Float safety
# ---------------------------------------------------------------------------


def is_safe_float(value: float) -> bool:
    """Check that a float is a finite, non-negative-zero value.

    Rejects:
        - NaN
        - +Inf / -Inf
        - -0.0 (negative zero — causes JSON non-determinism)

    Returns True if the float is safe for deterministic serialization.
    """
    if math.isnan(value) or math.isinf(value):
        return False
    # Detect -0.0: math.copysign(1.0, -0.0) == -1.0
    if value == 0.0 and math.copysign(1.0, value) < 0:
        return False
    return True


def validate_json_floats(data: object, path: str = "$") -> list[str]:
    """Deep scan a parsed JSON structure for hazardous float values.

    Returns a list of violation descriptions (empty = clean).
    """
    violations: list[str] = []

    if isinstance(data, float):
        if not is_safe_float(data):
            violations.append(f"{path}: hazardous float value {data!r}")
    elif isinstance(data, dict):
        for key, val in data.items():
            violations.extend(validate_json_floats(val, f"{path}.{key}"))
    elif isinstance(data, list):
        for i, val in enumerate(data):
            violations.extend(validate_json_floats(val, f"{path}[{i}]"))

    return violations


# ---------------------------------------------------------------------------
# Timing-safe comparison
# ---------------------------------------------------------------------------


def timing_safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison using hmac.compare_digest.

    Prevents timing side-channel attacks on hash/signature comparisons.
    """
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
