"""EIA Form 860M — monthly update between annual EIA-860 releases.

EIA's URL pattern changed in 2025: the legacy ``xls/eia860m.xlsx`` path
now returns an HTML error page (~67 KB), and the real files live at
``xls/{month}_generator{year}.xlsx`` (current month) or
``archive/xls/{month}_generator{year}.xlsx`` (older months).

We probe backwards from the current month to find the most recent file
that's actually big enough to be the real workbook (~13 MB; reject
anything < 1 MB as a placeholder).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from ..base import (
    CATEGORY_SOLAR,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import head_size_ok

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

CURRENT_PATTERN = "https://www.eia.gov/electricity/data/eia860m/xls/{month}_generator{year}.xlsx"
ARCHIVE_PATTERN = (
    "https://www.eia.gov/electricity/data/eia860m/archive/xls/{month}_generator{year}.xlsx"
)

MIN_REAL_BYTES = 1_000_000  # real workbooks are ~13 MB; HTML stubs are ~67 KB


def _latest_month_url() -> tuple[str, str]:
    """Walk months backwards from today; return (url, 'YYYY-MM') of the newest real file.

    EIA publishes ~2 months behind, so we have to walk back several months.
    Try the current-path first, then the archive path for older months.
    """
    today = date.today()
    year, month = today.year, today.month
    for _ in range(24):  # up to 2 years back
        m_name = MONTHS[month - 1]
        for pattern in (CURRENT_PATTERN, ARCHIVE_PATTERN):
            url = pattern.format(month=m_name, year=year)
            # require_length: a monthly workbook always advertises its
            # size — a length-less 200 here is a stub, not a release.
            if head_size_ok(url, MIN_REAL_BYTES, require_length=True):
                return url, f"{year}-{month:02d}"
        # Step one month earlier
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    raise HttpError("no recent EIA-860M file reachable")


class Eia860M(DataSource):
    id = "eia_860m"
    # Version is a byproduct of the fetch (year/month walk or archive
    # listing) — the puller uses the returned FetchResult.remote_version (#264).
    derives_version_on_fetch = True
    name = "EIA Form 860M (monthly)"
    category = CATEGORY_SOLAR
    coverage = "National"
    cadence = "Monthly (~2 months publication lag)"
    estimated_size_mb = 14.0
    update_cadence_days = 30
    description = (
        "Monthly snapshot of operating, planned and retired generators, "
        "covering the lag between annual EIA-860 releases. Same generator-"
        "level detail in a single Excel workbook. Use to catch new utility-"
        "scale solar plants that came online recently."
    )
    legal = LegalInfo(
        publisher="U.S. Energy Information Administration (EIA)",
        license="Public Domain (US federal government work)",
        license_url="https://www.eia.gov/about/copyrights_reuse.php",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Landing page lists every monthly file by name. The current file's
        # specific URL changes each month so a stable direct link isn't
        # possible.
        manual_url="https://www.eia.gov/electricity/data/eia860m/",
        attribution="Source: U.S. Energy Information Administration, Form EIA-860M.",
        notes=(
            "On the EIA-860M page, find the newest 'Survey 860M' entry "
            "(approx. 2 months behind current — e.g. March 2026 data is "
            "published in May). Click the .xlsx link — file is named "
            "{month}_generator{year}.xlsx (~13 MB).\n"
            "\n"
            "After download: drop into data/raw/eia_860m/current/ (any "
            "filename works).\n"
            "\n"
            "Workbook has 'Operating', 'Planned', 'Retired' sheets — same "
            "schema as annual EIA-860. Use this for plants that came "
            "online since the last annual release."
        ),
    )

    def remote_version(self) -> str:
        _url, version = _latest_month_url()
        return version

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        url, version = _latest_month_url()
        # Preserve the natural EIA filename so verify_raw / preprocessing
        # can identify the month.
        filename = url.rsplit("/", 1)[-1]
        out = dest_dir / filename
        n = download(
            url,
            out,
            lambda done, tot: progress(done, tot, filename),
            expected_min_bytes=MIN_REAL_BYTES,
        )
        return FetchResult(
            files=[out],
            remote_version=version,
            total_bytes=n,
        )


SOURCE = Eia860M()
