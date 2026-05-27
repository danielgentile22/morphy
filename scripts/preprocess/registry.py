"""Import every Normalizer / Join / View so they self-register.

Single point of import for the CLI and the UI worker. Adding a new
source / join / view = import its module here.

Each imported module runs its ``@register_normalizer`` /
``@register_join`` / ``@register_view`` decorators at import time,
populating the registries in ``preprocess.base``. Without this module
being imported, ``all_normalizers()`` / ``all_joins()`` / ``all_views()``
return empty and the whole pipeline is a no-op.
"""

# ── Normalizers ───────────────────────────────────────────────────────
from .normalizers import (  # noqa: F401
    arc_distressed,
    eia_860,
    eia_860m,
    faa_oeaaa,
    fcc_asr,
    hifld_towers,
    hud_overlays,
    state_billboards,
    state_parcels,
    usda_persistent_poverty,
    uspvdb,
)

# ── Joins ─────────────────────────────────────────────────────────────
from .joins import (  # noqa: F401
    county_score_lookup,
    infra_to_parcel,
    interestingness_score,
    owner_cluster,
    parcel_hosts_infra,
    spatial_attribute,
)

# ── Views ─────────────────────────────────────────────────────────────
from .views import (  # noqa: F401
    county_summary,
    distressed_parcels_hosting_infra,
    interestingness_top_1000,
    llc_owned_parcels_with_infra,
    owner_clusters,
    parcels_hosting_infra,
    state_summary,
    towers_with_landowner,
)
