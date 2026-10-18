# ADR-065: Redesigned app information architecture: three sections plus a Dashboard digest hub

**Status:** Accepted
**Date:** 2026-06-06
**Pairs with:** ADR-061 (lead-centric redesign), ADR-066, ADR-067
**Plan:** the UI-overhaul plan (decisions D1, D5, D9, D10, D13). It shipped, and the plan doc was retired; git history has it.

## Context

Before this change the app was **map-first**. A persistent MapLibre map was the base surface, and
the Lead surfaces (Candidates, My Leads, Lead page) rendered as full-screen overlays
on top of it via hash routes (`App.svelte`). As the product grew (auth, kanban,
filters, merge/split, carriers) the single map-with-overlays shell started to feel
crowded. There was also no home for what the analyst does day to day: see what needs
attention, what has been done, and what is coming up. The user asked to "design the UI
around what we do, not random pages."

## Decision

Reorganize into **three top-level sections**, **`Dashboard · Explore · Leads`**.
Each behaves differently and is designed around the workflow rather than the data:

- **Dashboard** is the landing surface, a **hub of digests**, each expandable to a
  full **sub-page**. It has an **Attention** feed (unhandled replies plus overdue tasks,
  which doubles as the notification center via a nav badge), a **Tasks** digest →
  the Tasks workspace, a **Calendar** digest → the full calendar, a **History**
  digest → the full activity log, and a **Stats** digest → analytics. Tasks,
  Calendar, History and Stats are **sub-pages of Dashboard, not top-level pages.**
- **Explore** is discovery (tower-grained; see ADR-067).
- **Leads** is the owner-grained work surface (the former "My Leads" kanban plus Lead
  page, renamed; scope = every Lead off New).

The map stops being "the app" and becomes one lens inside Explore. It stays mounted
while in Explore (don't tear it down on nav).

## Consequences

- Routing moves from "overlays over a base map" to genuine sections with
  Dashboard sub-routes (`#/dashboard/{tasks,calendar,history,stats}`).
- Explore and Leads are largely a **re-home and reframe** of existing surfaces
  (`MapView`, `Candidates`, `MyLeads`, `LeadPage`, the shared `FilterModel`). The
  net-new engineering concentrates in the **Dashboard and Tasks** subsystem.
- The standalone **Candidates** surface folds into Explore. "Candidate" survives
  only as shorthand for a Lead still at New.

## Alternatives considered

- **Keep map-first and add a Dashboard overlay.** Rejected. It keeps the crowded
  single-surface model the redesign exists to fix.
- **Four sections (Tasks as its own top-level page).** Rejected by the user.
  Tasks is a Dashboard sub-page so the landing stays a clean digest hub and the top
  nav stays the "big 3."
