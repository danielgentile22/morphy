"""Parametric Join: copy aggregated county_score columns onto any target.

Registers one instance per target type (parcel / tower / solar_facility);
the body is a thin feed over the shared county-score annotator
(``preprocess.annotators.county_score``). The parcel instance runs
*chunked* (ADR-051): the Composer drives it per parcel shard, with the
rollup hoisted once in ``prepare_chunks`` (PERF-021). The tower / solar
instances run whole-layer via ``apply``. One computation, two feeds — no
twin to drift.
"""

from __future__ import annotations

from ..annotators import county_score
from ..base import ComposeContext, Join, register_join_instance


class CountyScoreLookupJoin(Join):
    """Annotate `target_type` with the per-county distress_tier +
    persistent_poverty rolled up from ARC + USDA county_score sources.
    """

    columns_added = county_score.COLUMNS_ADDED

    def __init__(
        self,
        target_type: str,
        name: str | None = None,
        depends_on: list[str] | None = None,
    ):
        self.target_type = target_type
        # Default naming mirrors the previous classes (CountyScoreToParcelJoin
        # etc.) so existing logs / manifests stay readable. Callers can pass
        # `name` explicitly to pin a legacy name (e.g. "CountyScoreToSolarJoin"
        # for solar_facility, where the underscore would otherwise expand).
        title = "".join(part.capitalize() for part in target_type.split("_"))
        self.name = name or f"CountyScoreTo{title}Join"
        self.inputs = [target_type, "county_score"]
        self.annotates = target_type
        self.chunked = target_type == "parcel"
        self.depends_on = list(depends_on or [])
        self._prepared = None

    # ── whole-layer feed (tower / solar) ──────────────────────────────────
    def apply(self, ctx: ComposeContext) -> None:
        target = ctx.get(self.target_type)
        agg = county_score.prepare(ctx.get("county_score"))
        if target is None or agg is None:
            return
        ctx.set(self.target_type, county_score.annotate(target, agg))
        ctx.join_log.append(self.name)

    # ── chunked feed (parcel, ADR-051) ────────────────────────────────────
    def is_applicable(self, ctx: ComposeContext) -> bool:
        if self.chunked:
            # Parcels are streamed, never in ctx; the annotator no-ops on a
            # missing rollup, matching the pre-registry chunk loop exactly.
            return True
        return super().is_applicable(ctx)

    def prepare_chunks(self, ctx: ComposeContext) -> None:
        # Hoisted out of the shard loop (PERF-021): one groupby over the
        # small, chunk-independent county_score table.
        self._prepared = county_score.prepare(ctx.get("county_score"))

    def apply_chunk(self, chunk):
        return county_score.annotate(chunk, self._prepared)

    def release_chunks(self) -> None:
        self._prepared = None


# Target types to register at import time. Solar pins the legacy name
# (the old class was CountyScoreToSolarJoin, no "Facility") so existing
# manifest entries / logs stay continuous. depends_on pins each instance's
# position: parcel after the hosts-infra columns; tower/solar after their
# parcel_* columns from the infra→parcel joins — output column order is
# part of the byte-identical compose contract.
_REGISTRATIONS: tuple[tuple[str, str | None, list[str] | None], ...] = (
    ("parcel", None, ["ParcelHostsInfraJoin"]),
    ("tower", None, ["TowerToParcelJoin"]),
    ("solar_facility", "CountyScoreToSolarJoin", ["SolarToParcelJoin"]),
)

for _target, _name, _deps in _REGISTRATIONS:
    register_join_instance(CountyScoreLookupJoin(_target, name=_name, depends_on=_deps))
