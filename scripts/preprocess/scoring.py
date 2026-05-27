"""Per-parcel interestingness scoring (ADR-058).

Two halves on either side of a stable seam:

  - ``ScoreComponents`` + ``compute_components`` — weight-free signals.
    Pure functions over a parcel row; both Python and the future TS
    scorer (``app/src/lib/scoring.ts``) start from this same dict shape.
  - ``ScoringProfile`` + ``apply_weights`` — named bundle of knobs +
    the only consumer-facing scoring entry point. ``DEFAULT_PROFILE``
    reproduces the legacy hardcoded weights so parquet output is
    unchanged.

Adding a new signal is two edits: append a field to ``ScoreComponents``
and a derivation in ``compute_components``. The matching weight goes
into ``ScoringProfile``. The TS scorer (when it lands) gets the same
field-level diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Weight-free signals ────────────────────────────────────────────────────


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
    """Extract ``ScoreComponents`` from a parcel row (pandas Series).

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


# ── Weighted scoring ───────────────────────────────────────────────────────


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

    Breakdown keys match the legacy ``interestingness_components`` shape
    so downstream consumers (the detail panel, exports) keep reading
    from the same field names.
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
