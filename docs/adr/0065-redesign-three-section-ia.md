# ADR-065: Redesigned app IA — three sections + Dashboard digest-hub

**Status:** Accepted
**Date:** 2026-06-06
**Pairs with:** ADR-061 (lead-centric redesign), ADR-066, ADR-067
**Plan:** the UI-overhaul plan (decisions D1, D5, D9, D10, D13) — shipped; the plan doc was retired, recover from git history if needed.

## Context

The app today is **map-first**: a persistent MapLibre map is the base surface and
the Lead surfaces (Candidates, My Leads, Lead page) render as full-screen overlays
on top of it via hash routes (`App.svelte`). As the product grew (auth, kanban,
filters, merge/split, carriers) the single map-with-overlays shell started to feel
crowded, and there was no home for the things the co-founder actually does day to
day — see what needs attention, what's been done, and what's coming up. The
co-founder asked to "design the UI around what we do, not random pages."

## Decision

Reorganize into **three top-level sections** — **`Dashboard · Explore · Leads`** —
each behaving differently, designed around the workflow rather than the data:

- **Dashboard** — the landing surface, a **hub of digests**, each expandable to a
  full **sub-page**: an **Attention** feed (unhandled replies + overdue tasks,
  which doubles as the notification center via a nav badge), a **Tasks** digest →
  the Tasks workspace, a **Calendar** digest → the full calendar, a **History**
  digest → the full activity log, and a **Stats** digest → analytics. Tasks /
  Calendar / History / Stats are **sub-pages of Dashboard, not top-level pages.**
- **Explore** — discovery (tower-grained; see ADR-067).
- **Leads** — the owner-grained work surface (today's "My Leads" kanban + Lead
  page, renamed; scope = every Lead off New).

The map stops being "the app" and becomes one lens inside Explore; it stays mounted
while in Explore (don't tear it down on nav).

## Consequences

- Routing moves from "overlays over a base map" to genuine sections with
  Dashboard sub-routes (`#/dashboard/{tasks,calendar,history,stats}`).
- Explore and Leads are largely a **re-home + reframe** of existing surfaces
  (`MapView`, `Candidates`, `MyLeads`, `LeadPage`, the shared `FilterModel`); the
  net-new engineering concentrates in the **Dashboard + Tasks** subsystem.
- The standalone **Candidates** surface folds into Explore; "Candidate" survives
  only as shorthand for a Lead still at New.

## Alternatives considered

- **Keep map-first + add a Dashboard overlay.** Rejected — perpetuates the crowded
  single-surface model the redesign exists to fix.
- **Four sections (Tasks as its own top-level page).** Rejected by the co-founder:
  Tasks is a Dashboard sub-page so the landing stays a clean digest hub and the top
  nav stays the "big 3."
