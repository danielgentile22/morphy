"""FCC ULS — ancillary cross-service bulk files.

Three weekly bulk extracts that cut *across* the per-band ULS files:

* ``o_uls.zip``     — Ownership Form 602 filings: the human/corporate
                      ownership chain behind each licensee FRN. The
                      primary way to unmask an LLC license-holder.
* ``a_aatc.zip``    — Assignments and Transfers of Control applications:
                      who is buying/selling spectrum from whom.
* ``a_lease_608.zip`` — Form 608 secondary-market spectrum leases.

These complement the per-band files in fcc_uls.py — ownership/transfer
records reference licensees from every radio service.
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


@dataclass
class _UlsMeta:
    suffix: str
    label: str
    zip_name: str
    est_mb: int
    summary: str


ULS_META = [
    _UlsMeta(
        "ownership",
        "Ownership (Form 602) Filings",
        "o_uls.zip",
        5,
        "Form 602 ownership disclosures: the corporate/individual "
        "ownership chain behind each licensee FRN. Critical for "
        "unmasking LLC-held spectrum.",
    ),
    _UlsMeta(
        "transfers",
        "Assignments & Transfers of Control",
        "a_aatc.zip",
        105,
        "Spectrum license assignments and transfers of control. Tracks "
        "consolidation events (Sprint→T-Mobile, regional buyouts) that "
        "trigger tower-lease renegotiation.",
    ),
    _UlsMeta(
        "leasing",
        "Spectrum Leasing (Form 608)",
        "a_lease_608.zip",
        275,
        "Secondary-market spectrum leases. The only place where carriers "
        "renting spectrum to others (rather than holding directly) is "
        "disclosed.",
    ),
]


SECTION_NAMES = {
    "ownership": "Ownership",
    "transfers": "Assignments and Transfers",
    "leasing": "Spectrum Leasing",
}


def _make_legal(meta: "_UlsMeta") -> LegalInfo:
    folder = meta.zip_name.replace(".zip", "")
    section = SECTION_NAMES.get(meta.suffix, meta.label)
    return LegalInfo(
        publisher="Federal Communications Commission (FCC)",
        license="Public Domain (US federal government work)",
        license_url="https://www.fcc.gov/proceedings-actions/copyright",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct link to this file's zip — clicking starts download.
        manual_url=f"{BASE_URL}/{meta.zip_name}",
        attribution="Source: FCC ULS public-access weekly database.",
        notes=(
            f"Direct download: {meta.zip_name}. Clicking 'Open manual "
            f"download URL' grabs the file directly.\n"
            f"\n"
            f"If data.fcc.gov is slow, the landing page lists every weekly "
            f"bulk file by section: "
            f"https://www.fcc.gov/uls/transactions/daily-weekly  →  scroll "
            f"to '{section}'  →  {'Filings' if meta.suffix == 'ownership' else 'Applications'}.\n"
            f"\n"
            f"After download: unzip into "
            f"data/raw/fcc_uls_{meta.suffix}/current/{folder}/"
        ),
    )


class FccUlsMeta(DataSource):
    """One cross-service ULS bulk file."""
    meta: _UlsMeta

    def __init__(self, meta: _UlsMeta) -> None:
        super().__init__()
        self.meta = meta
        self.id = f"fcc_uls_{meta.suffix}"
        self.name = f"FCC ULS — {meta.label}"
        self.category = CATEGORY_TOWERS
        self.coverage = "National (cross-service)"
        self.cadence = "Weekly (Sundays)"
        self.estimated_size_mb = float(meta.est_mb)
        self.description = meta.summary
        self.legal = _make_legal(meta)

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.meta.zip_name}"

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
        zip_path = dest_dir / self.meta.zip_name
        n = download(
            self.url,
            zip_path,
            lambda done, tot: progress(done, tot, self.meta.zip_name),
            expected_min_bytes=100_000,
        )
        extracted = safe_extract_zip(zip_path, dest_dir / self.meta.zip_name.replace(".zip", ""))
        zip_path.unlink()
        return FetchResult(
            files=extracted,
            remote_version=self.remote_version(),
            total_bytes=n,
        )


SOURCES = [FccUlsMeta(m) for m in ULS_META]
