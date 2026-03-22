"""
pipeline.ingest — Source-specific ingestion modules for the ISI pipeline.

Each module:
    1. Reads ONE raw data source
    2. Produces BilateralDataset(s) in the canonical schema
    3. Applies source-specific normalization
    4. Returns provenance metadata

Modules:
    - bis_lbs:   BIS Locational Banking Statistics (CSV, SDMX format)
    - imf_cpis:  IMF CPIS portfolio investment (CSV, wide format)
    - comtrade:  UN Comtrade bilateral trade (CSV, bulk download)
    - sipri:     SIPRI arms transfers (CSV, Trade Register)
    - logistics: Eurostat/OECD logistics (CSV, Eurostat SDMX format)
"""
