"""
ISI Results Evidence Pack — Build Entrypoint.

Reads snapshot artifacts from the ISI backend and generates the complete
empirical evidence pack for the Results Volume (Paper #2).

Usage:
    cd /path/to/repo
    python -m ISI_Paper.tools.results_pack.build_results_pack

All outputs are written to:
    ISI_Paper/evidence_pack_results_v1.0_2024/
"""

from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

# This script runs from the repo root
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND = REPO_ROOT / "backend"
SNAPSHOTS = BACKEND / "snapshots"
REGISTRY_PATH = SNAPSHOTS / "registry.json"
SNAPSHOT_DIR = SNAPSHOTS / "v1.0" / "2024"
V01_DIR = BACKEND / "v01"

OUTPUT_ROOT = REPO_ROOT / "ISI_Paper" / "evidence_pack_results_v1.0_2024"
DATA_EXPORTS = OUTPUT_ROOT / "data_exports"
TABLES_TEX = OUTPUT_ROOT / "tables_tex"
FIGURES_DIR = OUTPUT_ROOT / "figures"
AUDIT_DIR = OUTPUT_ROOT / "audit"
COUNTRY_PAGES_DIR = DATA_EXPORTS / "country_pages"

# ---------------------------------------------------------------------------
# Imports from our package
# ---------------------------------------------------------------------------

from .constants import (
    AXIS_ISI_KEYS,
    AXIS_SLUGS,
    EU27_CODES,
    EU27_COUNT,
    ISI_COUNTRIES_COLUMNS,
    METHODOLOGY_VERSION,
    YEAR,
)
from .derive import (
    build_country_page,
    compute_axis_drivers,
    compute_correlation_matrix,
    compute_distribution_vectors,
    compute_per_axis_stats,
    compute_ranking,
    compute_summary_stats,
    validate_data,
)
from .io_utils import (
    collect_input_hashes,
    collect_output_hashes,
    load_json,
    sha256_file,
    write_csv,
    write_json,
    write_text,
)
from .render import (
    render_axis_drivers_table,
    render_correlation_table,
    render_per_axis_stats_table,
    render_ranking_table,
    render_summary_stats_table,
    try_render_figures,
)


# ---------------------------------------------------------------------------
# Main build pipeline
# ---------------------------------------------------------------------------

def build() -> None:
    print("=" * 70)
    print("ISI Results Evidence Pack — Build")
    print(f"  Methodology: {METHODOLOGY_VERSION}")
    print(f"  Year: {YEAR}")
    print(f"  Snapshot: {SNAPSHOT_DIR}")
    print(f"  Output: {OUTPUT_ROOT}")
    print("=" * 70)
    print()

    # ------------------------------------------------------------------
    # 0. Load inputs
    # ------------------------------------------------------------------
    print("[0] Loading input artifacts...")

    registry = load_json(REGISTRY_PATH)
    isi_data = load_json(SNAPSHOT_DIR / "isi.json")

    # Load all 27 country snapshot files
    country_snapshots: dict[str, dict[str, Any]] = {}
    country_dir = SNAPSHOT_DIR / "country"
    for code in sorted(EU27_CODES):
        path = country_dir / f"{code}.json"
        country_snapshots[code] = load_json(path)

    # Load all 6 axis files
    axis_data: dict[int, dict[str, Any]] = {}
    axis_dir = SNAPSHOT_DIR / "axis"
    for n in range(1, 7):
        axis_data[n] = load_json(axis_dir / f"{n}.json")

    # Load v01 country files for audit data (best-effort)
    country_v01: dict[str, dict[str, Any] | None] = {}
    for code in sorted(EU27_CODES):
        v01_path = V01_DIR / "country" / f"{code}.json"
        if v01_path.is_file():
            country_v01[code] = load_json(v01_path)
        else:
            country_v01[code] = None

    print(f"  isi.json: {len(isi_data['countries'])} countries")
    print(f"  Country snapshots: {len(country_snapshots)}")
    print(f"  Axis files: {len(axis_data)}")
    print(f"  V01 audit files: {sum(1 for v in country_v01.values() if v is not None)}")
    print()

    # ------------------------------------------------------------------
    # A. Canonical results dataset
    # ------------------------------------------------------------------
    print("[A] Computing ranking and canonical dataset...")

    ranked = compute_ranking(isi_data)
    assert len(ranked) == EU27_COUNT, f"Expected {EU27_COUNT} countries, got {len(ranked)}"

    # CSV
    write_csv(DATA_EXPORTS / "isi_countries.csv", ISI_COUNTRIES_COLUMNS, ranked)

    # JSON with metadata block
    isi_countries_json = {
        "metadata": {
            "description": "ISI country scores and ranking — EU-27, 2024",
            "methodology_version": METHODOLOGY_VERSION,
            "year": YEAR,
            "window": isi_data.get("window", ""),
            "aggregation_rule": isi_data.get("aggregation_rule", ""),
            "formula": isi_data.get("formula", ""),
            "generated_by": "ISI_Paper/tools/results_pack/build_results_pack.py",
            "source": "backend/snapshots/v1.0/2024/isi.json",
        },
        "countries": ranked,
    }
    write_json(DATA_EXPORTS / "isi_countries.json", isi_countries_json)
    print(f"  Wrote isi_countries.csv ({len(ranked)} rows)")
    print(f"  Wrote isi_countries.json")
    print()

    # ------------------------------------------------------------------
    # B. Summary statistics
    # ------------------------------------------------------------------
    print("[B] Computing summary statistics...")

    summary_stats = compute_summary_stats(ranked, isi_data.get("statistics", {}))
    write_json(DATA_EXPORTS / "summary_stats.json", summary_stats)
    render_summary_stats_table(summary_stats, TABLES_TEX / "table_summary_stats.tex")

    # Per-axis stats
    axis_stats = compute_per_axis_stats(ranked)
    write_json(DATA_EXPORTS / "per_axis_stats.json", axis_stats)
    render_per_axis_stats_table(axis_stats, TABLES_TEX / "table_axis_stats.tex")

    # Validate stats
    for stat_name, v in summary_stats["validation_vs_isi_json"].items():
        status = "OK" if v["pass"] else "MISMATCH"
        print(f"  {stat_name}: computed={v['computed']:.8f}, expected={v['expected']:.8f} [{status}]")
    print(f"  median={summary_stats['median']:.8f}")
    print(f"  std(pop)={summary_stats['std_population']:.8f}")
    print()

    # ------------------------------------------------------------------
    # C. Full ranking table
    # ------------------------------------------------------------------
    print("[C] Generating ranking table...")

    render_ranking_table(ranked, TABLES_TEX / "table_ranking_full.tex")
    write_csv(DATA_EXPORTS / "ranking_full.csv", ISI_COUNTRIES_COLUMNS, ranked)
    print(f"  Wrote table_ranking_full.tex")
    print(f"  Wrote ranking_full.csv")
    print()

    # ------------------------------------------------------------------
    # D. Axis driver identification
    # ------------------------------------------------------------------
    print("[D] Computing axis drivers...")

    drivers = compute_axis_drivers(ranked)
    driver_columns = (
        "country", "country_name", "rank", "isi_composite",
        "max_axis", "max_axis_score", "second_max_axis", "second_max_score",
        "profile_type", "axis_mean", "axis_std", "spike_threshold", "spike_k",
    )
    write_csv(DATA_EXPORTS / "axis_drivers.csv", driver_columns, drivers)
    render_axis_drivers_table(drivers, TABLES_TEX / "table_axis_drivers_topbottom.tex")

    spike_count = sum(1 for d in drivers if d["profile_type"] == "single-spike")
    broad_count = sum(1 for d in drivers if d["profile_type"] == "broad-based")
    print(f"  Single-spike: {spike_count}, Broad-based: {broad_count}")
    print()

    # ------------------------------------------------------------------
    # E. Cross-axis correlation
    # ------------------------------------------------------------------
    print("[E] Computing correlation matrix...")

    corr = compute_correlation_matrix(ranked)
    corr_csv_rows: list[dict[str, Any]] = []
    for i, row in enumerate(corr["matrix"]):
        entry: dict[str, Any] = {"axis": AXIS_SLUGS[i]}
        for j, val in enumerate(row):
            entry[AXIS_SLUGS[j]] = val
        corr_csv_rows.append(entry)

    corr_columns = ("axis",) + AXIS_SLUGS
    write_csv(DATA_EXPORTS / "corr_axes_pearson.csv", corr_columns, corr_csv_rows)
    write_json(DATA_EXPORTS / "corr_axes_pearson.json", corr)
    render_correlation_table(corr, TABLES_TEX / "table_corr_matrix.tex")

    # Print top 3 correlations
    for pair in corr["pairs"][:3]:
        print(f"  {pair['axis_a']} × {pair['axis_b']}: r={pair['r']:.4f}")
    print()

    # ------------------------------------------------------------------
    # F. Distribution data + figures
    # ------------------------------------------------------------------
    print("[F] Distribution data and figures...")

    dist = compute_distribution_vectors(ranked)
    write_json(DATA_EXPORTS / "distribution_vectors.json", dist)

    figures_ok = try_render_figures(ranked, corr, FIGURES_DIR)
    if figures_ok:
        print("  Figures generated: hist_composite.pdf, boxplot_axes.pdf, corr_heatmap.pdf")
    else:
        msg = (
            "Figures could not be generated.\n"
            "matplotlib is not installed in the current Python environment.\n"
            "\n"
            "To generate figures, install matplotlib:\n"
            "  pip install matplotlib\n"
            "\n"
            "Then re-run:\n"
            "  python -m ISI_Paper.tools.results_pack.build_results_pack\n"
            "\n"
            "Required figures:\n"
            "  - figures/hist_composite.pdf (histogram of ISI composite scores)\n"
            "  - figures/boxplot_axes.pdf (box plot of axis distributions)\n"
            "  - figures/corr_heatmap.pdf (Pearson correlation heatmap)\n"
        )
        FIGURES_DIR.mkdir(parents=True, exist_ok=True)
        write_text(FIGURES_DIR / "figures_not_built.txt", msg)
        print("  matplotlib not available — wrote figures_not_built.txt")
    print()

    # ------------------------------------------------------------------
    # G. Country appendix pages
    # ------------------------------------------------------------------
    print("[G] Building country appendix pages...")

    rank_by_code: dict[str, int] = {r["country"]: r["rank"] for r in ranked}

    for code in sorted(EU27_CODES):
        snap = country_snapshots[code]
        v01 = country_v01.get(code)
        rank = rank_by_code[code]
        page = build_country_page(snap, v01, rank)
        write_json(COUNTRY_PAGES_DIR / f"{code}.json", page)

    print(f"  Wrote {len(EU27_CODES)} country page files")
    print()

    # ------------------------------------------------------------------
    # H. Integrity + reproducibility audit
    # ------------------------------------------------------------------
    print("[H] Writing audit files...")

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Git commit
    git_commit = "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
            timeout=5,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except Exception:
        pass

    # Input hashes
    input_hashes = collect_input_hashes(SNAPSHOT_DIR, REGISTRY_PATH)

    # Write run manifest (without output hashes first — we'll add them after)
    run_manifest: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "git_commit": git_commit,
        "methodology_version": METHODOLOGY_VERSION,
        "year": YEAR,
        "python_version": sys.version,
        "input_files": input_hashes,
        "output_files": {},  # placeholder
    }

    # Validation report
    validation_lines = validate_data(ranked, isi_data, summary_stats, country_snapshots)
    report_lines: list[str] = []
    report_lines.append("# ISI Results Evidence Pack — Validation Report")
    report_lines.append("")
    report_lines.append(f"**Generated:** {timestamp}")
    report_lines.append(f"**Git commit:** `{git_commit}`")
    report_lines.append(f"**Methodology:** {METHODOLOGY_VERSION}")
    report_lines.append(f"**Year:** {YEAR}")
    report_lines.append(f"**Scope:** EU-27")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Validation Checks")
    report_lines.append("")
    report_lines.extend(validation_lines)
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Input Artifacts")
    report_lines.append("")
    report_lines.append(f"Total input files hashed: {len(input_hashes)}")
    report_lines.append("")
    for path_str, h in sorted(input_hashes.items()):
        # Show relative path
        try:
            rel = str(Path(path_str).relative_to(REPO_ROOT))
        except ValueError:
            rel = path_str
        report_lines.append(f"- `{rel}`: `{h[:16]}...`")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Countries with Axis Score = 1.0")
    report_lines.append("")
    for r in ranked:
        for key in AXIS_ISI_KEYS:
            if r[key] == 1.0:
                report_lines.append(f"- **{r['country']}** ({r['country_name']}): `{key}` = 1.0")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Concentration Profile Summary")
    report_lines.append("")
    report_lines.append(f"- Single-spike countries: {spike_count}")
    report_lines.append(f"- Broad-based countries: {broad_count}")
    report_lines.append(f"- Spike detection threshold: k = {drivers[0]['spike_k']}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## Strongest Cross-Axis Correlations")
    report_lines.append("")
    for pair in corr["pairs"][:5]:
        report_lines.append(f"- {pair['axis_a']} × {pair['axis_b']}: r = {pair['r']:.4f}")
    report_lines.append("")
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("*End of validation report.*")
    report_lines.append("")

    write_text(AUDIT_DIR / "validation_report.md", "\n".join(report_lines))

    # Now compute output hashes and write final run manifest
    output_hashes = collect_output_hashes(OUTPUT_ROOT)
    run_manifest["output_files"] = output_hashes
    write_json(AUDIT_DIR / "run_manifest.json", run_manifest)

    # Re-hash the manifest itself and update (the manifest includes its own
    # hash as "self_hash": we skip this to avoid infinite loop; the manifest
    # is included in output_files by the second pass)

    print(f"  Wrote validation_report.md")
    print(f"  Wrote run_manifest.json ({len(output_hashes)} output files)")
    print()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("=" * 70)
    print("BUILD COMPLETE")
    print(f"  Output directory: {OUTPUT_ROOT}")
    print(f"  Data exports: {len(list(DATA_EXPORTS.rglob('*')))} files")
    print(f"  LaTeX tables: {len(list(TABLES_TEX.rglob('*.tex')))} files")
    print(f"  Figures: {'generated' if figures_ok else 'not built (missing matplotlib)'}")
    print(f"  Audit files: {len(list(AUDIT_DIR.rglob('*')))} files")
    print("=" * 70)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build()
