# CLAUDE.md

Orientation for coding-agent sessions in this repo. Read this, then the subsystem
`CLAUDE.md` for the area you are touching, then the deep doc it links. This repo was built
with coding agents, and these files are the instructions they worked from.

## 1. What this project is

morphy is an archived portfolio project. It was Phase 1 of an analyst tool for finding the
landowners under cell towers and ranking them as candidates to renegotiate their ground
leases. No single dataset links a tower to its landowner, so morphy builds that link by
joining FCC Antenna Structure Registration (ASR) towers to state parcel records and to
HUD, Appalachian Regional Commission (ARC) and USDA distress overlays. On top of that it adds
carrier identification, tunable scoring, owner resolution, and a lead triage workflow backed
by a tenant-scoped API. The business behind it no longer operates. A read-only demo runs at
https://morphy-demo.fly.dev.

- What shipped and where it stopped: [docs/STATUS.md](docs/STATUS.md). **Read it before starting a task.**
- Product language and glossary: [GLOSSARY.md](GLOSSARY.md)
- Decisions: [docs/DECISIONS.md](docs/DECISIONS.md) (index) + [docs/adr/](docs/adr/)

Hard non-goals: LLC unmasking beyond public officer disclosures (ADR-041 as narrowed by
ADR-057); rooftop installations (ADR-054); mass email or CRM automation; nationwide coverage
without a paid parcel source (ADR-012).

## 2. Where things live

```
morphy/
├── README.md          Project overview
├── GLOSSARY.md        Product language (glossary)
├── docs/              Deep docs; adr/ holds the decision records
├── app/               Svelte 5 + MapLibre map app          → app/CLAUDE.md
├── backend/           FastAPI + SQLAlchemy write layer     → backend/CLAUDE.md
├── contracts/         Cross-language contract fixtures
├── scripts/fetch/     Headless puller library              → scripts/fetch/CLAUDE.md
├── scripts/data_tui/  Textual data TUI, the only puller UI → scripts/data_tui/CLAUDE.md
├── scripts/preprocess/ Normalizer → Join → View → Compose  → scripts/preprocess/CLAUDE.md
├── scripts/serve.py   Range-capable static server for the map app
├── data/              Git-ignored (~15 GB raw + composites)
└── tests/             Pytest: preprocess pipeline + app-asset scripts
```

Each subsystem `CLAUDE.md` holds that area's entry points, contracts, and
most-violated invariants; they load automatically when you work on files there.
Full layout and system diagram: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 3. How to run things

Full details in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

```bash
uv sync && source .venv/bin/activate           # once
python -m data_tui                             # pull → preprocess → verify → deploy
python scripts/preprocess.py [--state 05] [--app-assets] [--tiles] [--owners-index] [--rebuild-manifest]
python scripts/verify_raw.py                   # contents check
python scripts/serve.py 8765                   # data server (repo root)
AUTH_DEV_MODE=1 uvicorn backend.app.main:app --reload --port 8000   # API, dev/dev login
cd app && npm run dev                          # map app on :5173
pytest
```

## 4. Global invariants

- **Headless `scripts/fetch/`.** No UI imports; Textual lives only in `scripts/data_tui/`.
- **Atomic writes everywhere.** Download to `.partial`, rename into `current/`; manifest writes go through `Manifest.save()`.
- **Preprocess outputs EPSG:4326.** Every spatial output reprojected to WGS84.
- **No normalize-time filtering.** Keep all rows, add status/validity columns, let Joins and Views filter ([ARCHITECTURE.md §3.3](docs/ARCHITECTURE.md)).
- **Use `safe_merge`** when a Join adds columns a Normalizer initialized as placeholders (ADR-020).
- **Never add scraping to a MANUAL_ONLY source** without confirming the publisher's terms changed.
- **The data TUI is the only puller UI.** The Qt desktop puller is deleted; do not resurrect it or reintroduce PySide6.
- **Sparse comments.** Only where the *why* is non-obvious.

Backend invariants (mechanics in [backend/README.md](backend/README.md), do-not-relax list in [backend/CLAUDE.md](backend/CLAUDE.md)):

- **`tenant_id` on every table; every route filters by it** (ADR-055). `credential` and `tenant` are the deliberate exceptions.
- **Auth posture is load-bearing** (ADR-062/063/069): credentials live in the `credential` table (managed only via `python -m app.users`) and re-authorize every request, API routes and the edge-gated `/data/processed/*` alike. The JWT is identity-only in the httpOnly `morphy_session` cookie; teams are tenants; `AUTH_DEV_MODE` fails closed. Never reintroduce `APP_USERS`/`users.txt`, localStorage tokens, tenant claims in the JWT, or the `tenant_id=1` stub; never commit the DB or hand-edit hashes.
- **Read-only is a credential flag, enforced in one gate** (ADR-077): `current_principal` refuses a `read_only` principal's non-GET/HEAD/OPTIONS request with 403. Never add per-route read-only checks or a read-only claim in the JWT. `DEMO_MODE` (the password-less demo login) fails closed. Boot refuses unless `DEMO_USERNAME` names an existing read-only credential, and `POST /api/auth/demo` re-checks that on every call.
- **Schema changes ship as Alembic revisions**, never back-fill helpers in `db.py`. The OpenAPI schema is the frontend's type contract: regenerate and commit both artifacts after any model change.
- **Owner merge/split resolves in one place:** `display_cluster_id = coalesce(override_target, raw_cluster_id)`, never forked per surface or baked into parquet. The owners index is schema-versioned (contract in [scripts/preprocess/CLAUDE.md](scripts/preprocess/CLAUDE.md)).
- **Secrets stay out of the repo.** Keys go in git-ignored `.env` files (`.env.example` and `app/.env.example` list them). The MapTiler key is optional; without it the app falls back to a keyless basemap.

## 5. Phase 1 geography

State-level scope (ADR-001). Anchors `05` (AR), `12` (FL), `30` (MT), `54` (WV);
deferred `37` (NC); dropped IN, UT, MN. Per-state detail: [docs/STATUS.md](docs/STATUS.md).

## 6. Where to look for what

| Question | File |
|---|---|
| Per-source schema / license / policy | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) |
| When does each source need a refresh? | [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) |
| Caveats, fragile upstreams, licensing constraints | [docs/LIMITATIONS.md](docs/LIMITATIONS.md) |
| PII / data handling | [docs/SECURITY.md](docs/SECURITY.md) |
| What shipped, what never did | [docs/STATUS.md](docs/STATUS.md) |
| Deploy / share outputs | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Testing strategy | [docs/TESTING.md](docs/TESTING.md) |
| Puller UX design | [docs/PULLER_UX.md](docs/PULLER_UX.md) |
| Map app architecture | [app/ARCHITECTURE.md](app/ARCHITECTURE.md) |
| What shipped when | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| What is on disk, last fetch time, last 200 puller events | `data/manifest.json`, `data/fetch.log` |

## 7. Domain docs

Single-context repo. Before working in an area, read [GLOSSARY.md](GLOSSARY.md) and the
ADRs in [docs/adr/](docs/adr/) that touch it. Use the glossary's terms in names, tests and
docs, and avoid the aliases it lists. If a change contradicts an ADR, say so explicitly and
record a new ADR rather than overriding it silently.
