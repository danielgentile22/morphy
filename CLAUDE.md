# CLAUDE.md

Orientation for Claude Code sessions working in this repo. Read this
first; then dip into the relevant doc under [docs/](docs/) when you
need depth.

**Last updated:** 2026-05-30 (**the Lead write-layer grew past the tracer** — Slice 2 **magic-link auth merged** (#48 / PR #56: HS256 JWT + route-level tenant-from-JWT, the `tenant_id=1` stub is gone, fail-closed `AUTH_DEV_MODE`), and the Slice 3 **full Lead page** is in review (#49 / PR #57: cross-state holdings + EPSG:4326 mini-map + editable contact + contact-attempts log + auto-logged status; owners index bumped to **schema v2**). Prior 2026-05-30: Slice 1 write-layer tracer (#47 / PR #54) — the first backend code on disk. See docs/STATUS.md.

> **🔀 2026-05-25 phase shift:** The project pivoted from "v1 pitch
> demo" to **Phase 1 of a co-founder-facing product** — see
> [ADR-053](docs/adr/0053-product-phase-shift.md). Phase 1 is
> freestanding towers across AR + MT + FL + WV (NC deferred to a Phase-1
> stretch candidate; WV elevated to a committed anchor 2026-05-29,
> [ADR-060](docs/adr/0060-wv-committed-anchor.md)); Phase 2 is rooftops
> ([ADR-054](docs/adr/0054-asset-universe-phase-1-2.md)). Several legacy
> ADRs were superseded, narrowed, or partially reversed — see
> [docs/DECISIONS.md](docs/DECISIONS.md) for the full index.

---

## 0. Working with the user

These rules apply to every action you take in this repo, override
session defaults, and should not be relaxed without explicit
instruction.

### Explanation & communication

- After completing any task, provide a clear summary of what you did
  and why.
- When you create or modify files, list each file changed with a
  one-line description of the change.
- Explain any non-obvious decisions or trade-offs you made.
- If you chose a particular approach over alternatives, briefly say why.
- Flag anything you were uncertain about or assumptions you had to make.

### Running & reproducing

- Whenever you create something runnable (script, app, service, test),
  include exact commands to run it.
- Specify any prerequisites: dependencies to install, environment
  variables, required versions, services that must be running.
- Give the commands as copy-pasteable blocks, in the order they should
  be run.
- If there's a build step, state it explicitly and separately from the
  run step.
- Mention how to verify it worked (expected output, how to test, what
  success looks like).

### Code changes

- Before making large or structural changes, briefly outline the plan first.
- Make minimal, targeted changes unless asked to refactor.
- Don't delete or rewrite working code without explaining why.
- Preserve existing style and conventions in the codebase.

### Safety & caution

- Ask before running destructive commands (deleting files, dropping
  data, force-pushing, etc.).
- Don't install new dependencies without mentioning it and explaining
  why it's needed.
- If a command could affect things outside the project directory, call
  it out first.

### When stuck or blocked

- If you hit an error you can't resolve, stop and explain what failed,
  what you tried, and what you'd need to proceed.
- Don't silently work around problems in ways that hide them.

---

## 1. What this project is

Phase 1 of a co-founder-facing product that helps landowners renegotiate
ground leases for infrastructure on their property — primarily cell
towers. The data problem: no single dataset links an asset to the
landowner; we construct it by joining FCC ASR + state parcels + HUD /
ARC / USDA distress overlays, then layer carrier identification + lease
document storage + LLM-based extraction + triage workflow on top.

- **Business case:** [PROJECT_BRIEF.md](PROJECT_BRIEF.md)
- **Current scope (what's in/out right now):** [docs/SCOPE.md](docs/SCOPE.md)
- **Goals + outcome bar:** [docs/GOALS.md](docs/GOALS.md)
- **Today's state:** [docs/STATUS.md](docs/STATUS.md)

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
│   ├── research/             Data-source legal/license research
│   └── archive/              Historical (preprocess v1, original v3 plan)
├── app/                      Svelte 5 + MapLibre map app (see app/ARCHITECTURE.md)
├── app_puller/               PySide6 desktop puller
├── backend/                  FastAPI + SQLAlchemy lead-triage write-layer (tenant-scoped Lead state; SQLite dev / Postgres). Magic-link auth merged (#48); full Lead page — holdings + contact + attempts (#49). S3 lease-doc storage + Claude API still planned. See backend/README.md
├── scripts/
│   ├── fetch/                Headless puller library
│   ├── preprocess/           Normalizer/Join/View framework + Composer
│   ├── serve.py              Range-capable static server (for the map app)
│   └── *.py                  Top-level CLI scripts
├── data/                     Git-ignored (~15 GB raw + composites)
└── tests/                    Pytest — preprocess pipeline + app-asset scripts
```

The full repository layout + system diagram is in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 3. The current work plan

Phase 1 slice plan (untimed, goal-driven): **F → A → C → D+E → B**. After Slice B, the **4-week outcome-bar clock** starts (cofounder uses the product as his primary daily triage tool for 4 consecutive weeks).

> **Update (2026-05-30):** the ADR-055/056 write-layer (originally part of D+E) was pulled ahead via the lead-centric triage redesign, and its end-to-end **tracer is merged** (#47 / PR #54) — a cross-state owners-index precompute + a tenant-scoped FastAPI/Postgres Lead backend + a Candidates/Lead UI. Lease-doc upload + LLM extraction (the rest of D+E) remain unimplemented; see docs/STATUS.md §6.

Per-slice "shipped" gates in [docs/GOALS.md §3](docs/GOALS.md). Current slice + blockers in [docs/STATUS.md](docs/STATUS.md) — always check it before starting a new task.

---

## 4. How to run things

Full details in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Quick reference:

```bash
source .venv/bin/activate
python -m app_puller                            # raw data fetcher (desktop UI)
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

State-level scope ([ADR-001](docs/adr/0001-state-level-geographic-scope.md)). Phase 1 committed anchor states: `05` (AR), `12` (FL), `30` (MT), `54` (WV — added + elevated to a committed anchor 2026-05-29, [ADR-060](docs/adr/0060-wv-committed-anchor.md); `wv_parcels`, WVGISTC statewide layer SB 588; see [docs/STATUS.md §4.4](docs/STATUS.md)). Deferred / Phase-1 stretch: `37` (NC) — raw deleted 2026-05-20, re-fetch + normalize + compose deferred (NC OneMap re-fetch intermittently 504s); still in the picture, just not a committed anchor. Dropped entirely (no owner data): `18` (IN — ADR-017), `49` (UT — ADR-049). Live anchor set + per-state status in [docs/SCOPE.md §2](docs/SCOPE.md) / [docs/STATUS.md](docs/STATUS.md).

---

## 8. Conventions for code edits

- **Headless `scripts/fetch/`.** No PySide6 imports inside it. Qt
  lives only in `app_puller/`.
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
- **Backend — `tenant_id` everywhere** ([ADR-055](docs/adr/0055-hosted-private-backend.md)). Every table has it; every route filters by it. SQLAlchemy ORM, SQLite dev / Postgres via `DATABASE_URL`. The tenant is now **derived from the magic-link JWT** (`current_tenant_id`, #48) — do not reintroduce the `tenant_id=1` stub; respect the fail-closed `AUTH_DEV_MODE` posture. Schema changes ride an additive `init_db` migration until Alembic (e.g. the Slice 3 `lead.contact_*` columns, #49). See `backend/README.md`.

---

## 9. Where to look for what

| Question | File |
|---|---|
| What does this project do? | [PROJECT_BRIEF.md](PROJECT_BRIEF.md) |
| What's in scope right now? | [docs/SCOPE.md](docs/SCOPE.md) |
| What does success look like? | [docs/GOALS.md](docs/GOALS.md) |
| What works today? | [docs/STATUS.md](docs/STATUS.md) |
| How does the system fit together? | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Per-source schema / license / policy | [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) |
| When does each source need a refresh? | [docs/DATA_FRESHNESS.md](docs/DATA_FRESHNESS.md) |
| Caveats + pre-commercial blockers | [docs/LIMITATIONS.md](docs/LIMITATIONS.md) |
| PII / data-handling | [docs/SECURITY.md](docs/SECURITY.md) |
| Glossary of terms | [docs/GLOSSARY.md](docs/GLOSSARY.md) + [CONTEXT.md](CONTEXT.md) |
| Past / future of the project | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Locked design choices | [docs/DECISIONS.md](docs/DECISIONS.md) (index of all ADRs) + [docs/adr/](docs/adr/) (per-ADR files) |
| How to deploy / share outputs | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
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
