"""Equivalence harness: legacy streaming pre-pass vs DuckDB stage (PRD #135).

Stage 1 of the DuckDB migration replaces the hand-rolled per-shard sjoin
loop (`_build_infra_to_parcel_lookups`) with one spatial join over the
state's sharded parquet. This harness runs the **frozen legacy
implementation** (copied verbatim below from compose.py @ 92dd67c) and
the DuckDB implementation over the same fixtures and asserts the
stage-1 equivalence definition. It outlives the migration as a
regression net until the legacy reference is retired with the last
stage.

Stage-1 equivalence definition (fixed before the migration):

1. **Coverage** — the set of matched infra row indices per layer is
   identical. Unmatched rows are absent from both lookups; a None/empty
   layer yields ``{}`` in both.
2. **Attachment** — for each matched infra row, the attach dict has the
   same key set (a keep-column is attached iff the matched shard's
   schema has it) and equal values, where NaN ≡ None (parquet nulls
   surface as NaN through pandas and as None through DuckDB).
3. **Tie-break determinism** — an infra row inside >1 host-eligible
   parcel attaches the first match in canonical shard order, then
   within-shard row order, in both engines.
4. **Host eligibility** — per shard: ``geometry_valid`` (null → False)
   when the shard carries the column, GEOS validity otherwise; null
   geometry never matches.

Tests assert outputs (the lookup dicts), never SQL text or engine
internals.
"""

from __future__ import annotations

import logging
import math

import geopandas as gpd
import pandas as pd
import preprocess
import pytest
from preprocess.base import Normalizer
from preprocess.compose import _INFRA_PARCEL_RENAME, _build_infra_to_parcel_lookups
from preprocess.compose_helpers import iter_state_parcel_shards
from preprocess.io import write_geoparquet
from shapely.geometry import Point, Polygon

# Reused fixture state: two parcel sources × two shards, towers on A001/B003.
from tests.test_compose_property import (  # noqa: F401
    STATE,
    _ensure_registry_loaded,
    fixture_dirs,
    registered_normalizers,
)

log = logging.getLogger("preprocess.compose")


# ── Frozen legacy reference (compose.py @ 92dd67c, verbatim semantics) ─────


def _legacy_valid_parcel_mask(chunk: gpd.GeoDataFrame):
    if "geometry_valid" in chunk.columns:
        return chunk["geometry_valid"].fillna(False).astype(bool)
    return chunk.geometry.notna() & chunk.geometry.is_valid


def _legacy_build_infra_to_parcel_lookups(
    specs: dict[str, tuple[gpd.GeoDataFrame | None, list[str]]],
    state_fips: str,
) -> dict[str, dict[int, dict]]:
    out: dict[str, dict[int, dict]] = {name: {} for name in specs}
    active = {
        name: (infra[["geometry"]].reset_index(), keep_cols)
        for name, (infra, keep_cols) in specs.items()
        if infra is not None and len(infra) > 0
    }
    if not active:
        return out
    for _label, chunk in iter_state_parcel_shards(state_fips):
        if "geometry" not in chunk.columns:
            continue
        valid_chunk = chunk[_legacy_valid_parcel_mask(chunk)]
        if len(valid_chunk) == 0:
            continue
        for name, (infra_geo, keep_cols) in active.items():
            present = [c for c in keep_cols if c in valid_chunk.columns]
            right = valid_chunk[[*present, "geometry"]].rename(columns=_INFRA_PARCEL_RENAME)
            try:
                hit = gpd.sjoin(infra_geo, right, how="inner", predicate="within")
            except Exception as e:  # noqa: BLE001
                log.warning("infra→parcel sjoin failed on a shard for %s: %s", name, e)
                continue
            lookup = out[name]
            for row in hit.itertuples(index=False):
                row_d = row._asdict() if hasattr(row, "_asdict") else dict(row)
                idx = int(row_d.get("index", -1))
                if idx < 0:
                    continue
                attach = {
                    k: v for k, v in row_d.items() if k not in {"index", "index_right", "geometry"}
                }
                lookup.setdefault(idx, attach)
    return out


# ── Comparison: NaN ≡ None, per the stage-1 equivalence definition ─────────


def _norm_attach(attach: dict) -> dict:
    out = {}
    for k, v in attach.items():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out[k] = None
        else:
            out[k] = v
    return out


def _norm_lookups(lookups: dict[str, dict[int, dict]]) -> dict[str, dict[int, dict]]:
    return {
        name: {int(idx): _norm_attach(attach) for idx, attach in lookup.items()}
        for name, lookup in lookups.items()
    }


def _assert_equivalent(specs, state_fips):
    legacy = _norm_lookups(_legacy_build_infra_to_parcel_lookups(specs, state_fips))
    ducked = _norm_lookups(_build_infra_to_parcel_lookups(specs, state_fips))
    assert ducked == legacy
    return ducked


TOWER_KEEP = ["parcel_id_full", "owner_name", "assessed_value", "acreage", "land_use_code"]


# ── Over the existing compose-property fixtures ────────────────────────────


def test_equivalence_on_property_fixtures(fixture_dirs, registered_normalizers):
    """Both engines over the standard fixture state (2 sources × 2 shards)."""
    towers = gpd.read_parquet(
        fixture_dirs["normalized"] / "fixture_towers" / "towers.parquet"
    ).reset_index(drop=True)
    specs = {
        "tower": (towers, TOWER_KEEP),
        "solar": (None, ["parcel_id_full", "owner_name"]),
        "billboard": (None, ["parcel_id_full", "owner_name"]),
    }
    result = _assert_equivalent(specs, STATE.fips)
    # Not vacuous: T001 sits on A001, T002 on B003 (fixture geometry).
    assert result["tower"][0]["parcel_id_full"] == "A001"
    assert result["tower"][1]["parcel_id_full"] == "B003"
    assert result["tower"][0]["parcel_owner"] == "SHARED LANDOWNER LLC"
    assert result["solar"] == {} and result["billboard"] == {}


# ── Edge-case fixture: validity, ties, schema variance ─────────────────────


def _square(cx: float, cy: float, half: float = 0.5) -> Polygon:
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


@pytest.fixture
def edge_fixture(tmp_path, monkeypatch):
    """Two parcel sources exercising every clause of the equivalence definition.

    src_one/edge_a (no geometry_valid column):
      P1/P2 — identical overlapping squares around (0,0)  → tie-break
      P5    — invalid bowtie around (4,0)                 → GEOS-branch exclusion
    src_one/edge_b (has geometry_valid):
      P3 — square at (2,0), geometry_valid=False          → flag exclusion
      P6 — square at (6,0), geometry_valid=True           → flag inclusion
      P8 — square at (8,0), geometry_valid=NULL           → null ≡ False
    src_two/edge_c (missing assessed_value/acreage/land_use_code; overlaps P1/P2):
      P7 — square at (0,0)        → later source loses the tie
      P9 — square at (10,0)       → attach dict lacks the missing columns
    """
    norm_root = tmp_path / "normalized"
    norm_root.mkdir()
    monkeypatch.setattr(preprocess, "NORMALIZED_ROOT", norm_root)

    bowtie = Polygon([(3.5, -0.5), (4.5, 0.5), (4.5, -0.5), (3.5, 0.5)])
    shard_a = gpd.GeoDataFrame(
        {
            "parcel_id_full": ["P1", "P2", "P5"],
            "owner_name": ["OWNER ONE", "OWNER TWO", "OWNER FIVE"],
            "assessed_value": [100.0, 200.0, 500.0],
            "acreage": [1.0, 2.0, 5.0],
            "land_use_code": ["RES", "RES", "AGR"],
            "state_fips": ["05", "05", "05"],
            "geometry": [_square(0, 0), _square(0, 0), bowtie],
        },
        crs="EPSG:4326",
    )
    shard_b = gpd.GeoDataFrame(
        {
            "parcel_id_full": ["P3", "P6", "P8"],
            "owner_name": ["OWNER THREE", "OWNER SIX", "OWNER EIGHT"],
            "assessed_value": [300.0, 600.0, 800.0],
            "acreage": [3.0, 6.0, 8.0],
            "land_use_code": ["RES", "RES", "RES"],
            "geometry_valid": pd.array([False, True, None], dtype="boolean"),
            "state_fips": ["05", "05", "05"],
            "geometry": [_square(2, 0), _square(6, 0), _square(8, 0)],
        },
        crs="EPSG:4326",
    )
    shard_c = gpd.GeoDataFrame(
        {
            "parcel_id_full": ["P7", "P9"],
            "owner_name": ["OWNER SEVEN", "OWNER NINE"],
            "state_fips": ["05", "05"],
            "geometry": [_square(0, 0), _square(10, 0)],
        },
        crs="EPSG:4326",
    )
    write_geoparquet(shard_a, norm_root / "src_one" / "parcels" / "edge_a.parquet")
    write_geoparquet(shard_b, norm_root / "src_one" / "parcels" / "edge_b.parquet")
    write_geoparquet(shard_c, norm_root / "src_two" / "parcels" / "edge_c.parquet")

    class _SrcOne(Normalizer):
        source_id = "src_one"
        canonical_types = ["parcel"]

        def normalize(self, raw_dir, out_dir):  # pragma: no cover
            raise NotImplementedError

    class _SrcTwo(Normalizer):
        source_id = "src_two"
        canonical_types = ["parcel"]

        def normalize(self, raw_dir, out_dir):  # pragma: no cover
            raise NotImplementedError

    fixture = [_SrcOne(), _SrcTwo()]
    import preprocess.base as base_mod
    import preprocess.compose as compose_mod
    import preprocess.compose_helpers as helpers_mod

    for mod in (base_mod, compose_mod, helpers_mod):
        monkeypatch.setattr(mod, "all_normalizers", lambda: fixture)
    return norm_root


def test_equivalence_edge_cases(edge_fixture):
    towers = gpd.GeoDataFrame(
        {
            "asr_number": ["T1", "T2", "T3", "T4", "T5", "T6", "T7"],
            "geometry": [
                Point(0, 0),  # T1: P1/P2/P7 tie → P1 (first shard, first row)
                Point(2, 0),  # T2: only P3, geometry_valid=False → unmatched
                Point(4, 0),  # T3: only the invalid bowtie → unmatched
                Point(6, 0),  # T4: P6, geometry_valid=True → matched
                Point(10, 0),  # T5: P9 in the column-poor source → partial attach
                Point(50, 50),  # T6: matches nothing
                Point(8, 0),  # T7: P8, geometry_valid=NULL → unmatched
            ],
        },
        crs="EPSG:4326",
    )
    empty_solar = gpd.GeoDataFrame(
        {"facility_id": [], "geometry": []}, geometry="geometry", crs="EPSG:4326"
    )
    specs = {
        "tower": (towers, TOWER_KEEP),
        "solar": (empty_solar, ["parcel_id_full", "owner_name"]),
        "billboard": (None, ["parcel_id_full", "owner_name"]),
    }
    result = _assert_equivalent(specs, "05")

    matched = result["tower"]
    assert set(matched) == {0, 3, 4}
    # Tie-break: P1 beats P2 (same shard, earlier row) and P7 (later source).
    assert matched[0]["parcel_id_full"] == "P1"
    assert matched[3]["parcel_id_full"] == "P6"
    # Column-poor source: only the columns its schema has are attached.
    assert matched[4] == {"parcel_id_full": "P9", "parcel_owner": "OWNER NINE"}
    assert "parcel_value" not in matched[4]
    assert result["solar"] == {} and result["billboard"] == {}


def test_equivalence_no_parcel_shards(edge_fixture, monkeypatch):
    """A state with no parcel shards yields empty lookups from both engines."""
    towers = gpd.GeoDataFrame({"asr_number": ["T1"], "geometry": [Point(0, 0)]}, crs="EPSG:4326")
    specs = {"tower": (towers, TOWER_KEEP)}
    result = _assert_equivalent(specs, "30")  # fixture shards are all state 05
    assert result == {"tower": {}}


# ═══ Stage 2: county_summary rollup ════════════════════════════════════════
#
# Equivalence definition (fixed before the migration):
#
# 1. **Row set** — one row per county_fips present in eligible shards; rows
#    with null county_fips are dropped (pandas groupby dropna ≡ WHERE
#    county_fips IS NOT NULL). A shard whose schema lacks any required
#    column contributes nothing (streaming consume() raised per chunk and
#    the loop skipped it ≡ schema-filtered file list).
# 2. **Cells** — integer counts, strings, and booleans are exactly equal,
#    with matching dtypes after the parquet round-trip; float sums agree to
#    rel 1e-12 (summation order differs between per-chunk partials and one
#    scan — defined tolerance per the PRD).
# 3. **distress_tier "first" / persistent_poverty "any"** — county-constant
#    by construction (one county_score rollup annotates every chunk), so
#    first-non-null is order-free; the DuckDB side still reads in
#    deterministic file order.
# 4. **Order** — columns in the legacy named-agg order; rows by
#    parcels_hosting_infra desc. Tie order is NOT part of the contract:
#    legacy used pandas sort_values' default (unstable quicksort), so ties
#    landed in artifact order — the real-data MT check surfaced this. The
#    DuckDB engine pins ties to county_fips asc (deterministic); the
#    harness compares under that canonical re-sort and separately asserts
#    the produced file is already in it. The index is not part of the
#    contract (write_parquet drops it).


class _LegacyCountySummaryAggregator:
    """Frozen streaming aggregator (compose_helpers.py @ 5344d6c, verbatim
    consume/finalize bodies; the GroupbyChunkAggregator plumbing it
    inherited reduced to the _partials list)."""

    name = "county_summary"

    def __init__(self) -> None:
        self._partials: list[pd.DataFrame] = []

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        if "county_fips" not in chunk.columns:
            return
        df = chunk.copy()
        df["_any_infra"] = (
            df.get("has_tower", False).fillna(False)
            | df.get("has_solar", False).fillna(False)
            | df.get("has_billboard", False).fillna(False)
        )
        df["_llc"] = (df.get("owner_kind", "") == "llc").astype(int)
        partial = (
            df.groupby("county_fips")
            .agg(
                parcel_count=("parcel_id_full", "size"),
                total_assessed_value=("assessed_value", "sum"),
                total_acres=("acreage", "sum"),
                tower_count=("tower_count", "sum"),
                solar_count=("solar_count", "sum"),
                billboard_count=("billboard_count", "sum"),
                parcels_hosting_infra=("_any_infra", "sum"),
                parcels_in_oz=("in_oz", "sum"),
                parcels_in_qct=("in_qct", "sum"),
                distress_tier=("distress_tier", "first"),
                persistent_poverty=("persistent_poverty", "any"),
                llc_owner_count=("_llc", "sum"),
            )
            .reset_index()
        )
        self._partials.append(partial)

    def finalize(self, _ctx) -> pd.DataFrame | None:
        if not self._partials:
            return None
        combined = pd.concat(self._partials, ignore_index=True)
        result = (
            combined.groupby("county_fips")
            .agg(
                parcel_count=("parcel_count", "sum"),
                total_assessed_value=("total_assessed_value", "sum"),
                total_acres=("total_acres", "sum"),
                tower_count=("tower_count", "sum"),
                solar_count=("solar_count", "sum"),
                billboard_count=("billboard_count", "sum"),
                parcels_hosting_infra=("parcels_hosting_infra", "sum"),
                parcels_in_oz=("parcels_in_oz", "sum"),
                parcels_in_qct=("parcels_in_qct", "sum"),
                distress_tier=("distress_tier", "first"),
                persistent_poverty=("persistent_poverty", "any"),
                llc_owner_count=("llc_owner_count", "sum"),
            )
            .reset_index()
        )
        return result.sort_values("parcels_hosting_infra", ascending=False)


def _replay_legacy_county_summary(paths) -> pd.DataFrame | None:
    """Feed shard files to the frozen aggregator the way compose did:
    consume() exceptions are swallowed per chunk (compose logged + skipped)."""
    agg = _LegacyCountySummaryAggregator()
    for p in paths:
        chunk = gpd.read_parquet(p)
        try:
            agg.consume(chunk)
        except Exception:  # noqa: BLE001 — mirrors compose's per-chunk guard
            pass
    return agg.finalize(None)


def _canonical_order(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(
        ["parcels_hosting_infra", "county_fips"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)


def _assert_county_summary_equivalent(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    # Cells/dtypes/columns must match under the canonical order (legacy tie
    # order was a quicksort artifact — see criterion 4); the produced frame
    # must additionally already BE in canonical order (new-engine determinism).
    pd.testing.assert_frame_equal(
        _canonical_order(actual), _canonical_order(expected), rtol=1e-12, atol=0
    )
    pd.testing.assert_frame_equal(actual.reset_index(drop=True), _canonical_order(actual))


def test_county_summary_equivalence_via_compose(fixture_dirs, registered_normalizers, tmp_path):
    """Full compose writes views/county_summary.parquet through the DuckDB
    rollup; the frozen streaming aggregator replayed over the same composite
    shards must produce the identical artifact."""
    from preprocess.compose import ComposeConfig, compose
    from preprocess.io import write_parquet

    compose(ComposeConfig(state=STATE))
    comp_root = fixture_dirs["composite"]
    produced = pd.read_parquet(comp_root / "05" / "views" / "county_summary.parquet")

    shard_paths = sorted((comp_root / "05" / "parcels").glob("*.parquet"))
    legacy = _replay_legacy_county_summary(shard_paths)
    assert legacy is not None
    # Round-trip the legacy frame through the same writer so dtype coercions
    # (the file contract) are compared, not in-memory quirks.
    write_parquet(legacy, tmp_path / "legacy_county_summary.parquet")
    expected = pd.read_parquet(tmp_path / "legacy_county_summary.parquet")

    _assert_county_summary_equivalent(produced, expected)
    # Not vacuous: the fixture spans 4 counties with towers in 05001 + 05005.
    assert len(produced) == 4
    by_county = produced.set_index("county_fips")
    assert int(by_county.loc["05001", "parcels_hosting_infra"]) == 1
    assert int(by_county.loc["05005", "tower_count"]) == 1
    assert by_county.loc["05001", "distress_tier"] == "distressed"


def test_county_summary_equivalence_synthetic_edges(tmp_path):
    """Hand-built annotated-shaped shards exercising the stage-2 definition:
    NaN sums, null county dropped, owner_kind/llc counting, a required-column-
    missing shard excluded by both engines, county-constant distress."""
    from preprocess.compose_helpers import county_summary_rollup

    def shard(rows, drop=()):
        gdf = gpd.GeoDataFrame(
            {
                "county_fips": [r[0] for r in rows],
                "parcel_id_full": [r[1] for r in rows],
                "assessed_value": [r[2] for r in rows],
                "acreage": [r[3] for r in rows],
                "tower_count": [r[4] for r in rows],
                "solar_count": 0,
                "billboard_count": 0,
                "has_tower": [r[4] > 0 for r in rows],
                "has_solar": False,
                "has_billboard": [r[5] for r in rows],
                "in_oz": [r[6] for r in rows],
                "in_qct": False,
                "distress_tier": [r[7] for r in rows],
                "persistent_poverty": [r[8] for r in rows],
                "owner_kind": [r[9] for r in rows],
                "geometry": [Point(0, 0)] * len(rows),
            },
            crs="EPSG:4326",
        )
        return gdf.drop(columns=list(drop))

    s1 = shard(
        [
            ("11111", "X1", 100.5, 1.25, 1, False, True, "distressed", True, "llc"),
            ("11111", "X2", float("nan"), 2.0, 0, False, False, "distressed", True, "individual"),
            ("22222", "X3", 50.0, 0.5, 0, True, False, "", False, ""),
            (None, "X4", 10.0, 0.1, 0, False, False, "", False, ""),  # null county → dropped
        ]
    )
    s2 = shard(
        [
            ("11111", "X5", 200.25, 3.5, 2, False, True, "distressed", True, "llc"),
            ("22222", "X6", 75.0, 1.0, 0, False, False, "", False, "individual"),
        ]
    )
    # Missing a required column (acreage): consume() raised → chunk skipped;
    # the rollup must exclude the file the same way.
    s3 = shard([("33333", "X7", 1.0, 9.9, 5, True, True, "at-risk", True, "llc")], drop=["acreage"])

    paths = []
    for i, s in enumerate((s1, s2, s3)):
        p = tmp_path / f"shard_{i}.parquet"
        write_geoparquet(s, p)
        paths.append(p)

    ducked = county_summary_rollup(paths)
    legacy = _replay_legacy_county_summary(paths)
    assert ducked is not None and legacy is not None
    _assert_county_summary_equivalent(ducked, legacy)

    by_county = ducked.set_index("county_fips")
    assert list(by_county.index) == ["11111", "22222"]  # 33333 excluded, null dropped
    assert int(by_county.loc["11111", "parcel_count"]) == 3
    assert by_county.loc["11111", "total_assessed_value"] == pytest.approx(300.75)
    assert int(by_county.loc["11111", "llc_owner_count"]) == 2
    assert int(by_county.loc["11111", "parcels_in_oz"]) == 2
    assert bool(by_county.loc["11111", "persistent_poverty"]) is True
    assert int(by_county.loc["22222", "parcels_hosting_infra"]) == 1  # billboard counts as infra


def test_county_summary_rollup_no_eligible_shards(tmp_path):
    """No files / no eligible files → None from both engines (view skipped)."""
    from preprocess.compose_helpers import county_summary_rollup

    assert county_summary_rollup([]) is None
    assert _replay_legacy_county_summary([]) is None
