"""FCC Universal Licensing System — weekly bulk extracts per radio service.

ULS publishes one bulk zip per service. We expose one DataSource per band
so the UI can show them as separate rows (and the user can pull only what
they need; cellular alone is enough for the v1 prototype).

Schema (from public ULS docs): each .dat file is pipe-delimited with one
record-type per file: HD (header/license), EN (entity), LO (location),
FR (frequency), CO (control point), AN (antenna), etc. See:
https://www.fcc.gov/sites/default/files/public_access_database_definitions_sql_v_5.txt
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..base import (
    CATEGORY_TOWERS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..http import download, head
from ..legal import AutomationPolicy, CommercialUse, LegalInfo
from ._helpers import parse_http_date, safe_extract_zip

BASE_URL = "https://data.fcc.gov/download/pub/uls/complete"

# FCC bundles all auction-allocated, geographic-area licenses (PCS, AWS,
# 700 MHz, WCS, etc.) into a single "Market Based Services" bulk file.
# Only the legacy Cellular Part 22 (site-licensed) and Microwave are
# separate rows on the public-access page.
#
# (id_suffix, human name, zip filename, approx size MB, description)
ULS_BANDS = [
    (
        "cellular",
        "Cellular (Part 22)",
        "l_cell.zip",
        20,
        "Legacy 850 MHz cellular — AT&T, Verizon. Site-by-site licensed.",
    ),
    (
        "market",
        "Market-Based Services",
        "l_market.zip",
        75,
        "All auction-allocated, geographic-area licenses bundled into one "
        "file: PCS (Part 24), AWS (Part 27), 700 MHz, WCS, BRS/EBS. These "
        "are the major-carrier 4G/5G bands.",
    ),
    (
        "micro",
        "Microwave (Parts 74/101)",
        "l_micro.zip",
        185,
        "Point-to-point backhaul microwave links between towers and "
        "network hubs. Indicates network-critical sites.",
    ),
]


@dataclass
class _UlsBand:
    suffix: str
    label: str
    zip_name: str
    est_mb: int
    summary: str


def _make_legal(band: _UlsBand) -> LegalInfo:
    folder = band.zip_name.replace(".zip", "")
    return LegalInfo(
        publisher="Federal Communications Commission (FCC)",
        license="Public Domain (US federal government work)",
        license_url="https://www.fcc.gov/proceedings-actions/copyright",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct link to this band's zip — clicking starts download.
        manual_url=f"{BASE_URL}/{band.zip_name}",
        attribution="Source: FCC ULS public-access weekly database.",
        notes=(
            f"Direct download: {band.zip_name} (~{band.est_mb} MB unzipped is "
            f"larger). Clicking 'Open manual download URL' grabs the file.\n"
            f"\n"
            f"If data.fcc.gov is slow, the landing page lists every weekly "
            f"bulk file by service: "
            f"https://www.fcc.gov/uls/transactions/daily-weekly  →  "
            f"scroll to '{band.label}'  →  Sunday Licenses.\n"
            f"\n"
            f"After download: unzip into "
            f"data/raw/fcc_uls_{band.suffix}/current/{folder}/  "
            f"(matches what the puller's auto-fetch produces).\n"
            f"\n"
            f"Pipe-delimited .dat tables (HD/EN/LO/FR/CO/AN/SC/HS/...). "
            f"ULS coordinates are unreliable — use for carrier presence, not siting."
        ),
    )


class FccUlsBand(DataSource):
    """One radio-service slice of ULS. Subclasses set the band metadata."""

    band: _UlsBand

    def __init__(self, band: _UlsBand) -> None:
        super().__init__()
        self.band = band
        self.id = f"fcc_uls_{band.suffix}"
        self.name = f"FCC ULS — {band.label}"
        self.category = CATEGORY_TOWERS
        self.coverage = "National (US + territories)"
        self.cadence = "Weekly (Sundays)"
        self.estimated_size_mb = float(band.est_mb)
        self.description = (
            f"{band.summary} Pipe-delimited bulk extract; join HD↔EN↔LO "
            "by Unique System Identifier (USI)."
        )
        self.legal = _make_legal(band)

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.band.zip_name}"

    def remote_version(self) -> str:
        h = head(self.url)
        lm = parse_http_date(h.get("last_modified"))
        if lm:
            return lm
        etag = h.get("etag")
        if etag:
            return etag.strip('"')
        cl = h.get("content_length")
        if cl:
            return f"len-{cl}"
        raise RuntimeError(f"could not derive remote version for {self.id}")

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        zip_path = dest_dir / self.band.zip_name
        n = download(
            self.url,
            zip_path,
            lambda done, tot: progress(done, tot, self.band.zip_name),
            expected_min_bytes=200_000,
        )
        extracted = safe_extract_zip(zip_path, dest_dir / "extracted")
        zip_path.unlink()
        return FetchResult(
            files=extracted,
            remote_version=self.remote_version(),
            total_bytes=n,
        )


# Instantiate one source per band; registry imports this list directly.
SOURCES = [FccUlsBand(_UlsBand(*b)) for b in ULS_BANDS]
