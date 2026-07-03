"""USPVDB normalizer — eia_id recovery (audit M-f / #210).

The EIA plant code is the cross-feed key the solar dedup (MACRO-3) matches
on. USPVDB v4.0 (2026-04) renamed the shapefile field ``p_eia_id`` →
``eia_id``; the normalizer reads the v4 name first and falls back to the
pre-v4 spelling, emitting a first-class ``eia_id`` column whose strings
match eia_860's ``facility_id`` code space ("2953", never "2953.0").
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from preprocess.normalizers.uspvdb import UspvdbNormalizer, _eia_id_str
from shapely.geometry import Polygon

SQUARE = Polygon([(-92.0, 34.0), (-91.99, 34.0), (-91.99, 34.01), (-92.0, 34.01)])


def _write_shapefile(raw_dir: Path, columns: dict) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame({**columns, "geometry": [SQUARE] * len(next(iter(columns.values())))})
    gdf = gdf.set_crs("EPSG:4326")
    gdf.to_file(raw_dir / "uspvdb_test.shp")


def _normalize(tmp_path: Path, columns: dict) -> gpd.GeoDataFrame:
    raw, out = tmp_path / "raw", tmp_path / "out"
    _write_shapefile(raw, columns)
    result = UspvdbNormalizer().normalize(raw, out)
    assert result.canonical_rows == len(next(iter(columns.values())))
    return gpd.read_parquet(out / "solar_facilities.parquet")


def test_v4_eia_id_lands_as_first_class_column(tmp_path: Path) -> None:
    out = _normalize(
        tmp_path,
        {
            "case_id": [400011, 400012],
            "eia_id": [2953, 67406],  # v4 field name, int64
            "p_name": ["Carpenter", "Happy Solar"],
            "p_state": ["AR", "AR"],
            "p_county": ["Jefferson", "Jefferson"],
            "p_cap_ac": [12.5, 20.0],
            "p_cap_dc": [16.0, 25.0],
            "p_year": [2019, 2021],
        },
    )
    # Strings in eia_860 facility_id code space — the MACRO-3 dedup key.
    assert out["eia_id"].tolist() == ["2953", "67406"]
    assert out["capacity_mw"].tolist() == [12.5, 20.0]  # E7: AC preferred


def test_pre_v4_p_eia_id_fallback(tmp_path: Path) -> None:
    out = _normalize(
        tmp_path,
        {
            "case_id": [400011],
            "p_eia_id": [2953],  # pre-v4 field name
            "p_name": ["Carpenter"],
            "p_state": ["AR"],
            "p_county": ["Jefferson"],
            "p_cap_ac": [12.5],
            "p_cap_dc": [16.0],
            "p_year": [2019],
        },
    )
    assert out["eia_id"].tolist() == ["2953"]


def test_missing_eia_id_is_blank_not_crash(tmp_path: Path) -> None:
    out = _normalize(
        tmp_path,
        {
            "case_id": [400011],
            "p_name": ["No Key Farm"],
            "p_state": ["AR"],
            "p_county": ["Jefferson"],
            "p_cap_ac": [5.0],
            "p_cap_dc": [6.0],
            "p_year": [2020],
        },
    )
    assert out["eia_id"].tolist() == [""]


def test_eia_id_str_strips_integral_float():
    """A nullable column arrives float — '2953.0' must still key as '2953'."""
    assert _eia_id_str(2953) == "2953"
    assert _eia_id_str(2953.0) == "2953"
    assert _eia_id_str(None) == ""
    assert _eia_id_str(float("nan")) == ""
    assert _eia_id_str(" 2953 ") == "2953"
