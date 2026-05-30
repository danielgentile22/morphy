"""Serves the static cross-state owners index, joined with lead state.

The index (``owners_index.json``) is produced by the preprocess pipeline
(``scripts/preprocess/owners_index.py``) and is read-only + shared across
tenants. This service left-joins it with the requesting tenant's lead
state (via ``LeadStore``) so the Candidates list and Lead page see one
merged view. Owners with no persisted Lead are implicitly at ``new``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .lead_status import INITIAL_STATUS
from .lead_store import LeadStore


class OwnersIndexService:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self._owners: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        """(Re)load the index from disk. Missing file → empty index (the
        backend still boots; Candidates is simply empty until the
        precompute runs)."""
        if not self.index_path.exists():
            self._owners, self._by_id = [], {}
            return
        data = json.loads(self.index_path.read_text())
        owners = data.get("owners", [])
        # The precompute already sorts by score desc; sort defensively so
        # ranking never depends on file order.
        owners = sorted(owners, key=lambda o: o.get("score", 0.0), reverse=True)
        self._owners = owners
        self._by_id = {o["display_cluster_id"]: o for o in owners}

    @property
    def count(self) -> int:
        return len(self._owners)

    def get_owner(self, display_cluster_id: str) -> dict | None:
        return self._by_id.get(display_cluster_id)

    def list_candidates(self, store: LeadStore, limit: int | None = None) -> list[dict]:
        """Owners still at status New (Candidates), ranked by interestingness.

        An owner is a Candidate when it has no persisted Lead or its Lead
        is at New. Returns owner dicts with ``status`` attached.
        """
        status_by_id = store.status_map()
        out: list[dict] = []
        for owner in self._owners:  # already score-sorted
            status = status_by_id.get(owner["display_cluster_id"], INITIAL_STATUS)
            if status != INITIAL_STATUS:
                continue
            out.append({**owner, "status": status})
            if limit is not None and len(out) >= limit:
                break
        return out

    def lead_view(self, store: LeadStore, display_cluster_id: str) -> dict | None:
        """Owner rollup + this tenant's lead state + contact attempts.

        Returns ``None`` if the owner is unknown to the index.
        """
        owner = self.get_owner(display_cluster_id)
        if owner is None:
            return None
        lead = store.get_lead(display_cluster_id)
        attempts = store.list_attempts(display_cluster_id)
        return {
            "owner": owner,
            "status": lead.status if lead else INITIAL_STATUS,
            "notes": lead.notes if lead else "",
            "updated_at": lead.updated_at.isoformat() if lead else None,
            "attempts": [
                {
                    "id": a.id,
                    "occurred_on": a.occurred_on.isoformat(),
                    "channel": a.channel,
                    "outcome": a.outcome,
                    "note": a.note,
                }
                for a in attempts
            ],
        }
