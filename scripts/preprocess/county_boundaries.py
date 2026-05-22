"""county_boundaries.geojson — the county-choropleth source layer.

`county_scores.parquet` carries per-county distress data but **no
geometry**. This clips a vendored Census cartographic county file
(public domain, 1:20M — committed under ``assets/``) to a state's
counties and joins the distress data, producing the polygon layer the
map app shades at low zoom (parcels take over when zoomed in).

An ``--app-assets`` output — built by ``run_app_assets()`` and by a
standalone ``preprocess.py --app-assets`` run; no recompose needed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import COMPOSITE_ROOT, PACKAGE_DIR
from .io import write_geojson

log = logging.getLogger("preprocess.county_boundaries")

# Vendored Census cartographic county boundaries (GENZ2023, 1:20M).
COUNTY_SHAPEFILE = PACKAGE_DIR / "assets" / "cb_2023_us_county_20m.zip"

# Distress fields collapsed out of county_scores. county_scores holds two
# rows per county — an `arc_distressed` row (tier + ARC flags) and a
# `usda_persistent_poverty` row (persistent_poverty) — so each field is
# populated on only one of the two.
_SCORE_FIELDS: tuple[str, ...] = ("tier", "arc_distressed", "arc_at_risk", "persistent_poverty")


def _is_populated(value: object) -> bool:
    """True if a county_scores cell carries a real value (not null / blank)."""
    if value is None:
        return False
    if isinstance(value, float) and value != value:  # NaN
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    return True


def collapse_county_scores(county_scores: pd.DataFrame) -> pd.DataFrame:
    """Collapse county_scores (2 rows / county) to one record per county.

    For each distress field, take the populated value across a county's
    two source rows. Returns a frame indexed by ``county_fips``.
    """

    def first_populated(series: pd.Series) -> object:
        for value in series:
            if _is_populated(value):
                return value
        return None

    fields = [f for f in _SCORE_FIELDS if f in county_scores.columns]
    return county_scores.groupby("county_fips")[fields].agg(first_populated)


def build_county_boundaries(state_fips: str, *, composite_root: Path | None = None) -> Path:
    """Write ``composite/<fips>/county_boundaries.geojson`` for one state.

    Raises on a missing county_scores.parquet or the missing vendored
    Census file — the caller decides whether that is fatal.
    """
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    state_dir = root / state_fips
    scores_path = state_dir / "county_scores.parquet"
    if not scores_path.exists():
        raise FileNotFoundError(f"no county_scores.parquet for state {state_fips}: {scores_path}")
    if not COUNTY_SHAPEFILE.exists():
        raise FileNotFoundError(f"vendored Census county file missing: {COUNTY_SHAPEFILE}")

    # Clip the national county file to this state, reproject to WGS84.
    counties = gpd.read_file(COUNTY_SHAPEFILE)
    counties = counties[counties["STATEFP"] == state_fips].copy()
    if counties.empty:
        raise ValueError(f"no counties in the Census file for state FIPS {state_fips}")
    counties = counties.to_crs("EPSG:4326")

    # Collapse + join the distress data.
    scores = collapse_county_scores(pd.read_parquet(scores_path))
    counties = counties.merge(scores, left_on="GEOID", right_index=True, how="left")

    counties = counties.rename(columns={"GEOID": "county_fips", "NAME": "county_name"})
    keep = ["county_fips", "county_name", *_SCORE_FIELDS, "geometry"]
    out = counties[[c for c in keep if c in counties.columns]]

    out_path = state_dir / "county_boundaries.geojson"
    write_geojson(out, out_path)
    log.info("wrote %s (%d counties)", out_path, len(out))
    return out_path


def _states_with_county_scores(composite_root: Path) -> list[str]:
    """FIPS of every composed state with county_scores, app-excluded ones dropped."""
    from .app_assets import EXCLUDED_FIPS

    if not composite_root.exists():
        return []
    return sorted(
        d.name
        for d in composite_root.iterdir()
        if d.is_dir()
        and d.name not in EXCLUDED_FIPS
        and (d / "county_scores.parquet").exists()
    )


def run_county_boundaries(
    state_fips: str | None = None,
    *,
    composite_root: Path | None = None,
) -> dict:
    """Build county_boundaries.geojson for one state or every composed state."""
    root = composite_root if composite_root is not None else COMPOSITE_ROOT
    states = [state_fips] if state_fips else _states_with_county_scores(root)
    ok: list[str] = []
    failed: list[str] = []
    for fips in states:
        try:
            build_county_boundaries(fips, composite_root=root)
            ok.append(fips)
        except Exception as exc:  # noqa: BLE001 — one state's failure must not abort the rest
            log.error("county_boundaries failed for state %s: %s", fips, exc)
            failed.append(fips)
    return {"ok": ok, "failed": failed}
