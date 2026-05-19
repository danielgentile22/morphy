"""HUD Opportunity Zones + Qualified Census Tracts → canonical `distress_overlay`.

Both sources are GeoJSON FeatureCollections from HUD's ArcGIS Open Data
hub. Same Normalizer handles both — but they're registered as separate
sources (one per source_id), so two classes share one read function.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import geopandas as gpd
import pandas as pd

from ..base import (
    NormalizeResult,
    Normalizer,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..geom import add_polygon_derivatives
from ..io import dual_write_spatial, write_raw_parquet
from ._helpers import canon_county_fips, canon_state_fips, safe_str

log = logging.getLogger("preprocess.hud_overlays")


def _find_geojson(raw_dir: Path) -> Optional[Path]:
    if not raw_dir.exists():
        return None
    candidates = list(raw_dir.rglob("*.geojson")) + list(raw_dir.rglob("*.json"))
    return candidates[0] if candidates else None


def _normalize_overlay(
    raw_dir: Path,
    out_dir: Path,
    source_id: str,
    overlay_type: str,
    basename: str,
) -> NormalizeResult:
    src = _find_geojson(raw_dir)
    if src is None:
        raise FileNotFoundError(f"{source_id}: no .geojson found under {raw_dir}")
    gdf = gpd.read_file(src)
    log.info("%s: read %d features from %s", source_id, len(gdf), src.name)

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    raw_bytes = write_raw_parquet(gdf, out_dir, name="raw.parquet")

    # Build canonical rows. Field names vary (OZ uses GEOID10/STATE/COUNTY/TRACT,
    # QCT uses STATE/COUNTY/TRACT/GEOID2024 etc.) — try common spellings.
    rows: list[dict] = []
    for _, r in gdf.iterrows():
        # GEOID
        geoid = (
            r.get("GEOID10") or r.get("GEOID") or r.get("GEOID2024") or
            r.get("GEOID20") or r.get("geoid") or ""
        )
        state_fips = canon_state_fips(
            r.get("STATE") or r.get("STATEFP") or r.get("state_fips") or
            r.get("STATE_FIPS")
        )
        county_fips_raw = (
            r.get("COUNTY") or r.get("COUNTYFP") or r.get("county_fips")
        )
        county_fips = canon_county_fips(county_fips_raw, state_fips=state_fips)
        tract = safe_str(r.get("TRACT") or r.get("tract") or r.get("TRACTCE"))
        rural = r.get("Rural") or r.get("rural") or r.get("RURAL")
        rural_flag = None
        if rural is not None and not (isinstance(rural, float) and pd.isna(rural)):
            rural_flag = safe_str(rural).upper() in ("Y", "YES", "TRUE", "1")
        rows.append({
            "overlay_type": overlay_type,
            "geoid": safe_str(geoid),
            "state_fips": state_fips,
            "county_fips": county_fips,
            "tract": tract,
            "rural_flag": rural_flag,
            "attributes": {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
                           for k, v in r.items() if k != "geometry"},
            "geometry": r.geometry,
        })

    out = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    out = add_polygon_derivatives(out)
    out = add_system_columns(out, source_id, "distress_overlay")

    files, written = dual_write_spatial(out, out_dir, basename, write_simplified_geojson=True)
    total = raw_bytes + written

    qr = quality_report(source_id, {"raw": gdf, basename: out})
    qr_path = write_quality_report(out_dir, qr)

    return NormalizeResult(
        raw_rows=len(gdf),
        canonical_rows=len(out),
        bytes=total,
        output_files=files + [out_dir / "raw.parquet", qr_path],
        canonical_types_written=["distress_overlay"],
        quality_report=qr,
    )


@register_normalizer
class HudOzNormalizer(Normalizer):
    source_id = "hud_oz"
    canonical_types = ["distress_overlay"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        return _normalize_overlay(
            raw_dir, out_dir, self.source_id, "opportunity_zone", "opportunity_zones",
        )


@register_normalizer
class HudQctNormalizer(Normalizer):
    source_id = "hud_qct"
    canonical_types = ["distress_overlay"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        return _normalize_overlay(
            raw_dir, out_dir, self.source_id, "qct", "qualified_census_tracts",
        )
