"""Tests for scripts/preprocess/facets.py — the DuckDB-WASM inputs."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from preprocess.facets import attr_columns, build_facets


def _make_parcels_parquet(path: Path, n: int = 12) -> None:
    """A tiny parcels.parquet fixture — attribute columns + the columns
    that facets.py must drop (geometry / extras / _-prefixed)."""
    scores = [round(0.07 * i, 3) for i in range(n)]
    random.Random(1).shuffle(scores)  # out of order — so the sort is testable
    cols: dict[str, pa.Array] = {
        "parcel_id": pa.array([f"P{i:03d}" for i in range(n)]),
        "owner_kind": pa.array([("llc", "trust", "individual")[i % 3] for i in range(n)]),
        "distress_tier": pa.array([("distressed", "at-risk")[i % 2] for i in range(n)]),
        "land_use_desc": pa.array(["Vacant Land"] * n),
        "county_fips": pa.array(["05001"] * n),
        "assessed_value": pa.array([1000.0 * i for i in range(n)]),
        "acreage": pa.array([1.5 * i for i in range(n)]),
        "interestingness_score": pa.array(scores),
        "owner_cluster_size": pa.array([1 + i for i in range(n)]),
        "owner_name_norm": pa.array([f"owner {i}" for i in range(n)]),
        "geom_bbox": pa.array(["[-1,-1,1,1]"] * n),
        "distress_overlays": pa.array(['["qct"]'] * n),
        "interestingness_components": pa.array(['{"infrastructure":0.4}'] * n),
        # ── columns facets.py must drop ──
        "geometry": pa.array([b"wkb"] * n, type=pa.binary()),
        "geom_centroid": pa.array([b"wkb"] * n, type=pa.binary()),
        "geom_simplified": pa.array([b"wkb"] * n, type=pa.binary()),
        "extras": pa.array(["{}"] * n),
        "_source": pa.array(["ar_parcels"] * n),
        "_schema_version": pa.array([1] * n),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(cols), path)


def test_attr_columns_drops_geometry_and_internals() -> None:
    cols = [
        "parcel_id",
        "geometry",
        "geom_centroid",
        "geom_bbox",
        "extras",
        "_source",
        "owner_kind",
    ]
    assert attr_columns(cols) == ["parcel_id", "geom_bbox", "owner_kind"]


def test_build_facets_missing_parquet_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_facets("99", composite_root=tmp_path)


def test_build_facets_slim_parquet_drops_geometry(tmp_path: Path) -> None:
    _make_parcels_parquet(tmp_path / "99" / "parcels.parquet", n=12)
    build_facets("99", composite_root=tmp_path)

    attr = pq.read_table(tmp_path / "99" / "parcels_attr.parquet")
    names = set(attr.column_names)
    # Geometry + internal columns are gone.
    for dropped in ("geometry", "geom_centroid", "geom_simplified", "extras", "_source"):
        assert dropped not in names
    # Attribute columns — incl. geom_bbox + the nested JSON strings — survive.
    for kept in ("parcel_id", "geom_bbox", "distress_overlays", "interestingness_components"):
        assert kept in names


def test_build_facets_slim_parquet_sorted_by_score(tmp_path: Path) -> None:
    _make_parcels_parquet(tmp_path / "99" / "parcels.parquet", n=12)
    build_facets("99", composite_root=tmp_path)

    scores = (
        pq.read_table(tmp_path / "99" / "parcels_attr.parquet", columns=["interestingness_score"])
        .column("interestingness_score")
        .to_pylist()
    )
    assert scores == sorted(scores, reverse=True)


def test_build_facets_json_shape(tmp_path: Path) -> None:
    _make_parcels_parquet(tmp_path / "99" / "parcels.parquet", n=12)
    build_facets("99", composite_root=tmp_path)

    facets = json.loads((tmp_path / "99" / "facets.json").read_text())
    assert facets["total"] == 12

    owner_kinds = facets["categorical"]["owner_kind"]
    assert {p["value"] for p in owner_kinds} == {"llc", "trust", "individual"}
    assert sum(p["count"] for p in owner_kinds) == 12

    av = facets["numeric"]["assessed_value"]
    assert av["min"] == 0.0
    assert av["max"] == 11000.0
