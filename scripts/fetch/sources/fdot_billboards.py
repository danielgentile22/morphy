"""Florida DOT — Outdoor Advertising permits (monthly Excel).

FDOT publishes a monthly OAS (Outdoor Advertising System) extract as an
Excel workbook. Each row is a permit: permit #, owner, county, route,
lat/lon, status, dates.

The exact URL is a stable filename refreshed in place each month.
"""

from __future__ import annotations

from pathlib import Path

from ..base import (
    CATEGORY_BILLBOARDS,
    DataSource,
    FetchResult,
    ProgressCallback,
)
from ..legal import AutomationPolicy, CommercialUse, LegalInfo

# FDOT moved Outdoor Advertising from Maintenance into Right of Way and
# retired the public bulk-extract xlsx in the process. The data is now
# only available via:
#   • Interactive search at https://oda.fdot.gov/  (no bulk export)
#   • GIS Enterprise View https://gis.fdot.gov/webappbuilder/apps/6/  (no API)
#   • Records request to the OA office: (850) 414-4601
# So this source is now MANUAL_ONLY.
NEW_OA_PAGE = "https://www.fdot.gov/rightofway/OutdoorAdvertising.shtm/new-outdoor-advertising-site"


class FdotBillboards(DataSource):
    id = "fdot_billboards"
    name = "FDOT Outdoor Advertising permits"
    category = CATEGORY_BILLBOARDS
    coverage = "State: Florida"
    cadence = "On request (bulk extract retired)"
    estimated_size_mb = 8.0
    description = (
        "Florida DOT outdoor-advertising permit records. Each permit has "
        "owner (sign company), county, route, mile-marker, status, dates, "
        "and historically lat/lon. Was the single best public billboard "
        "dataset in the US — until FDOT retired the bulk xlsx in 2025."
    )
    legal = LegalInfo(
        publisher="Florida Department of Transportation (FDOT)",
        license="Florida public records (open data)",
        license_url="https://www.fdot.gov/rightofway/OutdoorAdvertising.shtm",
        # FDOT removed the public xlsx. No bulk URL exists anymore.
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED,
        manual_url=NEW_OA_PAGE,
        attribution="Source: Florida DOT Outdoor Advertising program.",
        notes=(
            "STATUS: bulk extract retired by FDOT around 2025. No public "
            "xlsx exists anymore. Three ways to get data:\n"
            "\n"
            "1. INTERACTIVE SEARCH (small queries): https://oda.fdot.gov/  "
            "— search by permit #, county, owner. Export from the UI is "
            "limited; works for spot checks, not for bulk.\n"
            "\n"
            "2. GIS Enterprise View (visual): https://gis.fdot.gov/"
            "webappbuilder/apps/6/  — interactive map with permit pins.\n"
            "\n"
            "3. BULK DATA (the actual workflow): contact the Outdoor "
            "Advertising Office at (850) 414-4601, or write to:\n"
            "     FDOT Outdoor Advertising\n"
            "     605 Suwannee Street, Mail Station 22\n"
            "     Tallahassee, FL 32399-0450\n"
            "Request: 'A complete extract of all active outdoor advertising "
            "sign permits with coordinates and license-holder names, in "
            "Excel or CSV format.'\n"
            "\n"
            "When you receive the file, drop it (xlsx/csv) into "
            "data/raw/fdot_billboards/current/ and click 'Rescan disk'."
        ),
    )

    def remote_version(self) -> str:
        return "manual"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        raise RuntimeError(
            "fdot_billboards is MANUAL_ONLY — FDOT retired the bulk extract. "
            "Contact the OA office (notes have the phone number)."
        )


SOURCE = FdotBillboards()
