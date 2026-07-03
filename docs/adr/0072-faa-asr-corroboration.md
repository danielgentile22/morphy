# ADR-072: FAA↔ASR co-location match dedups the towers layer

**Status:** Accepted — **implemented** (#219): the towers layer is deduped by a 50 m FAA↔ASR match; `faa_corroborated` rides the tower structure (owners-index v9) + panel.

## Amendment (2026-07-03) — no `is_active` derivation; M-j deferred

Implementing this corrected two premises:

- **`is_active` is left as-is (not "derived from FAA status").** The FAA DOF `verification_status` is only `O` (position-verified) / `U` (unverified) — it carries **no** active/inactive/decommissioned signal. A DOF obstacle simply *exists*, which is what the E8-era hard-coded `True` already says. On a matched pair the surviving **ASR** row keeps its own real `is_active` (from the FCC status codes); FAA-only survivors stay `True` (presence in the DOF). There is nothing truer to derive, so the E8 carve-out is **closed by documentation**, not a new derivation.
- **M-j (`location` tail) → decided *drop*, removal deferred.** The unread ULS `location_*` columns are tangential to the *geometric* FAA↔ASR match (they're licensee-side data, not obstacle coordinates), so "exploit for corroboration" doesn't apply. They're confirmed unread → the call is to drop them, as a focused dead-column cleanup separate from this dedup (fixes.json M-j stays open until that lands).
**Date:** 2026-07-03
**Prerequisite (landed):** [#215](https://github.com/danielgentile22/infra-lease-analytics/issues/215) — the identity split (`asr_number` FCC-only, FAA rows carry `obstacle_number`, union identity = `_source_row_id`).

## Context

FAA DOF rows are **78.5%** of the towers layer, unioned with FCC ASR with **no dedup or match** — double-counting the **~66%** of ASR towers that have a co-located FAA obstacle. All FAA rows are hard-coded `is_active = true` (the E8 carve-out). The audit measured that **62.6% of ASR towers have an FAA obstacle within 50 m** — the corroboration signal is computable but unbuilt.

## Decision

- **Spatial co-location match.** For each FAA obstacle, the nearest ASR tower **within 50 m** ⇒ same physical tower. The threshold is grounded in the 62.6%-within-50m measurement and ASR's ~30 m coordinate grain (INH-3).
- **Survivor = the ASR row** (it carries owner, contact, carrier). Stamp `faa_corroborated = true` and derive a real `is_active` from FAA's verification status (**closes the E8 carve-out**). The matched FAA row leaves the layer, but its `obstacle_number` + status ride onto the surviving ASR row.
- **Unmatched FAA rows survive** as their own towers: `faa_corroborated = false`, `is_active` from FAA status.
- **Tie-break** (two ASR towers within 50 m): nearest wins; exact ties broken by lower `_source_row_id` (deterministic, resume-safe).
- **M-j resolved — exploit the `location` tail:** where ULS structure-type/height is present, use it as a *second* corroboration signal on the match rather than dropping the columns. Flip `fixes.json` **M-j → done**.

## Consequences

- A **large, deliberate tower-count drop** (the double-count leaving) — before/after reported and human-blessed before deploy.
- New `faa_corroborated` quality signal on the panel (two independent federal sources agree the tower is real).
- `is_active` becomes meaningful instead of a constant.
- Composite regen; the match covered by tests. **50 m is the one tunable knob** — revisit if the match rate looks wrong at 30 m / 100 m.

## Alternatives considered

- **Exact-ID join** — impossible; the datasets share no ID (that's why it's a spatial match).
- **Keep the union, flag overlaps only** — rejected; leaves the double-count in every count and rollup.
