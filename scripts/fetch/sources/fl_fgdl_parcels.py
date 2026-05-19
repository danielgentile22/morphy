"""Florida statewide parcels — FGDL DSL parcel composite.

The Florida Geographic Data Library (FGDL) at the University of Florida
publishes a statewide parcel composite (DSL = Division of State Lands).
Direct download — clicking starts a ~173 MB zip immediately.

Filename embeds the release month/year (e.g. dsl_parcel_composite_oct25.zip)
which means the URL changes with each annual release. Source is left as
MANUAL_ONLY so the user is reminded to occasionally check for a newer
filename; if/when we automate it, the fetch path would scrape the
/zips/geospatial_data/current/ listing for the newest matching file.
"""

from __future__ import annotations

from pathlib import Path

from ..base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..legal import AutomationPolicy, CommercialUse, LegalInfo


class FlFgdlParcels(DataSource):
    id = "fl_fgdl_parcels"
    name = "Florida statewide parcels (FGDL DSL composite)"
    category = CATEGORY_PARCELS
    coverage = "State: Florida"
    cadence = "Annual (filename embeds month/year, e.g. oct25)"
    estimated_size_mb = 173.0
    update_cadence_days = None
    description = (
        "Florida statewide parcel composite published by the UF GeoPlan "
        "Center FGDL. Polygons with owner name, mailing address, value, "
        "land use. Refreshed annually."
    )
    legal = LegalInfo(
        publisher="Florida Geographic Data Library (UF GeoPlan)",
        license="FGDL terms of use (free, with attribution)",
        license_url="https://fgdl.org/",
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        # Direct file URL — clicking starts the ~173 MB download. The
        # filename embeds the release month/year (oct25), so we'll need
        # to bump this when FGDL publishes a new version. The directory
        # listing is browsable for the latest filename.
        manual_url=("https://fgdl.org/zips/geospatial_data/current/dsl_parcel_composite_oct25.zip"),
        attribution="Source: FGDL, University of Florida GeoPlan Center.",
        notes=(
            "Direct download: dsl_parcel_composite_oct25.zip (~173 MB). "
            "Clicking 'Open manual URL' grabs the file immediately — no "
            "click-through agreement needed from this endpoint.\n"
            "\n"
            "After download: unzip into data/raw/fl_fgdl_parcels/current/. "
            "Keep all .shp/.shx/.dbf/.prj files together (shapefile set is "
            "read as a unit). Click 'Rescan disk' in the puller.\n"
            "\n"
            "If the manual URL 404s, FGDL has published a new month/year. "
            "Browse https://fgdl.org/zips/geospatial_data/current/ and look "
            "for the newest 'dsl_parcel_composite_*.zip', then update the "
            "manual_url in scripts/fetch/sources/fl_fgdl_parcels.py.\n"
            "\n"
            "Attributes include owner name, mailing address, value, land "
            "use, and parcel identifiers."
        ),
    )

    def remote_version(self) -> str:
        return "manual"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        raise RuntimeError("fl_fgdl_parcels is MANUAL_ONLY — accept terms on FGDL site.")


SOURCE = FlFgdlParcels()
