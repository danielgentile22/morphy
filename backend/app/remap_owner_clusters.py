"""One-time remap of tenant lead state + merge overrides when the owner
cluster-key recipe changes (ADR-075 / #221).

The cross-state key went from name-only to **name + state** (alias-aware for the
curated towercos), so every owner's ``display_cluster_id`` changed at the
composite regen. ``Lead`` (status/notes/contact), ``ContactAttempt`` and
``OwnerClusterOverride`` are all keyed by that id — so without this they orphan
and the team's triage history silently resets. The owners-index build emits
``owner_key_migration.json`` (``{old_key: [{"new":.., "state":..}, ...]}``);
this reads it and rewrites those rows in place, once, at deploy.

Policy (conservative — never lose data):
  * **one → one** (single-state owner): repoint.
  * **one → many** (a same-name owner that now SPLITS per state): duplicate the
    row to each new sub-cluster — the co-founder resolves the wrong half.
  * **many → one** (aliased towerco fragments that now MERGE): for a Lead PK
    collision, keep the most-advanced status + concatenate notes; attempts just
    repoint (their id is the PK, no collision).
  * **unmapped** (an id not in the map — a genuine orphan, or already a new-style
    key): left untouched. New keys are never map *keys*, so a second run is a
    **no-op** — the remap is idempotent + safe to re-run.

Run once at deploy, after the fresh index + sidecar are in place:

    cd backend && python -m app.remap_owner_clusters            # map next to the index
    cd backend && python -m app.remap_owner_clusters --map PATH # explicit sidecar
    cd backend && python -m app.remap_owner_clusters --dry-run  # report, change nothing

The pure ``plan_*`` functions below carry the policy (and are unit-tested); the
DB layer is a thin adapter over them.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .lead_status import STATUSES
from .models import ContactAttempt, Lead, OwnerClusterOverride

# Merge precedence for a Lead PK collision (many→one): more work done wins.
# ``uninterested`` (a parked/lost *decision*) beats bare ``new`` but loses to any
# active progress; ``in_business`` (won) always wins.
_MERGE_RANK: dict[str, int] = {
    "new": 0,
    "uninterested": 1,
    "researching": 2,
    "contacted": 3,
    "interested": 4,
    "in_business": 5,
}
# A new status must get an explicit merge precedence (don't silently rank 0).
assert set(_MERGE_RANK) == set(STATUSES), "_MERGE_RANK must cover every lead status"

Expander = Callable[[str], list[tuple[str, str]]]


def build_expander(mapping: dict[str, list[dict]]) -> Expander:
    """``old_key → [(new_key, state), ...]``. An id absent from the map expands
    to itself (state "") — so an unmapped/orphan/already-new id is a no-op."""
    table: dict[str, list[tuple[str, str]]] = {
        old: [(e["new"], str(e.get("state", ""))) for e in news] for old, news in mapping.items()
    }
    return lambda old: table.get(old, [(old, "")])


def _is_identity(old: str, targets: list[tuple[str, str]]) -> bool:
    """True when the id maps only to itself (unmapped) — nothing to do."""
    return len(targets) == 1 and targets[0][0] == old


# ── pure planners (no DB — the tested policy surface) ────────────────────────


def plan_attempt_targets(cid: str, expand: Expander) -> list[str]:
    """The new cluster id(s) a ContactAttempt on ``cid`` should live under.
    Empty ⇒ unmapped (leave the row as-is)."""
    targets = expand(cid)
    if _is_identity(cid, targets):
        return []
    return [new for new, _ in targets]


def plan_leads(leads: list[dict], expand: Expander) -> tuple[list[dict], int]:
    """Desired ``lead`` rows after the remap, for the rows whose id is remapped.

    ``leads`` are plain dicts (the remapped subset). Splits duplicate a lead to
    each new sub-cluster; collisions on ``(tenant_id, new_cid)`` merge (most-
    advanced status + concatenated notes). Returns ``(rows, n_merged)``."""
    buckets: dict[tuple[int, str], list[dict]] = {}
    for lead in leads:
        for new_cid, _state in expand(lead["display_cluster_id"]):
            buckets.setdefault((lead["tenant_id"], new_cid), []).append(lead)
    out: list[dict] = []
    merged = 0
    for (tenant, cid), members in buckets.items():
        if len(members) == 1:
            out.append({**members[0], "tenant_id": tenant, "display_cluster_id": cid})
        else:
            out.append(_merge_leads(members, tenant, cid))
            merged += 1
    return out, merged


def _merge_leads(members: list[dict], tenant: int, cid: str) -> dict:
    """Combine several old Leads colliding on one new id: keep the most-advanced
    status (its contact block), concatenate distinct notes."""
    winner = max(members, key=lambda m: _MERGE_RANK.get(m.get("status", "new"), 0))
    notes = [m["notes"] for m in members if m.get("notes", "").strip()]
    seen: list[str] = []
    for n in notes:
        if n not in seen:
            seen.append(n)
    return {
        **winner,
        "tenant_id": tenant,
        "display_cluster_id": cid,
        "notes": "\n---\n".join(seen),
    }


def plan_overrides(overrides: list[dict], expand: Expander) -> list[dict]:
    """Desired ``owner_cluster_override`` rows after the remap. A merge edge
    (source→target) is repointed through the map, pairing a split source with
    the same-state target where the split provides one (else the first target).
    Self-edges (source==target after remap) are dropped."""
    out: list[dict] = []
    seen: set[tuple[int, str]] = set()
    for ov in overrides:
        tgt_exp = expand(ov["target_cluster_id"])
        tgt_by_state = {st: new for new, st in tgt_exp}
        default_tgt = tgt_exp[0][0]
        for src_new, src_state in expand(ov["source_cluster_id"]):
            tgt_new = tgt_by_state.get(src_state, default_tgt)
            if src_new == tgt_new:
                continue
            key = (ov["tenant_id"], src_new)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "tenant_id": ov["tenant_id"],
                    "source_cluster_id": src_new,
                    "target_cluster_id": tgt_new,
                }
            )
    return out


# ── DB apply (thin adapter over the planners) ────────────────────────────────

_LEAD_COLS = (
    "tenant_id",
    "display_cluster_id",
    "status",
    "notes",
    "contact_name",
    "contact_phone",
    "contact_email",
    "best_channel",
)
_OV_COLS = ("tenant_id", "source_cluster_id", "target_cluster_id")


def remap(session: Session, mapping: dict[str, list[dict]], *, dry_run: bool = False) -> dict:
    """Apply the old→new key map to every lead-state table. Returns a stats dict.
    Idempotent (new keys are never map keys). Commits unless ``dry_run``."""
    expand = build_expander(mapping)
    keys = set(mapping)
    stats = {
        "attempts_repointed": 0,
        "attempts_duplicated": 0,
        "leads_remapped": 0,
        "leads_merged": 0,
        "overrides_remapped": 0,
    }

    # ── ContactAttempt: repoint (+ duplicate on a split); id PK ⇒ no collision.
    for a in session.scalars(select(ContactAttempt)).all():
        if a.display_cluster_id not in keys:
            continue
        targets = plan_attempt_targets(a.display_cluster_id, expand)
        if not targets:
            continue
        stats["attempts_repointed"] += 1
        if not dry_run:
            a.display_cluster_id = targets[0]
            for extra in targets[1:]:
                session.add(_clone_attempt(a, extra))
        stats["attempts_duplicated"] += len(targets) - 1

    # ── Lead: plan the remapped subset, then delete-old + upsert-planned.
    all_leads = session.scalars(select(Lead)).all()
    remapped = [ll for ll in all_leads if ll.display_cluster_id in keys]
    if remapped:
        planned, n_merged = plan_leads([_row_dict(ll, _LEAD_COLS) for ll in remapped], expand)
        stats["leads_remapped"] = len(remapped)
        stats["leads_merged"] = n_merged
        if not dry_run:
            remapped_ids = {id(ll) for ll in remapped}
            # survivors = leads NOT being remapped (a planned new-cid row that
            # lands on one merges into it rather than colliding on the PK).
            survivors = {
                (ll.tenant_id, ll.display_cluster_id): ll
                for ll in all_leads
                if id(ll) not in remapped_ids
            }
            for ll in remapped:
                session.delete(ll)
            session.flush()
            for row in planned:
                _upsert_lead(session, survivors, row)

    # ── OwnerClusterOverride: remap edges, drop self-edges.
    all_ov = session.scalars(select(OwnerClusterOverride)).all()
    remapped_ov = [o for o in all_ov if o.source_cluster_id in keys or o.target_cluster_id in keys]
    if remapped_ov:
        planned_ov = plan_overrides([_row_dict(o, _OV_COLS) for o in remapped_ov], expand)
        stats["overrides_remapped"] = len(planned_ov)
        if not dry_run:
            for o in remapped_ov:
                session.delete(o)
            session.flush()
            for row in planned_ov:
                session.add(OwnerClusterOverride(**row))

    if not dry_run:
        session.commit()
    return stats


def _row_dict(obj, cols: tuple[str, ...]) -> dict:
    return {c: getattr(obj, c) for c in cols}


def _clone_attempt(a: ContactAttempt, new_cid: str) -> ContactAttempt:
    return ContactAttempt(
        tenant_id=a.tenant_id,
        display_cluster_id=new_cid,
        occurred_on=a.occurred_on,
        channel=a.channel,
        outcome=a.outcome,
        note=a.note,
        direction=a.direction,
        logged_by_user_id=a.logged_by_user_id,
    )


def _upsert_lead(session: Session, survivors: dict, row: dict) -> None:
    """Insert the planned Lead, or merge into a surviving target row (a new-cid
    Lead that already existed keeps the more-advanced status)."""
    pk = (row["tenant_id"], row["display_cluster_id"])
    prior = survivors.get(pk)
    if prior is not None:
        if _MERGE_RANK.get(row["status"], 0) > _MERGE_RANK.get(prior.status, 0):
            for c in _LEAD_COLS[2:]:
                setattr(prior, c, row[c])
        return
    new_lead = Lead(**row)
    session.add(new_lead)
    survivors[pk] = new_lead


def load_mapping(path: Path) -> dict[str, list[dict]]:
    """Read the ``owner_key_migration.json`` sidecar → the old→new map."""
    data = json.loads(path.read_text())
    return data.get("map", data)  # tolerate a bare map or the wrapped sidecar


def _default_map_path() -> Path:
    from .config import settings

    return settings.owners_index_path.parent / "owner_key_migration.json"


def _main(argv: list[str]) -> int:  # pragma: no cover - thin argparse shell
    parser = argparse.ArgumentParser(
        prog="python -m app.remap_owner_clusters",
        description="One-time remap of lead state + overrides after the ADR-075 key change.",
    )
    parser.add_argument("--map", type=Path, default=None, help="path to owner_key_migration.json")
    parser.add_argument("--dry-run", action="store_true", help="report, change nothing")
    args = parser.parse_args(argv[1:])

    from .db import SessionLocal, init_db

    map_path = args.map or _default_map_path()
    if not map_path.exists():
        print(f"no migration map at {map_path} — nothing to do", file=sys.stderr)
        return 0
    mapping = load_mapping(map_path)
    if not mapping:
        print("migration map is empty — nothing to do")
        return 0

    init_db()
    with SessionLocal() as session:
        stats = remap(session, mapping, dry_run=args.dry_run)
    prefix = "[dry-run] " if args.dry_run else ""
    print(f"{prefix}remap from {map_path} ({len(mapping)} old keys):")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(_main(sys.argv))
