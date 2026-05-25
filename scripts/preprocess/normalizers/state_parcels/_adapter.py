"""ParcelAdapter — the per-source description that lets the shared parcel
driver normalize one upstream parcel feed into canonical ``parcel`` rows.

One ``ParcelAdapter`` per ``source_id`` (so FL has two: ``fl_fgdl_parcels``
and ``fdor_nal``). The driver in :mod:`._driver` takes an adapter as its
only state-specific input — there are no source_id-keyed lookups.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...base import Normalizer, NormalizeResult

if TYPE_CHECKING:
    import geopandas as gpd

# Type aliases that the dataclass fields use.
CountyResolver = Callable[[str], "str | None"]
PostMap = Callable[["gpd.GeoDataFrame"], "gpd.GeoDataFrame"]


@dataclass(frozen=True)
class ParcelAdapter:
    """Per-source description for the shared parcel-normalize driver.

    Attributes:
        source_id: The fetch-side ``DataSource.id`` this adapter describes.
        state_fips: Two-digit state FIPS hint, used when the raw county
            column doesn't carry the state prefix (e.g. MT has only county
            names; AR has a 3-digit county code).
        field_map: Canonical-name → list of candidate raw column names;
            first match wins. See ``_driver._map_layer_to_canonical`` for
            the canonical-field vocabulary.
        county_resolver: Optional callable taking a raw county value and
            returning a 5-digit county FIPS (or None if it can't resolve).
            Used when the raw field is a county *name* rather than a FIPS
            (e.g. MT Cadastral's ``CountyName``). When None, the driver
            falls back to ``canon_county_fips``.
        post_map: Optional escape hatch — runs after the default
            canonical mapping. Receives the canonical GeoDataFrame and
            returns the (possibly mutated) GeoDataFrame. Reserve for
            quirks that can't be expressed via ``field_map`` alone.
    """

    source_id: str
    state_fips: str
    field_map: dict[str, list[str]]
    county_resolver: CountyResolver | None = None
    post_map: PostMap | None = None


class ParcelNormalizer(Normalizer):
    """Concrete Normalizer that delegates to the shared parcel driver.

    One instance per ParcelAdapter — registered via
    ``register_normalizer_instance(ParcelNormalizer(ADAPTER))``.
    """

    canonical_types = ["parcel"]

    def __init__(self, adapter: ParcelAdapter) -> None:
        self.adapter = adapter
        self.source_id = adapter.source_id

    def normalize(self, raw_dir: Path, out_dir: Path) -> NormalizeResult:
        # Local import keeps _adapter.py free of the geopandas/pyogrio
        # import cost when the registry is loaded without running normalize.
        from ._driver import normalize_state_parcels

        return normalize_state_parcels(raw_dir, out_dir, self.adapter)
