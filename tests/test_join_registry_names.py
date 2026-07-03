"""Structural guards for the Join registry (#263, restores ADR-002).

Ghost join names — manifest strings with no adapter behind them — are
killed structurally: whatever compose writes into ``joins_applied`` must
be a registered adapter, and the chunked parcel stages must come out of
the ordered registry in the exact sequence the byte-identical compose
contract pins (output column order follows chunk-stage order).
"""

from __future__ import annotations

import json

import preprocess.registry  # noqa: F401 — populate the registries
from preprocess.base import all_joins, ordered_joins

from tests.test_compose_property import (  # noqa: F401 — fixtures
    STATE,
    fixture_dirs,
    registered_normalizers,
)


def test_chunked_join_order_is_pinned():
    # The chunk-stage sequence IS the parcel output column order — part of
    # the byte-identical compose contract. depends_on encodes it; a change
    # here must be a deliberate output-format decision.
    chunked = [j.name for j in ordered_joins() if j.chunked]
    assert chunked == [
        "ParcelHostsInfraJoin",
        "CountyScoreToParcelJoin",
        "ParcelToDistressJoin",
        "OwnerClusterJoin",
        "InterestingnessScoreJoin",
    ]


def test_dependency_ordering_is_live():
    # The toposort is exercised by real edges: interestingness reads the
    # columns every other chunk stage writes, so it must sort last of the
    # chunked joins even though it registers before some whole-layer ones.
    order = [j.name for j in ordered_joins()]
    interest = order.index("InterestingnessScoreJoin")
    for dep in (
        "ParcelHostsInfraJoin",
        "CountyScoreToParcelJoin",
        "ParcelToDistressJoin",
        "OwnerClusterJoin",
    ):
        assert order.index(dep) < interest


def test_manifest_join_names_are_registered(fixture_dirs, registered_normalizers, tmp_path):
    # Run a real compose over the property-test fixtures, then check that
    # every name it wrote to summary.json corresponds to a registered
    # adapter — a ghost name can no longer reach the manifest.
    from preprocess.compose import ComposeConfig, compose

    result = compose(ComposeConfig(state=STATE))
    summary_path = fixture_dirs["composite"] / STATE.fips / "summary.json"
    summary = json.loads(summary_path.read_text())
    registered = {j.name for j in all_joins()}
    applied = set(summary["joins_applied"])
    assert applied, "compose recorded no joins"
    assert applied <= registered, f"ghost join names in manifest: {applied - registered}"
    assert set(result.joins_applied) <= registered
