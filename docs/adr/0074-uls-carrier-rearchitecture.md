# ADR-074: Rearchitect ULS→carrier — all modern spectrum, honest authorization semantics

**Status:** Accepted — implementation pending ([#220](https://github.com/danielgentile22/infra-lease-analytics/issues/220), audit **MACRO-1**; absorbs **M-e**).
**Date:** 2026-07-03
**Extends:** [ADR-053](0053-product-phase-shift.md) Slice A (carrier identification).
**Prerequisite (landed):** [#216](https://github.com/danielgentile22/infra-lease-analytics/issues/216) — the license-status badge (the honest-disclosure slice that survives this rework).

## Context

The audit found a pipeline gap that **drops every PCS / AWS / 700 MHz license row**, so 100% of attached carriers are legacy **Part-22** cellular — T-Mobile and Dish attach **zero**. On top of that, **47%** of licensee names are unmapped to a canonical carrier, and — structurally — a license is a **spectrum authorization over an area, not a confirmed tenant** (INH-10).

## Decision

- **Flow all modern spectrum services through** — PCS, AWS, 700 MHz, and Cellular — not just Part-22. This is what surfaces T-Mobile / Dish at all.
- **Licensee-name → canonical-carrier mapping** via a curated alias table (the major carriers + common holding-company variants); measure and report the **unmapped-name rate before/after**.
- **Badge semantics = authorization, not tenancy.** The badge claims **"Licensed in this area"** (a carrier holds spectrum overlapping the tower), explicitly **not** "confirmed tenant." Keeps INH-10 honest while still giving the co-founder a lead signal; tenancy is confirmed downstream (lease docs, Slice D+E).
- **M-e resolved — exploit `entity`:** the ULS entity layer (composed in 3/4 states, consumed by nothing) feeds the name→carrier mapping. Flip `fixes.json` **M-e → done**. *(If entity proves too sparse to help, drop the compose instead — decide at implementation and report which.)*

## Consequences

- Carrier coverage rises (T-Mobile / Dish attach where licensed) — delta reported; unmapped rate materially down.
- Badge wording changes across the tower panel + map legend.
- Composite regen; the join covered by tests.
- The badge is a **lead signal, not proof of tenancy** — this is the honest framing, deliberately weaker than the old implicit claim.

## Alternatives considered

- **Keep Part-22-only** — rejected; silently drops the two carriers the co-founder most wants to see.
- **Claim tenancy from a license** — rejected; false (a license ≠ a tenant), and would mislead a live negotiation.
