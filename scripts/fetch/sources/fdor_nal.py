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

The portal requires per-county selection + license click-through, so
this source is MANUAL_ONLY with a walkthrough that covers all 67
Florida counties.

V1 coverage: **all 67 Florida counties** (per docs/SCOPE.md). FDOR
publishes one PAR ZIP per county on the Map Data directory; the user
downloads them in one batch and uploads via the puller.

Miami-Dade and St. Johns maintain condo records in separate files
(per the FDOR shapefile readme) — the walkthrough flags grabbing
those condo extras alongside the main per-county PAR ZIPs.
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
from ..walkthroughs import ManualStep, ManualWalkthrough

# All 67 Florida counties — FDOR publishes one PAR ZIP per county on
# the Map Data directory. Listed alphabetically to match the directory
# listing order; the walkthrough uses this as a download checklist.
FL_COUNTIES: list[str] = [
    "Alachua", "Baker", "Bay", "Bradford", "Brevard", "Broward",
    "Calhoun", "Charlotte", "Citrus", "Clay", "Collier", "Columbia",
    "DeSoto", "Dixie", "Duval", "Escambia", "Flagler", "Franklin",
    "Gadsden", "Gilchrist", "Glades", "Gulf", "Hamilton", "Hardee",
    "Hendry", "Hernando", "Highlands", "Hillsborough", "Holmes",
    "Indian River", "Jackson", "Jefferson", "Lafayette", "Lake", "Lee",
    "Leon", "Levy", "Liberty", "Madison", "Manatee", "Marion", "Martin",
    "Miami-Dade", "Monroe", "Nassau", "Okaloosa", "Okeechobee", "Orange",
    "Osceola", "Palm Beach", "Pasco", "Pinellas", "Polk", "Putnam",
    "Santa Rosa", "Sarasota", "Seminole", "St. Johns", "St. Lucie",
    "Sumter", "Suwannee", "Taylor", "Union", "Volusia", "Wakulla",
    "Walton", "Washington",
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


class FdorNal(DataSource):
    id = "fdor_nal"
    name = "FL FDOR — Name/Address/Legal (per-county tax roll)"
    category = CATEGORY_PARCELS
    coverage = "State: Florida (all 67 counties)"
    cadence = "Annual (mid-year release)"
    estimated_size_mb = 3500.0  # 67 counties × ~30-100 MB PAR ZIP each
    update_cadence_days = 365
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
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        manual_url=LANDING_PAGE,
        attribution=(
            "Source: Florida Department of Revenue, Property Tax Oversight, "
            "per-county PAR shapefile (PIN + NAL joined)."
        ),
        notes=(
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
        # MANUAL_ONLY — version is whatever the user pulled. The puller
        # marks local_version='manual' on walkthrough completion.
        return "manual"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        raise RuntimeError(f"{self.id} is MANUAL_ONLY — see walkthrough.")

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
