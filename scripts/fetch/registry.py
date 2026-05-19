"""Source registry — single point of import for every DataSource.

Adding a new source = add a line below. The UI and the puller both call
``all_sources()`` and never touch the source modules directly.
"""

from __future__ import annotations

from .base import CATEGORY_ORDER, DataSource
from .sources.arc_distressed import SOURCE as ARC

# Solar
from .sources.eia_860 import SOURCE as EIA_860
from .sources.eia_860m import SOURCE as EIA_860M
from .sources.faa_oeaaa import SOURCE as FAA_OEAAA

# Towers
from .sources.fcc_asr import SOURCE as FCC_ASR
from .sources.fcc_uls import SOURCES as FCC_ULS_BANDS
from .sources.fcc_uls_meta import SOURCES as FCC_ULS_META

# Billboards
from .sources.fdot_billboards import SOURCE as FDOT_BILLBOARDS
from .sources.fl_fgdl_parcels import SOURCE as FL_PARCELS
from .sources.hifld_towers import SOURCE as HIFLD_TOWERS

# Distress
from .sources.hud_oz import SOURCE as HUD_OZ
from .sources.hud_qct import SOURCE as HUD_QCT
from .sources.lbnl_tts import SOURCE as LBNL_TTS

# Parcels
from .sources.nc_onemap_parcels import SOURCE as NC_PARCELS
from .sources.ncdot_billboards import SOURCE as NCDOT_BILLBOARDS
from .sources.regrid_parcels import SOURCE as REGRID
from .sources.state_parcels import SOURCES as STATE_PARCELS_MANUAL
from .sources.txdot_billboards import SOURCE as TXDOT_BILLBOARDS
from .sources.usda_persistent_poverty import SOURCE as USDA_PP
from .sources.uspvdb import SOURCE as USPVDB

_ALL: list[DataSource] = [
    FCC_ASR,
    *FCC_ULS_BANDS,
    *FCC_ULS_META,
    FAA_OEAAA,
    HIFLD_TOWERS,
    EIA_860,
    EIA_860M,
    USPVDB,
    LBNL_TTS,
    FDOT_BILLBOARDS,
    NCDOT_BILLBOARDS,
    TXDOT_BILLBOARDS,
    NC_PARCELS,
    FL_PARCELS,
    *STATE_PARCELS_MANUAL,
    REGRID,
    HUD_OZ,
    HUD_QCT,
    ARC,
    USDA_PP,
]

# Sanity: no duplicate IDs
_seen: set[str] = set()
for s in _ALL:
    if s.id in _seen:
        raise RuntimeError(f"duplicate source id in registry: {s.id}")
    _seen.add(s.id)


def all_sources() -> list[DataSource]:
    """Return every registered DataSource, ordered by category then name."""
    by_cat = {cat: [] for cat in CATEGORY_ORDER}
    for s in _ALL:
        by_cat.setdefault(s.category, []).append(s)
    ordered: list[DataSource] = []
    for cat in CATEGORY_ORDER:
        ordered.extend(sorted(by_cat.get(cat, []), key=lambda s: s.name.lower()))
    # Append any unknown categories (defensive)
    for cat, sources in by_cat.items():
        if cat not in CATEGORY_ORDER:
            ordered.extend(sorted(sources, key=lambda s: s.name.lower()))
    return ordered


def get_source(source_id: str) -> DataSource:
    for s in _ALL:
        if s.id == source_id:
            return s
    raise KeyError(f"no such source: {source_id}")


def grouped() -> dict[str, list[DataSource]]:
    """Return {category: [sources]} in display order."""
    out: dict[str, list[DataSource]] = {cat: [] for cat in CATEGORY_ORDER}
    for s in all_sources():
        out.setdefault(s.category, []).append(s)
    return out
