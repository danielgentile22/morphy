# DEPLOYMENT — How this runs

**Last updated:** 2026-06-04
**Status:** **Live in production** at [morphyconsulting.com](https://morphyconsulting.com) (Fly app `morphy-consulting`, region `iad`) since 2026-06-04 — the hosted-private backend shipped per [ADR-055](./adr/0055-hosted-private-backend.md) as narrowed by [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md) (#96 built, #16 closed). Local dev still runs all four surfaces on a laptop (§1). **To update the running app, see §8 → "Day-2 operations".**

This doc describes how to stand up the project — what to install, how to run each subsystem, how to ship outputs to a partner, and what Slice 4 adds when the backend lands.

---

## 1. Where this runs (local development)

All four surfaces run locally on a developer's machine (the hosted app is §8):

| Surface | Run command | Port / location |
|---|---|---|
| **Puller** | `python -m app_puller` | Desktop window |
| **Preprocess CLI** | `python scripts/preprocess.py [flags]` | Terminal |
| **Map app** | `python scripts/serve.py 8765` + `cd app && npm run dev` | localhost:5173 |
| **Tests** | `pytest` · `cd app && npm run test:unit && npm run test:e2e` | Terminal |

**The hosted-private backend is now live** (§8) — a single Fly.io machine + SQLite-on-volume + Cloudflare R2 + FastAPI + username/password auth (Claude API for lease extraction lands with D+E). The map app stays static; it talks to the backend over a thin API for the write-layer features (lead state, lease upload, activity log, scoring profiles per user). The local commands above are still how you develop; **to ship a change to the live app, see §8 → "Day-2 operations".**

---

## 2. Prerequisites

| Component | Version | Why |
|---|---|---|
| Python | 3.11 | Tested baseline; pyogrio + PySide6 known good |
| macOS arm64 / Linux x86_64 | Any recent | macOS arm64 is the primary dev environment |
| Homebrew (macOS) | — | For `gh` CLI and `tippecanoe` |
| Disk space | ≥ 50 GB free | Raw data + composites; AR alone is ~3 GB raw, ~5 GB normalized |
| RAM | ≥ 16 GB recommended | Preprocess on AR (2.1M rows) peaks at ~6 GB RSS |
| Node.js | ≥ 20 | Vite + Svelte build for the map app |
| Tippecanoe | ≥ 2.45 | `parcels.pmtiles` generation (`preprocess.py --tiles`) |

---

## 3. First-time setup

```bash
# Clone (after Section 2 of the work plan creates the GitHub repo)
git clone git@github.com:<user>/pilot.git
cd pilot

# Python environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify installation
python scripts/verify_raw.py     # No raw data yet — expect "missing" rows
python -m app_puller             # Should launch the puller window
```

The first run sets up empty `data/raw/` and `data/processed/`
directories (gitignored).

---

## 4. Standard workflow

### 4.1 Refresh data

1. Launch the puller: `python -m app_puller`.
2. Click **Check for updates** (parallel HEAD across all sources).
3. The puller's "What needs my attention" panel surfaces:
   - Auto sources past their `next_recommended_check_at` → click
     **Pull all stale** to refresh.
   - Manual sources stale → walkthrough modal guides each download.
4. Click **Rescan disk** after any manual download.
5. Click **Verify contents** to confirm each source has expected files.

### 4.2 Preprocess

Either via the puller:

- Click **Preprocess** → state dropdown (or "all") → click **Run**.

Or via CLI:

```bash
python scripts/preprocess.py                   # everything
python scripts/preprocess.py --state 05        # one state
python scripts/preprocess.py --source ar_parcels --force-rebuild
python scripts/preprocess.py --rebuild-manifest  # sync manifest from disk
```

Outputs land at `data/processed/normalized/<source>/` and
`data/processed/composite/<state_fips>/`.

### 4.3 Build the app's data assets + view the map

```bash
python scripts/preprocess.py --app-assets   # index.json + per-state facets / slim parquet / county boundaries
python scripts/preprocess.py --tiles        # per-state parcels.pmtiles (needs tippecanoe)

python scripts/serve.py 8765                # range-capable data server, from the repo root
cd app && npm install && npm run dev        # http://localhost:5173  (?state=05 to deep-link)
```

`python -m http.server` does **not** work for the app — PMTiles and
DuckDB-WASM need HTTP Range / 206, which it does not send; `serve.py`
does. The app auto-discovers composed states via `composite/index.json`.
See [app/ARCHITECTURE.md](../app/ARCHITECTURE.md).

### 4.4 Run tests

```bash
pytest                                     # preprocess pipeline + app-asset scripts
pytest --cov=scripts.preprocess            # with coverage
ruff check . && ruff format --check .      # lint + format
cd app && npm run check && npm run test:unit && npm run test:e2e
```

---

## 5. Sharing outputs (no hosted instance)

Until hosted deployment lands, sharing the system with a partner /
investor means:

### 5.1 Best: walk them through live (screen share)

- Run the map app locally; share screen.
- Pitch scenarios in [SCOPE.md §5](./SCOPE.md) walk cleanly.

### 5.2 Static: hand them a ZIP

For asynchronous review:

```bash
# Bundle the public-facing app + per-state composites
tar -czf pilot-demo-$(date +%Y%m%d).tar.gz \
    app/ \
    data/processed/composite/05/ \
    data/processed/composite/37/ \
    docs/INVESTOR_BRIEF.md \
    docs/NUMBERS.md \
    docs/SCOPE.md \
    README.md
```

The recipient needs Node 20+: from `app/`, `npm install && npm run
build`, then run `python scripts/serve.py 8765` (repo root) +
`npm run preview` — see [../app/ARCHITECTURE.md](../app/ARCHITECTURE.md).
**PII caveat:** this tarball contains parcel-owner names + mailing
addresses. Encrypt at rest; share via a secure channel.

### 5.3 Pitch-deck assets

`docs/pitch-assets/*.png` / `*.gif` are the demo screenshots.
Reference these in the pitch deck. They live in the repo so a
co-founder onboarding the deck has the source files.

---

## 6. Environment variables

Most runs need no env vars. Optional:

| Variable | Used by | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | `scripts/diagnose.py` (puller "Diagnose this failure") | LLM-powered verify-failure diagnosis (~$0.04 per call) |
| `REGRID_S3_BUCKET`, `REGRID_S3_PREFIX`, `AWS_*` | `scripts/fetch/sources/regrid_parcels.py` | Only activates the Regrid source if all set (paid; out of scope for v1) |

Store in `.env` (git-ignored) and source before running:

```bash
source .env
python -m app_puller
```

---

## 7. Backups

Currently manual. Before any pitch:

1. `tar -czf backups/pilot-$(date +%Y%m%d-%H%M).tar.gz data/processed/`
   — composite outputs are the expensive thing; raw can always be
   re-pulled.
2. Push to a personal cloud backup (iCloud Drive, Dropbox, etc.) —
   **encrypted** because parcel data is PII.

Post-pitch: automated daily snapshot to a small object-storage
bucket; encrypted at rest.

---

## 8. Hosted-private backend (Slice 4 — D + E)

Locked in [ADR-055](./adr/0055-hosted-private-backend.md) (supersedes ADR-006 — static-site, no backend — for write-layer features only; read-only analytical layers stay static). The **platform, database, and object-store** choices below are **narrowed by [ADR-064](./adr/0064-phase1-hosting-fly-sqlite.md)** (2026-06-03 hosting-decision session): Fly.io single always-on machine + SQLite-on-volume + Cloudflare front, ~$5–8/mo — not the managed-Postgres + separate-S3-service shape ADR-055 originally defaulted to. **Live in production since 2026-06-04** at [morphyconsulting.com](https://morphyconsulting.com) (Fly app `morphy-consulting`, region `iad`, 10 GB volume, SQLite + Litestream → R2 `morphy-prod`, Cloudflare orange-cloud / Full-strict): deploy artifacts built (#96), cloud provisioned, issue #16 closed. The **provisioning runbook** below is the one-time stand-up; **"Day-2 operations" is how you update the running app.**

### Stack (per ADR-064)

| Component | Choice | Notes |
|---|---|---|
| Hosting | **Fly.io**, US region, **single always-on machine** (`min_machines_running=1`) | User chose the `fly deploy` PaaS over a ~$2/mo-cheaper bare VM. One machine only — SQLite is single-writer. |
| App | **FastAPI** (uvicorn) | Thin CRUD + auth + extraction-orchestration; same language as preprocess. |
| In-machine web server | **Caddy + uvicorn under supervisord** | Caddy serves `app/dist` (SPA) + `/data/*` Range/206 + gzip and reverse-proxies `/api/*` → uvicorn. Replaces `scripts/serve.py` in prod. (Fly `[processes]` is *not* used — it would spawn separate machines and break single-volume / single-writer.) |
| Storage | **Fly Volume, 10 GB** (`fly volume extend` later) | Holds the 4.29 GB served composite + SQLite + lease PDFs. The 4.29 GB stays **same-origin behind the login** (PII). |
| Database | **SQLite on the Volume** | `DATABASE_URL=sqlite+pysqlite:////data/lead_state.sqlite3`. Tenant isolation is app-level (identical to PG); schema is PG-portable. Avoids Fly Managed PG ($38/mo). Tenant-shaped schema from Day 1 — every table has `tenant_id`. |
| Object store | **Cloudflare R2** | Backups + (at D+E) lease PDFs; encrypted; private bucket. Also the laptop→R2→volume staging relay for data sync. |
| Backups | **Litestream → R2** (continuous SQLite) + Fly volume snapshots; restic→R2 for PDFs at D+E | Composite data is disposable (re-compose); precious = SQLite write-layer + lease PDFs. |
| Auth | **Username/password** (`credential` table in the volume DB) | Managed via `fly ssh` + `python -m app.users`; teams = tenants; identity-only HS256 JWTs in an httpOnly cookie; the credential table is authoritative per request, and Caddy `forward_auth` gates `/data/processed/*` behind it ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md) as amended by [ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). |
| Domain + perimeter | **Custom domain via Cloudflare Registrar**; **Cloudflare proxy (orange-cloud), no Access**; SSL Full (strict); cache-bypass `/data/*` | Edge DDoS + WAF + hidden origin + login rate-limiting, no extra user friction. App login stays the auth boundary; Access deferred. |
| LLM | **Anthropic Claude API** | Sonnet 4.6 default + Opus 4.7 retry for lease extraction ([ADR-059](./adr/0059-llm-lease-extraction.md)); prompt caching on. |
| Address normalization | **libpostal** (preferred) or **`usaddress`** (fallback) | For owner-cluster strengthening — pick at build time per dep-management friction. |
| Transport | **HTTPS only** (HSTS) | TLS at Cloudflare's edge + Fly's edge (Full strict). |
| Machine size / cost | **shared-cpu-1x @ 1 GB**, **~$5–8/mo** all-in + ~$10/yr domain | Within ADR-057 reframed budget. DuckDB runs client-side, so the server stays light. |

### Env vars (per ADR-064)

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | FastAPI app | `sqlite+pysqlite:////data/lead_state.sqlite3` — **must point at the Volume**, not the default repo path (which is ephemeral in-container and unwatched by Litestream). |
| `AUTH_DEV_MODE` | Auth surface | `0` in prod (fail-closed; the default is already `False`). |
| `AUTH_JWT_SECRET` | Auth surface | Signs identity-only session JWTs (rotating it revokes every active session). |
| `OWNERS_INDEX_PATH` | FastAPI app | `/data/processed/composite/owners_index.json` — the owners index ships in the served composite on the Volume, **not** the default repo path. |
| `LITESTREAM_DB_PATH` | Litestream | `/data/lead_state.sqlite3` — the DB to replicate (same file as `DATABASE_URL`). |
| `LITESTREAM_BUCKET` / `LITESTREAM_ENDPOINT` | Litestream + `rclone` | R2 bucket + endpoint (`https://<acct>.r2.cloudflarestorage.com`). |
| `LITESTREAM_PATH` / `LITESTREAM_REGION` | Litestream | Replica prefix (`lead_state`) + region (`auto` for R2). |
| `LITESTREAM_ACCESS_KEY_ID` / `LITESTREAM_SECRET_ACCESS_KEY` | Litestream + `rclone` | R2 keys (Fly secrets). |
| `SITE_ROOT` / `DATA_WEB_ROOT` / `BACKEND_UPSTREAM` / `CADDY_PORT` | Caddy | Image defaults (`/srv/dist` · `/` · `127.0.0.1:8000` · `8080`); same names the edge-serving test sets. |
| `ANTHROPIC_API_KEY` | Lease-extraction worker | Claude API (added at D+E). |

Secrets (`AUTH_JWT_SECRET`, the `LITESTREAM_*` R2 keys + bucket/endpoint, `ANTHROPIC_API_KEY`) go in **Fly secrets**; non-secret env (`AUTH_DEV_MODE`, `DATABASE_URL`, `OWNERS_INDEX_PATH`, `LITESTREAM_DB_PATH`/`PATH`/`REGION`, the Caddy vars) in `fly.toml [env]`. Never in repo. **No `BACKEND_BASE_URL`** — the map app resolves its API base as `VITE_API_BASE ?? '/api'` (`app/src/lib/leads-api.ts`), so single-origin Caddy needs nothing set, and a later domain change needs no rebuild.

### Deploy artifacts (issue #96 — built; at the repo root)

| Artifact | Role | Tested by |
|---|---|---|
| `Dockerfile` | Multi-stage: node builds `app/dist`; runtime bundles Caddy 2.11 + Litestream 0.5.11 + rclone 1.74 (from their official images) + restic + supervisor + the backend. | Built at `fly deploy` (needs Docker). |
| `.dockerignore` | Keeps the 15 GB `data/` (and any legacy `users.txt`) out of the build context. | — |
| `fly.toml` | One machine, US region, 10 GB volume at `/data`, `[env]`, `/api/health` check, `min_machines_running=1`, `auto_stop_machines=off`. | — |
| `Caddyfile` | SPA fallback; `/data/processed/*` gated by `forward_auth` → `/api/auth/check` (ADR-069) with Range/206 + gzip + `Cache-Control: private, no-store`; `/api/*` → uvicorn; HSTS; the DB never served. | `tests/test_caddy_serving.py` (real caddy) |
| `supervisord.conf` | Runs uvicorn + Caddy + Litestream in the one machine; all logs → stdout (`fly logs`). | — |
| `litestream.yml` | Continuous SQLite → R2 replication (env-driven; same file for prod + the drill). | `tests/test_litestream_restore.py` (real litestream + minio) |
| `deploy.sh` | `code` (`fly deploy`; **refuses a dirty working tree** — `ALLOW_DIRTY=1` overrides), `data` (laptop → R2 → volume via `scripts/sync_composite.py`, mirror, **dry-run by default**), `all`, `smoke`. | `shellcheck` clean |
| `scripts/sync_composite.py` | Owns the served-composite include/exclude contract (drops `*/parcels/` compose-inputs, keeps `parcels.pmtiles`); drives rclone (mirror / dry-run / idempotent). | `tests/test_sync_composite.py` (real rclone) |

**Image dependency decision (PRD #96).** The image installs **`backend/requirements.txt`** (the slim FastAPI/uvicorn/SQLAlchemy/PyJWT set), **not** the root `requirements.txt` — the latter carries geopandas/shapely/pyproj/PySide6 used only by the preprocess pipeline, which never runs in this image. (The PRD's fallback "extract a slim subset" was unnecessary: that subset already existed as `backend/requirements.txt`.) **Not** systemd units (that was the bare-VM path, not taken).

### Provisioning runbook (operator — needs your hands)

Each step needs credentials/accounts the build can't supply. Run in order:

`APP` below is your globally-unique Fly app name (`pilot-app` is likely taken —
pick your own and set `app =` in fly.toml to match). `fly deploy` builds the
image on Fly's remote builder, so **no local Docker is required**.

```bash
# 1. flyctl + app + 10 GB volume (region must match fly.toml primary_region)
fly auth login
fly apps create "$APP"                            # then set app = "$APP" in fly.toml
fly volume create pilot_data --size 10 --region iad --app "$APP"

# 2. Domain at Cloudflare Registrar (manual, in the dashboard) — ~$10/yr.

# 3. Private R2 bucket + an S3 API token (access key / secret) — Cloudflare R2.

# 4. Secrets (never in the repo): JWT signing secret + R2 config/keys. The
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

# 5. First deploy (remote build). uvicorn FAIL-CLOSES until a credential row
#    exists (intended, ADR-063/069), so /api/health stays red and the machine
#    looks unhealthy until step 6 — that is expected, not a bug.
FLY_APP="$APP" ./deploy.sh code

# 6. Bootstrap the first user — INTERACTIVE (hidden password prompt; positional
#    <username> <team>). Writes the credential table in the volume DB; uvicorn
#    then self-heals on its next restart (no redeploy for later user changes).
#    (Migrating an existing users.txt instead: python -m app.users import-file <path>)
fly ssh console --app "$APP"
#   inside the machine:
#     cd /srv/backend && python -m app.users add <username> <team>
#     (type + confirm the password, then `exit`)

# 7. Confirm the pipe is live
fly status --app "$APP"
curl -fsS "https://$APP.fly.dev/api/health"       # {"status":"ok",...}

# 8. Sync the ~4.29 GB served composite (dry-run first, then --apply).
#    Configure a local rclone 'r2' remote first, e.g.:
#      rclone config create r2 s3 provider=Cloudflare access_key_id=<key> \
#        secret_access_key=<secret> endpoint=https://<account>.r2.cloudflarestorage.com region=auto
FLY_APP="$APP" R2_REMOTE=r2:<bucket>/composite ./deploy.sh data           # dry-run
FLY_APP="$APP" R2_REMOTE=r2:<bucket>/composite ./deploy.sh data --apply   # laptop→R2→volume

# 9. Custom domain + Cloudflare edge
fly certs add <domain> --app "$APP"               # then `fly certs show <domain>` for DNS records
#    Cloudflare: DNS → Fly, orange-cloud proxy, SSL Full (strict),
#    a cache rule that BYPASSES cache for /data/* (PII never at the edge),
#    optional rate-limit on /api/auth/login.

# 10. Verify + durability
FLY_APP="$APP" APP_URL="https://<domain>" ./deploy.sh smoke   # SPA 200, unauth /data→401 (gated), /api live
#    then run /verify for the full login round-trip.
#    Fly volume snapshots are automatic (daily); extend retention as desired.
#    Litestream restore drill: tests/test_litestream_restore.py is its rehearsal.
```

### Day-2 operations (updating the live app)

The live app is one Docker image (SPA + FastAPI + Caddy + Litestream + rclone) on
one Fly machine. **Updating it** means rebuilding that image or refreshing the
data on its volume. All commands assume `FLY_APP=morphy-consulting`.

**Update the code — the common case (any frontend or backend change):**

```bash
git checkout main && git pull                       # deploy from a clean, current tree
FLY_APP=morphy-consulting ./deploy.sh code          # remote build → roll the machine
FLY_APP=morphy-consulting ./deploy.sh smoke         # SPA 200 · unauth /data 401 · /api/health 200
```

`fly deploy` ships the **working tree**, not `git HEAD` — so deploy from a clean
checkout of exactly what you want live. `deploy.sh code` enforces this: it aborts
on a dirty tree (`ALLOW_DIRTY=1` overrides for a deliberate local experiment). The
remote builder compiles `app/dist` and assembles the runtime layer; the single
machine then rolls to the new image (a few seconds' blip — one machine, single
SQLite writer, so there's no zero-downtime rollout). Hard-refresh the browser
after (Cloudflare won't cache the SPA shell, but your browser may hold old JS).

**Update the map data (after a recompose):**

```bash
FLY_APP=morphy-consulting R2_REMOTE=r2:morphy-prod/composite ./deploy.sh data          # dry-run (default)
FLY_APP=morphy-consulting R2_REMOTE=r2:morphy-prod/composite ./deploy.sh data --apply  # laptop→R2→volume
fly apps restart morphy-consulting                  # REQUIRED — reload the owners index (see gotchas)
```

**Manage users (add / remove / re-team) — no redeploy:**

```bash
fly ssh console --app morphy-consulting
  cd /srv/backend && python -m app.users add <username> <team>   # positional args + hidden password prompt
  # ... list / remove via `python -m app.users --help`; then `exit`
```

The credential table is authoritative **per request**, so changes apply on the
next click — never a redeploy, never hand-edit hashes (ADR-069; the CLI writes
the same volume DB Litestream replicates, so credentials are in the continuous
backup).

**Everything else:**

| Change | Command |
|---|---|
| A **secret** (JWT / R2 / Anthropic key) | `fly secrets set NAME=value --app morphy-consulting` — auto-restarts the machine |
| A **non-secret env var** (`fly.toml [env]`) | edit `fly.toml`, then `./deploy.sh code` (it's deploy config) |
| **Restart** the machine | `fly apps restart morphy-consulting` |
| **Logs / status / shell** | `fly logs` · `fly status` · `fly ssh console` (all `--app morphy-consulting`) |
| **Roll back** a bad deploy | `git checkout <good-sha>` → `./deploy.sh code` (the `init_db` migration is additive, so older code stays compatible) |

**Conventions that must hold (don't violate these):**

- **One machine, one SQLite writer.** Never scale to >1 machine, never add a Fly
  `[processes]` block, never turn `auto_stop_machines` on — each breaks the
  single-volume / single-writer invariant.
- **Deploy from a clean tree** (the guard enforces it) — the image *is* the tree,
  not the commit.
- **Restart after a data sync** — the backend caches `owners_index.json` at boot,
  so a fresh sync shows `owners_indexed: 0` until you `fly apps restart`.
- **Don't restart mid-sync** — a restart kills the in-machine `fly ssh` rclone leg
  and leaves the volume partial. Let `deploy.sh data` finish (it's idempotent — a
  re-run repairs a partial).
- **Auth stays fail-closed** ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)) — never `AUTH_DEV_MODE=1` in prod, never put tenant/team claims in
  the JWT, never web-serve the DB, never weaken the `/data/processed/*`
  `forward_auth` gate (`deploy.sh smoke` asserts unauth → 401/403).
- **`/data/*` is PII** — keep it cache-bypassed at Cloudflare (orange-cloud + the
  `/data/*` cache rule); it must never sit at the edge.
- **Schema changes** ride the additive `init_db` migration until Alembic lands.

### Local / CI commands

```bash
# Local backend (SQLite default; no Postgres needed)
cd backend && uvicorn app.main:app --reload --port 8000

# Tests (the four hosting modules need rclone / caddy / litestream + minio installed)
pytest                                          # full suite
pytest tests/test_sync_composite.py tests/test_caddy_serving.py tests/test_litestream_restore.py
ruff check . && ruff format --check .           # the only real CI gate — run before declaring done
```

### PII custody (see [SECURITY.md](./SECURITY.md))

- HTTPS everywhere (Cloudflare + Fly edges, HSTS); origin IP hidden behind Cloudflare.
- The 4.29 GB of parcel-owner PII stays **same-origin behind the login**, enforced at the edge: Caddy `forward_auth` refuses unauthenticated `/data/processed/*` (ADR-069; `deploy.sh smoke` asserts it). `/data/*` is cache-bypassed at Cloudflare so PII never sits at the edge.
- SQLite + lease PDFs on the encrypted Volume; Litestream replicates SQLite to a private R2 bucket; lease PDFs served via signed download URLs only (at D+E).
- Session JWTs expire (30-day TTL); rotating `AUTH_JWT_SECRET` revokes every session at once.
- Multi-tenancy isolation tests gate every PR.

## 9. Map-app static deployment (Phase 2+)

For when the project sells to a third user or you want a hosted demo (Phase 3 path):

- Map app: static-site hosted bundle (S3 + CloudFront / Cloudflare Pages / Vercel) — no backend changes from Slice 4.
- Per-state PMTiles served via HTTP range requests.
- DuckDB-WASM queries parquet directly from object storage.
- Access controls via Cloudflare Access or a login gate on the static bundle.
- Parcel data PII never publicly cached / indexed.

Not built. Tracked in [ROADMAP.md](./ROADMAP.md) → Phase 3.

---

## 10. Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Puller crashes on launch | PySide6 version mismatch | `pip install --upgrade --force-reinstall PySide6==6.7.3` |
| Preprocess fails: `ImportError: openpyxl` | Missing optional dep | `pip install -r requirements.txt` (openpyxl is now required) |
| Map app shows "Could not load the map data" | Data server down | Start `python scripts/serve.py 8765` from the repo root — not `http.server` (it has no Range support) |
| Stale manifest disagrees with disk | Interrupted run | `python scripts/preprocess.py --rebuild-manifest` |
| Tests fail with "no such fixture" | New fixture not created | Run `pytest --collect-only` to see test IDs; check `tests/fixtures/` |
