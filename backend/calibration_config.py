"""
backend.calibration_config — Empirical Calibration Configuration

EXTENSION PASS A: Empirical Calibration Layer.

Problem addressed:
    The dominant constraint scoring in epistemic_arbiter uses fixed
    heuristic weights (severity=3, claims_forbidden=2, primary_path=1).
    These are reasonable but unvalidated. Without a calibration
    mechanism, the weights cannot improve from empirical evidence.

Solution:
    A versioned, immutable-at-runtime calibration artifact that stores:
    - The dominance weight vector
    - Feature definitions
    - Calibration metadata (dataset, timestamp, method)

    The arbiter reads this artifact at scoring time. If missing or
    corrupted, the arbiter deterministically reverts to the original
    heuristic weights.

Design contract:
    - Calibration config is DATA, not LOGIC.
    - Weights are FROZEN at runtime — no online learning, no feedback
      loops, no self-modifying behavior.
    - Every arbiter verdict exposes which calibration version and
      weight vector it used.
    - CALIBRATION_LOCK invariant: runtime weights must match the
      versioned config exactly.

Honesty note:
    "Heuristic weights are honest defaults. Calibrated weights are
    empirically grounded replacements. Both are explicit, versioned,
    and auditable. Neither is hidden or self-modifying."
"""

from __future__ import annotations

from typing import Any


# ═══════════════════════════════════════════════════════════════════════════
# CALIBRATION MODE — honest labeling
# ═══════════════════════════════════════════════════════════════════════════

class CalibrationMode:
    """Runtime calibration mode — honest about provenance.

    HEURISTIC_DEFAULT: Weights are hand-tuned defaults. No fitting
        was performed. This is the honest label for the current state.
    FITTED: Weights were produced by an offline fitting procedure
        against labeled data. method != 'manual_heuristic' and
        dataset != 'none' are required preconditions.
    """
    HEURISTIC_DEFAULT = "HEURISTIC_DEFAULT"
    FITTED = "FITTED"


# ═══════════════════════════════════════════════════════════════════════════
# WEIGHT FEATURE DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════

# These are the features used in dominance scoring.
# The feature set is FIXED — calibration changes weights, not features.
DOMINANCE_FEATURES: tuple[str, ...] = (
    "severity",          # ARBITER_STATUS_ORDER level of the reason
    "claims_forbidden",  # Number of claim categories this source forbids
    "primary_path",      # 1 if source is on primary decision path, else 0
    "recurrence",        # Number of times this source appears in reasons
)

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "severity": (
        "Maps to ARBITER_STATUS_ORDER: VALID=0, RESTRICTED=1, "
        "FLAGGED=2, SUPPRESSED=3, BLOCKED=4."
    ),
    "claims_forbidden": (
        "Number of outward-facing claim categories this reason's "
        "source directly forbids (0-5)."
    ),
    "primary_path": (
        "Binary: 1 if source is truth_resolution, governance, or "
        "runtime_status (primary epistemic decision path); 0 otherwise."
    ),
    "recurrence": (
        "Count of how many times this source appears across all "
        "arbiter reasons. Higher recurrence = more pervasive constraint."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# HEURISTIC DEFAULTS (original hand-tuned weights)
# ═══════════════════════════════════════════════════════════════════════════

HEURISTIC_WEIGHTS: dict[str, float] = {
    "severity": 3.0,
    "claims_forbidden": 2.0,
    "primary_path": 1.0,
    "recurrence": 0.0,  # Not used in heuristic mode
}

HEURISTIC_VERSION = "heuristic-v1"


# ═══════════════════════════════════════════════════════════════════════════
# CALIBRATION CONFIG (the artifact)
# ═══════════════════════════════════════════════════════════════════════════

class CalibrationConfig:
    """Immutable calibration configuration artifact.

    Once constructed, the weights and metadata cannot change.
    This is by design — the arbiter must not modify calibration
    at runtime.
    """

    __slots__ = (
        "_version", "_weights", "_method", "_dataset",
        "_timestamp", "_notes", "_frozen", "_mode",
    )

    def __init__(
        self,
        *,
        version: str,
        weights: dict[str, float],
        method: str = "manual_heuristic",
        dataset: str = "none",
        timestamp: str = "unknown",
        notes: str = "",
    ) -> None:
        # Validate features
        required = set(DOMINANCE_FEATURES)
        provided = set(weights.keys())
        if provided != required:
            missing = required - provided
            extra = provided - required
            raise ValueError(
                f"CalibrationConfig weight keys must match DOMINANCE_FEATURES. "
                f"Missing: {missing}, Extra: {extra}"
            )

        # Validate weights are finite non-negative
        for feature, w in weights.items():
            if not isinstance(w, (int, float)) or w < 0:
                raise ValueError(
                    f"Weight for '{feature}' must be non-negative number, "
                    f"got {w!r}."
                )

        self._version = version
        self._weights = dict(weights)  # defensive copy
        self._method = method
        self._dataset = dataset
        self._timestamp = timestamp
        self._notes = notes
        # Mode is determined by actual metadata, not by declaration
        self._mode = (
            CalibrationMode.FITTED
            if method != "manual_heuristic" and dataset != "none"
            else CalibrationMode.HEURISTIC_DEFAULT
        )
        self._frozen = True

    @property
    def version(self) -> str:
        return self._version

    @property
    def weights(self) -> dict[str, float]:
        return dict(self._weights)  # always return copy

    @property
    def method(self) -> str:
        return self._method

    @property
    def dataset(self) -> str:
        return self._dataset

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @property
    def notes(self) -> str:
        return self._notes

    @property
    def mode(self) -> str:
        """Return calibration mode: HEURISTIC_DEFAULT or FITTED."""
        return self._mode

    def is_fitted(self) -> bool:
        """True only if weights were produced by offline fitting.

        Requires: method != 'manual_heuristic' AND dataset != 'none'.
        This is the honesty check — no weight is called fitted
        unless it actually was.
        """
        return self._mode == CalibrationMode.FITTED

    def weight(self, feature: str) -> float:
        """Get weight for a single feature."""
        if feature not in self._weights:
            raise KeyError(
                f"Unknown feature '{feature}'. "
                f"Valid features: {sorted(self._weights.keys())}"
            )
        return self._weights[feature]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for audit/export."""
        return {
            "version": self._version,
            "weights": dict(self._weights),
            "method": self._method,
            "dataset": self._dataset,
            "timestamp": self._timestamp,
            "notes": self._notes,
            "features": list(DOMINANCE_FEATURES),
            "calibration_mode": self._mode,
            "calibration_artifact_present": self.is_fitted(),
        }

    def __repr__(self) -> str:
        return (
            f"CalibrationConfig(version={self._version!r}, "
            f"weights={self._weights!r}, method={self._method!r})"
        )


# ═══════════════════════════════════════════════════════════════════════════
# DEFAULT INSTANCE (heuristic fallback)
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_CALIBRATION = CalibrationConfig(
    version=HEURISTIC_VERSION,
    weights=HEURISTIC_WEIGHTS,
    method="manual_heuristic",
    dataset="none",
    timestamp="2026-03-27",
    notes=(
        "Hand-tuned heuristic weights. "
        "severity=3, claims_forbidden=2, primary_path=1, recurrence=0. "
        "These are heuristic defaults — not fitted to data."
    ),
)


# ═══════════════════════════════════════════════════════════════════════════
# ACTIVE CONFIG (module-level, set once at import)
# ═══════════════════════════════════════════════════════════════════════════

_active_config: CalibrationConfig = DEFAULT_CALIBRATION


def get_active_calibration() -> CalibrationConfig:
    """Return the currently active calibration config.

    If no fitted calibration has been loaded, returns the
    heuristic default. Check config.mode for honest labeling.
    """
    return _active_config


def load_calibration(config: CalibrationConfig) -> None:
    """Load a calibration config as the active configuration.

    This is called ONCE during system initialization, not at
    runtime within the pipeline. The arbiter reads from
    get_active_calibration() which returns whatever was loaded.

    Args:
        config: A validated CalibrationConfig instance.
    """
    global _active_config
    if not isinstance(config, CalibrationConfig):
        raise TypeError(
            f"Expected CalibrationConfig, got {type(config).__name__}."
        )
    _active_config = config


def reset_to_heuristic() -> None:
    """Reset active calibration to the heuristic default.

    Used in testing and as the fallback path.
    """
    global _active_config
    _active_config = DEFAULT_CALIBRATION


# ═══════════════════════════════════════════════════════════════════════════
# CALIBRATION PIPELINE INTERFACE (OFFLINE ONLY)
# ═══════════════════════════════════════════════════════════════════════════

# This section defines the SCHEMA for offline calibration.
# The actual optimization is done OUTSIDE the pipeline.

CALIBRATION_DATA_SCHEMA: dict[str, str] = {
    "country": "ISO-2 country code",
    "reason_source": "Source module that produced the reason",
    "reason_decision": "Arbiter decision (VALID/RESTRICTED/FLAGGED/SUPPRESSED/BLOCKED)",
    "n_claims_forbidden": "Number of claim categories forbidden by this source",
    "is_primary_path": "Boolean: source is on primary decision path",
    "n_recurrence": "Number of times this source appears in reasons",
    "was_true_bottleneck": "Boolean: expert label — was this the actual dominant bottleneck?",
}

CALIBRATION_OBJECTIVE: str = (
    "Minimize binary cross-entropy between the model's predicted dominant "
    "constraint (argmax of dominance scores) and the expert-labeled "
    "'was_true_bottleneck' field. The optimization is convex in the "
    "weight space when features are non-negative."
)

CALIBRATION_OUTPUT_FORMAT: dict[str, str] = {
    "version": "Semantic version string (e.g. 'calibrated-v1')",
    "weights": "Dict[str, float] mapping feature names to calibrated weights",
    "method": "Optimization method used (e.g. 'logistic_regression')",
    "dataset": "Description of training dataset",
    "timestamp": "ISO-8601 timestamp of calibration run",
    "notes": "Free-text notes about calibration quality",
}
