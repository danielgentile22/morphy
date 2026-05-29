"""parcels.parquet → parcels.pmtiles via tippecanoe.

The parcel layer is too large for GeoJSON (AR is 2.1M polygons / a
multi-GB GeoJSON — ADR-052). The map app renders parcels as WebGL vector
tiles instead; this builds the PMTiles file each state's app reads.

The parquet is streamed through tippecanoe with fixed-size record
batches (independent of the file's physical row-group layout), so peak
memory stays bounded regardless of state size. Only the geometry column
plus a small display/styling attribute set are read — never the full
55-column row.

CLI (wired into scripts/preprocess.py):
    python scripts/preprocess.py --tiles                 # all composed states
    python scripts/preprocess.py --tiles --state 05      # one state
A normal full run also builds tiles unless --skip-tiles is passed.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

import pyarrow.parquet as pq
import shapely

from . import COMPOSITE_ROOT

log = logging.getLogger("preprocess.tiles")

# The display + styling attribute subset baked into each tile feature.
# Enough for a useful click panel before DuckDB (Phase C upgrades the
# panel to a full-row fetch). has_billboard is always false for AR/MT
# (billboards are FL-only) — kept for FL / forward compatibility.
TILE_ATTRIBUTES: tuple[str, ...] = (
    "parcel_id",
    "owner_name",
    "owner_kind",
    "acreage",
    "assessed_value",
    "land_use_desc",
    "distress_tier",
    "in_oz",
    "has_tower",
    "has_solar",
    "has_billboard",
    "interestingness_score",
)

GEOMETRY_COLUMN = "geometry"
BATCH_SIZE = 50_000
MIN_ZOOM = 6
MAX_ZOOM = 14


def tippecanoe_available() -> bool:
    """True if the `tippecanoe` binary is on PATH."""
    return shutil.which("tippecanoe") is not None


def _resolve_parcels_source(state_dir: Path) -> tuple[list[Path], bool]:
    """Locate the parcel parquet(s) for tile building.

    Returns (paths, is_sharded). Either a single-element list (legacy
    layout) or a list of per-shard files (chunked compose, ADR-051).
    """
    from .app_assets import resolve_parcel_paths

    return resolve_parcel_paths(state_dir)


def _stream_features_from_path(parquet_path: Path, stdin) -> int:
    """Stream GeoJSON-seq features from one parquet file into a pipe."""
    pf = pq.ParquetFile(parquet_path)
    available = set(pf.schema_arrow.names)
    if GEOMETRY_COLUMN not in available:
        raise ValueError(f"{parquet_path} has no '{GEOMETRY_COLUMN}' column")
    attr_cols = [c for c in TILE_ATTRIBUTES if c in available]
    columns = [GEOMETRY_COLUMN, *attr_cols]

    written = 0
    for batch in pf.iter_batches(batch_size=BATCH_SIZE, columns=columns):
        wkb = batch.column(GEOMETRY_COLUMN).to_numpy(zero_copy_only=False)
        geoms = shapely.from_wkb(wkb)
        geojson_geoms = shapely.to_geojson(geoms)  # vectorised → array of JSON strings
        attrs = {c: batch.column(c).to_pylist() for c in attr_cols}
        for i in range(len(geoms)):
            if geoms[i] is None or geojson_geoms[i] is None:
                continue
            props = {c: attrs[c][i] for c in attr_cols}
            line = (
                '{"type":"Feature","geometry":'
                + str(geojson_geoms[i])
                + ',"properties":'
                + json.dumps(props, default=str)
                + "}\n"
            )
            stdin.write(line.encode("utf-8"))
            written += 1
    return written


def _stream_features(parquet_paths, stdin) -> int:
    """Stream features from one or many parquet files into a pipe.

    Accepts either a single `Path` (legacy single-file callers, including
    the test suite) or a list of `Path` (chunked sharded layout).

    Decodes the primary `geometry` column (full-resolution WKB) directly
    — never `geom_simplified`, since tippecanoe does its own per-zoom
    simplification and double-simplifying degrades quality.
    """
    if isinstance(parquet_paths, Path):
        parquet_paths = [parquet_paths]
    written = 0
    for p in parquet_paths:
        written += _stream_features_from_path(p, stdin)
    return written


def build_state_tiles(
    state_fips: str,
    *,
    composite_root: Path | None = None,
    min_zoom: int = MIN_ZOOM,
    max_zoom: int = MAX_ZOOM,
) -> Path:
    """Build `composite/<fips>/parcels.pmtiles` from the parcel parquet(s).

    Reads from either `parcels.parquet` (legacy single-file) or a
    `parcels/` shard directory (chunked compose, ADR-051). Writes to a
    `.partial` file and renames on success (atomic). Raises on a missing
    source, a missing tippecanoe, or a non-zero tippecanoe exit — the
    caller decides whether that is fatal.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    state_dir = root / state_fips
    parquet_paths, is_sharded = _resolve_parcels_source(state_dir)
    if not tippecanoe_available():
        raise RuntimeError("tippecanoe is not installed — run `brew install tippecanoe`")

    out_path = state_dir / "parcels.pmtiles"
    # tippecanoe selects its output format from the file extension, so the
    # temp file must also end in .pmtiles — otherwise it writes MBTiles.
    tmp_path = state_dir / ".parcels.tmp.pmtiles"
    cmd = [
        "tippecanoe",
        "-o",
        str(tmp_path),
        "-l",
        "parcels",
        f"-Z{min_zoom}",
        f"-z{max_zoom}",
        "--drop-densest-as-needed",
        "--simplification=10",
        "--force",
    ]
    log.info(
        "tippecanoe → %s (%d %s)",
        out_path,
        len(parquet_paths),
        "shards" if is_sharded else "file",
    )
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        written = _stream_features(parquet_paths, proc.stdin)
        proc.stdin.close()
    except Exception:
        proc.kill()
        proc.wait()
        tmp_path.unlink(missing_ok=True)
        raise
    rc = proc.wait()
    if rc != 0:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"tippecanoe exited {rc} building tiles for state {state_fips}")
    tmp_path.replace(out_path)
    log.info("wrote %s (%d features)", out_path, written)
    return out_path


def _composed_states(composite_root: Path) -> list[str]:
    """FIPS of every directory that has parcel parquet(s), app-excluded ones dropped."""
    from .app_assets import iter_composed_states, state_has_parcels

    return iter_composed_states(composite_root, predicate=state_has_parcels)


def run_tiles(state_fips: str | None = None, *, composite_root: Path | None = None) -> dict:
    """Build PMTiles for one state or every composed state.

    A missing tippecanoe is reported (not raised) so a normal preprocess
    run can continue without it; a per-state failure is logged and the
    remaining states still run.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    if not tippecanoe_available():
        msg = "tippecanoe not installed — skipping tile generation (brew install tippecanoe)"
        log.warning(msg)
        return {"ok": [], "failed": [], "skipped": True, "message": msg}

    states = [state_fips] if state_fips else _composed_states(root)
    ok: list[str] = []
    failed: list[str] = []
    for fips in states:
        try:
            build_state_tiles(fips, composite_root=root)
            ok.append(fips)
        except Exception as exc:  # noqa: BLE001 — one state's failure must not abort the rest
            log.error("tile generation failed for state %s: %s", fips, exc)
            failed.append(fips)
    return {"ok": ok, "failed": failed, "skipped": False, "message": ""}
