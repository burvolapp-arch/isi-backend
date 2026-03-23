"""
pipeline.status — Canonical status enums for the ISI pipeline.

ALL ingestion modules, validation, and orchestration MUST use these
enums. No raw strings. No ambiguity.

Taxonomy:
    IngestionStatus  — outcome of a single source ingestion attempt
    ValidationStatus — outcome of validation checks on a dataset
    AxisStatus       — final composite status for a reporter × axis

Design rules:
    - STRUCTURAL_LIMITATION: the source genuinely does not cover this
      reporter/region and no alternative exists. E.g., Eurostat logistics
      for non-EU countries.
    - IMPLEMENTATION_LIMITATION: the data exists in principle but is not
      yet ingested by the current pipeline. E.g., SIPRI data for Japan
      exists in the SIPRI database but has not been downloaded yet.
    - FAILED: ingestion was attempted and produced invalid/unusable data.
"""

from __future__ import annotations

from enum import Enum


class IngestionStatus(str, Enum):
    """Status of a single source ingestion attempt."""

    OK = "OK"
    """Ingestion succeeded and produced records."""

    NO_DATA = "NO_DATA"
    """Source file/API returned zero relevant records after filtering."""

    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    """Expected raw file does not exist on disk."""

    API_FAILED = "API_FAILED"
    """API request failed after all retries."""

    STRUCTURAL_LIMITATION = "STRUCTURAL_LIMITATION"
    """Source genuinely does not cover this reporter/region.
    No alternative exists. Not a pipeline bug.
    Example: Eurostat logistics for Japan."""

    IMPLEMENTATION_LIMITATION = "IMPLEMENTATION_LIMITATION"
    """Data exists in principle but current pipeline cannot ingest it yet.
    Requires either: data download, format support, or new module.
    Example: SIPRI data for Japan (exists in SIPRI DB, not yet downloaded)."""

    MALFORMED_FILE = "MALFORMED_FILE"
    """Raw file exists but cannot be parsed (bad encoding, missing headers)."""

    EXCEPTION = "EXCEPTION"
    """Unexpected runtime error during ingestion."""

    NO_BILATERAL_DATA = "NO_BILATERAL_DATA"
    """Source exists but has no bilateral partner dimension.
    E.g., maritime mode-share data (tonnage by ship type, not by country)."""

    PENDING = "PENDING"
    """Not yet attempted (initial state only)."""


class ValidationStatus(str, Enum):
    """Status of validation checks on a dataset."""

    PASS = "PASS"
    """All validation checks passed."""

    WARNING = "WARNING"
    """Data is usable but has minor issues (missing partners, etc.)."""

    FAIL = "FAIL"
    """Validation failed — dataset is not suitable for computation."""

    PENDING = "PENDING"
    """Validation has not been run yet."""


class AxisStatus(str, Enum):
    """Final status for a reporter × axis after all sources are processed."""

    PASS = "PASS"
    WARNING = "WARNING"
    STRUCTURAL_LIMITATION = "STRUCTURAL_LIMITATION"
    IMPLEMENTATION_LIMITATION = "IMPLEMENTATION_LIMITATION"
    FAILED = "FAILED"


# Statuses considered acceptable for pipeline completion
ACCEPTABLE_STATUSES = frozenset({
    AxisStatus.PASS,
    AxisStatus.WARNING,
    AxisStatus.STRUCTURAL_LIMITATION,
    AxisStatus.IMPLEMENTATION_LIMITATION,
})
