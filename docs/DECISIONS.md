# DECISIONS — Architecture Decision Records (ADRs)

**Last updated:** 2026-05-19

Compact ADRs for every locked-in choice. New decisions append; old
decisions never disappear (struck through `~~like this~~` if reversed).
Each entry: Context (1 sentence), Decision, Consequences. Keep under
30 lines per ADR.

> When in doubt about a design call, check this file before
> reopening the debate. If the entry is here, the decision is locked
> unless the *context* materially changes.

---

## Foundation

### ADR-001 — Geographic scope is state-level, not county-level

- **Date:** 2026-05 (v3 framework adoption)
- **Context:** The original Graham-County one-shot was county-specific.
  When generalizing, county-level composes would multiply outputs and
  make cross-state analytics awkward.
- **Decision:** The Composer runs per **state** (FIPS). County-level
  analysis is achieved via Views that filter a state composite by
  `county_fips`, not via a separate Composer mode.
- **Consequences:** State dropdown in the map; cross-county queries
  free; per-county refresh requires re-running the whole state.

### ADR-002 — Registry-driven Normalizer / Join / View architecture

- **Date:** 2026-05
- **Context:** Hard-coded preprocessing wouldn't generalize past
  Graham; we expected to add sources, joins, and views faster than the
  core pipeline could absorb them.
- **Decision:** Three registries (Normalizer per source, Join per
  relationship, View per derived dataset), each populated via
  `@register_*` decorators imported by `scripts/preprocess/registry.py`.
- **Consequences:** Adding a source = one file in `normalizers/`.
  Adding a filter = one file in `views/`. The core pipeline doesn't
  change.

### ADR-003 — Dual GeoParquet + GeoJSON output

- **Date:** 2026-05
- **Context:** Parquet is dramatically smaller, supports column
  projection, and is the right analytical format. But the legacy
  Leaflet app only speaks GeoJSON.
- **Decision:** Every spatial output is written as both
  `<layer>.parquet` (canonical) and `<layer>.geojson` (for the map).
  For layers ≥ `HUGE_GEOJSON_THRESHOLD` (100K rows) only the
  simplified-geometry GeoJSON is written.
- **Consequences:** Doubles disk usage for small layers, but lets
  the map keep working while DuckDB-style analytics use Parquet.
  Future map app rehaul (ADR-030) will drop the redundant GeoJSON.

### ADR-004 — Current-only data versioning, no history

- **Date:** 2026-05 (user-confirmed during puller design)
- **Context:** Retaining every prior raw download would balloon disk
  use (~15 GB per snapshot today, more as we add states); incremental
  diffing isn't needed for a feasibility prototype.
- **Decision:** `data/raw/<source_id>/current/` is the only state
  retained. Re-pulls overwrite. Audit trail lives in `data/fetch.log`.
- **Consequences:** Can't time-travel ("what did parcels look like
  6 months ago?"). Acceptable for a pitch cut; revisit if commercial
  use requires audit trail.

### ADR-005 — On-demand fetch trigger only

- **Date:** 2026-05
- **Context:** Scheduled background daemons add operational burden
  for a solo-dev prototype.
- **Decision:** All raw pulls are manually triggered via the puller
  UI. No cron, no in-app schedulers.
- **Consequences:** The puller must surface staleness clearly
  (Section 3 freshness model) so the user doesn't forget. Cadence-
  aware notification is a future task.

### ADR-006 — Static-site map app, no backend server

- **Date:** 2026-05
- **Context:** A backend would simplify large-data queries but
  triples the deployment surface for a feasibility tool.
- **Decision:** The map app is a static HTML/JS bundle. All filtering
  / search runs in the browser (today: in-memory JS; v2: DuckDB-WASM).
- **Consequences:** PMTiles + Parquet + GeoJSON via HTTP range
  requests scale to the v2 design. Puts a lower bound on map app
  complexity (DuckDB-WASM bundle is ~6 MB).

### ADR-007 — PySide6 pinned at 6.7.3

- **Date:** 2026-05
- **Context:** PySide6 6.11.x had a cocoa-plugin load failure on the
  developer's macOS arm64 setup.
- **Decision:** Pin `PySide6 == 6.7.3` (long-term-support branch).
- **Consequences:** Don't `pip install --upgrade` casually. Re-evaluate
  if 6.7.x reaches EOL.

---

## Data sourcing (v1 pitch cut)

### ADR-010 — Strict free-only data budget

- **Date:** 2026-05-19
- **Context:** User confirmed budget posture is "strict free only" for
  the pitch cut.
- **Decision:** No paid data (Regrid, ATTOM, CoreLogic, …) and no
  paid SaaS until / unless explicitly unlocked. Stubs stay in code
  but are documented as out of scope.
- **Consequences:** Statewide parcel coverage is patchwork — limited
  to the ~7 free statewide feeds. Anchor states chosen accordingly.

### ADR-011 — Anchor states locked: AR + NC + MT + UT (+ FL stretch)

- **Date:** 2026-05-19
- **Context:** Free-data states with usable owner attribution.
- **Decision:** AR (confirmed great), NC (refresh from 11-month-stale
  data), MT (free cadastral), UT (small, clean). FL pursued only via
  new `fdor_nal` per-county tax-roll source (current FGDL DSL data
  is wrong dataset).
- **Consequences:** Pitch narrative is 4–5 states; not nationwide.

### ADR-012 — Regrid deferred (paid)

- **Date:** 2026-05-19
- **Context:** Regrid is the gold-standard nationwide parcel feed at
  ~$1k+/mo per state license.
- **Decision:** Stub source stays in registry; not pursued for v1.
- **Consequences:** Nationwide coverage waits for budget unlock.

### ADR-013 — FCC ULS normalizers deferred to post-pitch

- **Date:** 2026-05-19
- **Context:** ~5 GB of raw ULS data on disk across 6 bands + meta;
  complex per-band schema; landowner-side pitch doesn't depend on
  carrier tenancy data.
- **Decision:** Leave raw data on disk; mark sources as deferred in
  the registry; no normalizers built this cut.
- **Consequences:** Carrier-presence per tower is a v2 enhancement.
  Lease-economic modeling waits.

### ADR-014 — Billboards deferred

- **Date:** 2026-05-19
- **Context:** Three state DOT billboard sources are in the registry;
  not core to the cell-tower thesis.
- **Decision:** Defer billboard normalizers to post-pitch.
- **Consequences:** Pitch is cell-tower only.

### ADR-015 — HIFLD towers retired

- **Date:** 2026-05-19
- **Context:** DHS retired the public HIFLD cellular-towers layer
  in 2024 as part of an infrastructure-data security review.
- **Decision:** Mark RETIRED in registry. Do not attempt to re-fetch.
- **Consequences:** FCC ASR is now the sole tower-locations source.
  Some short / rooftop towers won't appear (ASR's ≥ 200 ft threshold).

### ADR-016 — LBNL Tracking the Sun dropped from active registry

- **Date:** 2026-05-19
- **Context:** Rooftop / distributed solar data is interesting but
  USPVDB + EIA 860 already cover our solar narrative for the pitch.
- **Decision:** Drop LBNL from active registry. Raw data stays on
  disk; can re-add as a deferred source if rooftop solar becomes
  in-scope post-pitch.
- **Consequences:** Solar story is utility-scale only for now.

### ADR-017 — Indiana dropped from anchor states

- **Date:** 2026-05-18
- **Context:** Indiana's public parcels (downloaded via in_parcels)
  carry no `owner_name` column whatsoever — only `parcel_id`,
  geometry, county FIPS, situs address.
- **Decision:** Mothball IN from pitch anchor set; raw stays on
  disk for future re-evaluation.
- **Consequences:** Pitch demo skips IN entirely; map app hides it.

### ADR-018 — Minnesota deferred (license ambiguity)

- **Date:** 2026-05-18
- **Context:** MnGeo publishes "Plan Parcels Open" but license
  metadata reads "No License Provided" — ambiguous commercial-use
  status.
- **Decision:** Defer pending MnGeo confirmation. Don't pull, don't
  process, don't include in pitch numbers.
- **Consequences:** Loses a Midwestern data point for now.

### ADR-019 — FL FGDL DSL parcels replaced by `fdor_nal` source

- **Date:** 2026-05-19
- **Context:** The currently-installed FL parcel data is FGDL's
  Department of State Lands (DSL) layer — publicly-owned state
  land only, not the FDOR NAL tax roll with private owners.
- **Decision:** Drop FGDL from active registry. Add a new
  `scripts/fetch/sources/fdor_nal.py` source for the FDOR NAL data,
  policy MANUAL_ONLY (per-county downloads).
- **Consequences:** FL anchor depends on user pulling 5–10
  representative counties (Miami-Dade, Hillsborough, Orange, Duval,
  Pinellas, Lee, Polk, Brevard, Volusia, Marion suggested).

---

## Code architecture

### ADR-020 — `safe_merge` helper for joins with pre-initialized columns

- **Date:** 2026-05-19
- **Context:** Three `county_score_to_*` joins all hit a `KeyError`
  because the parcel schema initialized `distress_tier` /
  `persistent_poverty` as placeholders, causing `_x`/`_y` column
  collision on `pd.merge`.
- **Decision:** Extract a `safe_merge(left, right, on,
  columns_to_add)` helper into `scripts/preprocess/base.py` that
  drops pre-existing target columns before merging. Apply to every
  join that adds columns also initialized in a normalizer.
- **Consequences:** Generic guard; future joins won't repeat this
  bug pattern.

### ADR-021 — `--source` flag for selective rebuild

- **Date:** 2026-05-19
- **Context:** Force-rebuild currently re-normalizes everything; for
  a single-source fix, this wastes 30+ min.
- **Decision:** `python scripts/preprocess.py --source <id>` runs
  one source through the normal manifest-aware path. No bypass.
- **Consequences:** Eliminates the manifest-bypass problem that
  caused this session's stale manifest.

### ADR-022 — `--rebuild-manifest` for disk-derived sync

- **Date:** 2026-05-19
- **Context:** The preprocess manifest can drift from disk reality
  when work is interrupted or paths are touched outside the runner.
- **Decision:** `python scripts/preprocess.py --rebuild-manifest`
  walks `data/processed/normalized/*/` + `data/processed/composite/*/`
  and rewrites the manifest from current files. Does not re-run
  preprocessing.
- **Consequences:** Cheap recovery path; should be in user's muscle
  memory after any non-trivial work session.

### ADR-023 — `HUGE_GEOJSON_THRESHOLD = 100,000` rows

- **Date:** 2026-05-18
- **Context:** AR (2.1M) and IN (3.7M) produced 3.6 GB / 5.6 GB
  parcel GeoJSONs that no browser can load.
- **Decision:** In `scripts/preprocess/io.py`, layers with ≥ 100K
  rows skip the full-geometry GeoJSON; only the simplified-geometry
  copy is written under `<layer>.geojson`.
- **Consequences:** Map app sees one geojson regardless; quality
  degrades smoothly. Parquet is canonical so analytics are unaffected.

### ADR-024 — Owner clustering = SHA1(normalized name + address)

- **Date:** 2026-05
- **Context:** Detecting "this owner owns 12 parcels" requires
  canonicalizing names and addresses (case, punctuation, suffixes).
- **Decision:** `cluster_id = sha1(normalize_owner_name(name) +
  '|' + normalize_address(addr))`. Implementation in
  `scripts/preprocess/cluster.py`.
- **Consequences:** Cluster IDs are stable across runs given the
  same inputs. Imperfect (e.g., "Smith Family Trust" vs "Smith
  Family Living Trust" cluster apart); good-enough for the pitch.

---

## Future (locked-in for the next push)

### ADR-030 — Map app v2 stack: MapLibre + PMTiles + DuckDB-WASM + Svelte

- **Date:** 2026-05-19
- **Context:** The current Leaflet app can't handle multi-million-
  parcel states; filter surface lags v3 schema fields.
- **Decision:** v2 will be MapLibre GL JS (WebGL rendering), PMTiles
  (single-file vector tiles, no server), DuckDB-WASM (in-browser
  SQL over Parquet via HTTP range requests), Svelte + Vite (UI).
  Tippecanoe generates PMTiles at preprocess time.
- **Consequences:** Adds Node toolchain + Homebrew tippecanoe to
  developer requirements. Static-site model preserved (ADR-006).

### ADR-031 — Map app rehaul deferred to post-pitch

- **Date:** 2026-05-19
- **Context:** Audit found bigger gaps (broken endpoints, missing
  normalizers, no tests, doc drift) than the map app itself.
  Sequencing them first builds a solid foundation for the rebuild.
- **Decision:** v1 Leaflet app gets minimal patches only during this
  cut (Section 8 of the work plan). Full rebuild starts after the
  pitch lands.
- **Consequences:** Pitch demos use the current map. Map performance
  caveats live in LIMITATIONS.md.

---

## Policy

### ADR-040 — Parcel-owner data is PII; treat accordingly

- **Date:** 2026-05-19
- **Context:** Parcel data carries owner names + mailing addresses,
  which together meet most PII definitions even when individually
  public-record.
- **Decision:** (a) No public hosting of composite outputs until
  access controls exist. (b) `data/` and `data/processed/` are
  git-ignored. (c) Sharing outputs externally requires an explicit
  reason logged in `docs/SECURITY.md`.
- **Consequences:** GitHub repo is private by default. Demo
  screenshots that show real owner names may need redaction
  depending on audience.

### ADR-041 — No LLC unmasking (permanent non-goal)

- **Date:** Carried forward from PROJECT_BRIEF
- **Context:** Resolving the human(s) behind an LLC is sensitive,
  expensive, and a separate product.
- **Decision:** Never implement in this repo. Display the raw
  entity string.
- **Consequences:** Pitch shows entity names as-is. Resolving people
  behind entities is a downstream business question, not ours.

### ADR-042 — Documentation lives in `docs/` (subfolder)

- **Date:** 2026-05-19
- **Context:** Root had 7 .md files with ~3500 lines mixing business,
  technical, plan, and limitations. Cognitively overloading.
- **Decision:** Root keeps only README.md, CLAUDE.md, PROJECT_BRIEF.md.
  All other docs move to `docs/`. New docs go straight to `docs/`.
- **Consequences:** Root stays scannable. Inbound links from
  README/CLAUDE point into `docs/`.

### ADR-043 — Tests: pytest for backend; Vitest + Playwright deferred to map app v2

- **Date:** 2026-05-19
- **Context:** Backend is Python; frontend rebuild is deferred.
- **Decision:** Add pytest now for `scripts/preprocess/` + fixtures.
  Vitest + Playwright wait until the map app v2 work begins.
- **Consequences:** Backend regression coverage is the immediate
  priority; UI tests follow the rebuild.

### ADR-044 — CI on GitHub Actions

- **Date:** 2026-05-19
- **Context:** User confirmed GitHub as the version-control home.
- **Decision:** `.github/workflows/lint.yml` (ruff) and
  `.github/workflows/test.yml` (pytest) on every push.
- **Consequences:** All pushes must pass lint + tests once Section 6
  lands. Branch protection follows.
