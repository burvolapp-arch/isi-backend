# ISI API — Development Commands
# Usage: make <target>

.PHONY: dev prod manifest smoke lint security audit ci clean

# ── Local development (single worker, auto-reload) ──────────
dev:
	ENV=dev uvicorn backend.isi_api_v01:app --host 0.0.0.0 --port 8000 --reload

# ── Production-like local run (gunicorn + uvicorn workers) ──
prod:
	ENV=prod gunicorn backend.isi_api_v01:app \
		--bind 0.0.0.0:8000 \
		--worker-class uvicorn.workers.UvicornWorker \
		--workers 2 \
		--timeout 30 \
		--graceful-timeout 10 \
		--keep-alive 5 \
		--max-requests 2000 \
		--max-requests-jitter 200 \
		--access-logfile -

# ── Generate MANIFEST.json for backend/v01 artifacts ────────
manifest:
	python scripts/generate_manifest.py

# ── Smoke test (boots server, curls endpoints) ──────────────
smoke:
	python scripts/smoke_test.py

# ── Linting ─────────────────────────────────────────────────
lint:
	ruff check backend/

# ── Security scan ───────────────────────────────────────────
security:
	bandit -r backend/ -c pyproject.toml

# ── Dependency audit ────────────────────────────────────────
audit:
	pip-audit -r requirements.txt

# ── Full CI pipeline (local) ────────────────────────────────
ci: lint security audit
	python -c "from backend.isi_api_v01 import app; print('import_ok')"
	@echo "CI checks passed."

# ── Clean pyc / caches ─────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
