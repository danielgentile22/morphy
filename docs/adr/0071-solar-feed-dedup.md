# ADR-071: Solar feed dedup with EIA-860 as the base of record

**Status:** Accepted and implemented (`_dedup_solar_facility` in `scripts/preprocess/compose.py`). Rows with no plant code pass through unkeyed; the name-plus-proximity fallback below was not built.
**Date:** 2026-07-03
**Origin:** one of seven decisions (ADR-070-076) from a data audit, whose working files are not part of this repo.
**Prerequisites (landed):** the earlier solar feed cleaning, the recovery of `eia_id` as a first-class USPVDB column, and the intersects spatial predicate.

## Context

Three solar feeds, EIA-860 (annual), EIA-860M (monthly) and the U.S. Large-Scale Solar Photovoltaic Database (USPVDB, from USGS), are concatenated with **no dedup**. About 967 rows represent roughly **3× ~300 distinct farms**, and USPVDB is reduced to points (polygons dropped). An earlier fix recovered the `eia_id` cross-reference key, which is now first-class on USPVDB rows in the same code space as EIA-860's `facility_id`. So an exact join key exists.

**Data drift found during the audit:** USPVDB v4.0 (on disk) renamed `p_eia_id`→`eia_id` **and dropped the owner/operator field**. EIA-860 still carries operator.

## Decision

- **EIA-860 (annual) is the base of record.** It is the authoritative federal generator inventory, and the only feed still carrying operator/owner.
- **Dedup key:** `eia_id` ↔ EIA-860 `facility_id`. A physical farm present in multiple feeds collapses to one row.
- **Precedence on conflict: 860 → 860M → USPVDB.**
  - **860M** contributes only plants too new to appear in the annual 860 yet.
  - **USPVDB** contributes **polygon geometry** (joined by `eia_id`). A matched farm upgrades from point to footprint; unmatched USPVDB rows survive as point-only.
- Attribute precedence follows feed order; **geometry** precedence favors the USPVDB polygon when present.
- Rows carrying **no `eia_id`** can't be exactly keyed. The plan was to fall back to a name plus coordinate proximity match and disclose the residual.

## Consequences

- Solar count drops from about 967 to about 300 distinct farms, and parcel-solar attachment counts change. Re-eyeball after regen.
- Composite regen; dedup covered by tests.

## Alternatives considered

- **USPVDB as base.** Rejected. It dropped operator and is point-only for unmatched rows.
- **Union then dedup by name.** Rejected. `eia_id` is the exact key; name matching is a fuzzy fallback only.
