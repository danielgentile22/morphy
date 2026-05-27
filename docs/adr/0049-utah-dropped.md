# ADR-049: Utah dropped from anchor states (no owner data)

**Status:** Accepted
**Date:** 2026-05-20

**Supersedes:** the UT portion of [ADR-011](0011-anchor-states.md).

## Context

UT was an anchor state, picked as the "small, clean dataset" to validate the stack quickly. While wiring up the `ut_parcels` pull, an audit of UGRC's parcel data found that **none** of its public parcel layers include an owner name: the statewide aggregate (`UtahStatewideParcels`, 1.59M records), the per-county basic parcels, and the per-county LIR parcels — all 29 counties scanned — carry value, acreage, property class, year built, and situs address, but the only owner-adjacent field is `OWN_TYPE` (a private/government category, not a name). UGRC's Land Information Record standard deliberately omits owner name. Owner data lives behind 29 separate county-assessor portals with no bulk download.

## Decision

Drop UT from the anchor set, mirroring the Indiana decision ([ADR-017](0017-indiana-dropped.md)) — owner data is the core of the pitch (LLC identification, owner clustering, interestingness scoring) and a UT composite would have empty `owner_name` columns. Anchor set is now **AR + NC + MT + FL**. `UtParcelsManual` moved to the registry's `_DEFERRED` block; it stays imported so it can be re-promoted if a Utah owner-data source ever materialises. MT absorbs UT's former "small clean state" role.

## Consequences

Pitch narrative is 4 states, all with owner data — a *more* consistent demo than 5 states where one behaves differently. No code beyond the registry move + `ut_parcels` description fix. The `ut_parcels.py` source's earlier description ("normalised owner + value attributes") was factually wrong and has been corrected.
