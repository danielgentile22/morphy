"""HUD Opportunity Zones — national tract polygons.

Layer hosted on the HUD GIS Open Data ArcGIS Hub. Same REST pattern as
HIFLD. Returns ~8,700 census-tract polygons.
"""

from __future__ import annotations

from ..base import CATEGORY_DISTRESS
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._arcgis import ArcGisHubSource

# HUD reshuffled their ArcGIS Online org in 2025: the OZ layer moved
# from FeatureServer/0 to FeatureServer/13 inside the same service.
LAYER_URL = (
    "https://services.arcgis.com/VTyQ9soqVukalItT/arcgis/rest/services/"
    "Opportunity_Zones/FeatureServer/13"
)


class HudOz(ArcGisHubSource):
    id = "hud_oz"
    name = "HUD Opportunity Zones (OZ 1.0)"
    category = CATEGORY_DISTRESS
    coverage = "National"
    cadence = "Static (2018 designation); OZ 2.0 redesignations 2026-28"
    estimated_size_mb = 30.0
    update_cadence_days = None
    description = (
        "Polygons of every census tract designated a Qualified "
        "Opportunity Zone under the 2017 TCJA. Primary distress proxy "
        "for the prototype. Note that OZ 2.0 redesignations are being "
        "made by governors during 2026 — boundaries will change."
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
            "ef143299845841f8abb95969c01f88b5_13/downloads/data"
            "?format=geojson&spatialRefId=4326"
        ),
        attribution="Source: HUD GIS Open Data, Opportunity Zones.",
        notes=(
            "Direct download: ~30 MB GeoJSON of all ~8,700 OZ tract "
            "polygons. Clicking the manual URL starts the download.\n"
            "\n"
            "HUD Open Data hub page (alternate formats — Shapefile / KML / "
            "CSV): https://hudgis-hud.opendata.arcgis.com/datasets/"
            "opportunity-zones\n"
            "\n"
            "After download: save as data/raw/hud_oz/current/"
            "opportunity_zones.geojson\n"
            "\n"
            "Note: this is the OZ 1.0 (2018 TCJA) designation. OZ 2.0 "
            "redesignations made by governors during 2026 will change "
            "boundaries — track via the HUD 'DCTA_Eligibility' services."
        ),
    )

    layer_url = LAYER_URL
    out_name = "opportunity_zones.geojson"
    error_label = "HUD OZ"


SOURCE = HudOz()
