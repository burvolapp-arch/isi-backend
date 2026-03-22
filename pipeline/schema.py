"""
pipeline.schema — Canonical data schema for the ISI ingestion pipeline.

ALL axes MUST output data conforming to this schema.
No exceptions. No alternative formats. No silent degradation.

The canonical row is:
    reporter: ISO-2 country code (the country whose dependency is measured)
    partner:  ISO-2 country code (the trade/investment counterpart)
    value:    float > 0 (USD or TIV units, depending on source)
    year:     int (calendar year of measurement)
    source:   string (upstream data source identifier)
    axis:     string (ISI axis slug)

Additional context fields are permitted but MUST NOT replace these 6.
"""

from __future__ import annotations

import csv
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pipeline.status import ValidationStatus


# ---------------------------------------------------------------------------
# Canonical record — the atomic unit of bilateral data
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BilateralRecord:
    """One bilateral observation: reporter→partner flow for a given axis/year.

    This is the canonical schema. ALL ingestion modules must produce
    instances of this class. ALL validation operates on lists of these.
    """
    reporter: str       # ISO-2 code
    partner: str        # ISO-2 code
    value: float        # positive float (USD millions or TIV)
    year: int           # calendar year
    source: str         # source identifier (e.g., "imf_cpis", "bis_lbs")
    axis: str           # axis slug (e.g., "financial", "energy")

    # Optional context fields — NEVER replace the 6 canonical fields
    product_code: str | None = None    # HS code, CPIS indicator, etc.
    product_desc: str | None = None    # human-readable product name
    unit: str = "USD_MN"               # value unit
    sub_category: str | None = None    # fuel type, material group, etc.

    def __post_init__(self):
        """Validate invariants at construction time."""
        if not self.reporter or len(self.reporter) < 2:
            raise ValueError(f"Invalid reporter code: '{self.reporter}'")
        if not self.partner or len(self.partner) < 2:
            raise ValueError(f"Invalid partner code: '{self.partner}'")
        if self.value < 0:
            raise ValueError(
                f"Negative value {self.value} for {self.reporter}→{self.partner}"
            )
        if self.year < 1990 or self.year > 2030:
            raise ValueError(f"Year out of range: {self.year}")
        if not self.source:
            raise ValueError("Source must not be empty")
        if not self.axis:
            raise ValueError("Axis must not be empty")

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable canonical representation."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Dataset — a collection of bilateral records with metadata
# ---------------------------------------------------------------------------

@dataclass
class BilateralDataset:
    """A validated collection of BilateralRecords for one reporter/axis.

    This is the unit of staging/validation/export.
    """
    reporter: str
    axis: str
    source: str
    year_range: tuple[int, int]
    records: list[BilateralRecord] = field(default_factory=list)

    # Metadata fields (populated during validation)
    n_partners: int = 0
    total_value: float = 0.0
    partners: list[str] = field(default_factory=list)
    validation_status: str = ValidationStatus.PENDING  # PENDING, PASS, FAIL, WARNING
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    ingestion_timestamp: str = ""
    data_hash: str = ""

    def __post_init__(self):
        if not self.ingestion_timestamp:
            self.ingestion_timestamp = datetime.now(timezone.utc).isoformat()

    def add_record(self, record: BilateralRecord) -> None:
        """Add a record, enforcing reporter/axis consistency."""
        if record.reporter != self.reporter:
            raise ValueError(
                f"Record reporter '{record.reporter}' does not match "
                f"dataset reporter '{self.reporter}'"
            )
        if record.axis != self.axis:
            raise ValueError(
                f"Record axis '{record.axis}' does not match "
                f"dataset axis '{self.axis}'"
            )
        self.records.append(record)

    def compute_metadata(self) -> None:
        """Compute summary metadata from records."""
        self.n_partners = len(set(r.partner for r in self.records))
        self.total_value = sum(r.value for r in self.records)
        self.partners = sorted(set(r.partner for r in self.records))
        self._compute_hash()

    def _compute_hash(self) -> None:
        """Compute deterministic hash of all record values for auditability."""
        hasher = hashlib.sha256()
        for r in sorted(self.records, key=lambda x: (x.reporter, x.partner, x.year)):
            row_str = f"{r.reporter}|{r.partner}|{r.value}|{r.year}|{r.source}|{r.axis}"
            hasher.update(row_str.encode("utf-8"))
        self.data_hash = hasher.hexdigest()

    def to_csv(self, path: Path) -> Path:
        """Export to canonical CSV format."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "reporter", "partner", "value", "year",
                "source", "axis", "product_code", "sub_category", "unit",
            ])
            for r in sorted(self.records, key=lambda x: (-x.value, x.partner)):
                writer.writerow([
                    r.reporter, r.partner, r.value, r.year,
                    r.source, r.axis, r.product_code or "", r.sub_category or "",
                    r.unit,
                ])
        return path

    def to_metadata_json(self, path: Path) -> Path:
        """Export metadata as JSON for audit trail.

        Includes interpretation_caveats — mandatory disclaimers about
        what the data does and does NOT represent. Every downstream
        consumer MUST read these before using the data.
        """
        path.parent.mkdir(parents=True, exist_ok=True)

        # Load axis-level constraints from AXIS_REGISTRY
        axis_constraints: dict[str, Any] = {}
        interpretation_caveats: list[str] = []
        try:
            from pipeline.config import AXIS_REGISTRY
            for _axis_id, info in AXIS_REGISTRY.items():
                if info["slug"] == self.axis:
                    axis_constraints = {
                        "value_type": info.get("value_type", "UNKNOWN"),
                        "value_label": info.get("value_label", "Unknown"),
                        "scope": info.get("scope", "Not specified"),
                        "exclusions": info.get("exclusions", []),
                        "interpretation_note": info.get("interpretation_note", ""),
                        "confidence_baseline": info.get("confidence_baseline", 0.5),
                        "window_type": info.get("window_type", "unknown"),
                        "window_semantics": info.get("window_semantics", ""),
                        "temporal_sensitivity": info.get("temporal_sensitivity", "unknown"),
                    }
                    # Build caveats list
                    if info.get("interpretation_note"):
                        interpretation_caveats.append(info["interpretation_note"])
                    if info.get("exclusions"):
                        interpretation_caveats.append(
                            "Excluded from scope: " + "; ".join(info["exclusions"])
                        )
                    if info.get("value_type") == "TIV_MN":
                        interpretation_caveats.append(
                            "Values are in SIPRI Trend Indicator Value (TIV), "
                            "NOT monetary units. TIV measures military capability "
                            "transferred, not financial cost. Do NOT compare TIV "
                            "totals to USD trade values from other axes."
                        )
                    if info.get("temporal_sensitivity") == "high":
                        interpretation_caveats.append(
                            "This axis has HIGH temporal sensitivity. Year-to-year "
                            "variation may reflect delivery schedules, not changing "
                            "dependency. Use multi-year windows for trend analysis."
                        )
                    break
        except ImportError:
            interpretation_caveats.append(
                "AXIS_REGISTRY unavailable — interpretation constraints not loaded."
            )

        meta = {
            "reporter": self.reporter,
            "axis": self.axis,
            "source": self.source,
            "year_range": list(self.year_range),
            "n_records": len(self.records),
            "n_partners": self.n_partners,
            "total_value": self.total_value,
            "partners": self.partners,
            "validation_status": self.validation_status,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "ingestion_timestamp": self.ingestion_timestamp,
            "data_hash": self.data_hash,
            "top_partners": self._top_partners(10),
            "axis_constraints": axis_constraints,
            "interpretation_caveats": interpretation_caveats,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return path

    def _top_partners(self, n: int) -> list[dict[str, Any]]:
        """Return top-N partners by value with shares."""
        if self.total_value <= 0:
            return []
        partner_values: dict[str, float] = {}
        for r in self.records:
            partner_values[r.partner] = partner_values.get(r.partner, 0.0) + r.value
        sorted_partners = sorted(partner_values.items(), key=lambda x: -x[1])
        return [
            {
                "partner": p,
                "value": round(v, 8),
                "share": round(v / self.total_value, 8) if self.total_value > 0 else 0,
            }
            for p, v in sorted_partners[:n]
        ]


# ---------------------------------------------------------------------------
# Ingestion manifest — tracks what was ingested and when
# ---------------------------------------------------------------------------

@dataclass
class IngestionManifest:
    """Full provenance record for one pipeline run."""
    run_id: str
    start_time: str
    end_time: str = ""
    pipeline_version: str = "1.1.0"
    datasets_ingested: list[dict[str, Any]] = field(default_factory=list)
    datasets_validated: list[dict[str, Any]] = field(default_factory=list)
    datasets_rejected: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    status: str = "RUNNING"  # RUNNING, COMPLETED, FAILED

    def record_ingestion(
        self,
        reporter: str,
        axis: str,
        source: str,
        n_records: int,
        status: str,
    ) -> None:
        self.datasets_ingested.append({
            "reporter": reporter,
            "axis": axis,
            "source": source,
            "n_records": n_records,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def record_validation(
        self,
        reporter: str,
        axis: str,
        status: str,
        errors: list[str],
        warnings: list[str],
    ) -> None:
        target = self.datasets_validated if status != "FAIL" else self.datasets_rejected
        target.append({
            "reporter": reporter,
            "axis": axis,
            "status": status,
            "errors": errors,
            "warnings": warnings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def finalize(self, status: str = "COMPLETED") -> None:
        self.end_time = datetime.now(timezone.utc).isoformat()
        self.status = status

    def to_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
            f.write("\n")
        return path
