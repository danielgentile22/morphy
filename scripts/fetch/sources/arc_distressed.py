"""Appalachian Regional Commission — county economic-status designations.

ARC publishes annual county-level economic-status classifications:
Distressed / At-Risk / Transitional / Competitive / Attainment. Released
as an Excel workbook + interactive map.

The Excel is on a stable ARC site but the URL embeds the fiscal year,
which changes annually. We probe the most recent plausible FY.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..base import (
    CATEGORY_DISTRESS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo

# ARC renamed the xlsx files repeatedly (FY2026 release used
# "CountyEconomicStatusandDistressAreasFY2026DataTables.xlsx" with no
# hyphens, not the old "FY2026-County-Economic-Status-..." pattern).
# Rather than guess the filename, hit the FY landing page and scrape
# the first .xlsx it links to.
FY_PAGE_PATTERN = (
    "https://www.arc.gov/about-the-appalachian-region/"
    "county-economic-status-and-distressed-areas-by-state-fy-{fy}/"
)
# Older years are at the no-prefix slug.
LEGACY_PAGE_PATTERN = (
    "https://www.arc.gov/county-economic-status-and-distressed-areas-by-state-fy-{fy}/"
)


class ArcDistressed(DataSource):
    id = "arc_distressed"
    name = "ARC County Economic Status (Appalachian region)"
    category = CATEGORY_DISTRESS
    coverage = "Appalachian region (13 states, 423 counties)"
    cadence = "Annual (fiscal year, June)"
    estimated_size_mb = 0.3
    description = (
        "ARC's annual classification of each Appalachian county into one "
        "of five economic-status tiers, based on a composite of three-"
        "year-average unemployment, per-capita market income, and poverty "
        "rate vs. national averages. 'Distressed' is the most severe."
    )
    legal = LegalInfo(
        publisher="Appalachian Regional Commission (ARC)",
        license="Public Domain (federal-state partnership)",
        license_url="https://www.arc.gov/data-sources/",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # FY page lists the current year's xlsx link prominently — more
        # stable than the raw xlsx URL since ARC renames the files yearly.
        manual_url=(
            "https://www.arc.gov/about-the-appalachian-region/"
            "county-economic-status-and-distressed-areas-by-state-fy-2026/"
        ),
        attribution="Source: Appalachian Regional Commission.",
        notes=(
            "On the FY page, scroll to 'Data Tables' and click the "
            "'County Economic Status and Distress Areas FY2026 Data "
            "Tables' xlsx link (~0.3 MB).\n"
            "\n"
            "After download: save into data/raw/arc_distressed/current/ "
            "(any filename — the puller's auto-fetch saves it as "
            "arc_county_economic_status_FY<year>.xlsx).\n"
            "\n"
            "If a newer FY page exists (June each year — try FY-2027 etc.), "
            "swap the year in the URL.\n"
            "\n"
            "The workbook lists every Appalachian county with its economic "
            "status tier (Distressed / At-Risk / Transitional / Competitive "
            "/ Attainment) and the underlying 3-yr unemployment, per-capita "
            "income, and poverty-rate components."
        ),
    )

    def _xlsx_on_page(self, page_url: str) -> str | None:
        try:
            html = fetch_text(page_url)
        except HttpError:
            return None
        m = re.search(r'https?://[^\s"\'<>]+\.xlsx', html)
        return m.group(0) if m else None

    def _latest(self) -> tuple[str, str]:
        # Fiscal-year file FYn is typically published in May/June of year n.
        # Try FY = current calendar year first, then walk back.
        cy = date.today().year
        for fy in (cy + 1, cy, cy - 1, cy - 2):
            for page_pat in (FY_PAGE_PATTERN, LEGACY_PAGE_PATTERN):
                xlsx = self._xlsx_on_page(page_pat.format(fy=fy))
                if xlsx:
                    return xlsx, f"FY{fy}"
        raise HttpError("no recent ARC distressed file reachable")

    def remote_version(self) -> str:
        _, v = self._latest()
        return v

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        url, version = self._latest()
        out = dest_dir / f"arc_county_economic_status_{version}.xlsx"
        n = download(
            url,
            out,
            lambda done, tot: progress(done, tot, out.name),
            expected_min_bytes=10_000,
        )
        return FetchResult(files=[out], remote_version=version, total_bytes=n)


SOURCE = ArcDistressed()
