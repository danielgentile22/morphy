"""Florida Department of Revenue — per-county PAR parcel shapefiles.

FDOR's Map Data directory ships two flavors of per-county parcel files:

* **PIN** shapefiles — geometry only (FID + Shape + PARCELNO), no
  attribution. Not useful for us.
* **PAR** shapefiles — PIN joined with current-year NAL (Name,
  Address, Legal) tax-roll attributes. One file per county per year;
  contains parcel polygons + owner name + mailing address +
  just/assessed value + use code + land / improvement values. **This
  is the canonical FL landowner-data source we use.**

Join key inside the PAR shapefile is PARCELNO (= PARCEL_ID in NAL).
The standalone NAL/SDF text files in FDOR's Tax Roll Data File
directory are the same attributes minus geometry — we don't need them
since the join is already done in PAR.

This source replaces the FL FGDL DSL state-land parcel layer that was
previously in the registry (DSL covers state-owned land, not the
private parcels we care about).

Auto-fetch (flipped from MANUAL_ONLY 2026-07-03): the Map Data
"directory" is a SharePoint document library whose anonymous REST API
(``/_api/web/GetFolderByServerRelativeUrl(...)``) lists vintages and
files, and every PAR zip is a direct anonymous HTTPS download — no
click-through, no license interstitial (the earlier MANUAL_ONLY
classification assumed one that does not exist). robots.txt permits
crawling the data portal. FDOR pre-creates next year's folder months
before populating it (2026F existed empty while 2025F held the live
rolls), so vintage discovery walks newest-first until files appear.

V1 coverage: **all 67 Florida counties** (per docs/SCOPE.md), one PAR
ZIP per county per vintage (~4.1 GB total), plus the Miami-Dade and
St. Johns condo extras that live in the same PAR folder. Filenames are
inconsistent (``par.zip`` / ``Ppar.zip`` / ``par.shp.zip``), so the
fetcher downloads by each file's listed ServerRelativeUrl instead of
constructing names. The walkthrough is retained as the fallback.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

from ..base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ..walkthroughs import ManualStep, ManualWalkthrough
from ._helpers import fetch_zip_extracted

# All 67 Florida counties — FDOR publishes one PAR ZIP per county on
# the Map Data directory. Listed alphabetically to match the directory
# listing order; the walkthrough uses this as a download checklist.
FL_COUNTIES: list[str] = [
    "Alachua",
    "Baker",
    "Bay",
    "Bradford",
    "Brevard",
    "Broward",
    "Calhoun",
    "Charlotte",
    "Citrus",
    "Clay",
    "Collier",
    "Columbia",
    "DeSoto",
    "Dixie",
    "Duval",
    "Escambia",
    "Flagler",
    "Franklin",
    "Gadsden",
    "Gilchrist",
    "Glades",
    "Gulf",
    "Hamilton",
    "Hardee",
    "Hendry",
    "Hernando",
    "Highlands",
    "Hillsborough",
    "Holmes",
    "Indian River",
    "Jackson",
    "Jefferson",
    "Lafayette",
    "Lake",
    "Lee",
    "Leon",
    "Levy",
    "Liberty",
    "Madison",
    "Manatee",
    "Marion",
    "Martin",
    "Miami-Dade",
    "Monroe",
    "Nassau",
    "Okaloosa",
    "Okeechobee",
    "Orange",
    "Osceola",
    "Palm Beach",
    "Pasco",
    "Pinellas",
    "Polk",
    "Putnam",
    "Santa Rosa",
    "Sarasota",
    "Seminole",
    "St. Johns",
    "St. Lucie",
    "Sumter",
    "Suwannee",
    "Taylor",
    "Union",
    "Volusia",
    "Wakulla",
    "Walton",
    "Washington",
]

LANDING_PAGE = (
    "https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx"
)
# Direct deep link to the Map Data directory where the PAR shapefiles live.
# Confirmed against FDOR's Parcel Shapefiles Readme (2026-05-19).
MAP_DATA_README = (
    "https://floridarevenue.com/property/dataportal/Documents/"
    "PTO%20Data%20Portal/Map%20Data/Parcel%20Shapefiles%20Readme.pdf"
)

SP_HOST = "https://floridarevenue.com"
# Server-relative path of the Map Data document library folder.
MAP_DATA_PATH = "/property/dataportal/Documents/PTO Data Portal/Map Data"
# SharePoint's REST API returns Atom XML unless Accept asks for JSON.
_SP_JSON = {"Accept": "application/json;odata=nometadata"}


def _sp_list(server_relative_path: str, kind: str, select: str) -> list[dict]:
    """List ``Folders`` or ``Files`` of a SharePoint folder anonymously."""
    url = (
        f"{SP_HOST}/property/dataportal/_api/web/"
        f"GetFolderByServerRelativeUrl('{quote(server_relative_path)}')/{kind}"
        f"?$select={select}&$top=500"
    )
    try:
        return json.loads(fetch_text(url, headers=_SP_JSON))["value"]
    except (json.JSONDecodeError, KeyError) as e:
        raise HttpError(f"unexpected SharePoint listing response for {server_relative_path}: {e}")


def _latest_par_listing() -> tuple[str, list[dict]]:
    """Return (vintage, PAR file listing) for the newest populated vintage."""
    folders = _sp_list(MAP_DATA_PATH, "Folders", "Name")
    vintages = sorted(
        (f["Name"] for f in folders if re.fullmatch(r"\d{4}F", f["Name"])),
        reverse=True,
    )
    for vintage in vintages:
        try:
            files = _sp_list(
                f"{MAP_DATA_PATH}/{vintage}/{vintage} PAR",
                "Files",
                "Name,ServerRelativeUrl,Length,TimeLastModified",
            )
        except HttpError:
            continue  # vintage folder without a PAR subfolder yet
        files = [f for f in files if f["Name"].lower().endswith(".zip")]
        if files:
            return vintage, files
    raise HttpError("no populated <year>F PAR folder found under FDOR Map Data")


class FdorNal(DataSource):
    id = "fdor_nal"
    # Version is a byproduct of the fetch (year/month walk or archive
    # listing) — the puller uses the returned FetchResult.remote_version (#264).
    derives_version_on_fetch = True
    name = "FL FDOR — Name/Address/Legal (per-county tax roll)"
    category = CATEGORY_PARCELS
    coverage = "State: Florida (all 67 counties)"
    cadence = "Annual (mid-year release)"
    estimated_size_mb = 4200.0  # 69 PAR zips (67 counties + 2 condo extras), 4.14 GB in 2025F
    update_cadence_days = 365
    # 69 sequential zip downloads (~4 GB): an interrupted run keeps its
    # already-extracted per-county dirs and skips them on the next run.
    supports_resume = True
    description = (
        "Florida Department of Revenue per-county PAR parcel shapefiles — "
        "parcel polygons joined with NAL (Name-Address-Legal) tax-roll "
        "attributes. Per-county annual files with owner name, mailing "
        "address, just/assessed value, use code, and land/improvement "
        "values, all carrying geometry. Replaces the FGDL DSL state-land "
        "layer previously tracked. Ships all 67 Florida counties."
    )
    legal = LegalInfo(
        publisher="Florida Department of Revenue (FDOR)",
        license="Florida public records (Ch. 119, F.S.) — commercial reuse permitted with attribution",
        license_url=LANDING_PAGE,
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        manual_url=LANDING_PAGE,
        attribution=(
            "Source: Florida Department of Revenue, Property Tax Oversight, "
            "per-county PAR shapefile (PIN + NAL joined)."
        ),
        notes=(
            "Auto-fetch flipped from MANUAL_ONLY 2026-07-03: every PAR zip "
            "is a direct anonymous HTTPS download from the Map Data "
            "SharePoint library (listed via its anonymous REST API); no "
            "click-through or license interstitial exists, and robots.txt "
            "permits the data portal. The walkthrough is retained as the "
            "fallback.\n"
            "\n"
            "Two shapefile flavors are published: PIN (geometry only) and "
            "PAR (PIN joined with current-year NAL). We use PAR. Join key "
            "inside the file is PARCELNO. Some polygons won't have NAL "
            "matches (Ch. 119 redactions, rights-of-way, condos w/o "
            "individually mapped units, ownership-unknown parcels) — the "
            "normalizer will keep them with null owner columns.\n"
            "\n"
            "Miami-Dade and St. Johns ship separate condo property files "
            "alongside the main PAR — grab those too (Miami-Dade is in v1).\n"
            "\n"
            "Schema reference: see Parcel Shapefiles Readme + the FDOR "
            "User's Guide for Department Property Tax Data Files."
        ),
    )

    def remote_version(self) -> str:
        vintage, files = _latest_par_listing()
        newest = max(f["TimeLastModified"] for f in files)
        return f"{vintage}:{newest[:10]}"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        vintage, listing = _latest_par_listing()
        rv = f"{vintage}:{max(f['TimeLastModified'] for f in listing)[:10]}"
        listing = sorted(listing, key=lambda f: f["Name"].lower())
        total = sum(int(f["Length"]) for f in listing)

        done = 0
        written: list[Path] = []
        for item in listing:
            name = item["Name"]
            county_dir = dest_dir / name[:-4]  # matches the manual-upload layout
            # Resume: a non-empty per-county dir means that zip already
            # downloaded + extracted on a previous interrupted run.
            if county_dir.is_dir() and any(county_dir.iterdir()):
                written.extend(p for p in county_dir.rglob("*") if p.is_file())
            else:
                url = SP_HOST + quote(item["ServerRelativeUrl"])
                files, _ = fetch_zip_extracted(
                    url,
                    dest_dir,
                    progress,
                    zip_name=name,
                    extract_to=county_dir,
                    expected_min_bytes=100_000,
                    progress_offset=done,
                    progress_total=total,
                )
                written.extend(files)
            done += int(item["Length"])
            progress(done, total, name)
        return FetchResult(files=written, remote_version=rv, total_bytes=done)

    def manual_walkthrough(self) -> ManualWalkthrough:
        # Format as a 3-column checklist so 67 names don't dominate the modal.
        col_h = (len(FL_COUNTIES) + 2) // 3
        cols = [FL_COUNTIES[i : i + col_h] for i in range(0, len(FL_COUNTIES), col_h)]
        rows = []
        for r in range(col_h):
            cells = [cols[c][r] if r < len(cols[c]) else "" for c in range(len(cols))]
            rows.append("  " + "  ·  ".join(f"{n:<14}" for n in cells))
        county_list = "\n".join(rows)
        return ManualWalkthrough(
            landing_page_url=LANDING_PAGE,
            steps=[
                ManualStep(
                    title="Open the FDOR Assessment Roll / GIS Data portal",
                    body=(
                        "Click the deep link below. Expand **Download "
                        "Current Assessment Roll and GIS Data** on the page; "
                        "you'll see links to the Tax Roll Data File "
                        "directory, the Map Data directory, the Parcel "
                        "Shapefiles Readme, and the FGIO Open Data Portal."
                    ),
                    deep_link=LANDING_PAGE,
                ),
                ManualStep(
                    title="(Optional) Skim the Parcel Shapefiles Readme",
                    body=(
                        "Confirms two key facts: (1) you want the **PAR** "
                        "shapefiles (PIN + NAL already joined), not PIN; "
                        "(2) Miami-Dade and St. Johns ship separate "
                        "condominium files."
                    ),
                    deep_link=MAP_DATA_README,
                ),
                ManualStep(
                    title="Open the Map Data directory",
                    body=(
                        "Click **Map Data directory** from the expanded "
                        "section. You'll see one folder per Florida "
                        "county (67 total) plus a year selector. Pick the "
                        "latest available year — typically the previous tax "
                        "year, refreshed each August."
                    ),
                ),
                ManualStep(
                    title="Download all 67 PAR shapefiles",
                    body=(
                        "FDOR publishes one PAR zip per Florida county. "
                        "Download **all 67** — the file naming pattern is "
                        "`<county>_2025par.zip` (a few use `2025Ppar.zip` "
                        "— same format, FDOR is just inconsistent). Skip "
                        "any `PIN` zips: PIN is geometry only, no owner "
                        "data.\n"
                        "\n"
                        "Also grab the two condo extras (separate files):\n"
                        "  • `miamidade_condos_2025par.zip`\n"
                        "  • `stjohnscondos_2025.zip`\n"
                        "\n"
                        "The 67 counties (alphabetical):\n"
                        f"\n{county_list}\n"
                        "\nEach PAR zip is ~30–150 MB; total ~2-3 GB. The "
                        "portal serves them directly — no queueing. Tip: "
                        "right-click → 'Save Link As' (or middle-click) on "
                        "each name to bulk-download without leaving the page."
                    ),
                ),
                ManualStep(
                    title="Upload via the puller (or drop into current/ by hand)",
                    body=(
                        "Easiest: click **⤴ Upload file(s)…** in the puller "
                        "and select all downloaded ZIPs at once — the puller "
                        "auto-extracts each into "
                        "`data/raw/fdor_nal/current/<county>/`. The "
                        "normalizer uses rglob, so per-county subfolders "
                        "are fine.\n"
                        "\n"
                        "Manual alternative: extract each ZIP and drop the "
                        "shapefile parts into `data/raw/fdor_nal/current/` "
                        "directly. Keep file sets (`.shp`, `.shx`, `.dbf`, "
                        "`.prj`) together."
                    ),
                ),
                ManualStep(
                    title="Click 'I'm done' to verify + record",
                    body=(
                        "The puller will confirm the directory is non-empty "
                        "and run `validate()`. Once recorded, the preprocess "
                        "step (Section 5) will normalize each county into "
                        "the canonical `parcel` schema and concatenate them "
                        "into the FL state composite."
                    ),
                ),
            ],
            expected_files=["*.shp", "*.dbf", "*.shx", "*.prj"],
            notes_on_failure=(
                "If FDOR's Map Data directory listing looks broken for a "
                "given county, the same PAR data is mirrored on the FGIO "
                "Open Data Portal (linked from the main page). Avoid the "
                "Tax Roll Data File directory — those are the standalone "
                "NAL CSVs without geometry; PAR shapefiles already have "
                "those attributes joined."
            ),
        )


SOURCE = FdorNal()
