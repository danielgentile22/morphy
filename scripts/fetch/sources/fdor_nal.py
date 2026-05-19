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
this source is MANUAL_ONLY with a walkthrough that lists the v1
representative counties.

V1 county coverage (locked in :: docs/SCOPE.md):
  Miami-Dade, Hillsborough, Orange, Duval, Pinellas, Lee, Polk,
  Brevard, Volusia, Marion — 10 counties covering ~60% of FL
  population and a representative geographic / market mix.

Miami-Dade and St. Johns maintain condo records in separate files
(per the FDOR shapefile readme). Miami-Dade is in v1, so the
walkthrough flags grabbing those extras too.
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

# V1 representative counties — see docs/SCOPE.md for the rationale on
# why these ten (not all 67). The FDOR portal exposes one ZIP per
# county per year.
V1_COUNTIES: list[tuple[str, str]] = [
    ("Miami-Dade", "23"),
    ("Hillsborough", "29"),
    ("Orange", "48"),
    ("Duval", "16"),
    ("Pinellas", "52"),
    ("Lee", "36"),
    ("Polk", "53"),
    ("Brevard", "05"),
    ("Volusia", "64"),
    ("Marion", "42"),
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
    coverage = "State: Florida (10 representative counties for v1)"
    cadence = "Annual (mid-year release)"
    estimated_size_mb = 500.0  # ~10 counties × ~40-100 MB CSV each
    update_cadence_days = 365
    description = (
        "Florida Department of Revenue per-county PAR parcel shapefiles — "
        "parcel polygons joined with NAL (Name-Address-Legal) tax-roll "
        "attributes. Per-county annual files with owner name, mailing "
        "address, just/assessed value, use code, and land/improvement "
        "values, all carrying geometry. Replaces the FGDL DSL state-land "
        "layer previously tracked. V1 ships 10 representative counties "
        "(~60% of FL population)."
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
        county_list = "\n".join(f"  - {name} (county code {code})" for name, code in V1_COUNTIES)
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
                    title="Download the PAR shapefile for each v1 county",
                    body=(
                        "For each county below, download the **PAR** zip "
                        "(not PIN — PIN has no owner data). The 10 v1 "
                        "counties:\n"
                        f"\n{county_list}\n"
                        "\nFor **Miami-Dade**, also grab any condo-related "
                        "files in that county's folder (separate from the "
                        "main PAR zip). Each PAR zip is ~30–150 MB. The "
                        "portal serves them directly — no queueing."
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
