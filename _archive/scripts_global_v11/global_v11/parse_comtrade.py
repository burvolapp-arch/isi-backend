#!/usr/bin/env python3
"""ISI v1.1 — UN Comtrade Parser: Bilateral Trade Data for Non-EU Countries

Parses UN Comtrade bulk download CSV files into the same normalized flat
format used by the existing Eurostat Comext pipelines. This allows the
global axis computations (Technology, Critical Inputs) to consume Comtrade
data with identical schema expectations.

UN Comtrade CSV schema (bulk download):
  Classification, Year, Period, PeriodDesc, AggLevel,
  IsLeaf, ReporterCode, ReporterISO, ReporterDesc,
  PartnerCode, PartnerISO, PartnerDesc,
  FlowCode, FlowDesc, CmdCode, CmdDesc,
  QtyUnitCode, QtyUnitAbbr, Qty, AltQtyUnitCode,
  AltQtyUnitAbbr, AltQty, NetWgt, GrossWgt,
  Cifvalue, Fobvalue, PrimaryValue, LegacyEstimation,
  IsReported

Output (normalized flat CSV):
  reporter,partner,product_code,hs_level,year,value
  (matching the Comext flat file schema expected by tech/critical_inputs scripts)

Country code handling:
  - Comtrade uses ISO-3 numeric codes (ReporterCode) and ISO-3 alpha (ReporterISO)
  - We convert to ISO-2 alpha using the mapping table
  - Partners with ISO-2 = "XX" or unmapped are preserved as-is
    (they represent aggregates like "World" and are filtered downstream)

Scope:
  This parser processes ALL reporters and partners in the input file.
  Scope filtering to Phase 1 countries happens downstream.

Constraint spec references:
  - Section 7.4 (HS-6 granularity limitation for non-EU)
  - Section 7.5 (temporal mixing rules)
  - LIM-002 (HS6 vs CN8 granularity gap)
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ISO-3 alpha → ISO-2 alpha mapping for Phase 1 + common partners
# This covers reporters AND partners that may appear in Comtrade data.
ISO3_TO_ISO2: dict[str, str] = {
    # Phase 1 expansion countries
    "AUS": "AU",
    "CHN": "CN",
    "GBR": "GB",
    "JPN": "JP",
    "KOR": "KR",
    "NOR": "NO",
    "USA": "US",
    # Common trade partners (for partner column resolution)
    "DEU": "DE",
    "FRA": "FR",
    "ITA": "IT",
    "NLD": "NL",
    "BEL": "BE",
    "ESP": "ES",
    "AUT": "AT",
    "POL": "PL",
    "SWE": "SE",
    "IRL": "IE",
    "DNK": "DK",
    "FIN": "FI",
    "PRT": "PT",
    "CZE": "CZ",
    "ROU": "RO",
    "HUN": "HU",
    "SVK": "SK",
    "BGR": "BG",
    "HRV": "HR",
    "LTU": "LT",
    "SVN": "SI",
    "LVA": "LV",
    "EST": "EE",
    "CYP": "CY",
    "LUX": "LU",
    "MLT": "MT",
    "GRC": "GR",  # Greece: ISO-3 GRC → ISO-2 GR (not Eurostat "EL")
    # Major non-EU trade partners
    "TWN": "TW",
    "SGP": "SG",
    "MYS": "MY",
    "THA": "TH",
    "VNM": "VN",
    "IDN": "ID",
    "PHL": "PH",
    "IND": "IN",
    "BRA": "BR",
    "MEX": "MX",
    "CAN": "CA",
    "CHE": "CH",
    "ISR": "IL",
    "SAU": "SA",
    "ARE": "AE",
    "ZAF": "ZA",
    "RUS": "RU",
    "TUR": "TR",
    "NZL": "NZ",
}


def parse_comtrade_bulk(
    input_path: Path,
    output_path: Path,
    flow_filter: str = "M",  # M = imports
    hs_codes: set[str] | None = None,
    hs_level: int = 6,
    year_range: tuple[int, int] | None = None,
) -> dict[str, int]:
    """Parse UN Comtrade bulk CSV into normalized flat format.

    Args:
        input_path: Path to raw Comtrade CSV.
        output_path: Path for output normalized CSV.
        flow_filter: "M" for imports, "X" for exports. Default imports.
        hs_codes: Optional set of HS code prefixes to filter (e.g., {"8541", "8542"}).
                  If None, all codes are included.
        hs_level: HS classification level (2, 4, or 6). Default 6.
        year_range: Optional (min_year, max_year) inclusive filter.

    Returns:
        Stats dict with counts.
    """
    if not input_path.is_file():
        print(f"FATAL: Comtrade input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {
        "rows_read": 0,
        "rows_filtered_flow": 0,
        "rows_filtered_hs": 0,
        "rows_filtered_year": 0,
        "rows_unmapped_reporter": 0,
        "rows_written": 0,
        "reporters_seen": set(),
        "partners_seen": set(),
    }

    with open(input_path, "r", encoding="utf-8", newline="") as fin, \
         open(output_path, "w", encoding="utf-8", newline="") as fout:

        reader = csv.DictReader(fin)
        writer = csv.writer(fout)
        writer.writerow(["reporter", "partner", "product_code", "hs_level", "year", "value"])

        for row in reader:
            stats["rows_read"] += 1

            # Flow filter (imports only by default)
            flow_code = row.get("FlowCode", row.get("flowCode", ""))
            if flow_filter and str(flow_code) not in (flow_filter, _flow_code_numeric(flow_filter)):
                stats["rows_filtered_flow"] += 1
                continue

            # Year filter
            year_str = row.get("Year", row.get("year", ""))
            try:
                year = int(year_str)
            except (ValueError, TypeError):
                continue
            if year_range and (year < year_range[0] or year > year_range[1]):
                stats["rows_filtered_year"] += 1
                continue

            # HS code filter
            cmd_code = row.get("CmdCode", row.get("cmdCode", "")).strip()
            if hs_codes:
                matched = False
                for prefix in hs_codes:
                    if cmd_code.startswith(prefix):
                        matched = True
                        break
                if not matched:
                    stats["rows_filtered_hs"] += 1
                    continue

            # Country code resolution
            reporter_iso3 = row.get("ReporterISO", row.get("reporterISO", "")).strip()
            partner_iso3 = row.get("PartnerISO", row.get("partnerISO", "")).strip()

            reporter_iso2 = ISO3_TO_ISO2.get(reporter_iso3, reporter_iso3)
            partner_iso2 = ISO3_TO_ISO2.get(partner_iso3, partner_iso3)

            if reporter_iso2 == reporter_iso3 and len(reporter_iso3) == 3:
                stats["rows_unmapped_reporter"] += 1

            # Value resolution (prefer PrimaryValue, fallback Cifvalue)
            value_str = row.get("PrimaryValue", row.get("primaryValue", ""))
            if not value_str or value_str.strip() == "":
                value_str = row.get("Cifvalue", row.get("cifvalue", "0"))
            try:
                value = float(value_str)
            except (ValueError, TypeError):
                value = 0.0

            if value <= 0:
                continue

            writer.writerow([
                reporter_iso2,
                partner_iso2,
                cmd_code[:hs_level] if len(cmd_code) >= hs_level else cmd_code,
                hs_level,
                year,
                value,
            ])
            stats["rows_written"] += 1
            stats["reporters_seen"].add(reporter_iso2)
            stats["partners_seen"].add(partner_iso2)

    # Convert sets to counts for JSON serialization
    stats["n_reporters"] = len(stats["reporters_seen"])
    stats["n_partners"] = len(stats["partners_seen"])
    del stats["reporters_seen"]
    del stats["partners_seen"]

    return stats


def _flow_code_numeric(flow_str: str) -> str:
    """Map flow letter to Comtrade numeric code."""
    return {"M": "1", "X": "2", "R": "3"}.get(flow_str, flow_str)


# ---------------------------------------------------------------------------
# Axis-specific entry points
# ---------------------------------------------------------------------------

def parse_comtrade_for_tech(
    input_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Parse Comtrade data for Technology axis (HS 8541, 8542 — semiconductors).

    Uses HS-6 level. LIM-002 applies: CN8 granularity not available.
    """
    if input_path is None:
        input_path = (
            PROJECT_ROOT / "data" / "raw" / "comtrade"
            / "comtrade_semiconductors_2022_2024.csv"
        )
    if output_dir is None:
        output_dir = PROJECT_ROOT / "data" / "processed" / "global_v11" / "tech"

    out_path = output_dir / "comtrade_semiconductor_2022_2024_flat.csv"

    print(f"Parsing Comtrade for Technology axis...")
    print(f"  Input:  {input_path}")
    print(f"  Output: {out_path}")

    stats = parse_comtrade_bulk(
        input_path=input_path,
        output_path=out_path,
        flow_filter="M",
        hs_codes={"8541", "8542"},
        hs_level=6,
        year_range=(2022, 2024),
    )

    print(f"  Stats: {stats}")
    return out_path


def parse_comtrade_for_critical_inputs(
    input_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Parse Comtrade data for Critical Inputs axis.

    Uses HS-6 level. Material group mapping must use HS-6 prefixes
    since CN8 is not available. LIM-002 applies.
    """
    if input_path is None:
        input_path = (
            PROJECT_ROOT / "data" / "raw" / "comtrade"
            / "comtrade_critical_materials_2022_2024.csv"
        )
    if output_dir is None:
        output_dir = PROJECT_ROOT / "data" / "processed" / "global_v11" / "critical_inputs"

    out_path = output_dir / "comtrade_critical_inputs_2022_2024_flat.csv"

    print(f"Parsing Comtrade for Critical Inputs axis...")
    print(f"  Input:  {input_path}")
    print(f"  Output: {out_path}")

    # No HS filter — the raw file should already be pre-filtered to
    # critical materials HS codes. If not, a mapping filter is applied
    # downstream.
    stats = parse_comtrade_bulk(
        input_path=input_path,
        output_path=out_path,
        flow_filter="M",
        hs_codes=None,  # rely on pre-filtered raw file
        hs_level=6,
        year_range=(2022, 2024),
    )

    print(f"  Stats: {stats}")
    return out_path


def parse_comtrade_for_energy(
    input_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Parse Comtrade data for Energy axis (fuel imports).

    Energy axis uses fuel-category trade flows.
    HS codes: 2701 (coal), 2709 (crude oil), 2710 (petroleum products),
              2711 (natural gas), 2716 (electricity).
    """
    if input_path is None:
        input_path = (
            PROJECT_ROOT / "data" / "raw" / "comtrade"
            / "comtrade_energy_fuels_2022_2024.csv"
        )
    if output_dir is None:
        output_dir = PROJECT_ROOT / "data" / "processed" / "global_v11" / "energy"

    out_path = output_dir / "comtrade_energy_fuels_2022_2024_flat.csv"

    print(f"Parsing Comtrade for Energy axis...")
    print(f"  Input:  {input_path}")
    print(f"  Output: {out_path}")

    stats = parse_comtrade_bulk(
        input_path=input_path,
        output_path=out_path,
        flow_filter="M",
        hs_codes={"2701", "2709", "2710", "2711", "2716"},
        hs_level=6,
        year_range=(2022, 2024),
    )

    print(f"  Stats: {stats}")
    return out_path


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="UN Comtrade parser for ISI v1.1 global expansion"
    )
    parser.add_argument(
        "axis",
        choices=["tech", "critical_inputs", "energy", "all"],
        help="Which axis to parse Comtrade data for",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Override input file path",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Override output directory",
    )

    args = parser.parse_args()

    print("=" * 68)
    print("ISI v1.1 — UN Comtrade Parser (Global Phase 1)")
    print("=" * 68)
    print()

    if args.axis in ("tech", "all"):
        parse_comtrade_for_tech(args.input, args.output_dir)
        print()

    if args.axis in ("critical_inputs", "all"):
        parse_comtrade_for_critical_inputs(args.input, args.output_dir)
        print()

    if args.axis in ("energy", "all"):
        parse_comtrade_for_energy(args.input, args.output_dir)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
