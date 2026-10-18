# Data sources

Reference for every data feed the puller knows about. It serves two readers:

1. **The operator** decides before pulling whether the source is safe
   to automate, whether the license permits use, and what format the
   file will arrive in.
2. **The preprocessor** needs the on-disk layout, file format, and
   field and schema layout of each raw source.

For higher-level context:

- **What shipped and where the project stopped** → [STATUS.md](./STATUS.md)
- **When does each source need a refresh?** → [DATA_FRESHNESS.md](./DATA_FRESHNESS.md)
- **Caveats and known limits** → [LIMITATIONS.md](./LIMITATIONS.md)

> **Automation legend**
> **Automated**: the publisher permits automated download.
> **Tolerated**: automated download is tolerated (no explicit endpoint; pulled politely).
> **Manual**: manual download required (terms of service, click-through, captcha, or no stable URL).
> **Credentialed**: paid or login-gated source.
> **Deferred / removed**: not active in the Phase 1 cut; see [DECISIONS.md](./DECISIONS.md).

**Status notes** (as of 2026-06-26; the per-source table below agrees):

- **`hifld_towers`** was **removed from the repo** on 2026-07-03. The Department of Homeland Security (DHS) retired the public layer in 2024 (ADR-015), so the dead fetcher and normalizer were deleted rather than kept parked. Index row 9 stays as a tombstone for numbering.
- **`regrid_parcels`** is a **Phase 2+ unlock** (paid). ADR-010 was reframed by [ADR-057](./adr/0057-budget-posture-reframed.md) from "out of scope" to "current-budget posture".
- **`lbnl_tts`** is **dropped** from the active registry (superseded, ADR-016).
- **`fcc_uls_cellular`** (Part 22, the `l_cell` bulk file) and the **PCS / AWS / 700 MHz radio-service-code subset of `fcc_uls_market`** (the `l_market` Market-Based Services bulk file) are **Phase 1 Slice A**, carrier identification. [ADR-053](./adr/0053-product-phase-shift.md) partially reverses ADR-013 for these. The FCC does **not** ship `fcc_uls_pcs` / `_aws` / `_700mhz` as separate downloads. Those bands are carved out of the single `l_market` file by `radio_service_code` (see sections 2-7).
- The rest of `fcc_uls_market` (WCS code `WS`, 600 MHz `WT`, Narrowband PCS, paging, BRS/EBS, …) and **`fcc_uls_micro`** (Microwave, point-to-point backhaul) stay **deferred**. None of them is one of the four Phase 1 carrier bands.
- **`fdot_billboards`** and **`ncdot_billboards`** were tagged **Phase 1 Slice C parcel enrichment** (ADR-014 partially reversed for FL; the NCDOT extract rides with the deferred NC stretch). **Both stayed in the registry `_DEFERRED` block and were never wired active.** `txdot_billboards` stays deferred because TX is not an anchor state.
- **`fl_fgdl_parcels`** was replaced as FL's *primary* parcel source by `fdor_nal` (ADR-019), then **re-activated as a complement on 2026-07-03**. It is the Division of State Lands (DSL) *state-owned land* composite, a distinct parcel class from the private tax rolls in the Name-Address-Legal (NAL) file, and its ~241K parcels are in the FL composite. It auto-fetches by direct download; the fetcher discovers the newest release filename from the FGDL listing.
- **`in_parcels`** is **mothballed** (no owner data, ADR-017).
- **`mn_parcels`** is **deferred** (license ambiguity, ADR-018).
- **`ut_parcels`** is **deferred** (no owner data, ADR-049).
- **`hud_oz`, `hud_qct`, `usda_persistent_poverty`**: endpoints confirmed live on 2026-05-21; pulled and normalized into the AR and MT composites.
- **`nc_onemap_parcels`**: the fetched raw data was deleted on 2026-05-20. Re-fetch, normalize, and compose were **deferred to a Phase 1 stretch**. NC (37) is not a committed anchor and does **not** gate Slice F. The source object stays in registry `_ACTIVE`, so it is "active" in code.
- **Phase 1 additions that were planned but never built** (source entries 30-32 below): Steel-in-the-Air free county-level lease benchmarks (`steel_in_the_air_free`), Secretary of State business-entity lookups (`sos_business_<state>`), and UCC-1 filings (`ucc1_<state>`). All three were meant for the Slice D+E lead-detail panel per [ADR-057](./adr/0057-budget-posture-reframed.md). Steel-in-the-Air's terms forbid reproducing its data, so it stayed a hand-read reference benchmark and none of its data is in the repo or on the demo.

---

## Index

| # | Source | Category | Coverage | Automation | Phase 1 status | Commercial use allowed |
|---|---|---|---|---|---|---|
| 1 | FCC ASR | Towers | National | Automated | Active | Yes (public domain) |
| 2 | FCC ULS Cellular (`fcc_uls_cellular`, Part 22, `l_cell`) | Towers | National | Automated | **Phase 1 Slice A** | Yes (public domain) |
| 3 | FCC ULS Market-Based: PCS subset (`fcc_uls_market` `l_market`, code `CW`) | Towers | National | Automated | **Phase 1 Slice A** | Yes (public domain) |
| 4 | FCC ULS Market-Based: AWS subset (`fcc_uls_market`, codes `AW/AT/AD/AH`) | Towers | National | Automated | **Phase 1 Slice A** | Yes (public domain) |
| 5 | FCC ULS Market-Based: 700 MHz subset (`fcc_uls_market`, codes `WY/WZ/WU/WX`) | Towers | National | Automated | **Phase 1 Slice A** | Yes (public domain) |
| 6 | FCC ULS Market-Based: WCS and other market services (`l_market` code `WS`, etc.) | Towers | National | Automated | Deferred | Yes (public domain) |
| 7 | FCC ULS Microwave (`fcc_uls_micro`, Part 101) | Towers | National | Automated | Deferred | Yes (public domain) |
| 8 | FAA Digital Obstacle File (DOF) | Towers | National | Automated | Active | Yes (public domain) |
| 9 | ~~HIFLD Cellular Towers~~ | Towers | National | n/a | Removed 2026-07-03 (upstream dead since 2024) | n/a |
| 10 | EIA Form 860 (annual) | Solar | National | Automated | Active | Yes (public domain) |
| 11 | EIA Form 860M (monthly) | Solar | National | Automated | Active | Yes (public domain) |
| 12 | USGS USPVDB | Solar | National | Automated | Active | Yes (public domain) |
| 13 | LBNL Tracking the Sun | Solar | National | Tolerated | Deferred | Yes, with attribution |
| 14 | FDOT Outdoor Advertising permits | Billboards | Florida | Automated | Deferred (planned for Phase 1 Slice C) | Yes (public records) |
| 15 | NCDOT Outdoor Advertising permits | Billboards | North Carolina | Manual | Deferred (planned for Phase 1 Slice C) | Yes (public records) |
| 16 | TxDOT Outdoor Advertising permits | Billboards | Texas | Manual | Deferred (TX not an anchor) | Yes (public records) |
| 17 | NC OneMap statewide parcels | Parcels | NC (100 counties) | Automated | Deferred Phase 1 stretch. In the registry, but raw data deleted 2026-05-20; re-fetch does not gate Slice F | Yes, with attribution |
| 18 | FL FGDL DSL parcels (state-owned land) | Parcels | Florida | Automated (since 2026-07-03) | Active, complements source 29 | Yes, with attribution |
| 19 | Montana Cadastral parcels | Parcels | Montana | Automated (since 2026-07-03) | Active | Yes, with attribution |
| 20 | Minnesota statewide parcels (MnGeo) | Parcels | Minnesota | Manual | Deferred (license ambiguity) | Yes, with attribution |
| 21 | Indiana statewide parcels (IGIO) | Parcels | Indiana | Manual | Deferred (no owner data) | Yes, with attribution |
| 22 | Arkansas statewide parcels | Parcels | Arkansas | Manual | Active | Yes, with attribution |
| 23 | Utah UGRC LIR parcels | Parcels | Utah | Manual | Deferred (no owner data, ADR-049) | Yes, with attribution |
| 24 | Regrid (Landgrid) nationwide parcels | Parcels | All 50 states (configurable) | Credentialed | Deferred (paid; free-only budget) | Yes, per license |
| 25 | HUD Opportunity Zones | Distress | National | Automated | Active | Yes (public domain) |
| 26 | HUD Qualified Census Tracts | Distress | National | Automated | Active | Yes (public domain) |
| 27 | ARC County Economic Status | Distress | Appalachia (13 states) | Automated | Active | Yes (public domain) |
| 28 | USDA ERS Persistent Poverty Counties | Distress | National | Tolerated | Active | Yes (public domain) |
| 29 | **FL FDOR NAL** (per-county tax roll) | Parcels | FL (all 67 counties) | Automated (since 2026-07-03) | Active. Raw intact; normalized (11.18M parcels) and composed (recomposed 2026-05-29); shown in the app | Yes, with attribution |
| 30 | **Steel-in-the-Air** (free county-level lease benchmarks) | Lease comps | National (counties) | Tolerated | Reference benchmark only; never ingested, not redistributed, not on the demo | No (terms forbid reproduction beyond limited attributed quotation) |
| 31 | **Secretary of State business-entity lookups** | Officer disclosure | Per anchor state | Manual | Planned for **Phase 1 Slice D** (one-click in the lead-detail panel); never built | Yes (public records) |
| 32 | **UCC-1 filings** | Third-party-ownership clues | Per anchor state | Manual | Planned for **Phase 1 Slice D** (shown in the lead-detail panel); never built | Yes (public records) |
| 33 | **WV statewide parcels** (WVGISTC / SB 588) | Parcels | WV (all 55 counties) | Automated (since 2026-07-03) | Active | Yes, with attribution |

---

# Towers

## 1. FCC Antenna Structure Registration (ASR)

- **ID:** `fcc_asr` · **Cadence:** Weekly (Sundays) · **Size:** ~90 MB
- **Source page:** <https://www.fcc.gov/wireless/data/public-access-files-database-downloads>
- **Direct bulk:**
  `https://data.fcc.gov/download/pub/uls/complete/r_tower.zip`
  `https://data.fcc.gov/download/pub/uls/complete/d_tower.zip`
- **License:** Public domain (US federal government work).
- **Automation:** Automated. Bulk download is the access mode the Federal Communications Commission (FCC) intends.
- **Commercial use:** Yes.

### What's inside the zip
Pipe-delimited `.dat` files (no header row). Column order comes from
`asr_sql_table_definitions_3.txt`. The most important tables:

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
  `zip_code`, `phone`, `frn` (FCC Registration Number).

### Joins
`RA.registration_number ↔ CO.registration_number ↔ EN.registration_number`.

### Caveats
- Coordinates are in degrees-minutes-seconds (DMS). Convert to decimal,
  then negate longitude for the western hemisphere.
- Filter `status_code = 'C'` to limit to constructed structures.
- Older registrations may be off by tens to hundreds of metres
  (a known FCC data-quality limitation).

---

## 2-7. FCC Universal Licensing System (ULS)

**On-disk reality (corrected 2026-05-30).** Despite the per-band IDs in the index above, the FCC ships only **two** relevant bulk files, mirrored on disk as two raw source dirs:

- **`fcc_uls_cellular`** → `l_cell`: Part 22 site-based Cellular, a single radio service (`CL`).
- **`fcc_uls_market`** → `l_market`: the *Market-Based Services* bundle. It holds PCS, AWS, and 700 MHz **plus** WCS, 600 MHz, Narrowband PCS, paging, BRS/EBS and ~30 other geographic-area services, all interleaved in one table set and told apart only by the HD `radio_service_code`.

There is **no** separate `l_broad` / `l_aws` / `l_700` / `l_wcs` download. Those rows all live inside `l_market`.

**Phase 1 Slice A** (carrier identification; [ADR-053](./adr/0053-product-phase-shift.md) partially reverses ADR-013) normalizes **all of `l_cell`** plus the **PCS / AWS / 700 MHz `radio_service_code` subset of `l_market`**. Every other market service stays deferred, notably WCS and the separate Microwave file (`l_micro`). The normalizer (`scripts/preprocess/normalizers/fcc_uls.py`) writes the `cellular` band at `normalized/fcc_uls_cellular/` and the three market bands at `normalized/fcc_uls_market/{pcs,aws,700mhz}/`, each as canonical `license` / `location` parquet plus a `quality_report.json`. A `band` column on every row carries the classification downstream.

A `load_state_data` override reads the market bands' nested per-band layout into compose. Without it, the default flat-path loader saw zero market rows and every PCS/AWS/700 MHz carrier silently dropped (found by the data audit). The `entity` layer, formerly a third parquet per band, was **dropped** after the same audit. Compose built it but nothing consumed it, and the `license` layer already merges the licensee name and FRN it carried from EN `entity_type 'L'`.

### Radio-service-code → band classification (the Slice A scope decision)

| Band (in scope) | Source file | `radio_service_code`(s) |
|---|---|---|
| `cellular` | `l_cell` | `CL` |
| `pcs` | `l_market` | `CW` (Broadband PCS, Part 24) |
| `aws` | `l_market` | `AW` (AWS-1), `AT` (AWS-3), `AD` (AWS-4), `AH` (AWS H-Block); all Part 27 |
| `700mhz` | `l_market` | `WY`, `WZ` (Lower), `WU` (Upper C), `WX` (Guard band); all Part 27 (`WP` mapped, absent in the current extract) |

Excluded as out of band scope (a documented scope decision, **not** a quality filter): `WS` (WCS, deferred per ADR-013), `WT` (600 MHz), `CN` / `CY` (Narrowband PCS) and all other `l_market` services.

| ID | Band(s) | File | Approx size (zip) | Phase 1? |
|---|---|---|---|---|
| `fcc_uls_cellular` | Cellular (Part 22) | `l_cell.zip` | ~20 MB | **Yes (Slice A)** |
| `fcc_uls_market` | PCS + AWS + 700 MHz (+ deferred WCS / 600 / NB-PCS / paging / …) | `l_market.zip` | ~75 MB | **PCS/AWS/700 subset (Slice A)** |
| `fcc_uls_micro` | Microwave (Part 101) | `l_micro.zip` | ~185 MB | Deferred |

- **Cadence:** Weekly (Sundays) · **Base URL:** `https://data.fcc.gov/download/pub/uls/complete/`
- **Source page:** <https://www.fcc.gov/uls/transactions/daily-weekly>
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Schema (subset relevant to lease work)
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
`HD.usi ↔ EN.usi ↔ LO.usi ↔ FR.usi`. The Unique System Identifier
(`usi`) is the universal join key.

### Caveats
- ULS coordinates are *unreliable*. Use ULS for carrier presence (which
  licensees hold authorization at a site) and ASR for the actual tower
  coordinates. This is documented FCC guidance.

### ULS↔ASR matching (`asr_number` coverage and tolerance calibration)
The carrier join (`scripts/preprocess/joins/uls_to_asr.py`) relies on two
measured facts about the `LO` records:

- **`asr_number` coverage is bimodal, not uniform.** About **59% of Cellular**
  rows carry it (Part 22 is site-based, so most rows name the registered ASR
  tower) and **0% of PCS/AWS/700** rows do (Part 24/27 market licenses describe
  a licensed *area*, not a registered structure). So the exact cross-reference
  is a Cellular feature, and every PCS/AWS/700 match comes from the spatial
  fallback.
- **The "blank ULS coordinates" caveat does not hold for these site-based
  bands.** Lat/lon is populated ~100%. The problem is *drift*, not blankness.
  The true co-located ULS↔ASR distance is p95 ≈ 44 m (anchor states) / 64 m
  (national), ≤100 m on 97-98% of genuine pairs, and ≤500 m on 99.6-99.9%.
  That calibrates the confidence tiers: exact `asr_number` → `verified`,
  nearest ASR ≤100 m → `likely`, ≤500 m → `possible`, beyond that → refused
  (the far tail is data-entry garbage). Do not loosen the 100/500 m thresholds.

Regenerate the full coverage and drift analysis on demand (it reads normalized
parquet and recomputes nothing): `python scripts/audits/uls_asr_number_coverage.py`.

---

## 8. FAA Digital Obstacle File (DOF)

- **ID:** `faa_oeaaa` · **Cadence:** Daily · **Size:** ~12 MB
- **Source page:** <https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dof/>
- **Direct bulk:** `https://aeronav.faa.gov/Obst_Data/DAILY_DOF_DAT.ZIP`
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Structure
The Federal Aviation Administration (FAA) zip contains `DOF.DAT`, a
fixed-width text file. `DOF_README` in the same archive documents the
columns. Key columns:

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
| Height above ground level, AGL (ft) | 89-93 | |
| Height above mean sea level, AMSL (ft) | 95-99 | |

### Joins
Standalone. Useful as a complement to FCC ASR: DOF catalogues *any*
obstacle, while ASR is only the FCC-registered subset.

---

## 9. HIFLD Cellular Towers (removed)

**Removed from the repo on 2026-07-03.** DHS retired the public
Homeland Infrastructure Foundation-Level Data (HIFLD) Cellular Towers
layer in 2024 (ADR-015). The fetcher and normalizer were deleted because
the upstream can never come back as-is. It was a GeoJSON point layer used
as a cross-check against FCC ASR for towers under ~60 m. The number stays
so index rows 10+ keep their numbers.

---

# Solar

## 10. EIA Form 860 (annual)

- **ID:** `eia_860` · **Cadence:** Annual (~September release)
- **Size:** ~25 MB · **Source page:** <https://www.eia.gov/electricity/data/eia860/>
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Structure
The Energy Information Administration (EIA) zip contains many Excel
workbooks, one per Form 860 schedule. For solar work, the relevant sheets:

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
- **License, automation, commercial use:** same as EIA-860.

### Structure
A single Excel workbook with sheets `Operating`, `Planned`, `Retired`.
Key fields match Form 860. Use it for plants that came online between
annual 860 releases.

---

## 12. USGS USPVDB

- **ID:** `uspvdb` · **Cadence:** ~Annual · **Size:** ~40 MB
- **Source page:** <https://eerscmap.usgs.gov/uspvdb/>
- **Digital object identifier:** <https://doi.org/10.5066/P9IA3TUS>
- **Requested acknowledgement:** "Map services and data are available from Large-Scale Solar Photovoltaic Database, provided by the U.S. Geological Survey and Lawrence Berkeley National Laboratory via https://energy.usgs.gov/uspvdb" (reproduced in [NOTICE.md](../NOTICE.md))
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Structure
The US Geological Survey (USGS) U.S. Large-Scale Solar Photovoltaic
Database (USPVDB) download is a zip with a shapefile, a GeoPackage, and a
CSV of every ≥1 MW US solar PV facility. The features are **polygons**, not
points. Key attributes: `p_state`, `p_county`, `p_eia_id` (joins to EIA-860
`Plant Code`), `p_year`, `p_area`, `p_cap_dc`, `p_cap_ac`, `p_tech_sec`,
`p_axis`, `p_tilt`, `p_lulc_pre`.

### Joins
`p_eia_id ↔ EIA-860 Plant Code` for a crosswalk to owner and operator details.

---

## 13. LBNL Tracking the Sun

- **ID:** `lbnl_tts` · **Cadence:** Annual · **Size:** ~250 MB
- **Source page:** <https://emp.lbl.gov/tracking-the-sun>
- **License:** Lawrence Berkeley National Laboratory (LBNL) public-data terms: free use with citation.
- **Automation:** Tolerated. The fetcher scrapes the landing page to find the
  current-year link, then GETs it directly.
- **Commercial use:** Yes, with attribution.

### Structure
A single large CSV (sometimes published as a ZIP). One row per
distributed PV installation, ~3M+ rows. Key fields:

| Field | Notes |
|---|---|
| `data_provider_1` | Which utility or state programme reported it |
| `system_size_DC` | kW (DC) |
| `installation_date` | YYYY-MM-DD |
| `state` | |
| `zip_code` | **Address is masked to ZIP** for privacy |
| `city` | |
| `customer_segment` | RES / COM / IND / GOV / NPF |
| **`third_party_ownership`** | **The key field. `1` = leased or power purchase agreement (PPA), `0` = host-owned** |
| `installer_name` | |
| `inverter_loading_ratio`, `tracking`, `module_manufacturer`, … | technical detail |

### Notes for the preprocessor
- Addresses are city/ZIP only, so a precise parcel join is impossible.
  The best approach is *probabilistic* matching against a parcel layer:
  the count of third-party-owned (TPO) systems in each ZIP joined to the
  parcel density of likely residential single-family hosts.
- The TPO=1 subset is the renegotiable-lease subset.

---

# Billboards

## 14. FDOT Outdoor Advertising permits

- **ID:** `fdot_billboards` · **Cadence:** Monthly · **Size:** ~8 MB
- **Direct:** `https://www.fdot.gov/content/dam/fdotgov/files/maintenance/outdoor-advertising/oas-permit-extract.xlsx` (dead as of 2026-10-18; the Florida Department of Transportation (FDOT) moved its outdoor advertising pages, and the source never reached the active registry)
- **Source page:** <https://www.fdot.gov/rightofway/OutdoorAdvertising.shtm> · **Website policies:** <https://www.fdot.gov/agencyresources/webpoliciesandnotices.shtm>
- **License:** Florida public records · **Automation:** Automated · **Commercial use:** Yes

### Structure
A single Excel workbook (XLSX). Each row is a permitted sign. Key fields:
`Permit Number`, `Owner Name`, `County`, `Section`, `Subsection`,
`Mile Post`, `Side of Road`, `Latitude`, `Longitude`, `Height`,
`Status`, `Status Date`, `Issued Date`.

### Joins
Spatial join (lat/long) into a Florida parcel layer: source 29, FDOR NAL.
Source 18, FGDL, was the wrong dataset and was replaced per ADR-019.

### Notes
The best public billboard dataset in the US. FDOT may occasionally rename
or restructure the CMS path. If the puller hits a 404, use the source page
above to find the current link.

---

## 15. NCDOT Outdoor Advertising permits

- **ID:** `ncdot_billboards` · **Cadence:** On request · **Size:** ~5 MB est.
- **Source page:** <https://connect.ncdot.gov/business/Roadside/Pages/Outdoor-Advertising.aspx>
- **License:** NC public records (G.S. 132)
- **Automation:** Manual only. The North Carolina Department of Transportation
  (NCDOT) has no stable bulk URL, and it discourages scraping the search portal.
- **Commercial use:** Yes.

### Workflow
Email the NCDOT Roadside Environmental Unit to request the current
permit extract, or file a G.S. 132 records request. Drop the resulting
file into `data/raw/ncdot_billboards/current/`.

### Expected structure
Typically an Excel workbook with permit number, owner (sign company),
county, route, mile-marker, status, and dates. Coordinates may need
geocoding from route and mile-marker.

---

## 16. TxDOT Outdoor Advertising permits

- **ID:** `txdot_billboards` · **Cadence:** On request · **Size:** ~20 MB est.
- **Source page:** <https://www.txdot.gov/business/permits/outdoor-advertising.html>
- **License:** Texas public records (Government Code Ch. 552)
- **Automation:** Manual only. It needs a Texas Public Information Act (TPIA) request.
- **Commercial use:** Yes.

### Workflow
Submit a TPIA request to the Texas Department of Transportation (TxDOT)
Right of Way Division asking for "all outdoor advertising sign permits with
coordinates if available". Drop the file in `data/raw/txdot_billboards/current/`.

---

# Parcels

## 17. NC OneMap statewide parcels

- **ID:** `nc_onemap_parcels` · **Cadence:** Monthly (per county) · **Size:** ~10 GB on disk (1186 paginated GeoJSON files)
- **Source page:** <https://www.nconemap.gov/datasets/nconemap::north-carolina-parcels-polygons>
- **Bulk API (broken):** `https://www.nconemap.gov/api/download/v1/items/.../shapefile` returns a persistent HTTP 500 since mid-2026.
- **MapServer query (used by auto-fetch):** `https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1/query`
- **License:** Open data / NC public records
- **Automation:** Automated via MapServer pagination (ADR-048). It runs ~30-60 min unattended and resumes after an interruption.
- **Commercial use:** Yes, with attribution.

### Data status

`data/raw/nc_onemap_parcels/` was **deleted on 2026-05-20**. It held 8.3 GB:
1,106 of 1,186 pages, fetched before a server-side HTTP 504 stalled the
fetch. It needs a full re-fetch via the puller once the NC OneMap
endpoint is confirmed stable.

### Structure
On-disk layout: `data/raw/nc_onemap_parcels/current/page_NNNN.geojson`.
Each file is one GeoJSON FeatureCollection per 5000-feature page (5.9M
records total, so ~1186 pages). EPSG:4326. The normalizer's existing
GeoJSON rglob path picks them up without changes. MapServer field names are
lowercase (`ownname`, `mailadd`, `cntyfips` etc.). The field map in
`scripts/preprocess/normalizers/state_parcels.py` declares both casings
so it works with MapServer pages and with legacy shapefile bulk downloads.

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
| `STATCFIPS` | 5-digit state+county FIPS code |

### Notes
- The CRS is typically NC State Plane (EPSG:2264). The preprocessor
  reprojects to EPSG:4326.
- Per-county refresh cadence varies. The metadata service exposes the
  most recent edit timestamp for the entire layer.

---

## 18. Florida state-owned land parcels (FGDL DSL composite)

- **ID:** `fl_fgdl_parcels` · **Cadence:** Annual · **Size:** ~173 MB zip
- **Source page:** <https://fgdl.org/zips/geospatial_data/current/>
- **License:** Florida Geographic Data Library (FGDL) terms of use (free, with attribution)
- **Automation:** Automated (flipped from manual on 2026-07-03). The zip is a direct anonymous HTTPS download with no click-through and no login. The click-through only guards FGDL's *metadata explorer*, not the file directory, and robots.txt disallows only `/wp-admin/`. The release filename embeds month and year (`dsl_parcel_composite_oct25.zip`), so the fetcher discovers the newest file from the browsable listing, the same pattern as WV vintage discovery. The walkthrough stays as a fallback.
- **Commercial use:** Yes, with attribution.

### Role
Florida's Division of State Lands parcel composite covers **state-owned
land**, a distinct parcel class from the FDOR NAL private tax rolls
(source 29). It complements NAL rather than substituting for it: ~241K of
the FL composite's parcels come from this layer. A tower on state land is
not a private-landowner lead, and that is signal, not noise.

### Structure
A zipped File Geodatabase (`dsl_parcel_composite_<mon><yy>.gdb/`).
`FACILITY_NAME` (the managing facility, not a private owner),
`PLOT_ACREAGE_NBR`, `LAND_CATEGORY_NAME`, parcel keys
(`BTLDS_PARCEL_KEY` / `DSL_PARCEL_COMPOSITE_KEY`). County comes as
`COUNTY_NAME` only, with no FIPS code, so the adapter falls back to state FIPS 12.

---

## 19. Montana Cadastral

- **ID:** `mt_cadastral_parcels` · **Cadence:** Quarterly · **Size:** ~600 MB
- **Source page:** <https://msl.mt.gov/geoinfo/msdi/cadastral/> · **Service metadata (terms):** <https://gisservice.mt.gov/ArcGIS/rest/services/msdi_cadastral_map_v1/MapServer/info/iteminfo?f=pjson>
- **License:** Montana public records
- **Automation:** Automated (flipped from manual on 2026-07-03). The statewide SHP zip is a direct anonymous HTTPS download from the Montana State Library mirror (`ftpgeoinfo.msl.mt.gov`), with no click-through, no login, and no published robots.txt. The walkthrough stays as a fallback. The use-side caveats under Montana Code §2-6-1017 are unchanged.
- **Commercial use:** Yes, with attribution.

### Structure
A statewide shapefile with normalized owner, mailing, value, and acreage fields.

---

## 20. Minnesota statewide parcels (MnGeo)

- **ID:** `mn_parcels` · **Cadence:** Annual · **Size:** ~800 MB
- **Source page:** <https://gisdata.mn.gov/dataset/parcels-statewide>
- **License:** Minnesota Geospatial Commons terms (click-through)
- **Automation:** Manual only
- **Commercial use:** Yes, with attribution.

---

## 21. Indiana statewide parcels (IGIO)

- **ID:** `in_parcels` · **Cadence:** Annual · **Size:** ~1.5 GB
- **Source page:** <https://gis.iu.edu/dataset/infrastructure-real-estate/in-2024-parcels>
- **License:** Indiana public records (published by the Indiana Geographic Information Office, IGIO)
- **Automation:** Manual only
- **Commercial use:** Yes, with attribution.

---

## 22. Arkansas statewide parcels

- **ID:** `ar_parcels` · **Cadence:** Annual · **Size:** ~1.2 GB
- **Source page:** <https://gis.arkansas.gov/product/parcels/>
- **License:** Arkansas public records
- **Automation:** Manual only
- **Commercial use:** Yes, with attribution.

---

## 23. Utah UGRC LIR parcels (deferred, no owner data)

- **ID:** `ut_parcels` · **Cadence:** Quarterly · **Size:** ~900 MB
- **Source page:** <https://gis.utah.gov/products/sgid/cadastre/parcels/>
- **License:** Utah public records
- **Automation:** Manual only · **Registry:** Deferred
- **Commercial use:** Yes, with attribution.

**Deferred from the Phase 1 anchor set (ADR-049).** The Utah Geospatial
Resource Center (UGRC) publishes three parcel layers: the statewide
aggregate, the per-county basic parcels, and the per-county Land
Information Record (LIR) parcels for all 29 counties. All three carry
value, acreage, property class, year built, and situs address but **no
owner name**. The LIR standard omits owner name; the only owner-adjacent
field is `OWN_TYPE`, a private/government category. Owner data lives
behind per-county assessor portals with no bulk download. Indiana (source
21) has the same blocker. The source stays in the registry's deferred
block so it can be re-promoted if a Utah owner-data source ever appears.

---

## 24. Regrid (Landgrid) nationwide parcels

- **ID:** `regrid_parcels` · **Cadence:** Quarterly (or monthly at a premium tier) · **Size:** ~60 GB (nationwide tier)
- **Source page:** <https://regrid.com/api>
- **License:** Commercial bulk-data license (per signed agreement)
- **Automation:** Credentialed (needs a paid subscription)
- **Commercial use:** Yes, per license.

### Required env vars
Set these in `.env` at the project root (git-ignored):

```
REGRID_S3_BUCKET=<bucket Regrid provisions for you>
REGRID_S3_PREFIX=<your tenant prefix>
AWS_ACCESS_KEY_ID=<key Regrid issues>
AWS_SECRET_ACCESS_KEY=<secret>
```

Without these, the UI shows "Credentials required" and skips the source.

### Structure
Delivered in the format chosen in the Regrid agreement (GeoPackage,
shapefile, GeoJSON, CSV, or Parquet). The schema is uniform across all
50 states. Owner mailing address, value, acreage, and land use are all
included at the Premium / Property Tax tier.

The subscription is priced per state, per region, or nationwide. The
free-only budget (ADR-010 as reframed by ADR-057) kept it out of Phase 1.

---

## 33. West Virginia statewide parcels (WVGISTC / MapWV, SB 588)

- **ID:** `wv_parcels` · **Cadence:** Annual (summer/fall publish) · **Size:** ~527 MB (zipped File Geodatabase)
- **Source page:** <https://wvgis.wvu.edu/data/dataset.php?ID=371> (record) · **Direct bulk:** `https://data.wvgis.wvu.edu/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_<year>/WV_WVGISTC_Tax_<year>.gdb.zip`
- **License:** Free public service under WV Senate Bill 588 (2017). The MapWV terms (<https://www.mapwv.gov/terms.html>) allow copying and distribution "without obligation … unless otherwise stated", and the data is provided "as is", not as a survey.
- **Automation:** Automated (flipped from manual on 2026-07-03). The bulk `.gdb.zip` is an anonymous direct HTTPS download with no login or click-through. The fetcher discovers the newest `WVGISTC_<year>/` vintage from the open directory listing. The walkthrough stays as a fallback.
- **Commercial use:** Yes, with attribution. The terms of service were reviewed and are permissive: no commercial bar and no strict attribution requirement. Attribution to the custodians (the WVU GIS Technical Center, WVGISTC, and the WV Property Tax Division) is kept as prudent practice. Residual gap: the embedded `.gdb` FGDC metadata was not read exhaustively.

### Structure
One File Geodatabase covering all 55 counties, ~1.39M parcels (Tax Year 2025).
The record splits across two objects joined on **`CleanParcelID`**:

- **`MasterSurfWV_2025`** holds the parcel polygons (EPSG:26917, reprojected
  to 4326), a thin owner set (`FullOwnerName`/`FullOwnerAddress`/
  `FullPhysicalAddress`), `Acres_C`, and a 2-digit `CountyID`.
- **`ParcelSummary`** is a geometry-less attribute table holding the full WV
  IAS assessment record: granular owner (`Owner1`/`Owner2`), structured
  mailing (`OwnerCity`/`OwnerStateCode`/`OwnerZipCode`), appraised values
  (`LandAppraisal`/`BuildingAppraisal`/`TotalAppraisal`), land use
  (`LandUseCode`/`LandUse`), and `CountyName`/`CountyCode`.

The normalizer left-merges `ParcelSummary` onto the polygons via the
adapter's `AttributeJoin` (see `state_parcel_adapters/wv.py`), so the full
owner, value, and land-use detail reaches the canonical `parcel` schema.

### Caveats
- **Surface owner only.** The parcel names the SURFACE owner, and split
  estates (severed minerals) are the norm in rural WV. That surface owner is
  exactly the tower-lease target. Do **not** conflate it with mineral ownership.
- **County code ≠ Census FIPS.** WV's `CountyID`/`CountyCode` is an
  alphabetical 01-55 sequence that does not equal the Census ANSI FIPS code,
  because Census collates McDowell (54047) before Marion (54049). An explicit
  verified name/code → FIPS table resolves it, **not** a prefix concatenation.
- **Appraised, not assessed.** `TotalAppraisal` is total *appraised* value.
  WV statutory assessed value is 60% of appraised and is not a stored column.
- All 55 counties are Appalachian, so the ARC distress overlay covers 100% of WV.

---

# Distress

## 25. HUD Opportunity Zones

- **ID:** `hud_oz` · **Cadence:** Static (2018 designation; Opportunity Zone (OZ) 2.0 redesignations 2026-2028)
- **Size:** ~30 MB
- **Source page:** <https://www.arcgis.com/home/item.html?id=ef143299845841f8abb95969c01f88b5> (HUD's official item; credit: U.S. Department of Housing and Urban Development, U.S. Census Bureau)
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Structure
A Department of Housing and Urban Development (HUD) GeoJSON
FeatureCollection of ~8,700 census-tract polygons. Key fields:
`GEOID10` (11-digit tract FIPS code), `STATE_FIPS`, `COUNTY_FIPS`, `TRACT`,
`STATE_ABBR`, `STATE_NAME`, `RURAL` (`Y` if designated a rural OZ).

---

## 26. HUD Qualified Census Tracts (QCT)

- **ID:** `hud_qct` · **Cadence:** Annual · **Size:** ~50 MB
- **Source page:** <https://www.arcgis.com/home/item.html?id=f55f80843c9a436ba8e578a54cdd8cea> (HUD's official 2026 item; credit: U.S. Department of Housing and Urban Development, U.S. Census Bureau)
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Structure
A GeoJSON FeatureCollection of census tracts designated QCT: ≥50% of
households below 60% of Area Median Income (AMI), or a ≥25% poverty rate.
Use it as a secondary distress overlay alongside Opportunity Zones.

---

## 27. ARC County Economic Status (Appalachia)

- **ID:** `arc_distressed` · **Cadence:** Annual (fiscal year, June) · **Size:** ~0.3 MB
- **Source page:** <https://www.arc.gov/distressed-designation-and-county-economic-status-classification-system/>
- **License:** Public domain · **Automation:** Automated · **Commercial use:** Yes

### Structure
An Appalachian Regional Commission (ARC) Excel workbook keyed by 5-digit
county FIPS code. Each county is classified as one of `Distressed`,
`At-Risk`, `Transitional`, `Competitive`, `Attainment`. The workbook also
carries the three underlying components: 3-year unemployment, per-capita
market income, and poverty rate.

### Joins
County FIPS code. Joins to any county-level layer.

---

## 28. USDA ERS Persistent Poverty Counties

- **ID:** `usda_persistent_poverty` · **Cadence:** Per decennial census (~5 years) · **Size:** ~1 MB
- **Source page:** <https://www.ers.usda.gov/data-products/county-typology-codes>
- **License:** Public domain · **Automation:** Tolerated
- **Commercial use:** Yes.

### Structure
A US Department of Agriculture Economic Research Service (USDA ERS) CSV
keyed by county FIPS code. The persistent-poverty flag is one column. The
same file holds the broader ERS county-typology codes (urban/rural,
farming-dependent, mining-dependent, etc.).

### Joins
County FIPS code.

---

## 29. FL FDOR per-county PAR parcel shapefiles (PIN + NAL joined)

- **ID:** `fdor_nal` · **Cadence:** Annual (Map Data refresh each August) · **Size:** ~28 GB raw on disk (all 67 counties; the `.dbf` attribute tables dominate)
- **Source page:** <https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx>
- **Map Data directory:** linked from the Florida Department of Revenue (FDOR) page; this is where the PAR shapefiles live
- **License:** Florida public records (Ch. 119, F.S.). Commercial reuse is allowed with attribution.
- **Automation:** Automated (flipped from manual on 2026-07-03). The Map Data "directory" is a SharePoint document library whose anonymous REST API lists vintages and files, and every PAR zip is a direct anonymous HTTPS download. The presumed license click-through does not exist, and robots.txt permits the data portal. Vintage discovery walks newest-first past FDOR's pre-created empty folders (for example `2026F`). Re-runs resume, because per-county dirs that already exist are skipped. The walkthrough stays as a fallback.
- **Commercial use:** Yes, with attribution.

### Relationship to FGDL DSL (source 18)
FGDL DSL covers state-owned land, not private parcels, so it can't be
the private-landowner dataset. FDOR's per-county PAR shapefiles are the
canonical Florida private-parcel landowner data: every county's parcel
polygons joined with the current-year NAL tax roll. Phase 1 shipped all
67 Florida counties (ADR-047), and the DSL layer composes alongside as
the state-land complement.

### PIN vs PAR (per FDOR's Parcel Shapefiles Readme)
- **PIN** = parcel geometry only (FID + Shape + PARCELNO). **Skip.**
- **PAR** = PIN joined with current-year NAL attributes. **Use this.**

The standalone NAL/SDF text files in FDOR's Tax Roll Data File
directory hold the same attributes minus geometry. They aren't needed
because PAR has them merged.

### Phase 1 county set
**All 67 Florida counties** (per ADR-047). FDOR publishes one PAR ZIP
per county in the Map Data directory, and the walkthrough lists every
county alphabetically as a download checklist. **Miami-Dade and
St. Johns** ship separate condominium property records. Grab both
condo files (`miamidade_condos_2025par.zip`, `stjohnscondos_2025.zip`)
alongside the main per-county PAR ZIPs.

### Workflow
The puller's **Walk me through** button shows step-by-step
instructions: skim the Parcel Shapefiles Readme, open the Map Data
directory, pick the latest year, download all 67 PAR ZIPs (plus the
two condo extras), and upload them with the puller's Upload button, which
auto-extracts them into per-county subfolders. The normalizer uses rglob,
so the per-county subfolder layout needs no special handling.

### Structure
A per-county shapefile with NAL columns joined on PARCELNO. Key columns
(NAL standard):

- `PARCELNO`: county-namespaced parcel ID (join key)
- `OWN_NAME`, `OWN_ADDR1`, `OWN_CITY`, `OWN_STATE`, `OWN_ZIPCD`: owner block
- `JV`: just value (FL's term for assessed value)
- `AV_SD`: school district assessed value
- `LND_VAL`, `IMP_VAL`: land and improvement value split
- `DOR_UC`: use code (FDOR-standard taxonomy)
- `ACT_YR_BLT`: actual year built
- `TOT_LVG_AR`: total living area (sq ft)

Shapefile column names are capped at 10 characters, so some NAL fields
may be truncated in the .dbf. The normalizer handles the field-name mapping.

### Caveats
Per the FDOR readme, shapefile polygon counts won't exactly match NAL
record counts. Ch. 119 redactions, right-of-way polygons, unmapped condo
units, and ownership-unknown parcels can land on one side but not the
other. The normalizer keeps unmatched polygons with null owner columns
rather than dropping them.

### Joins
County FIPS code (derived from the filename) + PARCELNO. Joins to FCC ASR,
FAA, and HUD overlays via a point-in-polygon spatial join.

---

# Phase 1 additions (Slice D lead-detail panel enrichment, never built)

These three sources were scoped for the Slice D+E lead-detail panel. None
was wired into the registry or the backend before the project stopped.

## 30. Steel-in-the-Air free county-level lease benchmarks

- **ID:** `steel_in_the_air_free` · **Cadence:** Irregular (roughly annual) · **Size:** small (~MB)
- **Source page:** <https://www.steelintheair.com/cell-tower-lease-rates/>
- **License:** proprietary. The [terms of use](https://www.steelintheair.com/sita_terms_of_use-disclosures/) forbid reproducing, distributing, publishing, or creating derivative works from its content without written consent. The only exception is limited quotation for non-commercial informational purposes, with attribution to Steel in the Air, Inc.
- **Automation:** None. No fetcher was written and no data was downloaded.
- **Commercial use:** No.
- **How the project used it:** as a reference benchmark only, read by hand to sanity-check the scale of lease rents. None of its data is in the repo, the pipeline, or the public demo.

### Purpose

The plan was to bootstrap the `lease_comp` table in the Slice D+E backend
with rent-mean and rent-percentile estimates for ~3000 US counties, so the
UI could say *"this tower's rent is in the Nth percentile vs {county/region}."*
On 2026-05-26, data-source research found that no free Steel-in-the-Air
county-level lease-rate dataset exists. See [STATUS.md](./STATUS.md) for
the Slice D rescope.

The target schema was
`lease_comp(state, county, asset_type, source='steel_in_the_air_free', year, rent_mean, rent_p25, rent_p75, sample_size)`.
The paid Steel-in-the-Air tier has finer-than-county granularity and was
the Phase 2 option per [ADR-057](./adr/0057-budget-posture-reframed.md).

---

## 31. Secretary of State business-entity lookups (per anchor state)

- **IDs:** `sos_business_ar`, `sos_business_mt`, `sos_business_fl`, `sos_business_wv` (one per committed anchor) · **Cadence:** Live (on-demand lookup) · **Size:** N/A (no bulk download)
- **Source pages:**
  - AR: <https://www.sos.arkansas.gov/corps/search_corps.php>
  - MT: <https://biz.sosmt.gov/search/business>
  - FL: <https://search.sunbiz.org/>
  - WV: <https://apps.sos.wv.gov/business/corporations/>
- **License:** Public records (per-state public-information statutes)
- **Automation:** Per-state UX varies. Some portals allow direct URL queries; others need search form posts. The backend would have wrapped each state's quirks.
- **Commercial use:** Yes.

### Purpose

The Slice D+E lead-detail panel was to offer a **one-click "look up LLC
officers"** button per lead. It would return the publicly disclosed
managers, officers, and registered-agent details for the LLC named on the
parcel. This is **not** identity resolution: these are officers the entity
itself registered publicly ([ADR-057](./adr/0057-budget-posture-reframed.md)
narrowing of ADR-041).

### Design notes

- The backend would cache lookups per `tenant_id`-scoped `(state, entity_name)`
  for a TTL (~30 days) to avoid hammering Secretary of State endpoints.
- Each state's UX is bespoke. FL's Sunbiz is well structured; other states'
  portals need more parsing. Each anchor state would need its own adapter.

---

## 32. UCC-1 filings (per anchor state)

- **IDs:** `ucc1_ar`, `ucc1_mt`, `ucc1_fl`, `ucc1_wv` (one per committed anchor) · **Cadence:** Live (on-demand lookup) · **Size:** N/A (no bulk download)
- **Source pages:** each state Secretary of State's Uniform Commercial Code (UCC) search (the same portals as source 31, on a separate UCC tab)
- **License:** Public records.
- **Automation:** Per-state lookup; bespoke adapters.
- **Commercial use:** Yes.

### Purpose

The Slice D+E lead-detail panel was to show these as **third-party-ownership
clues**. UCC-1 financing statements name secured parties. That helps confirm
whether an asset (often a solar system, occasionally tower equipment) is
third-party-owned and so on a renegotiable contract.

### Caveat

UCC-1 lookups by debtor name return many irrelevant filings: any UCC filing
the debtor has, not just real-estate-related ones. The design was for the
panel to filter or label by filing date and secured-party patterns rather
than try to be exhaustive.

---

## Per-source on-disk layout

All sources land at `data/raw/<source_id>/current/`. Example after a
pull of FCC ASR + HUD OZ:

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
└── hud_oz/
    └── current/
        └── opportunity_zones.geojson
```

The preprocessor reads from `data/raw/<source_id>/current/` only. It
never reads from `.partial/` (transient) or any temporary download path.

---

## Manifest

The puller writes `data/manifest.json`, recording per source:
- `local_version`: version of what's on disk
- `remote_version`: version the publisher last advertised
- `fetched_at` / `checked_at`: ISO 8601 timestamps
- `bytes`: total disk usage of `current/`
- `files`: relative paths under `data/raw/`
- `status`: one of `ok`, `stale`, `missing`, `check_failed`,
  `fetch_failed`, `manual_only`, `needs_credentials`
- `error`: the last error message, if any

The preprocessor can read this file to (a) verify the input version it's
consuming and (b) fail fast if a required source is missing.

---

## Adding a new source

1. Add `scripts/fetch/sources/<your_source>.py` defining a subclass of
   `DataSource` exported as `SOURCE` (or `SOURCES` for a list).
2. Import it in `scripts/fetch/registry.py` and append it to `_ACTIVE`
   (or `_DEFERRED` if it is outside the Phase 1 scope; see ADR-045).
3. Document it here with the same headings (Cadence / Size / Source /
   Direct URL / License / Automation / Commercial use / Structure / Joins).
4. Restart the puller. The new source appears in its category group.
