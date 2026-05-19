"""Manual-download walkthrough data model.

For MANUAL_ONLY sources the puller can't auto-fetch; it shows the user a
step-by-step guide instead. Each source returns one of these from
``DataSource.manual_walkthrough()``.

Kept in the headless ``scripts/fetch`` package (no Qt imports) so it can
be consumed by either a Qt UI or a CLI / web frontend in future.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ManualStep:
    """One ordered step in a manual-download walkthrough.

    ``screenshot`` is a path under ``app_puller/assets/walkthroughs/<id>/``
    that the UI may render inline. The fetch package itself never reads
    these files; the path is a contract with the UI.
    """

    title: str
    body: str  # Markdown allowed; the UI may render it.
    deep_link: str | None = None  # URL opened in the OS browser.
    screenshot: Path | None = None  # Relative to repo root; UI resolves.


@dataclass(frozen=True)
class ManualWalkthrough:
    """A complete manual-download flow for one source.

    The puller surfaces:
      - Each ``step`` in order, with an optional screenshot + deep link.
      - The ``landing_page_url`` as a "just open the page" fallback.
      - ``expected_files`` so the puller's validate step can confirm the
        user dropped the right artifacts into ``data/raw/<id>/current/``.

    ``notes_on_failure`` is a markdown string the puller shows when an
    earlier auto-fetch attempt failed — e.g., "If the URL above returns
    a 500, click 'Older snapshots' on the landing page and pick the
    most recent one."
    """

    landing_page_url: str
    steps: list[ManualStep]
    expected_files: list[str] = field(default_factory=list)
    notes_on_failure: str | None = None

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("ManualWalkthrough must have at least one step")
