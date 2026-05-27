# ADR-020: `safe_merge` helper for joins with pre-initialized columns

**Status:** Accepted
**Date:** 2026-05-19

## Context

Three `county_score_to_*` joins all hit a `KeyError` because the parcel schema initialized `distress_tier` / `persistent_poverty` as placeholders, causing `_x`/`_y` column collision on `pd.merge`.

## Decision

Extract a `safe_merge(left, right, on, columns_to_add)` helper into `scripts/preprocess/base.py` that drops pre-existing target columns before merging. Apply to every join that adds columns also initialized in a normalizer.

## Consequences

Generic guard; future joins won't repeat this bug pattern.
