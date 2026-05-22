# ROADMAP — Past, Present, Future

**Last updated:** 2026-05-20
**Pairs with:** [SCOPE.md](./SCOPE.md) (this cut), [STATUS.md](./STATUS.md)
(today), [GOALS.md](./GOALS.md) (why), [DECISIONS.md](./DECISIONS.md)
(locked-in choices).

This document traces the arc of the project: what's been built, what's
being built now, and what's planned next. It's the place to point
someone who asks "how did we get here and where are we going?"

---

## Past — what's been built

### v0 — Graham County one-shot (early prototype)

A single `preprocess.py` script that ingested FCC ASR, NC OneMap
parcels for Graham County NC, and HUD Opportunity Zones; spatial-
joined them; and produced three GeoJSON files for a Leaflet web map.
The original `PROJECT_BRIEF.md` describes this version.

- ✅ Proved the tower → parcel → distress linkage was technically
  achievable.
- ✅ Produced a working map demo for Graham County.
- ❌ Hard-coded to one county; not generalizable.
- 📁 Archive: `docs/archive/preprocess_v1.py.txt` (moved in Section
  5.6 of the production-readiness plan).

### v1 — The data puller

A standalone PySide6 desktop app at `app_puller/` for pulling 28 raw
data sources into `data/raw/<source_id>/current/`:

- Each source declares an `AutomationPolicy` (ALLOWED, TOLERATED,
  MANUAL_ONLY, CREDENTIALED) — the puller enforces these.
- Atomic `.partial` → `current/` promotion after `validate()` passes.
- Single `data/manifest.json` as the source of truth for "what we
  have on disk."
- JSONL event log for fetch attempts.

### v2 — Preprocess framework

A registry-driven preprocessing system replacing the one-shot script:

- `Normalizer` per source (raw → canonical schema)
- `Join` per cross-source relationship
- `View` per derived dataset (map filters, top-N lists, etc.)
- Per-state `Composer` that loads canonical data, runs joins, runs
  views, and writes a `catalog.json` for the map app to consume.
- Dual GeoParquet + GeoJSON output (Parquet canonical for analytics;
  GeoJSON for the legacy map app).
- Canonical schemas for `parcel`, `tower`, `distress_overlay`,
  `solar_facility`, `billboard`, `county_score`, plus 9 reserved
  types for future use.
- Owner clustering (normalized name + address → SHA1 cluster id).
- Interestingness scoring (composite per-parcel score for outreach
  prioritization).

### v3 — This cut (Production-readiness, May 2026)

Active work plan in `/.claude/plans/cached-wobbling-token.md`. Eight
sections in sequence:

1. Documentation foundation — ✅ complete
2. Version control + GitHub setup — ✅ complete
3. Data puller overhaul — ✅ complete
4. Data hygiene (raw data refresh) — ⚠️ AR/MT pulled and solid; FL raw intact, processed deleted; NC all data deleted (needs re-fetch)
5. Preprocess code hygiene — ⚠️ in progress; FL/NC need chunked compose (ADR-051) before re-running
6. Testing — ⬜ not started
7. Pitch readiness — ⬜ not started
8. Map app rehaul — ✅ complete (Svelte 5 + MapLibre + PMTiles + DuckDB-WASM)

Goal: a pitch-quality demo cut across 4 anchor states with
defensible numbers, tests, CI, and coherent docs. See
[SCOPE.md](./SCOPE.md) for the full definition and
[STATUS.md](./STATUS.md) for today's exact state.

---

## Present — what's being built right now

Per [SCOPE.md](./SCOPE.md):

- **Anchor states:** AR + NC + MT + FL (all four; UT dropped — no
  owner data, ADR-049). AR and MT compose cleanly today. FL raw data
  is intact (all 67 counties) but normalized + composite were deleted
  2026-05-20 to free disk; needs re-normalize + compose once the
  chunked compose is built (ADR-051). NC all raw data deleted
  2026-05-20; needs full re-fetch, normalize, and compose. See
  [STATUS.md](./STATUS.md).
- **Sources:** working set is FCC ASR, FAA OEAAA, state parcels for
  anchor states, HUD OZ + QCT, ARC distressed, USDA persistent
  poverty, EIA 860/860M, USPVDB.
- **Output:** per-state `data/processed/composite/<fips>/` with
  Parquet + GeoJSON + catalog.json + summary.json + views/.
- **Map app:** rebuilt — Svelte 5 + MapLibre + PMTiles + DuckDB-WASM,
  live at `app/` (see [../app/ARCHITECTURE.md](../app/ARCHITECTURE.md));
  the v1 Leaflet app is retired to `app_legacy_v1/`.
- **Tests + CI:** pytest scaffold + GitHub Actions in Section 6.

See [STATUS.md](./STATUS.md) for today's exact state.

---

## Near future — immediately after this cut

These are the things we deliberately deferred *within this cut* and
will pick up as the next push. None of them are speculative — they
have known scope and known need.

### FCC ULS normalizers

~5 GB of raw ULS data on disk for 6 bands (cellular, market-based,
microwave, ownership, transfers, leasing) plus metadata. None of it
is yet processed. Unlocks:

- **Carrier presence** per tower (AT&T / Verizon / T-Mobile / etc.) —
  single biggest driver of lease value.
- **Leasing data** — which licenses sub-lease their spectrum to
  whom; secondary lease economics.
- **Transfers** — license sales over time; market-velocity signal.

Estimated effort: a normalizer per band; complex but each is bounded.

### FDOR NAL for Florida (if not in this cut)

If we don't reach FL during Section 4 of this cut, it's the first
post-pitch state to add.

### Refresh cadence + alerting

The puller will track `next_recommended_check_at` per source after
Section 3. Post-pitch, add desktop notifications or weekly email
summary of stale sources.

---

## Mid-future — post-pitch quarters

### Second asset class: billboards

State DOT outdoor-advertising permit datasets (FL, NC, TX have raw
data on disk; normalizers deferred). Same parcel-join workflow as
towers; adds a second renegotiation-target asset class.

### Distress signal layering

Tax-delinquency lists, foreclosure pre-filings, sheriff-sale notices,
CDFI Investment Areas, Census ACS poverty/income at tract level. Each
adds an axis to the `interestingness_score` composite.

### LLC enrichment (not unmasking)

Secretary of State business-entity records → infer entity type,
formation date, registered agent. **Not** human-identity resolution.
UCC-1 filings to confirm third-party-owned assets.

### Solar third-party-ownership detection

LBNL "Tracking the Sun" rooftop data + state PUC interconnection
reports + UCC-1 filings → flag leased / PPA-owned solar systems
where the contract is potentially renegotiable.

### Hosted deployment

Single-user hosted instance (likely a small EC2 or Fly.io VM) so a
partner or co-founder can access the map without local install. Adds
basic auth.

---

## Long-term — the business

The data work documented in this repo is the foundation of a business
that:

1. **Identifies** undervalued ground-lease and buyout-target
   opportunities at scale.
2. **Prioritizes** them by economic-distress signal (most material
   help, highest probability of engagement).
3. **Equips** the landowner with the analytical basis to renegotiate
   or evaluate offers — independent of the tower/lease-buyout
   companies' counter-incentive.

What this repo does **not** include and **will not** include:

- **Outreach / CRM.** That's a separate product layer.
- **Contact-data resolution.** Partners or providers handle that.
- **LLC unmasking.** Sensitive, expensive, separate product.
- **Lease-buyout transaction infrastructure.** Different stack
  entirely.

The data layer is "the input." Everything else lives elsewhere.

### Geographic expansion ladder (long-term)

1. **Anchor states** (this cut): AR + NC + MT (+ FL).
2. **Free-data multi-state expansion:** add IA, AR-already-done,
   any other states with clean free statewide parcel feeds.
3. **Paid nationwide via Regrid:** instant ~150M parcels with
   consistent schema. Requires budget unlock (~$1k+/mo).
4. **Selective enrichment:** add tax-delinquency, foreclosure,
   recorder filings for priority counties.

Each step gates on actual business signal (are pilots converting?
Is there partner appetite?) — not on data-side ambition.

---

## How this roadmap evolves

- **Past** is append-only — each completed cut moves into "Past."
- **Present** is what the active work plan says; it changes whenever
  the plan file changes.
- **Near future** is the next 1–2 pushes; concrete enough that
  effort estimates exist.
- **Mid + long future** are intentionally soft — directionally right
  but expected to shift as we learn more from the pitch.

Update this doc at the start of every new section in the work plan,
and after every pitch / partner conversation that materially changes
priorities.
