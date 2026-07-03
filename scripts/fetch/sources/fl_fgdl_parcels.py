"""Florida — FGDL DSL parcel composite (state-owned land).

The Florida Geographic Data Library (FGDL) at the University of Florida
publishes the Division of State Lands parcel composite — Florida's
STATE-OWNED land parcels. It complements ``fdor_nal`` (private taxable
parcels with owners); it is not a substitute for it. ~241K parcels in
the FL composite come from this layer.

The release filename embeds month/year (dsl_parcel_composite_oct25.zip),
so the fetcher discovers the newest file from the browsable
/zips/geospatial_data/current/ listing — same pattern as the WV vintage
discovery.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..base import (
    CATEGORY_PARCELS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ..walkthroughs import ManualStep, ManualWalkthrough
from ._helpers import fetch_zip_extracted, version_from_head

FGDL_CURRENT_DIR = "https://fgdl.org/zips/geospatial_data/current/"

_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


class FlFgdlParcels(DataSource):
    id = "fl_fgdl_parcels"
    name = "Florida state-owned land parcels (FGDL DSL composite)"
    category = CATEGORY_PARCELS
    coverage = "State: Florida"
    cadence = "Annual (filename embeds month/year, e.g. oct25)"
    estimated_size_mb = 173.0
    update_cadence_days = 365
    description = (
        "Florida Division of State Lands parcel composite published by "
        "the UF GeoPlan Center FGDL — polygons for STATE-OWNED land "
        "(facility name, acreage, land category). Complements the FDOR "
        "NAL private tax rolls; a tower on state land is not a private-"
        "landowner lead."
    )
    legal = LegalInfo(
        publisher="Florida Geographic Data Library (UF GeoPlan)",
        license="FGDL terms of use (free, with attribution)",
        license_url="https://fgdl.org/",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        manual_url=FGDL_CURRENT_DIR,
        attribution="Source: FGDL, University of Florida GeoPlan Center.",
        notes=(
            "Auto-fetch flipped from MANUAL_ONLY 2026-07-03: the zip is a "
            "direct anonymous HTTPS download (no click-through, no login) "
            "and fgdl.org/robots.txt disallows only /wp-admin/. MANUAL_ONLY "
            "had only ever encoded the changing filename, not a legal bar; "
            "the fetcher now discovers the newest "
            "dsl_parcel_composite_<mon><yy>.zip from the browsable listing. "
            "The walkthrough is retained as the fallback.\n"
            "\n"
            "License: FGDL terms of use — free, attribution required "
            "(retained in `attribution`). Commercial use allowed with "
            "attribution.\n"
            "\n"
            "This is the Division of State Lands composite (state-owned "
            "parcels; FACILITY_NAME is not a private owner) — do not "
            "conflate with the FDOR NAL tax rolls."
        ),
    )

    def _latest_zip(self) -> tuple[str, str]:
        """Discover the newest dsl_parcel_composite zip from the listing."""
        listing = fetch_text(FGDL_CURRENT_DIR)
        tags = set(re.findall(r"dsl_parcel_composite_([a-z]{3}\d{2})\.zip", listing))
        dated = [(t, 2000 + int(t[3:]), _MONTHS.index(t[:3])) for t in tags if t[:3] in _MONTHS]
        if not dated:
            raise HttpError(f"no dsl_parcel_composite_<mon><yy>.zip found at {FGDL_CURRENT_DIR}")
        tag = max(dated, key=lambda d: (d[1], d[2]))[0]
        return f"{FGDL_CURRENT_DIR}dsl_parcel_composite_{tag}.zip", tag

    def remote_version(self) -> str:
        url, tag = self._latest_zip()
        return f"{tag}:{version_from_head(url, label=self.id)}"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        url, tag = self._latest_zip()
        rv = f"{tag}:{version_from_head(url, label=self.id)}"
        files, n = fetch_zip_extracted(
            url,
            dest_dir,
            progress,
            zip_name=url.rsplit("/", 1)[1],
            expected_min_bytes=100_000_000,
        )
        return FetchResult(files=files, remote_version=rv, total_bytes=n)

    def manual_walkthrough(self) -> ManualWalkthrough:
        return ManualWalkthrough(
            landing_page_url=FGDL_CURRENT_DIR,
            steps=[
                ManualStep(
                    title="Download the newest DSL parcel composite zip",
                    body=(
                        "Browse the FGDL current-data listing and download the "
                        "newest `dsl_parcel_composite_<mon><yy>.zip` (~173 MB; "
                        "direct download, no login or click-through)."
                    ),
                    deep_link=FGDL_CURRENT_DIR,
                ),
                ManualStep(
                    title="Install the zip",
                    body=(
                        "Use install-from-file (`i` in the data TUI) on the "
                        "downloaded zip — it extracts the "
                        "`dsl_parcel_composite_<mon><yy>.gdb/` File Geodatabase "
                        "into `data/raw/fl_fgdl_parcels/current/` and stamps "
                        "the manifest."
                    ),
                ),
            ],
            expected_files=["dsl_parcel_composite_<mon><yy>.gdb/"],
            notes_on_failure=(
                "If the listing has no dsl_parcel_composite zip, FGDL has "
                "restructured — start from https://fgdl.org/ and search for "
                "'DSL parcel composite'."
            ),
        )


SOURCE = FlFgdlParcels()
