# ADR-064: Phase-1 hosting — Fly.io single machine, SQLite-on-volume, Cloudflare front

**Status:** Accepted — **shipped & deployed** (#16 closed; the app is live in production on this stack — Fly machine, SQLite-on-volume + Litestream→R2, Cloudflare front; `deploy.sh smoke` gates the unauth data plane).
**Narrows:** [ADR-055](0055-hosted-private-backend.md) — the *platform* ("small VM, Fly/Render/Hetzner class, pick later"), the *database* (managed Postgres → SQLite-on-volume), and the *object store* (always-on S3 service → R2 for backups + later lease PDFs). The hosted-private backend, tenant-shaped schema, JWT sessions, and HTTPS/PII-custody requirements of ADR-055 all stand.
**Pairs with:** [ADR-057](0057-budget-posture-reframed.md) (right-sized budget), [ADR-063](0063-file-credentials-teams-per-request-authority.md) (file credentials / per-request authority), [ADR-040](0040-parcel-owner-pii.md) (parcel-owner PII).
**Date:** 2026-06-03

## Context

ADR-055 committed to a hosted-private backend but deliberately deferred the platform
("any will do; pick at Slice 4 implementation time") and defaulted to **managed
Postgres + a separate S3 service** at a $30–100/mo Phase-1 envelope. Issue #16 is that
deferred provisioning decision.

A 2026-06-03 hosting-decision session (see `HANDOFF-hosting-2026-06-03.md`) measured the
real deployment footprint and walked the full decision tree with the user. Facts
established this session (not to be re-derived):

- **The app is two layers**, and that split is why hosting can be cheap. A *static read
  layer* (the Svelte `app/dist` bundle + composite data, served over HTTP Range/206 —
  MapLibre PMTiles + **DuckDB-WASM run client-side in the browser**, so the server only
  serves byte ranges) and a *dynamic write layer* (`backend/` FastAPI + DB), trivial load
  for 2–5 users.
- **Actual app-served footprint is 4.29 GB, measured** (`du`-equivalent over
  `data/processed/composite` excluding the per-county `parcels/` *compose inputs*, which
  the app never fetches): PMTiles 1.76 GB + `parcels_attr.parquet` 1.97 GB + towers /
  distress / solar / county GeoJSON 0.51 GB + `owners_index.json` / `owners_filter.json` +
  catalog/summary JSON ~0.05 GB. The un-served `parcels/` inputs are a separate 8.43 GB.
  The "~12 GB" the older docs imply is misleading.
- **The backend already defaults to SQLite** (`backend/app/config.py`:
  `DATABASE_URL=sqlite+pysqlite:///…/lead_state.sqlite3`); tenant isolation is
  **application-level** (byte-identical on SQLite or Postgres) and the schema is
  PG-portable, so a later move to Postgres is a connection-string change, not a rewrite.
- The team is 2 people; the co-founder is the *product's user*. Right-size, don't
  over-provision (ADR-057). The Phase-1 outcome bar is the co-founder using the tool as
  his primary daily triage surface for 4 consecutive weeks.

## Decision

Host the Phase-1 backend on **Fly.io**, US region, as a **single always-on machine**
(`min_machines_running = 1`) with an attached **Fly Volume**, fronted by **Cloudflare**.
The user chose the Fly PaaS (`fly deploy`) over a cheaper bare VM (Hetzner/DigitalOcean/
Lightsail) for the deploy UX, accepting Fly's footguns below.

| # | Component | Choice | Rationale |
|---|---|---|---|
| 1 | Region | **US** (Fly US edge) | Map issues many sequential Range requests; US avoids ~100 ms transatlantic RTT compounding. |
| 2 | Platform | **Fly.io** (`fly deploy`) | User chose PaaS DX over ~$2/mo-cheaper bare VM. |
| 3 | Uptime | **Single always-on machine**, `min=1` | "Reachable always"; and SQLite is single-writer — **exactly one machine may write** (never scale to 2). |
| 4 | Static data | **On the Fly Volume, same origin**, behind the existing login | Keeps the 4.29 GB of parcel-owner **PII** behind the app's sign-in gate with no second auth layer (ADR-040, ADR-063). |
| 5 | Volume | **10 GB** (`fly volume extend` later) | Fits 4.29 GB + SQLite + early lease PDFs; volumes grow but never shrink, so start tight. |
| 6 | In-machine server | **Caddy + uvicorn under supervisord** | Caddy serves `app/dist` (SPA) + `/data/*` Range + gzip and reverse-proxies `/api/*` → uvicorn. Both run in one machine (Fly `[processes]` would spawn separate machines and break the single-volume / single-writer rule). Caddy is best-in-class at Range serving and portable off Fly. |
| 7 | Domain + DNS | **Custom domain via Cloudflare Registrar** (~$10/yr) | At-cost, free DNS, and puts the zone on Cloudflare so Access is available later for free. App reads its API base as `VITE_API_BASE ?? '/api'` → same-origin, no rebuild on domain change. |
| 8 | Perimeter | **Cloudflare proxy (orange-cloud), no Access**; SSL **Full (strict)**; **cache-bypass rule for `/data/*`** | Edge DDoS + WAF + hidden origin IP + login rate-limiting, with zero added user friction. Cloudflare Access deferred — it's a redundant identity system on top of `users.txt`. App login stays the authentication boundary. |
| 9 | `users.txt` | **On the Volume** (`APP_USERS_FILE=/data/users.txt`), managed via `fly ssh console` + `python -m app.users` | Preserves ADR-063 per-request file authority (edit → applies next request); never in git or the image. Bootstrap the first user via `fly ssh` after first deploy. |
| 10 | Database | **SQLite on the Volume** (`DATABASE_URL=sqlite+pysqlite:////data/lead_state.sqlite3`) | Avoids Fly Managed Postgres ($38/mo min ≈ 5× the rest of the bill) for features unused at 2–5 users / single writer. Migrate to PG later if ever needed. |
| 11 | Backups | **Litestream → R2** (continuous SQLite replication, point-in-time restore) + Fly volume snapshots as baseline; **restic → R2 for lease PDFs added at D+E** | Composite data is disposable (re-pull / re-compose). Precious bits = the SQLite write-layer (a crash must not cost the co-founder a day of triage notes during the 4-week bar) and future lease PDFs. |
| 12 | Deploy + data sync | `fly deploy` (multi-stage Dockerfile) ships **code only**; the 4.29 GB syncs **laptop → R2 → Volume via `rclone`** | The data can't live in the image; the R2 staging relay (private bucket, reused from backups) is fast/resumable and avoids slow `rsync`-over-WireGuard. |
| 13 | Machine size | **shared-cpu-1x @ 1 GB** (`fly scale memory` to grow) | DuckDB runs client-side, so the server is light; 1 GB leaves headroom for D+E PDF text extraction. |

**Secrets** (`fly secrets`): `AUTH_JWT_SECRET`, R2 access/secret keys, later `ANTHROPIC_API_KEY`.
**Env** (`fly.toml [env]`): `AUTH_DEV_MODE=0`, `APP_USERS_FILE=/data/users.txt`,
`DATABASE_URL=sqlite+pysqlite:////data/lead_state.sqlite3`.

**All-in cost: ~$5–8/mo** (compute ~$3–5 + 10 GB volume $1.50 + R2 pennies) + ~$10/yr domain
— comfortably inside the ADR-057 right-sized posture and well under ADR-055's $30–100/mo
envelope (the managed-PG line alone was $38/mo).

### Gotchas this decision pins (must hold when issue #16 is built)

- **SQLite path must be the Volume.** The config default writes to the *repo* path
  (`…/data/processed/lead_state.sqlite3`), which inside the container is ephemeral and is
  **not** the Litestream-watched Volume. Override `DATABASE_URL` (and `APP_USERS_FILE`) to
  `/data/…` or the co-founder's data is silently lost on redeploy.
- **One writer only.** Never run a second machine for this app.
- **`/data/*` must never be cached at Cloudflare's edge** (PII). Set an explicit
  cache-bypass rule; rely on `Cache-Control: private/no-store` from Caddy as defence in depth.

## Consequences

- Issue #16's acceptance criteria are rewritten: managed Postgres + S3 → SQLite-on-volume +
  Litestream→R2; `APP_USERS` / `python -m app.password` → mount `users.txt` /
  `python -m app.users` (already superseded by ADR-063); add the Cloudflare/domain steps.
- `docs/DEPLOYMENT.md §8` stack table + env vars updated to this stack (the stale
  `BACKEND_BASE_URL` row is dropped — the app uses `VITE_API_BASE`, defaulting to `/api`).
- The deploy deliverable becomes Fly artifacts — `Dockerfile`, `fly.toml`, `Caddyfile`,
  `supervisord.conf`, `litestream.yml`, `deploy.sh` — **not** the bare-VM systemd units the
  handoff sketched.
- Provisioning steps that need the user's hands (interactive / payment-gated): `fly auth` +
  app/volume creation, the domain purchase, R2 key generation, `fly secrets set`.
- `scripts/share.sh` + `.env.share` still use the old `APP_USERS` / `.env.share` model and
  fail closed at boot; their migration to `users.txt` is tracked separately (they are the
  user's uncommitted files — do not edit without asking).
- A later move to managed Postgres remains a connection-string change (schema is PG-portable),
  and the R2-static-offload variant remains a documented future optimization if Volume
  uploads become a recurring pain — both reversible without a rewrite.

## Alternatives considered

- **Bare VM (Hetzner CX22 €3.79 EU / DigitalOcean $6 / Lightsail $7).** Cheapest and the
  natural fit for the 4 GB-on-disk + SQLite shape (rsync to disk; no container indirection).
  Rejected by the user in favour of Fly's `fly deploy` UX. Hetzner's cheap tier is EU-only
  (transatlantic latency); US needs its pricier CPX line.
- **Managed Postgres (per ADR-055).** Rejected — Fly Managed PG starts at $38/mo for
  capabilities unused at single-writer / 2–5 users; SQLite + Litestream covers durability.
- **Offload the static 4.29 GB to Cloudflare R2.** Tempting on Fly (trivial `rclone sync`
  vs fiddly Volume upload, ~$0.06/mo). Rejected for the read layer because the data is PII:
  on R2 it leaves the app's login gate and needs Cloudflare Access or backend presigned URLs
  (which expire mid-session, fighting MapLibre/DuckDB's long-lived Range fetching) — more
  permanent complexity than an infrequent Volume re-sync. R2 is still used as a private
  *backup* + *staging-transfer* target.
- **Cloudflare Access (zero-trust perimeter).** Rejected for now — a redundant second
  identity system over the purpose-built `users.txt` auth; a single Access policy can be
  added later if the PII posture must tighten.
- **Scale-to-zero (auto-stop) machine.** Rejected — cold-start stutter on first daily use
  fights the "reachable always" requirement, for trivial savings.
