"""Per-user self-service endpoints (PRD #121): /api/me/settings, /api/me,
/api/me/password.

Drives the real HTTP surface the SPA uses (sign in → bearer token → call),
asserting the user-scoped behavior a teammate would feel: defaults before any
write, settings isolated between two teammates on the *same* board, display-name
updates, and the security-critical password change (wrong current → 401, the
file untouched; success → the new credential is live on the next login).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path

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


@contextlib.contextmanager
def users_file(*lines: str) -> Iterator[None]:
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
    client.cookies.clear()  # header-driven identities — the cookie would outrank them
    return auth_header(r.json()["access_token"])


# ── GET/PUT /api/me/settings ──────────────────────────────────────────────────
def test_get_settings_returns_sane_defaults_for_a_fresh_user() -> None:
    with users_file(cred("alice", "pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "pw")
        body = client.get("/api/me/settings", headers=h).json()
        assert body == {
            "theme": "system",
            "colorblind": False,
            "basemap": "light",
            "view_mode": "last",
            "home_view": "",
            "filter_default": "",
            "filter_default_apply": False,
        }


def test_put_settings_upserts_some_keys_and_returns_resolved() -> None:
    with users_file(cred("alice", "pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "pw")
        r = client.put(
            "/api/me/settings",
            headers=h,
            json={"theme": "dark", "colorblind": True, "basemap": "voyager"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["theme"] == "dark"
        assert body["colorblind"] is True
        assert body["basemap"] == "voyager"
        # untouched keys keep their defaults
        assert body["view_mode"] == "last"
        # the change persisted across a fresh GET
        assert client.get("/api/me/settings", headers=h).json()["theme"] == "dark"


def test_put_settings_ignores_explicit_null_values() -> None:
    # An explicit null means "leave unchanged" — it must never store the string
    # "None" (which would read back as a garbage theme).
    with users_file(cred("alice", "pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "pw")
        client.put("/api/me/settings", headers=h, json={"theme": "dark"})
        r = client.put("/api/me/settings", headers=h, json={"theme": None, "basemap": "voyager"})
        body = r.json()
        assert body["theme"] == "dark"  # untouched, not "None"
        assert body["basemap"] == "voyager"


def test_put_settings_persists_opaque_blobs_verbatim() -> None:
    blob = '{"states":["AR","MT"],"assessedValue":[1000,50000]}'
    with users_file(cred("alice", "pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "pw")
        client.put("/api/me/settings", headers=h, json={"filter_default": blob})
        assert client.get("/api/me/settings", headers=h).json()["filter_default"] == blob


def test_settings_are_isolated_between_teammates_on_one_board() -> None:
    with (
        users_file(cred("alice", "pw-a", "team-rocket"), cred("bob", "pw-b", "team-rocket")),
        api(SAMPLE) as (client, _eng, _s),
    ):
        alice = sign_in(client, "alice", "pw-a")
        bob = sign_in(client, "bob", "pw-b")

        client.put("/api/me/settings", headers=alice, json={"theme": "dark"})

        # Same team, but Bob's preferences are his own — still the default.
        assert client.get("/api/me/settings", headers=bob).json()["theme"] == "system"
        assert client.get("/api/me/settings", headers=alice).json()["theme"] == "dark"


def test_settings_require_authentication() -> None:
    with api(SAMPLE) as (client, _eng, _s):
        assert client.get("/api/me/settings").status_code == 401


# ── PUT /api/me (display name) ────────────────────────────────────────────────
def test_display_name_is_blank_by_default_and_settable() -> None:
    with users_file(cred("alice", "pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "pw")
        assert client.get("/api/auth/me", headers=h).json()["display_name"] == ""

        r = client.put("/api/me", headers=h, json={"display_name": "Alice A."})
        assert r.status_code == 200, r.text
        assert r.json()["display_name"] == "Alice A."
        # reflected on the identity endpoint the SPA loads on boot
        assert client.get("/api/auth/me", headers=h).json()["display_name"] == "Alice A."


# ── POST /api/me/password ─────────────────────────────────────────────────────
def test_password_change_wrong_current_is_401_and_login_unaffected() -> None:
    with users_file(cred("alice", "right-pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "right-pw")
        r = client.post(
            "/api/me/password",
            headers=h,
            json={"current_password": "WRONG", "new_password": "brand-new-pw"},
        )
        assert r.status_code == 401
        # the old password still signs in — nothing changed
        assert (
            client.post(
                "/api/auth/login", json={"username": "alice", "password": "right-pw"}
            ).status_code
            == 200
        )


def test_password_change_success_makes_the_new_credential_live() -> None:
    with users_file(cred("alice", "old-pw", "acme")), api(SAMPLE) as (client, _eng, _s):
        h = sign_in(client, "alice", "old-pw")
        r = client.post(
            "/api/me/password",
            headers=h,
            json={"current_password": "old-pw", "new_password": "fresh-pw"},
        )
        assert r.status_code in (200, 204), r.text

        # the new password logs in on the very next request; the old one is dead
        assert (
            client.post(
                "/api/auth/login", json={"username": "alice", "password": "fresh-pw"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/auth/login", json={"username": "alice", "password": "old-pw"}
            ).status_code
            == 401
        )
