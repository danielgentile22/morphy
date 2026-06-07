"""Scoring presets (UI overhaul P4 / #115): tenant-shared CRUD + single
default; store-level + API-level."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.app.scoring_preset_store import ScoringPresetStore

from ._helpers import api, auth_header, login

EMPTY_INDEX = {"schema_version": 5, "count": 0, "owners": []}


def _store(engine: Engine, tenant: int = 1) -> ScoringPresetStore:
    return ScoringPresetStore(Session(bind=engine, future=True), tenant)


def test_create_and_list(engine: Engine) -> None:
    _store(engine).create(name="Distressed rural", config='{"useDefault": false}')
    rows = _store(engine).list()
    assert [p.name for p in rows] == ["Distressed rural"]


def test_only_one_default_per_tenant(engine: Engine) -> None:
    a = _store(engine).create(name="A", config="{}", is_default=True)
    b = _store(engine).create(name="B", config="{}", is_default=True)  # supersedes A
    rows = {p.name: p.is_default for p in _store(engine).list()}
    assert rows == {"A": False, "B": True}
    # explicit set_default flips it back
    _store(engine).set_default(a.id)
    rows = {p.name: p.is_default for p in _store(engine).list()}
    assert rows == {"A": True, "B": False}
    assert b.id  # referenced


def test_delete(engine: Engine) -> None:
    p = _store(engine).create(name="X", config="{}")
    assert _store(engine).delete(p.id) is True
    assert _store(engine).list() == []
    assert _store(engine).delete(p.id) is False


def test_presets_are_tenant_scoped(engine: Engine) -> None:
    p = _store(engine, 1).create(name="team-1", config="{}")
    assert _store(engine, 2).list() == []
    assert _store(engine, 2).get(p.id) is None
    assert _store(engine, 2).set_default(p.id) is None
    assert _store(engine, 2).delete(p.id) is False


def test_presets_shared_within_a_tenant(engine: Engine) -> None:
    # Tenant-shared: created on one session, visible on another (no per-user).
    _store(engine, 1).create(name="shared", config='{"weights": {"distress": 1}}')
    assert [p.name for p in _store(engine, 1).list()] == ["shared"]


# ── API level ─────────────────────────────────────────────────────────────────
@pytest.fixture
def client() -> TestClient:
    with api(EMPTY_INDEX) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_api_create_list_default_delete(client: TestClient) -> None:
    created = client.post(
        "/api/scoring-presets",
        json={"name": "High-value metro", "config": {"useDefault": False, "weights": {"oz": 1}}},
    )
    assert created.status_code == 200
    pid = created.json()["id"]
    assert created.json()["config"]["weights"]["oz"] == 1  # config round-trips

    listed = client.get("/api/scoring-presets").json()
    assert listed["count"] == 1 and listed["presets"][0]["name"] == "High-value metro"

    made_default = client.post(f"/api/scoring-presets/{pid}/default")
    assert made_default.json()["is_default"] is True

    assert client.delete(f"/api/scoring-presets/{pid}").status_code == 204
    assert client.get("/api/scoring-presets").json()["count"] == 0


def test_api_create_requires_name(client: TestClient) -> None:
    assert client.post("/api/scoring-presets", json={"name": " ", "config": {}}).status_code == 422
