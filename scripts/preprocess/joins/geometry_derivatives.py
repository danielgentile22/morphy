"""Re-compute geometry derivatives after the state filter clips data.

Normalize-time derivatives are computed against the full source extent.
After per-state filtering, the simplified geometry is still valid (it's
just simpler than the original) so this is a no-op for now — it exists
as a registry slot so future versions can re-simplify with state-relative
tolerance, recompute H3 cells, etc.
"""

from __future__ import annotations

from ..base import ComposeContext, Join, register_join


@register_join
class GeometryDerivativesJoin(Join):
    name = "GeometryDerivativesJoin"
    inputs = ["parcel"]  # at least one geometric type
    annotates = "*"
    columns_added = []

    def apply(self, ctx: ComposeContext) -> None:
        ctx.join_log.append(self.name)

    def is_applicable(self, ctx: ComposeContext) -> bool:
        return True
