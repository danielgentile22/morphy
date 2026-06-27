# CHANGELOG — Milestone history

**Last updated:** 2026-06-26

The newest-first record of what shipped when. [STATUS.md](./STATUS.md) owns *current* state;
this doc owns the trail. Finer detail than this lives in git.

For why each decision was made, see the ADRs ([DECISIONS.md](./DECISIONS.md)).

---

## Phase 1 — the product cut (2026-05-25 → present)

### 2026-06 — internal tooling, Ask Claude, hardening, Halo re-skin

- **2026-06-25/27 — data-audit fixes + basemap + county-FIPS fix.** All 14 EASY-bucket
  data-audit fixes landed (#198/#202/#203); MapTiler Satellite Hybrid basemap became the
  app default (#199/#200/#201/#204); a malformed-`CENSUS_BK` cross-state county-FIPS bug
  was fixed in preprocess (#206).
- **2026-06-23/24 — "Halo" dark design system.** The map app + data-audit site were
  re-skinned onto a unified dark theme (PRD/#194/#196/#197); the light/dark chrome toggle
  was retired (the map basemap picker stays). Dashboard moved to a 2×2 digest grid.
- **2026-06-20 — data-audit catalog + Ask Claude shipped & deployed.** The standalone
  `audit-site/` Svelte app (live at `morphyconsulting.com/audit/`, gated by the same
  `forward_auth` as `/data/processed/*`; PR #176 + #181–#186) — a browsable data catalog
  over `docs/research/data-audit/`. **Ask Claude** (PRD #187, slices #188–#190) is the
  backend's first SSE stream: `POST /api/audit/ask` + an `ask_log` table (Alembic
  `0002_ask_log`). Deployed 2026-06-20 but **dormant until the `ANTHROPIC_API_KEY` Fly
  secret is set** — returns a clean 503 meanwhile; the catalog is unaffected.
- **2026-06-21 — dead-code removal sweep (#192/#193).** Retired the verified-dead
  parcel-grained filter subsystem + backend/preprocess micro-cuts.
- **2026-06-12/13 — Phase-1 hardening, PRDs #130–#138 (all shipped, deployed
  2026-06-13).** Closed the unauthenticated PII data plane + moved credentials into the
  app DB + cookie sessions (#130, ADR-069); frontend CI gate (#131); uv toolchain + real
  packaging, `sys.path` hacks retired (#132); generated OpenAPI→TS types, drift-gated
  (#133); Alembic versioned migrations (#134); DuckDB as the preprocess heavy-lift engine
  (#135); pyright on `backend/` (#136); cross-language contract fixtures (#137); Qt puller
  frozen bug-fix-only with a named Textual-TUI successor (#138).

### 2026-06-04/07 — production + UI overhaul

- **Deployed to production (#16 / #96).** The app went live (Fly single always-on machine
  `morphy-consulting`, SQLite-on-volume + Litestream→R2 backups, Cloudflare front;
  ADR-064). DuckDB-WASM + PMTiles served client-side over HTTP Range. `deploy.sh smoke`
  asserts unauth `/data/processed/*` → 401/403.
- **UI overhaul + Settings (PRD #103/#119/#121/#125; ADR-065/066/067/068).** Three-section
  IA (Dashboard · Explore · Leads) + Dashboard digest hub; the Tasks subsystem (`task`
  table, `/api/tasks`, auto follow-ups); tower-grained Explore + per-tower `score` (owners
  index → **schema v5**); inbound-reply activity seam (`ContactAttempt.direction`);
  per-user Settings (theme/colorblind/basemap/default view/filter defaults) + self-service
  password change.

### 2026-05-30/06-02 — auth + lead-centric redesign + carriers

- **Auth (PRD #75 + #83; ADR-062/063).** Username/password front door replaced magic-link;
  teams-as-tenants; the credential source re-authorizes every request; identity-only JWT.
  (Storage later moved to the DB by #130/ADR-069.)
- **Lead-centric triage redesign complete (PRD #46, ADR-061).** Slices #47–#53: write-layer
  tracer → auth → full Lead page (owners index v2) → structures-first map → My-Leads kanban
  → top-bar filters + owner/ASR search (v3) → manual owner merge/split.
- **Slice A — carrier identification landed.** ULS↔ASR carrier layer (#11/#12/#22/#24) +
  carrier-list UI (#28, owners index → v4 `carriers`). Coverage ~6–17% of ASR towers
  (high-precision / low-recall) — an empty list is the common case.
- **Slice C — tunable scoring UI shipped** (#105/#114/#115; tunable live re-rank + named
  presets). Solar→parcel done (#14); billboards remain a no-op until anchor raw data is
  populated (#13).

### 2026-05-29 — West Virginia anchor + FL recompose

- **WV added + elevated to a committed anchor (PR #44, ADR-060).** New `wv_parcels`
  MANUAL_ONLY source (WVGISTC statewide `.gdb`, SB 588); `composite/54` built (1,389,855
  parcels, 11 joins, 8 views, 0 warnings); committed set became **AR + MT + FL + WV**.
- **FL recomposed (county-score gap closed).** `composite/12` rebuilt via chunked compose
  (11,425,608 parcels, 11 joins, 8 views, 0 warnings); `county_scores` layer + tower/solar
  county-score joins now present, consistent with AR/MT.

### 2026-05-25 — phase shift: pitch demo → Phase 1 product (ADR-053)

The project reframed from "v1 pitch-quality demo across 4 states" to "Phase 1 of a
co-founder-facing product." Previously-deferred feature areas flipped in-scope (FCC ULS
carriers, billboards/solar on parcel, lease-doc upload + LLM extraction, triage write
layer, free public-records contact enrichment). The slice plan F → A → C → D+E → B and the
4-week outcome bar were set here. Superseded/narrowed ADRs: 006→055, 010→057 (reframed),
041→057 (narrowed). See [SCOPE.md](./SCOPE.md).

---

## Pre-pivot — pitch-cut foundation

### v3 — pitch-cut foundation (May 2026, partial)

Eight-section production-readiness plan oriented to a pitch-quality demo across 4 anchor
states. The framework, the puller, Git + CI, the map-app rehaul (Svelte 5 + MapLibre +
PMTiles + DuckDB-WASM at `app/`), and the AR/MT data-quality remediation all shipped.
Sections 6 (testing) and 7 (pitch readiness) didn't ship before the 2026-05-25 pivot.

### v2 — preprocess framework

Registry-driven preprocessing replacing the one-shot script: `Normalizer` per source,
`Join` per cross-source relationship, `View` per derived dataset, per-state `Composer`,
dual GeoParquet + GeoJSON output (modulo `NO_GEOJSON_THRESHOLD`, ADR-052), canonical
schemas (`parcel`/`tower`/`distress_overlay`/`solar_facility`/`billboard`/`county_score`),
owner clustering (ADR-024), interestingness scoring (ADR-058).

### v1 — data puller

PySide6 desktop app at `app_puller/` for pulling raw data sources into
`data/raw/<source_id>/current/`. Per-source `AutomationPolicy`; atomic `.partial → current/`
promotion; single `data/manifest.json`; JSONL fetch log. (Now frozen — PRD #138.)

### v0 — Graham County one-shot (early prototype)

A single `preprocess.py` script that ingested FCC ASR + NC OneMap parcels for Graham County
+ HUD Opportunity Zones, spatial-joined them, and produced three GeoJSON files for a Leaflet
web map. Proved tower → parcel → distress linkage; hard-coded to one county. The v1 one-shot
script + its plan were retired (recover from git: `git log --all -- docs/archive/`).
