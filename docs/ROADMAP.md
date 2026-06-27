# ROADMAP — What's next

**Last updated:** 2026-06-26
**Pairs with:** [SCOPE.md](./SCOPE.md) (current scope + slice plan), [STATUS.md](./STATUS.md)
(today's state), [CHANGELOG.md](./CHANGELOG.md) (what shipped when),
[DECISIONS.md](./DECISIONS.md).

This doc is **future-only**: Phase 2, Phase 3, and the long-term business. What's been built
lives in [CHANGELOG.md](./CHANGELOG.md); where we are right now lives in
[STATUS.md](./STATUS.md). Updated at the start of every new slice/phase and after every
material strategic conversation.

---

## Present (pointer)

Phase 1 is live in production; Slices F, A, C, and most of D+E have shipped. The remaining
Phase-1 work is the rest of D+E (lease-doc upload + LLM extraction) then Slice B (vendor
inference); after B, the 4-week outcome-bar clock starts. The canonical slice plan is
[SCOPE.md §3](./SCOPE.md); today's exact state is [STATUS.md](./STATUS.md).

---

## Phase 2 — after the Phase 1 outcome bar

Asset-universe expansion to rooftop / in-building installations + operational scale. Not
started until the Phase 1 outcome bar passes — the co-founder's 4 weeks of usage will surface
the actual highest-pain Phase 2 item.

### Asset universe — rooftops ([ADR-054](./adr/0054-asset-universe-phase-1-2.md))

- Different data foundation (CoStar / LoopNet / mortgage feeds — mostly paid).
- Different anchor-state fit (dense-urban; AR / MT have little rooftop volume).
- Co-founder asks that defer with rooftops: tenant occupancy, building-owner mortgage status,
  tenant mix, electric-meter source, property-manager team.

### Operational scale

- **Mass email + response tracking** — third-party email infra (Postmark / SES) + webhook
  handling + deliverability hygiene + CAN-SPAM compliance.
- **Self-serve refresh from the product** — wire the puller into the backend so the co-founder
  can trigger a re-pull without the dev. (Successor path: the Textual-TUI puller, PRD #138.)
- **Recorded-lease automation** — scrape Memorandum-of-Lease recordings from county clerk
  sites for top counties (per-county effort; rare-rent-disclosing jurisdictions yield
  smoking-gun comps).
- **Paid Steel-in-the-Air tier** — granular per-tower comp data, augmenting the free
  county-averages bootstrap ([ADR-057](./adr/0057-budget-posture-reframed.md)).
- **Paid skip-trace for contact enrichment** — Whitepages Pro / Cole / IDI for owner phone +
  email beyond the SoS officer-disclosure baseline. Stays within ADR-057's narrowed posture.
- **Comparables maturation** — as uploaded leases accumulate (ADR-059 extraction loop), the
  private comp DB starts dominating the public-data bootstrap; "outliers in X-mile radius"
  becomes a real feature.

### Scaling watch-triggers (lines to watch, not work)

The single-machine deploy (ADR-064) has two known cliffs — neither a problem at Phase-1 scale:

- **Owners index served as in-memory JSON.** Python's JSON overhead is ~3–5× file size on a
  1 GB VM that also runs Caddy + Litestream. When `owners_index.json` approaches ~100 MB
  (≈ current states × 3), move the read path to SQLite or server-side DuckDB over the parquet
  — `OwnersIndexService` already isolates the swap.
- **SQLite, one writer.** The day a second machine, a background writer, or >~10 concurrent
  writers appears, switch to Postgres — the code is already DB-agnostic, `psycopg` ships, and
  testcontainers tests exist. Postgres RLS (engine-enforced tenant isolation) is the
  principled follow-on if tenants beyond the founding team appear.

### Stretch — mortgage / financial-distress signal

Paid CoStar / ATTOM / mortgage feeds — surfaces "owner mortgage current?" / "owner
liquidity?" (co-founder's explicit asks deferred from Phase 1).

---

## Phase 3 and beyond

Quarter-scale, contingent on Phase 2 traction:

- **Geographic expansion** — free-data state additions (IA; post-IN/UT if owner data
  unlocks); paid nationwide via **Regrid** (~150M parcels, consistent schema — budget unlock).
- **Multi-tenant sale** — the tenant-shaped schema baked Day 1 (ADR-055) anticipates selling
  the tool to other land-side consultants; each new tenant is a row in `tenant`, no rewrite.
- **Billboards as a primary triage axis** — they run as parcel enrichment in Phase 1; Phase 3
  makes them equal to towers.
- **LLC enrichment, not unmasking** — SoS business-entity records → entity type, formation
  date, registered agent. Human-identity resolution stays a permanent non-goal (ADR-041
  narrowed via ADR-057).
- **Solar third-party-ownership detection** — LBNL "Tracking the Sun" + state PUC
  interconnection reports + UCC-1 filings → flag leased / PPA-owned solar where the contract
  is renegotiable.

---

## Long-term — the business

The data + tool work here is the foundation of a business that **identifies** undervalued
ground-lease / buyout-target opportunities at scale, **prioritizes** them by
economic-distress + lease-economics signal, and **equips** the landowner to renegotiate or
evaluate offers.

Permanent non-goals (also in [CLAUDE.md §1](../CLAUDE.md)): outreach automation beyond Phase
2's mass-email, contact-data resolution beyond paid skip-trace, LLC unmasking in the sensitive
sense (ADR-041 narrowed), and lease-buyout transaction infrastructure (a different stack
entirely).

---

## How this roadmap evolves

**Phase 2** sharpens after the Phase 1 outcome bar — usage surfaces the highest-pain item.
**Phase 3 + long-term** are intentionally soft: directionally right, expected to shift. Update
at the start of every new slice/phase and after every material strategic conversation.
