# ISI API — Production Container (hardened)
# No build-time secrets, no dev tools, non-root user, minimal surface.
# backend/ MUST contain v01/ with all 37+ pre-materialized JSON artifacts.

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

# Copy entire backend/ — application code + pre-materialized v01/ artifacts.
# No globs, no optional copies. If backend/v01/ is missing, the build still
# succeeds but /health will report data_present=false (by design).
COPY backend/ /app/backend/

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
