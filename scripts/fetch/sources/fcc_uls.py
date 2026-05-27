"""FCC Universal Licensing System — weekly bulk extracts.

ULS publishes two flavours of bulk file:

* **Per-band** files (l_cell, l_market, l_micro): one per radio service.
  Each is the per-licensee table set for that service (HD/EN/LO/FR/...).
* **Cross-service** files (o_uls = ownership, a_aatc = assignments and
  transfers, a_lease_608 = secondary leases): one per concern, cutting
  across all radio services.

Both flavours share the same publisher / format / fetch contract, so
they share one ``DataSource`` class plus one declaration list. The UI
lists each entry separately so the user can pull only what they need.

Schema (from public ULS docs): each .dat file is pipe-delimited with one
record-type per file. See
https://www.fcc.gov/sites/default/files/public_access_database_definitions_sql_v_5.txt
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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

UlsKind = Literal["band", "meta"]


@dataclass
class _UlsFile:
    """One ULS bulk file declaration."""

    suffix: str
    label: str
    zip_name: str
    est_mb: int
    summary: str
    kind: UlsKind

    @property
    def folder(self) -> str:
        return self.zip_name.replace(".zip", "")

    @property
    def coverage(self) -> str:
        return "National (US + territories)" if self.kind == "band" else "National (cross-service)"

    @property
    def section_name(self) -> str:
        """Where to scroll on the public-access landing page."""
        return {
            "ownership": "Ownership",
            "transfers": "Assignments and Transfers",
            "leasing": "Spectrum Leasing",
        }.get(self.suffix, self.label)

    @property
    def section_subheading(self) -> str:
        if self.kind == "band":
            return "Sunday Licenses"
        return "Filings" if self.suffix == "ownership" else "Applications"

    @property
    def expected_min_bytes(self) -> int:
        return 200_000 if self.kind == "band" else 100_000

    @property
    def description(self) -> str:
        if self.kind == "band":
            return (
                f"{self.summary} Pipe-delimited bulk extract; join HD↔EN↔LO "
                "by Unique System Identifier (USI)."
            )
        return self.summary


# FCC bundles all auction-allocated, geographic-area licenses (PCS, AWS,
# 700 MHz, WCS, etc.) into a single "Market Based Services" bulk file.
# Only the legacy Cellular Part 22 (site-licensed) and Microwave are
# separate rows on the public-access page.
ULS_FILES: list[_UlsFile] = [
    _UlsFile(
        "cellular",
        "Cellular (Part 22)",
        "l_cell.zip",
        20,
        "Legacy 850 MHz cellular — AT&T, Verizon. Site-by-site licensed.",
        "band",
    ),
    _UlsFile(
        "market",
        "Market-Based Services",
        "l_market.zip",
        75,
        "All auction-allocated, geographic-area licenses bundled into one "
        "file: PCS (Part 24), AWS (Part 27), 700 MHz, WCS, BRS/EBS. These "
        "are the major-carrier 4G/5G bands.",
        "band",
    ),
    _UlsFile(
        "micro",
        "Microwave (Parts 74/101)",
        "l_micro.zip",
        185,
        "Point-to-point backhaul microwave links between towers and "
        "network hubs. Indicates network-critical sites.",
        "band",
    ),
    _UlsFile(
        "ownership",
        "Ownership (Form 602) Filings",
        "o_uls.zip",
        5,
        "Form 602 ownership disclosures: the corporate/individual "
        "ownership chain behind each licensee FRN. Critical for "
        "unmasking LLC-held spectrum.",
        "meta",
    ),
    _UlsFile(
        "transfers",
        "Assignments & Transfers of Control",
        "a_aatc.zip",
        105,
        "Spectrum license assignments and transfers of control. Tracks "
        "consolidation events (Sprint→T-Mobile, regional buyouts) that "
        "trigger tower-lease renegotiation.",
        "meta",
    ),
    _UlsFile(
        "leasing",
        "Spectrum Leasing (Form 608)",
        "a_lease_608.zip",
        275,
        "Secondary-market spectrum leases. The only place where carriers "
        "renting spectrum to others (rather than holding directly) is "
        "disclosed.",
        "meta",
    ),
]


def _make_legal(f: _UlsFile) -> LegalInfo:
    band_notes = (
        f"Direct download: {f.zip_name} (~{f.est_mb} MB unzipped is larger). "
        f"Clicking 'Open manual download URL' grabs the file.\n"
        f"\n"
        f"If data.fcc.gov is slow, the landing page lists every weekly "
        f"bulk file by service: "
        f"https://www.fcc.gov/uls/transactions/daily-weekly  →  "
        f"scroll to '{f.label}'  →  {f.section_subheading}.\n"
        f"\n"
        f"After download: unzip into "
        f"data/raw/fcc_uls_{f.suffix}/current/{f.folder}/  "
        f"(matches what the puller's auto-fetch produces).\n"
        f"\n"
        f"Pipe-delimited .dat tables (HD/EN/LO/FR/CO/AN/SC/HS/...). "
        f"ULS coordinates are unreliable — use for carrier presence, not siting."
    )
    meta_notes = (
        f"Direct download: {f.zip_name}. Clicking 'Open manual "
        f"download URL' grabs the file directly.\n"
        f"\n"
        f"If data.fcc.gov is slow, the landing page lists every weekly "
        f"bulk file by section: "
        f"https://www.fcc.gov/uls/transactions/daily-weekly  →  scroll "
        f"to '{f.section_name}'  →  {f.section_subheading}.\n"
        f"\n"
        f"After download: unzip into "
        f"data/raw/fcc_uls_{f.suffix}/current/{f.folder}/"
    )
    return LegalInfo(
        publisher="Federal Communications Commission (FCC)",
        license="Public Domain (US federal government work)",
        license_url="https://www.fcc.gov/proceedings-actions/copyright",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        manual_url=f"{BASE_URL}/{f.zip_name}",
        attribution="Source: FCC ULS public-access weekly database.",
        notes=band_notes if f.kind == "band" else meta_notes,
    )


class FccUlsBulk(DataSource):
    """One ULS bulk file (band or meta)."""

    file: _UlsFile

    def __init__(self, file: _UlsFile) -> None:
        super().__init__()
        self.file = file
        self.id = f"fcc_uls_{file.suffix}"
        self.name = f"FCC ULS — {file.label}"
        self.category = CATEGORY_TOWERS
        self.coverage = file.coverage
        self.cadence = "Weekly (Sundays)"
        self.estimated_size_mb = float(file.est_mb)
        self.description = file.description
        self.legal = _make_legal(file)

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.file.zip_name}"

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
        zip_path = dest_dir / self.file.zip_name
        n = download(
            self.url,
            zip_path,
            lambda done, tot: progress(done, tot, self.file.zip_name),
            expected_min_bytes=self.file.expected_min_bytes,
        )
        # `band` files extract into a generic `extracted/` subdir so the
        # downstream FCC ULS normalizer can probe one path regardless of
        # which band ran; `meta` files extract into a folder named after
        # the zip to keep their distinct DAT-table identities clear.
        target = dest_dir / ("extracted" if self.file.kind == "band" else self.file.folder)
        extracted = safe_extract_zip(zip_path, target)
        zip_path.unlink()
        return FetchResult(
            files=extracted,
            remote_version=self.remote_version(),
            total_bytes=n,
        )


# All bulk files (bands + cross-service) registered in one list.
SOURCES = [FccUlsBulk(f) for f in ULS_FILES]
