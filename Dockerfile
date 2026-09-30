# syntax=docker/dockerfile:1
# App image for the dev/demo setup (see docker-compose.yaml). Runs as root on purpose:
# the sandbox is driven through the host's /var/run/docker.sock.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY manage.py ./
COPY config/ config/
COPY challenges/ challenges/
COPY game/ game/
# Only the challenge definitions are needed at runtime (settings.CHALLENGES_YAML).
COPY sandbox/internal/challenge/challenges.yaml sandbox/internal/challenge/challenges.yaml
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN python manage.py collectstatic --noinput

ENV BASHDASH_DB_DIR=/data \
    BASHDASH_DEBUG=False
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
