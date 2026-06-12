"""Interim off-site backup of the credentials file (PRD #130, stage 1).

Litestream replicates the SQLite DB to R2 but not ``users.txt`` — until
credentials move into the app database, the file is the only irreplaceable
state a volume loss would not recover. ``scripts/backup_users.sh`` copies it
off-site on a loop; these tests drive its one-shot mode (``--once``) against a
local-path destination (rclone treats a plain path as its local backend, so no
remote config is needed) and pin the externally observable contract:

  * a configured run copies the file to the destination, byte-for-byte;
  * a re-run after an edit refreshes the destination (the loop converges);
  * unconfigured (no destination derivable) exits 0 without writing anything,
    so a local/dev process tree never crash-loops;
  * a missing source file exits 0 without creating a destination.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backup_users.sh"

requires_rclone = pytest.mark.skipif(shutil.which("rclone") is None, reason="rclone not installed")


def _run_once(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    # Strip any ambient backup/litestream config so the test env is hermetic.
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("USERS_FILE", "USERS_BACKUP_DEST", "LITESTREAM_BUCKET")
    }
    env.update(env_overrides)
    return subprocess.run(
        ["bash", str(_SCRIPT), "--once"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@requires_rclone
def test_a_configured_run_copies_the_file_offsite(tmp_path: Path) -> None:
    src = tmp_path / "users.txt"
    src.write_text("alice:$fake$hash:acme\n", encoding="utf-8")
    dest = tmp_path / "offsite" / "users.txt"

    proc = _run_once({"USERS_FILE": str(src), "USERS_BACKUP_DEST": str(dest)})

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


@requires_rclone
def test_a_rerun_after_an_edit_refreshes_the_backup(tmp_path: Path) -> None:
    src = tmp_path / "users.txt"
    src.write_text("alice:$fake$hash:acme\n", encoding="utf-8")
    dest = tmp_path / "offsite" / "users.txt"
    env = {"USERS_FILE": str(src), "USERS_BACKUP_DEST": str(dest)}

    assert _run_once(env).returncode == 0
    src.write_text("alice:$fake$hash:acme\nbob:$fake$hash2:acme\n", encoding="utf-8")
    assert _run_once(env).returncode == 0

    assert dest.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_unconfigured_run_exits_zero_and_writes_nothing(tmp_path: Path) -> None:
    src = tmp_path / "users.txt"
    src.write_text("alice:$fake$hash:acme\n", encoding="utf-8")

    proc = _run_once({"USERS_FILE": str(src)})  # no dest, no LITESTREAM_BUCKET

    assert proc.returncode == 0
    assert "no destination" in proc.stdout
    # Nothing appeared next to the source (the only writable place it knows).
    assert sorted(p.name for p in tmp_path.iterdir()) == ["users.txt"]


@requires_rclone
def test_a_missing_source_file_exits_zero_without_a_destination(tmp_path: Path) -> None:
    dest = tmp_path / "offsite" / "users.txt"

    proc = _run_once(
        {"USERS_FILE": str(tmp_path / "does-not-exist.txt"), "USERS_BACKUP_DEST": str(dest)}
    )

    assert proc.returncode == 0
    assert not dest.exists()
