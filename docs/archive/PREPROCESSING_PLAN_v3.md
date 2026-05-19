# PREPROCESSING_PLAN.md

Design document for the data-preprocessing layer. Read this before
writing any preprocessing code. Outputs feed the map app at `app/` and
all future analytical/feature/ML work.

Status: **PLAN (v3, finalised, max-functionality pass) — not implemented yet.**
Existing `scripts/preprocess.py` is the v1 NC-only one-shot; this
document replaces it.

This plan deliberately over-builds the structure (registry-driven
normalizers, joins, and views; dual GeoParquet + GeoJSON outputs;
full-fidelity raw preservation; time-series fields; geometry
derivatives; reserved canonical types for ML/aggregations) so that
**any future map-app feature, analytical query, or ML pipeline is a
config change, not a preprocessor rewrite.**

---

## 1. Principles

1. **Per-source Normalizer, registry-driven Joins, registry-driven Views.**
   Three independent extension points:
   - A new raw source = write one `Normalizer`. Nothing else changes.
   - A new spatial relationship = write one `Join`. Composer picks it up
     automatically.
   - A new map-app feature ("show me parcels owned by an LLC near a
     tower in an OZ") = write one `View`. Doesn't touch existing code.

2. **Dual output format.** Every dataset writes BOTH:
   - **GeoParquet** — the canonical analytical format. Columnar,
     compressed, typed, column-projection-capable. Fast to read for
     analysis, ML, joins, filtering.
   - **GeoJSON** — only for outputs the browser-based map app loads.
     Slower and larger, but browsers can load it directly.

3. **State-level geographies.** Composer runs per state. Dropdown in
   the UI auto-populates from "which states do we have parcel data for".

4. **Process everything.** Normalize stage runs every source that has
   data. Compose stage runs every state that has parcel coverage.

5. **Idempotent + incremental.** Re-runs skip sources whose
   `local_version` hasn't changed AND whose normalized output exists.
   UI has a **Force rebuild** checkbox.

6. **Schema versioning.** Every canonical schema has a `_schema_version`
   integer. Composer / Views fail loudly on mismatches.

7. **Provenance baked in.** Every record carries `_source`,
   `_processed_at`, `_schema_version`.

8. **Fail loudly per source.** A broken FCC parse fails FCC's normalize,
   logs it, and lets the rest run.

9. **Quality reports.** Each Normalizer emits a `quality_report.json`
   with row counts, null-rates per critical field, coordinate-out-of-
   bounds counts.

10. **No new dependencies in Phase 1.** `geopandas` + `pandas` +
    `pyproj` + `shapely` + `pyogrio` are all installed. PyArrow ships
    with pyogrio. (Phase 2 may add `tippecanoe` for vector tiles —
    flagged before installing.)

### Max-fidelity principles (new in v3)

11. **Full-fidelity raw preservation.** Every Normalizer writes BOTH:
    - `raw.parquet` — every column from the source, untouched
      (renamed only to legal Parquet names if necessary), all rows,
      no filtering. This is the lossless archive.
    - `<canonical_type>.parquet` — the canonical-schema view derived
      from the raw. May filter, rename, retype, derive columns.
    Future questions ("what's in the source's hidden `_dor_remarks`
    field?") get answered without re-downloading.

12. **No aggressive filtering at normalize time.** Examples of what
    NOT to do at normalize: filter ASR to `status_code='C'` only,
    drop parcels with null owner, drop ULS licenses past expiration.
    Instead: preserve everything, add status/validity columns, let
    Joins and Views filter when needed. Future analyses may want the
    "thrown-away" data.

13. **Time-series ready.** Every canonical schema has:
    - `valid_from` (date) — when this record first appeared in upstream
    - `valid_to` (date | null) — null = still current
    On re-run, records that disappear from upstream get `valid_to` set
    instead of being deleted. This enables longitudinal analyses
    (tower decommissioning, OZ designation changes, parcel ownership
    transfers over time).

14. **Geometry derivatives baked in.** Every polygon record gets:
    - `geom_centroid` (Point) — for fast "show me on map" at low zoom
    - `geom_area_m2` (float) — for filtering / sorting
    - `geom_bbox` (4 floats) — for fast spatial pre-filtering
    - `geom_simplified` (Geometry) — Douglas-Peucker @ 10m tolerance,
      for fast browser rendering of huge layers
    Every point record gets:
    - `geom_h3_r8` (string) — H3 index at resolution 8 (~0.7 km²),
      for fast clustering / density / proximity queries
    These cost ~5% storage but unlock dozens of future map features
    without recomputation.

15. **Discoverable outputs.** Every state composite directory has a
    `catalog.json` listing every output file, its schema, row count,
    column descriptions, and the Views available. The map app and any
    future client can read this and adapt — no hardcoded paths,
    no hardcoded toggles. Self-documenting.

16. **Reserved future fields.** Every canonical schema reserves
    columns that aren't used yet but won't require a schema bump
    later:
    - `_tenant_id` (string, default `'pilot'`) — for future
      multi-user / multi-customer scenarios
    - `_quality_score` (float 0–1, default `null`) — for future
      record-confidence scoring (e.g. when one tower has conflicting
      data across ASR / ULS / HIFLD)

---

## 2. Why GeoParquet (and when GeoJSON)

GeoParquet wins on every technical metric except browser compatibility:

| | GeoParquet | GeoJSON |
|---|---|---|
| File size (NC parcels) | ~4 MB | ~34 MB |
| Read time (full) | 100ms | 3s |
| Read time (3 columns) | 20ms | 3s (must parse all) |
| Strong types | yes | no |
| Column projection | yes | no |
| Browser-loadable | no | yes |
| Geopandas support | native | native |

**Decision: always write both.** Parquet is the analytical default;
GeoJSON only exists for browser consumption.

Phase 2 optional third format: **vector tiles** (`tippecanoe`-generated
MBTiles or PMTiles) for layers that exceed ~50 MB GeoJSON (statewide
parcels). The map app can switch to vector tiles for those layers
while keeping GeoJSON for small overlays. Hook reserved; not built in
Phase 1.

---

## 3. Directory layout

```
data/
├── raw/                              # puller writes here (existing)
│   └── <source_id>/current/...
├── processed/
│   ├── normalized/                   # ── Stage A: per-source canonical
│   │   ├── fcc_asr/
│   │   │   ├── raw.parquet                  # ← v3: full-fidelity source
│   │   │   ├── towers.parquet               # canonical view
│   │   │   ├── towers.geojson               # for map app
│   │   │   └── quality_report.json
│   │   ├── nc_onemap_parcels/
│   │   │   ├── raw.parquet                  # every column NC OneMap had
│   │   │   ├── parcels.parquet
│   │   │   ├── parcels.geojson
│   │   │   └── quality_report.json
│   │   ├── arc_distressed/
│   │   │   ├── raw.parquet
│   │   │   ├── county_scores.parquet
│   │   │   └── quality_report.json
│   │   ├── fcc_uls_cellular/
│   │   │   ├── raw.parquet                  # all FCC ULS bytes
│   │   │   ├── licenses.parquet
│   │   │   ├── locations.parquet
│   │   │   ├── entities.parquet
│   │   │   └── quality_report.json
│   │   └── ...
│   ├── composite/                    # ── Stage B: per-state joined
│   │   ├── 37/                       # NC FIPS
│   │   │   ├── towers.parquet
│   │   │   ├── towers.geojson
│   │   │   ├── parcels.parquet              # with geom derivatives + reverse joins
│   │   │   ├── parcels.geojson
│   │   │   ├── parcels.simplified.geojson   # ← v3: for browser perf
│   │   │   ├── opportunity_zones.geojson
│   │   │   ├── solar_facilities.parquet
│   │   │   ├── billboards.parquet
│   │   │   ├── views/
│   │   │   │   ├── towers_with_landowner.parquet
│   │   │   │   ├── towers_with_landowner.geojson
│   │   │   │   ├── parcels_hosting_infra.parquet
│   │   │   │   ├── llc_owned_parcels_with_infra.parquet
│   │   │   │   ├── distressed_parcels_hosting_infra.parquet
│   │   │   │   ├── owner_clusters.parquet
│   │   │   │   ├── county_summary.parquet
│   │   │   │   ├── state_summary.parquet
│   │   │   │   └── interestingness_top_1000.parquet
│   │   │   ├── catalog.json                 # ← v3: self-documenting
│   │   │   └── summary.json
│   │   ├── 12/                       # FL FIPS — same layout
│   │   ├── 27/                       # MN FIPS — same layout
│   │   └── ...
│   └── preprocess_manifest.json
└── manifest.json                     # puller's raw manifest (existing)
```

`preprocess_manifest.json` schema:

```json
{
  "schema_version": 3,
  "normalized": {
    "<source_id>": {
      "raw_local_version": "...",
      "preprocessed_at": "<ISO 8601>",
      "raw_rows": <int>,
      "canonical_rows": <int>,
      "bytes": <int>,
      "schema_version": <int>,
      "status": "ok" | "failed" | "skipped" | "unavailable",
      "error": null | "...",
      "quality_report_path": "...",
      "history": [
        {"preprocessed_at": "...", "raw_rows": ..., "canonical_rows": ..., "status": "ok"}
      ]
    }
  },
  "composed": {
    "<state_fips>": {
      "preprocessed_at": "<ISO 8601>",
      "sources_used": ["fcc_asr", "nc_onemap_parcels", ...],
      "joins_applied": ["TowerToParcel", "ParcelToDistress", ...],
      "views_built": ["towers_with_landowner", "owner_clusters", ...],
      "counts": {
        "towers": <int>,
        "parcels": <int>,
        "towers_matched_to_landowners": <int>,
        "parcels_in_oz": <int>,
        "parcels_in_qct": <int>,
        "llc_owned_parcels": <int>,
        ...
      },
      "status": "ok" | "failed",
      "error": null | "..."
    }
  }
}
```

`catalog.json` per state (auto-generated, consumed by map app):

```json
{
  "state_fips": "37",
  "state_name": "North Carolina",
  "generated_at": "<ISO 8601>",
  "layers": {
    "towers": {
      "path": "towers.geojson",
      "parquet_path": "towers.parquet",
      "geometry_type": "Point",
      "rows": 9427,
      "schema": {...},
      "description": "FCC ASR registered antenna structures..."
    },
    "parcels": { ... },
    ...
  },
  "views": {
    "towers_with_landowner": {
      "path": "views/towers_with_landowner.geojson",
      "rows": 11,
      "description": "Towers successfully matched to a parcel owner.",
      "inputs": ["tower"]
    },
    "llc_owned_parcels_with_infra": { ... },
    ...
  }
}
```

---

## 4. Canonical schemas

Every Normalizer writes one or more of these. EPSG:4326. Fields not
present in the source are left null. Filter-eligible columns are
preserved at normalize time (don't filter; flag).

**Every record gets these system columns automatically:**

```
_source            string          source_id from the puller
_source_row_id    string          opaque pointer back into raw.parquet
_processed_at     timestamp        UTC
_schema_version   int
_tenant_id        string           reserved; default 'pilot'
_quality_score    float | null     reserved; per-record confidence 0..1
valid_from        date             when this record first appeared
valid_to          date | null      null = still in upstream
```

### `tower` (Point geometry + derivatives)

```
asr_number       string         primary key
owner_name       string
height_m         float | null
structure_type   string         ASR code
status           string         'constructed' | 'granted' | 'cancelled' | 'dismantled' | ...
is_active        bool           derived: status in ('constructed','granted')
date_built       date | null
date_dismantled  date | null
street, city, state, zip  string | null
county_fips      string         5-digit
state_fips       string         2-digit
lat, lon         float
geom_h3_r8       string         H3 cell index (~0.7 km²)
extras           json           source-specific extras
raw_row_ref      string         pointer to raw.parquet row
```

### `parcel` (Polygon geometry + derivatives + reverse joins)

```
parcel_id            string     county PIN (raw)
parcel_id_full       string     state+county+PIN (globally unique)
owner_name           string
owner_name_2         string | null
owner_kind           string     'individual' | 'llc' | 'trust' | 'gov' | 'partnership' | 'corporation' | 'unknown'
owner_name_norm      string     uppercased, trimmed, punctuation-stripped — for clustering
mailing_addr         string
mailing_addr_norm    string     normalized for clustering
mailing_city, state, zip  string | null
situs_addr           string | null
situs_city, state, zip   string | null
acreage              float | null
land_value           float | null
improvement_value    float | null
assessed_value       float | null
land_use_code        string | null
land_use_desc        string | null
year_built           int | null
county_fips          string
state_fips           string
extras               json

# Geometry derivatives (computed at normalize time)
geom_centroid        point
geom_area_m2         float
geom_bbox            json       [minx, miny, maxx, maxy]
geom_simplified      polygon    Douglas-Peucker @ 10m

# Reverse-join columns (populated at compose time)
has_tower            bool       (default false; set true by TowerToParcelJoin)
tower_count          int        (default 0)
has_solar            bool
solar_count          int
has_billboard        bool
billboard_count      int
infrastructure_summary  json    [{"type":"tower","id":"1234567","owner":"..."}, ...]
in_oz                bool
in_qct               bool
distress_overlays    json       ["opportunity_zone", "qct"]
distress_tier        string     from ARC: 'distressed' | 'at-risk' | ...
persistent_poverty   bool
interestingness_score float     0..1 (from InterestingnessScoreJoin)
```

### `distress_overlay` (Polygon)

```
overlay_type     string         'opportunity_zone' | 'qct' | 'persistent_poverty' | ...
geoid            string
state_fips, county_fips, tract  string | null
rural_flag       bool | null
attributes       json
geom_centroid    point
geom_area_m2     float
geom_bbox        json
geom_simplified  polygon
```

### `county_score` (Tabular)

```
county_fips         string      5-digit primary key
tier                string      'distressed' | 'at-risk' | 'transitional' | 'competitive' | 'attainment'
score               float | null
persistent_poverty  bool | null
arc_distressed      bool | null
arc_at_risk         bool | null
sources             json        ["arc", "usda_persistent_poverty"]
```

### `solar_facility` (Point OR Polygon — both kept when source has both)

```
facility_id      string         primary key
name             string
operator         string | null
capacity_mw      float
online_date      date | null
retired_date     date | null
is_operational   bool
technology       string | null
tracking_type    string | null
county_fips, state_fips  string
geom             point | polygon | both
geom_centroid    point          for polygon facilities
geom_area_m2     float | null
geom_h3_r8       string
extras           json
```

### `billboard` (Point)

```
permit_no        string
owner            string
status           string
state_fips, county_fips  string
route            string | null
mile_marker      float | null
issue_date       date | null
lat, lon         float
geom_h3_r8       string
extras           json
```

### `license` (Tabular — FCC ULS per-band)

```
usi              string         primary key
call_sign        string
licensee_frn     string
licensee_name    string
service          string         'cellular' | 'market' | 'micro' | ...
radio_service_code string
grant_date       date | null
expired_date     date | null
status           string
is_active        bool           derived
```

### `location` (Tabular — FCC ULS LO.dat)

```
usi              string         joins to license.usi
location_number  int
location_class   string
site_status      string
lat, lon         float | null   ULS coords unreliable
location_addr    string | null
county_fips      string | null
geom_h3_r8       string | null
```

### `entity` (Tabular — FCC ULS EN.dat / Ownership Form 602)

```
frn              string         primary key
name             string
name_norm        string         for clustering
entity_type      string         'CO' | 'IN' | 'GO' | ...
address, city, state, zip
phone            string | null
parent_frn       string | null  from o_uls — controlling parent
ultimate_parent_frn string | null   computed: walk the parent_frn chain
```

### `transfer` (Tabular — FCC ULS Assignments & Transfers)

```
file_number      string
filing_date      date
transfer_type    string         'assignment' | 'transfer'
from_frn         string
to_frn           string
licenses_affected jsonb        list of usi
```

### `lease` (Tabular — FCC ULS Spectrum Leasing Form 608)

```
lease_id         string
file_number      string
lessor_frn       string
lessee_frn       string
start_date, end_date  date | null
licenses_affected jsonb
```

### `distributed_pv` (Tabular — LBNL TTS)

```
record_id        string
state_fips, zip  string
city             string
installation_date date
system_size_kw   float
customer_segment string         'RES' | 'COM' | 'IND' | 'GOV' | 'NPF'
third_party_ownership bool
installer_name   string
```

### Reserved canonical types (v3 — for forward-compat)

**`aggregation`** (Tabular) — for pre-computed rollups (per-county
summary, per-state summary, etc.):

```
aggregation_id   string         e.g. 'county_summary:37075'
aggregation_type string         'county_summary' | 'state_summary' | 'h3_density' | ...
key              json           e.g. {"county_fips": "37075"}
metrics          json           e.g. {"tower_count": 11, "parcel_count": 9427, ...}
generated_from   json           list of source_ids used
```

**`model_prediction`** (Tabular) — for ML outputs (interestingness
scores, classification results, regression outputs):

```
prediction_id    string         primary key
model_name       string         e.g. 'tower_lease_value_v1'
model_version    string
target_type      string         'tower' | 'parcel' | 'county'
target_id        string         the asr_number / parcel_id_full / fips
predicted_value  float | null
predicted_class  string | null
confidence       float
features_used    json
predicted_at     timestamp
```

**`address_point`** (Point) — for future geocoded address layers:

```
address_id       string
original_addr    string
normalized_addr  string
lat, lon         float
geocoder         string         e.g. 'census' | 'nominatim'
match_quality    float
county_fips, state_fips  string
```

Reserving these types now means Phase 2/3 features that need them
don't trigger schema-bump migrations.

---

## 5. Normalizer interface

```python
# scripts/preprocess/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

CURRENT_SCHEMA_VERSIONS = {
    'tower': 1, 'parcel': 1, 'distress_overlay': 1, 'county_score': 1,
    'solar_facility': 1, 'billboard': 1, 'license': 1, 'location': 1,
    'entity': 1, 'transfer': 1, 'lease': 1, 'distributed_pv': 1,
    'aggregation': 1, 'model_prediction': 1, 'address_point': 1,
}


@dataclass
class NormalizeResult:
    raw_rows: int
    canonical_rows: int
    bytes: int
    output_files: list[Path]
    quality_report: dict


class Normalizer(ABC):
    """One Normalizer per raw source. Reads from raw/<source_id>/current/,
    writes raw.parquet (full fidelity) + canonical .parquet/.geojson +
    quality_report.json to processed/normalized/<source_id>/.
    """
    source_id: str
    canonical_types: list[str]

    @abstractmethod
    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        """Read raw_dir, write:
          - raw.parquet                 (all source columns; no filtering)
          - <type_name>.parquet         (canonical view of raw)
          - <type_name>.geojson         (if geometry)
          - quality_report.json
        """

    def is_available(self, raw_dir: Path) -> bool:
        return raw_dir.exists() and any(raw_dir.rglob("*"))

    # Default implementations provided in base.py:
    def write_raw(self, df, out_dir): ...           # writes raw.parquet
    def derive_geometry_columns(self, gdf): ...     # adds centroid/area/h3
    def add_system_columns(self, df): ...           # adds _source/_processed_at etc.
    def compare_to_previous(self, out_dir): ...     # detects new/disappeared rows,
                                                    # sets valid_from/valid_to
```

The base class does the boring stuff (system columns, geometry
derivatives, raw.parquet write, valid_from/valid_to bookkeeping) so each
subclass only writes the source-specific column mapping logic.

---

## 6. Join + View registries

```python
class Join(ABC):
    inputs: list[str]
    annotates: str
    columns_added: list[str]

    @abstractmethod
    def apply(self, ctx: 'ComposeContext') -> None: ...


class View(ABC):
    name: str
    inputs: list[str]
    description: str
    write_geojson: bool = False    # most views are parquet-only; map-app-facing ones flip this

    @abstractmethod
    def build(self, ctx: 'ComposeContext'): ...
```

### Built-in Phase-1 Joins

```python
@register_join
class GeometryDerivativesJoin(Join):
    """Already done at normalize time, but re-runs after any spatial filter
    so simplified-geometry columns stay accurate post-clip."""
    inputs = ['parcel', 'distress_overlay', 'solar_facility']
    annotates = '*'

@register_join
class TowerToParcelJoin(Join):
    inputs = ['tower', 'parcel']
    annotates = 'tower'
    columns_added = ['parcel_id_full', 'parcel_owner', 'parcel_value',
                     'parcel_acreage', 'parcel_use_code']

@register_join
class ParcelHostsInfraJoin(Join):
    """Sets has_tower/tower_count/has_solar/etc + infrastructure_summary
    on parcels. Runs after TowerToParcel, SolarToParcel, BillboardToParcel."""
    inputs = ['parcel', 'tower', 'solar_facility', 'billboard']
    annotates = 'parcel'
    columns_added = ['has_tower','tower_count','has_solar','solar_count',
                     'has_billboard','billboard_count','infrastructure_summary']

@register_join
class ParcelToDistressJoin(Join):
    inputs = ['parcel', 'distress_overlay']
    annotates = 'parcel'
    columns_added = ['in_oz', 'in_qct', 'distress_overlays']

@register_join
class TowerToDistressJoin(Join): ...

@register_join
class SolarToParcelJoin(Join): ...

@register_join
class BillboardToParcelJoin(Join): ...

@register_join
class CountyScoreToParcelJoin(Join):
    inputs = ['parcel', 'county_score']
    annotates = 'parcel'
    columns_added = ['distress_tier', 'persistent_poverty']

@register_join
class CountyScoreToTowerJoin(Join): ...

@register_join
class CountyScoreToSolarJoin(Join): ...

@register_join
class OwnerClusterJoin(Join):
    """Group parcels by owner_name_norm + mailing_addr_norm to detect
    multi-parcel owners. Annotates each parcel with cluster_id + cluster_size."""
    inputs = ['parcel']
    annotates = 'parcel'
    columns_added = ['owner_cluster_id', 'owner_cluster_size',
                     'owner_cluster_value_total']

@register_join
class InterestingnessScoreJoin(Join):
    """Compute outreach-priority score per parcel: combines hosts-infra,
    in-distress, owner-is-LLC, owner-cluster-size. 0..1."""
    inputs = ['parcel']
    annotates = 'parcel'
    columns_added = ['interestingness_score', 'interestingness_components']

@register_join
class EntityToLicenseJoin(Join):       # Phase 2
    """Walk parent_frn chain to attach ultimate_parent_frn to each license."""
    inputs = ['license', 'entity']
    annotates = 'license'

@register_join
class LicenseToTowerJoin(Join):        # Phase 2 — careful, ULS coords unreliable
    """Match active cellular licenses to towers by ASR registrant FRN
    OR by location proximity (fallback). Adds carrier_count per tower."""
    inputs = ['tower', 'license', 'entity', 'location']
    annotates = 'tower'
    columns_added = ['carrier_count', 'carrier_names', 'license_count']
```

### Built-in Phase-1 Views

```python
@register_view
class TowersWithLandownersView(View):
    name = 'towers_with_landowner'
    write_geojson = True
    inputs = ['tower']
    description = 'Towers that successfully matched to a parcel.'

@register_view
class ParcelsHostingInfraView(View):
    name = 'parcels_hosting_infra'
    write_geojson = True
    inputs = ['parcel']
    description = 'Parcels hosting any tower / billboard / solar.'

@register_view
class LlcOwnedParcelsWithInfraView(View):
    name = 'llc_owned_parcels_with_infra'
    write_geojson = True
    inputs = ['parcel']
    description = ('Parcels owned by LLCs that host any infrastructure — '
                   'highest-value outreach segment.')

@register_view
class DistressedParcelsHostingInfraView(View):
    name = 'distressed_parcels_hosting_infra'
    write_geojson = True
    inputs = ['parcel']
    description = 'Same as above but filtered to OZ/QCT/distressed counties.'

@register_view
class OwnerClustersView(View):
    name = 'owner_clusters'
    inputs = ['parcel']
    description = ('Owners holding multiple parcels — useful for portfolio '
                   'outreach. Aggregated by owner_cluster_id.')

@register_view
class CountySummaryView(View):
    name = 'county_summary'
    inputs = ['tower', 'parcel', 'solar_facility', 'billboard', 'county_score']
    description = 'Per-county rollup: counts, distress tier, infra density.'

@register_view
class StateSummaryView(View):
    name = 'state_summary'
    inputs = ['tower', 'parcel', 'solar_facility', 'billboard']
    description = 'Per-state rollup: counts, top-N owners, top-N counties.'

@register_view
class InterestingnessTop1000View(View):
    name = 'interestingness_top_1000'
    write_geojson = True
    inputs = ['parcel']
    description = ('Top 1,000 parcels by interestingness_score — default '
                   'outreach list. Map app loads this for instant overlay.')
```

**Adding a new map-app feature → just write a View.** The Composer
auto-discovers it; the map app auto-renders a toggle for it (via
`catalog.json`).

---

## 7. State registry

```python
@dataclass(frozen=True)
class StateGeography:
    fips: str       # '37'
    abbr: str       # 'NC'
    name: str       # 'North Carolina'
    bbox: tuple[float, float, float, float]

STATES: dict[str, StateGeography] = {
    '01': StateGeography('01', 'AL', 'Alabama', (-88.47, 30.14, -84.89, 35.01)),
    # ... all 50 + DC + 5 territories
    '37': StateGeography('37', 'NC', 'North Carolina', (-84.32, 33.84, -75.46, 36.59)),
    ...
}

def states_with_parcel_data(preprocess_manifest) -> list[StateGeography]:
    """States we have ≥1 parcel normalize output for — what the UI shows."""
```

---

## 8. The Composer

```python
@dataclass
class ComposeConfig:
    state: StateGeography
    force_rebuild: bool = False
    skip_views: list[str] = field(default_factory=list)
    skip_joins: list[str] = field(default_factory=list)


def compose(cfg: ComposeConfig) -> ComposeResult:
    """1. Load each canonical type from processed/normalized/*
          filtered to cfg.state.fips.
       2. Run every registered Join (in dependency order).
       3. Run every registered View.
       4. Write composite/<state_fips>/<type>.parquet + .geojson +
          .simplified.geojson (for large layers).
       5. Write composite/<state_fips>/views/<view_name>.parquet (+ .geojson
          if View.write_geojson).
       6. Write composite/<state_fips>/catalog.json.
       7. Write composite/<state_fips>/summary.json."""
```

---

## 9. Performance considerations

For large states (FL parcels ~9M, MN ~2.7M, NC ~3.4M):

- **GeoParquet column projection.** Most joins / views only need a few
  columns.
- **Spatial indexes default-on** in `geopandas.sjoin`.
- **Per-state pre-filter.** Filter on `state_fips` before any spatial
  work.
- **Streaming reads** via `pyogrio.read_dataframe(skip_features=...)`
  for sources that don't fit in memory.
- **Chunked Parquet writes** for sources > 2 GB.
- **`geom_simplified` for browser GeoJSON output.** Statewide parcels
  full-resolution = 100s of MB GeoJSON; simplified = ~10x smaller.
- **H3 indexing for proximity queries.** Pre-computing
  `geom_h3_r8` makes "all towers within 5 km of X" O(1) lookup.

Phase 2 optional: **vector tiles via tippecanoe** for statewide parcels
that exceed browser-friendly GeoJSON sizes. Hook reserved; flag
before adding the dependency.

Memory budget: 16 GB local machine. Statewide composes fit; nationwide
compose flagged as Phase 3+ (Dask territory).

---

## 10. Per-source Normalizer mapping

| Source | Canonical type(s) | Normalizer file | Phase |
|---|---|---|---|
| `fcc_asr` | tower | `fcc_asr.py` | 1 |
| `faa_oeaaa` | tower | `faa_oeaaa.py` | 1 |
| `hifld_towers` | tower | `hifld_towers.py` (skips if empty) | 1 |
| `fcc_uls_cellular`/`market`/`micro` | license, location, entity | `fcc_uls.py` | 2 |
| `fcc_uls_ownership` | entity | `fcc_uls_ownership.py` | 2 |
| `fcc_uls_transfers` | transfer | `fcc_uls_transfers.py` | 2 |
| `fcc_uls_leasing` | lease | `fcc_uls_leasing.py` | 2 |
| `eia_860`, `eia_860m` | solar_facility | `eia_860.py` | 1 |
| `uspvdb` | solar_facility | `uspvdb.py` | 1 |
| `lbnl_tts` | distributed_pv | `lbnl_tts.py` | 2 |
| `fdot_billboards`, `ncdot_billboards`, `txdot_billboards` | billboard | `state_billboards.py` | 1 |
| `nc_onemap_parcels`/`fl_fgdl_parcels`/`mn_parcels`/`mt`/`in`/`ar`/`ut` | parcel | `state_parcels.py` | 1 |
| `regrid_parcels` | parcel | `state_parcels.py` (when credentialed) | 2 |
| `hud_oz`, `hud_qct` | distress_overlay | `hud_overlays.py` | 1 |
| `arc_distressed` | county_score | `arc_distressed.py` | 1 |
| `usda_persistent_poverty` | county_score | `usda_persistent_poverty.py` | 1 |

**Phase 1**: everything geometric + county-tier. Map app works for any
state in the dropdown.

**Phase 2**: FCC ULS family + LBNL TTS — adds carrier presence per
tower, ownership unmasking, lease/transfer history, distributed solar.

**Phase 3**: vector tiles (large layers), nationwide composes (Dask),
ML feature pipelines (using `model_prediction` canonical type).

---

## 11. UI integration

Add a **Preprocess** button to the action bar in
`app_puller/main_window.py`, between **Verify contents** and
**Cancel current pull**.

Click flow:
1. Open `PreprocessDialog`:
   - **State dropdown** — auto-populated, defaults to "All states"
   - **Normalize section** — one row per Normalizer with status
   - **Compose section** — one row per state being composed, with
     sub-progress (joins applied, views built)
   - **Force rebuild** checkbox
   - **Run / Cancel / Close** buttons
   - Activity log streams realtime
2. **Run** starts `PreprocessWorker` QThread.
3. **Cancel** = stop after current source.
4. ✗ FAIL rows expose `[Diagnose with AI]` — reuses `diagnose.py`.
5. On completion, activity log gets a summary line.

Action bar:

```
[Check for updates] [Pull all stale] [Pull all missing]
[Rescan disk] [Verify contents] [Preprocess]      [Cancel current pull]
```

---

## 12. Required code changes

- **`scripts/preprocess/` (new package)**
  - `__init__.py`
  - `base.py` — `Normalizer`, `Join`, `View` ABCs + registries +
    `ComposeContext` + base helpers (system columns, geom derivatives,
    valid_from/to bookkeeping, raw.parquet write)
  - `registry.py` — imports + registers all Normalizers
  - `manifest.py` — read/write `preprocess_manifest.json`
  - `compose.py` — the Composer + catalog.json writer
  - `geographies.py` — `STATES` + `states_with_parcel_data()`
  - `quality.py` — `QualityReport` builder
  - `io.py` — dual-write helper (Parquet+GeoJSON), simplified-geojson
    helper, chunked Parquet reader
  - `geom.py` — derive_centroid/area/bbox/simplified/h3 helpers
  - `cluster.py` — owner-clustering helpers
  - `score.py` — interestingness scoring
  - `normalizers/`
    - `_helpers.py` — DMS→decimal, FIPS canonicalize, owner-kind regex,
      owner-name normalizer, address normalizer
    - `fcc_asr.py`, `faa_oeaaa.py`, `hifld_towers.py`
    - `fcc_uls.py`, `fcc_uls_ownership.py`, `fcc_uls_transfers.py`,
      `fcc_uls_leasing.py`
    - `eia_860.py`, `uspvdb.py`, `lbnl_tts.py`
    - `state_billboards.py`, `state_parcels.py`
    - `hud_overlays.py`, `arc_distressed.py`, `usda_persistent_poverty.py`
  - `joins/`
    - `geometry_derivatives.py`, `tower_to_parcel.py`,
      `tower_to_distress.py`, `parcel_to_distress.py`,
      `parcel_hosts_infra.py`, `solar_to_parcel.py`,
      `billboard_to_parcel.py`, `county_score_to_parcel.py`,
      `county_score_to_tower.py`, `county_score_to_solar.py`,
      `owner_cluster.py`, `interestingness_score.py`,
      `license_to_tower.py` (Phase 2),
      `entity_to_license.py` (Phase 2)
  - `views/`
    - `towers_with_landowner.py`, `parcels_hosting_infra.py`,
      `llc_owned_parcels_with_infra.py`,
      `distressed_parcels_hosting_infra.py`, `owner_clusters.py`,
      `county_summary.py`, `state_summary.py`,
      `interestingness_top_1000.py`, ...
- **`scripts/preprocess.py`** — thin CLI wrapper:
  ```bash
  python scripts/preprocess.py
  python scripts/preprocess.py --state 37
  python scripts/preprocess.py --normalize-only
  python scripts/preprocess.py --compose-only --state 12
  python scripts/preprocess.py --force-rebuild
  python scripts/preprocess.py --list-views
  python scripts/preprocess.py --list-joins
  ```
- **`app_puller/main_window.py`** — Preprocess button + handler.
- **`app_puller/preprocess_dialog.py` (new)** — Qt dialog.
- **`app_puller/workers.py`** — `PreprocessWorker`.
- **`app/app.js`** — reads `catalog.json` to auto-render state dropdown
  + view toggles. Falls back to the v1 hardcoded paths if no catalog
  exists yet.
- **`CLAUDE.md`** — new §11 pointing at this plan + `scripts/preprocess/`.
- **`requirements.txt`** — no changes for Phase 1.

---

## 13. Map-app forward-compatibility

The map app should:
1. On load, fetch `data/processed/composite/` directory listing (or a
   manifest at `processed/manifest.json`) to find available states.
2. For each state, fetch `catalog.json` to discover:
   - What layers are available (towers, parcels, distress, solar, ...)
   - What views are available (toggles in sidebar auto-generated)
   - Schemas (column descriptions auto-fill the click-popup)
3. Switch state → re-fetch its catalog → load its layers.
4. Performance: prefer `parcels.simplified.geojson` at low zoom,
   load full `parcels.geojson` (or vector tiles when added) at high zoom.

This is the "new map-app feature = preprocess View, not preprocess
code" promise.

---

## 14. Verification & "how do I know it worked"

### Phase 1 done when:

```bash
python scripts/preprocess.py
ls data/processed/normalized/
# expect one folder per source with raw.parquet + <type>.parquet/.geojson + quality_report.json

ls data/processed/composite/37/
# expect: towers.parquet/.geojson, parcels.parquet/.geojson,
#         parcels.simplified.geojson, distress.geojson,
#         solar_facilities.parquet, billboards.parquet,
#         views/* (8+ files), catalog.json, summary.json

cat data/processed/composite/37/summary.json
# expect ~3-4M parcels (NC statewide), ~10K towers, ~10 OZ tracts

# Map app:
python -m http.server 8765
# open http://localhost:8765/app/
# state dropdown shows NC (+ any other state with parcel data)
# view toggles in sidebar auto-rendered from catalog
```

### Quality reports:

```bash
cat data/processed/normalized/fcc_asr/quality_report.json
# expect rows count, null_rate per critical field, geometry_validity_pct,
# warnings about DMS parse errors
```

### Time-series check:

```bash
# Re-pull FCC ASR (fresh data, some structures may be added/removed)
# Re-run preprocess
cat data/processed/normalized/fcc_asr/quality_report.json
# expect 'history' entry showing diff: N new rows, M rows now-inactive
# parquet retains the now-inactive rows with valid_to set
```

---

## 15. Open decisions (locked-in)

All locked from v2:
1. ✅ Geography scope: state-level dropdown, all 50 states + DC.
2. ✅ Output format: GeoParquet + GeoJSON dual write.
3. ✅ Forward-functionality: maximize. Reserved canonical types for
   aggregations + ML predictions + address points. Full-fidelity raw
   preservation. Geometry derivatives baked in. Reverse-summary
   columns on parcels. Time-series fields throughout.
4. ✅ No auto-run after pulls.
5. ✅ Cancel = stop after current source.
6. ✅ Process everything; ignore legacy `data/raw/NC/`.

---

## 16. Forward-compatibility checklist

| Want to add… | What you write | Lines of code | Touches existing? |
|---|---|---|---|
| A new raw data source | One Normalizer | ~80–200 | No |
| A new spatial relationship | One Join | ~30–60 | No |
| A new map-app filter/view | One View (map app auto-discovers) | ~40–100 | No |
| A new canonical type | Schema in §4 + 1+ Normalizers + relevant Joins | ~200 | No |
| A new pilot state | Already supported via dropdown | 0 | No |
| Change schema of existing canonical type | Bump `_schema_version`, write migration | ~50 | All Normalizers writing that type |
| A new output format | Helper in `io.py` + opt-in flag | ~50 | No |
| **A new pre-built rollup (per-tract, per-ZIP, per-H3-cell)** | One View using `aggregation` type | ~50 | No |
| **An ML model prediction layer** | A Normalizer writing `model_prediction` type | ~80 | No |
| **Owner unmasking** (LLC → human) | A Join walking entity table + a View | ~100 | No |
| **Distance-to-nearest-X features** | A Join using H3 cells | ~60 | No |
| **A new outreach scoring algorithm** | Edit `InterestingnessScoreJoin` OR add a new Score Join | ~30 | Only score code |
| **Carrier coverage maps** | Phase 2 (LicenseToTower Join + map-app View) | ~100 | No |
| **Vector tiles for big layers** | Phase 2 (add tippecanoe + opt-in in `io.py`) | ~80 | Map app render path only |
| **Geocoded address layer** | A Normalizer using `address_point` canonical type | ~150 | No |
| **Census ACS demographics overlay** | New Normalizer + `distress_overlay` (or new type) | ~150 | No |
| **Track changes over time** | Already enabled — query `valid_from`/`valid_to` | 0 | No |
| **Multi-user / multi-tenant** | Already reserved `_tenant_id` column | 0 (just start using it) | No |
| **Per-record confidence scoring** | Already reserved `_quality_score` column | Score logic only | No |

The only thing that's hard to extend without a refactor is changing
the registry contract itself.

---

## 17. What this plan deliberately does NOT do

- Does not change the puller / fetch architecture.
- Does not introduce a database; flat files on disk are fine at this
  scale (16 GB local RAM, ~50 GB on-disk per state worst case).
- Does not handle nationwide composes (Phase 3+; needs Dask).
- Does not handle real-time updates — full re-runs only.
- Does not handle multi-user *operationally* — schema is reserved,
  but auth/session/UI work is out of scope.
- Does not migrate the legacy `data/raw/NC/` layout.

(Many items that v2 deferred — vector tiles, owner unmasking, ML
features, ACS demographics, address geocoding — now have **reserved
hooks** in v3. They're still not built in Phase 1, but adding them
later won't require any preprocessor restructuring.)

---

## 18. Implementation order (Phase 1)

~3–5 days of focused work:

1. `scripts/preprocess/base.py` (ABCs, registries, ComposeContext,
   base helpers for system columns / geom derivatives / valid_from/to)
2. `scripts/preprocess/io.py` (dual-write helper + simplified-geojson)
3. `scripts/preprocess/geom.py` (centroid/area/bbox/simplified/h3)
4. `scripts/preprocess/cluster.py` (owner-clustering)
5. `scripts/preprocess/score.py` (interestingness)
6. `scripts/preprocess/geographies.py` (STATES registry)
7. `scripts/preprocess/manifest.py`
8. `scripts/preprocess/normalizers/_helpers.py`
9. `scripts/preprocess/normalizers/fcc_asr.py` (port from v1)
10. `scripts/preprocess/normalizers/state_parcels.py` (NC first;
    mapping table for others)
11. `scripts/preprocess/normalizers/hud_overlays.py`
12. `scripts/preprocess/normalizers/arc_distressed.py`
13. `scripts/preprocess/normalizers/usda_persistent_poverty.py`
14. `scripts/preprocess/joins/*.py` (the Phase-1 joins, including the
    new `owner_cluster.py` and `interestingness_score.py`)
15. `scripts/preprocess/views/*.py` (the Phase-1 views, including
    `county_summary.py`, `state_summary.py`,
    `interestingness_top_1000.py`)
16. `scripts/preprocess/compose.py` (with `catalog.json` writer)
17. `scripts/preprocess.py` (CLI wrapper)
18. CLI smoke test (`python scripts/preprocess.py --state 37`)
19. `app_puller/workers.py` (`PreprocessWorker`)
20. `app_puller/preprocess_dialog.py`
21. `app_puller/main_window.py` (Preprocess button)
22. End-to-end smoke test (button → dialog → run → map app loads
    + view toggles auto-appear)
23. Remaining Phase-1 Normalizers (FAA DOF, EIA, USPVDB, FDOT)
24. `app/app.js` — catalog-driven state dropdown + view toggles
25. Update `CLAUDE.md` + `README.md`

Phase 2 (FCC ULS family + LBNL TTS + vector tiles) follows as separate
PRs without needing to touch Phase 1 code.
