"""The user-management surface from the CLI's point of view (#87 → PRD #130).

The command *functions* the CLI shell drives live in ``credentials_store``
and carry their own unit surface (test_credentials_store.py). This module
pins what the CLI exists for end-to-end:

  * a store-added user can really sign in over HTTP (the add → login loop);
  * the one-shot ``import-file`` migration: a seeded users.txt imports with
    **identical login outcomes and tenant assignments** — the first team in
    the file keeps tenant 1 and its pre-teams lead board (PRD #130 user
    story 9).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.app import credentials, credentials_store
from backend.app.models import Lead
from backend.app.password import hash_password

from ._helpers import api, auth_header, seed_credential

SAMPLE = {
    "schema_version": 1,
    "count": 1,
    "owners": [
        {
            "display_cluster_id": "nat0000aaaa",
            "owner_name": "AMERICAN TOWERS LLC",
            "owner_name_norm": "AMERICAN TOWERS",
            "owner_kind": "llc",
            "states": ["AR"],
            "n_states": 1,
            "cross_state": False,
            "parcel_count": 1,
            "tower_count": 3,
            "solar_count": 0,
            "total_assessed_value": 1.0,
            "max_parcel_score": 0.5,
            "score": 0.5,
            "distress_tier": "at-risk",
            "in_oz": False,
            "in_qct": False,
            "persistent_poverty": False,
        }
    ],
}

CID = "nat0000aaaa"


# ── end-to-end: a store-added user signs in over HTTP ─────────────────────────
def test_an_added_user_can_sign_in_through_the_api() -> None:
    with api(SAMPLE) as (client, eng, _sender):
        seed_credential(eng, "cli-user", "cli-password", "devteam")
        r = client.post(
            "/api/auth/login", json={"username": "cli-user", "password": "cli-password"}
        )
        assert r.status_code == 200
        assert r.json()["access_token"]


# ── the one-shot users.txt migration (PRD #130) ───────────────────────────────
def _users_txt(tmp_path: Path) -> Path:
    f = tmp_path / "users.txt"
    f.write_text(
        "# the original team must stay first (tenant 1)\n"
        f"alice:{hash_password('pw-a')}:first-team\n"
        f"bob:{hash_password('pw-b')}:second-team\n",
        encoding="utf-8",
    )
    return f


def test_import_file_yields_identical_login_outcomes_and_tenants(tmp_path: Path) -> None:
    """The PRD's migration bar: seeded file → import → the same usernames sign
    in with the same passwords, the first team keeps tenant 1 (inheriting the
    pre-teams board), and the second team gets its own."""
    users_txt = _users_txt(tmp_path)

    with api(SAMPLE) as (client, eng, _sender):
        # An importable table must be empty — drop the api() dev seed first.
        with Session(bind=eng, future=True) as s:
            credentials_store.remove(s, "dev")
            entries = list(credentials.load(users_txt).values())
            assert credentials_store.import_entries(s, entries) == 2

        # Pre-existing tenant-1 lead state (the pre-teams board).
        with Session(bind=eng, future=True) as s:
            s.add(Lead(tenant_id=1, display_cluster_id=CID, status="contacted", notes="old"))
            s.commit()

        def sign_in(username: str, password: str) -> dict:
            r = client.post("/api/auth/login", json={"username": username, "password": password})
            assert r.status_code == 200, r.text
            client.cookies.clear()
            return auth_header(r.json()["access_token"])

        # Identical login outcomes: the same passwords work, wrong ones get the
        # same specific 401s as before the migration.
        alice = sign_in("alice", "pw-a")
        bob = sign_in("bob", "pw-b")
        r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
        assert (r.status_code, r.json()["detail"]) == (401, "Incorrect password")
        r = client.post("/api/auth/login", json={"username": "ghost", "password": "x"})
        assert (r.status_code, r.json()["detail"]) == (401, "Unknown username")

        # Tenant assignments preserved: alice's first-team owns tenant 1 and
        # the pre-teams board; bob's second-team is tenant 2, fresh board.
        alice_me = client.get("/api/auth/me", headers=alice).json()
        bob_me = client.get("/api/auth/me", headers=bob).json()
        assert (alice_me["tenant_id"], alice_me["team"]) == (1, "first-team")
        assert (bob_me["tenant_id"], bob_me["team"]) == (2, "second-team")
        assert client.get(f"/api/leads/{CID}", headers=alice).json()["status"] == "contacted"
        assert client.get(f"/api/leads/{CID}", headers=bob).json()["status"] == "new"


def test_import_file_refuses_to_run_twice(tmp_path: Path) -> None:
    users_txt = _users_txt(tmp_path)
    with api(SAMPLE) as (_client, eng, _sender):
        # api() already seeded dev — the table is non-empty, so the one-shot
        # import must refuse rather than merge.
        with Session(bind=eng, future=True) as s:
            entries = list(credentials.load(users_txt).values())
            try:
                credentials_store.import_entries(s, entries)
                raised = False
            except credentials_store.CredentialsError:
                raised = True
            assert raised
            assert credentials_store.count(s) == 1  # just dev — nothing merged
