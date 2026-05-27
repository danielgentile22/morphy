"""TxDOT — Outdoor Advertising Regulatory Program.

Texas DOT runs the largest outdoor-advertising regulatory program in the
country but does NOT publish a stable bulk download. Permits are visible
through their licensing portal but scraping the portal is disallowed by
its terms. MANUAL_ONLY in the UI.
"""

from __future__ import annotations


from ..base import (
    CATEGORY_BILLBOARDS,
    ManualOnlySource,
)
from ..legal import AutomationPolicy, CommercialUse, LegalInfo


class TxdotBillboards(ManualOnlySource):
    id = "txdot_billboards"
    name = "TxDOT Outdoor Advertising permits"
    category = CATEGORY_BILLBOARDS
    coverage = "State: Texas"
    cadence = "On request (no stable bulk URL)"
    estimated_size_mb = 20.0
    update_cadence_days = None
    description = (
        "Texas DOT outdoor-advertising permit records. TxDOT licenses "
        "sign companies and registers each permitted billboard, but does "
        "not publish a bulk download. Request via Texas Public Information "
        "Act to the TxDOT Right of Way Division."
    )
    legal = LegalInfo(
        publisher="Texas Department of Transportation (TxDOT)",
        license="Texas public records (Government Code Ch. 552)",
        license_url="https://www.txdot.gov/about/contact-us/public-information-requests.html",
        automation=AutomationPolicy.MANUAL_ONLY,
        commercial_use=CommercialUse.ALLOWED,
        # Outdoor advertising program page — links to the TPIA request form.
        manual_url="https://www.txdot.gov/business/permits/outdoor-advertising.html",
        attribution="Source: TxDOT Right of Way Division.",
        notes=(
            "NO public bulk download. Submit a Texas Public Information "
            "Act (TPIA) request to TxDOT:\n"
            "\n"
            "1. Go to https://www.txdot.gov/about/contact-us/public-"
            "information-requests.html and click 'Submit a public "
            "information request'.\n"
            "\n"
            "2. Request text: 'All active outdoor advertising sign permits "
            "issued by the Right of Way Division, with coordinates if "
            "available and license-holder names. Excel or CSV preferred.'\n"
            "\n"
            "3. TPIA responses are due within 10 business days. Drop the "
            "file (xlsx/csv) into data/raw/txdot_billboards/current/ and "
            "click 'Rescan disk' in the puller."
        ),
    )




SOURCE = TxdotBillboards()
