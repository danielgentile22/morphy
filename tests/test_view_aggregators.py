"""Structural guards for View-owned aggregation (#266).

Each parcel View owns its streaming aggregation via ``make_aggregator``;
the aggregator_for_view name-switch ladder and the dead ``build()``
bodies are gone. These tests pin the seam's contract: every parcel view
streams, aggregators are fresh per compose (multi-state isolation), and
a view must supply exactly one implementation.
"""

from __future__ import annotations

import preprocess.registry  # noqa: F401 — populate the registries
import pytest
from preprocess.base import _VIEW_REGISTRY, View, all_views, register_view


def test_every_parcel_view_streams():
    # Under the chunked composer a parcel view without an aggregator is
    # silently skipped (warn path) — a registered parcel view must stream.
    parcel_views = [v for v in all_views() if "parcel" in v.inputs]
    assert parcel_views, "no parcel views registered"
    for v in parcel_views:
        agg = v.make_aggregator()
        assert agg is not None, f"parcel view {v.name} has no streaming aggregator"
        assert agg.name == v.name


def test_non_parcel_views_build_post_loop():
    non_parcel = [v for v in all_views() if "parcel" not in v.inputs]
    assert [v.name for v in non_parcel] == ["towers_with_landowner"]
    assert non_parcel[0].make_aggregator() is None


def test_aggregators_are_fresh_per_call():
    # The composer calls make_aggregator once per state; a shared instance
    # would bleed one state's accumulated rows into the next state's output.
    for v in all_views():
        first = v.make_aggregator()
        if first is None:
            continue
        assert first is not v.make_aggregator(), f"{v.name} reuses its aggregator instance"


def test_register_view_requires_one_implementation():
    class NeitherView(View):
        name = "neither_view_test"
        inputs = ["parcel"]

    with pytest.raises(ValueError, match="must override build or make_aggregator"):
        register_view(NeitherView)
    assert "neither_view_test" not in _VIEW_REGISTRY
