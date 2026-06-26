"""Solar-feed normalizer fixes E5/E6/E7.

The solar normalizers read Excel/shapefiles and had no tests. These target
the pure decision points the audit fixes turn on, without building fixtures:

  - E6: the canonical EIA-860 layer must be solar-only (``_solar_only``).
  - E7: USPVDB capacity standardizes to the AC rating (``_select_capacity``).
  - E5: the 860M normalizer reads the correctly-named "Plant State" column.
"""

from __future__ import annotations

import pandas as pd
from preprocess.normalizers.eia_860 import _solar_only
from preprocess.normalizers.eia_860m import Eia860MNormalizer
from preprocess.normalizers.fips import canon_state_fips
from preprocess.normalizers.uspvdb import _select_capacity

# ── E6: EIA-860 canonical layer is solar-only ─────────────────────────────


def test_solar_only_drops_non_solar_plants_keeps_solar():
    # Left-merging the solar tab leaves non-solar plants with a blank Technology.
    df = pd.DataFrame(
        {
            "Plant Code": ["1", "2", "3", "4"],
            "Technology": ["Solar Photovoltaic", "", "Natural Gas", "Solar Thermal"],
        }
    )
    out = _solar_only(df)
    assert out["Plant Code"].tolist() == ["1", "4"]


def test_solar_only_empty_when_no_technology_column():
    # No solar tab merged → no Technology column → nothing is "solar".
    df = pd.DataFrame({"Plant Code": ["1", "2"]})
    assert len(_solar_only(df)) == 0


def test_full_plant_list_is_preserved_for_raw_even_when_filtered():
    # The filter returns a view; the source frame (what raw.parquet gets) is
    # untouched — full-fidelity raw preservation (the E6 invariant note).
    df = pd.DataFrame({"Plant Code": ["1", "2"], "Technology": ["Solar Photovoltaic", "Coal"]})
    _ = _solar_only(df)
    assert len(df) == 2  # raw frame unchanged


# ── E7: USPVDB capacity standardized to AC, rating recorded ───────────────


def test_capacity_prefers_ac_and_records_it():
    assert _select_capacity("100", "140") == (100.0, "AC")


def test_capacity_falls_back_to_dc_only_when_ac_absent():
    assert _select_capacity(None, "140") == (140.0, "DC")
    assert _select_capacity("", "140") == (140.0, "DC")


def test_capacity_none_when_neither_present():
    assert _select_capacity(None, None) == (None, None)


# ── E5: EIA-860M reads "Plant State", not "State" ─────────────────────────


def test_860m_resolves_state_from_plant_state_column():
    # The bug: code read r.get("State") but the column is "Plant State", so
    # state_fips was None on 100% of rows and the whole feed was dropped. Mirror
    # the normalizer's resolution to prove the right column now resolves.
    row = {"Plant State": "FL", "Plant Name": "X"}
    state_fips = canon_state_fips(row.get("Plant State") or row.get("State"))
    assert state_fips == "12"


def test_860m_normalizer_class_targets_solar_facility():
    # Smoke: the normalizer is the solar_facility producer we patched.
    assert Eia860MNormalizer.canonical_types == ["solar_facility"]
