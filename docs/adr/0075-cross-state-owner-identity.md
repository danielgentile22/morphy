# ADR-075: Cross-state owner identity — name+state key plus a curated multi-state alias table

**Status:** Accepted — implementation pending ([#221](https://github.com/danielgentile22/infra-lease-analytics/issues/221), audit **MACRO-6**).
**Date:** 2026-07-03
**Refines:** [ADR-024](0024-owner-clustering-sha1.md) (clustering normalization) + [ADR-056](0056-lead-equals-owner-cluster.md) (Lead = owner cluster, merge/split UI).

## Context

The audit found the cross-state Lead cluster key is **name-only**, so it fails in **both directions**:

- **False merges** — "City of Jacksonville" AR + FL collapse into one Lead.
- **Fragmentation** — towerco / utility name variants split one real owner into many Leads.

The two failures pull opposite ways: false merges want a *tighter* key, fragmentation a *looser* one. Repo invariant: clustering must **err toward not merging**; `display_cluster_id = coalesce(override_target, raw_cluster_id)` resolved in **one place**, never baked into the parquet; the owners index is schema-versioned. No paid unmasking ([ADR-041](0041-no-llc-unmasking.md)/[057](0057-budget-posture-reframed.md)).

## Decision

- **Default cluster key = normalized name + state.** Splits same-name distinct owners across states immediately, and respects the err-toward-not-merging invariant.
- **Curated multi-state alias table** deliberately **re-merges** known cross-state entities (Crown Castle / SBA / American Tower / Vertical Bridge, major utilities) across the state boundary — the targeted exception to the state-scoped key. Feeds `raw_cluster_id` computation.
- **Invariant preserved:** `display_cluster_id = coalesce(override_target, raw_cluster_id)`, one place, never in the parquet. Manual overrides still win.
- **Owners-index schema version bumped** per contract; backend model declaration mirrored. **Existing tenant overrides migrated** via an old→new `raw_cluster_id` map (re-clustering changes ids; the map preserves every override).

## Consequences

- Known false merges (Jacksonville AR+FL) split; known fragmentation (towercos) improved — both demonstrated before/after.
- Schema-version bump + backend mirror + a migration that must preserve every existing override.
- Composite + owners index regen; clustering covered by tests.

## Alternatives considered

- **Name-only with tighter normalization** — rejected; can't split same-name-different-state.
- **Name + full-address key** — rejected; over-splits one owner across their many parcels (addresses vary per parcel).
- **Paid entity resolution / skip-trace** — non-goal (ADR-041/057).
