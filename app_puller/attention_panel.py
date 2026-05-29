"""Attention-panel data layer: pure decision logic, no Qt widgets.

The widget that renders this list (the "⚠ What needs my attention" panel
above the source tree) lives in ``main_window.py``; the *decision* logic
— which sources need a human action right now, and what kind — is pure
and lives here so it's unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fetch.base import DataSource
from fetch.legal import AutomationPolicy
from fetch.manifest import FRESHNESS_STALE, Manifest

ActionKind = Literal["walkthrough", "refresh", "open_manual"]


@dataclass(frozen=True)
class AttentionItem:
    source: DataSource
    reason: str
    action: ActionKind


def attention_items(sources: list[DataSource], manifest: Manifest) -> list[AttentionItem]:
    """Return the list of sources that need a human action right now.

    Order matches the order of ``sources``; callers control display order
    via that input.
    """
    out: list[AttentionItem] = []
    for s in sources:
        e = manifest.entry(s.id)
        has_walkthrough = s.manual_walkthrough() is not None

        if e.status == "check_failed":
            if s.legal.automation == AutomationPolicy.MANUAL_ONLY and has_walkthrough:
                out.append(
                    AttentionItem(s, "Endpoint failing — walkthrough available", "walkthrough")
                )
            else:
                out.append(AttentionItem(s, f"Endpoint failing: {e.error or '—'}", "open_manual"))
            continue
        if e.status == "fetch_failed":
            out.append(AttentionItem(s, f"Last fetch failed: {e.error or '—'}", "refresh"))
            continue
        # Manual sources that haven't been installed yet
        if s.legal.automation == AutomationPolicy.MANUAL_ONLY and not e.is_installed():
            reason = "Manual download required" + (
                " — walkthrough available" if has_walkthrough else ""
            )
            out.append(
                AttentionItem(
                    s,
                    reason,
                    "walkthrough" if has_walkthrough else "open_manual",
                )
            )
            continue
        # Auto sources that aren't installed (and aren't credentialed-no-creds)
        if not e.is_installed():
            if (
                s.legal.automation == AutomationPolicy.CREDENTIALED
                and not s.credentials_available()
            ):
                # surfaced separately as informational; not actionable here
                continue
            out.append(AttentionItem(s, "Not installed", "refresh"))
            continue
        # Stale (remote version differs)
        if e.is_stale():
            out.append(AttentionItem(s, "New version available", "refresh"))
            continue
        # Past cadence
        if e.freshness() == FRESHNESS_STALE:
            days = e.days_since_fetch()
            cad = s.update_cadence_days
            reason = (
                f"Past cadence ({days}d / {cad}d) — re-check publisher"
                if days is not None and cad
                else "Past recommended refresh date"
            )
            if s.legal.automation == AutomationPolicy.MANUAL_ONLY and has_walkthrough:
                out.append(AttentionItem(s, reason, "walkthrough"))
            else:
                out.append(AttentionItem(s, reason, "refresh"))
    return out
