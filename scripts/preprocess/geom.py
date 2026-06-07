"""Geometry derivatives: centroid, area, bbox, simplified, H3 cell index.

These run at normalize time on polygon/point layers so downstream Joins
and Views never need to recompute them.

Conventions:
  - Input GeoDataFrame is expected in EPSG:4326.
  - Area is computed in metres² by reprojecting to EPSG:5070 (CONUS Albers)
    for the calculation only — leaves the GDF in 4326.
  - Simplification is done in degrees (tolerance ≈ 0.0001 ≈ 10 m at 40°N).
    This is approximate but avoids a full reprojection round-trip; downstream
    map rendering doesn't need sub-metre accuracy.
  - H3 indexing requires the optional `h3` library. If it's not installed,
    the column is left null and we log a warning once.
"""

from __future__ import annotations

import logging

import geopandas as gpd

log = logging.getLogger("preprocess.geom")

# Default simplification tolerance in degrees (~10m at 40°N).
DEFAULT_SIMPLIFY_TOL_DEG = 0.0001
# Default H3 resolution (~0.7 km² cells — fine enough for proximity, coarse
# enough to be useful for clustering).
DEFAULT_H3_RES = 8

_AREA_CRS = "EPSG:5070"  # NAD83 / Conus Albers Equal Area Conic, metres

_h3_module = None
_h3_warned = False


def _h3():
    """Lazy-import h3. Returns None and logs once if unavailable."""
    global _h3_module, _h3_warned
    if _h3_module is not None:
        return _h3_module
    try:
        import h3 as h3_module  # type: ignore

        _h3_module = h3_module
        return h3_module
    except ImportError:
        if not _h3_warned:
            log.info("h3 library not installed — geom_h3_r8 columns will be null")
            _h3_warned = True
        return None


def add_polygon_derivatives(
    gdf: gpd.GeoDataFrame,
    *,
    simplify_tol_deg: float = DEFAULT_SIMPLIFY_TOL_DEG,
) -> gpd.GeoDataFrame:
    """Add geom_centroid / geom_area_m2 / geom_bbox / geom_simplified.

    No-op (returns input unchanged) for non-polygonal GDFs.
    Geometry-invalid rows get null derivatives; the main geometry is preserved.
    """
    if gdf is None or gdf.empty:
        return gdf

    geom_types = set(gdf.geom_type.dropna().unique())
    if not (geom_types & {"Polygon", "MultiPolygon"}):
        return gdf

    if gdf.crs is None:
        log.warning("polygon GDF has no CRS — assuming EPSG:4326")
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    # Centroid (in 4326). suppress shapely warnings about lat/lon centroid
    # being approximate — for our use this is fine (low zoom marker).
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        gdf["geom_centroid"] = gdf.geometry.centroid

    # Area in m² via reprojection to Albers Equal Area.
    try:
        gdf["geom_area_m2"] = gdf.to_crs(_AREA_CRS).geometry.area
    except Exception as e:
        log.warning("area calc failed (%s); using null", e)
        gdf["geom_area_m2"] = None

    # Bounding box as a JSON-serializable list [minx, miny, maxx, maxy].
    # Vectorized (PERF-020): one numpy round-trip instead of a row-wise Python
    # lambda over every parcel — same list-of-4-floats per row, order preserved.
    bounds = gdf.geometry.bounds
    gdf["geom_bbox"] = bounds[["minx", "miny", "maxx", "maxy"]].to_numpy().tolist()

    # Simplified geometry — Douglas-Peucker @ tolerance. preserve_topology=True
    # to avoid self-intersections.
    gdf["geom_simplified"] = gdf.geometry.simplify(simplify_tol_deg, preserve_topology=True)

    return gdf


def add_point_derivatives(
    gdf: gpd.GeoDataFrame,
    *,
    h3_res: int = DEFAULT_H3_RES,
) -> gpd.GeoDataFrame:
    """Add geom_h3_r8 (or geom_h3_r{N}) to a point GDF. Skipped if h3 not installed."""
    if gdf is None or gdf.empty:
        return gdf

    col = f"geom_h3_r{h3_res}"
    h3_mod = _h3()
    if h3_mod is None:
        gdf[col] = None
        return gdf

    def _cell(geom):
        if geom is None or geom.is_empty:
            return None
        try:
            # h3 v4 API: latlng_to_cell(lat, lng, res)
            return h3_mod.latlng_to_cell(geom.y, geom.x, h3_res)
        except AttributeError:
            # h3 v3 fallback: geo_to_h3(lat, lng, res)
            return h3_mod.geo_to_h3(geom.y, geom.x, h3_res)
        except Exception:
            return None

    gdf[col] = gdf.geometry.map(_cell)
    return gdf
