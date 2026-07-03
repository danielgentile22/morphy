# ADR-071: Solar feed dedup — EIA-860 as the base of record

**Status:** Accepted — implementation pending ([#217](https://github.com/danielgentile22/infra-lease-analytics/issues/217), audit **MACRO-3**).
**Date:** 2026-07-03
**Prerequisites (landed):** E5 + E6 (feed cleaning), [#210](https://github.com/danielgentile22/infra-lease-analytics/issues/210) (`eia_id` recovered + first-class on USPVDB), [#211](https://github.com/danielgentile22/infra-lease-analytics/issues/211) (intersects predicate).

## Context

Three solar feeds — EIA-860 (annual), EIA-860M (monthly), USPVDB (USGS) — are concatenated with **no dedup**: ~967 rows ≈ **3× ~300 distinct farms**, and USPVDB is reduced to points (polygons dropped). #210 recovered the `eia_id` cross-reference key, now first-class on USPVDB rows in the same code space as EIA-860's `facility_id` — so an exact join key exists.

**Data drift flagged this session:** USPVDB v4.0 (on disk) renamed `p_eia_id`→`eia_id` **and dropped the owner/operator field**; EIA-860 still carries operator.

## Decision

- **EIA-860 (annual) is the base of record** — the authoritative federal generator inventory, and the only feed still carrying operator/owner.
- **Dedup key:** `eia_id` ↔ EIA-860 `facility_id`. A physical farm present in multiple feeds collapses to one row.
- **Precedence on conflict: 860 → 860M → USPVDB.**
  - **860M** contributes only plants too new to appear in the annual 860 yet.
  - **USPVDB** contributes **polygon geometry** (joined by `eia_id`) — a matched farm upgrades from point to footprint; unmatched USPVDB rows survive as point-only.
- Attribute precedence follows feed order; **geometry** precedence favors the USPVDB polygon when present.
- Rows carrying **no `eia_id`** can't be exactly keyed → fall back to a name + coordinate proximity match; report how many rows this covers and disclose any residual.

## Consequences

- Solar count drops ~967 → ~300 distinct farms; parcel-solar attachment counts change — re-eyeball after regen.
- Composite regen; dedup covered by tests.

## Alternatives considered

- **USPVDB as base** — rejected; it dropped operator and is point-only for unmatched rows.
- **Union then dedup by name** — rejected; `eia_id` is the exact key, name matching is a fuzzy fallback only.
