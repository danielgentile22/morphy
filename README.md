# morphy

Finds the landowner under every cell tower in a state and ranks them for ground-lease
renegotiation, by joining federal tower registries to county parcel records and economic
distress data.

**Status:** Archived. A portfolio project by Daniel Gentile.

**Live demo:** [morphy-demo.fly.dev](https://morphy-demo.fly.dev). Press "Explore the demo" on
the sign-in page; it needs no password. The demo is read-only. The backend refuses every write
with a 403, and the lead board holds six fictional leads seeded for the demo
([ADR-077](docs/adr/0077-read-only-demo-credential.md)).

<!--
## Screenshots

![Explore view: towers and parcels on the map, filtered by score](docs/images/explore.png)
![Lead page: owner cluster, towers, carriers and activity log](docs/images/lead.png)
![Data TUI: source status, pull progress and verify](docs/images/data-tui.png)
-->

## The problem

Cell towers usually sit on land leased from a private owner, often a farmer or a small family
trust, under a ground lease signed decades ago. Those leases are often worth renegotiating,
but finding the owners is the hard part. The FCC knows where every registered tower stands.
Counties know who owns every parcel. No public dataset connects the two.

morphy builds that connection for four states (Arkansas, Montana, Florida and West Virginia).
It places every FCC Antenna Structure Registration (ASR) tower on its parcel, attaches the
owner, groups an owner's parcels across counties and states, and layers on distress signals:
HUD Opportunity Zones and Qualified Census Tracts, Appalachian Regional Commission
distressed counties, and USDA persistent-poverty counties. An analyst then works the result
as leads in a map app: filter, rank with tunable scores, open an owner, log contact attempts,
and merge or split owner clusters by hand.

## Architecture

Four subsystems, each with its own agent orientation file:

| Subsystem | Path | What it does |
|---|---|---|
| Data TUI | [`scripts/data_tui/`](scripts/data_tui/CLAUDE.md) | Textual terminal app over the headless fetch library. Pulls raw data, runs preprocess, verifies outputs, and deploys data, all from one screen. |
| Preprocess pipeline | [`scripts/preprocess/`](scripts/preprocess/CLAUDE.md) | Registry-driven Normalizer → Join → View → Compose framework on DuckDB. Writes per-state composites, PMTiles and the cross-state owners index. |
| Map app | [`app/`](app/CLAUDE.md) | Svelte 5 + MapLibre single-page app with Dashboard, Explore and Leads sections. |
| Backend | [`backend/`](backend/CLAUDE.md) | FastAPI + SQLAlchemy write layer for leads, tasks, activity, scoring presets and owner overrides. |

```
public sources ──► scripts/fetch ──► data/raw ──► scripts/preprocess ──► data/processed
 (FCC, counties,      (data TUI)                   normalize, join,        composites,
  HUD, ARC, USDA,                                  view, compose           PMTiles, owners index
  EIA, FAA)                                                                     │
                                                                                ▼
                               backend (FastAPI, SQLite) ◄──── app (Svelte, MapLibre,
                               leads, tasks, overrides          PMTiles, DuckDB-WASM)
```

Deployed, the app, the API and the data files sit behind one Caddy server on a single Fly
machine, with SQLite replicated to object storage by Litestream. The full system diagram and
data flow are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Technical highlights

- **Registry-driven pipeline.** Each source is one `DataSource` entry with an automation
  policy (`ALLOWED`, `TOLERATED`, `MANUAL_ONLY`, `CREDENTIALED`) that records what the
  publisher's terms permit. 17 sources are active and 12 more are registered but deferred.
  Normalizers map each source to a canonical schema, Joins link them, and Views define the
  outputs. Adding a state means adding a parcel adapter, not a new code path
  ([ADR-002](docs/adr/0002-registry-driven-architecture.md)).
- **Big-state compose on a laptop.** Florida has 11.4 million parcels. Loading them in one
  pass peaked near 19.5 GB, past the 16 GB dev machine, so compose runs in chunks on DuckDB
  ([ADR-051](docs/adr/0051-chunked-compose.md)).
- **No tile server.** Parcels ship as PMTiles read by HTTP range request, and the browser
  filters and searches parcel attributes with DuckDB-WASM over parquet. The static file
  server only has to honor `Range`.
- **Tenant-scoped API.** Every table carries `tenant_id` and every route filters by it, with
  isolation tests marked `tenant_isolation`
  ([ADR-055](docs/adr/0055-hosted-private-backend.md)). Schema changes ship as Alembic
  revisions, and the committed OpenAPI schema generates the frontend's TypeScript types,
  checked in CI.
- **Cookie auth that re-checks every request.** Credentials live in the database with
  PBKDF2 hashes. The JWT carries identity only, sits in an httpOnly `morphy_session` cookie,
  and is re-authorized against the credential table on every request. Caddy uses the same
  check (`forward_auth`) to gate the static data files. With `AUTH_DEV_MODE` unset, the app
  refuses to start without a real secret and at least one credential
  ([ADR-069](docs/adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)).
- **A read-only demo enforced in one place.** Read-only is a flag on the credential row.
  `current_principal`, the dependency every authenticated route already uses, refuses that
  principal's non-GET requests, and a test enumerates every write route to prove none slips
  past. `DEMO_MODE` adds a password-less sign-in for that one credential and refuses to boot
  unless it exists and is read-only
  ([ADR-077](docs/adr/0077-read-only-demo-credential.md)).
- **Owner merge and split.** The pipeline clusters owners by normalized name plus state, with
  an alias table for the national tower companies
  ([ADR-075](docs/adr/0075-cross-state-owner-identity.md)). Analyst overrides resolve in one
  expression, `display_cluster_id = coalesce(override_target, raw_cluster_id)`, so no surface
  can disagree about who an owner is.
- **Tests.** About 1,100 pytest tests (627 for the pipeline and app-asset scripts, 472 for
  the backend), about 515 Vitest unit tests and about 40 Playwright end-to-end tests for the
  map app. GitHub Actions runs lint, tests and an OpenAPI type-drift check
  ([docs/TESTING.md](docs/TESTING.md)).
- **Built with coding agents.** The root [CLAUDE.md](CLAUDE.md) and one per subsystem give
  agents their entry points, contracts and the invariants they most often broke. They are
  left in place as a record of how the project was built.

## Running it locally

Prerequisites: [uv](https://docs.astral.sh/uv/) (it installs Python 3.11 from `uv.lock`),
Node.js 22 (the version CI and the Dockerfile use), and `tippecanoe` for parcel tiles (`brew install tippecanoe`). Expect
several GB of disk for one state's raw data.

```bash
uv sync && source .venv/bin/activate
```

**1. Pull one state.** Montana is a good first state because its statewide parcel layer downloads
automatically.

```bash
python -m data_tui
```

The launch sweep checks every source. Select a row and press `p` to pull it. For Montana pull
`mt_cadastral_parcels`, `fcc_asr` (national towers) and the overlays (`hud_oz`, `hud_qct`,
`arc_distressed`, `usda_persistent_poverty`). `P` pulls every stale source at once, and `q`
quits. [docs/PULLER_UX.md](docs/PULLER_UX.md) covers the rest.

**2. Build the outputs.**

```bash
python scripts/preprocess.py --state 30      # normalize + compose Montana
python scripts/preprocess.py --app-assets    # index.json, facets, slim parquet
python scripts/preprocess.py --tiles         # parcels.pmtiles (needs tippecanoe)
python scripts/preprocess.py --owners-index  # cross-state owner clusters for Leads
```

**3. Run the stack** (three terminals, from the repo root):

```bash
python scripts/serve.py 8765                                       # data files
AUTH_DEV_MODE=1 uvicorn backend.app.main:app --reload --port 8000  # API
cd app && npm install && npm run dev                               # http://localhost:5173
```

`AUTH_DEV_MODE=1` uses an ephemeral signing secret and a built-in `dev` / `dev` login. Sign
in with that. Vite proxies `/data` to port 8765 and `/api` to port 8000.

**Optional settings.** Copy `.env.example` to `.env` and `app/.env.example` to `app/.env`
(both git-ignored). The app's file takes a MapTiler key for the satellite basemap. Without
one the app uses a keyless Esri basemap.

**Tests:**

```bash
pytest
ruff check . && ruff format --check .
uv run pyright
cd app && npm run check && npm run test:unit && npm run test:e2e
```

## Data sources and attribution

The MIT license covers the code only. No source data is in this repo: `data/` is git-ignored,
and the data TUI pulls each dataset from its publisher. The data comes from federal agencies
(FCC, HUD, USDA, USGS, the Appalachian Regional Commission) and from state parcel publishers in
Arkansas, Florida, Montana and West Virginia. [NOTICE.md](NOTICE.md) gives each publisher's
terms and the credits and disclaimers they ask for, including a takedown contact for owner
names, which come from public records. Per-source schemas, licenses and automation policies
are in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md), and data handling is in
[docs/SECURITY.md](docs/SECURITY.md).

## Design decisions

Every significant choice is recorded as an architecture decision record in
[docs/adr/](docs/adr/), indexed in [docs/DECISIONS.md](docs/DECISIONS.md). Good starting
points: why states were the unit of scope
([ADR-001](docs/adr/0001-state-level-geographic-scope.md)), why a lead is an owner cluster
([ADR-056](docs/adr/0056-lead-equals-owner-cluster.md)), why one Fly machine with SQLite
([ADR-064](docs/adr/0064-phase1-hosting-fly-sqlite.md)), and why carrier matches are labeled
"licensed in this area" rather than confirmed tenants
([ADR-074](docs/adr/0074-uls-carrier-rearchitecture.md)).

## Where it stopped

The pipeline, the four state composites, carrier identification, tunable scoring, owner
resolution, the backend and the triage UI all shipped. Lease document upload with LLM
extraction ([ADR-059](docs/adr/0059-llm-lease-extraction.md)) and tower-company inference were
designed but never built. [docs/STATUS.md](docs/STATUS.md) has the full account, and
[docs/CHANGELOG.md](docs/CHANGELOG.md) has the dated history.

## License and author

MIT, see [LICENSE](LICENSE). Built by Daniel Gentile.
