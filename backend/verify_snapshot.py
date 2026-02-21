"""
backend.verify_snapshot — CLI for snapshot integrity verification.

Usage:
    python -m backend.verify_snapshot --methodology v1.0 --year 2024
    python -m backend.verify_snapshot --methodology v1.0 --year 2024 --json
    python -m backend.verify_snapshot --methodology v1.0 --year 2024 --quiet

Exit codes:
    0: Valid — all checks passed.
    1: Missing files — expected snapshot files not found.
    2: Manifest mismatch — SHA-256 hash of one or more files differs.
    3: Hash mismatch — per-country or snapshot-level hash mismatch.
    4: Structural invariant violation — data shape, rank, or classification error.
    5: Methodology mismatch — methodology version inconsistency.

Output:
    Default: human-readable summary to stdout.
    --json: structured JSON report to stdout.
    --quiet: no output, only exit code.

Institutional tool. No print noise. Structured output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.snapshot_integrity import (
    EXIT_HASH_MISMATCH,
    EXIT_MANIFEST_MISMATCH,
    EXIT_METHODOLOGY_MISMATCH,
    EXIT_MISSING_FILES,
    EXIT_OK,
    EXIT_STRUCTURAL_INVARIANT,
    validate_snapshot,
)
from backend.snapshot_resolver import SNAPSHOTS_ROOT


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_snapshot",
        description="Verify ISI snapshot integrity: structure, hashes, invariants.",
    )
    parser.add_argument(
        "--methodology",
        required=True,
        help="Methodology version (e.g., v1.0).",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Snapshot year (e.g., 2024).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON report.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress all output. Exit code only.",
    )
    parser.add_argument(
        "--snapshot-root",
        type=str,
        default=None,
        help="Override snapshot root directory (default: backend/snapshots/).",
    )
    return parser


EXIT_CODE_LABELS: dict[int, str] = {
    EXIT_OK: "VALID",
    EXIT_MISSING_FILES: "MISSING_FILES",
    EXIT_MANIFEST_MISMATCH: "MANIFEST_MISMATCH",
    EXIT_HASH_MISMATCH: "HASH_MISMATCH",
    EXIT_STRUCTURAL_INVARIANT: "STRUCTURAL_INVARIANT_VIOLATION",
    EXIT_METHODOLOGY_MISMATCH: "METHODOLOGY_MISMATCH",
}


def main(argv: list[str] | None = None) -> int:
    """Run snapshot verification. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(args.snapshot_root) if args.snapshot_root else SNAPSHOTS_ROOT
    snapshot_dir = root / args.methodology / str(args.year)

    report = validate_snapshot(
        snapshot_dir=snapshot_dir,
        methodology_version=args.methodology,
        year=args.year,
    )

    if args.quiet:
        return report.exit_code

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return report.exit_code

    # Human-readable output
    status = "VALID" if report.valid else EXIT_CODE_LABELS.get(report.exit_code, "FAILED")
    print(f"Snapshot: {args.methodology}/{args.year}")
    print(f"Status:   {status}")
    print(f"Checks:   {len(report.checks)}")

    for check in report.checks:
        marker = "✓" if check["passed"] else "✗"
        detail = f" — {check['detail']}" if check.get("detail") else ""
        print(f"  {marker} {check['check']}{detail}")

    if report.errors:
        print(f"\nErrors ({len(report.errors)}):")
        for err in report.errors:
            print(f"  • {err}")

    print(f"\nExit code: {report.exit_code}")
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
