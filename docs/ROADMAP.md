# ROADMAP — Past, Present, Future

**Last updated:** 2026-06-13 (UI overhaul + Settings + #130–#138 hardening shipped; deployed to production)
**Pairs with:** [SCOPE.md](./SCOPE.md), [STATUS.md](./STATUS.md), [GOALS.md](./GOALS.md), [DECISIONS.md](./DECISIONS.md) + new ADRs under `docs/adr/`.

This document traces the project arc: what's been built, what's being built now, what's planned next. Updated at the start of every new slice / phase and after every material strategic conversation.

---

## Past — what's been built

### v0 — Graham County one-shot (early prototype)

A single `preprocess.py` script that ingested FCC ASR + NC OneMap parcels for Graham County + HUD Opportunity Zones; spatial-joined them; produced three GeoJSON files for a Leaflet web map.

- ✅ Proved tower → parcel → distress linkage was technically achievable.
- ✅ Produced a working map demo for Graham County.
- ❌ Hard-coded to one county; not generalizable.
- 📁 The v1 one-shot script + its v3 plan were retired; recover from git history if ever needed (`git log --all -- docs/archive/`).

### v1 — Data puller

PySide6 desktop app at `app_puller/` for pulling 28 raw data sources into `data/raw/<source_id>/current/`. Per-source `AutomationPolicy`; atomic `.partial → current/` promotion; single `data/manifest.json`; JSONL fetch log.

### v2 — Preprocess framework

Registry-driven preprocessing replacing the one-shot script:

- `Normalizer` per source (raw → canonical schema)
- `Join` per cross-source relationship
- `View` per derived dataset
- Per-state `Composer`
- Dual GeoParquet + GeoJSON output (modulo `NO_GEOJSON_THRESHOLD` per ADR-052)
- Canonical schemas for `parcel`, `tower`, `distress_overlay`, `solar_facility`, `billboard`, `county_score`
- Owner clustering (ADR-024 — gets strengthened in Phase 1 Slice 4 per [ADR-056](./adr/0056-lead-equals-owner-cluster.md))
- Interestingness scoring (becomes tunable + transparent per [ADR-058](./adr/0058-tunable-transparent-scoring.md))

### v3 — Pitch-cut foundation (May 2026, partial)

Eight-section production-readiness plan oriented to a pitch-quality demo across 4 anchor states. The framework, the puller, Git + CI, the map app rehaul (Svelte 5 + MapLibre + PMTiles + DuckDB-WASM at `app/`), and the AR/MT data-quality remediation all shipped. Sections 6 (testing) and 7 (pitch readiness) didn't ship before the pivot to product-phase work on 2026-05-25.

---

## Present — Phase 1 (the product cut)

On **2026-05-25** the project pivoted from "pitch-quality demo" to "fleshed-out co-founder-facing product" — see [ADR-053](./adr/0053-product-phase-shift.md). The committed anchors are **AR + MT + FL + WV** (NC demoted to a deferred Phase-1 stretch 2026-05-29; WV added + elevated to a committed anchor 2026-05-29, [ADR-060](./adr/0060-wv-committed-anchor.md) — see [SCOPE.md §2](./SCOPE.md)); the audience changed; several previously-deferred feature areas flipped to in-scope.

Slice plan (untimed, goal-driven):

1. **F** — Committed-anchor composes (AR + MT + FL + WV); FL recomposed 2026-05-29, county-score gap closed (chunked compose ADR-051); WV added + committed as the 4th anchor 2026-05-29 (ADR-060, PR #44). NC re-fetch + compose **deferred** (Phase-1 stretch).
2. **A** — FCC ULS carrier identification (Cellular + PCS + AWS / 700) — **landed:** data layer merged (#12 normalize → #11 ULS↔ASR join calibration → #22 licensee→brand rollup → #24 `carriers` on every tower); carrier-list UI merged (#28 / PR #71). Coverage ~6–17% of ASR towers (high-precision / low-recall).
3. **C** — Asset enrichment (billboards + solar on parcel) + tunable scoring UI
4. **D + E** — Lease doc upload + LLM extraction + triage state / write layer / CSV exports (backend stands up here per [ADR-055](./adr/0055-hosted-private-backend.md)). **Reordered 2026-05-30:** the write-layer + lead-centric triage UI redesign were pulled forward ahead of A and C and **shipped** ([ADR-061](./adr/0061-lead-centric-triage-redesign.md), PRD #46, Slices #47–#53); the remaining D+E work is lease-doc upload + LLM extraction.
5. **B** — Vendor (tower-co) inference

> **Update 2026-06-13 — most of Phase 1 shipped; product live in production.** On
> top of the lead-centric redesign (PRD #46 / [ADR-061](./adr/0061-lead-centric-triage-redesign.md),
> Slices #47–#53) came the UI overhaul — three-section IA + Tasks + tower-grained
> Explore (PRD #103/#119/#121, ADR-065/066/067), per-user Settings (PRD #121,
> ADR-068), and the #130–#138 hardening pass. **Slice A (carriers) landed**
> (#11/#12/#22/#24 + UI #28; ~6–17% coverage, so the original "≥70%" gate is
> overtaken by measured reality — [GOALS §3](./GOALS.md)), and **Slice C's tunable
> scoring UI shipped** (#105/#114/#115). **Next:** the rest of **D+E** — lease-doc
> upload + LLM extraction (not yet started) — then **Slice B** (vendor inference).
> The 4-week outcome-bar clock starts after Slice B. See [STATUS.md](./STATUS.md)
> for the live state.

Per-slice gates in [GOALS.md §3](./GOALS.md). Outcome bar: co-founder uses the product as his primary daily triage tool for 4 consecutive weeks.

See [STATUS.md](./STATUS.md) for today's exact state.

---

## Near future — Phase 2 (after Phase 1 outcome bar)

Phase 2 is asset-universe expansion to rooftop / in-building installations + operational scale. Not started until Phase 1 outcome bar passes — the co-founder's 4 weeks of usage will surface the actual highest-pain Phase 2 item.

### Asset universe — rooftops

- Different data foundation (CoStar / LoopNet / mortgage feeds — mostly paid).
- Different anchor-state fit (dense-urban; AR / MT have little rooftop volume).
- Co-founder asks that defer with rooftops: tenant occupancy in the building, building owner mortgage status, building tenant mix, electric meter source, property manager team.

See [ADR-054](./adr/0054-asset-universe-phase-1-2.md).

### Operational scale

- **Mass email + response tracking** — third-party email infra (Postmark / SES) + webhook handling + deliverability hygiene + CAN-SPAM compliance.
- **Self-serve refresh from the product** — wire the puller into the backend so the co-founder can trigger a re-pull without the dev.
- **Recorded-lease automation** — scrape Memorandum of Lease recordings from county clerk sites for top counties (per-county effort; rare-rent-disclosing jurisdictions get smoking-gun comps).
- **Paid Steel-in-the-Air tier** — granular per-tower comp data, augmenting the free county-averages bootstrap (ADR-057 reframes ADR-010).
- **Paid skip-trace for contact enrichment** — Whitepages Pro / Cole Information / IDI for owner phone + email beyond the SoS officer-disclosure baseline. Stays explicitly within ADR-057's narrowed posture.
- **Comparables maturation** — as uploaded leases accumulate (ADR-059 extraction loop), the private comp DB starts dominating the public-data bootstrap; "outliers in X-mile radius" becomes a real feature.

### Scaling watch-triggers (not work, just the lines to watch)

The single-machine deploy (ADR-064) has two known cliffs to watch for — neither is a
problem at Phase-1 scale, but each has a clear trigger and a pre-planned move:

- **Owners index served as in-memory JSON.** Python's JSON object overhead is ~3–5×
  file size on a 1 GB VM that also runs Caddy + Litestream. When `owners_index.json`
  approaches ~100 MB (≈ current states × 3), move the read path to SQLite or
  server-side DuckDB over the parquet — `OwnersIndexService` already isolates the swap.
- **SQLite, one writer.** The day a second machine, a background-writer process, or
  >~10 concurrent writers appears, switch to Postgres — the code is already DB-agnostic,
  `psycopg` ships, and testcontainers tests exist. Postgres RLS (engine-enforced tenant
  isolation) is the principled follow-on if tenants beyond the founding team appear.

### Stretch — mortgage / financial distress signal

Paid CoStar / ATTOM / mortgage feeds. Surfaces "owner mortgage current?" "owner liquidity?" — co-founder's explicit asks deferred from Phase 1.

---

## Mid-future — Phase 3 and beyond

Quarter-scale, contingent on Phase 2 traction:

### Geographic expansion

- **Free-data state additions** (IA, post-IN/UT if/when owner data unlocks).
- **Paid nationwide via Regrid** — instant ~150M parcels with consistent schema. Budget unlock conversation.

### Multi-tenant sale

The tenant-shaped schema baked Day 1 (ADR-055) anticipates selling the tool to other land-side consultants. Each new tenant = a row in `tenant`; no rewrite.

### Second asset class — billboards as primary

Billboard pipeline runs in Phase 1 as enrichment (parcels host billboards). Phase 3 makes billboards a primary triage axis equal to towers.

### LLC enrichment, not unmasking

Secretary of State business-entity records → infer entity type, formation date, registered agent. **Not** human-identity resolution (still permanent non-goal per ADR-041 narrowed via [ADR-057](./adr/0057-budget-posture-reframed.md)).

### Solar third-party-ownership detection

LBNL "Tracking the Sun" rooftop data + state PUC interconnection reports + UCC-1 filings → flag leased / PPA-owned solar systems where the contract is renegotiable.

---

## Long-term — the business

The data + tool work in this repo is the foundation of a business that:

1. **Identifies** undervalued ground-lease and buyout-target opportunities at scale.
2. **Prioritizes** them by economic-distress + lease-economics signal.
3. **Equips** the landowner with the analytical basis to renegotiate or evaluate offers.

What this repo does **not** include and **will not** include:

- **Outreach automation** beyond what fits in Phase 2 (mass email + tracking)
- **Contact-data resolution beyond paid skip-trace** — partner data
- **LLC unmasking** in the sensitive sense (still permanent non-goal per ADR-041 narrowed)
- **Lease-buyout transaction infrastructure** — different stack entirely

---

## How this roadmap evolves

- **Past** is append-only.
- **Present** changes whenever the Phase 1 slice plan changes.
- **Near future = Phase 2** sharpens after the Phase 1 outcome bar — the co-founder's 4 weeks of usage will surface the actual highest-pain Phase 2 item.
- **Mid + long** intentionally soft; directionally right but expected to shift.

Update at the start of every new slice / phase, and after every material strategic conversation.
