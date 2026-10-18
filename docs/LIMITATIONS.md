# Limitations

**Archived.** The project is no longer under development. This file records the state of its
known limits when work stopped.

Data caveats, licensing constraints, scope limits, and known gaps. Read this before trusting
any output of the system. Read it with [STATUS.md](./STATUS.md) (what shipped and where it
stopped) and [SECURITY.md](./SECURITY.md) (PII posture).

Entries are grouped by kind:

- **Data caveats.** Quirks of the public sources and the joins built on them.
- **Licensing constraints.** Sources whose terms or publication limit what the data can be used for.
- **Scope limits and unbuilt features.** Deliberate non-goals, and planned work that was never built.
- **Resolved.** Issues that were fixed, kept so the reasoning survives.

---

## Data caveats

### ASR tower coordinates have known drift

Older FCC Antenna Structure Registration (ASR) records can have coordinates that drift from
the true location by tens to hundreds of meters. Visual inspection against satellite imagery
shows about 5-15% of towers in any given county miss their hosting parcel.

Implication:

- The tower→parcel spatial join uses strict `within` (no buffered match), so it
  **under-counts** matches rather than guess wrong.
- A tower with `parcel_id IS NULL` might still sit on a parcel the strict join missed.
- Outreach-grade use would need a buffered-fallback match with a manual-review step.

How to mitigate:

- When a tower has no parcel match, the detail panel says so: "No matching parcel,
  coordinates may have drift; verify against imagery."
- Report the strict join count as "towers we can confidently place on a specific parcel," not
  as "towers on private land."

---

### Carrier identification has spatial-fallback false positives

Slice A joins FCC Universal Licensing System (ULS) licenses to ASR towers in two ways. Where
ULS carries an ASR number, the join is a cross-reference (`verified` tag). Elsewhere it falls
back to spatial proximity (`likely` within 100 m, `possible` within 100-500 m). ULS coordinates
are unreliable, so the spatial-fallback bucket carries some wrong-tower matches.

Measured coverage came in at about 6-17% of ASR towers (high precision, low recall), well under
the original 70% target. An empty carrier list on a tower is normal. The ULS rework in
[ADR-074](./adr/0074-uls-carrier-rearchitecture.md) restored the modern spectrum bands
(PCS, AWS, 700 MHz) and reframed the badge as "Licensed in this area, not a confirmed tenant."

Implication:

- The detail panel shows each carrier with a confidence tag. Treat `likely` and `possible`
  matches as leads to check, not facts.

How to mitigate:

- Tighten the spatial-proximity tolerance based on a sample audit of cellular `LO` (location)
  records: if fewer than 30% carry a populated `asr_number`, tighten it.
- Recorded leases and carrier-contact verification would resolve ambiguous cases. Neither was
  built.

---

### Owner-type classification has a small residual

`infer_owner_kind` regex-classifies each parcel's `owner_name` into llc / trust / corporation /
partnership / gov / church / school / individual / unknown. After the 2026-05-21 remediation the
`unknown` rate is **2.1% (AR) / 4.9% (MT)**, down from about 51% / 35%. The government
patterns catch federal, state, county, tribal, and public-authority owners. Two residuals
remain, documented rather than chased further:

- **The `individual` bucket absorbs some unincorporated businesses.** Family farms, sole
  proprietorships, and `&`-joined names with no LLC/INC/CORP token read as person names. This
  does not affect the LLC and trust segments (matched on entity tokens), only the individual
  versus small-business split.
- **A long tail of keyword-less government names stays classified `individual`.** Examples are
  bare "HIGHWAY", "HWY", or "COUNTY ROAD" right-of-way fragments. They are tiny clusters (30
  parcels or fewer) and rank far below the top of any view.

Implication:

- The ranked views (`owner_clusters`, `interestingness_top_1000`) are clean of government
  owners at the top. The audit verified this by re-classifying the largest clusters in each
  state.
- A human should still confirm the owner type on any high-value target.

How to mitigate:

- The classifier is a deterministic regex table in `scripts/preprocess/cluster.py`, simple to
  extend when new patterns surface.

---

### HUD Opportunity Zone data is the original "OZ 1.0" designations

The Opportunity Zone (OZ) layer is the OZ 1.0 set from the 2017 Tax Cuts and Jobs Act, valid
through 2028. Governors are making "OZ 2.0" redesignations under the One Big Beautiful Bill Act
during 2026, so the map will change.

Implication:

- Tracts flagged `in_oz = true` today may not be OZ tracts after 2026.

How to mitigate:

- Refresh OZ data after each governor's redesignation announcement.
- Update the catalog `generated_at` so consumers can tell which vintage they are seeing.

---

### ARC distress is hardcoded to fiscal year 2026

The `arc_distressed` source fetches the Appalachian Regional Commission (ARC)
distress-classification list for the current fiscal year. The annual rotation may move counties
between tiers.

Implication:

- Any figure derived from it holds for the fiscal year at fetch time. Refresh annually.
- If a county changes tier mid-cycle, note it in the relevant commit.

---

### HIFLD cellular towers layer is permanently retired

The Department of Homeland Security (DHS) removed the public Homeland Infrastructure Foundation
Level Data (HIFLD) cellular-towers layer in its 2024 infrastructure-data security review. The
REST endpoint still answers but only returns errors, and no replacement is published for general
use. The fetcher and normalizer were removed from the repo on 2026-07-03.

Implication:

- FCC ASR is the only tower-location source.
- ASR's roughly 200-ft height threshold makes small and rooftop towers invisible. That matters
  for dense urban analysis and much less for the rural focus of this project.
- Vetted users can apply for HIFLD access through DHS's Geospatial Information Infrastructure
  (GII) portal. This project did not.

How to mitigate:

- Treat ASR plus FAA Obstruction Evaluation / Airport Airspace Analysis (OE/AAA) records as the
  joint tower-location truth.

---

### NC parcel fetch is incomplete

The NC partial (about 8.6 GB) was **deleted on 2026-05-20**, and NC was **demoted from the
committed anchors on 2026-05-29** to a deferred stretch state. The detail below describes the
fetch state as of 2026-05-20, kept for anyone who picks NC back up. See
[STATUS.md](./STATUS.md) for where NC stood when work stopped.

The NC OneMap MapServer auto-fetch (ADR-048) reached about 93%: **1,106 of 1,186** pages
(offsets 0-5,525,000, about 8.6 GB) were fetched and valid in
`data/raw/nc_onemap_parcels/.partial/`. The fetch then stalled. The MapServer returned **HTTP 504
Gateway Time-out** on the deep-offset query at `resultOffset=5,530,000`. Earlier probes of other
deep offsets succeeded (about 35 s each), so this was intermittent server-side degradation, not a
code bug.

A separate quirk: the puller's `prepare_fresh_partial()` wipes `.partial/` at the start of every
fetch, which defeats the NC source's documented resumability. A puller re-run restarts from page
0. The 1,106 pages were preserved at the time by resuming with a headless driver pointed at the
existing `.partial/`.

Implication:

- NC cannot be normalized or composed until the full pull lands. Since NC is deferred, this does
  not affect the committed anchor set (AR, MT, FL, WV).
- NC compose (about 5.9M parcels) runs through the chunked DuckDB compose, so memory is not the
  constraint it once was (see the resolved large-state entry below).

How to mitigate:

1. Re-run the fetch when the endpoint is healthy. Because of the `.partial/` wipe, plan for a
   full pull or resume with a headless driver.
2. Then normalize and compose NC.
3. Outreach-grade use needs a quarterly or faster refresh. Verify mailing addresses
   immediately before any physical mail.

---

### Parcel-owner names and addresses are PII

Each field (owner name, mailing address, parcel geometry) is public record on its own, but **the
combination** meets most definitions of personally identifying information (PII). Treat
composite parcel outputs accordingly.

Implication:

- **Never host composite outputs without access controls.** The hosted app serves them only
  behind auth (see the resolved data-plane entry below and [SECURITY.md](./SECURITY.md)).
- **`data/` is git-ignored.** No raw or composite output, and no secret, is committed to this
  repo.
- **Screenshots** that show real owner names may need redaction depending on the audience.
- **The local data server has no auth.** `python scripts/serve.py 8765` is for localhost only.

How to mitigate:

- [SECURITY.md](./SECURITY.md) is the authoritative PII posture ([ADR-040](./adr/0040-parcel-owner-pii.md)).
- Prefer AR (a high-LLC-ratio state) for screenshots, so entity names, not individuals, dominate
  the visible labels.

---

### Data pipeline is batch-only

Re-running `python scripts/preprocess.py` overwrites all outputs for any state it touches. There
is no streaming ingest and no scheduled refresh.

The hosted-private backend ([ADR-055](./adr/0055-hosted-private-backend.md)) holds the mutable
state: username/password auth ([ADR-062](./adr/0062-username-password-replaces-magic-link.md),
[ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md),
[ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)), teams as tenants on
a tenant-shaped schema, lead and task state, and the activity log. Lease documents were planned
for the backend but never built. The read-only analytical layers (parquet, PMTiles, GeoJSON) stay
static files, gated behind auth at the edge.

Implication:

- A developer runs the puller and preprocess by hand to refresh data.
- Self-serve refresh from the product (wiring the puller into the backend) was considered and
  never built.

---

### Raw data keeps the latest version only

`data/raw/<source_id>/current/` keeps only the latest version of each source
([ADR-004](./adr/0004-current-only-versioning.md)). The fetch log (`data/fetch.log`) records pull
events but does not keep historical raw files, so the system cannot answer "what did parcels look
like 6 months ago?"

Implication:

- Fine for a feasibility prototype.
- Outreach-grade use would need a snapshot-retention policy or a provider with versioned
  datasets.

How to mitigate:

- Composite outputs carry `sources_used_versions` in `catalog.json`, which answers "which raw
  versions did this composite come from?"
- Major refreshes get a commit listing the sources and dates.

---

## Licensing constraints

### MN "Plan Parcels Open" has no stated license

The Minnesota statewide parcels layer (`mn_parcels` →
`https://gis.data.mn.gov/datasets/minnesota::plan-parcels-open-2`) is marked **"No License
Provided. Request permission to use"** on the MnGeo dataset page, despite the "Open" name.

Implication:

- Fine for internal evaluation only.
- Any use beyond that requires reading MnGeo's actual terms and, if they are ambiguous, getting
  explicit written permission. MnGeo may point to per-county licensing for some of the 59
  contributing counties.
- The cost is probably $0 with attribution, but "No License Provided" means that cannot be
  assumed.

How to verify:

1. Open the dataset page → "View Full Details" → License section.
2. If still unclear, email MnGeo at `mngeo@state.mn.us` (or use
   https://www.mngeo.state.mn.us/contact.html) with the use case.
3. For the 28 counties that did not opt in, parcel data needs county-by-county licensing.

MN was deferred from the anchor states pending this check
([ADR-018](./adr/0018-minnesota-deferred.md)).

---

### Indiana parcel data has no public owner column

Indiana's statewide parcels (`in_parcels`) publish geometry, parcel IDs, situs address, and county
FIPS code, but **no `owner_name` column at all**. Indiana's public-records framework does not
expose ownership in the statewide GIS layer.

Implication:

- IN cannot produce any owner-driven view (LLC filtering, owner clusters, interestingness
  ranking).
- IN was dropped from the anchor states ([ADR-017](./adr/0017-indiana-dropped.md)).
- It could only return with a paid owner-attribution source (Regrid, county-by-county
  computer-assisted mass appraisal (CAMA) exports, or similar).

---

## Scope limits and unbuilt features

### Paid LLC unmasking and identity resolution are permanent non-goals

When an LLC, trust, or shell entity owns a parcel, the app shows the raw entity string. **Paid
skip-trace and shell-piercing are permanent non-goals** under
[ADR-041](./adr/0041-no-llc-unmasking.md) as narrowed by
[ADR-057](./adr/0057-budget-posture-reframed.md).

The narrowing allowed free public-records officer disclosure: one-click Secretary of State (SoS)
business-entity lookups (LLC managers and officers the entity itself discloses) and UCC-1 filings
(Uniform Commercial Code financing statements). These are not shell-piercing, since they show only
what the entity registered publicly. The lookup links were planned for the lead-detail panel and
never built.

Implication:

- Landowner contact data is the parcel mailing address only. Phone, email, and the beneficial
  owner behind a shell entity are out of scope.
- For LLC-owned parcels (heavily weighted in AR, with about 222K LLCs), SoS records would show
  publicly disclosed officers. Shells that file no officer information leave only the
  registered-agent address.
- Paid skip-trace (Whitepages Pro, Cole, IDI, Pipl) would bring Fair Credit Reporting Act
  (FCRA)-adjacent custody obligations (see [SECURITY.md](./SECURITY.md)).

---

### Rooftop installations are out of Phase 1 scope

Phase 1 covers freestanding towers only ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)).
Fields that only make sense for rooftop and in-building installations were deferred with the
rooftop universe:

- Tenant occupancy in the building
- Building owner mortgage status and liquidity
- Building tenant mix
- Electric meter source (sub-meter versus building power)
- Property manager and management team

Implication: dense urban areas (Miami, Charlotte, Tampa) show no rooftop sites, and the detail
panel has no building-context data.

Rooftop data is mostly paid (CoStar, LoopNet, mortgage feeds).
[ADR-057](./adr/0057-budget-posture-reframed.md) reframed the budget posture to allow paid
sources in a later phase. That phase never happened.

---

### Lease extraction was never built, and its accuracy bar was never tested

[ADR-059](./adr/0059-llm-lease-extraction.md) specified LLM-based structured extraction from
uploaded lease PDFs. Its gate was **at least 85% field accuracy on a 20-lease hand-labelled
gold set**, with the gold set built first and the eval re-run on every prompt or model change
(see [TESTING.md](./TESTING.md)). No lease upload, extraction, or gold-set code was written.

Implication:

- The design called for every extracted field to carry a "needs verification" tag until the
  gold set existed, then per-field confidence tags (verbatim citation versus inferred).

---

### Vendor inference was never built

Slice B planned a `vendor_best_guess` for at least 60% of towers, from the ASR registrant plus a
portfolio roll-up heuristic (Crown, ATC, SBA, and Vertical Bridge acquisition patterns). For
**sold towers**, where the current operator differs from the ASR registrant, the heuristic falls
through. No free dataset records current tower ownership directly. Slice B was not started.

The design called for:

- A prominent confidence tag on every vendor guess.
- A hand-maintained acquisition roll-up table for the top dozen tower companies (Crown Castle USA
  plus the acquired Global Signal, Pinnacle, and Optasite portfolios → "Crown Castle"; American
  Tower plus the Spectrasite legacy → "American Tower"; and so on).
- Memorandum of Lease lessee names from recorded leases, to raise coverage in the most-traded
  counties.

---

### No free lease-rate comparables dataset exists

The comparables feature was planned to bootstrap from Steel-in-the-Air's free county-level
lease-rent benchmarks. Data-source research on 2026-05-26 found that free dataset does not exist.
Steel-in-the-Air's terms also forbid reproducing its data beyond limited attributed quotation, so
it was only ever a reference benchmark for sanity checks. None of its data is in the repo or on
the demo. The next-best free path was rent disclosures in tower real estate investment trust
(REIT) annual reports (10-K filings) and asset-backed securitization filings. The comparables
feature was never built.

The design called for comp values labelled with their basis, `(county average, N=NN)` versus
`(N tower-side leases in 10mi, N=NN)`, and for per-tower comparables to grow from uploaded leases
over time (empty within any radius until about 20 leases land there).

---

### Test coverage

Per [TESTING.md](./TESTING.md), each Phase 1 slice targeted at least 70% line coverage of the code
it added. What shipped:

- Backend HTTP API tests.
- Multi-tenancy isolation tests (`pytest -m tenant_isolation`).
- Preprocess pipeline tests, including DuckDB-versus-pandas equivalence.

What was planned and never built:

- The LLM extraction eval on the 20-lease gold set.
- Data audits as a post-compose CI gate.

---

## Resolved

### Static map data was served without authentication (resolved 2026-06-12, ADR-069)

The static analytical data (parcel parquet, PMTiles, county GeoJSON, `owners_filter.json`,
`owners_index.json`) had no authentication of its own. Anyone who knew a URL could fetch
parcel-owner PII directly and bypass the sign-in gate. Before the fix, an unauthenticated range
request to the hosted owners index returned `206` with content.

The fix: the session JWT rides in the httpOnly `morphy_session` cookie, and Caddy `forward_auth`
calls `GET /api/auth/check` before serving any byte under `/data/processed/*`. Per-request
authority ([ADR-063](./adr/0063-file-credentials-teams-per-request-authority.md)) now covers the
data plane ([ADR-069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)). Two
regression gates: `tests/test_caddy_serving.py` proves unauthenticated → 401 and authenticated
Range → 206 against the real Caddy binary, and `deploy.sh smoke` asserts the unauthenticated
probe returns 401 or 403 after every deploy.

Still true for local dev: `python scripts/serve.py 8765` has no auth. Never expose port 8765 (or a
`/data` proxy to it) beyond localhost.

---

### Large-state composites exceeded the 16 GB dev machine (resolved 2026-06-13, ADR-051)

The Composer's `_load_state_data` originally loaded every county parquet for a state into memory
and `pd.concat`'d them. That measured about 1,710 bytes per parcel, so **about 19.5 GB peak** for
Florida's 11.18M parcels on a 16 GB machine. A local FL compose swapped through the load and then
filled the disk writing the roughly 13 GB `parcels.parquet`.

The fix: chunked compose ([ADR-051](./adr/0051-chunked-compose.md)).
`scripts/preprocess/compose.py` is a per-chunk loop over parcel shards backed by DuckDB
(`iter_state_parcel_shards` plus `duck.session`), so peak memory stays bounded regardless of state
size. `tests/test_duckdb_equivalence.py` pins equivalence with the old pandas path. FL composites
were built and deployed on 2026-06-13.

---

### FL FDOR: 6 of 67 counties dropped on a geometry error (resolved 2026-05-20)

`fdor_nal` originally normalized 63 of 67 counties. Five had unclosed-ring polygons that GEOS
rejected on read, and one (`stjohnscondos_2025`) ships as a geometry-less `.dbf`.

The fix: `on_invalid="fix"` on the layer reads, plus an `is_file()` guard on the `.shp` glob (so a
directory with a `.shp` suffix, as in leon, is not misread). The re-normalize came out clean:
**all 67 counties, 11,184,113 parcels** (68 county parquet files), with 2,976 rows (0.03%) dropped
for unrepairable geometry. `stjohnscondos_2025` is correctly excluded, since a condo supplement with
no `.shp` cannot enter a spatial pipeline.

---

### FL parcel data on disk was the wrong dataset (resolved)

The `fl_fgdl_parcels` source originally pulled Florida's FGDL DSL (Division of State Lands)
parcels, which cover publicly owned state land only. The project needed the Florida Department of
Revenue (FDOR) NAL (Name, Address, Legal) tax roll with private owner attribution. As a result
the FL composite (`composite/12/`) showed almost no owner names and the LLC views were empty.

The fix: the `scripts/fetch/sources/fdor_nal.py` source normalized all 67 counties and 11.18M
parcels (see the entry above), so FL composites carry owner names. FDOR NAL is per county; the
user pulls all 67 counties through the puller's walkthrough
([ADR-047](./adr/0047-fdor-nal-67-counties.md)). The FGDL DSL source was dropped from the active
registry. FL is a committed Phase 1 anchor (AR, MT, FL, WV per
[ADR-060](./adr/0060-wv-committed-anchor.md)).

---

### Five upstream endpoints failed (resolved)

The HUD and USDA endpoints were recorded as dead during the 2026-05-19 triage. A re-check on
2026-05-21 found all three responding normally. The sources had never been pulled (the raw
directories did not exist). HUD Opportunity Zones and Qualified Census Tracts (QCT), served by
ArcGIS FeatureServer pagination, and the USDA Economic Research Service (ERS) direct CSV all fetch
and normalize cleanly and feed the AR and MT distress overlays and county scores. No fetch-code
change was needed.

| Source | Original error (2026-05-19) | Status |
|---|---|---|
| `hud_oz` | HTTP 400 | Resolved 2026-05-21. Endpoint live; pulled and normalized. |
| `hud_qct` | HTTP 400 | Resolved 2026-05-21. Endpoint live; pulled and normalized. |
| `usda_persistent_poverty` | HTTP 404 | Resolved 2026-05-21. ERS county-typology CSV live. |
| `nc_onemap_parcels` | HTTP 500 | Resolved 2026-05-19. Rewired to MapServer pagination ([ADR-048](./adr/0048-nc-onemap-mapserver-pagination.md)). |
| `hifld_towers` | HTTP 400 | Retired. DHS pulled the public layer in 2024; fetcher and normalizer removed 2026-07-03. |

The NC fetch is resolved as a code path, but the pull itself stayed incomplete (see the NC entry
above).

---

### FCC ULS data was downloaded but not normalized (resolved 2026-05-30, Slice A)

About 5 GB of raw FCC ULS data sat on disk across six bands (cellular, market-based, microwave,
ownership, transfers, leasing) plus metadata, unprocessed. Carrier presence per tower, the
biggest single driver of lease value, was missing from the outputs.

The fix: the ULS normalizer (`scripts/preprocess/normalizers/fcc_uls.py`) shipped with Slice A.
It emits `asr_number` with a verified ASR cross-reference plus a spatial-proximity fallback, so
carrier-per-tower is in the composite. See the carrier-identification entry above for the
remaining caveats. Lease-economic modeling (per-tower revenue, sub-lease relationships) was never
built.

---

### The map app could not render all parcels (resolved 2026-05-21, ADR-030)

The all-parcels layer originally could not be shown. The Composer's per-state `parcels.geojson`
(about 3.9 GB for AR) crashed any browser, and
[ADR-052](./adr/0052-no-geojson-threshold.md) stopped emitting it. The rebuilt app
([ADR-030](./adr/0030-map-app-v2-stack.md)) renders **every** parcel (2.1M AR, 920K MT) as
PMTiles vector tiles, built by `scripts/preprocess/tiles.py` and read over HTTP Range, with a
DuckDB-WASM engine for filtering across all parcels. No all-parcels GeoJSON is produced; the
composite still emits the lighter per-state View GeoJSONs for the overlay layers.
