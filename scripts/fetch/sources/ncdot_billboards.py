"""NCDOT — Outdoor Advertising permits.

North Carolina DOT publishes outdoor-advertising permit data through
their Roadside Environmental Unit. The list of active permits is
available via a public records request and through a web search portal;
**no stable bulk-download URL is published**, so this source is
MANUAL_ONLY in the UI.
"""

from __future__ import annotations


from ..base import (
    CATEGORY_BILLBOARDS,
    ManualOnlySource,
)
from ..legal import AutomationPolicy, CommercialUse, LegalInfo


class NcdotBillboards(ManualOnlySource):
    id = "ncdot_billboards"
    name = "NCDOT Outdoor Advertising permits"
    category = CATEGORY_BILLBOARDS
    coverage = "State: North Carolina"
    cadence = "On request (no stable bulk URL)"
    estimated_size_mb = 5.0
    update_cadence_days = None
    description = (
        "NC DOT outdoor-advertising permit records. NC publishes a "
        "permit search UI but not a stable bulk-download endpoint, so "
        "this source must be requested manually (records request to the "
        "Roadside Environmental Unit, or scraping the search UI which is "
        "explicitly discouraged). Download manually and drop the file "
        "into data/raw/ncdot_billboards/current/."
    )
    legal = LegalInfo(
        publisher="North Carolina Department of Transportation (NCDOT)",
        license="NC public records (G.S. 132)",
        license_url="https://www.ncdot.gov/initiatives-policies/Transportation/Pages/access-to-records.aspx",
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED,
        # NCDOT scrubbed the Outdoor Advertising program page from public
        # navigation (no clean replacement URL exists as of 2026). The
        # records-request contact form still works and is the practical
        # entry point.
        manual_url="https://www.ncdot.gov/contact/",
        attribution="Source: NCDOT Roadside Environmental Unit, Outdoor Advertising.",
        notes=(
            "NO public bulk download exists, AND NCDOT has retired the "
            "old Roadside Outdoor Advertising program page. Workflow:\n"
            "\n"
            "1. SUBMIT A RECORDS REQUEST via the manual URL (NCDOT's "
            "general contact form). Choose 'Public Records Request' as the "
            "topic. Request text: 'Under G.S. 132, please provide a "
            "current Excel or CSV extract of all active outdoor "
            "advertising sign permits issued by the Roadside Environmental "
            "Unit, including license-holder name, coordinates (or route + "
            "mile-marker), permit number, status, and dates.'\n"
            "\n"
            "2. ALTERNATIVE: try emailing outdooradvertising@ncdot.gov "
            "directly (legacy address; may or may not be monitored). "
            "Or find the current OA program manager in the NCDOT staff "
            "directory at https://apps.ncdot.gov/dot/directory/\n"
            "\n"
            "3. When you receive the file, drop it (xlsx/csv/pdf) into "
            "data/raw/ncdot_billboards/current/ and click 'Rescan disk'."
        ),
    )




SOURCE = NcdotBillboards()
