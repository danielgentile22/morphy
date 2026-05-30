# ADR-061: Lead-centric triage UI redesign — cross-state leads, structures-first map, write-layer pulled forward

**Status:** Accepted — **Shipped** via PRD #46 (Slices #47–#53, merged 2026-05-30). The UI layout question the original status flagged is resolved: a slim **top filter bar + "More" popover** (chosen over the collapsible left drawer, #52); the throwaway prototype was folded into `app/` and deleted.
**Date:** 2026-05-30
**Realizes / extends:** [ADR-056](0056-lead-equals-owner-cluster.md) (Lead = owner-cluster). **Pairs with:** [ADR-055](0055-hosted-private-backend.md) (backend), [ADR-053](0053-product-phase-shift.md) (phase shift), [ADR-058](0058-tunable-transparent-scoring.md) (scoring), [ADR-030](0030-map-app-v2-stack.md) (map stack). **Follow-up to:** [ADR-024](0024-owner-clustering-sha1.md) (cross-state clustering).

## Context

The map app (`app/`, ADR-030) is **parcel-centric**: the heavy base layer is 2.1M+ parcels (PMTiles), DuckDB-WASM filters run over a parcel parquet, `TopList` ranks the top-1000 *parcels*, every filter is a parcel attribute, and the app is **read-only** (no write path of any kind). Towers exist but are second-class (a clickable point layer + a detail panel). This is correct for the pitch cut but wrong for the product phase (ADR-053).

The co-founder triages **landowners**, not parcels — ADR-056 already locked *Lead = owner-cluster* as the triage primitive, with lead status / contact attempts / notes on the cluster and a backend (ADR-055: Postgres + S3 + FastAPI + magic-link auth + `tenant_id` Day 1) to hold them. ADR-056 sketched a list→detail layout but did not specify the app shell, the map pivot, the discovery-vs-worklist split, the status model, or how the cluttered filter sidebar is reorganized. A 2026-05-30 design session (`/grill-with-docs`) resolved those, and surfaced three decisions that go *beyond* what ADR-055/056 already settled.

## Decision

The redesign realizes ADR-056's lead-centric model as a concrete UI, plus three new calls:

**1. Cross-state lead identity (extends ADR-056; follow-up to ADR-024).**
A Lead is **national**: one owner-cluster spanning all anchor states (a single "WEYERHAEUSER CO" record across AR + MT + FL + WV), not one lead per state. This requires a cross-state owner-resolution step the pipeline does not have today (it clusters within a state). ADR-024's `SHA1(normalized name + address)` is stable across recomposes but folds *address* into the key — which would **split** a national owner across their regional mailing addresses. The cross-state merge key must therefore be **name-anchored** (address dropped or canonicalized for the merge), riding on ADR-056's already-specified conservative-normalization layers + manual merge/split UI + `display_cluster_id = coalesce(override_target, raw_cluster_id)` override path.

**2. The write-layer (Slice D+E) is pulled forward, ahead of Slices A and C.**
The plan order was F → A (carriers) → C (enrichment/scoring UI) → D+E (backend + lead state) → B. We build the ADR-055/056 backend + the redesigned triage UI **now**, before A and C. The backend stack itself is unchanged — this is a *sequencing* decision, not a new architecture. Consequence: the redesigned UI initially shows *today's* data (no carrier identification, no tunable scoring); A and C enrich it later.

**3. Structures-first, lead-centric UI architecture.**
- **Map pivots from parcels to structures.** Tower points become the primary, clickable layer (clustered at low zoom); the PMTiles parcel layer renders on-demand (when a lead is focused or the user zooms in). Towers are light (~15.8K/state; ~50–60K across four anchors) so a **cross-state overview** is now feasible. Solar renders as a secondary clickable marker; billboards when their raw data lands. Any structure is an entry point but all roll up to the owner Lead.
- **Routed app shell, MapLibre kept alive.** Three surfaces — `/map`, the **Candidates** discovery list, and **My Leads** (`/leads`) — plus a shareable Lead detail page (`/lead/:key`). The MapLibre instance persists across route changes so switching is instant and the map can highlight the active lead.
- **Two list surfaces, one population.** Every owner has a **Lead status** (default `New`). *Candidates* = owners at `New`, ranked by the cluster-rollup score (ADR-056/058) — the discovery surface where the millions live. *My Leads* = a kanban of owners advanced past `New`. There is **no separate save/tracked flag**; "start tracking" simply means setting status to `Researching`.
- **Lead status ladder** (single status per lead; branches after Contacted): `New → Researching → Contacted →` then either `Interested → In Business` or `Uninterested` (terminal). The kanban has one lane per status (New excluded; Uninterested is a closed lane).
- **Tracking fields on the Lead** (per ADR-056's `lead(tenant_id, owner_cluster_id, …)`): a structured **contact-attempts log** (date · channel · outcome), a free-text **notes** field, and **auto-logged status transitions**. Contact info = mailing address read-only from parcel data + manually entered contact name / phone / email / channel. (For LLC owners, a future free SoS-officer enrichment per ADR-057-narrowed ADR-041 — not in this redesign.)
- **Filters redefined + relocated.** Drop parcel-noise filters (acreage; raw `has_tower`, now always true); keep/upgrade lead-centric ones (multi-state, interestingness score, distress tier + OZ/QCT/persistent-poverty, owner kind, portfolio size, total assessed value, county) and add structure-centric ones (structure type, tower height, tower active/inactive, structure count; carrier once Slice A lands). Placement is chosen between a **slim top filter bar + "More" popover** and a **decluttered collapsible left drawer** — both prototyped before committing. Map and Candidates share one filter state.

**4. Validate before building for real.** A throwaway prototype (mock data, the whole flow, toggleable filter placements) is built first; the real backend + UI build follows once the shape is confirmed.

## Consequences

- **Slice order changes.** STATUS §6, GOALS §3, and ROADMAP must record that D+E (write-layer + this UI) now precedes A and C. The Phase-1 slice plan F→A→C→D+E→B is amended.
- **New pipeline work:** a cross-state owner-resolution / cluster-merge step (follow-up to ADR-024). Within-state SHA1 clustering stays for the analytical layers (no schema break); the cross-state, name-anchored merge layers in for the Lead key.
- **ADR-030's stack is unchanged**; its *parcel-centric UX* is superseded by this lead/structure-centric UX. PMTiles + DuckDB-WASM + catalog GeoJSON remain the static read layers.
- **Hybrid architecture (per ADR-055):** static read layers (parcels, scoring, catalog) over HTTP range; dynamic lead/notes/contact state over the FastAPI backend. The `lead` table is keyed `(tenant_id, display_cluster_id)`.
- **PII custody grows** — contact info is now entered and stored server-side (ADR-040 / ADR-055): HTTPS, encrypted at rest.
- The app gains a router and a build-time dependency on a running backend for the write surfaces (reads still work statically).

## Alternatives considered

- **Per-antenna or per-parcel Lead grain.** Rejected (matches ADR-056) — fragments one phone call across multiple records.
- **Within-state lead identity.** Rejected — a national portfolio owner is genuinely one outreach target; cross-state correctness was preferred over the simpler within-state key.
- **Prototype-grade persistence (localStorage / tiny write endpoint) instead of the real backend.** Rejected for production — the co-founder is the daily user across devices; the ADR-055 backend is the right home. (The throwaway *prototype* still mocks data — it just doesn't ship as the persistence layer.)
- **Keep parcels as the painted base map.** Rejected — keeps the heavy per-state load and blocks the cross-state overview.
- **One list with a "saved" filter, or a saved-only list.** Rejected — discovery (millions at New, ranked) and the worklist (advanced leads, kanban) are different modes; a universal status cleanly separates them without a second concept.
- **Independent progress flags instead of a single status ladder.** Rejected — a single funnel position answers "where does this lead stand?" and enables the kanban; orthogonal flags can be added later if needed.
