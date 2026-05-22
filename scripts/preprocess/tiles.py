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


def _stream_features(parquet_path: Path, stdin) -> int:
    """Stream GeoJSON-seq features from a parcels parquet into a pipe.

    Decodes the primary `geometry` column (full-resolution WKB) directly
    — never `geom_simplified`, since tippecanoe does its own per-zoom
    simplification and double-simplifying degrades quality.
    """
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


def build_state_tiles(
    state_fips: str,
    *,
    composite_root: Path | None = None,
    min_zoom: int = MIN_ZOOM,
    max_zoom: int = MAX_ZOOM,
) -> Path:
    """Build `composite/<fips>/parcels.pmtiles` from `parcels.parquet`.

    Writes to a `.partial` file and renames on success (atomic). Raises
    on a missing parquet, a missing tippecanoe, or a non-zero tippecanoe
    exit — the caller decides whether that is fatal.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    state_dir = root / state_fips
    parquet_path = state_dir / "parcels.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"no parcels.parquet for state {state_fips}: {parquet_path}")
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
    log.info("tippecanoe → %s", out_path)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        written = _stream_features(parquet_path, proc.stdin)
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
    """FIPS of every directory that has a parcels.parquet, app-excluded ones dropped."""
    from .app_assets import EXCLUDED_FIPS

    if not composite_root.exists():
        return []
    return sorted(
        d.name
        for d in composite_root.iterdir()
        if d.is_dir() and d.name not in EXCLUDED_FIPS and (d / "parcels.parquet").exists()
    )


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
