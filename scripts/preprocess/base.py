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


# ── Per-canonical-type metadata ──────────────────────────────────────────────

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

# Spatial canonical types carry geometry; tabular ones don't. The default
# loader uses this to decide whether to read parquets as GeoDataFrames.
SPATIAL_TYPES: set[str] = {
    "tower",
    "parcel",
    "distress_overlay",
    "solar_facility",
    "billboard",
    "address_point",
}
TABULAR_TYPES: set[str] = {
    "county_score",
    "license",
    "location",
    "entity",
    "transfer",
    "lease",
    "distributed_pv",
    "aggregation",
    "model_prediction",
}

# Per-canonical-type file/directory basename. The default loader reads from
# ``normalized/<source_id>/<basename>/*.parquet`` (sharded) or
# ``normalized/<source_id>/<basename>.parquet`` (single file); the Composer
# uses the same basename when writing per-state composite outputs. Where a
# canonical type isn't listed, the type name itself is the basename.
OUTPUT_BASENAMES: dict[str, str] = {
    "tower": "towers",
    "parcel": "parcels",
    "distress_overlay": "distress_overlays",
    "solar_facility": "solar_facilities",
    "billboard": "billboards",
    "county_score": "county_scores",
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

    def load_state_data(
        self, state_fips: str
    ) -> dict[str, Any]:
        """Read this source's normalized output, filtered to one state.

        For each declared :attr:`canonical_types`, the default looks for
        parquet output under
        ``normalized/<source_id>/<basename>/*.parquet`` (sharded layout,
        used by per-county parcel normalizers — ADR-050) or, failing
        that, ``normalized/<source_id>/<basename>.parquet`` (single
        file, used by the national sources). Spatial types are read as
        GeoDataFrames; tabular types as DataFrames. Rows are filtered
        by the ``state_fips`` column — which is a **hard contract** on
        every canonical output. A canonical type with no rows for the
        requested state is omitted from the returned dict.

        Override only when the source's output layout or
        state-identification scheme genuinely differs from this
        contract (no source needs to today).
        """
        from . import NORMALIZED_ROOT  # local to avoid an import cycle

        src_dir = NORMALIZED_ROOT / self.source_id
        if not src_dir.exists():
            return {}

        out: dict[str, Any] = {}
        for ct in self.canonical_types:
            basename = OUTPUT_BASENAMES.get(ct, ct)
            subdir = src_dir / basename
            if subdir.is_dir():
                paths = sorted(subdir.glob("*.parquet"))
            else:
                single = src_dir / f"{basename}.parquet"
                paths = [single] if single.exists() else []
            if not paths:
                continue

            frames: list[Any] = []
            for p in paths:
                try:
                    df = _read_parquet_typed(p, ct)
                except Exception as e:
                    log.warning("load_state_data: failed to read %s: %s", p, e)
                    continue
                if "state_fips" not in df.columns:
                    log.warning(
                        "load_state_data: %s lacks the contractual `state_fips` "
                        "column; skipping (override Normalizer.load_state_data "
                        "to filter another way)",
                        p,
                    )
                    continue
                filtered = df[df["state_fips"] == state_fips]
                if len(filtered) > 0:
                    frames.append(filtered.copy())

            if frames:
                out[ct] = _concat_typed(frames, ct)
        return out


def _read_parquet_typed(path: Path, canonical_type: str):
    """Read a parquet as the right frame type for its canonical_type."""
    import pandas as pd

    if canonical_type in SPATIAL_TYPES:
        import geopandas as gpd

        return gpd.read_parquet(path)
    return pd.read_parquet(path)


def _concat_typed(frames: list, canonical_type: str):
    """Concat frames preserving GeoDataFrame-ness for spatial types."""
    import pandas as pd

    if canonical_type in SPATIAL_TYPES:
        import geopandas as gpd

        return gpd.GeoDataFrame(
            pd.concat(frames, ignore_index=True),
            geometry="geometry",
            crs="EPSG:4326",
        )
    return pd.concat(frames, ignore_index=True)


_NORMALIZER_REGISTRY: OrderedDict[str, Normalizer] = OrderedDict()


def register_normalizer(cls: type[Normalizer]) -> type[Normalizer]:
    """Class decorator: instantiate and register a Normalizer."""
    register_normalizer_instance(cls())
    return cls


def register_normalizer_instance(inst: Normalizer) -> Normalizer:
    """Register an already-constructed Normalizer.

    Sibling of @register_normalizer for normalizers whose construction
    needs arguments (e.g. ParcelNormalizer, which takes a ParcelAdapter)
    and so can't fit the zero-arg-decorator pattern.
    """
    cls_name = type(inst).__name__
    if not inst.source_id:
        raise ValueError(f"{cls_name}: source_id is required")
    if not inst.canonical_types:
        raise ValueError(f"{cls_name}: canonical_types is required")
    for ct in inst.canonical_types:
        if ct not in CURRENT_SCHEMA_VERSIONS:
            raise ValueError(
                f"{cls_name}: unknown canonical_type {ct!r} — add it to CURRENT_SCHEMA_VERSIONS"
            )
    if inst.source_id in _NORMALIZER_REGISTRY:
        raise ValueError(f"duplicate normalizer for source_id {inst.source_id!r}")
    _NORMALIZER_REGISTRY[inst.source_id] = inst
    return inst


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


# ── Join helper ───────────────────────────────────────────────────────────────


def safe_merge(left, right, *, on, columns_added, how="left"):
    """Left-merge ``right`` into ``left``, where ``right`` contributes
    ``columns_added``.

    Normalizers initialise reverse-summary columns (e.g. ``distress_tier``,
    ``persistent_poverty`` on a parcel) as placeholders so the canonical
    schema is stable before any Join runs. When a Join later merges in the
    *real* values, pandas sees the column on both sides and produces
    ``col_x`` / ``col_y`` — silently leaving the placeholder in place. This
    helper drops the pre-existing ``columns_added`` from ``left`` first so
    the merge populates fresh values cleanly.

    Restores GeoDataFrame geometry registration when ``left`` was
    geospatial — a plain ``merge`` can drop the geometry-column binding.

    Callers still do their own ``fillna`` afterwards: the right default
    differs per column ("" for a tier string, False for a boolean flag).
    """
    import geopandas as gpd

    left_clean = left.drop(columns=[c for c in columns_added if c in left.columns])
    merged = left_clean.merge(right, on=on, how=how)
    if "geometry" in merged.columns:
        merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=getattr(left, "crs", None))
    return merged


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
