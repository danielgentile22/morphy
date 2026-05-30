"""Tenant resolution — stubbed for Slice 1.

ADR-055: every route filters by a ``tenant_id`` derived from the session,
but the schema "always reads 1 for now". Real magic-link auth that issues
a session and resolves the tenant is Slice 2 (#48). This dependency is the
single seam to swap then — routes already depend on it.
"""

from __future__ import annotations

from .config import settings


def current_tenant_id() -> int:
    """FastAPI dependency returning the active tenant id (stubbed to 1)."""
    return settings.stub_tenant_id
