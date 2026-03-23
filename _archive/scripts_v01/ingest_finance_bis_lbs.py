"""ISI v0.1 — BIS Locational Banking Statistics Ingestion (Raw, 2024-Q4)"""

from pathlib import Path

import requests

BIS_API_BASE = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_LBS_D_PUB/1.0"

# Dimension order (12):
# FREQ.L_MEASURE.L_POSITION.L_INSTR.L_DENOM.L_CURR_TYPE.L_PARENT_CTY.L_REP_BANK_TYPE.L_REP_CTY.L_CP_SECTOR.L_CP_COUNTRY.L_POS_TYPE
#
# Fixed values:
#   FREQ = Q (quarterly)
#   L_MEASURE = S (stock / outstanding amounts)
#   L_POSITION = C (cross-border)
#   L_INSTR = A (all instruments)
#   L_DENOM = TO1 (all currencies)
#   L_CURR_TYPE = A (all currency types)
#   L_PARENT_CTY = 5J (all parent countries)
#   L_REP_BANK_TYPE = A (all bank types)
#   L_REP_CTY = (empty = all reporting countries)
#   L_CP_SECTOR = A (all counterparty sectors)
#   L_CP_COUNTRY = (empty = all counterparty countries)
#   L_POS_TYPE = N (net)
#
# Period: 2024-Q4 (end-of-year stock)

SDMX_KEY = "Q.S.C.A.TO1.A.5J.A..A..N"

QUERY_PARAMS = {
    "startPeriod": "2024-Q4",
    "endPeriod": "2024-Q4",
    "format": "csv",
}

OUTPUT_DIR = Path("data/raw/finance")
OUTPUT_FILE = OUTPUT_DIR / "bis_lbs_2024_raw.csv"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    url = f"{BIS_API_BASE}/{SDMX_KEY}"
    print(f"Fetching BIS LBS (2024-Q4) ...")
    response = requests.get(url, params=QUERY_PARAMS, timeout=300)
    response.raise_for_status()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(response.text)

    print(f"Saved {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
