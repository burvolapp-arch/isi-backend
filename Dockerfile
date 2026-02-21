# ISI API — Production Container (hardened)
# No build-time secrets, no dev tools, non-root user, minimal surface.
# backend/ MUST contain v01/ with all 37+ pre-materialized JSON artifacts.
# Snapshots are baked at build time and read-only at runtime.

FROM python:3.11-slim

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

# Copy entire backend/ — application code + pre-materialized snapshot artifacts.
COPY backend/ /app/backend/

# Enforce read-only permissions on snapshot artifacts at build time.
# Files: 0444 (read-only for all). Directories: 0555 (traverse-only for all).
# This is defense-in-depth — even if the filesystem is mounted read-write,
# the files themselves reject writes.
RUN find /app/backend/snapshots -type f -exec chmod 0444 {} + && \
    find /app/backend/snapshots -type d -exec chmod 0555 {} + && \
    find /app/backend/config -type f -exec chmod 0444 {} + 2>/dev/null; true

# Switch to non-root user
USER isi

EXPOSE 8080

# Production: gunicorn as PID 1 with uvicorn workers.
# Shell form with exec — $PORT is expanded at runtime by sh, then exec
# replaces sh so gunicorn becomes PID 1 (correct signal handling).
# Railway injects PORT dynamically; no fallback, no hardcoded port.
CMD ["sh", "-c", "exec gunicorn backend.isi_api_v01:app --bind 0.0.0.0:${PORT} --worker-class uvicorn.workers.UvicornWorker --workers 2 --timeout 120 --graceful-timeout 10 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200 --access-logfile -"]
