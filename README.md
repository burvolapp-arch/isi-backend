# ISI Backend — International Sovereignty Index API

Read-only JSON API serving pre-materialized ISI v0.1 data for 27 EU countries across 6 dependency axes.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run in development mode (auto-reload, docs enabled)
make dev
# → http://localhost:8000/docs

# Run in production mode (gunicorn, docs disabled)
make prod
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API metadata |
| GET | `/health` | Health check (always 200) |
| GET | `/ready` | Readiness probe |
| GET | `/countries` | All 27 EU countries with scores |
| GET | `/country/{code}` | Full country detail |
| GET | `/country/{code}/axes` | Axis scores for one country |
| GET | `/country/{code}/axis/{n}` | Single axis detail |
| GET | `/axes` | Axis registry |
| GET | `/axis/{n}` | Full axis detail across countries |
| GET | `/isi` | Composite ISI scores |

Full contract: `docs/api/isi_api_contract_v01.md`

## Production Hardening

The API is hardened for public-internet deployment:

### Security Features

- **CORS**: Strict origin allowlist (no wildcard in production)
- **Security headers**: HSTS, X-Frame-Options, CSP, Referrer-Policy, Permissions-Policy
- **Rate limiting**: Per-IP limits (120/min general, 30/min data endpoints)
- **Request size limits**: Hard cap on request body (1 KB, API is GET-only)
- **Docs disabled**: `/docs`, `/redoc`, `/openapi.json` disabled in production unless `ENABLE_DOCS=1`
- **No stack trace leakage**: Global exception handler returns generic 500
- **Structured logging**: JSON logs with masked client IPs, request IDs
- **Data integrity**: Optional SHA-256 manifest verification at startup
- **Container hardening**: Non-root user, no .pyc, no dev tools

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENV` | `prod` | `dev` or `prod`. Controls CORS, docs, HSTS, log level |
| `ALLOWED_ORIGINS` | _(empty)_ | Comma-separated CORS origins. Empty in prod = deny all cross-origin |
| `ENABLE_DOCS` | _(empty)_ | Set to `1` to enable `/docs` and `/redoc` in production |
| `REQUIRE_DATA` | _(empty)_ | Set to `1` to hard-fail startup if `backend/v01/` is missing or corrupt |
| `REDIS_URL` | _(empty)_ | Redis connection URL for distributed rate limiting. If absent, uses in-memory (per-instance) |
| `PORT` | `8000` | Listening port (Railway sets this automatically) |

### Data Integrity (MANIFEST.json)

```bash
# After running the exporter, generate integrity manifest:
make manifest
# or: python scripts/generate_manifest.py

# If MANIFEST.json is present at startup:
#   - API verifies SHA-256 hashes of all backend/v01/*.json files
#   - If REQUIRE_DATA=1 and hashes mismatch → startup aborts (exit 1)
#   - Otherwise → API serves /health as "degraded"
```

### Deployment (Railway)

Railway detects the `Dockerfile` at repo root and builds automatically.

Set these environment variables in Railway dashboard:
- `ENV=prod`
- `ALLOWED_ORIGINS=https://your-frontend.example.com`
- `REQUIRE_DATA=1` (if data is baked into the image)

### CI / Development Commands

```bash
make lint       # ruff check
make security   # bandit scan
make audit      # pip-audit dependency scan
make ci         # all of the above + import test
make smoke      # boot server and test endpoints
make manifest   # generate data integrity manifest
make clean      # remove __pycache__
```

## Architecture

```
backend/
├── __init__.py            # Package marker
├── isi_api_v01.py         # FastAPI app (hardened)
├── security.py            # Middleware: headers, rate-limit, request-id, manifest
├── export_isi_backend_v01.py  # Upstream: CSV → JSON materializer
└── v01/                   # Pre-materialized JSON artifacts (not in git)
    ├── meta.json
    ├── axes.json
    ├── countries.json
    ├── isi.json
    ├── country/*.json     # 27 country detail files
    ├── axis/*.json        # 6 axis detail files
    └── MANIFEST.json      # SHA-256 integrity manifest
```

## License

Proprietary — Panargus / Burvolapp Architecture.
