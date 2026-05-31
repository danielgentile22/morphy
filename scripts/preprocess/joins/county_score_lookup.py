"""Parametric Join: copy aggregated county_score columns onto any target.

Registers one instance per target type (parcel / tower / solar_facility);
the body is a thin whole-layer feed over the shared county-score
annotator (``preprocess.annotators.county_score``). The parcel instance
is skipped by the streaming Composer (which annotates parcels per chunk
through the same annotator); the tower / solar instances run live via the
registry. One computation, two feeds — no twin to drift.
"""

from __future__ import annotations

from ..annotators import county_score
from ..base import ComposeContext, Join, register_join_instance


class CountyScoreLookupJoin(Join):
    """Annotate `target_type` with the per-county distress_tier +
    persistent_poverty rolled up from ARC + USDA county_score sources.
    """

    columns_added = county_score.COLUMNS_ADDED

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
        agg = county_score.prepare(ctx.get("county_score"))
        if target is None or agg is None:
            return
        ctx.set(self.target_type, county_score.annotate(target, agg))
        ctx.join_log.append(self.name)


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
