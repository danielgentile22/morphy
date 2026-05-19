"""Legal / licensing metadata for data sources.

Every DataSource declares a ``LegalInfo`` object describing:
  * who owns the data and under what license
  * whether automated download is *explicitly* permitted (or merely
    tolerated, or actively prohibited)
  * whether commercial use is permitted
  * a human-facing URL the user can open in a browser if we decide
    we are not allowed to automate the pull

The UI surfaces these flags so the user can make an informed decision
before clicking "Pull".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AutomationPolicy(str, Enum):
    """How we treat automated downloads for a given source."""

    # Bulk downloads are explicitly provided by the publisher
    # (e.g. FCC weekly zips, EIA Excel archives). Safe to automate.
    ALLOWED = "allowed"

    # No explicit bulk-download endpoint but downloading published
    # files referenced from a public page is reasonable. We use
    # polite scraping (single request, identifies itself, respects robots).
    TOLERATED = "tolerated"

    # Terms of service prohibit automated access, OR the data sits behind
    # a portal that requires a click-through agreement, OR robots.txt
    # disallows. The UI will NOT pull these automatically — it shows the
    # manual download URL and waits for the human.
    MANUAL_ONLY = "manual_only"

    # Paid / credentialed source — we will only attempt automation if
    # credentials are configured. Otherwise behaves like MANUAL_ONLY.
    CREDENTIALED = "credentialed"


class CommercialUse(str, Enum):
    ALLOWED = "allowed"           # Public domain or explicitly permits commercial use
    ALLOWED_WITH_ATTRIBUTION = "allowed_with_attribution"
    RESTRICTED = "restricted"     # Non-commercial only or licence ambiguous
    UNKNOWN = "unknown"           # Not yet researched; treat with caution


@dataclass(frozen=True)
class LegalInfo:
    publisher: str
    license: str                  # short name, e.g. "Public Domain (US federal work)"
    license_url: str | None       # link to the actual terms
    automation: AutomationPolicy
    commercial_use: CommercialUse
    manual_url: str               # human-facing landing page for manual download
    attribution: str | None = None
    notes: str | None = None      # caveats, ToS quirks, citation requirements
