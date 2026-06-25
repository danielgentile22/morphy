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
# Client-side MapTiler key for the Satellite basemap (now the default). This is
# NOT a secret — it ships in the browser bundle regardless, and is protected by
# MapTiler's HTTP-referrer allowlist (morphyconsulting.com + localhost), not by
# secrecy. So it's baked in as the default here; no deploy-time arg needed.
# Override (e.g. a different key) with: fly deploy --build-arg VITE_MAPTILER_KEY=...
ARG VITE_MAPTILER_KEY="REDACTED_MAPTILER_KEY"
ENV VITE_MAPTILER_KEY=$VITE_MAPTILER_KEY
RUN npm run build
# -> /app/dist

# ── Stage 1b: build the data-audit browser bundle (audit-site/dist) ────────
# Standalone Svelte app base-pathed at /audit/; served behind the session gate
# (see Caddyfile). Its serve-audit-data plugin only runs in dev/preview, so the
# build needs only audit-site/ — the audit artifacts are baked in separately.
FROM node:22-slim AS audit-frontend
WORKDIR /audit
COPY audit-site/package.json audit-site/package-lock.json ./
RUN npm ci
COPY audit-site/ ./
RUN npm run build
# -> /audit/dist

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

# Backend Python deps from the same locked graph CI tested (PRD #132): export
# the `backend` dependency group from uv.lock (hash-pinned) and install it
# system-wide. The uv binary is bind-mounted for this step only, so it never
# lands in an image layer. The group stays the slim FastAPI/uvicorn/SQLAlchemy/
# PyJWT/psycopg set — pipeline GIS + GUI weight never enters this image
# (PRD #96 "image dependency decision", upheld).
COPY pyproject.toml uv.lock /tmp/uv-project/
RUN --mount=from=ghcr.io/astral-sh/uv:0.11.21,source=/uv,target=/usr/local/bin/uv \
    cd /tmp/uv-project \
    && uv export --frozen --only-group backend --no-emit-project -o backend-requirements.txt \
    && uv pip install --system --no-cache -r backend-requirements.txt \
    && rm -rf /tmp/uv-project

# App code, the built SPA, the data-sync contract (run on the machine for the
# R2->volume leg), and the process configs.
COPY backend/ /srv/backend/
COPY scripts/sync_composite.py /srv/scripts/sync_composite.py
COPY --from=frontend /app/dist /srv/dist
# The audit browser bundle + a snapshot of the audit artifacts it live-fetches.
# A re-run that rewrites docs/research/data-audit/ ships on the next deploy.
COPY --from=audit-frontend /audit/dist /srv/audit-dist
COPY docs/research/data-audit /srv/audit-data
COPY Caddyfile /etc/caddy/Caddyfile
COPY litestream.yml /etc/litestream.yml
COPY supervisord.conf /etc/supervisord.conf

# Non-secret runtime config the Caddyfile reads. Volume is mounted at /data, so
# DATA_WEB_ROOT="/" maps the URL prefix /data/processed/X onto the file
# /data/processed/X. Auth/DB/Litestream env + secrets come from fly.toml + Fly
# secrets, not here.
ENV SITE_ROOT=/srv/dist \
    AUDIT_SITE_ROOT=/srv/audit-dist \
    AUDIT_DATA_ROOT=/srv/audit-data \
    DATA_WEB_ROOT=/ \
    BACKEND_UPSTREAM=127.0.0.1:8000 \
    CADDY_PORT=8080 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["supervisord", "-c", "/etc/supervisord.conf"]
