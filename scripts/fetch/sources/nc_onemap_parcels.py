"""NC OneMap Parcels — statewide standardized parcel layer.

NC OneMap (the state's official GIS clearinghouse) publishes the
"Integrated Cadastral Data Exchange" (ICDE) — every county's parcel
records, normalised to a common content standard, refreshed monthly.

Originally we used NC OneMap's Hub bulk-download API
(``/api/download/v1/items/<id>/shapefile``). That endpoint started
returning HTTP 500 in mid-2026 with no resolution from NC. Instead of
flipping to MANUAL_ONLY (which costs the user ~6 hours of staggered
browser downloads — Hub's UI requires splitting the 5.9M-record layer
into ~6 batches to dodge async-export ceilings), we drive the
underlying ArcGIS MapServer ``/query`` endpoint directly with
``resultOffset`` pagination at 5000 features per page.

This is the canonical way to consume ArcGIS REST layers — version-
stable, well documented, and unaffected by whatever's broken at the
Hub UI layer. The fetch takes ~30–60 minutes (1,186 sequential
requests with geometry) but it's fully unattended and resumable: each
page is written as ``page_NNNN.geojson``; if the run is interrupted,
the next run skips already-completed pages.

The MapServer returns lowercase field names (``ownname``,
``mailadd``, ``cntyfips`` etc.) whereas the old shapefile bulk used
uppercase (``OWNNAME``, ``MAILADD``, ``STCNTYFIPS``). The NC adapter's
field map (``scripts/preprocess/normalizers/state_parcel_adapters/nc.py``)
lists both casings so old data on disk still normalizes correctly.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from pathlib import Path

from ..base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._arcgis import arcgis_edit_date_version

# Metadata endpoint for the polygon feature layer (gives lastEditDate).
# NC OneMap is a MapServer (not FeatureServer); the polygon layer is /1.
META_URL = "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1?f=pjson"

# The /query endpoint of the same MapServer layer. We paginate this for
# bulk fetch since the Hub-level download API is permanently broken.
QUERY_ENDPOINT = (
    "https://services.nconemap.gov/secure/rest/services/NC1Map_Parcels/MapServer/1/query"
)

# Server-declared max. Confirmed at /MapServer/1?f=json → maxRecordCount.
# Going higher silently caps; going lower is needlessly chatty.
PAGE_SIZE = 5000

# Politeness: tiny delay between pages so we're not hammering NC's
# server during the ~1k-request loop. Negligible vs per-request time.
PAGE_DELAY_SEC = 0.1

# Explicit field list — must include every column the NC adapter's
# field map references (see
# scripts/preprocess/normalizers/state_parcel_adapters/nc.py).
# Using outFields=* would inflate each page ~36% with unused metadata.
# objectid is required for stable orderByFields pagination.
OUT_FIELDS = ",".join(
    [
        "objectid",
        "parno",
        "nparno",
        "ownname",
        "ownname2",
        "mailadd",
        "mcity",
        "mstate",
        "mzip",
        "siteadd",
        "scity",
        "gisacres",
        "landval",
        "improvval",
        "parval",
        "parusecode",
        "parusedesc",
        "structyear",
        "stcntyfips",
        "cntyfips",
        "cntyname",
    ]
)

# Human-facing dataset page (kept as a manual_url fallback in case the
# auto-fetch ever breaks and the user needs to retrieve data by hand).
DATASET_PAGE = "https://www.nconemap.gov/datasets/nconemap::north-carolina-parcels-polygons"


class NcOnemapParcels(DataSource):
    id = "nc_onemap_parcels"
    name = "NC OneMap — statewide parcels (all 100 counties)"
    category = CATEGORY_PARCELS
    coverage = "State: North Carolina (100 counties)"
    cadence = "Monthly (per-county refresh schedule)"
    estimated_size_mb = 10000.0  # ~10 GB across ~1186 paginated GeoJSON files
    update_cadence_days = 90
    # The 1,186-page fetch is the longest single operation in the puller;
    # a server-side 504 at page 1,106 (real history, 2026-05) used to mean
    # starting over from page 1. With resume support enabled, prepare_partial
    # preserves the previous run's page_*.geojson files and the per-page
    # `if page_path.exists()` guard in `fetch()` below skips them.
    supports_resume = True
    description = (
        "NC OneMap publishes a statewide normalised parcel layer "
        "aggregating all 100 NC counties via the Integrated Cadastral "
        "Data Exchange (ICDE). Standard schema: owner name(s), mailing "
        "address, situs address, acreage, assessed value, land use code, "
        "county FIPS. Per-county refresh cadence varies (mostly monthly, "
        "some quarterly). Fetched via paginated MapServer queries — "
        "the Hub bulk-download API has been broken since mid-2026."
    )
    legal = LegalInfo(
        publisher="NC OneMap (NC Department of Information Technology, GICC)",
        license="Public domain / open data (NC public records)",
        license_url="https://www.nconemap.gov/pages/terms",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        manual_url=DATASET_PAGE,
        attribution="Source: NC OneMap / NC GICC Integrated Cadastral Data Exchange.",
        notes=(
            "Auto-fetch drives NC OneMap's ArcGIS MapServer /query endpoint "
            "with resultOffset pagination at 5000 features/page (server "
            "max). One GeoJSON file is written per page under "
            "data/raw/nc_onemap_parcels/current/page_NNNN.geojson; the "
            "normalizer reads them all via rglob.\n"
            "\n"
            "Fetch takes ~30–60 min (sequential, ~1186 pages, with "
            "geometry @ EPSG:4326). Resumable: existing complete page "
            "files are skipped on re-run.\n"
            "\n"
            "Was previously wired to the Hub bulk-download API "
            "(/api/download/v1/items/.../shapefile) — that endpoint "
            "returns persistent HTTP 500. Pagination via MapServer is the "
            "canonical workaround (see ADR-048)."
        ),
    )

    def remote_version(self) -> str:
        # Same edit-date probe as the ArcGIS Hub sources (#258); only the
        # paginated MapServer fetch below is NC-specific.
        return arcgis_edit_date_version(META_URL, label="NC OneMap")

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        """Paginated MapServer query → one GeoJSON file per 5000-feature page."""
        rv = self.remote_version()  # capture once; avoid 2nd HEAD post-download
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 1) Total record count — needed for progress + page-count.
        count_url = f"{QUERY_ENDPOINT}?where=1%3D1&returnCountOnly=true&f=json"
        try:
            total_features = int(json.loads(fetch_text(count_url))["count"])
        except (HttpError, json.JSONDecodeError, KeyError, ValueError) as e:
            raise HttpError(f"NC OneMap count query failed: {e}")

        total_pages = (total_features + PAGE_SIZE - 1) // PAGE_SIZE
        written: list[Path] = []

        # 2) Walk pages. download() gives us atomic writes + per-page retry.
        for page_idx in range(total_pages):
            offset = page_idx * PAGE_SIZE
            page_path = dest_dir / f"page_{page_idx:04d}.geojson"

            # Resume: skip pages already on disk (size threshold filters
            # out truncated/aborted writes; full pages are ≥ a few KB even
            # when the underlying records are mostly null).
            if page_path.exists() and page_path.stat().st_size > 1024:
                written.append(page_path)
                progress(
                    min(offset + PAGE_SIZE, total_features),
                    total_features,
                    page_path.name,
                )
                continue

            params = urllib.parse.urlencode(
                {
                    "where": "1=1",
                    "outFields": OUT_FIELDS,
                    "returnGeometry": "true",
                    "outSR": "4326",
                    "resultOffset": str(offset),
                    "resultRecordCount": str(PAGE_SIZE),
                    # Stable ordering across pages — without this, the server
                    # is free to return rows in different orders each call,
                    # leading to dupes or gaps.
                    "orderByFields": "objectid",
                    "f": "geojson",
                }
            )
            url = f"{QUERY_ENDPOINT}?{params}"

            download(url, page_path, on_progress=None, expected_min_bytes=200)

            # MapServer returns errors as HTTP 200 with {"error": {...}}; spot-
            # check the head of the file before counting the page as good.
            with open(page_path, "rb") as fh:
                head = fh.read(256)
            if b'"error"' in head and b'"FeatureCollection"' not in head:
                # Tear down the bad file so a retry doesn't see "exists".
                try:
                    page_path.unlink()
                except OSError:
                    pass
                raise HttpError(
                    f"NC OneMap page {page_idx} (offset {offset}) returned error envelope: {head!r}"
                )

            written.append(page_path)
            progress(
                min(offset + PAGE_SIZE, total_features),
                total_features,
                page_path.name,
            )
            time.sleep(PAGE_DELAY_SEC)

        total_bytes = sum(p.stat().st_size for p in written)
        return FetchResult(
            files=written,
            remote_version=rv,
            total_bytes=total_bytes,
        )


SOURCE = NcOnemapParcels()
