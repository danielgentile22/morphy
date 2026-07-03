"""Tenant-scoped reads/writes over the ``User`` identity table (PRD #253 W1).

The team roster, stats/activity name-lookups, and the display-name edit
previously queried the ORM straight from route bodies — the one tenant-scoped
entity with no store, so its filter was hand-written and isolation-untested.
Every user query now flows through here, on the ``TenantScopedStore`` base.
"""

from __future__ import annotations

from sqlalchemy import select

from .models import User
from .tenant_scoped_store import TenantScopedStore


class UserStore(TenantScopedStore):
    def get(self, user_id: int) -> User | None:
        return self.get_scoped(User, user_id)

    def names_by_id(self) -> dict[int, str]:
        """``user_id → render name`` (the ``User.name`` rule) for the tenant."""
        rows = self.session.scalars(self.scoped(select(User)))
        return {u.id: u.name for u in rows}

    def list_by_email(self) -> list[User]:
        """The tenant's teammates, ordered by email — the task-assignment roster."""
        return list(self.session.scalars(self.scoped(select(User).order_by(User.email))))

    def set_display_name(self, user_id: int, display_name: str) -> User | None:
        """Set a teammate's display name (trimmed; '' falls back to email at
        render sites). Returns None when the user isn't this tenant's."""
        user = self.get(user_id)
        if user is None:
            return None
        user.display_name = display_name.strip()
        self.session.commit()
        return user
