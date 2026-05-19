"""Other free statewide parcel feeds.

States that publish a single statewide parcel layer with owner attributes
under permissive public-records terms but whose download portals require
a click-through, captcha, or interactive selection step. Each is exposed
as MANUAL_ONLY so the UI shows the official URL and the user fetches
once, then drops the file into ``data/raw/<id>/current/``.

When/if any of these states begins publishing a stable bulk URL, the
matching class can be promoted to AutomationPolicy.ALLOWED with a
``fetch()`` implementation.
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


def _make_legal(publisher: str, manual_url: str, attribution: str, notes: str) -> LegalInfo:
    return LegalInfo(
        publisher=publisher,
        license="State public-records / open data (varies by state)",
        license_url=manual_url,
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        manual_url=manual_url,
        attribution=attribution,
        notes=notes,
    )


class _ManualParcels(DataSource):
    """Common implementation for MANUAL_ONLY state parcel layers."""

    def remote_version(self) -> str:
        return "manual"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        raise RuntimeError(f"{self.id} is MANUAL_ONLY — see manual_url.")


# ── Montana Cadastral ─────────────────────────────────────────────────────
class MtCadastralParcels(_ManualParcels):
    id = "mt_cadastral_parcels"
    name = "Montana Cadastral (statewide parcels)"
    category = CATEGORY_PARCELS
    coverage = "State: Montana"
    cadence = "Quarterly"
    estimated_size_mb = 600.0
    description = (
        "Montana statewide cadastral framework, hosted by MT State "
        "Library. Standardised owner, address, value, acreage. Portal "
        "delivers per-county or statewide shapefile after selection."
    )
    legal = _make_legal(
        "Montana State Library / MT Dept. of Administration",
        "https://geoinfo.msl.mt.gov/",
        "Source: Montana Cadastral Framework, MT State Library.",
        notes=(
            "1. Open the Montana State Library Geographic Information "
            "portal. Search 'Cadastral' or follow the 'Cadastral / "
            "Framework' link.\n"
            "2. Choose the statewide download (~600 MB shapefile, refreshed "
            "quarterly). The portal walks you through agreeing to use terms.\n"
            "3. Unzip into data/raw/mt_cadastral_parcels/current/.\n"
            "\n"
            "The cadastral file has normalised owner name, mailing address, "
            "value, acreage, and parcel ID."
        ),
    )


# ── Minnesota MetroGIS / MnGeo parcels ────────────────────────────────────
class MnParcelsManual(_ManualParcels):
    id = "mn_parcels"
    name = "Minnesota statewide parcels (MnGeo aggregate)"
    category = CATEGORY_PARCELS
    coverage = "State: Minnesota"
    cadence = "Annual aggregate; per-county varies"
    estimated_size_mb = 800.0
    description = (
        "MnGeo publishes a statewide aggregate of all 87 MN counties' "
        "parcels, with normalised owner, value, address. Download is via "
        "the MN Geospatial Commons (click-through agreement)."
    )
    legal = _make_legal(
        "Minnesota Geospatial Information Office (MnGeo)",
        # MnGeo migrated from gisdata.mn.gov (CKAN) to gis.data.mn.gov
        # (ArcGIS Hub) in 2025-2026. The "Plan Parcels Open" dataset is
        # the statewide aggregate compiled from the ~59 opt-in counties.
        # (The "Tax Parcels" item under minnesota:: is misleadingly named —
        # it's actually a single Steele County layer.)
        "https://gis.data.mn.gov/datasets/minnesota::plan-parcels-open-2",
        "Source: MnGeo / Minnesota Geospatial Commons.",
        notes=(
            "1. On the dataset page (the manual URL), click the 'Download' "
            "tab and choose **File Geodatabase**. Shapefile may exceed the "
            "2 GB spec limit on a statewide layer; .gdb has no cap.\n"
            "\n"
            "2. Unzip into data/raw/mn_parcels/current/. If you got "
            "shapefile, keep all .shp/.shx/.dbf/.prj together; if .gdb, "
            "move the whole .gdb folder.\n"
            "\n"
            "3. Click 'Rescan disk' in the puller.\n"
            "\n"
            "Coverage: 59 of 87 MN counties (those that opted into MnGeo's "
            "open-data sharing). The remaining ~28 counties require "
            "licensed agreements with the county directly. Covers most of "
            "the state's population since the Twin Cities metro counties "
            "are all opted in.\n"
            "\n"
            "If the URL 404s, MnGeo restructured again — browse "
            "https://gis.data.mn.gov/search?q=parcels+open and look for "
            "'Plan Parcels Open' owned by the 'minnesota' account.\n"
            "\n"
            "⚠ COMMERCIAL-USE CAVEAT: the dataset page says 'No License "
            "Provided — Request permission to use' despite the 'Open' "
            "naming. Fine for the prototype; before using MN parcel data "
            "in any product or sales material, read LIMITATIONS.md at the "
            "project root and verify with MnGeo."
        ),
    )


# ── Indiana statewide parcels (IGS / IGIO) ────────────────────────────────
class InParcelsManual(_ManualParcels):
    id = "in_parcels"
    name = "Indiana statewide parcels"
    category = CATEGORY_PARCELS
    coverage = "State: Indiana"
    cadence = "Annual"
    estimated_size_mb = 1500.0
    description = (
        "Indiana Geographic Information Office publishes a statewide "
        "parcel layer compiled from county sources. Owner, mailing, "
        "value attributes included."
    )
    legal = _make_legal(
        "Indiana Geographic Information Office (IGIO)",
        # Direct link to the 'Parcel Boundaries of Indiana Current' Hub
        # item (IGIO-maintained, refreshed annually). Clicking lands on
        # the dataset's About tab where the Download button lives.
        "https://www.indianamap.org/datasets/ce78e8017fcb479c81a06a6255cfcfa6_0/about",
        "Source: Indiana Geographic Information Office.",
        notes=(
            "1. On the dataset page (the manual URL), click 'Download' "
            "and choose **File Geodatabase**. (Shapefile fails with a "
            "'2 GB limit' error — the shapefile format can't hold the "
            "full statewide set. File Geodatabase has no such cap.) The "
            "'Current' version is the IGIO-maintained release, refreshed "
            "annually.\n"
            "\n"
            "2. Unzip — you'll get a folder named like "
            "'Parcel_Boundaries_<...>.gdb/'. Move the entire .gdb folder "
            "(not its contents — the folder itself) into "
            "data/raw/in_parcels/current/.\n"
            "\n"
            "3. Click 'Rescan disk' in the puller.\n"
            "\n"
            "If IndianaMap redirects you to https://dataharvest.gio.in.gov/"
            "pages/data-access, fill out the short Data Sharing Initiative "
            "form there and the download link will email back within a "
            "few minutes.\n"
            "\n"
            "Attributes: parcel number, owner, mailing address, value. "
            "Compiled from county sources by IGIO."
        ),
    )


# ── Arkansas GIS Office statewide parcels ─────────────────────────────────
class ArParcelsManual(_ManualParcels):
    id = "ar_parcels"
    name = "Arkansas statewide parcels"
    category = CATEGORY_PARCELS
    coverage = "State: Arkansas"
    cadence = "Annual"
    estimated_size_mb = 1200.0
    description = (
        "Arkansas GIS Office statewide parcel polygons + Assessment "
        "Coordination Division attributes (owner, value, use)."
    )
    legal = _make_legal(
        "Arkansas GIS Office",
        "https://gis.arkansas.gov/",
        "Source: Arkansas GIS Office.",
        notes=(
            "1. On the Arkansas GIS Office portal, navigate to Products → "
            "Cadastral / Parcels.\n"
            "2. Download the statewide parcel layer (~1.2 GB). The portal "
            "may ask you to register an email before download.\n"
            "3. Unzip into data/raw/ar_parcels/current/.\n"
            "\n"
            "Includes Assessment Coordination Division attributes (owner, "
            "value, use code)."
        ),
    )


# ── Utah AGRC statewide parcels ───────────────────────────────────────────
class UtParcelsManual(_ManualParcels):
    id = "ut_parcels"
    name = "Utah statewide parcels (AGRC LIR)"
    category = CATEGORY_PARCELS
    coverage = "State: Utah"
    cadence = "Quarterly"
    estimated_size_mb = 900.0
    description = (
        "Utah AGRC's Land Information Records (LIR) statewide parcel "
        "layer with normalised owner + value attributes."
    )
    legal = _make_legal(
        "Utah Automated Geographic Reference Center (AGRC)",
        "https://gis.utah.gov/products/sgid/cadastre/parcels/",
        "Source: Utah AGRC, Land Information Records.",
        notes=(
            "On the SGID Cadastre / Parcels page, click the 'Land "
            "Information Records (LIR)' download. ~900 MB statewide "
            "shapefile or .gdb, refreshed quarterly.\n"
            "\n"
            "Unzip into data/raw/ut_parcels/current/. Has normalised "
            "owner + value attributes."
        ),
    )


SOURCES = [
    MtCadastralParcels(),
    MnParcelsManual(),
    InParcelsManual(),
    ArParcelsManual(),
    UtParcelsManual(),
]
