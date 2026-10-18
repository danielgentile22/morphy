# ADR-072: FAA↔ASR co-location match dedups the towers layer

**Status:** Accepted and implemented. The towers layer is deduped by a 50 m match between Federal Aviation Administration (FAA) obstacles and FCC Antenna Structure Registration (ASR) towers. `faa_corroborated` rides the tower structure (owners-index v9) and the panel. The amendment below corrects two premises of the original decision.
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Prerequisite (landed):** the identity split (`asr_number` is FCC-only, FAA rows carry `obstacle_number`, union identity = `_source_row_id`).

## Amendment (2026-07-03): no `is_active` derivation; the unread ULS `location_*` columns are dropped later

Implementing this corrected two premises:

- **`is_active` is left as-is (not "derived from FAA status").** The FAA Digital Obstacle File (DOF) `verification_status` is only `O` (position-verified) or `U` (unverified). It carries **no** active/inactive/decommissioned signal. A DOF obstacle simply *exists*, which is what the hard-coded `True` on FAA rows already says. On a matched pair the surviving **ASR** row keeps its own real `is_active` (from the FCC status codes); FAA-only survivors stay `True` (presence in the DOF). There is nothing truer to derive, so the hard-coded value is **closed by documentation**, not a new derivation.
- **The unread ULS `location_*` columns: decided to drop, removal deferred.** The FCC Universal Licensing System (ULS) `location_*` columns are tangential to the *geometric* FAA↔ASR match. They are licensee-side data, not obstacle coordinates, so "use them for corroboration" doesn't apply. They are confirmed unread, so the call is to drop them as a focused dead-column cleanup separate from this dedup.

## Context

FAA DOF rows are **78.5%** of the towers layer, unioned with FCC ASR with **no dedup or match**. That double-counts the **~66%** of ASR towers that have a co-located FAA obstacle. All FAA rows are hard-coded `is_active = true`. The audit measured that **62.6% of ASR towers have an FAA obstacle within 50 m**, so the corroboration signal is computable but was unbuilt.

## Decision

- **Spatial co-location match.** For each FAA obstacle, the nearest ASR tower **within 50 m** is the same physical tower. The threshold is grounded in the 62.6%-within-50m measurement and ASR's ~30 m coordinate grain.
- **Survivor = the ASR row** (it carries owner, contact, carrier). Stamp `faa_corroborated = true` and derive a real `is_active` from FAA's verification status, replacing the hard-coded value. (The amendment reversed the `is_active` part.) The matched FAA row leaves the layer, but its `obstacle_number` and status ride onto the surviving ASR row.
- **Unmatched FAA rows survive** as their own towers: `faa_corroborated = false`, `is_active` from FAA status.
- **Tie-break** (two ASR towers within 50 m): nearest wins; exact ties go to the lower `_source_row_id` (deterministic, resume-safe).
- **Use the ULS `location_*` columns:** where ULS structure type or height is present, use it as a *second* corroboration signal on the match rather than dropping the columns. (The amendment reversed this too.)

## Consequences

- A **large, deliberate tower-count drop** as the double-count leaves. Before/after is reported and approved by a human before deploy.
- New `faa_corroborated` quality signal on the panel (two independent federal sources agree the tower is real).
- `is_active` was meant to become meaningful instead of a constant. The amendment found FAA data has no signal for it, so it stays as described there.
- Composite regen; the match covered by tests. **50 m is the one tunable knob.** Revisit if the match rate looks wrong at 30 m or 100 m.

## Alternatives considered

- **Exact-ID join.** Impossible. The datasets share no ID, which is why it's a spatial match.
- **Keep the union, flag overlaps only.** Rejected. It leaves the double-count in every count and rollup.
