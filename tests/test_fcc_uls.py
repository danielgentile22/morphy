"""Tests for the FCC ULS normalizer (#12, Slice A).

Covers the band-scoped HD/EN/LO/FR join into canonical license/location/entity
rows, the on-disk reality of two raw files (l_cell + the market bundle), the
radio-service-code → band classification, DMS→decimal coordinates (including
S/W signs + blank/zero handling), asr_number passthrough, and the per-band
quality report.

Fixtures are tiny inline pipe-delimited .dat tables written to tmp_path; no
network or large raw data is touched.
"""

from __future__ import annotations

import json

import pandas as pd
from preprocess.normalizers.fcc_uls import (
    EN_COLS,
    FR_COLS,
    HD_COLS,
    LO_COLS,
    MARKET_BANDS,
    FccUlsCellularNormalizer,
    FccUlsMarketNormalizer,
)

# ── fixture helpers ──────────────────────────────────────────────────────────


def _row(cols: list[str], vals: dict) -> str:
    """Render one pipe-delimited record, blanks for unset columns."""
    cells = {c: "" for c in cols}
    for k, v in vals.items():
        if k not in cells:
            raise KeyError(f"unknown column {k!r}")
        cells[k] = "" if v is None else str(v)
    return "|".join(cells[c] for c in cols)


def _write_dat(path, cols: list[str], rows: list[dict]) -> None:
    path.write_text("\n".join(_row(cols, r) for r in rows) + "\n")


def _write_band_files(dat_dir, *, hd, en, lo, fr) -> None:
    dat_dir.mkdir(parents=True, exist_ok=True)
    _write_dat(dat_dir / "HD.dat", HD_COLS, hd)
    _write_dat(dat_dir / "EN.dat", EN_COLS, en)
    _write_dat(dat_dir / "LO.dat", LO_COLS, lo)
    _write_dat(dat_dir / "FR.dat", FR_COLS, fr)


def _cellular_fixture(raw_dir):
    """A minimal l_cell: two CL licenses, three locations, mixed coords/asr."""
    dat_dir = raw_dir / "fcc_uls_cellular" / "current" / "l_cell"
    hd = [
        dict(
            record_type="HD",
            unique_system_identifier="100",
            call_sign="KAAA111",
            license_status="A",
            radio_service_code="CL",
            grant_date="01/15/2010",
            expired_date="01/15/2030",
        ),
        dict(
            record_type="HD",
            unique_system_identifier="101",
            call_sign="KAAA222",
            license_status="C",
            radio_service_code="CL",
            cancellation_date="02/07/1997",
        ),
    ]
    en = [
        dict(
            record_type="EN",
            unique_system_identifier="100",
            call_sign="KAAA111",
            entity_type="L",
            entity_name="ALPHA CELLULAR LLC",
            frn="0001112223",
            street_address="1 MAIN ST",
            city="LITTLE ROCK",
            state="AR",
            zip_code="72201",
        ),
        dict(
            record_type="EN",
            unique_system_identifier="100",
            call_sign="KAAA111",
            entity_type="CL",
            first_name="John",
            last_name="Doe",
            street_address="1 MAIN ST",
            city="LITTLE ROCK",
            state="AR",
        ),
        dict(
            record_type="EN",
            unique_system_identifier="101",
            call_sign="KAAA222",
            entity_type="L",
            entity_name="BETA TELECOM INC",
            frn="0009998887",
            city="BOZEMAN",
            state="MT",
        ),
    ]
    lo = [
        # usi 100 / loc 1: good AR coords + an ASR number.
        dict(
            record_type="LO",
            unique_system_identifier="100",
            call_sign="KAAA111",
            location_number="1",
            location_address="HILLTOP",
            location_city="LITTLE ROCK",
            location_county="PULASKI",
            location_state="AR",
            ground_elevation="100.0",
            lat_degrees="34",
            lat_minutes="30",
            lat_seconds="0",
            lat_direction="N",
            long_degrees="92",
            long_minutes="15",
            long_seconds="0",
            long_direction="W",
            tower_registration_number="1234567",
            structure_type="GTOWER",
            height_of_support_structure="60.0",
            overall_height_of_structure="62.0",
        ),
        # usi 100 / loc 2: no coordinates, no ASR.
        dict(
            record_type="LO",
            unique_system_identifier="100",
            call_sign="KAAA111",
            location_number="2",
            location_city="CONWAY",
            location_state="AR",
            structure_type="LTOWER",
        ),
        # usi 101 / loc 1: good MT coords + ASR.
        dict(
            record_type="LO",
            unique_system_identifier="101",
            call_sign="KAAA222",
            location_number="1",
            location_state="MT",
            lat_degrees="45",
            lat_minutes="0",
            lat_seconds="0",
            lat_direction="N",
            long_degrees="110",
            long_minutes="0",
            long_seconds="0",
            long_direction="W",
            tower_registration_number="7654321",
            structure_type="MTOWER",
        ),
    ]
    fr = [
        dict(
            record_type="FR",
            unique_system_identifier="100",
            call_sign="KAAA111",
            frequency_assigned="824.04000000",
            frequency_upper_band="834.99000000",
        ),
        dict(
            record_type="FR",
            unique_system_identifier="101",
            call_sign="KAAA222",
            frequency_assigned="1900.00000000",
        ),
    ]
    _write_band_files(dat_dir, hd=hd, en=en, lo=lo, fr=fr)
    return raw_dir / "fcc_uls_cellular" / "current"


def _market_fixture(raw_dir):
    """A minimal l_market: in-scope PCS/AWS/700 plus out-of-scope WCS/600/NB-PCS."""
    dat_dir = raw_dir / "fcc_uls_market" / "current" / "l_market"
    hd = [
        dict(
            record_type="HD",
            unique_system_identifier="200",
            call_sign="WPCS001",
            license_status="A",
            radio_service_code="CW",
        ),  # PCS
        dict(
            record_type="HD",
            unique_system_identifier="201",
            call_sign="WAWS001",
            license_status="A",
            radio_service_code="AW",
        ),  # AWS-1
        dict(
            record_type="HD",
            unique_system_identifier="202",
            call_sign="W700001",
            license_status="A",
            radio_service_code="WY",
        ),  # 700 Lower
        dict(
            record_type="HD",
            unique_system_identifier="203",
            call_sign="WWCS001",
            license_status="A",
            radio_service_code="WS",
        ),  # WCS — deferred
        dict(
            record_type="HD",
            unique_system_identifier="204",
            call_sign="WNBP001",
            license_status="A",
            radio_service_code="CN",
        ),  # Narrowband PCS — excluded
        dict(
            record_type="HD",
            unique_system_identifier="205",
            call_sign="W600001",
            license_status="A",
            radio_service_code="WT",
        ),  # 600 MHz — excluded
        dict(
            record_type="HD",
            unique_system_identifier="206",
            call_sign="WAWS002",
            license_status="A",
            radio_service_code="AH",
        ),  # AWS H-block
    ]
    en = [
        dict(
            record_type="EN",
            unique_system_identifier=u,
            call_sign=f"W{u}",
            entity_type="L",
            entity_name=f"CARRIER {u} LLC",
            frn=f"000000{u}",
            state="FL",
        )
        for u in ("200", "201", "202", "203", "204", "205", "206")
    ]
    lo = [
        dict(
            record_type="LO",
            unique_system_identifier="200",
            call_sign="WPCS001",
            location_number="1",
            location_state="FL",
            lat_degrees="28",
            lat_minutes="0",
            lat_seconds="0",
            lat_direction="N",
            long_degrees="81",
            long_minutes="0",
            long_seconds="0",
            long_direction="W",
            tower_registration_number="2000001",
        ),
        dict(
            record_type="LO",
            unique_system_identifier="201",
            call_sign="WAWS001",
            location_number="1",
            location_state="FL",
        ),  # no coords/asr
        dict(
            record_type="LO",
            unique_system_identifier="202",
            call_sign="W700001",
            location_number="1",
            location_state="WV",
            lat_degrees="38",
            lat_minutes="0",
            lat_seconds="0",
            lat_direction="N",
            long_degrees="80",
            long_minutes="0",
            long_seconds="0",
            long_direction="W",
        ),
        # locations for the excluded services should never surface:
        dict(
            record_type="LO",
            unique_system_identifier="203",
            call_sign="WWCS001",
            location_number="1",
            location_state="FL",
            tower_registration_number="9999999",
        ),
        dict(
            record_type="LO",
            unique_system_identifier="206",
            call_sign="WAWS002",
            location_number="1",
            location_state="FL",
        ),
    ]
    fr = [
        dict(
            record_type="FR",
            unique_system_identifier="200",
            call_sign="WPCS001",
            frequency_assigned="1850.00000000",
            frequency_upper_band="1990.00000000",
        ),
    ]
    _write_band_files(dat_dir, hd=hd, en=en, lo=lo, fr=fr)
    return raw_dir / "fcc_uls_market" / "current"


def _read(path):
    return pd.read_parquet(path)


# ── cellular: HD/EN/LO/FR join coherence ─────────────────────────────────────


def test_cellular_join_produces_coherent_triple(tmp_path):
    raw = _cellular_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    result = FccUlsCellularNormalizer().normalize(raw, out)

    lic = _read(out / "license.parquet")
    loc = _read(out / "location.parquet")
    ent = _read(out / "entity.parquet")

    assert result.canonical_types_written == ["license", "location", "entity"]
    assert set(lic["band"]) == {"cellular"}
    assert set(loc["band"]) == {"cellular"}
    assert set(ent["band"]) == {"cellular"}

    # license: two headers, dates parsed, status decoded, licensee + freq joined.
    assert sorted(lic["usi"]) == ["100", "101"]
    r100 = lic[lic["usi"] == "100"].iloc[0]
    assert r100["license_status_desc"] == "Active"
    assert r100["expired_date"] == "2030-01-15"
    assert r100["grant_date"] == "2010-01-15"
    assert r100["licensee_name"] == "ALPHA CELLULAR LLC"
    assert r100["frn"] == "0001112223"
    assert r100["freq_low_mhz"] == 824.04
    assert r100["freq_high_mhz"] == 834.99
    r101 = lic[lic["usi"] == "101"].iloc[0]
    assert r101["license_status_desc"] == "Cancelled"
    assert r101["cancellation_date"] == "1997-02-07"
    # single assigned frequency → low == high
    assert r101["freq_low_mhz"] == 1900.0
    assert r101["freq_high_mhz"] == 1900.0

    # location: every LO row preserved (3), state_fips derived from the abbr.
    assert len(loc) == 3
    assert set(loc[loc["usi"] == "100"]["state_fips"]) == {"05"}
    assert set(loc[loc["usi"] == "101"]["state_fips"]) == {"30"}

    # entity: licensee + contact rows both kept.
    assert len(ent) == 3
    assert set(ent["entity_type"]) == {"L", "CL"}


# ── DMS → decimal, incl. signs + blank/zero handling ─────────────────────────


def test_dms_conversion_and_coord_status(tmp_path):
    raw = _cellular_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    FccUlsCellularNormalizer().normalize(raw, out)
    loc = _read(out / "location.parquet")

    good = loc[(loc["usi"] == "100") & (loc["location_number"] == "1")].iloc[0]
    assert good["coord_status"] == "ok"
    assert abs(good["lat"] - 34.5) < 1e-9  # 34°30' N
    assert abs(good["lon"] - (-92.25)) < 1e-9  # 92°15' W → negative

    missing = loc[(loc["usi"] == "100") & (loc["location_number"] == "2")].iloc[0]
    assert missing["coord_status"] == "missing"
    assert pd.isna(missing["lat"]) and pd.isna(missing["lon"])


def test_dms_south_east_and_null_island(tmp_path):
    """S/W go negative, E/N positive, and (0,0) is treated as missing."""
    dat_dir = tmp_path / "raw" / "fcc_uls_cellular" / "current" / "l_cell"
    hd = [
        dict(
            record_type="HD",
            unique_system_identifier="1",
            call_sign="K1",
            license_status="A",
            radio_service_code="CL",
        )
    ]
    en = [
        dict(
            record_type="EN",
            unique_system_identifier="1",
            call_sign="K1",
            entity_type="L",
            entity_name="X",
        )
    ]
    lo = [
        dict(
            record_type="LO",
            unique_system_identifier="1",
            call_sign="K1",
            location_number="1",
            lat_degrees="10",
            lat_minutes="30",
            lat_seconds="0",
            lat_direction="S",
            long_degrees="20",
            long_minutes="0",
            long_seconds="0",
            long_direction="E",
        ),
        dict(
            record_type="LO",
            unique_system_identifier="1",
            call_sign="K1",
            location_number="2",
            lat_degrees="0",
            lat_minutes="0",
            lat_seconds="0",
            lat_direction="N",
            long_degrees="0",
            long_minutes="0",
            long_seconds="0",
            long_direction="W",
        ),
    ]
    fr = []
    _write_band_files(dat_dir, hd=hd, en=en, lo=lo, fr=fr)

    out = tmp_path / "out"
    FccUlsCellularNormalizer().normalize(tmp_path / "raw" / "fcc_uls_cellular" / "current", out)
    loc = _read(out / "location.parquet")

    south = loc[loc["location_number"] == "1"].iloc[0]
    assert abs(south["lat"] - (-10.5)) < 1e-9  # 10°30' S → negative
    assert abs(south["lon"] - 20.0) < 1e-9  # 20° E → positive
    assert south["coord_status"] == "ok"

    null_island = loc[loc["location_number"] == "2"].iloc[0]
    assert null_island["coord_status"] == "missing"
    assert pd.isna(null_island["lat"])


# ── asr_number passthrough ───────────────────────────────────────────────────


def test_asr_number_passthrough_and_blank(tmp_path):
    raw = _cellular_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    FccUlsCellularNormalizer().normalize(raw, out)
    loc = _read(out / "location.parquet")

    present = loc[(loc["usi"] == "100") & (loc["location_number"] == "1")].iloc[0]
    assert present["asr_number"] == "1234567"
    absent = loc[(loc["usi"] == "100") & (loc["location_number"] == "2")].iloc[0]
    assert pd.isna(absent["asr_number"])
    # column always present, even where no LO row carries one.
    assert "asr_number" in loc.columns


# ── market band classification (in-scope kept, out-of-scope excluded) ────────


def test_market_band_classification(tmp_path):
    raw = _market_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    result = FccUlsMarketNormalizer().normalize(raw, out)

    pcs = _read(out / "pcs" / "license.parquet")
    aws = _read(out / "aws" / "license.parquet")
    band700 = _read(out / "700mhz" / "license.parquet")

    assert sorted(pcs["usi"]) == ["200"]
    assert set(pcs["band"]) == {"pcs"}
    assert sorted(aws["usi"]) == ["201", "206"]  # AW + AH both → aws
    assert set(aws["band"]) == {"aws"}
    assert sorted(band700["usi"]) == ["202"]

    # excluded services never appear in ANY band's output.
    all_usi = set(pcs["usi"]) | set(aws["usi"]) | set(band700["usi"])
    assert {"203", "204", "205"}.isdisjoint(all_usi)  # WCS, NB-PCS, 600 MHz

    # ...nor do their locations (incl. the ASR that WCS row carried).
    pcs_loc = _read(out / "pcs" / "location.parquet")
    aws_loc = _read(out / "aws" / "location.parquet")
    b700_loc = _read(out / "700mhz" / "location.parquet")
    all_asr = (
        set(pcs_loc["asr_number"].dropna())
        | set(aws_loc["asr_number"].dropna())
        | set(b700_loc["asr_number"].dropna())
    )
    assert "9999999" not in all_asr
    assert "2000001" in all_asr

    assert result.canonical_rows == 4  # 1 PCS + 2 AWS + 1 700MHz


def test_market_band_map_excludes_deferred_and_other_services():
    """Guard the scope decision itself: deferred/other codes are not mapped."""
    mapped = set().union(*MARKET_BANDS.values())
    assert "CW" in MARKET_BANDS["pcs"]
    assert {"AW", "AT", "AD", "AH"} <= MARKET_BANDS["aws"]
    assert {"WY", "WZ"} <= MARKET_BANDS["700mhz"]
    # WCS (WS) + Microwave stay deferred; 600 MHz (WT) + Narrowband PCS (CN)
    # are not among the four Phase-1 bands.
    for excluded in ("WS", "WT", "CN", "CY", "CL"):
        assert excluded not in mapped


# ── quality report: counts + null rates + the audit extras ───────────────────


def test_cellular_quality_report(tmp_path):
    raw = _cellular_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    FccUlsCellularNormalizer().normalize(raw, out)

    qr = json.loads((out / "quality_report.json").read_text())
    assert qr["source_id"] == "fcc_uls_cellular"
    assert qr["tables"]["license"]["rows"] == 2
    assert qr["tables"]["location"]["rows"] == 3
    assert qr["tables"]["entity"]["rows"] == 3

    extras = qr["extras"]
    assert extras["band"] == "cellular"
    assert extras["license_count"] == 2
    # 2 of 3 locations carry an ASR number; 2 of 3 have usable coordinates.
    assert abs(extras["asr_number_populated_rate"] - 2 / 3) < 1e-4
    assert abs(extras["coordinate_usable_rate"] - 2 / 3) < 1e-4

    # asr_number null rate is visible on the location table column stats too.
    asr_stats = qr["tables"]["location"]["columns"]["asr_number"]
    assert abs(asr_stats["null_rate"] - 1 / 3) < 1e-4


def test_market_aggregate_quality_report(tmp_path):
    raw = _market_fixture(tmp_path / "raw")
    out = tmp_path / "out"
    FccUlsMarketNormalizer().normalize(raw, out)

    # aggregate at the source root...
    agg = json.loads((out / "quality_report.json").read_text())
    assert set(agg["extras"]["bands"]) == {"pcs", "aws", "700mhz"}
    assert agg["extras"]["bands"]["aws"]["license_count"] == 2

    # ...and a per-band report in each sub-directory.
    pcs_qr = json.loads((out / "pcs" / "quality_report.json").read_text())
    assert pcs_qr["extras"]["band"] == "pcs"
    assert pcs_qr["extras"]["service_codes"] == ["CW"]


# ── availability probe ───────────────────────────────────────────────────────


def test_is_available(tmp_path):
    raw = _cellular_fixture(tmp_path / "raw")
    assert FccUlsCellularNormalizer().is_available(raw) is True
    assert FccUlsCellularNormalizer().is_available(tmp_path / "nonexistent") is False
