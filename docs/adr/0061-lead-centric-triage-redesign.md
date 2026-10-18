# ADR-061: Lead-centric triage UI redesign: cross-state leads, structures-first map, write layer pulled forward

**Status:** Accepted. **Shipped** (merged 2026-05-30). The UI layout question the original status flagged is resolved: a slim **top filter bar with a "More" popover**, chosen over the collapsible left drawer. The throwaway prototype was folded into `app/` and deleted.
**Date:** 2026-05-30
**Realizes / extends:** [ADR-056](0056-lead-equals-owner-cluster.md) (Lead = owner cluster). **Pairs with:** [ADR-055](0055-hosted-private-backend.md) (backend), [ADR-053](0053-product-phase-shift.md) (phase shift), [ADR-058](0058-tunable-transparent-scoring.md) (scoring), [ADR-030](0030-map-app-v2-stack.md) (map stack). **Follow-up to:** [ADR-024](0024-owner-clustering-sha1.md) (cross-state clustering).

## Context

The map app (`app/`, ADR-030) is **parcel-centric**. The heavy base layer is 2.1M+ parcels (PMTiles), DuckDB-WASM filters run over a parcel parquet, `TopList` ranks the top 1000 *parcels*, every filter is a parcel attribute, and the app is **read-only** (no write path of any kind). Towers exist but are second-class: a clickable point layer and a detail panel. That suited the demo cut but not the product phase (ADR-053).

Triage targets **landowners**, not parcels. ADR-056 already locked *Lead = owner cluster* as the triage unit, with lead status, contact attempts and notes on the cluster, and a backend to hold them (ADR-055: Postgres, S3, FastAPI, magic-link auth, `tenant_id` from day 1). ADR-056 sketched a list → detail layout but did not specify the app shell, the map pivot, the discovery-versus-worklist split, the status model, or how to reorganize the cluttered filter sidebar. A 2026-05-30 design session resolved those and surfaced three decisions that go *beyond* what ADR-055 and ADR-056 settled.

## Decision

The redesign turns ADR-056's lead-centric model into a concrete UI, plus three new calls.

**1. Cross-state lead identity (extends ADR-056; follow-up to ADR-024).**
A Lead is **national**: one owner cluster spanning all anchor states (a single "WEYERHAEUSER CO" record across AR, MT, FL and WV), not one lead per state. This needs a cross-state owner-resolution step the pipeline did not have (it clustered within a state). ADR-024's `SHA1(normalized name + address)` is stable across recomposes but folds the *address* into the key, which would **split** a national owner across their regional mailing addresses. The cross-state merge key must therefore be **name-anchored** (address dropped or canonicalized for the merge). It rides on ADR-056's conservative-normalization layers, the manual merge/split UI, and the `display_cluster_id = coalesce(override_target, raw_cluster_id)` override path.

**2. The write layer (Slice D+E) moves ahead of Slices A and C.**
The plan order was F → A (carriers) → C (enrichment and scoring UI) → D+E (backend and lead state) → B. The ADR-055/056 backend and the redesigned triage UI get built **now**, before A and C. The backend stack itself is unchanged. This is a *sequencing* decision, not a new architecture. As a result, the redesigned UI first shows the existing data (no carrier identification, no tunable scoring), and A and C enrich it later.

**3. Structures-first, lead-centric UI architecture.**
- **The map pivots from parcels to structures.** Tower points become the primary, clickable layer (clustered at low zoom). The PMTiles parcel layer renders on demand (when a lead is focused or the user zooms in). Towers are light (about 15.8K per state, 50-60K across four anchors), so a **cross-state overview** becomes feasible. Solar renders as a secondary clickable marker, and billboards once their raw data lands. Any structure is an entry point, and all of them roll up to the owner Lead.
- **A routed app shell that keeps MapLibre alive.** Three views: `/map`, the **Candidates** discovery list, and **My Leads** (`/leads`), plus a shareable Lead detail page (`/lead/:key`). The MapLibre instance persists across route changes, so switching is instant and the map can highlight the active lead.
- **Two list views, one population.** Every owner has a **Lead status** (default `New`). *Candidates* are owners at `New`, ranked by the cluster-rollup score (ADR-056/058). This is the discovery list, where the millions live. *My Leads* is a kanban of owners advanced past `New`. There is **no separate save or tracked flag**: "start tracking" means setting the status to `Researching`.
- **Lead status ladder** (one status per lead; it branches after Contacted): `New → Researching → Contacted →`, then either `Interested → In Business` or `Uninterested` (terminal). The kanban has one lane per status (New excluded; Uninterested is a closed lane).
- **Tracking fields on the Lead** (per ADR-056's `lead(tenant_id, owner_cluster_id, …)`): a structured **contact-attempts log** (date, channel, outcome), a free-text **notes** field, and **auto-logged status transitions**. Contact info is the mailing address, read-only from parcel data, plus a manually entered contact name, phone, email and channel. (Free Secretary of State officer enrichment for LLC owners, per ADR-057's narrowing of ADR-041, is not part of this redesign.)
- **Filters redefined and relocated.** Drop parcel-noise filters (acreage; raw `has_tower`, now always true). Keep or upgrade the lead-centric ones: multi-state, interestingness score, distress tier plus Opportunity Zone (OZ), Qualified Census Tract (QCT) and persistent poverty, owner kind, portfolio size, total assessed value, and county. Add structure-centric ones: structure type, tower height, tower active or inactive, structure count, and carrier once Slice A lands. Placement is chosen between a **slim top filter bar with a "More" popover** and a **decluttered collapsible left drawer**, with both prototyped before committing. Map and Candidates share one filter state.

**4. Validate before building for real.** A throwaway prototype (mock data, the whole flow, toggleable filter placements) comes first. The real backend and UI build follows once the shape is confirmed.

## Consequences

- **The slice order changes.** D+E (the write layer and this UI) now comes before A and C, amending the Phase 1 slice plan F → A → C → D+E → B. [STATUS.md](../STATUS.md) records the order that shipped.
- **New pipeline work:** a cross-state owner-resolution and cluster-merge step (follow-up to ADR-024). Within-state SHA1 clustering stays for the analytical layers (no schema break). The cross-state, name-anchored merge layers on top for the Lead key.
- **ADR-030's stack is unchanged.** Its *parcel-centric UX* is superseded by this lead- and structure-centric UX. PMTiles, DuckDB-WASM and the catalog GeoJSON remain the static read layers.
- **Hybrid architecture (per ADR-055):** static read layers (parcels, scoring, catalog) over HTTP range; dynamic lead, notes and contact state over the FastAPI backend. The `lead` table is keyed `(tenant_id, display_cluster_id)`.
- **PII custody grows.** Contact info is now entered and stored server-side (ADR-040, ADR-055): HTTPS and encryption at rest.
- The app gains a router and depends on a running backend for the write views (reads still work statically).

## Alternatives considered

- **Per-antenna or per-parcel Lead grain.** Rejected (matches ADR-056). It splits one phone call across several records.
- **Within-state lead identity.** Rejected. A national portfolio owner is really one outreach target, and cross-state correctness won over the simpler within-state key.
- **Prototype-grade persistence (localStorage or a tiny write endpoint) instead of the real backend.** Rejected for real use. The analyst works daily across devices, so the ADR-055 backend is the right home. (The throwaway *prototype* still mocks data. It just does not ship as the persistence layer.)
- **Keep parcels as the painted base map.** Rejected. It keeps the heavy per-state load and blocks the cross-state overview.
- **One list with a "saved" filter, or a saved-only list.** Rejected. Discovery (millions at New, ranked) and the worklist (advanced leads, kanban) are different modes. A universal status separates them without a second concept.
- **Independent progress flags instead of a single status ladder.** Rejected. A single funnel position answers "where does this lead stand?" and enables the kanban. Orthogonal flags can be added later if needed.
