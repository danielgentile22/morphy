# ADR-075: Cross-state owner identity with a name+state key plus a curated multi-state alias table

**Status:** Accepted and implemented. The migration was set to run at the batched deploy under the user's supervision (see *As implemented*).
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Refines:** [ADR-024](0024-owner-clustering-sha1.md) (clustering normalization) and [ADR-056](0056-lead-equals-owner-cluster.md) (Lead = owner cluster, merge/split UI).

## Context

The audit found the cross-state Lead cluster key is **name-only**, so it fails in **both directions**:

- **False merges.** "City of Jacksonville" in AR and FL collapse into one Lead.
- **Fragmentation.** Tower company and utility name variants split one real owner into many Leads.

The two failures pull opposite ways: false merges want a *tighter* key, fragmentation a *looser* one. Repo invariants: clustering must **err toward not merging**; `display_cluster_id = coalesce(override_target, raw_cluster_id)` is resolved in **one place**, never baked into the parquet; the owners index is schema-versioned. No paid unmasking ([ADR-041](0041-no-llc-unmasking.md)/[057](0057-budget-posture-reframed.md)).

## Decision

- **Default cluster key = normalized name + state.** It splits same-name distinct owners across states immediately, and respects the err-toward-not-merging invariant.
- **A curated multi-state alias table** deliberately **re-merges** known cross-state entities (Crown Castle, SBA, American Tower, Vertical Bridge, major utilities) across the state boundary. It is the targeted exception to the state-scoped key, and it feeds `raw_cluster_id` computation.
- **Invariant preserved:** `display_cluster_id = coalesce(override_target, raw_cluster_id)`, in one place, never in the parquet. Manual overrides still win.
- **Owners-index schema version bumped** per contract; backend model declaration mirrored. **Existing tenant overrides migrated** via an old→new `raw_cluster_id` map (re-clustering changes ids; the map preserves every override).

## Consequences

- Known false merges (Jacksonville AR+FL) split, and known fragmentation (tower companies) improves. Both are demonstrated before/after.
- Schema-version bump, backend mirror, and a migration that must preserve every existing override.
- Composite and owners index regen; clustering covered by tests.

## As implemented

- **Key = name + state, alias-aware.** `cluster.cross_state_owner_key(name_norm, state_fips)` hashes `name|state`. A curated `_MULTISTATE_ALIASES` table (Crown Castle, American Tower, SBA with a tower-company qualifier, Vertical Bridge) keys on the canonical alias with no state. Matching is **token-subset** (the normalizer token-sorts, so ordered substrings would miss) and singular-stemmed (TOWER/TOWERS). The owners-index resolver keys on name+state; schema bumped **v9→v10**.
- **Migration scope widened beyond the ADR's literal "overrides."** `Lead` (status/notes/contact) and `ContactAttempt` are *also* keyed by `display_cluster_id`, so the recipe change would orphan the team's whole triage history, not just merges. The build emits `owner_key_migration.json` (old→new map, at parcel-row grain so every name variant is captured). `backend/app/remap_owner_clusters.py` consumes it once at deploy to repoint all three tables. Policy: one→one repoints. One→many (a same-name owner that now splits per state) **duplicates** to each sub-cluster. Many→one (aliased fragments merging) **merges**, keeping the most-advanced status and concatenated notes. Unmapped ids are left untouched. The remap is idempotent (new keys are never map keys).
- **Preservation strategy was the user's call at deploy.** The one-shot remap above is the recommended default and what shipped. The deploy checkpoint was to re-confirm it against a read-time alias fallback or overrides only. Nothing runs until then, since the batched deploy already needs the user.
- **Backend mirror:** no new owner *field*, so no Pydantic change. The version bump and the remap CLI are the backend-side declaration.

## Alternatives considered

- **Name-only with tighter normalization.** Rejected. It can't split same-name owners in different states.
- **Name + full-address key.** Rejected. It over-splits one owner across their many parcels (addresses vary per parcel).
- **Paid entity resolution.** A non-goal (ADR-041/057).
