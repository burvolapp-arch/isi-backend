#!/usr/bin/env python3
"""
isi_api_v01.py — ISI Read-Only API Server

Serves pre-materialized JSON artifacts produced by
export_isi_backend_v01.py. Performs ZERO computation.
Every response is a direct file read from backend/v01/.

Endpoints:
    GET /                       → API metadata
    GET /countries              → All countries with summary scores
    GET /country/{code}         → Full country detail
    GET /country/{code}/axes    → All axis scores for one country
    GET /country/{code}/axis/{n} → Single axis detail for one country
    GET /axes                   → Axis registry
    GET /axis/{n}               → Full axis detail across all countries
    GET /isi                    → Composite ISI scores
    GET /health                 → Health check

No computation. No database. No state.
If a JSON file does not exist, the exporter has not been run.

Requires: fastapi, uvicorn (external dependencies for serving only)
"""

import json
import sys
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except ImportError:
    print(
        "FATAL: FastAPI not installed. Install with:\n"
        "  pip install fastapi uvicorn\n"
        "The API layer requires these two packages.",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parent / "v01"

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])

VALID_AXES = {1, 2, 3, 4, 5, 6}


# ---------------------------------------------------------------------------
# JSON file cache — loaded once at startup, never recomputed
# ---------------------------------------------------------------------------

_cache: dict[str, Any] = {}


def _load_json(filepath: Path) -> Any:
    """Load a JSON file. Returns parsed object or None if missing."""
    if not filepath.is_file():
        return None
    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _get_or_load(key: str, filepath: Path) -> Any:
    """Cache-through loader. Loads file once, serves from memory after."""
    if key not in _cache:
        data = _load_json(filepath)
        if data is None:
            return None
        _cache[key] = data
    return _cache[key]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ISI API",
    description="International Sovereignty Index — Read-Only API v0.1",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

@app.on_event("startup")
def validate_backend_data() -> None:
    """
    Verify that the backend data directory exists and contains
    the minimum required artifacts. Hard-fail if not.
    """
    if not BACKEND_ROOT.is_dir():
        print(
            f"WARNING: Backend data directory not found: {BACKEND_ROOT}\n"
            f"Run export_isi_backend_v01.py first to materialize JSON artifacts.",
            file=sys.stderr,
        )
        return

    required = ["meta.json", "axes.json", "countries.json", "isi.json"]
    missing = [f for f in required if not (BACKEND_ROOT / f).is_file()]
    if missing:
        print(
            f"WARNING: Missing backend artifacts: {missing}\n"
            f"Run export_isi_backend_v01.py to regenerate.",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root() -> dict:
    """API metadata."""
    data = _get_or_load("meta", BACKEND_ROOT / "meta.json")
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Backend data not materialized. Run export_isi_backend_v01.py.",
        )
    return data


@app.get("/health")
def health() -> dict:
    """Health check. Returns status of backend data availability."""
    meta_exists = (BACKEND_ROOT / "meta.json").is_file()
    countries_exist = (BACKEND_ROOT / "countries.json").is_file()
    isi_exists = (BACKEND_ROOT / "isi.json").is_file()

    country_files = list((BACKEND_ROOT / "country").glob("*.json")) if (BACKEND_ROOT / "country").is_dir() else []
    axis_files = list((BACKEND_ROOT / "axis").glob("*.json")) if (BACKEND_ROOT / "axis").is_dir() else []

    ok = meta_exists and countries_exist and isi_exists

    return {
        "status": "ok" if ok else "degraded",
        "backend_root": str(BACKEND_ROOT),
        "meta": meta_exists,
        "countries_summary": countries_exist,
        "isi_composite": isi_exists,
        "country_detail_files": len(country_files),
        "axis_detail_files": len(axis_files),
    }


@app.get("/countries")
def list_countries() -> Any:
    """All EU-27 countries with summary scores across all axes."""
    data = _get_or_load("countries", BACKEND_ROOT / "countries.json")
    if data is None:
        raise HTTPException(status_code=503, detail="countries.json not found.")
    return data


@app.get("/country/{code}")
def get_country(code: str) -> Any:
    """Full detail for one country: all axes, channels, partners, warnings."""
    code = code.upper().strip()
    if code not in EU27:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{code}' not in EU-27 scope.",
        )

    data = _get_or_load(f"country:{code}", BACKEND_ROOT / "country" / f"{code}.json")
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"Country file for '{code}' not materialized.",
        )
    return data


@app.get("/country/{code}/axes")
def get_country_axes(code: str) -> Any:
    """All axis scores for one country (extracted from full detail)."""
    code = code.upper().strip()
    if code not in EU27:
        raise HTTPException(status_code=404, detail=f"Country '{code}' not in EU-27 scope.")

    detail = _get_or_load(f"country:{code}", BACKEND_ROOT / "country" / f"{code}.json")
    if detail is None:
        raise HTTPException(status_code=503, detail=f"Country file for '{code}' not materialized.")

    return {
        "country": detail["country"],
        "country_name": detail["country_name"],
        "isi_composite": detail["isi_composite"],
        "axes": [
            {
                "axis_id": a["axis_id"],
                "axis_slug": a["axis_slug"],
                "score": a["score"],
                "classification": a["classification"],
            }
            for a in detail["axes"]
        ],
    }


@app.get("/country/{code}/axis/{axis_id}")
def get_country_axis(code: str, axis_id: int) -> Any:
    """Single axis detail for one country."""
    code = code.upper().strip()
    if code not in EU27:
        raise HTTPException(status_code=404, detail=f"Country '{code}' not in EU-27 scope.")
    if axis_id not in VALID_AXES:
        raise HTTPException(status_code=404, detail=f"Axis {axis_id} not valid. Must be 1-6.")

    detail = _get_or_load(f"country:{code}", BACKEND_ROOT / "country" / f"{code}.json")
    if detail is None:
        raise HTTPException(status_code=503, detail=f"Country file for '{code}' not materialized.")

    for a in detail["axes"]:
        if a["axis_id"] == axis_id:
            return {
                "country": detail["country"],
                "country_name": detail["country_name"],
                "axis": a,
            }

    raise HTTPException(status_code=404, detail=f"Axis {axis_id} not found for {code}.")


@app.get("/axes")
def list_axes() -> Any:
    """Axis registry: all six axes with metadata, channels, warnings."""
    data = _get_or_load("axes", BACKEND_ROOT / "axes.json")
    if data is None:
        raise HTTPException(status_code=503, detail="axes.json not found.")
    return data


@app.get("/axis/{axis_id}")
def get_axis(axis_id: int) -> Any:
    """Full axis detail: scores for all 27 countries, statistics, warnings."""
    if axis_id not in VALID_AXES:
        raise HTTPException(status_code=404, detail=f"Axis {axis_id} not valid. Must be 1-6.")

    data = _get_or_load(f"axis:{axis_id}", BACKEND_ROOT / "axis" / f"{axis_id}.json")
    if data is None:
        raise HTTPException(status_code=503, detail=f"Axis {axis_id} detail not materialized.")
    return data


@app.get("/isi")
def get_isi() -> Any:
    """Composite ISI scores for all countries."""
    data = _get_or_load("isi", BACKEND_ROOT / "isi.json")
    if data is None:
        raise HTTPException(status_code=503, detail="isi.json not found.")
    return data


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("Install uvicorn: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    print(f"ISI API v0.1 — serving from {BACKEND_ROOT}")
    print(f"Docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
