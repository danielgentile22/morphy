"""Headless manual-install engine (#237): layout, zip safety, manifest stamp."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

import pytest
from fetch import storage as storage_mod
from fetch.install import install_files, mark_manual_install, overwrite_conflicts
from fetch.manifest import Manifest


@dataclass
class Src:
    id: str = "src1"
    update_cadence_days: int | None = 90


@pytest.fixture
def raw_root(monkeypatch, tmp_path) -> Path:
    root = tmp_path / "raw"
    monkeypatch.setattr(storage_mod, "RAW_ROOT", root)
    return root


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return path


def test_install_copies_files_and_extracts_zip_into_subfolder(raw_root, tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("x")
    zp = _zip(tmp_path / "bundle.zip", {"inner/one.txt": b"1", "two.txt": b"2"})

    copied, extracted, errors = install_files("src1", [f, zp])

    assert (copied, extracted, errors) == (1, 2, [])
    cur = raw_root / "src1" / "current"
    assert (cur / "a.csv").read_text() == "x"
    # Zip lands in a same-named subfolder — the old Qt upload convention.
    assert (cur / "bundle" / "inner" / "one.txt").read_bytes() == b"1"
    assert (cur / "bundle" / "two.txt").exists()


def test_install_zip_preserved_when_extract_disabled(raw_root, tmp_path):
    zp = _zip(tmp_path / "bundle.zip", {"x.txt": b"1"})

    copied, extracted, errors = install_files("src1", [zp], extract_zips=False)

    assert (copied, extracted, errors) == (1, 0, [])
    assert (raw_root / "src1" / "current" / "bundle.zip").exists()


def test_traversal_zip_rejected(raw_root, tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../pwned.txt", b"x")

    copied, extracted, errors = install_files("src1", [evil])

    assert extracted == 0
    assert errors and "unsafe path" in errors[0]
    assert not (raw_root / "src1" / "current" / "pwned.txt").exists()


def test_overwrite_conflicts_respects_extract_mode(raw_root, tmp_path):
    cur = raw_root / "src1" / "current"
    cur.mkdir(parents=True)
    (cur / "a.csv").write_text("old")
    (cur / "b.zip").write_text("old")
    f = tmp_path / "a.csv"
    f.write_text("new")
    zp = _zip(tmp_path / "b.zip", {"x.txt": b"1"})

    # Extracting: the zip file itself is never written, so only a.csv conflicts.
    assert overwrite_conflicts("src1", [f, zp]) == ["a.csv"]
    assert set(overwrite_conflicts("src1", [f, zp], extract_zips=False)) == {"a.csv", "b.zip"}


def test_mark_manual_install_stamps_and_clears_failure(raw_root, tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("data")
    install_files("src1", [f])

    manifest = Manifest()
    entry = manifest.entry("src1")
    entry.status = "fetch_failed"
    entry.error = "HTTP 500"

    mark_manual_install(Src(), manifest)

    assert entry.local_version == "manual"
    assert entry.status == "ok"
    assert entry.error is None
    assert entry.bytes == 4
    assert len(entry.files) == 1 and entry.files[0].endswith("a.csv")
    assert entry.fetched_at is not None and entry.checked_at == entry.fetched_at
    assert entry.update_cadence_days == 90
    assert entry.next_recommended_check_at is not None


def test_mark_manual_install_without_cadence(raw_root, tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("data")
    install_files("src1", [f])
    manifest = Manifest()

    mark_manual_install(Src(update_cadence_days=None), manifest)

    assert manifest.entry("src1").next_recommended_check_at is None
