"""Parametric spatial-attribute Join (whole-layer feed).

Registers spec-driven instances that annotate an in-memory target layer
with columns derived from spatial hits against a source layer. The actual
computation lives in the shared annotator
(``preprocess.annotators.spatial_attribute``); this is the whole-layer
feed over it. The streaming Composer feeds the *same* annotator per parcel
chunk, so there is one implementation, not two.

Live registrations: ``TowerToDistressJoin`` (whole-layer via ``apply``)
and ``ParcelToDistressJoin`` (chunked, ADR-051 — the Composer drives it
per parcel shard through ``prepare_chunks``/``apply_chunk``).

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
    """Join driven by a `SpatialAttributeSpec` — whole-layer or chunked."""

    def __init__(
        self,
        spec: SpatialAttributeSpec,
        name: str,
        *,
        chunked: bool = False,
        filter_invalid_target_geom: bool = False,
        depends_on: list[str] | None = None,
    ):
        self.spec = spec
        self.name = name
        self.inputs = [spec.target, spec.source]
        self.annotates = spec.target
        self.columns_added = list(spec.derived_columns.keys())
        self.chunked = chunked
        # Declared here (not at the feed site) so the parcel feed's one
        # behavioral knob lives on the adapter with everything else it owns.
        self.filter_invalid_target_geom = filter_invalid_target_geom
        self.depends_on = list(depends_on or [])
        self._source = None

    def apply(self, ctx: ComposeContext) -> None:
        tgt = ctx.get(self.spec.target)
        src = ctx.get(self.spec.source)
        # Guard here (not just in annotate) so an absent/empty source is a
        # true no-op: no columns added, nothing appended to join_log.
        if tgt is None or src is None or len(src) == 0:
            return
        ctx.set(self.spec.target, annotate(tgt, src, self.spec))
        ctx.join_log.append(self.name)

    # ── chunked feed (parcel, ADR-051) ────────────────────────────────────
    def is_applicable(self, ctx: ComposeContext) -> bool:
        if self.chunked:
            # The target is streamed; the annotator no-ops on an absent
            # source, matching the pre-registry chunk loop exactly.
            return True
        return super().is_applicable(ctx)

    def prepare_chunks(self, ctx: ComposeContext) -> None:
        self._source = ctx.get(self.spec.source)

    def apply_chunk(self, chunk):
        return annotate(
            chunk,
            self._source,
            self.spec,
            filter_invalid_target_geom=self.filter_invalid_target_geom,
        )

    def release_chunks(self) -> None:
        self._source = None


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

# Pin legacy names so existing manifests + logs stay continuous. The parcel
# instance runs chunked with normalize-time geometry-validity filtering
# (PERF-028); depends_on pins its chunk-stage position (column order is part
# of the byte-identical compose contract).
register_join_instance(
    SpatialAttributeJoin(
        PARCEL_TO_DISTRESS_SPEC,
        "ParcelToDistressJoin",
        chunked=True,
        filter_invalid_target_geom=True,
        depends_on=["CountyScoreToParcelJoin"],
    )
)
register_join_instance(SpatialAttributeJoin(TOWER_TO_DISTRESS_SPEC, "TowerToDistressJoin"))
