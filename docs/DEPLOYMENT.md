# DEPLOYMENT — How this runs

**Last updated:** 2026-05-25
**Status:** Phase 1 = local data pipeline + map app today; **hosted-private backend stands up in Slice 4** (lease docs + lead state + auth) per [ADR-055](./adr/0055-hosted-private-backend.md).

This doc describes how to stand up the project — what to install, how to run each subsystem, how to ship outputs to a partner, and what Slice 4 adds when the backend lands.

---

## 1. Where this runs today (pre-Slice 4)

All four surfaces run locally on a developer's machine:

| Surface | Run command | Port / location |
|---|---|---|
| **Puller** | `python -m app_puller` | Desktop window |
| **Preprocess CLI** | `python scripts/preprocess.py [flags]` | Terminal |
| **Map app** | `python scripts/serve.py 8765` + `cd app && npm run dev` | localhost:5173 |
| **Tests** | `pytest` · `cd app && npm run test:unit && npm run test:e2e` | Terminal |

**Slice 4 (D + E) adds a hosted-private backend** — small VM + Postgres + S3-compatible object store + FastAPI + username/password auth + Claude API for lease extraction. The map app remains static; it talks to the backend over a thin API for the write-layer features (lead state, lease upload, activity log, scoring profiles per user). See §8 for the deployment shape.

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

Locked in [ADR-055](./adr/0055-hosted-private-backend.md). Supersedes ADR-006 (static-site, no backend) for write-layer features only — read-only analytical layers (parquet, PMTiles, GeoJSON) stay static.

### Stack

| Component | Choice (Slice 4 default) | Notes |
|---|---|---|
| Hosting | Small VM — **Fly.io / Render / Hetzner** class | Any will do; pick at Slice 4 implementation time |
| App | **FastAPI** (Python) | Same language as preprocess; thin CRUD + auth + extraction-orchestration surface |
| Database | **Postgres** (managed in prod; testcontainers in CI) | Tenant-shaped schema from Day 1 — every table has `tenant_id` |
| Object store | **S3-compatible** — Backblaze B2 / Cloudflare R2 / AWS S3 | Lease PDFs; encrypted at rest; signed download URLs only |
| Auth | **Username/password** (`backend/users.txt`) | File-based credentials managed via `python -m app.users`; teams = tenants; identity-only HS256 JWTs, file authoritative per request ([ADR-062](./adr/0062-username-password-replaces-magic-link.md) / [ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)) |
| LLM | **Anthropic Claude API** | Sonnet 4.6 default + Opus 4.7 retry for lease extraction ([ADR-059](./adr/0059-llm-lease-extraction.md)); prompt caching on |
| Address normalization | **libpostal** (preferred) or **`usaddress`** (fallback) | For owner-cluster strengthening — pick at build time per dep-management friction |
| Transport | **HTTPS only** (HSTS) | TLS terminated at the host platform's edge |
| Cost (Phase 1) | ~$30–100 / month | Within ADR-057 reframed budget |

### Env vars (Slice 4)

| Variable | Used by | Purpose |
|---|---|---|
| `DATABASE_URL` | FastAPI app | Managed Postgres connection string |
| `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | FastAPI app | Lease PDF object store |
| `ANTHROPIC_API_KEY` | Lease-extraction worker | Claude API |
| `APP_USERS_FILE` | Auth surface | Path to the mounted credentials file (default `backend/users.txt`; one `username:hash:team` line per user, managed via `python -m app.users`) |
| `AUTH_JWT_SECRET` | Auth surface | Signing user-session JWTs (rotating it revokes every active session) |
| `BACKEND_BASE_URL` | Map app | Where the API is reachable |

Stored in the host platform's secret store (Fly secrets / Render env vars / Hetzner vault). Never in repo.

### Run commands (Slice 4 — placeholders until build)

```bash
# Local backend (after Slice 4 lands)
cd backend
poetry install
DATABASE_URL=postgres://... S3_BUCKET=... ANTHROPIC_API_KEY=... \
  uvicorn app.main:app --reload --port 8000

# Migrations
cd backend && alembic upgrade head

# Tests
cd backend && pytest                       # spins testcontainers-postgres
cd backend && pytest -k tenant_isolation   # multi-tenancy isolation specifically
cd backend && pytest -m llm_eval           # gold-set LLM extraction eval (gating CI check)

# Production deploy (vendor-specific; example for Fly)
fly deploy --app pilot-backend
```

### PII custody (see [SECURITY.md](./SECURITY.md))

- HTTPS everywhere; HSTS.
- Postgres TLS in transit, encryption at rest, daily backups.
- S3 bucket private; SSE-S3 or KMS encryption; signed download URLs only.
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

## 9. Quick troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Puller crashes on launch | PySide6 version mismatch | `pip install --upgrade --force-reinstall PySide6==6.7.3` |
| Preprocess fails: `ImportError: openpyxl` | Missing optional dep | `pip install -r requirements.txt` (openpyxl is now required) |
| Map app shows "Could not load the map data" | Data server down | Start `python scripts/serve.py 8765` from the repo root — not `http.server` (it has no Range support) |
| Stale manifest disagrees with disk | Interrupted run | `python scripts/preprocess.py --rebuild-manifest` |
| Tests fail with "no such fixture" | New fixture not created | Run `pytest --collect-only` to see test IDs; check `tests/fixtures/` |
