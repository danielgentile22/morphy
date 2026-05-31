"""County-distress annotation: roll county_score up, copy onto a target.

Single deep implementation for the distress_tier + persistent_poverty
columns. Used two ways: the registered :class:`CountyScoreLookupJoin`
annotates the whole tower / solar layer in memory; the streaming
Composer annotates each parcel chunk. One body, two feeds.

  - :func:`prepare` collapses multi-source (ARC + USDA) county_score rows
    into one row per county_fips. Cheap and chunk-local (county_score is a
    small table), so a caller may hoist it once or call it per chunk —
    the result is identical.
  - :func:`annotate` copies the rolled-up columns onto any target keyed
    by county_fips.
"""

from __future__ import annotations

from ..base import safe_merge

COLUMNS_ADDED = ["distress_tier", "persistent_poverty"]


def prepare(scores):
    """Collapse multi-source county_score rows into one row per FIPS.

    First non-empty tier wins; persistent_poverty is OR-ed across the
    contributing sources. Returns ``None`` when there's nothing to roll
    up (the caller treats that as a no-op).
    """
    if scores is None or len(scores) == 0:
        return None
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


def annotate(target, agg):
    """Copy distress_tier + persistent_poverty onto ``target`` via county_fips.

    ``agg`` is the output of :func:`prepare`. No-op (returns ``target``
    unchanged, same object) when there's no aggregate. safe_merge drops
    the normalizer's placeholder columns first so the merge populates
    fresh values without the ``_x``/``_y`` suffix trap (ADR-020); the
    fillna restores per-column defaults ("" tier, False flag).
    """
    if target is None or agg is None or len(agg) == 0:
        return target
    merged = safe_merge(target, agg, on="county_fips", columns_added=COLUMNS_ADDED)
    merged["distress_tier"] = merged["distress_tier"].fillna("")
    merged["persistent_poverty"] = merged["persistent_poverty"].fillna(False)
    return merged
