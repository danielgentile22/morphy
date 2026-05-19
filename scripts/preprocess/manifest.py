"""Read / write data/processed/preprocess_manifest.json.

Schema (v3):

  {
    "schema_version": 3,
    "normalized": {
      "<source_id>": {
        "raw_local_version": "...",
        "preprocessed_at": "<ISO 8601>",
        "raw_rows": <int>,
        "canonical_rows": <int>,
        "bytes": <int>,
        "canonical_types": [...],
        "states_covered": [...],   (populated when parcel-like sources are normalized)
        "status": "ok" | "failed" | "skipped" | "unavailable",
        "error": null | "...",
        "quality_report_path": "...",
        "history": [
          {"preprocessed_at": "...", "raw_rows": ..., "canonical_rows": ..., "status": "ok"}
        ]
      }
    },
    "composed": {
      "<state_fips>": {
        "preprocessed_at": "...",
        "sources_used": [...],
        "joins_applied": [...],
        "views_built": [...],
        "counts": {...},
        "status": "ok" | "failed",
        "error": null | "..."
      }
    }
  }
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field

from . import PREPROCESS_MANIFEST_PATH

SCHEMA_VERSION = 3
HISTORY_LIMIT = 20  # keep last N normalize runs per source


@dataclass
class PreprocessManifest:
    schema_version: int = SCHEMA_VERSION
    normalized: dict[str, dict] = field(default_factory=dict)
    composed: dict[str, dict] = field(default_factory=dict)

    # ── load / save ─────────────────────────────────────────────────────

    @classmethod
    def load(cls) -> PreprocessManifest:
        if not PREPROCESS_MANIFEST_PATH.exists():
            return cls()
        try:
            raw = json.loads(PREPROCESS_MANIFEST_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            # Corrupt manifest — start fresh rather than crash.
            return cls()
        return cls(
            schema_version=raw.get("schema_version", SCHEMA_VERSION),
            normalized=raw.get("normalized", {}) or {},
            composed=raw.get("composed", {}) or {},
        )

    def save(self) -> None:
        PREPROCESS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "normalized": self.normalized,
            "composed": self.composed,
        }
        # Atomic write via temp file + rename.
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=PREPROCESS_MANIFEST_PATH.parent,
            prefix=".preprocess_manifest.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(payload, f, indent=2, sort_keys=True, default=str)
            os.replace(tmp_path, PREPROCESS_MANIFEST_PATH)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # ── normalize-side helpers ──────────────────────────────────────────

    def record_normalize(
        self,
        source_id: str,
        *,
        raw_local_version: str | None,
        raw_rows: int,
        canonical_rows: int,
        bytes_written: int,
        canonical_types: list[str],
        states_covered: list[str] | None = None,
        quality_report_path: str | None = None,
        status: str = "ok",
        error: str | None = None,
        preprocessed_at: str | None = None,
    ) -> None:
        from .base import utcnow_iso

        ts = preprocessed_at or utcnow_iso()
        prior = self.normalized.get(source_id, {})
        history = list(prior.get("history") or [])
        # Append a tiny history entry; cap to HISTORY_LIMIT.
        history.append(
            {
                "preprocessed_at": prior.get("preprocessed_at"),
                "raw_rows": prior.get("raw_rows"),
                "canonical_rows": prior.get("canonical_rows"),
                "status": prior.get("status"),
            }
        )
        history = [h for h in history if h.get("preprocessed_at")]
        history = history[-HISTORY_LIMIT:]
        self.normalized[source_id] = {
            "raw_local_version": raw_local_version,
            "preprocessed_at": ts,
            "raw_rows": raw_rows,
            "canonical_rows": canonical_rows,
            "bytes": bytes_written,
            "canonical_types": canonical_types,
            "states_covered": states_covered or [],
            "quality_report_path": quality_report_path,
            "status": status,
            "error": error,
            "history": history,
        }

    def skip_normalize(self, source_id: str, *, reason: str = "unchanged") -> None:
        if source_id not in self.normalized:
            return
        self.normalized[source_id]["status"] = "skipped"
        self.normalized[source_id]["skip_reason"] = reason

    def is_normalize_fresh(
        self,
        source_id: str,
        *,
        raw_local_version: str | None,
        out_dir,
    ) -> bool:
        """True if the last successful normalize was against the current
        raw_local_version AND its output files still exist on disk.
        """
        entry = self.normalized.get(source_id)
        if not entry or entry.get("status") not in ("ok", "skipped"):
            return False
        if entry.get("raw_local_version") != raw_local_version:
            return False
        # Spot check: at least one output file still exists.
        try:
            from pathlib import Path

            p = Path(out_dir)
            if not p.exists():
                return False
            if not any(p.glob("*.parquet")):
                return False
        except Exception:
            return False
        return True

    # ── compose-side helpers ────────────────────────────────────────────

    def record_compose(
        self,
        state_fips: str,
        *,
        sources_used: list[str],
        joins_applied: list[str],
        views_built: list[str],
        counts: dict[str, int],
        status: str = "ok",
        error: str | None = None,
        preprocessed_at: str | None = None,
    ) -> None:
        from .base import utcnow_iso

        ts = preprocessed_at or utcnow_iso()
        self.composed[state_fips] = {
            "preprocessed_at": ts,
            "sources_used": sources_used,
            "joins_applied": joins_applied,
            "views_built": views_built,
            "counts": counts,
            "status": status,
            "error": error,
        }


def get_raw_local_version(source_id: str) -> str | None:
    """Look up local_version for a source in the puller's manifest.json."""
    try:
        # Importing here keeps fetch package optional for preprocess unit tests.
        from fetch.manifest import Manifest as PullerManifest  # type: ignore
    except ImportError:
        return None
    pm = PullerManifest.load()
    entry = pm.sources.get(source_id)
    if entry is None:
        return None
    return getattr(entry, "local_version", None)
