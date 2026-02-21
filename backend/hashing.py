"""
backend.hashing — Deterministic computation hashing for ISI snapshots.

Provides canonical float formatting, per-country computation hashes,
and snapshot-level hashes. All hash inputs are human-readable text,
inspectable for debugging.

Design contract:
    - canonical_float() produces identical output across CPython 3.10–3.14.
    - compute_country_hash() is deterministic for identical inputs.
    - compute_snapshot_hash() is deterministic for identical country hashes.
    - Hash inputs include EVERY value that affects the computation.
    - No hidden parameters. No implicit state.
"""

from __future__ import annotations

import hashlib

from backend.constants import ROUND_PRECISION


def canonical_float(value: float) -> str:
    """Convert a rounded float to its canonical string representation for hashing.

    Uses fixed-point notation with exactly ROUND_PRECISION decimal places.
    No scientific notation. No trailing zeros removal. No locale sensitivity.

    Examples (ROUND_PRECISION=8):
        canonical_float(0.5)        → "0.50000000"
        canonical_float(0.11646504) → "0.11646504"
        canonical_float(1.0)        → "1.00000000"
        canonical_float(0.0)        → "0.00000000"

    Invariant: canonical_float(round(x, ROUND_PRECISION)) produces identical
    output on CPython 3.10–3.14. This is guaranteed because IEEE 754
    double-precision can exactly represent all values with ≤8 significant
    decimal digits after rounding, and Python's f-string formatting uses
    the same dtoa implementation across versions.
    """
    return f"{value:.{ROUND_PRECISION}f}"


def compute_country_hash(
    country_code: str,
    year: int,
    methodology_version: str,
    axis_scores: dict[str, float],
    composite: float,
    data_window: str,
    methodology_params: dict,
) -> str:
    """Compute SHA-256 hash of a country's snapshot computation.

    All float values MUST already be rounded to ROUND_PRECISION before calling.

    Args:
        country_code: 2-letter ISO code (e.g., "SE").
        year: Reference year (e.g., 2024).
        methodology_version: Registry version (e.g., "v1.0").
        axis_scores: {axis_slug: rounded_score} — alphabetical slug keys.
        composite: Rounded composite score.
        data_window: Data reference window string (e.g., "2022–2024").
        methodology_params: Full methodology entry from registry.

    Returns:
        SHA-256 hex digest (64 characters).

    Properties:
        - Canonical order: all keys sorted alphabetically.
        - Text-based: hash input is human-readable, inspectable for debugging.
        - Newline-terminated: every field on its own line, final newline included.
        - Encoding: UTF-8, explicitly specified.
    """
    axis_slugs = sorted(axis_scores.keys())

    parts = [
        f"country={country_code}",
        f"year={year}",
        f"methodology={methodology_version}",
        f"data_window={data_window}",
    ]

    for slug in axis_slugs:
        parts.append(f"axis.{slug}={canonical_float(axis_scores[slug])}")

    parts.append(f"composite={canonical_float(composite)}")
    parts.append(f"aggregation_rule={methodology_params['aggregation_rule']}")

    # Weights in canonical order
    weights = methodology_params["axis_weights"]
    for slug in axis_slugs:
        parts.append(f"weight.{slug}={canonical_float(weights[slug])}")

    # Thresholds as canonical string (descending order)
    thresholds = methodology_params["classification_thresholds"]
    for threshold_entry in sorted(thresholds, key=lambda t: -t[0]):
        parts.append(f"threshold={canonical_float(threshold_entry[0])}:{threshold_entry[1]}")

    parts.append(f"default_classification={methodology_params['default_classification']}")

    hash_input = "\n".join(parts) + "\n"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def compute_snapshot_hash(country_hashes: dict[str, str]) -> str:
    """Compute the snapshot-level hash from all per-country hashes.

    Args:
        country_hashes: {country_code: hex_hash}

    Returns:
        SHA-256 hex digest of all country hashes concatenated in
        alphabetical country order.
    """
    if not country_hashes:
        raise ValueError("country_hashes is empty")

    parts = []
    for code in sorted(country_hashes.keys()):
        parts.append(f"{code}={country_hashes[code]}")

    hash_input = "\n".join(parts) + "\n"
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
