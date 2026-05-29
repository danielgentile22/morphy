"""Tests for puller status + attention decision logic.

Both modules are pure (no Qt widgets, no manifest disk I/O) so we can
exercise the full state matrix from synthetic inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from fetch.legal import AutomationPolicy, CommercialUse, LegalInfo
from fetch.manifest import (
    FRESHNESS_FRESH,
    FRESHNESS_STALE,
    Manifest,
    SourceEntry,
)

# app_puller.status imports PySide6.QtGui (QColor); the headless CI runner
# lacks the Qt system libs (libEGL), so skip this module there rather than
# erroring at collection. Runs normally where PySide6 is installed.
pytest.importorskip("PySide6.QtGui")

from app_puller.attention_panel import attention_items  # noqa: E402
from app_puller.status import (  # noqa: E402
    FRESHNESS_COLORS,
    STATUS_LABELS,
    freshness_label_for,
    status_for,
)

# ── synthetic source ─────────────────────────────────────────────────────


def _legal(automation: AutomationPolicy) -> LegalInfo:
    return LegalInfo(
        publisher="x",
        license="x",
        license_url="x",
        automation=automation,
        commercial_use=CommercialUse.ALLOWED,
        manual_url="https://example.com",
    )


@dataclass
class _FakeSource:
    """Minimal stand-in for DataSource — only what status / attention read."""

    id: str = "fake"
    name: str = "Fake"
    update_cadence_days: int | None = 30
    legal: LegalInfo = field(default_factory=lambda: _legal(AutomationPolicy.ALLOWED))
    _has_walkthrough: bool = False
    _has_creds: bool = True

    def manual_walkthrough(self):
        return object() if self._has_walkthrough else None

    def credentials_available(self) -> bool:
        return self._has_creds


def _entry(**kw) -> SourceEntry:
    e = SourceEntry()
    for k, v in kw.items():
        setattr(e, k, v)
    return e


# ── status_for ───────────────────────────────────────────────────────────


def test_status_for_manual_only_not_installed():
    s = _FakeSource()
    s.legal = _legal(AutomationPolicy.MANUAL_ONLY)
    assert status_for(s, _entry()) == "manual_only"


def test_status_for_manual_only_installed_shows_ok():
    """A manually-dropped MANUAL_ONLY source should resolve to 'ok'."""
    s = _FakeSource()
    s.legal = _legal(AutomationPolicy.MANUAL_ONLY)
    e = _entry(local_version="manual", status="ok")
    assert status_for(s, e) == "ok"


def test_status_for_credentialed_no_creds_not_installed():
    s = _FakeSource(_has_creds=False)
    s.legal = _legal(AutomationPolicy.CREDENTIALED)
    assert status_for(s, _entry()) == "needs_credentials"


def test_status_for_check_failed_passes_through():
    s = _FakeSource()
    e = _entry(status="check_failed")
    assert status_for(s, e) == "check_failed"


def test_status_for_installed_and_stale_returns_stale():
    s = _FakeSource()
    # Installed but remote version differs → entry.is_stale() True
    e = _entry(local_version="2024-01-01", remote_version="2024-02-01", status="ok")
    assert status_for(s, e) == "stale"


def test_status_for_unknown_status_falls_back_to_missing():
    s = _FakeSource()
    e = _entry(status="weirdo-not-in-labels")
    assert status_for(s, e) == "missing"


# ── freshness_label_for ──────────────────────────────────────────────────


def test_freshness_label_missing_install():
    s = _FakeSource()
    label, color = freshness_label_for(s, _entry())
    assert label == STATUS_LABELS["missing"][0]


def test_freshness_label_endpoint_failing_overrides_install():
    """check_failed should win even on a missing install."""
    s = _FakeSource()
    e = _entry(status="check_failed")
    label, _ = freshness_label_for(s, e)
    assert "Endpoint failing" in label


def test_freshness_label_fresh_installed():
    s = _FakeSource(update_cadence_days=30)
    now = datetime.now(UTC)
    e = _entry(
        local_version="v1",
        remote_version="v1",
        status="ok",
        fetched_at=now.isoformat(timespec="seconds"),
        update_cadence_days=30,
        # Recommended check is 30d out; we're within the "fresh" window.
        next_recommended_check_at=(now + timedelta(days=30)).isoformat(timespec="seconds"),
    )
    label, color = freshness_label_for(s, e)
    assert label.startswith("✓ Fresh")
    assert color == FRESHNESS_COLORS[FRESHNESS_FRESH]


def test_freshness_label_stale_past_cadence():
    s = _FakeSource(update_cadence_days=7)
    now = datetime.now(UTC)
    long_ago = (now - timedelta(days=30)).isoformat(timespec="seconds")
    e = _entry(
        local_version="v1",
        remote_version="v1",
        status="ok",
        fetched_at=long_ago,
        update_cadence_days=7,
        # next_recommended_check_at was 7d after fetch — 23 days ago by now.
        next_recommended_check_at=(now - timedelta(days=23)).isoformat(timespec="seconds"),
    )
    label, color = freshness_label_for(s, e)
    assert "Stale" in label
    assert color == FRESHNESS_COLORS[FRESHNESS_STALE]


# ── attention_items ──────────────────────────────────────────────────────


def _build_manifest(entries: dict[str, SourceEntry]) -> Manifest:
    """Build a Manifest with pre-seeded entries — no disk I/O."""
    m = Manifest()
    m.sources = entries
    return m


def test_attention_items_empty_when_no_sources():
    assert attention_items([], _build_manifest({})) == []


def test_attention_items_surface_check_failed():
    s = _FakeSource()
    m = _build_manifest({s.id: _entry(status="check_failed", error="500 Server Error")})
    items = attention_items([s], m)
    assert len(items) == 1
    assert items[0].action == "open_manual"
    assert "Endpoint failing" in items[0].reason


def test_attention_items_walkthrough_for_manual_only_uninstalled_with_walkthrough():
    s = _FakeSource(_has_walkthrough=True)
    s.legal = _legal(AutomationPolicy.MANUAL_ONLY)
    m = _build_manifest({s.id: _entry()})
    items = attention_items([s], m)
    assert len(items) == 1
    assert items[0].action == "walkthrough"
    assert "walkthrough available" in items[0].reason


def test_attention_items_open_manual_for_manual_only_without_walkthrough():
    s = _FakeSource(_has_walkthrough=False)
    s.legal = _legal(AutomationPolicy.MANUAL_ONLY)
    m = _build_manifest({s.id: _entry()})
    items = attention_items([s], m)
    assert items[0].action == "open_manual"


def test_attention_items_credentialed_no_creds_is_skipped():
    """No-creds + not-installed sources are surfaced via the puller's
    informational lane, not as actionable attention items."""
    s = _FakeSource(_has_creds=False)
    s.legal = _legal(AutomationPolicy.CREDENTIALED)
    m = _build_manifest({s.id: _entry()})
    assert attention_items([s], m) == []


def test_attention_items_stale_emits_refresh():
    s = _FakeSource()
    m = _build_manifest({s.id: _entry(local_version="v1", remote_version="v2", status="ok")})
    items = attention_items([s], m)
    assert len(items) == 1
    assert items[0].action == "refresh"
    assert "New version available" in items[0].reason


def test_attention_items_fresh_installed_yields_nothing():
    s = _FakeSource(update_cadence_days=30)
    now = datetime.now(UTC)
    m = _build_manifest(
        {
            s.id: _entry(
                local_version="v1",
                remote_version="v1",
                status="ok",
                fetched_at=now.isoformat(timespec="seconds"),
                update_cadence_days=30,
                next_recommended_check_at=(now + timedelta(days=30)).isoformat(timespec="seconds"),
            )
        }
    )
    assert attention_items([s], m) == []
