"""Orchestrates check + fetch for any DataSource.

The UI never calls a source directly — it always goes through this
module so that the manifest is updated correctly, the .partial directory
is staged + promoted atomically, errors are logged, and legal policy
(MANUAL_ONLY / CREDENTIALED) is enforced.
"""

from __future__ import annotations

import json
import re
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from . import LOG_PATH
from .base import DataSource, ProgressCallback
from .legal import AutomationPolicy
from .manifest import Manifest
from .storage import (
    directory_bytes,
    prepare_fresh_partial,
    prepare_partial_for_resume,
    promote_partial,
)


def log_event(event: str, **fields: Any) -> None:
    """Append a single JSON object to fetch.log."""
    payload: dict[str, Any] = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "event": event,
    }
    payload.update(fields)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


_URL_RE = re.compile(r"https?://[^\s'\"<>]+")


def _error_url(msg: str, source: DataSource) -> str:
    """Best-effort 'URL tried' for the manifest's structured last_error.

    The http helpers embed the exact URL in every error message
    (``HEAD <url> → …``, ``download <url> failed …``); fall back to the
    source's manual landing page when a non-HTTP error carries none.
    """
    m = _URL_RE.search(msg)
    return m.group(0).rstrip(".,)") if m else source.legal.manual_url


@dataclass
class CheckOutcome:
    source_id: str
    ok: bool
    remote_version: str | None = None
    error: str | None = None


@dataclass
class FetchOutcome:
    source_id: str
    ok: bool
    skipped: bool = False  # True for MANUAL_ONLY / missing creds
    skip_reason: str | None = None
    bytes: int = 0
    remote_version: str | None = None
    error: str | None = None


def check_one(source: DataSource, manifest: Manifest) -> CheckOutcome:
    """Ask the source for its current remote version; update the manifest."""
    log_event("check_start", source=source.id)

    # MANUAL_ONLY sources never auto-check; the UI shows a manual link.
    if source.legal.automation == AutomationPolicy.MANUAL_ONLY:
        manifest.entry(source.id).status = "manual_only"
        log_event("check_skipped", source=source.id, reason="manual_only")
        return CheckOutcome(source.id, ok=True, remote_version=None)

    # CREDENTIALED sources without creds also skip (puller never touches them).
    if source.legal.automation == AutomationPolicy.CREDENTIALED:
        if not source.credentials_available():
            manifest.entry(source.id).status = "needs_credentials"
            log_event("check_skipped", source=source.id, reason="no_credentials")
            return CheckOutcome(source.id, ok=True, remote_version=None)

    started = time.monotonic()
    try:
        rv = source.remote_version()
    except Exception as e:  # noqa: BLE001 — sources can raise anything
        elapsed = round(time.monotonic() - started, 1)
        msg = f"{type(e).__name__}: {e}"
        url = _error_url(msg, source)
        manifest.mark_check_failed(source.id, msg, url=url, elapsed=elapsed)
        log_event("check_failed", source=source.id, error=msg, url=url, elapsed=elapsed)
        return CheckOutcome(source.id, ok=False, error=msg)

    manifest.mark_check(source.id, rv)
    # Keep the manifest's declared cadence in sync with the source even
    # when no fetch happens — lets the freshness UI work as soon as a
    # source's cadence is added or changed.
    manifest.update_cadence(source.id, source.update_cadence_days)
    log_event("check_ok", source=source.id, remote_version=rv)
    return CheckOutcome(source.id, ok=True, remote_version=rv)


def fetch_one(
    source: DataSource,
    manifest: Manifest,
    progress: ProgressCallback,
    cancel_check: Callable[[], bool] | None = None,
) -> FetchOutcome:
    """Download the source into its current/ directory and update manifest.

    Honours the source's automation policy:
      * MANUAL_ONLY  → skip with reason
      * CREDENTIALED → skip if credentials_available() is False
    """
    sid = source.id
    log_event("fetch_start", source=sid)

    if source.legal.automation == AutomationPolicy.MANUAL_ONLY:
        log_event("fetch_skipped", source=sid, reason="manual_only")
        return FetchOutcome(
            sid,
            ok=True,
            skipped=True,
            skip_reason="Manual download required (publisher does not permit automation).",
        )

    if source.legal.automation == AutomationPolicy.CREDENTIALED:
        if not source.credentials_available():
            log_event("fetch_skipped", source=sid, reason="no_credentials")
            return FetchOutcome(
                sid,
                ok=True,
                skipped=True,
                skip_reason="Credentials not configured (paid source).",
            )

    started = time.monotonic()
    try:
        # Capture the remote version once, before the download (#264), so a
        # publisher update landing mid-fetch can't be stamped as already-
        # installed. Sources whose version is a byproduct of the fetch work
        # (EIA year/month walks, parcel-archive listings) skip the pre-probe
        # and return it from fetch() instead.
        pre_version = (
            None if getattr(source, "derives_version_on_fetch", False) else source.remote_version()
        )

        # Resumable sources (e.g. NC OneMap's 1,186-page fetch) preserve
        # the previous run's .partial/ so a stall can pick up where it
        # left off. Non-resumable sources start clean — every source's
        # validate() expects to see only files this run produced.
        if getattr(source, "supports_resume", False):
            partial = prepare_partial_for_resume(sid)
            log_event("fetch_resume_attempt", source=sid, bytes_carried=directory_bytes(partial))
        else:
            partial = prepare_fresh_partial(sid)
        # Source-supplied progress is forwarded as (done, total, label)
        result = source.fetch(partial, progress)
        source.validate(result.files)
        promote_partial(sid)

        remote_version = pre_version if pre_version is not None else result.remote_version
        manifest.stamp_installed(
            sid,
            local_version=remote_version,
            remote_version=remote_version,
            cadence_days=source.update_cadence_days,
        )
        entry = manifest.entry(sid)
        log_event(
            "fetch_ok",
            source=sid,
            remote_version=remote_version,
            bytes=entry.bytes,
            n_files=len(entry.files),
        )
        return FetchOutcome(sid, ok=True, bytes=entry.bytes, remote_version=remote_version)

    except Exception as e:  # broad: never let one source kill the whole UI
        elapsed = round(time.monotonic() - started, 1)
        tb = traceback.format_exc(limit=2)
        msg = f"{type(e).__name__}: {e}"
        url = _error_url(msg, source)
        manifest.mark_fetch_failed(sid, msg, url=url, elapsed=elapsed)
        log_event("fetch_failed", source=sid, error=msg, url=url, elapsed=elapsed, traceback=tb)
        return FetchOutcome(sid, ok=False, error=msg)
