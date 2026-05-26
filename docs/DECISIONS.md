# DECISIONS — Architecture Decision Records (ADRs)

**Last updated:** 2026-05-25

Compact ADRs for every locked-in choice. New decisions append; old
decisions never disappear (struck through `~~like this~~` if reversed
or **annotated with a Status line** if superseded / revised by a newer ADR).
Each entry: Context (1 sentence), Decision, Consequences. Keep under
30 lines per ADR.

> When in doubt about a design call, check this file before
> reopening the debate. If the entry is here, the decision is locked
> unless the *context* materially changes.

---

## 📋 ADR-053 and onwards live in `docs/adr/`

This file is the legacy ADR home (ADR-001 through ADR-052). New ADRs
go in `docs/adr/` per `CLAUDE.md §9`. Current new ADRs (all from the
2026-05-25 phase-shift grill — see `docs/grill-2026-05-25-summary.md`):

- [ADR-053 — Product phase shift (pitch → product)](./adr/0053-product-phase-shift.md)
- [ADR-054 — Phase 1 freestanding / Phase 2 rooftops](./adr/0054-asset-universe-phase-1-2.md)
- [ADR-055 — Hosted-private backend (supersedes ADR-006)](./adr/0055-hosted-private-backend.md)
- [ADR-056 — Lead = owner-cluster (follow-up to ADR-024)](./adr/0056-lead-equals-owner-cluster.md)
- [ADR-057 — Budget posture reframed (revises ADR-010 + ADR-041)](./adr/0057-budget-posture-reframed.md)
- [ADR-058 — Tunable + transparent scoring](./adr/0058-tunable-transparent-scoring.md)
- [ADR-059 — LLM extraction approach for leases](./adr/0059-llm-lease-extraction.md)

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
- **Consequences:** Doubles disk usage for small layers. The shipped
  map app (ADR-030) reads the GeoJSON for its catalog layers; the
  parcel layer uses PMTiles built from the Parquet.

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

- **Status:** ⊘ Superseded by [ADR-055](./adr/0055-hosted-private-backend.md) for write-layer features (lead state, lease docs, auth). Read-only analytical layers (parquet, PMTiles, GeoJSON) stay static.
- **Date:** 2026-05
- **Context:** A backend would simplify large-data queries but
  triples the deployment surface for a feasibility tool.
- **Decision:** The map app is a static JS bundle. All filtering /
  search runs in the browser (DuckDB-WASM over Parquet).
- **Consequences:** PMTiles + Parquet + GeoJSON over HTTP range
  requests need no backend. Puts a lower bound on map app complexity
  (the DuckDB-WASM bundle is ~6 MB).

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

- **Status:** ↻ Revised by [ADR-057](./adr/0057-budget-posture-reframed.md) — reframed from "permanent stance" to "current budget posture for Phase 1." Paid unlocks expected Phase 2+.
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
- **Status:** UT dropped by ADR-049 — anchor set is now AR + NC + MT + FL.
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

- **Status:** ↻ Partially reversed by [ADR-053](./adr/0053-product-phase-shift.md) Slice A — Cellular (Part 22) + PCS (Part 24) + AWS / 700 MHz (Part 27) bands are in Phase 1 for carrier identification. Microwave, Ownership, Transfers, Leasing remain deferred to Slice B / Phase 2.
- **Date:** 2026-05-19
- **Context:** ~5 GB of raw ULS data on disk across 6 bands + meta;
  complex per-band schema; landowner-side pitch doesn't depend on
  carrier tenancy data.
- **Decision:** Leave raw data on disk; mark sources as deferred in
  the registry; no normalizers built this cut.
- **Consequences:** Carrier-presence per tower is a v2 enhancement.
  Lease-economic modeling waits.

### ADR-014 — Billboards deferred

- **Status:** ↻ Partially reversed by [ADR-053](./adr/0053-product-phase-shift.md) Slice C — billboards run as **parcel enrichment** (`has_billboard`, `billboard_count`) in Phase 1, not as a primary triage axis. Billboards-as-primary asset class still deferred to Phase 3.
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

- **Status:** ↻ Follow-up locked in [ADR-056](./adr/0056-lead-equals-owner-cluster.md) — Slice 4 layers stronger conservative normalization (suffix stripping, name-token sort, trust/estate normalization, USPS address standardization) + a manual merge/split UI before the SHA1 hashing. Phonetic name match explicitly excluded (biases toward false merges).
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

- **Status:** ✅ Realized — shipped 2026-05-21. See
  [../app/ARCHITECTURE.md](../app/ARCHITECTURE.md).
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

- **Status:** ⊘ Superseded — the rehaul was executed within this cut
  as Section 8 (2026-05-21), not deferred to post-pitch. See ADR-030.
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

- **Status:** ↻ Narrowed by [ADR-057](./adr/0057-budget-posture-reframed.md) — paid skip-trace + shell-piercing remain permanent non-goals. Free public-records officer disclosure (Secretary of State business-entity lookups, UCC-1) is in scope for Phase 1 (Slice 4 D+E lead-detail panel).
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

- **Status:** ✅ Realized — the map app ships with Vitest unit +
  Playwright E2E tests in `app/tests/` (2026-05-21).
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

### ADR-045 — Registry split: `_ACTIVE` + `_DEFERRED` blocks

- **Date:** 2026-05-19
- **Context:** Section 4.3 reduced the v1 surface to ~14 sources but
  the original `scripts/fetch/registry.py` had no way to track
  "imported but not in v1 scope" classes. Deleting them would erase
  the schema work; comment-blocks rot.
- **Decision:** Registry exposes two lists — `_ACTIVE` (shown to the
  puller and preprocess) and `_DEFERRED` (imported but invisible
  upstream). `all_sources()` returns only active; `deferred_sources()`
  exists for tooling. `get_source()` resolves across both so a
  reactivated source keeps working with the same ID.
- **Consequences:** Reactivating any deferred source = one-line move
  between the lists. Puller's `_prune_orphan_manifest_entries` cleans
  the manifest automatically when something moves from active to
  deferred.

### ADR-046 — FL parcel data: replace FGDL DSL with FDOR NAL

- **Date:** 2026-05-19
- **Status:** Superseded by ADR-047 (county set expanded from 10 to all 67).
- **Context:** The previously-active `fl_fgdl_parcels` source pulls
  FGDL DSL (state-domain land — state-owned parcels) which has no
  private-landowner data. Composing FL with that produced empty
  `owner_name` columns and was useless for our pitch.
- **Decision:** New source `fdor_nal` (Florida Department of Revenue
  Name-Address-Legal tax roll, per-county). MANUAL_ONLY with a
  per-county walkthrough; v1 originally shipped 10 representative
  counties (~60% of FL population): Miami-Dade, Hillsborough, Orange,
  Duval, Pinellas, Lee, Polk, Brevard, Volusia, Marion.
- **Consequences:** FL composite gains owner data. FGDL DSL moved to
  deferred.

### ADR-047 — FL FDOR NAL coverage expanded to all 67 counties

- **Date:** 2026-05-19
- **Supersedes:** ADR-046 (county set).
- **Context:** Original FDOR scope was 10 representative counties
  (~60% of FL population) to keep manual-download effort bounded.
  After confirming the PAR shapefiles are PIN+NAL joined and downloads
  are direct (no queueing or click-through per county beyond the
  one-time portal terms acceptance), the marginal effort to pull all
  67 is low while the pitch narrative gets stronger ("all of Florida"
  vs "representative counties").
- **Decision:** `fdor_nal` ships all 67 Florida counties for v1. The
  walkthrough lists every county alphabetically as a download
  checklist. Both condo files (`miamidade_condos_2025par.zip` and
  `stjohnscondos_2025.zip`) are included.
- **Consequences:** FL raw footprint grows from ~500 MB to ~2-3 GB
  (still well within budget — disk, not API). Preprocess time for FL
  scales ~6.7x; this stress-tests the Section 5.2 vectorization work.
  Strengthens the pitch by removing "10 counties, why those?" as an
  objection vector. No change to the canonical schema, normalizer, or
  the FGDL deferral.

### ADR-048 — NC OneMap parcels: auto-fetch via MapServer pagination

- **Date:** 2026-05-19
- **Context:** `nc_onemap_parcels` was wired to NC OneMap's Hub
  download API
  (`https://www.nconemap.gov/api/download/v1/items/<id>/shapefile`)
  which previously delivered the statewide shapefile bundle reliably.
  As of 2026-05 the endpoint returns persistent HTTP 500 across
  retries hours apart. A first pass flipped the source to
  MANUAL_ONLY, but the manual path required the user to split the
  5.9M-record layer into ~6 batches via Hub's Download tab (Hub's
  async export ceiling is ~2M features) — wasting ~6 hours per
  refresh. The underlying ArcGIS MapServer `/query` endpoint is
  healthy and supports pagination at 5000 features/page.
- **Decision:** Keep `AutomationPolicy.ALLOWED`. Replace the broken
  bulk-API `fetch()` with a paginated MapServer query loop. Each
  page (5000 features, geometry @ EPSG:4326, ~21 explicit fields) is
  written as `page_NNNN.geojson` under
  `data/raw/nc_onemap_parcels/current/`. Resumable on interruption:
  pages already on disk are skipped. The normalizer reads them via
  rglob (already supports GeoJSON). The field map in
  `state_parcels.py` lists both casings (uppercase from legacy
  shapefile bulk, lowercase from MapServer JSON) for forward + back
  compat.
- **Consequences:** Fetch takes ~30–60 min unattended (1,186
  sequential requests). Disk footprint: ~10 GB (vs ~2 GB for the
  old single-shapefile download — the per-page GeoJSON pages carry
  redundant FeatureCollection envelopes and verbose JSON encoding;
  acceptable trade-off for full automation). MapServer `/query` is
  the canonical ArcGIS REST endpoint, version-stable, and won't
  break with Hub UI redesigns. If NC restores the bulk-download API
  we can swap back to the simpler single-file path; the MapServer
  pagination remains as a documented fallback either way.

### ADR-049 — Utah dropped from anchor states (no owner data)

- **Date:** 2026-05-20
- **Supersedes:** the UT portion of ADR-011.
- **Context:** UT was an anchor state, picked as the "small, clean
  dataset" to validate the stack quickly. While wiring up the
  `ut_parcels` pull, an audit of UGRC's parcel data found that
  **none** of its public parcel layers include an owner name: the
  statewide aggregate (`UtahStatewideParcels`, 1.59M records), the
  per-county basic parcels, and the per-county LIR parcels — all 29
  counties scanned — carry value, acreage, property class, year
  built, and situs address, but the only owner-adjacent field is
  `OWN_TYPE` (a private/government category, not a name). UGRC's
  Land Information Record standard deliberately omits owner name.
  Owner data lives behind 29 separate county-assessor portals with
  no bulk download.
- **Decision:** Drop UT from the anchor set, mirroring the Indiana
  decision (ADR-017) — owner data is the core of the pitch (LLC
  identification, owner clustering, interestingness scoring) and a
  UT composite would have empty `owner_name` columns. Anchor set is
  now **AR + NC + MT + FL**. `UtParcelsManual` moved to the
  registry's `_DEFERRED` block; it stays imported so it can be
  re-promoted if a Utah owner-data source ever materialises. MT
  absorbs UT's former "small clean state" role.
- **Consequences:** Pitch narrative is 4 states, all with owner
  data — a *more* consistent demo than 5 states where one behaves
  differently. No code beyond the registry move + `ut_parcels`
  description fix. The `ut_parcels.py` source's earlier description
  ("normalised owner + value attributes") was factually wrong and
  has been corrected.

---

## Code architecture (continued)

### ADR-050 — Streaming per-county parcel normalize

- **Date:** 2026-05-20
- **Context:** The parcel normalizer originally read every layer of a
  multi-layer source, materialised them all in memory, and
  concatenated before mapping to canonical. Fine for single-layer
  sources (AR), but Florida's FDOR set is 67 county shapefiles
  totalling ~28 GB raw — concatenating would need ~50 GB peak RAM,
  far past the 16 GB dev machine. The old code also had a silent
  "fall back to all layers" path that, combined with a wrong MT
  field map, concatenated 12 unrelated Montana shapefiles into one
  garbage 6.5M-row output.
- **Decision:** The normalizer **streams** — it processes one
  county-layer at a time, maps it to canonical, and writes one
  parquet per county under
  `normalized/<source>/<canonical_type>/<county>.parquet`, with the
  raw copy under `normalized/<source>/raw/<county>.parquet`. Peak
  memory is bounded to a single county. Normalize-stage GeoJSON
  output is dropped (GeoParquet only); the Composer still dual-writes
  GeoParquet + GeoJSON for the map app (ADR-003). The Composer's
  loader reads the per-county parquet directory transparently. The
  silent layer-fallback was removed and replaced with a loud
  `RuntimeError`.
- **Consequences:** FL's 11.2M-parcel set normalizes within memory.
  AR's re-normalize got *faster and smaller* (~2m29s, 1.3 GB output)
  because the redundant GeoJSON write is gone. The MT garbage-output
  failure mode is now impossible — a missing expected layer fails
  loudly instead of silently widening scope.

### ADR-051 — Chunked compose for memory-bounded large states

- **Date:** 2026-05-20
- **Status:** Approved; **not yet implemented** as of 2026-05-20.
- **Context:** The normalizer streams (ADR-050), but the **Composer**
  does not. `compose._load_state_data` loads every county parquet for
  a state into memory and `pd.concat`s them — measured at ~1,710
  bytes/parcel, so ~19.5 GB peak for Florida's 11.18M parcels, far
  past the 16 GB dev machine. A local FL compose this session ran
  through the load and all 9 joins (macOS swaps rather than
  OOM-killing) but the ~13 GB `parcels.parquet` write exhausted the
  near-full disk. NC (~5.9M parcels) will hit the same wall.
- **Decision:** Refactor the Composer to **chunk** parcels — process
  one county at a time, run the parcel-touching joins against the
  small ancillary tables, and write per-county composite slices
  (parcels become a multi-file layer, like the normalized layout).
  Globally-scoped joins/views (e.g. owner clustering) get a slim
  two-pass: pass 1 computes cluster IDs from an owner-columns-only
  projection of all parcels; pass 2 attaches them per county. Peak
  memory stays bounded to a single county.
- **Consequences:** FL and NC compose locally, as will future large
  states. The Composer plus the global joins/views need the refactor
  and tests. No change to the canonical schema or the `catalog.json`
  contract. Small single-layer states (AR, MT) are unaffected.

### ADR-052 — `NO_GEOJSON_THRESHOLD`: Parquet-only for very large layers

- **Date:** 2026-05-21
- **Context:** `io.py` had a single `HUGE_GEOJSON_THRESHOLD` (100K rows)
  that switched a layer from a *full* to a *simplified* GeoJSON. The
  logic assumed "simplified ⇒ browser-safe", which is false past a few
  hundred thousand polygons: AR's 2.1M-parcel simplified
  `parcels.geojson` was **3.9 GB** and MT's **1.8 GB** — unloadable in
  any browser. The audit flagged this as a P0 blocker.
- **Decision:** Add a hard ceiling `NO_GEOJSON_THRESHOLD` (250,000 rows).
  At or above it, `dual_write_spatial` writes **Parquet only** — no full
  and no simplified GeoJSON. `catalog.json` advertises a `geojson_path`
  only when the file actually exists on disk. The map app needs no
  all-parcels GeoJSON — it renders every parcel from PMTiles vector
  tiles (built from the Parquet), and the per-state Views as GeoJSON.
- **Consequences:** AR/MT composites no longer carry a multi-GB
  `parcels.geojson` (~5.7 GB disk reclaimed). Parquet stays the
  canonical analytical format. Towers, solar, distress overlays and
  every View sit well under the ceiling and keep their GeoJSON. No
  change to the catalog contract beyond paths now being existence-gated.
