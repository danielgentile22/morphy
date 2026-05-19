"""Core abstractions for the preprocess framework.

Defines:
  - CURRENT_SCHEMA_VERSIONS — bumped per canonical type when its schema changes
  - Normalizer ABC + registry
  - Join ABC + registry (run during compose)
  - View ABC + registry (run after joins)
  - ComposeContext — the per-state working state shared between joins + views
  - NormalizeResult / ComposeResult — return types
  - Helpers (system columns, raw-parquet write, valid_from/to bookkeeping)

The puller is independent of this module; preprocess only depends on the
puller's manifest at read time (for raw_local_version tracking).
"""

from __future__ import annotations

import json
import logging
import sys
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Make the sibling 'fetch' package importable when running as a script.
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

log = logging.getLogger("preprocess")


# ── Schema versions ───────────────────────────────────────────────────────────

CURRENT_SCHEMA_VERSIONS: dict[str, int] = {
    "tower": 1,
    "parcel": 1,
    "distress_overlay": 1,
    "county_score": 1,
    "solar_facility": 1,
    "billboard": 1,
    "license": 1,
    "location": 1,
    "entity": 1,
    "transfer": 1,
    "lease": 1,
    "distributed_pv": 1,
    # Reserved for future use:
    "aggregation": 1,
    "model_prediction": 1,
    "address_point": 1,
}


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class NormalizeResult:
    """Returned by Normalizer.normalize()."""

    raw_rows: int
    canonical_rows: int  # may differ from raw if filtering (rare)
    bytes: int  # total bytes written
    output_files: list[Path]
    canonical_types_written: list[str]
    quality_report: dict


@dataclass
class ComposeResult:
    state_fips: str
    sources_used: list[str]
    joins_applied: list[str]
    views_built: list[str]
    counts: dict[str, int]
    output_files: list[Path]


# ── Normalizer ABC + registry ────────────────────────────────────────────────


class Normalizer(ABC):
    """One per raw source. Reads raw/<source_id>/current/, writes
    canonical-schema output to processed/normalized/<source_id>/.
    """

    source_id: str = ""
    canonical_types: list[str] = []  # one or more of CURRENT_SCHEMA_VERSIONS keys

    @abstractmethod
    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        """Read raw_dir, write outputs to out_dir."""

    def is_available(self, raw_dir: Path) -> bool:
        """Default: source is available if raw_dir is non-empty."""
        if not raw_dir.exists():
            return False
        return any(p.is_file() for p in raw_dir.rglob("*"))


_NORMALIZER_REGISTRY: OrderedDict[str, Normalizer] = OrderedDict()


def register_normalizer(cls: type[Normalizer]) -> type[Normalizer]:
    """Class decorator: instantiate and register a Normalizer."""
    inst = cls()
    if not inst.source_id:
        raise ValueError(f"{cls.__name__}: source_id is required")
    if not inst.canonical_types:
        raise ValueError(f"{cls.__name__}: canonical_types is required")
    for ct in inst.canonical_types:
        if ct not in CURRENT_SCHEMA_VERSIONS:
            raise ValueError(
                f"{cls.__name__}: unknown canonical_type {ct!r} — add it to CURRENT_SCHEMA_VERSIONS"
            )
    if inst.source_id in _NORMALIZER_REGISTRY:
        raise ValueError(f"duplicate normalizer for source_id {inst.source_id!r}")
    _NORMALIZER_REGISTRY[inst.source_id] = inst
    return cls


def all_normalizers() -> list[Normalizer]:
    return list(_NORMALIZER_REGISTRY.values())


def get_normalizer(source_id: str) -> Normalizer:
    if source_id not in _NORMALIZER_REGISTRY:
        raise KeyError(f"no normalizer for source_id {source_id!r}")
    return _NORMALIZER_REGISTRY[source_id]


# ── ComposeContext ───────────────────────────────────────────────────────────


@dataclass
class ComposeContext:
    """Per-state working state. The Composer loads normalized data into this,
    Joins mutate it in place, Views read from it.

    Tables are keyed by canonical_type. Each entry is a GeoDataFrame (for
    spatial types) or a DataFrame (for tabular types like county_score).
    """

    state_fips: str
    state_name: str
    state_abbr: str
    tables: dict[str, Any] = field(default_factory=dict)  # type -> GDF/DF
    join_log: list[str] = field(default_factory=list)
    view_log: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def get(self, canonical_type: str):
        return self.tables.get(canonical_type)

    def set(self, canonical_type: str, value) -> None:
        self.tables[canonical_type] = value

    def has(self, canonical_type: str) -> bool:
        v = self.tables.get(canonical_type)
        if v is None:
            return False
        try:
            return len(v) > 0
        except TypeError:
            return True


# ── Join ABC + registry ──────────────────────────────────────────────────────


class Join(ABC):
    """A spatial or attribute join that annotates one canonical type with
    columns derived from another. Runs once per state during compose.

    Joins declare their inputs, what they annotate, and what columns they
    add — used for dependency ordering and for catalog generation.
    """

    name: str = ""  # human-friendly name (also used for log)
    inputs: list[str] = []  # canonical types this join reads
    annotates: str = ""  # canonical type this join enriches (or "*")
    columns_added: list[str] = []
    depends_on: list[str] = []  # other Join names that must run first

    @abstractmethod
    def apply(self, ctx: ComposeContext) -> None: ...

    def is_applicable(self, ctx: ComposeContext) -> bool:
        """Default: applicable if all inputs are present."""
        return all(ctx.has(t) for t in self.inputs)


_JOIN_REGISTRY: list[Join] = []


def register_join(cls: type[Join]) -> type[Join]:
    inst = cls()
    if not inst.name:
        inst.name = cls.__name__
    if not inst.inputs:
        raise ValueError(f"{cls.__name__}: inputs required")
    if not inst.annotates:
        raise ValueError(f"{cls.__name__}: annotates required")
    _JOIN_REGISTRY.append(inst)
    return cls


def all_joins() -> list[Join]:
    return list(_JOIN_REGISTRY)


def ordered_joins() -> list[Join]:
    """Return joins in dependency order. Raises on cycles."""
    by_name = {j.name: j for j in _JOIN_REGISTRY}
    ordered: list[Join] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(j: Join) -> None:
        if j.name in visited:
            return
        if j.name in visiting:
            raise ValueError(f"join dependency cycle involving {j.name}")
        visiting.add(j.name)
        for dep_name in j.depends_on:
            if dep_name not in by_name:
                raise ValueError(f"join {j.name} depends on unknown join {dep_name}")
            visit(by_name[dep_name])
        visiting.remove(j.name)
        visited.add(j.name)
        ordered.append(j)

    for j in _JOIN_REGISTRY:
        visit(j)
    return ordered


# ── View ABC + registry ──────────────────────────────────────────────────────


class View(ABC):
    """A derived dataset built from already-joined canonical tables."""

    name: str = ""
    inputs: list[str] = []
    description: str = ""
    write_geojson: bool = False  # map-app-facing views set this True

    @abstractmethod
    def build(self, ctx: ComposeContext):
        """Return a GeoDataFrame or DataFrame, or None if not buildable."""

    def is_applicable(self, ctx: ComposeContext) -> bool:
        return all(ctx.has(t) for t in self.inputs)


_VIEW_REGISTRY: OrderedDict[str, View] = OrderedDict()


def register_view(cls: type[View]) -> type[View]:
    inst = cls()
    if not inst.name:
        inst.name = cls.__name__
    if not inst.inputs:
        raise ValueError(f"{cls.__name__}: inputs required")
    if inst.name in _VIEW_REGISTRY:
        raise ValueError(f"duplicate view name {inst.name!r}")
    _VIEW_REGISTRY[inst.name] = inst
    return cls


def all_views() -> list[View]:
    return list(_VIEW_REGISTRY.values())


def get_view(name: str) -> View:
    if name not in _VIEW_REGISTRY:
        raise KeyError(f"no view named {name!r}")
    return _VIEW_REGISTRY[name]


# ── System-column helpers (used by Normalizer subclasses) ─────────────────────


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def utcnow_date() -> str:
    return datetime.now(UTC).date().isoformat()


def add_system_columns(
    df,
    source_id: str,
    canonical_type: str,
    *,
    tenant_id: str = "pilot",
    valid_from: str | None = None,
):
    """Stamp the four system columns + the three time-series ones on every row.

    Returns the same DataFrame/GeoDataFrame (modified in place + returned for
    chaining). Caller decides ordering — these are typically appended last so
    they're easy to spot.
    """
    schema_version = CURRENT_SCHEMA_VERSIONS.get(canonical_type, 1)
    now = utcnow_iso()
    today = valid_from or utcnow_date()

    df["_source"] = source_id
    df["_processed_at"] = now
    df["_schema_version"] = schema_version
    df["_tenant_id"] = tenant_id
    if "_quality_score" not in df.columns:
        df["_quality_score"] = None
    df["valid_from"] = today
    if "valid_to" not in df.columns:
        df["valid_to"] = None
    return df


# ── Quality-report builder ────────────────────────────────────────────────────


def quality_report(
    source_id: str,
    tables: dict[str, Any],
    *,
    warnings: list[str] | None = None,
) -> dict:
    """Build a quality report from a dict of {table_name: dataframe}."""
    report: dict[str, Any] = {
        "source_id": source_id,
        "generated_at": utcnow_iso(),
        "tables": {},
        "warnings": list(warnings or []),
    }
    for name, df in tables.items():
        if df is None:
            report["tables"][name] = {"rows": 0, "note": "table not produced"}
            continue
        try:
            rows = len(df)
        except TypeError:
            rows = 0
        cols_summary: dict[str, dict] = {}
        for col in getattr(df, "columns", []):
            if col == "geometry":
                continue
            try:
                ser = df[col]
                non_null = int(ser.notna().sum())
                null_rate = round(1.0 - non_null / max(rows, 1), 4)
                cols_summary[str(col)] = {
                    "null_rate": null_rate,
                    "dtype": str(ser.dtype),
                }
            except Exception:
                cols_summary[str(col)] = {"null_rate": None, "dtype": "unknown"}

        geom_pct = None
        if hasattr(df, "geometry"):
            try:
                geom_pct = round(float(df.geometry.is_valid.mean()) * 100, 2) if rows else None
            except Exception:
                geom_pct = None

        report["tables"][name] = {
            "rows": rows,
            "columns": cols_summary,
            "geometry_validity_pct": geom_pct,
        }
    return report


def write_quality_report(out_dir: Path, report: dict) -> Path:
    path = out_dir / "quality_report.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    return path
