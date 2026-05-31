"""Parametric spatial-attribute Join (whole-layer feed).

Registers spec-driven instances that annotate an in-memory target layer
with columns derived from spatial hits against a source layer. The actual
computation lives in the shared annotator
(``preprocess.annotators.spatial_attribute``); this is the whole-layer
feed over it. The streaming Composer feeds the *same* annotator per parcel
chunk, so there is one implementation, not two.

Live registrations: ``TowerToDistressJoin`` (runs via the registry on the
tower layer). ``ParcelToDistressJoin`` is registered for name/manifest
continuity but skipped by the Composer, which annotates parcels per chunk.

``SpatialAttributeSpec`` is re-exported here from the annotator so the
long-standing ``from preprocess.joins.spatial_attribute import …`` surface
stays stable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..annotators.spatial_attribute import SpatialAttributeSpec, annotate
from ..base import ComposeContext, Join, register_join_instance

__all__ = [
    "SpatialAttributeSpec",
    "SpatialAttributeJoin",
    "PARCEL_TO_DISTRESS_SPEC",
    "TOWER_TO_DISTRESS_SPEC",
]


class SpatialAttributeJoin(Join):
    """Whole-layer Join driven by a `SpatialAttributeSpec`."""

    def __init__(self, spec: SpatialAttributeSpec, name: str):
        self.spec = spec
        self.name = name
        self.inputs = [spec.target, spec.source]
        self.annotates = spec.target
        self.columns_added = list(spec.derived_columns.keys())

    def apply(self, ctx: ComposeContext) -> None:
        tgt = ctx.get(self.spec.target)
        src = ctx.get(self.spec.source)
        # Guard here (not just in annotate) so an absent/empty source is a
        # true no-op: no columns added, nothing appended to join_log.
        if tgt is None or src is None or len(src) == 0:
            return
        ctx.set(self.spec.target, annotate(tgt, src, self.spec))
        ctx.join_log.append(self.name)


# ── Distress-overlay specs ──────────────────────────────────────────────
#
# Both replace what were previously two near-identical hand-written
# Joins (ParcelToDistressJoin / TowerToDistressJoin). Parcels use
# `intersects` because parcel polygons can straddle overlay boundaries;
# towers use `within` because a tower's point is either inside or not.
# Both derive the same three columns from the same set of overlay_type
# values, so the spec is reused.

_DISTRESS_DERIVED: dict[str, Callable[[set[str]], Any]] = {
    "distress_overlays": lambda s: sorted(s),
    "in_oz": lambda s: "opportunity_zone" in s,
    "in_qct": lambda s: "qct" in s,
}

PARCEL_TO_DISTRESS_SPEC = SpatialAttributeSpec(
    target="parcel",
    source="distress_overlay",
    predicate="intersects",
    category_column="overlay_type",
    derived_columns=_DISTRESS_DERIVED,
)

TOWER_TO_DISTRESS_SPEC = SpatialAttributeSpec(
    target="tower",
    source="distress_overlay",
    predicate="within",
    category_column="overlay_type",
    derived_columns=_DISTRESS_DERIVED,
)

# Pin legacy names so existing manifests + logs stay continuous.
register_join_instance(SpatialAttributeJoin(PARCEL_TO_DISTRESS_SPEC, "ParcelToDistressJoin"))
register_join_instance(SpatialAttributeJoin(TOWER_TO_DISTRESS_SPEC, "TowerToDistressJoin"))
