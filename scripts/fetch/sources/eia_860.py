"""EIA Form 860 — annual utility-scale generator detail.

URL pattern: https://www.eia.gov/electricity/data/eia860/archive/xls/eia860{YEAR}.zip
Plus the "current year" file at .../xls/eia860.zip after Sep release.

Strategy: probe the most recent plausible year (Sept onwards) and fall
back through prior years. The latest year that returns 200 OK is the
remote version.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from ..base import (
    CATEGORY_SOLAR,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, download, head
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import safe_extract_zip


# EIA hosts past years at /xls/eia860{year}.zip (the /archive/xls/ path
# became a stub returning a tiny placeholder in 2025). The current-year
# release is at /xls/eia860.zip.
ARCHIVE_PATTERN = "https://www.eia.gov/electricity/data/eia860/xls/eia860{year}.zip"
CURRENT_URL = "https://www.eia.gov/electricity/data/eia860/xls/eia860.zip"


def _probe_url(url: str, min_bytes: int = 1_000_000) -> bool:
    """Check that ``url`` resolves AND returns a file bigger than placeholder.

    EIA serves ~67 KB stub pages for unreleased archive years that return
    200 OK — without the size check the year-probe falsely picks them as
    the 'latest available' archive.
    """
    try:
        h = head(url)
        if not h.get("status", "").startswith("2"):
            return False
        cl = h.get("content_length")
        if cl is not None:
            try:
                if int(cl) < min_bytes:
                    return False
            except (TypeError, ValueError):
                pass
        return True
    except HttpError:
        return False


class Eia860(DataSource):
    id = "eia_860"
    name = "EIA Form 860 (annual)"
    category = CATEGORY_SOLAR
    coverage = "National (all US utility-scale generators ≥1 MW)"
    cadence = "Annual (released ~September)"
    estimated_size_mb = 25.0
    description = (
        "Generator-level detail for all US power plants ≥1 MW (solar, "
        "wind, gas, coal, nuclear, etc). The Solar tab gives plant code, "
        "owner, county/state, lat/lon, nameplate capacity, online date, "
        "tracking type (fixed/1-axis/2-axis). Authoritative for utility-"
        "scale solar locations."
    )
    legal = LegalInfo(
        publisher="U.S. Energy Information Administration (EIA)",
        license="Public Domain (US federal government work)",
        license_url="https://www.eia.gov/about/copyrights_reuse.php",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct link to the most recent annual archive (~22 MB).
        manual_url="https://www.eia.gov/electricity/data/eia860/xls/eia8602024.zip",
        attribution="Source: U.S. Energy Information Administration, Form EIA-860.",
        notes=(
            "Direct download: eia8602024.zip (~22 MB, the 2024 reporting "
            "year — latest published as of 2026). If a newer year is out "
            "(EIA releases in September), substitute the year:\n"
            "  https://www.eia.gov/electricity/data/eia860/xls/eia860<YYYY>.zip\n"
            "\n"
            "EIA-860 landing page lists every archive year: "
            "https://www.eia.gov/electricity/data/eia860/\n"
            "\n"
            "After download: unzip into data/raw/eia_860/current/. "
            "The '3_1_Generator_Y<year>.xlsx' sheet has coordinates and "
            "capacity per generator; '3_3_Solar_Y<year>.xlsx' is the solar-"
            "specific extract."
        ),
    )

    def _latest_year_url(self) -> tuple[str, str]:
        """Return (url, version_string) for the newest available archive year."""
        # Try newest first; final-year publication is ~September of (year+1)
        this_year = date.today().year
        candidates = [this_year - 1, this_year - 2, this_year - 3]
        for y in candidates:
            url = ARCHIVE_PATTERN.format(year=y)
            if _probe_url(url):
                return url, f"{y}"
        # Last resort — the "current" file
        if _probe_url(CURRENT_URL):
            return CURRENT_URL, "current"
        raise HttpError("no EIA-860 archive year reachable")

    def remote_version(self) -> str:
        _, v = self._latest_year_url()
        return v

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        url, version = self._latest_year_url()
        zip_path = dest_dir / f"eia860_{version}.zip"
        n = download(
            url,
            zip_path,
            lambda done, tot: progress(done, tot, zip_path.name),
            expected_min_bytes=1_000_000,
        )
        extracted = safe_extract_zip(zip_path, dest_dir / "eia860")
        zip_path.unlink()
        return FetchResult(
            files=extracted, remote_version=version, total_bytes=n,
        )


SOURCE = Eia860()
