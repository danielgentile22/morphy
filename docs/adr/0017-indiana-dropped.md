# ADR-017: Indiana dropped from anchor states

**Status:** Accepted
**Date:** 2026-05-18

## Context

Indiana's public parcels (downloaded via in_parcels) carry no `owner_name` column whatsoever, only `parcel_id`, geometry, county FIPS, situs address.

## Decision

Drop IN from the anchor set; raw data stays on disk for re-evaluation.

## Consequences

The map app hides IN entirely.
