"""The credentials file is authoritative on every request (#88, PRD #83).

The session JWT proves *identity only* (subject = username). On each API
request the backend re-checks the credentials file — cached by mtime,
re-read when it changes — to confirm the username still exists and to
resolve its *current* team to its tenant. Removing a user or changing
their team takes effect on their very next request, not when their
session eventually expires.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

import jwt as pyjwt

from backend.app import credentials
from backend.app.config import settings
from backend.app.password import hash_password

from ._helpers import api, auth_header

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


@contextlib.contextmanager
def users_file(*lines: str) -> Iterator[Path]:
    """Replace the test credentials file's content; restore afterward."""
    creds = Path(settings.credentials_path)
    original = creds.read_text()
    creds.write_text("\n".join(lines) + "\n")
    try:
        yield creds
    finally:
        creds.write_text(original)


def cred(username: str, password: str, team: str) -> str:
    return f"{username}:{hash_password(password)}:{team}"


def sign_in(client, username: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    client.cookies.clear()  # header-driven identities — the cookie would outrank them
    return auth_header(r.json()["access_token"])


# ── revocation: removal from the file kills the session on the next request ──
def test_a_removed_user_gets_401_on_their_very_next_request() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(cred("dev", "dev", "devteam"), cred("alice", "pw", "devteam")) as f:
            alice = sign_in(client, "alice", "pw")
            assert client.get("/api/candidates", headers=alice).status_code == 200

            # The admin removes alice from the file (no backend restart).
            f.write_text(cred("dev", "dev", "devteam") + "\n")

            # Her very next request is rejected — the unexpired JWT is not enough.
            assert client.get("/api/candidates", headers=alice).status_code == 401
            assert client.get("/api/auth/me", headers=alice).status_code == 401


# ── re-teaming: the file decides which board a session operates on ───────────
def test_a_team_change_in_the_file_re_homes_the_session_on_its_next_request() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw", "team-rocket"),
            cred("bob", "pw-b", "team-rocket"),
        ) as f:
            alice = sign_in(client, "alice", "pw")
            client.put(f"/api/leads/{CID}", headers=alice, json={"status": "researching"})
            assert client.get("/api/auth/me", headers=alice).json()["team"] == "team-rocket"

            # The admin moves alice to a new team — alice does NOT log in again.
            f.write_text(
                "\n".join(
                    [
                        cred("dev", "dev", "devteam"),
                        cred("alice", "pw", "team-plasma"),
                        cred("bob", "pw-b", "team-rocket"),
                    ]
                )
                + "\n"
            )

            # Her same session now operates on the new team's (fresh) board.
            me = client.get("/api/auth/me", headers=alice).json()
            assert me["team"] == "team-plasma"
            assert client.get(f"/api/leads/{CID}", headers=alice).json()["status"] == "new"

            # The old team's data is untouched: bob still sees it.
            bob = sign_in(client, "bob", "pw-b")
            assert client.get(f"/api/leads/{CID}", headers=bob).json()["status"] == "researching"


# ── the unchanged-file fast path ──────────────────────────────────────────────
def test_an_unchanged_file_is_not_reparsed_per_request(monkeypatch) -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(cred("dev", "dev", "devteam")):
            dev = sign_in(client, "dev", "dev")
            assert client.get("/api/candidates", headers=dev).status_code == 200

            # Once warm, repeated requests against an unchanged file must not
            # re-parse it (mtime short-circuits).
            calls: list[int] = []
            real_parse = credentials.parse

            def counting_parse(text: str):
                calls.append(1)
                return real_parse(text)

            monkeypatch.setattr(credentials, "parse", counting_parse)
            for _ in range(5):
                assert client.get("/api/candidates", headers=dev).status_code == 200
            assert calls == []  # zero re-parses across 5 requests


def test_a_session_keeps_working_against_an_unchanged_file() -> None:
    # The 30-day TTL still holds: same token, many requests, no interference.
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(cred("dev", "dev", "devteam")):
            dev = sign_in(client, "dev", "dev")
            for _ in range(3):
                assert client.get("/api/auth/me", headers=dev).status_code == 200
                assert client.get("/api/counts", headers=dev).status_code == 200


# ── the JWT is identity-only ──────────────────────────────────────────────────
def test_the_jwt_carries_identity_only_no_tenant_claim() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(cred("dev", "dev", "devteam")):
            r = client.post("/api/auth/login", json={"username": "dev", "password": "dev"})
            token = r.json()["access_token"]
            # Decode without verification just to inspect the claims shape.
            claims = pyjwt.decode(token, options={"verify_signature": False})
            assert claims["sub"] == "dev"
            assert "tid" not in claims  # no tenant claim — resolved per request
            assert "email" not in claims  # sub IS the identity; nothing else


def test_a_forged_tenant_claim_cannot_grant_access_to_another_board() -> None:
    """Even a token signed with the real secret but carrying extra claims
    gets its authorization from the FILE, not from anything in the token."""
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(
            cred("dev", "dev", "devteam"),
            cred("alice", "pw", "team-rocket"),
        ):
            alice = sign_in(client, "alice", "pw")
            client.put(f"/api/leads/{CID}", headers=alice, json={"status": "researching"})

            # Forge a token for dev with a bogus "tid" claim pointing at
            # alice's tenant. The claim must be ignored.
            forged = pyjwt.encode(
                {"sub": "dev", "tid": 2, "exp": 9999999999},
                settings.jwt_secret,
                algorithm=settings.jwt_algorithm,
            )
            view = client.get(f"/api/leads/{CID}", headers=auth_header(forged)).json()
            # dev's team is devteam (tenant 1) → sees its own fresh board,
            # NOT alice's researching state.
            assert view["status"] == "new"


# ── login outcomes also follow the file without restart (mtime path) ─────────
def test_login_outcomes_follow_file_edits_without_restart() -> None:
    with api(SAMPLE) as (client, _eng, _sender):
        with users_file(cred("dev", "dev", "devteam")) as f:
            # Not in the file yet.
            r = client.post("/api/auth/login", json={"username": "carol", "password": "pw"})
            assert r.status_code == 401

            # Appended to the file → next login succeeds, no restart.
            f.write_text(f.read_text() + cred("carol", "pw", "newteam") + "\n")
            r = client.post("/api/auth/login", json={"username": "carol", "password": "pw"})
            assert r.status_code == 200
