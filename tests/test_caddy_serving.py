"""Caddy edge-serving contract for the hosted app (PRD #96, Module C).

Boots the *real* repo-root ``Caddyfile`` (env-parameterised) against a fixture
volume + SPA bundle + a stub backend, and asserts the externally observable
behavior the deploy depends on:

  * ``/data/processed/*`` is gated by ``forward_auth`` → ``/api/auth/check``
    (PRD #130): an unauthenticated request gets 401 and zero file bytes; a
    session cookie (or bearer header) gets the file — Range/206 intact;
  * a Range request to ``/data/processed/*`` (authenticated) returns 206 +
    Content-Range;
  * an unknown route falls back to the SPA's index.html;
  * ``/api/*`` is reverse-proxied to the backend;
  * ``/data/processed/*`` responses are ``Cache-Control: private, no-store``;
  * the SQLite DB and ``users.txt`` (volume root, outside the web subtree) are
    never web-served (403/404) — the PII/credentials-never-served invariant;
  * HSTS is set on responses.

These guard the security-relevant edge config, so they drive the *real* binary
rather than asserting on the Caddyfile's text.
"""

from __future__ import annotations

import http.client
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

_CADDY = shutil.which("caddy")
_CADDYFILE = Path(__file__).resolve().parents[1] / "Caddyfile"

pytestmark = pytest.mark.skipif(_CADDY is None, reason="caddy binary not installed")

# Distinctive fixture contents so a wrong handler can't accidentally look right.
_DB_MARKER = b"SQLITE-SECRET-DB-CONTENTS"
_USERS_MARKER = b"alice:$hash$:acme\n"
_SPA_MARKER = b"<!doctype html><title>pilot-spa</title>"
_AUDIT_SPA_MARKER = b"<!doctype html><title>audit-spa</title>"
_AUDIT_DATA_MARKER = b'{"audit":"index-json-contents"}'
_TILE_BYTES = bytes(range(256)) * 8  # 2048 deterministic bytes

# The session the stub backend accepts (the real token semantics live in the
# backend's own test suite; the edge contract only cares about 2xx vs 401).
_SESSION_TOKEN = "edge-test-session"
_COOKIE = {"Cookie": f"pilot_session={_SESSION_TOKEN}"}
_BEARER = {"Authorization": f"Bearer {_SESSION_TOKEN}"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _StubBackend(BaseHTTPRequestHandler):
    """Stands in for uvicorn so the reverse-proxy hop has something to hit.

    Implements the forward-auth seam (PRD #130): ``/api/auth/check`` answers
    204 when the request carries the test session (cookie or bearer), 401
    otherwise — which is exactly the contract the real endpoint exposes.
    """

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        if self.path.startswith("/api/auth/check"):
            cookie = self.headers.get("Cookie", "")
            bearer = self.headers.get("Authorization", "")
            if f"pilot_session={_SESSION_TOKEN}" in cookie or bearer == f"Bearer {_SESSION_TOKEN}":
                self.send_response(204)
                self.end_headers()
            else:
                body = b'{"detail":"not authenticated"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            return
        body = b'{"status":"ok","via":"stub-backend"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # silence test noise
        pass


@pytest.fixture(scope="module")
def caddy_base(tmp_path_factory: pytest.TempPathFactory):
    tmp = tmp_path_factory.mktemp("caddy-edge")

    # Built SPA bundle, including a content-hashed asset under /assets/*.
    site = tmp / "dist"
    site.mkdir()
    (site / "index.html").write_bytes(_SPA_MARKER)
    (site / "assets").mkdir()
    (site / "assets" / "index-abc123.js").write_bytes(b"console.log('app')")

    # Audit browser bundle + its baked artifacts (served behind the gate at
    # /audit/* and /audit/data/*).
    audit_site = tmp / "audit-dist"
    audit_site.mkdir()
    (audit_site / "index.html").write_bytes(_AUDIT_SPA_MARKER)
    (audit_site / "assets").mkdir()
    (audit_site / "assets" / "index-aud987.js").write_bytes(b"console.log('audit')")
    audit_data = tmp / "audit-data"
    audit_data.mkdir()
    (audit_data / "index.json").write_bytes(_AUDIT_DATA_MARKER)

    # Fixture "volume": served composite under processed/, plus the DB and
    # users.txt at the volume root (outside the web-served subtree).
    volume = tmp / "volume"
    composite = volume / "processed" / "composite" / "05"
    composite.mkdir(parents=True)
    (composite / "parcels.pmtiles").write_bytes(_TILE_BYTES)
    (volume / "lead_state.sqlite3").write_bytes(_DB_MARKER)
    (volume / "users.txt").write_bytes(_USERS_MARKER)

    backend_port = _free_port()
    caddy_port = _free_port()
    httpd = HTTPServer(("127.0.0.1", backend_port), _StubBackend)
    backend_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    backend_thread.start()

    env = {
        **os.environ,
        "CADDY_PORT": str(caddy_port),
        "SITE_ROOT": str(site),
        "AUDIT_SITE_ROOT": str(audit_site),
        "AUDIT_DATA_ROOT": str(audit_data),
        # Root for /data/processed/* maps the URL prefix onto the fixture volume:
        # /data/processed/X -> {DATA_WEB_ROOT}/data/processed/X. We symlink the
        # volume in as "data" so the 1:1 mapping holds against the fixture.
        "DATA_WEB_ROOT": str(tmp),
        "BACKEND_UPSTREAM": f"127.0.0.1:{backend_port}",
    }
    (tmp / "data").symlink_to(volume, target_is_directory=True)

    proc = subprocess.Popen(
        [_CADDY, "run", "--config", str(_CADDYFILE), "--adapter", "caddyfile"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _wait_until_ready(caddy_port, proc)
    try:
        yield f"127.0.0.1:{caddy_port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        httpd.shutdown()


def _wait_until_ready(port: int, proc: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"caddy exited early:\n{proc.stdout.read() if proc.stdout else ''}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("caddy did not become ready in time")


def _get(host_port: str, path: str, headers: dict[str, str] | None = None):
    host, port = host_port.split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    conn.request("GET", path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, hdrs, body


# ── the data-plane gate (PRD #130) ───────────────────────────────────────────
def test_unauthenticated_composite_request_is_refused(caddy_base: str) -> None:
    # The exposure this PRD closes: before forward_auth, anyone who knew a URL
    # could download the owner-PII composite. Now: 401, zero file bytes.
    status, _hdrs, body = _get(caddy_base, "/data/processed/composite/05/parcels.pmtiles")
    assert status == 401
    assert _TILE_BYTES[0:16] not in body


def test_unauthenticated_range_request_is_refused_too(caddy_base: str) -> None:
    # The probe that found the exposure was a Range request returning 206.
    status, hdrs, body = _get(
        caddy_base,
        "/data/processed/composite/05/parcels.pmtiles",
        {"Range": "bytes=0-3"},
    )
    assert status == 401
    assert "content-range" not in hdrs
    assert body != _TILE_BYTES[0:4]


def test_a_garbage_session_is_refused(caddy_base: str) -> None:
    status, _hdrs, body = _get(
        caddy_base,
        "/data/processed/composite/05/parcels.pmtiles",
        {"Cookie": "pilot_session=not-the-session"},
    )
    assert status == 401
    assert _TILE_BYTES[0:16] not in body


def test_a_bearer_header_also_passes_the_gate(caddy_base: str) -> None:
    # The transition path (tests, curl): Authorization still authenticates.
    status, _hdrs, body = _get(caddy_base, "/data/processed/composite/05/parcels.pmtiles", _BEARER)
    assert status == 200
    assert body == _TILE_BYTES


def test_range_request_to_composite_returns_206(caddy_base: str) -> None:
    # Authenticated Range/206 must survive the gate — PMTiles + DuckDB-WASM
    # depend on it (the PRD's done-bar pairs this with the 401 above).
    status, hdrs, body = _get(
        caddy_base,
        "/data/processed/composite/05/parcels.pmtiles",
        {"Range": "bytes=0-3", **_COOKIE},
    )
    assert status == 206
    assert hdrs.get("content-range", "").startswith("bytes 0-3/")
    assert body == _TILE_BYTES[0:4]


def test_unknown_route_falls_back_to_the_spa(caddy_base: str) -> None:
    status, _hdrs, body = _get(caddy_base, "/leads/some/deep/client-route")
    assert status == 200
    assert body == _SPA_MARKER


def test_hashed_assets_get_immutable_cache_headers(caddy_base: str) -> None:
    # PERF-019: content-hashed /assets/* are immutable, so repeat visits hit
    # cache instead of revalidating the big MapLibre/DuckDB chunks.
    status, hdrs, _body = _get(caddy_base, "/assets/index-abc123.js")
    assert status == 200
    cc = hdrs.get("cache-control", "")
    assert "immutable" in cc
    assert "max-age=31536000" in cc


def test_index_html_stays_revalidated(caddy_base: str) -> None:
    # The immutable rule must be scoped to /assets/* — index.html must NOT be
    # hard-cached, so a new deploy is picked up immediately.
    _status, hdrs, _body = _get(caddy_base, "/")
    assert "immutable" not in hdrs.get("cache-control", "")


def test_api_is_reverse_proxied_to_the_backend(caddy_base: str) -> None:
    status, _hdrs, body = _get(caddy_base, "/api/health")
    assert status == 200
    assert b"stub-backend" in body


def test_composite_responses_are_not_cacheable(caddy_base: str) -> None:
    status, hdrs, _ = _get(caddy_base, "/data/processed/composite/05/parcels.pmtiles", _COOKIE)
    assert status == 200
    assert hdrs.get("cache-control") == "private, no-store"


def test_sqlite_db_is_never_web_served(caddy_base: str) -> None:
    # The DB lives at the volume root, outside /data/processed — a request for
    # it must be refused, never leak Lead data through the static file server.
    status, _hdrs, body = _get(caddy_base, "/data/lead_state.sqlite3")
    assert status in (403, 404)
    assert _DB_MARKER not in body


def test_users_file_is_never_web_served(caddy_base: str) -> None:
    status, _hdrs, body = _get(caddy_base, "/data/users.txt")
    assert status in (403, 404)
    assert _USERS_MARKER not in body


def test_hsts_header_is_set(caddy_base: str) -> None:
    _status, hdrs, _ = _get(caddy_base, "/api/health")
    assert "max-age=" in hdrs.get("strict-transport-security", "")


# ── the data-audit browser, behind the same session gate ─────────────────────
def test_audit_spa_requires_auth(caddy_base: str) -> None:
    # The audit exposes internal data semantics — it is never public.
    status, _hdrs, body = _get(caddy_base, "/audit/")
    assert status == 401
    assert _AUDIT_SPA_MARKER not in body


def test_audit_spa_served_when_authenticated(caddy_base: str) -> None:
    status, _hdrs, body = _get(caddy_base, "/audit/", _COOKIE)
    assert status == 200
    assert body == _AUDIT_SPA_MARKER


def test_audit_deep_route_falls_back_to_audit_spa(caddy_base: str) -> None:
    # The hash router's history fallback: any /audit/* path resolves to the
    # audit bundle's index.html (not the main SPA's).
    status, _hdrs, body = _get(caddy_base, "/audit/some/client/route", _COOKIE)
    assert status == 200
    assert body == _AUDIT_SPA_MARKER


def test_audit_assets_get_immutable_cache(caddy_base: str) -> None:
    status, hdrs, _body = _get(caddy_base, "/audit/assets/index-aud987.js", _COOKIE)
    assert status == 200
    cc = hdrs.get("cache-control", "")
    assert "immutable" in cc and "max-age=31536000" in cc


def test_audit_data_requires_auth(caddy_base: str) -> None:
    # index.json carries the audit's findings (internal) — gate it like the
    # composite, zero bytes to an unauthenticated caller.
    status, _hdrs, body = _get(caddy_base, "/audit/data/index.json")
    assert status == 401
    assert _AUDIT_DATA_MARKER not in body


def test_audit_data_served_when_authenticated(caddy_base: str) -> None:
    status, hdrs, body = _get(caddy_base, "/audit/data/index.json", _COOKIE)
    assert status == 200
    assert body == _AUDIT_DATA_MARKER
    # Internal data semantics — never cached anywhere.
    assert hdrs.get("cache-control") == "private, no-store"
