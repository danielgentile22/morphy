"""Repo-level guard: credential material must never be committed (#84 →
ADR-069).

Credentials live in the app database (the ``credential`` table holds password
hashes), so the DB file must never be tracked; legacy ``users.txt`` files may
still exist on dev machines and the prod volume, so the file-era guard stays
as hygiene. Only the fake-entry ``users.txt.example`` (the ``import-file``
format doc) is committed. This test fails the suite if any of that is ever
broken (an accidental ``git add -f``, a .gitignore edit, or a credential
store created under a tracked path).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:  # pragma: no cover - environment without git
        pytest.skip("git not available")


def test_the_legacy_credentials_file_is_git_ignored() -> None:
    # check-ignore exits 0 when the path IS ignored.
    assert _git("check-ignore", "-q", "backend/users.txt").returncode == 0, (
        "backend/users.txt must be listed in .gitignore"
    )


def test_no_credentials_file_is_tracked_anywhere() -> None:
    tracked = _git("ls-files").stdout.splitlines()
    offenders = [p for p in tracked if Path(p).name == "users.txt"]
    assert offenders == [], f"a legacy credentials file is committed: {offenders}"


def test_no_sqlite_database_is_tracked_anywhere() -> None:
    # The DB-era guard (ADR-069): the app database carries the credential
    # table (password hashes) plus tenant lead data — it must never be
    # committed, under any name or path.
    tracked = _git("ls-files").stdout.splitlines()
    offenders = [p for p in tracked if p.endswith((".sqlite3", ".sqlite", ".db"))]
    assert offenders == [], f"a database file is committed: {offenders}"


def test_the_example_file_documents_the_import_format() -> None:
    example = REPO_ROOT / "backend" / "users.txt.example"
    assert example.is_file(), "backend/users.txt.example (the import-file format doc) is missing"
    text = example.read_text()
    # It must document the line shape, and must never contain a real-looking
    # credential (every example hash is tagged as fake).
    assert "username" in text and ":" in text
    for line in text.splitlines():
        if line.strip() and not line.strip().startswith("#"):
            assert "EXAMPLE" in line, "example entries must be obviously fake"
