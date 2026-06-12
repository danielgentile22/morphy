"""Owner clustering: group parcels by normalized owner+address.

Annotates each parcel with owner_cluster_id, owner_cluster_size,
owner_cluster_value_total. Cluster id is a sha1 hash of the
(normalized_owner, normalized_addr) pair — stable across runs.

This is the concept's single deep implementation. Two parts behind one
seam, because cluster size/value are whole-state group aggregates a
single county chunk can't compute alone:

  - :func:`prepare` consumes an *iterable* of frames carrying owner
    columns and returns the owner_cluster_id-keyed aggregate. The
    Composer's DuckDB pre-pass (PRD #135) passes only the rows needing
    the Python re-normalization fallback; a whole-layer caller passes
    ``[parcels]``.
  - :func:`annotate` computes the per-row cluster_id on the frame itself
    and maps size/value from that aggregate.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from ..cluster import cluster_id, normalized_owner_cols

# Columns :func:`prepare` reads. Geometry is never needed, so the streaming
# feed projects to these and keeps the pre-pass tiny (~tens of MB even for
# an 11 M-parcel state, vs the full layer).
OWNER_COLS = [
    "owner_name_norm",
    "mailing_addr_norm",
    "owner_name",
    "mailing_addr",
    "assessed_value",
]

_EMPTY_LOOKUP = pd.DataFrame(
    columns=["owner_cluster_size", "owner_cluster_value_total"],
    index=pd.Index([], name="owner_cluster_id"),
)


def row_cluster_ids(df) -> list[str]:
    """Per-row owner_cluster_id (the within-state grain) for a frame carrying
    owner columns.

    Owner identity — the normalize → hash recipe and the "prefer the
    precomputed ``*_norm`` column, else re-normalize the raw column" fallback —
    is the primitive in :mod:`preprocess.cluster`. This just zips the
    within-state key (``cluster_id``: name + address) over the columns that
    helper returns, so a shard whose source skipped normalization still
    resolves and the recipe lives in exactly one place.
    """
    owner_norm, addr_norm = normalized_owner_cols(df)
    return [cluster_id(o, a) for o, a in zip(owner_norm, addr_norm)]


def prepare(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Build the owner_cluster_id → (size, value_total) aggregate.

    Returns a DataFrame indexed by ``owner_cluster_id`` — always unique,
    so it's safe to ``.map`` against even when parcel_id_full duplicates
    across shards (the FL FDOR NAL case, where PARCEL_ID is county-unique
    not state-unique). Parcels with no clusterable owner/address
    (cluster_id == "") are excluded from the aggregate and default to
    size 1 / value 0 at annotate time.

    Consumes the iterable one frame at a time, accumulating only the
    per-frame (cluster_id, value) projection — so a generator of shards
    keeps peak memory bounded to one shard.
    """
    rows: list[pd.DataFrame] = []
    for df in frames:
        rows.append(
            pd.DataFrame(
                {
                    "owner_cluster_id": row_cluster_ids(df),
                    "assessed_value": pd.to_numeric(
                        df.get("assessed_value", 0), errors="coerce"
                    ).fillna(0.0),
                }
            )
        )
    if not rows:
        return _EMPTY_LOOKUP.copy()
    allp = pd.concat(rows, ignore_index=True)
    non_empty = allp[allp["owner_cluster_id"] != ""]
    if len(non_empty) == 0:
        return _EMPTY_LOOKUP.copy()
    agg = non_empty.groupby("owner_cluster_id").agg(
        owner_cluster_size=("owner_cluster_id", "size"),
        owner_cluster_value_total=("assessed_value", "sum"),
    )
    agg["owner_cluster_size"] = agg["owner_cluster_size"].astype(int)
    agg["owner_cluster_value_total"] = agg["owner_cluster_value_total"].astype(float)
    return agg  # index = owner_cluster_id (unique)


def annotate(parcels, lookup: pd.DataFrame):
    """Add owner_cluster_id / _size / _value_total to a parcel frame.

    Per-row cluster_id is recomputed on ``parcels`` itself; size + value
    are mapped from the aggregate ``lookup`` (built by :func:`prepare`).
    Direct column assignment overwrites the normalizer's placeholder
    columns cleanly — no merge, so no ``_x``/``_y`` suffix trap (ADR-020).
    A parcel with no aggregate match (incl. empty cluster id) is a
    cluster of one (size 1, value 0).
    """
    parcels = parcels.copy()
    parcels["owner_cluster_id"] = row_cluster_ids(parcels)
    if lookup is not None and len(lookup) > 0:
        size = parcels["owner_cluster_id"].map(lookup["owner_cluster_size"])
        value = parcels["owner_cluster_id"].map(lookup["owner_cluster_value_total"])
    else:
        size = pd.Series([pd.NA] * len(parcels), index=parcels.index)
        value = pd.Series([pd.NA] * len(parcels), index=parcels.index)
    parcels["owner_cluster_size"] = size.fillna(1).astype(int)
    parcels["owner_cluster_value_total"] = value.fillna(0).astype(float)
    return parcels
