"""Per-state rollup — high-level stats for this state's composite."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd

from ..base import ChunkAggregator, View, register_view


@register_view
class StateSummaryView(View):
    name = "state_summary"
    inputs = ["parcel"]
    description = "State-level rollup: total counts, top owners, top counties."
    write_geojson = False

    def make_aggregator(self) -> ChunkAggregator:
        return StateSummaryAggregator()


class StateSummaryAggregator:
    """Streaming state_summary — a one-row DataFrame.

    Bespoke because the view mixes scalar counts, top-N owners, and
    top-N counties; finalize also reads the in-memory infra layer counts
    from ctx (tower / solar / billboard).
    """

    name = "state_summary"

    def __init__(self) -> None:
        self._parcel_count = 0
        self._any_infra = 0
        self._llc = 0
        self._oz = 0
        self._qct = 0
        self._distressed = 0
        self._persistent = 0
        self._top_owners: list[pd.DataFrame] = []
        self._top_counties: list[pd.DataFrame] = []

    def consume(self, chunk: gpd.GeoDataFrame) -> None:
        df = chunk
        self._parcel_count += len(df)
        any_infra = df.get("has_tower", False).fillna(False) | df.get("has_solar", False).fillna(
            False
        )
        self._any_infra += int(any_infra.sum())
        if "owner_kind" in df.columns:
            self._llc += int((df["owner_kind"] == "llc").sum())
        self._oz += int(df.get("in_oz", False).fillna(False).sum())
        self._qct += int(df.get("in_qct", False).fillna(False).sum())
        if "distress_tier" in df.columns:
            self._distressed += int(df["distress_tier"].fillna("").isin(["distressed"]).sum())
        self._persistent += int(df.get("persistent_poverty", False).fillna(False).sum())
        # Per-chunk partial top-20 owner aggregates (combined at finalize).
        if "owner_cluster_id" in df.columns:
            sub = df[df["owner_cluster_id"] != ""]
            if len(sub) > 0:
                owner_partial = (
                    sub.groupby("owner_cluster_id")
                    .agg(
                        owner_name=("owner_name", "first"),
                        owner_kind=("owner_kind", "first"),
                        parcel_count=("owner_cluster_id", "size"),
                        total_value=("assessed_value", "sum"),
                    )
                    .reset_index()
                )
                self._top_owners.append(owner_partial)
        # Per-chunk partial per-county aggregates.
        if "county_fips" in df.columns:
            df = df.copy()
            df["_any_infra"] = any_infra
            county_partial = (
                df.groupby("county_fips")
                .agg(
                    parcels_hosting_infra=("_any_infra", "sum"),
                    parcel_count=("parcel_id_full", "size"),
                )
                .reset_index()
            )
            self._top_counties.append(county_partial)

    def finalize(self, ctx: Any) -> pd.DataFrame:
        # Combine partials into final top-20.
        owners_top: list[dict] = []
        if self._top_owners:
            owners = pd.concat(self._top_owners, ignore_index=True)
            owners = (
                owners.groupby("owner_cluster_id")
                .agg(
                    owner_name=("owner_name", "first"),
                    owner_kind=("owner_kind", "first"),
                    parcel_count=("parcel_count", "sum"),
                    total_value=("total_value", "sum"),
                )
                .reset_index()
                .sort_values("total_value", ascending=False)
                .head(20)
            )
            owners_top = owners.to_dict(orient="records")
        counties_top: list[dict] = []
        if self._top_counties:
            counties = pd.concat(self._top_counties, ignore_index=True)
            counties = (
                counties.groupby("county_fips")
                .agg(
                    parcels_hosting_infra=("parcels_hosting_infra", "sum"),
                    parcel_count=("parcel_count", "sum"),
                )
                .reset_index()
                .sort_values("parcels_hosting_infra", ascending=False)
                .head(20)
            )
            counties_top = counties.to_dict(orient="records")

        tower_count = len(ctx.get("tower")) if ctx.has("tower") else 0
        solar_count = len(ctx.get("solar_facility")) if ctx.has("solar_facility") else 0
        billboard_count = len(ctx.get("billboard")) if ctx.has("billboard") else 0

        return pd.DataFrame(
            [
                {
                    "state_fips": ctx.state_fips,
                    "state_name": ctx.state_name,
                    "tower_count": tower_count,
                    "parcel_count": self._parcel_count,
                    "solar_facility_count": solar_count,
                    "billboard_count": billboard_count,
                    "parcels_hosting_infra": self._any_infra,
                    "llc_owned_parcels": self._llc,
                    "parcels_in_oz": self._oz,
                    "parcels_in_qct": self._qct,
                    "parcels_distressed_county": self._distressed,
                    "parcels_persistent_poverty": self._persistent,
                    "top_owners": owners_top,
                    "top_counties": counties_top,
                }
            ]
        )
