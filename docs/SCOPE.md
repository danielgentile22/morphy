# SCOPE — v1 Pitch / Demo Cut

**Last updated:** 2026-05-19
**Status:** Active — execution in progress
**Owner of this doc:** Whoever is currently driving the project (single dev today)

This document is the **single source of truth for "what we are building
right now."** Anything not listed here is out of scope for the current
push. Future scope lives in [ROADMAP.md](./ROADMAP.md).

---

## 1. What this version is

A **pitch-quality demo cut** of the pilot project — the artifact a
co-founder, investor, or strategic partner can be walked through in 10
minutes and that defensibly answers:

- Can we identify cell-tower ground-lease renegotiation opportunities at
  scale, using only free public data?
- What does that look like across multiple states?
- What's the data quality and what are the known gaps?

It is **not** a production tool, not a customer-facing app, not a
commercial outreach system. See [LIMITATIONS.md](./LIMITATIONS.md) for
the full caveat list.

---

## 2. Anchor geographies (locked)

| State | FIPS | Role | Why |
|---|---|---|---|
| **Arkansas** | 05 | Primary demo state | 2.1M parcels, full owner data, 222K LLCs, working end-to-end |
| **North Carolina** | 37 | Original pilot context (Graham County) | Where the thesis was first proven; needs refresh |
| **Montana** | 30 | Western proof point | Free cadastral with owner data; rural-tower representative |
| **Utah** | 49 | Small, clean dataset | Smaller state lets us validate the whole stack quickly |
| **Florida** | 12 | Stretch target | Only if FDOR NAL (per-county tax roll) is reachable |

**Dropped from this cut** (will revisit later — see ROADMAP):

- **Indiana (FIPS 18)** — Indiana's public parcel data has no
  `owner_name` column at all. Cannot generate the LLC-owner / cluster
  scenarios that anchor the demo. Mothball until a paid source unlocks
  owners.
- **Minnesota (FIPS 27)** — MN Geo's parcel feed is published as "Plan
  Parcels Open" but the license metadata reads "No License Provided."
  Defer until MnGeo confirms commercial-use status (see SECURITY.md).
- **Current FL FGDL parcels** — turned out to be DSL state-land parcels
  (publicly owned), not the FDOR NAL tax roll we actually want. Drop
  this raw source from the active registry; replace with `fdor_nal`
  if we pursue FL.

---

## 3. In-scope data sources

For each anchor state, we ingest, normalize, and join:

### Tower-side

- **FCC ASR** — federal Antenna Structure Registration (all towers
  ≥ 200 ft or near airports). Authoritative point locations.
- **FAA OEAAA** — proposed and recently-built tall structures. Forward-
  looking pipeline.

### Landowner-side

- **State parcel layers** for each anchor state (NC OneMap, AR Geographic
  Information Office, MT Cadastral, UT Parcel Project, and — if pursued —
  FL FDOR NAL per-county downloads).

### Distress overlays

- **HUD Opportunity Zones** (OZ 1.0 designations; OZ 2.0 redesignations
  rolling out 2026–2028).
- **HUD Qualified Census Tracts (QCT)**.
- **ARC distressed counties** (Appalachian Regional Commission economic
  status tiers — only matters where Appalachia intersects).
- **USDA persistent poverty** counties.

### Solar (secondary; supports cross-asset narrative)

- **EIA Form 860 + 860M** — utility-scale plant locations + monthly
  status updates.
- **USPVDB** — USGS US Photovoltaic Database (array polygons).

---

## 4. Out-of-scope sources (for this cut)

| Source(s) | Status | Why deferred |
|---|---|---|
| `fcc_uls_*` (6 ULS bands + meta) | Deferred | ~5 GB raw on disk; complex schema; carrier-tenant data is v2, not core to landowner-side pitch |
| `state_billboards` (FDOT, NCDOT, TXDOT) | Deferred | Not core to cell-tower ground-lease thesis; revisit when adding billboards as an asset class |
| `lbnl_tts` (rooftop solar) | Deferred | Superseded by USPVDB + EIA 860 for the cross-asset narrative we need |
| `hifld_towers` | **Retired** | DHS retired the public layer in 2024; no replacement |
| `regrid_parcels` | **Out (paid)** | Free-only budget; stub stays in registry, not pursued |
| Tax-delinquency lists, foreclosure data, county recorder filings, SoS UCC, REIT 10-Ks | Future | Discussed in PROJECT_BRIEF §8; explicit v2+ enrichments |
| LLC unmasking (resolving the human behind an entity) | **Permanent non-goal** | Sensitive, expensive, separate product |

---

## 5. Demo scenarios (the pitch walks through these)

1. **LLC outreach in distressed Arkansas counties.** Open AR composite,
   filter `owner_kind=LLC` + `in_distress`, click top-interestingness
   parcel, show owner + mailing + tower(s) on parcel. Numbers come from
   `views/llc_owned_parcels_with_infra.parquet` and
   `views/distressed_parcels_hosting_infra.parquet`.
2. **Owner cluster analysis.** Pick one of the largest landowners in
   the state (size from `owner_cluster_size`); show all parcels they
   own, how many host infrastructure, the total assessed value.
   Numbers come from `views/owner_clusters.parquet` and
   `views/interestingness_top_1000.parquet`.
3. **Cross-state coverage comparison.** Side-by-side totals + top
   opportunities for the anchor states (AR, NC, MT, UT, FL-if-available).
   Numbers come from each state's `summary.json`.

Every number on the screen during these scenarios must be traceable to
a specific parquet file + query. See [NUMBERS.md](./NUMBERS.md) (filled
in during Section 7 of the work plan).

---

## 6. Hard non-goals (do not scope-creep here)

These are explicit non-goals for this cut. Carrying forward from
PROJECT_BRIEF §2 and refined for the multi-state context:

- **No authentication / backend / database.** Static parquet + GeoJSON
  files on the local filesystem.
- **No production deployment.** Runs locally; the puller is a desktop
  app and the map is `python -m http.server`.
- **No carrier/tenant economics modeling.** ULS data is on disk but not
  yet normalized; lease-value modeling lives further downstream.
- **No outreach / CRM / contact management.** We surface owners; we
  don't contact them. PII handling rules in [SECURITY.md](./SECURITY.md).
- **No LLC unmasking.** Display the raw entity string; do not attempt
  to resolve the human behind it.
- **No nationwide coverage.** 3–5 anchor states; nationwide requires a
  paid parcel source (Regrid), which is out of budget for this cut.
- **No map app rehaul during this cut.** The full Svelte/PMTiles
  rebuild is scoped in [MAP_APP_REHAUL.md](./MAP_APP_REHAUL.md) and
  marked DEFERRED. Only minimal patches to the current Leaflet app
  during Section 8 of the work plan.

---

## 7. What "done" looks like for this cut

The end-state check that closes Sections 1–8 of the work plan:

- [ ] Every anchor state composes cleanly: 0 warnings, 9/9 joins, ≥ 6
      views (≥ 8 for the states with owner data).
- [ ] Every figure cited in the pitch traces to a specific parquet
      file + query, captured in NUMBERS.md.
- [ ] 3 demo scenarios captured as screenshots / GIFs under
      `docs/pitch-assets/`.
- [ ] Tests pass locally (≥ 30 tests, ≥ 70 % coverage of
      `scripts/preprocess/`) and CI is green on GitHub.
- [ ] Docs reorganized into `docs/`; no stale references at repo root.
- [ ] Puller has: freshness column, "what needs my attention" panel,
      MANUAL-walkthrough modal for each MANUAL_ONLY anchor source.
- [ ] A non-technical partner can read the docs and answer the five
      questions in [GOALS.md §3](./GOALS.md) in 15 minutes.

---

## 8. Where to look next

- **Why we're doing this** → [GOALS.md](./GOALS.md)
- **What state we're in today** → [STATUS.md](./STATUS.md)
- **Past + future** → [ROADMAP.md](./ROADMAP.md)
- **Locked-in design decisions** → [DECISIONS.md](./DECISIONS.md)
- **How the system is put together** → [ARCHITECTURE.md](./ARCHITECTURE.md)
- **Per-source detail** → [DATA_SOURCES.md](./DATA_SOURCES.md)
- **Glossary of terms** → [GLOSSARY.md](./GLOSSARY.md)
- **Caveats and pre-commercial blockers** → [LIMITATIONS.md](./LIMITATIONS.md)
- **PII / data-handling posture** → [SECURITY.md](./SECURITY.md)
