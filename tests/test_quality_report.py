"""Tests for the QualityReport dataclasses + codec.

Covers:

- The builder (``quality_report``) produces a typed object whose shape
  matches the on-disk format.
- The codec round-trips: ``QualityReport.from_dict(qr.to_dict()) == qr``.
- The "table not produced" shape (``df=None``) is preserved through
  the round trip.
- Backwards-compat: legacy on-disk reports with unknown keys at the
  root (e.g. the ``states_covered`` key state_parcels used to stamp
  there) parse into ``extras``.
- Extras round-trip via the new on-disk format.
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd
from preprocess.base import (
    ColumnStats,
    QualityReport,
    TableStats,
    quality_report,
    write_quality_report,
)
from shapely.geometry import Polygon


def _square(i: int) -> Polygon:
    return Polygon([(i, i), (i + 1, i), (i + 1, i + 1), (i, i + 1)])


# ── builder produces a typed object ──────────────────────────────────────


def test_builder_returns_typed_quality_report():
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", "y", "z"]})
    qr = quality_report("test_source", {"main": df})
    assert isinstance(qr, QualityReport)
    assert qr.source_id == "test_source"
    assert qr.generated_at  # ISO timestamp populated
    assert "main" in qr.tables
    main = qr.tables["main"]
    assert isinstance(main, TableStats)
    assert main.rows == 3
    assert set(main.columns.keys()) == {"a", "b"}
    assert isinstance(main.columns["a"], ColumnStats)
    # one of three values is null -> null_rate ≈ 0.333
    assert main.columns["a"].null_rate is not None
    assert 0.30 < main.columns["a"].null_rate < 0.35
    assert main.columns["b"].null_rate == 0.0


def test_builder_records_geometry_validity_for_geodataframe():
    gdf = gpd.GeoDataFrame(
        {"x": [1, 2]},
        geometry=[_square(0), _square(10)],
        crs="EPSG:4326",
    )
    qr = quality_report("test_source", {"geo": gdf})
    geo = qr.tables["geo"]
    assert geo.geometry_validity_pct == 100.0


def test_builder_none_df_records_not_produced():
    qr = quality_report("test_source", {"raw": None})
    raw = qr.tables["raw"]
    assert raw.rows == 0
    assert raw.note == "table not produced"
    assert raw.columns == {}
    assert raw.geometry_validity_pct is None


def test_builder_passes_warnings_through():
    qr = quality_report("test_source", {}, warnings=["one warning", "another"])
    assert qr.warnings == ["one warning", "another"]


# ── codec round-trip ─────────────────────────────────────────────────────


def test_codec_round_trips_full_report():
    """A populated report survives to_dict → from_dict unchanged."""
    qr = QualityReport(
        source_id="test_source",
        generated_at="2026-05-25T00:00:00Z",
        tables={
            "main": TableStats(
                rows=42,
                columns={
                    "a": ColumnStats(null_rate=0.0, dtype="int64"),
                    "b": ColumnStats(null_rate=0.5, dtype="object"),
                },
                geometry_validity_pct=99.5,
            ),
            "raw": TableStats(rows=0, note="table not produced"),
        },
        warnings=["one"],
        extras={"states_covered": ["05", "30"]},
    )
    round_tripped = QualityReport.from_dict(qr.to_dict())
    assert round_tripped == qr


def test_codec_preserves_not_produced_shape_on_disk():
    """The "not produced" entry should serialize as just {rows, note} —
    no empty columns dict, no None geometry_validity_pct."""
    qr = QualityReport(
        source_id="s",
        generated_at="t",
        tables={"raw": TableStats(rows=0, note="table not produced")},
    )
    on_disk = qr.to_dict()["tables"]["raw"]
    assert on_disk == {"rows": 0, "note": "table not produced"}


# ── backwards-compat: legacy on-disk reports parse ──────────────────────


def test_from_dict_lifts_unknown_root_keys_into_extras():
    """Reports written before this PR have ``states_covered`` at the
    root. The codec must lift those into ``extras`` so consumers can
    keep using a single typed access pattern."""
    legacy = {
        "source_id": "test_source",
        "generated_at": "2026-05-18T00:00:00Z",
        "tables": {"parcels": {"rows": 100, "columns": {}, "geometry_validity_pct": 100.0}},
        "warnings": [],
        # Legacy root-level extras
        "states_covered": ["05", "30"],
        "some_other_old_key": {"a": 1},
    }
    qr = QualityReport.from_dict(legacy)
    assert qr.extras["states_covered"] == ["05", "30"]
    assert qr.extras["some_other_old_key"] == {"a": 1}
    assert "parcels" in qr.tables
    assert qr.tables["parcels"].rows == 100


def test_from_dict_tolerates_missing_optional_fields():
    """Minimal legacy reports (pre-warnings era) must still parse."""
    minimal = {"source_id": "s", "generated_at": "t", "tables": {}}
    qr = QualityReport.from_dict(minimal)
    assert qr.source_id == "s"
    assert qr.warnings == []
    assert qr.extras == {}
    assert qr.tables == {}


# ── on-disk write produces valid JSON ───────────────────────────────────


def test_write_quality_report_emits_valid_json(tmp_path):
    qr = QualityReport(
        source_id="test_source",
        generated_at="2026-05-25T00:00:00Z",
        tables={"raw": TableStats(rows=5)},
        extras={"states_covered": ["05"]},
    )
    path = write_quality_report(tmp_path, qr)
    assert path.name == "quality_report.json"
    parsed = json.loads(path.read_text())
    assert parsed["source_id"] == "test_source"
    assert parsed["tables"]["raw"]["rows"] == 5
    assert parsed["extras"]["states_covered"] == ["05"]
    # Round-trip through from_dict matches the original.
    assert QualityReport.from_dict(parsed) == qr
