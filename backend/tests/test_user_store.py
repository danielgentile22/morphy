"""UserStore unit tests (#261) — two-tenant scoping off the app.

The HTTP isolation suite can't observe an unscoped ``names_by_id`` (lookups
are keyed by the caller's own user ids), so the store level is where that
leak is provable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.models import User
from backend.app.user_store import UserStore


def _store(engine, tenant_id: int) -> UserStore:
    return UserStore(Session(bind=engine, future=True), tenant_id)


def _seed(session: Session) -> tuple[User, User, User]:
    alice = User(tenant_id=1, email="alice@a.test", display_name="Alice")
    bob = User(tenant_id=1, email="bob@a.test", display_name="")
    eve = User(tenant_id=2, email="eve@b.test", display_name="Eve")
    session.add_all([alice, bob, eve])
    session.commit()
    return alice, bob, eve


def test_names_by_id_is_tenant_scoped(engine) -> None:
    a, b = _store(engine, 1), _store(engine, 2)
    alice, bob, eve = _seed(a.session)
    assert a.names_by_id() == {alice.id: "Alice", bob.id: "bob@a.test"}  # email fallback
    assert b.names_by_id() == {eve.id: "Eve"}


def test_list_by_email_is_tenant_scoped_and_ordered(engine) -> None:
    a, b = _store(engine, 1), _store(engine, 2)
    _seed(a.session)
    assert [u.email for u in a.list_by_email()] == ["alice@a.test", "bob@a.test"]
    assert [u.email for u in b.list_by_email()] == ["eve@b.test"]


def test_get_and_set_display_name_are_tenant_scoped(engine) -> None:
    a, b = _store(engine, 1), _store(engine, 2)
    alice, _bob, _eve = _seed(a.session)
    assert b.get(alice.id) is None
    assert b.set_display_name(alice.id, "hijacked") is None
    updated = a.set_display_name(alice.id, "  Alice A.  ")
    assert updated is not None and updated.display_name == "Alice A."  # trimmed
