# CLAUDE.md

Orientation for agent sessions in this repo. Read this, then the subsystem
`CLAUDE.md` for the area you are touching, then the deep doc it links.

## 1. What this project is

Phase 1 of a co-founder-facing product that helps landowners renegotiate
ground leases for infrastructure on their property, primarily cell towers.
No single dataset links an asset to its landowner; we construct it by joining
FCC ASR + state parcels + HUD / ARC / USDA distress overlays, then layer carrier
identification, lease document storage, LLM extraction, and a triage workflow
on top. Deployed in production.

- Business case: [PROJECT_BRIEF.md](PROJECT_BRIEF.md)
- Scope, goals, outcome bar, slice plan (**F → A → C → D+E → B**): [docs/SCOPE.md](docs/SCOPE.md)
- What works today and what is next: [docs/STATUS.md](docs/STATUS.md). **Read it before starting a task.**
- Product language and glossary: [CONTEXT.md](CONTEXT.md)
- Locked decisions: [docs/DECISIONS.md](docs/DECISIONS.md) (index) + [docs/adr/](docs/adr/)

Hard non-goals: paid LLC unmasking / skip-trace (ADR-041 as narrowed by ADR-057);
rooftop installations in Phase 1 (ADR-054); mass email / CRM automation;
nationwide coverage without a paid parcel source (ADR-012).

## 2. Where things live

```
pilot/
├── PROJECT_BRIEF.md   Business case
├── CONTEXT.md         Product language (glossary)
├── docs/              Deep docs; adr/ (decisions), agents/ (skill config), research/ (data-source licensing)
├── app/               Svelte 5 + MapLibre map app          → app/CLAUDE.md
├── backend/           FastAPI + SQLAlchemy write layer     → backend/CLAUDE.md
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
python scripts/preprocess.py [--state 05] [--app-assets] [--tiles] [--rebuild-manifest]
python scripts/verify_raw.py                   # contents check
python scripts/serve.py 8765                   # data server (repo root)
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
- **Auth posture is load-bearing** (ADR-062/063/069): credentials live in the `credential` table (managed only via `python -m app.users`) and re-authorize every request, API routes and the edge-gated `/data/processed/*` alike. The JWT is identity-only in the httpOnly `pilot_session` cookie; teams are tenants; `AUTH_DEV_MODE` fails closed. Never reintroduce `APP_USERS`/`users.txt`, localStorage tokens, tenant claims in the JWT, or the `tenant_id=1` stub; never commit the DB or hand-edit hashes.
- **Schema changes ship as Alembic revisions**, never back-fill helpers in `db.py`. The OpenAPI schema is the frontend's type contract: regenerate and commit both artifacts after any model change.
- **Owner merge/split resolves in one place:** `display_cluster_id = coalesce(override_target, raw_cluster_id)`, never forked per surface or baked into parquet. The owners index is schema-versioned (contract in [scripts/preprocess/CLAUDE.md](scripts/preprocess/CLAUDE.md)).

## 5. Pilot geography

State-level scope (ADR-001). Anchors `05` (AR), `12` (FL), `30` (MT), `54` (WV);
deferred stretch `37` (NC); dropped IN, UT, MN. Per-state status: [docs/SCOPE.md §2](docs/SCOPE.md).

## 6. Where to look for what

| Question | File |
|---|---|
| Per-source schema / license / policy | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) |
| When does each source need a refresh? | [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) |
| Caveats, fragile upstreams, pre-commercial blockers | [docs/LIMITATIONS.md](docs/LIMITATIONS.md) |
| PII / data handling | [docs/SECURITY.md](docs/SECURITY.md) |
| Phase 2/3 | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Deploy / share outputs | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| `data/` on the external T9 drive, exfat gotchas | [docs/EXTERNAL_DATA_DRIVE.md](docs/EXTERNAL_DATA_DRIVE.md) |
| Testing strategy | [docs/TESTING.md](docs/TESTING.md) |
| Puller UX design | [docs/PULLER_UX.md](docs/PULLER_UX.md) |
| Map app architecture | [app/ARCHITECTURE.md](app/ARCHITECTURE.md) |
| What shipped when | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| What is on disk, last fetch time, last 200 puller events | `data/manifest.json`, `data/fetch.log` |

## 7. Agent skills

GitHub Issues at `danielgentile22/infra-lease-analytics`; default triage labels
(not yet created on the repo, `triage` creates them on first use); single-context
domain docs. Details in [docs/agents/](docs/agents/).

## 8. Code-review-graph MCP

This repo has a code knowledge graph (`.mcp.json`, auto-updated by hooks). Prefer
it over Grep/Glob/Read for exploring code, tracing callers, and judging impact:
`semantic_search_nodes`, `query_graph`, `get_impact_radius`, `detect_changes`,
`get_review_context`. The `/explore-codebase`, `/debug-issue`, `/refactor-safely`,
and `/review-changes` skills wrap the common workflows.
