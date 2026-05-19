"""LBNL Tracking the Sun — distributed (rooftop) PV systems.

The LBNL EMP team publishes an annual public file with ~3M+ systems
across the major net-metering states. Filename includes the publication
date (e.g. ``Public_data_file_2024_edition.csv``), so detection is
page-scrape + parse-newest-link.

Because the exact URL changes each year, this source is set to
TOLERATED automation: we politely fetch the landing page once, parse the
download link, and follow it.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from ..base import (
    CATEGORY_SOLAR,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import HttpError, fetch_text
from ..legal import AutomationPolicy, CommercialUse, LegalInfo

LANDING_URL = "https://emp.lbl.gov/tracking-the-sun"


class _LinkScraper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        for k, v in attrs:
            if k.lower() == "href" and v:
                self.links.append(v)


def _absolutise(href: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://emp.lbl.gov" + href
    return "https://emp.lbl.gov/" + href.lstrip("./")


def _find_public_file_link() -> tuple[str, str]:
    """Return (download_url, version_string) for the most recent public data file."""
    html = fetch_text(LANDING_URL)
    parser = _LinkScraper()
    parser.feed(html)
    candidates = [h for h in parser.links if re.search(r"public.+(csv|zip)$", h, re.I)]
    # Prefer the link mentioning the most recent year
    candidates.sort(
        key=lambda h: max((int(y) for y in re.findall(r"20\d{2}", h)), default=0),
        reverse=True,
    )
    if not candidates:
        raise HttpError("LBNL Tracking the Sun: no public data link found on page")
    chosen = _absolutise(candidates[0])
    # Use filename as the version slug
    name = chosen.rsplit("/", 1)[-1]
    return chosen, name


class LbnlTts(DataSource):
    id = "lbnl_tts"
    name = "LBNL U.S. Distributed Solar & Storage Data (formerly Tracking the Sun)"
    category = CATEGORY_SOLAR
    coverage = "National (best coverage in CA/NJ/MA/NY/AZ/CT/MD/MN/OR/WA + others)"
    cadence = "Annual"
    estimated_size_mb = 218.0
    update_cadence_days = None
    description = (
        "Per-system rooftop / distributed PV + storage dataset. ~4.5 M "
        "installations through 2024. Includes the third-party-ownership "
        "flag — the key field for renegotiable solar leases. Addresses "
        "masked to city/ZIP."
    )
    legal = LegalInfo(
        publisher="Lawrence Berkeley National Laboratory (LBNL), DOE",
        license="LBNL public-data terms (free use with attribution)",
        license_url=LANDING_URL,
        # LBNL fronts the site with Cloudflare which rejects scripted
        # User-Agents (always 403). Auto-fetch can't work — MANUAL_ONLY
        # is the honest setting.
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED_WITH_ATTRIBUTION,
        manual_url=LANDING_URL,
        attribution=(
            "Source: U.S. Distributed Solar and Storage Data (Tracking the "
            "Sun successor), Lawrence Berkeley National Laboratory."
        ),
        notes=(
            "1. On the landing page, click the green 'Public data file' "
            "link in the first bullet (~218 MB zip).\n"
            "\n"
            "2. Unzip locally — expands to a ~1.9 GB CSV named like "
            "'TTS_LBNL_public_file_<YEAR>_edition.csv'.\n"
            "\n"
            "3. Drop the CSV directly into data/raw/lbnl_tts/current/. "
            "Click 'Rescan disk' in the puller.\n"
            "\n"
            "Key column for lease-optimization: third_party_ownership "
            "(1 = leased/PPA, 0 = host-owned). TPO=1 subset is the "
            "renegotiable subset.\n"
            "\n"
            "NOT auto-pulled: LBNL fronts emp.lbl.gov with Cloudflare which "
            "blocks scripted requests. This always has to be manual."
        ),
    )

    def remote_version(self) -> str:
        return "manual"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        raise RuntimeError(
            "lbnl_tts is MANUAL_ONLY — Cloudflare blocks scripted fetches. "
            "Download from the landing page."
        )


SOURCE = LbnlTts()
