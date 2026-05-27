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

from ..base import CATEGORY_PARCELS, ManualOnlySource
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ..walkthroughs import ManualStep, ManualWalkthrough


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


# ── Montana Cadastral ─────────────────────────────────────────────────────
class MtCadastralParcels(ManualOnlySource):
    id = "mt_cadastral_parcels"
    name = "Montana Cadastral (statewide parcels)"
    category = CATEGORY_PARCELS
    coverage = "State: Montana"
    cadence = "Quarterly"
    estimated_size_mb = 1000.0
    update_cadence_days = 90
    description = (
        "Montana statewide cadastral framework, hosted by MT State "
        "Library on their public FTP mirror "
        "(ftpgeoinfo.msl.mt.gov). Standardised owner, address, value, "
        "acreage. Statewide SHP zip is ~1 GB."
    )
    legal = _make_legal(
        "Montana State Library / MT Dept. of Administration",
        "https://geoinfo.msl.mt.gov/",
        "Source: Montana Cadastral Framework, MT State Library.",
        notes=(
            "Walkthrough: see manual_walkthrough() on this source — the "
            "puller's 'Walk me through' button surfaces the steps. The "
            "cadastral file has normalised owner name, mailing address, "
            "value, acreage, and parcel ID."
        ),
    )

    def manual_walkthrough(self) -> ManualWalkthrough:
        return ManualWalkthrough(
            landing_page_url="https://ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Cadastral/",
            steps=[
                ManualStep(
                    title="Open MT's cadastral FTP directory",
                    body=(
                        "Click the deep link below to open the MT State "
                        "Library's bulk-download FTP listing for the "
                        "statewide cadastral framework. The two main files "
                        "you'll see are `MontanaCadastral_SHP.zip` (~1 GB "
                        "shapefile) and `MontanaCadastral_GDB.zip` (~825 "
                        "MB File Geodatabase). Refreshed quarterly; check "
                        "the file date to confirm freshness."
                    ),
                    deep_link="https://ftpgeoinfo.msl.mt.gov/Data/Spatial/MSDI/Cadastral/",
                ),
                ManualStep(
                    title="Download MontanaCadastral_SHP.zip",
                    body=(
                        "Click **`MontanaCadastral_SHP.zip`** (the larger "
                        "of the two — ~1 GB). **Do not** download the "
                        "`_GDB.zip` version — our normalizer reads "
                        "shapefiles, not File Geodatabase. No terms-of-"
                        "use click-through here; the file downloads "
                        "directly from the FTP mirror."
                    ),
                ),
                ManualStep(
                    title="Upload via the puller",
                    body=(
                        "Easiest: click **⤴ Upload file(s)…** in the puller "
                        "and select the downloaded `MontanaCadastral_SHP.zip` "
                        "— the puller auto-extracts it into "
                        "`data/raw/mt_cadastral_parcels/current/`.\n"
                        "\n"
                        "Manual alternative: extract the ZIP yourself and "
                        "drop the shapefile parts (`.shp`, `.shx`, `.dbf`, "
                        "`.prj`, optional `.cpg`) into "
                        "`data/raw/mt_cadastral_parcels/current/`. Keep "
                        "all shapefile parts together — they're a single "
                        "dataset."
                    ),
                ),
                ManualStep(
                    title="Click 'I'm done' to verify + record",
                    body=(
                        "The puller will confirm the directory is non-"
                        "empty and run `validate()`. Once recorded, the "
                        "preprocess step (Section 5) will normalize MT "
                        "parcels into the canonical `parcel` schema."
                    ),
                ),
            ],
            expected_files=["*.shp", "*.dbf", "*.shx", "*.prj"],
            notes_on_failure=(
                "If the FTP URL has rotted, the parent portal is "
                "https://geoinfo.msl.mt.gov/ — search for 'cadastral "
                "framework'. The FTP mirror is the canonical download "
                "endpoint and rarely moves."
            ),
        )


# ── Minnesota MetroGIS / MnGeo parcels ────────────────────────────────────
class MnParcelsManual(ManualOnlySource):
    id = "mn_parcels"
    name = "Minnesota statewide parcels (MnGeo aggregate)"
    category = CATEGORY_PARCELS
    coverage = "State: Minnesota"
    cadence = "Annual aggregate; per-county varies"
    estimated_size_mb = 800.0
    update_cadence_days = None
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
class InParcelsManual(ManualOnlySource):
    id = "in_parcels"
    name = "Indiana statewide parcels"
    category = CATEGORY_PARCELS
    coverage = "State: Indiana"
    cadence = "Annual"
    estimated_size_mb = 1500.0
    update_cadence_days = None
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
class ArParcelsManual(ManualOnlySource):
    id = "ar_parcels"
    name = "Arkansas statewide parcels"
    category = CATEGORY_PARCELS
    coverage = "State: Arkansas"
    cadence = "Annual"
    estimated_size_mb = 1200.0
    update_cadence_days = 365
    description = (
        "Arkansas GIS Office statewide parcel polygons + Assessment "
        "Coordination Division attributes (owner, value, use)."
    )
    legal = _make_legal(
        "Arkansas GIS Office",
        "https://gis.arkansas.gov/",
        "Source: Arkansas GIS Office.",
        notes=(
            "Walkthrough: see manual_walkthrough() on this source. "
            "Includes Assessment Coordination Division attributes (owner, "
            "value, use code)."
        ),
    )

    def manual_walkthrough(self) -> ManualWalkthrough:
        return ManualWalkthrough(
            landing_page_url="https://gis.arkansas.gov/",
            steps=[
                ManualStep(
                    title="Open the Arkansas GIS Office portal",
                    body=(
                        "Click the deep link to open the AR GIS Office portal in "
                        "your browser. The landing page has a 'Products' menu in "
                        "the top nav."
                    ),
                    deep_link="https://gis.arkansas.gov/",
                ),
                ManualStep(
                    title="Navigate to Products → Cadastral / Parcels",
                    body=(
                        "From the Products menu, choose **Cadastral** or directly "
                        "**Parcels**. The statewide layer is the top item on that "
                        "page (~1.2 GB)."
                    ),
                    deep_link="https://gis.arkansas.gov/product-category/cadastral/",
                ),
                ManualStep(
                    title="Download the statewide parcel layer",
                    body=(
                        "Click the statewide-parcels download. The portal may "
                        "ask you to register an email address before the download "
                        "begins — that's expected."
                    ),
                ),
                ManualStep(
                    title="Unzip into data/raw/ar_parcels/current/",
                    body=(
                        "Move the unzipped contents (shapefile parts or .gdb "
                        "folder) into\n"
                        "```\n"
                        "data/raw/ar_parcels/current/\n"
                        "```\n"
                        "Keep file groupings intact — shapefile parts together, "
                        "or the entire .gdb folder if you got a geodatabase."
                    ),
                ),
                ManualStep(
                    title="Click 'Rescan disk' in the puller",
                    body=(
                        "Back in the puller, click **Rescan disk** to register the "
                        "new files, then **Verify contents** for sanity-check."
                    ),
                ),
            ],
            expected_files=["*.shp", "*.dbf", "*.shx", "*.prj"],
            notes_on_failure=(
                "If the portal looks empty for cadastral, AR sometimes routes "
                "downloads through a separate ACD (Assessment Coordination "
                "Division) data request form — search 'ACD parcels' or contact "
                "the GIS Office support line listed on their homepage."
            ),
        )


# ── Utah AGRC statewide parcels ───────────────────────────────────────────
class UtParcelsManual(ManualOnlySource):
    id = "ut_parcels"
    name = "Utah statewide parcels (UGRC LIR)"
    category = CATEGORY_PARCELS
    coverage = "State: Utah"
    cadence = "Quarterly"
    estimated_size_mb = 900.0
    update_cadence_days = 365
    description = (
        "Utah UGRC's Land Information Records (LIR) statewide parcel "
        "layer — value, acreage, property class, year built, situs "
        "address. NOTE: UGRC's LIR standard does NOT include owner "
        "names; deferred from the v1 anchor set for that reason "
        "(ADR-049)."
    )
    legal = _make_legal(
        "Utah Automated Geographic Reference Center (AGRC)",
        "https://gis.utah.gov/products/sgid/cadastre/parcels/",
        "Source: Utah AGRC, Land Information Records.",
        notes=(
            "Walkthrough: see manual_walkthrough() on this source. Has "
            "normalised owner + value attributes."
        ),
    )

    def manual_walkthrough(self) -> ManualWalkthrough:
        return ManualWalkthrough(
            landing_page_url="https://gis.utah.gov/products/sgid/cadastre/parcels/",
            steps=[
                ManualStep(
                    title="Open the Utah AGRC SGID Parcels page",
                    body=(
                        "Click the deep link to open the AGRC Cadastre / Parcels "
                        "page. This is the official entry point for the statewide "
                        "Land Information Records (LIR) layer."
                    ),
                    deep_link="https://gis.utah.gov/products/sgid/cadastre/parcels/",
                ),
                ManualStep(
                    title="Find the Land Information Records (LIR) download",
                    body=(
                        "On the page, look for the **Land Information Records "
                        "(LIR)** section. There are two variants — pick the "
                        "**statewide** download, not per-county. ~900 MB."
                    ),
                ),
                ManualStep(
                    title="Choose Shapefile or File Geodatabase",
                    body=(
                        "Either format works. Shapefile is most portable; "
                        "File Geodatabase preserves nicer field names. The "
                        "preprocessor reads either."
                    ),
                ),
                ManualStep(
                    title="Unzip into data/raw/ut_parcels/current/",
                    body=(
                        "Move the unzipped contents into\n"
                        "```\n"
                        "data/raw/ut_parcels/current/\n"
                        "```\n"
                        "Keep shapefile parts together, or the entire .gdb folder."
                    ),
                ),
                ManualStep(
                    title="Click 'Rescan disk' in the puller",
                    body=(
                        "Back in the puller, click **Rescan disk**, then "
                        "**Verify contents** to confirm the layer."
                    ),
                ),
            ],
            expected_files=["*.shp", "*.dbf", "*.shx", "*.prj"],
            notes_on_failure=(
                "If the AGRC SGID portal restructured, the parcels item still "
                "lives under SGID Cadastre — search "
                "https://gis.utah.gov/sgid for 'parcels' or 'LIR'."
            ),
        )


# ── active anchor states (AR + MT) ───────────────────────────────────────
# NC has its own auto-fetch source (nc_onemap_parcels). FL has its own
# manual source (fdor_nal). MN, IN, and UT are deferred — MN's license is
# ambiguous (see [[mn-parcels-license-commercial-blocker]]); IN's and UT's
# public parcels have no owner_name column (UGRC's LIR standard omits it —
# see ADR-049). Deferred classes stay imported so they can be re-promoted
# by editing the active block alone.
SOURCES = [
    MtCadastralParcels(),
    ArParcelsManual(),
]

DEFERRED_SOURCES = [
    MnParcelsManual(),
    InParcelsManual(),
    UtParcelsManual(),
]
