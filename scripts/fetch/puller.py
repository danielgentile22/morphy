"""Orchestrates check + fetch for any DataSource.

The UI never calls a source directly — it always goes through this
module so that the manifest is updated correctly, the .partial directory
is staged + promoted atomically, errors are logged, and legal policy
(MANUAL_ONLY / CREDENTIALED) is enforced.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .base import DataSource, ProgressCallback
from .http import HttpError
from .legal import AutomationPolicy
from .log import log_event
from .manifest import Manifest
from .storage import (
    current_dir,
    directory_bytes,
    prepare_fresh_partial,
    promote_partial,
)


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

    try:
        rv = source.remote_version()
    except (HttpError, Exception) as e:  # broad: source may raise anything
        msg = f"{type(e).__name__}: {e}"
        manifest.mark_check_failed(source.id, msg)
        log_event("check_failed", source=source.id, error=msg)
        return CheckOutcome(source.id, ok=False, error=msg)

    manifest.mark_check(source.id, rv)
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

    try:
        partial = prepare_fresh_partial(sid)
        # Source-supplied progress is forwarded as (done, total, label)
        result = source.fetch(partial, progress)
        source.validate(result.files)
        promote_partial(sid)

        # Re-resolve file paths to point inside current/ for the manifest
        cur = current_dir(sid)
        moved_files: list[Path] = []
        for f in result.files:
            try:
                rel = f.relative_to(partial)
                moved_files.append(cur / rel)
            except ValueError:
                moved_files.append(f)
        total_bytes = directory_bytes(cur) or result.total_bytes

        manifest.mark_fetch_ok(sid, result.remote_version, moved_files, total_bytes)
        log_event(
            "fetch_ok",
            source=sid,
            remote_version=result.remote_version,
            bytes=total_bytes,
            n_files=len(moved_files),
        )
        return FetchOutcome(sid, ok=True, bytes=total_bytes, remote_version=result.remote_version)

    except Exception as e:  # broad: never let one source kill the whole UI
        tb = traceback.format_exc(limit=2)
        msg = f"{type(e).__name__}: {e}"
        manifest.mark_fetch_failed(sid, msg)
        log_event("fetch_failed", source=sid, error=msg, traceback=tb)
        return FetchOutcome(sid, ok=False, error=msg)
