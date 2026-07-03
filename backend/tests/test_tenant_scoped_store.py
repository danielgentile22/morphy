"""The TenantScopedStore base contract (ADR-055), proven once for every store.

Two tenants share one database; ``scoped`` / ``get_scoped`` must make the
other tenant's rows read as absent. Uses real models covering both PK shapes:
``Task`` (autoincrement id + tenant_id column → fetch-then-recheck) and
``AntennaOverride`` / ``UserSetting`` (tenant-prefixed composite PK → the
tenant is injected into the identity key).
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.app.models import AntennaOverride, Task, UserSetting
from backend.app.tenant_scoped_store import TenantScopedStore

pytestmark = pytest.mark.tenant_isolation

TENANT_A = 1
TENANT_B = 2


@pytest.fixture
def store_pair(engine):
    a = TenantScopedStore(Session(bind=engine, future=True), TENANT_A)
    b = TenantScopedStore(Session(bind=engine, future=True), TENANT_B)
    yield a, b
    a.session.close()
    b.session.close()


def _seed_tasks(session: Session) -> tuple[Task, Task]:
    ta = Task(tenant_id=TENANT_A, title="a's task")
    tb = Task(tenant_id=TENANT_B, title="b's task")
    session.add_all([ta, tb])
    session.commit()
    return ta, tb


def test_scoped_select_sees_only_own_tenant(store_pair):
    a, b = store_pair
    _seed_tasks(a.session)
    titles_a = [t.title for t in a.session.scalars(a.scoped(select(Task)))]
    titles_b = [t.title for t in b.session.scalars(b.scoped(select(Task)))]
    assert titles_a == ["a's task"]
    assert titles_b == ["b's task"]


def test_scoped_infers_entity_from_single_column_select(store_pair):
    a, b = store_pair
    a.session.add_all(
        [
            AntennaOverride(tenant_id=TENANT_A, asr="1000001", archived=True),
            AntennaOverride(tenant_id=TENANT_B, asr="1000002", archived=True),
        ]
    )
    a.session.commit()
    stmt = select(AntennaOverride.asr).where(AntennaOverride.archived.is_(True))
    assert set(a.session.scalars(a.scoped(stmt))) == {"1000001"}
    assert set(b.session.scalars(b.scoped(stmt))) == {"1000002"}


def test_scoped_aggregate_select_needs_explicit_model(store_pair):
    a, _ = store_pair
    _seed_tasks(a.session)
    stmt = select(func.count()).select_from(Task)
    with pytest.raises(ValueError, match="pass it explicitly"):
        a.scoped(stmt)
    assert a.session.scalar(a.scoped(stmt, Task)) == 1


def test_scoped_multi_entity_select_needs_explicit_model(store_pair):
    a, _ = store_pair
    # Guessing which of two entities to scope could leave the other table
    # unfiltered — the base must refuse rather than pick one.
    stmt = select(Task, AntennaOverride)
    with pytest.raises(ValueError, match="pass it explicitly"):
        a.scoped(stmt)


def test_get_scoped_rejects_wrong_composite_arity(store_pair):
    a, _ = store_pair
    with pytest.raises(ValueError, match="key component"):
        a.get_scoped(UserSetting, "theme")  # needs (user_id, key)
    with pytest.raises(ValueError, match="key component"):
        a.get_scoped(AntennaOverride, ("1234567", "extra"))


def test_scoped_update_and_delete_stay_within_tenant(store_pair):
    a, b = store_pair
    ta, tb = _seed_tasks(a.session)
    a.session.execute(a.scoped(update(Task).values(title="renamed")))
    a.session.commit()
    b.session.execute(b.scoped(delete(Task)))
    b.session.commit()
    survivors = list(a.session.scalars(select(Task)))  # unscoped: whole table
    assert [(t.tenant_id, t.title) for t in survivors] == [(TENANT_A, "renamed")]


def test_get_scoped_id_pk_is_invisible_across_tenants(store_pair):
    a, b = store_pair
    ta, tb = _seed_tasks(a.session)
    assert a.get_scoped(Task, ta.id) is not None
    assert a.get_scoped(Task, tb.id) is None
    assert b.get_scoped(Task, ta.id) is None
    assert a.get_scoped(Task, 99999) is None


def test_get_scoped_composite_pk_injects_tenant(store_pair):
    a, b = store_pair
    a.session.add(AntennaOverride(tenant_id=TENANT_A, asr="1234567"))
    a.session.commit()
    found = a.get_scoped(AntennaOverride, "1234567")
    assert found is not None and found.tenant_id == TENANT_A
    assert b.get_scoped(AntennaOverride, "1234567") is None


def test_get_scoped_multi_part_composite_pk(store_pair):
    a, b = store_pair
    a.session.add(UserSetting(tenant_id=TENANT_A, user_id=7, key="theme", value="dark"))
    a.session.commit()
    row = a.get_scoped(UserSetting, (7, "theme"))
    assert row is not None and row.value == "dark"
    assert b.get_scoped(UserSetting, (7, "theme")) is None
