"""HUD Qualified Census Tracts (QCT) — national polygons.

LIHTC-designated tracts (poverty-rate or income-based). Same ArcGIS Hub
pattern as the OZ layer.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from ..base import (
    CATEGORY_DISTRESS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import arcgis_query_all

# HUD renamed the QCT service from Qualified_Census_Tracts_2024 to
# QUALIFIED_CENSUS_TRACTS (uppercase). Layer 0 holds the 2025 tracts;
# QUALIFIED_CENSUS_TRACTS_2026/FeatureServer/0 holds the 2026 set.
LAYER_URL = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/"
    "QUALIFIED_CENSUS_TRACTS/FeatureServer/0"
)
META_URL = f"{LAYER_URL}?f=pjson"


class HudQct(DataSource):
    id = "hud_qct"
    name = "HUD Qualified Census Tracts (QCT)"
    category = CATEGORY_DISTRESS
    coverage = "National"
    cadence = "Annual"
    estimated_size_mb = 50.0
    update_cadence_days = 365
    description = (
        "Census tracts designated by HUD as Qualified Census Tracts "
        "(LIHTC-eligible). Either ≥50% of households are below 60% of "
        "AMI, or the poverty rate is ≥25%. A second distress overlay "
        "alongside Opportunity Zones."
    )
    legal = LegalInfo(
        publisher="U.S. Department of Housing and Urban Development (HUD)",
        license="Public Domain (US federal government work)",
        license_url="https://hudgis-hud.opendata.arcgis.com/",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct ArcGIS Hub download URL — clicking grabs the GeoJSON.
        manual_url=(
            "https://opendata.arcgis.com/api/v3/datasets/"
            "778bd77740e34b20a35e611232fa551f_0/downloads/data"
            "?format=geojson&spatialRefId=4326"
        ),
        attribution="Source: HUD GIS Open Data, Qualified Census Tracts.",
        notes=(
            "Direct download: ~50 MB GeoJSON of all QCT tract polygons "
            "(currently the 2025 designation). Clicking starts the download.\n"
            "\n"
            "HUD Open Data hub page (alternate formats — Shapefile / KML / "
            "CSV): https://hudgis-hud.opendata.arcgis.com/datasets/"
            "qualified-census-tracts\n"
            "\n"
            "After download: save as data/raw/hud_qct/current/qct.geojson\n"
            "\n"
            "QCT criteria: ≥50% of households below 60% AMI, OR poverty "
            "rate ≥25%. Used alongside Opportunity Zones as a secondary "
            "distress overlay."
        ),
    )

    def remote_version(self) -> str:
        text = fetch_text(META_URL)
        try:
            meta = json.loads(text)
        except json.JSONDecodeError as e:
            raise HttpError(f"HUD QCT metadata not JSON: {e}")
        edit_ms = (meta.get("editingInfo") or {}).get("lastEditDate")
        if isinstance(edit_ms, (int, float)):
            from datetime import datetime

            dt = datetime.fromtimestamp(edit_ms / 1000, tz=UTC)
            return dt.date().isoformat()
        return f"n-{meta.get('name', '?')}"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        rv = self.remote_version()  # capture once; avoid 2nd HEAD post-download
        out = dest_dir / "qct.geojson"
        n = arcgis_query_all(
            LAYER_URL,
            out,
            lambda done, tot: progress(done, tot, "qct.geojson"),
        )
        if n < 500_000:
            raise HttpError(f"HUD QCT download only {n} bytes — incomplete")
        return FetchResult(
            files=[out],
            remote_version=rv,
            total_bytes=n,
        )

    def validate(self, files: list[Path]) -> None:
        super().validate(files)
        with open(files[0]) as f:
            head = f.read(2048)
        if '"FeatureCollection"' not in head:
            raise ValueError("HUD QCT download is not a GeoJSON FeatureCollection")


SOURCE = HudQct()
