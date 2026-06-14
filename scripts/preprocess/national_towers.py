"""national_towers.py — the precomputed combined tower file (PRD #163 / #166).

One ``composite/towers.json`` unioning every composed state's
``towers.parquet`` slim columns, so the map app fetches a single JSON
and turns it into the tower FeatureCollection directly — instead of
booting the ~6 MB DuckDB-WASM engine and running a per-state
``UNION ALL`` on the *tower critical path* (~1.0 s before the first
dot). DuckDB-WASM still lazy-inits on the client for the first parcel
click / owner search; it is simply no longer touched to draw towers.

The fields mirror the frontend ``TowerRow`` and the aliases today's
client tower query emits, so the loader can feed rows straight into the
existing pure ``rowsToFeatureCollection``:

    asr_number → asr, parcel_owner → owner, height_m, state,
    is_active → active, lat, lon

The same SQL the client runs is used here (same casts, same
``lat/lon IS NOT NULL`` drop), so the combined file is equivalent to the
per-state union the frontend produces today (pinned by
tests/test_national_towers.py).

**Baked ``cid``** — each row also carries the owner's cross-state Lead
key (``display_cluster_id``), precomputed with the canonical
``cluster.normalize_owner_name`` → ``cross_state_owner_key`` recipe (the
same hash the client's ``ownerNameToClusterId`` produces, pinned by the
``owner-cluster`` parity test). Measured during #166: hashing 80,814
owner names client-side costs ~227 ms — the single largest CPU cost on
the new tower load (vs ~53 ms to JSON.parse the file), so it is baked
here and the loader prefers a present ``cid``. ``cid`` is additive +
optional: a stale file without it still loads (the client recomputes),
so producer/consumer can deploy independently (owners-index posture).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from . import COMPOSITE_ROOT, duck
from .cluster import cross_state_owner_key, normalize_owner_name

log = logging.getLogger("preprocess.national_towers")

TOWERS_FILENAME = "towers.json"
# Per-state source the union reads (the structures-first map's tower source).
TOWERS_PARQUET = "towers.parquet"
# towers.json shape version — bump when the row schema changes so the app
# can default missing fields instead of mis-reading an old file.
TOWERS_SCHEMA_VERSION = 1


def _state_has_towers(state_dir: Path) -> bool:
    """A composed state contributes iff it has a towers.parquet on disk."""
    return (state_dir / TOWERS_PARQUET).exists()


def _write_json_atomic(payload: dict, path: Path) -> None:
    """Temp-file + ``os.replace`` write so a reader never sees a half file
    (the repo-wide atomic-JSON convention). Compact separators keep the big
    tower array small on the wire — this file is machine-read only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            json.dump(payload, f, sort_keys=True, separators=(",", ":"))
        Path(tmp_name).replace(path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def build_national_towers(composite_root: Path | None = None) -> dict:
    """Union every composed state's ``towers.parquet`` into ``composite/towers.json``.

    Reads the slim tower columns over the ``duck.py`` engine (consistent
    with the DuckDB-as-heavy-lift posture, PRD #135), aliasing them to the
    frontend ``TowerRow`` field names and dropping coordinate-less rows —
    the exact projection the client's ``loadTowerPoints`` query runs today,
    so the output equals the per-state union it replaces. States without a
    ``towers.parquet`` are skipped (the file degrades to fewer towers, never
    an empty map). Returns ``{path, count, states}``.
    """
    from .app_assets import iter_composed_states

    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    fips_list = iter_composed_states(root, predicate=_state_has_towers)

    towers: list[dict] = []
    if fips_list:
        paths = [root / fips / TOWERS_PARQUET for fips in fips_list]
        paths_sql = ", ".join(duck.sql_str(str(p)) for p in paths)
        with duck.session() as con:
            rows = con.execute(
                f"""
                SELECT CAST(asr_number AS VARCHAR) AS asr,
                       CAST(parcel_owner AS VARCHAR) AS owner,
                       CAST(height_m AS DOUBLE) AS height_m,
                       CAST(state AS VARCHAR) AS state,
                       CAST(is_active AS BOOLEAN) AS active,
                       CAST(lat AS DOUBLE) AS lat,
                       CAST(lon AS DOUBLE) AS lon
                FROM read_parquet([{paths_sql}], union_by_name=true)
                WHERE lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY state, asr, lat, lon
                """
            ).fetchall()
        for asr, owner, height_m, state, active, lat, lon in rows:
            towers.append(
                {
                    "asr": asr,
                    "owner": owner,
                    # Baked Lead key — same recipe (and result) as the client's
                    # ownerNameToClusterId; '' for an un-clusterable landowner.
                    "cid": cross_state_owner_key(normalize_owner_name(owner)),
                    "height_m": height_m,
                    "state": state,
                    "active": active,
                    "lat": lat,
                    "lon": lon,
                }
            )

    payload = {
        "schema_version": TOWERS_SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "count": len(towers),
        "states": fips_list,
        "towers": towers,
    }
    path = root / TOWERS_FILENAME
    _write_json_atomic(payload, path)
    log.info("wrote %s (%d towers across %d state(s))", path, len(towers), len(fips_list))
    return {"path": str(path), "count": len(towers), "states": fips_list}


def run_national_towers(composite_root: Path | None = None) -> dict:
    """``--app-assets`` step: build the combined ``composite/towers.json``."""
    return build_national_towers(composite_root=composite_root)
