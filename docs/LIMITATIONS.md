# LIMITATIONS

**Last updated:** 2026-05-19

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

## 🚫 Parcel data staleness — NC at 11 months old

**Added 2026-05-19.**

The Graham County / NC parcel data on disk was last refreshed
**2025-07-15** — nearly a year old as of this writing. Ownership /
mailing address / valuation changes from the past 11 months are not
reflected. Stale parcel data leads to false-positive outreach (owner
sold; new owner unaware of context).

Implication:

- Pre-pitch: refresh NC before any partner walkthrough.
- Outreach: minimum quarterly refresh for any state used in active
  outreach, ideally monthly.
- Address-deliverability: independently verify the mailing address
  immediately before any physical mail.

How to mitigate:

1. Pull fresh NC OneMap data via the puller (Section 4.4 of the work
   plan).
2. After every NC refresh, log a CHANGELOG entry noting the new
   `local_version` and re-run NC's compose.
3. Long-term: subscribe to a paid provider (Regrid, ATTOM) for
   verified address-current data when budget unlocks.

---

## 🚫 Five upstream endpoints currently fail

**Added 2026-05-19.**

The following sources return HTTP errors as of 2026-05-19:

| Source | Error | Action plan |
|---|---|---|
| `hud_oz` | HTTP 400 from ArcGIS service | Switch to HUD's static OZ shapefile (Section 4.1) |
| `hud_qct` | HTTP 400 from ArcGIS service | Static shapefile fallback (Section 4.1) |
| `usda_persistent_poverty` | HTTP 404 (URL migrated) | Find current ERS path; static fallback (Section 4.1) |
| `nc_onemap_parcels` | HTTP 500 | Retry; MANUAL_ONLY walkthrough if persistent (Section 4.1) |
| `hifld_towers` | HTTP 400 | Retire (Section 4.1); DHS pulled the public layer in 2024 |

Implication:

- These four (excluding HIFLD) are needed for the v1 pitch.
- All resolution paths are documented; Section 4.1 of the work plan
  executes them.

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

- Document the gap as a known limitation in INVESTOR_BRIEF.md.
- Treat ASR + FAA OEAAA as the joint tower-location truth.

---

## 🚫 FL parcel data on disk is the wrong dataset

**Added 2026-05-19.**

The current `fl_fgdl_parcels` source pulls Florida's FGDL **DSL**
(Department of State Lands) parcels — publicly-owned state land only.
It is **not** the FDOR NAL (Name, Address, Legal) tax-roll dataset
with private owner attribution that we actually want.

Implication:

- Current FL composite (`composite/12/`) shows ~0 owner names; LLC
  views are empty; demo scenarios don't land.
- FL is a stretch anchor state for the pitch — included only if we
  pull FDOR NAL during Section 4.2 (new `fdor_nal` source).

How to mitigate:

- New source `scripts/fetch/sources/fdor_nal.py` planned for Section 4.2.
- FDOR NAL is per-county; user pulls 5–10 representative counties for
  the pitch.
- The FGDL DSL source is dropped from the active registry.

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
- **Future Map app rehaul** must include access controls before any
  hosted deployment (deferred — see [SECURITY.md](./SECURITY.md)).

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

## ⚠ FCC ULS data downloaded but not yet normalized

**Added 2026-05-19.**

~5 GB of raw FCC ULS data is on disk across six bands (cellular,
market-based, microwave, ownership, transfers, leasing) plus
metadata. None of it is currently processed into canonical types.
Carrier presence per tower — single biggest driver of lease value —
is therefore not in our outputs.

Implication:

- Pitch narrative can mention carrier/tenant data as a "we have the
  raw, normalize is a v2 build."
- Lease-economic modeling (per-tower revenue, sub-lease
  relationships) is unavailable until ULS normalizers ship.

How to mitigate:

- Documented as a deferred workstream in ROADMAP.md.
- Raw data on disk stays — when ULS normalizers land, they read from
  current files, no re-fetch needed.

---

## ⚠ No incremental updates; single-machine deployment

**Added 2026-05-19.**

The pipeline is batch-only. Re-running `python scripts/preprocess.py`
overwrites all outputs for any state it touches. There is no:

- Streaming ingest of new ASR / FAA OEAAA records as they land.
- Cron-driven scheduled refresh.
- Multi-machine / cloud-hosted deployment.
- Multi-user access controls.

Implication:

- Solo-dev workflow only.
- Data "as of" any pitch is the last manual refresh date.
- Sharing outputs requires zipping `composite/<fips>/` and handing
  it over — no shared URL.

How to mitigate:

- Pitch context: explicitly say "this is a local prototype; production
  deployment is post-funding."
- For pre-pitch, run the freshness checklist in
  [DATA_FRESHNESS.md §5](./DATA_FRESHNESS.md).

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
- Major refreshes get a CHANGELOG entry.

---

## ⚠ No LLC unmasking (permanent non-goal)

**Added 2026-05-19. (Carried forward from PROJECT_BRIEF §7.)**

When an LLC, trust, or shell entity owns a parcel, we display the raw
entity string. We do not attempt to resolve the human(s) behind it.

Implication:

- Outreach targeting an LLC reaches the registered agent, not
  necessarily the beneficial owner.
- For high-value parcels, the user would manually look up SoS records
  → this is a future enrichment, not this codebase's job.

Permanent — see ADR-041.

---

## ⚠ Map app cannot load huge parcel layers

**Added 2026-05-19.**

The current Leaflet app loads parcel layers via `fetch()` + JSON parse.
For AR (3.6 GB simplified GeoJSON) or IN (5.6 GB) this will crash any
browser. FL at 491 MB freezes for several seconds.

Implication:

- Current app reliably handles only small-parcel states.
- AR demo currently works because the GeoJSON is gated behind the
  state selector and only fires after click; even so, performance is
  poor.

How to mitigate:

- Minimal patches in Section 8 of the work plan add a state-selector
  guard.
- Full fix in [MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md) — MapLibre +
  PMTiles vector tiles handle 3.7M+ parcels at 60fps. Deferred.

---

## ℹ ARC distress is hardcoded to FY 2026

**Added 2026-05-19.**

The `arc_distressed` source fetches the current fiscal-year
distress-classification list. The annual rotation may reclassify
counties between tiers.

Implication:

- Pitch numbers cite the FY at fetch time; refresh annually.
- If a county changes tier mid-pitch-cycle, document in CHANGELOG.

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

## ℹ No tests today

**Added 2026-05-19.**

The repo currently has zero automated tests, zero CI, no pre-commit.
Section 6 of the work plan adds pytest + GitHub Actions.

Implication:

- Any change has manual-only verification.
- Section 6 adds ≥ 30 tests with ≥ 70 % coverage of
  `scripts/preprocess/`.

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
