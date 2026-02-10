# ISI API — Production Container (hardened)
# No build-time secrets, no dev tools, non-root user, minimal surface.

FROM python:3.11-slim AS base

# Prevent .pyc files and enable unbuffered stdout for logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user early
RUN groupadd --gid 1001 isi && \
    useradd --uid 1001 --gid isi --shell /bin/false --create-home isi

WORKDIR /app

# Install dependencies first (Docker layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --no-compile -r /app/requirements.txt && \
    rm -rf /root/.cache /tmp/*

# Copy application code only
COPY backend/__init__.py /app/backend/__init__.py
COPY backend/isi_api_v01.py /app/backend/isi_api_v01.py
COPY backend/security.py /app/backend/security.py

# Copy pre-materialized data if present (optional at build time).
# The wildcard pattern avoids a build failure when backend/v01/ does not exist.
# If v01/ is absent, the API boots in degraded mode (/health reports "degraded").
COPY backend/v0[1]/ /app/backend/v01/

# Switch to non-root user
USER isi

EXPOSE 8000

# Production: gunicorn with uvicorn workers
# --timeout 30:       kill workers that hang > 30s
# --graceful-timeout 10: allow 10s for graceful shutdown
# --keep-alive 5:     close idle keepalive connections after 5s
# --max-requests 2000: recycle workers to prevent memory leaks
# --max-requests-jitter 200: stagger recycling across workers
# --access-logfile -: log to stdout for Railway
CMD ["gunicorn", "backend.isi_api_v01:app", \
     "--bind", "0.0.0.0:8000", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--timeout", "30", \
     "--graceful-timeout", "10", \
     "--keep-alive", "5", \
     "--max-requests", "2000", \
     "--max-requests-jitter", "200", \
     "--access-logfile", "-"]
