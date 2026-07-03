# ADR-072: FAA↔ASR co-location match dedups the towers layer

**Status:** Accepted — implementation pending ([#219](https://github.com/danielgentile22/infra-lease-analytics/issues/219), audit **MACRO-2**; absorbs **M-j** and closes the **E8** `is_active` carve-out).
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
