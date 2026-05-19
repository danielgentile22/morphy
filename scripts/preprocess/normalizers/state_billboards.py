"""State DOT billboard permits (Excel/CSV) → canonical `billboard`.

One Normalizer per state — FDOT, NCDOT, TxDOT — all sharing column
mapping helpers since the structures are very similar. NC and TX are
records-request-only, so their formats may vary; we read first sheet
of whatever .xlsx/.csv shows up and look for lat/lon-ish columns.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from ..base import (
    Normalizer,
    NormalizeResult,
    add_system_columns,
    quality_report,
    register_normalizer,
    write_quality_report,
)
from ..geom import add_point_derivatives
from ..io import dual_write_spatial, write_raw_parquet
from ._helpers import canon_county_fips, canon_state_fips, safe_str, to_float

log = logging.getLogger("preprocess.billboards")


def _read_any_table(raw_dir: Path) -> tuple[pd.DataFrame, Path]:
    cand = (
        list(raw_dir.rglob("*.xlsx")) + list(raw_dir.rglob("*.xls")) + list(raw_dir.rglob("*.csv"))
    )
    if not cand:
        raise FileNotFoundError(f"no .xlsx / .xls / .csv under {raw_dir}")
    path = cand[0]
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, low_memory=False)
    else:
        df = pd.read_excel(path, sheet_name=0, dtype=str)
    return df, path


def _find_col(df: pd.DataFrame, names: list[str]) -> str | None:
    lower = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    for n in names:
        for k, orig in lower.items():
            if n.lower() in k:
                return orig
    return None


def _normalize_billboards(
    raw_dir: Path,
    out_dir: Path,
    source_id: str,
    state_abbr: str,
) -> NormalizeResult:
    df, path = _read_any_table(raw_dir)
    log.info("%s: read %d rows from %s", source_id, len(df), path.name)
    raw_bytes = write_raw_parquet(df, out_dir, name="raw.parquet")

    lat_col = _find_col(df, ["Latitude", "lat", "Lat", "LATITUDE", "latdec"])
    lon_col = _find_col(df, ["Longitude", "lon", "Long", "LONGITUDE", "londec"])
    permit_col = _find_col(df, ["Permit Number", "Permit", "Permit #", "permit_no"])
    owner_col = _find_col(df, ["Owner Name", "Owner", "Licensee", "Sign Owner"])
    status_col = _find_col(df, ["Status", "Permit Status"])
    county_col = _find_col(df, ["County"])
    route_col = _find_col(df, ["Route", "Highway", "Road"])
    mm_col = _find_col(df, ["Mile Post", "Mile Marker", "Milepost", "MP"])
    date_col = _find_col(df, ["Issued Date", "Issue Date", "Permit Date"])

    rows = []
    state_fips = canon_state_fips(state_abbr)
    for _, r in df.iterrows():
        lat = to_float(r.get(lat_col)) if lat_col else None
        lon = to_float(r.get(lon_col)) if lon_col else None
        geom = None
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            geom = Point(lon, lat)
        county_fips = canon_county_fips(
            r.get(county_col) if county_col else None,
            state_fips=state_fips,
        )
        rows.append(
            {
                "permit_no": safe_str(r.get(permit_col)) if permit_col else "",
                "owner": safe_str(r.get(owner_col)) if owner_col else "",
                "status": safe_str(r.get(status_col)) if status_col else "",
                "state_fips": state_fips,
                "county_fips": county_fips,
                "route": safe_str(r.get(route_col)) if route_col else "",
                "mile_marker": to_float(r.get(mm_col)) if mm_col else None,
                "issue_date": safe_str(r.get(date_col)) if date_col else "",
                "lat": lat,
                "lon": lon,
                "extras": {},
                "_source_row_id": safe_str(r.get(permit_col)) if permit_col else "",
                "geometry": geom,
            }
        )
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    out = add_point_derivatives(out)
    out = add_system_columns(out, source_id, "billboard")
    files, written = dual_write_spatial(out, out_dir, "billboards")
    total = raw_bytes + written
    qr = quality_report(source_id, {"raw": df, "billboards": out})
    qr_path = write_quality_report(out_dir, qr)
    return NormalizeResult(
        raw_rows=len(df),
        canonical_rows=len(out),
        bytes=total,
        output_files=files + [out_dir / "raw.parquet", qr_path],
        canonical_types_written=["billboard"],
        quality_report=qr,
    )


@register_normalizer
class FdotBillboardsNormalizer(Normalizer):
    source_id = "fdot_billboards"
    canonical_types = ["billboard"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        return _normalize_billboards(raw_dir, out_dir, self.source_id, "FL")


@register_normalizer
class NcdotBillboardsNormalizer(Normalizer):
    source_id = "ncdot_billboards"
    canonical_types = ["billboard"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        return _normalize_billboards(raw_dir, out_dir, self.source_id, "NC")


@register_normalizer
class TxdotBillboardsNormalizer(Normalizer):
    source_id = "txdot_billboards"
    canonical_types = ["billboard"]

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        return _normalize_billboards(raw_dir, out_dir, self.source_id, "TX")
