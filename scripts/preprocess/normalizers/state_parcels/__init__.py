"""State-parcel normalizers.

Every state's parcel layer maps to the same canonical schema; only the
column names differ. Each upstream parcel feed gets its own
:class:`.ParcelAdapter` under ``adapters/``, and the shared driver
:func:`._driver.normalize_state_parcels` does the actual work.

Importing this package triggers ``register_normalizer_instance`` for
every adapter, so the rest of the pipeline (Composer, CLI, UI) sees one
Normalizer per ``source_id`` just as before.

Adding a new parcel source:

  1. Create ``adapters/<state>.py`` exporting one ``ParcelAdapter``
     constant. See ``adapters/ar.py`` for the minimal shape and
     ``adapters/mt.py`` for the optional ``county_resolver``.
  2. Import it here and pass it to ``_register``.
"""

from __future__ import annotations

from ...base import register_normalizer_instance
from ._adapter import ParcelAdapter, ParcelNormalizer
from .adapters.ar import AR_PARCELS_ADAPTER
from .adapters.fdor_nal import FDOR_NAL_ADAPTER
from .adapters.fl_fgdl import FL_FGDL_PARCELS_ADAPTER
from .adapters.mn import MN_PARCELS_ADAPTER
from .adapters.mt import MT_CADASTRAL_PARCELS_ADAPTER
from .adapters.nc import NC_ONEMAP_PARCELS_ADAPTER

__all__ = ["ParcelAdapter", "ParcelNormalizer"]


def _register(adapter: ParcelAdapter) -> ParcelNormalizer:
    return register_normalizer_instance(ParcelNormalizer(adapter))


_register(AR_PARCELS_ADAPTER)
_register(NC_ONEMAP_PARCELS_ADAPTER)
_register(MT_CADASTRAL_PARCELS_ADAPTER)
_register(FL_FGDL_PARCELS_ADAPTER)
_register(FDOR_NAL_ADAPTER)
_register(MN_PARCELS_ADAPTER)
