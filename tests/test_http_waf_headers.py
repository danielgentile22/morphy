"""Regression tests for the 2026-07 FCC WAF stall fix.

data.fcc.gov silently stalls requests that don't advertise a browser-like
``Accept-Encoding: gzip, deflate`` ("gzip" alone also stalls). We therefore
send that header on every request — which means bodies may arrive
compressed, so the body-reading paths must decompress transparently.
"""

import gzip
import io
import urllib.request
from email.message import Message

import pytest
from fetch import http


class _FakeResponse:
    def __init__(self, body: bytes = b"", headers: dict | None = None):
        self._body = io.BytesIO(body)
        self.headers = Message()
        for k, v in (headers or {}).items():
            self.headers[k] = v
        self.status = 200

    def read(self, n: int = -1) -> bytes:
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def capture(monkeypatch):
    """Patch urlopen; returns a dict the test can inspect + configure."""
    box = {"req": None, "resp": _FakeResponse()}

    def fake_urlopen(req, timeout=None):
        box["req"] = req
        return box["resp"]

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return box


def test_head_sends_waf_passing_headers(capture):
    http.head("https://example.test/file.zip")
    req = capture["req"]
    assert req.get_header("Accept-encoding") == "gzip, deflate"
    assert req.get_header("Accept") == "*/*"
    assert "PilotDataPuller" in req.get_header("User-agent")


def test_fetch_text_gunzips_body(capture):
    capture["resp"] = _FakeResponse(
        gzip.compress("héllo".encode()),
        {"Content-Encoding": "gzip", "Content-Type": "text/plain; charset=utf-8"},
    )
    assert http.fetch_text("https://example.test/page") == "héllo"


def test_fetch_text_plain_body_unchanged(capture):
    capture["resp"] = _FakeResponse(b"plain", {"Content-Type": "text/plain; charset=utf-8"})
    assert http.fetch_text("https://example.test/page") == "plain"


def test_download_gunzips_and_counts_written_bytes(capture, tmp_path):
    payload = b"x" * 100_000  # compresses far below 100 KB
    capture["resp"] = _FakeResponse(gzip.compress(payload), {"Content-Encoding": "gzip"})
    dest = tmp_path / "out.bin"
    # expected_min_bytes above the compressed size proves the check runs on
    # decompressed (on-disk) bytes, not wire bytes.
    n = http.download("https://example.test/file", dest, expected_min_bytes=50_000)
    assert n == len(payload)
    assert dest.read_bytes() == payload
