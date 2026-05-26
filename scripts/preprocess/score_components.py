"""Weight-free per-parcel signals.

`ScoreComponents` is the **contract** between Python and the future
TypeScript scorer (ADR-058): both sides start from the same dict shape
and apply a `ScoringProfile` to it. Components themselves never carry
weights — they describe what's true about a parcel, not how much it's
worth.

Adding a new component is two edits: append a field to `ScoreComponents`
and a derivation in `compute_components`. The matching weight goes into
`score_weights.ScoringProfile`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScoreComponents:
    """Per-parcel weight-free signals. Same shape Python ↔ TypeScript.

    Field semantics:
      - infra_types — number of distinct infra kinds present (0..3 today:
        tower + solar + billboard)
      - max_infra_instances — max(tower_count, solar_count, billboard_count)
      - overlays — number of distress overlays the parcel sits in (0..3)
      - arc_tier — "" | "transitional" | "at-risk" | "distressed"
      - owner_kind — "" | "individual" | "llc" | "trust" | …
      - cluster_size — number of parcels in this owner_cluster (1..N)
    """

    infra_types: int = 0
    max_infra_instances: int = 0
    overlays: int = 0
    arc_tier: str = ""
    owner_kind: str = ""
    cluster_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "infra_types": self.infra_types,
            "max_infra_instances": self.max_infra_instances,
            "overlays": self.overlays,
            "arc_tier": self.arc_tier,
            "owner_kind": self.owner_kind,
            "cluster_size": self.cluster_size,
        }


def compute_components(row: Any) -> ScoreComponents:
    """Extract `ScoreComponents` from a parcel row (pandas Series).

    Pure function — no weight application here. Missing columns default
    sensibly so the function survives an early-pipeline call before
    every Join has run.
    """
    has_tower = bool(_get(row, "has_tower", False))
    has_solar = bool(_get(row, "has_solar", False))
    has_billboard = bool(_get(row, "has_billboard", False))
    tower_count = int(_get(row, "tower_count", 0) or 0)
    solar_count = int(_get(row, "solar_count", 0) or 0)
    billboard_count = int(_get(row, "billboard_count", 0) or 0)

    in_oz = bool(_get(row, "in_oz", False))
    in_qct = bool(_get(row, "in_qct", False))
    persistent_poverty = bool(_get(row, "persistent_poverty", False))

    arc_tier = (_get(row, "distress_tier", "") or "").lower()
    owner_kind = (_get(row, "owner_kind", "") or "").lower()
    cluster_size = int(_get(row, "owner_cluster_size", 0) or 0)

    return ScoreComponents(
        infra_types=int(has_tower) + int(has_solar) + int(has_billboard),
        max_infra_instances=max(tower_count, solar_count, billboard_count),
        overlays=int(in_oz) + int(in_qct) + int(persistent_poverty),
        arc_tier=arc_tier,
        owner_kind=owner_kind,
        cluster_size=cluster_size,
    )


def _get(row: Any, key: str, default):
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    if v is None:
        return default
    try:
        # NaN check without importing pandas (NaN != NaN)
        if v != v:
            return default
    except Exception:
        pass
    return v
