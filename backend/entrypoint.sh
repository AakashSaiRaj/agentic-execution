#!/usr/bin/env bash
# Container entrypoint: wait for the database, apply migrations, then serve.
set -euo pipefail

echo "Applying database migrations (with retry until DB is reachable)..."
ATTEMPTS=0
MAX_ATTEMPTS=30
until alembic upgrade head; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
    echo "Database not ready after ${MAX_ATTEMPTS} attempts; giving up." >&2
    exit 1
  fi
  echo "  migration attempt ${ATTEMPTS}/${MAX_ATTEMPTS} failed; retrying in 2s..."
  sleep 2
done

echo "Migrations applied. Starting API server (workers=${UVICORN_WORKERS:-1})..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --workers "${UVICORN_WORKERS:-1}" --proxy-headers --forwarded-allow-ips "*"
