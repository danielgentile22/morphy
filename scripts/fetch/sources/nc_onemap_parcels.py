"""NC OneMap Parcels — statewide standardized parcel layer.

NC OneMap (the state's official GIS clearinghouse) publishes the
"Integrated Cadastral Data Exchange" (ICDE) — every county's parcel
records, normalised to a common content standard, refreshed monthly.

We use the Feature Service REST endpoint for the statewide point layer
metadata to detect updates, and the published statewide File
Geodatabase download for bulk pulls of *all 100 counties* in one shot.

Bulk file: published as a .gdb.zip via the NC OneMap data catalog. The
zip URL is stable across releases (the contents change in place).
"""

from __future__ import annotations

import json
from pathlib import Path

from ..base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import safe_extract_zip


# Metadata endpoint for the polygon feature layer (gives lastEditDate).
# NC OneMap is a MapServer (not FeatureServer); the polygon layer is /1.
META_URL = (
    "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/"
    "MapServer/1?f=pjson"
)

# Bulk download via the NC OneMap Hub API (zipped shapefile of polygons).
# The old services.nconemap.gov/data/parcels/NCParcels.gdb.zip path was
# retired in 2025; this Hub item URL is the documented replacement.
# Item GUID is the polygon layer's stable Hub item ID.
BULK_DOWNLOAD = (
    "https://www.nconemap.gov/api/download/v1/items/"
    "1de3d7d828ce4813b838ddf055b40317/shapefile?layers=1"
)


class NcOnemapParcels(DataSource):
    id = "nc_onemap_parcels"
    name = "NC OneMap — statewide parcels (all 100 counties)"
    category = CATEGORY_PARCELS
    coverage = "State: North Carolina (100 counties)"
    cadence = "Monthly (per-county refresh schedule)"
    estimated_size_mb = 2200.0
    description = (
        "NC OneMap publishes a statewide normalised parcel layer "
        "aggregating all 100 NC counties. Standard schema: owner name(s), "
        "mailing address, situs address, acreage, assessed value, land "
        "use code, county FIPS. The state's data catalogue refreshes "
        "each county on its own cadence (mostly monthly). Large download "
        "(~2 GB compressed)."
    )
    legal = LegalInfo(
        publisher="NC OneMap (NC Department of Information Technology, GICC)",
        license="Public domain / open data (NC public records)",
        license_url="https://www.nconemap.gov/pages/terms",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        # Landing page on NC OneMap — has the Download button. The direct
        # Hub API URL is async (kicks off a build job) and unreliable in
        # a browser; the page route is what works for humans.
        manual_url=(
            "https://www.nconemap.gov/datasets/nconemap::"
            "north-carolina-parcels-polygons"
        ),
        attribution="Source: NC OneMap / NC GICC Integrated Cadastral Data Exchange.",
        notes=(
            "On the page, click the 'Download' tab (top right) and choose "
            "Shapefile (~2 GB) or File Geodatabase. Large file — give it "
            "time.\n"
            "\n"
            "After download: unzip into data/raw/nc_onemap_parcels/current/ "
            "(keep all .shp/.shx/.dbf/.prj files together — shapefile set "
            "is read as a unit).\n"
            "\n"
            "Per-county data is contributed by each county's tax office and "
            "normalised by NC OneMap to the statewide schema (OWNNAME1, "
            "MAILADD, PROPLOC, GISACRES, LANDVAL, IMPROVVAL, PARVAL, etc.). "
            "Some counties refresh quarterly.\n"
            "\n"
            "Direct shapefile API (used by the puller's auto-fetch):\n"
            "  https://www.nconemap.gov/api/download/v1/items/"
            "1de3d7d828ce4813b838ddf055b40317/shapefile?layers=1"
        ),
    )

    def remote_version(self) -> str:
        try:
            text = fetch_text(META_URL)
            meta = json.loads(text)
        except (HttpError, json.JSONDecodeError) as e:
            raise HttpError(f"NC OneMap metadata error: {e}")
        edit_ms = (meta.get("editingInfo") or {}).get("lastEditDate")
        if isinstance(edit_ms, (int, float)):
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(edit_ms / 1000, tz=timezone.utc)
            return dt.date().isoformat()
        return f"n-{meta.get('name','?')}"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        zip_path = dest_dir / "NCParcels_shapefile.zip"
        n = download(
            BULK_DOWNLOAD,
            zip_path,
            lambda done, tot: progress(done, tot, zip_path.name),
            expected_min_bytes=50_000_000,
        )
        extracted = safe_extract_zip(zip_path, dest_dir / "NCParcels")
        zip_path.unlink()
        return FetchResult(
            files=extracted,
            remote_version=self.remote_version(),
            total_bytes=n,
        )


SOURCE = NcOnemapParcels()
