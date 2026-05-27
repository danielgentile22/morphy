"""facets.py — the DuckDB-WASM inputs: parcels_attr.parquet + facets.json.

Two ``--app-assets`` outputs per state, from a single read of
``parcels.parquet``:

- **parcels_attr.parquet** — the filterable / searchable / displayable
  columns only. The three WKB geometry columns, the ``extras`` blob and
  every ``_``-prefixed internal column are dropped; ``geom_bbox`` (a
  plain string — lets the app fly-to a parcel without geometry) and the
  JSON-string nested columns (``interestingness_components``,
  ``infrastructure_summary``, ``distress_overlays``) are kept. Written
  with many small row groups, sorted by ``interestingness_score``
  descending. DuckDB-WASM range-queries this file.
- **facets.json** — distinct categorical values + counts and numeric
  min/max, so the filter controls render instantly without a DuckDB
  round-trip.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from . import COMPOSITE_ROOT

log = logging.getLogger("preprocess.facets")

# Columns excluded from parcels_attr.parquet: the WKB geometry columns
# and the extras blob (every _-prefixed internal column is also dropped).
_DROP_EXACT: frozenset[str] = frozenset(
    {"geometry", "geom_centroid", "geom_simplified", "extras"}
)

CATEGORICAL_FACETS: tuple[str, ...] = (
    "owner_kind",
    "distress_tier",
    "land_use_desc",
    "county_fips",
)
NUMERIC_FACETS: tuple[str, ...] = (
    "assessed_value",
    "acreage",
    "interestingness_score",
    "owner_cluster_size",
)
SORT_COLUMN = "interestingness_score"
ROW_GROUP_SIZE = 16384
# Cap categorical facet lists so facets.json stays small (< 100 KB/state).
MAX_CATEGORICAL_VALUES = 200
FACETS_SCHEMA_VERSION = 1


def attr_columns(all_columns: list[str]) -> list[str]:
    """The columns kept in parcels_attr.parquet (drops geometry + internals)."""
    return [c for c in all_columns if c not in _DROP_EXACT and not c.startswith("_")]


def _compute_facets(table: pa.Table) -> dict:
    """Distinct categorical values + counts, and numeric min/max."""
    categorical: dict[str, list[dict]] = {}
    for col in CATEGORICAL_FACETS:
        if col not in table.column_names:
            continue
        counts = pc.value_counts(table.column(col))
        pairs = []
        for i in range(len(counts)):
            value = counts.field("values")[i].as_py()
            if value is None or value == "":
                continue
            pairs.append({"value": value, "count": counts.field("counts")[i].as_py()})
        pairs.sort(key=lambda p: p["count"], reverse=True)
        categorical[col] = pairs[:MAX_CATEGORICAL_VALUES]

    numeric: dict[str, dict] = {}
    for col in NUMERIC_FACETS:
        if col not in table.column_names:
            continue
        mm = pc.min_max(table.column(col)).as_py()
        numeric[col] = {"min": mm["min"], "max": mm["max"]}

    return {
        "schema_version": FACETS_SCHEMA_VERSION,
        "total": table.num_rows,
        "categorical": categorical,
        "numeric": numeric,
    }


def _write_parquet_atomic(table: pa.Table, path: Path) -> None:
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    os.close(tmp_fd)
    tmp = Path(tmp_name)
    try:
        pq.write_table(table, tmp, row_group_size=ROW_GROUP_SIZE, compression="zstd")
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _write_json_atomic(payload: dict, path: Path) -> None:
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        Path(tmp_name).replace(path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _resolve_parcels_source(state_dir: Path) -> tuple[Path, bool]:
    """Locate the parcels source for a state — either a single
    ``parcels.parquet`` (returned as that file's path) or a ``parcels/``
    shard directory (returned as the dir path). Use ``is_sharded`` to
    decide how to read.
    """
    from .app_assets import resolve_parcel_paths

    paths, is_sharded = resolve_parcel_paths(state_dir)
    return (state_dir / "parcels", True) if is_sharded else (paths[0], False)


def _read_parcels_table(source: Path, *, columns: list[str], is_sharded: bool) -> pa.Table:
    """Column-projected read of the parcels source. Sharded reads stream
    each file individually (bounded memory per shard) and concat at end."""
    if not is_sharded:
        return pq.read_table(source, columns=columns)
    shards = sorted(source.glob("*.parquet"))
    if not shards:
        raise FileNotFoundError(f"shard dir {source} contains no .parquet files")
    # Each shard's columns may overlap but the schema is consistent across
    # shards (chunked compose writes them from one chunk-aware loop). We
    # project at read time so the geometry payload is never materialised.
    tables: list[pa.Table] = []
    for shard in shards:
        pf = pq.ParquetFile(shard)
        present = [c for c in columns if c in pf.schema_arrow.names]
        tables.append(pq.read_table(shard, columns=present))
    return pa.concat_tables(tables, promote_options="default")


def build_facets(state_fips: str, *, composite_root: Path | None = None) -> dict:
    """Write parcels_attr.parquet + facets.json for one state.

    Raises FileNotFoundError when the state has neither parcels.parquet
    nor a parcels/ shard directory.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    state_dir = root / state_fips
    parcels_source, is_sharded = _resolve_parcels_source(state_dir)

    # Discover available columns from the first source (single file OR
    # first shard) so we can project consistently.
    if is_sharded:
        first_shard = next(iter(sorted(parcels_source.glob("*.parquet"))))
        schema_names = pq.ParquetFile(first_shard).schema_arrow.names
    else:
        schema_names = pq.ParquetFile(parcels_source).schema_arrow.names
    keep = attr_columns(schema_names)

    table = _read_parcels_table(parcels_source, columns=keep, is_sharded=is_sharded)
    if SORT_COLUMN in table.column_names:
        table = table.sort_by([(SORT_COLUMN, "descending")])

    attr_path = state_dir / "parcels_attr.parquet"
    _write_parquet_atomic(table, attr_path)

    facets = _compute_facets(table)
    facets["state_fips"] = state_fips
    facets_path = state_dir / "facets.json"
    _write_json_atomic(facets, facets_path)

    log.info(
        "wrote %s (%d cols, %s) + %s",
        attr_path,
        table.num_columns,
        "sharded" if is_sharded else "single-file",
        facets_path,
    )
    return {"attr_path": str(attr_path), "facets_path": str(facets_path), "rows": table.num_rows}


def _states_with_parcels(composite_root: Path) -> list[str]:
    """States that have either a parcels.parquet or a parcels/ shard dir."""
    from .app_assets import iter_composed_states, state_has_parcels

    return iter_composed_states(composite_root, predicate=state_has_parcels)


def run_facets(state_fips: str | None = None, *, composite_root: Path | None = None) -> dict:
    """Build facets + the slim parquet for one state or every composed state."""
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    states = [state_fips] if state_fips else _states_with_parcels(root)
    ok: list[str] = []
    failed: list[str] = []
    for fips in states:
        try:
            build_facets(fips, composite_root=root)
            ok.append(fips)
        except Exception as exc:  # noqa: BLE001 — one state's failure must not abort the rest
            log.error("facets failed for state %s: %s", fips, exc)
            failed.append(fips)
    return {"ok": ok, "failed": failed}
