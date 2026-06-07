# ADR-067: Explore is tower-grained with per-tower scoring; the owner stays the unit of work

**Status:** Accepted
**Date:** 2026-06-06
**Extends:** ADR-061 (Lead = cross-state owner), ADR-056
**Pairs with:** ADR-065, ADR-058 (amended)
**Plan:** [docs/UI_OVERHAUL.md](../UI_OVERHAUL.md) (decisions D1, D2, D3)

## Context

ADR-061 made the map **structures-first** but the **Lead** owner-grained: a tower
click resolves to its landowner and opens the owner's Lead page, because outreach is
"one owner, one call." The co-founder framed the redesign's discovery surface
differently: "you open the map to find an interesting **antenna**, not an
interesting owner." That creates a tension — browse by tower, but act on a person —
and it surfaced a data gap: interestingness is computed parcel-grained and rolled up
to the owner, so towers carry no score of their own and same-owner towers would tie.

## Decision

**Explore is tower-grained in both lenses** (map points and a ranked long list are
both towers), and the tension with the owner-grained Lead is resolved by separating
**discovery** from **work**:

- **Each tower gets its own score and its own detail page.** The base per-tower
  score is the tower's **underlying parcel** interestingness (already computed
  parcel-grained — different towers sit on different parcels, so scores differ
  naturally), made tunable per ADR-058 (as amended).
- On every tower the **owner is a link** → the owner page (the existing **Lead**
  page), which lists **all that owner's towers, ranked and filterable**.
- **Pursuing** a tower advances that **owner's** Lead `New → Researching` (one
  owner, one Lead, all towers as holdings — ADR-061 unchanged) and records the
  triggering antenna as the Lead's **trigger** ("flagged from ASR …") so the
  discovery context isn't lost.

So Explore is the **tower** discovery lens; **Leads** is the **owner** work surface;
the tower→owner resolution the map already does is the bridge.

## Consequences

- **New per-tower score** on the towers/owners index (parcel score projected onto
  each tower; owners-index schema bump with safe defaults per CLAUDE.md §8).
- **New tower detail page** (today a tower click goes straight to the owner).
- **New Lead attribute: trigger** — the asset that sparked pursuit (a nullable
  column or a `channel='flag'` activity row; the latter avoids a schema change and
  supports multiple triggers).
- ADR-061's "structures-first map → owner Lead on click" is **extended, not
  reversed**: the map is still structures-first and the Lead is still the
  owner-cluster; we add a tower-first inspection layer in front of it.

## Alternatives considered

- **Map = towers, list = owners** (two object grains). Rejected — the co-founder
  wanted Explore tower-oriented throughout; per-tower scoring removes the list-
  redundancy reason that motivated an owner list.
- **Score towers by their owner's rolled-up score.** Rejected — same-owner towers
  tie, flooding the ranked list; per-parcel scoring differentiates them.
- **One Manage entry per tower.** Rejected — breaks one-owner-one-call (ADR-061): a
  40-tower owner would become 40 rows for a single phone call.
