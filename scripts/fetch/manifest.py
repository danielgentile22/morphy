"""Persistent manifest of what we have on disk.

Single JSON file at ``data/manifest.json``. The puller is the only writer.

Schema (``schema_version = 2``, current — bumped from v1 in Section 3
of the production-readiness plan):

    {
      "schema_version": 2,
      "last_full_check": "<ISO8601>" | null,
      "sources": {
        "<source_id>": {
          "remote_version": "<string>",
          "local_version":  "<string>",        # version of what we have on disk
          "fetched_at":     "<ISO8601>",
          "checked_at":     "<ISO8601>",
          "bytes":          <int>,
          "files":          ["relative/path", ...],
          "status":         "ok" | "stale" | "missing" | "check_failed" | "fetch_failed",
          "error":          null | "<message>",

          # ── added in schema_version 2 ─────────────────────────────────
          "update_cadence_days":      null | <int>,   # snapshotted from the source
          "next_recommended_check_at": "<ISO8601>" | null
        }
      }
    }

V1 → V2 migration: when the manifest loads with ``schema_version == 1``,
the new fields default to ``None``. They populate on the next fetch /
check via the source's declared cadence.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import MANIFEST_PATH

SCHEMA_VERSION = 2

# ── freshness states ────────────────────────────────────────────────────
# Returned by SourceEntry.freshness() — drives the puller UI badges.
FRESHNESS_FRESH = "fresh"
FRESHNESS_DUE_SOON = "due_soon"
FRESHNESS_STALE = "stale"
FRESHNESS_UNKNOWN = "unknown"  # no fetched_at OR no cadence

# How far past `next_recommended_check_at` (as a fraction of one cadence
# window) we consider the source "due soon" rather than fully stale.
# Defined here so docs/DATA_FRESHNESS.md and the puller can reference it.
DUE_SOON_FRACTION = 0.5


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


@dataclass
class SourceEntry:
    remote_version: str | None = None
    local_version: str | None = None
    fetched_at: str | None = None
    checked_at: str | None = None
    bytes: int = 0
    files: list[str] = field(default_factory=list)
    status: str = "missing"
    error: str | None = None
    # v2 additions ────────────────────────────────────────────────────
    update_cadence_days: int | None = None
    next_recommended_check_at: str | None = None

    def is_installed(self) -> bool:
        return self.local_version is not None and self.status in {"ok", "stale"}

    def is_stale(self) -> bool:
        if not self.is_installed():
            return False
        if self.remote_version is None:
            return False
        return self.local_version != self.remote_version

    def freshness(self, now: datetime | None = None) -> str:
        """Return one of ``FRESHNESS_*`` based on cadence + fetched_at.

        - ``FRESHNESS_FRESH`` — within (1 - DUE_SOON_FRACTION) of cadence
        - ``FRESHNESS_DUE_SOON`` — past 50 % of cadence window
        - ``FRESHNESS_STALE`` — past ``next_recommended_check_at``
        - ``FRESHNESS_UNKNOWN`` — no cadence declared, or never fetched
        """
        if not self.is_installed():
            return FRESHNESS_UNKNOWN
        if self.update_cadence_days is None:
            return FRESHNESS_UNKNOWN
        nra = _parse_iso(self.next_recommended_check_at)
        if nra is None:
            return FRESHNESS_UNKNOWN
        now = now or _now()
        if now >= nra:
            return FRESHNESS_STALE
        cadence = timedelta(days=self.update_cadence_days)
        due_soon_at = nra - (cadence * DUE_SOON_FRACTION)
        if now >= due_soon_at:
            return FRESHNESS_DUE_SOON
        return FRESHNESS_FRESH

    def days_since_fetch(self, now: datetime | None = None) -> int | None:
        f = _parse_iso(self.fetched_at)
        if f is None:
            return None
        return max(0, ((now or _now()) - f).days)


@dataclass
class Manifest:
    schema_version: int = SCHEMA_VERSION
    last_full_check: str | None = None
    sources: dict[str, SourceEntry] = field(default_factory=dict)

    # ── disk i/o ────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> Manifest:
        if not MANIFEST_PATH.exists():
            return cls()
        try:
            with open(MANIFEST_PATH) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt manifest — start fresh rather than crash the UI.
            return cls()
        loaded_version = raw.get("schema_version", 1)
        sources: dict[str, SourceEntry] = {}
        for sid, entry in raw.get("sources", {}).items():
            # Strip unknown keys (forward-compat: older clients ignore newer fields).
            valid_keys = SourceEntry.__dataclass_fields__.keys()
            clean = {k: v for k, v in entry.items() if k in valid_keys}
            sources[sid] = SourceEntry(**clean)
        # Migration: v1 entries simply lack the new fields, which dataclass
        # defaults supply. Always re-stamp to the current version on save.
        return cls(
            schema_version=loaded_version,
            last_full_check=raw.get("last_full_check"),
            sources=sources,
        )

    def save(self) -> None:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        # On save, normalize to the current schema_version regardless of
        # what we loaded — every entry has the v2 fields after dataclass
        # construction.
        payload = {
            "schema_version": SCHEMA_VERSION,
            "last_full_check": self.last_full_check,
            "sources": {sid: asdict(entry) for sid, entry in self.sources.items()},
        }
        # Atomic write: temp file in same dir, then rename.
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=MANIFEST_PATH.parent, prefix=".manifest.", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            os.replace(tmp_path, MANIFEST_PATH)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── accessors ───────────────────────────────────────────────────────

    def entry(self, source_id: str) -> SourceEntry:
        if source_id not in self.sources:
            self.sources[source_id] = SourceEntry()
        return self.sources[source_id]

    def mark_check(self, source_id: str, remote_version: str) -> None:
        e = self.entry(source_id)
        e.remote_version = remote_version
        e.checked_at = _now_iso()
        if e.local_version is None:
            e.status = "missing"
        elif e.local_version != remote_version:
            e.status = "stale"
        else:
            e.status = "ok"

    def mark_check_failed(self, source_id: str, error: str) -> None:
        e = self.entry(source_id)
        e.checked_at = _now_iso()
        e.status = "check_failed"
        e.error = error

    def mark_fetch_ok(
        self,
        source_id: str,
        remote_version: str,
        files: list[Path],
        total_bytes: int,
        update_cadence_days: int | None = None,
    ) -> None:
        from . import RAW_ROOT

        rels = []
        for f in files:
            try:
                rels.append(str(f.relative_to(RAW_ROOT)))
            except ValueError:
                rels.append(str(f))
        e = self.entry(source_id)
        now = _now()
        e.remote_version = remote_version
        e.local_version = remote_version
        e.fetched_at = now.isoformat(timespec="seconds")
        e.checked_at = e.fetched_at
        e.bytes = total_bytes
        e.files = rels
        e.status = "ok"
        e.error = None
        # v2: stamp cadence + next recommended check
        e.update_cadence_days = update_cadence_days
        if update_cadence_days is not None:
            e.next_recommended_check_at = (now + timedelta(days=update_cadence_days)).isoformat(
                timespec="seconds"
            )
        else:
            e.next_recommended_check_at = None

    def mark_fetch_failed(self, source_id: str, error: str) -> None:
        e = self.entry(source_id)
        e.checked_at = _now_iso()
        e.status = "fetch_failed"
        e.error = error

    def update_cadence(self, source_id: str, update_cadence_days: int | None) -> None:
        """Reflect a source's declared cadence into the manifest without
        forcing a fetch. Recomputes ``next_recommended_check_at`` relative
        to the existing ``fetched_at`` when one is known."""
        e = self.entry(source_id)
        e.update_cadence_days = update_cadence_days
        f = _parse_iso(e.fetched_at)
        if f is None or update_cadence_days is None:
            e.next_recommended_check_at = None
            return
        e.next_recommended_check_at = (f + timedelta(days=update_cadence_days)).isoformat(
            timespec="seconds"
        )

    def set_last_full_check(self) -> None:
        self.last_full_check = _now_iso()
