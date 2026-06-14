"""Tests for scripts/preprocess/tiles.py — the parcels.pmtiles builder.

The streaming logic is tested without tippecanoe (it writes GeoJSON-seq
to any file object); the full build is gated on tippecanoe being
installed (Phase B installs it).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import shapely
from preprocess.tiles import (
    TILE_ATTRIBUTES,
    _stream_features,
    build_state_tiles,
    tippecanoe_available,
)


def _make_parcels_parquet(path: Path, n: int = 10) -> None:
    """Write a tiny parcels.parquet fixture: n small polygons + attributes."""
    polys = [shapely.box(i, i, i + 0.01, i + 0.01) for i in range(n)]
    columns: dict[str, pa.Array] = {
        "geometry": pa.array([shapely.to_wkb(p) for p in polys], type=pa.binary()),
        "parcel_id": pa.array([f"P{i:04d}" for i in range(n)]),
        "owner_name": pa.array([f"OWNER {i}" for i in range(n)]),
        "owner_kind": pa.array(["llc"] * n),
        "acreage": pa.array([1.5 * i for i in range(n)]),
        "assessed_value": pa.array([10_000 * i for i in range(n)]),
        "land_use_desc": pa.array(["Vacant Land"] * n),
        "distress_tier": pa.array(["distressed"] * n),
        "in_oz": pa.array([i % 2 == 0 for i in range(n)]),
        "has_tower": pa.array([i % 3 == 0 for i in range(n)]),
        "has_solar": pa.array([False] * n),
        "has_billboard": pa.array([False] * n),
        "interestingness_score": pa.array([round(0.1 * i, 2) for i in range(n)]),
        # An extra column that must NOT leak into the tiles.
        "owner_name_norm": pa.array([f"owner {i}" for i in range(n)]),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(columns), path)


def test_tippecanoe_available_returns_bool() -> None:
    assert isinstance(tippecanoe_available(), bool)


def test_stream_features_emits_one_geojson_feature_per_row(tmp_path: Path) -> None:
    parquet = tmp_path / "parcels.parquet"
    _make_parcels_parquet(parquet, n=10)

    sink = io.BytesIO()
    written = _stream_features(parquet, sink)
    assert written == 10

    lines = sink.getvalue().decode("utf-8").splitlines()
    assert len(lines) == 10
    feats = [json.loads(line) for line in lines]
    for f in feats:
        assert f["type"] == "Feature"
        assert f["geometry"]["type"] == "Polygon"
        # Only the baked attributes are present — no extras leak.
        assert set(f["properties"]) <= set(TILE_ATTRIBUTES)
        assert "owner_name_norm" not in f["properties"]
    # The baked attributes carry through with the right values.
    assert feats[0]["properties"]["parcel_id"] == "P0000"
    assert feats[3]["properties"]["has_tower"] is True
    assert feats[0]["properties"]["distress_tier"] == "distressed"


def test_build_state_tiles_missing_parquet_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_state_tiles("99", composite_root=tmp_path)


@pytest.mark.skipif(not tippecanoe_available(), reason="tippecanoe not installed")
def test_build_state_tiles_produces_valid_pmtiles(tmp_path: Path) -> None:
    from pmtiles.reader import MmapSource, Reader

    _make_parcels_parquet(tmp_path / "99" / "parcels.parquet", n=10)

    out = build_state_tiles("99", composite_root=tmp_path)

    assert out == tmp_path / "99" / "parcels.pmtiles"
    assert out.exists()
    # A PMTiles v3 file begins with the ASCII magic "PMTiles".
    assert out.read_bytes()[:7] == b"PMTiles"
    # The atomic-write temp file is cleaned up.
    assert not (tmp_path / "99" / ".parcels.tmp.pmtiles").exists()

    # The header reflects the tippecanoe flags: single-zoom z14 (min == max
    # == the appearance zoom Z_on; the z6–13 tiles are no longer generated
    # since the frontend gates parcel rendering at Z_on — PRD #163 / #167),
    # MVT, one vector layer named "parcels".
    with out.open("rb") as f:
        reader = Reader(MmapSource(f))
        header = reader.header()
        assert header["min_zoom"] == 14
        assert header["max_zoom"] == 14
        assert str(header["tile_type"]).endswith("MVT")
        layers = [layer["id"] for layer in reader.metadata().get("vector_layers", [])]
        assert layers == ["parcels"]
