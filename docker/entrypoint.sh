#!/bin/sh
set -eu

python manage.py migrate --noinput

# Optional staff account for /staff and /admin (no-op if it already exists).
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    python manage.py createsuperuser --noinput \
        --email "${DJANGO_SUPERUSER_EMAIL:-staff@example.com}" 2>&1 \
        | grep -v "already taken" || true
fi

# One worker on purpose: the sandbox semaphore and reap_stale_once() are per-process,
# and SQLite (WAL) prefers a single writer process. Concurrency comes from threads.
exec gunicorn config.wsgi \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --threads "${GUNICORN_THREADS:-16}" \
    --access-logfile -
