# CLAUDE.md

Orientation for Claude Code sessions working in this repo. Read this
first; then dip into the relevant doc under [docs/](docs/) when you
need depth.

**Current state:** [docs/STATUS.md](docs/STATUS.md) is the live status (what works
today); the slice plan + scope live in [docs/SCOPE.md](docs/SCOPE.md); the
milestone trail in [docs/CHANGELOG.md](docs/CHANGELOG.md). The product is deployed
in production; Slices F, A, and C have shipped (and most of **D+E**); the rest of
D+E (lease-doc upload + LLM extraction) is the next unbuilt slice. (Last doc sweep:
2026-06-26.)

> **🔀 Phase shift (2026-05-25):** this went from "v1 pitch demo" to **Phase 1 of
> a co-founder-facing product** — freestanding towers across AR + MT + FL + WV,
> rooftops in Phase 2. Full narrative + the superseded/narrowed ADRs live in
> [docs/SCOPE.md](docs/SCOPE.md) + [ADR-053](docs/adr/0053-product-phase-shift.md);
> decision index in [docs/DECISIONS.md](docs/DECISIONS.md).

---

## 0. Working with the user

These rules apply to every action you take in this repo, override
session defaults, and should not be relaxed without explicit instruction.

- **Explain.** After a task, summarize what you did and why; list each changed
  file with a one-line note; flag non-obvious decisions, trade-offs, assumptions,
  and why you chose an approach over the alternatives.
- **Make it runnable.** For anything runnable (script/app/service/test), give exact
  copy-pasteable commands in order, the prerequisites (deps, env vars, versions,
  running services), a build step stated separately if there is one, and how to
  verify success.
- **Code changes.** Outline a plan before large or structural changes; keep changes
  minimal and targeted unless asked to refactor; don't delete or rewrite working
  code without explaining why; preserve existing style and conventions.
- **Safety.** Ask before destructive commands (deleting files, dropping data,
  force-pushing) or anything that reaches outside the project directory; don't
  install new dependencies without saying so and why.
- **When stuck.** Stop and explain what failed, what you tried, and what you'd need
  to proceed — don't silently work around problems in ways that hide them.

---

## 1. What this project is

Phase 1 of a co-founder-facing product that helps landowners renegotiate
ground leases for infrastructure on their property — primarily cell
towers. The data problem: no single dataset links an asset to the
landowner; we construct it by joining FCC ASR + state parcels + HUD /
ARC / USDA distress overlays, then layer carrier identification + lease
document storage + LLM-based extraction + triage workflow on top.

- **Business case:** [PROJECT_BRIEF.md](PROJECT_BRIEF.md)
- **Current scope + goals + outcome bar + slice plan:** [docs/SCOPE.md](docs/SCOPE.md)
- **Today's state:** [docs/STATUS.md](docs/STATUS.md)
- **What shipped when:** [docs/CHANGELOG.md](docs/CHANGELOG.md)

Hard non-goals (do not scope-creep): paid LLC unmasking / skip-trace
([ADR-041](docs/adr/0041-no-llc-unmasking.md) as narrowed by
[ADR-057](docs/adr/0057-budget-posture-reframed.md)); rooftop installations
in Phase 1 ([ADR-054](docs/adr/0054-asset-universe-phase-1-2.md)); mass
email / CRM automation; nationwide coverage without a paid parcel
source ([ADR-012](docs/adr/0012-regrid-deferred.md)).

---

## 2. Where things live

```
pilot/
├── README.md                 Quick start
├── CLAUDE.md                 This file
├── PROJECT_BRIEF.md          Business case
├── CONTEXT.md                Canonical product language (glossary)
├── docs/                     All deep-dive documentation
│   ├── adr/                  Architecture Decision Records (all ADRs)
│   ├── agents/               Skill-system configuration
│   └── research/             Data-source legal/license research
├── app/                      Svelte 5 + MapLibre map app (see app/ARCHITECTURE.md)
├── backend/                  FastAPI + SQLAlchemy lead-triage write-layer — tenant-scoped Lead state + Tasks, username/password auth, owners-index read path. Deployed in production. Auth + schema mechanics canonical in backend/README.md; invariants in §8.
├── scripts/
│   ├── fetch/                Headless puller library
│   ├── data_tui/             Textual data TUI — *the* puller (PRD #233; pull → preprocess → verify → deploy)
│   ├── preprocess/           Normalizer/Join/View framework + Composer
│   ├── serve.py              Range-capable static server (for the map app)
│   └── *.py                  Top-level CLI scripts
├── data/                     Git-ignored (~15 GB raw + composites)
└── tests/                    Pytest — preprocess pipeline + app-asset scripts
```

The full repository layout + system diagram is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

### Intent Layer (per-subsystem AGENTS.md)

**Before modifying code in one of these subsystems, read its `AGENTS.md`
first** — each captures the local entry points, contracts, and invariants
that are easy to violate, and links to the deep doc for that area. This
`CLAUDE.md` stays the single project-root context file; the nodes below are
its children.

| Subsystem | Node | Owns | Most-violated invariant |
|---|---|---|---|
| Map app (frontend) | [`app/AGENTS.md`](app/AGENTS.md) | Svelte 5 + MapLibre read-layer triage UI | Schema-completeness contract; structures-first map |
| Write-layer backend | [`backend/AGENTS.md`](backend/AGENTS.md) | FastAPI Lead status/notes/attempts + Tasks | `tenant_id` everywhere; `credential`-table per-request authority; identity-only JWT |
| Headless puller | [`scripts/fetch/AGENTS.md`](scripts/fetch/AGENTS.md) | `DataSource` fetchers + manifest | No UI imports; never add scraping to a MANUAL_ONLY source |
| Preprocess pipeline | [`scripts/preprocess/AGENTS.md`](scripts/preprocess/AGENTS.md) | Normalizer→Join→View→Compose ETL | EPSG:4326 output; no normalize-time filtering; owners-index schema versioning |
| Data TUI (the puller) | [`scripts/data_tui/AGENTS.md`](scripts/data_tui/AGENTS.md) | Textual pull→preprocess→verify→deploy lifecycle | Thin shell — headless libs stay unchanged; deploy confirm-gated |

> **Historical:** the PySide6 desktop puller (`app_puller/`) was frozen by PRD #138
> and retired in #240 (2026-07-03) once the tested Textual successor (PRD #233)
> covered its scope — package and PySide6 pin deleted in the same change.

Global invariants (apply across all subsystems) live in §8 below.

---

## 3. The current work plan

The canonical slice plan (**F → A → C → D+E → B**), per-slice gates, and outcome bar
live in [docs/SCOPE.md §3–§4](docs/SCOPE.md). What's shipped / next is in
[docs/STATUS.md](docs/STATUS.md) — **always read it before starting a task.**

---

## 4. How to run things

Full details in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Quick reference:

```bash
uv sync                                         # once: .venv from uv.lock (all groups + editable fetch/preprocess)
source .venv/bin/activate
python -m data_tui                              # data TUI — pull → preprocess → verify → deploy (PRD #233)
python scripts/preprocess.py                    # all sources + all states
python scripts/preprocess.py --state 05         # one state
python scripts/preprocess.py --app-assets       # index.json + per-state facets / slim parquet / county boundaries
python scripts/preprocess.py --tiles            # per-state parcels.pmtiles (needs tippecanoe)
python scripts/preprocess.py --rebuild-manifest # resync manifest with disk
python scripts/verify_raw.py                    # contents check
python scripts/serve.py 8765                    # range-capable data server (repo root)
cd app && npm run dev                           # map app — http://localhost:5173
pytest                                          # preprocess + app-asset script tests
```

---

## 5. Adding a new data source

1. Create `scripts/fetch/sources/<your_source>.py` with one subclass
   of `DataSource`, exported as `SOURCE` (or `SOURCES = [...]`).
   Prefer the matching mixin from `fetch.base` when one fits:
   `ManualOnlySource` (click-through downloads) supplies the canonical
   `remote_version() → "manual"` + `fetch() → RuntimeError` pair.
2. Set `AutomationPolicy` correctly — default to `MANUAL_ONLY` if
   unsure. Never err on the side of unauthorized scraping.
3. Set `update_cadence_days` (see
   [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) §2 for the rules).
4. For MANUAL_ONLY: implement `manual_walkthrough()` returning
   ordered steps with deep links + expected files
   (see [docs/PULLER_UX.md](docs/PULLER_UX.md) §4).
5. Append to `scripts/fetch/registry.py`.
6. Document in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).
7. If you need a normalizer, create
   `scripts/preprocess/normalizers/<source>.py`,
   `@register_normalizer`, declare which `canonical_types` it produces.
   Add to `scripts/preprocess/registry.py`.
8. Add a test fixture under `tests/fixtures/<source>_raw/` + a test
   file `tests/test_<source>.py` (one file per source surface;
   see [docs/TESTING.md §9](docs/TESTING.md)).

Things to get right:

- `remote_version()` must be **cheap** (one HEAD, one small JSON GET).
  Slow probes block the parallel "Check for updates" sweep. The
  `_helpers.version_from_head(url)` helper covers the canonical
  Last-Modified → ETag → Content-Length fallback chain.
- `fetch()` must call the `progress` callback during streaming so the
  UI bar advances.
- Use `_helpers.safe_extract_zip` for any zip extraction
  (path-traversal protection).
- `validate()` runs after fetch / after manual download — make it
  forgiving of zip vs unzipped variants.

---

## 6. Known fragile points

Per-source upstream-failure tracking is in
[docs/LIMITATIONS.md](docs/LIMITATIONS.md). Most fragile:

- FCC ASR / ULS bulk URLs (publisher restructures occasionally).
- FAA DOF archive page (path rename).
- HUD ArcGIS layers (service rename / layer-ID change — live as of
  2026-05-21 but restructure-prone; `remote_version()` probes them).
- USDA ERS file URL (migrates between editions; current path live).
- LBNL TTS annual filename (scraper finds newest).
- EIA 860 / 860M placeholder pages (we check `min_bytes`).

**Never "fix" a MANUAL_ONLY source by adding scraping logic without
confirming the publisher's terms have changed.**

---

## 7. Pilot geography reference

State-level scope ([ADR-001](docs/adr/0001-state-level-geographic-scope.md)). Committed
anchors `05` (AR), `12` (FL), `30` (MT), `54` (WV); deferred stretch `37` (NC); dropped
`18` (IN), `49` (UT), `27` (MN). The canonical anchor list + per-state status are owned by
[docs/SCOPE.md §2](docs/SCOPE.md) and [docs/STATUS.md](docs/STATUS.md).

---

## 8. Conventions for code edits

- **Headless `scripts/fetch/`.** No UI imports inside it. Textual
  lives only in `scripts/data_tui/`.
- **Atomic writes everywhere.** Download to `.partial`, rename to
  `current/`. Manifest writes go through `Manifest.save()` (temp +
  rename).
- **Preprocess outputs EPSG:4326.** Every spatial output reprojected
  to WGS84 lat/lon.
- **Sparse comments.** Only where the *why* is non-obvious
  (a hidden constraint, a workaround, surprising behavior).
- **No new normalize-time filtering** (full-fidelity raw preservation;
  see [ARCHITECTURE.md §3.3](docs/ARCHITECTURE.md)). Keep all rows;
  add status / validity columns; let Joins and Views filter.
- **Use `safe_merge`** when a Join adds columns that a Normalizer
  initializes as placeholders ([ADR-020](docs/adr/0020-safe-merge-helper.md)).
- **The data TUI is the only puller UI** (PRD #233/#240): the Qt desktop puller is retired and deleted — do not resurrect it or reintroduce PySide6; puller features go to `scripts/data_tui/` (see [`scripts/data_tui/AGENTS.md`](scripts/data_tui/AGENTS.md)).

**Backend invariants** (do not relax — full mechanics in [`backend/README.md`](backend/README.md), do-not-relax list in [`backend/AGENTS.md`](backend/AGENTS.md)):

- **`tenant_id` on every table; every route filters by it** ([ADR-055](docs/adr/0055-hosted-private-backend.md)); SQLAlchemy ORM, SQLite dev / Postgres via `DATABASE_URL`. The `credential`/`tenant` tables are the deliberate exceptions (a credential *determines* the tenant).
- **Auth posture is load-bearing** (ADR-062/063/069): credentials live in the **`credential` table** (managed only via `python -m app.users`) and **re-authorize every request** — API routes *and* the edge-gated `/data/processed/*`; the JWT is **identity-only** in the **httpOnly `pilot_session` cookie**; **teams are tenants**; `AUTH_DEV_MODE` fails closed. Never reintroduce `APP_USERS`/`users.txt`, localStorage tokens, tenant/team claims in the JWT, or the `tenant_id=1` stub; never commit the DB or hand-edit hashes.
- **Schema changes ship as Alembic revisions** (PRD #134) — never additive back-fill helpers in `db.py`. The **OpenAPI schema is the frontend's type contract** (PRD #133) — regenerate + commit both artifacts after any model change.
- **Owner merge/split + the owners index each resolve in one place**: `display_cluster_id = coalesce(override_target, raw_cluster_id)` (never forked per surface, never baked into the parquet); the owners index is schema-versioned with safe defaults + backend-model declaration (contract in [`scripts/preprocess/AGENTS.md`](scripts/preprocess/AGENTS.md)).

---

## 9. Where to look for what

| Question | File |
|---|---|
| What does this project do? | [PROJECT_BRIEF.md](PROJECT_BRIEF.md) |
| What's in scope + what does success look like? | [docs/SCOPE.md](docs/SCOPE.md) |
| What works today? | [docs/STATUS.md](docs/STATUS.md) |
| What shipped when? | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| How does the system fit together? | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Per-source schema / license / policy | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) |
| When does each source need a refresh? | [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) |
| Caveats + pre-commercial blockers | [docs/LIMITATIONS.md](docs/LIMITATIONS.md) |
| PII / data-handling | [docs/SECURITY.md](docs/SECURITY.md) |
| Glossary of terms (A–Z) | [docs/GLOSSARY.md](docs/GLOSSARY.md) |
| Product language + mental model | [CONTEXT.md](CONTEXT.md) |
| What's next (Phase 2/3) | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Locked design choices | [docs/DECISIONS.md](docs/DECISIONS.md) (index of all ADRs) + [docs/adr/](docs/adr/) (per-ADR files) |
| How to deploy / share outputs | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| `data/` on an external drive (T9) + exfat gotchas | [docs/EXTERNAL_DATA_DRIVE.md](docs/EXTERNAL_DATA_DRIVE.md) |
| Testing strategy | [docs/TESTING.md](docs/TESTING.md) |
| Puller UX design | [docs/PULLER_UX.md](docs/PULLER_UX.md) |
| Map app — architecture + how to run | [app/ARCHITECTURE.md](app/ARCHITECTURE.md) |
| Data-source legal/license research (2026-05-26) | [docs/research/](docs/research/) |
| Active work plan | [docs/STATUS.md](docs/STATUS.md) + [docs/ROADMAP.md](docs/ROADMAP.md) |
| What's on disk + last fetch time | `data/manifest.json` |
| Last 200 puller events | `data/fetch.log` |
| Per-source canonical-schema mapping | `scripts/preprocess/normalizers/<source>.py` |
| Per-state field maps for parcel sources | `scripts/preprocess/normalizers/state_parcels.py` |

---

## Agent skills

Configuration for Matt Pocock's engineering skills (`triage`, `to-issues`,
`to-prd`, `diagnose`, `tdd`, `improve-codebase-architecture`,
`grill-with-docs`, etc.). Each subsection points to a doc the skills
consult; edit those docs directly to change behavior.

### Issue tracker

GitHub Issues at `danielgentile22/infra-lease-analytics`, managed via the
`gh` CLI. See [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md).

### Triage labels

Five canonical labels using default names (`needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`). Not yet created on the
repo — the `triage` skill will create them on first use. See
[docs/agents/triage-labels.md](docs/agents/triage-labels.md).

### Domain docs

Single-context: [CONTEXT.md](CONTEXT.md) at the repo root. All ADRs under
[docs/adr/](docs/adr/), indexed by [docs/DECISIONS.md](docs/DECISIONS.md).
See [docs/agents/domain.md](docs/agents/domain.md).

---

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
