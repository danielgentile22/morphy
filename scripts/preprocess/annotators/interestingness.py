"""Interestingness scoring: bake the default-profile score per parcel.

Single deep implementation. Sits at the seam between the weight-free
``ScoreComponents`` extractor and the weight applier (both in
``preprocess.scoring``): bakes the default-profile score + its post-weight
breakdown into parquet. Live re-scoring under a different profile (ADR-058)
happens in the browser over owner-level features, not per-parcel components.

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
    # Post-weight breakdown — the column the detail panel reads.
    parcels["interestingness_components"] = scored.apply(lambda t: t[1])
    # E10: the weight-free `interestingness_components_raw` twin was dropped —
    # it had no consumer (the TS scorer re-scores from owner-level features,
    # not per-parcel raw components).
    return parcels
