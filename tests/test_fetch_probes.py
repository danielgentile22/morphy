"""Offline tests for the shared fetch probes + stub rejection (#258).

The fragile publisher-facing mechanics (ArcGIS edit-date probe, size-gated
HEAD stub rejection, the Last-Modified→ETag→Content-Length chain, the
zip-download-extract dance) now live behind shared helpers; these tests
pin them with monkeypatched HTTP primitives, per the state-parcel fetcher
test pattern. No network.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fetch.http import HttpError
from fetch.registry import get_source
from fetch.sources import _arcgis as arcgis_mod
from fetch.sources import _helpers as helpers_mod
from fetch.sources import eia_860 as eia860_mod
from fetch.sources import eia_860m as eia860m_mod
from fetch.sources import faa_oeaaa as faa_mod
from fetch.sources import fcc_asr as asr_mod
from fetch.sources._arcgis import arcgis_edit_date_version
from fetch.sources._helpers import head_size_ok, version_from_head

# 2025-01-01T00:00:00Z in epoch milliseconds.
_EDIT_MS = 1_735_689_600_000


def _sink(*_args):
    pass


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def _fake_download(payload_by_url: dict[str, bytes]):
    def fake(url, dest, on_progress=None, *, expected_min_bytes=0, cancel_check=None):
        data = payload_by_url[url]
        dest.write_bytes(data)
        if on_progress:
            on_progress(len(data), len(data))
        return len(data)

    return fake


# ── ArcGIS edit-date probe ─────────────────────────────────────────────────


def test_arcgis_edit_date_version_iso_date(monkeypatch):
    meta = {"name": "Layer", "editingInfo": {"lastEditDate": _EDIT_MS}}
    monkeypatch.setattr(arcgis_mod, "fetch_text", lambda url: json.dumps(meta))
    assert arcgis_edit_date_version("https://x/meta?f=pjson", label="X") == "2025-01-01"


def test_arcgis_edit_date_version_name_fallback(monkeypatch):
    monkeypatch.setattr(arcgis_mod, "fetch_text", lambda url: json.dumps({"name": "QCT_2025"}))
    assert arcgis_edit_date_version("https://x", label="X") == "n-QCT_2025"
    monkeypatch.setattr(arcgis_mod, "fetch_text", lambda url: "{}")
    assert arcgis_edit_date_version("https://x", label="X") == "n-?"


def test_arcgis_edit_date_version_bad_json(monkeypatch):
    monkeypatch.setattr(arcgis_mod, "fetch_text", lambda url: "<html>maintenance</html>")
    with pytest.raises(HttpError, match="HUD OZ metadata not JSON"):
        arcgis_edit_date_version("https://x", label="HUD OZ")


@pytest.mark.parametrize(
    ("source_id", "out_name"),
    [("hud_oz", "opportunity_zones.geojson"), ("hud_qct", "qct.geojson")],
)
def test_hud_sources_are_hub_configuration(monkeypatch, tmp_path, source_id, out_name):
    src = get_source(source_id)
    meta = {"name": "svc", "editingInfo": {"lastEditDate": _EDIT_MS}}
    probes: list[str] = []

    def fake_fetch_text(url):
        probes.append(url)
        return json.dumps(meta)

    queried: list[str] = []

    def fake_query_all(layer_url, dest, on_progress=None, page_size=2000):
        queried.append(layer_url)
        payload = b'{"type": "FeatureCollection", "features": []}' + b" " * 600_000
        dest.write_bytes(payload)
        return len(payload)

    monkeypatch.setattr(arcgis_mod, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(arcgis_mod, "arcgis_query_all", fake_query_all)

    res = src.fetch(tmp_path, _sink)
    assert res.remote_version == "2025-01-01"
    assert res.files == [tmp_path / out_name]
    assert res.total_bytes > 600_000
    assert queried == [src.layer_url]
    assert probes == [f"{src.layer_url}?f=pjson"]  # version captured exactly once
    src.validate(res.files)  # FeatureCollection sniff accepts the payload


def test_hud_fetch_rejects_undersized_payload(monkeypatch, tmp_path):
    src = get_source("hud_oz")
    monkeypatch.setattr(
        arcgis_mod,
        "fetch_text",
        lambda url: json.dumps({"editingInfo": {"lastEditDate": _EDIT_MS}}),
    )

    def tiny_query_all(layer_url, dest, on_progress=None, page_size=2000):
        dest.write_bytes(b'{"type": "FeatureCollection", "features": []}')
        return 45

    monkeypatch.setattr(arcgis_mod, "arcgis_query_all", tiny_query_all)
    with pytest.raises(HttpError, match="only 45 bytes"):
        src.fetch(tmp_path, _sink)


def test_hud_validate_rejects_non_featurecollection(tmp_path):
    src = get_source("hud_qct")
    bad = tmp_path / "qct.geojson"
    bad.write_text("<html>error page</html>")
    with pytest.raises(ValueError, match="not a GeoJSON FeatureCollection"):
        src.validate([bad])


def test_nc_onemap_reuses_hub_probe(monkeypatch):
    src = get_source("nc_onemap_parcels")
    meta = {"name": "Parcels", "editingInfo": {"lastEditDate": _EDIT_MS}}
    monkeypatch.setattr(arcgis_mod, "fetch_text", lambda url: json.dumps(meta))
    assert src.remote_version() == "2025-01-01"


# ── Size-gated HEAD probe (EIA stub rejection) ─────────────────────────────


def _head_returning(h):
    def fake(url):
        if isinstance(h, Exception):
            raise h
        return h

    return fake


@pytest.mark.parametrize(
    ("headers", "require_length", "expected"),
    [
        ({"status": "200", "content_length": "2000000"}, False, True),
        ({"status": "200", "content_length": "2000000"}, True, True),
        ({"status": "200", "content_length": "67000"}, False, False),  # stub page
        ({"status": "200", "content_length": "67000"}, True, False),
        ({"status": "404", "content_length": "2000000"}, False, False),
        ({"status": "200", "content_length": None}, False, True),  # trust the 2xx
        ({"status": "200", "content_length": None}, True, False),  # workbook must size
        ({"status": "200", "content_length": "n/a"}, False, True),
        ({"status": "200", "content_length": "n/a"}, True, False),
    ],
)
def test_head_size_ok_matrix(monkeypatch, headers, require_length, expected):
    monkeypatch.setattr(helpers_mod, "head", _head_returning(headers))
    assert head_size_ok("https://x", 1_000_000, require_length=require_length) is expected


def test_head_size_ok_network_failure(monkeypatch):
    monkeypatch.setattr(helpers_mod, "head", _head_returning(HttpError("HEAD https://x → boom")))
    assert head_size_ok("https://x", 1_000_000) is False


def test_eia860_year_walk_skips_stub_years(monkeypatch):
    from datetime import date

    y = date.today().year
    real = eia860_mod.ARCHIVE_PATTERN.format(year=y - 2)
    ok = {real: True}
    monkeypatch.setattr(eia860_mod, "head_size_ok", lambda url, mb, **kw: ok.get(url, False))
    url, version = eia860_mod.SOURCE._latest_year_url()
    assert (url, version) == (real, f"{y - 2}")

    ok = {eia860_mod.CURRENT_URL: True}
    assert eia860_mod.SOURCE._latest_year_url() == (eia860_mod.CURRENT_URL, "current")

    ok = {}
    with pytest.raises(HttpError, match="no EIA-860 archive year reachable"):
        eia860_mod.SOURCE._latest_year_url()


def test_eia860m_month_walk_requires_length(monkeypatch):
    calls: list[dict] = []

    def fake(url, min_bytes, **kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(eia860m_mod, "head_size_ok", fake)
    url, version = eia860m_mod._latest_month_url()
    # A length-less 200 is a stub for the monthly workbook — the walk
    # must probe with require_length=True.
    assert calls[0] == {"require_length": True}
    assert len(version) == 7 and version[4] == "-"  # YYYY-MM


# ── version_from_head chain ────────────────────────────────────────────────


def test_version_from_head_chain(monkeypatch):
    monkeypatch.setattr(
        helpers_mod,
        "head",
        _head_returning({"last_modified": "Wed, 01 Jan 2025 00:00:00 GMT"}),
    )
    assert version_from_head("https://x") == "2025-01-01"

    monkeypatch.setattr(helpers_mod, "head", _head_returning({"etag": '"abc123"'}))
    assert version_from_head("https://x") == "abc123"

    monkeypatch.setattr(helpers_mod, "head", _head_returning({"content_length": "1234"}))
    assert version_from_head("https://x") == "len-1234"

    monkeypatch.setattr(helpers_mod, "head", _head_returning({}))
    with pytest.raises(RuntimeError, match="could not derive remote version for FCC ASR"):
        version_from_head("https://x", label="FCC ASR")


# ── Zip dances through fetch_zip_extracted ─────────────────────────────────


def test_faa_fetch_extracts_into_dof_subfolder(monkeypatch, tmp_path):
    monkeypatch.setattr(faa_mod, "version_from_head", lambda url, label="": "2026-07-01")
    payload = _zip_bytes({"DOF.DAT": b"x" * 10, "DOF_README": b"docs"})
    monkeypatch.setattr(helpers_mod, "download", _fake_download({faa_mod.DOF_URL: payload}))

    res = get_source("faa_oeaaa").fetch(tmp_path, _sink)
    assert (tmp_path / "dof" / "DOF.DAT").exists()
    assert not (tmp_path / "DAILY_DOF_DAT.ZIP").exists()  # zip removed after extract
    assert res.remote_version == "2026-07-01"
    assert res.total_bytes == len(payload)


def test_fcc_asr_d_tower_failure_stays_non_fatal(monkeypatch, tmp_path):
    monkeypatch.setattr(asr_mod, "version_from_head", lambda url, label="": "2026-07-01")
    r_payload = _zip_bytes({"RA.dat": b"r" * 10, "CO.dat": b"c" * 5})
    # No d_tower entry: the optional download raises and must be swallowed.
    monkeypatch.setattr(helpers_mod, "download", _fake_download({asr_mod.R_TOWER_URL: r_payload}))

    src = get_source("fcc_asr")
    res = src.fetch(tmp_path, _sink)
    assert (tmp_path / "r_tower" / "RA.dat").exists()
    assert res.total_bytes == len(r_payload)
    src.validate(res.files)  # RA.dat present → valid without d_tower


# ── Policy census (guardrail: #258 changes no automation posture) ──────────


def test_touched_sources_keep_their_automation_policy():
    from fetch.legal import AutomationPolicy

    allowed = ["fcc_asr", "eia_860", "eia_860m", "hud_oz", "hud_qct", "uspvdb", "faa_oeaaa"]
    for sid in allowed:
        assert get_source(sid).legal.automation == AutomationPolicy.ALLOWED, sid
    assert get_source("nc_onemap_parcels").legal.automation == AutomationPolicy.ALLOWED
    assert get_source("usda_persistent_poverty").legal.automation == AutomationPolicy.TOLERATED
    for sid in ["lbnl_tts", "ar_parcels"]:
        assert get_source(sid).is_manual_only, sid
