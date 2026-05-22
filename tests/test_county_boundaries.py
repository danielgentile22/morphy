"""Tests for scripts/preprocess/county_boundaries.py.

`collapse_county_scores` is tested on a fixture; `build_county_boundaries`
is tested against the real AR / MT county_scores (skipped if those
composites are not on disk) — the vendored Census file is always present.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from preprocess.county_boundaries import (
    COUNTY_SHAPEFILE,
    build_county_boundaries,
    collapse_county_scores,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMPOSITE = _REPO_ROOT / "data" / "processed" / "composite"


def test_collapse_county_scores_merges_two_rows_per_county() -> None:
    # Two counties, each with an arc_distressed row + a persistent_poverty row.
    raw = pd.DataFrame(
        [
            {
                "county_fips": "05001",
                "_source": "arc_distressed",
                "tier": "transitional",
                "arc_distressed": False,
                "arc_at_risk": False,
                "persistent_poverty": None,
            },
            {
                "county_fips": "05001",
                "_source": "usda_persistent_poverty",
                "tier": "",
                "arc_distressed": None,
                "arc_at_risk": None,
                "persistent_poverty": False,
            },
            {
                "county_fips": "05003",
                "_source": "arc_distressed",
                "tier": "distressed",
                "arc_distressed": True,
                "arc_at_risk": False,
                "persistent_poverty": None,
            },
            {
                "county_fips": "05003",
                "_source": "usda_persistent_poverty",
                "tier": "",
                "arc_distressed": None,
                "arc_at_risk": None,
                "persistent_poverty": True,
            },
        ]
    )
    collapsed = collapse_county_scores(raw)

    assert len(collapsed) == 2
    # Each field takes the populated value across the two source rows.
    assert collapsed.loc["05001", "tier"] == "transitional"
    assert not collapsed.loc["05001", "persistent_poverty"]
    assert collapsed.loc["05003", "tier"] == "distressed"
    assert collapsed.loc["05003", "arc_distressed"]
    assert collapsed.loc["05003", "persistent_poverty"]


def test_vendored_census_file_is_present() -> None:
    # The Census cartographic county file is a committed preprocess asset.
    assert COUNTY_SHAPEFILE.exists(), f"missing vendored Census file: {COUNTY_SHAPEFILE}"


def test_build_county_boundaries_missing_scores_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_county_boundaries("05", composite_root=tmp_path)


@pytest.mark.parametrize(("fips", "n_counties"), [("05", 75), ("30", 56)])
def test_build_county_boundaries_one_record_per_county(
    tmp_path: Path, fips: str, n_counties: int
) -> None:
    real_scores = _COMPOSITE / fips / "county_scores.parquet"
    if not real_scores.exists():
        pytest.skip(f"composite/{fips} not on disk")

    (tmp_path / fips).mkdir(parents=True)
    shutil.copy(real_scores, tmp_path / fips / "county_scores.parquet")

    out = build_county_boundaries(fips, composite_root=tmp_path)
    assert out == tmp_path / fips / "county_boundaries.geojson"

    fc = json.loads(out.read_text())
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == n_counties

    # County FIPS are unique — exactly one record per county.
    fips_seen = [f["properties"]["county_fips"] for f in fc["features"]]
    assert len(set(fips_seen)) == n_counties
    assert all(c.startswith(fips) for c in fips_seen)

    # The distress join landed — every feature carries the score fields.
    props = fc["features"][0]["properties"]
    for field in ("county_fips", "county_name", "tier", "persistent_poverty"):
        assert field in props
