# DATA_SOURCES

**Last updated:** 2026-05-25 (Phase 1 product pivot — reverses several deferrals; adds Steel-in-the-Air + SoS + UCC-1 entries).

Reference for every data feed the puller knows about. Serves two audiences:

1. **The operator** — decide before pulling whether the source is safe
   to automate, whether the license permits use, and what format the
   file will arrive in.
2. **The preprocessor** — needs to know the on-disk layout, file
   format, and field/schema layout of each raw source.

For higher-level context:

- **What's in scope right now?** → [SCOPE.md](./SCOPE.md)
- **What works today?** → [STATUS.md](./STATUS.md)
- **When does each source need a refresh?** → [DATA_FRESHNESS.md](./DATA_FRESHNESS.md)
- **Caveats + pre-commercial blockers** → [LIMITATIONS.md](./LIMITATIONS.md)

> **Status legend**
> ✅ Automated download permitted by publisher
> 🟡 Automated download tolerated (no explicit endpoint; pulled politely)
> 🚫 Manual download required (terms of service, click-through, captcha, or no stable URL)
> 🔒 Credentialed / paid source
> ⊘ **Retired or deferred** — source not active in v1 cut; see [DECISIONS.md](./DECISIONS.md)

**Status overrides** (current as of 2026-05-25; reconcile with the per-source table below):

- **`hifld_towers`** is **RETIRED** (DHS removed the public layer in 2024 — ADR-015).
- **`regrid_parcels`** is **Phase 2+ unlock** (paid; ADR-010 reframed by [ADR-057](./adr/0057-budget-posture-reframed.md) — was "out of scope," now "current-budget posture").
- **`lbnl_tts`** is **DROPPED** from active registry (superseded — ADR-016).
- **`fcc_uls_cellular`, `fcc_uls_pcs`, `fcc_uls_aws`, `fcc_uls_700mhz`** are **Phase 1 Slice A** (in scope for carrier identification — [ADR-053](./adr/0053-product-phase-shift.md) partially reverses ADR-013).
- **`fcc_uls_wcs`, `fcc_uls_micro`** remain **DEFERRED** (microwave is point-to-point backhaul, not carrier-tenancy; WCS is low-volume).
- **`fdot_billboards`, `ncdot_billboards`** are **Phase 1 Slice C as parcel enrichment** (ADR-014 partially reversed for FL + NC). `txdot_billboards` stays deferred (TX not in anchor states).
- **`fl_fgdl_parcels`** is **REPLACED** by `fdor_nal` (ADR-019).
- **`in_parcels`** is **MOTHBALLED** (no owner data — ADR-017).
- **`mn_parcels`** is **DEFERRED** (license ambiguity — ADR-018).
- **`ut_parcels`** is **DEFERRED** (no owner data — ADR-049).
- **`hud_oz`, `hud_qct`, `usda_persistent_poverty`** — endpoints confirmed live 2026-05-21; pulled and normalized into the AR + MT composites.
- **`nc_onemap_parcels`** fetch deleted 2026-05-20; needs full re-fetch (Slice F).
- **NEW Phase 1 additions** (see source entries 30–32 below): Steel-in-the-Air free county-level lease benchmarks (`steel_in_the_air_free`), Secretary of State business-entity lookups (`sos_business_<state>`), UCC-1 filings (`ucc1_<state>`) — all bake into the Slice 4 lead-detail panel per [ADR-057](./adr/0057-budget-posture-reframed.md).

---

## Index

| # | Source | Category | Coverage | Automation | v1 status | Commercial use |
|---|---|---|---|---|---|---|
| 1 | FCC ASR | Towers | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 2 | FCC ULS — Cellular (Part 22) | Towers | National | ✅ | **Phase 1 Slice A** | ✅ Yes (public domain) |
| 3 | FCC ULS — PCS | Towers | National | ✅ | **Phase 1 Slice A** | ✅ Yes (public domain) |
| 4 | FCC ULS — AWS | Towers | National | ✅ | **Phase 1 Slice A** | ✅ Yes (public domain) |
| 5 | FCC ULS — 700 MHz | Towers | National | ✅ | **Phase 1 Slice A** | ✅ Yes (public domain) |
| 6 | FCC ULS — WCS | Towers | National | ✅ | ⊘ deferred | ✅ Yes (public domain) |
| 7 | FCC ULS — Microwave (Part 101) | Towers | National | ✅ | ⊘ deferred | ✅ Yes (public domain) |
| 8 | FAA Digital Obstacle File (DOF) | Towers | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 9 | HIFLD Cellular Towers | Towers | National | 🚫 | ⊘ retired (2024) | ✅ Yes (open data) |
| 10 | EIA Form 860 (annual) | Solar | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 11 | EIA Form 860M (monthly) | Solar | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 12 | USGS USPVDB | Solar | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 13 | LBNL Tracking the Sun | Solar | National | 🟡 | ⊘ deferred | ✅ Yes, with attribution |
| 14 | FDOT Outdoor Advertising permits | Billboards | Florida | ✅ | **Phase 1 Slice C** (parcel enrichment) | ✅ Yes (public records) |
| 15 | NCDOT Outdoor Advertising permits | Billboards | North Carolina | 🚫 | **Phase 1 Slice C** (parcel enrichment) | ✅ Yes (public records) |
| 16 | TxDOT Outdoor Advertising permits | Billboards | Texas | 🚫 | ⊘ deferred (TX not anchor) | ✅ Yes (public records) |
| 17 | NC OneMap statewide parcels | Parcels | NC (100 counties) | ✅ | ✓ active — raw deleted 2026-05-20; needs re-fetch | ✅ Yes, with attribution |
| 18 | FL FGDL DSL parcels | Parcels | Florida | 🚫 | ⊘ deferred (wrong dataset; replaced by #29) | ✅ Yes, with attribution |
| 19 | Montana Cadastral parcels | Parcels | Montana | 🚫 | ✓ active | ✅ Yes, with attribution |
| 20 | Minnesota statewide parcels (MnGeo) | Parcels | Minnesota | 🚫 | ⊘ deferred (license ambiguity) | ✅ Yes, with attribution |
| 21 | Indiana statewide parcels (IGIO) | Parcels | Indiana | 🚫 | ⊘ deferred (no owner data) | ✅ Yes, with attribution |
| 22 | Arkansas statewide parcels | Parcels | Arkansas | 🚫 | ✓ active | ✅ Yes, with attribution |
| 23 | Utah UGRC LIR parcels | Parcels | Utah | 🚫 | ⊘ deferred (no owner data — ADR-049) | ✅ Yes, with attribution |
| 24 | Regrid (Landgrid) nationwide parcels | Parcels | All 50 states (configurable) | 🔒 | ⊘ deferred (paid; free-only budget) | ✅ Yes, per license |
| 25 | HUD Opportunity Zones | Distress | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 26 | HUD Qualified Census Tracts | Distress | National | ✅ | ✓ active | ✅ Yes (public domain) |
| 27 | ARC County Economic Status | Distress | Appalachia (13 states) | ✅ | ✓ active | ✅ Yes (public domain) |
| 28 | USDA ERS Persistent Poverty Counties | Distress | National | 🟡 | ✓ active | ✅ Yes (public domain) |
| 29 | **FL FDOR NAL** (per-county tax roll) | Parcels | FL (all 67 counties) | 🚫 | ✓ active — raw intact; normalized + composite deleted 2026-05-20, needs re-run (Slice F) | ✅ Yes, with attribution |
| 30 | **Steel-in-the-Air** (free county-level lease benchmarks) — NEW | Lease comps | National (counties) | 🟡 | **Phase 1 Slice D** (bootstrap `lease_comp`) | ✅ Yes, with attribution |
| 31 | **Secretary of State business-entity lookups** — NEW | Officer disclosure | Per anchor state | 🚫 | **Phase 1 Slice D** (one-click in lead-detail panel) | ✅ Yes (public records) |
| 32 | **UCC-1 filings** — NEW | Third-party-ownership clues | Per anchor state | 🚫 | **Phase 1 Slice D** (surfaced in lead-detail panel) | ✅ Yes (public records) |
| 33 | **WV statewide parcels** (WVGISTC / SB 588) — NEW | Parcels | WV (all 55 counties) | 🚫 | ✓ active | ✅ Yes, with attribution |

---

# TOWERS

## 1. FCC Antenna Structure Registration (ASR)

- **ID:** `fcc_asr` · **Cadence:** Weekly (Sundays) · **Size:** ~90 MB
- **Source page:** <https://www.fcc.gov/wireless/data/public-access-files-database-downloads>
- **Direct bulk:**
  `https://data.fcc.gov/download/pub/uls/complete/r_tower.zip`
  `https://data.fcc.gov/download/pub/uls/complete/d_tower.zip`
- **License:** Public Domain (US federal government work).
- **Automation:** ✅ Bulk download is the publisher's intended access mode.
- **Commercial use:** ✅ Yes.

### What's inside the zip
Pipe-delimited `.dat` files (no header row). Column order comes from
`asr_sql_table_definitions_3.txt`. Most important tables:

| File | Records | Key |
|---|---|---|
| `RA.dat` | Registration / structure | `registration_number` |
| `CO.dat` | Coordinates (DMS) | `registration_number` |
| `EN.dat` | Entity (registrant / owner) | `registration_number` |
| `RE.dat` | Reference number history | `registration_number` |
| `SC.dat` | Special conditions | `registration_number` |
| `HS.dat` | History | `registration_number` |

### Key fields the preprocessor uses
- From `RA`: `registration_number`, `file_number`, `status_code`,
  `date_constructed`, `structure_type`, `overall_height_above_ground`,
  `height_of_structure`, `structure_street_address`, `structure_city`,
  `structure_state_code`, `county_code`, `zip_code`.
- From `CO`: `latitude_degrees/minutes/seconds/direction`,
  `longitude_degrees/minutes/seconds/direction`, `coordinate_type`
  (`T`=tower, `A`=array).
- From `EN`: `entity_name`, `street_address`, `city`, `state`,
  `zip_code`, `phone`, `frn`.

### Joins
`RA.registration_number ↔ CO.registration_number ↔ EN.registration_number`.

### Caveats
- Coordinates are DMS — convert to decimal then negate longitude for the
  western hemisphere.
- Filter `status_code = 'C'` to limit to constructed structures.
- Older registrations may be off by tens to hundreds of metres
  (acknowledged FCC data-quality limitation).

---

## 2–7. FCC Universal Licensing System (ULS) — six radio services

Six separate source IDs, one per band. **Phase 1 Slice A normalises bands 2–5 (Cellular + PCS + AWS + 700 MHz)** for carrier identification per tower ([ADR-053](./adr/0053-product-phase-shift.md) partially reverses ADR-013). Bands 6 + 7 (WCS, Microwave) remain deferred — WCS is low-volume; Microwave is point-to-point backhaul, not carrier-tenancy.

| ID | Band | File | Approx size | Phase 1? |
|---|---|---|---|---|
| `fcc_uls_cellular` | Cellular (Part 22) | `l_cell.zip` | ~220 MB | **Yes (Slice A)** |
| `fcc_uls_pcs` | Broadband PCS | `l_broad.zip` | ~140 MB | **Yes (Slice A)** |
| `fcc_uls_aws` | AWS | `l_aws.zip` | ~60 MB | **Yes (Slice A)** |
| `fcc_uls_700mhz` | Lower/Upper 700 MHz | `l_700.zip` | ~40 MB | **Yes (Slice A)** |
| `fcc_uls_wcs` | WCS 2.3 GHz | `l_wcs.zip` | ~10 MB | Deferred |
| `fcc_uls_micro` | Microwave (Part 101) | `l_micro.zip` | ~350 MB | Deferred |

- **Cadence:** Weekly (Sundays) · **Base URL:** `https://data.fcc.gov/download/pub/uls/complete/`
- **Source page:** <https://www.fcc.gov/uls/transactions/daily-weekly>
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Schema (subset relevant to lease-optimization)
Each zip unpacks into pipe-delimited `.dat` files keyed by record type:

| File | Records | Notes |
|---|---|---|
| `HD.dat` | License header | `usi`, `call_sign`, `licensee_id`, `radio_service_code`, `grant_date`, `expired_date`, `cancellation_date`, `effective_date`, `entity_name` |
| `EN.dat` | Entity / licensee | `usi`, `entity_name`, `street_address`, `city`, `state`, `zip` |
| `LO.dat` | Location | `usi`, `call_sign`, `location_class_code`, `location_number`, `site_status`, lat/long DMS, `location_address`, `location_city`, `location_county`, `location_state` |
| `FR.dat` | Frequency | `usi`, `frequency_assigned`, `bandwidth`, `frequency_upper_band` |
| `CO.dat` | Control point | `usi`, `control_point_address` |
| `AN.dat` | Antenna | `usi`, `antenna_make`, `model`, `gain`, `height_to_tip` |
| `SC.dat` / `HS.dat` | Special conditions / history | |

### Joins
`HD.usi ↔ EN.usi ↔ LO.usi ↔ FR.usi`. The "Unique System Identifier"
(`usi`) is the universal join key.

### Caveats
- ULS coordinates are *unreliable* — use ULS for carrier presence (which
  licensees have authorization at a site) and ASR for the actual tower
  coordinates. This is documented FCC guidance.

---

## 8. FAA Digital Obstacle File (DOF)

- **ID:** `faa_oeaaa` · **Cadence:** Daily · **Size:** ~12 MB
- **Source page:** <https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dof/>
- **Direct bulk:** `https://aeronav.faa.gov/Obst_Data/DAILY_DOF_DAT.ZIP`
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Structure
The zip contains `DOF.DAT` — a fixed-width text file (columns documented
in `DOF_README` inside the same archive). Key columns:

| Field | Position | Notes |
|---|---|---|
| OAS code (state/area) | 1-2 | Two-letter |
| Obstacle number | 4-9 | Stable ID |
| Verification status | 11-11 | `V`=verified, `O`=other |
| Country | 13-14 | |
| State | 16-17 | |
| City | 19-34 | |
| Latitude DMS | 36-49 | `DD-MM-SS.SSH` |
| Longitude DMS | 51-65 | `DDD-MM-SS.SSH` |
| Type | 67-84 | TOWER, BUILDING, STACK, … |
| Quantity | 86-87 | |
| AGL height (ft) | 89-93 | |
| AMSL height (ft) | 95-99 | |

### Joins
Standalone — useful as a forward-pipeline complement to FCC ASR (DOF
catalogues *any* obstacle; ASR is only the FCC-registered subset).

---

## 9. HIFLD — Cellular Towers

- **ID:** `hifld_towers` · **Cadence:** Irregular (~monthly) · **Size:** ~35 MB
- **Source page:** <https://hifld-geoplatform.hub.arcgis.com/datasets/geoplatform::cellular-towers/>
- **Direct bulk:** ArcGIS REST query endpoint, returns GeoJSON.
- **License:** Open data / public domain (per HIFLD Open terms)
- **Automation:** ✅ · **Commercial:** ✅

### Structure
GeoJSON FeatureCollection. Point features. Common fields include:
`Tower_ID`, `Owner`, `Latitude`, `Longitude`, `LicenseNum`, `Height_ft`,
`Tower_Type`, `Source`. Use as cross-check against FCC ASR for towers
under ~60 m that ASR doesn't catalogue.

---

# SOLAR

## 10. EIA Form 860 (annual)

- **ID:** `eia_860` · **Cadence:** Annual (~September release)
- **Size:** ~25 MB · **Source page:** <https://www.eia.gov/electricity/data/eia860/>
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Structure
Zip containing many Excel workbooks (one per Form 860 schedule). For
solar work, the relevant sheets:

| File | Sheet | Use |
|---|---|---|
| `3_1_Generator_Y<year>.xlsx` | `Operable` | Generator-level detail for every operating ≥1 MW unit |
| `2___Plant_Y<year>.xlsx` | `Plant` | Plant-level lat/lon, county, utility ID |
| `3_3_Solar_Y<year>.xlsx` | `Operable Solar` | Solar-specific: tracking, tilt, technology |

### Key fields
`Plant Code`, `Plant Name`, `Latitude`, `Longitude`, `State`, `County`,
`Nameplate Capacity (MW)`, `Operating Year`, `Technology`, `Tracking`,
`Tilt`, `Owner Name`.

### Joins
`Plant Code` is the universal key across all Form 860 workbooks.

---

## 11. EIA Form 860M (monthly)

- **ID:** `eia_860m` · **Cadence:** Monthly · **Size:** ~5 MB
- **Direct:** `https://www.eia.gov/electricity/data/eia860m/xls/eia860m.xlsx`
- **License/Automation/Commercial:** same as EIA-860.

### Structure
Single Excel workbook with sheets `Operating`, `Planned`, `Retired`.
Key fields match Form 860. Use for plants that came online between
annual 860 releases.

---

## 12. USGS USPVDB

- **ID:** `uspvdb` · **Cadence:** ~Annual · **Size:** ~40 MB
- **Source page:** <https://eerscmap.usgs.gov/uspvdb/>
- **ScienceBase:** <https://www.sciencebase.gov/catalog/item/6442d80ed34ec61a8de52a8f>
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Structure
Download zip contains shapefile + GeoPackage + CSV of every ≥1 MW
US solar PV facility. **Polygons** (not points). Key attributes:
`p_state`, `p_county`, `p_eia_id` (joins to EIA-860 `Plant Code`),
`p_year`, `p_area`, `p_cap_dc`, `p_cap_ac`, `p_tech_sec`,
`p_axis`, `p_tilt`, `p_lulc_pre`.

### Joins
`p_eia_id ↔ EIA-860 Plant Code` for crosswalk to owner/operator details.

---

## 13. LBNL Tracking the Sun

- **ID:** `lbnl_tts` · **Cadence:** Annual · **Size:** ~250 MB
- **Source page:** <https://emp.lbl.gov/tracking-the-sun>
- **License:** LBNL public-data terms — free use with citation
- **Automation:** 🟡 Tolerated (we scrape landing page to find the
  current-year link, then GET directly)
- **Commercial:** ✅ With attribution.

### Structure
Single large CSV (sometimes published as ZIP). One row per
distributed PV installation. ~3 M+ rows. Key fields:

| Field | Notes |
|---|---|
| `data_provider_1` | Which utility / state programme reported it |
| `system_size_DC` | kW (DC) |
| `installation_date` | YYYY-MM-DD |
| `state` | |
| `zip_code` | **Address is masked to ZIP** for privacy |
| `city` | |
| `customer_segment` | RES / COM / IND / GOV / NPF |
| **`third_party_ownership`** | **THE key field — `1` = leased/PPA, `0` = host-owned** |
| `installer_name` | |
| `inverter_loading_ratio`, `tracking`, `module_manufacturer`, … | technical detail |

### Notes for preprocessor
- Because addresses are city/ZIP-only, a precise parcel join is
  impossible. The best approach is *probabilistic* matching against a
  parcel layer (count of TPO systems in each ZIP joined to parcel
  density of likely residential single-family hosts).
- The TPO=1 subset is the renegotiable-lease subset.

---

# BILLBOARDS

## 14. FDOT Outdoor Advertising permits

- **ID:** `fdot_billboards` · **Cadence:** Monthly · **Size:** ~8 MB
- **Direct:** `https://www.fdot.gov/content/dam/fdotgov/files/maintenance/outdoor-advertising/oas-permit-extract.xlsx` (URL pattern may shift if FDOT restructures their CMS)
- **Source page:** <https://www.fdot.gov/maintenance/outdooradvertising>
- **License:** Florida public records · **Automation:** ✅ · **Commercial:** ✅

### Structure
Single Excel workbook (XLSX). Each row is a permitted sign. Key fields:
`Permit Number`, `Owner Name`, `County`, `Section`, `Subsection`,
`Mile Post`, `Side of Road`, `Latitude`, `Longitude`, `Height`,
`Status`, `Status Date`, `Issued Date`.

### Joins
Spatial join (Lat/Long) into a Florida parcel layer (source #18, FGDL).

### Notes
The single best public billboard dataset in the US. FDOT may
occasionally rename or restructure the CMS path — if a 404 surfaces in
the puller, use the source page above to find the current link.

---

## 15. NCDOT Outdoor Advertising permits

- **ID:** `ncdot_billboards` · **Cadence:** On request · **Size:** ~5 MB est.
- **Source page:** <https://connect.ncdot.gov/business/Roadside/Pages/Outdoor-Advertising.aspx>
- **License:** NC public records (G.S. 132)
- **Automation:** 🚫 Manual only — no stable bulk URL; scraping the
  search portal is discouraged.
- **Commercial:** ✅ Yes.

### Workflow
Email the NCDOT Roadside Environmental Unit to request the current
permit extract, or file a G.S. 132 records request. Drop the resulting
file into `data/raw/ncdot_billboards/current/`.

### Expected structure
Typically an Excel workbook with permit #, owner (sign company),
county, route, mile-marker, status, dates. Coordinates may need
geocoding from route + mile-marker.

---

## 16. TxDOT Outdoor Advertising permits

- **ID:** `txdot_billboards` · **Cadence:** On request · **Size:** ~20 MB est.
- **Source page:** <https://www.txdot.gov/business/permits/outdoor-advertising.html>
- **License:** Texas public records (Government Code Ch. 552)
- **Automation:** 🚫 Manual only — TPIA request required
- **Commercial:** ✅ Yes.

### Workflow
Submit a Texas Public Information Act request to TxDOT Right of Way
Division specifying "all outdoor advertising sign permits with
coordinates if available". Drop file in `data/raw/txdot_billboards/current/`.

---

# PARCELS

## 17. NC OneMap — statewide parcels

- **ID:** `nc_onemap_parcels` · **Cadence:** Monthly (per-county) · **Size:** ~10 GB on disk (1186 paginated GeoJSON files)
- **Source page:** <https://www.nconemap.gov/datasets/nconemap::north-carolina-parcels-polygons>
- **Bulk API (broken):** `https://www.nconemap.gov/api/download/v1/items/.../shapefile` — returns persistent HTTP 500 since mid-2026
- **MapServer query (used by auto-fetch):** `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1/query`
- **License:** Open data / NC public records
- **Automation:** ✅ Auto-fetch via MapServer pagination (ADR-048). Runs ~30–60 min unattended; resumable on interruption.
- **Commercial:** ✅ with attribution.

### Current data status

`data/raw/nc_onemap_parcels/` was **deleted 2026-05-20** (was 8.3 GB,
1,106 of 1,186 pages fetched before a server-side HTTP 504 stalled the
fetch). Needs a full re-fetch via the puller when the NC OneMap
endpoint is confirmed stable.

### Structure
On-disk layout: `data/raw/nc_onemap_parcels/current/page_NNNN.geojson`
— one GeoJSON FeatureCollection per 5000-feature page (5.9M records
total → ~1186 pages). EPSG:4326. The normalizer's existing GeoJSON
rglob path picks them up transparently. MapServer field names are
lowercase (`ownname`, `mailadd`, `cntyfips` etc.); the field map in
`scripts/preprocess/normalizers/state_parcels.py` declares both
casings for forward + back compat with legacy shapefile bulk downloads.

### Standardized fields
| Field | Description |
|---|---|
| `PARNO` | County parcel number |
| `NPARNO` | State+county+APN (statewide unique) |
| `OWNNAME1` / `OWNNAME2` | Owner name(s) |
| `MAILADD` / `MAILCITY` / `MAILSTATE` / `MAILZIP` | Owner mailing address |
| `PROPLOC` | Situs address |
| `GISACRES` | GIS-computed acres |
| `LANDVAL` / `IMPROVVAL` / `PARVAL` | Land / improvement / total value |
| `LANDUSE` / `LANDUSEDS` | Land-use code + description |
| `STRUCYR` | Year structure built |
| `STATCFIPS` | 5-digit state+county FIPS |

### Notes
- CRS is typically NC State Plane (EPSG:2264) — reproject to EPSG:4326
  in the preprocessor.
- Per-county refresh cadence varies; the metadata service exposes the
  most-recent edit timestamp for the entire layer.

---

## 18. Florida statewide parcels (FGDL / FDOR NAL)

- **ID:** `fl_fgdl_parcels` · **Cadence:** Annual · **Size:** ~4.5 GB
- **Source page:** <https://www.fgdl.org/metadataexplorer/explorer.jsp>
- **License:** FGDL terms (free with attribution; click-through required)
- **Automation:** 🚫 Manual only — portal requires click-through agreement.
- **Commercial:** ✅ With attribution.

### Workflow
Accept FGDL terms on the metadata explorer, search for "PARCELS" for
the current year, download the statewide shapefile or GDB, drop into
`data/raw/fl_fgdl_parcels/current/`.

### Structure
FL DOR NAL (Name-Address-Legal) attributes joined to parcel polygons.
Owner name, mailing, "just value" (FL's term for assessed value), land
use code, sale history.

---

## 19. Montana Cadastral

- **ID:** `mt_cadastral_parcels` · **Cadence:** Quarterly · **Size:** ~600 MB
- **Source page:** <https://geoinfo.msl.mt.gov/Home/msdi/cadastral>
- **License:** Montana public records
- **Automation:** 🚫 Manual only
- **Commercial:** ✅ With attribution.

### Structure
Statewide shapefile with normalised owner, mailing, value, acreage.

---

## 20. Minnesota statewide parcels (MnGeo)

- **ID:** `mn_parcels` · **Cadence:** Annual · **Size:** ~800 MB
- **Source page:** <https://gisdata.mn.gov/dataset/parcels-statewide>
- **License:** MN Geospatial Commons terms (click-through)
- **Automation:** 🚫 Manual only
- **Commercial:** ✅ With attribution.

---

## 21. Indiana statewide parcels (IGIO)

- **ID:** `in_parcels` · **Cadence:** Annual · **Size:** ~1.5 GB
- **Source page:** <https://gis.iu.edu/dataset/infrastructure-real-estate/in-2024-parcels>
- **License:** IN public records
- **Automation:** 🚫 Manual only
- **Commercial:** ✅ With attribution.

---

## 22. Arkansas statewide parcels

- **ID:** `ar_parcels` · **Cadence:** Annual · **Size:** ~1.2 GB
- **Source page:** <https://gis.arkansas.gov/product/parcels/>
- **License:** AR public records
- **Automation:** 🚫 Manual only
- **Commercial:** ✅ With attribution.

---

## 23. Utah UGRC LIR parcels — DEFERRED (no owner data)

- **ID:** `ut_parcels` · **Cadence:** Quarterly · **Size:** ~900 MB
- **Source page:** <https://gis.utah.gov/products/sgid/cadastre/parcels/>
- **License:** UT public records
- **Automation:** 🚫 Manual only · **Registry:** ⊘ deferred
- **Commercial:** ✅ With attribution.

**Deferred from the v1 anchor set (ADR-049).** UGRC's parcel layers —
the statewide aggregate, the per-county basic parcels, and the
per-county LIR parcels (all 29 counties) — carry value, acreage,
property class, year built, and situs address but **no owner name**.
UGRC's Land Information Record standard omits owner name; the only
owner-adjacent field is `OWN_TYPE` (a private/government category).
Owner data lives behind per-county assessor portals with no bulk
download. Same blocker as Indiana (#22). Kept in the registry's
deferred block so it can be re-promoted if a Utah owner-data source
ever materialises.

---

## 24. Regrid (Landgrid) — nationwide parcels

- **ID:** `regrid_parcels` · **Cadence:** Quarterly (or monthly at premium tier) · **Size:** ~60 GB (nationwide tier)
- **Source page:** <https://regrid.com/api>
- **License:** Commercial bulk-data licence (per signed agreement)
- **Automation:** 🔒 Credentialed (requires paid subscription)
- **Commercial:** ✅ Per licence.

### Required env vars
Set in `.env` at the project root (gitignored):

```
REGRID_S3_BUCKET=<bucket Regrid provisions for you>
REGRID_S3_PREFIX=<your tenant prefix>
AWS_ACCESS_KEY_ID=<key Regrid issues>
AWS_SECRET_ACCESS_KEY=<secret>
```

Without these, the UI shows "Credentials required" and skips the source.

### Structure
Delivered as your chosen format (GeoPackage, shapefile, GeoJSON, CSV,
or Parquet) — see your Regrid agreement. Schema is uniform across all
50 states; owner mailing address, value, acreage, land use all included
when you license the Premium / Property Tax tier.

### Pricing reference
- Single state: ~$2K-$5K/year
- Regional bundle: ~$8K-$15K/year
- Nationwide: ~$15K-$50K/year
(Exact pricing requires a sales conversation. See main project notes.)

---

## 33. West Virginia statewide parcels (WVGISTC / MapWV, SB 588)

- **ID:** `wv_parcels` · **Cadence:** Annual (summer/fall publish) · **Size:** ~527 MB (zipped File Geodatabase)
- **Source page:** <https://wvgis.wvu.edu/data/dataset.php?ID=371> (record) · **Direct bulk:** `https://data.wvgis.wvu.edu/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_<year>/WV_WVGISTC_Tax_<year>.gdb.zip`
- **License:** Free public service under WV SB 588 (2017); MapWV terms (<https://www.mapwv.gov/terms.html>) — copy/distribute "without obligation … unless otherwise stated"; provided "as is," not a survey.
- **Automation:** 🚫 Manual only — but the bulk `.gdb.zip` is an anonymous direct HTTPS download (no login/click-through). The walkthrough includes the `curl` command; could be promoted to auto-fetch later (the annual `WVGISTC_<year>` path segment is the only moving part).
- **Commercial:** ✅ With attribution. ToS reviewed and permissive (no commercial bar, no strict attribution requirement); attribution to the custodians retained as prudent practice. Residual: embedded `.gdb` FGDC metadata not exhaustively read.

### Structure
One File Geodatabase, all 55 counties, ~1.39M parcels (Tax Year 2025).
The record splits across two objects joined on **`CleanParcelID`**:

- **`MasterSurfWV_2025`** — parcel polygons (EPSG:26917 → reprojected to
  4326), thin owner set (`FullOwnerName`/`FullOwnerAddress`/
  `FullPhysicalAddress`), `Acres_C`, 2-digit `CountyID`.
- **`ParcelSummary`** — geometry-less attribute table (the full WV IAS
  assessment record): granular owner (`Owner1`/`Owner2`), structured
  mailing (`OwnerCity`/`OwnerStateCode`/`OwnerZipCode`), appraised values
  (`LandAppraisal`/`BuildingAppraisal`/`TotalAppraisal`), land use
  (`LandUseCode`/`LandUse`), `CountyName`/`CountyCode`.

The normalizer left-merges `ParcelSummary` onto the polygons via the
adapter's `AttributeJoin` (see `state_parcel_adapters/wv.py`), so the full
owner/value/land-use detail reaches the canonical `parcel` schema.

### Caveats
- **Surface owner only.** The parcel names the SURFACE owner; split-estate
  (severed minerals) is the norm in rural WV. That surface owner is exactly
  the tower-lease target — do **not** conflate with mineral ownership.
- **County code ≠ Census FIPS.** WV's `CountyID`/`CountyCode` is an
  alphabetical 01–55 sequence that does not equal Census ANSI FIPS — Census
  collates McDowell (54047) before Marion (54049). Resolved via an explicit
  verified name/code → FIPS table, **not** a prefix-concat.
- **Appraised, not assessed.** `TotalAppraisal` is total *appraised* value;
  WV statutory assessed value is 60% of appraised and is not a stored column.
- All 55 counties are Appalachian → ARC distress overlay covers 100% of WV.

---

# DISTRESS

## 25. HUD Opportunity Zones

- **ID:** `hud_oz` · **Cadence:** Static (2018 designation; OZ 2.0 redesignations 2026-28)
- **Size:** ~30 MB
- **Source page:** <https://hudgis-hud.opendata.arcgis.com/datasets/opportunity-zones>
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Structure
GeoJSON FeatureCollection of ~8,700 census-tract polygons. Key fields:
`GEOID10` (11-digit tract FIPS), `STATE_FIPS`, `COUNTY_FIPS`, `TRACT`,
`STATE_ABBR`, `STATE_NAME`, `RURAL` (`Y` if designated rural OZ).

---

## 26. HUD Qualified Census Tracts (QCT)

- **ID:** `hud_qct` · **Cadence:** Annual · **Size:** ~50 MB
- **Source page:** <https://hudgis-hud.opendata.arcgis.com/datasets/qualified-census-tracts>
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Structure
GeoJSON FeatureCollection. Census tracts designated QCT (≥50% of
households below 60% AMI, or ≥25% poverty rate). Use as a secondary
distress overlay alongside Opportunity Zones.

---

## 27. ARC County Economic Status (Appalachia)

- **ID:** `arc_distressed` · **Cadence:** Annual (FY, June) · **Size:** ~0.3 MB
- **Source page:** <https://www.arc.gov/county-economic-status-in-appalachia/>
- **License:** Public Domain · **Automation:** ✅ · **Commercial:** ✅

### Structure
Excel workbook keyed by 5-digit county FIPS. Each county classified
as one of: `Distressed`, `At-Risk`, `Transitional`, `Competitive`,
`Attainment`. Plus the three underlying components (3-year unemployment,
per-capita market income, poverty rate).

### Joins
County FIPS — joins to any county-level layer.

---

## 28. USDA ERS Persistent Poverty Counties

- **ID:** `usda_persistent_poverty` · **Cadence:** Per-decennial (~5 years) · **Size:** ~1 MB
- **Source page:** <https://www.ers.usda.gov/data-products/county-typology-codes>
- **License:** Public Domain · **Automation:** 🟡 Tolerated
- **Commercial:** ✅ Yes.

### Structure
CSV keyed by county FIPS. The persistent-poverty flag is one column;
the same file contains the broader ERS county-typology codes (urban/
rural, farming-dependent, mining-dependent, etc.).

### Joins
County FIPS.

---

## 29. FL FDOR — per-county PAR parcel shapefiles (PIN + NAL joined)

- **ID:** `fdor_nal` · **Cadence:** Annual (Map Data refresh each August) · **Size:** ~28 GB raw on disk (all 67 counties; the `.dbf` attribute tables dominate)
- **Source page:** <https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx>
- **Map Data directory:** linked from the FDOR page (where the PAR shapefiles live)
- **License:** Florida public records (Ch. 119, F.S.) — commercial reuse with attribution
- **Automation:** 🚫 Manual only — per-county selection + redistribution-terms click-through.
- **Commercial:** ✅ With attribution.

### Why this and not FGDL DSL (source #18)
FGDL DSL covers state-owned land, not private parcels — wrong dataset
for landowner outreach. FDOR's per-county PAR shapefiles are the
canonical Florida private-parcel landowner data (every county's
parcel polygons joined with the current-year NAL tax-roll). v1 ships
all 67 Florida counties (ADR-047).

### PIN vs PAR (per FDOR's Parcel Shapefiles Readme)
- **PIN** = parcel geometry only (FID + Shape + PARCELNO). **Skip.**
- **PAR** = PIN joined with current-year NAL attributes. **Use this.**

The standalone NAL/SDF text files in FDOR's Tax Roll Data File
directory are the same attributes minus geometry — not needed because
PAR has them merged.

### v1 county set
**All 67 Florida counties** (per ADR-047). FDOR publishes one PAR ZIP
per county on the Map Data directory; the walkthrough lists every
county alphabetically as a download checklist. **Miami-Dade and
St. Johns** ship separate condominium property records — grab both
condo files (`miamidade_condos_2025par.zip`, `stjohnscondos_2025.zip`)
alongside the main per-county PAR ZIPs.

### Workflow
The puller's **Walk me through** button surfaces step-by-step
instructions: skim the Parcel Shapefiles Readme, open the Map Data
directory, pick the latest year, download all 67 PAR ZIPs (plus the
two condo extras), upload them via the puller's Upload button
(auto-extract into per-county subfolders). The normalizer uses rglob,
so per-county subfolder layout is transparent.

### Structure
Per-county shapefile with NAL columns joined on PARCELNO. Key columns
(NAL standard):

- `PARCELNO` — county-namespaced parcel ID (join key)
- `OWN_NAME`, `OWN_ADDR1`, `OWN_CITY`, `OWN_STATE`, `OWN_ZIPCD` — owner block
- `JV` — just value (FL's term for assessed value)
- `AV_SD` — school district assessed value
- `LND_VAL`, `IMP_VAL` — land + improvement value split
- `DOR_UC` — use code (FDOR-standard taxonomy)
- `ACT_YR_BLT` — actual year built
- `TOT_LVG_AR` — total living area (sq ft)

Note: shapefile column names are capped at 10 chars, so some NAL
fields may be truncated in the .dbf. The normalizer (Section 5)
handles the field-name mapping.

### Caveats
Per the FDOR readme, shapefile polygon counts won't exactly match NAL
record counts — Ch. 119 redactions, rights-of-way polygons,
unmapped condo units, and ownership-unknown parcels can land on one
side but not the other. The normalizer keeps unmatched polygons with
null owner columns rather than dropping them.

### Joins
County FIPS (derived from filename) + PARCELNO → joins to FCC ASR /
FAA / HUD overlays via point-in-polygon spatial join.

---

# PHASE 1 ADDITIONS (Slice D — Lead-detail panel enrichment)

## 30. Steel-in-the-Air — free county-level lease benchmarks

- **ID:** `steel_in_the_air_free` · **Cadence:** Irregular (Steel-in-the-Air publishes annually-ish) · **Size:** small (~MB)
- **Source page:** <https://www.steelintheair.com/cell-tower-lease-rates/>
- **License:** Steel-in-the-Air's free-tier terms (free with attribution)
- **Automation:** 🟡 Tolerated (TBD at Slice D kickoff — confirm download URL + format)
- **Commercial use:** ✅ With attribution.

### Purpose

Bootstraps the `lease_comp` table in the Slice 4 backend. ~3000 US counties with rent-mean / rent-percentile estimates. UI surfaces *"this tower's rent is in the Nth percentile vs {county/region}."* **Note (2026-05-26):** data-source research found that no free Steel-in-the-Air county-level lease-rate dataset exists — see [STATUS.md §7](./STATUS.md) for the Slice D rescope.

### Open at Slice D kickoff

- Confirm exact download URL + format (web-scrape vs static CSV/JSON).
- Confirm the free tier's attribution requirements.
- Schema mapping: target `lease_comp(state, county, asset_type, source='steel_in_the_air_free', year, rent_mean, rent_p25, rent_p75, sample_size)`.

### Phase 2 unlock

Steel-in-the-Air **paid tier** has finer-than-county granularity. Phase 2 conversation per [ADR-057](./adr/0057-budget-posture-reframed.md).

---

## 31. Secretary of State business-entity lookups (per anchor state)

- **IDs:** `sos_business_ar`, `sos_business_mt`, `sos_business_fl`, `sos_business_nc` · **Cadence:** Live (lookup on-demand) · **Size:** N/A (no bulk download)
- **Source pages:**
  - AR: <https://www.sos.arkansas.gov/corps/search_corps.php>
  - MT: <https://biz.sosmt.gov/search/business>
  - FL: <https://search.sunbiz.org/>
  - NC: <https://www.sosnc.gov/online_services/search>
- **License:** Public records (per-state public-information statutes)
- **Automation:** Per-state UX varies — some allow direct URL queries; others require search form posts. Backend wraps each per-state quirk.
- **Commercial use:** ✅ Yes.

### Purpose

Slice 4 lead-detail panel surfaces a **one-click "look up LLC officers"** button per lead. Returns publicly-disclosed managers / officers / registered-agent details for the LLC named on the parcel. **Not** identity resolution — these are officers the entity itself publicly registered ([ADR-057](./adr/0057-budget-posture-reframed.md) narrowing of ADR-041).

### Implementation notes

- Backend caches lookups per `tenant_id`-scoped `(state, entity_name)` for a TTL (~30 days) to avoid hammering SoS endpoints.
- Each state's UX is bespoke (FL's Sunbiz is well-structured; NC's portal needs more parsing). Expect a per-state adapter per anchor state.

---

## 32. UCC-1 filings (per anchor state)

- **IDs:** `ucc1_ar`, `ucc1_mt`, `ucc1_fl`, `ucc1_nc` · **Cadence:** Live (lookup on-demand) · **Size:** N/A (no bulk download)
- **Source pages:** each state SoS's UCC search (same SoS portals as #31 above, separate UCC tab)
- **License:** Public records.
- **Automation:** Per-state lookup; bespoke adapters.
- **Commercial use:** ✅ Yes.

### Purpose

Surfaced in the Slice 4 lead-detail panel as **third-party-ownership clues**. UCC-1 financing statements name secured parties — useful for confirming whether an asset (often solar systems, occasionally tower equipment) is third-party-owned and therefore on a renegotiable contract.

### Caveat

UCC-1 lookups by debtor name return many irrelevant filings (any UCC filing the debtor has, not just real-estate-related). The lead-detail panel filters / labels by filing date + secured-party patterns rather than trying to be exhaustive.

---

## Per-source on-disk layout

All sources land at `data/raw/<source_id>/current/`. Example after a
pull of FCC ASR + HUD OZ + HIFLD:

```
data/raw/
├── fcc_asr/
│   └── current/
│       ├── r_tower/
│       │   ├── RA.dat
│       │   ├── CO.dat
│       │   ├── EN.dat
│       │   └── …
│       └── d_tower/
│           └── …
├── hifld_towers/
│   └── current/
│       └── cellular_towers.geojson
└── hud_oz/
    └── current/
        └── opportunity_zones.geojson
```

The preprocessor reads from `data/raw/<source_id>/current/` only —
never from `.partial/` (transient) or any temporary download path.

---

## Manifest

The Puller writes `data/manifest.json` recording, per source:
- `local_version` — version of what's on disk
- `remote_version` — version the publisher last advertised
- `fetched_at` / `checked_at` — ISO 8601 timestamps
- `bytes` — total disk usage of `current/`
- `files` — relative paths under `data/raw/`
- `status` — one of `ok`, `stale`, `missing`, `check_failed`,
  `fetch_failed`, `manual_only`, `needs_credentials`
- `error` — last error message if any

The preprocessor can read this file to (a) verify the input version it's
consuming, (b) fail fast if a required source is missing.

---

## Adding a new source

1. Add `scripts/fetch/sources/<your_source>.py` defining a subclass of
   `DataSource` exported as `SOURCE` (or `SOURCES` for a list).
2. Import it in `scripts/fetch/registry.py` and append to `_ACTIVE`
   (or `_DEFERRED` if not part of the v1 pitch scope — see ADR-045).
3. Document it here with the same headings (Cadence / Size / Source /
   Direct URL / License / Automation / Commercial / Structure / Joins).
4. Restart the Puller — the new source appears in its category group.
