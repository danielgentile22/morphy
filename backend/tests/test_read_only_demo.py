"""The public read-only demo (ADR-077).

A ``read_only`` credential signs in and reads like any other, but every
non-GET request it makes is refused with 403 by the one gate in
``current_principal``. ``DEMO_MODE`` (off by default) adds a password-less
``POST /api/auth/demo`` that issues the normal identity-only session for the
configured demo credential, and boot refuses to serve demo mode unless that
credential exists and is read-only. ``python -m app.demo_seed`` builds the
demo board idempotently.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Iterator

import pytest
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from backend.app import credentials_store, main
from backend.app.auth import READ_ONLY_DETAIL, SESSION_COOKIE
from backend.app.config import Settings, settings
from backend.app.credentials_store import ensure_fail_closed_boot
from backend.app.demo_seed import STORYLINES, seed
from backend.app.lead_store import LeadStore
from backend.app.owners_index_service import OwnersIndexService
from backend.app.task_store import TaskStore

from ._helpers import api, auth_header, login

CID = "nat0000aaaa"


def _owner(cid: str, kind: str, score: float, towers: int = 1) -> dict:
    return {
        "display_cluster_id": cid,
        "owner_name": f"OWNER {cid}",
        "owner_name_norm": f"OWNER {cid}",
        "owner_kind": kind,
        "states": ["AR"],
        "n_states": 1,
        "cross_state": False,
        "parcel_count": 1,
        "tower_count": towers,
        "solar_count": 0,
        "total_assessed_value": 1.0,
        "max_parcel_score": score,
        "score": score,
        "distress_tier": "at-risk",
        "in_oz": False,
        "in_qct": False,
        "persistent_poverty": False,
    }


SAMPLE = {"schema_version": 1, "count": 1, "owners": [_owner(CID, "llc", 0.5)]}

# Sign-in/out and the demo login never resolve a principal; they stay open.
_AUTH_ROUTES = {"/api/auth/login", "/api/auth/logout", "/api/auth/demo"}


@pytest.fixture
def demo_settings(monkeypatch) -> Iterator[Settings]:
    cfg = dataclasses.replace(settings, demo_mode=True, demo_username="demo")
    monkeypatch.setattr(main, "settings", cfg)
    yield cfg


def _add_reader(eng, username: str = "demo", team: str = "demo") -> None:
    with Session(bind=eng, future=True) as s:
        credentials_store.add(s, username, team, "pw", read_only=True)


def _write_routes() -> list[tuple[str, str]]:
    out = []
    for route in main.app.routes:
        if not isinstance(route, APIRoute) or route.path in _AUTH_ROUTES:
            continue
        for method in route.methods - {"GET", "HEAD", "OPTIONS"}:
            out.append((method, re.sub(r"\{[^}]+\}", "1", route.path)))
    return sorted(out)


# ── the read-only gate ───────────────────────────────────────────────────────
def test_every_write_route_refuses_a_read_only_principal() -> None:
    routes = _write_routes()
    assert ("POST", "/api/me/password") in routes  # the enumeration sees the writes
    assert len(routes) >= 15
    with api(SAMPLE) as (client, eng, _sender):
        _add_reader(eng)
        headers = auth_header(login(client, "demo", "pw"))
        for method, path in routes:
            r = client.request(method, path, json={}, headers=headers)
            assert r.status_code == 403, (method, path, r.status_code, r.text)
            assert r.json()["detail"] == READ_ONLY_DETAIL


def test_read_only_principal_reads_normally() -> None:
    with api(SAMPLE) as (client, eng, _sender):
        _add_reader(eng)
        headers = auth_header(login(client, "demo", "pw"))
        me = client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["read_only"] is True
        assert client.get("/api/candidates", headers=headers).status_code == 200
        assert client.get(f"/api/leads/{CID}", headers=headers).status_code == 200
        assert client.get("/api/auth/check", headers=headers).status_code == 204


def test_read_only_principal_cannot_change_its_password() -> None:
    with api(SAMPLE) as (client, eng, _sender):
        _add_reader(eng)
        headers = auth_header(login(client, "demo", "pw"))
        r = client.post(
            "/api/me/password",
            json={"current_password": "pw", "new_password": "taken-over"},
            headers=headers,
        )
        assert r.status_code == 403
        with Session(bind=eng, future=True) as s:
            assert credentials_store.authenticate(s, "demo", "pw").ok


def test_a_writable_principal_is_unaffected() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        headers = auth_header(login(client))
        assert client.get("/api/auth/me", headers=headers).json()["read_only"] is False
        r = client.put(f"/api/leads/{CID}", json={"notes": "hello"}, headers=headers)
        assert r.status_code == 200


def test_flagging_read_only_applies_on_the_next_request() -> None:
    with api(SAMPLE) as (client, eng, _sender):
        headers = auth_header(login(client))
        with Session(bind=eng, future=True) as s:
            credentials_store.set_read_only(s, "dev", True)
        r = client.put(f"/api/leads/{CID}", json={"notes": "x"}, headers=headers)
        assert r.status_code == 403


# ── the demo login ───────────────────────────────────────────────────────────
def test_demo_login_is_404_and_config_says_off_by_default() -> None:
    with api(SAMPLE) as (client, eng, _sender):
        _add_reader(eng)
        assert client.get("/api/auth/config").json() == {"demo_mode": False}
        r = client.post("/api/auth/demo")
        assert r.status_code == 404
        assert SESSION_COOKIE not in r.headers.get("set-cookie", "")


def test_demo_login_issues_a_read_only_cookie_session(demo_settings) -> None:
    with api(SAMPLE) as (client, eng, _sender):
        _add_reader(eng)
        assert client.get("/api/auth/config").json() == {"demo_mode": True}
        r = client.post("/api/auth/demo")
        assert r.status_code == 200, r.text
        set_cookie = r.headers["set-cookie"].lower()
        assert SESSION_COOKIE in set_cookie
        assert "httponly" in set_cookie
        # The cookie alone now authenticates, read-only, including the edge gate.
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == "demo"
        assert me.json()["read_only"] is True
        assert client.get("/api/auth/check").status_code == 204
        assert client.put(f"/api/leads/{CID}", json={"notes": "x"}).status_code == 403
        assert client.post("/api/auth/logout").status_code == 204


def test_demo_login_refuses_a_writable_or_missing_credential(demo_settings) -> None:
    with api(SAMPLE) as (client, eng, _sender):
        assert client.post("/api/auth/demo").status_code == 404  # no such credential
        with Session(bind=eng, future=True) as s:
            credentials_store.add(s, "demo", "demo", "pw")  # writable
        assert client.post("/api/auth/demo").status_code == 404


def test_demo_login_keeps_the_cross_origin_guard(demo_settings) -> None:
    with api(SAMPLE) as (client, eng, _sender):
        _add_reader(eng)
        r = client.post("/api/auth/demo", headers={"Origin": "https://evil.example"})
        assert r.status_code == 403


# ── fail-closed boot ─────────────────────────────────────────────────────────
_SECRET = "a-real-secret-long-enough-for-hs256-signing"


def _prod_demo(username: str = "demo") -> Settings:
    return dataclasses.replace(
        settings,
        dev_mode=False,
        jwt_secret=_SECRET,
        jwt_secret_is_ephemeral=False,
        demo_mode=True,
        demo_username=username,
    )


def test_demo_boot_refuses_without_the_demo_credential(engine) -> None:
    with Session(bind=engine, future=True) as s:
        credentials_store.add(s, "alice", "acme", "pw")
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        ensure_fail_closed_boot(engine, _prod_demo())


def test_demo_boot_refuses_a_writable_demo_credential(engine) -> None:
    with Session(bind=engine, future=True) as s:
        credentials_store.add(s, "demo", "demo", "pw")
    with pytest.raises(RuntimeError, match="not a read-only"):
        ensure_fail_closed_boot(engine, _prod_demo())


def test_demo_boot_serves_with_a_read_only_demo_credential(engine) -> None:
    _add_reader(engine)
    ensure_fail_closed_boot(engine, _prod_demo())  # must not raise


def test_demo_mode_env_is_off_unless_explicitly_truthy(monkeypatch) -> None:
    for raw, expected in (("", False), ("0", False), ("false", False), ("1", True), ("true", True)):
        monkeypatch.setenv("DEMO_MODE", raw)
        assert Settings.from_env().demo_mode is expected, raw
    monkeypatch.delenv("DEMO_MODE")
    assert Settings.from_env().demo_mode is False


# ── the seed script ──────────────────────────────────────────────────────────
def _index(tmp_path, owners: list[dict]) -> OwnersIndexService:
    path = tmp_path / "owners_index.json"
    path.write_text(json.dumps({"schema_version": 5, "count": len(owners), "owners": owners}))
    return OwnersIndexService(path)


def test_seed_is_idempotent(engine, tmp_path) -> None:
    owners = [_owner(f"c{i:02d}", "llc" if i % 2 else "corporate", 1 - i / 100) for i in range(10)]
    owners.append(_owner("person", "individual", 2.0))  # outranks all, never seeded
    owners.append(_owner("no-towers", "llc", 3.0, towers=0))
    index = _index(tmp_path, owners)

    with Session(bind=engine, future=True) as s:
        first = seed(s, username="demo", index=index)
    assert first.password  # created now, shown once
    assert first.leads_created == len(STORYLINES)
    assert first.skipped is None

    with Session(bind=engine, future=True) as s:
        second = seed(s, username="demo", index=index)
        assert second.password is None
        assert second.leads_created == 0
        entry = credentials_store.get(s, "demo")
        assert entry is not None
        assert entry.read_only is True
        assert credentials_store.authenticate(s, "demo", first.password).ok
        leads = LeadStore(s, 1).list_leads()
        tasks = TaskStore(s, 1).list()

    by_id = {lead.display_cluster_id: lead.status for lead in leads}
    assert len(by_id) == len(STORYLINES)
    assert "person" not in by_id and "no-towers" not in by_id
    assert sorted(by_id.values()) == sorted(story.path[-1] for story in STORYLINES)
    assert len(tasks) == sum(1 for story in STORYLINES if story.task)
    assert all("Demo entry, fictional." in lead.notes for lead in leads)


def test_seed_reflags_an_existing_credential_read_only(engine, tmp_path) -> None:
    with Session(bind=engine, future=True) as s:
        credentials_store.add(s, "demo", "demo", "pw")
        result = seed(s, username="demo", index=_index(tmp_path, []))
        entry = credentials_store.get(s, "demo")
    assert result.password is None
    assert entry is not None
    assert entry.read_only is True


def test_seed_without_an_owners_index_still_creates_the_credential(engine, tmp_path) -> None:
    index = OwnersIndexService(tmp_path / "missing.json")
    with Session(bind=engine, future=True) as s:
        result = seed(s, username="demo", index=index)
        assert credentials_store.get(s, "demo") is not None
    assert result.password
    assert result.leads_created == 0
    assert result.skipped is not None
