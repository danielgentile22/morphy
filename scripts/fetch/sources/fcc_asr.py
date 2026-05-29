"""FCC Antenna Structure Registration — weekly bulk extract.

Two zips:
  * r_tower.zip — registered structures (the primary file)
  * a_tower.zip — applications, dismissed/pending (skipped here; brief
                  says we don't need it)

The FCC publishes new versions every Sunday at the URLs below. ETag and
Last-Modified are honoured.
"""

from __future__ import annotations

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

R_TOWER_URL = "https://data.fcc.gov/download/pub/uls/complete/r_tower.zip"
D_TOWER_URL = "https://data.fcc.gov/download/pub/uls/complete/d_tower.zip"


class FccAsr(DataSource):
    id = "fcc_asr"
    name = "FCC Antenna Structure Registration (ASR)"
    category = CATEGORY_TOWERS
    coverage = "National (US + territories)"
    cadence = "Weekly (Sundays)"
    estimated_size_mb = 90.0
    update_cadence_days = 7
    description = (
        "Federal registry of antenna structures over ~60 m (200 ft) above "
        "ground, or any height near an airport. Includes registration "
        "number, owner, coordinates (DMS), height, structure type, status. "
        "Primary source for tower locations."
    )
    legal = LegalInfo(
        publisher="Federal Communications Commission (FCC)",
        license="Public Domain (US federal government work)",
        license_url="https://www.fcc.gov/proceedings-actions/copyright",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct link to the Registrations zip — clicking starts download.
        manual_url="https://data.fcc.gov/download/pub/uls/complete/r_tower.zip",
        attribution="Source: FCC ULS public-access weekly database.",
        notes=(
            "Two zips needed:\n"
            "  • r_tower.zip (~37 MB, REQUIRED)  ← the manual URL points here\n"
            "  • d_tower.zip (~52 MB, optional FAA determinations) at\n"
            "    https://data.fcc.gov/download/pub/uls/complete/d_tower.zip\n"
            "If data.fcc.gov is slow, the landing page lists all weekly bulk "
            "files: https://www.fcc.gov/wireless/data/public-access-files-database-downloads\n"
            "After download: unzip each into a same-named subfolder under "
            "data/raw/fcc_asr/current/ (e.g. .../current/r_tower/RA.dat ...). "
            "Pipe-delimited .dat files; see asr_sql_table_definitions for layout."
        ),
    )

    def remote_version(self) -> str:
        # Use the r_tower.zip Last-Modified as the source-of-truth version.
        # If unavailable, fall back to ETag.
        h = head(R_TOWER_URL)
        lm = parse_http_date(h.get("last_modified"))
        if lm:
            return lm
        etag = h.get("etag")
        if etag:
            return etag.strip('"')
        # Last resort — content length changes weekly too
        cl = h.get("content_length")
        if cl:
            return f"len-{cl}"
        raise RuntimeError("could not derive remote version for FCC ASR")

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        rv = self.remote_version()  # capture once; avoid 2nd HEAD post-download
        files: list[Path] = []
        total = 0

        # 1. r_tower.zip (registrations) — required
        r_zip = dest_dir / "r_tower.zip"
        n = download(
            R_TOWER_URL,
            r_zip,
            lambda done, tot: progress(done, tot, "r_tower.zip"),
            expected_min_bytes=5_000_000,
        )
        total += n
        extracted = safe_extract_zip(r_zip, dest_dir / "r_tower")
        files.extend(extracted)
        r_zip.unlink()  # keep only the unpacked .dat files

        # 2. d_tower.zip (FAA determinations) — secondary; allow failure
        d_zip = dest_dir / "d_tower.zip"
        try:
            n = download(
                D_TOWER_URL,
                d_zip,
                lambda done, tot: progress(done, tot, "d_tower.zip"),
                expected_min_bytes=500_000,
            )
            total += n
            files.extend(safe_extract_zip(d_zip, dest_dir / "d_tower"))
            d_zip.unlink()
        except Exception:
            # Determinations are optional for the prototype — log and continue
            pass

        return FetchResult(
            files=files,
            remote_version=rv,
            total_bytes=total,
        )

    def validate(self, files: list[Path]) -> None:
        super().validate(files)
        # We require at least RA.dat (registrations) to consider the pull valid
        names = {f.name.upper() for f in files}
        if "RA.DAT" not in names:
            raise ValueError("FCC ASR fetch missing RA.dat")


SOURCE = FccAsr()
