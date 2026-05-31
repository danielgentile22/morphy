"""Tests for the hybrid ULS↔ASR join (#24, Slice A).

Covers the three #11-calibrated confidence paths (verified cross-ref, likely
≤ 100 m, possible 100-500 m), the > 500 m refusal, dedup of the same
(carrier, callsign) reached two ways (best tag wins), the #22 brand rollup
(incl. the kept unmapped tail), the FAA-tower cross-ref exclusion, the empty
list for an unmatched tower, the parquet round-trip of the list-of-struct, and
the summary.json coverage block.

Fixtures are tiny inline frames; no network or large raw data is touched.
Distances are realised through the join's own EPSG:5070 projection — the
latitude offsets below sit comfortably inside their tier with margin to spare.
"""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd
import pytest

# Force registration of every Join.
from preprocess import registry  # noqa: F401
from preprocess.base import ComposeContext, all_joins
from preprocess.io import write_geoparquet
from preprocess.joins.uls_to_asr import (
    UlsToAsrJoin,
    carrier_coverage_summary,
    load_uls_licenses,
)
from shapely.geometry import Point

# Towers spaced 0.1° (~11 km) apart so each spatial test location has an
# unambiguous nearest tower. (name, asr_number, _source, lat, lon)
_TOWERS = [
    ("T_verified", "1000001", "fcc_asr", 34.70, -92.30),
    ("T_likely", "1000002", "fcc_asr", 34.80, -92.30),
    ("T_possible", "1000003", "fcc_asr", 34.90, -92.30),
    ("T_dedup", "1000004", "fcc_asr", 35.00, -92.30),
    ("T_far", "1000005", "fcc_asr", 35.10, -92.30),
    ("T_empty", "1000099", "fcc_asr", 35.20, -92.30),
    # Same asr_number as T_verified but an FAA structure, parked far away:
    # cross-ref must ignore it (FAA study numbers aren't FCC registrations)
    # and it is too distant for any spatial match → stays empty.
    ("T_faa", "1000001", "faa_oeaaa", 40.00, -100.00),
]

_LIKELY_OFF = 0.0005  # ~55 m  → likely
_POSSIBLE_OFF = 0.0030  # ~333 m → possible

# (usi, callsign, asr_number, lat, lon)
_LOCATIONS = [
    ("V1", "KNKA001", "1000001", 34.70, -92.30),  # verified → AT&T
    ("L1", "KNKB002", None, 34.80 + _LIKELY_OFF, -92.30),  # likely → Verizon
    ("P1", "KNKC003", None, 34.90 + _POSSIBLE_OFF, -92.30),  # possible → T-Mobile
    ("N1", "KNKD004", None, 37.00, -95.00),  # > 500 m from all → no match
    ("D1", "KNKE005", "1000004", 35.00, -92.30),  # verified → Verizon (T_dedup)
    ("D2", "KNKE005", None, 35.00 + _LIKELY_OFF, -92.30),  # likely → Verizon (dedup w/ D1)
    ("F1", "KNKF006", "1000005", 35.10, -92.30),  # verified → unmapped tail (T_far)
]

# usi → (licensee_name, expired_date)
_LICENSE = {
    "V1": ("New Cingular Wireless PCS, LLC", "2030-01-01"),
    "L1": ("Cellco Partnership", None),
    "P1": ("T-Mobile US, Inc.", "2031-06-30"),
    "N1": ("Cellco Partnership", None),
    "D1": ("Verizon Wireless", "2029-12-31"),
    "D2": ("Cellco Partnership", None),
    "F1": ("Podunk Rural Telephone Cooperative", "2028-01-01"),
}


def _towers_gdf() -> gpd.GeoDataFrame:
    rows = [
        {
            "name": name,
            "asr_number": asr,
            "_source": src,
            "lat": lat,
            "lon": lon,
            "extras": {},
            "geometry": Point(lon, lat),
        }
        for name, asr, src, lat, lon in _TOWERS
    ]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def _locations_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "usi": usi,
                "callsign": cs,
                "asr_number": asr,
                "lat": lat,
                "lon": lon,
                "coord_status": "ok",
            }
            for usi, cs, asr, lat, lon in _LOCATIONS
        ]
    )


def _license_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"usi": usi, "licensee_name": name, "expired_date": exp}
            for usi, (name, exp) in _LICENSE.items()
        ]
    )


def _run() -> gpd.GeoDataFrame:
    """Apply the join to the full fixture; return towers indexed by name."""
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    ctx.set("tower", _towers_gdf())
    ctx.set("location", _locations_df())
    ctx.set("license", _license_df())  # injected → takes precedence over disk
    UlsToAsrJoin().apply(ctx)
    return ctx.get("tower").set_index("name")


# ── confidence paths ────────────────────────────────────────────────────────


def test_verified_cross_ref_and_brand_rollup():
    out = _run()
    carriers = out.loc["T_verified", "carriers"]
    assert len(carriers) == 1
    e = carriers[0]
    assert e["carrier_name"] == "AT&T"  # #22 brand rollup applied
    assert e["callsign"] == "KNKA001"
    assert e["confidence_tag"] == "verified"
    assert e["license_expiry"] == "2030-01-01"


def test_likely_spatial_within_100m():
    out = _run()
    carriers = out.loc["T_likely", "carriers"]
    assert len(carriers) == 1
    assert carriers[0]["carrier_name"] == "Verizon"
    assert carriers[0]["confidence_tag"] == "likely"


def test_possible_spatial_100_to_500m():
    out = _run()
    carriers = out.loc["T_possible", "carriers"]
    assert len(carriers) == 1
    assert carriers[0]["carrier_name"] == "T-Mobile"
    assert carriers[0]["confidence_tag"] == "possible"


def test_beyond_500m_is_refused():
    out = _run()
    # The N1 location is > 500 m from every tower, so no tower picks it up.
    assert all(
        not any(c["callsign"] == "KNKD004" for c in carriers) for carriers in out["carriers"]
    )


def test_dedup_keeps_best_tag():
    # (Verizon, KNKE005) reachable via verified (D1) and likely (D2) → one
    # entry, the verified tag (and its expiry) winning.
    out = _run()
    carriers = out.loc["T_dedup", "carriers"]
    assert len(carriers) == 1
    assert carriers[0]["carrier_name"] == "Verizon"
    assert carriers[0]["confidence_tag"] == "verified"
    assert carriers[0]["license_expiry"] == "2029-12-31"


def test_unmapped_licensee_kept_with_raw_name():
    # Presence over brand recognition: the tail licensee stays, raw-named.
    out = _run()
    carriers = out.loc["T_far", "carriers"]
    assert len(carriers) == 1
    assert carriers[0]["carrier_name"] == "Podunk Rural Telephone Cooperative"
    assert carriers[0]["confidence_tag"] == "verified"


def test_unmatched_tower_gets_empty_list():
    out = _run()
    assert out.loc["T_empty", "carriers"] == []


def test_faa_tower_excluded_from_cross_ref():
    # T_faa shares asr_number "1000001" with T_verified but is an FAA
    # structure parked far away → never cross-reffed, never near a location.
    out = _run()
    assert out.loc["T_faa", "carriers"] == []


def test_spatial_fallback_ignores_faa_towers():
    # An FAA structure co-located with an FCC ASR tower must not steal the
    # spatial match: #11's tolerances are calibrated for ULS↔ASR only.
    towers = gpd.GeoDataFrame(
        [
            {
                "name": "ASR",
                "asr_number": "2000001",
                "_source": "fcc_asr",
                "geometry": Point(-93.0, 36.0),
            },
            {
                "name": "FAA",
                "asr_number": "000777",
                "_source": "faa_oeaaa",
                "geometry": Point(-93.0, 36.0),
            },
        ],
        geometry="geometry",
        crs="EPSG:4326",
    )
    loc = pd.DataFrame(
        [
            {
                "usi": "S1",
                "callsign": "KX1",
                "asr_number": None,
                "lat": 36.0 + _LIKELY_OFF,
                "lon": -93.0,
                "coord_status": "ok",
            }
        ]
    )
    lic = pd.DataFrame([{"usi": "S1", "licensee_name": "Cellco Partnership", "expired_date": None}])
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    ctx.set("tower", towers)
    ctx.set("location", loc)
    ctx.set("license", lic)
    UlsToAsrJoin().apply(ctx)
    out = ctx.get("tower").set_index("name")
    assert out.loc["ASR", "carriers"][0]["carrier_name"] == "Verizon"
    assert out.loc["ASR", "carriers"][0]["confidence_tag"] == "likely"
    assert out.loc["FAA", "carriers"] == []


# ── schema / robustness ───────────────────────────────────────────────────


def test_every_tower_has_a_carriers_list():
    out = _run()
    assert "carriers" in out.columns
    assert all(isinstance(v, list) for v in out["carriers"])


def test_no_locations_no_ops_to_empty_lists():
    ctx = ComposeContext(state_fips="05", state_name="Arkansas", state_abbr="AR")
    ctx.set("tower", _towers_gdf())
    UlsToAsrJoin().apply(ctx)
    out = ctx.get("tower")
    assert "carriers" in out.columns
    assert all(v == [] for v in out["carriers"])


def test_carriers_survive_parquet_round_trip(tmp_path):
    out = _run()
    gdf = out.reset_index()
    path = tmp_path / "towers.parquet"
    write_geoparquet(gdf, path)
    back = gpd.read_parquet(path).set_index("name")
    # The writer JSON-encodes list/dict columns (same as extras / distress).
    decoded = json.loads(back.loc["T_verified", "carriers"])
    assert decoded == out.loc["T_verified", "carriers"]
    assert json.loads(back.loc["T_empty", "carriers"]) == []


# ── coverage summary (the #24 acceptance gate metric) ─────────────────────


def test_coverage_summary():
    out = _run().reset_index()
    cov = carrier_coverage_summary(out)
    assert cov["computed"] is True
    assert cov["asr_towers"] == 6  # six fcc_asr towers
    assert cov["asr_towers_with_carrier"] == 5  # all but T_empty
    assert cov["coverage_pct"] == pytest.approx(83.3, abs=0.1)
    assert cov["by_confidence"] == {"verified": 3, "likely": 1, "possible": 1}
    assert cov["all_towers"] == 7  # includes the FAA structure
    assert cov["all_towers_with_carrier"] == 5


def test_coverage_summary_handles_missing_column():
    cov = carrier_coverage_summary(_towers_gdf())  # no carriers column yet
    assert cov == {"computed": False}


# ── registration + disk license loader ────────────────────────────────────


def test_join_is_registered():
    names = {j.name for j in all_joins()}
    assert "UlsToAsrJoin" in names


def test_load_uls_licenses_reads_band_parquets(tmp_path, monkeypatch):
    import preprocess

    band_dir = tmp_path / "fcc_uls_cellular"
    band_dir.mkdir()
    pd.DataFrame(
        {
            "usi": ["1", "1", "2"],  # duplicate usi → deduped
            "licensee_name": ["AT&T Mobility LLC", "AT&T Mobility LLC", "Cellco Partnership"],
            "expired_date": ["2030-01-01", "2030-01-01", None],
        }
    ).to_parquet(band_dir / "license.parquet", index=False)
    monkeypatch.setattr(preprocess, "NORMALIZED_ROOT", tmp_path)

    lic = load_uls_licenses()
    assert list(lic.columns) == ["usi", "licensee_name", "expired_date"]
    assert len(lic) == 2  # deduped on usi
    assert set(lic["usi"]) == {"1", "2"}
