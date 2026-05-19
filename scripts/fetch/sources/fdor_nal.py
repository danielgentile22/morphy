"""Florida Department of Revenue — Name, Address, Legal (NAL) tax roll.

FDOR publishes per-county annual NAL files containing parcel-level
owner name, mailing address, just/assessed value, use code, land /
improvement value, year built. This is the canonical FL landowner-data
source — it replaces the FL FGDL DSL state-land parcel layer that was
previously in the registry (DSL covers state-owned land, not the
private parcels we care about).

The portal requires per-county selection + license click-through, so
this source is MANUAL_ONLY with a walkthrough that lists the v1
representative counties.

V1 county coverage (locked in :: docs/SCOPE.md):
  Miami-Dade, Hillsborough, Orange, Duval, Pinellas, Lee, Polk,
  Brevard, Volusia, Marion — 10 counties covering ~60% of FL
  population and a representative geographic / market mix.
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


class FdorNal(DataSource):
    id = "fdor_nal"
    name = "FL FDOR — Name/Address/Legal (per-county tax roll)"
    category = CATEGORY_PARCELS
    coverage = "State: Florida (10 representative counties for v1)"
    cadence = "Annual (mid-year release)"
    estimated_size_mb = 500.0  # ~10 counties × ~40-100 MB CSV each
    update_cadence_days = 365
    description = (
        "Florida Department of Revenue's NAL (Name, Address, Legal) "
        "tax-roll dataset — per-county annual files containing every "
        "parcel's owner name, mailing address, just/assessed value, "
        "use code, year built, and land/improvement values. The "
        "canonical landowner-data source for FL; replaces the FGDL "
        "DSL state-land layer previously tracked. V1 ships 10 "
        "representative counties (~60% of FL population)."
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
            "Name-Address-Legal (NAL) file."
        ),
        notes=(
            "Portal requires per-county selection + click-through accepting "
            "FDOR's redistribution terms. Per-county files come as ZIPs "
            "containing one fixed-width or CSV file per county. Drop every "
            "county's ZIP (or extracted file) into "
            "data/raw/fdor_nal/current/ before clicking 'I'm done' in the "
            "walkthrough; the normalizer will read whichever counties are "
            "present.\n"
            "\n"
            "Schema reference: https://floridarevenue.com/property/Documents/"
            "DataPortal_NAL_Layout.pdf (field map for NAL CSV columns)."
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
                        "Click the deep link below. The page lists FDOR's "
                        "per-county tax-roll downloads. You'll need to accept "
                        "the redistribution terms once at the top of the page."
                    ),
                    deep_link=LANDING_PAGE,
                ),
                ManualStep(
                    title="Select 'NAL — Name, Address, Legal' as the file type",
                    body=(
                        "On the portal, choose **NAL — Name, Address, Legal** "
                        "from the file-type dropdown (not GIS shapefile, not "
                        "SDF). NAL is the file that contains owner name + "
                        "mailing address — the columns we care about for "
                        "landowner outreach."
                    ),
                ),
                ManualStep(
                    title="Select the current assessment year",
                    body=(
                        "Pick the latest year FDOR exposes (typically the "
                        "previous tax year, released mid-current-year). The "
                        "puller will tag whatever year you select as the "
                        "snapshot's local_version."
                    ),
                ),
                ManualStep(
                    title="Download the v1 representative counties",
                    body=(
                        "Download the NAL file for each of these 10 counties "
                        "(in any order):\n"
                        f"\n{county_list}\n"
                        "\nEach file is ~30–100 MB. The portal queues "
                        "downloads — give it a few minutes. If a county fails, "
                        "retry it individually from the portal."
                    ),
                ),
                ManualStep(
                    title="Drop every county file into data/raw/fdor_nal/current/",
                    body=(
                        "Move every downloaded ZIP (or extracted CSV) into\n"
                        "```\n"
                        "data/raw/fdor_nal/current/\n"
                        "```\n"
                        "Naming convention: keep FDOR's filenames "
                        "(`NAL11F202xxxxxxxxx.zip` etc.) — the normalizer "
                        "parses the embedded county code. Mixing CSVs and "
                        "ZIPs is OK; the normalizer reads both."
                    ),
                ),
                ManualStep(
                    title="Click 'I'm done' to verify + record",
                    body=(
                        "The puller will check that the directory is non-"
                        "empty and run validate(). Once recorded, the "
                        "preprocess step (Section 5) will normalize each "
                        "county into the canonical `parcel` schema and "
                        "concatenate them into the FL state composite."
                    ),
                ),
            ],
            expected_files=["*.zip", "*.csv", "*.txt"],
            notes_on_failure=(
                "If the FDOR portal blocks download (rare, but happens during "
                "their mid-year tax-roll roll-out), retry the next day — they "
                "stage county-by-county and the portal sometimes serves a "
                "stub file. Look for 'NAL' in the filename; ignore SDF "
                "(state-domain) files."
            ),
        )


SOURCE = FdorNal()
