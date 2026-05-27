"""Per-source quality summary.

Every Normalizer returns a :class:`QualityReport` on its
:class:`NormalizeResult`. The report is also written to
``normalized/<source_id>/quality_report.json`` for offline inspection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ColumnStats:
    """Per-column row-quality summary inside a TableStats."""

    null_rate: float | None
    dtype: str

    def to_dict(self) -> dict[str, Any]:
        return {"null_rate": self.null_rate, "dtype": self.dtype}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ColumnStats:
        return cls(null_rate=d.get("null_rate"), dtype=str(d.get("dtype", "unknown")))


@dataclass
class TableStats:
    """One Normalizer-produced table's quality summary."""

    rows: int
    columns: dict[str, ColumnStats] = field(default_factory=dict)
    # Validity percentage for GeoDataFrame geometry columns; None when the
    # table is tabular or geometry computation failed.
    geometry_validity_pct: float | None = None
    # Free-text annotation: "table not produced", or per-source notes such
    # as "column stats sampled from 1 of N layers".
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"rows": self.rows}
        # The "not produced" shape is just {rows: 0, note}; only include
        # columns/geometry_validity_pct when the table actually exists.
        if self.columns or self.geometry_validity_pct is not None:
            out["columns"] = {k: v.to_dict() for k, v in self.columns.items()}
            out["geometry_validity_pct"] = self.geometry_validity_pct
        if self.note is not None:
            out["note"] = self.note
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TableStats:
        cols_raw = d.get("columns") or {}
        columns = {k: ColumnStats.from_dict(v) for k, v in cols_raw.items()}
        return cls(
            rows=int(d.get("rows", 0)),
            columns=columns,
            geometry_validity_pct=d.get("geometry_validity_pct"),
            note=d.get("note"),
        )


@dataclass
class QualityReport:
    """Typed, codec-backed version of the per-source quality summary.

    Source-specific add-ons (e.g. ``state_parcels`` stamps
    ``"states_covered"``) live in :attr:`extras` rather than at the
    root; the codec round-trips them through the ``"extras"`` key in
    the JSON. Old on-disk reports with unknown root keys are still
    parseable — :meth:`from_dict` moves anything it doesn't recognise
    into ``extras``.
    """

    source_id: str
    generated_at: str
    tables: dict[str, TableStats] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    # Root keys recognised by the codec. Anything else found in a JSON
    # file flows into `extras` on parse.
    _KNOWN_ROOT_KEYS = frozenset(
        {"source_id", "generated_at", "tables", "warnings", "extras"}
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "generated_at": self.generated_at,
            "tables": {k: v.to_dict() for k, v in self.tables.items()},
            "warnings": list(self.warnings),
            "extras": dict(self.extras),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QualityReport:
        tables = {k: TableStats.from_dict(v) for k, v in (d.get("tables") or {}).items()}
        extras = dict(d.get("extras") or {})
        # Backwards-compat: anything at the root the codec doesn't know
        # is a legacy source-specific add-on; lift it into `extras`.
        for k, v in d.items():
            if k not in cls._KNOWN_ROOT_KEYS:
                extras[k] = v
        return cls(
            source_id=str(d.get("source_id", "")),
            generated_at=str(d.get("generated_at", "")),
            tables=tables,
            warnings=list(d.get("warnings") or []),
            extras=extras,
        )


def quality_report(
    source_id: str,
    tables: dict[str, Any],
    *,
    warnings: list[str] | None = None,
) -> QualityReport:
    """Build a :class:`QualityReport` from a dict of {table_name: dataframe}.

    A ``None`` value in ``tables`` records a "table not produced" entry
    (rows=0, note set) — used by sources that conditionally emit a
    canonical type.
    """
    from .system_columns import utcnow_iso

    report = QualityReport(
        source_id=source_id,
        generated_at=utcnow_iso(),
        warnings=list(warnings or []),
    )
    for name, df in tables.items():
        if df is None:
            report.tables[name] = TableStats(rows=0, note="table not produced")
            continue
        try:
            rows = len(df)
        except TypeError:
            rows = 0
        columns: dict[str, ColumnStats] = {}
        for col in getattr(df, "columns", []):
            if col == "geometry":
                continue
            try:
                ser = df[col]
                non_null = int(ser.notna().sum())
                null_rate = round(1.0 - non_null / max(rows, 1), 4)
                columns[str(col)] = ColumnStats(null_rate=null_rate, dtype=str(ser.dtype))
            except Exception:
                columns[str(col)] = ColumnStats(null_rate=None, dtype="unknown")

        geom_pct: float | None = None
        if hasattr(df, "geometry"):
            try:
                geom_pct = round(float(df.geometry.is_valid.mean()) * 100, 2) if rows else None
            except Exception:
                geom_pct = None

        report.tables[name] = TableStats(
            rows=rows,
            columns=columns,
            geometry_validity_pct=geom_pct,
        )
    return report


def write_quality_report(out_dir: Path, report: QualityReport) -> Path:
    """Serialize a QualityReport to ``<out_dir>/quality_report.json``."""
    path = out_dir / "quality_report.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str))
    return path
