"""Import every Normalizer / Join / View so they self-register.

Single point of import for the CLI and the UI worker. Adding a new
source / join / view = import its module here.
"""

# Normalizers
from .normalizers import (
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

# Joins
from .joins import (
    geometry_derivatives,
    tower_to_parcel,
    tower_to_distress,
    parcel_to_distress,
    parcel_hosts_infra,
    solar_to_parcel,
    billboard_to_parcel,
    county_score_to_parcel,
    county_score_to_tower,
    county_score_to_solar,
    owner_cluster,
    interestingness_score,
)

# Views
from .views import (
    towers_with_landowner,
    parcels_hosting_infra,
    llc_owned_parcels_with_infra,
    distressed_parcels_hosting_infra,
    owner_clusters,
    county_summary,
    state_summary,
    interestingness_top_1000,
)
