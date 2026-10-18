# ADR-074: Rearchitect ULS→carrier with all modern spectrum and honest authorization semantics

**Status:** Accepted and implemented. It also settled the fate of the unused ULS `entity` layer. The before/after unmapped-name number was due at the batched composite regen, since it needs real data (`scripts/audits/carrier_brand_coverage.py`).
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Extends:** [ADR-053](0053-product-phase-shift.md) Slice A (carrier identification).
**Prerequisite (landed):** the license-status badge (the honest-disclosure slice that survives this rework).

## Context

The audit found a pipeline gap in the FCC Universal Licensing System (ULS) data that **drops every PCS / AWS / 700 MHz license row**. So 100% of attached carriers are legacy **Part-22** cellular, and T-Mobile and Dish attach **zero**. On top of that, **47%** of licensee names are unmapped to a canonical carrier. And structurally, a license is a **spectrum authorization over an area, not a confirmed tenant**.

## Decision

- **Flow all modern spectrum services through**: PCS, AWS, 700 MHz, and Cellular, not just Part-22. This is what surfaces T-Mobile and Dish at all.
- **Licensee-name → canonical-carrier mapping** via a curated alias table (the major carriers plus common holding-company variants). Measure and report the **unmapped-name rate before/after**.
- **Badge semantics = authorization, not tenancy.** The badge claims **"Licensed in this area"** (a carrier holds spectrum overlapping the tower), explicitly **not** "confirmed tenant." That keeps the license-is-not-a-tenant point honest while still giving the user a lead signal. Tenancy is confirmed downstream (lease docs, Slice D+E).
- **Use the `entity` layer.** The ULS entity layer (composed in 3 of 4 states, consumed by nothing) feeds the name→carrier mapping. *(If entity proves too sparse to help, drop the compose instead. Decide at implementation and report which.)*

## Consequences

- Carrier coverage rises (T-Mobile and Dish attach where licensed), with the delta reported; the unmapped rate drops.
- Badge wording changes across the tower panel and map legend.
- Composite regen; the join covered by tests.
- The badge is a **lead signal, not proof of tenancy**. This is the honest framing, deliberately weaker than the old implicit claim.

## As implemented

- **The root cause was a loader layout mismatch, not the licensing model.** The `fcc_uls_market` normalizer already produced all four bands. It writes each to a nested `fcc_uls_market/<band>/location.parquet`, but the default `Normalizer.load_state_data` only probes the flat `fcc_uls_market/location.parquet`, so compose loaded **zero** market rows. The fix is a `FccUlsMarketNormalizer.load_state_data` override that gathers the per-band dirs (the base's read/filter/concat is factored into `_read_state_paths`, shared by both). The ULS↔ASR join was already band-agnostic, so no join change was needed. Market locations (no `asr_number`) now attach via the proximity fallback (`likely`/`possible`, never `verified`).
- **The `entity` layer was dropped.** It added nothing: the `license` layer already merges the licensee name and FCC Registration Number (FRN) from EN `entity_type 'L'`. It was removed from both ULS normalizers (and from the composite it silently bloated), and the coverage audit was repointed to `license.parquet`.
- **Name mapping.** The existing curated `carrier_brands` table already maps the majors' market entities (New Cingular→AT&T, Cellco→Verizon, T-Mobile License→T-Mobile, Northstar/SNR→Dish). The fix *activates* it on rows that never loaded. No speculative regional patterns were added. They are unverifiable without data, and the large tail (defunct ALLTEL, sold-off SMSA/RSA partnerships) stays unmapped by design. The before/after unmapped-rate number is measured at regen.
- **Badge semantics.** `CarrierList` gained a one-line "Licensed in this area, not a confirmed tenant" disclaimer (shared by both render surfaces; skipped in the dense compact holdings). The empty-state copy changed from "No carriers identified" to "No carrier licensed here."

## Alternatives considered

- **Keep Part-22 only.** Rejected. It silently drops the two carriers the user most wants to see.
- **Claim tenancy from a license.** Rejected. It is false (a license is not a tenant), and would mislead a live negotiation.
