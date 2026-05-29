# ADR-017: Indiana dropped from anchor states

**Status:** Accepted
**Date:** 2026-05-18

## Context

Indiana's public parcels (downloaded via in_parcels) carry no `owner_name` column whatsoever — only `parcel_id`, geometry, county FIPS, situs address.

## Decision

Mothball IN from pitch anchor set; raw stays on disk for future re-evaluation.

## Consequences

Pitch demo skips IN entirely; map app hides it.
