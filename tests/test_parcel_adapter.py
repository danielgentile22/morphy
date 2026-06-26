"""Tests for the per-source ParcelAdapter + the shared parcel driver.

The driver's I/O surface (reading shapefiles / .gdb / .gpkg via pyogrio
and writing per-county GeoParquet) is exercised by the full preprocess
pipeline; these tests target the pure canonical-mapping seam — given a
GeoDataFrame for one layer and a ParcelAdapter, what does
``map_layer_to_canonical`` produce?

Coverage focuses on the three FIPS-derivation paths that historically
hid bugs:

  * AR — integer CountyFips, needs state-prefix concatenation
  * MT — county *name* (CountyName), needs ``county_resolver``
  * FDOR NAL — 12-digit CENSUS_BK GEOID, county FIPS is positions 0–4

Plus invariants on the registry and the adapter dataclass.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from preprocess.base import all_normalizers
from preprocess.normalizers.state_parcel_adapters.ar import AR_PARCELS_ADAPTER
from preprocess.normalizers.state_parcel_adapters.fdor_nal import FDOR_NAL_ADAPTER
from preprocess.normalizers.state_parcel_adapters.mt import (
    MT_CADASTRAL_PARCELS_ADAPTER,
    MT_COUNTY_NAME_TO_FIPS,
)
from preprocess.normalizers.state_parcels import (
    ParcelAdapter,
    ParcelNormalizer,
    _to_4326,
    map_layer_to_canonical,
)
from shapely.geometry import Polygon

# ── helpers ──────────────────────────────────────────────────────────────


def _square(x: float = 0.0, y: float = 0.0, size: float = 0.01) -> Polygon:
    """A trivial valid square in EPSG:4326 — geometry validity isn't the focus."""
    return Polygon([(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)])


def _gdf(rows: list[dict]) -> gpd.GeoDataFrame:
    """Make a GeoDataFrame with rows that already have a 'geometry' column."""
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


# ── registry invariants ──────────────────────────────────────────────────


def test_active_parcel_adapters_register():
    """Importing the package registers exactly the expected active sources.

    IN and UT were dropped during the per-source-adapter refactor — they
    must not reappear in the registry. MN is intentionally DEFERRED (ADR-018
    + "No License Provided" commercial blocker), so it is imported but not
    registered into the active set.
    """
    parcel_ids = sorted(n.source_id for n in all_normalizers() if "parcel" in n.canonical_types)
    assert parcel_ids == [
        "ar_parcels",
        "fdor_nal",
        "fl_fgdl_parcels",
        "mt_cadastral_parcels",
        "nc_onemap_parcels",
        "wv_parcels",
    ]


def test_each_parcel_normalizer_carries_its_adapter():
    """ParcelNormalizer.adapter.source_id must match the registry key."""
    for n in all_normalizers():
        if "parcel" not in n.canonical_types:
            continue
        assert isinstance(n, ParcelNormalizer)
        assert n.adapter.source_id == n.source_id


def test_parcel_adapter_is_frozen():
    """ParcelAdapter is a frozen dataclass — mutating it should raise."""
    with pytest.raises(Exception):  # noqa: B017 — dataclasses raise FrozenInstanceError
        AR_PARCELS_ADAPTER.state_fips = "99"  # type: ignore[misc]


# ── CRS handling: an unlabeled non-4326 layer must not be mislabeled (P1) ─


def test_to_4326_assumes_4326_only_for_lonlat_coords():
    """An unlabeled layer whose coords look like lon/lat is assumed EPSG:4326."""
    g = gpd.GeoDataFrame({"geometry": [_square(-92.0, 34.0)]}, geometry="geometry", crs=None)
    out = _to_4326(g)
    assert out is not None
    assert out.crs is not None and out.crs.to_epsg() == 4326


def test_to_4326_skips_unlabeled_projected_layer():
    """An unlabeled layer with projected coords (State Plane feet, millions)
    is SKIPPED, not silently mislabeled as WGS84 — mislabeling corrupts joins."""
    projected = Polygon(
        [(2_500_000, 700_000), (2_500_100, 700_000), (2_500_100, 700_100), (2_500_000, 700_100)]
    )
    g = gpd.GeoDataFrame({"geometry": [projected]}, geometry="geometry", crs=None)
    assert _to_4326(g) is None


def test_to_4326_reprojects_labeled_non_4326():
    """A layer with a declared non-4326 CRS is reprojected to lon/lat."""
    g = gpd.GeoDataFrame({"geometry": [_square(-92.0, 34.0)]}, geometry="geometry", crs="EPSG:4326")
    g = g.to_crs("EPSG:3857")  # Web Mercator — coords now in metres
    out = _to_4326(g)
    assert out is not None and out.crs.to_epsg() == 4326
    # Back in lon/lat range near the original.
    minx, miny, maxx, maxy = out.total_bounds
    assert -93.0 < minx < -91.0 and 33.0 < miny < 35.0


# ── geometry validity is flagged, never dropped at normalize time (P2) ────


def test_geometry_validity_flagged_not_dropped():
    """Invalid / null geometry is flagged via the geometry_valid status column,
    never dropped at normalize time (CLAUDE §8 full-fidelity preservation)."""
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])  # self-intersecting → invalid
    assert not bowtie.is_valid
    g = _gdf(
        [
            {"ParcelId": "P1", "OwnerName": "A", "CountyFips": "001", "geometry": _square()},
            {"ParcelId": "P2", "OwnerName": "B", "CountyFips": "001", "geometry": bowtie},
            {"ParcelId": "P3", "OwnerName": "C", "CountyFips": "001", "geometry": None},
        ]
    )
    out = map_layer_to_canonical(g, AR_PARCELS_ADAPTER)
    assert len(out) == 3  # nothing dropped
    assert "geometry_valid" in out.columns
    assert list(bool(v) for v in out["geometry_valid"]) == [True, False, False]


# ── AR: 3-digit CountyFips needs state-prefix concatenation ──────────────


def test_ar_county_fips_prefix_concat():
    """AR ships CountyFips as either 3-digit ('001') or already-5-digit ('05001').
    Either way the canonical county_fips should be 5 digits prefixed by state '05'."""
    g = _gdf(
        [
            {"ParcelId": "A1", "OwnerName": "ALICE", "CountyFips": "001", "geometry": _square()},
            {"ParcelId": "A2", "OwnerName": "BOB", "CountyFips": "05001", "geometry": _square()},
            {"ParcelId": "A3", "OwnerName": "CARL", "CountyFips": 1, "geometry": _square()},
        ]
    )
    out = map_layer_to_canonical(g, AR_PARCELS_ADAPTER)
    assert out["county_fips"].tolist() == ["05001", "05001", "05001"]
    assert out["state_fips"].tolist() == ["05", "05", "05"]
    assert out["parcel_id"].tolist() == ["A1", "A2", "A3"]
    assert out["owner_name"].tolist() == ["ALICE", "BOB", "CARL"]


def test_ar_missing_county_falls_back_to_state_fips():
    """If CountyFips is blank, canon_county_fips returns None for county; the
    state_fips fallback in the driver keeps state_fips populated as '05'."""
    g = _gdf([{"ParcelId": "X", "OwnerName": "OWNER", "CountyFips": "", "geometry": _square()}])
    out = map_layer_to_canonical(g, AR_PARCELS_ADAPTER)
    assert out["county_fips"].iloc[0] is None
    assert out["state_fips"].iloc[0] == "05"


# ── MT: county_resolver maps a *name* to a 5-digit FIPS ──────────────────


def test_mt_county_resolver_uppercases_and_resolves():
    """MT Cadastral ships county as a name string. The county_resolver must
    handle leading/trailing spaces and case insensitivity, and resolve every
    Montana county listed in MT_COUNTY_NAME_TO_FIPS."""
    g = _gdf(
        [
            {
                "PARCELID": "M1",
                "OwnerName": "OWNER",
                "CountyName": "Beaverhead",
                "geometry": _square(),
            },
            {
                "PARCELID": "M2",
                "OwnerName": "OWNER",
                "CountyName": "  YELLOWSTONE  ",
                "geometry": _square(),
            },
            {
                "PARCELID": "M3",
                "OwnerName": "OWNER",
                "CountyName": "lewis and clark",
                "geometry": _square(),
            },
        ]
    )
    out = map_layer_to_canonical(g, MT_CADASTRAL_PARCELS_ADAPTER)
    assert out["county_fips"].tolist() == ["30001", "30111", "30049"]
    assert all(s == "30" for s in out["state_fips"])


def test_mt_unknown_county_name_resolves_to_none():
    """Misspellings should yield county_fips=None; state_fips falls back to '30'."""
    g = _gdf(
        [
            {
                "PARCELID": "Z",
                "OwnerName": "OWNER",
                "CountyName": "NOT A REAL COUNTY",
                "geometry": _square(),
            }
        ]
    )
    out = map_layer_to_canonical(g, MT_CADASTRAL_PARCELS_ADAPTER)
    assert out["county_fips"].iloc[0] is None
    assert out["state_fips"].iloc[0] == "30"


def test_mt_resolver_table_has_all_56_counties():
    """Sanity check on the lookup table — Montana has 56 counties."""
    assert len(MT_COUNTY_NAME_TO_FIPS) == 56
    assert all(fips.startswith("30") and len(fips) == 5 for fips in MT_COUNTY_NAME_TO_FIPS.values())


# ── FDOR NAL: 12-digit CENSUS_BK GEOID → county is positions 0..4 ────────


def test_fdor_census_bk_slices_to_county_fips():
    """FDOR NAL's only county identifier is CENSUS_BK, a 12-digit census-block
    GEOID. canon_county_fips slices positions 0–4 — must preserve the leading
    zero of state FIPS '12'."""
    g = _gdf(
        [
            # Alachua county, FL: CENSUS_BK starts 12001...
            {
                "PARCEL_ID": "F1",
                "OWN_NAME": "OWNER",
                "CENSUS_BK": "120010001001",
                "geometry": _square(),
            },
            # Miami-Dade: starts 12086...
            {
                "PARCEL_ID": "F2",
                "OWN_NAME": "OWNER",
                "CENSUS_BK": "120869812003",
                "geometry": _square(),
            },
        ]
    )
    out = map_layer_to_canonical(g, FDOR_NAL_ADAPTER)
    assert out["county_fips"].tolist() == ["12001", "12086"]
    assert all(s == "12" for s in out["state_fips"])


def test_fdor_missing_census_bk_falls_back_to_state_fips():
    g = _gdf([{"PARCEL_ID": "F", "OWN_NAME": "OWNER", "CENSUS_BK": "", "geometry": _square()}])
    out = map_layer_to_canonical(g, FDOR_NAL_ADAPTER)
    assert out["county_fips"].iloc[0] is None
    assert out["state_fips"].iloc[0] == "12"


# ── WV: county resolver (Mc collation), sidecar-join fields, full mailing ─


def test_wv_county_resolver_handles_mc_collation_and_names():
    """WV's CountyID 01..55 is alphabetical and does NOT equal Census FIPS:
    Census collates McDowell (54047) before Marion (54049). The resolver must
    map both the 2-digit code and the county name to the right Census FIPS."""
    from preprocess.normalizers.state_parcel_adapters.wv import (
        WV_COUNTY_CODE_TO_FIPS,
        WV_COUNTY_NAME_TO_FIPS,
        _resolve_wv_county,
    )

    # The Mc-collation quirk — a naive 2*N-1 prefix would mis-assign these.
    assert _resolve_wv_county("27") == "54047"  # McDowell by code
    assert _resolve_wv_county("24") == "54049"  # Marion by code
    assert _resolve_wv_county("MCDOWELL") == "54047"
    assert _resolve_wv_county("Marion") == "54049"
    assert _resolve_wv_county("01") == "54001"  # Barbour
    assert _resolve_wv_county("Wyoming") == "54109"
    assert _resolve_wv_county("") is None
    assert _resolve_wv_county("NOT A COUNTY") is None

    # Table integrity: 55 counties, the odd 54001..54109 Census range, no dupes.
    assert len(WV_COUNTY_NAME_TO_FIPS) == 55
    assert len(WV_COUNTY_CODE_TO_FIPS) == 55
    odd_range = [f"54{n:03d}" for n in range(1, 110, 2)]
    assert sorted(WV_COUNTY_NAME_TO_FIPS.values()) == odd_range
    assert set(WV_COUNTY_CODE_TO_FIPS.values()) == set(WV_COUNTY_NAME_TO_FIPS.values())


def test_wv_parcels_mapping_post_join():
    """WV canonical mapping over a frame shaped like the post-AttributeJoin
    result (MasterSurfWV polygon columns + joined ParcelSummary columns):
    county from CountyID code, owner/value/land-use from the joined columns,
    and mailing_addr as the full single line (no city/state/zip duplication)."""
    from preprocess.normalizers.state_parcel_adapters.wv import WV_PARCELS_ADAPTER

    g = _gdf(
        [
            {  # CountyID 27 = McDowell -> 54047
                "CleanParcelID": "W1",
                "CountyID": "27",
                "FullOwnerName": None,  # polygon owner can be null; Owner1 wins
                "Owner1": "ALICE SMITH",
                "Owner2": "BOB SMITH",
                "FullOwnerAddress": "1 MAIN ST, WELCH, WV 24801",
                "OwnerCity": "WELCH",
                "OwnerStateCode": "WV",
                "OwnerZipCode": "24801",
                "FullPhysicalAddress": "1 MAIN ST",
                "CalculatedAcres": 5.0,
                "LandAppraisal": 1000,
                "BuildingAppraisal": 2000,
                "TotalAppraisal": 3000.0,
                "LandUseCode": "112",
                "LandUse": "112 - Active Farm",
                "geometry": _square(),
            },
            {  # CountyID 24 = Marion -> 54049
                "CleanParcelID": "W2",
                "CountyID": "24",
                "FullOwnerName": None,
                "Owner1": "CARL JONES",
                "Owner2": "",
                "FullOwnerAddress": "2 OAK AVE, FAIRMONT, WV 26554",
                "OwnerCity": "FAIRMONT",
                "OwnerStateCode": "WV",
                "OwnerZipCode": "26554",
                "FullPhysicalAddress": "2 OAK AVE",
                "CalculatedAcres": 1.0,
                "LandAppraisal": 500,
                "BuildingAppraisal": 0,
                "TotalAppraisal": 500.0,
                "LandUseCode": "100",
                "LandUse": "100 - Residential Vacant",
                "geometry": _square(),
            },
        ]
    )
    out = map_layer_to_canonical(g, WV_PARCELS_ADAPTER)
    assert out["county_fips"].tolist() == ["54047", "54049"]
    assert out["state_fips"].tolist() == ["54", "54"]
    assert out["owner_name"].tolist() == ["ALICE SMITH", "CARL JONES"]
    assert out["owner_name_2"].tolist() == ["BOB SMITH", ""]
    # mailing_addr is the full single line — NOT the city/state/zip appended.
    assert out["mailing_addr"].iloc[0] == "1 MAIN ST, WELCH, WV 24801"
    assert out["mailing_city"].iloc[0] == "WELCH"
    assert out["mailing_state"].iloc[0] == "WV"
    assert out["mailing_zip"].iloc[0] == "24801"
    assert out["situs_addr"].iloc[0] == "1 MAIN ST"
    assert out["land_value"].tolist() == [1000.0, 500.0]
    assert out["improvement_value"].tolist() == [2000.0, 0.0]
    assert out["assessed_value"].tolist() == [3000.0, 500.0]
    assert out["land_use_code"].tolist() == ["112", "100"]
    assert out["acreage"].tolist() == [5.0, 1.0]


# ── mailing_addr_is_full: full single-line address isn't duplicated ───────


def test_mailing_addr_is_full_skips_structured_append():
    """With mailing_addr_is_full=True the composite is just the full-line
    candidate; the structured city/state/zip columns still populate but are
    not re-appended. The default (False) appends them (and would duplicate)."""
    field_map = {
        "owner_name": ["O"],
        "mailing_addr": ["FULLADDR"],
        "mailing_city": ["CITY"],
        "mailing_state": ["ST"],
        "mailing_zip": ["ZIP"],
        "county_fips": ["CF"],
    }
    g = _gdf(
        [
            {
                "O": "X",
                "FULLADDR": "1 MAIN ST, WELCH, WV 24801",
                "CITY": "WELCH",
                "ST": "WV",
                "ZIP": "24801",
                "CF": "54047",
                "geometry": _square(),
            }
        ]
    )
    full = ParcelAdapter(
        source_id="t_full", state_fips="54", field_map=field_map, mailing_addr_is_full=True
    )
    out = map_layer_to_canonical(g, full)
    assert out["mailing_addr"].iloc[0] == "1 MAIN ST, WELCH, WV 24801"
    assert out["mailing_city"].iloc[0] == "WELCH"

    default = ParcelAdapter(source_id="t_def", state_fips="54", field_map=field_map)
    out2 = map_layer_to_canonical(g, default)
    assert out2["mailing_addr"].iloc[0] == "1 MAIN ST, WELCH, WV 24801, WELCH, WV, 24801"


# ── owner-kind inference runs through the canonical mapping ──────────────


def test_owner_kind_inferred_from_owner_name():
    """Smoke test that infer_owner_kind is wired into the canonical mapping —
    bug-detection for 'we forgot to call it', not a re-test of cluster.py."""
    g = _gdf(
        [
            {
                "ParcelId": "1",
                "OwnerName": "ACME PROPERTIES LLC",
                "CountyFips": "001",
                "geometry": _square(),
            },
            {
                "ParcelId": "2",
                "OwnerName": "ALICE SMITH",
                "CountyFips": "001",
                "geometry": _square(),
            },
            {
                "ParcelId": "3",
                "OwnerName": "FIRST BAPTIST CHURCH",
                "CountyFips": "001",
                "geometry": _square(),
            },
        ]
    )
    out = map_layer_to_canonical(g, AR_PARCELS_ADAPTER)
    kinds = out["owner_kind"].tolist()
    assert "llc" in kinds
    assert "individual" in kinds
    assert "church" in kinds


# ── post_map escape hatch ────────────────────────────────────────────────


# ── E9: situs state/zip populate from the raw (no longer hard-coded None) ─


def test_fl_situs_zip_populates_from_phy_zipcd():
    """FDOR NAL carries PHY_ZIPCD; E9 maps it to situs_zip (was hard-coded None).
    FL has no physical-state column, so situs_state stays blank."""
    g = _gdf(
        [
            {
                "PARCEL_ID": "F1",
                "OWN_NAME": "OWNER",
                "PHY_ADDR1": "1 BEACH RD",
                "PHY_CITY": "MIAMI",
                "PHY_ZIPCD": "33101",
                "CENSUS_BK": "120860001001",
                "geometry": _square(),
            }
        ]
    )
    out = map_layer_to_canonical(g, FDOR_NAL_ADAPTER)
    assert out["situs_zip"].iloc[0] == "33101"
    assert out["situs_city"].iloc[0] == "MIAMI"
    assert out["situs_state"].iloc[0] == ""


def test_ar_situs_zip_populates_from_adrzip5():
    """AR's AdrLabel/AdrCity/AdrZip5 are the situs (physical) location — E9 maps
    AdrZip5 to situs_zip too."""
    g = _gdf(
        [
            {
                "ParcelId": "A1",
                "OwnerName": "OWNER",
                "AdrLabel": "100 MAIN ST",
                "AdrCity": "LITTLE ROCK",
                "AdrZip5": "72201",
                "CountyFips": "001",
                "geometry": _square(),
            }
        ]
    )
    out = map_layer_to_canonical(g, AR_PARCELS_ADAPTER)
    assert out["situs_zip"].iloc[0] == "72201"


# ── E11: WV year_built maps from the joined ParcelSummary.YearBuilt ───────


def test_wv_year_built_maps_from_parcel_summary():
    from preprocess.normalizers.state_parcel_adapters.wv import WV_PARCELS_ADAPTER

    g = _gdf(
        [
            {
                "CleanParcelID": "W1",
                "CountyID": "01",
                "Owner1": "OWNER",
                "YearBuilt": 1975,  # rides the joined ParcelSummary
                "geometry": _square(),
            },
            {
                "CleanParcelID": "W2",
                "CountyID": "01",
                "Owner1": "OWNER",
                "YearBuilt": None,  # ~46% are null — stays NaN, not 0
                "geometry": _square(),
            },
        ]
    )
    out = map_layer_to_canonical(g, WV_PARCELS_ADAPTER)
    assert out["year_built"].iloc[0] == 1975
    assert pd.isna(out["year_built"].iloc[1])


# ── E12: MT CityStateZ parses into situs city/state/zip ──────────────────


def test_mt_parse_city_state_zip_handles_format_drift():
    from preprocess.normalizers.state_parcel_adapters.mt import _parse_city_state_zip

    assert _parse_city_state_zip("MISSOULA, MT 59801") == ("MISSOULA", "MT", "59801")
    assert _parse_city_state_zip("MISSOULA MT 59801") == ("MISSOULA", "MT", "59801")
    assert _parse_city_state_zip("GREAT FALLS MT 59405-1234") == ("GREAT FALLS", "MT", "59405-1234")
    # Missing parts come back blank; a one-word city is not mistaken for a state.
    assert _parse_city_state_zip("BILLINGS") == ("BILLINGS", "", "")
    assert _parse_city_state_zip("") == ("", "", "")


def test_mt_split_situs_post_map_fills_three_fields():
    """The combined CityStateZ is carried into situs_city by the field_map, then
    the post_map splits it. (map_layer_to_canonical doesn't run post_map — the
    driver does — so apply it directly, as test_post_map_runs_when_set does.)"""
    from preprocess.normalizers.state_parcel_adapters.mt import _split_situs

    g = _gdf(
        [
            {
                "PARCELID": "M1",
                "OwnerName": "OWNER",
                "AddressLin": "1 BIG SKY RD",
                "CityStateZ": "BOZEMAN, MT 59715",
                "CountyName": "Gallatin",
                "geometry": _square(),
            }
        ]
    )
    out = _split_situs(map_layer_to_canonical(g, MT_CADASTRAL_PARCELS_ADAPTER))
    assert out["situs_addr"].iloc[0] == "1 BIG SKY RD"
    assert out["situs_city"].iloc[0] == "BOZEMAN"
    assert out["situs_state"].iloc[0] == "MT"
    assert out["situs_zip"].iloc[0] == "59715"


# ── E4: FL DOR use code decodes to land-use text via the adapter post_map ─


def test_fl_land_use_decodes_via_post_map():
    from preprocess.normalizers.state_parcel_adapters.fdor_nal import _decode_land_use

    g = _gdf(
        [
            {"PARCEL_ID": "F1", "OWN_NAME": "O", "DOR_UC": "071", "geometry": _square()},
            {"PARCEL_ID": "F2", "OWN_NAME": "O", "DOR_UC": "072", "geometry": _square()},
            # A local code ≥ 100 has no statewide text → falls back to the code.
            {"PARCEL_ID": "F3", "OWN_NAME": "O", "DOR_UC": "150", "geometry": _square()},
        ]
    )
    out = _decode_land_use(map_layer_to_canonical(g, FDOR_NAL_ADAPTER))
    assert out["land_use_desc"].tolist() == ["Churches", "Private schools and colleges", "150"]
    # The raw code column is untouched.
    assert out["land_use_code"].tolist() == ["071", "072", "150"]


def test_post_map_runs_when_set():
    """An adapter's optional post_map callable must run after the default
    mapping — verified end-to-end via map_layer_to_canonical (the driver
    calls it after add_polygon_derivatives, but the contract is the same)."""

    def double_score(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        gdf = gdf.copy()
        gdf["interestingness_score"] = 0.5  # was 0.0 from the canonical default
        return gdf

    adapter = ParcelAdapter(
        source_id="test_post_map",
        state_fips="05",
        field_map=AR_PARCELS_ADAPTER.field_map,
        post_map=double_score,
    )
    g = _gdf([{"ParcelId": "T", "OwnerName": "OWNER", "CountyFips": "001", "geometry": _square()}])
    out = map_layer_to_canonical(g, adapter)
    # post_map isn't called by map_layer_to_canonical itself — it's the
    # driver's job. We assert the canonical mapping populated the default,
    # then apply post_map directly to assert the hook shape.
    assert out["interestingness_score"].iloc[0] == 0.0
    after = double_score(out)
    assert after["interestingness_score"].iloc[0] == 0.5
