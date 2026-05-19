"""Interestingness scoring.

Composite per-parcel score (0..1) that captures "how attractive is this
parcel for outreach". Used by the default outreach-priority view.

Components (sum to ≤1.0; clipped to [0,1]):
  • hosts infrastructure         (tower / billboard / solar): up to 0.40
      - 0.30 for any infra
      - +0.05 if multiple types
      - +0.05 if multiple instances of any type
  • in distress overlay          (OZ / QCT / persistent poverty): up to 0.25
      - 0.15 for one overlay
      - +0.05 per additional
  • county distress tier         (ARC): up to 0.15
      - 0.15 distressed, 0.10 at-risk, 0.05 transitional
  • owner is LLC / trust         up to 0.10
  • owner cluster size >=2       up to 0.10
      - 0.05 for >=2 parcels
      - +0.05 if >=5 parcels (portfolio holder)

The breakdown is preserved in `interestingness_components` so the map app
can show "why this parcel scored high".
"""

from __future__ import annotations

from typing import Any


def score_parcel_row(row) -> tuple[float, dict[str, float]]:
    """Compute interestingness score for one parcel row.

    row is a pandas Series; missing columns default sensibly.
    Returns (score in [0,1], component breakdown).
    """
    components: dict[str, float] = {}

    # --- infrastructure ---
    has_tower = bool(_get(row, "has_tower", False))
    has_solar = bool(_get(row, "has_solar", False))
    has_billboard = bool(_get(row, "has_billboard", False))
    tower_count = int(_get(row, "tower_count", 0) or 0)
    solar_count = int(_get(row, "solar_count", 0) or 0)
    billboard_count = int(_get(row, "billboard_count", 0) or 0)
    infra_types = int(has_tower) + int(has_solar) + int(has_billboard)
    max_instances = max(tower_count, solar_count, billboard_count)

    infra_score = 0.0
    if infra_types >= 1:
        infra_score = 0.30
        if infra_types >= 2:
            infra_score += 0.05
        if max_instances >= 2:
            infra_score += 0.05
    components["infrastructure"] = round(infra_score, 3)

    # --- distress overlays ---
    in_oz = bool(_get(row, "in_oz", False))
    in_qct = bool(_get(row, "in_qct", False))
    persistent_poverty = bool(_get(row, "persistent_poverty", False))
    overlays = int(in_oz) + int(in_qct) + int(persistent_poverty)
    distress_score = 0.0
    if overlays >= 1:
        distress_score = 0.15 + 0.05 * (overlays - 1)
    components["distress_overlays"] = round(distress_score, 3)

    # --- ARC county tier ---
    tier = (_get(row, "distress_tier", "") or "").lower()
    tier_score = {"distressed": 0.15, "at-risk": 0.10, "transitional": 0.05}.get(tier, 0.0)
    components["county_tier"] = round(tier_score, 3)

    # --- owner kind ---
    owner_kind = (_get(row, "owner_kind", "") or "").lower()
    owner_score = 0.10 if owner_kind in ("llc", "trust") else 0.0
    components["owner_kind"] = round(owner_score, 3)

    # --- owner cluster ---
    cluster_size = int(_get(row, "owner_cluster_size", 0) or 0)
    cluster_score = 0.0
    if cluster_size >= 2:
        cluster_score = 0.05
        if cluster_size >= 5:
            cluster_score += 0.05
    components["owner_cluster"] = round(cluster_score, 3)

    total = sum(components.values())
    total = max(0.0, min(1.0, total))
    return round(total, 3), components


def _get(row: Any, key: str, default):
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    if v is None:
        return default
    try:
        # pandas NaN check without importing
        if v != v:  # NaN != NaN
            return default
    except Exception:
        pass
    return v
