"""Persistent manifest of what we have on disk.

Single JSON file at ``data/manifest.json``. The puller is the only writer.

Schema (schema_version = 1):

    {
      "schema_version": 1,
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
          "error":          null | "<message>"
        }
      }
    }
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import MANIFEST_PATH


SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SourceEntry:
    remote_version: Optional[str] = None
    local_version: Optional[str] = None
    fetched_at: Optional[str] = None
    checked_at: Optional[str] = None
    bytes: int = 0
    files: list[str] = field(default_factory=list)
    status: str = "missing"
    error: Optional[str] = None

    def is_installed(self) -> bool:
        return self.local_version is not None and self.status in {"ok", "stale"}

    def is_stale(self) -> bool:
        if not self.is_installed():
            return False
        if self.remote_version is None:
            return False
        return self.local_version != self.remote_version


@dataclass
class Manifest:
    schema_version: int = SCHEMA_VERSION
    last_full_check: Optional[str] = None
    sources: dict[str, SourceEntry] = field(default_factory=dict)

    # ── disk i/o ────────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> "Manifest":
        if not MANIFEST_PATH.exists():
            return cls()
        try:
            with open(MANIFEST_PATH) as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Corrupt manifest — start fresh rather than crash the UI.
            return cls()
        sources = {
            sid: SourceEntry(**entry) for sid, entry in raw.get("sources", {}).items()
        }
        return cls(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            last_full_check=raw.get("last_full_check"),
            sources=sources,
        )

    def save(self) -> None:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
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
    ) -> None:
        from . import RAW_ROOT
        rels = []
        for f in files:
            try:
                rels.append(str(f.relative_to(RAW_ROOT)))
            except ValueError:
                rels.append(str(f))
        e = self.entry(source_id)
        e.remote_version = remote_version
        e.local_version = remote_version
        e.fetched_at = _now_iso()
        e.checked_at = _now_iso()
        e.bytes = total_bytes
        e.files = rels
        e.status = "ok"
        e.error = None

    def mark_fetch_failed(self, source_id: str, error: str) -> None:
        e = self.entry(source_id)
        e.checked_at = _now_iso()
        e.status = "fetch_failed"
        e.error = error

    def set_last_full_check(self) -> None:
        self.last_full_check = _now_iso()
