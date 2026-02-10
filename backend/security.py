"""
backend.security — Security middleware and utilities for ISI API.

Provides:
    - SecurityHeadersMiddleware: adds OWASP-recommended response headers
    - RequestSizeLimitMiddleware: rejects oversized request bodies
    - RequestIdMiddleware: attaches X-Request-ID to every request/response
    - structured_log: JSON-structured request logging
    - verify_manifest: SHA-256 integrity check for backend/v01 artifacts
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("isi.security")


# ---------------------------------------------------------------------------
# Request-ID middleware
# ---------------------------------------------------------------------------

class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request and echo it in response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        t0 = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        # Structured log
        _log_request(request, response.status_code, latency_ms, request_id)
        return response


# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Inject OWASP-recommended security headers into every response.
    HSTS is only added when env is 'prod' (assumes TLS termination
    upstream, which Railway provides).
    """

    def __init__(self, app: Any, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        )
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        # Cache-Control: /health and /ready are no-store;
        # data endpoints get short private cache
        path = request.url.path
        if path in ("/health", "/ready"):
            response.headers["Cache-Control"] = "no-store"
        elif path == "/":
            response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            response.headers["Cache-Control"] = "private, no-store"
        return response


# ---------------------------------------------------------------------------
# Request size limit middleware
# ---------------------------------------------------------------------------

MAX_BODY_BYTES = 1024  # 1 KB — API is GET-only, no reason for large bodies


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies exceeding MAX_BODY_BYTES."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return Response(
                        content='{"detail":"Request body too large"}',
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass
        return await call_next(request)


# ---------------------------------------------------------------------------
# Structured request logging
# ---------------------------------------------------------------------------

def _mask_ip(ip: str | None) -> str:
    """Truncate IP for privacy — keep first two octets of IPv4, prefix of IPv6."""
    if not ip:
        return "unknown"
    if ":" in ip:
        # IPv6: keep first 4 groups
        parts = ip.split(":")
        return ":".join(parts[:4]) + "::*"
    # IPv4: keep first two octets
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.*"
    return "unknown"


def _log_request(
    request: Request,
    status_code: int,
    latency_ms: float,
    request_id: str,
) -> None:
    """Emit a structured JSON log line for the request."""
    log_data = {
        "event": "http_request",
        "method": request.method,
        "path": request.url.path,
        "status": status_code,
        "latency_ms": latency_ms,
        "client_ip": _mask_ip(request.client.host if request.client else None),
        "request_id": request_id,
    }
    # Use INFO for normal, WARNING for 4xx, ERROR for 5xx
    if status_code >= 500:
        logger.error(json.dumps(log_data))
    elif status_code >= 400:
        logger.warning(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))


# ---------------------------------------------------------------------------
# MANIFEST.json integrity verification
# ---------------------------------------------------------------------------

def verify_manifest(backend_root: Path) -> dict[str, Any]:
    """
    Verify SHA-256 hashes of backend/v01 artifacts against MANIFEST.json.

    Returns:
        {
            "manifest_present": bool,
            "verified": bool,        # True if all hashes match
            "errors": [str, ...],    # list of mismatch descriptions
            "files_checked": int,
        }
    """
    manifest_path = backend_root / "MANIFEST.json"
    result: dict[str, Any] = {
        "manifest_present": False,
        "verified": False,
        "errors": [],
        "files_checked": 0,
    }

    if not manifest_path.is_file():
        return result

    result["manifest_present"] = True

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        result["errors"].append(f"Failed to read MANIFEST.json: {type(exc).__name__}")
        return result

    files_list = manifest.get("files", [])
    if not files_list:
        result["errors"].append("MANIFEST.json contains no file entries")
        return result

    for entry in files_list:
        rel_path = entry.get("path", "")
        expected_hash = entry.get("sha256", "")
        if not rel_path or not expected_hash:
            result["errors"].append(f"Invalid manifest entry: {entry}")
            continue

        file_path = backend_root / rel_path
        if not file_path.is_file():
            result["errors"].append(f"Missing file: {rel_path}")
            continue

        actual_hash = _sha256_file(file_path)
        result["files_checked"] += 1
        if actual_hash != expected_hash:
            result["errors"].append(
                f"Hash mismatch: {rel_path} "
                f"(expected {expected_hash[:16]}..., got {actual_hash[:16]}...)"
            )

    result["verified"] = len(result["errors"]) == 0
    return result


def _sha256_file(filepath: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
