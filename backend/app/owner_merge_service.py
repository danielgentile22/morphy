"""Manual owner-cluster merge/split overrides (Slice 7 / #53, ADR-056).

The conservative cross-state resolver (``CrossStateOwnerResolver``) is biased
toward *not* merging — a false merge means a wrong-person call. This service
is the manual net for when it gets identity wrong: it lets a tenant **merge**
two owner-clusters into one, or **split** a previously-merged one apart.

It is a deep, tenant-scoped module over one table, ``owner_cluster_override``.
The whole contract is the resolution rule

    display_cluster_id = coalesce(override_target, raw_cluster_id)

expressed by :meth:`resolve`, which follows the override chain (A→B→C) to a
fixed point. Raw cluster ids in the parquet/owners index are never mutated, so
overrides survive an owners-index recompute. Every query filters by
``tenant_id`` (ADR-055) — one tenant's merge is invisible to another's.

Lead *state* (status/notes/contact/attempts) is never moved here: merge/split
touch only this table. The read layer (``OwnersIndexService``) reconciles
member lead-state at serve time under the surviving target — see its docstring.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.orm import Session

from .models import OwnerClusterOverride


class MergeError(ValueError):
    """Raised when a merge is illegal (self-merge / already merged / cycle)."""


class OwnerMergeService:
    def __init__(self, session: Session, tenant_id: int) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self._map: dict[str, str] | None = None  # cached per request; see _invalidate

    # ── reads ────────────────────────────────────────────────────────────────
    def override_map(self) -> dict[str, str]:
        """``source_cluster_id → target_cluster_id`` for this tenant.

        Cached on the instance (one request) so ``resolve`` / ``members_of``
        don't re-query; ``merge`` / ``split`` invalidate it.
        """
        if self._map is None:
            rows = self.session.scalars(
                select(OwnerClusterOverride).where(OwnerClusterOverride.tenant_id == self.tenant_id)
            )
            self._map = {r.source_cluster_id: r.target_cluster_id for r in rows}
        return self._map

    def resolve(self, cluster_id: str) -> str:
        """The effective ``display_cluster_id`` for a raw cluster id.

        Follows the override chain to a fixed point (``coalesce`` over the
        whole chain). The visited-set guard makes a malformed cycle terminate
        rather than spin — merges can't create one (see :meth:`merge`), but a
        read must never hang on bad data.
        """
        omap = self.override_map()
        seen: set[str] = set()
        cur = cluster_id
        while cur in omap and cur not in seen:
            seen.add(cur)
            cur = omap[cur]
        return cur

    def members_of(self, root: str) -> set[str]:
        """Every raw cluster id that resolves to ``root`` (incl. ``root``).

        The merged owner served under ``root`` is the union of these — used to
        concatenate their lead-state activity streams and to list the merged-in
        clusters a split can detach.
        """
        omap = self.override_map()
        members = {root}
        for source in omap:
            if self.resolve(source) == root:
                members.add(source)
        return members

    # ── writes ───────────────────────────────────────────────────────────────
    def merge(self, *, source: str, target: str) -> None:
        """Merge ``source`` into ``target`` — afterward ``source`` resolves to
        ``target``'s effective id.

        Both are resolved to their current roots first, so a merge always joins
        whole groups at the group level (picking an already-merged member folds
        in its whole group). Raises :class:`MergeError` if the two already share
        a root (self-merge / already merged) — that equality also makes a cycle
        impossible, since the new edge points a root at a *different* root.
        """
        src_root = self.resolve(source)
        tgt_root = self.resolve(target)
        if src_root == tgt_root:
            raise MergeError(f"{source!r} already resolves to {tgt_root!r}; nothing to merge")
        existing = self.session.get(OwnerClusterOverride, (self.tenant_id, src_root))
        if existing is not None:  # src_root was itself a source — re-point it
            existing.target_cluster_id = tgt_root
        else:
            self.session.add(
                OwnerClusterOverride(
                    tenant_id=self.tenant_id,
                    source_cluster_id=src_root,
                    target_cluster_id=tgt_root,
                )
            )
        self.session.commit()
        self._invalidate()

    def split(self, *, source: str) -> bool:
        """Detach ``source`` — delete its override row so it returns to its raw
        cluster as an independent Lead. Returns True if a row was removed."""
        result = self.session.execute(
            delete(OwnerClusterOverride).where(
                OwnerClusterOverride.tenant_id == self.tenant_id,
                OwnerClusterOverride.source_cluster_id == source,
            )
        )
        self.session.commit()
        self._invalidate()
        # A DELETE returns a CursorResult at runtime; SQLAlchemy types execute()
        # as the base Result, which has no .rowcount.
        return bool(cast(CursorResult, result).rowcount)

    def _invalidate(self) -> None:
        self._map = None
