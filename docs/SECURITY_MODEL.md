# Panargus ISI — Security Model

> **Scope**: FastAPI backend serving pre-computed ISI snapshots.
> **Posture**: Read-only data, no user accounts, no PII, no write-back.
> **Last updated**: 2025-07-11 (NSA-finish phase)

---

## 1. Asset Inventory

| Asset | Location | Sensitivity |
|---|---|---|
| Snapshot JSON files | `backend/snapshots/{methodology}/{year}/` | **Integrity-critical** — source of all API responses |
| Registry | `backend/snapshots/registry.json` | **Integrity-critical** — determines available methodologies/years |
| MANIFEST.json | Per-snapshot directory | **Integrity-critical** — SHA-256 checksums of every artifact |
| HASH_SUMMARY.json | Per-snapshot directory | **Integrity-critical** — root hash of the entire snapshot |
| API keys / rate limit config | Environment variables | Confidential |
| Container image | Docker / Railway | Supply-chain surface |

## 2. Trust Boundaries

```
┌─────────────────────────────────┐
│  Internet (untrusted)           │
│  └─ HTTP client                 │
└──────────┬──────────────────────┘
           │ HTTPS (TLS terminated by Railway)
           ▼
┌─────────────────────────────────┐
│  Reverse proxy / load balancer  │
│  (Railway infrastructure)       │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Gunicorn + Uvicorn workers     │
│  ┌────────────────────────────┐ │
│  │  FastAPI application       │ │
│  │  ┌──────────────────────┐  │ │
│  │  │  SnapshotCache       │  │ │  ← Thread-safe, bounded, read-only
│  │  │  SnapshotResolver    │  │ │  ← Input-validated before filesystem
│  │  └──────────────────────┘  │ │
│  └────────────────────────────┘ │
│  ┌────────────────────────────┐ │
│  │  Filesystem (read-only)    │ │  ← Snapshot data, baked into image
│  └────────────────────────────┘ │
└─────────────────────────────────┘
```

**Trust boundary**: All user input crosses the Internet→Application boundary.
Every value from the HTTP layer is adversarial until validated.

## 3. Attacker Model

| Attacker | Capability | Goal |
|---|---|---|
| **Remote unauthenticated** | Arbitrary HTTP requests | Path traversal, information disclosure, DoS |
| **Supply-chain** | Tampered snapshot files on disk | Serve falsified data without detection |
| **Insider / CI** | Modify source or snapshot between builds | Introduce subtle data corruption |

## 4. Attack Surfaces & Mitigations

### A. Path Traversal

**Surface**: `methodology`, `country_code`, `axis_id` parameters flow into filesystem paths.

**Mitigations** (defense-in-depth):
1. **Strict allowlist regex** at cache entry point — rejects before any path construction:
   - Methodology: `^v[0-9]{1,10}\.[0-9]{1,10}\Z` (ASCII digits only, length-bounded, no trailing newline)
   - Country code: `^[A-Z]{2}$` (ISO 3166-1 alpha-2)
   - Axis ID: `^[1-9]$` (single digit)
2. **`pathlib.resolve()` containment check** — resolved path must be under snapshot root
3. **Year range validation**: `[2000, 2100]`
4. **Artifact key allowlist** — only known prefixes (`isi`, `country:`, `axis:`, `hash_summary`, `manifest`) accepted

### B. TOCTOU / Filesystem Tamper

**Surface**: Files could be modified between integrity check and serving.

**Mitigations**:
1. **Mtime pinning** — `SnapshotCache` records `os.path.getmtime()` on first load
2. **`check_tamper()`** — compares pinned mtimes; atomically invalidates entire slot on any deviation
3. **Startup validation** — when `SNAPSHOT_STRICT_VALIDATION=1`, the app validates the latest snapshot at startup and refuses to start (`sys.exit(1)`) if integrity fails
4. **`/ready` reflects validation state** — Kubernetes/Railway probes see `ready: false` if snapshot didn't pass validation
5. **Docker image is read-only in production** — snapshot files baked at build time

### C. Information Disclosure

**Surface**: Error messages, stack traces, log output.

**Mitigations**:
1. **Global exception handler** — returns generic `"Internal server error"` for unhandled exceptions
2. **Internal endpoint** (`/_internal/snapshot/verify`) — excluded from OpenAPI; sanitizes all absolute paths from output; disabled by default (`ENABLE_INTERNAL_VERIFY=0`)
3. **Log sanitizer** (`backend/log_sanitizer.py`):
   - Strips project root from paths
   - Redacts external filesystem paths as `<external>`
   - Redacts connection strings (redis://, postgresql://, mysql://, amqp://, mongodb://)
   - Sanitizes exception messages before logging
4. **No stack traces in any HTTP response** — `try/except` with safe structured JSON

### D. Denial of Service

**Surface**: Unbounded cache growth, expensive computation.

**Mitigations**:
1. **Bounded cache** — `MAX_CACHED_SNAPSHOTS` (default 3) with LRU eviction
2. **Artifact count cap** — `MAX_ARTIFACTS_PER_SNAPSHOT = 50` per slot
3. **Rate limiting** — `slowapi` on all endpoints (configurable per-endpoint)
4. **Year range bounds** — prevents filesystem enumeration of arbitrary years
5. **Methodology length cap** — `{1,10}` digits prevents regex DoS and absurdly long path components

### E. Startup / Readiness

**Surface**: Serving stale or corrupt data if validation is skipped.

**Mitigations**:
1. **Strict mode** (`SNAPSHOT_STRICT_VALIDATION=1`): full integrity validation at startup — fail-fast
2. **`/ready`** endpoint: returns `ready: false` if strict mode enabled and snapshot not validated
3. **`/health`** endpoint: always returns 200 (liveness only — no data dependency)

## 5. Invariants (Enforced by Tests)

These properties are verified by the 283-test suite and CI pipeline:

| # | Invariant | Enforcement |
|---|---|---|
| 1 | No methodology string that doesn't match `^v[0-9]{1,10}\.[0-9]{1,10}\Z` reaches the filesystem | `TestStrictAllowlists` (16 attack vectors) |
| 2 | No country code that doesn't match `^[A-Z]{2}$` reaches the filesystem | `TestStrictAllowlists` (10 attack vectors) |
| 3 | No axis ID that doesn't match `^[1-9]$` reaches the filesystem | `TestStrictAllowlists` (7 attack vectors) |
| 4 | No year outside `[2000, 2100]` reaches the resolver or cache | `TestStrictAllowlists` + `TestResolverInputValidation` |
| 5 | File modification after caching triggers tamper detection | `TestTamperDetection` (6 tests) |
| 6 | Cache never exceeds `MAX_CACHED_SNAPSHOTS` slots | `TestCacheBounds` |
| 7 | Cache never exceeds `MAX_ARTIFACTS_PER_SNAPSHOT` per slot | `TestCacheBounds` |
| 8 | No HTTP response contains an absolute filesystem path | `TestInternalEndpointHardening` |
| 9 | No HTTP response contains a stack trace | `TestInternalEndpointHardening` |
| 10 | Internal endpoint excluded from OpenAPI schema | `TestInternalEndpointHardening` |
| 11 | All 27 EU countries present in ISI response | `TestOpenAPIContract` |
| 12 | POST /scenario rejects unknown axes and out-of-range values with 400 | `TestOpenAPIContract` |
| 13 | GET /scenario returns 405 (method not allowed) | `TestOpenAPIContract` |
| 14 | Snapshot JSON is canonical (deterministic re-serialization) | CI `integrity.yml` |
| 15 | MANIFEST SHA-256 checksums match file content byte-for-byte | CI `integrity.yml` |
| 16 | HASH_SUMMARY root hash matches recomputed hash | CI `integrity.yml` |

## 6. CI Integrity Pipeline (`.github/workflows/integrity.yml`)

Every push and PR triggers:
1. **Ruff lint** — static analysis
2. **Bandit** — security-focused static analysis
3. **pip-audit** — known vulnerability scan of dependencies
4. **Import smoke test** — verifies `backend.isi_api_v01` loads without error
5. **Full test suite** — 283 tests
6. **Snapshot integrity verification** — `verify_snapshot --methodology v1.0 --year 2024 --json`
7. **Canonical JSON determinism** — re-serialize every snapshot JSON; diff must be empty
8. **MANIFEST byte-level verification** — recompute SHA-256 of every file; compare to MANIFEST
9. **HASH_SUMMARY verification** — recompute root hash; compare to HASH_SUMMARY

## 7. Residual Risk

| Risk | Likelihood | Impact | Acceptance |
|---|---|---|---|
| TLS termination misconfiguration at Railway | Low | High | Accepted — outside application boundary |
| Python runtime CVE | Low | High | Mitigated by pinned 3.11-slim + pip-audit in CI |
| Snapshot data quality (not correctness of source data) | N/A | N/A | Out of scope — this model covers integrity, not accuracy |
| Side-channel timing attacks on cache | Very low | Low | Accepted — no secrets in cache lookup paths |
