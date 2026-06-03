"""Team → tenant resolution (#86, PRD #83).

Session-scoped like ``LeadStore`` / ``OwnerMergeService``. Teams ARE tenants
(no new isolation machinery): this service only find-or-creates ``Tenant``
rows by normalized team name, **in credentials-file order**, so the first
team in the file always receives tenant id 1 and thereby inherits the
pre-teams lead board. Tenant rows are never deleted — a team whose users
are all removed from the file keeps its board.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Tenant


class TenantService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def register_teams(self, names_in_file_order: list[str]) -> dict[str, Tenant]:
        """Find-or-create a tenant per team name, preserving file order.

        Called on every login with *all* teams from the credentials file —
        not just the logging-in user's — so registration order is always
        file order, never login order.
        """
        return {name: self.find_or_create(name) for name in names_in_file_order}

    def find_or_create(self, name: str) -> Tenant:
        tenant = self.get_by_name(name)
        if tenant is None:
            tenant = Tenant(name=name)
            self.session.add(tenant)
            try:
                self.session.commit()
            except IntegrityError:
                # Two logins raced to register the same new team; the other
                # one won. Re-read its row instead of failing this login.
                self.session.rollback()
                tenant = self.get_by_name(name)
                assert tenant is not None  # the unique violation proves it exists
                return tenant
            self.session.refresh(tenant)
        return tenant

    def get_by_name(self, name: str) -> Tenant | None:
        return self.session.scalars(select(Tenant).where(Tenant.name == name)).first()

    def get_name(self, tenant_id: int) -> str:
        """The team name for a tenant id ('' when no Tenant row exists —
        e.g. a session minted before the team was registered)."""
        tenant = self.session.get(Tenant, tenant_id)
        return tenant.name if tenant else ""
