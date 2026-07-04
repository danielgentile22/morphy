"""DataSource abstract base class.

Every data feed (FCC ASR, EIA 860, NC OneMap parcels, etc.) subclasses
``DataSource`` and implements the small protocol below. The UI and the
manifest treat all sources uniformly through this interface.

A source is responsible for four things:
  1. Declaring metadata (id, name, category, coverage, legal info,
     manual-download URL, estimated size, update cadence, refresh
     cadence in days).
  2. Reporting the *remote* version string — whatever changes when the
     publisher uploads a new file (a date, an ETag, a hash of a listing).
  3. Performing the actual fetch into ``RAW_ROOT / <id> / current``.
  4. For MANUAL_ONLY sources: providing a ``manual_walkthrough()`` that
     the puller can render as a step-by-step download guide.

Sources should never write outside their own directory and should never
mutate the manifest themselves — the puller owns both of those.
"""

from __future__ import annotations

import abc
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .legal import LegalInfo
from .walkthroughs import ManualWalkthrough

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
ProgressCallback = Callable[[int, int | None, str], None]


@dataclass(frozen=True)
class FetchResult:
    """What ``DataSource.fetch`` returns to the puller.

    ``remote_version`` is optional (#264): the puller captures the version
    once per pull via ``remote_version()`` before the download, so most
    sources leave it ``None``. Sources that derive the version as a
    byproduct of fetch (a year walk, a directory listing) set
    ``derives_version_on_fetch`` and return it here instead.
    """

    files: list[Path]
    total_bytes: int
    remote_version: str | None = None


@dataclass
class DataSource(abc.ABC):
    """Subclass and override the four ``@abstractmethod`` hooks."""

    # ── identity ────────────────────────────────────────────────────────
    id: str = field(init=False)  # stable slug, e.g. "fcc_asr"
    name: str = field(init=False)  # human label
    category: str = field(init=False)  # one of CATEGORY_*
    coverage: str = field(init=False)  # "National", "State: NC", etc.
    cadence: str = field(init=False)  # "Weekly", "Monthly", "Quarterly", "Annual", "Irregular"
    description: str = field(init=False)  # one-paragraph summary
    legal: LegalInfo = field(init=False)
    estimated_size_mb: float = field(init=False)  # rough; informational only

    # ── freshness ───────────────────────────────────────────────────────
    # Days between expected publisher updates. ``None`` for one-shot
    # reference data (boundary files, frozen historical designations).
    # Drives the puller's freshness badges + "What needs my attention".
    # See docs/DATA_FRESHNESS.md for the per-source rationale.
    update_cadence_days: int | None = field(init=False, default=None)

    # ── resumability ────────────────────────────────────────────────────
    # When True the puller preserves the previous run's ``.partial/``
    # directory instead of wiping it at fetch start, so a stalled long-
    # running paginated fetch (e.g. NC OneMap's 1,186 pages) can pick up
    # where it left off. The source's ``fetch`` is responsible for
    # idempotently skipping already-complete per-page files inside the
    # preserved directory. Default False — single-file or small fetches
    # don't benefit and want the cleanslate guarantee.
    supports_resume: bool = field(init=False, default=False)

    # ── version capture (#264) ──────────────────────────────────────────
    # The puller captures ``remote_version()`` once, before the download,
    # so a mid-fetch publisher update can't be recorded as already-
    # installed. Sources whose version is a byproduct of the fetch work
    # itself — a year/month walk (EIA) or a directory listing (parcel
    # archives) — set this True, skip the pre-probe, and return the version
    # in their ``FetchResult`` instead.
    derives_version_on_fetch: bool = field(init=False, default=False)

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
        Returns the files actually written; the puller derives the version
        (see ``derives_version_on_fetch`` to return it here instead).
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

    # ── manual-download walkthrough ─────────────────────────────────────

    def manual_walkthrough(self) -> ManualWalkthrough | None:
        """Step-by-step download instructions for MANUAL_ONLY sources.

        Override on every MANUAL_ONLY source. Default returns ``None`` for
        ALLOWED / TOLERATED sources (the puller auto-fetches them) and for
        CREDENTIALED sources (which prompt for credentials instead).
        """
        return None

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


class ManualOnlySource(DataSource):
    """Base for sources the publisher only exposes via click-through download.

    Provides the canonical ``remote_version() → "manual"`` + ``fetch()
    → RuntimeError`` pair so each MANUAL_ONLY subclass only needs to
    declare its metadata + a ``manual_walkthrough()`` override.
    """

    def remote_version(self) -> str:
        return "manual"

    def fetch(self, dest_dir: Path, progress: ProgressCallback) -> FetchResult:
        raise RuntimeError(f"{self.id} is MANUAL_ONLY — see manual_url.")
