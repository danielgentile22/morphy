"""Apply scoring weights to `ScoreComponents`.

`ScoringProfile` is a named bundle of knobs. `apply_weights(components,
profile) -> (score, breakdown)` is the only consumer-facing function.
The Python default profile (`DEFAULT_PROFILE`) reproduces the legacy
hardcoded weights exactly — so the score baked into parquet stays
identical after the refactor.

ADR-058 commits to the same shape for the TypeScript twin in
`app/src/lib/scoring.ts`: when that lands, both sides apply weights
over the same `ScoreComponents` dict, and any drift is one shared
field-level diff away from being visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .score_components import ScoreComponents


@dataclass
class ScoringProfile:
    """Named bundle of weights — the user-tunable surface."""

    name: str = "default"
    # Infrastructure
    infra_any: float = 0.30
    infra_multi_type: float = 0.05
    infra_multi_instance: float = 0.05
    # Distress overlays
    distress_first: float = 0.15
    distress_extra: float = 0.05
    # ARC tier — keys are the canonical tier names emitted by the
    # county-score normalizers (lowercased).
    arc_tier: dict[str, float] = field(
        default_factory=lambda: {
            "distressed": 0.15,
            "at-risk": 0.10,
            "transitional": 0.05,
        }
    )
    # Owner kind
    owner_llc_trust: float = 0.10
    # Owner cluster size
    cluster_min: float = 0.05
    cluster_portfolio: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "infra_any": self.infra_any,
            "infra_multi_type": self.infra_multi_type,
            "infra_multi_instance": self.infra_multi_instance,
            "distress_first": self.distress_first,
            "distress_extra": self.distress_extra,
            "arc_tier": dict(self.arc_tier),
            "owner_llc_trust": self.owner_llc_trust,
            "cluster_min": self.cluster_min,
            "cluster_portfolio": self.cluster_portfolio,
        }


DEFAULT_PROFILE = ScoringProfile()


def apply_weights(
    c: ScoreComponents, p: ScoringProfile | None = None
) -> tuple[float, dict[str, float]]:
    """Combine components + profile into (score in [0,1], breakdown).

    Breakdown keys match the legacy `interestingness_components` shape so
    downstream consumers (the detail panel, exports) keep reading from
    the same field names.
    """
    profile = p or DEFAULT_PROFILE

    infra = 0.0
    if c.infra_types >= 1:
        infra = profile.infra_any
        if c.infra_types >= 2:
            infra += profile.infra_multi_type
        if c.max_infra_instances >= 2:
            infra += profile.infra_multi_instance

    distress = 0.0
    if c.overlays >= 1:
        distress = profile.distress_first + profile.distress_extra * (c.overlays - 1)

    tier = profile.arc_tier.get(c.arc_tier, 0.0)
    owner = profile.owner_llc_trust if c.owner_kind in ("llc", "trust") else 0.0

    cluster = 0.0
    if c.cluster_size >= 2:
        cluster = profile.cluster_min
        if c.cluster_size >= 5:
            cluster += profile.cluster_portfolio

    breakdown = {
        "infrastructure": round(infra, 3),
        "distress_overlays": round(distress, 3),
        "county_tier": round(tier, 3),
        "owner_kind": round(owner, 3),
        "owner_cluster": round(cluster, 3),
    }
    total = max(0.0, min(1.0, sum(breakdown.values())))
    return round(total, 3), breakdown
