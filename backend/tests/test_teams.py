"""Teams as tenants (#86, PRD #83).

A team IS a tenant: the `tenant` table records id + unique normalized name,
teams are find-or-created in credentials-file order (so the first team in the
file receives tenant 1 and inherits the pre-teams lead board), and login
resolves the user's team to its tenant. Teammates share one board; different
teams' boards are invisible to each other — enforced by the existing
tenant scoping, driven here through real logins.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app import credentials
from backend.app.config import settings
from backend.app.models import Lead, Tenant
from backend.app.password import hash_password
from backend.app.tenant_service import TenantService

from ._helpers import api, auth_header

# A tiny owners index so the data routes resolve (one owner, status New).
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


# ── credentials-file helpers ──────────────────────────────────────────────────
@contextlib.contextmanager
def users_file(*lines: str) -> Iterator[None]:
    """Replace the test credentials file's content; restore afterward.

    Login re-reads the file, so the swapped users are live immediately.
    """
    creds = Path(settings.credentials_path)
    original = creds.read_text()
    creds.write_text("\n".join(lines) + "\n")
    try:
        yield
    finally:
        creds.write_text(original)


def cred(username: str, password: str, team: str) -> str:
    return f"{username}:{hash_password(password)}:{team}"


def sign_in(client, username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return auth_header(r.json()["access_token"])


# ── team registration (file order) ────────────────────────────────────────────
def test_teams_register_in_file_order_first_team_gets_tenant_1(new_session) -> None:
    svc = TenantService(new_session())
    tenants = svc.register_teams(["team-original", "team-second", "team-third"])
    assert tenants["team-original"].id == 1
    assert tenants["team-second"].id == 2
    assert tenants["team-third"].id == 3


def test_same_team_name_resolves_to_the_same_tenant_on_repeat(new_session) -> None:
    svc = TenantService(new_session())
    first = svc.register_teams(["acme", "globex"])
    again = TenantService(new_session()).register_teams(["acme", "globex"])
    assert again["acme"].id == first["acme"].id
    assert again["globex"].id == first["globex"].id


def test_a_new_team_appended_later_gets_a_new_tenant_not_an_existing_one(new_session) -> None:
    svc = TenantService(new_session())
    svc.register_teams(["acme"])
    tenants = TenantService(new_session()).register_teams(["acme", "newteam"])
    assert tenants["acme"].id == 1
    assert tenants["newteam"].id == 2


def test_teams_in_file_order_helper_is_first_appearance_order() -> None:
    users = credentials.parse(
        "\n".join(
            [
                f"alice:{hash_password('a')}:team-b",
                f"bob:{hash_password('b')}:team-a",
                f"carol:{hash_password('c')}:team-b",  # team-b already seen
            ]
        )
    )
    assert credentials.teams_in_file_order(users) == ["team-b", "team-a"]


# ── login resolves the team to its tenant ─────────────────────────────────────
def test_login_lands_each_user_on_their_teams_tenant() -> None:
    with (
        users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw-a", "team-rocket"),
            cred("carol", "pw-c", "team-plasma"),
        ),
        api(SAMPLE) as (client, _eng, _sender),
    ):
        dev_me = client.get("/api/auth/me", headers=sign_in(client, "dev", "dev")).json()
        alice_me = client.get("/api/auth/me", headers=sign_in(client, "alice", "pw-a")).json()
        carol_me = client.get("/api/auth/me", headers=sign_in(client, "carol", "pw-c")).json()

        # File order: devteam → 1, team-rocket → 2, team-plasma → 3.
        assert dev_me["tenant_id"] == 1
        assert alice_me["tenant_id"] == 2
        assert carol_me["tenant_id"] == 3
        # The identity endpoint reports the team name.
        assert dev_me["team"] == "devteam"
        assert alice_me["team"] == "team-rocket"
        assert carol_me["team"] == "team-plasma"


# ── shared board / isolation, driven through real logins ──────────────────────
def test_teammates_share_one_board_and_other_teams_are_isolated() -> None:
    with (
        users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw-a", "team-rocket"),
            cred("bob", "pw-b", "team-rocket"),
            cred("carol", "pw-c", "team-plasma"),
        ),
        api(SAMPLE) as (client, _eng, _sender),
    ):
        alice = sign_in(client, "alice", "pw-a")
        bob = sign_in(client, "bob", "pw-b")
        carol = sign_in(client, "carol", "pw-c")

        # Alice advances the owner and leaves a note + a contact attempt.
        client.put(
            f"/api/leads/{CID}", headers=alice, json={"status": "researching", "notes": "ours"}
        )
        client.post(
            f"/api/leads/{CID}/attempts",
            headers=alice,
            json={"channel": "phone", "outcome": "no answer"},
        )

        # Bob (same team) sees all of it.
        bob_view = client.get(f"/api/leads/{CID}", headers=bob).json()
        assert bob_view["status"] == "researching"
        assert bob_view["notes"] == "ours"
        assert len(bob_view["attempts"]) > 0
        # And bob's counts reflect the shared board.
        assert client.get("/api/counts", headers=bob).json() == {"candidates": 0, "my_leads": 1}

        # Carol (another team) sees none of it.
        carol_view = client.get(f"/api/leads/{CID}", headers=carol).json()
        assert carol_view["status"] == "new"
        assert carol_view["notes"] == ""
        assert carol_view["attempts"] == []
        assert client.get("/api/counts", headers=carol).json() == {"candidates": 1, "my_leads": 0}


def test_owner_merges_are_per_team() -> None:
    two_owner_sample = {
        "schema_version": 1,
        "count": 2,
        "owners": [
            SAMPLE["owners"][0],
            {**SAMPLE["owners"][0], "display_cluster_id": "nat0000bbbb", "owner_name": "B LLC"},
        ],
    }
    with (
        users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw-a", "team-rocket"),
            cred("carol", "pw-c", "team-plasma"),
        ),
        api(two_owner_sample) as (client, _eng, _sender),
    ):
        alice = sign_in(client, "alice", "pw-a")
        carol = sign_in(client, "carol", "pw-c")

        # Alice merges B into A — for her team only.
        r = client.post(
            f"/api/leads/{CID}/merge", headers=alice, json={"source_cluster_id": "nat0000bbbb"}
        )
        assert r.status_code == 200
        assert [m["display_cluster_id"] for m in r.json()["merged_members"]] == ["nat0000bbbb"]

        # Carol's view of A has no merged members; B is still its own Lead.
        carol_a = client.get(f"/api/leads/{CID}", headers=carol).json()
        assert carol_a["merged_members"] == []
        assert client.get("/api/leads/nat0000bbbb", headers=carol).status_code == 200


# ── the first team inherits the pre-teams board ───────────────────────────────
def test_first_team_in_file_inherits_pre_existing_tenant_1_lead_state() -> None:
    with (
        users_file(
            cred("dev", "dev", "devteam"),
            cred("carol", "pw-c", "team-plasma"),
        ),
        api(SAMPLE) as (client, eng, _sender),
    ):
        # Pre-teams data: a lead advanced under tenant 1 before the tenant
        # table ever existed (no Tenant row points at it).
        with Session(bind=eng, future=True) as s:
            s.add(Lead(tenant_id=1, display_cluster_id=CID, status="contacted", notes="old"))
            s.commit()

        # dev is the FIRST team in the file → devteam registers as tenant 1 →
        # the old board is theirs.
        dev = sign_in(client, "dev", "dev")
        view = client.get(f"/api/leads/{CID}", headers=dev).json()
        assert view["status"] == "contacted"
        assert view["notes"] == "old"

        # carol's team registered second → tenant 2 → sees a fresh board.
        carol = sign_in(client, "carol", "pw-c")
        assert client.get(f"/api/leads/{CID}", headers=carol).json()["status"] == "new"


# ── team changes in the file re-home the user ─────────────────────────────────
def test_changing_a_users_team_re_homes_them_on_next_login() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw-a", "team-rocket"),
        ):
            alice = sign_in(client, "alice", "pw-a")
            client.put(f"/api/leads/{CID}", headers=alice, json={"status": "researching"})
            assert client.get("/api/auth/me", headers=alice).json()["team"] == "team-rocket"

        # The admin moves alice to a different team.
        with users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw-a", "team-plasma"),
        ):
            alice2 = sign_in(client, "alice", "pw-a")
            me = client.get("/api/auth/me", headers=alice2).json()
            assert me["team"] == "team-plasma"
            # She now operates on the new team's (empty) board…
            assert client.get(f"/api/leads/{CID}", headers=alice2).json()["status"] == "new"

        # …and team-rocket's data was not moved or deleted.
        with users_file(
            cred("dev", "dev", "devteam"),
            cred("bob", "pw-b", "team-rocket"),
        ):
            bob = sign_in(client, "bob", "pw-b")
            assert client.get(f"/api/leads/{CID}", headers=bob).json()["status"] == "researching"


# ── concurrent registration of the same new team ─────────────────────────────
def test_two_sessions_racing_to_register_a_team_both_get_the_same_tenant(new_session) -> None:
    """Simulates the lost race: session B checks (team absent), session A
    registers it, then B's insert hits the unique constraint. B must
    recover with A's row — never surface a 500 to the login route."""
    svc_a = TenantService(new_session())
    svc_b = TenantService(new_session())

    # B's check-then-act is interleaved with A's registration: monkeypatch
    # B's "check" to simulate having seen no row (the stale read).
    original_get = svc_b.get_by_name
    reads: list[str] = []

    def stale_first_read(name: str):
        if not reads:
            reads.append(name)
            return None  # B saw "absent" before A committed
        return original_get(name)

    svc_b.get_by_name = stale_first_read  # type: ignore[method-assign]
    a_tenant = svc_a.find_or_create("acme")
    b_tenant = svc_b.find_or_create("acme")  # insert collides → recovers

    assert a_tenant.id == b_tenant.id == 1


# ── tenant rows are never deleted ──────────────────────────────────────────────
def test_a_team_with_no_remaining_users_keeps_its_tenant_and_data(new_session) -> None:
    svc = TenantService(new_session())
    svc.register_teams(["acme", "globex"])
    # All of acme's users are removed from the file; only globex remains.
    TenantService(new_session()).register_teams(["globex"])
    session = new_session()
    names = sorted(t.name for t in session.query(Tenant).all())
    assert names == ["acme", "globex"]  # acme's tenant row survives
