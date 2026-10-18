# ADR-064: Phase 1 hosting on a single Fly.io machine with SQLite on a volume

**Status:** Accepted. **Shipped and deployed** on this stack: one Fly machine (app `morphy-demo`), SQLite on the volume with Litestream replication to the R2 bucket `morphy-demo`, and `deploy.sh smoke` gating the unauthenticated data plane. The original design put Cloudflare in front of a custom domain. That custom domain and the Cloudflare front were later dropped, and the public demo runs at https://morphy-demo.fly.dev on Fly's own TLS edge. Credential storage moved from `users.txt` into the database's `credential` table under [ADR-069](0069-credentials-in-db-cookie-sessions-gated-data-plane.md).
**Narrows:** [ADR-055](0055-hosted-private-backend.md): the *platform* ("small VM, Fly/Render/Hetzner class, pick later"), the *database* (managed Postgres → SQLite on a volume), and the *object store* (an always-on S3 service → R2 for backups and, later, lease PDFs). The hosted-private backend, tenant-shaped schema, JWT sessions, and the HTTPS and PII-custody requirements of ADR-055 all stand.
**Pairs with:** [ADR-057](0057-budget-posture-reframed.md) (right-sized budget), [ADR-063](0063-file-credentials-teams-per-request-authority.md) (file credentials, per-request authority), [ADR-040](0040-parcel-owner-pii.md) (parcel-owner PII).
**Date:** 2026-06-03

## Context

ADR-055 committed to a hosted-private backend but deferred the platform choice to
implementation time, and defaulted to **managed Postgres plus a separate S3 service**
within a $30-100/mo Phase 1 budget. This ADR makes that deferred provisioning decision.

A 2026-06-03 hosting session measured the real deployment footprint and walked the full
decision tree. The facts it established:

- **The app is two layers**, and that split is why hosting can be cheap. A *static read
  layer* (the Svelte `app/dist` bundle plus composite data, served over HTTP Range/206;
  MapLibre PMTiles and **DuckDB-WASM run in the browser**, so the server only serves
  byte ranges) and a *dynamic write layer* (the `backend/` FastAPI app and its DB), with
  trivial load for 2-5 users.
- **The app-served footprint is 4.29 GB, measured** (`du`-equivalent over
  `data/processed/composite`, excluding the per-county `parcels/` *compose inputs*, which
  the app never fetches): PMTiles 1.76 GB, `parcels_attr.parquet` 1.97 GB, towers,
  distress, solar and county GeoJSON 0.51 GB, plus `owners_index.json`, `owners_filter.json`
  and catalog/summary JSON at about 0.05 GB. The unserved `parcels/` inputs are a separate
  8.43 GB. The "~12 GB" the older docs implied was misleading.
- **The backend already defaults to SQLite** (`backend/app/config.py`:
  `DATABASE_URL=sqlite+pysqlite:///…/lead_state.sqlite3`). Tenant isolation is
  **application-level** (identical on SQLite or Postgres) and the schema is
  Postgres-portable, so a later move to Postgres is a connection-string change, not a rewrite.
- The team is two people with one daily user. Right-size, do not over-provision (ADR-057).

## Decision

Host the Phase 1 backend on **Fly.io**, in a US region, as a **single always-on machine**
(`min_machines_running = 1`) with an attached **Fly Volume**. The original design fronted it
with **Cloudflare**. Fly's PaaS (`fly deploy`) won over a cheaper bare VM (Hetzner,
DigitalOcean, Lightsail) for its deploy workflow, accepting the Fly pitfalls listed below.

| # | Component | Choice | Rationale |
|---|---|---|---|
| 1 | Region | **US** (Fly US edge) | The map issues many sequential Range requests. A US region avoids about 100 ms of transatlantic round-trip time compounding. |
| 2 | Platform | **Fly.io** (`fly deploy`) | The PaaS deploy workflow won over a bare VM about $2/mo cheaper. |
| 3 | Uptime | **A single always-on machine**, `min=1` | The app must always be reachable, and SQLite is single-writer: **exactly one machine may write** (never scale to 2). |
| 4 | Static data | **On the Fly Volume, same origin**, behind the existing login | Keeps the 4.29 GB of parcel-owner **PII** behind the app's sign-in gate with no second auth layer (ADR-040, ADR-063). |
| 5 | Volume | **10 GB** (`fly volume extend` later) | Fits 4.29 GB plus SQLite plus early lease PDFs. Volumes grow but never shrink, so start tight. |
| 6 | In-machine server | **Caddy and uvicorn under supervisord** | Caddy serves `app/dist` (the SPA) and `/data/*` with Range and gzip, and reverse-proxies `/api/*` to uvicorn. Both run in one machine, because Fly `[processes]` would spawn separate machines and break the single-volume, single-writer rule. Caddy handles Range serving well and is portable off Fly. |
| 7 | Domain and DNS | Originally a **custom domain through Cloudflare Registrar** (about $10/yr). Later dropped in favor of the `morphy-demo.fly.dev` hostname. | The registrar was at-cost with free DNS and put the zone on Cloudflare so Access stayed available for free. The app reads its API base as `VITE_API_BASE ?? '/api'`, so it is same-origin and a domain change needs no rebuild. That is what made dropping the domain free. |
| 8 | Perimeter | Originally a **Cloudflare proxy (orange cloud), no Access**, SSL **Full (strict)**, and a **cache-bypass rule for `/data/*`**. Dropped along with the custom domain; Fly's edge terminates TLS. | The proxy was meant to add edge DDoS protection, a web application firewall, a hidden origin IP, and login rate limiting with no added user friction. Cloudflare Access was deferred as a redundant identity system on top of the app's credentials. The app login stays the authentication boundary either way. |
| 9 | Credentials | **`users.txt` on the Volume** (`APP_USERS_FILE=/data/users.txt`), managed with `fly ssh console` and `python -m app.users`. Superseded by ADR-069, which moved credentials into the database on the same volume. | Preserved ADR-063's per-request file authority (an edit applies on the next request) and kept credentials out of git and the image. The first user is bootstrapped over `fly ssh` after the first deploy. |
| 10 | Database | **SQLite on the Volume** (`DATABASE_URL=sqlite+pysqlite:////data/lead_state.sqlite3`) | Avoids Fly Managed Postgres ($38/mo minimum, about 5× the rest of the bill) for features unused at 2-5 users with a single writer. Migrate to Postgres later if ever needed. |
| 11 | Backups | **Litestream → R2** (continuous SQLite replication to the `morphy-demo` bucket, point-in-time restore) with Fly volume snapshots as a baseline. **restic → R2 for lease PDFs** was planned for Slice D+E. | Composite data is disposable (re-pull and re-compose). The data worth protecting is the SQLite write layer (a crash must not lose a day of triage notes) and any future lease PDFs. |
| 12 | Deploy and data sync | `fly deploy` (multi-stage Dockerfile) ships **code only**. The 4.29 GB syncs **laptop → R2 → Volume with `rclone`** (`r2:morphy-demo/composite`). | The data cannot live in the image. The R2 staging relay (a private bucket, reused from backups) is fast and resumable and avoids slow `rsync` over WireGuard. |
| 13 | Machine size | **shared-cpu-1x at 1 GB** (`fly scale memory` to grow) | DuckDB runs in the browser, so the server is light. 1 GB leaves headroom for Slice D+E PDF text extraction. |

**Secrets** (`fly secrets`): `AUTH_JWT_SECRET` and the R2 access and secret keys.
**Env** (`fly.toml [env]`): `AUTH_DEV_MODE=0`, `APP_USERS_FILE=/data/users.txt` (before ADR-069),
`DATABASE_URL=sqlite+pysqlite:////data/lead_state.sqlite3`.

**All-in cost: about $5-8/mo** (compute about $3-5, the 10 GB volume $1.50, R2 pennies),
plus about $10/yr for the domain while it existed. That sits inside the ADR-057 right-sized
posture and well under ADR-055's $30-100/mo budget (the managed Postgres line alone was $38/mo).

### Pitfalls this decision pins

- **The SQLite path must be on the Volume.** The config default writes to the *repo* path
  (`…/data/processed/lead_state.sqlite3`), which is ephemeral inside the container and
  **not** the Litestream-watched Volume. Override `DATABASE_URL` (and, before ADR-069,
  `APP_USERS_FILE`) to `/data/…`, or the lead-state data is silently lost on redeploy.
- **One writer only.** Never run a second machine for this app.
- **`/data/*` must never be cached at a shared edge** (PII). With Cloudflare in front this
  meant an explicit cache-bypass rule. Caddy's `Cache-Control: private/no-store` is the
  defence in depth, and it still applies without Cloudflare.

## Consequences

- The production hosting plan changed from managed Postgres and S3 to SQLite on a volume
  with Litestream → R2, and from `APP_USERS` / `python -m app.password` to the credentials
  file and `python -m app.users` (already superseded by ADR-063).
- The [DEPLOYMENT.md](../DEPLOYMENT.md) stack table and env vars follow this stack. The
  stale `BACKEND_BASE_URL` row was dropped: the app uses `VITE_API_BASE`, defaulting to `/api`.
- The deploy deliverable is a set of Fly artifacts (`Dockerfile`, `fly.toml`, `Caddyfile`,
  `supervisord.conf`, `litestream.yml`, `deploy.sh`), not bare-VM systemd units.
- Some provisioning steps need a human (interactive or payment-gated): `fly auth`, app and
  volume creation, R2 key generation, and `fly secrets set`. The domain purchase was one of
  these until the domain was dropped.
- A later move to managed Postgres remains a connection-string change (the schema is
  Postgres-portable). Offloading the static data to R2 remains a documented future
  optimization if Volume uploads become a recurring pain. Both are reversible without a rewrite.

## Alternatives considered

- **Bare VM (Hetzner CX22 at €3.79 in the EU, DigitalOcean at $6, Lightsail at $7).** The
  cheapest option and a natural fit for the 4 GB-on-disk plus SQLite shape (rsync to disk, no
  container indirection). Rejected in favor of Fly's `fly deploy` workflow. Hetzner's cheap
  tier is EU-only (transatlantic latency), and a US region needs its pricier CPX line.
- **Managed Postgres (per ADR-055).** Rejected. Fly Managed Postgres starts at $38/mo for
  capabilities unused with a single writer and 2-5 users. SQLite with Litestream covers durability.
- **Offload the static 4.29 GB to Cloudflare R2.** Tempting on Fly (a trivial `rclone sync`
  instead of a fiddly Volume upload, about $0.06/mo). Rejected for the read layer because the
  data is PII. On R2 it leaves the app's login gate and needs Cloudflare Access or backend
  presigned URLs, and presigned URLs expire mid-session, which fights the long-lived Range
  fetching MapLibre and DuckDB do. That is more permanent complexity than an occasional Volume
  re-sync. R2 is still used as a private *backup* and *staging-transfer* target.
- **Cloudflare Access (zero-trust perimeter).** Rejected. It would be a redundant second
  identity system over the purpose-built app auth. A single Access policy could have been
  added later if the PII posture needed to tighten.
- **A scale-to-zero (auto-stop) machine.** Rejected. Cold-start stutter on the first use of
  the day fights the always-reachable requirement, for trivial savings.
