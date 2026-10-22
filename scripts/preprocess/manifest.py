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

The shape lives in the typed dataclasses below. ``to_dict`` / ``from_dict``
codec preserves the on-disk JSON format; ``from_dict`` is backwards-
compatible with legacy entries that pre-date any field added later.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

from . import PREPROCESS_MANIFEST_PATH

SCHEMA_VERSION = 3
HISTORY_LIMIT = 20  # keep last N normalize runs per source


# ── Entry dataclasses ──────────────────────────────────────────────────────


@dataclass
class NormalizeHistoryEntry:
    """One row of a NormalizeEntry's run history."""

    preprocessed_at: str | None
    raw_rows: int | None
    canonical_rows: int | None
    status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preprocessed_at": self.preprocessed_at,
            "raw_rows": self.raw_rows,
            "canonical_rows": self.canonical_rows,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizeHistoryEntry:
        return cls(
            preprocessed_at=d.get("preprocessed_at"),
            raw_rows=d.get("raw_rows"),
            canonical_rows=d.get("canonical_rows"),
            status=d.get("status"),
        )


@dataclass
class NormalizeEntry:
    """One Normalizer's manifest entry — outcome of the most recent run
    plus a bounded run history.
    """

    raw_local_version: str | None
    preprocessed_at: str
    raw_rows: int | None
    canonical_rows: int | None
    bytes: int
    canonical_types: list[str] = field(default_factory=list)
    states_covered: list[str] = field(default_factory=list)
    quality_report_path: str | None = None
    status: str = "ok"
    error: str | None = None
    skip_reason: str | None = None
    rebuilt_from_disk_at: str | None = None
    history: list[NormalizeHistoryEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "raw_local_version": self.raw_local_version,
            "preprocessed_at": self.preprocessed_at,
            "raw_rows": self.raw_rows,
            "canonical_rows": self.canonical_rows,
            "bytes": self.bytes,
            "canonical_types": list(self.canonical_types),
            "states_covered": list(self.states_covered),
            "quality_report_path": self.quality_report_path,
            "status": self.status,
            "error": self.error,
            "history": [h.to_dict() for h in self.history],
        }
        # Optional fields only appear when set, to keep on-disk shape
        # backwards-compatible with manifests that pre-date them.
        if self.skip_reason is not None:
            out["skip_reason"] = self.skip_reason
        if self.rebuilt_from_disk_at is not None:
            out["rebuilt_from_disk_at"] = self.rebuilt_from_disk_at
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NormalizeEntry:
        history_raw = d.get("history") or []
        return cls(
            raw_local_version=d.get("raw_local_version"),
            preprocessed_at=str(d.get("preprocessed_at", "")),
            raw_rows=d.get("raw_rows"),
            canonical_rows=d.get("canonical_rows"),
            bytes=int(d.get("bytes") or 0),
            canonical_types=list(d.get("canonical_types") or []),
            states_covered=list(d.get("states_covered") or []),
            quality_report_path=d.get("quality_report_path"),
            status=str(d.get("status", "ok")),
            error=d.get("error"),
            skip_reason=d.get("skip_reason"),
            rebuilt_from_disk_at=d.get("rebuilt_from_disk_at"),
            history=[NormalizeHistoryEntry.from_dict(h) for h in history_raw],
        )


@dataclass
class ComposeEntry:
    """One state's compose-outcome manifest entry."""

    preprocessed_at: str
    sources_used: list[str] = field(default_factory=list)
    joins_applied: list[str] = field(default_factory=list)
    joins_skipped: list[str] = field(default_factory=list)
    views_built: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    status: str = "ok"
    error: str | None = None
    rebuilt_from_disk_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "preprocessed_at": self.preprocessed_at,
            "sources_used": list(self.sources_used),
            "joins_applied": list(self.joins_applied),
            "views_built": list(self.views_built),
            "counts": dict(self.counts),
            "status": self.status,
            "error": self.error,
        }
        # joins_skipped only set by the rebuild path today — keep optional
        # on disk so live manifests stay clean.
        if self.joins_skipped:
            out["joins_skipped"] = list(self.joins_skipped)
        if self.rebuilt_from_disk_at is not None:
            out["rebuilt_from_disk_at"] = self.rebuilt_from_disk_at
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ComposeEntry:
        return cls(
            preprocessed_at=str(d.get("preprocessed_at", "")),
            sources_used=list(d.get("sources_used") or []),
            joins_applied=list(d.get("joins_applied") or []),
            joins_skipped=list(d.get("joins_skipped") or []),
            views_built=list(d.get("views_built") or []),
            counts=dict(d.get("counts") or {}),
            status=str(d.get("status", "ok")),
            error=d.get("error"),
            rebuilt_from_disk_at=d.get("rebuilt_from_disk_at"),
        )


# ── PreprocessManifest ─────────────────────────────────────────────────────


@dataclass
class PreprocessManifest:
    schema_version: int = SCHEMA_VERSION
    normalized: dict[str, NormalizeEntry] = field(default_factory=dict)
    composed: dict[str, ComposeEntry] = field(default_factory=dict)

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
            normalized={
                sid: NormalizeEntry.from_dict(e) for sid, e in (raw.get("normalized") or {}).items()
            },
            composed={
                fips: ComposeEntry.from_dict(e) for fips, e in (raw.get("composed") or {}).items()
            },
        )

    def save(self) -> None:
        PREPROCESS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": self.schema_version,
            "normalized": {sid: e.to_dict() for sid, e in self.normalized.items()},
            "composed": {fips: e.to_dict() for fips, e in self.composed.items()},
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
        """Record a live normalize-run outcome.

        Builds a fresh NormalizeEntry, appending the prior outcome (if any)
        to the bounded history list before replacing the entry.
        """
        from .base import utcnow_iso

        ts = preprocessed_at or utcnow_iso()
        prior = self.normalized.get(source_id)
        history: list[NormalizeHistoryEntry] = []
        if prior is not None:
            history = list(prior.history)
            history.append(
                NormalizeHistoryEntry(
                    preprocessed_at=prior.preprocessed_at or None,
                    raw_rows=prior.raw_rows,
                    canonical_rows=prior.canonical_rows,
                    status=prior.status,
                )
            )
            history = [h for h in history if h.preprocessed_at]
            history = history[-HISTORY_LIMIT:]
        self.normalized[source_id] = NormalizeEntry(
            raw_local_version=raw_local_version,
            preprocessed_at=ts,
            raw_rows=raw_rows,
            canonical_rows=canonical_rows,
            bytes=bytes_written,
            canonical_types=list(canonical_types),
            states_covered=list(states_covered or []),
            quality_report_path=quality_report_path,
            status=status,
            error=error,
            history=history,
        )

    def skip_normalize(self, source_id: str, *, reason: str = "unchanged") -> None:
        """Mark an existing normalize entry as skipped without rebuilding it."""
        entry = self.normalized.get(source_id)
        if entry is None:
            return
        entry.status = "skipped"
        entry.skip_reason = reason

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
        if entry is None or entry.status not in ("ok", "skipped"):
            return False
        if entry.raw_local_version != raw_local_version:
            return False
        # Spot check: at least one output parquet still exists. rglob so
        # it also finds the multi-file layout (normalized/<id>/parcels/*.parquet).
        try:
            from pathlib import Path

            p = Path(out_dir)
            if not p.exists():
                return False
            if not any(p.rglob("[!.]*.parquet")):
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
        joins_skipped: list[str] | None = None,
        status: str = "ok",
        error: str | None = None,
        preprocessed_at: str | None = None,
    ) -> None:
        """Record a live compose-run outcome for one state."""
        from .base import utcnow_iso

        ts = preprocessed_at or utcnow_iso()
        self.composed[state_fips] = ComposeEntry(
            preprocessed_at=ts,
            sources_used=list(sources_used),
            joins_applied=list(joins_applied),
            joins_skipped=list(joins_skipped or []),
            views_built=list(views_built),
            counts=dict(counts),
            status=status,
            error=error,
        )


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


def rebuild_from_disk() -> PreprocessManifest:
    """Rebuild the preprocess manifest from on-disk normalized + composite files.

    Walks ``data/processed/normalized/<id>/`` and
    ``data/processed/composite/<state_fips>/`` and rewrites the manifest
    from what actually exists, discarding stale "failed" entries that
    were resolved out-of-band (e.g., the openpyxl fix in this session).

    Caller is responsible for `manifest.save()` after — this function
    returns the manifest object so the caller can inspect counts first.
    """
    from datetime import UTC, datetime

    from . import COMPOSITE_ROOT, NORMALIZED_ROOT

    m = PreprocessManifest()
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")

    if NORMALIZED_ROOT.exists():
        for src_dir in sorted(NORMALIZED_ROOT.iterdir()):
            if not src_dir.is_dir():
                continue
            # Legacy single-file sources: <basename>.parquet at the root.
            parquets = [p for p in sorted(src_dir.glob("[!.]*.parquet")) if p.name != "raw.parquet"]
            canonical_types = [p.stem for p in parquets]
            # Multi-file datasets: a <basename>/ subdir of per-county
            # parquets (the parcel normalizer). Exclude the raw/ archive.
            for sub in sorted(d for d in src_dir.iterdir() if d.is_dir()):
                if sub.name == "raw":
                    continue
                sub_parquets = sorted(sub.glob("[!.]*.parquet"))
                if sub_parquets:
                    parquets += sub_parquets
                    canonical_types.append(sub.name)
            if not parquets:
                continue
            total_bytes = sum(p.stat().st_size for p in parquets)
            states_covered: list[str] = []
            qreport = src_dir / "quality_report.json"
            qreport_path: str | None = None
            if qreport.exists():
                qreport_path = str(qreport.relative_to(NORMALIZED_ROOT.parent.parent))
                try:
                    qdata = json.loads(qreport.read_text())
                    # Legacy QRs put states_covered at the root; new QRs put
                    # it under "extras" (per PR #6's codec migration). Try
                    # both, preferring the new location.
                    extras = qdata.get("extras") if isinstance(qdata, dict) else None
                    if isinstance(extras, dict) and isinstance(extras.get("states_covered"), list):
                        states_covered = list(extras["states_covered"])
                    elif isinstance(qdata, dict) and isinstance(qdata.get("states_covered"), list):
                        states_covered = list(qdata["states_covered"])
                except (json.JSONDecodeError, OSError):
                    pass
            mtimes = [p.stat().st_mtime for p in parquets]
            ts = datetime.fromtimestamp(max(mtimes), tz=UTC).isoformat(timespec="seconds")
            raw_lv = get_raw_local_version(src_dir.name)
            m.normalized[src_dir.name] = NormalizeEntry(
                raw_local_version=raw_lv,
                preprocessed_at=ts,
                raw_rows=None,
                canonical_rows=None,
                bytes=total_bytes,
                canonical_types=canonical_types,
                states_covered=states_covered,
                quality_report_path=qreport_path,
                status="ok",
                rebuilt_from_disk_at=now_iso,
            )

    if COMPOSITE_ROOT.exists():
        for state_dir in sorted(COMPOSITE_ROOT.iterdir()):
            if not state_dir.is_dir():
                continue
            catalog_path = state_dir / "catalog.json"
            if not catalog_path.exists():
                continue
            try:
                catalog = json.loads(catalog_path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # joins_applied / joins_skipped / sources_used live in
            # summary.json, not catalog.json — load it so a rebuilt
            # manifest carries the full lists.
            summary: dict = {}
            summary_path = state_dir / "summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text())
                except (json.JSONDecodeError, OSError):
                    summary = {}
            # catalog.json shape: {layers: {canonical_type: {rows: int, ...}},
            #                      views: {view_name: {...}}, ...}
            counts: dict[str, int] = {}
            layers_obj = catalog.get("layers") or {}
            if isinstance(layers_obj, dict):
                for ctype, lentry in layers_obj.items():
                    rows = lentry.get("rows") if isinstance(lentry, dict) else None
                    if isinstance(rows, int):
                        counts[ctype] = rows
            views_obj = catalog.get("views") or {}
            views_built = (
                list(views_obj.keys())
                if isinstance(views_obj, dict)
                else list(catalog.get("views_built") or [])
            )
            ts = datetime.fromtimestamp(catalog_path.stat().st_mtime, tz=UTC).isoformat(
                timespec="seconds"
            )
            m.composed[state_dir.name] = ComposeEntry(
                preprocessed_at=ts,
                sources_used=list(summary.get("sources_used") or []),
                joins_applied=list(summary.get("joins_applied") or []),
                joins_skipped=list(summary.get("joins_skipped") or []),
                views_built=views_built,
                counts=counts,
                status="ok",
                rebuilt_from_disk_at=now_iso,
            )

    return m
