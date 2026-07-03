"""TenantScopedStore — the one home for the tenant filter (ADR-055).

Every tenant-scoped store subclasses this and routes its reads and bulk
writes through :meth:`scoped` / :meth:`get_scoped` instead of hand-writing
``tenant_id`` conditions. The two historical idioms collapse here:

- where-clause on a select/update/delete → ``scoped(stmt)``;
- fetch-by-PK-then-recheck-in-Python, *and* the composite-PK variant where
  ``tenant_id`` is part of the primary key → ``get_scoped(Model, pk)``.

Inserts are not filters: stores still stamp ``tenant_id=self.tenant_id`` on
new rows explicitly.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from sqlalchemy import Delete, Select, Update, inspect
from sqlalchemy.orm import Session

_M = TypeVar("_M")
_StmtT = TypeVar("_StmtT", Select[Any], Update, Delete)


def _statement_entity(stmt: Select[Any] | Update | Delete) -> type[Any]:
    """The mapped class a statement operates on, for the tenant filter."""
    if isinstance(stmt, Select):
        entities = {
            entity
            for desc in stmt.column_descriptions
            if (entity := desc.get("entity")) is not None
        }
        if len(entities) == 1:
            return entities.pop()
        # Zero (e.g. select(func.count())) or several (a join) — guessing
        # either way could scope the wrong table, so refuse.
        raise ValueError(
            "cannot infer the model from this select; pass it explicitly: scoped(stmt, Model)"
        )
    return stmt.entity_description["entity"]


class TenantScopedStore:
    """Base for stores whose every read and write belongs to one tenant."""

    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def scoped(self, stmt: _StmtT, model: type[Any] | None = None) -> _StmtT:
        """``stmt`` narrowed to this tenant. The model is inferred from the
        statement; pass it explicitly only when there is no mapped entity to
        infer from (aggregate selects like ``select(func.count())``)."""
        target = model if model is not None else _statement_entity(stmt)
        return stmt.where(target.tenant_id == self.tenant_id)

    def get_scoped(self, model: type[_M], pk: Any) -> _M | None:
        """PK fetch that is invisible across tenants.

        When ``tenant_id`` is part of ``model``'s primary key, it is injected
        into the identity key (callers pass only the non-tenant components).
        Otherwise the row is fetched by PK and re-checked, so a row from
        another tenant reads as absent.
        """
        mapper = inspect(model)
        if mapper is None:
            raise ValueError(f"{model!r} is not a mapped class")
        pk_cols = [c.key for c in mapper.primary_key]
        if "tenant_id" in pk_cols:
            parts = pk if isinstance(pk, tuple) else (pk,)
            if len(parts) != len(pk_cols) - 1:
                raise ValueError(
                    f"{model.__name__} needs {len(pk_cols) - 1} key component(s) "
                    f"besides tenant_id, got {len(parts)}"
                )
            rest = iter(parts)
            key = tuple(self.tenant_id if col == "tenant_id" else next(rest) for col in pk_cols)
            return self.session.get(model, key)
        obj = self.session.get(model, pk)
        if obj is None or cast(Any, obj).tenant_id != self.tenant_id:
            return None
        return obj
