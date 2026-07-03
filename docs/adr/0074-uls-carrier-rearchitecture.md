# ADR-074: Rearchitect ULS→carrier — all modern spectrum, honest authorization semantics

**Status:** Accepted — **implemented** ([#220](https://github.com/danielgentile22/infra-lease-analytics/issues/220), audit **MACRO-1**; absorbs **M-e**). The unmapped-name before/after number is the one deliverable that lands at the batched composite regen (it needs real data — `scripts/audits/carrier_brand_coverage.py`).
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

## As implemented (#220)

- **Root cause was a loader layout mismatch, not the licensing model.** The `fcc_uls_market` normalizer already produced all four bands; it writes each to a nested `fcc_uls_market/<band>/location.parquet`, but the default `Normalizer.load_state_data` only probes the flat `fcc_uls_market/location.parquet` — so compose loaded **zero** market rows. Fixed with a `FccUlsMarketNormalizer.load_state_data` override that gathers the per-band dirs (base's read/filter/concat factored into `_read_state_paths`, shared by both). The ULS↔ASR join was already band-agnostic, so no join change was needed — market locations (no `asr_number`) now attach via the proximity fallback (`likely`/`possible`, never `verified`).
- **M-e resolved = DROP.** Not exploited: the licensee name + FRN the `entity` layer carried the `license` layer already merges from EN `entity_type 'L'`, so it added nothing. Removed from both ULS normalizers (and from the composite it silently bloated); the coverage audit repointed to `license.parquet`.
- **Name mapping.** The existing curated `carrier_brands` table already maps the majors' market entities (New Cingular→AT&T, Cellco→Verizon, T-Mobile License→T-Mobile, Northstar/SNR→Dish); the fix simply *activates* it on rows that never loaded. No speculative regional patterns were added (unverifiable without data, and the large tail — defunct ALLTEL, sold-off SMSA/RSA partnerships — is honestly-unmapped by design). The before/after unmapped-rate number is measured at regen.
- **Badge semantics.** `CarrierList` gained a one-line "Licensed in this area — not a confirmed tenant" disclaimer (shared by both render surfaces; skipped in the dense compact holdings), and the empty-state copy shifted from "No carriers identified" to "No carrier licensed here."

## Alternatives considered

- **Keep Part-22-only** — rejected; silently drops the two carriers the co-founder most wants to see.
- **Claim tenancy from a license** — rejected; false (a license ≠ a tenant), and would mislead a live negotiation.
