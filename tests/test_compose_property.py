"""Property tests for the streaming Composer (ADR-051).

These exercise the per-shard / per-state invariants the Composer must
hold (owner-cluster sizes, sharded layout, tower attach, OZ membership,
duplicate parcel_id tolerance). Synthetic fixture under tmp_path with
two parcel sources × two shards each, plus
tower/solar/billboard/distress_overlay/county_score companion tables.

Plus focused unit tests for `_reverse_index` (infra-side identity in
the per-parcel summary) and the chunked-vs-aggregator equivalence.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import preprocess
import pytest
from preprocess import COMPOSITE_ROOT as REAL_COMPOSITE_ROOT  # noqa: F401
from preprocess.base import (
    Normalizer,
    NormalizeResult,
    QualityReport,
    register_normalizer_instance,
)
from preprocess.compose import ComposeConfig, compose
from preprocess.geographies import StateGeography
from preprocess.io import write_geoparquet, write_parquet
from shapely.geometry import Point, Polygon

STATE = StateGeography(fips="05", abbr="AR", name="Arkansas", bbox=(-94.6, 33, -89.6, 36.5))


# ── Fixture parcels: two sources × two shards each = 8 parcels ────────────


def _parcel_shard(
    pids: list[str],
    owners: list[str],
    owner_kinds: list[str],
    addresses: list[str],
    counties: list[str],
    values: list[float],
    centers: list[tuple[float, float]],
    state_fips: str = "05",
) -> gpd.GeoDataFrame:
    from preprocess.cluster import normalize_address, normalize_owner_name

    rows = []
    for pid, owner, kind, addr, county, value, (cx, cy) in zip(
        pids, owners, owner_kinds, addresses, counties, values, centers
    ):
        poly = Polygon(
            [
                (cx - 0.1, cy - 0.1),
                (cx + 0.1, cy - 0.1),
                (cx + 0.1, cy + 0.1),
                (cx - 0.1, cy + 0.1),
            ]
        )
        rows.append(
            {
                "parcel_id_full": pid,
                "parcel_id": pid,
                "owner_name": owner,
                "owner_name_norm": normalize_owner_name(owner),
                "owner_kind": kind,
                "mailing_addr": addr,
                "mailing_addr_norm": normalize_address(addr),
                "state_fips": state_fips,
                "county_fips": county,
                "land_use_code": "RES",
                "land_use_desc": "residential",
                "acreage": 1.0,
                "assessed_value": value,
                "geometry": poly,
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


@pytest.fixture
def fixture_dirs(tmp_path, monkeypatch):
    """Set up isolated normalized + composite roots; write fixture data."""
    norm_root = tmp_path / "normalized"
    comp_root = tmp_path / "composite"
    norm_root.mkdir()
    comp_root.mkdir()
    monkeypatch.setattr(preprocess, "NORMALIZED_ROOT", norm_root)
    monkeypatch.setattr(preprocess, "COMPOSITE_ROOT", comp_root)
    # The compose module captured COMPOSITE_ROOT at import time — patch
    # that binding too.
    import preprocess.compose as compose_mod

    monkeypatch.setattr(compose_mod, "COMPOSITE_ROOT", comp_root)

    # ── Parcels: two sources × two shards each ──
    src_a = norm_root / "fixture_src_a" / "parcels"
    src_b = norm_root / "fixture_src_b" / "parcels"
    src_a.mkdir(parents=True)
    src_b.mkdir(parents=True)

    # Shared owner across two parcels → cluster_size = 2
    shared_owner = "SHARED LANDOWNER LLC"
    shared_addr = "123 MAIN ST"

    shard_a1 = _parcel_shard(
        pids=["A001", "A002"],
        owners=[shared_owner, "ALICE INDIVIDUAL"],
        owner_kinds=["llc", "individual"],
        addresses=[shared_addr, "200 OAK AVE"],
        counties=["05001", "05003"],
        values=[100_000.0, 50_000.0],
        centers=[(-92.5, 34.5), (-92.6, 34.6)],
    )
    shard_a2 = _parcel_shard(
        pids=["A003", "A004"],
        owners=["BOB TRUST", "CAROL CORP"],
        owner_kinds=["trust", "corporation"],
        addresses=["300 PINE ST", "400 ELM RD"],
        counties=["05001", "05005"],
        values=[75_000.0, 250_000.0],
        centers=[(-92.4, 34.4), (-92.3, 34.3)],
    )
    shard_b1 = _parcel_shard(
        pids=["B001", "B002"],
        owners=[shared_owner, "DAVE INDIVIDUAL"],
        owner_kinds=["llc", "individual"],
        addresses=[shared_addr, "500 BIRCH LN"],
        counties=["05003", "05007"],
        values=[150_000.0, 80_000.0],
        centers=[(-92.7, 34.7), (-92.8, 34.8)],
    )
    shard_b2 = _parcel_shard(
        pids=["B003", "B004"],
        owners=["EVE LLC", "FAITH FAMILY TRUST"],
        owner_kinds=["llc", "trust"],
        addresses=["600 CEDAR ST", "700 WILLOW DR"],
        counties=["05005", "05007"],
        values=[120_000.0, 90_000.0],
        centers=[(-92.9, 34.9), (-93.0, 35.0)],
    )
    write_geoparquet(shard_a1, src_a / "shard_a1.parquet")
    write_geoparquet(shard_a2, src_a / "shard_a2.parquet")
    write_geoparquet(shard_b1, src_b / "shard_b1.parquet")
    write_geoparquet(shard_b2, src_b / "shard_b2.parquet")

    # ── Towers: 2 towers, one on A001 (LLC), one on B003 ──
    towers_dir = norm_root / "fixture_towers"
    towers_dir.mkdir(parents=True)
    towers = gpd.GeoDataFrame(
        [
            {
                "asr_number": "T001",
                "owner_name": "Big Tower Co",
                "registrant_name": "Big Tower Co",
                "state_fips": "05",
                "county_fips": "05001",
                "geometry": Point(-92.5, 34.5),
            },
            {
                "asr_number": "T002",
                "owner_name": "Other Tower Co",
                "registrant_name": "Other Tower Co",
                "state_fips": "05",
                "county_fips": "05005",
                "geometry": Point(-92.9, 34.9),
            },
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    write_geoparquet(towers, towers_dir / "towers.parquet")

    # ── Distress overlay: an OZ over the western corner of the fixture ──
    overlays_dir = norm_root / "fixture_overlays"
    overlays_dir.mkdir(parents=True)
    overlays = gpd.GeoDataFrame(
        [
            {
                "overlay_type": "opportunity_zone",
                "state_fips": "05",
                "geometry": Polygon([(-93.5, 34.0), (-92.55, 34.0), (-92.55, 35.5), (-93.5, 35.5)]),
            },
            {
                "overlay_type": "qct",
                "state_fips": "05",
                "geometry": Polygon([(-93.5, 34.7), (-92.55, 34.7), (-92.55, 35.5), (-93.5, 35.5)]),
            },
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    write_geoparquet(overlays, overlays_dir / "distress_overlays.parquet")

    # ── County score: ARC + USDA-style rows for some counties ──
    scores_dir = norm_root / "fixture_scores"
    scores_dir.mkdir(parents=True)
    scores = pd.DataFrame(
        [
            {
                "county_fips": "05001",
                "state_fips": "05",
                "tier": "distressed",
                "persistent_poverty": True,
            },
            {
                "county_fips": "05003",
                "state_fips": "05",
                "tier": "at-risk",
                "persistent_poverty": False,
            },
            {"county_fips": "05005", "state_fips": "05", "tier": "", "persistent_poverty": True},
        ]
    )
    write_parquet(scores, scores_dir / "county_scores.parquet")

    return {"normalized": norm_root, "composite": comp_root}


# ── Fixture Normalizers (registered just for these tests) ────────────────


class _FixtureParcelSrcA(Normalizer):
    source_id = "fixture_src_a"
    canonical_types = ["parcel"]

    def normalize(self, raw_dir, out_dir):  # pragma: no cover
        raise NotImplementedError


class _FixtureParcelSrcB(Normalizer):
    source_id = "fixture_src_b"
    canonical_types = ["parcel"]

    def normalize(self, raw_dir, out_dir):  # pragma: no cover
        raise NotImplementedError


class _FixtureTowers(Normalizer):
    source_id = "fixture_towers"
    canonical_types = ["tower"]

    def normalize(self, raw_dir, out_dir):  # pragma: no cover
        raise NotImplementedError


class _FixtureOverlays(Normalizer):
    source_id = "fixture_overlays"
    canonical_types = ["distress_overlay"]

    def normalize(self, raw_dir, out_dir):  # pragma: no cover
        raise NotImplementedError


class _FixtureScores(Normalizer):
    source_id = "fixture_scores"
    canonical_types = ["county_score"]

    def normalize(self, raw_dir, out_dir):  # pragma: no cover
        raise NotImplementedError


@pytest.fixture
def registered_normalizers(monkeypatch):
    """Replace the global normalizer registry with the fixture set so
    compose / compose see only our test sources."""
    fixture_normalizers = [
        _FixtureParcelSrcA(),
        _FixtureParcelSrcB(),
        _FixtureTowers(),
        _FixtureOverlays(),
        _FixtureScores(),
    ]
    # `all_normalizers` is imported by many modules — patch in each.
    import preprocess.base as base_mod
    import preprocess.compose as compose_mod
    import preprocess.compose_helpers as helpers_mod

    monkeypatch.setattr(base_mod, "all_normalizers", lambda: fixture_normalizers)
    monkeypatch.setattr(compose_mod, "all_normalizers", lambda: fixture_normalizers)
    monkeypatch.setattr(helpers_mod, "all_normalizers", lambda: fixture_normalizers)
    return fixture_normalizers


# Force-load the real joins + views before running these tests so the
# global join/view registry is populated.
@pytest.fixture(autouse=True)
def _ensure_registry_loaded():
    from preprocess import registry  # noqa: F401


# ── The regression assertion ─────────────────────────────────────────────


PARCEL_COLS_TO_COMPARE = [
    "parcel_id_full",
    "county_fips",
    "owner_name",
    "owner_kind",
    "owner_cluster_id",
    "owner_cluster_size",
    "has_tower",
    "tower_count",
    "has_solar",
    "solar_count",
    "has_billboard",
    "billboard_count",
    "infrastructure_summary",
    "distress_tier",
    "persistent_poverty",
    "in_oz",
    "in_qct",
    "interestingness_score",
]


def _load_parcels(comp_root: Path, fips: str = "05") -> pd.DataFrame:
    shards = sorted((comp_root / fips / "parcels").glob("*.parquet"))
    assert shards, f"compose produced no parcel shards for state {fips}"
    frames = [gpd.read_parquet(p) for p in shards]
    return pd.concat(
        [pd.DataFrame(f.drop(columns=["geometry"])) for f in frames], ignore_index=True
    )


def _sort_infra_summary(v):
    """Sort an infrastructure_summary list by id so order isn't load-bearing."""
    if not isinstance(v, list):
        return v
    return sorted(v, key=lambda d: (d.get("type", ""), d.get("id", "")))


def _normalize_for_compare(df: pd.DataFrame) -> pd.DataFrame:
    """Project to the comparison columns, sort by parcel_id_full, reset index."""
    present = [c for c in PARCEL_COLS_TO_COMPARE if c in df.columns]
    out = df[present].sort_values("parcel_id_full").reset_index(drop=True)
    if "infrastructure_summary" in out.columns:
        out = out.copy()
        out["infrastructure_summary"] = out["infrastructure_summary"].map(_sort_infra_summary)
    return out


def test_compose_writes_sharded_layout(fixture_dirs, registered_normalizers):
    comp_root: Path = fixture_dirs["composite"]
    cfg = ComposeConfig(state=STATE)
    compose(cfg)
    # No single parcels.parquet
    assert not (comp_root / "05" / "parcels.parquet").exists()
    # A parcels/ dir of shards instead
    shards_dir = comp_root / "05" / "parcels"
    assert shards_dir.is_dir()
    shards = list(shards_dir.glob("*.parquet"))
    assert len(shards) == 4, f"expected 4 shards (2 sources × 2 shards each), got {len(shards)}"
    # Catalog advertises the sharded layer
    import json

    catalog = json.loads((comp_root / "05" / "catalog.json").read_text())
    parcel_layer = catalog["layers"]["parcels"]
    assert parcel_layer["sharded"] is True
    assert parcel_layer["shard_count"] == 4
    assert parcel_layer["parquet_path"] == "parcels"


def test_compose_owner_clusters_size_2(fixture_dirs, registered_normalizers):
    """Two parcels share owner+address → cluster size 2 for both."""
    comp_root: Path = fixture_dirs["composite"]
    compose(ComposeConfig(state=STATE))
    parcels = _load_parcels(comp_root).set_index("parcel_id_full")
    # A001 and B001 share owner+address.
    assert parcels.loc["A001", "owner_cluster_size"] == 2
    assert parcels.loc["B001", "owner_cluster_size"] == 2
    assert parcels.loc["A001", "owner_cluster_id"] == parcels.loc["B001", "owner_cluster_id"]
    # Other parcels are solo.
    assert parcels.loc["A002", "owner_cluster_size"] == 1


def test_compose_tower_to_parcel_attaches(fixture_dirs, registered_normalizers):
    comp_root: Path = fixture_dirs["composite"]
    compose(ComposeConfig(state=STATE))
    parcels = _load_parcels(comp_root).set_index("parcel_id_full")
    # Tower T001 lives on parcel A001's polygon.
    assert bool(parcels.loc["A001", "has_tower"]) is True
    assert int(parcels.loc["A001", "tower_count"]) == 1
    # Tower T002 lives on B003.
    assert bool(parcels.loc["B003", "has_tower"]) is True
    # Parcels without towers see has_tower=False.
    assert bool(parcels.loc["A002", "has_tower"]) is False


def test_compose_distress_overlay_membership(fixture_dirs, registered_normalizers):
    comp_root: Path = fixture_dirs["composite"]
    compose(ComposeConfig(state=STATE))
    parcels = _load_parcels(comp_root).set_index("parcel_id_full")
    # The OZ overlay spans the western corner — A001/A002/B001 are inside.
    assert bool(parcels.loc["A001", "in_oz"]) is True
    # A004 sits outside the overlay polygon.
    assert bool(parcels.loc["A004", "in_oz"]) is False


def test_compose_tolerates_duplicate_parcel_id_full(tmp_path, monkeypatch):
    """FL FDOR NAL's PARCEL_ID is county-unique, not state-unique — so
    chunked compose must NOT key its owner-cluster lookup on
    parcel_id_full. This test seeds duplicate parcel_id_full across two
    shards and verifies compose succeeds end-to-end (the bug
    raised `cannot reindex on an axis with duplicate labels`).
    """
    norm_root = tmp_path / "normalized"
    comp_root = tmp_path / "composite"
    norm_root.mkdir()
    comp_root.mkdir()
    monkeypatch.setattr(preprocess, "NORMALIZED_ROOT", norm_root)
    monkeypatch.setattr(preprocess, "COMPOSITE_ROOT", comp_root)
    import preprocess.compose as compose_mod

    monkeypatch.setattr(compose_mod, "COMPOSITE_ROOT", comp_root)

    # Two shards each carrying a parcel with parcel_id_full="DUP-001"
    # but different counties — exactly the FL pattern.
    src = norm_root / "fixture_dup" / "parcels"
    src.mkdir(parents=True)
    shard_a = _parcel_shard(
        pids=["DUP-001", "UNIQUE-A"],
        owners=["SHARED OWNER LLC", "ALICE"],
        owner_kinds=["llc", "individual"],
        addresses=["123 MAIN ST", "200 OAK AVE"],
        counties=["12001", "12001"],  # county A
        values=[100_000.0, 50_000.0],
        centers=[(-82.5, 28.5), (-82.6, 28.6)],
        state_fips="12",
    )
    shard_b = _parcel_shard(
        pids=["DUP-001", "UNIQUE-B"],  # same parcel_id_full, different county
        owners=["DIFFERENT OWNER", "BOB"],
        owner_kinds=["individual", "individual"],
        addresses=["999 SOMEWHERE", "300 PINE"],
        counties=["12003", "12003"],  # county B
        values=[200_000.0, 75_000.0],
        centers=[(-82.7, 28.7), (-82.8, 28.8)],
        state_fips="12",
    )
    write_geoparquet(shard_a, src / "shard_a.parquet")
    write_geoparquet(shard_b, src / "shard_b.parquet")

    # Minimal companion tables so compose doesn't no-op on missing inputs.
    (norm_root / "fixture_dup_scores").mkdir(parents=True)
    write_parquet(
        pd.DataFrame(
            [
                {
                    "county_fips": "12001",
                    "state_fips": "12",
                    "tier": "",
                    "persistent_poverty": False,
                },
                {
                    "county_fips": "12003",
                    "state_fips": "12",
                    "tier": "at-risk",
                    "persistent_poverty": False,
                },
            ]
        ),
        norm_root / "fixture_dup_scores" / "county_scores.parquet",
    )

    class _DupParcels(Normalizer):
        source_id = "fixture_dup"
        canonical_types = ["parcel"]

        def normalize(self, raw_dir, out_dir):  # pragma: no cover
            raise NotImplementedError

    class _DupScores(Normalizer):
        source_id = "fixture_dup_scores"
        canonical_types = ["county_score"]

        def normalize(self, raw_dir, out_dir):  # pragma: no cover
            raise NotImplementedError

    fixture = [_DupParcels(), _DupScores()]
    import preprocess.base as base_mod
    import preprocess.compose_helpers as helpers_mod

    for mod in (base_mod, compose_mod, helpers_mod):
        monkeypatch.setattr(mod, "all_normalizers", lambda: fixture)

    fl_state = StateGeography(fips="12", abbr="FL", name="Florida", bbox=(-87, 24, -80, 31))
    # The bug: this call raised "cannot reindex on an axis with duplicate labels".
    res = compose(ComposeConfig(state=fl_state))
    assert res.counts.get("parcel", 0) == 4  # 2 shards × 2 parcels
    # Each shard should have been written.
    shards = sorted((comp_root / "12" / "parcels").glob("*.parquet"))
    assert len(shards) == 2

    # The owner cluster computed per-row from owner_name + mailing_addr
    # — so the two DUP-001 rows belong to *different* clusters because
    # they have different owners. cluster_size for each should be 1.
    parcels = _load_parcels(comp_root, fips="12")
    # Group by (county_fips, parcel_id_full) to disambiguate the dupes.
    by_key = parcels.set_index(["county_fips", "parcel_id_full"])
    assert int(by_key.loc[("12001", "DUP-001"), "owner_cluster_size"]) == 1
    assert int(by_key.loc[("12003", "DUP-001"), "owner_cluster_size"]) == 1
    # Different owner/addr → different cluster ids.
    assert (
        by_key.loc[("12001", "DUP-001"), "owner_cluster_id"]
        != by_key.loc[("12003", "DUP-001"), "owner_cluster_id"]
    )


# ── _reverse_index unit test ───────────────────────────────────────────────


def test_reverse_index_carries_infra_side_identity():
    """`_reverse_index` summary entries must record the infra row's own
    id/owner (asr_number for towers, etc.), not the parcel's. Single-shot
    ``ParcelHostsInfraJoin`` writes infra-side identity; chunked must match.
    The Svelte ``DetailsPanel.svelte`` renders this list as "infrastructure
    on this parcel" — the user wants the infra's identity surfaced.
    """
    from preprocess.compose import _reverse_index

    infra = gpd.GeoDataFrame(
        {
            "asr_number": ["ASR-001", "ASR-002"],
            "owner_name": ["AT&T Mobility", "Verizon"],
            "geometry": [Point(-92.0, 35.0), Point(-92.1, 35.1)],
        },
        crs="EPSG:4326",
    )
    # Both towers attach to the same parcel (P001) — exercise the count+list path.
    lookup = {
        0: {"parcel_id_full": "P001", "parcel_owner": "BOB JONES"},
        1: {"parcel_id_full": "P001", "parcel_owner": "BOB JONES"},
    }

    counts, summary = _reverse_index(
        lookup, infra=infra, kind="tower", id_col="asr_number", owner_col="owner_name"
    )

    assert counts == {"P001": 2}
    items = sorted(summary["P001"], key=lambda d: d["id"])
    assert items == [
        {"type": "tower", "id": "ASR-001", "owner": "AT&T Mobility"},
        {"type": "tower", "id": "ASR-002", "owner": "Verizon"},
    ]
    # Critically: never the parcel's id or owner.
    for item in items:
        assert item["id"] != "P001"
        assert item["owner"] != "BOB JONES"


def test_apply_lookup_assigns_per_column_independently():
    """The for-col loop runs `.map(lambda i: lookup[i][col])` once per column.
    Each lambda captures `col` by reference, but `.map` runs synchronously
    inside the loop body so the captured `col` is current — never the
    last-iteration value. This test guards against a future change that
    might defer the map (e.g. lazy GeoDataFrame ops)."""
    from preprocess.compose import _apply_lookup

    infra = gpd.GeoDataFrame(
        {
            "asr_number": ["A", "B", "C"],
            "geometry": [Point(0, 0), Point(1, 1), Point(2, 2)],
        },
        crs="EPSG:4326",
    )
    lookup = {
        0: {"parcel_id_full": "P-A", "parcel_owner": "Alice"},
        1: {"parcel_id_full": "P-B", "parcel_owner": "Bob"},
        # idx 2 absent → both columns should be None for row "C"
    }
    out = _apply_lookup(infra, lookup)
    assert list(out["parcel_id_full"][:2]) == ["P-A", "P-B"]
    assert list(out["parcel_owner"][:2]) == ["Alice", "Bob"]
    # Row 2 has no lookup entry — both columns are NaN (pandas Series.map
    # default-fills with NaN for missing keys, not None).
    assert pd.isna(out["parcel_id_full"].iloc[2])
    assert pd.isna(out["parcel_owner"].iloc[2])


def test_reverse_index_handles_empty_inputs():
    from preprocess.compose import _reverse_index

    counts, summary = _reverse_index(
        {}, infra=None, kind="tower", id_col="asr_number", owner_col="owner_name"
    )
    assert counts == {} and summary == {}

    empty_infra = gpd.GeoDataFrame(
        {"asr_number": [], "owner_name": [], "geometry": []},
        geometry="geometry",
        crs="EPSG:4326",
    )
    counts, summary = _reverse_index(
        {}, infra=empty_infra, kind="tower", id_col="asr_number", owner_col="owner_name"
    )
    assert counts == {} and summary == {}
