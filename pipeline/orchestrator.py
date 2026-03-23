"""
pipeline.orchestrator — Main pipeline runner for ISI data ingestion.

Orchestrates:
    1. Directory structure creation (RAW → STAGING → VALIDATED → META)
    2. Source-specific ingestion per reporter × axis
    3. Normalization → Validation → Export
    4. Provenance manifests and audit logs
    5. Summary reporting

Usage:
    from pipeline.orchestrator import run_pipeline
    results = run_pipeline("JP")                    # single country
    results = run_pipeline(["JP", "US", "CN"])      # multiple countries
    results = run_pipeline()                        # all ISI countries
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.config import (
    PROJECT_ROOT,
    STAGING_DIR,
    VALIDATED_DIR,
    META_DIR,
    AUDIT_DIR,
    AXIS_REGISTRY,
    AXIS_SLUGS,
    ALL_ISI_COUNTRIES,
)
from pipeline.schema import BilateralDataset, IngestionManifest
from pipeline.validate import validate_dataset, validate_and_report
from pipeline.status import IngestionStatus, ValidationStatus, AxisStatus, ACCEPTABLE_STATUSES
from pipeline.ingest.bis_lbs import ingest_bis_lbs
from pipeline.ingest.imf_cpis import ingest_imf_cpis
from pipeline.ingest.comtrade import ingest_comtrade
from pipeline.ingest.sipri import ingest_sipri
from pipeline.ingest.logistics import ingest_logistics

logger = logging.getLogger("pipeline.orchestrator")

# ---------------------------------------------------------------------------
# Axis → ingestion function mapping
# ---------------------------------------------------------------------------

# Each axis maps to one or more (source, ingest_fn) pairs
AXIS_INGEST_MAP: dict[int, list[tuple[str, Any]]] = {
    1: [
        ("bis_lbs", ingest_bis_lbs),
        ("imf_cpis", ingest_imf_cpis),
    ],
    2: [
        ("un_comtrade_energy", lambda r, **kw: ingest_comtrade(r, axis="energy", **kw)),
    ],
    3: [
        ("un_comtrade_tech", lambda r, **kw: ingest_comtrade(r, axis="technology", **kw)),
    ],
    4: [
        ("sipri", ingest_sipri),
    ],
    5: [
        ("un_comtrade_crit", lambda r, **kw: ingest_comtrade(r, axis="critical_inputs", **kw)),
    ],
    6: [
        ("eurostat_logistics", ingest_logistics),
    ],
}


# ---------------------------------------------------------------------------
# Directory structure management
# ---------------------------------------------------------------------------

def ensure_directories(reporter: str) -> dict[str, Path]:
    """Create the full directory structure for a reporter.

    Returns dict of {layer: path}.
    """
    dirs = {}
    for axis_id, axis_info in AXIS_REGISTRY.items():
        slug = axis_info["slug"]
        for layer_name, layer_root in [
            ("staging", STAGING_DIR),
            ("validated", VALIDATED_DIR),
            ("meta", META_DIR),
        ]:
            d = layer_root / reporter / slug
            d.mkdir(parents=True, exist_ok=True)
            dirs[f"{layer_name}/{reporter}/{slug}"] = d

    # Audit directory
    audit_dir = AUDIT_DIR / reporter
    audit_dir.mkdir(parents=True, exist_ok=True)
    dirs[f"audit/{reporter}"] = audit_dir

    return dirs


# ---------------------------------------------------------------------------
# Single reporter × axis ingestion
# ---------------------------------------------------------------------------

def ingest_one(
    reporter: str,
    axis_id: int,
) -> list[tuple[BilateralDataset | None, dict]]:
    """Ingest all data sources for one reporter × axis.

    Returns list of (dataset, stats) tuples (one per source).
    """
    if axis_id not in AXIS_INGEST_MAP:
        logger.warning("No ingestion functions registered for axis %d", axis_id)
        return []

    results = []
    for source_name, ingest_fn in AXIS_INGEST_MAP[axis_id]:
        try:
            dataset, stats = ingest_fn(reporter)
            stats["_source_label"] = source_name
            results.append((dataset, stats))
        except Exception as e:
            logger.error(
                "INGESTION ERROR: %s axis=%d source=%s: %s",
                reporter, axis_id, source_name, e,
            )
            stats = {
                "source": source_name,
                "reporter": reporter,
                "status": IngestionStatus.EXCEPTION,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
            results.append((None, stats))

    return results


# ---------------------------------------------------------------------------
# Export stage
# ---------------------------------------------------------------------------

def export_dataset(
    dataset: BilateralDataset,
    validation_report: dict,
) -> dict[str, str]:
    """Export a validated dataset to staging/validated/meta layers.

    Returns dict of output paths.
    """
    reporter = dataset.reporter
    axis = dataset.axis
    source = dataset.source

    paths: dict[str, str] = {}

    # Staging CSV (always written)
    staging_path = STAGING_DIR / reporter / axis / f"{source}.csv"
    dataset.to_csv(staging_path)
    paths["staging_csv"] = str(staging_path)

    # Validated CSV (only if validation passed)
    if dataset.validation_status in (ValidationStatus.PASS, ValidationStatus.WARNING):
        validated_path = VALIDATED_DIR / reporter / axis / f"{source}.csv"
        dataset.to_csv(validated_path)
        paths["validated_csv"] = str(validated_path)

    # Metadata JSON (always written)
    meta_path = META_DIR / reporter / axis / f"{source}_meta.json"
    dataset.to_metadata_json(meta_path)
    paths["meta_json"] = str(meta_path)

    # Validation report JSON
    report_path = META_DIR / reporter / axis / f"{source}_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(validation_report, f, indent=2, ensure_ascii=False, default=str)
        f.write("\n")
    paths["validation_json"] = str(report_path)

    return paths


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    reporters: str | list[str] | None = None,
    axes: list[int] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run the full ISI data ingestion pipeline.

    Args:
        reporters: Single ISO-2 code, list of codes, or None for all.
        axes: List of axis IDs to process, or None for all.
        dry_run: If True, ingest and validate but don't export.

    Returns:
        Comprehensive results dict with:
        - manifest: full provenance record
        - results: per-reporter per-axis results
        - summary: aggregate statistics
    """
    # Resolve reporters
    if reporters is None:
        reporter_list = sorted(ALL_ISI_COUNTRIES)
    elif isinstance(reporters, str):
        reporter_list = [reporters]
    else:
        reporter_list = list(reporters)

    # Resolve axes
    if axes is None:
        axis_list = sorted(AXIS_REGISTRY.keys())
    else:
        axis_list = list(axes)

    # Initialize manifest
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    manifest = IngestionManifest(
        run_id=run_id,
        start_time=datetime.now(timezone.utc).isoformat(),
    )

    logger.info("=" * 70)
    logger.info("ISI GLOBAL DATA INGESTION PIPELINE v1.1")
    logger.info("=" * 70)
    logger.info("Run ID:     %s", run_id)
    logger.info("Reporters:  %s (%d)", reporter_list, len(reporter_list))
    logger.info("Axes:       %s", [AXIS_SLUGS.get(a, a) for a in axis_list])
    logger.info("Dry run:    %s", dry_run)
    logger.info("=" * 70)

    all_results: dict[str, dict[str, Any]] = {}
    summary = {
        "reporters_processed": 0,
        "datasets_ingested": 0,
        "datasets_validated": 0,
        "datasets_passed": 0,
        "datasets_warned": 0,
        "datasets_failed": 0,
        "datasets_no_data": 0,
        "total_records": 0,
    }

    for reporter in reporter_list:
        logger.info("")
        logger.info("─" * 60)
        logger.info("REPORTER: %s", reporter)
        logger.info("─" * 60)

        reporter_results: dict[str, Any] = {}
        ensure_directories(reporter)

        for axis_id in axis_list:
            axis_slug = AXIS_SLUGS.get(axis_id, f"axis_{axis_id}")
            logger.info("  Axis %d (%s):", axis_id, axis_slug)

            # Ingest all sources for this axis
            ingestion_results = ingest_one(reporter, axis_id)

            axis_results: list[dict] = []
            for dataset, stats in ingestion_results:
                source_label = stats.get("_source_label", stats.get("source", "unknown"))

                if dataset is None:
                    status = stats.get("status", "NO_DATA")
                    logger.info("    %s: %s", source_label, status)
                    manifest.record_ingestion(
                        reporter, axis_slug, source_label,
                        n_records=0, status=status,
                    )
                    summary["datasets_no_data"] += 1
                    axis_results.append({
                        "source": source_label,
                        "status": status,
                        "stats": stats,
                    })
                    continue

                summary["datasets_ingested"] += 1
                summary["total_records"] += len(dataset.records)

                # Validate
                validation_report = validate_and_report(dataset)
                val_status = dataset.validation_status
                summary["datasets_validated"] += 1

                if val_status == ValidationStatus.PASS:
                    summary["datasets_passed"] += 1
                elif val_status == ValidationStatus.WARNING:
                    summary["datasets_warned"] += 1
                else:
                    summary["datasets_failed"] += 1

                logger.info(
                    "    %s: %s — %d records, %d partners, validation=%s",
                    source_label, stats.get("status", "?"),
                    len(dataset.records), dataset.n_partners, val_status,
                )

                manifest.record_ingestion(
                    reporter, axis_slug, source_label,
                    n_records=len(dataset.records), status=stats.get("status", "OK"),
                )
                manifest.record_validation(
                    reporter, axis_slug, val_status,
                    errors=dataset.validation_errors,
                    warnings=dataset.validation_warnings,
                )

                # Export
                export_paths = {}
                if not dry_run:
                    export_paths = export_dataset(dataset, validation_report)

                axis_results.append({
                    "source": source_label,
                    "status": stats.get("status", "?"),
                    "validation_status": val_status,
                    "n_records": len(dataset.records),
                    "n_partners": dataset.n_partners,
                    "total_value": dataset.total_value,
                    "stats": stats,
                    "export_paths": export_paths,
                })

            reporter_results[axis_slug] = axis_results

        all_results[reporter] = reporter_results
        summary["reporters_processed"] += 1

    # Finalize manifest
    manifest.end_time = datetime.now(timezone.utc).isoformat()
    manifest.status = "COMPLETED"

    # Write manifest
    if not dry_run:
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path = AUDIT_DIR / f"manifest_{run_id}.json"
        manifest.to_json(manifest_path)
        logger.info("Manifest: %s", manifest_path)

    # Summary
    logger.info("")
    logger.info("=" * 70)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 70)
    for key, val in summary.items():
        logger.info("  %-30s %s", key, val)
    logger.info("=" * 70)

    return {
        "manifest": manifest,
        "results": all_results,
        "summary": summary,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for the pipeline."""
    import argparse

    parser = argparse.ArgumentParser(
        description="ISI Global Data Ingestion Pipeline v1.1",
    )
    parser.add_argument(
        "reporters",
        nargs="*",
        help="ISO-2 country codes to process (default: all ISI countries)",
    )
    parser.add_argument(
        "--axes",
        type=int,
        nargs="+",
        help="Axis IDs to process (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without exporting",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    reporters = args.reporters if args.reporters else None
    results = run_pipeline(
        reporters=reporters,
        axes=args.axes,
        dry_run=args.dry_run,
    )

    # Exit code based on results
    if results["summary"]["datasets_failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
