"""Parcel/infra annotation bodies — one deep implementation per concept.

Each module here owns the single computation for one annotation, behind a
``prepare`` / ``annotate`` seam where a cross-chunk aggregate exists:

  - ``prepare(global_inputs) -> state`` — the part that needs a whole-state
    (or whole-layer) view: cluster sizes, the county-score rollup. Cheap and
    chunk-local concepts omit it.
  - ``annotate(target, state) -> target`` — the per-row / per-table body.

Two feeds drive the same body. The streaming Composer runs ``prepare`` once
in a pre-pass and ``annotate`` per county shard (parcels — ADR-050 keeps peak
memory to one shard). The registered parametric Joins (tower / solar targets)
call ``annotate`` on the whole in-memory layer. There is no second
implementation to drift against: the registered Joins (whole-layer via
``apply``, chunked via ``prepare_chunks``/``apply_chunk`` — #263) are thin
feed adapters over these modules.
"""
