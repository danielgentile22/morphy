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

import json
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
        df["_any_infra"] = df.get("has_tower", False).fillna(False) | df.get(
            "has_solar", False
        ).fillna(False)
        df["_llc"] = (df.get("owner_kind", "") == "llc").astype(int)
        partial = (
            df.groupby("county_fips")
            .agg(
                parcel_count=("parcel_id_full", "size"),
                total_assessed_value=("assessed_value", "sum"),
                total_acres=("acreage", "sum"),
                tower_count=("tower_count", "sum"),
                solar_count=("solar_count", "sum"),
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
                "has_tower": [r[4] > 0 for r in rows],
                "has_solar": False,
                # r[5] was the old has_billboard flag (dropped, E14) — unused now.
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
    # Towers count as infra (X1+X5 in 11111); 22222's only "infra" was a
    # billboard, which no longer counts (E14), so it drops to 0.
    assert int(by_county.loc["11111", "parcels_hosting_infra"]) == 2
    assert int(by_county.loc["22222", "parcels_hosting_infra"]) == 0


def test_county_summary_rollup_no_eligible_shards(tmp_path):
    """No files / no eligible files → None from both engines (view skipped)."""
    from preprocess.compose_helpers import county_summary_rollup

    assert county_summary_rollup([]) is None
    assert _replay_legacy_county_summary([]) is None


# ═══ Stage 3: owner-cluster pre-pass ═══════════════════════════════════════
#
# Equivalence definition (fixed before the migration):
#
# 1. **Cluster set** — identical owner_cluster_id index (unique; the
#    un-clusterable "" key excluded). A shard missing any OWNER_COLS column
#    contributes nothing (the legacy column-projected pd.read_parquet raised
#    and the shard was skipped ≡ shard-eligibility filter).
# 2. **Sizes** — owner_cluster_size exactly equal, int64.
# 3. **Value totals** — owner_cluster_value_total within rel 1e-12 (float
#    summation order differs between one concat-sum and SQL+fallback partial
#    sums), float64. assessed_value coercion: non-numeric/None → 0
#    (pd.to_numeric(errors="coerce").fillna(0) ≡ coalesce(TRY_CAST, 0)).
# 4. **Key recipe** — stored *_norm values nonblank → used verbatim, keyed
#    substr(sha1(name||'|'||addr),1,12) (DuckDB sha1 ≡ hashlib over UTF-8);
#    blank/absent norm with a non-blank raw → that ROW routes through the
#    live cluster.py recipe in Python (never re-implemented in SQL), and
#    cross-engine rows summing into the same cluster combine. Blank
#    detection is whitespace-strip; stored norms are whitespace-collapsed
#    at normalize time, so trim() parity holds.
# 5. **Empty** — no shards / no eligible shards / nothing clusterable →
#    the same empty lookup frame (columns + index name).


def _legacy_iter_state_parcel_shards_columns(state_fips, columns):
    """Frozen column-projected shard iterator (compose_helpers.py @ 95932ce,
    verbatim semantics — deleted from production with stage 3). Resolves
    all_normalizers/NORMALIZED_ROOT through the live modules so the
    fixtures' monkeypatching applies."""
    import preprocess as preprocess_pkg
    import preprocess.compose_helpers as helpers_mod
    from preprocess.base import OUTPUT_BASENAMES

    root = preprocess_pkg.NORMALIZED_ROOT
    parcel_basename = OUTPUT_BASENAMES.get("parcel", "parcel")
    cols = list(dict.fromkeys([*columns, "state_fips"]))

    parcel_sources = [n for n in helpers_mod.all_normalizers() if "parcel" in n.canonical_types]
    for n in parcel_sources:
        src_dir = root / n.source_id / parcel_basename
        if not src_dir.is_dir():
            continue
        for shard_path in sorted(src_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(shard_path, columns=cols)
            except Exception:  # noqa: BLE001 — missing column ⇒ shard skipped
                continue
            slice_ = df[df["state_fips"] == state_fips]
            if len(slice_) == 0:
                continue
            yield f"{n.source_id}__{shard_path.stem}", slice_.copy()


def _legacy_build_owner_cluster_lookup(state_fips: str) -> pd.DataFrame:
    """Frozen legacy pre-pass: stream OWNER_COLS projections into the live
    owner_cluster.prepare (the reference recipe both engines share)."""
    from preprocess.annotators import owner_cluster

    frames = (
        df
        for _label, df in _legacy_iter_state_parcel_shards_columns(
            state_fips, owner_cluster.OWNER_COLS
        )
    )
    return owner_cluster.prepare(frames)


def _assert_owner_lookup_equivalent(state_fips: str) -> pd.DataFrame:
    from preprocess.compose import _build_owner_cluster_lookup

    legacy = _legacy_build_owner_cluster_lookup(state_fips)
    ducked = _build_owner_cluster_lookup(state_fips)
    pd.testing.assert_frame_equal(ducked.sort_index(), legacy.sort_index(), rtol=1e-12, atol=0)
    return ducked


def test_owner_lookup_equivalence_on_property_fixtures(fixture_dirs, registered_normalizers):
    """Both engines over the standard fixture state — the shared owner
    (two parcels, two sources) must aggregate to one cluster of size 2."""
    from preprocess.cluster import cluster_id, normalize_address, normalize_owner_name

    result = _assert_owner_lookup_equivalent(STATE.fips)
    assert len(result) > 0
    shared = cluster_id(
        normalize_owner_name("SHARED LANDOWNER LLC"), normalize_address("123 MAIN ST")
    )
    assert int(result.loc[shared, "owner_cluster_size"]) == 2
    assert result.loc[shared, "owner_cluster_value_total"] == pytest.approx(250_000.0)


@pytest.fixture
def owner_edge_fixture(tmp_path, monkeypatch):
    """Owner-column edge cases across two sources.

    src_one/owners_a (full owner cols, norms populated):
      r1/r2 — same stored norms                  → SQL path, cluster size 2
      r3 — blank norms, raw name+addr present    → Python fallback; its key
           EQUALS r1/r2's (raw normalizes to the same norms) → sizes sum 3
      r4 — blank norms, blank raws               → "" key, excluded
      r5 — blank norms, noise-only raw name      → fallback normalizes to "",
           addr blank → "" key, excluded
      r6 — name norm good, addr norm blank + raw → fallback row mixing a
           verbatim stored norm with a live-normalized addr
      r7 — assessed_value None                   → 0 toward its total
    src_one/owners_b — mailing_addr column MISSING → whole shard excluded
      (legacy projected read raised); its unique owner must not appear.
    src_two/owners_c — same norms as r1 (cross-source sum), assessed_value
      stored as VARCHAR ("250.25" sums; "N/A" → 0).
    """
    from preprocess.cluster import normalize_address, normalize_owner_name

    norm_root = tmp_path / "normalized"
    norm_root.mkdir()
    monkeypatch.setattr(preprocess, "NORMALIZED_ROOT", norm_root)

    n_shared = normalize_owner_name("SHARED LANDOWNER LLC")
    a_shared = normalize_address("123 MAIN ST")

    def df(rows, columns):
        return pd.DataFrame(rows, columns=columns)

    cols = [
        "owner_name_norm",
        "mailing_addr_norm",
        "owner_name",
        "mailing_addr",
        "assessed_value",
        "state_fips",
    ]
    shard_a = df(
        [
            (n_shared, a_shared, "Shared Landowner LLC", "123 Main St", 100.0, "05"),
            (n_shared, a_shared, "SHARED LANDOWNER LLC", "123 MAIN ST", 50.5, "05"),
            # Raw normalizes to the same norms as r1/r2 (undotted LLC — the
            # dotted form survives punctuation-stripping as stray tokens).
            ("", "", "Shared Landowner LLC", "123 Main Street", 25.25, "05"),
            ("", "", "", "", 99.0, "05"),
            ("", "", "LLC", None, 7.0, "05"),
            (normalize_owner_name("GOOD OWNER"), "", "Good Owner", "77 Pine Road", 10.0, "05"),
            (n_shared, a_shared, "SHARED LANDOWNER LLC", "123 MAIN ST", None, "05"),
        ],
        cols,
    )
    shard_b = df(
        [
            (
                normalize_owner_name("ONLY IN B"),
                normalize_address("9 B ST"),
                "Only In B",
                None,
                1.0,
                "05",
            )
        ],
        cols,
    ).drop(columns=["mailing_addr"])
    shard_c = df(
        [
            (n_shared, a_shared, "SHARED LANDOWNER LLC", "123 MAIN ST", "250.25", "05"),
            (n_shared, a_shared, "SHARED LANDOWNER LLC", "123 MAIN ST", "N/A", "05"),
        ],
        cols,
    )
    from preprocess.io import write_parquet

    write_parquet(shard_a, norm_root / "src_one" / "parcels" / "owners_a.parquet")
    write_parquet(shard_b, norm_root / "src_one" / "parcels" / "owners_b.parquet")
    write_parquet(shard_c, norm_root / "src_two" / "parcels" / "owners_c.parquet")

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


def test_owner_lookup_equivalence_edge_cases(owner_edge_fixture):
    from preprocess.cluster import cluster_id, normalize_address, normalize_owner_name

    result = _assert_owner_lookup_equivalent("05")

    shared = cluster_id(
        normalize_owner_name("SHARED LANDOWNER LLC"), normalize_address("123 MAIN ST")
    )
    # r1 + r2 + r7 (SQL) + r3 (Python fallback) + shard_c's two rows = 6.
    assert int(result.loc[shared, "owner_cluster_size"]) == 6
    # 100.0 + 50.5 + 0 (None) + 25.25 + 250.25 + 0 ("N/A")
    assert result.loc[shared, "owner_cluster_value_total"] == pytest.approx(426.0)
    # The owner unique to the column-poor shard must be absent (shard skipped).
    only_b = cluster_id(normalize_owner_name("ONLY IN B"), normalize_address("9 B ST"))
    assert only_b not in result.index
    # The mixed row (stored name norm + live-normalized addr) keys correctly.
    mixed = cluster_id(normalize_owner_name("GOOD OWNER"), normalize_address("77 Pine Road"))
    assert int(result.loc[mixed, "owner_cluster_size"]) == 1
    # Un-clusterable rows (r4 blank-blank, r5 noise-only name) are excluded:
    # the only clusters are shared / mixed.
    assert set(result.index) == {shared, mixed}


def test_owner_lookup_no_shards(owner_edge_fixture):
    """A state with no shards → the same empty lookup frame from both."""
    from preprocess.compose import _build_owner_cluster_lookup

    legacy = _legacy_build_owner_cluster_lookup("30")
    ducked = _build_owner_cluster_lookup("30")
    pd.testing.assert_frame_equal(ducked, legacy)
    assert list(ducked.columns) == ["owner_cluster_size", "owner_cluster_value_total"]
    assert ducked.index.name == "owner_cluster_id"
    assert len(ducked) == 0


# ═══ Stage 4: slim parquet (parcels_attr) + facets ═════════════════════════
#
# Equivalence definition (fixed before the migration):
#
# 1. **parcels_attr.parquet** — same column names in the same order
#    (attr_columns over the FIRST source file's schema; a column missing
#    from a later shard reads as NULL, a column present only in a later
#    shard is excluded — both like the legacy promoting concat); same row
#    count; identical cell values (NaN ≡ None). Rows sorted by
#    interestingness_score desc with ties in source order (pyarrow's
#    stable sort ≡ ORDER BY score DESC NULLS LAST, filename, row number);
#    with no sort column, source order preserved. Row groups ≤
#    ROW_GROUP_SIZE and zstd compression in both writers (the DuckDB-WASM
#    range-query contract); byte layout is NOT contractual. A column that
#    is entirely null in the source (arrow `null` type — e.g. MT's
#    situs_state, surfaced by the real-data check) has no real stored
#    type: the new engine writes it as VARCHAR (the semantically right
#    type), so its pandas round-trip dtype differs from legacy's
#    object-from-null — values (all null) compared, dtype exempt.
# 2. **facets.json** — schema_version / state_fips / total exact; numeric
#    min/max exact (NULL → null). Categorical lists hold the same
#    (value, count) pairs compared under canonical (count desc, value asc)
#    order — the legacy order among equal counts was value_counts
#    encounter-order (non-contractual); the new engine emits the canonical
#    order. When MAX_CATEGORICAL_VALUES truncates at a count tie, which
#    tied values survive is engine-dependent (documented tolerance).
# 3. **Atomicity** — temp-file + replace in both engines.


def _legacy_build_facets_outputs(state_dir, out_dir):
    """Frozen legacy facets engine (facets.py @ b0602ab, verbatim
    semantics): per-shard projected read + promoting concat + pyarrow
    sort + small-row-group write; pyarrow value_counts facets. Writes
    parcels_attr.parquet under out_dir; returns the facets dict
    (without the state_fips key the caller adds)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from preprocess.facets import CATEGORICAL_FACETS as CAT
    from preprocess.facets import MAX_CATEGORICAL_VALUES as MAXC
    from preprocess.facets import NUMERIC_FACETS as NUM
    from preprocess.facets import ROW_GROUP_SIZE, SORT_COLUMN, attr_columns

    single = state_dir / "parcels.parquet"
    if single.exists():
        source, is_sharded = single, False
    else:
        source, is_sharded = state_dir / "parcels", True

    if is_sharded:
        first_shard = next(iter(sorted(source.glob("*.parquet"))))
        schema_names = pq.ParquetFile(first_shard).schema_arrow.names
    else:
        schema_names = pq.ParquetFile(source).schema_arrow.names
    keep = attr_columns(schema_names)

    if not is_sharded:
        table = pq.read_table(source, columns=keep)
    else:
        tables = []
        for shard in sorted(source.glob("*.parquet")):
            pf = pq.ParquetFile(shard)
            present = [c for c in keep if c in pf.schema_arrow.names]
            tables.append(pq.read_table(shard, columns=present))
        table = pa.concat_tables(tables, promote_options="default")
    if SORT_COLUMN in table.column_names:
        table = table.sort_by([(SORT_COLUMN, "descending")])

    pq.write_table(
        table, out_dir / "parcels_attr.parquet", row_group_size=ROW_GROUP_SIZE, compression="zstd"
    )

    categorical = {}
    for col in CAT:
        if col not in table.column_names:
            continue
        counts = pc.value_counts(table.column(col))
        pairs = []
        for i in range(len(counts)):
            value = counts.field("values")[i].as_py()
            if value is None or value == "":
                continue
            pairs.append({"value": value, "count": counts.field("counts")[i].as_py()})
        pairs.sort(key=lambda p: p["count"], reverse=True)
        categorical[col] = pairs[:MAXC]
    numeric = {}
    for col in NUM:
        if col not in table.column_names:
            continue
        mm = pc.min_max(table.column(col)).as_py()
        numeric[col] = {"min": mm["min"], "max": mm["max"]}
    from preprocess.facets import FACETS_SCHEMA_VERSION

    return {
        "schema_version": FACETS_SCHEMA_VERSION,
        "total": table.num_rows,
        "categorical": categorical,
        "numeric": numeric,
    }


def _canon_facets(facets: dict) -> dict:
    out = json.loads(json.dumps(facets))  # deep copy, JSON-normalized scalars
    for col, pairs in out.get("categorical", {}).items():
        out["categorical"][col] = sorted(pairs, key=lambda p: (-p["count"], str(p["value"])))
    return out


def _assert_facets_outputs_equivalent(state_dir, legacy_dir, produced_facets: dict) -> None:
    """Build the frozen legacy outputs into legacy_dir, then compare both
    artifacts against what the DuckDB engine wrote under state_dir."""
    legacy_facets = _legacy_build_facets_outputs(state_dir, legacy_dir)

    new_attr = pd.read_parquet(state_dir / "parcels_attr.parquet")
    old_attr = pd.read_parquet(legacy_dir / "parcels_attr.parquet")
    assert list(new_attr.columns) == list(old_attr.columns)
    # All-null source columns: values compared, dtype exempt (criterion 1).
    all_null = [c for c in old_attr.columns if old_attr[c].isna().all()]
    for c in all_null:
        assert new_attr[c].isna().all() and len(new_attr[c]) == len(old_attr[c])
    strict = [c for c in old_attr.columns if c not in all_null]
    pd.testing.assert_frame_equal(new_attr[strict], old_attr[strict])

    import pyarrow.parquet as pq

    meta = pq.ParquetFile(state_dir / "parcels_attr.parquet").metadata
    from preprocess.facets import ROW_GROUP_SIZE

    assert all(meta.row_group(i).num_rows <= ROW_GROUP_SIZE for i in range(meta.num_row_groups))
    assert meta.row_group(0).column(0).compression == "ZSTD"

    produced = {k: v for k, v in produced_facets.items() if k != "state_fips"}
    assert _canon_facets(produced) == _canon_facets(legacy_facets)


def test_facets_equivalence_via_compose(fixture_dirs, registered_normalizers, tmp_path):
    """Full compose then the DuckDB build_facets vs the frozen legacy
    engine over the same composite shards."""
    from preprocess.compose import ComposeConfig, compose
    from preprocess.facets import build_facets

    compose(ComposeConfig(state=STATE))
    comp_root = fixture_dirs["composite"]
    build_facets("05", composite_root=comp_root)

    state_dir = comp_root / "05"
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()

    produced = json.loads((state_dir / "facets.json").read_text())
    _assert_facets_outputs_equivalent(state_dir, legacy_dir, produced)
    # Not vacuous: 8 fixture parcels, sorted by score, county facet present.
    assert produced["total"] == 8
    assert {p["value"] for p in produced["categorical"]["county_fips"]} == {
        "05001",
        "05003",
        "05005",
        "05007",
    }


def test_facets_equivalence_synthetic_edges(tmp_path, monkeypatch):
    """Sharded state with schema variance, score ties across shards,
    blank/None categorical values, and a None numeric value."""
    from preprocess.facets import build_facets

    state_dir = tmp_path / "comp" / "42"
    shards = state_dir / "parcels"
    shards.mkdir(parents=True)

    s1 = pd.DataFrame(
        {
            "parcel_id_full": ["A1", "A2", "A3"],
            "owner_kind": ["llc", "", None],
            "land_use_desc": ["Vacant", "Vacant", "Farm"],
            "county_fips": ["42001", "42001", "42003"],
            "assessed_value": [10.0, None, 30.0],
            "interestingness_score": [0.5, 0.5, 0.9],  # tie inside the shard
            "owner_cluster_size": [1, 2, 3],
            # All-null in every shard → arrow `null` type in the source; the
            # real-data MT check caught the dtype drift this causes (engines
            # must both round-trip it to pandas object).
            "situs_state": [None, None, None],
            "geometry": [b"x", b"y", b"z"],
            "_internal": ["d", "d", "d"],
        }
    )
    s2 = pd.DataFrame(
        {
            # land_use_desc missing entirely → NULLs in the slim parquet;
            # only_in_b present only here → excluded from the slim parquet.
            "parcel_id_full": ["B1", "B2"],
            "owner_kind": ["trust", "llc"],
            "county_fips": ["42003", "42005"],
            "assessed_value": [40.0, 50.0],
            "interestingness_score": [0.5, 1.2],  # 0.5 ties across shards
            "owner_cluster_size": [4, 5],
            "situs_state": [None, None],
            "geometry": [b"x", b"y"],
            "only_in_b": ["zzz", "zzz"],
        }
    )
    s1.to_parquet(shards / "s1.parquet", index=False)
    s2.to_parquet(shards / "s2.parquet", index=False)

    build_facets("42", composite_root=tmp_path / "comp")
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    produced = json.loads((state_dir / "facets.json").read_text())
    _assert_facets_outputs_equivalent(state_dir, legacy_dir, produced)

    attr = pd.read_parquet(state_dir / "parcels_attr.parquet")
    assert "geometry" not in attr.columns and "_internal" not in attr.columns
    assert "only_in_b" not in attr.columns
    assert list(attr["parcel_id_full"]) == ["B2", "A3", "A1", "A2", "B1"]  # ties in file order
    assert attr["land_use_desc"].isna().tolist() == [True, False, False, False, True]
    # Blank/None owner_kind dropped from the facet; counts correct.
    kinds = {p["value"]: p["count"] for p in produced["categorical"]["owner_kind"]}
    assert kinds == {"llc": 2, "trust": 1}
    assert produced["numeric"]["assessed_value"] == {"min": 10.0, "max": 50.0}


def test_facets_equivalence_single_file_layout(tmp_path):
    """The legacy single-file parcels.parquet layout still builds and
    matches the frozen engine."""
    from preprocess.facets import build_facets

    state_dir = tmp_path / "comp" / "43"
    state_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "parcel_id_full": ["C1", "C2"],
            "owner_kind": ["llc", "individual"],
            "county_fips": ["43001", "43001"],
            "assessed_value": [5.0, 15.0],
            "interestingness_score": [0.2, 0.7],
            "owner_cluster_size": [1, 1],
            "geometry": [b"x", b"y"],
        }
    ).to_parquet(state_dir / "parcels.parquet", index=False)

    build_facets("43", composite_root=tmp_path / "comp")
    legacy_dir = tmp_path / "legacy"
    legacy_dir.mkdir()
    produced = json.loads((state_dir / "facets.json").read_text())
    _assert_facets_outputs_equivalent(state_dir, legacy_dir, produced)
    attr = pd.read_parquet(state_dir / "parcels_attr.parquet")
    assert list(attr["parcel_id_full"]) == ["C2", "C1"]


# ═══ Stage 5: owners-index input scan ══════════════════════════════════════
#
# Equivalence definition (fixed before the migration):
#
# 1. **The contract is the final document** — build_owners_index over the
#    same composite root must produce an identical dict (generated_at
#    excluded) whether the per-state Lead-universe scan runs through the
#    legacy full-width pandas read + mask or the DuckDB predicate-pushdown
#    scan. That covers row content, scan order (file order per state, so
#    score-tie owner ordering is reproduced), per-state column presence
#    (INDEX_INPUT_COLUMNS ∩ available), null structure flags ≡ False, and
#    a state with no structure-bearing rows staying out of `states`.
# 2. **The resolver is shared, not frozen** — CrossStateOwnerResolver and
#    its recipes (mode-based names, holdings/JSON assembly, mailing pick)
#    stay in pandas/Python; only the scan that feeds it changed engines.
# 3. Schema version (v5) and both output filenames are untouched.


def _legacy_read_state_parcels(state_dir):
    """Frozen legacy Lead-universe scan (owners_index.py @ 04ad69a,
    verbatim semantics): full-width column-projected pandas read, then
    the has_tower/has_solar mask."""
    from preprocess.owners_index import INDEX_INPUT_COLUMNS, pq_columns

    attr = state_dir / "parcels_attr.parquet"
    if not attr.exists():
        return pd.DataFrame()
    cols = pq_columns(attr)
    wanted = [c for c in INDEX_INPUT_COLUMNS if c in cols]
    df = pd.read_parquet(attr, columns=wanted)
    has_tower = df.get("has_tower", False)
    has_solar = df.get("has_solar", False)
    mask = pd.Series(has_tower, index=df.index).fillna(False).astype(bool) | pd.Series(
        has_solar, index=df.index
    ).fillna(False).astype(bool)
    return df[mask].copy()


def _build_owners_index_with(reader, root, alpha=None):
    """build_owners_index with the per-state scan swapped in — the rest of
    the driver (state iteration, towers enrichment, resolver) is the live
    shared code, per criterion 2."""
    from preprocess import owners_index as oi

    kwargs = {} if alpha is None else {"alpha": alpha}
    real = oi._read_state_parcels
    oi._read_state_parcels = reader
    try:
        return oi.build_owners_index(root, **kwargs)
    finally:
        oi._read_state_parcels = real


def _strip_generated_at(index: dict) -> dict:
    out = dict(index)
    out.pop("generated_at", None)
    return out


def test_owners_index_equivalence_via_compose(fixture_dirs, registered_normalizers):
    """compose → facets → owners index, with the legacy scan vs the DuckDB
    scan feeding the same shared resolver."""
    from preprocess.compose import ComposeConfig, compose
    from preprocess.facets import build_facets
    from preprocess.owners_index import _read_state_parcels, build_owners_index

    compose(ComposeConfig(state=STATE))
    comp_root = fixture_dirs["composite"]
    build_facets("05", composite_root=comp_root)

    new_index = build_owners_index(comp_root)
    legacy_index = _build_owners_index_with(_legacy_read_state_parcels, comp_root)
    assert _strip_generated_at(new_index) == _strip_generated_at(legacy_index)

    # Not vacuous: the Lead universe is the two tower-bearing parcels
    # (A001 + B003), each its own owner → two Leads with one holding each.
    assert new_index["states"] == ["05"]
    assert new_index["count"] == 2
    by_name = {o["owner_name"]: o for o in new_index["owners"]}
    assert set(by_name) == {"SHARED LANDOWNER LLC", "EVE LLC"}
    for o in new_index["owners"]:
        assert o["tower_count"] == 1
        assert len(o["holdings"]) == 1
        assert o["holdings"][0]["structures"][0]["type"] == "tower"

    # The scan itself: only structure-bearing rows surface into pandas.
    lead_rows = _read_state_parcels(comp_root / "05")
    assert len(lead_rows) == 2


def test_owners_index_scan_edge_cases(tmp_path):
    """Direct scan equivalence on hand-built parcels_attr files: null
    flags, a missing has_solar column, no flag columns at all, and a
    state with zero structure-bearing rows."""
    from preprocess.owners_index import _read_state_parcels

    def write_attr(dirname, df):
        d = tmp_path / dirname
        d.mkdir()
        df.to_parquet(d / "parcels_attr.parquet", index=False)
        return d

    s_nulls = write_attr(
        "nulls",
        pd.DataFrame(
            {
                "owner_name": ["A", "B", "C", "D"],
                "owner_name_norm": ["A", "B", "C", "D"],
                "state_fips": ["05"] * 4,
                "has_tower": pd.array([True, None, False, None], dtype="boolean"),
                "has_solar": pd.array([None, True, None, False], dtype="boolean"),
                "tower_count": [1, 0, 0, 0],
            }
        ),
    )
    s_no_solar_col = write_attr(
        "nosolar",
        pd.DataFrame(
            {
                "owner_name": ["E", "F"],
                "owner_name_norm": ["E", "F"],
                "state_fips": ["05", "05"],
                "has_tower": [False, True],
                "tower_count": [0, 2],
            }
        ),
    )
    s_no_flags = write_attr(
        "noflags",
        pd.DataFrame({"owner_name": ["G"], "owner_name_norm": ["G"], "state_fips": ["05"]}),
    )
    s_empty_universe = write_attr(
        "emptyuni",
        pd.DataFrame(
            {
                "owner_name": ["H"],
                "owner_name_norm": ["H"],
                "state_fips": ["05"],
                "has_tower": [False],
                "has_solar": [False],
            }
        ),
    )

    for d in (s_nulls, s_no_solar_col, s_no_flags, s_empty_universe):
        new = _read_state_parcels(d)
        old = _legacy_read_state_parcels(d)
        assert len(new) == len(old)
        if len(old) > 0:
            assert list(new.columns) == list(old.columns)
            assert new["owner_name"].tolist() == old["owner_name"].tolist()
    assert _read_state_parcels(s_nulls)["owner_name"].tolist() == ["A", "B"]
    assert _read_state_parcels(s_no_solar_col)["owner_name"].tolist() == ["F"]
    assert len(_read_state_parcels(s_no_flags)) == 0
    assert len(_read_state_parcels(s_empty_universe)) == 0
    # Missing file → empty frame, like legacy.
    assert len(_read_state_parcels(tmp_path / "absent")) == 0
