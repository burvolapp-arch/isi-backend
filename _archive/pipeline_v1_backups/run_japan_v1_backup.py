#!/usr/bin/env python3
"""
ISI v1.1 — Japan Pipeline Example Run

Demonstrates the full data ingestion pipeline for Japan (JP)
across all 6 axes:
    1. Financial   (BIS LBS + IMF CPIS)
    2. Energy      (UN Comtrade fuels)
    3. Technology  (UN Comtrade semiconductors)
    4. Defense     (SIPRI arms transfers)
    5. Critical Inputs (UN Comtrade materials)
    6. Logistics   (Eurostat freight)

Usage:
    python pipeline/run_japan.py
    python pipeline/run_japan.py --dry-run
    python pipeline/run_japan.py --verbose
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import (
    STAGING_DIR,
    VALIDATED_DIR,
    META_DIR,
    AUDIT_DIR,
    AXIS_REGISTRY,
    AXIS_SLUGS,
)
from pipeline.schema import BilateralDataset
from pipeline.validate import validate_dataset, validate_and_report
from pipeline.ingest.bis_lbs import ingest_bis_lbs
from pipeline.ingest.imf_cpis import ingest_imf_cpis
from pipeline.ingest.comtrade import ingest_comtrade
from pipeline.ingest.sipri import ingest_sipri
from pipeline.ingest.logistics import ingest_logistics

REPORTER = "JP"


def print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_dataset_summary(dataset: BilateralDataset | None, stats: dict) -> None:
    """Print a formatted summary of a dataset ingestion result."""
    if dataset is None:
        print(f"  Status:  {stats.get('status', 'UNKNOWN')}")
        print(f"  Records: 0")
        return

    print(f"  Status:      {stats.get('status', '?')}")
    print(f"  Records:     {len(dataset.records)}")
    print(f"  Partners:    {dataset.n_partners}")
    print(f"  Total value: {dataset.total_value:,.2f} {dataset.records[0].unit if dataset.records else '?'}")
    print(f"  Validation:  {dataset.validation_status}")

    # Top 5 partners
    if dataset.records:
        partner_vals: dict[str, float] = {}
        for r in dataset.records:
            partner_vals[r.partner] = partner_vals.get(r.partner, 0) + r.value
        sorted_p = sorted(partner_vals.items(), key=lambda x: -x[1])
        total = dataset.total_value
        print(f"  Top partners:")
        for p, v in sorted_p[:5]:
            share = (v / total * 100) if total > 0 else 0
            print(f"    {p}: {v:>12,.2f} ({share:>5.1f}%)")

    if dataset.validation_errors:
        print(f"  ERRORS:")
        for err in dataset.validation_errors[:5]:
            print(f"    ✗ {err}")
    if dataset.validation_warnings:
        print(f"  WARNINGS:")
        for warn in dataset.validation_warnings[:5]:
            print(f"    ⚠ {warn}")


def export_if_valid(dataset: BilateralDataset, validation_report: dict, dry_run: bool) -> None:
    """Export dataset to staging/validated/meta layers."""
    if dry_run:
        print(f"  [DRY RUN] Would export to staging/validated/meta")
        return

    reporter = dataset.reporter
    axis = dataset.axis
    source = dataset.source

    # Staging CSV
    staging_path = STAGING_DIR / reporter / axis / f"{source}.csv"
    dataset.to_csv(staging_path)
    print(f"  → Staging:   {staging_path}")

    # Validated CSV (if passed)
    if dataset.validation_status in ("PASS", "WARNING"):
        validated_path = VALIDATED_DIR / reporter / axis / f"{source}.csv"
        dataset.to_csv(validated_path)
        print(f"  → Validated: {validated_path}")

    # Metadata JSON
    meta_path = META_DIR / reporter / axis / f"{source}_meta.json"
    dataset.to_metadata_json(meta_path)
    print(f"  → Metadata:  {meta_path}")

    # Validation report
    report_path = META_DIR / reporter / axis / f"{source}_validation.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(validation_report, f, indent=2, default=str)
    print(f"  → Validation: {report_path}")


def run_japan(dry_run: bool = False, verbose: bool = False) -> dict:
    """Execute the full pipeline for Japan."""

    # Configure logging
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    start_time = datetime.now(timezone.utc)

    print_section("ISI v1.1 — JAPAN DATA INGESTION PIPELINE")
    print(f"  Reporter: {REPORTER}")
    print(f"  Time:     {start_time.isoformat()}")
    print(f"  Dry run:  {dry_run}")

    # Ensure directories
    for axis_id, info in AXIS_REGISTRY.items():
        slug = info["slug"]
        for layer in (STAGING_DIR, VALIDATED_DIR, META_DIR):
            (layer / REPORTER / slug).mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / REPORTER).mkdir(parents=True, exist_ok=True)

    results = {}
    total_records = 0
    total_passed = 0
    total_failed = 0

    # ── Axis 1: Financial ─────────────────────────────────────────

    print_section("AXIS 1: FINANCIAL")

    # BIS LBS
    print("\n  [BIS LBS] Ingesting...")
    bis_dataset, bis_stats = ingest_bis_lbs(REPORTER)
    if bis_dataset:
        validate_dataset(bis_dataset)
        report = validate_and_report(bis_dataset)
        print_dataset_summary(bis_dataset, bis_stats)
        export_if_valid(bis_dataset, report, dry_run)
        total_records += len(bis_dataset.records)
        if bis_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, bis_stats)
        total_failed += 1
    results["financial_bis"] = bis_stats

    # IMF CPIS
    print("\n  [IMF CPIS] Ingesting...")
    cpis_dataset, cpis_stats = ingest_imf_cpis(REPORTER)
    if cpis_dataset:
        validate_dataset(cpis_dataset)
        report = validate_and_report(cpis_dataset)
        print_dataset_summary(cpis_dataset, cpis_stats)
        export_if_valid(cpis_dataset, report, dry_run)
        total_records += len(cpis_dataset.records)
        if cpis_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, cpis_stats)
        total_failed += 1
    results["financial_cpis"] = cpis_stats

    # ── Axis 2: Energy ────────────────────────────────────────────

    print_section("AXIS 2: ENERGY")
    print("\n  [UN Comtrade — Energy Fuels] Ingesting...")
    energy_dataset, energy_stats = ingest_comtrade(REPORTER, axis="energy")
    if energy_dataset:
        validate_dataset(energy_dataset)
        report = validate_and_report(energy_dataset)
        print_dataset_summary(energy_dataset, energy_stats)
        export_if_valid(energy_dataset, report, dry_run)
        total_records += len(energy_dataset.records)
        if energy_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, energy_stats)
        total_failed += 1
    results["energy"] = energy_stats

    # ── Axis 3: Technology ────────────────────────────────────────

    print_section("AXIS 3: TECHNOLOGY")
    print("\n  [UN Comtrade — Semiconductors] Ingesting...")
    tech_dataset, tech_stats = ingest_comtrade(REPORTER, axis="technology")
    if tech_dataset:
        validate_dataset(tech_dataset)
        report = validate_and_report(tech_dataset)
        print_dataset_summary(tech_dataset, tech_stats)
        export_if_valid(tech_dataset, report, dry_run)
        total_records += len(tech_dataset.records)
        if tech_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, tech_stats)
        total_failed += 1
    results["technology"] = tech_stats

    # ── Axis 4: Defense ───────────────────────────────────────────

    print_section("AXIS 4: DEFENSE")
    print("\n  [SIPRI Trade Register] Ingesting...")
    defense_dataset, defense_stats = ingest_sipri(REPORTER)
    if defense_dataset:
        validate_dataset(defense_dataset)
        report = validate_and_report(defense_dataset)
        print_dataset_summary(defense_dataset, defense_stats)
        export_if_valid(defense_dataset, report, dry_run)
        total_records += len(defense_dataset.records)
        if defense_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, defense_stats)
        total_failed += 1
    results["defense"] = defense_stats

    # ── Axis 5: Critical Inputs ───────────────────────────────────

    print_section("AXIS 5: CRITICAL INPUTS")
    print("\n  [UN Comtrade — Critical Materials] Ingesting...")
    crit_dataset, crit_stats = ingest_comtrade(REPORTER, axis="critical_inputs")
    if crit_dataset:
        validate_dataset(crit_dataset)
        report = validate_and_report(crit_dataset)
        print_dataset_summary(crit_dataset, crit_stats)
        export_if_valid(crit_dataset, report, dry_run)
        total_records += len(crit_dataset.records)
        if crit_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, crit_stats)
        total_failed += 1
    results["critical_inputs"] = crit_stats

    # ── Axis 6: Logistics ─────────────────────────────────────────

    print_section("AXIS 6: LOGISTICS")
    print("\n  [Eurostat Logistics] Ingesting...")
    log_dataset, log_stats = ingest_logistics(REPORTER)
    if log_dataset:
        validate_dataset(log_dataset)
        report = validate_and_report(log_dataset)
        print_dataset_summary(log_dataset, log_stats)
        export_if_valid(log_dataset, report, dry_run)
        total_records += len(log_dataset.records)
        if log_dataset.validation_status in ("PASS", "WARNING"):
            total_passed += 1
        else:
            total_failed += 1
    else:
        print_dataset_summary(None, log_stats)
        total_failed += 1
    results["logistics"] = log_stats

    # ── Summary ───────────────────────────────────────────────────

    end_time = datetime.now(timezone.utc)
    elapsed = (end_time - start_time).total_seconds()

    print_section("JAPAN PIPELINE SUMMARY")
    print(f"  Total datasets attempted: {total_passed + total_failed}")
    print(f"  Datasets PASSED/WARNING:  {total_passed}")
    print(f"  Datasets FAILED/NO_DATA:  {total_failed}")
    print(f"  Total records ingested:   {total_records:,}")
    print(f"  Elapsed time:             {elapsed:.2f}s")
    print()

    # Write summary JSON
    if not dry_run:
        summary_path = AUDIT_DIR / REPORTER / "japan_pipeline_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary = {
            "reporter": REPORTER,
            "run_time": start_time.isoformat(),
            "elapsed_seconds": elapsed,
            "total_records": total_records,
            "datasets_passed": total_passed,
            "datasets_failed": total_failed,
            "results": {k: {"status": v.get("status", "?")} for k, v in results.items()},
        }
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"  Summary: {summary_path}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ISI v1.1 — Japan Pipeline Example")
    parser.add_argument("--dry-run", action="store_true", help="Validate without exporting")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    run_japan(dry_run=args.dry_run, verbose=args.verbose)
