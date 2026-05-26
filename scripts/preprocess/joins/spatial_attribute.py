"""Parametric spatial-attribute Join.

Pattern: for each row in `target`, find rows of `source` it spatially
hits (under a configurable predicate), bucket the hits by a category
column, then derive new annotation columns from the per-row set of
category values.

Replaces hand-written per-target distress joins (ParcelToDistressJoin /
TowerToDistressJoin). Future spatial annotators (FEMA flood zones,
broadband-served polygons, etc.) follow the same shape — one
`SpatialAttributeSpec` declaration + one `register_join_instance` call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

import geopandas as gpd

from ..base import ComposeContext, Join, register_join_instance

Predicate = Literal["intersects", "within", "contains"]


@dataclass(frozen=True)
class SpatialAttributeSpec:
    """Declarative description of a spatial-attribute annotation.

    Fields:
      target            — canonical type to annotate (e.g. "parcel").
      source            — canonical type carrying the categorical attribute
                          (e.g. "distress_overlay").
      predicate         — sjoin predicate. Parcels typically `intersects`
                          an overlay polygon; point-like targets (towers)
                          are `within` an overlay polygon.
      category_column   — column on `source` whose distinct values become
                          the per-target set buckets (e.g. "overlay_type").
                          When None, every source row contributes a single
                          sentinel; useful for boolean "any hit?" annotations.
      derived_columns   — map column-name → fn(set_of_categories) → value.
                          Each entry becomes one new column on `target`.
    """

    target: str
    source: str
    predicate: Predicate
    category_column: str | None
    derived_columns: dict[str, Callable[[set[str]], Any]]


class SpatialAttributeJoin(Join):
    """Generic Join driven by a `SpatialAttributeSpec`."""

    def __init__(self, spec: SpatialAttributeSpec, name: str):
        self.spec = spec
        self.name = name
        self.inputs = [spec.target, spec.source]
        self.annotates = spec.target
        self.columns_added = list(spec.derived_columns.keys())

    def apply(self, ctx: ComposeContext) -> None:
        tgt = ctx.get(self.spec.target)
        src = ctx.get(self.spec.source)
        if tgt is None or src is None or len(src) == 0:
            return

        per_target: dict[int, set[str]] = {}
        cats: list[Any]
        if self.spec.category_column is not None:
            cats = list(src[self.spec.category_column].dropna().unique())
        else:
            cats = [None]

        for cat in cats:
            subset = (
                src[src[self.spec.category_column] == cat]
                if cat is not None
                else src
            )
            try:
                hit = gpd.sjoin(
                    tgt[["geometry"]].reset_index(),
                    subset[["geometry"]],
                    how="inner",
                    predicate=self.spec.predicate,
                )
            except Exception:
                # Spatial-join failures (mixed CRS, empty geom column on
                # one side) are recoverable per-category — keep going so
                # one bad overlay_type doesn't suppress the others.
                continue
            for idx in hit["index"].unique():
                per_target.setdefault(int(idx), set()).add(
                    cat if cat is not None else "_hit_"
                )

        tgt = tgt.copy()
        for col_name, fn in self.spec.derived_columns.items():
            tgt[col_name] = tgt.index.map(lambda i: fn(per_target.get(int(i), set())))
        ctx.set(self.spec.target, tgt)
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
register_join_instance(
    SpatialAttributeJoin(PARCEL_TO_DISTRESS_SPEC, "ParcelToDistressJoin")
)
register_join_instance(
    SpatialAttributeJoin(TOWER_TO_DISTRESS_SPEC, "TowerToDistressJoin")
)
