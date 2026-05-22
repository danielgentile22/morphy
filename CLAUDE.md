# CLAUDE.md

Orientation for Claude Code sessions working in this repo. Read this
first; then dip into the relevant doc under [docs/](docs/) when you
need depth.

**Last updated:** 2026-05-21 (full deep-dives live in `docs/`; read
[docs/STATUS.md](docs/STATUS.md) first — it is the current-state
handoff snapshot).

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

Feasibility prototype for a business that helps landowners renegotiate
ground leases for infrastructure on their property — primarily cell
towers. The data problem: no single dataset links an asset to the
landowner; we construct it by joining FCC ASR + state parcels + HUD /
ARC / USDA distress overlays.

- **Business case:** [PROJECT_BRIEF.md](PROJECT_BRIEF.md)
- **Current scope (what's in/out right now):** [docs/SCOPE.md](docs/SCOPE.md)
- **Goals + KPIs:** [docs/GOALS.md](docs/GOALS.md)
- **Today's state:** [docs/STATUS.md](docs/STATUS.md)

Hard non-goals (do not scope-creep): no LLC unmasking
([DECISIONS.md ADR-041](docs/DECISIONS.md)); no carrier/tenant
economics modeling; no production deployment; no nationwide coverage
without a paid parcel source (ADR-012).

---

## 2. Where things live

```
pilot/
├── README.md                 Quick start
├── CLAUDE.md                 This file
├── PROJECT_BRIEF.md          Business case
├── docs/                     All deep-dive documentation
│   └── archive/              Historical (preprocess v1, original v3 plan)
├── app/                      Svelte 5 + MapLibre map app (see app/ARCHITECTURE.md)
├── app_legacy_v1/            Leaflet map (v1, retired)
├── app_puller/               PySide6 desktop puller
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

Eight sections in sequence — documentation first, then code:

1. Documentation foundation — ✅ done
2. Version control + GitHub setup — ✅ done
3. Data puller overhaul — ✅ done
4. Data hygiene (raw data refresh) — ⚠️ AR/MT solid (HUD OZ/QCT + USDA distress sources added 2026-05-21); FL raw intact, processed deleted 2026-05-20; NC all data deleted 2026-05-20 (needs re-fetch)
5. Preprocess code hygiene — ⚠️ code complete; AR/MT audited clean 2026-05-21; FL/NC need chunked compose (ADR-051) before re-normalizing + composing
6. Testing — ⬜ not started
7. Pitch readiness — ⬜ not started
8. Map app rehaul — ✅ done (Svelte 5 + MapLibre + PMTiles + DuckDB-WASM; now at `app/`, see [app/ARCHITECTURE.md](app/ARCHITECTURE.md))

Note: the plan file `.claude/plans/cached-wobbling-token.md` is
currently **missing from disk** — [docs/STATUS.md](docs/STATUS.md) §6
is the authoritative section tracker until it is restored.

Always check the plan before starting a new task. Each section ends
with explicit verification before the next starts. For the precise
current state — including known bugs with their fixes and the
uncommitted-work list — read [docs/STATUS.md](docs/STATUS.md).

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

## 5. Locked design decisions

Read [docs/DECISIONS.md](docs/DECISIONS.md) before reopening any of
these. Highlights:

- State-level (not county-level) preprocess scope.
- Dual GeoParquet + GeoJSON output; huge layers skip the full GeoJSON.
- Current-only versioning (no history retained).
- On-demand pull only (no daemons / cron).
- Static-site map app (no backend).
- Anchor states: AR + NC + MT (+ FL stretch). UT dropped — no owner data (ADR-049).
- Free-only budget for v1 pitch; Regrid out of scope.
- FCC ULS normalizers + billboards deferred to post-pitch.
- HIFLD retired; LBNL TTS dropped; current FL FGDL replaced by `fdor_nal`.
- Map app v2 (MapLibre + PMTiles + DuckDB-WASM + Svelte) — realized, now at `app/`.
- Parcel-owner data is PII; no public hosting without access controls.
- Docs live in `docs/`; root keeps only README / CLAUDE / PROJECT_BRIEF.

---

## 6. Adding a new data source

1. Create `scripts/fetch/sources/<your_source>.py` with one subclass
   of `DataSource`, exported as `SOURCE` (or `SOURCES = [...]`).
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
8. Add a test fixture under `tests/fixtures/<source>_raw/` + a test in
   `tests/test_normalizers.py` (after Section 6 lands).

Things to get right:

- `remote_version()` must be **cheap** (one HEAD, one small JSON GET).
  Slow probes block the parallel "Check for updates" sweep.
- `fetch()` must call the `progress` callback during streaming so the
  UI bar advances.
- Use `_helpers.safe_extract_zip` for any zip extraction
  (path-traversal protection).
- `validate()` runs after fetch / after manual download — make it
  forgiving of zip vs unzipped variants.

---

## 7. Known fragile points

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

## 8. Pilot geography reference

Currently anchored at the **state** level (per ADR-001). See
[docs/SCOPE.md §2](docs/SCOPE.md) for the live anchor-state set. Graham
County NC (`37075`) is the original pilot context; expansion to multi-
state is the current cut.

Key state FIPS used throughout: `05` (AR), `12` (FL), `30` (MT),
`37` (NC). Dropped (no owner data): `18` (IN), `49` (UT).

---

## 9. Conventions for code edits

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
  initializes as placeholders ([DECISIONS.md ADR-020](docs/DECISIONS.md)).

---

## 10. Where to look for what

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
| Glossary of terms | [docs/GLOSSARY.md](docs/GLOSSARY.md) |
| Past / future of the project | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Locked design choices | [docs/DECISIONS.md](docs/DECISIONS.md) |
| How to deploy / share outputs | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Testing strategy | [docs/TESTING.md](docs/TESTING.md) |
| Puller UX design | [docs/PULLER_UX.md](docs/PULLER_UX.md) |
| Map app — architecture + how to run | [app/ARCHITECTURE.md](app/ARCHITECTURE.md) |
| Map app rebuild plan (realized) | [docs/MAP_APP_REHAUL.md](docs/MAP_APP_REHAUL.md) |
| Version history | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| Active work plan | `.claude/plans/cached-wobbling-token.md` |
| What's on disk + last fetch time | `data/manifest.json` |
| Last 200 puller events | `data/fetch.log` |
| Per-source canonical-schema mapping | `scripts/preprocess/normalizers/<source>.py` |
| Per-state field maps for parcel sources | `scripts/preprocess/normalizers/state_parcels.py` |
