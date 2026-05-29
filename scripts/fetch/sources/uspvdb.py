"""USGS US Large-Scale Solar Photovoltaic Database (USPVDB).

Polygons of every utility-scale PV array >= 1 MW in the US, with
attributes for capacity, install year, technology.

USGS publishes the data three ways via stable direct URLs on the
project's /data/ page — we use the shapefile zip as canonical:

  https://eerscmap.usgs.gov/uspvdb/assets/data/uspvdbSHP.zip      (~7 MB)
  https://eerscmap.usgs.gov/uspvdb/assets/data/uspvdbGeoJSON.zip  (~2 MB)
  https://eerscmap.usgs.gov/uspvdb/assets/data/uspvdbCSV.zip      (~2 MB)

The file is overwritten in place on each version release (~annual),
which makes a date-stamped XML the cleanest version probe.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..base import (
    CATEGORY_SOLAR,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download, fetch_text, head
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import parse_http_date, safe_extract_zip

DATA_PAGE = "https://eerscmap.usgs.gov/uspvdb/data/"
SHP_ZIP_URL = "https://eerscmap.usgs.gov/uspvdb/assets/data/uspvdbSHP.zip"


def _version_from_page() -> str | None:
    """Scrape the data page for the date-stamped XML filename.

    The metadata XML is named `uspvdb_v<N>_<N>_<YYYYMMDD>.xml` and is the
    most reliable indicator of which release is currently live.
    """
    try:
        html = fetch_text(DATA_PAGE, max_bytes=200_000)
    except HttpError:
        return None
    m = re.search(r"uspvdb_v\d+_\d+_(\d{8})\.xml", html)
    if not m:
        return None
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


class Uspvdb(DataSource):
    id = "uspvdb"
    name = "USGS USPVDB (utility-scale PV polygons)"
    category = CATEGORY_SOLAR
    coverage = "National"
    cadence = "~Annual updates"
    estimated_size_mb = 7.0
    update_cadence_days = 90
    description = (
        "USGS-curated database of every >=1 MW US solar PV facility, "
        "with polygon footprints (not just centroid points), capacity, "
        "land cover before installation, install year. Best layer for "
        "the spatial parcel join because you get the actual array shape."
    )
    legal = LegalInfo(
        publisher="U.S. Geological Survey (USGS)",
        license="Public Domain (US federal government work)",
        license_url="https://www.usgs.gov/copyright",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct shapefile zip — clicking starts the ~7 MB download.
        manual_url=SHP_ZIP_URL,
        attribution=("Source: USGS US Large-Scale Solar Photovoltaic Database. Fujita et al."),
        notes=(
            "Direct download: uspvdbSHP.zip (~7 MB shapefile bundle).\n"
            "\n"
            "USPVDB project page (alternate formats + documentation): "
            "https://eerscmap.usgs.gov/uspvdb/data/\n"
            "Other formats available there:\n"
            "  • uspvdbGeoJSON.zip (~2 MB)\n"
            "  • uspvdbCSV.zip (~2 MB, no geometry)\n"
            "\n"
            "After download: unzip into data/raw/uspvdb/current/ — keep "
            "all .shp/.shx/.dbf/.prj together (shapefile set is read as "
            "a unit)."
        ),
    )

    def remote_version(self) -> str:
        v = _version_from_page()
        if v:
            return v
        # Fallback: HEAD the shapefile zip and use Last-Modified.
        h = head(SHP_ZIP_URL)
        lm = parse_http_date(h.get("last_modified"))
        if lm:
            return lm
        cl = h.get("content_length")
        if cl:
            return f"len-{cl}"
        raise HttpError("could not derive remote version for USPVDB")

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        rv = self.remote_version()  # capture once; avoid 2nd HEAD post-download
        zip_path = dest_dir / "uspvdbSHP.zip"
        n = download(
            SHP_ZIP_URL,
            zip_path,
            lambda done, tot: progress(done, tot, "uspvdbSHP.zip"),
            expected_min_bytes=500_000,
        )
        extracted = safe_extract_zip(zip_path, dest_dir / "uspvdb")
        zip_path.unlink()
        return FetchResult(
            files=extracted,
            remote_version=rv,
            total_bytes=n,
        )


SOURCE = Uspvdb()
