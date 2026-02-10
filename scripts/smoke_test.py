#!/usr/bin/env python3
"""
smoke_test.py — Boot the ISI API locally and verify core endpoints.

Starts uvicorn in a subprocess, waits for it to be ready, then
curls the key endpoints and checks status codes / response shapes.

Usage:
    python scripts/smoke_test.py

Requirements: httpx (in requirements-dev.txt)

Task: ISI-SMOKE
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("FATAL: httpx not installed. pip install httpx", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_V01 = PROJECT_ROOT / "backend" / "v01"
BASE_URL = "http://127.0.0.1:8099"
TIMEOUT = 10


def wait_for_server(url: str, max_wait: int = 10) -> bool:
    """Poll server until it responds or timeout."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                return True
        except httpx.ConnectError:
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    print("=" * 64)
    print("ISI API — Smoke Test")
    print("=" * 64)
    print()

    data_present = BACKEND_V01.is_dir() and (BACKEND_V01 / "meta.json").is_file()
    print(f"  backend/v01 present: {data_present}")
    print()

    # Start server
    env = os.environ.copy()
    env["ENV"] = "dev"
    env.pop("REQUIRE_DATA", None)

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.isi_api_v01:app",
            "--host", "127.0.0.1",
            "--port", "8099",
            "--log-level", "warning",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        if not wait_for_server(BASE_URL):
            print("FATAL: Server did not start within 10s", file=sys.stderr)
            proc.terminate()
            proc.wait(5)
            sys.exit(1)

        print("  Server is up. Running checks...\n")
        failures = 0

        # Test 1: /health → 200
        r = httpx.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        ok = r.status_code == 200
        body = r.json()
        print(f"  GET /health → {r.status_code}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1
        # Verify safe fields
        for field in ("status", "version", "data_present", "data_file_count", "timestamp"):
            if field not in body:
                print(f"    MISSING field: {field}")
                failures += 1
        # Must NOT have backend_root (path leak)
        if "backend_root" in body:
            print("    FAIL: /health leaks backend_root path")
            failures += 1

        # Test 2: /ready → 200
        r = httpx.get(f"{BASE_URL}/ready", timeout=TIMEOUT)
        ok = r.status_code == 200
        print(f"  GET /ready → {r.status_code}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

        # Test 3: /countries
        r = httpx.get(f"{BASE_URL}/countries", timeout=TIMEOUT)
        if data_present:
            ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) == 27
            print(f"  GET /countries → {r.status_code} ({len(r.json())} entries)  {'PASS' if ok else 'FAIL'}")
        else:
            ok = r.status_code == 503
            print(f"  GET /countries → {r.status_code} (expected 503, no data)  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

        # Test 4: Security headers
        r = httpx.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        for header in ("x-content-type-options", "x-frame-options", "referrer-policy"):
            if header not in r.headers:
                print(f"    MISSING security header: {header}")
                failures += 1
            else:
                print(f"    {header}: {r.headers[header]}")

        # Test 5: X-Request-ID
        if "x-request-id" in r.headers:
            print(f"    x-request-id: {r.headers['x-request-id']}  PASS")
        else:
            print("    MISSING: x-request-id  FAIL")
            failures += 1

        # Test 6: Invalid country code → 404
        r = httpx.get(f"{BASE_URL}/country/ZZ", timeout=TIMEOUT)
        ok = r.status_code == 404
        print(f"  GET /country/ZZ → {r.status_code}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

        # Test 7: Invalid axis → 404
        r = httpx.get(f"{BASE_URL}/axis/99", timeout=TIMEOUT)
        ok = r.status_code == 404
        print(f"  GET /axis/99 → {r.status_code}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures += 1

        # Test 8: Docs disabled in prod (we're in dev, so should be available)
        r = httpx.get(f"{BASE_URL}/docs", timeout=TIMEOUT, follow_redirects=True)
        print(f"  GET /docs → {r.status_code}  (dev mode, expected 200)")

        print()
        if failures > 0:
            print(f"RESULT: {failures} failure(s)")
            sys.exit(1)
        else:
            print("RESULT: ALL PASSED")

    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


if __name__ == "__main__":
    main()
