# Phase-1 app image (PRD #96, ADR-064): the SPA bundle + FastAPI + Caddy +
# Litestream + restic + supervisord, in one always-on Fly machine.
# syntax=docker/dockerfile:1

# ── Stage 1: build the SPA bundle (app/dist) ───────────────────────────────
FROM node:22-slim AS frontend
WORKDIR /app
# Install deps from the lockfile first so this layer caches across source edits.
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build
# -> /app/dist

# ── Stage 2: runtime ───────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# OS deps: supervisor (the in-machine process tree), restic (future lease-PDF
# backups — the documented D+E hook), ca-certificates (TLS to R2). Minimal.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        supervisor \
        restic \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Static Go binaries from their official images, pinned to the versions the
# repo's tests were written against (caddy 2.11, litestream 0.5.11, rclone 1.74).
COPY --from=caddy:2.11 /usr/bin/caddy /usr/local/bin/caddy
COPY --from=litestream/litestream:0.5.11 /usr/local/bin/litestream /usr/local/bin/litestream
COPY --from=rclone/rclone:1.74 /usr/local/bin/rclone /usr/local/bin/rclone

# Backend Python deps: the SLIM backend set (FastAPI/uvicorn/SQLAlchemy/PyJWT),
# NOT the root requirements.txt — that carries geopandas/shapely/pyproj/PySide6
# used only by the preprocess pipeline, which never runs in this image. (PRD #96
# "image dependency decision": the slim subset already exists as
# backend/requirements.txt, so we use it rather than the heavy root set.)
COPY backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

# App code, the built SPA, the data-sync contract (run on the machine for the
# R2->volume leg), and the process configs.
COPY backend/ /srv/backend/
COPY scripts/sync_composite.py /srv/scripts/sync_composite.py
COPY --from=frontend /app/dist /srv/dist
COPY Caddyfile /etc/caddy/Caddyfile
COPY litestream.yml /etc/litestream.yml
COPY supervisord.conf /etc/supervisord.conf

# Non-secret runtime config the Caddyfile reads. Volume is mounted at /data, so
# DATA_WEB_ROOT="/" maps the URL prefix /data/processed/X onto the file
# /data/processed/X. Auth/DB/Litestream env + secrets come from fly.toml + Fly
# secrets, not here.
ENV SITE_ROOT=/srv/dist \
    DATA_WEB_ROOT=/ \
    BACKEND_UPSTREAM=127.0.0.1:8000 \
    CADDY_PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
