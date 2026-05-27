"""FAA Obstruction Evaluation / Airport Airspace Analysis (OE/AAA).

FAA reviews any proposed structure tall enough to potentially affect
navigable airspace. Their DOF (Digital Obstacle File) is the closest
thing to a clean bulk feed; the OE/AAA "case" archive itself does NOT
expose a stable bulk-download URL — you have to navigate the search UI.

Strategy:
  * Try the DOF current daily file (officially supported bulk).
  * If that becomes unreliable, we surface a manual link.

DOF distribution URL (FAA AIM, "Digital Obstacle File / Daily DOF"):
  https://aeronav.faa.gov/Obst_Data/DAILY_DOF_DAT.ZIP
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
from ._helpers import parse_http_date, safe_extract_zip, version_from_head

DOF_URL = "https://aeronav.faa.gov/Obst_Data/DAILY_DOF_DAT.ZIP"


class FaaOeaaa(DataSource):
    id = "faa_oeaaa"
    name = "FAA Digital Obstacle File (DOF)"
    category = CATEGORY_TOWERS
    coverage = "National + outlying territories"
    cadence = "Daily"
    estimated_size_mb = 12.0
    update_cadence_days = 1
    description = (
        "FAA's daily file of every catalogued obstacle: towers, tall "
        "buildings, smokestacks, etc. Each record has lat/lon (DMS), AGL "
        "and AMSL height, obstacle type, and verification status. Useful "
        "as a forward-pipeline complement to FCC ASR — DOF often shows "
        "structures before they appear in ASR."
    )
    legal = LegalInfo(
        publisher="Federal Aviation Administration (FAA)",
        license="Public Domain (US federal government work)",
        license_url="https://www.faa.gov/web_policies/",
        automation=AutomationPolicy.ALLOWED,
        commercial_use=CommercialUse.ALLOWED,
        # Direct download — clicking starts a ~12 MB zip download.
        manual_url="https://aeronav.faa.gov/Obst_Data/DAILY_DOF_DAT.ZIP",
        attribution="Source: FAA Aeronautical Information Services, Digital Obstacle File.",
        notes=(
            "Direct download: DAILY_DOF_DAT.ZIP (~12 MB). Clicking starts "
            "the file immediately.\n"
            "\n"
            "FAA DOF landing page (with format docs): "
            "https://www.faa.gov/air_traffic/flight_info/aeronav/digital_products/dof/\n"
            "\n"
            "After download: unzip into data/raw/faa_oeaaa/current/dof/ "
            "(contains DOF.DAT — fixed-width text, see DOF_README inside "
            "the archive for column positions).\n"
            "\n"
            "NOT the OE/AAA case archive (which has no bulk endpoint and "
            "requires the search UI)."
        ),
    )

    def remote_version(self) -> str:
        return version_from_head(DOF_URL, label=self.id)

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        rv = self.remote_version()  # capture once; avoid 2nd HEAD post-download
        zip_path = dest_dir / "DAILY_DOF_DAT.ZIP"
        n = download(
            DOF_URL,
            zip_path,
            lambda done, tot: progress(done, tot, "DAILY_DOF_DAT.ZIP"),
            expected_min_bytes=100_000,
        )
        extracted = safe_extract_zip(zip_path, dest_dir / "dof")
        zip_path.unlink()
        return FetchResult(
            files=extracted,
            remote_version=rv,
            total_bytes=n,
        )


SOURCE = FaaOeaaa()
