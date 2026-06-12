"""DuckDB session helper — the heavy-lift engine's one entry point (PRD #135).

This is the ONLY module that manages DuckDB connections for the
preprocess pipeline: connection setup, spatial-extension loading, and
registration of a state's sharded normalized parcels as a queryable
relation. Stages that migrate to the DuckDB engine express their work
as SQL over the relations registered here; nothing else creates or
configures connections.

The spatial extension rides the lockfile as a platform wheel
(`duckdb-extension-spatial`), so sessions load it from site-packages —
no runtime download, hermetic in CI and offline. If the wheel and the
`duckdb` package ever desync (the binary is built per DuckDB version),
`session()` falls back to the standard install-from-repo path rather
than failing the run.

Registration mirrors `compose_helpers.iter_state_parcel_shards` exactly:
same shard enumeration order (parcel normalizers in registry order, then
sorted filenames), same skip-with-warning for unreadable shards or
shards missing the contractual ``state_fips`` column, same per-state row
filter. The registered view adds three ordering/identity columns —
``__shard_seq`` / ``__shard_label`` / ``__row_idx`` — so SQL stages can
reproduce the canonical shard iteration order deterministically (e.g.
"first match wins" tie-breaks).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from .base import OUTPUT_BASENAMES

log = logging.getLogger("preprocess.duck")

#: Name of the per-state parcels view `register_state_parcels` creates.
PARCELS_VIEW = "parcels"


# ── Session ────────────────────────────────────────────────────────────────


def _spatial_extension_path() -> str | None:
    """Locate the spatial extension binary inside the locked wheel."""
    try:
        import duckdb_extension_spatial
    except ImportError:
        return None
    pkg = Path(duckdb_extension_spatial.__file__).parent
    hits = sorted((pkg / "extensions").rglob("*.duckdb_extension"))
    return str(hits[0]) if hits else None


@contextmanager
def session() -> Iterator[duckdb.DuckDBPyConnection]:
    """In-memory DuckDB connection with the spatial extension loaded.

    Use as ``with duck.session() as con:`` — the connection (and any temp
    tables / registrations on it) is closed when the block exits.
    """
    con = duckdb.connect()
    ext = _spatial_extension_path()
    loaded = False
    if ext is not None:
        try:
            con.load_extension(ext)
            loaded = True
        except duckdb.Error as e:
            # Wheel built for a different duckdb version — fall back below.
            log.warning("spatial extension wheel unusable (%s); installing from repo", e)
    if not loaded:
        # No usable wheel — the standard extension repository (needs network
        # once; cached under ~/.duckdb afterwards).
        con.install_extension("spatial")
        con.load_extension("spatial")
    try:
        yield con
    finally:
        con.close()


# ── Sharded-parquet registration ───────────────────────────────────────────


@dataclass(frozen=True)
class ParcelShard:
    """One normalized parcel shard, in canonical iteration order."""

    seq: int  # position in the canonical shard order (0-based)
    source_id: str
    label: str  # "<source_id>__<stem>" — matches iter_state_parcel_shards
    path: Path
    columns: tuple[str, ...]  # parquet schema column names (footer-only read)


def _normalized_root() -> Path:
    # Deferred import — picks up `monkeypatch.setattr(preprocess,
    # "NORMALIZED_ROOT", ...)` from tests, matching compose_helpers.
    from . import NORMALIZED_ROOT

    return NORMALIZED_ROOT


def _parcel_normalizers():
    # Deferred resolution so tests that patch `preprocess.base.all_normalizers`
    # are honored here without also patching this module.
    from . import base

    return [n for n in base.all_normalizers() if "parcel" in n.canonical_types]


def parcel_shards(*, normalized_root: Path | None = None) -> list[ParcelShard]:
    """Enumerate every normalized parcel shard in canonical order.

    Order is the contract: parcel normalizers in registry order, then
    sorted ``*.parquet`` filenames — identical to what
    `iter_state_parcel_shards` yields. Unreadable shards and shards
    missing ``state_fips`` are skipped with a warning, like the
    streaming iterator they mirror.
    """
    root = normalized_root if normalized_root is not None else _normalized_root()
    parcel_basename = OUTPUT_BASENAMES.get("parcel", "parcel")
    shards: list[ParcelShard] = []
    for n in _parcel_normalizers():
        src_dir = root / n.source_id / parcel_basename
        if not src_dir.is_dir():
            continue
        for shard_path in sorted(src_dir.glob("*.parquet")):
            try:
                columns = tuple(pq.read_schema(shard_path).names)
            except Exception as e:  # noqa: BLE001 — one bad shard mustn't abort
                log.warning("skipping unreadable shard %s: %s", shard_path, e)
                continue
            if "state_fips" not in columns:
                log.warning("shard %s missing contractual state_fips column; skipping", shard_path)
                continue
            shards.append(
                ParcelShard(
                    seq=len(shards),
                    source_id=n.source_id,
                    label=f"{n.source_id}__{shard_path.stem}",
                    path=shard_path,
                    columns=columns,
                )
            )
    return shards


def sql_str(value: str) -> str:
    """Quote a string as a SQL literal (single quotes doubled)."""
    return "'" + value.replace("'", "''") + "'"


def register_state_parcels(
    con: duckdb.DuckDBPyConnection,
    state_fips: str,
    *,
    normalized_root: Path | None = None,
    view: str = PARCELS_VIEW,
) -> list[ParcelShard]:
    """Create/replace a view over every normalized parcel shard for a state.

    The view unions all shards by column name (a column missing from one
    shard reads as NULL for its rows), filters to ``state_fips``, and
    carries ``__shard_seq`` / ``__shard_label`` / ``__row_idx`` so queries
    can order rows by the canonical shard iteration. GeoParquet geometry
    columns surface as typed ``GEOMETRY`` (the spatial extension reads the
    GeoParquet metadata) — no WKB decoding needed in stage SQL.

    Returns the registered shard list; ``[]`` means no shards exist and
    no view was created. Per-shard schemas are on ``ParcelShard.columns``
    so stages can apply per-shard semantics (e.g. "column present in the
    matched shard").
    """
    shards = parcel_shards(normalized_root=normalized_root)
    if not shards:
        return []
    paths_sql = ", ".join(sql_str(str(s.path)) for s in shards)
    shard_map_sql = ", ".join(
        f"({sql_str(str(s.path))}, {s.seq}, {sql_str(s.label)})" for s in shards
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW "{view}" AS
        SELECT p.* EXCLUDE (filename, file_row_number),
               m.__shard_seq,
               m.__shard_label,
               p.file_row_number AS __row_idx
        FROM read_parquet([{paths_sql}],
                          union_by_name=true, filename=true, file_row_number=true) p
        JOIN (VALUES {shard_map_sql}) AS m(__path, __shard_seq, __shard_label)
          ON p.filename = m.__path
        WHERE p.state_fips = {sql_str(state_fips)}
        """
    )
    return shards
