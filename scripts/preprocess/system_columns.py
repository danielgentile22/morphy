"""System columns + system-time helpers + the canonical ``safe_merge``.

Every Normalizer stamps the four system columns + three time-series
columns onto every row before write. The same module hosts the merge
helper Joins use to populate placeholder columns without colliding into
``_x`` / ``_y`` suffixes.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def utcnow_date() -> str:
    return datetime.now(UTC).date().isoformat()


def add_system_columns(
    df,
    source_id: str,
    canonical_type: str,
    *,
    tenant_id: str = "pilot",
    valid_from: str | None = None,
):
    """Stamp the four system columns + the three time-series ones on every row.

    Returns the same DataFrame/GeoDataFrame (modified in place + returned for
    chaining). Caller decides ordering — these are typically appended last so
    they're easy to spot.
    """
    from .base import CURRENT_SCHEMA_VERSIONS

    schema_version = CURRENT_SCHEMA_VERSIONS.get(canonical_type, 1)
    now = utcnow_iso()
    today = valid_from or utcnow_date()

    df["_source"] = source_id
    df["_processed_at"] = now
    df["_schema_version"] = schema_version
    df["_tenant_id"] = tenant_id
    if "_quality_score" not in df.columns:
        df["_quality_score"] = None
    df["valid_from"] = today
    if "valid_to" not in df.columns:
        df["valid_to"] = None
    return df


def safe_merge(left, right, *, on, columns_added, how="left"):
    """Left-merge ``right`` into ``left``, where ``right`` contributes
    ``columns_added``.

    Normalizers initialise reverse-summary columns (e.g. ``distress_tier``,
    ``persistent_poverty`` on a parcel) as placeholders so the canonical
    schema is stable before any Join runs. When a Join later merges in the
    *real* values, pandas sees the column on both sides and produces
    ``col_x`` / ``col_y`` — silently leaving the placeholder in place. This
    helper drops the pre-existing ``columns_added`` from ``left`` first so
    the merge populates fresh values cleanly.

    Restores GeoDataFrame geometry registration when ``left`` was
    geospatial — a plain ``merge`` can drop the geometry-column binding.

    Callers still do their own ``fillna`` afterwards: the right default
    differs per column ("" for a tier string, False for a boolean flag).
    """
    import geopandas as gpd

    left_clean = left.drop(columns=[c for c in columns_added if c in left.columns])
    merged = left_clean.merge(right, on=on, how=how)
    if "geometry" in merged.columns:
        merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=getattr(left, "crs", None))
    return merged
