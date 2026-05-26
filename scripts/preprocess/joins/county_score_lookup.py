"""Parametric Join: copy aggregated county_score columns onto any target.

Replaces the three near-identical per-target files
(county_score_to_parcel / _to_tower / _to_solar). Register one instance
per target type; the body is shared.
"""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join_instance, safe_merge


class CountyScoreLookupJoin(Join):
    """Annotate `target_type` with the per-county distress_tier +
    persistent_poverty rolled up from ARC + USDA county_score sources.
    """

    columns_added = ["distress_tier", "persistent_poverty"]

    def __init__(self, target_type: str, name: str | None = None):
        self.target_type = target_type
        # Default naming mirrors the previous classes (CountyScoreToParcelJoin
        # etc.) so existing logs / manifests stay readable. Callers can pass
        # `name` explicitly to pin a legacy name (e.g. "CountyScoreToSolarJoin"
        # for solar_facility, where the underscore would otherwise expand).
        title = "".join(part.capitalize() for part in target_type.split("_"))
        self.name = name or f"CountyScoreTo{title}Join"
        self.inputs = [target_type, "county_score"]
        self.annotates = target_type

    def apply(self, ctx: ComposeContext) -> None:
        target = ctx.get(self.target_type)
        scores = ctx.get("county_score")
        if target is None or scores is None or len(scores) == 0:
            return
        agg = _aggregate_county_score(scores)
        merged = safe_merge(
            target, agg, on="county_fips", columns_added=self.columns_added
        )
        merged["distress_tier"] = merged["distress_tier"].fillna("")
        merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
        ctx.set(self.target_type, merged)
        ctx.join_log.append(self.name)


def _aggregate_county_score(scores):
    """Collapse multi-source (ARC + USDA) county_score rows into one row per FIPS."""
    return (
        scores.groupby("county_fips")
        .agg(
            {
                "tier": lambda x: next((v for v in x if v), ""),
                "persistent_poverty": "any",
            }
        )
        .reset_index()
        .rename(columns={"tier": "distress_tier"})
    )


# Target types to register at import time. Solar pins the legacy name
# (the old class was CountyScoreToSolarJoin, no "Facility") so existing
# manifest entries / logs stay continuous.
_REGISTRATIONS: tuple[tuple[str, str | None], ...] = (
    ("parcel", None),
    ("tower", None),
    ("solar_facility", "CountyScoreToSolarJoin"),
)

for _target, _name in _REGISTRATIONS:
    register_join_instance(CountyScoreLookupJoin(_target, name=_name))
