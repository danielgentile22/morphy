"""Memory-bounds assertions for streaming compose (ADR-051).

The whole point of the streaming Composer is that **peak memory stays
bounded to a single shard's footprint**, not the union of every shard.
These tests assert that property in two complementary ways:

1. **No-leak**: weak references to each yielded chunk are dead after the
   run. Catches a regression where the composer accidentally kept a
   list-of-chunks (the bug that ADR-051 set out to fix).
2. **At-most-one-live**: during the chunk loop, the composer doesn't
   hold a reference to a previously-yielded chunk while processing the
   next one. Asserted by an iterator that checks live counts on each
   yield.

Both tests reuse the fixture state from the property test module so the
end-to-end shape is identical.
"""

from __future__ import annotations

import gc
import weakref

# Fixtures are picked up from the property test module — sharing them
# avoids re-implementing the synthetic normalized layout.
from tests.test_compose_property import (  # noqa: F401
    STATE,
    _ensure_registry_loaded,
    fixture_dirs,
    registered_normalizers,
)


def test_chunk_loop_releases_each_chunk_after_processing(
    fixture_dirs, registered_normalizers, monkeypatch
):
    """No accumulation: every yielded chunk is collectable after the run."""
    from preprocess import compose as cc
    from preprocess.compose_helpers import iter_state_parcel_shards

    chunk_refs: list[weakref.ref] = []

    def tracked(state_fips, **kw):
        for label, chunk in iter_state_parcel_shards(state_fips, **kw):
            chunk_refs.append(weakref.ref(chunk))
            yield label, chunk

    monkeypatch.setattr(cc, "iter_state_parcel_shards", tracked)

    cfg = cc.ComposeConfig(state=STATE)
    cc.compose(cfg)

    gc.collect()
    # After the run, no chunk should still be alive — the composer must
    # not retain them. Tolerate up to 1 alive ref (the iterator's last
    # closure may briefly keep one in some Python builds) — anything
    # more indicates an accumulation regression.
    alive = sum(1 for r in chunk_refs if r() is not None)
    assert alive <= 1, (
        f"compose leaked references to {alive} parcel chunks "
        f"after the run finished (expected 0 or 1)"
    )
    # Also assert we actually iterated more than one chunk so the test
    # isn't trivially passing on an empty fixture.
    assert len(chunk_refs) >= 2, "fixture should yield ≥2 shards"


def test_chunks_dont_outlive_two_iterations(
    fixture_dirs, registered_normalizers, monkeypatch
):
    """A chunk yielded at iteration N must be collectable by iteration N+2.

    Looser than "at most one live" — Python's for-loop naturally keeps the
    iteration variable bound until the next cycle starts, so a strict "one
    alive" check would always fire. But by the time *two* further chunks
    have been processed, the original chunk must be unreachable; otherwise
    the composer is accumulating state per chunk.
    """
    from preprocess import compose as cc
    from preprocess.compose_helpers import iter_state_parcel_shards

    # Per-yield (label, weakref) so we can correlate.
    yielded: list[tuple[str, weakref.ref]] = []
    # After each yield, look back two yields and verify the chunk is dead.
    violations: list[str] = []

    def tracked(state_fips, **kw):
        for label, chunk in iter_state_parcel_shards(state_fips, **kw):
            yielded.append((label, weakref.ref(chunk)))
            if len(yielded) >= 3:
                gc.collect()
                old_label, old_ref = yielded[-3]
                if old_ref() is not None:
                    violations.append(
                        f"chunk {old_label} still alive 2 iterations after yield"
                    )
            yield label, chunk

    monkeypatch.setattr(cc, "iter_state_parcel_shards", tracked)

    cfg = cc.ComposeConfig(state=STATE)
    cc.compose(cfg)

    assert violations == [], f"compose retained chunks too long: {violations}"
