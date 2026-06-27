# LIMITATIONS

**Last updated:** 2026-06-26

Open issues, data caveats, licensing constraints, and known gaps —
things a reader must know before trusting any output of this system
for real-world decisions. Read with [SCOPE.md](./SCOPE.md) (what we're
building) and [SECURITY.md](./SECURITY.md) (PII posture).

Each entry is dated and tagged with a severity:

- 🚫 **BLOCKER** — must be resolved or worked around before commercial use
- ⚠ **CAUTION** — usable now but warrants review before pitch / outreach
- ℹ **NOTE** — known quirk; tracked but not action-blocking

Append new entries at the **top** (newest first). Don't delete entries
when resolved — strike them through and add a "RESOLVED" note so the
audit trail survives.

---

## 🚫 Rooftop installations + their context fields are Phase 2 only

**Added 2026-05-25.**

Phase 1 covers freestanding towers only ([ADR-054](./adr/0054-asset-universe-phase-1-2.md)). Co-founder wishlist items that only make sense for rooftop / in-building installations defer with the rooftop universe:

- Tenant occupancy in the building
- Building owner mortgage current / liquidity
- Building tenant mix
- Electric meter source (sub-meter vs part of building power)
- Property manager + management team

Implication: a co-founder lead in a dense-urban context (Miami, Charlotte, Tampa) will not see rooftop sites in Phase 1 — the lead-detail panel will be empty of building-context data. Pitch this as Phase 2 scope honestly; don't pretend the data is coming in Phase 1.

How to mitigate: Phase 2 rooftop data is mostly paid (CoStar / LoopNet / mortgage feeds). [ADR-057](./adr/0057-budget-posture-reframed.md) reframes the budget posture to allow this.

---

## 🚫 Lease extraction accuracy is unproven until the gold-set is built

**Added 2026-05-25.**

Slice D+E ships LLM-based structured extraction from uploaded lease PDFs ([ADR-059](./adr/0059-llm-lease-extraction.md)). The per-slice gate is **≥ 85% field accuracy on a 20-lease hand-labelled gold-set**. Until that gold-set is built and the eval runs, **field-level accuracy is unknown** and the co-founder must treat extracted values as drafts requiring verification.

Implication:
- Pre-gold-set: every extracted lease field gets a "needs verification" tag in the UI. Co-founder cross-checks against the source PDF every time.
- Post-gold-set: confidence-tagged fields (verbatim citation vs inferred — per ADR-059) calibrate co-founder trust per-field.

How to mitigate:
1. Build the 20-lease gold-set as the **first deliverable in Slice D+E**, before any extraction code is shipped to the co-founder.
2. Re-run the gold-set eval on every prompt or model change. Gating PR check per [TESTING.md §11.3](./TESTING.md).

---

## ⚠ Contact-data path is mailing-only plus free SoS lookups

**Added 2026-05-25.**

Phase 1 surfaces landowner mailing address (from parcel data) plus one-click Secretary of State business-entity lookups + UCC-1 filings in the lead-detail panel ([ADR-057](./adr/0057-budget-posture-reframed.md) narrowing of ADR-041). **The co-founder still does any remaining research per lead** — phone, email, current address for individuals, beneficial owner behind shell entities.

Implication:
- For LLC-owned parcels (heavily weighted in AR — 222K LLCs): SoS surfaces *publicly disclosed* officers; cofounder calls them. For shells that file no officer info publicly, he's stuck with the registered-agent address.
- For individual-owned parcels: mailing address only; phone/email via cofounder's own research.
- Paid skip-trace (Whitepages Pro / Cole / IDI / Pipl) is a Phase 2+ unlock; integrating it brings FCRA-adjacent custody implications (see [SECURITY.md §7](./SECURITY.md)).

How to mitigate:
- The Slice D+E lead-detail panel includes the SoS lookup links + a snail-mail letter template generator to compress per-lead research time.
- Phase 2 evaluation: paid skip-trace integration vs cofounder-side research scaling.

---

## ⚠ Vendor inference is best-guess only (60% coverage bar)

**Added 2026-05-25.**

Slice B's `vendor_best_guess` populates for ≥ 60% of towers via ASR Registrant + portfolio roll-up heuristic (Crown / ATC / SBA / VB acquisition patterns). For **sold towers** where the current operator differs from the ASR Registrant, the heuristic falls through — confidence tag indicates this. No free dataset directly records current tower ownership.

Implication:
- The lead-detail panel shows the Registrant + a vendor guess with a confidence tag. Co-founder uses his own knowledge / web search for low-confidence cases.
- Phase 2 recorded-lease automation (Memorandum of Lease lessee names) would push coverage higher for the highest-traded counties.

How to mitigate:
- Display the confidence tag prominently; never pitch a vendor name as fact when the tag is low.
- Build a hand-maintained acquisition-rollup table for the top dozen tower-cos (Crown's Crown Castle USA + acquired Global Signal, Pinnacle, Optasite portfolios → "Crown Castle"; ATC's American Tower + Spectrasite legacy → "American Tower"; etc.).

---

## ⚠ Carrier identification has spatial-fallback false positives (70% coverage bar)

**Added 2026-05-25.**

Slice A's ULS↔ASR join is hybrid: ASR-number cross-reference where ULS has it (`verified` tag); spatial-proximity fallback elsewhere (`likely` ≤ 100m, `possible` 100–500m). ULS coordinates are unreliable per PROJECT_BRIEF §8A — the spatial-fallback bucket carries some wrong-tower matches.

Implication:
- The lead-detail panel shows each carrier with a confidence tag. Co-founder second-guesses `likely` / `possible` matches before pitching "we can help with your AT&T lease."
- The 70% coverage bar is *at least one carrier identified*; a tower with only spatial-fallback carriers is still in the 70% count.

How to mitigate:
- Tighten spatial-proximity tolerance based on the Slice A kickoff data audit (sample 1000 Cellular `LO` records — if <30% have a populated `asr_number`, tighten the spatial-proximity tolerance).
- Phase 2: recorded leases + carrier-contact verification would resolve ambiguous cases.

---

## ⚠ Comparables cold-start — first 12 months are county-average only

**Added 2026-05-25.**

The comparables feature was originally planned to bootstrap from Steel-in-the-Air's free county-level lease-rent benchmarks. **2026-05-26 data-source research confirms that free dataset doesn't exist** — see [STATUS.md §7](./STATUS.md) for the open Slice D rescope. Per-tower comparables grow from the co-founder's uploaded leases over time — slow either way.

Implication:
- **At Slice D+E launch:** "rent vs county average" works Day 1 for every county; "outliers within X-mile radius" is empty until ~20 leases land in any radius.
- **After ~6 months of cofounder uploads:** smaller radii start populating.
- **After ~12+ months:** the private comp DB starts dominating the public bootstrap.

How to mitigate:
- UI clearly labels comp values as `(county average, N=NN)` vs `(N tower-side leases in 10mi, N=NN)` so the co-founder knows the data quality.
- Phase 2 paid Steel-in-the-Air tier adds finer-than-county granularity Day 1.
- Phase 2 recorded-lease automation pulls Memorandum lessee-side rent data from the rare counties that record it.

---

## ℹ Owner-type classification has a small residual

**Added 2026-05-21.**

`infer_owner_kind` regex-classifies each parcel's `owner_name` into
llc / trust / corporation / partnership / gov / church / school /
individual / unknown. After the 2026-05-21 remediation the `unknown`
rate is **2.1 % (AR) / 4.9 % (MT)** — down from ~51 % / ~35 % — and the
government patterns catch federal, state, county, tribal, and
public-authority owners. Two residuals remain, documented rather than
chased further:

- **The `individual` bucket absorbs some unincorporated businesses** —
  family farms, sole proprietorships, and `&`-joined names with no
  LLC/INC/CORP token read as person-names. This does not affect the
  LLC / trust outreach segments (entity-token matched) — only the
  individual vs. small-business split.
- **A long tail of keyword-less government names** — e.g. bare
  "HIGHWAY" / "HWY" / "COUNTY ROAD" right-of-way fragments — stay
  classified `individual`. They are tiny clusters (≤ 30 parcels) and
  rank far below the top of any outreach view.

Implication:

- The outreach views (`owner_clusters`, `interestingness_top_1000`)
  are clean of government at the top — verified in the audit by
  re-classifying the largest clusters of each state.
- For commercial outreach a human should still confirm the owner type
  on any high-value target.

How to mitigate:

- The classifier is a deterministic regex table in
  `scripts/preprocess/cluster.py` — straightforward to extend when new
  patterns surface.

---

## ~~🚫 Large-state composites exceed the 16 GB dev machine~~ ✅ RESOLVED

**Added 2026-05-20. RESOLVED 2026-06-13 (chunked DuckDB compose, PRD #135).**

Originally the Composer's `_load_state_data` loaded every county parquet
for a state into memory and `pd.concat`'d them — measured at ~1,710
bytes/parcel, so **~19.5 GB peak** for Florida's 11.18M parcels on a
16 GB machine. A local FL compose swapped through the load and then
exhausted the disk writing the ~13 GB `parcels.parquet`.

**Fixed:** chunked compose shipped (approved — ADR-051; implemented in
PRD #135). `scripts/preprocess/compose.py` is now a per-chunk loop over
parcel shards backed by DuckDB (`iter_state_parcel_shards` +
`duck.session`), so peak memory stays bounded regardless of state size;
equivalence with the old pandas path is pinned by
`tests/test_duckdb_equivalence.py`. FL composites were built and
deployed to production 2026-06-13. The peak-RAM / disk wall no longer
holds.

---

## ~~FL FDOR — 6 of 67 counties dropped on a geometry error~~ ✅ RESOLVED

**Added 2026-05-20. RESOLVED 2026-05-20.**

`fdor_nal` originally normalized 63 of 67 counties — five had
unclosed-ring polygons GEOS rejected on read, and one
(`stjohnscondos_2025`) ships as a geometry-less `.dbf`. **Fixed:**
`on_invalid="fix"` on the layer reads plus an `is_file()` guard on the
`.shp` glob (so a `*.shp`-suffixed *directory* — leon — is not
mis-read). Re-normalized clean: **all 67 counties, 11,184,113 parcels**
(68 county parquet files), 2,976 rows (0.03%) dropped for unrepairable
geometry. `stjohnscondos_2025` is correctly excluded — a condo
supplement with no `.shp` cannot enter a spatial pipeline.

---

## 🚫 NC parcel fetch incomplete — stalled on a server 504

**Added 2026-05-20. Updated 2026-05-29:** the NC partial (~8.6 GB) was **deleted 2026-05-20**, and NC was **demoted from the committed anchors on 2026-05-29** — it's now a deferred Phase-1 stretch (re-fetch is not a Slice-F gate). The forensic detail below describes the fetch state *as of 2026-05-20* and is retained for whoever picks NC back up; see [STATUS.md §4.2](./STATUS.md) for the current position.

The NC OneMap MapServer auto-fetch (ADR-048) is **~93% done** —
**1,106 of 1,186** pages (offsets 0–5,525,000, ~8.6 GB) are fetched
and valid in `data/raw/nc_onemap_parcels/.partial/`. The fetch then
stalled: the MapServer returns **HTTP 504 Gateway Time-out** on the
deep-offset query at `resultOffset=5,530,000`. Earlier probes of other
deep offsets succeeded (~35 s each), so this is an intermittent
server-side degradation, not a code bug.

Separate quirk: the puller's `prepare_fresh_partial()` wipes
`.partial/` at the start of every fetch, defeating the NC source's
documented resumability — a puller re-run would restart from page 0.
This session preserved the 1,106 pages by resuming with a headless
driver pointed at the existing `.partial/`.

Implication:

- NC cannot be normalized or composed until the remaining ~80 pages
  land. Since NC was demoted to a deferred Phase-1 stretch (2026-05-29),
  this no longer blocks the committed-anchor set (AR + MT + FL + WV) —
  it is deferred work, not a Slice-F gate.
- NC compose (~5.9M parcels) will also hit the memory wall above.

How to mitigate:

1. Re-run the resumable fetch when the endpoint recovers — it skips
   the 1,106 completed pages.
2. Then normalize + compose NC. Detail in [STATUS.md §4.2](./STATUS.md).
3. Outreach-grade use later needs a quarterly-or-better refresh
   cadence; verify mailing addresses immediately before any physical
   mail.

---

## ~~🚫 Five upstream endpoints currently fail~~ ✅ RESOLVED

**Added 2026-05-19. Updated 2026-05-21 — HUD + USDA resolved.**

The HUD and USDA endpoints were recorded as dead during the 2026-05-19
triage. Re-checked 2026-05-21: **all three respond normally** — the
sources had simply never been pulled (the raw directories did not
exist). HUD OZ + QCT (ArcGIS FeatureServer pagination) and USDA ERS
(direct CSV) all fetch and normalize cleanly, and now feed the AR + MT
distress overlays / county scores. No fetch-code change was needed.

| Source | Original error (2026-05-19) | Status |
|---|---|---|
| ~~`hud_oz`~~ | ~~HTTP 400~~ | ✅ RESOLVED 2026-05-21 — endpoint live; pulled + normalized |
| ~~`hud_qct`~~ | ~~HTTP 400~~ | ✅ RESOLVED 2026-05-21 — endpoint live; pulled + normalized |
| ~~`usda_persistent_poverty`~~ | ~~HTTP 404~~ | ✅ RESOLVED 2026-05-21 — ERS county-typology CSV live |
| ~~`nc_onemap_parcels`~~ | ~~HTTP 500~~ | RESOLVED 2026-05-19 — rewired to MapServer pagination (ADR-048) |
| `hifld_towers` | HTTP 400 | Retired — DHS pulled the public layer in 2024 |

NB: the NC *fetch* is resolved as a code path but the pull itself is
still incomplete — see the NC entry above.

---

## 🚫 HIFLD Cellular Towers layer is permanently retired

**Added 2026-05-19.**

DHS removed the public HIFLD cellular-towers layer in its 2024
infrastructure-data security review. The REST endpoint is a zombie
(returns errors); no replacement is published for general use.

Implication:

- FCC ASR is the sole tower-locations source.
- ASR's ~200-ft height threshold means small / rooftop towers are
  invisible. Significant for dense urban analysis; minor for the
  rural-focused thesis we're pitching.
- Vetted users may apply for HIFLD access via DHS's GII portal; not
  pursued here.

How to mitigate:

- Document the gap as a known limitation in PROJECT_BRIEF.md.
- Treat ASR + FAA OEAAA as the joint tower-location truth.

---

## ~~🚫 FL parcel data on disk is the wrong dataset~~ ✅ RESOLVED

**Added 2026-05-19. RESOLVED — `fdor_nal` shipped + composed.**

Originally the `fl_fgdl_parcels` source pulled Florida's FGDL **DSL**
(Department of State Lands) parcels — publicly-owned state land only —
**not** the FDOR NAL (Name, Address, Legal) tax-roll dataset with
private owner attribution that we actually want, so the FL composite
(`composite/12/`) showed ~0 owner names and the LLC views were empty.

**Fixed:** the new `scripts/fetch/sources/fdor_nal.py` source shipped
and normalized all 67 counties / 11.18M parcels (see the RESOLVED FDOR
entry above), so FL composites now carry owner names. FDOR NAL is
per-county; the user pulls all 67 counties via the puller's walkthrough
(ADR-047), and the FGDL DSL source is dropped from the active registry.
FL is a **committed Phase-1 anchor** (AR + MT + FL + WV per
[ADR-060](./adr/0060-wv-committed-anchor.md)), not a stretch.

---

## 🚫 Indiana parcel data has no public owner column

**Added 2026-05-19.**

Indiana's statewide parcels (`in_parcels`) publish geometry, parcel
IDs, situs address, and county FIPS — but **no `owner_name` column at
all**. Indiana's public-records framework does not expose ownership
at the statewide GIS layer.

Implication:

- IN cannot generate any owner-driven view (LLC outreach, owner
  clusters, interestingness ranking).
- Dropped from the anchor-state set for this pitch cut (ADR-017).
- Will only return to anchor status with a paid owner-attribution
  source (Regrid, county-by-county CAMA exports, or similar).

---

## ⚠ Parcel-owner names + addresses are PII

**Added 2026-05-19.**

While each individual field (owner name, mailing address, parcel
geometry) is public-record, **the combination** meets most PII
definitions. Treat composite parcel outputs accordingly.

Implication:

- **Do not host composite outputs publicly** without access controls.
- **`data/` is git-ignored**; never commit raw or composite outputs to
  the repo.
- **Demo screenshots** that show real owner names may need redaction
  depending on audience (a friendly co-founder vs. a stage demo).
- **The map app has no access controls** — do not host it publicly
  without authentication (see [SECURITY.md](./SECURITY.md)).

How to mitigate:

- GitHub repo is private (per ADR-040).
- `docs/SECURITY.md` lists the PII posture as authoritative.
- Pitch-asset screenshots use AR (a high-LLC-ratio state) so that LLC
  names dominate the visible labels — those are entities, not
  individuals.

---

## ⚠ ASR tower coordinates have known drift

**Added 2026-05-19. (Carried forward from PROJECT_BRIEF §7.)**

Older FCC ASR registrations can have coordinates that drift from true
location by tens to hundreds of meters. Visual inspection against
satellite imagery confirms ~5–15 % of towers in any given county miss
their hosting parcel.

Implication:

- The tower→parcel spatial join uses strict `within` (no buffered
  match), so we **under-count** matches rather than guess wrong.
- A `parcel_id IS NULL` tower might still be on a parcel — just one
  the strict join missed.
- For real outreach we'd add a buffered-fallback match with a
  manual-review step.

How to mitigate:

- LIMITATIONS surfaced in detail panels (when a tower has no parcel
  match, the panel says "No matching parcel — coordinates may have
  drift; verify against imagery").
- Don't cite the strict join number as "X towers on private land" in
  the pitch; cite it as "X towers we can confidently place on a
  specific parcel."

---

## ⚠ HUD OZ data is the original "OZ 1.0" designations

**Added 2026-05-19. (Carried forward from PROJECT_BRIEF §4C / §7.)**

The OZ layer bundled here is the OZ 1.0 designations from the 2017
Tax Cuts and Jobs Act, valid through 2028. **"OZ 2.0"
redesignations** under the One Big Beautiful Bill Act are being made
by governors during 2026 — the map will change.

Implication:

- Tracts flagged `in_oz = true` today may not be OZ tracts post-2026.
- Pitch narrative should mention the redesignation cycle as a known
  evolution, not as a gotcha.

How to mitigate:

- Refresh OZ data after each governor's redesignation announcement.
- Update the catalog `generated_at` so consumers can tell which
  vintage they're seeing.

---

## ~~⚠ FCC ULS data downloaded but not yet normalized~~ ✅ RESOLVED

**Added 2026-05-19. RESOLVED 2026-05-30 (Slice A).**

Originally ~5 GB of raw FCC ULS data sat on disk across six bands
(cellular, market-based, microwave, ownership, transfers, leasing)
plus metadata, unprocessed — so carrier presence per tower, the single
biggest driver of lease value, was not in our outputs.

**Fixed:** the ULS normalizer (`scripts/preprocess/normalizers/fcc_uls.py`)
shipped as part of Slice A (landed 2026-05-30). It emits `asr_number`
with a verified ASR cross-reference plus a spatial-proximity fallback,
so carrier-per-tower is now in the composite — see the *"Carrier
identification has spatial-fallback false positives"* entry above for
the live caveats. Lease-economic modeling (per-tower revenue, sub-lease
relationships) remains future work.

---

## ⚠ Data pipeline is batch-only

**Added 2026-05-19. Updated 2026-06-13.**

The data pipeline is batch-only. Re-running `python scripts/preprocess.py` overwrites all outputs for any state it touches. There is no streaming ingest, no cron-driven refresh.

**The hosted-private backend is live** ([ADR-055](./adr/0055-hosted-private-backend.md)) — username/password auth ([ADR-062](./adr/0062-username-password-replaces-magic-link.md)/[063](./adr/0063-file-credentials-teams-per-request-authority.md)/[069](./adr/0069-credentials-in-db-cookie-sessions-gated-data-plane.md)), teams-as-tenants on a tenant-shaped schema (2–5 users Phase 1). Lead + task state and the activity log live there (lease docs are the next unbuilt slice). The static-site model is preserved for read-only analytical layers (parquet, PMTiles, GeoJSON), now edge-gated behind auth.

Implication:
- The data pipeline still requires the dev to run the puller manually (Phase 1).
- The live D+E backend gives the co-founder a real workflow surface (auth, persistent lead state, and — once the rest of D+E lands — lease uploads + CSV exports) rather than ad-hoc spreadsheets.
- Self-serve refresh from the product is a Phase 2 candidate (wire the puller into the backend).

How to mitigate:
- Phase 1: dev triggers refreshes; cofounder works in the backend-powered triage UI.
- Phase 2: self-serve refresh; mass email; multi-tenant if Phase 3 sells the tool.

---

## ⚠ No automated audit trail

**Added 2026-05-19.**

`data/raw/<source_id>/current/` keeps the latest version only (ADR-004).
The fetch log (`data/fetch.log`) records pull events but doesn't
preserve historical raw files. We cannot fully answer "what did
parcels look like 6 months ago?"

Implication:

- Acceptable for a feasibility prototype.
- For real outreach we'd need a snapshot-retention policy or a paid
  provider with API-versioned datasets.

How to mitigate:

- Composite outputs carry `sources_used_versions` in
  `catalog.json` after Section 5.5 — we can at least answer "what
  raw versions did this composite come from?"
- Major refreshes get a commit with the source list + dates.

---

## ⚠ Paid LLC unmasking + identity resolution remain permanent non-goals (ADR-041 narrowed)

**Added 2026-05-19. Updated 2026-05-25.**

When an LLC, trust, or shell entity owns a parcel, we display the raw entity string. **Paid skip-trace and shell-piercing remain permanent non-goals** per ADR-041 as narrowed by [ADR-057](./adr/0057-budget-posture-reframed.md).

**What's now in scope for Phase 1** (the narrowing): free public-records officer disclosure. The Slice D+E lead-detail panel surfaces one-click Secretary of State business-entity lookups (LLC managers / officers are publicly disclosed by the entity itself) and UCC-1 filings. These are *not* shell-piercing — they show what the entity itself has publicly registered.

Implication:
- For LLCs that publicly disclose officers via SoS: the cofounder gets the officer names + can call them.
- For shells filing no officer info publicly: the cofounder still hits the registered-agent address. Beneficial-owner resolution stays out of scope.

See also the *"Contact-data path is mailing-only plus free SoS lookups"* limitation above.

---

## ✓ Map app rendering all parcels — RESOLVED (2026-05-21)

**Resolved by the map app rehaul (ADR-030).**

Originally the all-parcels layer could not be shown: the Composer's
per-state `parcels.geojson` (AR's ~3.9 GB) crashed any browser, and
ADR-052 stopped emitting it. The rebuilt app renders **every** parcel
(2.1 M AR / 920 K MT) as PMTiles vector tiles — built by
`scripts/preprocess/tiles.py`, read over HTTP Range — with a DuckDB-WASM
engine for filtering across all parcels. No all-parcels GeoJSON is
produced; the composite still emits the lighter per-state View GeoJSONs
for the overlay layers.

---

## ℹ ARC distress is hardcoded to FY 2026

**Added 2026-05-19.**

The `arc_distressed` source fetches the current fiscal-year
distress-classification list. The annual rotation may reclassify
counties between tiers.

Implication:

- Pitch numbers cite the FY at fetch time; refresh annually.
- If a county changes tier mid-cycle, note in the relevant commit.

---

## ⚠ MN "Plan Parcels Open" — license unspecified

**Added 2026-05-18.** (Carried over from prior version of this doc.)

The Minnesota statewide parcels layer (`mn_parcels` →
`https://gis.data.mn.gov/datasets/minnesota::plan-parcels-open-2`) is
marked **"No License Provided — Request permission to use"** on the
MnGeo dataset page, despite the "Open" naming.

Implication:

- Fine for internal evaluation only.
- Before using MN parcel data in any **product, outreach, sales
  material, or paid deliverable** — read MnGeo's actual terms and, if
  ambiguous, email them for explicit written permission. They may
  direct you to per-county licensing for some of the 59 contributing
  counties.
- Cost: probably $0 with attribution, but the explicit "No License
  Provided" note means we cannot assume that.

How to verify before commercialization:

1. Open the dataset page → "View Full Details" → License section.
2. If still unclear, email MnGeo at `mngeo@state.mn.us` (or via
   https://www.mngeo.state.mn.us/contact.html) with the use case.
3. For any of the 28 non-opted-in counties, parcel data needs to be
   licensed county-by-county.

Current status: **MN deferred** from anchor states pending this
verification (ADR-018).

---

## ✅ Static map data is served without authentication — RESOLVED in production (PRD #130, ADR-069)

**Added 2026-06-02. Resolved 2026-06-12.**

The exposure: the static analytical data (parcel parquet, PMTiles, county GeoJSON, `owners_filter.json`, `owners_index.json`) was served with no authentication of its own — anyone who knew a URL could fetch parcel-owner PII directly, bypassing the sign-in gate. Verified live before the fix: an unauthenticated range request to the production owners index returned `206` with content.

**The fix (shipped + verified on prod):** the session JWT rides in an httpOnly cookie, and Caddy `forward_auth` asks `GET /api/auth/check` before serving any byte under `/data/processed/*` — per-request authority (ADR-063) now covers the data plane. Regression-gated twice: `tests/test_caddy_serving.py` proves unauth → 401 / authed Range → 206 against the real binary, and `deploy.sh smoke` asserts the unauthenticated probe returns 401/403 after every deploy.

**Still true for local dev:** `python scripts/serve.py 8765` has no auth — never expose port 8765 (or a `/data` proxy to it) beyond localhost.

---

## ℹ Test coverage is per-slice (Phase 1)

**Added 2026-05-19. Updated 2026-05-25.**

Original Section 6 of the legacy work plan never shipped before the 2026-05-25 pivot. **Per-slice test-coverage bar** ([SCOPE.md §4](./SCOPE.md), [TESTING.md §11.5](./TESTING.md)): ≥ 70% line coverage of new code added in each Phase 1 slice. Plus:

- Backend HTTP API tests (Slice D+E).
- Multi-tenancy isolation tests from Day 1 (Slice D+E).
- LLM extraction eval as a gating CI check on a 20-lease gold-set (Slice D+E).
- Data audits as CI (post-compose gate).

Implication: as of 2026-05-25, much of this is still pre-implementation. Pre-Slice-1 work has no tests; Slice F starts shipping them.

---

## Template for future entries

```
## [emoji] [short title]

**Added YYYY-MM-DD.**

[The constraint in one paragraph.]

Implication:
- [what's safe now]
- [what becomes risky at commercialization / pitch]
- [cost / mitigation]

How to mitigate:
1. [concrete step]
2. [concrete step]
```
