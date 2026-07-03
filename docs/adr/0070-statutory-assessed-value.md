# ADR-070: Surface statutory assessed value alongside market/appraised

**Status:** Accepted — implementation pending ([#213](https://github.com/danielgentile22/infra-lease-analytics/issues/213), audit **M-k**).
**Date:** 2026-07-03
**Deepens:** the audit **E2** relabel (which made the surfaced value honestly "market / appraised").

## Context

The parcel value we surface is **market / appraised** in all four states (the honest E2 relabel). The **statutory assessed** value — the figure property tax is actually levied on — is a *different number* living in a *different field* per state. A landowner renegotiating a lease cares about both: market signals the asset's worth; assessed signals the owner's tax basis and carrying cost. Surfacing only one hides a number the co-founder wants.

## Decision

- Surface statutory assessed value as a **new field alongside** the existing market/appraised value — **not** instead of it.
- Per-state source:
  - **FL** — `AV_NSD` (assessed value, non-school-district).
  - **AR** — `AssessValu` (statutory 20%-of-appraised).
  - **WV** — **computed** as `0.60 × appraised` (the WV feed has no raw assessed column; WV assesses at 60%).
  - **MT** — no statutory assessed field identified in the current feed → assessed stays null, market only; disclosed. *(Verify against HEAD at implementation — the audit named only FL/AR/WV for M-k.)*
- Labels: **"Assessed value (statutory)"** and the existing **"Market / appraised value."** WV's carries a **"derived — 60% of appraised"** note.
- The assessed-value **filter operates on the assessed figure**, not market.

## Consequences

- Two value columns in the parcel schema + `towers.json`; the value filter's semantics change.
- The statutory *basis* differs per state (FL full, AR 20%, WV 60%), so cross-state assessed filtering compares different fractions — this is why the label says **statutory**, not a comparable market number. The market/appraised column remains the cross-state-comparable one.
- Composite regen required; before/after eyeballed.
- **Verify the column names against HEAD before coding** — the audit's file:line refs predate current `main`.

## Alternatives considered

- **Assessed instead-of market** — rejected; loses the market signal the co-founder also uses.
- **A single "value" field** — rejected; conflates two genuinely different numbers.
