"""Tests for scripts/preprocess/app_assets.py — the composite/index.json writer.

The index writer is load-bearing for the map app's boot: the app reads
composite/index.json to learn which states are composed. These tests run
against tiny on-disk fixtures (a temp composite root with fake state
directories), never the real ~15 GB data tree.
"""

from __future__ import annotations

import json
from pathlib import Path

from preprocess.app_assets import (
    EXCLUDED_FIPS,
    INDEX_SCHEMA_VERSION,
    build_index,
    write_composite_index,
)
from preprocess.geographies import get_state


def _make_state_dir(
    composite_root: Path,
    fips: str,
    *,
    catalog: bool = True,
    counts: dict | None = None,
) -> Path:
    """Create a minimal fake composite/<fips>/ directory.

    ``catalog`` controls whether catalog.json exists (its presence is the
    "this state is composed" signal). ``counts`` controls summary.json.
    """
    d = composite_root / fips
    d.mkdir(parents=True, exist_ok=True)
    if catalog:
        (d / "catalog.json").write_text(json.dumps({"state_fips": fips, "layers": {}}))
    if counts is not None:
        (d / "summary.json").write_text(json.dumps({"counts": counts}))
    return d


def test_build_index_basic(tmp_path: Path) -> None:
    _make_state_dir(tmp_path, "05", counts={"parcel": 100, "tower": 7})
    index = build_index(tmp_path)

    assert index["schema_version"] == INDEX_SCHEMA_VERSION
    assert "generated_at" in index
    assert len(index["states"]) == 1

    st = index["states"][0]
    assert st["fips"] == "05"
    assert st["abbr"] == "AR"
    assert st["name"] == "Arkansas"
    # bbox comes from geographies.get_state — the authoritative envelope.
    assert st["bbox"] == list(get_state("05").bbox)
    assert st["counts"] == {"parcel": 100, "tower": 7}


def test_build_index_excludes_fips_18(tmp_path: Path) -> None:
    # Indiana (18) is kept on disk but must never surface in the app.
    _make_state_dir(tmp_path, "05", counts={"parcel": 1})
    _make_state_dir(tmp_path, "18", counts={"parcel": 999})
    index = build_index(tmp_path)

    fips_listed = {s["fips"] for s in index["states"]}
    assert "18" not in fips_listed
    assert "05" in fips_listed
    assert "18" in EXCLUDED_FIPS


def test_build_index_skips_dir_without_catalog(tmp_path: Path) -> None:
    # A directory with no catalog.json is an incomplete compose — skip it.
    _make_state_dir(tmp_path, "05", catalog=False, counts={"parcel": 1})
    index = build_index(tmp_path)
    assert index["states"] == []


def test_build_index_skips_unknown_fips(tmp_path: Path) -> None:
    # A directory name that is not a real FIPS must not crash the scan.
    _make_state_dir(tmp_path, "99", counts={"parcel": 1})
    _make_state_dir(tmp_path, "05", counts={"parcel": 1})
    index = build_index(tmp_path)
    assert {s["fips"] for s in index["states"]} == {"05"}


def test_build_index_missing_summary_yields_empty_counts(tmp_path: Path) -> None:
    _make_state_dir(tmp_path, "05", counts=None)  # catalog.json but no summary.json
    index = build_index(tmp_path)
    assert index["states"][0]["counts"] == {}


def test_build_index_corrupt_summary_yields_empty_counts(tmp_path: Path) -> None:
    d = _make_state_dir(tmp_path, "05", counts=None)
    (d / "summary.json").write_text("{ this is not valid json")
    index = build_index(tmp_path)
    assert index["states"][0]["counts"] == {}


def test_build_index_sorted_by_name(tmp_path: Path) -> None:
    # 30 = Montana, 05 = Arkansas — output must be alphabetical by name,
    # not by FIPS (so the state selector reads naturally).
    _make_state_dir(tmp_path, "30", counts={"parcel": 1})
    _make_state_dir(tmp_path, "05", counts={"parcel": 1})
    index = build_index(tmp_path)
    assert [s["name"] for s in index["states"]] == ["Arkansas", "Montana"]


def test_build_index_empty_root(tmp_path: Path) -> None:
    assert build_index(tmp_path)["states"] == []


def test_build_index_nonexistent_root(tmp_path: Path) -> None:
    assert build_index(tmp_path / "nope")["states"] == []


def test_build_index_ignores_non_int_counts(tmp_path: Path) -> None:
    # summary.json counts can carry odd values — only ints are kept.
    _make_state_dir(tmp_path, "05", counts={"parcel": 5, "bad": None, "also_bad": "x"})
    index = build_index(tmp_path)
    assert index["states"][0]["counts"] == {"parcel": 5}


def test_write_composite_index_writes_valid_json(tmp_path: Path) -> None:
    _make_state_dir(tmp_path, "05", counts={"parcel": 5})
    out = write_composite_index(composite_root=tmp_path)

    assert out == tmp_path / "index.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["schema_version"] == INDEX_SCHEMA_VERSION
    assert len(data["states"]) == 1
    assert data["states"][0]["fips"] == "05"


def test_write_composite_index_leaves_no_temp_files(tmp_path: Path) -> None:
    # The atomic write must clean up after itself — no .index.*.tmp left.
    _make_state_dir(tmp_path, "05", counts={"parcel": 5})
    write_composite_index(composite_root=tmp_path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".index.")]
    assert leftovers == []


def test_write_composite_index_overwrites(tmp_path: Path) -> None:
    _make_state_dir(tmp_path, "05", counts={"parcel": 5})
    write_composite_index(composite_root=tmp_path)
    # Add a second state and rewrite — the index reflects current disk.
    _make_state_dir(tmp_path, "30", counts={"parcel": 9})
    out = write_composite_index(composite_root=tmp_path)
    data = json.loads(out.read_text())
    assert {s["fips"] for s in data["states"]} == {"05", "30"}
