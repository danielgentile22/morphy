# ADR-070: Surface statutory assessed value alongside market/appraised

**Status:** Accepted and implemented, as narrowed by the amendment below.
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Deepens:** the audit's earlier relabel, which made the surfaced value honestly "market / appraised".

## Context

The parcel value we surface is **market / appraised** in all four states (after that relabel). The **statutory assessed** value, the figure property tax is actually levied on, is a *different number* living in a *different field* per state. A landowner renegotiating a lease cares about both. Market value signals the asset's worth; assessed value signals the owner's tax basis and carrying cost. Surfacing only one hides a number the user wants.

## Decision

- Surface statutory assessed value as a **new field alongside** the existing market/appraised value, **not** instead of it.
- Per-state source:
  - **FL**: `AV_NSD` (assessed value, non-school-district).
  - **AR**: `AssessValu` (statutory 20% of appraised).
  - **WV**: **computed** as `0.60 × appraised` (the WV feed has no raw assessed column; WV assesses at 60%).
  - **MT**: no statutory assessed field in the feed, so statutory stays null (shown as a blank); market only.
- Labels: **"Assessed value (statutory)"** and the existing **"Market / appraised value."**
- The statutory figure is surfaced **per parcel** (parcel panel and tower panel), where it is meaningful.
- The **owner-level filter and score stay on market** (see the amendment below).

## Amendment (2026-07-03): owner-level axis stays on market (option 1)

Decision (c) originally said the assessed-value *filter* would move to statutory. Implementing it surfaced two facts about that filter, which is an **owner-level cross-state rollup** (sum of the owner's parcels), not a per-parcel figure:

1. **MT has no statutory value at all**, so every MT owner would roll up to **$0**, wrecking a "low value = interesting" filter and score.
2. **Statutory basis differs by state** (AR 20%, WV 60%, FL 100%), so summing across an owner's states mixes fractions. The result is not a comparable number.

Market value (`assessed_value`) is populated in all four states and *is* comparable across states. So the **owner-level filter and the ADR-073 score axis stay on market**. The previously mislabelled "assessed" filter, pill and summary are **relabelled "market"** to be honest. Statutory is surfaced per parcel only. Options 2 and 3 (a separate statutory owner rollup, and a market/statutory toggle) were left as a purely additive extension that was never built.

## Consequences

- Two value columns in the parcel schema and `towers.json`; the value filter's semantics change.
- The statutory *basis* differs per state (FL full, AR 20%, WV 60%), so cross-state assessed filtering would compare different fractions. That is why the label says **statutory**, not a comparable market number. The market/appraised column remains the one comparable across states.
- Composite regen required; before/after eyeballed.
- The audit's file:line references predated the implementation, so the column names were verified against the current code before coding.

## Alternatives considered

- **Assessed instead of market.** Rejected. It loses the market signal the user also relies on.
- **A single "value" field.** Rejected. It conflates two genuinely different numbers.
