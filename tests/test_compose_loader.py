"""Tests for the Composer's per-source loading seam.

Covers:

- ``Normalizer.load_state_data`` default implementation (single-file layout,
  per-county-shard layout, missing source, missing state, contract
  enforcement when state_fips is absent).
- ``compose._load_state_data`` concatenation across multiple sources
  producing the same canonical type.
- The county_score state_fips backfill in usda_persistent_poverty and
  arc_distressed — they must now honor the hard state_fips contract.

The default loader reads from ``NORMALIZED_ROOT``, which is a module-level
constant in ``preprocess/__init__.py``. Tests monkey-patch the module
attribute (and re-import the indirection inside the loader) to point at a
temp directory.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import preprocess
import pytest
from preprocess.base import (
    SPATIAL_TYPES,  # noqa: F401 — imported to make the contract visible to readers
    Normalizer,
    NormalizeResult,
)
from shapely.geometry import Point


@pytest.fixture
def fake_normalized_root(tmp_path: Path, monkeypatch):
    """Point NORMALIZED_ROOT at a temp directory for the duration of one test.

    Patches the module attribute on the ``preprocess`` package so that the
    local-import inside ``Normalizer.load_state_data`` picks it up.
    """
    root = tmp_path / "normalized"
    root.mkdir()
    monkeypatch.setattr(preprocess, "NORMALIZED_ROOT", root)
    return root


# ── Small in-process Normalizer subclasses for testing the seam ──────────


class _TowerStubNormalizer(Normalizer):
    """Single-file spatial layout: normalized/<id>/towers.parquet."""

    source_id = "stub_towers"
    canonical_types = ["tower"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:  # pragma: no cover
        raise NotImplementedError("not exercised by these tests")


class _ParcelStubNormalizer(Normalizer):
    """Per-shard spatial layout: normalized/<id>/parcels/<county>.parquet."""

    source_id = "stub_parcels"
    canonical_types = ["parcel"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:  # pragma: no cover
        raise NotImplementedError("not exercised by these tests")


class _ScoreStubNormalizer(Normalizer):
    """Single-file tabular layout: normalized/<id>/county_scores.parquet."""

    source_id = "stub_scores"
    canonical_types = ["county_score"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:  # pragma: no cover
        raise NotImplementedError("not exercised by these tests")


def _write_tower_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(path)


def _write_scores_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path)


# ── default load_state_data: single-file spatial ────────────────────────


def test_default_loader_single_file_spatial_filters_by_state(fake_normalized_root):
    src = fake_normalized_root / "stub_towers"
    _write_tower_parquet(
        src / "towers.parquet",
        [
            {"name": "AR_tower_1", "state_fips": "05", "geometry": Point(-92.5, 35.0)},
            {"name": "AR_tower_2", "state_fips": "05", "geometry": Point(-92.7, 35.1)},
            {"name": "MT_tower",   "state_fips": "30", "geometry": Point(-110.0, 47.0)},
        ],
    )
    out = _TowerStubNormalizer().load_state_data("05")
    assert set(out.keys()) == {"tower"}
    assert len(out["tower"]) == 2
    assert isinstance(out["tower"], gpd.GeoDataFrame)
    assert all(out["tower"]["state_fips"] == "05")


def test_default_loader_returns_empty_when_no_state_matches(fake_normalized_root):
    src = fake_normalized_root / "stub_towers"
    _write_tower_parquet(
        src / "towers.parquet",
        [{"name": "AR_tower", "state_fips": "05", "geometry": Point(-92.5, 35.0)}],
    )
    out = _TowerStubNormalizer().load_state_data("99")
    assert out == {}


# ── default load_state_data: per-shard spatial (the parcel layout) ──────


def test_default_loader_walks_per_shard_directory(fake_normalized_root):
    """Mirrors the ParcelNormalizer's normalized/<id>/parcels/<county>.parquet
    layout (ADR-050). Default loader must glob the subdirectory, not require
    a single-file path."""
    src = fake_normalized_root / "stub_parcels"
    _write_tower_parquet(
        src / "parcels" / "pulaski.parquet",
        [
            {"parcel_id": "P1", "state_fips": "05", "geometry": Point(-92.3, 34.7)},
            {"parcel_id": "P2", "state_fips": "05", "geometry": Point(-92.4, 34.8)},
        ],
    )
    _write_tower_parquet(
        src / "parcels" / "benton.parquet",
        [
            {"parcel_id": "P3", "state_fips": "05", "geometry": Point(-94.1, 36.3)},
            {"parcel_id": "P4", "state_fips": "30", "geometry": Point(-110.0, 47.0)},
        ],
    )
    out = _ParcelStubNormalizer().load_state_data("05")
    assert len(out["parcel"]) == 3
    assert isinstance(out["parcel"], gpd.GeoDataFrame)
    assert set(out["parcel"]["parcel_id"]) == {"P1", "P2", "P3"}


# ── default load_state_data: tabular ────────────────────────────────────


def test_default_loader_tabular_filters_by_state(fake_normalized_root):
    src = fake_normalized_root / "stub_scores"
    _write_scores_parquet(
        src / "county_scores.parquet",
        [
            {"county_fips": "05001", "state_fips": "05", "persistent_poverty": True},
            {"county_fips": "05003", "state_fips": "05", "persistent_poverty": False},
            {"county_fips": "30001", "state_fips": "30", "persistent_poverty": True},
        ],
    )
    out = _ScoreStubNormalizer().load_state_data("05")
    assert len(out["county_score"]) == 2
    assert isinstance(out["county_score"], pd.DataFrame)
    assert not isinstance(out["county_score"], gpd.GeoDataFrame)


# ── default load_state_data: nothing on disk ────────────────────────────


def test_default_loader_returns_empty_when_source_dir_missing(fake_normalized_root):
    """No normalized output yet for this source — return {} cleanly."""
    out = _TowerStubNormalizer().load_state_data("05")
    assert out == {}


def test_default_loader_returns_empty_when_basename_missing(fake_normalized_root):
    """Source dir exists but the canonical-type parquet isn't there."""
    (fake_normalized_root / "stub_towers").mkdir()
    # Put a stray file that isn't the towers parquet.
    (fake_normalized_root / "stub_towers" / "raw.parquet").write_bytes(b"\x00" * 8)
    out = _TowerStubNormalizer().load_state_data("05")
    assert out == {}


# ── default load_state_data: contract enforcement ───────────────────────


def test_default_loader_skips_parquet_lacking_state_fips(fake_normalized_root, caplog):
    """If a parquet on disk lacks the contractual state_fips column, the
    default loader logs a warning and skips it (returning {} for that type)
    rather than crashing or guessing — the override path is documented in
    the warning message."""
    src = fake_normalized_root / "stub_scores"
    _write_scores_parquet(
        src / "county_scores.parquet",
        [{"county_fips": "05001", "persistent_poverty": True}],
    )
    with caplog.at_level("WARNING", logger="preprocess"):
        out = _ScoreStubNormalizer().load_state_data("05")
    assert out == {}
    assert any("state_fips" in r.message for r in caplog.records)


# ── Composer's _load_state_data wrapper ─────────────────────────────────


def test_compose_loader_concats_across_sources(fake_normalized_root, monkeypatch):
    """_load_state_data must concat frames across multiple normalizers that
    produce the same canonical type — e.g. arc_distressed + usda_persistent_poverty
    both produce county_score."""
    from preprocess import compose
    from preprocess.base import ComposeContext

    # Two synthetic normalizers producing the same canonical type.
    class A(_ScoreStubNormalizer):
        source_id = "stub_scores_a"

    class B(_ScoreStubNormalizer):
        source_id = "stub_scores_b"

    _write_scores_parquet(
        fake_normalized_root / "stub_scores_a" / "county_scores.parquet",
        [
            {"county_fips": "05001", "state_fips": "05", "persistent_poverty": True},
            {"county_fips": "30001", "state_fips": "30", "persistent_poverty": True},
        ],
    )
    _write_scores_parquet(
        fake_normalized_root / "stub_scores_b" / "county_scores.parquet",
        [
            {"county_fips": "05003", "state_fips": "05", "tier": "distressed"},
        ],
    )

    monkeypatch.setattr(compose, "all_normalizers", lambda: [A(), B()])

    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    sources_used = compose._load_state_data(ctx)

    assert set(sources_used) == {"stub_scores_a", "stub_scores_b"}
    assert ctx.has("county_score")
    combined = ctx.get("county_score")
    assert len(combined) == 2  # one AR row from A, one AR row from B
    assert set(combined["county_fips"]) == {"05001", "05003"}


def test_compose_loader_skips_failing_normalizer(fake_normalized_root, monkeypatch, caplog):
    """If a normalizer's load_state_data raises, _load_state_data logs the
    error and continues — one broken source can't poison the whole compose."""
    from preprocess import compose
    from preprocess.base import ComposeContext

    class Broken(_TowerStubNormalizer):
        source_id = "stub_broken"

        def load_state_data(self, state_fips):
            raise RuntimeError("simulated failure")

    class Healthy(_TowerStubNormalizer):
        source_id = "stub_healthy"

    _write_tower_parquet(
        fake_normalized_root / "stub_healthy" / "towers.parquet",
        [{"name": "T", "state_fips": "05", "geometry": Point(-92.5, 35.0)}],
    )

    monkeypatch.setattr(compose, "all_normalizers", lambda: [Broken(), Healthy()])

    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    with caplog.at_level("WARNING", logger="preprocess.compose"):
        sources_used = compose._load_state_data(ctx)

    assert sources_used == ["stub_healthy"]
    assert ctx.has("tower")
    assert any("simulated failure" in r.message for r in caplog.records)


# ── USDA + ARC honor the new state_fips contract ────────────────────────


def test_usda_normalizer_adds_state_fips_column(tmp_path):
    """The USDA county_score backfill must populate state_fips from
    county_fips[:2] so the source honors the new hard contract."""
    from preprocess.normalizers.usda_persistent_poverty import (
        UsdaPersistentPovertyNormalizer,
    )

    csv = tmp_path / "raw" / "PovertyEstimates.csv"
    csv.parent.mkdir(parents=True)
    # Attribute needs to match the regex `persistent.poverty` (case-insensitive,
    # any single char in between) — "Persistent_Poverty_2020" qualifies.
    csv.write_text(
        "FIPStxt,Attribute,Value\n"
        "05001,Persistent_Poverty_2020,1\n"
        "30001,Persistent_Poverty_2020,0\n"
        "12001,Persistent_Poverty_2020,1\n"
    )

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = UsdaPersistentPovertyNormalizer().normalize(tmp_path / "raw", out_dir)

    scores = pd.read_parquet(out_dir / "county_scores.parquet")
    assert "state_fips" in scores.columns
    by_state = dict(zip(scores["county_fips"], scores["state_fips"], strict=True))
    assert by_state["05001"] == "05"
    assert by_state["30001"] == "30"
    assert by_state["12001"] == "12"
    assert res.canonical_rows == 3


def test_arc_normalizer_adds_state_fips_column(tmp_path):
    """Same contract: ARC's county_score output must include state_fips."""
    import openpyxl  # noqa: F401 — required for pandas .to_excel(engine='openpyxl')
    from preprocess.normalizers.arc_distressed import ArcDistressedNormalizer

    raw = tmp_path / "raw"
    raw.mkdir()
    xlsx = raw / "arc_economic_status_fy2025.xlsx"
    df = pd.DataFrame(
        [
            {"FIPS Code": "05001", "Economic Status Designation": "Distressed"},
            {"FIPS Code": "30001", "Economic Status Designation": "At-Risk"},
            {"FIPS Code": "12001", "Economic Status Designation": "Competitive"},
        ]
    )
    df.to_excel(xlsx, index=False, engine="openpyxl")

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    ArcDistressedNormalizer().normalize(raw, out_dir)

    scores = pd.read_parquet(out_dir / "county_scores.parquet")
    assert "state_fips" in scores.columns
    by_state = dict(zip(scores["county_fips"], scores["state_fips"], strict=True))
    assert by_state["05001"] == "05"
    assert by_state["30001"] == "30"
    assert by_state["12001"] == "12"
