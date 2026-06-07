"""Spatial-attribute annotation: per-target set of spatially-hit categories.

Single deep implementation for the "bucket spatial hits, derive columns"
pattern. Drives the distress-overlay annotation on both the live tower
registry join (:class:`SpatialAttributeJoin` with ``TOWER_TO_DISTRESS_SPEC``)
and the streaming parcel feed (``PARCEL_TO_DISTRESS_SPEC``), and is the
template for future spatial annotators (FEMA flood zones, broadband-served
polygons, …).

For each ``target`` geometry, find the set of ``category_column`` values
from ``source`` it spatially hits (under ``predicate``), then derive one
column per ``derived_columns`` entry from that per-row set. One body, two
feeds; the only feed-specific knob is whether to drop invalid/null target
geometry before the sjoin — parcels do (polygons can be invalid and would
corrupt or abort the sjoin), point targets like towers keep their
historical no-filter behavior.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import geopandas as gpd

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


def annotate(
    target,
    source,
    spec: SpatialAttributeSpec,
    *,
    filter_invalid_target_geom: bool = False,
):
    """Annotate ``target`` with ``spec.derived_columns`` from spatial hits.

    Returns ``target`` unchanged (same object) when ``source`` is empty:
    the parcel placeholders the normalizer set already hold the right
    empty values (so the streaming feed stays byte-identical), and infra
    targets simply get no columns — matching the historical registry
    behavior where an absent source is a no-op.

    When ``filter_invalid_target_geom`` is True, invalid/null-geometry
    rows are dropped from the sjoin input (they still appear in the
    output with the empty-set derivation via the index map). Used for
    parcels, whose polygons can be invalid.
    """
    if target is None or source is None or len(source) == 0:
        return target

    if spec.category_column is not None:
        cats: list[Any] = list(source[spec.category_column].dropna().unique())
    else:
        cats = [None]

    geo = target[["geometry"]].reset_index()
    if filter_invalid_target_geom:
        # Reuse the precomputed geometry_valid column when present (PERF-028) —
        # the normalizer already stored geometry.notna() & geometry.is_valid, so
        # this skips recomputing the expensive GEOS validity once per category
        # sjoin. Fall back to recomputing when the target lacks the column (e.g.
        # the tower feed never filters, so it never reaches here without it).
        if "geometry_valid" in target.columns:
            geo = geo[target["geometry_valid"].fillna(False).astype(bool).to_numpy()]
        else:
            geo = geo[geo.geometry.notna() & geo.geometry.is_valid]

    per_target: dict[int, set[str]] = {}
    for cat in cats:
        subset = source[source[spec.category_column] == cat] if cat is not None else source
        try:
            hit = gpd.sjoin(geo, subset[["geometry"]], how="inner", predicate=spec.predicate)
        except Exception:
            # Spatial-join failures (mixed CRS, empty geom column on one
            # side) are recoverable per-category — keep going so one bad
            # category doesn't suppress the others.
            continue
        for idx in hit["index"].unique():
            per_target.setdefault(int(idx), set()).add(cat if cat is not None else "_hit_")

    out = target.copy()
    # Resolve each row's hit-set ONCE, then derive every column from that single
    # list (PERF-029) — was one full-index Python walk per derived column.
    sets = [per_target.get(int(i), set()) for i in out.index]
    for col_name, fn in spec.derived_columns.items():
        out[col_name] = [fn(s) for s in sets]
    return out
