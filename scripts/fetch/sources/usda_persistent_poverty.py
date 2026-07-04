"""USDA Economic Research Service — Persistent Poverty Counties.

ERS publishes a county-typology dataset including the "persistent
poverty" flag (poverty ≥20% in every census from 1980-2020). Available
as a CSV from the ERS site.

The ERS rebuilds the typology after each decennial census + an updated
ACS estimate cycle; the same URL points to the latest. Because the ERS
publishing system requires interactive selection, the canonical CSV link
is documented but flagged TOLERATED — we attempt the direct file and
fall back gracefully if ERS changes their CMS path.
"""

from __future__ import annotations

from pathlib import Path

from ..base import (
    CATEGORY_DISTRESS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import version_from_head

# County Typology Codes 2025 — persistent-poverty flag included.
# ERS migrated from Laserfiche /sites/default/files paths to /media/<id>/
# in early 2026; the new URL is stable on the post-migration site.
DOWNLOAD_URL = "https://www.ers.usda.gov/media/6174/ers-county-typology-codes-2025-edition.csv"


class UsdaPersistentPoverty(DataSource):
    id = "usda_persistent_poverty"
    name = "USDA ERS Persistent Poverty Counties"
    category = CATEGORY_DISTRESS
    coverage = "National (county-level)"
    cadence = "Per decennial census + ACS refresh (~5 years)"
    estimated_size_mb = 1.0
    update_cadence_days = None
    description = (
        "USDA ERS County Typology Codes file. Contains a persistent-"
        "poverty flag (county poverty ≥20% in every census 1980→present). "
        "Joinable to any layer by 5-digit FIPS code."
    )
    legal = LegalInfo(
        publisher="USDA Economic Research Service (ERS)",
        license="Public Domain (US federal government work)",
        license_url="https://www.usda.gov/policies-and-links",
        automation=AutomationPolicy.TOLERATED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct CSV download — clicking grabs the file (~6 MB).
        manual_url=(
            "https://www.ers.usda.gov/media/6174/ers-county-typology-codes-2025-edition.csv"
        ),
        attribution="Source: USDA ERS County Typology Codes.",
        notes=(
            "Direct download: ers-county-typology-codes-2025-edition.csv "
            "(~6 MB). Clicking the manual URL grabs it directly.\n"
            "\n"
            "ERS data product page (with documentation + older editions): "
            "https://www.ers.usda.gov/data-products/county-typology-codes\n"
            "\n"
            "After download: save as data/raw/usda_persistent_poverty/"
            "current/county_typology_codes.csv\n"
            "\n"
            "Columns include FIPStxt (5-digit FIPS), State, County_Name, "
            "and one row per attribute — High_Persistent_Poverty_2024 / "
            "_2010 / etc. flags. Joinable to any county-level layer."
        ),
    )

    def remote_version(self) -> str:
        try:
            return version_from_head(DOWNLOAD_URL, label=self.id)
        except HttpError:
            raise  # network failure → check_failed, as before
        except RuntimeError:
            # Headerless 200 — historical behavior records a placeholder
            # version rather than failing the check sweep.
            return "unknown"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        # The puller captures remote_version once before the download (#264).
        out = dest_dir / "county_typology_codes.csv"
        n = download(
            DOWNLOAD_URL,
            out,
            lambda done, tot: progress(done, tot, out.name),
            expected_min_bytes=10_000,
        )
        return FetchResult(
            files=[out],
            total_bytes=n,
        )


SOURCE = UsdaPersistentPoverty()
