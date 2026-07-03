"""Badge + attention decision logic — pure functions, no UI imports.

Mirrors the semantics of ``app_puller/status.py`` + ``attention_panel.py``
without the Qt dependency (that module dies with the Qt puller in #240;
this one is its successor). Badge vocabulary per PRD #233 story 3:
fresh / due soon / stale / missing / endpoint-dead / manual / deferred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fetch.base import DataSource
from fetch.legal import AutomationPolicy
from fetch.manifest import (
    FRESHNESS_DUE_SOON,
    FRESHNESS_STALE,
    Manifest,
    SourceEntry,
)

# Badge kinds — stable ids the UI maps to styles.
FRESH = "fresh"
DUE_SOON = "due_soon"
STALE = "stale"
MISSING = "missing"
DEAD = "dead"  # endpoint-dead: last check or fetch failed
MANUAL = "manual"
DEFERRED = "deferred"


@dataclass(frozen=True)
class Badge:
    kind: str
    label: str


def badge_for(
    source: DataSource,
    entry: SourceEntry,
    *,
    deferred: bool = False,
    now: datetime | None = None,
) -> Badge:
    """Resolve the one badge shown in the status column.

    Precedence matches the Qt puller: policy/install state first
    (deferred, dead endpoint, manual, missing, new-version stale),
    then cadence freshness.
    """
    if deferred:
        return Badge(DEFERRED, "DEFERRED")
    if entry.status in ("check_failed", "fetch_failed"):
        return Badge(DEAD, "DEAD")
    if source.legal.automation == AutomationPolicy.MANUAL_ONLY and not entry.is_installed():
        return Badge(MANUAL, "MANUAL")
    if (
        source.legal.automation == AutomationPolicy.CREDENTIALED
        and not source.credentials_available()
        and not entry.is_installed()
    ):
        # ponytail: credentials are a manual action too; only Regrid (deferred) hits this
        return Badge(MANUAL, "MANUAL")
    if not entry.is_installed():
        return Badge(MISSING, "MISSING")
    if entry.is_stale():
        return Badge(STALE, "STALE new version")

    days = entry.days_since_fetch(now)
    cadence = source.update_cadence_days
    freshness = entry.freshness(now)
    if freshness == FRESHNESS_STALE:
        return Badge(STALE, f"STALE {days}d/{cadence}d")
    if freshness == FRESHNESS_DUE_SOON:
        return Badge(DUE_SOON, f"DUE SOON {days}d/{cadence}d")
    # fresh, or installed one-shot reference data with no cadence (unknown)
    return Badge(FRESH, f"FRESH {days}d" if days is not None else "FRESH")


# Attention severity ranks (lower = more urgent).
SEV_DEAD = 0
SEV_MISSING = 1
SEV_STALE = 2


@dataclass(frozen=True)
class AttentionItem:
    severity: int
    source_id: str
    name: str
    reason: str


def attention_items(
    sources: list[DataSource],
    manifest: Manifest,
    now: datetime | None = None,
) -> list[AttentionItem]:
    """Sources needing a human action, ranked dead > missing > stale."""
    out: list[AttentionItem] = []
    for s in sources:
        e = manifest.entry(s.id)
        if e.status == "check_failed":
            out.append(AttentionItem(SEV_DEAD, s.id, s.name, f"endpoint failing: {e.error or '—'}"))
        elif e.status == "fetch_failed":
            out.append(
                AttentionItem(SEV_DEAD, s.id, s.name, f"last fetch failed: {e.error or '—'}")
            )
        elif not e.is_installed():
            if (
                s.legal.automation == AutomationPolicy.CREDENTIALED
                and not s.credentials_available()
            ):
                continue  # informational, not actionable (matches Qt panel)
            reason = (
                "manual download required"
                if s.legal.automation == AutomationPolicy.MANUAL_ONLY
                else "not installed"
            )
            out.append(AttentionItem(SEV_MISSING, s.id, s.name, reason))
        elif e.is_stale():
            out.append(AttentionItem(SEV_STALE, s.id, s.name, "new version available"))
        elif e.freshness(now) == FRESHNESS_STALE:
            days, cad = e.days_since_fetch(now), s.update_cadence_days
            out.append(AttentionItem(SEV_STALE, s.id, s.name, f"past cadence ({days}d / {cad}d)"))
    out.sort(key=lambda it: (it.severity, it.name.lower()))
    return out
