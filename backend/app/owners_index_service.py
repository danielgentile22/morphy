"""Serves the static cross-state owners index, joined with lead state.

The index (``owners_index.json``) is produced by the preprocess pipeline
(``scripts/preprocess/owners_index.py``) and is read-only + shared across
tenants. This service left-joins it with the requesting tenant's lead
state (via ``LeadStore``) so the Candidates list and Lead page see one
merged view. Owners with no persisted Lead are implicitly at ``new``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from .lead_status import INITIAL_STATUS
from .lead_store import LeadStore
from .owner_merge_service import OwnerMergeService

# Distress-tier severity (mirrors the precompute's ordering) — the merged
# owner inherits the worst tier across the clusters folded into it.
_TIER_RANK = {"": 0, "transitional": 1, "at-risk": 2, "distressed": 3}
_RANK_TIER = {v: k for k, v in _TIER_RANK.items()}


class OwnersIndexService:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self._owners: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._order: dict[str, int] = {}
        self._alpha: float = 0.1
        self.reload()

    def reload(self) -> None:
        """(Re)load the index from disk. Missing file → empty index (the
        backend still boots; Candidates is simply empty until the
        precompute runs)."""
        if not self.index_path.exists():
            self._owners, self._by_id, self._order = [], {}, {}
            return
        # read_bytes → json.loads(bytes) skips the intermediate str decode and
        # frees the ~43 MB transient sooner than read_text (PERF-026).
        data = json.loads(self.index_path.read_bytes())
        owners = data.get("owners", [])
        # The precompute already sorts by score desc; sort defensively so
        # ranking never depends on file order.
        owners = sorted(owners, key=lambda o: o.get("score", 0.0), reverse=True)
        self._owners = owners
        self._by_id = {o["display_cluster_id"]: o for o in owners}
        # Score-sorted position of each owner — lets get_owner's fast path order a
        # merge group's members exactly as effective() would (which appends them
        # in self._owners order), keeping single-owner merges byte-identical.
        self._order = {o["display_cluster_id"]: i for i, o in enumerate(owners)}
        # The cluster-score rollup constant (ADR-056) — reused when a manual
        # merge re-rolls a combined owner's score; default matches the precompute.
        self._alpha = float(data.get("alpha", 0.1))

    @property
    def count(self) -> int:
        return len(self._owners)

    # ── override-aware effective view ────────────────────────────────────────
    def effective(self, merges: OwnerMergeService | None) -> tuple[list[dict], dict[str, dict]]:
        """The owners list + lookup *after* applying this tenant's manual
        merges — ``display_cluster_id = coalesce(override_target, raw)``.

        Every read surface (Candidates, My-Leads, counts, Lead page, the map's
        tower→landowner resolution) goes through here, so a merge/split shows
        up identically everywhere — resolution is never forked per surface. No
        overrides (the overwhelming common case) ⇒ the static index is returned
        untouched, zero overhead.
        """
        if merges is None:
            return self._owners, self._by_id
        omap = merges.override_map()
        if not omap:
            return self._owners, self._by_id
        groups: dict[str, list[dict]] = {}
        for owner in self._owners:
            groups.setdefault(merges.resolve(owner["display_cluster_id"]), []).append(owner)
        merged = [self._merge_group(root, members) for root, members in groups.items()]
        merged.sort(key=lambda o: o.get("score", 0.0), reverse=True)
        return merged, {o["display_cluster_id"]: o for o in merged}

    def _merge_group(self, root: str, members: list[dict]) -> dict:
        """Combine the raw owners folded into ``root`` into one merged owner.

        The surviving identity (name/kind) is the target root's; the rollups
        sum/union across members and the score is re-rolled per ADR-056
        (``max(parcel_scores) + alpha·ln(parcel_count)``). A single-member
        group is returned as-is (the common case under a sparse override set).
        """
        if len(members) == 1:
            return members[0]
        base = next((m for m in members if m["display_cluster_id"] == root), members[0])

        def _union(key: str) -> list[str]:
            return sorted({v for m in members for v in (m.get(key) or [])})

        parcel_count = sum(int(m.get("parcel_count", 0)) for m in members)
        max_parcel_score = max(float(m.get("max_parcel_score", 0.0)) for m in members)
        states = _union("states")
        heights = [
            m["tallest_tower_height_m"]
            for m in members
            if m.get("tallest_tower_height_m") is not None
        ]
        mailing = next(
            (m.get("mailing_address") for m in members if m.get("mailing_address")), None
        )
        # base first so the survivor's holdings lead the list.
        ordered = [base, *(m for m in members if m is not base)]
        return {
            **base,
            "display_cluster_id": root,
            "states": states,
            "n_states": len(states),
            "cross_state": len(states) >= 2,
            "counties": _union("counties"),
            "structure_types": _union("structure_types"),
            "parcel_count": parcel_count,
            "tower_count": sum(int(m.get("tower_count", 0)) for m in members),
            "solar_count": sum(int(m.get("solar_count", 0)) for m in members),
            "structure_count": sum(int(m.get("structure_count", 0)) for m in members),
            "active_tower_count": sum(int(m.get("active_tower_count", 0)) for m in members),
            "total_assessed_value": round(
                sum(float(m.get("total_assessed_value", 0.0)) for m in members), 2
            ),
            "max_parcel_score": round(max_parcel_score, 4),
            "score": round(max_parcel_score + self._alpha * math.log(parcel_count), 4),
            "distress_tier": _RANK_TIER[
                max(_TIER_RANK.get(m.get("distress_tier", ""), 0) for m in members)
            ],
            "in_oz": any(bool(m.get("in_oz")) for m in members),
            "in_qct": any(bool(m.get("in_qct")) for m in members),
            "persistent_poverty": any(bool(m.get("persistent_poverty")) for m in members),
            "tallest_tower_height_m": max(heights) if heights else None,
            "mailing_address": mailing,
            "holdings": [h for m in ordered for h in (m.get("holdings") or [])],
        }

    def get_owner(
        self, display_cluster_id: str, merges: OwnerMergeService | None = None
    ) -> dict | None:
        """The (effective) owner for a cluster id, resolving any merge first so
        a merged-away source id still finds its surviving owner.

        Single-owner fast path (PERF-009): never rebuild + re-sort the whole
        16k index just to return one owner. With no overrides — or when the
        resolved root is its own singleton group — the raw owner *is* the
        effective owner. Only a genuine merge group (>1 member) is recombined,
        and only that group, byte-identically to ``effective()``'s per-group
        merge.
        """
        if merges is None:
            return self._by_id.get(display_cluster_id)
        root = merges.resolve(display_cluster_id)
        members = merges.members_of(root)
        if len(members) == 1:
            return self._by_id.get(root)
        member_owners = [self._by_id[m] for m in members if m in self._by_id]
        if not member_owners:
            return None
        # Order members exactly as effective() would (self._owners order) so the
        # merged owner — notably its concatenated holdings — is identical.
        member_owners.sort(key=lambda o: self._order.get(o["display_cluster_id"], 0))
        return self._merge_group(root, member_owners)

    def list_candidates(
        self,
        store: LeadStore,
        limit: int | None = None,
        merges: OwnerMergeService | None = None,
    ) -> list[dict]:
        """Owners still at status New (Candidates), ranked by interestingness.

        An owner is a Candidate when it has no persisted Lead or its Lead
        is at New. Returns owner dicts with ``status`` attached.
        """
        owners, _ = self.effective(merges)
        status_by_id = store.status_map()
        out: list[dict] = []
        for owner in owners:  # already score-sorted
            status = status_by_id.get(owner["display_cluster_id"], INITIAL_STATUS)
            if status != INITIAL_STATUS:
                continue
            out.append({**owner, "status": status})
            if limit is not None and len(out) >= limit:
                break
        return out

    def list_my_leads(
        self,
        store: LeadStore,
        limit: int | None = None,
        merges: OwnerMergeService | None = None,
    ) -> list[dict]:
        """Owners advanced *off* New — the My-Leads worklist (Slice 5 / #51).

        The complement of ``list_candidates``: every index owner whose Lead
        is at a non-New status, each with its ``status`` attached so the
        kanban can bucket it into a lane. Kept in score order; the client
        groups by status.
        """
        owners, _ = self.effective(merges)
        status_by_id = store.status_map()
        flags = store.latest_flags()  # cid → triggering ASR (#109)
        out: list[dict] = []
        for owner in owners:  # already score-sorted
            cid = owner["display_cluster_id"]
            status = status_by_id.get(cid, INITIAL_STATUS)
            if status == INITIAL_STATUS:
                continue
            out.append({**owner, "status": status, "trigger_asr": flags.get(cid, "")})
            if limit is not None and len(out) >= limit:
                break
        return out

    def counts(self, store: LeadStore, merges: OwnerMergeService | None = None) -> dict[str, int]:
        """Nav counts: ``{candidates, my_leads}`` over this tenant's view.

        Every (effective) owner is either a Candidate (New) or a My-Lead (off
        New), so the two partition the index. Counts the *true* totals
        (uncapped by any list ``limit``) in one pass.
        """
        owners, by_id = self.effective(merges)
        status_map = store.status_map()
        # The two buckets partition the index, so my_leads is fully determined by
        # the (tiny) persisted-lead set: an index owner off New (PERF-005). The
        # ``cid in by_id`` guard keeps an orphan lead (a persisted cid no longer
        # an effective owner) from being counted — exact parity with iterating
        # owners, but O(persisted leads) instead of O(all owners).
        my_leads = sum(
            1 for cid, status in status_map.items() if status != INITIAL_STATUS and cid in by_id
        )
        return {"candidates": len(owners) - my_leads, "my_leads": my_leads}

    def lead_view(
        self,
        store: LeadStore,
        display_cluster_id: str,
        merges: OwnerMergeService | None = None,
    ) -> dict | None:
        """Owner rollup + holdings + this tenant's lead state + attempts.

        The static side (rollup, holdings, mailing address, tallest tower)
        comes from the precomputed owners index, with any manual merge applied
        so the merged owner is served under its surviving (target) id. The
        per-tenant side reconciles across the merged-in clusters by
        **target-wins** for scalar state (status/notes/contact come from the
        target's own lead row) while the contact-attempt streams **concatenate**
        across all members. Returns ``None`` if the owner is unknown.
        """
        owner = self.get_owner(display_cluster_id, merges)
        if owner is None:
            return None
        root = owner["display_cluster_id"]
        members = merges.members_of(root) if merges is not None else {root}
        lead = store.get_lead(root)  # the surviving target row is authoritative
        # One IN-query across the merged members, DB-ordered newest-first
        # (PERF-022) — was a query-per-member + a Python re-sort.
        attempts = store.list_attempts_for(members)
        # Trigger antenna (#109): the latest flag row's ASR (attempts are
        # newest-first, so the first flag is the latest).
        trigger_asr = next((a.outcome for a in attempts if a.channel == "flag" and a.outcome), "")
        merged_members = [
            {"display_cluster_id": m, "owner_name": self._by_id.get(m, {}).get("owner_name", "")}
            for m in sorted(members - {root})
        ]
        status = lead.status if lead else INITIAL_STATUS
        return {
            # The owner carries the lead status too, so the view validates
            # straight into LeadDetail (whose OwnerSummary declares status).
            "owner": {**owner, "trigger_asr": trigger_asr, "status": status},
            "status": status,
            "notes": lead.notes if lead else "",
            "updated_at": lead.updated_at.isoformat() if lead else None,
            "contact_name": lead.contact_name if lead else "",
            "contact_phone": lead.contact_phone if lead else "",
            "contact_email": lead.contact_email if lead else "",
            "best_channel": lead.best_channel if lead else "",
            # Read-only source detail (absent on a pre-v2 index → safe defaults).
            "mailing_address": owner.get("mailing_address"),
            "tallest_tower_height_m": owner.get("tallest_tower_height_m"),
            "holdings": owner.get("holdings", []),
            "merged_members": merged_members,
            "attempts": [
                {
                    "id": a.id,
                    "occurred_on": a.occurred_on.isoformat(),
                    "channel": a.channel,
                    "outcome": a.outcome,
                    "note": a.note,
                    "direction": a.direction,
                }
                for a in attempts
            ],
        }
