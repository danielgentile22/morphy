"""Data-sync contract for the hosted composite (PRD #96, Module D).

The deploy step mirrors only the *served* composite — the files the map app
fetches under ``/data/processed/composite/...`` — to the Fly volume. It must
exclude the per-county ``parcels/`` compose-inputs (~8.43 GB the app never
fetches) while keeping the served ``parcels.pmtiles`` / ``parcels_attr.parquet``
tiles. A naive ``parcels*`` glob would wrongly drop the tiles; this module owns
the contract in one place so the bug can't slip in.

These unit tests drive a tiny fixture tree mirroring
``data/processed/composite/<fips>/…`` — never the real ~15 GB data.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sync_composite import iter_sync_files, rclone_filters, sync

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_composite.py"

# The pure contract (iter_sync_files) runs everywhere; the tests that drive a
# real sync need the rclone binary, so they skip where it's absent (e.g. CI).
requires_rclone = pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")


def _make_composite(root: Path) -> Path:
    """A minimal composite tree: top-level served indexes + two states, each
    with served files (incl. ``parcels.pmtiles``) and a ``parcels/`` dir of
    per-county compose-inputs that must NOT be synced."""
    root.mkdir(parents=True)
    for name in ("index.json", "owners_filter.json", "owners_index.json"):
        (root / name).write_text("{}")
    for fips in ("05", "30"):
        state = root / fips
        state.mkdir()
        for name in (
            "catalog.json",
            "facets.json",
            "county_boundaries.geojson",
            "parcels.pmtiles",
            "parcels_attr.parquet",
        ):
            (state / name).write_text("x")
        compose_inputs = state / "parcels"
        compose_inputs.mkdir()
        for county in ("001", "003"):
            (compose_inputs / f"{fips}{county}.geojson").write_text("compose-input")
    return root


def test_parcels_compose_inputs_excluded_but_pmtiles_kept(tmp_path: Path) -> None:
    src = _make_composite(tmp_path / "composite")

    synced = set(iter_sync_files(src))

    # The served vector tile is kept...
    assert Path("05/parcels.pmtiles") in synced
    # ...while the per-county compose-inputs directory is dropped wholesale.
    assert Path("05/parcels/05001.geojson") not in synced


def test_exfat_sidecars_never_synced(tmp_path: Path) -> None:
    src = _make_composite(tmp_path / "composite")
    (src / "05" / "._facets.json").write_text("appledouble")

    synced = set(iter_sync_files(src))

    assert Path("05/facets.json") in synced
    assert Path("05/._facets.json") not in synced
    assert "- ._*" in rclone_filters()


def _files_under(root: Path) -> set[Path]:
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


@requires_rclone
def test_sync_mirrors_exactly_the_predicted_served_set(tmp_path: Path) -> None:
    # Seam: the real rclone run must land exactly the set the pure contract
    # predicts — proving the rclone filters and ``iter_sync_files`` can't drift.
    src = _make_composite(tmp_path / "src")
    dst = tmp_path / "dst"

    sync(src, dst)

    assert _files_under(dst) == set(iter_sync_files(src))
    assert not (dst / "05" / "parcels").exists()  # compose-inputs never shipped


@requires_rclone
def test_second_sync_is_a_noop(tmp_path: Path) -> None:
    # A re-sync after an unchanged recompose must transfer nothing — refreshing
    # source data stays low-effort and safe to retry (PRD user story 12).
    src = _make_composite(tmp_path / "src")
    dst = tmp_path / "dst"
    sync(src, dst)

    result = sync(src, dst)

    assert result.transferred == 0


@requires_rclone
def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    src = _make_composite(tmp_path / "src")
    dst = tmp_path / "dst"

    sync(src, dst, dry_run=True)

    # Nothing landed: the destination tree is still empty (or never created).
    assert _files_under(dst) == set()


@requires_rclone
def test_mirror_deletes_files_absent_at_source(tmp_path: Path) -> None:
    # Mirror semantics (the chosen delete mode): a file the recompose dropped
    # must not linger on the volume.
    src = _make_composite(tmp_path / "src")
    dst = tmp_path / "dst"
    sync(src, dst)
    stale = dst / "99" / "dropped_state.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale")

    result = sync(src, dst)  # delete=True by default → mirror

    assert not stale.exists()
    assert result.deleted == 1


@requires_rclone
def test_additive_copy_keeps_files_absent_at_source(tmp_path: Path) -> None:
    src = _make_composite(tmp_path / "src")
    dst = tmp_path / "dst"
    sync(src, dst)
    extra = dst / "99" / "kept.json"
    extra.parent.mkdir(parents=True)
    extra.write_text("keep me")

    sync(src, dst, delete=False)  # copy → additive, never deletes

    assert extra.exists()


@requires_rclone
def test_cli_syncs_one_leg(tmp_path: Path) -> None:
    # deploy.sh shells out to this entry point per leg (laptop→R2, R2→volume).
    src = _make_composite(tmp_path / "src")
    dst = tmp_path / "dst"

    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), str(src), str(dst)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert _files_under(dst) == set(iter_sync_files(src))
