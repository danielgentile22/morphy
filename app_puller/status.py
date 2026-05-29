"""Status label + color resolution for the source tree column.

Pure functions over (DataSource, SourceEntry) — no Qt widget state. Lives
outside ``main_window.py`` so the freshness/install-state matrix is easy
to unit-test independently and easy to find when adjusting the label
text or palette.
"""

from __future__ import annotations

from fetch.base import DataSource
from fetch.legal import AutomationPolicy
from fetch.manifest import (
    FRESHNESS_DUE_SOON,
    FRESHNESS_FRESH,
    FRESHNESS_STALE,
    FRESHNESS_UNKNOWN,
    SourceEntry,
)
from PySide6.QtGui import QColor

STATUS_LABELS = {
    "ok": ("✓ Current", QColor("#2e7d32")),
    "stale": ("⟳ Stale (new version available)", QColor("#ef6c00")),
    "missing": ("✗ Not installed", QColor("#9e9e9e")),
    "check_failed": ("⚠ Check failed", QColor("#c62828")),
    "fetch_failed": ("⚠ Fetch failed", QColor("#c62828")),
    "manual_only": ("⤓ Manual download required", QColor("#5e35b1")),
    "needs_credentials": ("🔒 Credentials required", QColor("#5e35b1")),
}


# Colors for the freshness-aware status column. Matches docs/PULLER_UX.md §2.2.
FRESHNESS_COLORS = {
    FRESHNESS_FRESH: QColor("#2e7d32"),  # green
    FRESHNESS_DUE_SOON: QColor("#ef6c00"),  # orange
    FRESHNESS_STALE: QColor("#c62828"),  # red
    FRESHNESS_UNKNOWN: QColor("#9e9e9e"),  # gray
}


def freshness_label_for(source: DataSource, entry: SourceEntry) -> tuple[str, QColor]:
    """Display label + color combining install state + cadence freshness.

    The status column shows whichever is more actionable: install /
    policy state (missing, manual-only, needs-creds, endpoint failing,
    new version available), or freshness (fresh/due-soon/stale based on
    cadence).
    """
    # Policy / install state first — these always override freshness.
    if source.legal.automation == AutomationPolicy.MANUAL_ONLY and not entry.is_installed():
        return STATUS_LABELS["manual_only"]
    if (
        source.legal.automation == AutomationPolicy.CREDENTIALED
        and not source.credentials_available()
        and not entry.is_installed()
    ):
        return STATUS_LABELS["needs_credentials"]
    if entry.status == "check_failed":
        return ("⚠ Endpoint failing", QColor("#c62828"))
    if entry.status == "fetch_failed":
        return STATUS_LABELS["fetch_failed"]
    if not entry.is_installed():
        return STATUS_LABELS["missing"]
    if entry.is_stale():
        return STATUS_LABELS["stale"]

    # Installed + remote-version matches → fall back to cadence freshness.
    freshness = entry.freshness()
    days = entry.days_since_fetch()
    cadence = source.update_cadence_days

    if freshness == FRESHNESS_FRESH:
        label = f"✓ Fresh ({days}d)" if days is not None else "✓ Fresh"
        return (label, FRESHNESS_COLORS[FRESHNESS_FRESH])
    if freshness == FRESHNESS_DUE_SOON:
        label = (
            f"⏳ Due soon ({days}d / {cadence}d)" if days is not None and cadence else "⏳ Due soon"
        )
        return (label, FRESHNESS_COLORS[FRESHNESS_DUE_SOON])
    if freshness == FRESHNESS_STALE:
        label = (
            f"↻ Stale ({days}d / {cadence}d)"
            if days is not None and cadence
            else "↻ Stale (past cadence)"
        )
        return (label, FRESHNESS_COLORS[FRESHNESS_STALE])
    # FRESHNESS_UNKNOWN — installed but no cadence (one-shot reference data)
    return STATUS_LABELS["ok"]


def status_for(source: DataSource, entry: SourceEntry) -> str:
    """Resolve the displayable status, combining manifest + source policy.

    For MANUAL_ONLY / CREDENTIALED sources, files dropped into current/
    by hand (detected by ``_detect_manual_installs``) should still show
    as ✓ Current — show the install state when present, fall back to
    the policy-restricted state otherwise.
    """
    if source.legal.automation == AutomationPolicy.MANUAL_ONLY:
        if entry.is_installed():
            return "ok"
        return "manual_only"
    if (
        source.legal.automation == AutomationPolicy.CREDENTIALED
        and not source.credentials_available()
    ):
        if entry.is_installed():
            return "ok"
        return "needs_credentials"
    if entry.status in STATUS_LABELS:
        if entry.status == "ok" and entry.is_stale():
            return "stale"
        return entry.status
    return "missing"
