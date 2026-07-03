"""Fetch-layer tests for the 2026-07 MANUAL_ONLY→ALLOWED flips.

MT, WV, FL FDOR, and FL FGDL DSL parcel sources auto-fetch as of
2026-07-03 (direct anonymous HTTPS confirmed per-source; see each
source's legal notes). These tests pin the fetch mechanics: zip
download → extract-in-place → zip cleanup, WV vintage discovery, FGDL
newest-release discovery, FDOR SharePoint listing walk + per-county
resume. AR deliberately stays MANUAL_ONLY.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fetch.http import HttpError
from fetch.registry import get_source
from fetch.sources import _helpers as helpers_mod
from fetch.sources import fdor_nal as fdor_mod
from fetch.sources import fl_fgdl_parcels as fgdl_mod
from fetch.sources import state_parcels as sp_mod


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _fake_download(payload_by_url: dict[str, bytes]):
    """Stand-in for http.download: writes canned bytes, KeyErrors on
    unexpected URLs (which doubles as a 'was not called' assertion)."""

    def fake(url, dest, on_progress=None, *, expected_min_bytes=0, cancel_check=None):
        data = payload_by_url[url]
        dest.write_bytes(data)
        if on_progress:
            on_progress(len(data), len(data))
        return len(data)

    return fake


def _sink(*_args):
    pass


# ── policy census ──────────────────────────────────────────────────────────


def test_flip_census():
    for sid in ("mt_cadastral_parcels", "wv_parcels", "fdor_nal", "fl_fgdl_parcels"):
        src = get_source(sid)
        assert not src.is_manual_only, f"{sid} should be auto-fetch"
        assert src.manual_walkthrough() is not None, f"{sid} must keep its fallback walkthrough"
    assert get_source("ar_parcels").is_manual_only  # deliberately NOT flipped


# ── Montana ────────────────────────────────────────────────────────────────


def test_mt_fetch_extracts_and_cleans_up(monkeypatch, tmp_path):
    zbytes = _zip_bytes(
        {
            "MontanaCadastral_SHP/OWNERPARCEL.shp": b"shp-bytes",
            "MontanaCadastral_SHP/OWNERPARCEL.dbf": b"dbf-bytes",
        }
    )
    monkeypatch.setattr(helpers_mod, "download", _fake_download({sp_mod.MT_SHP_ZIP_URL: zbytes}))
    monkeypatch.setattr(sp_mod, "version_from_head", lambda url, label="": "2026-06-04")

    res = sp_mod.MtCadastralParcels().fetch(tmp_path, _sink)

    assert (tmp_path / "MontanaCadastral_SHP" / "OWNERPARCEL.shp").read_bytes() == b"shp-bytes"
    assert not (tmp_path / "MontanaCadastral_SHP.zip").exists(), "zip must be deleted"
    assert res.remote_version == "2026-06-04"
    assert res.total_bytes == len(zbytes)


# ── West Virginia ──────────────────────────────────────────────────────────

_WV_LISTING = """
<a HREF="/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_2024/">2024</a>
<a HREF="/pub/Clearinghouse/planningLanduseCadastres/Parcels/WVGISTC_2025/">2025</a>
"""


def test_wv_discovers_newest_vintage(monkeypatch):
    monkeypatch.setattr(sp_mod, "fetch_text", lambda url, **kw: _WV_LISTING)
    url, year = sp_mod.WvParcels()._latest_zip()
    assert year == 2025
    assert url.endswith("WVGISTC_2025/WV_WVGISTC_Tax_2025.gdb.zip")


def test_wv_no_vintages_raises(monkeypatch):
    monkeypatch.setattr(sp_mod, "fetch_text", lambda url, **kw: "<html>empty</html>")
    with pytest.raises(HttpError):
        sp_mod.WvParcels()._latest_zip()


def test_wv_fetch_extracts_gdb(monkeypatch, tmp_path):
    zbytes = _zip_bytes({"WV_WVGISTC_Tax_2025.gdb/gdb_file.gdbtable": b"gdb-bytes"})
    monkeypatch.setattr(sp_mod, "fetch_text", lambda url, **kw: _WV_LISTING)
    monkeypatch.setattr(sp_mod, "version_from_head", lambda url, label="": "2026-06-24")
    url = f"{sp_mod.WV_PARCELS_DIR}WVGISTC_2025/WV_WVGISTC_Tax_2025.gdb.zip"
    monkeypatch.setattr(helpers_mod, "download", _fake_download({url: zbytes}))

    res = sp_mod.WvParcels().fetch(tmp_path, _sink)

    assert (tmp_path / "WV_WVGISTC_Tax_2025.gdb" / "gdb_file.gdbtable").exists()
    assert not (tmp_path / "WV_WVGISTC_Tax_2025.gdb.zip").exists()
    assert res.remote_version == "2025:2026-06-24"


# ── Florida FGDL DSL (state-owned land) ────────────────────────────────────

_FGDL_LISTING = """
<a href="dsl_parcel_composite_oct24.zip">dsl_parcel_composite_oct24.zip</a>
<a href="dsl_parcel_composite_oct25.zip">dsl_parcel_composite_oct25.zip</a>
<a href="dsl_parcel_composite_mar25.zip">dsl_parcel_composite_mar25.zip</a>
"""


def test_fgdl_discovers_newest_release(monkeypatch):
    monkeypatch.setattr(fgdl_mod, "fetch_text", lambda url, **kw: _FGDL_LISTING)
    url, tag = fgdl_mod.FlFgdlParcels()._latest_zip()
    assert tag == "oct25"  # oct25 > mar25 > oct24
    assert url == f"{fgdl_mod.FGDL_CURRENT_DIR}dsl_parcel_composite_oct25.zip"


def test_fgdl_empty_listing_raises(monkeypatch):
    monkeypatch.setattr(fgdl_mod, "fetch_text", lambda url, **kw: "<html>nothing</html>")
    with pytest.raises(HttpError):
        fgdl_mod.FlFgdlParcels()._latest_zip()


def test_fgdl_fetch_extracts_gdb(monkeypatch, tmp_path):
    zbytes = _zip_bytes({"dsl_parcel_composite_oct25.gdb/a00000001.gdbtable": b"gdb-bytes"})
    monkeypatch.setattr(fgdl_mod, "fetch_text", lambda url, **kw: _FGDL_LISTING)
    monkeypatch.setattr(fgdl_mod, "version_from_head", lambda url, label="": "2025-12-04")
    url = f"{fgdl_mod.FGDL_CURRENT_DIR}dsl_parcel_composite_oct25.zip"
    monkeypatch.setattr(helpers_mod, "download", _fake_download({url: zbytes}))

    res = fgdl_mod.FlFgdlParcels().fetch(tmp_path, _sink)

    # Same layout the manual install produced: current/<name>.gdb/, zip gone.
    assert (tmp_path / "dsl_parcel_composite_oct25.gdb" / "a00000001.gdbtable").exists()
    assert not (tmp_path / "dsl_parcel_composite_oct25.zip").exists()
    assert res.remote_version == "oct25:2025-12-04"


# ── Florida FDOR ───────────────────────────────────────────────────────────

_FDOR_PAR_PATH = f"{fdor_mod.MAP_DATA_PATH}/2025F/2025F PAR"


def _fdor_fetch_text(url: str, **_kw) -> str:
    if "/Folders" in url:
        return json.dumps(
            {"value": [{"Name": "2026F"}, {"Name": "2025F"}, {"Name": "Mapping Data Information"}]}
        )
    if "2026F%20PAR" in url:
        raise HttpError("404: folder does not exist yet")  # pre-created, unpopulated vintage
    if "2025F%20PAR" in url:
        return json.dumps(
            {
                "value": [
                    {
                        "Name": "alachua_2025par.zip",
                        "ServerRelativeUrl": f"{_FDOR_PAR_PATH}/alachua_2025par.zip",
                        "Length": 100,
                        "TimeLastModified": "2025-08-01T04:00:00Z",
                    },
                    {
                        "Name": "baker_2025Ppar.zip",
                        "ServerRelativeUrl": f"{_FDOR_PAR_PATH}/baker_2025Ppar.zip",
                        "Length": 50,
                        "TimeLastModified": "2025-07-31T04:00:00Z",
                    },
                    {
                        "Name": "readme.pdf",
                        "ServerRelativeUrl": f"{_FDOR_PAR_PATH}/readme.pdf",
                        "Length": 10,
                        "TimeLastModified": "2025-07-01T04:00:00Z",
                    },
                ]
            }
        )
    raise AssertionError(f"unexpected fetch_text URL: {url}")


def test_fdor_remote_version_skips_empty_vintage(monkeypatch):
    monkeypatch.setattr(fdor_mod, "fetch_text", _fdor_fetch_text)
    # 2026F exists but is unpopulated → version comes from 2025F.
    assert fdor_mod.FdorNal().remote_version() == "2025F:2025-08-01"


def test_fdor_fetch_downloads_all_counties(monkeypatch, tmp_path):
    from urllib.parse import quote

    monkeypatch.setattr(fdor_mod, "fetch_text", _fdor_fetch_text)
    payloads = {
        fdor_mod.SP_HOST + quote(f"{_FDOR_PAR_PATH}/alachua_2025par.zip"): _zip_bytes(
            {"alachua.shp": b"a"}
        ),
        fdor_mod.SP_HOST + quote(f"{_FDOR_PAR_PATH}/baker_2025Ppar.zip"): _zip_bytes(
            {"baker.shp": b"b"}
        ),
    }
    monkeypatch.setattr(helpers_mod, "download", _fake_download(payloads))

    res = fdor_mod.FdorNal().fetch(tmp_path, _sink)

    # Per-county dirs matching the manual-upload layout; zips gone; PDF skipped.
    assert (tmp_path / "alachua_2025par" / "alachua.shp").exists()
    assert (tmp_path / "baker_2025Ppar" / "baker.shp").exists()
    assert not list(tmp_path.glob("*.zip"))
    assert res.remote_version == "2025F:2025-08-01"
    assert res.total_bytes == 150  # listed Lengths of the two zips, pdf excluded


def test_fdor_fetch_resumes_past_existing_county_dirs(monkeypatch, tmp_path):
    from urllib.parse import quote

    monkeypatch.setattr(fdor_mod, "fetch_text", _fdor_fetch_text)
    # alachua already extracted by a previous interrupted run…
    done = tmp_path / "alachua_2025par"
    done.mkdir()
    (done / "alachua.shp").write_bytes(b"a")
    # …so download must only be called for baker (KeyError otherwise).
    payloads = {
        fdor_mod.SP_HOST + quote(f"{_FDOR_PAR_PATH}/baker_2025Ppar.zip"): _zip_bytes(
            {"baker.shp": b"b"}
        ),
    }
    monkeypatch.setattr(helpers_mod, "download", _fake_download(payloads))

    res = fdor_mod.FdorNal().fetch(tmp_path, _sink)

    assert (tmp_path / "baker_2025Ppar" / "baker.shp").exists()
    assert any(p.name == "alachua.shp" for p in res.files)
