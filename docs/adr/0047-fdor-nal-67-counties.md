# ADR-047: FL FDOR NAL coverage expanded to all 67 counties

**Status:** Accepted
**Date:** 2026-05-19

**Supersedes:** [ADR-046](0046-fl-fdor-nal-10-counties.md) (county set).

## Context

The original Florida Department of Revenue (FDOR) Name-Address-Legal (NAL) scope was 10 representative counties (~60% of FL population) to keep manual-download effort bounded. The PAR (parcel) shapefiles turned out to already join the PIN (parcel identification number) and NAL records. Downloads are direct, with no queueing or click-through per county beyond the one-time portal terms acceptance. So the marginal effort to pull all 67 is low, and "all of Florida" is a clearer claim than "representative counties".

## Decision

`fdor_nal` ships all 67 Florida counties for v1. The walkthrough lists every county alphabetically as a download checklist. Both condo files (`miamidade_condos_2025par.zip` and `stjohnscondos_2025.zip`) are included.

## Consequences

FL raw footprint grows from ~500 MB to ~2-3 GB (still well within budget, since the cost is disk, not API calls). Preprocess time for FL scales ~6.7x; this stress-tests the Section 5.2 vectorization work. Full coverage also removes "why those 10 counties?" as a question. No change to the canonical schema, normalizer, or the FGDL deferral.
