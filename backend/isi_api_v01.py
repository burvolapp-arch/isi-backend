#!/usr/bin/env python3
"""
isi_api_v01.py — ISI API Server (hardened, v0.5)

Serves pre-materialized JSON artifacts produced by
export_isi_backend_v01.py and a deterministic scenario simulation
endpoint. Read endpoints are direct file reads from backend/v01/.
The POST /scenario endpoint performs bounded, validated computation
using the SAME data source as baseline endpoints.

Endpoints:
    GET /                       → API metadata
    GET /countries              → All countries with summary scores
    GET /country/{code}         → Full country detail
    GET /country/{code}/axes    → All axis scores for one country
    GET /country/{code}/axis/{n} → Single axis detail for one country
    GET /axes                   → Axis registry
    GET /axis/{n}               → Full axis detail across all countries
    GET /isi                    → Composite ISI scores
    POST /scenario              → What-if scenario simulation
    GET /health                 → Health check
    GET /ready                  → Readiness probe (Kubernetes / Railway)

No computation. No database. No state.
If a JSON file does not exist, the exporter has not been run.

Environment variables:
    ENV               — "dev" or "prod" (default: "prod")
    ALLOWED_ORIGINS   — Comma-separated CORS origins (default: none)
    ENABLE_DOCS       — "1" to force-enable /docs in prod
    REQUIRE_DATA      — "1" to hard-fail startup if backend/v01 missing
    REDIS_URL         — Optional Redis URL for distributed rate limiting

Requires: fastapi, uvicorn, gunicorn, slowapi
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from starlette.middleware.gzip import GZipMiddleware
except ImportError:
    print(
        "FATAL: FastAPI not installed. Install with:\n"
        "  pip install -r requirements.txt\n",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
except ImportError:
    print(
        "FATAL: slowapi not installed. Install with:\n"
        "  pip install -r requirements.txt\n",
        file=sys.stderr,
    )
    sys.exit(1)

from backend.security import (  # noqa: I001
    ETagMiddleware,
    RequestIdMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    verify_manifest,
)

from backend.scenario import (  # noqa: I001, E402
    CANONICAL_AXIS_KEYS,
    MAX_ADJUSTMENT,
    SCENARIO_VERSION,
    VALID_CANONICAL_KEYS,
    ScenarioRequest,
    ScenarioResponse,
    simulate,
)


# ---------------------------------------------------------------------------
# Logging configuration — structured JSON to stdout
# ---------------------------------------------------------------------------

_log_level = logging.DEBUG if os.getenv("ENV", "prod") == "dev" else logging.INFO
logging.basicConfig(
    level=_log_level,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("isi.api")


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

ENV = os.getenv("ENV", "prod").lower().strip()
ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "").strip()
ENABLE_DOCS = os.getenv("ENABLE_DOCS", "").strip() == "1"
REQUIRE_DATA = os.getenv("REQUIRE_DATA", "").strip() == "1"
REDIS_URL = os.getenv("REDIS_URL", "").strip() or None


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parent / "v01"

EU27 = sorted([
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
])
EU27_SET = frozenset(EU27)

VALID_AXES = {1, 2, 3, 4, 5, 6}

# Strict country code regex: exactly 2 alpha characters
_COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

_rate_storage: str | None = REDIS_URL if REDIS_URL else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["120/minute"],
    storage_uri=_rate_storage,
    strategy="fixed-window",
)


# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------

def _build_docs_kwargs() -> dict[str, Any]:
    """Determine docs/redoc/openapi URL availability."""
    if ENV == "prod" and not ENABLE_DOCS:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc"}


# ---------------------------------------------------------------------------
# Lifespan — replaces deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle for the ISI API.

    Startup: validate backend data, verify manifest integrity.
    If REQUIRE_DATA=1 and data is missing or corrupt, exit immediately.
    """
    logger.info(json.dumps({
        "event": "startup",
        "env": ENV,
        "require_data": REQUIRE_DATA,
        "cors_origins": len(_CORS_ORIGINS),
        "docs_enabled": ENABLE_DOCS or ENV == "dev",
        "rate_limit_backend": "redis" if REDIS_URL else "memory",
    }))

    data_present = _data_available()

    # Integrity verification
    if BACKEND_ROOT.is_dir():
        result = verify_manifest(BACKEND_ROOT)
        _integrity.update(result)
        if result["manifest_present"]:
            if result["verified"]:
                logger.info(json.dumps({
                    "event": "manifest_verified",
                    "files_checked": result["files_checked"],
                }))
            else:
                for err in result["errors"]:
                    logger.error(json.dumps({
                        "event": "manifest_error",
                        "error": err,
                    }))
                if REQUIRE_DATA:
                    logger.error(json.dumps({
                        "event": "startup_abort",
                        "reason": "Manifest integrity check failed",
                    }))
                    sys.exit(1)

    if not data_present:
        if REQUIRE_DATA:
            logger.error(json.dumps({
                "event": "startup_abort",
                "reason": "REQUIRE_DATA=1 but backend data not found",
            }))
            sys.exit(1)
        else:
            logger.warning(json.dumps({
                "event": "startup_degraded",
                "reason": "Backend data directory not found or incomplete",
            }))

    yield  # App is running — serve requests

    # Shutdown (nothing to clean up for a read-only API)
    logger.info(json.dumps({"event": "shutdown"}))


app = FastAPI(
    title="ISI API",
    description="International Sovereignty Index — API v0.2",
    version="0.2.0",
    lifespan=_lifespan,
    **_build_docs_kwargs(),
)

# Attach rate limiter
app.state.limiter = limiter


# ---------------------------------------------------------------------------
# CORS — Production origin policy
#
# Strict allow-list. No wildcard origins.
#   - Production:  https://isi.internationalsovereignty.org
#   - Legacy/preview: https://isi-frontend.vercel.app
#   - Dev:         http://localhost:3000
#   - Regex catch-all for future *.internationalsovereignty.org subdomains
#
# Credentials disabled (no cookies/auth headers cross-origin).
# Only GET + OPTIONS (preflight) permitted.
# ALLOWED_ORIGINS env var can extend the list at deploy time.
# ---------------------------------------------------------------------------

PRODUCTION_ORIGINS: list[str] = [
    "https://isi.internationalsovereignty.org",
    "https://isi-frontend.vercel.app",
]

DEV_ORIGINS: list[str] = [
    "http://localhost:3000",
]

_CORS_ORIGINS: list[str] = PRODUCTION_ORIGINS + DEV_ORIGINS

# Extend with any deploy-time overrides (Railway env var)
if ALLOWED_ORIGINS_RAW:
    for _o in ALLOWED_ORIGINS_RAW.split(","):
        _o = _o.strip()
        if _o and _o not in _CORS_ORIGINS:
            _CORS_ORIGINS.append(_o)

# Regex: match any current or future subdomain of internationalsovereignty.org
_CORS_ORIGIN_REGEX = r"https:\/\/.*\.internationalsovereignty\.org"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_origin_regex=_CORS_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=3600,
)

logger.info("CORS configured for: %s (regex: %s)", _CORS_ORIGINS, _CORS_ORIGIN_REGEX)


# ---------------------------------------------------------------------------
# Security & performance middleware (order matters: last registered = outermost)
# Starlette runs middleware in reverse registration order.
# Registration order here:  CORS → SecurityHeaders → ETag → RequestSizeLimit → RequestId → GZip
# Execution order (outermost first): GZip → RequestId → RequestSizeLimit → ETag → SecurityHeaders → CORS
# ---------------------------------------------------------------------------

app.add_middleware(SecurityHeadersMiddleware, enable_hsts=(ENV == "prod"))
app.add_middleware(ETagMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)


# ---------------------------------------------------------------------------
# Rate-limit error handler
# ---------------------------------------------------------------------------

@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
        headers={"Retry-After": "60"},
    )


# ---------------------------------------------------------------------------
# Validation error handler — 422 with received_payload
#
# When using `body: dict` as a parameter, FastAPI validates that the request
# body is valid JSON. If parsing fails, FastAPI raises RequestValidationError
# which defaults to 422. We intercept it here and return a structured
# VALIDATION_ERROR with the raw payload echoed back. This catches malformed
# JSON (missing Content-Type, non-JSON body, truncated body, etc.)
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id: str = getattr(request.state, "request_id", "unknown")

    # Attempt to echo back what the client sent (best-effort)
    received_payload: Any = None
    try:
        received_payload = exc.body  # FastAPI attaches raw body to the exception
    except Exception:
        pass

    errors = exc.errors()
    detail_items = []
    for e in errors:
        loc_parts = [str(p) for p in e.get("loc", []) if p != "body"]
        detail_items.append({
            "field": ".".join(loc_parts) if loc_parts else "body",
            "message": e.get("msg", "Validation failed"),
        })

    logger.warning(json.dumps({
        "event": "validation_error",
        "request_id": request_id,
        "path": request.url.path,
        "errors": detail_items,
        "received_payload": received_payload if isinstance(received_payload, (dict, list, str, type(None))) else str(received_payload),
    }))

    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "detail": detail_items[0] if len(detail_items) == 1 else detail_items,
            "received_payload": received_payload if isinstance(received_payload, (dict, list, str, type(None))) else str(received_payload),
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# Global exception handler — never leak internals
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(json.dumps({
        "event": "unhandled_exception",
        "exception_type": type(exc).__name__,
        "request_id": request_id,
        "path": request.url.path,
    }))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


# ---------------------------------------------------------------------------
# JSON file cache — loaded once at startup, never recomputed
# ---------------------------------------------------------------------------

_cache: dict[str, Any] = {}
_integrity: dict[str, Any] = {}


def _load_json(filepath: Path) -> Any:
    """Load a JSON file. Returns parsed object or None if missing."""
    if not filepath.is_file():
        return None
    with open(filepath, encoding="utf-8") as fh:
        return json.load(fh)


def _get_or_load(key: str, filepath: Path) -> Any:
    """Cache-through loader. Loads file once, serves from memory after."""
    if key not in _cache:
        data = _load_json(filepath)
        if data is None:
            return None
        _cache[key] = data
    return _cache[key]


def _data_available() -> bool:
    """Check if core data files exist."""
    return (
        BACKEND_ROOT.is_dir()
        and (BACKEND_ROOT / "meta.json").is_file()
        and (BACKEND_ROOT / "countries.json").is_file()
        and (BACKEND_ROOT / "isi.json").is_file()
    )


def _count_data_files() -> dict[str, int]:
    """Count data files without leaking paths."""
    country_dir = BACKEND_ROOT / "country"
    axis_dir = BACKEND_ROOT / "axis"
    return {
        "country_files": len(list(country_dir.glob("*.json"))) if country_dir.is_dir() else 0,
        "axis_files": len(list(axis_dir.glob("*.json"))) if axis_dir.is_dir() else 0,
    }


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _validate_country_code(code: str) -> str:
    """Validate and normalise a country code. Raises 404 if invalid."""
    code = code.strip().upper()
    if not _COUNTRY_RE.match(code):
        raise HTTPException(
            status_code=404,
            detail=f"Country '{code}' not in EU-27 scope.",
        )
    if code not in EU27_SET:
        raise HTTPException(
            status_code=404,
            detail=f"Country '{code}' not in EU-27 scope.",
        )
    return code


def _validate_axis_id(axis_id: int) -> int:
    """Validate axis ID. Raises 404 if invalid."""
    if axis_id not in VALID_AXES:
        raise HTTPException(
            status_code=404,
            detail=f"Axis {axis_id} not valid. Must be 1-6.",
        )
    return axis_id


# ---------------------------------------------------------------------------
# Endpoints — contract-frozen, response schemas unchanged
# ---------------------------------------------------------------------------

@app.get("/")
@limiter.limit("60/minute")
async def root(request: Request) -> dict:
    """API metadata."""
    data = _get_or_load("meta", BACKEND_ROOT / "meta.json")
    if data is None:
        raise HTTPException(
            status_code=503,
            detail="Backend data not materialized. Run export_isi_backend_v01.py.",
        )
    return data


@app.get("/health", include_in_schema=False)
async def health(request: Request) -> JSONResponse:
    """Liveness probe — primitive, isolated, zero dependencies.

    ALWAYS returns HTTP 200 with {"status": "ok", "version": "v0.4"}.
    No file I/O, no state reads, no cache access, no computation.
    Survives any internal failure. Safe for Railway healthcheck probing.

    Rich diagnostics (data_present, file counts) live in /ready.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "version": "v0.4"},
    )


@app.get("/ready")
@limiter.limit("60/minute")
async def ready(request: Request) -> JSONResponse:
    """Readiness probe — rich diagnostics, always 200.

    Reports data availability, file counts, integrity status, and version.
    HTTP status is always 200 so orchestrator probes never choke.
    Business-level readiness is indicated by the 'ready' field in the body.
    """
    try:
        data_present = _data_available()
        counts = _count_data_files() if BACKEND_ROOT.is_dir() else {"country_files": 0, "axis_files": 0}
        file_count = counts["country_files"] + counts["axis_files"]
    except Exception:
        data_present = False
        file_count = 0

    integrity_ok = _integrity.get("verified", True)  # True if no manifest
    ready_flag = data_present and integrity_ok

    body = {
        "ready": ready_flag,
        "status": "healthy" if data_present else "degraded",
        "version": "0.1.0",
        "data_present": data_present,
        "data_file_count": file_count,
        "integrity_verified": _integrity.get("verified") if _integrity.get("manifest_present") else None,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    return JSONResponse(status_code=200, content=body)


@app.get("/countries")
@limiter.limit("30/minute")
async def list_countries(request: Request) -> Any:
    """All EU-27 countries with summary scores across all axes."""
    data = _get_or_load("countries", BACKEND_ROOT / "countries.json")
    if data is None:
        raise HTTPException(status_code=503, detail="countries.json not found.")
    return data


@app.get("/country/{code}")
@limiter.limit("30/minute")
async def get_country(code: str, request: Request) -> Any:
    """Full detail for one country: all axes, channels, partners, warnings."""
    code = _validate_country_code(code)

    data = _get_or_load(f"country:{code}", BACKEND_ROOT / "country" / f"{code}.json")
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=f"Country file for '{code}' not materialized.",
        )
    return data


@app.get("/country/{code}/axes")
@limiter.limit("30/minute")
async def get_country_axes(code: str, request: Request) -> Any:
    """All axis scores for one country (extracted from full detail)."""
    code = _validate_country_code(code)

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
@limiter.limit("30/minute")
async def get_country_axis(code: str, axis_id: int, request: Request) -> Any:
    """Single axis detail for one country."""
    code = _validate_country_code(code)
    axis_id = _validate_axis_id(axis_id)

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
@limiter.limit("30/minute")
async def list_axes(request: Request) -> Any:
    """Axis registry: all six axes with metadata, channels, warnings."""
    data = _get_or_load("axes", BACKEND_ROOT / "axes.json")
    if data is None:
        raise HTTPException(status_code=503, detail="axes.json not found.")
    return data


@app.get("/axis/{axis_id}")
@limiter.limit("30/minute")
async def get_axis(axis_id: int, request: Request) -> Any:
    """Full axis detail: scores for all 27 countries, statistics, warnings."""
    axis_id = _validate_axis_id(axis_id)

    data = _get_or_load(f"axis:{axis_id}", BACKEND_ROOT / "axis" / f"{axis_id}.json")
    if data is None:
        raise HTTPException(status_code=503, detail=f"Axis {axis_id} detail not materialized.")
    return data


@app.get("/isi")
@limiter.limit("120/minute")
async def get_isi(request: Request) -> Any:
    """Composite ISI scores for all countries.

    Primary comparative-page endpoint. Rate-limited at 120/min (generous).
    Data is served from memory cache; zero blocking I/O after first load.
    """
    data = _get_or_load("isi", BACKEND_ROOT / "isi.json")
    if data is None:
        raise HTTPException(status_code=503, detail="isi.json not found.")
    return data


# ---------------------------------------------------------------------------
# POST /scenario — Contract-first scenario simulation (scenario-v1)
#
# Pydantic-validated request AND response. No partial responses.
# Input:  ScenarioRequest  {"country": "SE", "adjustments": {...}}
# Output: ScenarioResponse {country, baseline, simulated, delta, meta}
# Computation: simulated = clamp(baseline * (1 + adj), 0, 1)
# Uses the SAME _get_or_load("isi", ...) data source as GET /isi.
#
# Error contract:
#   400 → BAD_INPUT: invalid country, unknown axis key, out-of-range value
#   404 → COUNTRY_NOT_FOUND: country_code not in baseline dataset
#   422 → VALIDATION_ERROR: malformed JSON (FastAPI catches this)
#   500 → INTERNAL_ERROR: computation or serialization failure
#   405 → GET on /scenario (method not allowed)
# ---------------------------------------------------------------------------

@app.get("/scenario", include_in_schema=False)
async def scenario_get(request: Request) -> JSONResponse:
    """GET /scenario → 405 Method Not Allowed."""
    return JSONResponse(
        status_code=405,
        content={"error": "METHOD_NOT_ALLOWED", "message": "Use POST."},
        headers={"Allow": "POST, OPTIONS"},
    )


@app.get("/scenario/schema")
@limiter.limit("60/minute")
async def scenario_schema(request: Request) -> JSONResponse:
    """Debug/alignment route: returns the scenario contract.

    Shows AXIS_KEYS, example request, example success response, bounds.
    """
    return JSONResponse(
        status_code=200,
        content={
            "axis_keys": list(CANONICAL_AXIS_KEYS),
            "bounds": {"min": -MAX_ADJUSTMENT, "max": MAX_ADJUSTMENT},
            "version": SCENARIO_VERSION,
            "example_request": {
                "country": "SE",
                "adjustments": {
                    "energy_external_supplier_concentration": -0.15,
                    "defense_external_supplier_concentration": 0.10,
                },
            },
            "example_response": {
                "country": "SE",
                "baseline": {
                    "composite": 0.1967,
                    "rank": 15,
                    "classification": "mildly_concentrated",
                    "axes": {k: 0.20 for k in CANONICAL_AXIS_KEYS},
                },
                "simulated": {
                    "composite": 0.1950,
                    "rank": 16,
                    "classification": "mildly_concentrated",
                    "axes": {k: 0.20 for k in CANONICAL_AXIS_KEYS},
                },
                "delta": {
                    "composite": -0.0017,
                    "rank": 1,
                    "axes": {k: 0.0 for k in CANONICAL_AXIS_KEYS},
                },
                "meta": {
                    "version": SCENARIO_VERSION,
                    "timestamp": "2026-02-18T12:00:00+00:00",
                    "bounds": {"min": -0.2, "max": 0.2},
                },
            },
        },
    )


@app.post("/scenario", response_model=ScenarioResponse)
@limiter.limit("60/minute")
async def scenario(request: Request, body: dict) -> JSONResponse:
    """Contract-first scenario simulation (scenario-v1).

    Pydantic-validated request and response. Never returns partial data.

    Input:  {"country": "SE", "adjustments": {"defense_external_supplier_concentration": 0.10}}
    Output: Full ScenarioResponse with baseline, simulated, delta, meta blocks.

    NOTE: `body: dict` uses FastAPI native body injection to avoid
    BaseHTTPMiddleware body-stream deadlocks with Gunicorn/Uvicorn workers.
    We then validate via ScenarioRequest ourselves for strict 400 errors.
    """
    request_id: str = getattr(request.state, "request_id", "unknown")

    # --- Step 1: Validate input through Pydantic ---
    try:
        req = ScenarioRequest(**body)
    except Exception as exc:
        # Extract meaningful message from Pydantic ValidationError
        message = str(exc)
        # Pydantic v2 ValidationError has .errors()
        details: dict[str, Any] | list[Any] | None = None
        if hasattr(exc, "errors"):
            errors = exc.errors()  # type: ignore[union-attr]
            details = [
                {
                    "field": ".".join(str(p) for p in e.get("loc", [])),
                    "message": e.get("msg", ""),
                }
                for e in errors
            ]
            if len(details) == 1:
                message = details[0]["message"]
                details = details[0]

        logger.warning(json.dumps({
            "event": "scenario_bad_input",
            "request_id": request_id,
            "error": message[:500],
        }))

        return JSONResponse(
            status_code=400,
            content={
                "error": "BAD_INPUT",
                "message": message[:500],
                **({"details": details} if details else {}),
            },
        )

    country_code = req.country
    adjustments = req.adjustments

    # --- Step 2: Load baseline data (SAME data source as GET /isi) ---
    isi_data = _get_or_load("isi", BACKEND_ROOT / "isi.json")
    if isi_data is None:
        logger.error(json.dumps({
            "event": "scenario_data_missing",
            "request_id": request_id,
        }))
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Scenario computation failed.",
            },
        )

    all_baselines = isi_data.get("countries", [])
    if not all_baselines:
        logger.error(json.dumps({
            "event": "scenario_baselines_empty",
            "request_id": request_id,
        }))
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Scenario computation failed.",
            },
        )

    # --- Step 3: Run simulation (returns Pydantic ScenarioResponse) ---
    try:
        result: ScenarioResponse = simulate(
            country_code=country_code,
            adjustments=adjustments,
            all_baselines=all_baselines,
        )
    except ValueError as exc:
        logger.warning(json.dumps({
            "event": "scenario_country_not_in_baseline",
            "request_id": request_id,
            "country_code": country_code,
            "error": str(exc),
        }))
        return JSONResponse(
            status_code=404,
            content={
                "error": "COUNTRY_NOT_FOUND",
                "message": str(exc),
                "country": country_code,
            },
        )
    except Exception as exc:
        logger.error(json.dumps({
            "event": "scenario_computation_failed",
            "request_id": request_id,
            "country_code": country_code,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }))
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Scenario computation failed.",
            },
        )

    # --- Step 4: Serialize through Pydantic (guarantees contract) ---
    try:
        response_body = result.model_dump(mode="json")
    except Exception as exc:
        logger.error(json.dumps({
            "event": "scenario_serialization_failed",
            "request_id": request_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }))
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Scenario computation failed.",
            },
        )

    logger.info(json.dumps({
        "event": "scenario_success",
        "request_id": request_id,
        "country": country_code,
        "baseline_composite": response_body["baseline"]["composite"],
        "simulated_composite": response_body["simulated"]["composite"],
        "simulated_rank": response_body["simulated"]["rank"],
    }))

    return JSONResponse(status_code=200, content=response_body)


# ---------------------------------------------------------------------------
# Entry point (development only)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except ImportError:
        print("Install uvicorn: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    os.environ.setdefault("ENV", "dev")
    print(f"ISI API v0.1 — serving from {BACKEND_ROOT}")
    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
