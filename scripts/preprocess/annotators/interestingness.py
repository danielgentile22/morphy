"""Interestingness scoring: bake the default-profile score per parcel.

Single deep implementation. Sits at the seam between the weight-free
``ScoreComponents`` extractor and the weight applier (both in
``preprocess.scoring``): bakes the default-profile score into parquet and
also persists the raw components so the map app can re-score live under a
different profile (ADR-058).

Parcel-only; pure per-row math (no cross-chunk state), so there is no
``prepare`` step — :func:`annotate` is the whole concept.
"""

from __future__ import annotations

import geopandas as gpd

from ..scoring import DEFAULT_PROFILE, apply_weights, compute_components


def annotate(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Add interestingness_score + post-weight breakdown + raw components."""
    components = parcels.apply(compute_components, axis=1)
    scored = components.apply(lambda c: apply_weights(c, DEFAULT_PROFILE))
    parcels = parcels.copy()
    parcels["interestingness_score"] = scored.apply(lambda t: t[0])
    # Post-weight breakdown — the legacy column the detail panel reads.
    parcels["interestingness_components"] = scored.apply(lambda t: t[1])
    # Weight-free raw signals — the TS scorer (ADR-058) reads this.
    parcels["interestingness_components_raw"] = components.apply(lambda c: c.to_dict())
    return parcels
