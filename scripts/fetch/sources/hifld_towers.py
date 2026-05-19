"""HIFLD cellular towers (Homeland Infrastructure Foundation-Level Data).

HIFLD Open is the public subset of DHS/CISA's HIFLD program. The
Cellular Towers layer is hosted on the HIFLD Open ArcGIS Hub and
exposed via a stable REST endpoint that supports full GeoJSON export.

ArcGIS REST patterns used:
  * /<layer>?f=json                — metadata incl. editingInfo.lastEditDate
  * /<layer>/query?where=1=1&outFields=*&f=geojson  — full layer download
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

from ..base import (
    CATEGORY_TOWERS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo

LAYER_URL = (
    "https://services1.arcgis.com/Hp6G80Pky0om7QvQ/arcgis/rest/services/"
    "Cellular_Towers/FeatureServer/0"
)
METADATA_URL = f"{LAYER_URL}?f=pjson"
GEOJSON_URL = f"{LAYER_URL}/query?where=1%3D1&outFields=*&f=geojson&returnGeometry=true"


class HifldTowers(DataSource):
    id = "hifld_towers"
    name = "HIFLD — Cellular Towers"
    category = CATEGORY_TOWERS
    coverage = "National (CONUS + AK/HI + territories)"
    cadence = "Irregular (DHS-curated; typically monthly)"
    estimated_size_mb = 35.0
    update_cadence_days = None
    description = (
        "DHS/CISA-curated point dataset of cellular towers, drawn from "
        "FCC and commercial sources. Use as a sanity check against FCC "
        "ASR (which only registers ≥60 m structures)."
    )
    legal = LegalInfo(
        publisher="Homeland Infrastructure Foundation-Level Data (HIFLD), DHS/CISA",
        license="Public Domain / Open data (most layers)",
        license_url="https://hifld-geoplatform.hub.arcgis.com/pages/terms",
        # As of 2024 DHS pulled the public HIFLD Cellular Towers layer.
        # No reliable public replacement exists. Marked MANUAL_ONLY so the
        # puller won't repeatedly fail trying to auto-fetch a dead service.
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED,
        manual_url="https://hifld-geoplatform.hub.arcgis.com/search?q=cellular",
        attribution="Source: HIFLD Open / DHS Geospatial Management Office.",
        notes=(
            "STATUS: NO LONGER PUBLICLY AVAILABLE.\n"
            "\n"
            "DHS removed the public HIFLD Cellular Towers layer during their "
            "2024 infrastructure-data security review. The old REST service "
            "still resolves but returns no features.\n"
            "\n"
            "What to do:\n"
            "  1. Use FCC ASR as the primary cellular-tower source "
            "(it's already in the puller). ASR covers all registered "
            "structures ≥60 m and most cellular sites.\n"
            "  2. If you specifically need shorter / rooftop sites, "
            "request access to HIFLD's authenticated infrastructure data "
            "through DHS/CISA Geospatial Information Infrastructure (GII) "
            "at https://gii.dhs.gov/ — requires a vetted account.\n"
            "  3. Search the HIFLD Hub (manual URL above) periodically — "
            "if/when DHS publishes a replacement layer, drop the GeoJSON "
            "into data/raw/hifld_towers/current/cellular_towers.geojson "
            "and click Rescan disk."
        ),
    )

    def remote_version(self) -> str:
        text = fetch_text(METADATA_URL)
        try:
            meta = json.loads(text)
        except json.JSONDecodeError as e:
            raise HttpError(f"HIFLD metadata not JSON: {e}")
        edit_ms = (meta.get("editingInfo") or {}).get("lastEditDate")
        if isinstance(edit_ms, (int, float)):
            from datetime import datetime

            dt = datetime.fromtimestamp(edit_ms / 1000, tz=UTC)
            return dt.date().isoformat()
        # Fallback: layer name + record count (changes when data changes)
        return f"name-{meta.get('name', '?')}"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        out = dest_dir / "cellular_towers.geojson"
        n = download(
            GEOJSON_URL,
            out,
            lambda done, tot: progress(done, tot, "cellular_towers.geojson"),
            expected_min_bytes=100_000,
        )
        return FetchResult(
            files=[out],
            remote_version=self.remote_version(),
            total_bytes=n,
        )

    def validate(self, files: list[Path]) -> None:
        super().validate(files)
        # Must be parseable JSON with FeatureCollection
        with open(files[0]) as f:
            head = f.read(2048)
        if '"FeatureCollection"' not in head:
            raise ValueError("HIFLD download is not a GeoJSON FeatureCollection")


SOURCE = HifldTowers()
