# PROJECT BRIEF — Infrastructure Lease-Optimization Prototype

**Last updated:** 2026-05-19 (preamble added; Sections 1–4 + 7–10 remain
authoritative for business context; Sections 5 + 6 describe the
original v1 Graham-County prototype and are now historical).

> **Read this file for the *business case + market context*** — what
> we are building, why, and the strategic data sources we tap.
>
> For the **current technical state** see:
>
> - [docs/SCOPE.md](docs/SCOPE.md) — what's in scope right now (3–5
>   anchor states, free-only budget, pitch cut)
> - [docs/STATUS.md](docs/STATUS.md) — what works today
> - [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — how the system fits
>   together (replaces the Sections 5 + 6 description below)
>
> The v1 Graham-County one-shot referenced in Sections 5 + 6 has been
> superseded by the v3 framework. The business case (Sections 1–4,
> 7–10) remains authoritative.

---

## 1. Business Context (the "why")

We are evaluating the feasibility of a business that helps **landowners
renegotiate or optimize the contracts for infrastructure assets sitting on
their property** — primarily **cell towers**, secondarily **billboards** and
**solar installations**.

The core market inefficiency we are exploiting:

- A cell tower (or billboard, or solar farm) sits on a piece of land owned by
  someone — often an individual, a small LLC, a farmer, a church, or a local
  government.
- That landowner receives a **ground lease** payment from a tower company
  (Crown Castle, American Tower, SBA, Vertical Bridge, etc.).
- These leases are frequently **undervalued, poorly understood by the
  landowner, and aggressively renegotiated downward** by agents working for the
  tower companies (e.g. MD7, Tarpon, Black Dot).
- Large lease-buyout firms (AP Wireless, Unison, Landmark) make unsolicited
  lump-sum offers that are often well below true economic value.
- **Distressed landowners** (low income, tax-delinquent, in economically
  distressed regions) are the most likely to accept a bad deal and the most
  materially helped by a good one.

Our business sits on the **landowner's side** — identifying these landowners,
understanding their lease, and helping them get a better contract or buyout.

**The fundamental data problem:** No single public dataset tells you "this
tower is on this person's land and they are paid $X." That linkage must be
*constructed* by joining:

1. **Where the towers are** (FCC ASR — federal, public, free)
2. **Who owns the land underneath** (county parcel data — local, public, free)
3. **Which areas are economically distressed** (federal designations — public,
   free)

This prototype demonstrates that this linkage is technically achievable and
visually compelling.

---

## 2. Prototype Goals (the "what")

This is a **feasibility prototype**, not a production system. Its job is to
*demonstrate the concept* convincingly. Success criteria:

1. **Ingest** the raw FCC, parcel, and Opportunity Zone files (described in
   Section 4) and produce clean, joined GeoJSON.
2. **Spatially join** towers to the parcels they sit on, so each tower is
   linked to a landowner name and mailing address.
3. **Flag** which parcels/towers fall inside an Opportunity Zone (economic
   distress proxy).
4. **Visualize** all of this on an interactive map where a user can:
   - See every registered tower in the county
   - See every parcel boundary
   - See Opportunity Zone overlays
   - Click a tower → see its details + the landowner it sits on
   - Click a parcel → see ownership, value, distress status, whether it hosts
     a tower
   - Filter to "only parcels with towers" and "only parcels in Opportunity
     Zones"
5. **Be runnable** with minimal setup (a Python preprocessing script + a static
   web app served locally).

**Explicit non-goals for this prototype:**

- No database (flat GeoJSON files are fine at this scale)
- No authentication, no backend server, no deployment
- No carrier/tenant data (ULS) — that is a v2 enhancement
- No lease economics modeling — that is a later business-logic layer
- No outreach/CRM functionality
- No nationwide scale — one small county only

---

## 3. Pilot Geography: Graham County, North Carolina

**Why Graham County:**

- **Smallest-friction starting point.** One of the least-populous counties in
  NC (~8,000 people, ~290 sq mi), so all data files are tiny and the entire
  county can be reasoned about end-to-end.
- **Free, clean, standardized parcel data.** North Carolina's NC OneMap
  program provides per-county parcel downloads already mapped to a statewide
  content standard. Graham County's parcels were standardized on **2025-07-15**
  (recent enough to be reliable).
- **Economically distressed.** Graham County is classified as **ARC
  (Appalachian Regional Commission) distressed** — the most severe tier of
  Appalachian economic distress — and contains Opportunity Zone tracts. This
  makes it representative of the actual target market.
- **Rural tower pattern.** Tower coverage follows the US-129 corridor (the
  "Tail of the Dragon" tourism route) and other primary routes — a clean,
  comprehensible rural deployment pattern rather than a dense urban tangle.

**Key geographic constants** (use these in code):

| Constant | Value |
|---|---|
| State | North Carolina |
| County | Graham |
| State FIPS | `37` |
| County FIPS | `075` |
| Full county FIPS (GEOID) | `37075` |
| Approx. bounding box — North | `35.51` |
| Approx. bounding box — South | `35.10` |
| Approx. bounding box — East | `-83.55` |
| Approx. bounding box — West | `-83.98` |
| ARC status (hardcode for v1) | `Distressed` |

> The bounding box is approximate and intended for (a) the default map view
> and (b) a coarse pre-filter of the national FCC file. The authoritative
> spatial filter for parcels is the parcel layer's own county boundary, not
> the bounding box.

---

## 4. Data We Have Downloaded (the "inputs")

All raw data lives under `data/raw/`. The expected layout:

```
data/
├── raw/
│   ├── asr/                  FCC Antenna Structure Registration
│   │   ├── (Registrations zip contents — pipe-delimited .dat files)
│   │   ├── (FAA Determinations zip contents)
│   │   ├── asr_sql_table_definitions_3.txt   (schema — REQUIRED)
│   │   └── (ASR Database Field Definitions .xls — schema reference)
│   ├── parcels/              Graham County, NC parcels (from NC OneMap)
│   │   └── (shapefile set OR .gdb folder OR .gpkg)
│   └── opportunity-zones/    HUD Opportunity Zones (national)
│       └── (GeoJSON or shapefile — TO BE DOWNLOADED)
└── processed/                Pipeline output goes here (GeoJSON)
```

### 4A. FCC Antenna Structure Registration (ASR) — TOWERS

**Source:** FCC Public Access Files,
`https://www.fcc.gov/wireless/data/public-access-files-database-downloads`,
"Weekly Databases" → "Antenna Structure Registration" section.

**Files downloaded:**

| File | Approx. size | What it is |
|---|---|---|
| **Registrations** | ~35 MB | The core tower records: ASR number, owner reference, coordinates, height, structure type, status. **This is the primary input.** |
| **FAA Determinations** | ~52 MB | FAA approval records cross-referenced to structures. Secondary; useful for validation and forward pipeline. |

We deliberately did **not** download "Applications" (~196 MB, pending/historical
applications — not needed for prototype) or the "Ownership" filings (FCC license
control disclosures — *not* land ownership; irrelevant here).

**Critical schema notes for parsing ASR:**

- The files are **pipe-delimited (`|`) plain text** with the extension `.dat`.
- **There is no header row.** Column order and meaning come *only* from the
  schema definition files (`asr_sql_table_definitions_3.txt` and the
  `.xls` field definitions). **Read the schema file before parsing — do not
  assume column positions.**
- The data is split across multiple related tables, each a separate `.dat`
  file, joined on the registration number. The most relevant tables:
  - **`RA.dat`** — Registration / antenna structure records. Contains the ASR
    Registration Number, structure coordinates, overall height, structure
    type, status code, and date fields.
  - **`CO.dat`** — Coordinate / additional structure info (varies by FCC
    schema version — verify against the schema file).
  - **`EN.dat`** — Entity records: the registrant/owner name, contact, and
    address. Join to `RA` on registration number.
- **Coordinates are stored as separate degrees / minutes / seconds / direction
  fields, not as a single decimal value.** You must convert
  `DD + MM/60 + SS/3600`, then negate longitude for the western hemisphere
  (all of NC is `W` longitude / `N` latitude). Confirm the exact field names
  against the schema file.
- **Status codes** matter. Filter to constructed/granted structures (commonly
  status code `C` = Constructed). Exclude `Cancelled`, `Dismantled`,
  `Expired`. Confirm the status code domain in the "Code definitions for table
  data elements" reference.
- **Coordinate accuracy caveat:** ASR coordinates for older registrations can
  be off by tens to hundreds of meters. This is a known data-quality issue,
  **not a bug in our pipeline.** Some towers will visibly land in a road or
  one parcel away from their true position. We accept this for the prototype
  and surface it as a known limitation.

### 4B. Graham County Parcels (NC OneMap) — LANDOWNERS

**Source:** NC OneMap "Get Parcels" tool, downloaded per-county by clicking
Graham County on the interactive map. Standardized to NC parcel content
standard on **2025-07-15**.

**Format:** Whatever NC OneMap delivered — most likely a zipped **shapefile
set** (`.shp`, `.shx`, `.dbf`, `.prj`, possibly `.cpg`) or a **file
geodatabase** (`.gdb` folder) or a **GeoPackage** (`.gpkg`). The pipeline must
detect and handle whichever is present.

**Because NC standardized the attributes, expected fields include** (verify
actual field names by inspecting the file — NC OneMap publishes a data
dictionary, but inspect to be safe):

- A parcel identifier / PIN
- Owner name(s)
- Owner mailing address (street, city, state, ZIP) — often a separate set of
  fields from the situs (physical) address
- Situs / physical address
- Acreage (deeded and/or GIS-calculated)
- Assessed / appraised value (land, building, total — may be separate fields)
- Land use / property class code
- County name and FIPS

**Notes:**

- The parcel layer's coordinate reference system (CRS) is likely a NC State
  Plane projection (EPSG:2264 / NAD83 NC ftUS) or NC OneMap's published CRS —
  **reproject to EPSG:4326 (WGS84 lat/lon)** for the web map and before any
  spatial join with the WGS84 tower points.
- Owner names will be a mix of individuals (`SMITH JOHN A`), LLCs
  (`BLUE RIDGE HOLDINGS LLC`), trusts, churches, and government entities. The
  prototype does not need to unmask LLCs (that is a later phase) but it should
  display the raw owner string.
- Some parcels may have null/blank owner or value fields. Handle gracefully.

### 4C. HUD Opportunity Zones — DISTRESS OVERLAY (still to download)

**Source:** HUD GIS Open Data,
`https://hudgis-hud.opendata.arcgis.com/datasets/opportunity-zones`.
Download as **GeoJSON** (preferred) or shapefile. National file, ~30 MB.

**What it is:** Polygons of every U.S. census tract designated as a Qualified
Opportunity Zone (the original 2018 "OZ 1.0" designation, effective through
2028). Each feature has the tract GEOID and designation attributes.

**How we use it:** Filter to tracts that intersect Graham County, render as a
translucent base overlay, and flag any tower/parcel that falls within an OZ
tract.

> **Caveat to record in the README:** "OZ 2.0" tract redesignations are being
> made by governors during 2026; the map will change in 2026–2028. The
> prototype uses the OZ 1.0 layer that was downloaded. Note the download date.

### 4D. Optional / not yet downloaded

- **ARC distressed counties list** — not required; Graham County's distressed
  status is hardcoded for v1. Download later for multi-county expansion.

---

## 5. The Processing Pipeline (the "how")

A single Python script (`scripts/preprocess.py`) should:

1. **Locate and read the ASR schema** (`asr_sql_table_definitions_3.txt`)
   to derive correct column names/order for the pipe-delimited tables.
2. **Parse `RA.dat`** (registrations) and any auxiliary tables needed for
   coordinates; convert DMS → decimal degrees; filter to status =
   Constructed and to the Graham County bounding box.
3. **Parse `EN.dat`** (entities) and join to registrations on the registration
   number to attach the **tower owner / registrant** name and address.
4. **Read the parcel layer** (auto-detect shapefile / `.gdb` / `.gpkg`),
   reproject to EPSG:4326, retain the key attributes (PIN, owner, mailing
   address, situs, acreage, assessed value, land use).
5. **Read the Opportunity Zone layer**, reproject to EPSG:4326, clip/filter
   to tracts intersecting the county.
6. **Spatial join (point-in-polygon):** assign each tower to the parcel whose
   polygon contains it. Attach parcel PIN + landowner to the tower record.
   Conversely, flag each parcel that contains ≥1 tower.
7. **Distress flag:** flag each tower and each parcel that falls within an OZ
   tract.
8. **Write three GeoJSON outputs** to `data/processed/`, all in EPSG:4326:
   - `towers.geojson` — Point features; attributes: ASR number, tower
     owner/registrant, structure height, structure type, status,
     lat/lon, joined parcel PIN, joined landowner name, landowner
     mailing address, OZ flag.
   - `parcels.geojson` — Polygon features; attributes: PIN, owner, mailing
     address, situs, acreage, assessed value, land use, `has_tower`
     boolean, tower count, OZ flag.
   - `opportunity_zones.geojson` — tract polygons intersecting the county.
9. **Print a summary:** # towers found, # parcels in county, # parcels hosting
   a tower, # tower-hosting parcels that are in an OZ.

**Robustness requirements:**

- If an input file is missing or has an unexpected layout, **fail loudly with
  a clear message naming the expected file/path** — do not silently guess and
  do not attempt to download anything.
- Log counts at each stage so data loss is visible.
- Tolerate null/blank attribute values without crashing.

---

## 6. The Prototype Web App

A static single-page app under `app/`, runnable via
`python -m http.server` from the project root, loading the three processed
GeoJSON files via `fetch()`.

**Stack:** vanilla JavaScript + Leaflet + OpenStreetMap base tiles. **No build
step, no framework** for this prototype.

**Layout:**

- Full-screen map.
- Left sidebar (~350 px, collapsible):
  - Layer toggles: Towers / Parcels / Opportunity Zones.
  - Filters: "only parcels with towers", "only parcels in Opportunity
    Zones", owner dropdown (populated from data).
  - A details panel that populates on feature click.
  - A live count summary (towers visible / parcels visible).

**Styling:**

- Opportunity Zones: light translucent blue, drawn beneath everything.
- Parcels: thin gray outline by default; **yellow fill if it hosts a tower**;
  **orange fill if it hosts a tower AND is in an OZ**.
- Towers: red circle markers, slightly enlarged where clustered.

**Interaction:**

- Click tower → details: ASR #, tower owner, height, structure type, status,
  coordinates, the parcel it sits on, parcel owner, mailing address, OZ
  status, assessed value.
- Click parcel → details: PIN, owner, mailing address, acreage, assessed
  value, OZ status, hosts-a-tower?.
- Hover parcel → highlight boundary.
- Default view = Graham County bounding box.

---

## 7. Known Limitations (record these in the README)

1. **ASR coordinate drift.** Older registrations can be off by tens–hundreds
   of meters; some towers will land slightly off their true parcel. Visual
   verification against satellite imagery is the mitigation, not in scope for
   v1.
2. **ASR undercounts rooftop/short structures.** Antennas under ~200 ft and
   not near airports are not required to register. Urban rooftop sites are
   largely invisible. Graham County is rural so this is a minor concern here,
   but it matters for expansion.
3. **No carrier/tenant data.** We are not loading FCC ULS in v1, so we cannot
   yet show how many carriers (and therefore how much rent) a tower carries.
4. **Parcel data freshness.** Graham County parcels reflect a 2025-07-15
   standardization snapshot; ownership may have changed since.
5. **OZ 1.0 vs OZ 2.0.** The OZ layer is the original designation; a 2026
   redesignation process will change boundaries over 2026–2028.
6. **No LLC unmasking.** Parcels owned by LLCs/trusts show the raw entity
   name; resolving the human behind them is a later phase.
7. **Fee-owned tower sites.** Where the tower company owns the land outright
   there is no ground lease to optimize. The prototype does not yet
   distinguish these; flagging parcels whose owner name matches a known tower
   company is a useful v2 refinement.

---

## 8. Expansion Path / Other Data Options (future, not for this prototype)

This section documents the broader data universe so future iterations have a
roadmap. **None of this is needed for the Graham County prototype.**

### 8A. Deepen the cell-tower picture

- **FCC ULS (Universal Licensing System)** — identifies which carriers
  (AT&T, Verizon, T-Mobile, etc.) are licensed in an area. Joining ULS to ASR
  estimates tenant count per tower, the single biggest driver of lease value.
  Relevant radio services: Cellular (Part 22), PCS, AWS, 700 MHz, WCS. ULS
  coordinates are unreliable — use ULS only for carrier presence, ASR for
  location. Bulk files on the same FCC page.
- **FAA OE/AAA** (`oeaaa.faa.gov`) — proposed and recently built towers,
  often appearing before ASR. Good for a forward-looking pipeline.
- **FCC TCNS / Section 106 / Tribal notifications** — proposed sites with
  site addresses, useful for pipeline.
- **County Recorder "Memorandum of Lease" filings** — recorded short-form
  ground-lease summaries naming lessor (landowner) and lessee (tower co.).
  Searching grantor/grantee indexes for "Crown Castle", "American Tower",
  "SBA Towers/Properties", "Vertical Bridge", "Spectrasite", "Global
  Signal", "Pinnacle Towers" confirms which parcels actually have a lease
  and often the lease date/term. Highest-value primary-source enrichment.
- **Tower REIT 10-K filings (SEC EDGAR)** — aggregate portfolio and
  lease-expense benchmarks for valuation modeling.
- **Steel in the Air** — free published county-level lease-rent benchmarks;
  the best free input to a buyout-NPV model.

### 8B. Other infrastructure asset classes

- **Billboards:** State DOT outdoor-advertising permit databases. **Florida
  (FDOT)** publishes a monthly bulk Excel with permit, owner, and lat/lon —
  the single best billboard dataset. NC, TX, CA, MN, MI, GA, PA also publish
  permits (often needing a records request for the full geocoded set). Same
  parcel-join workflow applies.
- **Utility-scale solar:** **EIA Form 860 / 860M** (plant coords, owner,
  capacity), **USGS USPVDB** (array polygons), **interconnection.fyi**
  (ISO queues — forward pipeline of projects not yet built).
- **Distributed/rooftop solar:** **LBNL "Tracking the Sun"** (~3.3M systems,
  includes a third-party-ownership flag — the key field for renegotiable
  leased systems; addresses masked to city/ZIP, so probabilistic matching to
  parcels is required). State PUC net-metering interconnection reports and
  Secretary-of-State **UCC-1** filings (SunRun/Sunnova file these) help
  confirm third-party-owned systems on specific parcels.

### 8C. Distress and ownership enrichment

- **Treasury/HUD Opportunity Zones** (already in use) — plus **HUD
  QCT/DDA**, **ARC distressed tiers**, **USDA Persistent Poverty Counties**,
  **CDFI Investment Areas**, **EDA distressed designations**, **Census ACS
  5-year** tract poverty/income. These overlay cleanly in GIS to build a
  composite distress score for outreach prioritization.
- **County tax-delinquent / tax-sale lists** — acute financial-distress
  signal; many counties publish online (FL, TX, AR, GA, IN, IA, MD, MI, OK
  are good); others need a records request.
- **Foreclosure / pre-foreclosure** — ATTOM, PropertyRadar, CoreLogic
  (paid); county sheriff-sale / lis pendens notices (free, uneven).
- **Secretary of State business-entity & UCC search** — LLC unmasking
  (officers/registered agent) and third-party-solar confirmation.
- **Regrid (Landgrid)** — nationwide standardized parcel + owner data; a
  single statewide license removes per-county friction when expanding beyond
  the free-data states (NC, MT, FL, AR, IN, MN, UT, etc.).

### 8D. Recommended next pilot geographies (from the research)

In rough priority for expansion after Graham County: **Pike County, KY** and
**McDowell County, WV** (deep Appalachian distress; KY/WV parcels are
county-by-county and less clean than NC), **Hidalgo County, TX** (Rio Grande
Valley; heavy OZ coverage; CAD data online; demographic diversity), and
**Sunflower County, MS** (Delta persistent poverty). North Carolina and
Florida remain the lowest-friction states for data due to free standardized
statewide parcel layers (NC OneMap, FGDL) — staying within NC for the first
multi-county expansion is the path of least resistance.

---

## 9. Quick Reference — What Maps to What

| Question | Dataset that answers it |
|---|---|
| Where is the tower? | FCC ASR `RA.dat` coordinates |
| Who registered/owns the tower structure? | FCC ASR `EN.dat` entity |
| Who owns the *land* under the tower? | County parcel layer (spatial join) |
| Is this an economically distressed area? | HUD Opportunity Zones (v1); ARC/QCT/ACS (later) |
| Which carriers (rent drivers) are on the tower? | FCC ULS (v2 — not yet) |
| Does a ground lease actually exist & its terms? | County Recorder Memorandum of Lease (later) |
| What's the lease worth? | Steel in the Air benchmarks + REIT 10-Ks (later) |

---

## 10. Definitions

- **Parcel** — a single legally defined unit of real estate with a unique
  identifier (PIN/APN), defined polygon boundary, owner of record, tax-mailing
  address, assessed value, and land-use class. The atomic unit linking
  infrastructure to a human/entity.
- **ASR** — FCC Antenna Structure Registration; the federal registry of
  antenna structures (mostly towers) over ~200 ft or near airports.
- **Ground lease** — the contract by which a tower company pays a landowner
  to host a tower on the landowner's parcel.
- **Opportunity Zone (OZ)** — a census tract designated under the 2017 Tax
  Cuts and Jobs Act as economically distressed; used here as a distress proxy.
- **Spatial join** — assigning attributes from one geographic layer to another
  based on spatial relationship (here: which parcel polygon contains a tower
  point).
- **TPO** — third-party ownership (of a solar system); a leased/PPA system
  where the contract can potentially be renegotiated. Solar-side concept,
  noted for the expansion path.

---

*End of brief. The immediate deliverable is the `scripts/preprocess.py`
pipeline and the `app/` prototype described in Sections 5 and 6, operating on
the Graham County, NC data in Sections 3 and 4.*
