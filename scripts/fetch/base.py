"""DataSource abstract base class.

Every data feed (FCC ASR, EIA 860, NC OneMap parcels, etc.) subclasses
``DataSource`` and implements the small protocol below. The UI and the
manifest treat all sources uniformly through this interface.

A source is responsible for three things only:
  1. Declaring metadata (id, name, category, coverage, legal info,
     manual-download URL, estimated size, update cadence).
  2. Reporting the *remote* version string — whatever changes when the
     publisher uploads a new file (a date, an ETag, a hash of a listing).
  3. Performing the actual fetch into ``RAW_ROOT / <id> / current``.

Sources should never write outside their own directory and should never
mutate the manifest themselves — the puller owns both of those.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .legal import LegalInfo


# Categories shown as collapsible groups in the UI
CATEGORY_TOWERS = "Towers"
CATEGORY_SOLAR = "Solar"
CATEGORY_BILLBOARDS = "Billboards"
CATEGORY_PARCELS = "Parcels"
CATEGORY_DISTRESS = "Distress"

CATEGORY_ORDER = [
    CATEGORY_TOWERS,
    CATEGORY_SOLAR,
    CATEGORY_BILLBOARDS,
    CATEGORY_PARCELS,
    CATEGORY_DISTRESS,
]


# Progress callback signature: (bytes_done, bytes_total_or_None, current_file_name)
ProgressCallback = Callable[[int, Optional[int], str], None]


@dataclass(frozen=True)
class FetchResult:
    """What ``DataSource.fetch`` returns to the puller."""
    files: list[Path]
    remote_version: str
    total_bytes: int


@dataclass
class DataSource(abc.ABC):
    """Subclass and override the four ``@abstractmethod`` hooks."""

    # ── identity ────────────────────────────────────────────────────────
    id: str = field(init=False)              # stable slug, e.g. "fcc_asr"
    name: str = field(init=False)            # human label
    category: str = field(init=False)        # one of CATEGORY_*
    coverage: str = field(init=False)        # "National", "State: NC", etc.
    cadence: str = field(init=False)         # "Weekly", "Monthly", "Quarterly", "Annual", "Irregular"
    description: str = field(init=False)     # one-paragraph summary
    legal: LegalInfo = field(init=False)
    estimated_size_mb: float = field(init=False)   # rough; informational only

    # ── behaviour ───────────────────────────────────────────────────────

    @abc.abstractmethod
    def remote_version(self) -> str:
        """Return a string that changes whenever the publisher releases new data.

        Implementations should be cheap — typically a single HEAD request
        or a small JSON metadata call. Raise on network failure; the
        puller will catch and mark the source as ``check_failed``.
        """

    @abc.abstractmethod
    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        """Download data into ``dest_dir`` (already created, empty).

        Must report progress via ``progress(bytes_done, bytes_total, filename)``.
        Returns the list of files actually written and the remote_version
        string that corresponds to the downloaded snapshot.
        """

    def validate(self, files: list[Path]) -> None:
        """Quick sanity check after download. Override for source-specific checks.

        Default: every reported file exists and is non-empty. Raises
        ``ValueError`` on failure so the puller can quarantine the result.
        """
        for f in files:
            if not f.exists():
                raise ValueError(f"expected file missing: {f}")
            if f.stat().st_size == 0:
                raise ValueError(f"file is empty: {f}")

    # ── helpers (do not override) ───────────────────────────────────────

    @property
    def is_manual_only(self) -> bool:
        from .legal import AutomationPolicy
        return self.legal.automation == AutomationPolicy.MANUAL_ONLY

    @property
    def needs_credentials(self) -> bool:
        from .legal import AutomationPolicy
        return self.legal.automation == AutomationPolicy.CREDENTIALED

    def credentials_available(self) -> bool:
        """Override for credentialed sources. Default: always True."""
        return True
