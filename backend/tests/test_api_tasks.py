"""Task API (UI overhaul P2 / #107) over HTTP with a real JWT: create, list,
complete, and 404/422 + auth behavior."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ._helpers import api, auth_header, login

# Tasks don't read the owners index; an empty one is fine.
EMPTY_INDEX = {"schema_version": 5, "count": 0, "owners": []}


@pytest.fixture
def client() -> Iterator[TestClient]:
    with api(EMPTY_INDEX) as (c, _eng, _sender):
        c.headers.update(auth_header(login(c)))
        yield c


def test_create_list_and_complete(client: TestClient) -> None:
    created = client.post("/api/tasks", json={"title": "Call Michael", "description": "re: tower"})
    assert created.status_code == 200
    body = created.json()
    assert (body["title"], body["status"], body["completed_at"]) == ("Call Michael", "open", None)
    # the creator (dev user) is recorded
    assert body["created_by_user_id"] is not None
    tid = body["id"]

    listed = client.get("/api/tasks").json()
    assert listed["count"] == 1 and listed["tasks"][0]["id"] == tid

    done = client.put(f"/api/tasks/{tid}", json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert done.json()["completed_at"] is not None


def test_create_requires_a_title(client: TestClient) -> None:
    assert client.post("/api/tasks", json={"title": "  "}).status_code == 422


def test_update_rejects_a_bad_status(client: TestClient) -> None:
    tid = client.post("/api/tasks", json={"title": "x"}).json()["id"]
    assert client.put(f"/api/tasks/{tid}", json={"status": "bogus"}).status_code == 422


def test_get_and_update_unknown_task_is_404(client: TestClient) -> None:
    assert client.get("/api/tasks/999999").status_code == 404
    assert client.put("/api/tasks/999999", json={"status": "done"}).status_code == 404
    assert client.delete("/api/tasks/999999").status_code == 404


def test_delete_removes_the_task(client: TestClient) -> None:
    tid = client.post("/api/tasks", json={"title": "trash"}).json()["id"]
    assert client.delete(f"/api/tasks/{tid}").status_code == 204
    assert client.get(f"/api/tasks/{tid}").status_code == 404


def test_tasks_require_auth(client: TestClient) -> None:
    # Strip the bearer header → 401 (every data route is tenant-scoped + gated).
    assert client.get("/api/tasks", headers={"Authorization": ""}).status_code == 401


# ── links / assignee / filtering / search (#110) ─────────────────────────────
def test_create_with_links_and_filter(client: TestClient) -> None:
    client.post(
        "/api/tasks",
        json={
            "title": "call Michael",
            "description": "re: tower",
            "priority": "high",
            "lead_cluster_id": "cidA",
            "tower_asr": "000046",
            "labels": ["Outreach", "outreach"],
        },
    )
    client.post("/api/tasks", json={"title": "buy coffee", "priority": "low"})

    body = client.post("/api/tasks", json={"title": "linked"}).json()
    assert body["labels"] == [] and body["source"] == "manual"

    # filter by linked owner
    leadq = client.get("/api/tasks?lead=cidA").json()
    assert leadq["count"] == 1 and leadq["tasks"][0]["title"] == "call Michael"
    assert leadq["tasks"][0]["labels"] == ["outreach"]  # normalized + de-duped
    # filter by priority
    assert client.get("/api/tasks?priority=high").json()["count"] == 1
    # free-text search over title/description
    assert client.get("/api/tasks?q=michael").json()["count"] == 1
    assert client.get("/api/tasks?q=re%3A%20tower").json()["count"] == 1
    # filter by tower
    assert client.get("/api/tasks?tower=000046").json()["count"] == 1


def test_assign_and_clear_via_put(client: TestClient) -> None:
    tid = client.post("/api/tasks", json={"title": "assign me"}).json()["id"]
    # assign
    assigned = client.put(f"/api/tasks/{tid}", json={"assignee_user_id": 1}).json()
    assert assigned["assignee_user_id"] == 1
    # clearing with explicit null unassigns; omitting would leave it
    cleared = client.put(f"/api/tasks/{tid}", json={"assignee_user_id": None}).json()
    assert cleared["assignee_user_id"] is None


def test_bad_priority_rejected(client: TestClient) -> None:
    assert client.post("/api/tasks", json={"title": "x", "priority": "urgent"}).status_code == 422


def test_users_roster_lists_the_tenant(client: TestClient) -> None:
    # The dev login provisioned the dev user; the roster lists it with a name.
    body = client.get("/api/users").json()
    assert body["count"] >= 1
    u = body["users"][0]
    assert u["email"] and u["name"]  # name falls back to email when no display_name
