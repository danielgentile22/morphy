"""Per-source ParcelAdapter constants.

Each adapter module imports ``ParcelAdapter`` from ``..state_parcels``, and
``state_parcels`` in turn imports + registers every adapter at the bottom of
its module body. Importing an adapter module *as the entry point* therefore
trips a circular import (adapter → state_parcels → adapter-still-initializing).

Importing ``state_parcels`` here, at package load, forces the parent module to
initialize fully (defining ``ParcelAdapter``/``AttributeJoin`` and running the
registration block) before any adapter submodule executes — so adapters can be
imported standalone (e.g. ``pytest tests/test_parcel_adapter.py`` in isolation).
"""

from .. import state_parcels  # noqa: F401  (imported for its initialization side effect)
