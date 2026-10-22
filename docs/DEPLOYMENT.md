# Deployment

**Archived.** This project is no longer under active development. The doc describes how the code as it stands is run and deployed.

The hosted backend shipped per [ADR-055](./adr/0055-hosted-private-backend.md) as narrowed by [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md). The deploy artifacts target the Fly app `morphy-demo` (region `iad`), served at https://morphy-demo.fly.dev. Local development runs all four subsystems on a laptop (§1). To update a running app, see §8, "Day-2 operations".

This doc covers how to stand up the project: what to install, how to run each subsystem, how to share outputs offline, and how the hosted backend is deployed and operated (§8).

---

## 1. Where this runs (local development)

All four subsystems run locally on a developer's machine (the hosted app is §8):

| Subsystem | Run command | Port / location |
|---|---|---|
| **Data TUI (the puller)** | `python -m data_tui` | Terminal (full-screen) |
| **Preprocess CLI** | `python scripts/preprocess.py [flags]` | Terminal |
| **Map app** | `python scripts/serve.py 8765` + `cd app && npm run dev` | localhost:5173 |
| **Tests** | `pytest` · `cd app && npm run test:unit && npm run test:e2e` | Terminal |

The hosted backend (§8) is a single Fly.io machine with SQLite on a volume, Cloudflare R2 object storage for backups and data staging, FastAPI, and username/password auth. The map app stays static. It talks to the backend over a thin API for the write-layer features (lead state, tasks, activity log, per-user scoring presets). The local commands above are how you develop. To ship a change to a hosted app, see §8, "Day-2 operations".

---

## 2. Prerequisites

| Component | Version | Why |
|---|---|---|
| Python | 3.11 | Tested baseline; pyogrio known good |
| macOS arm64 / Linux x86_64 | Any recent | macOS arm64 was the primary dev environment |
| Homebrew (macOS) | Any | For `gh` CLI and `tippecanoe` |
| Disk space | ≥ 50 GB free | Raw data + composites; AR alone is ~3 GB raw, ~5 GB normalized. `data/` can live on an external drive. |
| RAM | ≥ 16 GB recommended | Preprocess on AR (2.1M rows) peaks at ~6 GB resident memory |
| Node.js | ≥ 20 | Vite + Svelte build for the map app |
| Tippecanoe | ≥ 2.45 | `parcels.pmtiles` generation (`preprocess.py --tiles`) |

---

## 3. First-time setup

```bash
git clone git@github.com:<user>/morphy.git
cd morphy

# Python environment: uv creates .venv on Python 3.11 from uv.lock
# (exact pinned versions, all dependency groups, editable project install).
# Install uv once: https://docs.astral.sh/uv/getting-started/installation/
uv sync
source .venv/bin/activate

# Verify installation
python scripts/verify_raw.py     # No raw data yet, so expect "missing" rows
python -m data_tui               # Should open the data TUI (q to quit)
```

The first run sets up empty `data/raw/` and `data/processed/`
directories (git-ignored).

---

## 4. Standard workflow

### 4.1 Refresh data

1. Launch the data TUI: `python -m data_tui` (the launch sweep checks
   every source in parallel).
2. The attention panel shows what needs action:
   - Auto sources stale or missing: `P` pulls them all in a background
     job (progress, resume, desktop notification on completion).
   - Manual source stale (AR parcels): `w` opens the guided
     walkthrough; `i` installs the downloaded files from disk.
3. Failures show a detail pane (URL tried, error, elapsed time); `d` runs
   the LLM diagnosis.

### 4.2 Preprocess

Either via the TUI:

- `r` opens state selection, preseeded with the states affected by what you
  pulled, then runs (background job with per-source and per-state progress).

Or via the CLI:

```bash
python scripts/preprocess.py                   # everything
python scripts/preprocess.py --state 05        # one state
python scripts/preprocess.py --source ar_parcels --force-rebuild
python scripts/preprocess.py --rebuild-manifest  # sync manifest from disk
```

Outputs land at `data/processed/normalized/<source>/` and
`data/processed/composite/<state_fips>/`.

### 4.3 Build the app's data assets and view the map

```bash
python scripts/preprocess.py --app-assets   # index.json + per-state facets / slim parquet / county boundaries
python scripts/preprocess.py --tiles        # per-state parcels.pmtiles (needs tippecanoe)

python scripts/serve.py 8765                # range-capable data server, from the repo root
cd app && npm install && npm run dev        # http://localhost:5173  (?state=05 to deep-link)
```

`python -m http.server` does **not** work for the app. PMTiles and
DuckDB-WASM need HTTP Range / 206, which it does not send; `serve.py`
does. The app discovers composed states via `composite/index.json`.
See [app/ARCHITECTURE.md](../app/ARCHITECTURE.md).

The Satellite basemap needs a MapTiler key. Put `VITE_MAPTILER_KEY` in a git-ignored
`app/.env` (`app/.env.example` documents it). Without a key the app uses the keyless Esri
basemaps and hides Satellite.

### 4.4 Run tests

```bash
pytest                                     # preprocess pipeline + app-asset scripts
pytest --cov=scripts.preprocess            # with coverage
ruff check . && ruff format --check .      # lint + format
cd app && npm run check && npm run test:unit && npm run test:e2e
```

---

## 5. Sharing outputs offline

The normal way to share the hosted app is to give someone a login (§8). For an offline bundle
with no hosted access and no account, hand over a tarball:

```bash
# Bundle the app + the four anchor-state composites
tar -czf morphy-bundle-$(date +%Y%m%d).tar.gz \
    app/ \
    data/processed/composite/05/ \
    data/processed/composite/12/ \
    data/processed/composite/30/ \
    data/processed/composite/54/ \
    README.md
```

The recipient needs Node 20+. From `app/`, run `npm install && npm run
build`, then run `python scripts/serve.py 8765` (repo root) and
`npm run preview`. See [../app/ARCHITECTURE.md](../app/ARCHITECTURE.md).
**PII caveat:** this tarball contains parcel-owner names and mailing
addresses, which are personally identifiable information (PII). Encrypt it at rest and share
it over a secure channel.

---

## 6. Environment variables

Most runs need no env vars. Optional:

| Variable | Used by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `scripts/diagnose.py` (the TUI's `d` diagnose action) | LLM-powered verify-failure diagnosis (~$0.04 per call). Local only: the deployed backend reads no Anthropic key. |
| `REGRID_S3_BUCKET`, `REGRID_S3_PREFIX`, `AWS_*` | `scripts/fetch/sources/regrid_parcels.py` | Activates the Regrid source only if all are set (paid; out of scope for v1) |
| `VITE_MAPTILER_KEY` | Map app build (`app/.env` in dev; `deploy.sh code` reads the repo-root `.env`) | Client-side key for the MapTiler Satellite basemap. Unset falls back to the keyless basemaps. |

Store them in a git-ignored `.env` (see the root `.env.example`) and source it
before running:

```bash
source .env
python -m data_tui
```

---

## 7. Backups

Local backups of composite outputs are manual:

1. `tar -czf backups/morphy-$(date +%Y%m%d-%H%M).tar.gz data/processed/`.
   Composite outputs are the expensive part; raw data can always be
   re-pulled.
2. Copy the archive to a personal cloud backup, **encrypted**, because parcel data is PII.

The hosted write-layer database has continuous backups through Litestream (§8).

---

## 8. Hosted-private backend (slice D+E)

[ADR-055](./adr/0055-hosted-private-backend.md) locked this design. It supersedes ADR-006 (static site, no backend) for write-layer features only; read-only analytical layers stay static. [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md) narrowed the platform, database, and object-store choices: one always-on Fly.io machine and SQLite on its volume, about $5-8 a month, instead of the managed-Postgres and separate-S3-service shape ADR-055 first defaulted to. The repo's artifacts target Fly app `morphy-demo` (region `iad`, 10 GB volume `morphy_data`, SQLite + Litestream → R2 bucket `morphy-demo`). There is no custom domain or CDN proxy in front; the app is served at https://morphy-demo.fly.dev. The provisioning runbook below is the one-time stand-up. "Day-2 operations" covers updating a running app.

### Stack (per ADR-064)

| Component | Choice | Notes |
|---|---|---|
| Hosting | **Fly.io**, US region, **single always-on machine** (`min_machines_running=1`) | ADR-064 chose the `fly deploy` PaaS over a bare VM that cost about $2 a month less. One machine only, because SQLite is single-writer. |
| App | **FastAPI** (uvicorn) | Thin CRUD + auth; same language as preprocess. |
| In-machine web server | **Caddy + uvicorn under supervisord** | Caddy serves `app/dist` (SPA) + `/data/*` Range/206 + gzip and reverse-proxies `/api/*` → uvicorn. Replaces `scripts/serve.py` in the hosted app. Fly `[processes]` is *not* used, because it would spawn separate machines and break the single-volume, single-writer setup. |
| Storage | **Fly Volume, 10 GB** (`fly volume extend` later) | Holds the 4.29 GB served composite + SQLite. The 4.29 GB stays **same-origin behind the login** (PII). |
| Database | **SQLite on the Volume** | `DATABASE_URL=sqlite+pysqlite:////data/lead_state.sqlite3`. Tenant isolation is app-level (identical to Postgres), and the schema is Postgres-portable. Avoids Fly Managed Postgres ($38 a month). Tenant-shaped schema from day one: every table has `tenant_id`. |
| Object store | **Cloudflare R2** | Private, encrypted bucket for backups. Also the laptop→R2→volume staging relay for data sync. Lease PDFs were planned here with D+E but never built. |
| Backups | **Litestream → R2** (continuous SQLite) + Fly volume snapshots | Composite data is disposable (re-compose). The SQLite write layer is the data worth protecting. The image carries restic for planned lease-PDF backups that were never built. |
| Auth | **Username/password** (`credential` table in the volume DB) | Managed via `fly ssh` + `python -m app.users`; teams are tenants; identity-only HS256 JWTs in the httpOnly `morphy_session` cookie. The credential table is authoritative per request, and Caddy `forward_auth` gates `/data/processed/*` behind it ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) as amended by [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). |
| Domain + perimeter | **None.** The app uses its `fly.dev` hostname | No custom domain, CDN, or proxy in front. The app login is the auth boundary, and Caddy keeps `/data/processed/*` out of caches with `Cache-Control: private, no-store`. |
| LLM | **Anthropic Claude API** (planned, never built) | Sonnet 4.6 default + Opus 4.7 retry for lease extraction ([ADR-059](./adr/0059-llm-lease-extraction.md)). |
| Transport | **HTTPS only** (HSTS) | TLS terminates at Fly's edge; Caddy speaks plain HTTP inside the machine and sets HSTS on every response. |
| Machine size / cost | **shared-cpu-1x @ 1 GB**, about $5-8 a month all-in | Within the ADR-057 budget. DuckDB runs client-side, so the server stays light. |

### Env vars (per ADR-064)

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | FastAPI app | `sqlite+pysqlite:////data/lead_state.sqlite3`. **Must point at the Volume**, not the default repo path (which is ephemeral in-container and unwatched by Litestream). |
| `AUTH_DEV_MODE` | Auth | `0` in the hosted app (fail-closed; the default is already `False`). |
| `AUTH_JWT_SECRET` | Auth | Signs identity-only session JWTs (rotating it revokes every active session). |
| `DEMO_MODE` | Auth | `1` in `morphy-demo`. Turns on the password-less read-only demo login (`POST /api/auth/demo`, ADR-077). Off unless explicitly truthy. When on, boot refuses unless `DEMO_USERNAME` names an existing read-only credential. |
| `DEMO_USERNAME` | Auth | The credential the demo login signs in as (default `demo`). |
| `OWNERS_INDEX_PATH` | FastAPI app | `/data/processed/composite/owners_index.json`. The owners index ships in the served composite on the Volume, **not** the default repo path. |
| `LITESTREAM_DB_PATH` | Litestream | `/data/lead_state.sqlite3`, the DB to replicate (same file as `DATABASE_URL`). |
| `LITESTREAM_BUCKET` / `LITESTREAM_ENDPOINT` | Litestream + `rclone` | R2 bucket + endpoint (`https://<acct>.r2.cloudflarestorage.com`). |
| `LITESTREAM_PATH` / `LITESTREAM_REGION` | Litestream | Replica prefix (`lead_state`) + region (`auto` for R2). |
| `LITESTREAM_ACCESS_KEY_ID` / `LITESTREAM_SECRET_ACCESS_KEY` | Litestream + `rclone` | R2 keys (Fly secrets). |
| `SITE_ROOT` / `DATA_WEB_ROOT` / `BACKEND_UPSTREAM` / `CADDY_PORT` | Caddy | Image defaults (`/srv/dist` · `/` · `127.0.0.1:8000` · `8080`); the same names the edge-serving test sets. |
| `VITE_MAPTILER_KEY` | SPA build (Docker build arg) | `deploy.sh code` reads it from the repo-root `.env` (git-ignored) and passes it as `--build-arg`. Empty builds the SPA with the keyless basemap. It is a client-side key, not a secret, so it ships in the public bundle. Restrict it to the demo domain (`morphy-demo.fly.dev`) in the MapTiler dashboard's allowed-origins setting. |

Secrets (`AUTH_JWT_SECRET`, the `LITESTREAM_*` R2 keys + bucket/endpoint) go in **Fly secrets**. Non-secret env (`AUTH_DEV_MODE`, `DEMO_MODE`, `DEMO_USERNAME`, `DATABASE_URL`, `OWNERS_INDEX_PATH`, `LITESTREAM_DB_PATH`/`PATH`/`REGION`, the Caddy vars) goes in `fly.toml [env]`. Never in the repo. **There is no `BACKEND_BASE_URL`.** The map app resolves its API base as `VITE_API_BASE ?? '/api'` (`app/src/lib/leads-api.ts`), so single-origin Caddy needs nothing set, and a later hostname change needs no rebuild.

### Deploy artifacts (repo root)

| Artifact | Role | Tested by |
|---|---|---|
| `Dockerfile` | Multi-stage: node builds `app/dist` (taking `VITE_MAPTILER_KEY` as a build arg, empty by default); the runtime bundles Caddy 2.11 + Litestream 0.5.11 + rclone 1.74 (from their official images) + restic + supervisor + the backend. | Built at `fly deploy` (needs Docker). |
| `.dockerignore` | Keeps the 15 GB `data/` (and any legacy `users.txt`) out of the build context. | None |
| `fly.toml` | One machine, US region, 10 GB volume at `/data`, `[env]`, `/api/health` check, `min_machines_running=1`, `auto_stop_machines=off`. | None |
| `Caddyfile` | SPA fallback; `/data/processed/*` gated by `forward_auth` → `/api/auth/check` (ADR-069) with Range/206 + gzip + `Cache-Control: private, no-store`; `/api/*` → uvicorn; HSTS; the rest of `/data/*` (the DB) answers 404 and is never served. | `tests/test_caddy_serving.py` (real caddy) |
| `supervisord.conf` | Runs uvicorn + Caddy + Litestream in the one machine; all logs → stdout (`fly logs`). When `DEMO_MODE` is truthy, the uvicorn program first runs the idempotent `python -m app.demo_seed`, so the read-only demo credential exists before boot checks for it. | None |
| `litestream.yml` | Continuous SQLite → R2 replication (env-driven; the same file for the hosted app and the restore drill). | `tests/test_litestream_restore.py` (real litestream + minio) |
| `deploy.sh` | `code` (`fly deploy`; **refuses a dirty working tree**, `ALLOW_DIRTY=1` overrides; forwards `VITE_MAPTILER_KEY` from `.env`), `data` (laptop → R2 → volume via `scripts/sync_composite.py`, mirror, **dry-run by default**), `all`, `smoke`. | `shellcheck` clean |
| `scripts/sync_composite.py` | Owns the served-composite include/exclude contract (drops `*/parcels/` compose-inputs, keeps `parcels.pmtiles`); drives rclone (mirror, dry-run, idempotent). | `tests/test_sync_composite.py` (real rclone) |

**Image dependency decision.** The image installs the **`backend` dependency group exported from `uv.lock`** (the slim FastAPI/uvicorn/SQLAlchemy/PyJWT/psycopg set, hash-pinned to the same locked graph CI tests). It does **not** install the pipeline groups. Those carry geopandas/shapely/pyproj, used only by preprocess, which never runs in this image. The old `backend/requirements.txt` is retired; the group lives in the root `pyproject.toml`. There are **no** systemd units (that was the bare-VM path, not taken).

### Provisioning runbook (operator steps)

Each step needs credentials or accounts the build can't supply. Run in order.

`APP` below is your globally unique Fly app name. `fly.toml` ships with `app = "morphy-demo"`;
pick your own name and set `app =` to match. `fly deploy` builds the image on Fly's remote
builder, so **no local Docker is required**.

```bash
# 1. flyctl + app + 10 GB volume (region must match fly.toml primary_region;
#    the volume name must match [[mounts]] source)
fly auth login
fly apps create "$APP"                            # then set app = "$APP" in fly.toml
fly volume create morphy_data --size 10 --region iad --app "$APP"

# 2. Private R2 bucket + an S3 API token (access key / secret) in Cloudflare R2.

# 3. Secrets (never in the repo): JWT signing secret + R2 config/keys. The
#    RCLONE_CONFIG_R2_* set lets the in-machine rclone resolve `r2:` for leg 2.
fly secrets set --app "$APP" \
  AUTH_JWT_SECRET="$(openssl rand -base64 48)" \
  LITESTREAM_BUCKET=<bucket> \
  LITESTREAM_ENDPOINT=https://<account>.r2.cloudflarestorage.com \
  LITESTREAM_ACCESS_KEY_ID=<key> LITESTREAM_SECRET_ACCESS_KEY=<secret> \
  RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
  RCLONE_CONFIG_R2_ACCESS_KEY_ID=<key> RCLONE_CONFIG_R2_SECRET_ACCESS_KEY=<secret> \
  RCLONE_CONFIG_R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com \
  RCLONE_CONFIG_R2_REGION=auto

# 4. First deploy (remote build). uvicorn FAIL-CLOSES until a credential row
#    exists (intended, ADR-063/069), so /api/health stays red and the machine
#    looks unhealthy until step 5. That is expected, not a bug.
#    With DEMO_MODE=1 (the fly.toml default) supervisord runs the demo seed
#    first, which creates the read-only `demo` credential, so boot succeeds
#    without step 5. Skip step 5 for a demo-only deployment.
FLY_APP="$APP" ./deploy.sh code

# 5. Bootstrap the first user. INTERACTIVE (hidden password prompt; positional
#    <username> <team>). Writes the credential table in the volume DB; uvicorn
#    then recovers on its next restart (no redeploy for later user changes).
#    (Migrating an existing users.txt instead: python -m app.users import-file <path>)
fly ssh console --app "$APP"
#   inside the machine:
#     cd /srv/backend && python -m app.users add <username> <team>
#     (type + confirm the password, then `exit`)

# 6. Confirm the pipe is live
fly status --app "$APP"
curl -fsS "https://$APP.fly.dev/api/health"       # {"status":"ok",...}

# 7. Sync the ~4.29 GB served composite (dry-run first, then --apply).
#    Configure a local rclone 'r2' remote first, e.g.:
#      rclone config create r2 s3 provider=Cloudflare access_key_id=<key> \
#        secret_access_key=<secret> endpoint=https://<account>.r2.cloudflarestorage.com region=auto
FLY_APP="$APP" R2_REMOTE=r2:<bucket>/composite ./deploy.sh data           # dry-run
FLY_APP="$APP" R2_REMOTE=r2:<bucket>/composite ./deploy.sh data --apply   # laptop→R2→volume

# 8. Verify + durability
FLY_APP="$APP" ./deploy.sh smoke   # SPA 200, unauth /data→401 (gated), /api live (APP_URL defaults to https://$APP.fly.dev)
#    then do a full login round-trip in the browser.
#    Fly volume snapshots are automatic (daily); extend retention as desired.
#    Litestream restore drill: tests/test_litestream_restore.py is its rehearsal.
```

### Day-2 operations (updating a running app)

The hosted app is one Docker image (SPA + FastAPI + Caddy + Litestream + rclone) on
one Fly machine. **Updating it** means rebuilding that image or refreshing the
data on its volume. `deploy.sh` defaults to `FLY_APP=morphy-demo` and
`R2_REMOTE=r2:morphy-prod/composite`. Override them only to target a different environment.

**Update the code, the common case (any frontend or backend change):**

```bash
git checkout main && git pull                       # deploy from a clean, current tree
./deploy.sh code                                    # remote build → roll the machine
./deploy.sh smoke                                   # SPA 200 · unauth /data 401 · /api/health 200
```

`fly deploy` ships the **working tree**, not `git HEAD`, so deploy from a clean
checkout of exactly what you want live. `deploy.sh code` enforces this: it aborts
on a dirty tree (`ALLOW_DIRTY=1` overrides for a deliberate local experiment). The
remote builder compiles `app/dist` and assembles the runtime layer. The single
machine then rolls to the new image. Expect a blip of a few seconds; with one machine and a
single SQLite writer there is no zero-downtime rollout. Hard-refresh the browser
afterward, since it may hold old JS.

**Update the map data (after a recompose):**

```bash
./deploy.sh data                                    # dry-run (default)
./deploy.sh data --apply                            # laptop→R2→volume
fly apps restart morphy-demo                        # REQUIRED: reload the owners index (see conventions)
```

> **One-time step after the ADR-075 owners-index v10 sync:** the cross-state key
> recipe changed (name-only → name+state), so every `display_cluster_id` changed and
> existing lead state and merge overrides had to be repointed once. After the data sync,
> before or with the restart, run the idempotent remap on the machine (it reads the
> `owner_key_migration.json` sidecar shipped in the composite):
> ```bash
> fly ssh console --app morphy-demo
>   cd /srv/backend && python -m app.remap_owner_clusters --dry-run   # report first
>   cd /srv/backend && python -m app.remap_owner_clusters            # apply
> ```
> Safe to re-run (new keys are never map keys, so a re-run is a no-op). Only needed for the v10 cutover.

**Manage users (add / remove / re-team), no redeploy:**

```bash
fly ssh console --app morphy-demo
  cd /srv/backend && python -m app.users add <username> <team>   # positional args + hidden password prompt
  # ... list / remove / set-team via `python -m app.users --help`; then `exit`
```

The credential table is authoritative **per request**, so changes apply on the
next click. Never redeploy for a user change, and never hand-edit hashes (ADR-069). The CLI
writes the same volume DB Litestream replicates, so credentials are in the continuous
backup.

**Everything else:**

| Change | Command |
|---|---|
| A **secret** (JWT / R2) | `fly secrets set NAME=value --app morphy-demo`, which restarts the machine |
| A **non-secret env var** (`fly.toml [env]`) | Edit `fly.toml`, then `./deploy.sh code` (it's deploy config) |
| **Restart** the machine | `fly apps restart morphy-demo` |
| **Logs / status / shell** | `fly logs` · `fly status` · `fly ssh console` (all `--app morphy-demo`) |
| **Roll back** a bad deploy | `git checkout <good-sha>` → `./deploy.sh code`. This is fine while the schema hasn't moved past the old code's Alembic head. If the bad deploy ran a migration the old code can't read, write a `downgrade`-driven fix forward instead of rolling back blindly. |

**Conventions that must hold:**

- **One machine, one SQLite writer.** Never scale to more than one machine, never add a Fly
  `[processes]` block, and never turn `auto_stop_machines` on. Each breaks the
  single-volume, single-writer invariant.
- **Deploy from a clean tree** (the guard enforces it). The image *is* the tree,
  not the commit.
- **Restart after a data sync.** The backend caches `owners_index.json` at boot,
  so a fresh sync shows `owners_indexed: 0` until you `fly apps restart`.
- **Don't restart mid-sync.** A restart kills the in-machine `fly ssh` rclone leg
  and leaves the volume partial. Let `deploy.sh data` finish (it's idempotent, so a
  re-run repairs a partial sync).
- **Auth stays fail-closed** ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)). Never set `AUTH_DEV_MODE=1` in the hosted app, never put tenant or team claims in
  the JWT, never web-serve the DB, and never weaken the `/data/processed/*`
  `forward_auth` gate (`deploy.sh smoke` asserts unauth → 401/403).
- **`/data/*` is PII.** Caddy marks it `Cache-Control: private, no-store`. If a caching proxy
  or CDN is ever put in front, it needs a cache-bypass rule for `/data/*` so PII never sits at
  the edge.
- **Schema changes** ship as Alembic revisions (see
  `backend/README.md` "Migrations"). The app runs upgrade-to-head at boot,
  which is safe *because of* the one-machine, one-writer invariant above. If that
  invariant ever falls (multiple machines, multi-writer Postgres), move the
  upgrade out of boot and into a release step that runs once before new code
  starts.

### Local / CI commands

```bash
# Local backend (SQLite default; no Postgres needed)
cd backend && uvicorn app.main:app --reload --port 8000

# Tests (the four hosting modules need rclone / caddy / litestream + minio installed)
pytest                                          # full suite (test.yml gate)
pytest tests/test_sync_composite.py tests/test_caddy_serving.py tests/test_litestream_restore.py

# CI runs four pull-request merge gates; run all before declaring done:
ruff check . && ruff format --check .           # lint.yml (also runs pyright on backend/)
cd app && npm run check && npm run test:unit    # frontend.yml (svelte-check + vitest + vite build)
# + test.yml (pytest, above) and api-types.yml (OpenAPI→TS drift: regenerate backend/openapi.json + app/src/lib/api-types.ts after any backend model change; both must match)
```

### PII custody (see [SECURITY.md](./SECURITY.md))

- HTTPS everywhere (TLS at Fly's edge, HSTS from Caddy).
- The 4.29 GB of parcel-owner PII stays **same-origin behind the login**, enforced at the edge: Caddy `forward_auth` refuses unauthenticated `/data/processed/*` (ADR-069; `deploy.sh smoke` asserts it). Caddy marks it `Cache-Control: private, no-store` so no cache keeps it.
- SQLite lives on the encrypted Volume, and Litestream replicates it to a private R2 bucket. Lease PDFs on the volume with signed download URLs were planned with D+E but never built.
- Session JWTs expire (30-day TTL by default, `AUTH_SESSION_TTL_DAYS`); rotating `AUTH_JWT_SECRET` revokes every session at once.
- Multi-tenancy isolation tests gate every pull request.

## 9. Map-app static deployment (considered, never built)

A static-only hosting path for the map app was considered but never built:

- Map app as a static hosted bundle (S3 + CloudFront, Cloudflare Pages, or Vercel), with no backend changes from the D+E backend (§8).
- Per-state PMTiles served via HTTP range requests.
- DuckDB-WASM queries parquet directly from object storage.
- Access control via Cloudflare Access or a login gate on the static bundle.
- Parcel data PII never publicly cached or indexed.

See [STATUS.md](./STATUS.md) for where the work stopped.

---

## 10. Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Data TUI fails to launch | Out-of-date environment | `uv sync` (Textual is in the `tui` group) |
| Preprocess fails: `ImportError: openpyxl` | Out-of-date environment | `uv sync` (openpyxl is in the pipeline group) |
| Map app shows "Could not load the map data" | Data server down | Start `python scripts/serve.py 8765` from the repo root, not `http.server` (it has no Range support) |
| Stale manifest disagrees with disk | Interrupted run | `python scripts/preprocess.py --rebuild-manifest` |
| Tests fail with "no such fixture" | New fixture not created | Run `pytest --collect-only` to see test IDs; check `tests/fixtures/` |
| Satellite basemap missing | No MapTiler key at build time | Set `VITE_MAPTILER_KEY` in `app/.env` (dev) or the repo-root `.env` (deploy), then rebuild |
