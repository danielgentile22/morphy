"""Source registry — single point of import for every DataSource.

The puller and preprocess pipeline both call ``all_sources()`` and never
touch source modules directly.

Sources are split into two blocks:

* **Active** — `_ACTIVE`. These appear in the puller UI, are checked
  on "Check for updates", and feed the v1-pitch preprocess pipeline.

* **Deferred** — `_DEFERRED`. Imported (so the classes still exist and
  manual reactivation is a one-line move) but NOT shown in the puller
  or normalized. Deferred sources are documented in
  [docs/DECISIONS.md](../../docs/DECISIONS.md) and
  [docs/DATA_SOURCES.md](../../docs/DATA_SOURCES.md). To reactivate
  one, move it from `_DEFERRED` into `_ACTIVE`.

Adding a new source = add a line to `_ACTIVE` (or `_DEFERRED` if it's
not in v1 scope).
"""

from __future__ import annotations

from .base import CATEGORY_ORDER, DataSource
from .sources.arc_distressed import SOURCE as ARC

# Solar
from .sources.eia_860 import SOURCE as EIA_860
from .sources.eia_860m import SOURCE as EIA_860M
from .sources.faa_oeaaa import SOURCE as FAA_OEAAA

# Towers (active)
from .sources.fcc_asr import SOURCE as FCC_ASR

# Towers — FCC ULS bulk files. Cellular (l_cell) + Market-Based (l_market; the
# PCS/AWS/700 subset) are Phase 1 Slice A (ADR-053 partially reverses ADR-013);
# Microwave + the cross-service ownership/transfers/leasing files stay deferred.
# Split into active/deferred below.
from .sources.fcc_uls import SOURCES as FCC_ULS_ALL

# FL parcels — `fl_fgdl_parcels` is deferred (wrong dataset for landowner work);
# replaced by `fdor_nal`.
from .sources.fdor_nal import SOURCE as FDOR_NAL

# Billboards (all deferred for v1 — not core to cell-tower thesis)
from .sources.fdot_billboards import SOURCE as FDOT_BILLBOARDS
from .sources.fl_fgdl_parcels import SOURCE as FL_FGDL_PARCELS

# Distress overlays (active)
from .sources.hud_oz import SOURCE as HUD_OZ
from .sources.hud_qct import SOURCE as HUD_QCT
from .sources.lbnl_tts import SOURCE as LBNL_TTS

# Parcels (active)
from .sources.nc_onemap_parcels import SOURCE as NC_PARCELS
from .sources.ncdot_billboards import SOURCE as NCDOT_BILLBOARDS
from .sources.regrid_parcels import SOURCE as REGRID
from .sources.state_parcels import (
    DEFERRED_SOURCES as STATE_PARCELS_DEFERRED,
)
from .sources.state_parcels import (
    SOURCES as STATE_PARCELS_ACTIVE,
)
from .sources.txdot_billboards import SOURCE as TXDOT_BILLBOARDS
from .sources.usda_persistent_poverty import SOURCE as USDA_PP
from .sources.uspvdb import SOURCE as USPVDB

# FCC ULS Phase-1 split: the two bands we now normalize (Slice A, #12) go
# active; Microwave + ownership/transfers/leasing stay deferred.
FCC_ULS_ACTIVE = [s for s in FCC_ULS_ALL if s.id in ("fcc_uls_cellular", "fcc_uls_market")]
FCC_ULS_DEFERRED = [s for s in FCC_ULS_ALL if s.id not in ("fcc_uls_cellular", "fcc_uls_market")]

# ── active sources (v1 pitch scope) ──────────────────────────────────────
_ACTIVE: list[DataSource] = [
    # Towers
    FCC_ASR,
    FAA_OEAAA,
    *FCC_ULS_ACTIVE,  # FCC ULS Cellular + Market-Based (PCS/AWS/700) — Slice A
    # Solar
    EIA_860,
    EIA_860M,
    USPVDB,
    # Parcels — anchor states
    NC_PARCELS,
    FDOR_NAL,
    *STATE_PARCELS_ACTIVE,  # MT + AR + WV
    # Distress overlays
    HUD_OZ,
    HUD_QCT,
    ARC,
    USDA_PP,
]

# ── deferred sources (out of v1 pitch scope) ─────────────────────────────
# These are imported above so classes stay accessible, but are NOT exposed
# to the puller or preprocess pipeline. See docs/DECISIONS.md for the
# rationale behind each deferral. To reactivate, move into _ACTIVE.
_DEFERRED: list[DataSource] = [
    # FCC ULS — Microwave (point-to-point backhaul) + the cross-service
    # ownership / transfers / leasing files. Cellular + Market-Based moved to
    # _ACTIVE for Slice A (ADR-053 partially reverses ADR-013).
    *FCC_ULS_DEFERRED,
    # LBNL Tracking the Sun — superseded by USPVDB + EIA 860 for our purposes.
    LBNL_TTS,
    # State billboard datasets — not core to the cell-tower thesis.
    FDOT_BILLBOARDS,
    NCDOT_BILLBOARDS,
    TXDOT_BILLBOARDS,
    # FL FGDL DSL — state-land parcels (wrong dataset for landowner work).
    # Replaced in active block by fdor_nal.
    FL_FGDL_PARCELS,
    # MN + IN parcels — MN license ambiguous; IN public parcels have no
    # owner_name column.
    *STATE_PARCELS_DEFERRED,
    # Regrid — paid; free-only budget for v1.
    REGRID,
]

# Sanity: no duplicate IDs across active OR deferred (since the user can
# move sources between blocks; never let two define the same id).
_seen: set[str] = set()
for s in (*_ACTIVE, *_DEFERRED):
    if s.id in _seen:
        raise RuntimeError(f"duplicate source id in registry: {s.id}")
    _seen.add(s.id)


def all_sources() -> list[DataSource]:
    """Return every active DataSource, ordered by category then name."""
    by_cat = {cat: [] for cat in CATEGORY_ORDER}
    for s in _ACTIVE:
        by_cat.setdefault(s.category, []).append(s)
    ordered: list[DataSource] = []
    for cat in CATEGORY_ORDER:
        ordered.extend(sorted(by_cat.get(cat, []), key=lambda s: s.name.lower()))
    # Append any unknown categories (defensive)
    for cat, sources in by_cat.items():
        if cat not in CATEGORY_ORDER:
            ordered.extend(sorted(sources, key=lambda s: s.name.lower()))
    return ordered


def deferred_sources() -> list[DataSource]:
    """Return the deferred (parked) sources, ordered by name."""
    return sorted(_DEFERRED, key=lambda s: s.name.lower())


def get_source(source_id: str) -> DataSource:
    """Look up by ID across both active AND deferred blocks.

    Deferred sources are still resolvable so tooling (verify, normalize,
    diagnose) keeps working if the user reactivates one mid-session.
    """
    for s in (*_ACTIVE, *_DEFERRED):
        if s.id == source_id:
            return s
    raise KeyError(f"no such source: {source_id}")


def grouped() -> dict[str, list[DataSource]]:
    """Return {category: [sources]} in display order, active sources only."""
    out: dict[str, list[DataSource]] = {cat: [] for cat in CATEGORY_ORDER}
    for s in all_sources():
        out.setdefault(s.category, []).append(s)
    return out
